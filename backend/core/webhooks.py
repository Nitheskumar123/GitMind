"""
GitHub Webhook handlers
Process incoming webhook events from GitHub
"""

import hmac
import hashlib
import json
import logging
from django.conf import settings
from django.utils import timezone
from .models import Repository, WebhookEvent, RepositoryWebhook
from .tasks import sync_repository_data

logger = logging.getLogger(__name__)


def verify_webhook_signature(payload_body, signature_header, secret):
    """
    Verify that the webhook payload was sent by GitHub
    """
    if not signature_header:
        return False
    
    # Get the signature from header
    sha_name, signature = signature_header.split('=')
    if sha_name != 'sha256':
        return False
    
    # Calculate expected signature
    mac = hmac.new(secret.encode(), msg=payload_body, digestmod=hashlib.sha256)
    expected_signature = mac.hexdigest()
    
    # Compare signatures
    return hmac.compare_digest(expected_signature, signature)


def process_webhook_event(event_type, delivery_id, payload, repository_full_name):
    """
    Process webhook event based on event type
    """
    try:
        # 1. Find repository
        repository = Repository.objects.get(full_name=repository_full_name)
        
        # 2. Silently ignore comment events to stop log noise
        if event_type == 'issue_comment':
            return {'status': 'ignored', 'message': 'Skipping comment event'}
        
        # 3. Create webhook event record (so you can see it in your dashboard)
        webhook_event = WebhookEvent.objects.create(
            repository=repository,
            event_type=event_type,
            delivery_id=delivery_id,
            payload=payload,
            processed=False,
        )
        
        # 4. Update webhook stats
        if hasattr(repository, 'webhook'):
            webhook = repository.webhook
            webhook.last_delivery_at = timezone.now()
            webhook.total_deliveries += 1
            webhook.save()
        
        # 5. Process based on event type
        if event_type == 'push':
            handle_push_event(webhook_event)
        elif event_type == 'pull_request':
            # This triggers the process_pr_webhook_event task in tasks.py
            handle_pull_request_event(webhook_event) 
        elif event_type == 'issues':
            handle_issues_event(webhook_event)
        elif event_type == 'ping':
            handle_ping_event(webhook_event)
        else:
            logger.info(f"Unhandled event type: {event_type}")
        
        # 6. Mark as processed
        webhook_event.processed = True
        webhook_event.processed_at = timezone.now()
        webhook_event.save()
        
        return True
        
    except Repository.DoesNotExist:
        logger.error(f"Repository not found: {repository_full_name}")
        return False
    except Exception as e:
        logger.error(f"Error processing webhook event: {e}")
        if 'webhook_event' in locals():
            webhook_event.error_message = str(e)
            webhook_event.save()
        return False
def handle_push_event(webhook_event):
    from .tasks import sync_commits, generate_repository_documentation
    from .automation import AutomationEngine

    # 1. Always sync the commits first so the DB is up to date
    sync_commits.delay(webhook_event.repository.id)

    try:
        repository = webhook_event.repository
        engine = AutomationEngine(repository)
        
        # Check if the user even wants auto-docs
        if not engine.settings.get('auto_update_docs', False):
            return

        # LOGIC FIX: 
        # Only trigger from a webhook if the frequency is 'daily' or a custom 'realtime'.
        # If it's 'weekly' or 'monthly', let the Celery Beat cron job handle it
        # so it doesn't bother the user with documentation updates on every single push.
        
        frequency = engine.settings.get('docs_update_frequency', 'weekly')
        
        if frequency == 'daily':
            # Check if we already did this today to avoid spamming the AI
            from .models import DocumentationGeneration
            already_updated_today = DocumentationGeneration.objects.filter(
                repository=repository,
                status='completed',
                created_at__date=timezone.now().date()
            ).exists()

            decision = engine.should_update_documentation()
            if decision['should_update'] and not already_updated_today:
                generate_repository_documentation.delay(repository.id, 'readme')
                logger.info(f"Daily Documentation update queued via Push for {repository.full_name}")
        
        else:
            logger.debug(f"Push received for {repository.full_name}. Skipping doc update (Frequency is {frequency}).")

    except Exception as e:
        logger.warning(f"Could not process documentation logic in webhook: {e}")

