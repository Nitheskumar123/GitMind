import json
import time
import logging
from datetime import timedelta
from typing import List, Dict, Any, Optional

from groq import Groq
from django.conf import settings
from django.utils import timezone
from django.db.models import Count, Avg, F
from django.db.models import Q

from .models import (
    Repository, 
    CodeInsight, 
    PullRequest, 
    Issue, 
    Commit, 
    User
)

# Configure logging
logger = logging.getLogger(__name__)

class InsightsEngine:
    """
    Proactive AI Insights Engine powered by Groq.
    Analyzes repository health, developer velocity, and project bottlenecks
    to generate actionable intelligence for maintainers.
    """

    def __init__(self):
        """Initialize Groq client and engine configurations."""
        self.api_key = getattr(settings, 'GROQ_API_KEY', None)
        if not self.api_key:
            logger.error("GROQ_API_KEY missing. Insights Engine will fail.")
            raise ValueError("GROQ_API_KEY is required for InsightsEngine.")
            
        self.client = Groq(api_key=self.api_key)
        self.model = getattr(settings, 'GROQ_MODEL', 'llama-3.3-70b-versatile')
        self.max_tokens = 3000

    def generate_repository_insights(self, repository):
        repo_data = self.collect_repository_data(repository)
        result = self.analyze_with_ai(repository, repo_data)      # returns dict now
        raw_insights = result.get('insights', [])                  # extract list
        self.actual_tokens_used = result.get('tokens_used', 0)    # store for tasks.py
        saved_insights = self.save_insights(repository, raw_insights)
        repository.last_synced_at = timezone.now()
        repository.save()
        return saved_insights

    def collect_repository_data(self, repository: Repository) -> Dict[str, Any]:
        """
        Aggregates metrics from Commits, PRs, and Issues to build a project snapshot.
        """
        now = timezone.now()
        last_7_days = now - timedelta(days=7)
        last_30_days = now - timedelta(days=30)

        # Pull Request Metrics
        open_prs = repository.pull_requests.filter(state='open')
        stale_prs = open_prs.filter(created_at__lt=last_7_days)
        merged_recently = repository.pull_requests.filter(
            merged=True, 
            merged_at__gte=last_30_days
        )

        # Issue Metrics
        open_issues = repository.issues.filter(state='open')
        critical_issues = open_issues.filter(
            body__icontains='urgent'
        ) | open_issues.filter(title__icontains='critical')

        # Commit & Activity Metrics
        recent_commits = repository.commits.filter(committed_at__gte=last_7_days)
        commit_authors = recent_commits.values('author_login').annotate(count=Count('id'))
        
        # Calculate Average PR Merge Time (Lead Time)
        avg_merge_time = merged_recently.annotate(
            duration=F('merged_at') - F('created_at')
        ).aggregate(avg_time=Avg('duration'))['avg_time']

        return {
            'metadata': {
                'name': repository.full_name,
                'lang': repository.language,
                'stars': repository.stars_count,
                'forks': repository.forks_count,
            },
            'prs': {
                'open_count': open_prs.count(),
                'stale_count': stale_prs.count(),
                'avg_merge_days': avg_merge_time.days if avg_merge_time else 'N/A',
                'stale_list': list(stale_prs.values('number', 'title', 'author_login', 'created_at')[:5])
            },
            'issues': {
                'open_count': open_issues.count(),
                'critical_count': critical_issues.count(),
                'critical_list': list(critical_issues.values('number', 'title')[:5])
            },
            'activity': {
                'commits_last_week': recent_commits.count(),
                'active_contributors': commit_authors.count(),
                'top_contributor': commit_authors.order_by('-count').first() if commit_authors else None
            }
        }

    def analyze_with_ai(self, repository: Repository, repo_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Communicates with Groq to identify patterns and generate the JSON insights.
        """
        system_prompt = """
        You are an AI Repository Health Consultant. Analyze the provided GitHub metrics and return 
        actionable insights in a structured JSON format.
        
        Categories of Insights:
        1. "alert": Critical bottlenecks or security/process risks.
        2. "suggestion": Workflow or code quality improvements.
        3. "win": Milestones or positive velocity trends.
        4. "trend": Statistical patterns (e.g., "Review time is increasing").

        Priorities: "critical", "high", "medium", "low".
        
        Format:
        {
            "insights": [
                {
                    "type": "alert",
                    "priority": "high",
                    "category": "activity",
                    "title": "Short Title",
                    "description": "Deep analysis of the issue",
                    "recommendation": "Exact step to take"
                }
            ]
        }
        """

        user_message = f"""
        Analyze the health of {repository.full_name}.
        
        DATA SNAPSHOT:
        - PRs: {repo_data['prs']['open_count']} open, {repo_data['prs']['stale_count']} stale (>7 days).
        - Issues: {repo_data['issues']['open_count']} total, {repo_data['issues']['critical_count']} critical.
        - Velocity: {repo_data['activity']['commits_last_week']} commits this week by {repo_data['activity']['active_contributors']} devs.
        - Avg Merge Time: {repo_data['prs']['avg_merge_days']} days.
        
        SPECIFIC STALE ITEMS:
        {self._format_json_for_prompt(repo_data['prs']['stale_list'])}
        
        Generate at least 3-5 high-quality, specific insights in JSON.
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                response_format={"type": "json_object"},
                temperature=0.2
            )
            
            data = json.loads(response.choices[0].message.content)
            return {
    'insights': data.get('insights', []),
    'tokens_used': response.usage.total_tokens  # ← add this
}

        except Exception as e:
            logger.error(f"Groq Inference Error: {e}")
            return {'insights': [], 'tokens_used': 0}

    def save_insights(self, repository: Repository, insights_list: List[Dict[str, Any]]) -> List[CodeInsight]:
        """
        Saves the generated insights to the DB, preventing duplicate alerts for the same issue.
        """
        saved_objects = []
        
        for item in insights_list:
            # logic: If an unresolved insight with the same title exists, just update its description
            # This prevents spamming the user with the same "Stale PR" alert every day.
            obj, created = CodeInsight.objects.update_or_create(
                repository=repository,
                title=item.get('title', 'Untitled Insight'),
                is_resolved=False,
                defaults={
                    'insight_type': item.get('type', 'suggestion'),
                    'priority': item.get('priority', 'medium'),
                    'description': item.get('description', ''),
                    'recommendation': item.get('recommendation', ''),
                    'category': item.get('category', 'general'),
                }
            )
            saved_objects.append(obj)
            
        return saved_objects

    def generate_all_user_insights(self, user: User) -> int:
        """
        Iterates through all active repositories for a specific user,
        respecting automation settings and frequency constraints.
        """
        from .automation import AutomationEngine  # Local import to avoid circular dependency
        
        active_repos = Repository.objects.filter(user=user, is_active=True)
        total_insight_count = 0
        
        for repo in active_repos:
            # Initialize the decision engine for this specific repository
            engine = AutomationEngine(repo)
            
            # Check if auto-insights is enabled and if the frequency conditions are met
            decision = engine.should_generate_insights()
            
            if decision['should_generate']:
                logger.info(f"Triggering AI insights for {repo.full_name} based on user settings.")
                
                # Generate and save the insights using the existing method
                results = self.generate_repository_insights(repo)
                total_insight_count += len(results)
                
                # Note: track_api_cost is usually called in the Celery task, 
                # but ensure tokens are tracked globally to avoid limit overruns.
            else:
                logger.info(f"Skipping insights for {repo.full_name}. Reason: {decision['reason']}")
        
        return total_insight_count

    def get_trend_report(self, repository: Repository, days: int = 30) -> Dict[str, Any]:
        """
        A non-AI utility to provide historical trend data for the frontend.
        """
        start_date = timezone.now() - timedelta(days=days)
        
        insights_by_type = CodeInsight.objects.filter(
            repository=repository, 
            created_at__gte=start_date
        ).values('insight_type').annotate(count=Count('id'))
        
        resolution_rate = CodeInsight.objects.filter(
            repository=repository,
            created_at__gte=start_date
        ).aggregate(
            total=Count('id'),
            resolved=Count('id', filter=Q(is_resolved=True))
        )
        
        return {
            'period_days': days,
            'insight_distribution': list(insights_by_type),
            'stats': resolution_rate
        }

    def _format_json_for_prompt(self, data: Any) -> str:
        """Helper to cleanly format data for LLM consumption."""
        return json.dumps(data, indent=2, default=str)

    def cleanup_old_insights(self, repository: Repository, days_old: int = 90):
        """Housekeeping: Delete very old resolved insights."""
        threshold = timezone.now() - timedelta(days=days_old)
        deleted, _ = CodeInsight.objects.filter(
            repository=repository,
            is_resolved=True,
            updated_at__lt=threshold
        ).delete()
        return deleted

    def trigger_webhook_alert(self, insight: CodeInsight):
        """
        Placeholder for future integration.
        Could send a Slack or Discord notification for 'critical' insights.
        """
        if insight.priority == 'critical':
            logger.warning(f"CRITICAL INSIGHT: {insight.title} on {insight.repository.full_name}")
            # Logic for Slack Webhook would go here
            pass

# End of insights_engine.py