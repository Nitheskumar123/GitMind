"""
Phase 5: AI-powered PR Description Generator
Uses Groq to analyze commits/diffs and produce structured markdown descriptions.
"""

import os
import re
import json
import time
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', getattr(settings, 'GROQ_API_KEY', ''))
GROQ_MODEL = os.environ.get('GROQ_MODEL', getattr(settings, 'GROQ_MODEL', 'llama-3.1-8b-instant'))


class PRDescriptionGenerator:
    """Generate structured PR descriptions from commit data and diffs."""

    # Files to strip before sending to Groq (context window safeguard)
    IGNORE_PATTERNS = [
        r'package-lock\.json',
        r'yarn\.lock',
        r'pnpm-lock\.yaml',
        r'Pipfile\.lock',
        r'poetry\.lock',
        r'\.svg$',
        r'\.min\.js$',
        r'\.min\.css$',
        r'\.map$',
        r'node_modules/',
        r'__pycache__/',
        r'\.pyc$',
        r'dist/',
        r'build/',
    ]

    MAX_DIFF_CHARS = 12_000  # Hard limit for Groq context

    def __init__(self):
        self.api_key = GROQ_API_KEY
        self.model = GROQ_MODEL

    # ------------------------------------------------------------------ #
    #  PUBLIC API
    # ------------------------------------------------------------------ #
    def generate_description(self, pull_request):
        """
        Main entry point.  Accepts a PullRequest model instance,
        fetches diff data, calls Groq, and saves a PRDescriptionTemplate.
        Returns dict with success/error + metadata.
        """
        start = time.time()
        try:
            from .github_api import GitHubAPIClient
            from .models import PRDescriptionTemplate

            repo = pull_request.repository
            user = repo.user
            client = GitHubAPIClient(user.github_access_token)

            # Gather context
            commits = self._get_commit_messages(client, repo.full_name, pull_request.number)
            diff = self._get_pr_diff(client, repo.full_name, pull_request.number)
            truncated_diff = self._truncate_diff(diff)

            # Build prompt & call Groq
            prompt = self._build_prompt(pull_request, commits, truncated_diff)
            ai_response, tokens_used = self._call_groq(prompt)

            if not ai_response:
                return {'success': False, 'error': 'Groq returned empty response'}

            parsed = self._parse_response(ai_response)
            elapsed = time.time() - start

            # Persist
            template, _created = PRDescriptionTemplate.objects.update_or_create(
                pull_request=pull_request,
                defaults={
                    'generated_description': parsed.get('description', ''),
                    'summary': parsed.get('summary', ''),
                    'features': parsed.get('features', []),
                    'bug_fixes': parsed.get('bug_fixes', []),
                    'breaking_changes': parsed.get('breaking_changes', []),
                    'refactors': parsed.get('refactors', []),
                    'has_tests': parsed.get('has_tests', False),
                    'requires_migration': parsed.get('requires_migration', False),
                    'applied_to_github': False,  # Reset so user can re-apply the new version
                    'tokens_used': tokens_used,
                    'generation_time': elapsed,
                    'model_used': self.model,
                },
            )

            return {
                'success': True,
                'template_id': template.id,
                'tokens_used': tokens_used,
                'generation_time': elapsed,
            }

        except Exception as e:
            logger.error(f"PR description generation failed: {e}")
            return {'success': False, 'error': str(e)}

    def apply_to_github(self, pull_request):
        """Push the stored generated description to the GitHub PR body."""
        try:
            from .models import PRDescriptionTemplate
            from .github_api import GitHubAPIClient

            template = PRDescriptionTemplate.objects.get(pull_request=pull_request)
            repo = pull_request.repository
            client = GitHubAPIClient(repo.user.github_access_token)

            client.update_pull_request_description(
                repo.full_name, pull_request.number, template.generated_description
            )

            template.applied_to_github = True
            template.save()
            return {'success': True}

        except Exception as e:
            logger.error(f"Failed to apply description to GitHub: {e}")
            return {'success': False, 'error': str(e)}

    # ------------------------------------------------------------------ #
    #  PRIVATE HELPERS
    # ------------------------------------------------------------------ #
    def _truncate_diff(self, diff_text):
        """
        Strip noisy files (lock files, SVGs, compiled assets)
        and hard-truncate to MAX_DIFF_CHARS.
        """
        if not diff_text:
            return ''

        lines = diff_text.split('\n')
        filtered = []
        skip_file = False

        for line in lines:
            if line.startswith('diff --git'):
                skip_file = any(
                    re.search(pat, line) for pat in self.IGNORE_PATTERNS
                )
            if not skip_file:
                filtered.append(line)

        result = '\n'.join(filtered)
        if len(result) > self.MAX_DIFF_CHARS:
            result = result[:self.MAX_DIFF_CHARS] + '\n\n... [diff truncated for AI analysis]'
        return result

    def _get_commit_messages(self, client, full_name, pr_number):
        try:
            repo = client.client.get_repo(full_name)
            pr = repo.get_pull(pr_number)
            return [c.commit.message for c in pr.get_commits()]
        except Exception as e:
            logger.warning(f"Could not fetch commits: {e}")
            return []

    def _get_pr_diff(self, client, full_name, pr_number):
        try:
            import requests
            headers = {
                'Authorization': f'token {client.access_token}',
                'Accept': 'application/vnd.github.v3.diff',
            }
            url = f'https://api.github.com/repos/{full_name}/pulls/{pr_number}'
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 200:
                return resp.text
            return ''
        except Exception as e:
            logger.warning(f"Could not fetch diff: {e}")
            return ''

    def _build_prompt(self, pr, commits, diff):
        commit_text = '\n'.join(f'- {m}' for m in commits[:20]) or 'No commits'
        return f"""Analyze this Pull Request and generate a structured description.

PR Title: {pr.title}
PR Branch: {pr.head_branch} → {pr.base_branch}
Files Changed: {pr.changed_files}
Additions: +{pr.additions}  Deletions: -{pr.deletions}

Commit Messages:
{commit_text}

Diff (truncated):
{diff[:8000]}

Respond with valid JSON only:
{{
  "summary": "2-3 sentence summary of what this PR does",
  "description": "Full markdown description with ## headers",
  "features": ["list of new features"],
  "bug_fixes": ["list of bug fixes"],
  "breaking_changes": ["list of breaking changes"],
  "refactors": ["list of refactors/improvements"],
  "has_tests": true/false,
  "requires_migration": true/false
}}"""

    def _call_groq(self, prompt):
        """Call Groq API and return (content, tokens_used) tuple."""
        try:
            import requests
            resp = requests.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': self.model,
                    'messages': [
                        {'role': 'system', 'content': 'You are a PR description generator. Return valid JSON only.'},
                        {'role': 'user', 'content': prompt},
                    ],
                    'temperature': 0.3,
                    'max_tokens': 2000,
                },
                timeout=60,
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data['choices'][0]['message']['content']
                # Extract token usage from API response
                usage = data.get('usage', {})
                tokens_used = usage.get('total_tokens', 0)
                logger.info(f"Groq tokens used: {tokens_used} (prompt: {usage.get('prompt_tokens', 0)}, completion: {usage.get('completion_tokens', 0)})")
                return content, tokens_used
            else:
                logger.error(f"Groq API error {resp.status_code}: {resp.text}")
                return None, 0
        except Exception as e:
            logger.error(f"Groq call failed: {e}")
            return None, 0

    def _parse_response(self, raw):
        try:
            cleaned = re.sub(r'^```json\s*', '', raw.strip())
            cleaned = re.sub(r'```\s*$', '', cleaned)
            data = json.loads(cleaned)
            return data
        except json.JSONDecodeError:
            return {
                'description': raw,
                'summary': raw[:200],
                'features': [],
                'bug_fixes': [],
                'breaking_changes': [],
                'refactors': [],
                'has_tests': False,
                'requires_migration': False,
            }