def handle_pull_request_event(webhook_event):
    payload = webhook_event.payload
    action = payload.get('action')
    repository = webhook_event.repository
    pr_data = payload.get('pull_request', {})
    pr_number = pr_data.get('number')

    logger.info(f"PR webhook received: action={action}, repo={repository.full_name}, PR=#{pr_number}")

    if action in ['opened', 'synchronize', 'reopened']:
        from .models import PullRequest
        from .tasks import process_pr_webhook_event
        from django.utils.dateparse import parse_datetime

        # Upsert the PR directly from webhook payload (synchronous, no race condition)
        pr, created = PullRequest.objects.update_or_create(
            repository=repository,
            number=pr_number,
            defaults={
                'github_id': str(pr_data.get('id', '')),
                'title': pr_data.get('title', ''),
                'body': pr_data.get('body') or '',
                'state': pr_data.get('state', 'open'),
                'html_url': pr_data.get('html_url', ''),
                'author_login': pr_data.get('user', {}).get('login', 'unknown'),
                'author_avatar_url': pr_data.get('user', {}).get('avatar_url'),
                'head_branch': pr_data.get('head', {}).get('ref', ''),
                'base_branch': pr_data.get('base', {}).get('ref', ''),
                'additions': pr_data.get('additions', 0),
                'deletions': pr_data.get('deletions', 0),
                'changed_files': pr_data.get('changed_files', 0),
                'comments_count': pr_data.get('comments', 0),
                'review_comments_count': pr_data.get('review_comments', 0),
                'commits_count': pr_data.get('commits', 0),
                'merged': pr_data.get('merged', False),
                'merged_at': parse_datetime(pr_data['merged_at']) if pr_data.get('merged_at') else None,
                'closed_at': parse_datetime(pr_data['closed_at']) if pr_data.get('closed_at') else None,
                'created_at': parse_datetime(pr_data.get('created_at')),
                'updated_at': parse_datetime(pr_data.get('updated_at')),
            }
        )
        logger.info(f"PR #{pr_number} {'created' if created else 'updated'} in DB. Queuing automation...")
        process_pr_webhook_event.delay(pr.id)
    try:
        from .models import UserPreferences
        prefs = webhook_event.repository.user.preferences
        if prefs.auto_generate_insights and prefs.insights_frequency == 'realtime':
            from .tasks import generate_insights_for_repository
            generate_insights_for_repository.delay(webhook_event.repository.id)
            logger.info(f"Realtime insights queued for {webhook_event.repository.full_name}")
    except Exception as e:
        logger.warning(f"Could not queue realtime insights: {e}")

    # Also queue a full sync in the background
    from .tasks import sync_pull_requests
    sync_pull_requests.delay(repository.id)
def handle_ping_event(webhook_event):
    """
    Handle ping event - webhook setup confirmation
    """
    logger.info(f"Received ping event for {webhook_event.repository.full_name}")
    # Just log it, no action needed
def handle_issues_event(webhook_event):
    """
    Handle issues event - issue opened, closed, labeled, etc.
    Triggers realtime insights if enabled.
    """
    logger.info(f"Processing issues event for {webhook_event.repository.full_name}")

    # Sync issues in background
    from .tasks import sync_issues
    sync_issues.delay(webhook_event.repository.id)

    # Trigger realtime insights if enabled
    try:
        prefs = webhook_event.repository.user.preferences
        if prefs.auto_generate_insights and prefs.insights_frequency == 'realtime':
            from .tasks import generate_insights_for_repository
            generate_insights_for_repository.delay(webhook_event.repository.id)
            logger.info(f"Realtime insights queued (issues event) for {webhook_event.repository.full_name}")
    except Exception as e:
        logger.warning(f"Could not queue realtime insights for issues event: {e}")