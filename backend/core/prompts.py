"""
System prompts for Claude AI assistant
"""

def get_system_prompt(user, repositories_context):
    """
    Generate system prompt with user context
    """
    return f"""You are an intelligent GitHub repository assistant helping {user.github_login} manage their repositories.

AVAILABLE DATA:
{repositories_context}

YOUR CAPABILITIES:
1. Search and filter repositories by language, stars, activity, etc.
2. Analyze pull requests, issues, and commits
3. Provide insights about code changes and team activity
4. Compare repositories and identify trends
5. Summarize recent activity and highlight important items
6. Explain code changes in simple terms

RESPONSE GUIDELINES:
- Be concise but informative
- Use markdown formatting for better readability
- Include specific numbers, dates, and statistics when relevant
- Provide actionable insights and recommendations
- When listing items, limit to top 5-10 unless user asks for more
- Always cite specific repository names, PR numbers, issue numbers
- Use emojis sparingly for visual clarity (⭐ for stars, 🔧 for fixes, etc.)

RESPONSE FORMAT:
- Use **bold** for repository names and important terms
- Use `code blocks` for code, filenames, and technical terms
- Use bullet points for lists
- Include links when referencing specific items
- Keep paragraphs short and scannable

Remember: You can only access data for repositories that {user.github_login} owns or has access to. Never make up data or provide information about repositories not in the context."""


def build_repositories_context(user):
    """
    Build context about user's repositories
    """
    from .models import Repository, PullRequest, Issue
    
    repos = Repository.objects.filter(user=user)
    
    context_parts = []
    context_parts.append(f"Total repositories: {repos.count()}")
    
    # Language breakdown
    languages = repos.values_list('language', flat=True).exclude(language__isnull=True)
    language_counts = {}
    for lang in languages:
        language_counts[lang] = language_counts.get(lang, 0) + 1
    
    if language_counts:
        context_parts.append("\nRepositories by language:")
        for lang, count in sorted(language_counts.items(), key=lambda x: x[1], reverse=True):
            context_parts.append(f"- {lang}: {count}")
    
    # Repository list with basic info
    context_parts.append("\nRepository list:")
    for repo in repos[:50]:  # Limit to 50 for context size
        repo_info = f"- **{repo.full_name}**"
        details = []
        if repo.language:
            details.append(f"Language: {repo.language}")
        details.append(f"Stars: {repo.stars_count}")
        details.append(f"Forks: {repo.forks_count}")
        details.append(f"Issues: {repo.open_issues_count}")
        
        pr_count = repo.pull_requests.count()
        issue_count = repo.issues.count()
        if pr_count > 0:
            details.append(f"PRs: {pr_count}")
        if issue_count > 0:
            details.append(f"Issues: {issue_count}")
        
        repo_info += f" ({', '.join(details)})"
        context_parts.append(repo_info)
    
    # Open PRs
    open_prs = PullRequest.objects.filter(
        repository__user=user,
        state='open'
    )
    if open_prs.exists():
        context_parts.append(f"\nOpen Pull Requests: {open_prs.count()}")
        for pr in open_prs[:10]:
            context_parts.append(
                f"- PR #{pr.number} in {pr.repository.full_name}: {pr.title} "
                f"(by {pr.author_login}, opened {pr.created_at.date()})"
            )
    
    # Open Issues
    open_issues = Issue.objects.filter(
        repository__user=user,
        state='open'
    )
    if open_issues.exists():
        context_parts.append(f"\nOpen Issues: {open_issues.count()}")
        for issue in open_issues[:10]:
            context_parts.append(
                f"- Issue #{issue.number} in {issue.repository.full_name}: {issue.title} "
                f"(by {issue.author_login}, opened {issue.created_at.date()})"
            )
    
    return "\n".join(context_parts)


