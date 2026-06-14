"""
Dependency Analyzer - Scans dependencies, fetches changelogs, calculates impact.
Uses version-diff scoring for automatic risk assessment.
"""

import re
import logging
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class DependencyAnalyzer:
    """Analyzes repository dependencies for breaking changes and impact."""

    def __init__(self, repository, access_token=None):
        self.repository = repository
        self.access_token = access_token or repository.user.github_access_token

    def analyze_all_dependencies(self):
        """
        Main entry point: parse requirements, fetch updates, analyze impact.
        Returns list of DependencyAnalysis records.
        """
        from .models import DependencyAnalysis
        from .github_api import GitHubAPIClient
        from .changelog_parser import ChangelogParser

        client = GitHubAPIClient(self.access_token)
        parser = ChangelogParser()

        # 1. Parse dependency files from the repository
        dependencies = self._fetch_and_parse_dependencies(client)
        if not dependencies:
            logger.info(f"No dependencies found for {self.repository.full_name}")
            return []

        results = []

        # 2. Analyze each dependency
        for dep in dependencies:
            try:
                analysis = self._analyze_single_dependency(dep, parser, client)
                if analysis:
                    results.append(analysis)
            except Exception as e:
                logger.error(f"Error analyzing {dep['name']}: {e}")

        return results

    def _fetch_and_parse_dependencies(self, client):
        """Fetch and parse dependency files from the repository."""
        dependencies = []

        # Try requirements.txt
        try:
            content = client.get_file_content(self.repository.full_name, 'requirements.txt')
            if content:
                deps = self.parse_requirements_file(content)
                dependencies.extend(deps)
        except Exception:
            pass

        # Try setup.py
        if not dependencies:
            try:
                content = client.get_file_content(self.repository.full_name, 'setup.py')
                if content:
                    deps = self._parse_setup_py(content)
                    dependencies.extend(deps)
            except Exception:
                pass

        # Try package.json
        if not dependencies:
            try:
                content = client.get_file_content(self.repository.full_name, 'package.json')
                if content:
                    deps = self.parse_package_json(content)
                    dependencies.extend(deps)
            except Exception:
                pass

        # Try Pipfile
        if not dependencies:
            try:
                content = client.get_file_content(self.repository.full_name, 'Pipfile')
                if content:
                    deps = self._parse_pipfile(content)
                    dependencies.extend(deps)
            except Exception:
                pass

        return dependencies

    def parse_requirements_file(self, content):
        """Parse Python requirements.txt format."""
        dependencies = []
        for line in content.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('-'):
                continue

            # Handle various formats: pkg==1.0, pkg>=1.0, pkg~=1.0, pkg
            match = re.match(r'^([a-zA-Z0-9_\-\.]+)\s*([><=~!]+)?\s*([0-9a-zA-Z\.\*\-]+)?', line)
            if match:
                name = match.group(1)
                version = match.group(3) or 'unknown'
                dependencies.append({
                    'name': name,
                    'current_version': version,
                    'ecosystem': 'pypi',
                })

        return dependencies

    def parse_package_json(self, content):
        """Parse npm package.json format."""
        import json
        dependencies = []

        try:
            data = json.loads(content)
            for section in ('dependencies', 'devDependencies'):
                for name, version in data.get(section, {}).items():
                    # Remove ^ or ~ prefix
                    clean_version = re.sub(r'^[\^~>=<]', '', version)
                    dependencies.append({
                        'name': name,
                        'current_version': clean_version,
                        'ecosystem': 'npm',
                    })
        except json.JSONDecodeError:
            pass

        return dependencies

    def _parse_setup_py(self, content):
        """Parse setup.py install_requires."""
        dependencies = []
        match = re.search(r'install_requires\s*=\s*\[(.*?)\]', content, re.DOTALL)
        if match:
            reqs = match.group(1)
            for line in reqs.split(','):
                line = line.strip().strip("'\"")
                if line:
                    pkg_match = re.match(r'^([a-zA-Z0-9_\-\.]+)\s*([><=~!]+)?\s*([0-9a-zA-Z\.\*\-]+)?', line)
                    if pkg_match:
                        dependencies.append({
                            'name': pkg_match.group(1),
                            'current_version': pkg_match.group(3) or 'unknown',
                            'ecosystem': 'pypi',
                        })
        return dependencies

    def _parse_pipfile(self, content):
        """Parse Pipfile [packages] section."""
        dependencies = []
        in_packages = False
        for line in content.split('\n'):
            line = line.strip()
            if line == '[packages]':
                in_packages = True
                continue
            elif line.startswith('['):
                in_packages = False
                continue
            if in_packages and '=' in line:
                parts = line.split('=', 1)
                name = parts[0].strip()
                version = parts[1].strip().strip('"\'').replace('*', 'unknown')
                if name:
                    dependencies.append({
                        'name': name,
                        'current_version': version,
                        'ecosystem': 'pypi',
                    })
        return dependencies

    def _analyze_single_dependency(self, dep, parser, client):
        """Analyze a single dependency: fetch latest version, changelog, calculate impact."""
        from .models import DependencyAnalysis

        package_name = dep['name']
        current_version = dep['current_version']
        ecosystem = dep.get('ecosystem', 'pypi')

        # Fetch package info
        if ecosystem == 'pypi':
            pkg_info = parser.fetch_from_pypi(package_name)
        elif ecosystem == 'npm':
            pkg_info = parser.fetch_from_npm(package_name)
        else:
            return None

        if not pkg_info:
            # Still create a record with minimal info
            analysis, _ = DependencyAnalysis.objects.update_or_create(
                repository=self.repository,
                package_name=package_name,
                defaults={
                    'current_version': current_version,
                    'latest_version': 'unknown',
                    'latest_safe_version': '',
                    'has_breaking_changes': False,
                    'impact_score': 0,
                }
            )
            return analysis

        latest_version = pkg_info.get('latest_version', '')

        # If already on latest, minimal analysis needed
        if current_version == latest_version:
            analysis, _ = DependencyAnalysis.objects.update_or_create(
                repository=self.repository,
                package_name=package_name,
                defaults={
                    'current_version': current_version,
                    'latest_version': latest_version,
                    'latest_safe_version': latest_version,
                    'has_breaking_changes': False,
                    'impact_score': 0,
                    'changelog_url': pkg_info.get('changelog_url') or '',
                }
            )
            return analysis

        # Fetch and parse changelog
        changelog_text = pkg_info.get('description') or ''
        changelog_url = pkg_info.get('changelog_url') or ''

        # Try to get GitHub releases if we have a repo URL
        github_repo = self._extract_github_repo(pkg_info)
        if github_repo:
            releases = parser.fetch_from_github(github_repo, current_version, latest_version)
            if releases:
                changelog_text = '\n\n'.join([
                    f"## {r['version']}\n{r['body']}" for r in releases
                ])

        # Parse changelog with AI
        changelog_data = parser.parse_with_ai(
            changelog_text, package_name, current_version, latest_version
        )

        breaking_changes = changelog_data.get('breaking_changes', [])

        # Scan codebase for affected patterns
        files_affected = []
        code_patterns_affected = []
        if breaking_changes:
            scan_results = self.scan_codebase_usage(package_name, breaking_changes, client)
            files_affected = scan_results.get('files', [])
            code_patterns_affected = scan_results.get('patterns', [])

        # Calculate impact score with version-diff scoring
        impact_score = self.calculate_impact_score(
            current_version, latest_version, breaking_changes, files_affected
        )

        # Find latest safe version (no breaking changes)
        latest_safe_version = self._find_safe_version(
            pkg_info.get('release_versions', []), current_version
        )

        # Estimate refactor time
        refactor_hours = self._estimate_refactor_time(breaking_changes, files_affected)

        # Generate migration script
        migration_script = self.generate_migration_script(code_patterns_affected)

        # Save analysis
        analysis, _ = DependencyAnalysis.objects.update_or_create(
            repository=self.repository,
            package_name=package_name,
            defaults={
                'current_version': current_version,
                'latest_version': latest_version,
                'latest_safe_version': latest_safe_version,
                'has_breaking_changes': len(breaking_changes) > 0,
                'breaking_changes': breaking_changes,
                'changelog_url': changelog_url,
                'impact_score': impact_score,
                'files_affected': files_affected,
                'code_patterns_affected': code_patterns_affected,
                'estimated_refactor_hours': refactor_hours,
                'migration_script': migration_script,
            }
        )

        return analysis

    def calculate_impact_score(self, current_version, latest_version, breaking_changes, files_affected):
        """
        Calculate impact score (0-100) using version-diff scoring.
        Major version bump = automatic +20.
        """
        score = 0

        # Version-diff scoring
        cur_parts = self._parse_version(current_version)
        lat_parts = self._parse_version(latest_version)

        if cur_parts and lat_parts:
            if lat_parts[0] > cur_parts[0]:
                score += 20  # Major version bump
            elif lat_parts[1] > cur_parts[1]:
                score += 5   # Minor version bump

        # Breaking changes scoring (each adds 15, capped at 60)
        score += min(len(breaking_changes) * 15, 60)

        # Files affected scoring (each adds 2, capped at 25)
        score += min(len(files_affected) * 2, 25)

        # Critical API changes bonus
        if any(
            bc.get('critical') or
            any(kw in str(bc.get('description', '')).lower()
                for kw in ['security', 'authentication', 'database', 'migration'])
            for bc in breaking_changes
        ):
            score += 15

        return min(score, 100)

    def scan_codebase_usage(self, package_name, breaking_changes, client):
        """Search repository files for deprecated patterns."""
        files_affected = []
        patterns_affected = []

        try:
            # Search for package usage in the repo
            search_query = f"{package_name} repo:{self.repository.full_name}"
            results = client.search_code(search_query)

            if results:
                files_affected = [item.get('path', '') for item in results[:20]]

            # Search for specific deprecated patterns mentioned in breaking changes
            for bc in breaking_changes[:5]:
                desc = bc.get('description', '')
                # Extract likely API names from the breaking change description
                api_names = re.findall(r'`([^`]+)`|\'([^\']+)\'|"([^"]+)"', desc)
                for groups in api_names:
                    for pattern in groups:
                        if pattern and len(pattern) > 2:
                            try:
                                search_results = client.search_code(
                                    f"{pattern} repo:{self.repository.full_name}"
                                )
                                if search_results:
                                    pattern_files = [r.get('path', '') for r in search_results[:10]]
                                    patterns_affected.append({
                                        'pattern': pattern,
                                        'replacement': bc.get('fix', ''),
                                        'files': pattern_files,
                                    })
                                    files_affected.extend(pattern_files)
                            except Exception:
                                pass

        except Exception as e:
            logger.warning(f"Codebase scan failed for {package_name}: {e}")

        return {
            'files': list(set(files_affected)),
            'patterns': patterns_affected,
        }

    def generate_migration_script(self, code_patterns):
        """Auto-generate find-and-replace migration script."""
        if not code_patterns:
            return ''

        lines = ['#!/bin/bash', '# Auto-generated migration script', '']

        for pattern in code_patterns:
            old = pattern.get('pattern', '')
            new = pattern.get('replacement', '')
            files = pattern.get('files', [])

            if old and new:
                lines.append(f'# Replace: {old} → {new}')
                lines.append(f'# Affected files: {", ".join(files[:5])}')
                # Generate sed command
                escaped_old = old.replace('/', '\\/')
                escaped_new = new.replace('/', '\\/')
                lines.append(
                    f'find . -name "*.py" -exec sed -i \'s/{escaped_old}/{escaped_new}/g\' {{}} +'
                )
                lines.append('')
            elif old:
                lines.append(f'# MANUAL REVIEW REQUIRED: {old}')
                lines.append(f'# Files: {", ".join(files[:5])}')
                lines.append(f'grep -rn "{old}" .')
                lines.append('')

        return '\n'.join(lines)

    def suggest_safe_upgrade_path(self, package_name):
        """Find the latest version without breaking changes."""
        from .changelog_parser import ChangelogParser
        parser = ChangelogParser()

        pkg_info = parser.fetch_from_pypi(package_name)
        if not pkg_info:
            return None

        versions = pkg_info.get('release_versions', [])
        current_analysis = self.repository.dependency_analyses.filter(
            package_name=package_name
        ).first()

        if not current_analysis:
            return pkg_info.get('latest_version', '')

        current_version = current_analysis.current_version
        cur_parts = self._parse_version(current_version)

        if not cur_parts:
            return pkg_info.get('latest_version', '')

        # Find latest version with same major version
        safe_versions = []
        for v in versions:
            v_parts = self._parse_version(v)
            if v_parts and v_parts[0] == cur_parts[0]:
                safe_versions.append(v)

        if safe_versions:
            return safe_versions[0]  # Already sorted descending
        return current_version

    # --- Helper methods ---

    def _parse_version(self, version_str):
        """Parse version string into tuple of ints."""
        if not version_str or version_str == 'unknown':
            return None
        match = re.match(r'(\d+)\.?(\d+)?\.?(\d+)?', version_str)
        if match:
            return tuple(int(x) if x else 0 for x in match.groups())
        return None

    def _extract_github_repo(self, pkg_info):
        """Extract GitHub repo name from package info URLs."""
        urls_to_check = [
            pkg_info.get('home_page', ''),
            pkg_info.get('repository', ''),
            pkg_info.get('project_url', ''),
        ]
        for url in urls_to_check:
            if url and 'github.com' in url:
                match = re.search(r'github\.com[/:]([^/]+/[^/\.\s]+)', url)
                if match:
                    return match.group(1).rstrip('.git')
        return None

    def _find_safe_version(self, versions, current_version):
        """Find latest version with same major version number."""
        cur_parts = self._parse_version(current_version)
        if not cur_parts:
            return ''

        for v in versions:
            v_parts = self._parse_version(v)
            if v_parts and v_parts[0] == cur_parts[0]:
                return v
        return current_version

    def _estimate_refactor_time(self, breaking_changes, files_affected):
        """Estimate refactor time in hours."""
        hours = 0
        hours += len(breaking_changes) * 1.5  # ~1.5 hours per breaking change
        hours += len(files_affected) * 0.25   # ~15 min per affected file
        return max(1, int(hours))
