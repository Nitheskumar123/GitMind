import requests
import secrets
import json
from django.conf import settings
from django.shortcuts import redirect
from django.contrib.auth import login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.db import models

from .models import (
    User, Repository, PullRequest, Issue, Commit, 
    Contributor, RepositoryWebhook, GitHubOAuthState
)
from .serializers import (
    UserSerializer, RepositorySerializer, PullRequestSerializer,
    IssueSerializer, CommitSerializer, ContributorSerializer,
    RepositoryWebhookSerializer
)
from .github_api import GitHubAPIClient
from .webhooks import verify_webhook_signature, process_webhook_event
from .tasks import sync_repository_data


# ============================================================================
# GITHUB OAUTH VIEWS
# ============================================================================

@require_http_methods(["GET"])
def github_login(request):
    """
    Initiate GitHub OAuth flow
    Redirects user to GitHub authorization page
    """
    state = secrets.token_urlsafe(32)
    GitHubOAuthState.objects.create(state=state)
    GitHubOAuthState.cleanup_old_states()
    
    github_auth_url = (
        f"https://github.com/login/oauth/authorize?"
        f"client_id={settings.GITHUB_CLIENT_ID}&"
        f"redirect_uri={settings.GITHUB_REDIRECT_URI}&"
        f"scope=repo,user,read:org&"
        f"state={state}"
    )
    
    return redirect(github_auth_url)


@require_http_methods(["GET"])
def github_callback(request):
    """
    GitHub OAuth callback handler
    """
    code = request.GET.get('code')
    state = request.GET.get('state')
    
    try:
        oauth_state = GitHubOAuthState.objects.get(state=state, is_used=False)
        oauth_state.is_used = True
        oauth_state.save()
    except GitHubOAuthState.DoesNotExist:
        return JsonResponse({'error': 'Invalid state parameter'}, status=400)
    
    if not code:
        return JsonResponse({'error': 'No authorization code provided'}, status=400)
    
    # Exchange code for access token
    token_url = 'https://github.com/login/oauth/access_token'
    token_data = {
        'client_id': settings.GITHUB_CLIENT_ID,
        'client_secret': settings.GITHUB_CLIENT_SECRET,
        'code': code,
        'redirect_uri': settings.GITHUB_REDIRECT_URI,
    }
    token_headers = {'Accept': 'application/json'}
    
    try:
        token_response = requests.post(token_url, data=token_data, headers=token_headers)
        token_response.raise_for_status()
        token_json = token_response.json()
        access_token = token_json.get('access_token')
        
        if not access_token:
            return JsonResponse({'error': 'Failed to obtain access token'}, status=400)
        
    except requests.RequestException as e:
        return JsonResponse({'error': f'GitHub API error: {str(e)}'}, status=500)
    
    # Fetch user information
    user_url = 'https://api.github.com/user'
    user_headers = {'Authorization': f'token {access_token}', 'Accept': 'application/json'}
    
    try:
        user_response = requests.get(user_url, headers=user_headers)
        user_response.raise_for_status()
        github_user = user_response.json()
    except requests.RequestException as e:
        return JsonResponse({'error': f'Failed to fetch user data: {str(e)}'}, status=500)
    
    # Create or update user
    github_id = str(github_user.get('id'))
    github_login = github_user.get('login')
    
    user, created = User.objects.update_or_create(
        github_id=github_id,
        defaults={
            'github_login': github_login,
            'username': github_login,
            'github_access_token': access_token,
            'github_avatar_url': github_user.get('avatar_url'),
            'github_profile_url': github_user.get('html_url'),
            'github_bio': github_user.get('bio'),
            'github_company': github_user.get('company'),
            'github_location': github_user.get('location'),
            'email': github_user.get('email') or f'{github_login}@github.user',
            'first_name': github_user.get('name', '').split()[0] if github_user.get('name') else '',
            'last_name': ' '.join(github_user.get('name', '').split()[1:]) if github_user.get('name') else '',
        }
    )
    
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    return redirect('/dashboard/')


# ============================================================================
# USER API VIEWS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user(request):
    """Get current authenticated user information"""
    serializer = UserSerializer(request.user)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_user(request):
    """Logout current user"""
    logout(request)
    return Response({'message': 'Successfully logged out'}, status=status.HTTP_200_OK)


