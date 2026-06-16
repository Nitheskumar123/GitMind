from rest_framework import serializers
from .models import (
    User, Repository, PullRequest, Issue, Commit, 
    Contributor, RepositoryWebhook, WebhookEvent,
    Conversation, ChatMessage, 
    PRAnalysis, CodeInsight, DocumentationGeneration, UserPreferences, RepositorySettings, 
    WebhookConfiguration, AutomationLog, CostTracking,
    PRDescriptionTemplate, CodeOwnership, ReviewerRecommendation, DeveloperExpertise,
    ConflictDetection, SymbolMap, DependencyAnalysis, DependencyUpdate,
    FileComprehensionScore,
)


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for User model
    """
    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'github_id',
            'github_login',
            'github_avatar_url',
            'github_profile_url',
            'github_bio',
            'github_company',
            'github_location',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class RepositorySerializer(serializers.ModelSerializer):
    """
    Serializer for Repository model
    """
    pull_requests_count = serializers.SerializerMethodField()
    issues_count = serializers.SerializerMethodField()
    commits_count = serializers.SerializerMethodField()
    contributors_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Repository
        fields = [
            'id',
            'github_id',
            'name',
            'full_name',
            'description',
            'html_url',
            'is_private',
            'is_fork',
            'language',
            'stars_count',
            'forks_count',
            'open_issues_count',
            'watchers_count',
            'default_branch',
            'size',
            'has_issues',
            'has_projects',
            'has_wiki',
            'is_active',
            'webhook_id',
            'last_synced_at',
            'created_at',
            'updated_at',
            'github_created_at',
            'github_updated_at',
            'github_pushed_at',
            'pull_requests_count',
            'issues_count',
            'commits_count',
            'contributors_count',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_pull_requests_count(self, obj):
        return obj.pull_requests.count()
    
    def get_issues_count(self, obj):
        return obj.issues.count()
    
    def get_commits_count(self, obj):
        return obj.commits.count()
    
    def get_contributors_count(self, obj):
        return obj.contributors.count()


class PullRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for PullRequest model
    """
    class Meta:
        model = PullRequest
        fields = [
            'id',
            'github_id',
            'number',
            'title',
            'body',
            'state',
            'html_url',
            'author_login',
            'author_avatar_url',
            'head_branch',
            'base_branch',
            'additions',
            'deletions',
            'changed_files',
            'comments_count',
            'review_comments_count',
            'commits_count',
            'mergeable',
            'merged',
            'merged_at',
            'closed_at',
            'created_at',
            'updated_at',
            'synced_at',
        ]


class IssueSerializer(serializers.ModelSerializer):
    """
    Serializer for Issue model
    """
    class Meta:
        model = Issue
        fields = [
            'id',
            'github_id',
            'number',
            'title',
            'body',
            'state',
            'html_url',
            'author_login',
            'author_avatar_url',
            'labels',
            'assignees',
            'comments_count',
            'closed_at',
            'created_at',
            'updated_at',
            'synced_at',
        ]


class CommitSerializer(serializers.ModelSerializer):
    """
    Serializer for Commit model
    """
    message_short = serializers.SerializerMethodField()
    
    class Meta:
        model = Commit
        fields = [
            'id',
            'sha',
            'message',
            'message_short',
            'html_url',
            'author_name',
            'author_email',
            'author_login',
            'author_avatar_url',
            'additions',
            'deletions',
            'total_changes',
            'committed_at',
            'synced_at',
        ]
    
    def get_message_short(self, obj):
        """Get first line of commit message"""
        return obj.message.split('\n')[0][:100]


class ContributorSerializer(serializers.ModelSerializer):
    """
    Serializer for Contributor model
    """
    class Meta:
        model = Contributor
        fields = [
            'id',
            'github_login',
            'avatar_url',
            'html_url',
            'contributions',
            'synced_at',
        ]


