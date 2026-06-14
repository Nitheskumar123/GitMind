import os
import time
import logging
import json
from typing import List, Dict, Any, Optional
from groq import Groq
from django.conf import settings
from .models import DocumentationGeneration, Repository
from django.utils import timezone

# Initialize Logger
logger = logging.getLogger(__name__)

class DocumentationGenerator:
    """
    Advanced Documentation Generator using Groq AI.
    Generates READMEs, API docs, and technical guides by analyzing repository structure.
    """

    def __init__(self):
        """Initialize Groq client and model settings."""
        self.api_key = getattr(settings, 'GROQ_API_KEY', None)
        if not self.api_key:
            logger.error("GROQ_API_KEY is missing from Django settings.")
            raise ValueError("GROQ_API_KEY is required.")
            
        self.client = Groq(api_key=self.api_key)
        self.model = getattr(settings, 'GROQ_MODEL', 'llama-3.3-70b-versatile')
        self.max_tokens = 4096

    def generate_readme(self, repository: Any, code_files: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate a comprehensive README.md for the repository.
        
        Args:
            repository: Repository model instance.
            code_files: List of dicts containing 'path' and 'content'.
        """
        start_time = time.time()
        
        # 1. Gather structural context
        structure_summary = self._analyze_code_structure(code_files)
        tech_stack = self._detect_tech_stack(code_files, repository.language)
        
        system_prompt = """
        You are a World-Class Technical Writer and Developer Advocate.
        Your goal is to create a README.md that makes a project look professional, 
        trustworthy, and easy to use.
        
        Required Sections:
        1. Professional Project Title & Catchy Description.
        2. Badges (Build, License, Version).
        3. Visual Tech Stack (Icons/Tags).
        4. Detailed Key Features.
        5. Prerequisites & Installation (be specific to the detected stack).
        6. Usage Examples with Code Blocks.
        7. Project Structure Tree.
        8. Contributing & License.
        
        Use clean Markdown, emojis for visual appeal, and high-quality headers.
        """

        user_message = f"""
        Generate a top-tier README.md for:
        Project: {repository.full_name}
        Description: {repository.description or 'No description provided'}
        Primary Language: {repository.language}
        
        Detected Tech Stack: {tech_stack}
        
        Repository Structure:
        {structure_summary}
        
        Key Code Samples for Context:
        {self._format_code_samples(code_files[:5])}
        
        Write the full Markdown content now.
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3,
                max_tokens=self.max_tokens
            )
            
            content = response.choices[0].message.content
            duration = time.time() - start_time
            tokens = response.usage.total_tokens

            return {
                'success': True,
                'content': content,
                'tokens_used': tokens,
                'generation_time': duration
            }

        except Exception as e:
            logger.error(f"Groq README generation failed: {e}")
            return {'success': False, 'error': str(e), 'generation_time': time.time() - start_time}

    def generate_api_documentation(self, code_files: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extracts and documents public APIs, endpoints, and class methods.
        """
        start_time = time.time()
        api_snippet = self._extract_api_code(code_files)
        
        system_prompt = """
        You are an API Documentation specialist.
        Generate a Markdown API Reference.
        For every function/endpoint, include:
        - Method & Route (if web API)
        - Parameters (type, required/optional)
        - Return value structure
        - A concise description
        - A 'Curl' or 'Python Request' example.
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Document the following API logic:\n\n{api_snippet}"}
                ],
                max_tokens=self.max_tokens
            )
            return {
                'success': True,
                'content': response.choices[0].message.content,
                'generation_time': time.time() - start_time
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _analyze_code_structure(self, code_files: List[Dict[str, Any]]) -> str:
        """Categorize files to help AI understand project architecture."""
        file_stats = {}
        important_paths = []
        
        for f in code_files:
            ext = f['path'].split('.')[-1]
            file_stats[ext] = file_stats.get(ext, 0) + 1
            
            # Identify core logic files
            path_lower = f['path'].lower()
            if any(k in path_lower for k in ['app', 'main', 'routes', 'models', 'controller', 'index']):
                important_paths.append(f['path'])

        summary = "File Types: " + ", ".join([f"{k}: {v}" for k, v in file_stats.items()])
        summary += "\nCore Components Identified: " + ", ".join(important_paths[:10])
        return summary

    def _detect_tech_stack(self, code_files: List[Dict[str, Any]], primary_lang: str) -> str:
        """Scan contents for specific frameworks."""
        stack = [primary_lang]
        content_blob = " ".join([f['content'][:500] for f in code_files]).lower()
        
        detectors = {
            'django': 'Django (Python Framework)',
            'flask': 'Flask (Python)',
            'react': 'React.js',
            'express': 'Express.js (Node)',
            'sqlalchemy': 'SQLAlchemy (ORM)',
            'pandas': 'Pandas (Data Science)',
            'dockerfile': 'Docker',
            'kubernetes': 'K8s',
            'groq': 'Groq SDK'
        }
        
        for key, val in detectors.items():
            if key in content_blob:
                stack.append(val)
        
        return ", ".join(list(set(stack)))

    def _format_code_samples(self, code_files: List[Dict[str, Any]]) -> str:
        """Prepares code snippets for the AI prompt."""
        formatted = []
        for f in code_files:
            path = f['path']
            # Take a chunk of code, but avoid blowing up token limit
            content = f['content'][:1200]
            formatted.append(f"--- File: {path} ---\n{content}\n")
        return "\n".join(formatted)

    def _extract_api_code(self, code_files: List[Dict[str, Any]]) -> str:
        """Filters files to find only those containing API definitions."""
        api_related = []
        keywords = ['@app.', '@api.', 'def ', 'class ', 'router.', 'endpoint', 'async def']
        
        for f in code_files:
            content = f['content']
            if any(k in content for k in keywords):
                api_related.append(f"File: {f['path']}\n{content[:1500]}")
        
        return "\n\n".join(api_related) if api_related else "No obvious API code found."

    def save_doc_to_db(self, repo_id: int, user_id: int, doc_type: str, result: Dict[str, Any]):
        """Persist the generated docs to the Django Database."""
        try:
            doc_entry = DocumentationGeneration.objects.create(
                repository_id=repo_id,
                user_id=user_id,
                doc_type=doc_type,
                status='completed' if result.get('success') else 'failed',
                content=result.get('content'),
                error_message=result.get('error'),
                tokens_used=result.get('tokens_used', 0),
                generation_time=result.get('generation_time', 0.0),      
                completed_at=timezone.now() if result.get('success') else None
            )
            return doc_entry
        except Exception as e:
            logger.error(f"Failed to save documentation to DB: {e}")
            return None

    def detect_language_simple(self, filename: str) -> str:
        """Mapping extensions to markdown language tags."""
        ext = filename.split('.')[-1].lower()
        mapping = {
            'py': 'python', 'js': 'javascript', 'ts': 'typescript',
            'html': 'html', 'css': 'css', 'go': 'go', 'rs': 'rust'
        }
        return mapping.get(ext, '')

# End of documentation_gen.py