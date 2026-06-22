from django.urls import path, include
from . import views

app_name = 'core'

urlpatterns = [
    # --- Health & System ---
    path('health/', views.health_check, name='health_check'),
    
    # --- GitHub OAuth & Session ---
    path('auth/github/', views.github_login, name='github_login'),
    path('auth/github/callback/', views.github_callback, name='github_callback'),
    path('auth/logout/', views.logout_user, name='logout'),
    path('user/me/', views.current_user, name='current_user'),
    
    # --- Repository Management ---
    path('repositories/', views.list_repositories, name='list_repositories'),
    path('repositories/sync/', views.sync_repositories, name='sync_repositories'),
    path('repositories/<int:repo_id>/', views.repository_detail, name='repository_detail'),
    path('repositories/<int:repo_id>/sync/', views.sync_single_repository, name='sync_single_repository'),
    path('repositories/<int:repo_id>/languages/', views.repository_languages, name='repository_languages'),
    path('repositories/<int:repo_id>/activity/', views.repository_activity, name='repository_activity'),
    
    # --- Pull Requests ---
    path('repositories/<int:repo_id>/pulls/', views.list_pull_requests, name='list_pull_requests'),
    path('repositories/<int:repo_id>/pulls/<int:pr_number>/', views.pull_request_detail, name='pull_request_detail'),
    
    # --- Issues & Commits ---
    path('repositories/<int:repo_id>/issues/', views.list_issues, name='list_issues'),
    path('repositories/<int:repo_id>/issues/<int:issue_number>/', views.issue_detail, name='issue_detail'),
    path('repositories/<int:repo_id>/commits/', views.list_commits, name='list_commits'),
    path('repositories/<int:repo_id>/contributors/', views.list_contributors, name='list_contributors'),
    
    # --- AI Code Analysis (Groq) ---
    path('repositories/<int:repo_id>/pulls/<int:pr_number>/analyze/', views.analyze_pr, name='analyze_pr'),
    path('repositories/<int:repo_id>/pulls/<int:pr_number>/analysis/', views.get_pr_analysis, name='get_pr_analysis'),
    
    # --- AI Documentation (Groq) ---
    path('repositories/<int:repo_id>/documentation/generate/', views.generate_documentation, name='generate_documentation'),
    path('repositories/<int:repo_id>/documentation/', views.get_documentation, name='get_documentation'),
    
    # --- AI Insights Engine (Groq) ---
    path('insights/', views.get_insights, name='get_insights'),
    path('insights/generate/', views.generate_all_insights_view, name='generate_all_insights'),
    path('repositories/<int:repo_id>/insights/', views.get_repository_insights, name='get_repository_insights'),
    path('repositories/<int:repo_id>/insights/generate/', views.generate_insights, name='generate_insights'),
    path('insights/<int:insight_id>/resolve/', views.resolve_insight, name='resolve_insight'),

    # --- AI Chat / Assistant ---
    path('conversations/', views.list_conversations, name='list_conversations'),
    path('conversations/create/', views.create_conversation, name='create_conversation'),
    path('conversations/<int:conversation_id>/', views.conversation_detail, name='conversation_detail'),
    path('conversations/<int:conversation_id>/delete/', views.delete_conversation, name='delete_conversation'),
    
    # --- Webhooks ---
    path('repositories/<int:repo_id>/webhook/', views.setup_webhook, name='setup_webhook'),
    path('repositories/<int:repo_id>/webhook/status/', views.webhook_status, name='webhook_status'),
    path('webhooks/github/', views.github_webhook_receiver, name='github_webhook_receiver'),

    # --- Settings APIs ---
    path('user/preferences/', views.user_preferences, name='user_preferences'),
    path('repositories/<int:repo_id>/settings/', views.repository_settings, name='repository_settings'),

    # --- Webhook APIs ---
    path('repositories/<int:repo_id>/webhook/setup/', views.setup_webhook, name='setup_webhook_alt'),
    path('repositories/<int:repo_id>/webhook/delete/', views.delete_webhook, name='delete_webhook'),

    # --- Automation Log APIs ---
    path('automation/logs/', views.automation_logs, name='automation_logs'),
    path('repositories/<int:repo_id>/automation/logs/', views.repository_automation_logs, name='repository_automation_logs'),

    # --- Cost Tracking APIs ---
    path('cost/summary/', views.cost_summary, name='cost_summary'),
    path('repositories/<int:repo_id>/cost/', views.repository_cost_summary, name='repository_cost_summary'),
    path('repositories/<int:repo_id>/pulls/<int:pr_number>/post-analysis/', 
         views.post_analysis_to_github, 
         name='post_analysis_to_github'),

    # ==========================================================================
    # PHASE 5: PR Description, Reviewer Recommendation, Code Ownership
    # ==========================================================================
    path('repositories/<int:repo_id>/pulls/<int:pr_number>/description/generate/',
         views.generate_pr_description, name='generate_pr_description'),
    path('repositories/<int:repo_id>/pulls/<int:pr_number>/description/',
         views.get_pr_description, name='get_pr_description'),
    path('repositories/<int:repo_id>/pulls/<int:pr_number>/description/apply/',
         views.apply_pr_description, name='apply_pr_description'),

    path('repositories/<int:repo_id>/pulls/<int:pr_number>/reviewers/',
         views.get_reviewer_recommendations, name='get_reviewer_recommendations'),
    path('repositories/<int:repo_id>/pulls/<int:pr_number>/reviewers/recommend/',
         views.recommend_reviewers, name='recommend_reviewers'),
    path('repositories/<int:repo_id>/pulls/<int:pr_number>/reviewers/request/',
         views.request_reviewers_on_github, name='request_reviewers_on_github'),

    path('repositories/<int:repo_id>/ownership/',
         views.get_code_ownership, name='get_code_ownership'),
    path('repositories/<int:repo_id>/ownership/analyze/',
         views.analyze_code_ownership, name='analyze_code_ownership'),

    # ==========================================================================
    # PHASE 7: Conflict Detection & Dependency Analysis
    # ==========================================================================

    # Conflict Detection
    path('repositories/<int:repo_id>/conflicts/analyze/',
         views.analyze_conflicts, name='analyze_conflicts'),
    path('repositories/<int:repo_id>/conflicts/',
         views.list_conflicts, name='list_conflicts'),
    path('repositories/<int:repo_id>/pulls/<int:pr_number>/conflicts/',
         views.pr_conflicts, name='pr_conflicts'),
    path('conflicts/<int:conflict_id>/resolve/',
         views.resolve_conflict, name='resolve_conflict'),
    path('conflicts/<int:conflict_id>/notify/',
         views.notify_conflict, name='notify_conflict'),

    # Dependency Analysis
    path('repositories/<int:repo_id>/dependencies/analyze/',
         views.analyze_dependencies, name='analyze_dependencies'),
    path('repositories/<int:repo_id>/dependencies/',
         views.list_dependencies, name='list_dependencies'),
    path('repositories/<int:repo_id>/dependencies/impact-report/',
         views.dependency_impact_report, name='dependency_impact_report'),
    path('repositories/<int:repo_id>/dependencies/<str:package_name>/',
         views.dependency_detail, name='dependency_detail'),

    # ==========================================================================
    # PHASE 8: Cognitive Debt Tracking
    # ==========================================================================
    path('repositories/<int:repo_id>/debt/',
         views.repository_cognitive_debt, name='repository_cognitive_debt'),
    path('repositories/<int:repo_id>/debt/summary/',
         views.cognitive_debt_summary, name='cognitive_debt_summary'),
    path('repositories/<int:repo_id>/debt/analyse/',
         views.trigger_debt_analysis, name='trigger_debt_analysis'),

    # ==========================================================================
    # PHASE 9: Intent Debt Detection
    # ==========================================================================
    path('repositories/<int:repo_id>/pulls/<int:pr_number>/intent-flags/',
         views.get_intent_flags, name='get_intent_flags'),
    path('intent-flags/<int:flag_id>/capture/',
         views.capture_intent, name='capture_intent'),
    path('intent-flags/<int:flag_id>/dismiss/',
         views.dismiss_intent, name='dismiss_intent'),
    path('repositories/<int:repo_id>/file-intent/',
         views.get_file_intent, name='get_file_intent'),
    path('repositories/<int:repo_id>/intent-summary/',
         views.get_intent_summary, name='get_intent_summary'),
    path('repositories/<int:repo_id>/intent-scan/',
         views.trigger_intent_scan, name='trigger_intent_scan'),
    path('intent-flags/pending/',
         views.get_user_pending_intents, name='get_user_pending_intents'),
]