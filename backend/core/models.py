from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


class User(AbstractUser):
    """
    Custom User model extending Django's AbstractUser
    Stores GitHub OAuth information
    """
    github_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    github_login = models.CharField(max_length=100, unique=True, null=True, blank=True)
    github_access_token = models.CharField(max_length=255, null=True, blank=True)
    github_avatar_url = models.URLField(max_length=500, null=True, blank=True)
    github_profile_url = models.URLField(max_length=500, null=True, blank=True)
    github_bio = models.TextField(null=True, blank=True)
    github_company = models.CharField(max_length=200, null=True, blank=True)
    github_location = models.CharField(max_length=200, null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
    
    def __str__(self):
        return self.github_login or self.username


class Repository(models.Model):
    """
    GitHub Repository model
    Stores basic repository information
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='repositories')
    
    # GitHub repository data
    github_id = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=255)
    full_name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    html_url = models.URLField(max_length=500)
    
    # Repository metadata
    is_private = models.BooleanField(default=False)
    is_fork = models.BooleanField(default=False)
    language = models.CharField(max_length=100, null=True, blank=True)
    stars_count = models.IntegerField(default=0)
    forks_count = models.IntegerField(default=0)
    open_issues_count = models.IntegerField(default=0)
    watchers_count = models.IntegerField(default=0)
    
    # Additional details (Phase 1)
    default_branch = models.CharField(max_length=100, default='main')
    size = models.IntegerField(default=0)  # in KB
    has_issues = models.BooleanField(default=True)
    has_projects = models.BooleanField(default=True)
    has_wiki = models.BooleanField(default=True)
    
    # Tracking
    is_active = models.BooleanField(default=True)
    webhook_id = models.CharField(max_length=100, null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    github_created_at = models.DateTimeField(null=True, blank=True)
    github_updated_at = models.DateTimeField(null=True, blank=True)
    github_pushed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'repositories'
        verbose_name = 'Repository'
        verbose_name_plural = 'Repositories'
        ordering = ['-github_updated_at']
    
    def __str__(self):
        return self.full_name


class PullRequest(models.Model):
    """
    GitHub Pull Request model
    """
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='pull_requests')
    
    # PR data
    github_id = models.CharField(max_length=100)
    number = models.IntegerField()
    title = models.CharField(max_length=500)
    body = models.TextField(null=True, blank=True)
    state = models.CharField(max_length=20)  # open, closed, merged
    html_url = models.URLField(max_length=500)
    
    # Author info
    author_login = models.CharField(max_length=100)
    author_avatar_url = models.URLField(max_length=500, null=True, blank=True)
    
    # Branches
    head_branch = models.CharField(max_length=255)
    base_branch = models.CharField(max_length=255)
    
    # Stats
    additions = models.IntegerField(default=0)
    deletions = models.IntegerField(default=0)
    changed_files = models.IntegerField(default=0)
    comments_count = models.IntegerField(default=0)
    review_comments_count = models.IntegerField(default=0)
    commits_count = models.IntegerField(default=0)
    
    # Status
    mergeable = models.BooleanField(null=True, blank=True)
    merged = models.BooleanField(default=False)
    merged_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    synced_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'pull_requests'
        unique_together = ['repository', 'number']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"#{self.number}: {self.title}"


class Issue(models.Model):
    """
    GitHub Issue model
    """
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='issues')
    
    # Issue data
    github_id = models.CharField(max_length=100)
    number = models.IntegerField()
    title = models.CharField(max_length=500)
    body = models.TextField(null=True, blank=True)
    state = models.CharField(max_length=20)  # open, closed
    html_url = models.URLField(max_length=500)
    
    # Author info
    author_login = models.CharField(max_length=100)
    author_avatar_url = models.URLField(max_length=500, null=True, blank=True)
    
    # Metadata
    labels = models.JSONField(default=list, blank=True)
    assignees = models.JSONField(default=list, blank=True)
    comments_count = models.IntegerField(default=0)
    
    # Status
    closed_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    synced_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'issues'
        unique_together = ['repository', 'number']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"#{self.number}: {self.title}"


class Commit(models.Model):
    """
    GitHub Commit model
    """
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='commits')
    
    # Commit data
    sha = models.CharField(max_length=40, unique=True)
    message = models.TextField()
    html_url = models.URLField(max_length=500)
    
    # Author info
    author_name = models.CharField(max_length=255)
    author_email = models.CharField(max_length=255)
    author_login = models.CharField(max_length=100, null=True, blank=True)
    author_avatar_url = models.URLField(max_length=500, null=True, blank=True)
    
    # Stats
    additions = models.IntegerField(default=0)
    deletions = models.IntegerField(default=0)
    total_changes = models.IntegerField(default=0)
    
    # Timestamp
    committed_at = models.DateTimeField()
    synced_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'commits'
        ordering = ['-committed_at']
    
    def __str__(self):
        return f"{self.sha[:7]}: {self.message[:50]}"


class Contributor(models.Model):
    """
    Repository Contributor model
    """
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='contributors')
    
    # Contributor data
    github_login = models.CharField(max_length=100)
    avatar_url = models.URLField(max_length=500, null=True, blank=True)
    html_url = models.URLField(max_length=500)
    
    # Stats
    contributions = models.IntegerField(default=0)
    
    # Timestamp
    synced_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'contributors'
        unique_together = ['repository', 'github_login']
        ordering = ['-contributions']
    
    def __str__(self):
        return f"{self.github_login} ({self.contributions} contributions)"


class RepositoryWebhook(models.Model):
    """
    GitHub Webhook configuration for repository
    """
    repository = models.OneToOneField(Repository, on_delete=models.CASCADE, related_name='webhook')
    
    # Webhook data
    github_webhook_id = models.CharField(max_length=100)
    webhook_url = models.URLField(max_length=500)
    secret = models.CharField(max_length=100)
    
    # Configuration
    events = models.JSONField(default=list)  # List of subscribed events
    is_active = models.BooleanField(default=True)
    
    # Stats
    last_delivery_at = models.DateTimeField(null=True, blank=True)
    total_deliveries = models.IntegerField(default=0)
    failed_deliveries = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'repository_webhooks'
    
    def __str__(self):
        return f"Webhook for {self.repository.full_name}"


class WebhookEvent(models.Model):
    """
    GitHub Webhook Event log
    """
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='webhook_events')
    
    # Event data
    event_type = models.CharField(max_length=50)  # push, pull_request, issues, etc.
    delivery_id = models.CharField(max_length=100, unique=True)
    payload = models.JSONField()
    
    # Processing status
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    
    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'webhook_events'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.event_type} - {self.delivery_id}"


class GitHubOAuthState(models.Model):
    """
    Temporary storage for OAuth state parameter
    Used to prevent CSRF attacks during GitHub OAuth flow
    """
    state = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'github_oauth_states'
        verbose_name = 'GitHub OAuth State'
        verbose_name_plural = 'GitHub OAuth States'
    
    def __str__(self):
        return f"State: {self.state[:20]}..."
    
    @classmethod
    def cleanup_old_states(cls):
        """
        Remove states older than 10 minutes
        """
        from datetime import timedelta
        threshold = timezone.now() - timedelta(minutes=10)
        cls.objects.filter(created_at__lt=threshold).delete()


class Conversation(models.Model):
    """
    AI Chat Conversation
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations')
    title = models.CharField(max_length=255, default='New Conversation')
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'conversations'
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"{self.user.github_login}: {self.title}"


class ChatMessage(models.Model):
    """
    Individual chat messages in a conversation
    """
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]
    
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    
    # Metadata
    tokens_used = models.IntegerField(default=0)
    processing_time = models.FloatField(default=0.0)  # in seconds
    
    # Timestamp
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'chat_messages'
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.role}: {self.content[:50]}..."
# ... (keep all existing models)