# ============================================================================
# REPOSITORY API VIEWS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_repositories(request):
    """List all repositories for current user"""
    repositories = Repository.objects.filter(user=request.user)
    serializer = RepositorySerializer(repositories, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def repository_detail(request, repo_id):
    """Get detailed repository information"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        serializer = RepositorySerializer(repository)
        return Response(serializer.data)
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_repositories(request):
    """Fetch and sync user's GitHub repositories"""
    user = request.user
    access_token = user.github_access_token
    
    if not access_token:
        return Response({'error': 'No GitHub access token found'}, status=400)
    
    client = GitHubAPIClient(access_token)
    github_repos = client.get_repositories()
    
    synced_count = 0
    for repo_data in github_repos:
        repository, created = Repository.objects.update_or_create(
            github_id=str(repo_data['id']),
            defaults={
                'user': user,
                'name': repo_data['name'],
                'full_name': repo_data['full_name'],
                'description': repo_data.get('description', ''),
                'html_url': repo_data['html_url'],
                'is_private': repo_data['private'],
                'is_fork': repo_data['fork'],
                'language': repo_data.get('language'),
                'stars_count': repo_data.get('stargazers_count', 0),
                'forks_count': repo_data.get('forks_count', 0),
                'open_issues_count': repo_data.get('open_issues_count', 0),
                'watchers_count': repo_data.get('watchers_count', 0),
                'default_branch': repo_data.get('default_branch', 'main'),
                'size': repo_data.get('size', 0),
                'has_issues': repo_data.get('has_issues', True),
                'has_projects': repo_data.get('has_projects', True),
                'has_wiki': repo_data.get('has_wiki', True),
                'github_created_at': repo_data.get('created_at'),
                'github_updated_at': repo_data.get('updated_at'),
                'github_pushed_at': repo_data.get('pushed_at'),
            }
        )
        synced_count += 1
    
    return Response({
        'message': f'Successfully synced {synced_count} repositories',
        'count': synced_count
    }, status=200)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sync_single_repository(request, repo_id):
    """Sync single repository data (PRs, issues, commits, etc.)"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        
        # Queue background task
        sync_repository_data.delay(repository.id)
        
        return Response({
            'message': f'Sync started for {repository.full_name}',
            'repository_id': repository.id
        }, status=202)
        
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


# ============================================================================
# PULL REQUEST API VIEWS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_pull_requests(request, repo_id):
    """List pull requests for repository"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        state = request.query_params.get('state', 'all')  # all, open, closed
        
        pull_requests = repository.pull_requests.all()
        if state != 'all':
            pull_requests = pull_requests.filter(state=state)
        
        serializer = PullRequestSerializer(pull_requests, many=True)
        return Response(serializer.data)
        
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def pull_request_detail(request, repo_id, pr_number):
    """Get pull request details"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        pull_request = repository.pull_requests.get(number=pr_number)
        serializer = PullRequestSerializer(pull_request)
        return Response(serializer.data)
    except (Repository.DoesNotExist, PullRequest.DoesNotExist):
        return Response({'error': 'Pull request not found'}, status=404)


# ============================================================================
# ISSUE API VIEWS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_issues(request, repo_id):
    """List issues for repository"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        state = request.query_params.get('state', 'all')  # all, open, closed
        
        issues = repository.issues.all()
        if state != 'all':
            issues = issues.filter(state=state)
        
        serializer = IssueSerializer(issues, many=True)
        return Response(serializer.data)
        
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def issue_detail(request, repo_id, issue_number):
    """Get issue details"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        issue = repository.issues.get(number=issue_number)
        serializer = IssueSerializer(issue)
        return Response(serializer.data)
    except (Repository.DoesNotExist, Issue.DoesNotExist):
        return Response({'error': 'Issue not found'}, status=404)


# ============================================================================
# COMMIT API VIEWS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_commits(request, repo_id):
    """List recent commits for repository"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        limit = int(request.query_params.get('limit', 30))
        
        commits = repository.commits.all()[:limit]
        serializer = CommitSerializer(commits, many=True)
        return Response(serializer.data)
        
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


# ============================================================================
# CONTRIBUTOR API VIEWS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_contributors(request, repo_id):
    """List contributors for repository"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        contributors = repository.contributors.all()
        serializer = ContributorSerializer(contributors, many=True)
        return Response(serializer.data)
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


# ============================================================================
# LANGUAGE STATS API VIEWS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def repository_languages(request, repo_id):
    """Get language statistics for repository"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        user = request.user
        
        client = GitHubAPIClient(user.github_access_token)
        languages = client.get_languages(repository.full_name)
        
        return Response(languages)
        
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


# ============================================================================
# ACTIVITY FEED API VIEWS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def repository_activity(request, repo_id):
    """Get combined activity feed for repository"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        
        # Get recent webhook events
        webhook_events = repository.webhook_events.all()[:20]
        
        activity_feed = []
        for event in webhook_events:
            activity_feed.append({
                'type': event.event_type,
                'timestamp': event.created_at,
                'processed': event.processed,
                'data': event.payload
            })
        
        return Response(activity_feed)
        
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


# ============================================================================
# WEBHOOK API VIEWS
# ============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def setup_webhook(request, repo_id):
    """Setup webhook for repository"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        user = request.user
        
        # Generate webhook secret
        webhook_secret = secrets.token_urlsafe(32)
        
        # Webhook URL (you'll need to replace with your actual domain in production)
        webhook_url = f"{settings.FRONTEND_URL}/api/webhooks/github/"
        
        # Create webhook on GitHub
        client = GitHubAPIClient(user.github_access_token)
        webhook_data = client.create_webhook(
            repository.full_name,
            webhook_url,
            webhook_secret,
            events=['push', 'pull_request', 'issues']
        )
        
        if not webhook_data:
            return Response({'error': 'Failed to create webhook'}, status=500)
        
        # Store webhook info in database
        webhook, created = RepositoryWebhook.objects.update_or_create(
            repository=repository,
            defaults={
                'github_webhook_id': str(webhook_data['id']),
                'webhook_url': webhook_url,
                'secret': webhook_secret,
                'events': webhook_data['events'],
                'is_active': webhook_data['active'],
            }
        )
        
        serializer = RepositoryWebhookSerializer(webhook)
        return Response(serializer.data, status=201)
        
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def webhook_status(request, repo_id):
    """Get webhook status for repository"""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        
        if not hasattr(repository, 'webhook'):
            return Response({'has_webhook': False})
        
        webhook = repository.webhook
        serializer = RepositoryWebhookSerializer(webhook)
        return Response({
            'has_webhook': True,
            'webhook': serializer.data
        })
        
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)

