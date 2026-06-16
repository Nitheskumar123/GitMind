"""
Celery background tasks for async processing
"""

from celery import shared_task
from django.utils import timezone
from .models import Repository, User, PullRequest, Issue, Commit, Contributor
from .github_api import GitHubAPIClient
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def track_api_cost(repository, user, action_type, tokens_used,
                   input_tokens=0, output_tokens=0):
    """
    Write to CostTracking so Settings → Usage & Costs shows real data.
    action_type: 'pr_analysis' | 'insights' | 'docs'
    """
    try:
        from .models import CostTracking
        from django.utils import timezone

        today = timezone.now().date()

        tracking, _ = CostTracking.objects.get_or_create(
            user=user,
            repository=repository,
            date=today,
            defaults={
                'tokens_used': 0,
                'input_tokens': 0,
                'output_tokens': 0,
                'api_calls': 0,
                'pr_analyses_count': 0,
                'insights_generated_count': 0,
                'docs_updated_count': 0,
            }
        )

        tracking.tokens_used   += tokens_used
        tracking.input_tokens  += input_tokens  or (tokens_used // 2)
        tracking.output_tokens += output_tokens or (tokens_used // 2)
        tracking.api_calls     += 1

        if action_type == 'pr_analysis':
            tracking.pr_analyses_count        += 1
        elif action_type == 'insights':
            tracking.insights_generated_count += 1
        elif action_type == 'docs':
            tracking.docs_updated_count       += 1
        elif action_type == 'chat':
            pass 

        tracking.calculate_cost()
        tracking.save()
        # REPLACE that logger line with:
        repo_name = repository.full_name if repository else 'N/A (chat)'
        logger.debug(f"Cost tracked: {tokens_used} tokens for {action_type} on {repo_name}")

    except Exception as e:
        logger.warning(f"Cost tracking failed (non-critical): {e}")


def update_automation_log(task_id, status, result_summary='',
                          tokens_used=0, duration_seconds=None):
    """
    Find an AutomationLog by Celery task_id and update its status.
    Called at the END of each Celery task (analyze_pull_request,
    generate_insights_for_repository, generate_repository_documentation).

    NOTE: Do NOT import or replace this with automation.py's version —
    that one takes log_id (DB primary key), this one takes task_id (Celery UUID).
    """
    try:
        from .models import AutomationLog

        log = AutomationLog.objects.filter(task_id=task_id).first()
        if not log:
            logger.debug(f"No AutomationLog found for task_id={task_id} (may not have been created yet)")
            return

        log.status         = status
        log.result_summary = result_summary
        log.tokens_used    = tokens_used
        log.completed_at   = timezone.now()
        if duration_seconds:
            log.duration_seconds = duration_seconds
        log.save()

    except Exception as e:
        logger.warning(f"Could not update automation log for task {task_id}: {e}")


def update_automation_log_by_id(log_id, status, result_summary=None,
                                error_message=None, tokens_used=0,
                                duration_seconds=None):
    """
    Find an AutomationLog by its database primary key (log.id) and update it.
    Called from process_pr_webhook_event which has the log object directly.

    Kept separate from update_automation_log() to avoid signature conflicts.
    """
    try:
        from .models import AutomationLog

        log = AutomationLog.objects.get(id=log_id)
        log.status       = status
        log.completed_at = timezone.now()

        if result_summary is not None:
            log.result_summary = result_summary
        if error_message is not None:
            log.error_message = error_message
        if tokens_used:
            log.tokens_used = tokens_used
        if duration_seconds:
            log.duration_seconds = duration_seconds

        log.save()
        return log

    except Exception as e:
        logger.warning(f"Could not update automation log id={log_id}: {e}")
        return None


# =============================================================================
# SYNC TASKS
# =============================================================================

@shared_task
def sync_repository_data(repository_id):
    """Sync all data for a single repository"""
    try:
        repository = Repository.objects.get(id=repository_id)
        user = repository.user

        if not user.github_access_token:
            logger.error(f"No access token for user {user.github_login}")
            return False

        client = GitHubAPIClient(user.github_access_token)

        repo_data = client.get_repository_details(repository.full_name)
        if repo_data:
            repository.stars_count       = repo_data['stargazers_count']
            repository.forks_count       = repo_data['forks_count']
            repository.open_issues_count = repo_data['open_issues_count']
            repository.watchers_count    = repo_data['watchers_count']
            repository.size              = repo_data['size']
            repository.github_updated_at = repo_data['updated_at']
            repository.github_pushed_at  = repo_data['pushed_at']
            repository.last_synced_at    = timezone.now()
            repository.save()

        sync_pull_requests(repository_id)
        sync_issues(repository_id)
        sync_commits(repository_id)
        sync_contributors(repository_id)

        # Phase 8: Trigger cognitive debt analysis after sync
        try:
            analyse_cognitive_debt.delay(repository_id)
        except Exception as debt_err:
            logger.warning(f"Cognitive debt auto-trigger failed (non-fatal): {debt_err}")

        logger.info(f"Successfully synced repository: {repository.full_name}")
        return True

    except Repository.DoesNotExist:
        logger.error(f"Repository {repository_id} not found")
        return False
    except Exception as e:
        logger.error(f"Error syncing repository {repository_id}: {e}")
        return False


@shared_task
def sync_pull_requests(repository_id):
    """Sync pull requests for repository"""
    try:
        repository = Repository.objects.get(id=repository_id)
        user = repository.user

        client = GitHubAPIClient(user.github_access_token)
        pr_data = client.get_pull_requests(repository.full_name)

        for pr in pr_data:
            PullRequest.objects.update_or_create(
                repository=repository,
                number=pr['number'],
                defaults={
                    'github_id':             str(pr['id']),
                    'title':                 pr['title'],
                    'body':                  pr['body'] or '',
                    'state':                 pr['state'],
                    'html_url':              pr['html_url'],
                    'author_login':          pr['author_login'],
                    'author_avatar_url':     pr['author_avatar_url'],
                    'head_branch':           pr['head_branch'],
                    'base_branch':           pr['base_branch'],
                    'additions':             pr['additions'],
                    'deletions':             pr['deletions'],
                    'changed_files':         pr['changed_files'],
                    'comments_count':        pr['comments_count'],
                    'review_comments_count': pr['review_comments_count'],
                    'commits_count':         pr['commits_count'],
                    'mergeable':             pr['mergeable'],
                    'merged':                pr['merged'],
                    'merged_at':             pr['merged_at'],
                    'closed_at':             pr['closed_at'],
                    'created_at':            pr['created_at'],
                    'updated_at':            pr['updated_at'],
                }
            )

        logger.info(f"Synced {len(pr_data)} pull requests for {repository.full_name}")
        return True

    except Exception as e:
        logger.error(f"Error syncing pull requests: {e}")
        return False


@shared_task
def sync_issues(repository_id):
    """Sync issues for repository"""
    try:
        repository = Repository.objects.get(id=repository_id)
        user = repository.user

        client = GitHubAPIClient(user.github_access_token)
        issue_data = client.get_issues(repository.full_name)

        for issue in issue_data:
            Issue.objects.update_or_create(
                repository=repository,
                number=issue['number'],
                defaults={
                    'github_id':      str(issue['id']),
                    'title':          issue['title'],
                    'body':           issue['body'] or '',
                    'state':          issue['state'],
                    'html_url':       issue['html_url'],
                    'author_login':   issue['author_login'],
                    'author_avatar_url': issue['author_avatar_url'],
                    'labels':         issue['labels'],
                    'assignees':      issue['assignees'],
                    'comments_count': issue['comments_count'],
                    'closed_at':      issue['closed_at'],
                    'created_at':     issue['created_at'],
                    'updated_at':     issue['updated_at'],
                }
            )

        logger.info(f"Synced {len(issue_data)} issues for {repository.full_name}")
        return True

    except Exception as e:
        logger.error(f"Error syncing issues: {e}")
        return False


@shared_task
def sync_commits(repository_id):
    """Sync commits for repository"""
    try:
        repository = Repository.objects.get(id=repository_id)
        user = repository.user

        client = GitHubAPIClient(user.github_access_token)
        commit_data = client.get_commits(repository.full_name, limit=100)

        for commit in commit_data:
            Commit.objects.update_or_create(
                sha=commit['sha'],
                defaults={
                    'repository':       repository,
                    'message':          commit['message'],
                    'html_url':         commit['html_url'],
                    'author_name':      commit['author_name'],
                    'author_email':     commit['author_email'],
                    'author_login':     commit['author_login'],
                    'author_avatar_url':commit['author_avatar_url'],
                    'additions':        commit['additions'],
                    'deletions':        commit['deletions'],
                    'total_changes':    commit['total_changes'],
                    'committed_at':     commit['committed_at'],
                }
            )

        logger.info(f"Synced {len(commit_data)} commits for {repository.full_name}")
        return True

    except Exception as e:
        logger.error(f"Error syncing commits: {e}")
        return False


@shared_task
def sync_contributors(repository_id):
    """Sync contributors for repository"""
    try:
        repository = Repository.objects.get(id=repository_id)
        user = repository.user

        client = GitHubAPIClient(user.github_access_token)
        contributor_data = client.get_contributors(repository.full_name)

        repository.contributors.all().delete()

        for contributor in contributor_data:
            Contributor.objects.create(
                repository=repository,
                github_login=contributor['login'],
                avatar_url=contributor['avatar_url'],
                html_url=contributor['html_url'],
                contributions=contributor['contributions'],
            )

        logger.info(f"Synced {len(contributor_data)} contributors for {repository.full_name}")
        return True

    except Exception as e:
        logger.error(f"Error syncing contributors: {e}")
        return False


@shared_task
def sync_all_repositories():
    """Periodic task to sync all active repositories"""
    try:
        active_repos = Repository.objects.filter(is_active=True)

        for repo in active_repos:
            sync_repository_data.delay(repo.id)

        logger.info(f"Queued sync for {active_repos.count()} repositories")
        return True

    except Exception as e:
        logger.error(f"Error queuing repository syncs: {e}")
        return False


# =============================================================================
# CODE ANALYSIS TASKS
# =============================================================================

@shared_task(bind=True)
def analyze_pull_request(self, pr_id):
    """
    Run AI code review on a pull request.
    Uses the module-level update_automation_log(task_id=...) defined above.

    IMPORTANT: Do NOT add 'from .automation import update_automation_log' inside
    this function — that version takes log_id, not task_id, and will crash.
    """
    import time
    start_time = time.time()

    try:
        from .models import PullRequest
        from .code_review import CodeReviewer
        from .automation import AutomationEngine

        pr = PullRequest.objects.select_related('repository__user').get(id=pr_id)

        logger.info(f"Starting analysis for PR #{pr.number} in {pr.repository.full_name}")

        reviewer = CodeReviewer(pr)
        analysis = reviewer.perform_analysis()

        if not analysis:
            logger.error(f"Analysis failed for PR #{pr.number}")
            update_automation_log(
                task_id=self.request.id,
                status='failed',
                result_summary='Analysis returned no result',
            )
            return False

        engine = AutomationEngine(pr.repository)
        if engine.should_post_comment():
            reviewer.post_comment_to_github(analysis)

        duration = time.time() - start_time

        update_automation_log(
            task_id=self.request.id,
            status='success',
            result_summary=f"Analysis complete. Found {analysis.issues_found} issues. Security: {analysis.security_score}/100",
            tokens_used=analysis.tokens_used,
            duration_seconds=duration,
        )

        track_api_cost(
            repository=pr.repository,
            user=pr.repository.user,
            action_type='pr_analysis',
            tokens_used=analysis.tokens_used,
        )

        return True

    except PullRequest.DoesNotExist:
        logger.error(f"PR {pr_id} not found")
        update_automation_log(task_id=self.request.id, status='failed', result_summary='PR not found')
        return False
    except Exception as e:
        logger.error(f"Error analyzing PR {pr_id}: {e}")
        update_automation_log(task_id=self.request.id, status='failed', result_summary=str(e))
        return False


@shared_task(bind=True)
def generate_repository_documentation(self, repo_id, doc_type='readme'):
    """Generate AI documentation for a repository."""
    import time
    start_time = time.time()

    try:
        from .models import Repository
        from .documentation_gen import DocumentationGenerator
        from .github_api import GitHubAPIClient

        repo = Repository.objects.select_related('user').get(id=repo_id)

        github = GitHubAPIClient(repo.user.github_access_token)
        code_files = github.get_repository_files(repo.full_name, max_files=20)

        if not code_files:
            update_automation_log(
                task_id=self.request.id,
                status='failed',
                result_summary='No code files found',
            )
            return {'success': False, 'reason': 'No files found'}

        generator = DocumentationGenerator()
        result = generator.generate_readme(repo, code_files) if doc_type in ('readme', '') \
                 else generator.generate_api_documentation(code_files)

        generator.save_doc_to_db(repo.id, repo.user.id, doc_type, result)

        if result.get('success'):
            filename = 'README_AI.md' if doc_type == 'readme' else 'API_DOCS_AI.md'
            github.create_or_update_file(
                repo_name=repo.full_name,
                file_path=filename,
                content=result['content'],
                commit_message=f'🤖 Auto-update {filename} via GitMind'
            )

        duration = time.time() - start_time
        tokens   = result.get('tokens_used', 1500)

        update_automation_log(
            task_id=self.request.id,
            status='success' if result.get('success') else 'failed',
            result_summary=f"Generated {doc_type} documentation",
            tokens_used=tokens,
            duration_seconds=duration,
        )

        if result.get('success'):
            track_api_cost(
                repository=repo,
                user=repo.user,
                action_type='docs',
                tokens_used=tokens,
            )

        return result

    except Exception as e:
        update_automation_log(task_id=self.request.id, status='failed', result_summary=str(e))
        logger.error(f"Documentation generation failed for repo {repo_id}: {e}")
        return {'success': False, 'error': str(e)}


@shared_task
def generate_insights_for_user(user_id):
    """Generate insights for all user repositories"""
    try:
        from .models import User
        from .insights_engine import InsightsEngine

        user = User.objects.get(id=user_id)
        logger.info(f"Generating insights for user: {user.github_login}")

        engine = InsightsEngine()
        total_insights = engine.generate_all_user_insights(user)

        logger.info(f"Generated {total_insights} insights for {user.github_login}")
        return total_insights

    except User.DoesNotExist:
        logger.error(f"User {user_id} not found")
        return 0
    except Exception as e:
        logger.error(f"Error generating insights: {e}")
        return 0


@shared_task(bind=True)
def generate_insights_for_repository(self, repo_id):
    """Generate AI insights for a single repository."""
    import time
    start_time = time.time()

    try:
        from .models import Repository
        from .insights_engine import InsightsEngine

        repo = Repository.objects.get(id=repo_id)
        engine = InsightsEngine()
        insights = engine.generate_repository_insights(repo)
        count = len(insights)
        actual_tokens = getattr(engine, 'actual_tokens_used', count * 600)

        duration = time.time() - start_time
        estimated_tokens = count * 600  # ~600 tokens per insight

        update_automation_log(
            task_id=self.request.id,
            status='success',
            result_summary=f"Generated {count} insights",
            tokens_used=actual_tokens,
            duration_seconds=duration,
        )

        track_api_cost(
            repository=repo,
            user=repo.user,
            action_type='insights',
            tokens_used=actual_tokens,
        )

        logger.info(f"Generated {count} insights for {repo.full_name}")
        return count

    except Repository.DoesNotExist:
        update_automation_log(task_id=self.request.id, status='failed', result_summary='Repo not found')
        return 0
    except Exception as e:
        update_automation_log(task_id=self.request.id, status='failed', result_summary=str(e))
        logger.error(f"Error generating insights: {e}")
        return 0


def fetch_repository_files(client, repository, max_files=10):
    """Fetch code files from repository"""
    try:
        import requests

        url = f"https://api.github.com/repos/{repository.full_name}/contents"
        headers = {
            'Authorization': f'token {client.access_token}',
            'Accept': 'application/vnd.github.v3+json'
        }

        response = requests.get(url, headers=headers)
        response.raise_for_status()
        contents = response.json()

        code_extensions = ['.py', '.js', '.ts', '.java', '.go', '.rs', '.rb', '.php', '.cpp', '.c']
        code_files = []

        for item in contents:
            if item['type'] == 'file':
                name = item['name']
                if any(name.endswith(ext) for ext in code_extensions):
                    file_response = requests.get(item['download_url'])
                    if file_response.status_code == 200:
                        code_files.append({
                            'path': name,
                            'content': file_response.text[:5000]
                        })
                        if len(code_files) >= max_files:
                            break

        return code_files

    except Exception as e:
        logger.error(f"Error fetching repository files: {e}")
        return []


# =============================================================================
# AUTOMATION IMPORTS
# NOTE: Only import AutomationEngine and log_automation_action from automation.py.
# Do NOT import update_automation_log from automation.py — it has a different
# signature (log_id vs task_id) and would overwrite the local version above.
# =============================================================================

from .automation import AutomationEngine, log_automation_action
from .webhook_manager import setup_webhook_for_repository, check_all_webhooks_health


# =============================================================================
# AUTOMATION TASKS
# =============================================================================

@shared_task
def setup_repository_webhook(repo_id):
    """Set up webhook for repository automatically"""
    try:
        repository = Repository.objects.get(id=repo_id)
        logger.info(f"Setting up webhook for {repository.full_name}")

        result = setup_webhook_for_repository(repository)

        if result['success']:
            logger.info(f"Webhook setup successful for {repository.full_name}")
        else:
            logger.error(f"Webhook setup failed for {repository.full_name}: {result.get('error')}")

        return result

    except Repository.DoesNotExist:
        logger.error(f"Repository {repo_id} not found")
        return {'success': False, 'error': 'Repository not found'}
    except Exception as e:
        logger.error(f"Error setting up webhook: {e}")
        return {'success': False, 'error': str(e)}


@shared_task
def process_pr_webhook_event(pr_id):
    """
    Process PR webhook event with smart automation.
    Decides whether to analyze based on settings.

    Uses update_automation_log_by_id() (log.id / DB primary key) because
    this task creates the log itself and has direct access to log.id.
    """
    try:
        pr = PullRequest.objects.select_related('repository__user').get(id=pr_id)
        repository = pr.repository
        user = repository.user

        logger.info(f"Processing PR webhook for #{pr.number} in {repository.full_name}")

        engine = AutomationEngine(repository)
        decision = engine.should_analyze_pr(pr)

        log = log_automation_action(
            action_type='pr_analysis',
            repository=repository,
            user=user,
            trigger='webhook',
            description=f"Webhook event for PR #{pr.number}: {pr.title}",
            status='running' if decision['should_analyze'] else 'skipped',
            pull_request=pr,
        )

        if not decision['should_analyze']:
            logger.info(f"Skipping PR analysis: {decision['reason']}")
            if log:
                # Use update_automation_log_by_id because we have log.id here
                update_automation_log_by_id(
                    log_id=log.id,
                    status='skipped',
                    result_summary=decision['reason'],
                )
            return {
                'analyzed': False,
                'reason': decision['reason'],
            }

        task = analyze_pull_request.delay(pr.id)

        # Stamp the log with the Celery task_id so update_automation_log()
        # in analyze_pull_request can find it later
        if log:
            log.task_id = task.id
            log.save()

        # Phase 5: Also trigger description generation + reviewer recommendation
        try:
            generate_pr_description_task.delay(pr.id)
            recommend_reviewers_task.delay(pr.id)
            logger.info(f"Phase 5: Queued description + reviewer tasks for PR #{pr.number}")
        except Exception as phase5_err:
            logger.warning(f"Phase 5 auto-trigger failed (non-fatal): {phase5_err}")

        logger.info(f"Queued PR analysis for #{pr.number}")
        return {
            'analyzed': True,
            'task_id': task.id,
            'reason': decision['reason'],
        }

    except PullRequest.DoesNotExist:
        logger.error(f"Pull request {pr_id} not found")
        return {'analyzed': False, 'error': 'PR not found'}
    except Exception as e:
        logger.error(f"Error processing PR webhook: {e}")
        return {'analyzed': False, 'error': str(e)}


@shared_task
def generate_daily_insights():
    """Celery Beat task: Generate insights for all active repositories. Runs daily at 8:00 AM."""
    try:
        from .models import UserPreferences

        logger.info("Starting daily insights generation")

        users_with_insights = UserPreferences.objects.filter(
            auto_generate_insights=True,
            insights_frequency__in=['daily', 'realtime']
        ).select_related('user')

        total_generated = 0
        repositories_processed = 0

        for user_pref in users_with_insights:
            user = user_pref.user
            repositories = Repository.objects.filter(user=user, is_active=True)

            for repo in repositories:
                engine = AutomationEngine(repo)
                decision = engine.should_generate_insights()

                if decision['should_generate']:
                    task = generate_insights_for_repository.delay(repo.id)

                    log_automation_action(
                        action_type='insight_generation',
                        repository=repo,
                        user=user,
                        trigger='scheduled_task',
                        description=f"Daily insights generation for {repo.full_name}",
                        status='running',
                        task_id=task.id,
                    )

                    total_generated += 1
                    repositories_processed += 1
                else:
                    logger.info(f"Skipping insights for {repo.full_name}: {decision['reason']}")

        logger.info(f"Daily insights: Processed {repositories_processed} repos, generated {total_generated} insights")
        return {
            'success': True,
            'repositories_processed': repositories_processed,
            'insights_generated': total_generated,
        }

    except Exception as e:
        logger.error(f"Error in daily insights generation: {e}")
        return {'success': False, 'error': str(e)}


@shared_task
def update_documentation_weekly():
    """Celery Beat task: Update documentation for repositories. Runs weekly on Friday at 4:00 PM."""
    try:
        from .models import UserPreferences

        logger.info("Starting weekly documentation update")

        users_with_docs = UserPreferences.objects.filter(
            auto_update_docs=True,
            docs_update_frequency='weekly'
        ).select_related('user')

        total_updated = 0
        repositories_processed = 0

        for user_pref in users_with_docs:
            user = user_pref.user
            repositories = Repository.objects.filter(user=user, is_active=True)

            for repo in repositories:
                engine = AutomationEngine(repo)
                decision = engine.should_update_documentation()

                if decision['should_update']:
                    task = generate_repository_documentation.delay(repo.id, 'readme')

                    log_automation_action(
                        action_type='doc_update',
                        repository=repo,
                        user=user,
                        trigger='scheduled_task',
                        description=f"Weekly documentation update for {repo.full_name}",
                        status='running',
                        task_id=task.id,
                    )

                    total_updated += 1
                    repositories_processed += 1
                else:
                    logger.info(f"Skipping docs for {repo.full_name}: {decision['reason']}")

        logger.info(f"Weekly docs: Processed {repositories_processed} repos, updated {total_updated}")
        return {
            'success': True,
            'repositories_processed': repositories_processed,
            'docs_updated': total_updated,
        }

    except Exception as e:
        logger.error(f"Error in weekly documentation update: {e}")
        return {'success': False, 'error': str(e)}


@shared_task
def check_webhook_health():
    """Celery Beat task: Check health of all webhooks. Runs hourly."""
    try:
        logger.info("Checking webhook health")
        health_summary = check_all_webhooks_health()
        logger.info(f"Webhook health check: {health_summary['healthy']}/{health_summary['checked']} healthy")
        return health_summary

    except Exception as e:
        logger.error(f"Error checking webhook health: {e}")
        return {'success': False, 'error': str(e)}
@shared_task
def update_documentation_daily():
    """Celery Beat: Daily docs update at 2:00 AM UTC."""
    try:
        from .models import UserPreferences
        users_with_docs = UserPreferences.objects.filter(
            auto_update_docs=True,
            docs_update_frequency='daily'
        ).select_related('user')

        for user_pref in users_with_docs:
            repositories = Repository.objects.filter(
                user=user_pref.user, is_active=True
            )
            for repo in repositories:
                engine = AutomationEngine(repo)
                decision = engine.should_update_documentation()
                if decision['should_update']:
                    task = generate_repository_documentation.delay(repo.id, 'readme')
                    log_automation_action(
                        action_type='doc_update', repository=repo,
                        user=user_pref.user, trigger='scheduled_task',
                        description=f"Daily docs update for {repo.full_name}",
                        status='running', task_id=task.id,
                    )
    except Exception as e:
        logger.error(f"Daily docs update failed: {e}")


@shared_task
def update_documentation_monthly():
    """Celery Beat: Monthly docs update on the 1st at 3:00 AM UTC."""
    try:
        from .models import UserPreferences
        users_with_docs = UserPreferences.objects.filter(
            auto_update_docs=True,
            docs_update_frequency='monthly'
        ).select_related('user')

        for user_pref in users_with_docs:
            repositories = Repository.objects.filter(
                user=user_pref.user, is_active=True
            )
            for repo in repositories:
                engine = AutomationEngine(repo)
                decision = engine.should_update_documentation()
                if decision['should_update']:
                    task = generate_repository_documentation.delay(repo.id, 'readme')
                    log_automation_action(
                        action_type='doc_update', repository=repo,
                        user=user_pref.user, trigger='scheduled_task',
                        description=f"Monthly docs update for {repo.full_name}",
                        status='running', task_id=task.id,
                    )
    except Exception as e:
        logger.error(f"Monthly docs update failed: {e}")
@shared_task
def generate_weekly_insights():
    """Celery Beat task: Generate insights for weekly users. Runs every Monday at 8:00 AM UTC."""
    try:
        from .models import UserPreferences

        logger.info("Starting weekly insights generation")

        users_with_insights = UserPreferences.objects.filter(
            auto_generate_insights=True,
            insights_frequency='weekly'
        ).select_related('user')

        total_generated = 0
        repositories_processed = 0

        for user_pref in users_with_insights:
            user = user_pref.user
            repositories = Repository.objects.filter(user=user, is_active=True)

            for repo in repositories:
                engine = AutomationEngine(repo)
                decision = engine.should_generate_insights()

                if decision['should_generate']:
                    task = generate_insights_for_repository.delay(repo.id)
                    log_automation_action(
                        action_type='insight_generation',
                        repository=repo,
                        user=user,
                        trigger='scheduled_task',
                        description=f"Weekly insights for {repo.full_name}",
                        status='running',
                        task_id=task.id,
                    )
                    total_generated += 1
                    repositories_processed += 1

        logger.info(f"Weekly insights: Processed {repositories_processed} repos")
        return {'success': True, 'insights_generated': total_generated}

    except Exception as e:
        logger.error(f"Error in weekly insights generation: {e}")
        return {'success': False, 'error': str(e)}


# =============================================================================
# PHASE 5: PR Description, Reviewer, Ownership Tasks
# =============================================================================

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def generate_pr_description_task(self, pr_id):
    """Generate AI PR description with retry logic."""
    try:
        pr = PullRequest.objects.get(id=pr_id)
        from .pr_description_gen import PRDescriptionGenerator
        gen = PRDescriptionGenerator()
        result = gen.generate_description(pr)
        logger.info(f"PR description generated for #{pr.number}: {result.get('success')}")
        return result
    except Exception as e:
        logger.error(f"PR description task failed: {e}")
        self.retry(countdown=60 * (2 ** self.request.retries), exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def analyze_code_ownership_task(self, repo_id):
    """Analyze code ownership for a repository with retry logic."""
    try:
        repo = Repository.objects.get(id=repo_id)
        from .code_ownership import CodeOwnershipAnalyzer
        analyzer = CodeOwnershipAnalyzer()
        result = analyzer.analyze_repository(repo)
        logger.info(f"Ownership analysis complete for {repo.full_name}: {result}")
        return result
    except Exception as e:
        logger.error(f"Ownership analysis task failed: {e}")
        self.retry(countdown=60 * (2 ** self.request.retries), exc=e)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def recommend_reviewers_task(self, pr_id):
    """Recommend reviewers for a PR with retry logic."""
    try:
        pr = PullRequest.objects.get(id=pr_id)
        from .reviewer_engine import ReviewerRecommendationEngine
        engine = ReviewerRecommendationEngine()
        result = engine.recommend_reviewers(pr)
        logger.info(f"Reviewer recommendations for PR #{pr.number}: {result.get('success')}")
        return result
    except Exception as e:
        logger.error(f"Reviewer recommendation task failed: {e}")
        self.retry(countdown=60 * (2 ** self.request.retries), exc=e)


@shared_task
def nightly_ownership_analysis():
    """Nightly Celery Beat task: refresh ownership data for all active repos."""
    from .code_ownership import CodeOwnershipAnalyzer
    repos = Repository.objects.filter(is_active=True)
    analyzer = CodeOwnershipAnalyzer()
    for repo in repos:
        try:
            analyzer.analyze_repository(repo)
        except Exception as e:
            logger.error(f"Nightly ownership failed for {repo.full_name}: {e}")
    logger.info(f"Nightly ownership analysis complete for {repos.count()} repos")


# =============================================================================
# PHASE 7: Conflict Detection & Dependency Analysis Tasks
# =============================================================================

@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def analyze_pr_conflicts_task(self, repo_id, pr_id=None):
    """
    Analyze conflicts for open PRs in a repository.
    If pr_id is specified, only analyze that PR. Otherwise analyze all open PRs.
    Uses cache-based locking to prevent duplicate tasks.
    """
    import time
    from django.core.cache import cache

    lock_key = f"conflict_analysis_lock_{repo_id}"
    if cache.get(lock_key):
        logger.info(f"Conflict analysis already running for repo {repo_id}, skipping")
        return {'skipped': True, 'reason': 'Already running'}

    # Set lock (expires in 10 minutes)
    cache.set(lock_key, True, timeout=600)

    try:
        repository = Repository.objects.get(id=repo_id)
        from .conflict_detector import ConflictDetector

        detector = ConflictDetector(repository)
        start_time = time.time()

        if pr_id:
            # Analyze specific PR
            pr = PullRequest.objects.get(id=pr_id, repository=repository)
            conflicts = detector.analyze_pr_conflicts(pr)
            logger.info(f"Conflict analysis for PR #{pr.number}: found {len(conflicts)} conflicts")
        else:
            # Analyze all open PRs
            open_prs = PullRequest.objects.filter(repository=repository, state='open')
            conflicts = []
            for pr in open_prs:
                try:
                    pr_conflicts = detector.analyze_pr_conflicts(pr)
                    conflicts.extend(pr_conflicts)
                except Exception as e:
                    logger.error(f"Error analyzing PR #{pr.number}: {e}")

            logger.info(f"Conflict analysis for {repository.full_name}: found {len(conflicts)} conflicts across {open_prs.count()} PRs")

        duration = time.time() - start_time

        log_automation_action(
            action_type='pr_analysis',
            repository=repository,
            user=repository.user,
            trigger='manual',
            description=f"Conflict detection for {repository.full_name}",
            status='success',
            task_id=self.request.id,
        )

        return {
            'success': True,
            'conflicts_found': len(conflicts),
            'duration': round(duration, 2),
        }

    except Repository.DoesNotExist:
        logger.error(f"Repository {repo_id} not found")
        return {'success': False, 'error': 'Repository not found'}
    except Exception as e:
        logger.error(f"Conflict analysis failed for repo {repo_id}: {e}")
        self.retry(countdown=120, exc=e)
    finally:
        cache.delete(lock_key)


@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def analyze_dependencies_task(self, repo_id):
    """
    Analyze all dependencies for a repository.
    Uses cache-based locking to prevent duplicate tasks.
    """
    import time
    from django.core.cache import cache

    lock_key = f"dep_analysis_lock_{repo_id}"
    if cache.get(lock_key):
        logger.info(f"Dependency analysis already running for repo {repo_id}, skipping")
        return {'skipped': True, 'reason': 'Already running'}

    cache.set(lock_key, True, timeout=600)

    try:
        repository = Repository.objects.get(id=repo_id)
        from .dependency_analyzer import DependencyAnalyzer

        analyzer = DependencyAnalyzer(repository)
        start_time = time.time()

        results = analyzer.analyze_all_dependencies()
        duration = time.time() - start_time

        breaking = sum(1 for r in results if r and r.has_breaking_changes)

        log_automation_action(
            action_type='insight_generation',
            repository=repository,
            user=repository.user,
            trigger='manual',
            description=f"Dependency analysis for {repository.full_name}",
            status='success',
            task_id=self.request.id,
        )

        logger.info(f"Dependency analysis for {repository.full_name}: {len(results)} packages, {breaking} with breaking changes")

        return {
            'success': True,
            'packages_analyzed': len(results),
            'breaking_changes': breaking,
            'duration': round(duration, 2),
        }

    except Repository.DoesNotExist:
        logger.error(f"Repository {repo_id} not found")
        return {'success': False, 'error': 'Repository not found'}
    except Exception as e:
        logger.error(f"Dependency analysis failed for repo {repo_id}: {e}")
        self.retry(countdown=120, exc=e)
    finally:
        cache.delete(lock_key)


@shared_task
def check_all_conflicts_daily():
    """Celery Beat: Run conflict detection across all active repositories daily."""
    try:
        repos = Repository.objects.filter(is_active=True)
        queued = 0
        for repo in repos:
            open_prs = repo.pull_requests.filter(state='open').count()
            if open_prs >= 2:  # Only check repos with 2+ open PRs
                analyze_pr_conflicts_task.delay(repo.id)
                queued += 1
        logger.info(f"Daily conflict check: queued {queued} repos")
        return {'success': True, 'repos_queued': queued}
    except Exception as e:
        logger.error(f"Daily conflict check failed: {e}")
        return {'success': False, 'error': str(e)}


@shared_task
def check_dependency_updates_weekly():
    """Celery Beat: Run dependency analysis for all active repositories weekly."""
    try:
        repos = Repository.objects.filter(is_active=True)
        queued = 0
        for repo in repos:
            analyze_dependencies_task.delay(repo.id)
            queued += 1
        logger.info(f"Weekly dependency check: queued {queued} repos")
        return {'success': True, 'repos_queued': queued}
    except Exception as e:
        logger.error(f"Weekly dependency check failed: {e}")
        return {'success': False, 'error': str(e)}


# =============================================================================
# PHASE 8: Cognitive Debt Analysis Task
# =============================================================================

@shared_task(bind=True, max_retries=2, default_retry_delay=120)
def analyse_cognitive_debt(self, repo_id, force=False):
    """
    Analyze cognitive debt for a repository.
    Reads commit history, detects AI-authored code, and computes comprehension
    scores per file.  Uses cache-based locking to prevent duplicate runs.

    Args:
        repo_id: Repository ID
        force: If True, clears the lock and forces a fresh analysis
    """
    import time
    from django.core.cache import cache

    lock_key = f"cognitive_debt_lock_{repo_id}"

    if force:
        cache.delete(lock_key)

    if cache.get(lock_key):
        logger.info(f"Cognitive debt analysis already running for repo {repo_id}, skipping")
        return {'skipped': True, 'reason': 'Already running'}

    cache.set(lock_key, True, timeout=120)  # 2-minute lock (reduced from 10 min)

    try:
        repository = Repository.objects.get(id=repo_id)
        from .cognitive_debt_analyzer import CognitiveDebtAnalyzer

        start_time = time.time()
        analyzer = CognitiveDebtAnalyzer(repository)
        result = analyzer.run()
        duration = time.time() - start_time

        log_automation_action(
            action_type='insight_generation',
            repository=repository,
            user=repository.user,
            trigger='auto',
            description=f"Cognitive debt analysis for {repository.full_name}",
            status='success',
            task_id=self.request.id,
        )

        logger.info(
            f"Cognitive debt analysis complete for {repository.full_name}: "
            f"{result['files_analyzed']} files in {duration:.1f}s"
        )

        return {
            'success': True,
            **result,
            'duration': round(duration, 2),
        }

    except Repository.DoesNotExist:
        logger.error(f"Repository {repo_id} not found for cognitive debt analysis")
        return {'success': False, 'error': 'Repository not found'}
    except Exception as e:
        logger.error(f"Cognitive debt analysis failed for repo {repo_id}: {e}")
        self.retry(countdown=120, exc=e)
    finally:
        cache.delete(lock_key)