class PRAnalysis(models.Model):
    """
    AI Analysis of Pull Request
    """
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    pull_request = models.OneToOneField(PullRequest, on_delete=models.CASCADE, related_name='analysis')
    
    # Analysis results
    summary = models.TextField()
    issues_found = models.IntegerField(default=0)
    security_score = models.IntegerField(default=100)  # 0-100
    performance_score = models.IntegerField(default=100)
    quality_score = models.IntegerField(default=100)
    complexity_score = models.IntegerField(default=0)
    
    # Detailed findings
    security_issues = models.JSONField(default=list)
    performance_issues = models.JSONField(default=list)
    code_smells = models.JSONField(default=list)
    positive_points = models.JSONField(default=list)
    
    # Metadata
    analyzed_at = models.DateTimeField(auto_now_add=True)
    analysis_time = models.FloatField(default=0.0)
    tokens_used = models.IntegerField(default=0)
    
    # GitHub integration
    comment_posted = models.BooleanField(default=False)
    github_comment_id = models.CharField(max_length=100, null=True, blank=True)
    
    class Meta:
        db_table = 'pr_analyses'
        verbose_name = 'PR Analysis'
        verbose_name_plural = 'PR Analyses'
    
    def __str__(self):
        return f"Analysis of PR #{self.pull_request.number}"


