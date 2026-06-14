"""
Phase 5: Code Ownership Analyzer
Determines file ownership and developer expertise from commit history.
Runs on onboarding or nightly Celery Beat — NOT on every webhook.
"""

import logging
from datetime import timedelta
from collections import defaultdict
from django.utils import timezone

logger = logging.getLogger(__name__)


class CodeOwnershipAnalyzer:
    """Analyze Git history to determine file ownership and developer expertise."""

    def analyze_repository(self, repository):
        """
        Full ownership analysis for a repository.
        Creates/updates CodeOwnership and DeveloperExpertise records.
        """
        try:
            from .github_api import GitHubAPIClient
            from .models import CodeOwnership, DeveloperExpertise, Commit

            user = repository.user
            client = GitHubAPIClient(user.github_access_token)

            # Get commits from our DB (already synced)
            commits = Commit.objects.filter(repository=repository).order_by('-committed_at')[:500]

            if not commits.exists():
                return {'success': True, 'files_analyzed': 0, 'developers_analyzed': 0}

            # Build ownership map: {file_path: {author: {commits, lines, last_date}}}
            ownership_map = defaultdict(lambda: defaultdict(lambda: {
                'commits': 0, 'lines': 0, 'last_date': None
            }))

            # Build developer map: {author: {commits, prs, files, domains, first, last}}
            developer_map = defaultdict(lambda: {
                'commits': 0, 'prs_authored': 0, 'files': set(),
                'domains': defaultdict(int), 'first': None, 'last': None, 'days': set(),
            })

            # Process commits
            for commit in commits:
                author = commit.author_login or commit.author_name or 'unknown'
                date = commit.committed_at

                # Developer tracking
                dev = developer_map[author]
                dev['commits'] += 1
                if date:
                    if dev['first'] is None or date < dev['first']:
                        dev['first'] = date
                    if dev['last'] is None or date > dev['last']:
                        dev['last'] = date
                    dev['days'].add(date.date())

                # Try to get changed files from commit via API
                try:
                    gh_commit = client.client.get_repo(repository.full_name).get_commit(commit.sha)
                    for f in gh_commit.files:
                        path = f.filename
                        ownership_map[path][author]['commits'] += 1
                        ownership_map[path][author]['lines'] += (f.additions + f.deletions)
                        if date:
                            existing = ownership_map[path][author]['last_date']
                            if existing is None or date > existing:
                                ownership_map[path][author]['last_date'] = date

                        dev['files'].add(path)
                        domain = self._infer_domain(path)
                        dev['domains'][domain] += 1
                except Exception:
                    continue

            # Save CodeOwnership records
            files_analyzed = 0
            for file_path, authors in ownership_map.items():
                # Find primary owner (most commits)
                primary = max(authors.items(), key=lambda x: x[1]['commits'])
                primary_owner = primary[0]
                total_commits = sum(a['commits'] for a in authors.values())
                total_lines = sum(a['lines'] for a in authors.values())

                # Expertise score: weighted by commits + recency
                max_score = max(a['commits'] for a in authors.values())
                expertise_score = min(100, int((max_score / max(total_commits, 1)) * 100))

                CodeOwnership.objects.update_or_create(
                    repository=repository,
                    file_path=file_path,
                    defaults={
                        'primary_owner': primary_owner,
                        'contributors': list(authors.keys()),
                        'commits_count': total_commits,
                        'lines_authored': total_lines,
                        'expertise_score': expertise_score,
                        'last_modified': primary[1]['last_date'] or timezone.now(),
                        'analyzed_at': timezone.now(),
                    },
                )
                files_analyzed += 1

            # Save DeveloperExpertise records
            developers_analyzed = 0
            for author, data in developer_map.items():
                expertise_map = {}
                total_domain = sum(data['domains'].values()) or 1
                for domain, count in data['domains'].items():
                    expertise_map[domain] = min(100, int((count / total_domain) * 100))

                DeveloperExpertise.objects.update_or_create(
                    repository=repository,
                    github_username=author,
                    defaults={
                        'expertise_areas': list(data['domains'].keys()),
                        'expertise_map': expertise_map,
                        'total_commits': data['commits'],
                        'total_prs_authored': data['prs_authored'],
                        'files_touched': list(data['files'])[:100],
                        'active_days': len(data['days']),
                        'first_contribution': data['first'],
                        'last_contribution': data['last'],
                        'analyzed_at': timezone.now(),
                    },
                )
                developers_analyzed += 1

            logger.info(
                f"Ownership analysis complete for {repository.full_name}: "
                f"{files_analyzed} files, {developers_analyzed} developers"
            )

            return {
                'success': True,
                'files_analyzed': files_analyzed,
                'developers_analyzed': developers_analyzed,
            }

        except Exception as e:
            logger.error(f"Ownership analysis failed for {repository.full_name}: {e}")
            return {'success': False, 'error': str(e)}

    def _infer_domain(self, file_path):
        """Infer expertise domain from file path."""
        path = file_path.lower()
        if any(p in path for p in ['test', 'spec', '__test__']):
            return 'testing'
        if any(p in path for p in ['frontend', 'src/components', 'src/pages', '.jsx', '.tsx', '.vue']):
            return 'frontend'
        if any(p in path for p in ['backend', 'api', 'views', 'models', 'serializers']):
            return 'backend'
        if any(p in path for p in ['.css', '.scss', '.less', '.styled']):
            return 'styling'
        if any(p in path for p in ['docker', 'ci', 'deploy', '.yml', '.yaml', 'terraform']):
            return 'devops'
        if any(p in path for p in ['docs', 'readme', '.md']):
            return 'documentation'
        if any(p in path for p in ['migration', 'schema', 'seeds']):
            return 'database'
        return 'general'
