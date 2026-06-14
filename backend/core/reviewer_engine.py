"""
Phase 5: Reviewer Recommendation Engine
Suggests reviewers based on code ownership and expertise.
Uses pre-computed CodeOwnership data — does NOT re-analyze the repo.
"""

import logging
from collections import defaultdict
from django.utils import timezone

logger = logging.getLogger(__name__)

# Configurable scoring weights
WEIGHTS = {
    'ownership': 0.40,
    'commits': 0.30,
    'recency': 0.20,
    'expertise': 0.10,
}


class ReviewerRecommendationEngine:
    """Recommend reviewers for a PR based on code ownership data."""

    def recommend_reviewers(self, pull_request):
        """
        Main entry point. Queries CodeOwnership records for files
        changed in the PR, scores candidates, and saves ReviewerRecommendation.
        """
        try:
            from .models import CodeOwnership, ReviewerRecommendation, DeveloperExpertise
            from .github_api import GitHubAPIClient

            repo = pull_request.repository
            user = repo.user

            # Get files changed in the PR
            client = GitHubAPIClient(user.github_access_token)
            changed_files = self._get_changed_files(client, repo.full_name, pull_request.number)

            if not changed_files:
                return {'success': True, 'recommendations': []}

            # Score candidates from CodeOwnership
            candidates = defaultdict(lambda: {
                'ownership_score': 0,
                'commit_score': 0,
                'recency_score': 0,
                'expertise_score': 0,
                'files_owned': [],
                'expertise_areas': set(),
            })

            for file_path in changed_files:
                ownerships = CodeOwnership.objects.filter(
                    repository=repo, file_path=file_path
                )
                for own in ownerships:
                    for contributor in own.contributors:
                        # Skip the PR author unless they're the only contributor
                        if contributor == pull_request.author_login:
                            continue

                        c = candidates[contributor]
                        c['ownership_score'] += own.expertise_score
                        c['commit_score'] += own.commits_count
                        c['files_owned'].append(file_path)

                        # Recency: higher score for more recent modifications
                        if own.last_modified:
                            days_ago = (timezone.now() - own.last_modified).days
                            c['recency_score'] += max(0, 100 - days_ago)

            # Fallback for solo-developer repos: include the PR author
            if not candidates:
                logger.info(f"No external reviewers found for PR #{pull_request.number}, "
                            f"including author as self-review fallback")
                for file_path in changed_files:
                    ownerships = CodeOwnership.objects.filter(
                        repository=repo, file_path=file_path
                    )
                    for own in ownerships:
                        for contributor in own.contributors:
                            c = candidates[contributor]
                            c['ownership_score'] += own.expertise_score
                            c['commit_score'] += own.commits_count
                            c['files_owned'].append(file_path)
                            c['is_self_review'] = True
                            if own.last_modified:
                                days_ago = (timezone.now() - own.last_modified).days
                                c['recency_score'] += max(0, 100 - days_ago)

            # Enrich with DeveloperExpertise
            for username, c in candidates.items():
                try:
                    exp = DeveloperExpertise.objects.get(
                        repository=repo, github_username=username
                    )
                    c['expertise_score'] += exp.total_commits
                    c['expertise_areas'] = set(exp.expertise_areas or [])
                except DeveloperExpertise.DoesNotExist:
                    pass

            # Compute final weighted scores
            scored = []
            for username, c in candidates.items():
                max_own = max((v['ownership_score'] for v in candidates.values()), default=1) or 1
                max_com = max((v['commit_score'] for v in candidates.values()), default=1) or 1
                max_rec = max((v['recency_score'] for v in candidates.values()), default=1) or 1
                max_exp = max((v['expertise_score'] for v in candidates.values()), default=1) or 1

                final = (
                    WEIGHTS['ownership'] * (c['ownership_score'] / max_own) +
                    WEIGHTS['commits'] * (c['commit_score'] / max_com) +
                    WEIGHTS['recency'] * (c['recency_score'] / max_rec) +
                    WEIGHTS['expertise'] * (c['expertise_score'] / max_exp)
                ) * 100

                # Cap self-review confidence at 60%
                if c.get('is_self_review'):
                    final = min(final, 60)

                scored.append({
                    'username': username,
                    'score': round(final, 1),
                    'files_owned': c['files_owned'],
                    'expertise_areas': list(c['expertise_areas']),
                    'is_self_review': c.get('is_self_review', False),
                })

            scored.sort(key=lambda x: x['score'], reverse=True)

            # Clear old recommendations
            ReviewerRecommendation.objects.filter(pull_request=pull_request).delete()

            # Save top recommendations
            recommendations = []
            for i, s in enumerate(scored[:5]):
                rtype = 'primary' if i == 0 else ('secondary' if i < 3 else 'shadow')
                reason = self._build_reason(s, rtype)

                rec = ReviewerRecommendation.objects.create(
                    pull_request=pull_request,
                    github_username=s['username'],
                    reviewer_type=rtype,
                    confidence_score=min(100, int(s['score'])),
                    recommendation_reason=reason,
                    files_relevant=s['files_owned'][:10],
                    expertise_areas=s['expertise_areas'][:5],
                )
                recommendations.append({
                    'id': rec.id,
                    'github_username': s['username'],
                    'reviewer_type': rtype,
                    'confidence_score': min(100, int(s['score'])),
                    'recommendation_reason': reason,
                })

            return {'success': True, 'recommendations': recommendations}

        except Exception as e:
            logger.error(f"Reviewer recommendation failed: {e}")
            return {'success': False, 'error': str(e)}

    def request_reviewers_on_github(self, pull_request, usernames):
        """Send review requests to GitHub for selected usernames."""
        try:
            from .github_api import GitHubAPIClient
            from .models import ReviewerRecommendation

            repo = pull_request.repository
            client = GitHubAPIClient(repo.user.github_access_token)
            client.request_reviewers(repo.full_name, pull_request.number, usernames)

            # Mark as requested
            ReviewerRecommendation.objects.filter(
                pull_request=pull_request,
                github_username__in=usernames,
            ).update(requested_on_github=True)

            return {'success': True, 'requested': usernames}

        except Exception as e:
            logger.error(f"Failed to request reviewers on GitHub: {e}")
            return {'success': False, 'error': str(e)}

    # ------------------------------------------------------------------ #
    #  HELPERS
    # ------------------------------------------------------------------ #
    def _get_changed_files(self, client, full_name, pr_number):
        try:
            repo = client.client.get_repo(full_name)
            pr = repo.get_pull(pr_number)
            return [f.filename for f in pr.get_files()]
        except Exception as e:
            logger.warning(f"Could not fetch PR files: {e}")
            return []

    def _build_reason(self, scored, reviewer_type):
        parts = []
        if scored.get('is_self_review'):
            parts.append('Self-review (only contributor)')
        elif reviewer_type == 'primary':
            parts.append('Top code owner for changed files')
        elif reviewer_type == 'shadow':
            parts.append('Suggested for learning opportunity')
        else:
            parts.append('Significant contributor to changed files')

        if scored['expertise_areas']:
            parts.append(f"Expert in: {', '.join(scored['expertise_areas'][:3])}")
        parts.append(f"Owns {len(scored['files_owned'])} of the changed files")
        return '. '.join(parts)