class CodeInsight(models.Model):
    """
    Proactive AI insights about repositories
    """
    INSIGHT_TYPES = [
        ('alert', 'Alert'),
        ('suggestion', 'Suggestion'),
        ('win', 'Win'),
        ('trend', 'Trend'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='insights')
    
    # Insight details
    insight_type = models.CharField(max_length=20, choices=INSIGHT_TYPES)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    title = models.CharField(max_length=255)
    description = models.TextField()
    recommendation = models.TextField(null=True, blank=True)
    
    # Metadata
    category = models.CharField(max_length=50)  # security, performance, quality, etc.
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    # Links
    related_pr = models.ForeignKey(PullRequest, null=True, blank=True, on_delete=models.SET_NULL)
    related_issue = models.ForeignKey(Issue, null=True, blank=True, on_delete=models.SET_NULL)
    action_url = models.URLField(max_length=500, null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'code_insights'
        ordering = ['-priority', '-created_at']
    
    def __str__(self):
        return f"{self.insight_type}: {self.title}"


class DocumentationGeneration(models.Model):
    """
    Track documentation generation requests
    """
    DOC_TYPES = [
        ('readme', 'README'),
        ('api', 'API Documentation'),
        ('contributing', 'Contributing Guide'),
        ('changelog', 'Changelog'),
        ('full', 'Full Documentation'),
    ]
    
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='documentation_generations')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    # Request details
    doc_type = models.CharField(max_length=20, choices=DOC_TYPES)
    options = models.JSONField(default=dict)
    
    # Generation results
    status = models.CharField(max_length=20, default='pending')  # pending, processing, completed, failed
    content = models.TextField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    
    # Metadata
    tokens_used = models.IntegerField(default=0)
    generation_time = models.FloatField(default=0.0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'documentation_generations'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.doc_type} for {self.repository.full_name}"


class CommitAnalysis(models.Model):
    """
    Analysis of commit quality
    """
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='commit_analyses')
    
    # Time period
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    
    # Analysis results
    total_commits = models.IntegerField(default=0)
    good_commits = models.IntegerField(default=0)
    needs_improvement = models.IntegerField(default=0)
    quality_score = models.IntegerField(default=0)  # 0-100
    
    # Detailed findings
    issues = models.JSONField(default=list)
    recommendations = models.JSONField(default=list)
    best_commits = models.JSONField(default=list)
    
    # Metadata
    analyzed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'commit_analyses'
        ordering = ['-analyzed_at']
    
    def __str__(self):
        return f"Commit analysis for {self.repository.full_name} ({self.period_start.date()})"
# ... (keep all existing models)

from django.core.validators import MinValueValidator, MaxValueValidator


