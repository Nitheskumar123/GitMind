import os
import json
import time
import logging
from typing import Dict, Any, List, Optional
from groq import Groq
from django.conf import settings
from .models import PRAnalysis, PullRequest

# Set up logging
logger = logging.getLogger(__name__)

class AICodeAnalyzer:
    """
    Advanced AI-Powered Code Analyzer using Groq.
    Analyzes Pull Request diffs for security, performance, and code quality.
    """

    def __init__(self):
        """Initialize the Groq client using Django settings."""
        self.api_key = getattr(settings, 'GROQ_API_KEY', None)
        if not self.api_key:
            logger.error("GROQ_API_KEY not found in settings.")
            raise ValueError("GROQ_API_KEY is required.")
        
        self.client = Groq(api_key=self.api_key)
        self.model = getattr(settings, 'GROQ_MODEL', 'llama-3.3-70b-versatile')
        self.max_tokens = getattr(settings, 'GROQ_MAX_TOKENS', 4096)

    def analyze_pr_diff(self, diff_content: str, pr_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze pull request diff for issues using Groq's high-speed inference.
        
        Args:
            diff_content (str): Git diff content.
            pr_context (dict): PR metadata (title, description, files changed, etc.)
        """
        start_time = time.time()
        
        system_prompt = """
        You are an expert Senior Software Engineer and Security Auditor. 
        Your task is to analyze a Git Pull Request diff and provide a deep technical review.
        
        Evaluation Criteria:
        1. Security: Check for SQL injection, XSS, hardcoded secrets, insecure Auth flows.
        2. Performance: Identify N+1 queries, inefficient loops, or heavy memory usage.
        3. Code Quality: Detect anti-patterns, DRY violations, and readability issues.
        4. Complexity: Estimate cyclomatic complexity and cognitive load.
        
        Output Format:
        You MUST respond in valid JSON format. Do not include any text outside the JSON block.
        {
            "summary": "Overall assessment of the PR",
            "security_issues": [
                {"severity": "high|medium|low", "line": 0, "issue": "desc", "recommendation": "fix"}
            ],
            "performance_issues": [
                {"severity": "medium|low", "line": 0, "issue": "desc", "recommendation": "fix"}
            ],
            "code_smells": [
                {"line": 0, "issue": "desc", "recommendation": "fix"}
            ],
            "positive_points": ["List of good things"],
            "complexity_score": 0,
            "estimated_review_time": "X minutes",
            "security_score": 0,
            "quality_score": 0
        }
        """

        user_message = f"""
        Analyze this pull request:
        PR Title: {pr_context.get('title', 'N/A')}
        Description: {pr_context.get('description', 'No description')}
        Files Changed: {pr_context.get('files_changed', 0)}
        Additions: +{pr_context.get('additions', 0)}
        Deletions: -{pr_context.get('deletions', 0)}
        
        Diff Content:
        {diff_content[:15000]}  # Increased limit for Groq's context window
        
        Provide the analysis in the requested JSON structure.
        """

        try:
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                model=self.model,
                temperature=0.2, # Lower temperature for more consistent JSON
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"}
            )

            raw_content = chat_completion.choices[0].message.content
            analysis = json.loads(raw_content)
            
            # Post-processing stats
            tokens_used = chat_completion.usage.total_tokens
            analysis_duration = time.time() - start_time

            return {
                'success': True,
                'analysis': analysis,
                'tokens_used': tokens_used,
                'analysis_time': analysis_duration
            }

        except Exception as e:
            logger.error(f"Groq PR Analysis failed: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'analysis_time': time.time() - start_time
            }

    def analyze_code_quality(self, code_content: str, language: str = 'python') -> Dict[str, Any]:
        """
        Deep dive into a specific file's quality and maintainability.
        """
        system_prompt = f"""
        You are a {language} specialist. Analyze the provided code for:
        - Readability & Naming conventions
        - Error handling robustness
        - Adherence to {language} best practices (e.g., PEP8 for Python)
        - Documentation/Docstring completeness
        
        Return JSON:
        {{
            "quality_score": 0-100,
            "readability": "Excellent|Good|Fair|Poor",
            "issues": [],
            "suggestions": []
        }}
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Analyze this {language} code:\n\n{code_content[:8000]}"}
                ],
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"Quality analysis error: {e}")
            return {'quality_score': 0, 'issues': [str(e)], 'suggestions': []}

    def generate_pr_comment(self, analysis: Dict[str, Any]) -> str:
        """
        Convert the JSON analysis into a beautifully formatted Markdown comment.
        """
        if not analysis:
            return "⚠️ AI Review failed to generate analysis."

        comment = "## 🤖 AI Code Review (Powered by Groq)\n\n"
        comment += f"> **Summary:** {analysis.get('summary', 'No summary available.')}\n\n"

        # Security Section
        sec_issues = analysis.get('security_issues', [])
        if sec_issues:
            comment += "### 🔴 Security Vulnerabilities\n"
            comment += "| Severity | Line | Issue | Recommendation |\n"
            comment += "|:---:|:---:|:---|:---|\n"
            for issue in sec_issues:
                sev_icon = "🛑" if issue.get('severity') == 'high' else "⚠️"
                comment += f"| {sev_icon} {issue.get('severity').upper()} | {issue.get('line')} | {issue.get('issue')} | {issue.get('recommendation')} |\n"
            comment += "\n"

        # Performance Section
        perf_issues = analysis.get('performance_issues', [])
        if perf_issues:
            comment += "### 🚀 Performance Optimization\n"
            for issue in perf_issues:
                comment += f"- **Line {issue.get('line')}**: {issue.get('issue')}\n"
                comment += f"  - *Fix:* {issue.get('recommendation')}\n"
            comment += "\n"

        # Quality/Smells
        smells = analysis.get('code_smells', [])
        if smells:
            comment += "### 💡 Code Quality & Smells\n"
            for smell in smells:
                comment += f"- **Line {smell.get('line')}**: {smell.get('issue')}\n"
            comment += "\n"

        # Positives
        positives = analysis.get('positive_points', [])
        if positives:
            comment += "### ✅ Positive Highlights\n"
            for point in positives:
                comment += f"- {point}\n"
            comment += "\n"

        # Metrics Table
        comment += "### 📊 Metrics\n"
        comment += f"- **Complexity Score:** `{analysis.get('complexity_score', 'N/A')}`\n"
        comment += f"- **Estimated Manual Review Time:** `{analysis.get('estimated_review_time', 'N/A')}`\n"
        comment += f"- **Quality Score:** `{analysis.get('quality_score', 0)}/100`\n"
        
        comment += "\n---\n*Disclaimer: AI reviews can be wrong. Please verify manually before merging.*"
        return comment

    def save_analysis_to_db(self, pull_request_id: int, analysis_results: Dict[str, Any]):
        """
        Persist analysis data into the Django PRAnalysis model.
        """
        try:
            pr = PullRequest.objects.get(id=pull_request_id)
            analysis_data = analysis_results.get('analysis', {})
            
            PRAnalysis.objects.update_or_create(
                pull_request=pr,
                defaults={
                    'summary': analysis_data.get('summary', ''),
                    'issues_found': len(analysis_data.get('security_issues', [])) + len(analysis_data.get('performance_issues', [])),
                    'security_score': analysis_data.get('security_score', 100),
                    'quality_score': analysis_data.get('quality_score', 100),
                    'complexity_score': analysis_data.get('complexity_score', 0),
                    'security_issues': analysis_data.get('security_issues', []),
                    'performance_issues': analysis_data.get('performance_issues', []),
                    'code_smells': analysis_data.get('code_smells', []),
                    'positive_points': analysis_data.get('positive_points', []),
                    'tokens_used': analysis_results.get('tokens_used', 0),
                    'analysis_time': analysis_results.get('analysis_time', 0.0)
                }
            )
            return True
        except PullRequest.DoesNotExist:
            logger.error(f"PR with ID {pull_request_id} not found.")
            return False
        except Exception as e:
            logger.error(f"Database save error: {e}")
            return False

# End of ai_code_analyzer.py