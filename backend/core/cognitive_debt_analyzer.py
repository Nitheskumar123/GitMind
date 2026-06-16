"""
Cognitive Debt Analyzer
-----------------------
Reads git commit history and uses the GitHub API to get actual file-level data
for each commit. Calculates a comprehension score (0–100) for every file.

Three signals:
  1. AI authorship — was this file written by AI?
  2. Human engagement — did any human modify it afterward?
  3. Contributor spread — how many people meaningfully touched it?

Score formula:
  score = (human_edit_ratio × 50) + (contributor_spread × 30) + (recency_bonus × 20)

Risk levels:
  70–100 = green  (team understands well)
  35–69  = amber  (partial — risky to change)
  0–34   = red    (nobody understands this file)
"""

import re
import logging
from datetime import timedelta
from collections import defaultdict

from django.utils import timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patterns that suggest a commit was AI-generated
# ---------------------------------------------------------------------------
AI_COMMIT_PATTERNS = [
    re.compile(r'\bcopilot\b', re.IGNORECASE),
    re.compile(r'\bai[\s\-_]?generated\b', re.IGNORECASE),
    re.compile(r'\bgenerated[\s\-_]?by[\s\-_]?ai\b', re.IGNORECASE),
    re.compile(r'\bauto[\s\-_]?generated\b', re.IGNORECASE),
    re.compile(r'\baccepted[\s\-_]?suggestion\b', re.IGNORECASE),
    re.compile(r'\bgithub[\s\-_]?copilot\b', re.IGNORECASE),
    re.compile(r'\bchatgpt\b', re.IGNORECASE),
    re.compile(r'\bgpt[\s\-_]?4\b', re.IGNORECASE),
    re.compile(r'\bclaude\b', re.IGNORECASE),
    re.compile(r'\bgemini\b', re.IGNORECASE),
    re.compile(r'\bai[\s\-_]?assist\b', re.IGNORECASE),
    re.compile(r'\bcode[\s\-_]?gen\b', re.IGNORECASE),
    re.compile(r'\b🤖\b'),
    re.compile(r'\bauto[\s\-_]?complete\b', re.IGNORECASE),
    re.compile(r'\bllm\b', re.IGNORECASE),
]

# Bot authors that are definitely not human
BOT_AUTHORS = {
    'dependabot', 'dependabot[bot]', 'renovate', 'renovate[bot]',
    'github-actions', 'github-actions[bot]', 'snyk-bot', 'codecov',
    'greenkeeper', 'imgbot', 'stale[bot]', 'mergify[bot]',
}

# File patterns to ignore (generated files, configs, etc.)
IGNORED_FILE_PATTERNS = [
    re.compile(r'(^|/)node_modules/'),
    re.compile(r'(^|/)vendor/'),
    re.compile(r'(^|/)dist/'),
    re.compile(r'(^|/)build/'),
    re.compile(r'(^|/)__pycache__/'),
    re.compile(r'\.min\.(js|css)$'),
    re.compile(r'package-lock\.json$'),
    re.compile(r'yarn\.lock$'),
    re.compile(r'\.lock$'),
    re.compile(r'\.pyc$'),
    re.compile(r'(^|/)\.git/'),
    re.compile(r'(^|/)migrations/'),
]