class UserPreferences(models.Model):
    """
    Global user preferences for automation features
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='preferences')
    
    # PR Analysis Settings
    auto_analyze_prs = models.BooleanField(default=False, help_text="Automatically analyze PRs when opened/updated")
    skip_draft_prs = models.BooleanField(default=True, help_text="Skip analysis for draft PRs")
    min_lines_for_analysis = models.IntegerField(default=50, validators=[MinValueValidator(1)], help_text="Minimum changed lines to trigger analysis")
    auto_post_comments = models.BooleanField(default=False, help_text="Automatically post analysis to GitHub (vs manual review)")
    
    # Documentation Settings
    auto_update_docs = models.BooleanField(default=False, help_text="Automatically update documentation")
    docs_update_frequency = models.CharField(
        max_length=20,
        choices=[
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
            ('manual', 'Manual Only'),
        ],
        default='weekly'
    )
    docs_min_changes = models.IntegerField(default=100, validators=[MinValueValidator(1)], help_text="Minimum code changes to trigger doc update")
    
    # Insights Settings
    auto_generate_insights = models.BooleanField(default=True, help_text="Automatically generate insights")
    insights_frequency = models.CharField(
        max_length=20,
        choices=[
            ('realtime', 'Real-time'),
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('manual', 'Manual Only'),
        ],
        default='daily'
    )
    
    # Notification Settings
    email_critical_issues = models.BooleanField(default=True, help_text="Email alerts for critical security issues")
    email_daily_digest = models.BooleanField(default=False, help_text="Daily summary email")
    slack_notifications = models.BooleanField(default=False, help_text="Send notifications to Slack")
    slack_webhook_url = models.URLField(max_length=500, null=True, blank=True)
    
    # Cost & Rate Limiting
    daily_token_limit = models.IntegerField(default=100000, validators=[MinValueValidator(1000)], help_text="Daily API token limit")
    pause_on_limit = models.BooleanField(default=True, help_text="Pause automation when limit reached")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_preferences'
        verbose_name = 'User Preference'
        verbose_name_plural = 'User Preferences'
    
    def __str__(self):
        return f"Preferences for {self.user.github_login}"


class RepositorySettings(models.Model):
    """
    Per-repository settings that override user preferences
    """
    repository = models.OneToOneField(Repository, on_delete=models.CASCADE, related_name='settings')
    
    # Override Controls
    override_global = models.BooleanField(default=False, help_text="Use custom settings instead of global preferences")
    
    # PR Analysis Settings (nullable = use global if not overridden)
    auto_analyze_prs = models.BooleanField(null=True, blank=True)
    skip_draft_prs = models.BooleanField(null=True, blank=True)
    min_lines_for_analysis = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    auto_post_comments = models.BooleanField(null=True, blank=True)
    
    # Documentation Settings
    auto_update_docs = models.BooleanField(null=True, blank=True)
    docs_update_frequency = models.CharField(max_length=20, null=True, blank=True)
    docs_min_changes = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    
    # Insights Settings
    auto_generate_insights = models.BooleanField(null=True, blank=True)
    insights_frequency = models.CharField(max_length=20, null=True, blank=True)
    
    # Feature Toggles
    enable_pr_analysis = models.BooleanField(default=True, help_text="Enable PR analysis for this repo")
    enable_insights = models.BooleanField(default=True, help_text="Enable insights generation")
    enable_documentation = models.BooleanField(default=True, help_text="Enable documentation updates")
    enable_webhooks = models.BooleanField(default=True, help_text="Enable webhook automation")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'repository_settings'
        verbose_name = 'Repository Setting'
        verbose_name_plural = 'Repository Settings'
    
    def __str__(self):
        return f"Settings for {self.repository.full_name}"
    
    def get_effective_settings(self):
        try:
            user_prefs = self.repository.user.preferences
        except UserPreferences.DoesNotExist:
            user_prefs = UserPreferences.objects.create(
            user=self.repository.user,
            auto_analyze_prs=False,
        )
        
        if not self.override_global:
            # Use global preferences
            return {
                'auto_analyze_prs': user_prefs.auto_analyze_prs if self.enable_pr_analysis else False,
                'skip_draft_prs': user_prefs.skip_draft_prs,
                'min_lines_for_analysis': user_prefs.min_lines_for_analysis,
                'auto_post_comments': user_prefs.auto_post_comments,
                'auto_update_docs': user_prefs.auto_update_docs if self.enable_documentation else False,
                'docs_update_frequency': user_prefs.docs_update_frequency,
                'docs_min_changes': user_prefs.docs_min_changes,
                'auto_generate_insights': user_prefs.auto_generate_insights if self.enable_insights else False,
                'insights_frequency': user_prefs.insights_frequency,
            }
        else:
            # Use repository overrides (with fallback to global)
            return {
                'auto_analyze_prs': self.auto_analyze_prs if self.auto_analyze_prs is not None else user_prefs.auto_analyze_prs,
                'skip_draft_prs': self.skip_draft_prs if self.skip_draft_prs is not None else user_prefs.skip_draft_prs,
                'min_lines_for_analysis': self.min_lines_for_analysis if self.min_lines_for_analysis is not None else user_prefs.min_lines_for_analysis,
                'auto_post_comments': self.auto_post_comments if self.auto_post_comments is not None else user_prefs.auto_post_comments,
                'auto_update_docs': self.auto_update_docs if self.auto_update_docs is not None else user_prefs.auto_update_docs,
                'docs_update_frequency': self.docs_update_frequency if self.docs_update_frequency else user_prefs.docs_update_frequency,
                'docs_min_changes': self.docs_min_changes if self.docs_min_changes is not None else user_prefs.docs_min_changes,
                'auto_generate_insights': self.auto_generate_insights if self.auto_generate_insights is not None else user_prefs.auto_generate_insights,
                'insights_frequency': self.insights_frequency if self.insights_frequency else user_prefs.insights_frequency,
            }


class WebhookConfiguration(models.Model):
    """
    Track webhook setup status for repositories
    """
    repository = models.OneToOneField(Repository, on_delete=models.CASCADE, related_name='webhook_config')
    
    # Webhook Status
    is_configured = models.BooleanField(default=False, help_text="Webhook successfully set up on GitHub")
    github_webhook_id = models.CharField(max_length=100, null=True, blank=True, help_text="GitHub's webhook ID")
    webhook_url = models.URLField(max_length=500, null=True, blank=True)
    webhook_secret = models.CharField(max_length=255, null=True, blank=True, help_text="Secret for webhook signature verification")
    
    # Events Subscribed
    events = models.JSONField(default=list, help_text="List of GitHub events this webhook listens to")
    
    # Health Monitoring
    last_ping = models.DateTimeField(null=True, blank=True, help_text="Last successful ping from GitHub")
    last_delivery = models.DateTimeField(null=True, blank=True, help_text="Last event delivery")
    consecutive_failures = models.IntegerField(default=0, help_text="Count of consecutive failed deliveries")
    is_active = models.BooleanField(default=True, help_text="Webhook is active and receiving events")
    
    # Error Tracking
    last_error = models.TextField(null=True, blank=True)
    error_count = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'webhook_configurations'
        verbose_name = 'Webhook Configuration'
        verbose_name_plural = 'Webhook Configurations'
    
    def __str__(self):
        status = "Active" if self.is_configured and self.is_active else "Inactive"
        return f"Webhook for {self.repository.full_name} ({status})"


class AutomationLog(models.Model):
    """
    Log all automated actions for audit trail
    """
    ACTION_TYPES = [
        ('pr_analysis', 'PR Analysis'),
        ('insight_generation', 'Insight Generation'),
        ('doc_update', 'Documentation Update'),
        ('webhook_event', 'Webhook Event'),
        ('scheduled_task', 'Scheduled Task'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ]
    
    # Action Details
    action_type = models.CharField(max_length=50, choices=ACTION_TYPES)
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='automation_logs', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='automation_logs')
    
    # Execution Details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    trigger = models.CharField(max_length=100, help_text="What triggered this action (webhook, schedule, manual)")
    description = models.TextField(help_text="Human-readable description of the action")
    
    # Related Objects
    pull_request = models.ForeignKey(PullRequest, on_delete=models.SET_NULL, null=True, blank=True)
    task_id = models.CharField(max_length=255, null=True, blank=True, help_text="Celery task ID")
    
    # Results
    result_summary = models.TextField(null=True, blank=True, help_text="Summary of what was accomplished")
    error_message = models.TextField(null=True, blank=True)
    
    # Performance Metrics
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    
    # Cost Tracking
    tokens_used = models.IntegerField(default=0)
    api_calls_made = models.IntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'automation_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['action_type']),
        ]
    
    def __str__(self):
        return f"{self.action_type} - {self.status} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"


class CostTracking(models.Model):
    """
    Track API usage and costs per user/repository
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cost_tracking')
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='cost_tracking', null=True, blank=True)
    
    # Date tracking
    date = models.DateField(help_text="Date of usage")
    
    # Usage Metrics
    pr_analyses_count = models.IntegerField(default=0)
    insights_generated_count = models.IntegerField(default=0)
    docs_updated_count = models.IntegerField(default=0)
    
    # Token Usage
    tokens_used = models.IntegerField(default=0, help_text="Total tokens consumed")
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    
    # API Calls
    api_calls = models.IntegerField(default=0, help_text="Number of API requests made")
    
    # Estimated Cost (USD)
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=4, default=0.0000)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'cost_tracking'
        unique_together = ['user', 'repository', 'date']
        ordering = ['-date']
        indexes = [
            models.Index(fields=['user', '-date']),
            models.Index(fields=['repository', '-date']),
        ]
    
    def __str__(self):
        repo_str = f" - {self.repository.full_name}" if self.repository else ""
        return f"{self.user.github_login}{repo_str} on {self.date}"
    
    def calculate_cost(self):
        """
        Calculate estimated cost based on Anthropic pricing
        Claude Sonnet: $3 per million input tokens, $15 per million output tokens
        """
        input_cost = (self.input_tokens / 1_000_000) * 0.59
        output_cost = (self.output_tokens / 1_000_000) * 0.79
        self.estimated_cost = input_cost + output_cost
        return self.estimated_cost


