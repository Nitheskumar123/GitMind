"""
Conflict Detector - Pre-emptive PR conflict detection engine.
Uses layered detection: AST analysis → symbol graph → AI verification (ambiguous only).
"""

import logging
from collections import defaultdict
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)


class ConflictDetector:
    """Detects conflicts between open PRs using a layered approach."""

    def __init__(self, repository, access_token=None):
        self.repository = repository
        self.access_token = access_token

    def analyze_pr_conflicts(self, pr):
        """
        Main entry point: analyze a PR for conflicts against all other open PRs.
        Returns list of detected conflicts.
        """
        from .models import PullRequest, ConflictDetection, SymbolMap
        from .symbol_analyzer import SymbolAnalyzer
        from .github_api import GitHubAPIClient

        analyzer = SymbolAnalyzer()
        conflicts = []

        # 1. Build symbol map for this PR
        pr_symbols = self._build_pr_symbol_map(pr, analyzer)
        pr_files = set(s['file_path'] for s in pr_symbols)

        # 2. Get all other open PRs in the same repository
        other_prs = PullRequest.objects.filter(
            repository=self.repository,
            state='open'
        ).exclude(id=pr.id)

        if not other_prs.exists():
            logger.info(f"No other open PRs to compare for PR #{pr.number}")
            return conflicts

        # 3. Compare with each open PR
        for other_pr in other_prs:
            other_symbols = self._get_cached_symbols(other_pr)
            if not other_symbols:
                other_symbols = self._build_pr_symbol_map(other_pr, analyzer)

            other_files = set(s['file_path'] for s in other_symbols)

            # Step 1: File-level overlap (deterministic)
            file_conflicts = self.detect_file_conflicts(pr_files, other_files)

            # Step 2: Function-level conflicts (deterministic)
            function_conflicts = self.detect_function_conflicts(pr_symbols, other_symbols)

            # Step 3: Symbol-level conflicts (deterministic)
            symbol_conflicts = self.detect_symbol_conflicts(pr_symbols, other_symbols)

            # Step 4: Dependency conflicts (deterministic)
            dep_conflicts = self.detect_dependency_conflicts(pr_symbols, other_symbols)

            # Combine all detected conflicts
            all_detected = file_conflicts + function_conflicts + symbol_conflicts + dep_conflicts

            if all_detected:
                # Calculate severity deterministically
                severity = self.calculate_severity(all_detected)

                # Step 5: AI verification ONLY for ambiguous severity
                if severity == 'medium':
                    ai_severity = self.ai_verify_severity(pr, other_pr, all_detected)
                    if ai_severity:
                        severity = ai_severity

                # Determine conflict type (use the highest-priority type found)
                conflict_type = self._determine_primary_conflict_type(all_detected)

                # Create or update conflict record
                conflict = self._save_conflict(
                    pr, other_pr, conflict_type, severity, all_detected
                )
                conflicts.append(conflict)

        # Generate merge order across all conflicting PRs
        if conflicts:
            merge_order = self.suggest_merge_order(conflicts)
            for conflict in conflicts:
                conflict.merge_order = merge_order
                conflict.save()

        return conflicts

    def detect_file_conflicts(self, pr1_files, pr2_files):
        """Detect overlapping file modifications."""
        overlapping = pr1_files & pr2_files
        conflicts = []
        for file_path in overlapping:
            conflicts.append({
                'type': 'file_level',
                'file': file_path,
                'description': f"Both PRs modify {file_path}",
            })
        return conflicts

    def detect_function_conflicts(self, pr1_symbols, pr2_symbols):
        """Detect same function modified in both PRs."""
        conflicts = []

        pr1_funcs = {(s['file_path'], s['name']): s for s in pr1_symbols if s['type'] == 'function'}
        pr2_funcs = {(s['file_path'], s['name']): s for s in pr2_symbols if s['type'] == 'function'}

        for key in set(pr1_funcs.keys()) & set(pr2_funcs.keys()):
            f1 = pr1_funcs[key]
            f2 = pr2_funcs[key]

            # Check if they modify the same lines (overlapping ranges)
            overlap = self._line_ranges_overlap(
                f1['line_start'], f1['line_end'],
                f2['line_start'], f2['line_end']
            )

            # Check if signatures differ
            sig_diff = f1.get('signature') != f2.get('signature')

            # Check if content changed differently
            hash_diff = f1.get('hash') and f2.get('hash') and f1['hash'] != f2['hash']

            if overlap or sig_diff or hash_diff:
                conflict_detail = {
                    'type': 'function_level',
                    'file': key[0],
                    'symbol': key[1],
                    'description': f"Both PRs modify function {key[1]} in {key[0]}",
                    'line_range_pr1': [f1['line_start'], f1['line_end']],
                    'line_range_pr2': [f2['line_start'], f2['line_end']],
                    'signature_conflict': sig_diff,
                }
                if sig_diff:
                    conflict_detail['pr1_signature'] = f1.get('signature', {})
                    conflict_detail['pr2_signature'] = f2.get('signature', {})
                conflicts.append(conflict_detail)

        return conflicts

    def detect_symbol_conflicts(self, pr1_symbols, pr2_symbols):
        """Detect renamed/deleted symbols used in the other PR."""
        conflicts = []

        pr1_names = {s['name'] for s in pr1_symbols if s['type'] in ('class', 'variable')}
        pr2_names = {s['name'] for s in pr2_symbols if s['type'] in ('class', 'variable')}

        # Symbols in PR1 but not PR2 (potentially renamed/removed)
        pr1_only = pr1_names - pr2_names
        pr2_only = pr2_names - pr1_names

        # Check if removed symbols are used as imports in the other PR
        pr1_imports = {s['name'].split('.')[-1] for s in pr1_symbols if s['type'] == 'import'}
        pr2_imports = {s['name'].split('.')[-1] for s in pr2_symbols if s['type'] == 'import'}

        for sym_name in pr1_only:
            if sym_name in pr2_imports:
                conflicts.append({
                    'type': 'symbol_level',
                    'symbol': sym_name,
                    'description': f"Symbol '{sym_name}' modified in PR1 but imported in PR2",
                })

        for sym_name in pr2_only:
            if sym_name in pr1_imports:
                conflicts.append({
                    'type': 'symbol_level',
                    'symbol': sym_name,
                    'description': f"Symbol '{sym_name}' modified in PR2 but imported in PR1",
                })

        return conflicts

    def detect_dependency_conflicts(self, pr1_symbols, pr2_symbols):
        """Detect dependency version conflicts in requirements files."""
        conflicts = []

        # Look for import changes to same packages
        pr1_imports = {s['name']: s for s in pr1_symbols if s['type'] == 'import'}
        pr2_imports = {s['name']: s for s in pr2_symbols if s['type'] == 'import'}

        # Check for conflicting imports from same module
        for name in set(pr1_imports.keys()) & set(pr2_imports.keys()):
            if pr1_imports[name].get('hash') != pr2_imports[name].get('hash'):
                conflicts.append({
                    'type': 'dependency',
                    'symbol': name,
                    'description': f"Both PRs modify import of {name}",
                })

        return conflicts

    def calculate_severity(self, conflicts):
        """Calculate severity from detected conflicts without AI."""
        score = 0
        type_weights = {
            'file_level': 1,
            'function_level': 3,
            'symbol_level': 4,
            'semantic': 5,
            'dependency': 4,
        }

        for conflict in conflicts:
            score += type_weights.get(conflict['type'], 1)

            # Bonus for signature conflicts
            if conflict.get('signature_conflict'):
                score += 3

        if score >= 10:
            return 'critical'
        elif score >= 6:
            return 'high'
        elif score >= 3:
            return 'medium'
        return 'low'

    def ai_verify_severity(self, pr1, pr2, conflicts):
        """Use Groq AI ONLY for ambiguous severity verification."""
        try:
            groq_api_key = getattr(settings, 'GROQ_API_KEY', '')
            if not groq_api_key:
                return None

            from groq import Groq
            client = Groq(api_key=groq_api_key)

            conflict_summary = "\n".join([
                f"- {c['type']}: {c['description']}" for c in conflicts[:10]
            ])

            prompt = f"""Given these code conflicts between PR #{pr1.number} ("{pr1.title}") and PR #{pr2.number} ("{pr2.title}"):

{conflict_summary}

Rate the severity as exactly one of: low, medium, high, critical
Consider: Will these conflicts break at runtime? Are they just style conflicts?
Respond with ONLY the severity word."""

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=10,
            )

            severity = response.choices[0].message.content.strip().lower()
            if severity in ('low', 'medium', 'high', 'critical'):
                return severity
            return None

        except Exception as e:
            logger.error(f"AI severity verification failed: {e}")
            return None

    def suggest_merge_order(self, conflicts):
        """
        Suggest optimal merge order using topological sort (Kahn's algorithm).
        Earlier PRs should generally merge first.
        """
        from collections import deque

        # Build DAG: edges from PR that should merge first → PR that should merge after
        graph = defaultdict(set)
        in_degree = defaultdict(int)
        all_prs = set()

        for conflict in conflicts:
            pr1 = conflict.pr_1
            pr2 = conflict.pr_2
            all_prs.add(pr1.number)
            all_prs.add(pr2.number)

            # Heuristic: older PR merges first (lower PR number = created earlier)
            if pr1.number < pr2.number:
                first, second = pr1.number, pr2.number
            else:
                first, second = pr2.number, pr1.number

            if second not in graph[first]:
                graph[first].add(second)
                in_degree[second] = in_degree.get(second, 0) + 1
                if first not in in_degree:
                    in_degree[first] = in_degree.get(first, 0)

        # Kahn's algorithm
        queue = deque([pr for pr in all_prs if in_degree.get(pr, 0) == 0])
        order = []

        while queue:
            pr = queue.popleft()
            order.append(pr)
            for neighbor in graph.get(pr, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # If cycle detected, fallback to simple ordering
        if len(order) != len(all_prs):
            order = sorted(all_prs)

        return order

    # --- Private helpers ---

    def _build_pr_symbol_map(self, pr, analyzer):
        """Build symbol map for a PR from its changed files."""
        from .models import SymbolMap
        from .github_api import GitHubAPIClient

        symbols = []
        try:
            client = GitHubAPIClient(self.access_token or self.repository.user.github_access_token)
            files = client.get_pull_request_files(self.repository.full_name, pr.number)

            for file_info in (files or []):
                filename = file_info.get('filename', '')
                if not filename.endswith(('.py', '.js', '.jsx', '.ts', '.tsx')):
                    continue

                patch = file_info.get('patch', '')
                if not patch:
                    continue

                # Try to get full file content
                try:
                    content = client.get_file_content(self.repository.full_name, filename, pr.head_sha if hasattr(pr, 'head_sha') else None)
                    if content:
                        file_symbols = analyzer.parse_file(content, filename)
                        symbols.extend(file_symbols)

                        # Cache symbols in DB
                        for sym in file_symbols:
                            SymbolMap.objects.update_or_create(
                                repository=self.repository,
                                pull_request=pr,
                                file_path=sym['file_path'],
                                symbol_name=sym['name'],
                                defaults={
                                    'symbol_type': sym['type'],
                                    'line_start': sym['line_start'],
                                    'line_end': sym['line_end'],
                                    'signature': sym.get('signature', {}),
                                    'hash': sym.get('hash', ''),
                                    'dependencies': sym.get('dependencies', []),
                                    'dependents': sym.get('dependents', []),
                                }
                            )
                except Exception as e:
                    logger.warning(f"Could not get content for {filename}: {e}")
                    # Fallback: extract symbols from patch
                    patch_symbols = analyzer.parse_file(patch, filename)
                    symbols.extend(patch_symbols)

        except Exception as e:
            logger.error(f"Error building symbol map for PR #{pr.number}: {e}")

        return symbols

    def _get_cached_symbols(self, pr):
        """Get cached symbols from database."""
        from .models import SymbolMap

        cached = SymbolMap.objects.filter(pull_request=pr)
        if not cached.exists():
            return None

        return [{
            'type': sym.symbol_type,
            'name': sym.symbol_name,
            'file_path': sym.file_path,
            'line_start': sym.line_start,
            'line_end': sym.line_end,
            'signature': sym.signature,
            'hash': sym.hash,
            'dependencies': sym.dependencies,
            'dependents': sym.dependents,
        } for sym in cached]

    def _line_ranges_overlap(self, start1, end1, start2, end2):
        """Check if two line ranges overlap."""
        return start1 <= end2 and start2 <= end1

    def _determine_primary_conflict_type(self, conflicts):
        """Determine the most severe conflict type from detected conflicts."""
        priority = ['semantic', 'symbol_level', 'function_level', 'dependency', 'file_level']
        types_found = {c['type'] for c in conflicts}
        for t in priority:
            if t in types_found:
                return t
        return 'file_level'

    def _save_conflict(self, pr1, pr2, conflict_type, severity, conflict_details):
        """Save or update conflict detection record."""
        from .models import ConflictDetection

        # Normalize PR order (lower number first)
        if pr1.number > pr2.number:
            pr1, pr2 = pr2, pr1

        affected_files = list(set(
            c.get('file', '') for c in conflict_details if c.get('file')
        ))
        conflicting_symbols = [
            {
                'symbol_name': c.get('symbol', c.get('file', '')),
                'type': c['type'],
                'description': c['description'],
                'line_range_pr1': c.get('line_range_pr1', []),
                'line_range_pr2': c.get('line_range_pr2', []),
            }
            for c in conflict_details
        ]

        # Generate resolution suggestion
        suggestion = self._generate_resolution_suggestion(pr1, pr2, conflict_type, severity)

        conflict, created = ConflictDetection.objects.update_or_create(
            pr_1=pr1,
            pr_2=pr2,
            defaults={
                'conflict_type': conflict_type,
                'severity': severity,
                'affected_files': affected_files,
                'conflicting_symbols': conflicting_symbols,
                'resolution_suggestion': suggestion,
                'is_resolved': False,
            }
        )

        return conflict

    def _generate_resolution_suggestion(self, pr1, pr2, conflict_type, severity):
        """Generate a resolution suggestion based on conflict type and severity."""
        suggestions = {
            'file_level': f"Both PR #{pr1.number} and #{pr2.number} modify the same files. "
                          f"Coordinate merge order. Merge PR #{pr1.number} first (older), "
                          f"then rebase PR #{pr2.number}.",
            'function_level': f"PR #{pr1.number} and #{pr2.number} modify the same functions. "
                              f"Merge PR #{pr1.number} first, then update PR #{pr2.number} "
                              f"to account for the changed function signatures.",
            'symbol_level': f"Symbol conflicts detected between PR #{pr1.number} and #{pr2.number}. "
                            f"One PR renames/removes symbols used in the other. "
                            f"Coordinate to ensure both PRs reference the same API.",
            'semantic': f"Semantic conflict: PRs #{pr1.number} and #{pr2.number} change the same "
                        f"behavior. Review both PRs together to ensure compatible changes.",
            'dependency': f"Dependency version conflict between PR #{pr1.number} and #{pr2.number}. "
                          f"Agree on a single version before merging either PR.",
        }

        return suggestions.get(conflict_type, f"Conflicts detected. Review PRs #{pr1.number} and #{pr2.number} together.")