def build_specific_query_context(user, query_lower):
    """
    Build context based on specific query keywords
    """
    from .models import Repository, PullRequest, Issue, Commit, Contributor
    from django.db.models import Q, Count
    
    context = []
    
    # Pull request queries
    if any(word in query_lower for word in ['pull request', 'pr', 'merge']):
        prs = PullRequest.objects.filter(repository__user=user)
        
        if 'open' in query_lower:
            prs = prs.filter(state='open')
            context.append(f"Open PRs: {prs.count()}")
        elif 'closed' in query_lower or 'merged' in query_lower:
            prs = prs.filter(Q(state='closed') | Q(merged=True))
            context.append(f"Closed/Merged PRs: {prs.count()}")
        
        if prs.exists():
            context.append("\nRecent PRs:")
            for pr in prs.order_by('-created_at')[:15]:
                context.append(
                    f"- **{pr.repository.full_name}** PR #{pr.number}: {pr.title}\n"
                    f"  State: {pr.state}, Author: {pr.author_login}, "
                    f"Changes: +{pr.additions}/-{pr.deletions}, "
                    f"Created: {pr.created_at.date()}"
                )
    
    # Issue queries
    if 'issue' in query_lower:
        issues = Issue.objects.filter(repository__user=user)
        
        if 'open' in query_lower:
            issues = issues.filter(state='open')
            context.append(f"Open Issues: {issues.count()}")
        elif 'closed' in query_lower:
            issues = issues.filter(state='closed')
            context.append(f"Closed Issues: {issues.count()}")
        
        if issues.exists():
            context.append("\nRecent Issues:")
            for issue in issues.order_by('-created_at')[:15]:
                labels = ', '.join([label['name'] for label in issue.labels]) if issue.labels else 'None'
                context.append(
                    f"- **{issue.repository.full_name}** Issue #{issue.number}: {issue.title}\n"
                    f"  State: {issue.state}, Author: {issue.author_login}, "
                    f"Labels: {labels}, Created: {issue.created_at.date()}"
                )
    
    # Commit queries
    if 'commit' in query_lower:
        commits = Commit.objects.filter(repository__user=user).order_by('-committed_at')[:20]
        if commits.exists():
            context.append(f"\nRecent Commits: {commits.count()}")
            for commit in commits:
                context.append(
                    f"- **{commit.repository.full_name}** {commit.sha[:7]}: {commit.message[:100]}\n"
                    f"  Author: {commit.author_login or commit.author_name}, "
                    f"Changes: +{commit.additions}/-{commit.deletions}, "
                    f"Date: {commit.committed_at.date()}"
                )
    
    # Contributor queries
    if any(word in query_lower for word in ['contributor', 'author', 'developer', 'team']):
        contributors = Contributor.objects.filter(repository__user=user)
        
        # Top contributors across all repos
        top_contributors = (
            contributors.values('github_login')
            .annotate(total_contributions=Count('id'))
            .order_by('-total_contributions')[:10]
        )
        
        if top_contributors:
            context.append("\nTop Contributors:")
            for contrib in top_contributors:
                context.append(f"- {contrib['github_login']}: {contrib['total_contributions']} contributions")
    
    # Language queries
    if 'language' in query_lower or 'python' in query_lower or 'javascript' in query_lower:
        repos = Repository.objects.filter(user=user)
        
        # Find specific language if mentioned
        languages = ['Python', 'JavaScript', 'TypeScript', 'Java', 'Go', 'Rust', 'C++', 'C#', 'Ruby', 'PHP']
        for lang in languages:
            if lang.lower() in query_lower:
                lang_repos = repos.filter(language__iexact=lang)
                if lang_repos.exists():
                    context.append(f"\n{lang} Repositories ({lang_repos.count()}):")
                    for repo in lang_repos:
                        context.append(
                            f"- **{repo.full_name}**: {repo.description or 'No description'}\n"
                            f"  Stars: {repo.stars_count}, Forks: {repo.forks_count}, "
                            f"Updated: {repo.github_updated_at.date() if repo.github_updated_at else 'N/A'}"
                        )
    
    return "\n".join(context) if context else ""