# =============================================================================
# PHASE 5 MODELS
# =============================================================================

class PRDescriptionTemplate(models.Model):
    """AI-generated PR description."""
    pull_request = models.OneToOneField(PullRequest, on_delete=models.CASCADE, related_name='description_template')

    # Generated content
    generated_description = models.TextField(blank=True)
    summary = models.TextField(blank=True)
    features = models.JSONField(default=list, blank=True)
    bug_fixes = models.JSONField(default=list, blank=True)
    breaking_changes = models.JSONField(default=list, blank=True)
    refactors = models.JSONField(default=list, blank=True)

    # Flags
    has_tests = models.BooleanField(default=False)
    requires_migration = models.BooleanField(default=False)
    applied_to_github = models.BooleanField(default=False)

    # AI metadata
    tokens_used = models.IntegerField(default=0)
    generation_time = models.FloatField(default=0.0)
    model_used = models.CharField(max_length=100, blank=True)

    # Status
    user_approved = models.BooleanField(default=False)
    user_edited = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'pr_description_templates'

    def __str__(self):
        return f"Description for PR #{self.pull_request.number}"


class CodeOwnership(models.Model):
    """File-level code ownership data."""
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='code_ownerships')
    file_path = models.CharField(max_length=500)
    primary_owner = models.CharField(max_length=200)
    contributors = models.JSONField(default=list, blank=True)
    commits_count = models.IntegerField(default=0)
    lines_authored = models.IntegerField(default=0)
    expertise_score = models.IntegerField(default=0)
    last_modified = models.DateTimeField(null=True, blank=True)
    analyzed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'code_ownership'
        unique_together = ['repository', 'file_path']

    def __str__(self):
        return f"{self.file_path} → {self.primary_owner}"