@csrf_exempt
@require_http_methods(["POST"])
def github_webhook_receiver(request):
    """
    Receive and process GitHub webhook events
    """
    event_type = request.headers.get('X-GitHub-Event')
    delivery_id = request.headers.get('X-GitHub-Delivery')
    signature = request.headers.get('X-Hub-Signature-256')

    # 1. HANDLE PING IMMEDIATELY
    # GitHub sends this to verify the URL is working. 
    # We must return 200 OK without checking the database.
    if event_type == 'ping':
        return JsonResponse({'status': 'pong'}, status=200)
    
    if not all([event_type, delivery_id, signature]):
        return JsonResponse({'error': 'Missing required headers'}, status=400)
    
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON payload'}, status=400)
    
    repository_data = payload.get('repository', {})
    repository_full_name = repository_data.get('full_name')
    
    if not repository_full_name:
        return JsonResponse({'error': 'Repository info missing'}, status=400)
    
    try:
        repository = Repository.objects.get(full_name=repository_full_name)
        
        # 2. FIX ATTRIBUTE CHECK
        # Based on your imports/models, check the correct related name.
        # If your model is 'RepositoryWebhook', the related name is usually 'webhook' 
        # or 'repositorywebhook'.
        if not hasattr(repository, 'webhook') and not hasattr(repository, 'repositorywebhook'):
             # If we are in dev, we might use the global secret from .env directly
             webhook_secret = settings.GITHUB_WEBHOOK_SECRET
        else:
             # Use the secret from .env as the primary source of truth for local dev
             webhook_secret = settings.GITHUB_WEBHOOK_SECRET
        
    except Repository.DoesNotExist:
        return JsonResponse({'error': 'Repository not found in local DB'}, status=404)
    
    # 3. VERIFY SIGNATURE
    if not verify_webhook_signature(request.body, signature, webhook_secret):
        logger.warning(f"Signature mismatch for repo: {repository_full_name}")
        return JsonResponse({'error': 'Invalid signature'}, status=401)
    
    # 4. PROCESS EVENT
    process_webhook_event(event_type, delivery_id, payload, repository_full_name)
    
    return JsonResponse({'status': 'success'}, status=200)

# ============================================================================
# HEALTH CHECK
# ============================================================================

@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """Health check endpoint"""
    return Response({
        'status': 'healthy',
        'message': 'GitMind API is running'
    }, status=200)


