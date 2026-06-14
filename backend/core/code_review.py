"""
Code Review Logic
Handles PR analysis workflow
"""

from .models import PullRequest, PRAnalysis
from .ai_code_analyzer import AICodeAnalyzer
from .github_api import GitHubAPIClient
import logging

logger = logging.getLogger(__name__)


class CodeReviewer:
    """
    Manages code review process
    """
    
    def __init__(self, pull_request):
        self.pr = pull_request
        self.repository = pull_request.repository
        self.user = self.repository.user
        self.analyzer = AICodeAnalyzer()
    
    def perform_analysis(self):
        """
        Perform full PR analysis
        
        Returns:
            PRAnalysis: Analysis object
        """
        logger.info(f"Starting analysis for PR #{self.pr.number}")
        
        # Get PR diff from GitHub
        client = GitHubAPIClient(self.user.github_access_token)
        diff_content = self.get_pr_diff(client)
        
        if not diff_content:
            logger.error("Failed to fetch PR diff")
            return None
        
        # Prepare PR context
        pr_context = {
            'title': self.pr.title,
            'description': self.pr.body,
            'files_changed': self.pr.changed_files,
            'additions': self.pr.additions,
            'deletions': self.pr.deletions,
        }
        
        # Run AI analysis
        result = self.analyzer.analyze_pr_diff(diff_content, pr_context)
        
        if not result['success']:
            logger.error(f"Analysis failed: {result.get('error')}")
            return None
        
        analysis_data = result['analysis']
        
        # Calculate scores
        security_score = self.calculate_security_score(analysis_data.get('security_issues', []))
        performance_score = self.calculate_performance_score(analysis_data.get('performance_issues', []))
        quality_score = self.calculate_quality_score(analysis_data.get('code_smells', []))
        
        # Count total issues
        total_issues = (
            len(analysis_data.get('security_issues', [])) +
            len(analysis_data.get('performance_issues', [])) +
            len(analysis_data.get('code_smells', []))
        )
        
        # Create or update analysis
        pr_analysis, created = PRAnalysis.objects.update_or_create(
            pull_request=self.pr,
            defaults={
                'summary': analysis_data.get('summary', 'Analysis complete'),
                'issues_found': total_issues,
                'security_score': security_score,
                'performance_score': performance_score,
                'quality_score': quality_score,
                'complexity_score': analysis_data.get('complexity_score', 0),
                'security_issues': analysis_data.get('security_issues', []),
                'performance_issues': analysis_data.get('performance_issues', []),
                'code_smells': analysis_data.get('code_smells', []),
                'positive_points': analysis_data.get('positive_points', []),
                'analysis_time': result['analysis_time'],
                'tokens_used': result['tokens_used'],
            }
        )
        
        logger.info(f"Analysis complete for PR #{self.pr.number}. Found {total_issues} issues.")
        
        return pr_analysis
    
    def post_comment_to_github(self, pr_analysis):
        """
        Post analysis as comment on GitHub PR
        
        Args:
            pr_analysis (PRAnalysis): Analysis object
        
        Returns:
            bool: Success status
        """
        if pr_analysis.comment_posted:
            logger.info(f"Comment already posted for PR #{self.pr.number}")
            return True
        
        # Generate comment
        analysis_data = {
            'summary': pr_analysis.summary,
            'security_issues': pr_analysis.security_issues,
            'performance_issues': pr_analysis.performance_issues,
            'code_smells': pr_analysis.code_smells,
            'positive_points': pr_analysis.positive_points,
            'complexity_score': pr_analysis.complexity_score,
        }
        
        comment_body = self.analyzer.generate_pr_comment(analysis_data)
        
        # Post to GitHub
        try:
            client = GitHubAPIClient(self.user.github_access_token)
            comment = self.post_pr_comment(client, comment_body)
            
            if comment:
                pr_analysis.comment_posted = True
                pr_analysis.github_comment_id = str(comment.get('id', ''))
                pr_analysis.save()
                
                logger.info(f"Posted comment to PR #{self.pr.number}")
                return True
            
        except Exception as e:
            logger.error(f"Failed to post comment: {e}")
        
        return False
    
    def get_pr_diff(self, client):
        """
        Fetch PR diff from GitHub
        
        Args:
            client (GitHubAPIClient): GitHub client
        
        Returns:
            str: Diff content
        """
        try:
            import requests
            
            # Use GitHub API to get diff
            url = f"https://api.github.com/repos/{self.repository.full_name}/pulls/{self.pr.number}"
            headers = {
                'Authorization': f'token {self.user.github_access_token}',
                'Accept': 'application/vnd.github.v3.diff'
            }
            
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            return response.text
            
        except Exception as e:
            logger.error(f"Error fetching PR diff: {e}")
            return None
    
    def post_pr_comment(self, client, comment_body):
        """
        Post comment to PR
        
        Args:
            client (GitHubAPIClient): GitHub client
            comment_body (str): Comment text
        
        Returns:
            dict: Comment data
        """
        try:
            import requests
            
            url = f"https://api.github.com/repos/{self.repository.full_name}/issues/{self.pr.number}/comments"
            headers = {
                'Authorization': f'token {self.user.github_access_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            data = {'body': comment_body}
            
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Error posting PR comment: {e}")
            return None
    
    def calculate_security_score(self, issues):
        """Calculate security score (0-100)"""
        if not issues:
            return 100
        
        penalty = 0
        for issue in issues:
            severity = issue.get('severity', 'low')
            if severity == 'critical':
                penalty += 40
            elif severity == 'high':
                penalty += 20
            elif severity == 'medium':
                penalty += 10
            else:
                penalty += 5
        
        return max(0, 100 - penalty)
    
    def calculate_performance_score(self, issues):
        """Calculate performance score (0-100)"""
        if not issues:
            return 100
        
        penalty = len(issues) * 15
        return max(0, 100 - penalty)
    
    def calculate_quality_score(self, issues):
        """Calculate code quality score (0-100)"""
        if not issues:
            return 100
        
        penalty = len(issues) * 10
        return max(0, 100 - penalty)