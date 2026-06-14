"""
Changelog Parser - Fetches and parses changelogs from PyPI, npm, and GitHub.
Uses Groq AI to categorize changelog entries into breaking/feature/fix.
"""

import re
import logging
import requests as http_requests
from django.conf import settings

logger = logging.getLogger(__name__)


class ChangelogParser:
    """Fetches and parses changelogs from package registries and GitHub."""

    def __init__(self):
        self.groq_api_key = getattr(settings, 'GROQ_API_KEY', '')

    def fetch_from_pypi(self, package_name):
        """Fetch package info and release notes from PyPI JSON API."""
        try:
            url = f"https://pypi.org/pypi/{package_name}/json"
            resp = http_requests.get(url, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"PyPI returned {resp.status_code} for {package_name}")
                return None

            data = resp.json()
            info = data.get('info', {})
            releases = data.get('releases', {})

            return {
                'name': package_name,
                'latest_version': info.get('version', ''),
                'summary': info.get('summary', ''),
                'home_page': info.get('home_page', ''),
                'project_url': info.get('project_url', ''),
                'package_url': info.get('package_url', ''),
                'release_versions': sorted(releases.keys(), key=self._version_sort_key, reverse=True)[:20],
                'description': info.get('description', '')[:2000],
                'changelog_url': self._find_changelog_url(info),
            }
        except Exception as e:
            logger.error(f"Error fetching PyPI info for {package_name}: {e}")
            return None

    def fetch_from_npm(self, package_name):
        """Fetch package info from npm registry."""
        try:
            url = f"https://registry.npmjs.org/{package_name}"
            resp = http_requests.get(url, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"npm returned {resp.status_code} for {package_name}")
                return None

            data = resp.json()
            latest = data.get('dist-tags', {}).get('latest', '')
            versions = list(data.get('versions', {}).keys())

            return {
                'name': package_name,
                'latest_version': latest,
                'summary': data.get('description', ''),
                'home_page': data.get('homepage', ''),
                'repository': data.get('repository', {}).get('url', ''),
                'release_versions': sorted(versions, key=self._version_sort_key, reverse=True)[:20],
            }
        except Exception as e:
            logger.error(f"Error fetching npm info for {package_name}: {e}")
            return None

    def fetch_from_github(self, repo_full_name, from_tag=None, to_tag=None, access_token=None):
        """Fetch release notes from GitHub releases API."""
        try:
            headers = {'Accept': 'application/vnd.github.v3+json'}
            if access_token:
                headers['Authorization'] = f'token {access_token}'

            url = f"https://api.github.com/repos/{repo_full_name}/releases"
            resp = http_requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"GitHub releases returned {resp.status_code} for {repo_full_name}")
                return None

            releases = resp.json()
            changelog_entries = []

            for release in releases[:20]:
                tag = release.get('tag_name', '')
                # Filter by tag range if specified
                if from_tag and to_tag:
                    tag_ver = self._extract_version(tag)
                    from_ver = self._extract_version(from_tag)
                    to_ver = self._extract_version(to_tag)
                    if tag_ver and from_ver and to_ver:
                        if self._version_sort_key(tag_ver) <= self._version_sort_key(from_ver):
                            continue
                        if self._version_sort_key(tag_ver) > self._version_sort_key(to_ver):
                            continue

                changelog_entries.append({
                    'version': tag,
                    'name': release.get('name', ''),
                    'body': release.get('body', '')[:2000],
                    'published_at': release.get('published_at', ''),
                    'prerelease': release.get('prerelease', False),
                })

            return changelog_entries
        except Exception as e:
            logger.error(f"Error fetching GitHub releases for {repo_full_name}: {e}")
            return None

    def parse_with_ai(self, changelog_text, package_name, from_version, to_version):
        """Use Groq AI to parse changelog and categorize changes."""
        if not self.groq_api_key:
            logger.warning("No GROQ_API_KEY configured, falling back to pattern parsing")
            return self.parse_with_patterns(changelog_text, package_name)

        try:
            from groq import Groq
            client = Groq(api_key=self.groq_api_key)

            prompt = f"""Analyze the following changelog for package "{package_name}" 
between versions {from_version} and {to_version}.

Categorize each change into EXACTLY one category:
- BREAKING: Changes that break backward compatibility
- FEATURE: New features or enhancements  
- FIX: Bug fixes
- DEPRECATION: Deprecated features that will be removed

Respond in this exact JSON format:
{{
    "breaking_changes": [
        {{"description": "...", "affects": ["file or API pattern"], "fix": "suggested fix"}}
    ],
    "new_features": ["description1", "description2"],
    "bug_fixes": ["description1"],
    "deprecations": [{{"description": "...", "removal_version": "..."}}]
}}

Changelog:
{changelog_text[:3000]}"""

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2000,
            )

            import json
            content = response.choices[0].message.content
            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                return json.loads(json_match.group())
            return self.parse_with_patterns(changelog_text, package_name)

        except Exception as e:
            logger.error(f"AI changelog parsing failed for {package_name}: {e}")
            return self.parse_with_patterns(changelog_text, package_name)

    def parse_with_patterns(self, changelog_text, package_name):
        """Pattern-based changelog parsing as fallback."""
        result = {
            'breaking_changes': [],
            'new_features': [],
            'bug_fixes': [],
            'deprecations': [],
        }

        if not changelog_text:
            return result

        lines = changelog_text.split('\n')
        for line in lines:
            line_lower = line.lower().strip()
            if not line_lower or line_lower.startswith('#'):
                continue

            if any(kw in line_lower for kw in ['breaking', 'removed', 'incompatible', 'migration required']):
                result['breaking_changes'].append({
                    'description': line.strip(),
                    'affects': [],
                    'fix': '',
                })
            elif any(kw in line_lower for kw in ['deprecated', 'deprecation']):
                result['deprecations'].append({
                    'description': line.strip(),
                    'removal_version': '',
                })
            elif any(kw in line_lower for kw in ['fix', 'bug', 'patch', 'resolve']):
                result['bug_fixes'].append(line.strip())
            elif any(kw in line_lower for kw in ['add', 'feature', 'new', 'enhance', 'support']):
                result['new_features'].append(line.strip())

        return result

    def extract_breaking_sections(self, changelog_text):
        """Extract sections specifically about breaking changes."""
        sections = []
        if not changelog_text:
            return sections

        # Look for breaking change headers
        patterns = [
            r'(?:^|\n)#+\s*[Bb]reaking\s*[Cc]hanges?(.*?)(?=\n#+|\Z)',
            r'(?:^|\n)\*\*[Bb]reaking\*\*(.*?)(?=\n\*\*|\Z)',
            r'(?:^|\n)BREAKING[:\s]+(.*?)(?=\n[A-Z]+[:\s]|\Z)',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, changelog_text, re.DOTALL)
            sections.extend([m.strip() for m in matches if m.strip()])

        return sections

    # --- Helper methods ---

    def _find_changelog_url(self, pypi_info):
        """Find changelog URL from PyPI package info."""
        project_urls = pypi_info.get('project_urls', {}) or {}
        for key, url in project_urls.items():
            if any(kw in key.lower() for kw in ['changelog', 'changes', 'history', 'release']):
                return url
        # Fallback: homepage
        return pypi_info.get('home_page', '')

    def _version_sort_key(self, version_str):
        """Create a sortable key from a version string."""
        version_str = self._extract_version(version_str) or version_str
        parts = re.split(r'[.\-]', version_str)
        key = []
        for part in parts:
            try:
                key.append(int(part))
            except ValueError:
                key.append(0)
        # Pad to 4 parts
        while len(key) < 4:
            key.append(0)
        return tuple(key)

    def _extract_version(self, tag):
        """Extract version number from a tag like v1.2.3 or release-1.2.3."""
        match = re.search(r'(\d+\.\d+(?:\.\d+)?(?:\.\d+)?)', tag)
        return match.group(1) if match else None