class CognitiveDebtAnalyzer:
    """
    Analyzes commit history of a repository and produces a comprehension
    score per file.  Uses the GitHub API to fetch actual files changed
    per commit (real file paths, not guesses).

    Instantiate with a Repository object, then call run().
    """

    def __init__(self, repository):
        self.repository = repository
        self.now = timezone.now()
        self.recency_window = timedelta(days=90)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self):
        """
        Main entry point.  Fetches commit details from GitHub (with
        file-level data), computes scores, and writes to DB.
        Returns a summary dict.
        """
        from .models import Commit, FileComprehensionScore

        # Get the user's access token for GitHub API calls
        access_token = self.repository.user.github_access_token
        if not access_token:
            logger.warning(f"No access token for {self.repository.full_name} — skipping debt analysis")
            return {'files_analyzed': 0, 'red_files': 0, 'amber_files': 0, 'green_files': 0}

        # Get commits from local DB (for message/author info)
        db_commits = list(
            Commit.objects.filter(repository=self.repository)
            .order_by('committed_at')
        )

        if not db_commits:
            logger.info(f"No commits found for {self.repository.full_name} — skipping debt analysis")
            return {'files_analyzed': 0, 'red_files': 0, 'amber_files': 0, 'green_files': 0}

        # Fetch actual files changed per commit from GitHub API
        file_data = self._build_file_data_from_github(db_commits, access_token)

        if not file_data:
            logger.info(f"No file data retrieved for {self.repository.full_name}")
            return {'files_analyzed': 0, 'red_files': 0, 'amber_files': 0, 'green_files': 0}

        red = amber = green = 0
        for file_path, data in file_data.items():
            score_info = self._compute_score(data)

            FileComprehensionScore.objects.update_or_create(
                repository=self.repository,
                file_path=file_path,
                defaults={
                    'ai_authorship_pct': score_info['ai_authorship_pct'],
                    'human_edit_count': score_info['human_edit_count'],
                    'total_commit_count': score_info['total_commit_count'],
                    'unique_contributors': score_info['unique_contributors'],
                    'comprehension_score': score_info['comprehension_score'],
                    'risk_level': score_info['risk_level'],
                    'last_human_edit_at': score_info['last_human_edit_at'],
                    'suggested_reviewer': score_info['suggested_reviewer'],
                },
            )

            if score_info['risk_level'] == 'red':
                red += 1
            elif score_info['risk_level'] == 'amber':
                amber += 1
            else:
                green += 1

        total = red + amber + green
        logger.info(
            f"Cognitive debt analysis for {self.repository.full_name}: "
            f"{total} files — {red} red, {amber} amber, {green} green"
        )

        return {
            'files_analyzed': total,
            'red_files': red,
            'amber_files': amber,
            'green_files': green,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_file_data_from_github(self, db_commits, access_token):
        """
        For each commit in the DB, fetch the actual files changed from the
        GitHub API.  Returns a dict:
            file_path -> {ai_commit_count, human_commit_count, authors, last_human_edit_at}
        """
        from github import Github, GithubException

        file_data = defaultdict(lambda: {
            'authors': defaultdict(int),
            'ai_commit_count': 0,
            'human_commit_count': 0,
            'last_human_edit_at': None,
        })

        try:
            client = Github(access_token)
            repo = client.get_repo(self.repository.full_name)
        except Exception as e:
            logger.error(f"Failed to connect to GitHub API for {self.repository.full_name}: {e}")
            return file_data

        # Process up to 50 most recent commits to stay within API rate limits
        commits_to_process = db_commits[-50:]

        for db_commit in commits_to_process:
            try:
                gh_commit = repo.get_commit(db_commit.sha)
            except GithubException as e:
                logger.warning(f"Skipping commit {db_commit.sha[:7]}: GitHub API error {e.status}")
                continue
            except Exception as e:
                logger.warning(f"Skipping commit {db_commit.sha[:7]}: {e}")
                continue

            is_ai = self._is_ai_commit(db_commit)
            author = (db_commit.author_login or db_commit.author_name or 'unknown').lower()

            # gh_commit.files gives us the actual list of files changed
            if not gh_commit.files:
                continue

            for gh_file in gh_commit.files:
                file_path = gh_file.filename

                if self._should_ignore_file(file_path):
                    continue

                entry = file_data[file_path]

                if is_ai or author in BOT_AUTHORS:
                    entry['ai_commit_count'] += 1
                else:
                    entry['human_commit_count'] += 1
                    entry['authors'][author] += 1
                    if (
                        entry['last_human_edit_at'] is None
                        or db_commit.committed_at > entry['last_human_edit_at']
                    ):
                        entry['last_human_edit_at'] = db_commit.committed_at

        return file_data

    def _compute_score(self, data):
        """
        Compute the comprehension score for a single file.

        score = (human_edit_ratio × 50) + (contributor_spread × 30) + (recency_bonus × 20)
        """
        total = data['ai_commit_count'] + data['human_commit_count']
        if total == 0:
            total = 1  # avoid division by zero

        # Signal 1: human edit ratio (0.0 – 1.0)
        human_edit_ratio = data['human_commit_count'] / total

        # Signal 2: contributor spread (0.0 – 1.0, capped at 3 unique contributors)
        unique_count = len(data['authors'])
        contributor_spread = min(unique_count, 3) / 3.0

        # Signal 3: recency bonus — was there a human commit in the last 90 days?
        recency_bonus = 0.0
        if data['last_human_edit_at']:
            if (self.now - data['last_human_edit_at']) <= self.recency_window:
                recency_bonus = 1.0

        # Weighted sum
        raw_score = (
            (human_edit_ratio * 50) +
            (contributor_spread * 30) +
            (recency_bonus * 20)
        )
        score = max(0, min(100, round(raw_score)))

        # Risk level
        if score >= 70:
            risk_level = 'green'
        elif score >= 35:
            risk_level = 'amber'
        else:
            risk_level = 'red'

        # Suggested reviewer: the human who touched it most
        suggested = ''
        if data['authors']:
            suggested = max(data['authors'], key=data['authors'].get)

        # AI authorship percentage
        ai_pct = (data['ai_commit_count'] / total) * 100

        return {
            'ai_authorship_pct': round(ai_pct, 1),
            'human_edit_count': data['human_commit_count'],
            'total_commit_count': total,
            'unique_contributors': unique_count,
            'comprehension_score': score,
            'risk_level': risk_level,
            'last_human_edit_at': data['last_human_edit_at'],
            'suggested_reviewer': suggested,
        }

    def _is_ai_commit(self, commit):
        """Heuristically detect if a commit was AI-generated."""
        msg = commit.message or ''

        # Check commit message for AI patterns
        for pattern in AI_COMMIT_PATTERNS:
            if pattern.search(msg):
                return True

        # Check author name for bots
        author = (commit.author_login or commit.author_name or '').lower()
        if author in BOT_AUTHORS:
            return True

        return False

    def _should_ignore_file(self, file_path):
        """Return True if this file should be excluded from analysis."""
        for pattern in IGNORED_FILE_PATTERNS:
            if pattern.search(file_path):
                return True
        return False
