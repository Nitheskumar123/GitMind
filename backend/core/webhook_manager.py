"""
Webhook Manager Module
----------------------
This module handles the lifecycle of GitHub Webhooks for the Intelligence Platform.
It is designed to be robust against common API errors, specifically the 422 
'Unprocessable Entity' which occurs when a duplicate webhook is attempted.

Features:
- Lookup-before-create logic (Duplicate Detection)
- Signature secret synchronization
- Health monitoring and validation
- Automatic recovery of deleted or broken hooks
"""

import requests
import secrets
import logging
import json
import time
from django.conf import settings
from django.utils import timezone
from .models import Repository, WebhookConfiguration

# Configure high-verbosity logging for Celery terminal monitoring
logger = logging.getLogger('core.webhooks')

class WebhookManager:
    """
    Manages GitHub webhook lifecycle with advanced error handling.
    """
    
    def __init__(self, repository):
        """
        Initialize the manager for a specific repository instance.
        """
        self.repository = repository
        self.user = repository.user
        self.github_token = self.user.github_access_token
        
        # Verify that we have the necessary credentials to communicate with GitHub
        if not self.github_token:
            logger.error(f"Critical: No GitHub token for user {self.user.username}")
            raise ValueError("GitHub access token missing. OAuth must be completed first.")

    # =========================================================================
    # PUBLIC API METHODS
    # =========================================================================

    def setup_webhook(self):
        """
        Main entry point to ensure a repository has an active webhook.
        
        This method follows a specific workflow to avoid 422 errors:
        1. Check local DB for existing configuration.
        2. Verify health if an ID already exists.
        3. Query GitHub API to see if the URL is already registered.
        4. Reuse the existing ID if found, otherwise create fresh.
        """
        logger.info(f"--- INITIALIZING WEBHOOK SETUP: {self.repository.full_name} ---")
        
        try:
            # 1. Database State Synchronization
            webhook_config, created = WebhookConfiguration.objects.get_or_create(
                repository=self.repository
            )
            
            # If the database already has an ID, check if it's still valid on GitHub
            if webhook_config.is_configured and webhook_config.github_webhook_id:
                health = self.check_health()
                if health['is_healthy']:
                    logger.info(f"Verified: Webhook {webhook_config.github_webhook_id} is active.")
                    return {
                        'success': True,
                        'webhook_id': webhook_config.github_webhook_id,
                        'message': 'Webhook verified as active'
                    }
                else:
                    logger.warning("Local ID found, but GitHub check failed. Re-syncing...")

            # 2. Configuration Preparation
            # We pull the base URL from settings (usually your ngrok URL)
            webhook_url = self._get_webhook_url()
            
            # Use the global webhook secret defined in your .env
            webhook_secret = getattr(settings, 'GITHUB_WEBHOOK_SECRET', None)
            if not webhook_secret:
                webhook_secret = secrets.token_urlsafe(32)
                logger.warning("GITHUB_WEBHOOK_SECRET not in settings. Generated temporary secret.")
            
            # Define the events the AI Platform needs to monitor
            events = [
                'pull_request',      # For AI Code Analysis
                'issues',            # For Insight Generation
                'push',              # For Documentation Updates
                'issue_comment',     # For Chat integration
                'pull_request_review'
            ]

            # 3. GitHub API Communication (The 'Lookup-then-Create' Strategy)
            logger.info(f"Searching GitHub for existing hooks pointing to: {webhook_url}")
            github_webhook_id = self._create_or_find_github_webhook(
                webhook_url=webhook_url,
                webhook_secret=webhook_secret,
                events=events
            )

            if not github_webhook_id:
                logger.error("Failed to acquire Webhook ID from GitHub API.")
                webhook_config.is_active = False
                webhook_config.save()
                return {'success': False, 'error': 'GitHub API error or timeout'}

            # 4. Persistence
            # Save all details to the local database to mark the repo as 'Active'
            webhook_config.is_configured = True
            webhook_config.github_webhook_id = github_webhook_id
            webhook_config.webhook_url = webhook_url
            webhook_config.webhook_secret = webhook_secret
            webhook_config.events = events
            webhook_config.is_active = True
            webhook_config.consecutive_failures = 0
            webhook_config.last_error = None
            webhook_config.updated_at = timezone.now()
            webhook_config.save()

            logger.info(f"SUCCESS: Webhook {github_webhook_id} is now registered locally.")
            return {
                'success': True,
                'webhook_id': github_webhook_id,
                'message': 'Webhook setup successfully'
            }

        except Exception as e:
            logger.exception(f"Setup Exception for {self.repository.full_name}: {str(e)}")
            return {'success': False, 'error': str(e)}

    def delete_webhook(self):
        """
        Safely removes the webhook from both GitHub and the local database.
        """
        try:
            webhook_config = WebhookConfiguration.objects.get(repository=self.repository)
            
            if webhook_config.github_webhook_id:
                logger.info(f"Requesting deletion of hook {webhook_config.github_webhook_id} from GitHub.")
                self._delete_github_webhook(webhook_config.github_webhook_id)

            webhook_config.delete()
            logger.info(f"Local record deleted for {self.repository.full_name}.")
            return {'success': True, 'message': 'Webhook removed'}

        except WebhookConfiguration.DoesNotExist:
            return {'success': False, 'error': 'No configuration found'}
        except Exception as e:
            logger.error(f"Deletion error: {e}")
            return {'success': False, 'error': str(e)}

    # =========================================================================
    # MONITORING & DIAGNOSTICS
    # =========================================================================

    def check_health(self):
        """
        Validates if the webhook is currently functional.
        """
        try:
            webhook_config = WebhookConfiguration.objects.get(repository=self.repository)
            
            if not webhook_config.github_webhook_id:
                return {'is_healthy': False, 'reason': 'No ID'}

            # Validate ID existence on GitHub
            exists = self._verify_webhook_on_github(webhook_config.github_webhook_id)
            
            is_healthy = exists and webhook_config.is_active and webhook_config.consecutive_failures < 5

            return {
                'is_healthy': is_healthy,
                'details': {
                    'github_verified': exists,
                    'is_active': webhook_config.is_active,
                    'failures': webhook_config.consecutive_failures,
                    'last_delivery': webhook_config.last_delivery
                }
            }
        except WebhookConfiguration.DoesNotExist:
            return {'is_healthy': False, 'reason': 'Record missing'}

    # =========================================================================
    # INTERNAL GITHUB API WRAPPERS
    # =========================================================================

    def _create_or_find_github_webhook(self, webhook_url, webhook_secret, events):
        """
        Implements the core logic to prevent 422 errors by checking for 
        existing hooks before attempting to create new ones.
        """
        headers = {
            'Authorization': f'token {self.github_token}',
            'Accept': 'application/vnd.github.v3+json',
            'Content-Type': 'application/json'
        }
        api_url = f"https://api.github.com/repos/{self.repository.full_name}/hooks"

        try:
            # --- PHASE 1: DUPLICATE DETECTION ---
            # Fetch all hooks from GitHub to see if our URL is already there
            response = requests.get(api_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                hooks = response.json()
                for hook in hooks:
                    github_url = hook.get('config', {}).get('url')
                    if github_url == webhook_url:
                        logger.info(f"Duplicate detected (ID: {hook['id']}). Adopting existing hook.")
                        # We return the existing ID instead of creating a new one
                        return str(hook['id'])
            
            # --- PHASE 2: CREATION ---
            # No duplicate found, proceed with POST request
            logger.info("No duplicates found on GitHub. Proceeding with creation.")
            payload = {
                'name': 'web',
                'active': True,
                'events': events,
                'config': {
                    'url': webhook_url,
                    'content_type': 'json',
                    'secret': webhook_secret,
                    'insecure_ssl': '0' 
                }
            }
            
            create_resp = requests.post(api_url, headers=headers, json=payload, timeout=10)
            
            if create_resp.status_code == 201:
                return str(create_resp.json()['id'])
            
            # Handle edge case where lookup failed but create still sees a duplicate
            if create_resp.status_code == 422:
                logger.error("422 Error: GitHub reports duplicate despite lookup. Retrying...")
                time.sleep(2)
                return self._create_or_find_github_webhook(webhook_url, webhook_secret, events)

            logger.error(f"GitHub API Error {create_resp.status_code}: {create_resp.text}")
            return None

        except Exception as e:
            logger.error(f"GitHub API Wrapper Error: {e}")
            return None

    # =========================================================================
    # LOW-LEVEL UTILITIES
    # =========================================================================

    def _get_webhook_url(self):
        """Constructs the absolute URL based on settings.py."""
        base = getattr(settings, 'WEBHOOK_BASE_URL', 'http://localhost:8000')
        base = base.rstrip('/')
        return f"{base}/api/webhooks/github/"

    def _verify_webhook_on_github(self, hook_id):
        """Check if a specific ID still exists in GitHub's database."""
        url = f"https://api.github.com/repos/{self.repository.full_name}/hooks/{hook_id}"
        headers = {'Authorization': f'token {self.github_token}', 'Accept': 'application/vnd.github.v3+json'}
        try:
            r = requests.get(url, headers=headers, timeout=5)
            return r.status_code == 200
        except:
            return False

    def _delete_github_webhook(self, hook_id):
        """API call to remove a hook from GitHub."""
        url = f"https://api.github.com/repos/{self.repository.full_name}/hooks/{hook_id}"
        headers = {'Authorization': f'token {self.github_token}', 'Accept': 'application/vnd.github.v3+json'}
        try:
            r = requests.delete(url, headers=headers, timeout=5)
            return r.status_code == 204
        except:
            return False

# =============================================================================
# GLOBAL BRIDGE FUNCTIONS (FOR TASKS.PY)
# =============================================================================

def setup_webhook_for_repository(repository):
    """Bridge for the Celery task."""
    manager = WebhookManager(repository)
    return manager.setup_webhook()

def check_all_webhooks_health():
    """Matches the exact name expected by core.tasks."""
    configs = WebhookConfiguration.objects.filter(is_configured=True)
    results = {'checked': configs.count(), 'healthy': 0, 'repaired': 0}
    
    for config in configs:
        manager = WebhookManager(config.repository)
        health = manager.check_health()
        if health['is_healthy']:
            results['healthy'] += 1
        else:
            manager.setup_webhook()
            results['repaired'] += 1
            
    return results