class ReviewerRecommendation(models.Model):
    """Suggested reviewer for a pull request."""
    REVIEWER_TYPES = [
        ('primary', 'Primary'),
        ('secondary', 'Secondary'),
        ('shadow', 'Shadow'),
    ]

    pull_request = models.ForeignKey(PullRequest, on_delete=models.CASCADE, related_name='reviewer_recommendations')
    github_username = models.CharField(max_length=200)
    reviewer_type = models.CharField(max_length=20, choices=REVIEWER_TYPES, default='secondary')
    confidence_score = models.IntegerField(default=0)
    recommendation_reason = models.TextField(blank=True)
    files_relevant = models.JSONField(default=list, blank=True)
    expertise_areas = models.JSONField(default=list, blank=True)
    requested_on_github = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reviewer_recommendations'

    def __str__(self):
        return f"{self.github_username} ({self.reviewer_type}) for PR #{self.pull_request.number}"


class DeveloperExpertise(models.Model):
    """Developer expertise mapping within a repository."""
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='developer_expertise')
    github_username = models.CharField(max_length=200)
    expertise_areas = models.JSONField(default=list, blank=True)
    expertise_map = models.JSONField(default=dict, blank=True)
    total_commits = models.IntegerField(default=0)
    total_prs_authored = models.IntegerField(default=0)
    files_touched = models.JSONField(default=list, blank=True)
    active_days = models.IntegerField(default=0)
    first_contribution = models.DateTimeField(null=True, blank=True)
    last_contribution = models.DateTimeField(null=True, blank=True)
    analyzed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'developer_expertise'
        unique_together = ['repository', 'github_username']

    def __str__(self):
        return f"{self.github_username} expertise in {self.repository.full_name}"


# =============================================================================
# PHASE 7 MODELS: Conflict Detection & Dependency Analysis
# =============================================================================

