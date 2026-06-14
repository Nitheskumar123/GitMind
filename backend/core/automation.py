"""
Automation Engine
Decides when to trigger AI analysis, documentation updates, and insights
based on user settings and repository state.
"""

import logging
from datetime import date, timedelta
from django.utils import timezone
from django.db.models import Sum

from .models import (
    Repository, PullRequest, RepositorySettings,
    CostTracking, UserPreferences, AutomationLog
)

logger = logging.getLogger(__name__)


# =============================================================================
# AUTOMATION ENGINE
# =============================================================================

class AutomationEngine:
    """
    Central decision engine for all automation tasks.
    Reads user/repo settings and decides whether to trigger AI features.
    """

    def __init__(self, repository):
        self.repository = repository
        self.user = repository.user
        self.settings = self._get_settings()

    def _get_settings(self):
        """
        Load effective settings for this repository.
        Merges global UserPreferences with per-repo RepositorySettings overrides.
        """
        try:
            try:
                user_prefs = self.user.preferences
            except UserPreferences.DoesNotExist:
                user_prefs = UserPreferences.objects.create(
                    user=self.user,
                    auto_analyze_prs=False,
                    auto_post_comments=False,
                    skip_draft_prs=True,
                    min_lines_for_analysis=50,
                    auto_update_docs=False,
                    docs_update_frequency='weekly',
                    docs_min_changes=100,
                    auto_generate_insights=False,
                    insights_frequency='daily',
                    daily_token_limit=100000,
                    pause_on_limit=True,
                )

            try:
                repo_settings = RepositorySettings.objects.get(repository=self.repository)
            except RepositorySettings.DoesNotExist:
                repo_settings = None

            effective = {
                'auto_analyze_prs': user_prefs.auto_analyze_prs,
                'auto_post_comments': user_prefs.auto_post_comments,
                'skip_draft_prs': user_prefs.skip_draft_prs,
                'min_lines_for_analysis': user_prefs.min_lines_for_analysis,
                'auto_update_docs': user_prefs.auto_update_docs,
                'docs_update_frequency': user_prefs.docs_update_frequency,
                'docs_min_changes': user_prefs.docs_min_changes,
                'auto_generate_insights': user_prefs.auto_generate_insights,
                'insights_frequency': user_prefs.insights_frequency,
                'daily_token_limit': user_prefs.daily_token_limit,
                'pause_on_limit': user_prefs.pause_on_limit,
            }

            if repo_settings and repo_settings.override_global:
                if repo_settings.auto_analyze_prs is not None:
                    effective['auto_analyze_prs'] = repo_settings.auto_analyze_prs
                if repo_settings.auto_post_comments is not None:
                    effective['auto_post_comments'] = repo_settings.auto_post_comments
                if repo_settings.enable_pr_analysis is not None:
                    effective['enable_pr_analysis'] = repo_settings.enable_pr_analysis
                if repo_settings.enable_documentation is not None:
                    effective['auto_update_docs'] = repo_settings.enable_documentation
                if repo_settings.enable_insights is not None:
                    effective['auto_generate_insights'] = repo_settings.enable_insights

            return effective

        except Exception as e:
            logger.error(f"Error loading settings for {self.repository.full_name}: {e}")
            return {
                'auto_analyze_prs': False,
                'auto_post_comments': False,
                'skip_draft_prs': True,
                'min_lines_for_analysis': 50,
                'auto_update_docs': False,
                'docs_update_frequency': 'weekly',
                'docs_min_changes': 100,
                'auto_generate_insights': False,
                'insights_frequency': 'daily',
                'daily_token_limit': 100000,
                'pause_on_limit': True,
            }

    # =========================================================================
    # PR ANALYSIS DECISION
    # =========================================================================

    def should_analyze_pr(self, pull_request):
        """
        Decide whether to run AI analysis on a pull request.

        Returns:
            dict: {'should_analyze': bool, 'reason': str}
        """
        try:
            # 1. Check if auto-analysis is enabled
            if not self.settings.get('auto_analyze_prs', False):
                return {
                    'should_analyze': False,
                    'reason': 'Auto PR analysis is disabled in settings'
                }

            # 2. Skip draft PRs if configured
            if self.settings.get('skip_draft_prs', True):
                if getattr(pull_request, 'draft', False):
                    return {
                        'should_analyze': False,
                        'reason': 'Skipping draft PR'
                    }

            # 3. Check minimum lines threshold
            #
            # FIX: GitHub webhook payloads often deliver additions=0 / deletions=0
            # for the initial 'opened' event because GitHub hasn't finished computing
            # the diff yet.  If both values are 0 we treat the count as unknown and
            # skip the threshold gate so the analysis still runs.
            #
            additions = pull_request.additions or 0
            deletions = pull_request.deletions or 0
            total_changes = additions + deletions

            if total_changes > 0:
                # We have real stats — apply the threshold
                min_lines = self.settings.get('min_lines_for_analysis', 50)
                if total_changes < min_lines:
                    return {
                        'should_analyze': False,
                        'reason': (
                            f'PR has {total_changes} changed lines, '
                            f'minimum is {min_lines}'
                        )
                    }
            else:
                # additions/deletions not yet available from the webhook payload;
                # allow analysis to proceed so we don't silently skip every PR.
                logger.info(
                    f"PR #{pull_request.number}: additions/deletions not yet available "
                    f"from webhook payload — skipping lines threshold check."
                )

            # 4. Skip if already analyzed (and not being re-triggered)
            if hasattr(pull_request, 'analysis') and pull_request.analysis:
                if pull_request.state == 'open':
                    # Allow re-analysis on 'synchronize' (new commits pushed)
                    pass
                else:
                    return {
                        'should_analyze': False,
                        'reason': 'PR already analyzed'
                    }

            # 5. Check daily token limit
            limit_exceeded, reason = self._check_token_limit()
            if limit_exceeded:
                return {'should_analyze': False, 'reason': reason}

            return {
                'should_analyze': True,
                'reason': 'All conditions met'
            }

        except Exception as e:
            logger.error(f"Error in should_analyze_pr: {e}")
            return {'should_analyze': False, 'reason': f'Error: {str(e)}'}

    # =========================================================================
    # COMMENT POSTING DECISION
    # =========================================================================

    def should_post_comment(self):
        """
        Decide whether to automatically post analysis comment to GitHub.

        Returns:
            bool
        """
        return bool(self.settings.get('auto_post_comments', False))

    # =========================================================================
    # DOCUMENTATION UPDATE DECISION
    # =========================================================================

    def should_update_documentation(self):
        """
        Decide whether to regenerate documentation for this repository.

        Returns:
            dict: {'should_update': bool, 'reason': str}
        """
        try:
            if not self.settings.get('auto_update_docs', False):
                return {
                    'should_update': False,
                    'reason': 'Auto documentation is disabled in settings'
                }

            frequency = self.settings.get('docs_update_frequency', 'weekly')
            if frequency == 'manual':
                return {
                    'should_update': False,
                    'reason': 'Documentation is set to manual-only mode'
                }

            from .models import Commit

            lookback_days = {'daily': 1, 'weekly': 7, 'monthly': 30}.get(frequency, 7)
            since = timezone.now() - timedelta(days=lookback_days)

            recent_commits = Commit.objects.filter(
                repository=self.repository,
                committed_at__gte=since
            )

            total_changes = sum(
                (c.additions or 0) + (c.deletions or 0)
                for c in recent_commits
            )

            min_changes = self.settings.get('docs_min_changes', 100)

            if total_changes < min_changes:
                return {
                    'should_update': False,
                    'reason': f'Only {total_changes} lines changed recently, minimum is {min_changes}'
                }

            limit_exceeded, reason = self._check_token_limit()
            if limit_exceeded:
                return {'should_update': False, 'reason': reason}

            return {
                'should_update': True,
                'reason': f'{total_changes} lines changed in last {lookback_days} days'
            }

        except Exception as e:
            logger.error(f"Error in should_update_documentation: {e}")
            return {'should_update': False, 'reason': f'Error: {str(e)}'}

    # =========================================================================
    # INSIGHTS GENERATION DECISION
    # =========================================================================

    def should_generate_insights(self):
        """
        Decide whether to generate insights for this repository.

        Returns:
            dict: {'should_generate': bool, 'reason': str}
        """
        try:
            if not self.settings.get('auto_generate_insights', False):
                return {
                    'should_generate': False,
                    'reason': 'Auto insights is disabled in settings'
                }

            frequency = self.settings.get('insights_frequency', 'daily')
            if frequency == 'manual':
                return {
                    'should_generate': False,
                    'reason': 'Insights set to manual-only mode'
                }

            from .models import CodeInsight

            latest_insight = CodeInsight.objects.filter(
                repository=self.repository
            ).order_by('-created_at').first()

            if latest_insight:
                time_since_insight = timezone.now() - latest_insight.created_at

                if frequency == 'realtime':
                    pass
                elif frequency == 'daily' and time_since_insight.total_seconds() < 86400:
                    return {
                        'should_generate': False,
                        'reason': 'Insights already generated in the last 24 hours'
                    }
                elif frequency == 'weekly' and time_since_insight.total_seconds() < 604800:
                    return {
                        'should_generate': False,
                        'reason': 'Insights already generated in the last 7 days'
                    }

            limit_exceeded, reason = self._check_token_limit()
            if limit_exceeded:
                return {'should_generate': False, 'reason': reason}

            return {
                'should_generate': True,
                'reason': 'All conditions met'
            }

        except Exception as e:
            logger.error(f"Error in should_generate_insights: {e}")
            return {'should_generate': False, 'reason': f'Error: {str(e)}'}

    # =========================================================================
    # TOKEN LIMIT CHECK
    # =========================================================================

    def _check_token_limit(self):
        """
        Returns (limit_exceeded: bool, reason: str)
        """
        try:
            from .models import UserPreferences, CostTracking
            from django.utils import timezone
            from django.db.models import Sum

            prefs = self.repository.user.preferences

            if not prefs.pause_on_limit:
                return False, ''

            today = timezone.now().date()
            today_tokens = CostTracking.objects.filter(
                user=self.repository.user,
                date=today
            ).aggregate(total=Sum('tokens_used'))['total'] or 0

            if today_tokens >= prefs.daily_token_limit:
                reason = (
                    f"Daily token limit reached "
                    f"({today_tokens:,}/{prefs.daily_token_limit:,} tokens used today)"
                )
                logger.warning(
                    f"Token limit exceeded for {self.repository.user.github_login}: {reason}"
                )
                return True, reason

            return False, ''

        except Exception:
            return False, ''