# ============================================================================
# CHAT API VIEWS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_conversations(request):
    """List all conversations for current user"""
    from .models import Conversation
    from .serializers import ConversationSerializer
    
    conversations = Conversation.objects.filter(user=request.user)
    serializer = ConversationSerializer(conversations, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def conversation_detail(request, conversation_id):
    """Get conversation details with messages"""
    from .models import Conversation
    from .serializers import ConversationSerializer, ChatMessageSerializer
    
    try:
        conversation = Conversation.objects.get(id=conversation_id, user=request.user)
        conversation_data = ConversationSerializer(conversation).data
        messages = conversation.messages.all()
        messages_data = ChatMessageSerializer(messages, many=True).data
        
        return Response({
            'conversation': conversation_data,
            'messages': messages_data
        })
    except Conversation.DoesNotExist:
        return Response({'error': 'Conversation not found'}, status=404)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_conversation(request):
    """Create new conversation"""
    from .models import Conversation
    from .serializers import ConversationSerializer
    
    conversation = Conversation.objects.create(
        user=request.user,
        title=request.data.get('title', 'New Conversation')
    )
    serializer = ConversationSerializer(conversation)
    return Response(serializer.data, status=201)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_conversation(request, conversation_id):
    """Delete conversation"""
    from .models import Conversation
    
    try:
        conversation = Conversation.objects.get(id=conversation_id, user=request.user)
        conversation.delete()
        return Response({'message': 'Conversation deleted'}, status=200)
    except Conversation.DoesNotExist:
        return Response({'error': 'Conversation not found'}, status=404)
# ... (keep all existing views)

# ============================================================================
# CODE ANALYSIS API VIEWS
# ============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def analyze_pr(request, repo_id, pr_number):
    """Trigger PR analysis"""
    from .models import Repository, PullRequest
    from .tasks import analyze_pull_request
    
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        pr = PullRequest.objects.get(repository=repository, number=pr_number)
        
        # Queue analysis
        analyze_pull_request.delay(pr.id)
        
        return Response({
            'message': f'Analysis started for PR #{pr_number}',
            'pr_id': pr.id
        }, status=202)
        
    except (Repository.DoesNotExist, PullRequest.DoesNotExist):
        return Response({'error': 'PR not found'}, status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_pr_analysis(request, repo_id, pr_number):
    """Get PR analysis results"""
    from .models import Repository, PullRequest, PRAnalysis
    from .serializers import PRAnalysisSerializer
    
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        pr = PullRequest.objects.get(repository=repository, number=pr_number)
        
        if hasattr(pr, 'analysis'):
            serializer = PRAnalysisSerializer(pr.analysis)
            return Response(serializer.data)
        else:
            return Response({'message': 'No analysis available yet'}, status=404)
        
    except (Repository.DoesNotExist, PullRequest.DoesNotExist):
        return Response({'error': 'PR not found'}, status=404)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_documentation(request, repo_id):
    """Generate repository documentation"""
    from .models import Repository
    from .tasks import generate_repository_documentation
    
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        doc_type = request.data.get('doc_type', 'readme')
        
        # Queue documentation generation
        generate_repository_documentation.delay(repository.id, doc_type)
        
        return Response({
            'message': f'Generating {doc_type} documentation',
            'repository': repository.full_name
        }, status=202)
        
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_documentation(request, repo_id):
    """Get generated documentation"""
    from .models import Repository, DocumentationGeneration
    from .serializers import DocumentationGenerationSerializer
    
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        
        # Get latest documentation
        docs = DocumentationGeneration.objects.filter(
            repository=repository,
            status='completed'
        ).order_by('-created_at')
        
        serializer = DocumentationGenerationSerializer(docs, many=True)
        return Response(serializer.data)
        
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_insights(request):
    """Get AI insights for user"""
    from .models import CodeInsight
    from .serializers import CodeInsightSerializer
    
    # Get insights for user's repositories
    insights = CodeInsight.objects.filter(
        repository__user=request.user,
        is_resolved=False
    ).order_by('-priority', '-created_at')[:20]
    
    serializer = CodeInsightSerializer(insights, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_repository_insights(request, repo_id):
    """Get insights for specific repository"""
    from .models import Repository, CodeInsight
    from .serializers import CodeInsightSerializer
    
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        
        insights = CodeInsight.objects.filter(
            repository=repository,
            is_resolved=False
        ).order_by('-priority', '-created_at')
        
        serializer = CodeInsightSerializer(insights, many=True)
        return Response(serializer.data)
        
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_insights(request, repo_id):
    """Trigger insight generation for repository"""
    from .models import Repository
    from .tasks import generate_insights_for_repository
    
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        
        # Queue insight generation
        generate_insights_for_repository.delay(repository.id)
        
        return Response({
            'message': 'Generating insights',
            'repository': repository.full_name
        }, status=202)
        
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def resolve_insight(request, insight_id):
    """Mark insight as resolved"""
    from .models import CodeInsight
    
    try:
        insight = CodeInsight.objects.get(
            id=insight_id,
            repository__user=request.user
        )
        
        insight.is_resolved = True
        insight.resolved_at = timezone.now()
        insight.save()
        
        return Response({'message': 'Insight resolved'}, status=200)
        
    except CodeInsight.DoesNotExist:
        return Response({'error': 'Insight not found'}, status=404)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_all_insights_view(request):
    """
    POST /api/insights/generate/
    Triggers Groq to analyze all active repositories for the current user.
    """
    from .insights_engine import InsightsEngine
    try:
        # Initialize the Groq-powered engine
        engine = InsightsEngine()
        
        # This calls the logic that iterates through all user repos
        total_count = engine.generate_all_user_insights(request.user)
        
        return Response({
            "success": True,
            "message": f"Successfully generated {total_count} insights across your repositories.",
            "count": total_count
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({
            "success": False, 
            "error": str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
# ... (keep all existing views)

from .models import UserPreferences, RepositorySettings, WebhookConfiguration, AutomationLog, CostTracking
from .serializers import (
    UserPreferencesSerializer, RepositorySettingsSerializer,
    WebhookConfigurationSerializer, AutomationLogSerializer, CostTrackingSerializer
)
from .webhook_manager import WebhookManager

# ============================================================================
# SETTINGS API VIEWS
# ============================================================================

@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def user_preferences(request):
    """Get or update user preferences"""
    
    # Get or create preferences
    prefs, created = UserPreferences.objects.get_or_create(user=request.user)
    
    if request.method == 'GET':
        serializer = UserPreferencesSerializer(prefs)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        serializer = UserPreferencesSerializer(prefs, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def repository_settings(request, repo_id):
    """Get or update repository settings"""
    
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)
    
    # Get or create settings
    settings, created = RepositorySettings.objects.get_or_create(repository=repository)
    
    if request.method == 'GET':
        serializer = RepositorySettingsSerializer(settings)
        return Response(serializer.data)
    
    elif request.method == 'PUT':
        serializer = RepositorySettingsSerializer(settings, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)


# ============================================================================
# WEBHOOK API VIEWS
# ============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def setup_webhook(request, repo_id):
    """Setup webhook for repository"""
    
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)
    
    from .tasks import setup_repository_webhook
    
    # Queue webhook setup
    task = setup_repository_webhook.delay(repository.id)
    
    return Response({
        'message': 'Webhook setup initiated',
        'task_id': task.id
    }, status=202)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def webhook_status(request, repo_id):
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        # Use filter().first() to avoid DoesNotExist crashes
        webhook_config = WebhookConfiguration.objects.filter(repository=repository).first()
        
        if not webhook_config or not webhook_config.is_configured:
            return Response({
                'is_configured': False,
                'is_active': False,
                'message': 'Webhook not configured'
            }, status=200)

        return Response({
            'is_configured': True,
            'is_active': webhook_config.is_active,
            'github_webhook_id': webhook_config.github_webhook_id,
            'last_delivery': webhook_config.last_delivery
        })
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_webhook(request, repo_id):
    """Delete webhook for repository"""
    
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        manager = WebhookManager(repository)
        result = manager.delete_webhook()
        
        if result['success']:
            return Response(result, status=200)
        else:
            return Response(result, status=400)
        
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


# ============================================================================
# AUTOMATION LOG API VIEWS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def automation_logs(request):
    """Get automation logs for user"""
    
    logs = AutomationLog.objects.filter(user=request.user)[:50]  # Last 50 logs
    serializer = AutomationLogSerializer(logs, many=True)
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def repository_automation_logs(request, repo_id):
    """Get automation logs for repository"""
    
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        logs = AutomationLog.objects.filter(repository=repository)[:50]
        serializer = AutomationLogSerializer(logs, many=True)
        return Response(serializer.data)
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


# ============================================================================
# COST TRACKING API VIEWS
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def cost_summary(request):
    """Get cost summary for user"""
    
    from django.db.models import Sum
    from datetime import date, timedelta
    
    today = date.today()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    # Today's usage
    today_usage = CostTracking.objects.filter(
        user=request.user,
        date=today
    ).aggregate(
        tokens=Sum('tokens_used'),
        cost=Sum('estimated_cost')
    )
    
    # This week
    week_usage = CostTracking.objects.filter(
        user=request.user,
        date__gte=week_ago
    ).aggregate(
        tokens=Sum('tokens_used'),
        cost=Sum('estimated_cost')
    )
    
    # This month
    month_usage = CostTracking.objects.filter(
        user=request.user,
        date__gte=month_ago
    ).aggregate(
        tokens=Sum('tokens_used'),
        cost=Sum('estimated_cost')
    )
    
    # Get daily breakdown
    daily_breakdown = CostTracking.objects.filter(
        user=request.user,
        date__gte=week_ago
    ).order_by('-date')
    
    return Response({
        'today': {
            'tokens': today_usage['tokens'] or 0,
            'cost': float(today_usage['cost'] or 0)
        },
        'this_week': {
            'tokens': week_usage['tokens'] or 0,
            'cost': float(week_usage['cost'] or 0)
        },
        'this_month': {
            'tokens': month_usage['tokens'] or 0,
            'cost': float(month_usage['cost'] or 0)
        },
        'daily_breakdown': CostTrackingSerializer(daily_breakdown, many=True).data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def repository_cost_summary(request, repo_id):
    """Get cost summary for repository"""
    
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        
        from django.db.models import Sum
        from datetime import date, timedelta
        
        today = date.today()
        month_ago = today - timedelta(days=30)
        
        # This month for this repo
        month_usage = CostTracking.objects.filter(
            repository=repository,
            date__gte=month_ago
        ).aggregate(
            tokens=Sum('tokens_used'),
            cost=Sum('estimated_cost'),
            pr_analyses=Sum('pr_analyses_count'),
            insights=Sum('insights_generated_count'),
            docs=Sum('docs_updated_count')
        )
        
        return Response({
            'repository': repository.full_name,
            'period': 'last_30_days',
            'tokens_used': month_usage['tokens'] or 0,
            'estimated_cost': float(month_usage['cost'] or 0),
            'pr_analyses': month_usage['pr_analyses'] or 0,
            'insights_generated': month_usage['insights'] or 0,
            'docs_updated': month_usage['docs'] or 0
        })
        
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)
import logging

logger = logging.getLogger(__name__)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def post_analysis_to_github(request, repo_id, pr_number):
    """Manually post saved analysis to GitHub"""
    from .models import Repository, PullRequest
    from .code_review import CodeReviewer

    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        pr = PullRequest.objects.get(repository=repository, number=pr_number)

        if not hasattr(pr, 'analysis'):
            return Response({'error': 'No analysis found. Run analysis first.'}, status=404)

        if pr.analysis.comment_posted:
            return Response({'error': 'Comment already posted to GitHub'}, status=400)

        reviewer = CodeReviewer(pr)
        success = reviewer.post_comment_to_github(pr.analysis)

        if success:
            return Response({'message': f'Comment posted to GitHub for PR #{pr_number}'}, status=200)
        else:
            return Response({'error': 'Failed to post comment to GitHub'}, status=500)

    except (Repository.DoesNotExist, PullRequest.DoesNotExist):
        return Response({'error': 'PR not found'}, status=404)
    except Exception as e:
        logger.error(f"Error posting analysis: {e}")
        return Response({'error': str(e)}, status=500)


# =============================================================================
# PHASE 5: PR Description Generator Views
# =============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_pr_description(request, repo_id, pr_number):
    """Trigger AI description generation for a PR."""
    try:
        repo = Repository.objects.get(id=repo_id, user=request.user)
        pr = PullRequest.objects.get(repository=repo, number=pr_number)
        from .tasks import generate_pr_description_task
        generate_pr_description_task.delay(pr.id)
        return Response({'message': 'Description generation started', 'pr_id': pr.id})
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)
    except PullRequest.DoesNotExist:
        return Response({'error': f'PR #{pr_number} not found'}, status=404)
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_pr_description(request, repo_id, pr_number):
    """Get the generated description for a PR."""
    try:
        from .models import PRDescriptionTemplate
        from .serializers import PRDescriptionTemplateSerializer
        repo = Repository.objects.get(id=repo_id, user=request.user)
        pr = PullRequest.objects.get(repository=repo, number=pr_number)
        template = PRDescriptionTemplate.objects.get(pull_request=pr)
        serializer = PRDescriptionTemplateSerializer(template)
        return Response(serializer.data)
    except (Repository.DoesNotExist, PullRequest.DoesNotExist):
        return Response({'error': 'PR not found'}, status=404)
    except PRDescriptionTemplate.DoesNotExist:
        return Response({'error': 'No description generated yet'}, status=404)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def apply_pr_description(request, repo_id, pr_number):
    """Apply generated description to GitHub PR."""
    try:
        repo = Repository.objects.get(id=repo_id, user=request.user)
        pr = PullRequest.objects.get(repository=repo, number=pr_number)
        from .pr_description_gen import PRDescriptionGenerator
        gen = PRDescriptionGenerator()
        result = gen.apply_to_github(pr)
        return Response(result, status=200 if result['success'] else 500)
    except (Repository.DoesNotExist, PullRequest.DoesNotExist):
        return Response({'error': 'PR not found'}, status=404)


# =============================================================================
# PHASE 5: Reviewer Recommendation Views
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_reviewer_recommendations(request, repo_id, pr_number):
    """Get reviewer recommendations for a PR."""
    try:
        from .models import ReviewerRecommendation
        from .serializers import ReviewerRecommendationSerializer
        repo = Repository.objects.get(id=repo_id, user=request.user)
        pr = PullRequest.objects.get(repository=repo, number=pr_number)
        recs = ReviewerRecommendation.objects.filter(pull_request=pr).order_by('-confidence_score')
        serializer = ReviewerRecommendationSerializer(recs, many=True)
        return Response(serializer.data)
    except (Repository.DoesNotExist, PullRequest.DoesNotExist):
        return Response({'error': 'PR not found'}, status=404)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def recommend_reviewers(request, repo_id, pr_number):
    """Trigger reviewer recommendation for a PR."""
    try:
        repo = Repository.objects.get(id=repo_id, user=request.user)
        pr = PullRequest.objects.get(repository=repo, number=pr_number)
        from .tasks import recommend_reviewers_task
        recommend_reviewers_task.delay(pr.id)
        return Response({'message': 'Reviewer recommendation started', 'pr_id': pr.id})
    except (Repository.DoesNotExist, PullRequest.DoesNotExist):
        return Response({'error': 'PR not found'}, status=404)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def request_reviewers_on_github(request, repo_id, pr_number):
    """Send review requests to GitHub."""
    try:
        repo = Repository.objects.get(id=repo_id, user=request.user)
        pr = PullRequest.objects.get(repository=repo, number=pr_number)
        usernames = request.data.get('reviewers', [])
        if not usernames:
            return Response({'error': 'No reviewers specified'}, status=400)
        from .reviewer_engine import ReviewerRecommendationEngine
        engine = ReviewerRecommendationEngine()
        result = engine.request_reviewers_on_github(pr, usernames)
        return Response(result, status=200 if result['success'] else 500)
    except (Repository.DoesNotExist, PullRequest.DoesNotExist):
        return Response({'error': 'PR not found'}, status=404)


# =============================================================================
# PHASE 5: Code Ownership Views
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_code_ownership(request, repo_id):
    """Get code ownership and developer expertise for a repo."""
    try:
        from .models import CodeOwnership, DeveloperExpertise
        from .serializers import CodeOwnershipSerializer, DeveloperExpertiseSerializer
        repo = Repository.objects.get(id=repo_id, user=request.user)
        ownerships = CodeOwnership.objects.filter(repository=repo).order_by('-expertise_score')[:100]
        expertise = DeveloperExpertise.objects.filter(repository=repo).order_by('-total_commits')
        return Response({
            'ownership': CodeOwnershipSerializer(ownerships, many=True).data,
            'expertise': DeveloperExpertiseSerializer(expertise, many=True).data,
        })
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def analyze_code_ownership(request, repo_id):
    """Trigger code ownership analysis for a repo."""
    try:
        repo = Repository.objects.get(id=repo_id, user=request.user)
        from .tasks import analyze_code_ownership_task
        analyze_code_ownership_task.delay(repo.id)
        return Response({'message': 'Ownership analysis started', 'repo_id': repo.id})
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


# =============================================================================
# PHASE 7: Conflict Detection & Dependency Analysis Views
# =============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def analyze_conflicts(request, repo_id):
    """Trigger conflict analysis for all open PRs in a repository."""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        from .tasks import analyze_pr_conflicts_task
        analyze_pr_conflicts_task.delay(repository.id)
        return Response({
            'message': 'Conflict analysis started',
            'repository': repository.full_name,
        }, status=202)
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_conflicts(request, repo_id):
    """List all detected conflicts for a repository."""
    try:
        from .models import ConflictDetection
        from .serializers import ConflictDetectionSerializer
        repository = Repository.objects.get(id=repo_id, user=request.user)
        show_resolved = request.query_params.get('resolved', 'false') == 'true'

        conflicts = ConflictDetection.objects.filter(
            pr_1__repository=repository
        )
        if not show_resolved:
            conflicts = conflicts.filter(is_resolved=False)

        serializer = ConflictDetectionSerializer(conflicts, many=True)
        return Response(serializer.data)
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def pr_conflicts(request, repo_id, pr_number):
    """Get conflicts for a specific pull request."""
    try:
        from .models import ConflictDetection
        from .serializers import ConflictDetectionSerializer
        repository = Repository.objects.get(id=repo_id, user=request.user)
        pr = repository.pull_requests.get(number=pr_number)

        conflicts = ConflictDetection.objects.filter(
            pr_1=pr
        ) | ConflictDetection.objects.filter(
            pr_2=pr
        )
        conflicts = conflicts.filter(is_resolved=False)

        serializer = ConflictDetectionSerializer(conflicts, many=True)
        return Response(serializer.data)
    except (Repository.DoesNotExist, PullRequest.DoesNotExist):
        return Response({'error': 'PR not found'}, status=404)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def resolve_conflict(request, conflict_id):
    """Mark a conflict as resolved."""
    try:
        from .models import ConflictDetection
        conflict = ConflictDetection.objects.get(
            id=conflict_id,
            pr_1__repository__user=request.user
        )
        conflict.is_resolved = True
        conflict.resolved_at = timezone.now()
        conflict.save()
        return Response({'message': 'Conflict marked as resolved'})
    except ConflictDetection.DoesNotExist:
        return Response({'error': 'Conflict not found'}, status=404)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def notify_conflict(request, conflict_id):
    """Notify developers about a conflict (posts GitHub comments)."""
    try:
        from .models import ConflictDetection
        conflict = ConflictDetection.objects.get(
            id=conflict_id,
            pr_1__repository__user=request.user
        )

        # Post comments on both PRs via GitHub API
        from .github_api import GitHubAPIClient
        client = GitHubAPIClient(request.user.github_access_token)
        repo_name = conflict.pr_1.repository.full_name

        comment_body = (
            f"⚠️ **Conflict Alert**\n\n"
            f"This PR conflicts with PR #{conflict.pr_2.number} (`{conflict.pr_2.title}`)\n\n"
            f"**Conflict Type:** {conflict.get_conflict_type_display()}\n"
            f"**Severity:** {conflict.get_severity_display()}\n\n"
            f"**Affected Files:** {', '.join(conflict.affected_files[:5])}\n\n"
            f"**Recommendation:** {conflict.resolution_suggestion}\n"
        )

        try:
            client.post_comment(repo_name, conflict.pr_1.number, comment_body)
            client.post_comment(repo_name, conflict.pr_2.number,
                comment_body.replace(
                    f"PR #{conflict.pr_2.number}",
                    f"PR #{conflict.pr_1.number}"
                )
            )
        except Exception:
            pass

        conflict.notified = True
        conflict.notified_at = timezone.now()
        conflict.save()

        return Response({'message': 'Developers notified'})
    except ConflictDetection.DoesNotExist:
        return Response({'error': 'Conflict not found'}, status=404)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def analyze_dependencies(request, repo_id):
    """Trigger dependency analysis for a repository."""
    try:
        repository = Repository.objects.get(id=repo_id, user=request.user)
        from .tasks import analyze_dependencies_task
        analyze_dependencies_task.delay(repository.id)
        return Response({
            'message': 'Dependency analysis started',
            'repository': repository.full_name,
        }, status=202)
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_dependencies(request, repo_id):
    """List all dependency analyses for a repository."""
    try:
        from .models import DependencyAnalysis
        from .serializers import DependencyAnalysisSerializer
        repository = Repository.objects.get(id=repo_id, user=request.user)

        analyses = DependencyAnalysis.objects.filter(
            repository=repository
        ).order_by('-impact_score')

        serializer = DependencyAnalysisSerializer(analyses, many=True)
        return Response(serializer.data)
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dependency_detail(request, repo_id, package_name):
    """Get detailed analysis for a specific dependency."""
    try:
        from .models import DependencyAnalysis
        from .serializers import DependencyAnalysisSerializer
        repository = Repository.objects.get(id=repo_id, user=request.user)

        analysis = DependencyAnalysis.objects.filter(
            repository=repository,
            package_name=package_name
        ).first()

        if not analysis:
            return Response({'error': 'Dependency analysis not found'}, status=404)

        serializer = DependencyAnalysisSerializer(analysis)
        return Response(serializer.data)
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dependency_impact_report(request, repo_id):
    """Get aggregated impact report for all dependencies."""
    try:
        from .models import DependencyAnalysis
        repository = Repository.objects.get(id=repo_id, user=request.user)

        analyses = DependencyAnalysis.objects.filter(repository=repository)

        total = analyses.count()
        with_updates = analyses.exclude(latest_version='').exclude(
            current_version=models.F('latest_version')
        ).count()
        breaking = analyses.filter(has_breaking_changes=True).count()
        safe = with_updates - breaking

        # Categorize by impact
        critical = analyses.filter(impact_score__gte=80).count()
        high = analyses.filter(impact_score__gte=60, impact_score__lt=80).count()
        medium = analyses.filter(impact_score__gte=30, impact_score__lt=60).count()
        low = analyses.filter(impact_score__lt=30).count()

        # Estimate total refactor time
        total_hours = sum(a.estimated_refactor_hours for a in analyses.filter(has_breaking_changes=True))

        return Response({
            'summary': {
                'total_dependencies': total,
                'updates_available': with_updates,
                'breaking_changes': breaking,
                'safe_updates': safe,
            },
            'impact_breakdown': {
                'critical': critical,
                'high': high,
                'medium': medium,
                'low': low,
            },
            'estimated_total_refactor_hours': total_hours,
            'last_analyzed': analyses.order_by('-analyzed_at').first().analyzed_at if analyses.exists() else None,
        })
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


# ============================================================================
# PHASE 8: COGNITIVE DEBT TRACKING
# ============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def repository_cognitive_debt(request, repo_id):
    """
    GET /api/repositories/<repo_id>/debt/
    Returns all file comprehension scores for a repository, sorted worst-first.
    """
    try:
        from .models import FileComprehensionScore
        from .serializers import FileComprehensionScoreSerializer

        repository = Repository.objects.get(id=repo_id, user=request.user)

        # Optional filter by risk level
        risk = request.query_params.get('risk', None)
        scores = FileComprehensionScore.objects.filter(repository=repository)
        if risk in ('red', 'amber', 'green'):
            scores = scores.filter(risk_level=risk)

        scores = scores.order_by('comprehension_score')

        serializer = FileComprehensionScoreSerializer(scores, many=True)
        return Response(serializer.data)
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def cognitive_debt_summary(request, repo_id):
    """
    GET /api/repositories/<repo_id>/debt/summary/
    Returns an aggregated summary for the dashboard header cards.
    """
    try:
        from .models import FileComprehensionScore

        repository = Repository.objects.get(id=repo_id, user=request.user)
        scores = FileComprehensionScore.objects.filter(repository=repository)

        total = scores.count()
        red = scores.filter(risk_level='red').count()
        amber = scores.filter(risk_level='amber').count()
        green = scores.filter(risk_level='green').count()

        # Compute overall repo comprehension score (average)
        if total > 0:
            from django.db.models import Avg
            avg_score = scores.aggregate(avg=Avg('comprehension_score'))['avg']
            overall_score = round(avg_score or 0)
        else:
            overall_score = 0

        # Get the worst files for alerts
        critical_files = scores.filter(risk_level='red').order_by('comprehension_score')[:5]
        critical_alerts = []
        for f in critical_files:
            critical_alerts.append({
                'file_path': f.file_path,
                'score': f.comprehension_score,
                'ai_pct': f.ai_authorship_pct,
                'suggested_reviewer': f.suggested_reviewer,
            })

        last_analyzed = scores.order_by('-last_analyzed_at').first()

        return Response({
            'total_files': total,
            'red_files': red,
            'amber_files': amber,
            'green_files': green,
            'overall_score': overall_score,
            'critical_alerts': critical_alerts,
            'last_analyzed_at': last_analyzed.last_analyzed_at if last_analyzed else None,
        })
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_debt_analysis(request, repo_id):
    """
    POST /api/repositories/<repo_id>/debt/analyse/
    Manually trigger cognitive debt analysis.
    """
    try:
        from .tasks import analyse_cognitive_debt

        repository = Repository.objects.get(id=repo_id, user=request.user)

        task = analyse_cognitive_debt.delay(repository.id, force=True)

        return Response({
            'message': f'Cognitive debt analysis started for {repository.full_name}',
            'task_id': task.id,
            'repository_id': repository.id,
        }, status=202)
    except Repository.DoesNotExist:
        return Response({'error': 'Repository not found'}, status=404)