class ConflictDetection(models.Model):
    """Pre-emptive conflict detection between open PRs."""
    CONFLICT_TYPE_CHOICES = [
        ('file_level', 'File Level'),
        ('function_level', 'Function Level'),
        ('symbol_level', 'Symbol Level'),
        ('semantic', 'Semantic'),
        ('dependency', 'Dependency'),
    ]
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    pr_1 = models.ForeignKey(PullRequest, on_delete=models.CASCADE, related_name='conflicts_as_pr1')
    pr_2 = models.ForeignKey(PullRequest, on_delete=models.CASCADE, related_name='conflicts_as_pr2')

    # Conflict details
    conflict_type = models.CharField(max_length=20, choices=CONFLICT_TYPE_CHOICES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='medium')
    affected_files = models.JSONField(default=list, blank=True)
    conflicting_symbols = models.JSONField(default=list, blank=True)
    resolution_suggestion = models.TextField(blank=True)
    merge_order = models.JSONField(default=list, blank=True)

    # Status
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    notified = models.BooleanField(default=False)
    notified_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    detected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'conflict_detections'
        ordering = ['-detected_at']
        indexes = [
            models.Index(fields=['pr_1', 'pr_2']),
            models.Index(fields=['severity']),
            models.Index(fields=['is_resolved']),
            models.Index(fields=['-detected_at']),
        ]

    def __str__(self):
        return f"Conflict: PR #{self.pr_1.number} ↔ PR #{self.pr_2.number} ({self.severity})"


class SymbolMap(models.Model):
    """Code symbol mapping per file per PR for conflict analysis."""
    SYMBOL_TYPE_CHOICES = [
        ('function', 'Function'),
        ('class', 'Class'),
        ('variable', 'Variable'),
        ('import', 'Import'),
    ]

    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='symbol_maps')
    pull_request = models.ForeignKey(PullRequest, on_delete=models.CASCADE, related_name='symbol_maps', null=True, blank=True)

    # Symbol details
    file_path = models.CharField(max_length=500)
    symbol_type = models.CharField(max_length=20, choices=SYMBOL_TYPE_CHOICES)
    symbol_name = models.CharField(max_length=255)
    line_start = models.IntegerField(default=0)
    line_end = models.IntegerField(default=0)

    # Signature & relationships
    signature = models.JSONField(default=dict, blank=True)
    dependencies = models.JSONField(default=list, blank=True)
    dependents = models.JSONField(default=list, blank=True)

    # Change detection
    hash = models.CharField(max_length=64, blank=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'symbol_maps'
        indexes = [
            models.Index(fields=['repository', 'file_path']),
            models.Index(fields=['symbol_name']),
            models.Index(fields=['pull_request']),
            models.Index(fields=['repository', 'symbol_name']),
        ]

    def __str__(self):
        return f"{self.symbol_type}: {self.symbol_name} in {self.file_path}"


class DependencyAnalysis(models.Model):
    """Dependency impact analysis per package per repository."""
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='dependency_analyses')

    # Package info
    package_name = models.CharField(max_length=255)
    current_version = models.CharField(max_length=50)
    latest_version = models.CharField(max_length=50, blank=True)
    latest_safe_version = models.CharField(max_length=50, blank=True)

    # Breaking changes
    has_breaking_changes = models.BooleanField(default=False)
    breaking_changes = models.JSONField(default=list, blank=True)
    changelog_url = models.URLField(max_length=500, blank=True)

    # Impact analysis
    impact_score = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    files_affected = models.JSONField(default=list, blank=True)
    code_patterns_affected = models.JSONField(default=list, blank=True)
    estimated_refactor_hours = models.IntegerField(default=0)

    # Migration
    migration_script = models.TextField(blank=True)

    # Timestamp
    analyzed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'dependency_analyses'
        ordering = ['-impact_score']
        indexes = [
            models.Index(fields=['repository', 'package_name']),
            models.Index(fields=['impact_score']),
            models.Index(fields=['-analyzed_at']),
        ]

    def __str__(self):
        return f"{self.package_name} {self.current_version} → {self.latest_version} (Impact: {self.impact_score})"


class DependencyUpdate(models.Model):
    """Track applied dependency upgrade operations."""
    UPDATE_TYPE_CHOICES = [
        ('major', 'Major'),
        ('minor', 'Minor'),
        ('patch', 'Patch'),
    ]

    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='dependency_updates')

    # Update details
    package_name = models.CharField(max_length=255)
    from_version = models.CharField(max_length=50)
    to_version = models.CharField(max_length=50)
    update_type = models.CharField(max_length=10, choices=UPDATE_TYPE_CHOICES)

    # Status
    applied = models.BooleanField(default=False)
    pull_request = models.ForeignKey(PullRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name='dependency_updates')
    migration_script_used = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'dependency_updates'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['repository', 'package_name']),
        ]

    def __str__(self):
        status = "Applied" if self.applied else "Pending"
        return f"{self.package_name} {self.from_version} → {self.to_version} ({status})"