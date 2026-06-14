from django.contrib import admin
from .models import (
    User, Repository, PullRequest, Issue, Commit, 
    Contributor, RepositoryWebhook, WebhookEvent, GitHubOAuthState,
    Conversation, ChatMessage
)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'github_login', 'email', 'created_at')
    search_fields = ('username', 'github_login', 'email')
    readonly_fields = ('github_id', 'created_at', 'updated_at')


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'user', 'language', 'stars_count', 'is_active', 'last_synced_at')
    search_fields = ('full_name', 'name')
    list_filter = ('is_private', 'is_fork', 'is_active', 'language')
    readonly_fields = ('github_id', 'created_at', 'updated_at')


@admin.register(PullRequest)
class PullRequestAdmin(admin.ModelAdmin):
    list_display = ('number', 'title', 'repository', 'state', 'author_login', 'created_at')
    search_fields = ('title', 'author_login')
    list_filter = ('state', 'merged')
    readonly_fields = ('github_id', 'synced_at')


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ('number', 'title', 'repository', 'state', 'author_login', 'created_at')
    search_fields = ('title', 'author_login')
    list_filter = ('state',)
    readonly_fields = ('github_id', 'synced_at')


@admin.register(Commit)
class CommitAdmin(admin.ModelAdmin):
    list_display = ('sha_short', 'message_short', 'repository', 'author_login', 'committed_at')
    search_fields = ('sha', 'message', 'author_login')
    readonly_fields = ('sha', 'synced_at')
    
    def sha_short(self, obj):
        return obj.sha[:7]
    sha_short.short_description = 'SHA'
    
    def message_short(self, obj):
        return obj.message[:50]
    message_short.short_description = 'Message'


@admin.register(Contributor)
class ContributorAdmin(admin.ModelAdmin):
    list_display = ('github_login', 'repository', 'contributions', 'synced_at')
    search_fields = ('github_login',)
    readonly_fields = ('synced_at',)


@admin.register(RepositoryWebhook)
class RepositoryWebhookAdmin(admin.ModelAdmin):
    list_display = ('repository', 'is_active', 'total_deliveries', 'failed_deliveries', 'last_delivery_at')
    list_filter = ('is_active',)
    readonly_fields = ('github_webhook_id', 'created_at', 'updated_at')


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'repository', 'delivery_id', 'processed', 'created_at')
    list_filter = ('event_type', 'processed')
    search_fields = ('delivery_id',)
    readonly_fields = ('created_at',)


@admin.register(GitHubOAuthState)
class GitHubOAuthStateAdmin(admin.ModelAdmin):
    list_display = ('state', 'created_at', 'is_used')
    readonly_fields = ('state', 'created_at')


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'title', 'message_count', 'created_at')
    search_fields = ('title', 'user__github_login')
    readonly_fields = ('created_at', 'updated_at')
    
    def message_count(self, obj):
        return obj.messages.count()
    message_count.short_description = 'Messages'


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'role', 'content_preview', 'tokens_used', 'created_at')
    list_filter = ('role',)
    search_fields = ('content',)
    readonly_fields = ('created_at',)
    
    def content_preview(self, obj):
        return obj.content[:100]
    content_preview.short_description = 'Content'
# ... (keep existing registrations)

from .models import UserPreferences, RepositorySettings, WebhookConfiguration, AutomationLog, CostTracking

@admin.register(UserPreferences)
class UserPreferencesAdmin(admin.ModelAdmin):
    list_display = ('user', 'auto_analyze_prs', 'auto_update_docs', 'auto_generate_insights', 'updated_at')
    search_fields = ('user__github_login',)
    list_filter = ('auto_analyze_prs', 'auto_update_docs', 'auto_generate_insights')


@admin.register(RepositorySettings)
class RepositorySettingsAdmin(admin.ModelAdmin):
    list_display = ('repository', 'override_global', 'enable_pr_analysis', 'enable_insights', 'enable_documentation')
    search_fields = ('repository__full_name',)
    list_filter = ('override_global', 'enable_pr_analysis', 'enable_insights')


@admin.register(WebhookConfiguration)
class WebhookConfigurationAdmin(admin.ModelAdmin):
    list_display = ('repository', 'is_configured', 'is_active', 'consecutive_failures', 'last_delivery')
    search_fields = ('repository__full_name',)
    list_filter = ('is_configured', 'is_active')
    readonly_fields = ('github_webhook_id', 'created_at', 'updated_at')


@admin.register(AutomationLog)
class AutomationLogAdmin(admin.ModelAdmin):
    list_display = ('action_type', 'repository', 'status', 'trigger', 'duration_seconds', 'created_at')
    search_fields = ('repository__full_name', 'description')
    list_filter = ('action_type', 'status', 'trigger')
    readonly_fields = ('created_at',)


@admin.register(CostTracking)
class CostTrackingAdmin(admin.ModelAdmin):
    list_display = ('user', 'repository', 'date', 'tokens_used', 'estimated_cost', 'api_calls')
    search_fields = ('user__github_login', 'repository__full_name')
    list_filter = ('date',)
    readonly_fields = ('created_at', 'updated_at')


# =============================================================================
# PHASE 5 MODELS
# =============================================================================
from .models import PRDescriptionTemplate, CodeOwnership, ReviewerRecommendation, DeveloperExpertise


@admin.register(PRDescriptionTemplate)
class PRDescriptionTemplateAdmin(admin.ModelAdmin):
    list_display = ('pull_request', 'model_used', 'tokens_used', 'applied_to_github', 'created_at')
    list_filter = ('applied_to_github', 'has_tests', 'requires_migration')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(CodeOwnership)
class CodeOwnershipAdmin(admin.ModelAdmin):
    list_display = ('repository', 'file_path', 'primary_owner', 'commits_count', 'expertise_score')
    search_fields = ('file_path', 'primary_owner')
    list_filter = ('repository',)


@admin.register(ReviewerRecommendation)
class ReviewerRecommendationAdmin(admin.ModelAdmin):
    list_display = ('pull_request', 'github_username', 'reviewer_type', 'confidence_score', 'requested_on_github')
    list_filter = ('reviewer_type', 'requested_on_github')
    search_fields = ('github_username',)


@admin.register(DeveloperExpertise)
class DeveloperExpertiseAdmin(admin.ModelAdmin):
    list_display = ('repository', 'github_username', 'total_commits', 'active_days')
    search_fields = ('github_username',)
    list_filter = ('repository',)