# =============================================================================
# AUTOMATION LOG HELPERS
# =============================================================================

def log_automation_action(action_type, repository, user, trigger,
                          description, status='running',
                          pull_request=None, task_id=None):
    """
    Create an AutomationLog entry to track what the system is doing.
    """
    try:
        log = AutomationLog.objects.create(
            action_type=action_type,
            repository=repository,
            user=user,
            trigger=trigger,
            description=description,
            status=status,
            pull_request=pull_request,
            task_id=task_id,
        )
        logger.info(f"Automation log created: [{action_type}] {description}")
        return log
    except Exception as e:
        logger.error(f"Failed to create automation log: {e}")
        return None


def update_automation_log(log_id, status, result_summary=None,
                          error_message=None, tokens_used=0,
                          duration_seconds=None):
    """
    Update an existing AutomationLog by its database primary key (log.id).
    """
    try:
        log = AutomationLog.objects.get(id=log_id)
        log.status = status
        log.completed_at = timezone.now()

        if result_summary:
            log.result_summary = result_summary
        if error_message:
            log.error_message = error_message
        if tokens_used:
            log.tokens_used = tokens_used
        if duration_seconds:
            log.duration_seconds = duration_seconds

        log.save()
        return log
    except AutomationLog.DoesNotExist:
        logger.error(f"AutomationLog {log_id} not found for update")
        return None
    except Exception as e:
        logger.error(f"Failed to update automation log {log_id}: {e}")
        return None