class RepositoryWebhookSerializer(serializers.ModelSerializer):
    """
    Serializer for RepositoryWebhook model
    """
    class Meta:
        model = RepositoryWebhook
        fields = [
            'id',
            'github_webhook_id',
            'webhook_url',
            'events',
            'is_active',
            'last_delivery_at',
            'total_deliveries',
            'failed_deliveries',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class WebhookEventSerializer(serializers.ModelSerializer):
    """
    Serializer for WebhookEvent model
    """
    class Meta:
        model = WebhookEvent
        fields = [
            'id',
            'event_type',
            'delivery_id',
            'payload',
            'processed',
            'processed_at',
            'error_message',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class ConversationSerializer(serializers.ModelSerializer):
    """
    Serializer for Conversation model
    """
    message_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = [
            'id',
            'title',
            'message_count',
            'last_message',
            'created_at',
            'updated_at',
        ]
    
    def get_message_count(self, obj):
        return obj.messages.count()
    
    def get_last_message(self, obj):
        last_msg = obj.messages.last()
        if last_msg:
            return {
                'role': last_msg.role,
                'content': last_msg.content[:100],
                'timestamp': last_msg.created_at
            }
        return None


class ChatMessageSerializer(serializers.ModelSerializer):
    """
    Serializer for ChatMessage model
    """
    class Meta:
        model = ChatMessage
        fields = [
            'id',
            'role',
            'content',
            'tokens_used',
            'processing_time',
            'created_at',
        ]
# ... (keep all existing serializers)

class PRAnalysisSerializer(serializers.ModelSerializer):
    """
    Serializer for PR Analysis
    """
    pull_request_number = serializers.SerializerMethodField()
    
    class Meta:
        model = PRAnalysis
        fields = [
            'id',
            'pull_request_number',
            'summary',
            'issues_found',
            'security_score',
            'performance_score',
            'quality_score',
            'complexity_score',
            'security_issues',
            'performance_issues',
            'code_smells',
            'positive_points',
            'analyzed_at',
            'analysis_time',
            'tokens_used',
            'comment_posted',
        ]
    
    def get_pull_request_number(self, obj):
        return obj.pull_request.number


class CodeInsightSerializer(serializers.ModelSerializer):
    """
    Serializer for Code Insight
    """
    repository_name = serializers.SerializerMethodField()
    
    class Meta:
        model = CodeInsight
        fields = [
            'id',
            'repository_name',
            'insight_type',
            'priority',
            'title',
            'description',
            'recommendation',
            'category',
            'is_resolved',
            'action_url',
            'created_at',
            'updated_at',
        ]
    
    def get_repository_name(self, obj):
        return obj.repository.full_name


class DocumentationGenerationSerializer(serializers.ModelSerializer):
    """
    Serializer for Documentation Generation
    """
    repository_name = serializers.SerializerMethodField()
    
    class Meta:
        model = DocumentationGeneration
        fields = [
            'id',
            'repository_name',
            'doc_type',
            'status',
            'content',
            'error_message',
            'tokens_used',
            'generation_time',
            'created_at',
            'completed_at',
        ]
    
    def get_repository_name(self, obj):
        return obj.repository.full_name
# ... (keep all existing serializers)

class UserPreferencesSerializer(serializers.ModelSerializer):
    """Serializer for user preferences"""
    
    class Meta:
        model = UserPreferences
        fields = [
            'id',
            'auto_analyze_prs',
            'skip_draft_prs',
            'min_lines_for_analysis',
            'auto_post_comments',
            'auto_update_docs',
            'docs_update_frequency',
            'docs_min_changes',
            'auto_generate_insights',
            'insights_frequency',
            'email_critical_issues',
            'email_daily_digest',
            'slack_notifications',
            'slack_webhook_url',
            'daily_token_limit',
            'pause_on_limit',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class RepositorySettingsSerializer(serializers.ModelSerializer):
    """Serializer for repository settings"""
    
    effective_settings = serializers.SerializerMethodField()
    
    class Meta:
        model = RepositorySettings
        fields = [
            'id',
            'override_global',
            'auto_analyze_prs',
            'skip_draft_prs',
            'min_lines_for_analysis',
            'auto_post_comments',
            'auto_update_docs',
            'docs_update_frequency',
            'docs_min_changes',
            'auto_generate_insights',
            'insights_frequency',
            'enable_pr_analysis',
            'enable_insights',
            'enable_documentation',
            'enable_webhooks',
            'effective_settings',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'effective_settings', 'created_at', 'updated_at']
    
    def get_effective_settings(self, obj):
        return obj.get_effective_settings()


class WebhookConfigurationSerializer(serializers.ModelSerializer):
    """Serializer for webhook configuration"""
    
    health_status = serializers.SerializerMethodField()
    
    class Meta:
        model = WebhookConfiguration
        fields = [
            'id',
            'is_configured',
            'github_webhook_id',
            'webhook_url',
            'events',
            'last_ping',
            'last_delivery',
            'consecutive_failures',
            'is_active',
            'last_error',
            'error_count',
            'health_status',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'health_status', 'created_at', 'updated_at']
    
    def get_health_status(self, obj):
        from .webhook_manager import WebhookManager
        manager = WebhookManager(obj.repository)
        return manager.check_health()


class AutomationLogSerializer(serializers.ModelSerializer):
    """Serializer for automation logs"""
    
    repository_name = serializers.SerializerMethodField()
    
    class Meta:
        model = AutomationLog
        fields = [
            'id',
            'action_type',
            'repository_name',
            'status',
            'trigger',
            'description',
            'pull_request',
            'task_id',
            'result_summary',
            'error_message',
            'started_at',
            'completed_at',
            'duration_seconds',
            'tokens_used',
            'api_calls_made',
            'created_at',
        ]
        read_only_fields = fields
    
    def get_repository_name(self, obj):
        return obj.repository.full_name if obj.repository else None


class CostTrackingSerializer(serializers.ModelSerializer):
    """Serializer for cost tracking"""
    
    class Meta:
        model = CostTracking
        fields = [
            'id',
            'date',
            'pr_analyses_count',
            'insights_generated_count',
            'docs_updated_count',
            'tokens_used',
            'input_tokens',
            'output_tokens',
            'api_calls',
            'estimated_cost',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


# =============================================================================
# PHASE 5 SERIALIZERS
# =============================================================================

class PRDescriptionTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PRDescriptionTemplate
        fields = [
            'id', 'pull_request', 'generated_description', 'summary',
            'features', 'bug_fixes', 'breaking_changes', 'refactors',
            'has_tests', 'requires_migration', 'applied_to_github',
            'tokens_used', 'generation_time', 'model_used',
            'user_approved', 'user_edited', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CodeOwnershipSerializer(serializers.ModelSerializer):
    class Meta:
        model = CodeOwnership
        fields = [
            'id', 'repository', 'file_path', 'primary_owner',
            'contributors', 'commits_count', 'lines_authored',
            'expertise_score', 'last_modified', 'analyzed_at',
        ]
        read_only_fields = fields


class ReviewerRecommendationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewerRecommendation
        fields = [
            'id', 'pull_request', 'github_username', 'reviewer_type',
            'confidence_score', 'recommendation_reason',
            'files_relevant', 'expertise_areas', 'requested_on_github',
            'created_at',
        ]
        read_only_fields = fields


class DeveloperExpertiseSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeveloperExpertise
        fields = [
            'id', 'repository', 'github_username', 'expertise_areas',
            'expertise_map', 'total_commits', 'total_prs_authored',
            'files_touched', 'active_days', 'first_contribution',
            'last_contribution', 'analyzed_at',
        ]
        read_only_fields = fields


# =============================================================================
# PHASE 7 SERIALIZERS: Conflict Detection & Dependency Analysis
# =============================================================================

class ConflictDetectionSerializer(serializers.ModelSerializer):
    """Serializer for conflict detection results."""
    pr_1_number = serializers.SerializerMethodField()
    pr_2_number = serializers.SerializerMethodField()
    pr_1_title = serializers.SerializerMethodField()
    pr_2_title = serializers.SerializerMethodField()
    pr_1_author = serializers.SerializerMethodField()
    pr_2_author = serializers.SerializerMethodField()

    class Meta:
        model = ConflictDetection
        fields = [
            'id', 'pr_1', 'pr_2', 'pr_1_number', 'pr_2_number',
            'pr_1_title', 'pr_2_title', 'pr_1_author', 'pr_2_author',
            'conflict_type', 'severity', 'affected_files', 'conflicting_symbols',
            'resolution_suggestion', 'merge_order',
            'is_resolved', 'resolved_at', 'notified', 'notified_at',
            'detected_at',
        ]
        read_only_fields = ['id', 'detected_at']

    def get_pr_1_number(self, obj):
        return obj.pr_1.number

    def get_pr_2_number(self, obj):
        return obj.pr_2.number

    def get_pr_1_title(self, obj):
        return obj.pr_1.title

    def get_pr_2_title(self, obj):
        return obj.pr_2.title

    def get_pr_1_author(self, obj):
        return obj.pr_1.author_login

    def get_pr_2_author(self, obj):
        return obj.pr_2.author_login


class SymbolMapSerializer(serializers.ModelSerializer):
    """Serializer for symbol map entries."""
    class Meta:
        model = SymbolMap
        fields = [
            'id', 'repository', 'pull_request', 'file_path',
            'symbol_type', 'symbol_name', 'line_start', 'line_end',
            'signature', 'dependencies', 'dependents', 'hash',
            'last_updated',
        ]
        read_only_fields = ['id', 'last_updated']


class DependencyAnalysisSerializer(serializers.ModelSerializer):
    """Serializer for dependency analysis results."""
    repository_name = serializers.SerializerMethodField()
    update_type = serializers.SerializerMethodField()

    class Meta:
        model = DependencyAnalysis
        fields = [
            'id', 'repository', 'repository_name', 'package_name',
            'current_version', 'latest_version', 'latest_safe_version',
            'has_breaking_changes', 'breaking_changes', 'changelog_url',
            'impact_score', 'files_affected', 'code_patterns_affected',
            'estimated_refactor_hours', 'migration_script',
            'update_type', 'analyzed_at',
        ]
        read_only_fields = ['id', 'analyzed_at']

    def get_repository_name(self, obj):
        return obj.repository.full_name

    def get_update_type(self, obj):
        """Determine if update is major/minor/patch."""
        import re
        cur = re.match(r'(\d+)\.?(\d+)?\.?(\d+)?', obj.current_version or '')
        lat = re.match(r'(\d+)\.?(\d+)?\.?(\d+)?', obj.latest_version or '')
        if not cur or not lat:
            return 'unknown'
        c = tuple(int(x) if x else 0 for x in cur.groups())
        l = tuple(int(x) if x else 0 for x in lat.groups())
        if l[0] > c[0]:
            return 'major'
        elif l[1] > c[1]:
            return 'minor'
        elif l[2] > c[2]:
            return 'patch'
        return 'current'


class DependencyUpdateSerializer(serializers.ModelSerializer):
    """Serializer for dependency update tracking."""
    repository_name = serializers.SerializerMethodField()

    class Meta:
        model = DependencyUpdate
        fields = [
            'id', 'repository', 'repository_name', 'package_name',
            'from_version', 'to_version', 'update_type',
            'applied', 'pull_request', 'migration_script_used',
            'created_at', 'applied_at',
        ]
        read_only_fields = ['id', 'created_at']

    def get_repository_name(self, obj):
        return obj.repository.full_name


# =============================================================================
# PHASE 8 SERIALIZERS: Cognitive Debt Tracking
# =============================================================================

class FileComprehensionScoreSerializer(serializers.ModelSerializer):
    """Serializer for per-file cognitive debt scores."""
    repository_name = serializers.SerializerMethodField()

    class Meta:
        model = FileComprehensionScore
        fields = [
            'id', 'repository', 'repository_name', 'file_path',
            'ai_authorship_pct', 'human_edit_count', 'total_commit_count',
            'unique_contributors', 'comprehension_score', 'risk_level',
            'last_human_edit_at', 'suggested_reviewer',
            'last_analyzed_at', 'created_at',
        ]
        read_only_fields = fields

    def get_repository_name(self, obj):
        return obj.repository.full_name