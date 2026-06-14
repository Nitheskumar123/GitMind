/**
 * Repository Detail Page JavaScript
 * Handles repository detail view functionality
 */

let currentRepoId = null;
let currentRepo = null;

document.addEventListener('DOMContentLoaded', async () => {
    // Check authentication
    if (!await checkAuth()) {
        window.location.href = '/';
        return;
    }

    // Get repository ID from URL
    const urlParams = new URLSearchParams(window.location.search);
    currentRepoId = urlParams.get('id');

    if (!currentRepoId) {
        showToast('No repository specified', 'error');
        setTimeout(() => window.location.href = '/dashboard/', 2000);
        return;
    }

    // Load user info
    await loadUserInfo();

    // Load repository data
    await loadRepositoryData();

    // Setup event listeners
    setupEventListeners();
});

function setupEventListeners() {
    // Logout
    document.getElementById('logoutBtn').addEventListener('click', handleLogout);

    // Sync repository
    document.getElementById('syncRepoBtn').addEventListener('click', syncRepository);

    // Tab switching
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // Pull request filters
    document.querySelectorAll('#pulls .filter-btn').forEach(btn => {
        btn.addEventListener('click', (e) => filterPullRequests(btn.dataset.state, e));
    });

    // Issue filters
    document.querySelectorAll('#issues .filter-btn').forEach(btn => {
        btn.addEventListener('click', (e) => filterIssues(btn.dataset.state, e));
    });
}

async function loadUserInfo() {
    try {
        const user = await apiRequest('/api/user/me/');
        document.getElementById('userName').textContent = user.github_login || user.username;
        document.getElementById('userAvatar').src = user.github_avatar_url || 'https://via.placeholder.com/40';
    } catch (error) {
        showToast('Failed to load user info', 'error');
    }
}

async function loadRepositoryData() {
    try {
        showLoading('Loading repository...');

        // Get repository details
        currentRepo = await apiRequest(`/api/repositories/${currentRepoId}/`);

        // Display repository info
        displayRepositoryHeader(currentRepo);

        // Load tab data
        await loadOverviewData();
        await loadPullRequests();
        await loadIssues();

        // Phase 5: Initialize expertise heatmap
        initializePhase5Widgets();

        hideLoading();
    } catch (error) {
        hideLoading();
        showToast('Failed to load repository', 'error');
        console.error(error);
    }
}

function displayRepositoryHeader(repo) {
    document.getElementById('repoFullName').textContent = repo.full_name;
    document.getElementById('repoDescription').textContent = repo.description || 'No description provided';
    document.getElementById('githubLink').href = repo.html_url;

    // Badge
    const badge = document.getElementById('repoBadge');
    badge.textContent = repo.is_private ? 'Private' : 'Public';
    badge.className = `repo-badge ${repo.is_private ? 'private' : 'public'}`;

    // Stats
    document.getElementById('repoStars').textContent = repo.stars_count;
    document.getElementById('repoForks').textContent = repo.forks_count;
    document.getElementById('repoIssues').textContent = repo.open_issues_count;
    document.getElementById('repoLanguage').textContent = repo.language || 'Unknown';

    // Updated time
    if (repo.github_updated_at) {
        const updated = formatDate(repo.github_updated_at);
        document.getElementById('repoUpdated').textContent = updated;
    }

    // Counts
    document.getElementById('prCount').textContent = repo.pull_requests_count || 0;
    document.getElementById('issueCount').textContent = repo.issues_count || 0;
}

async function loadOverviewData() {
    // Load commits
    loadCommits();

    // Load contributors
    loadContributors();

    // Load language stats
    loadLanguageStats();
}

async function loadCommits() {
    try {
        const commits = await apiRequest(`/api/repositories/${currentRepoId}/commits/?limit=10`);
        displayCommits(commits);
    } catch (error) {
        document.getElementById('commitsList').innerHTML = '<div class="empty-state">No commits found</div>';
    }
}

function displayCommits(commits) {
    const container = document.getElementById('commitsList');

    if (commits.length === 0) {
        container.innerHTML = '<div class="empty-state">No commits found</div>';
        return;
    }

    container.innerHTML = commits.map(commit => `
        <div class="commit-item">
            <img src="${commit.author_avatar_url || 'https://via.placeholder.com/32'}" 
                 alt="${commit.author_name}" 
                 class="commit-avatar">
            <div class="commit-info">
                <div class="commit-message">${escapeHtml(commit.message_short)}</div>
                <div class="commit-meta">
                    ${commit.author_name}
                    <span class="commit-sha">${commit.sha.substring(0, 7)}</span>
                    • ${formatDate(commit.committed_at)}
                    • <span style="color: #10b981">+${commit.additions}</span>
                    <span style="color: #ef4444">-${commit.deletions}</span>
                </div>
            </div>
        </div>
    `).join('');
}

async function loadContributors() {
    try {
        const contributors = await apiRequest(`/api/repositories/${currentRepoId}/contributors/`);
        displayContributors(contributors);
    } catch (error) {
        document.getElementById('contributorsList').innerHTML = '<div class="empty-state">No contributors found</div>';
    }
}

function displayContributors(contributors) {
    const container = document.getElementById('contributorsList');

    if (contributors.length === 0) {
        container.innerHTML = '<div class="empty-state">No contributors found</div>';
        return;
    }

    container.innerHTML = contributors.map(contributor => `
        <div class="contributor-card">
            <img src="${contributor.avatar_url}" 
                 alt="${contributor.github_login}" 
                 class="contributor-avatar">
            <div class="contributor-info">
                <div class="contributor-name">${contributor.github_login}</div>
                <div class="contributor-stats">${contributor.contributions} contributions</div>
            </div>
        </div>
    `).join('');
}

async function loadLanguageStats() {
    try {
        const languages = await apiRequest(`/api/repositories/${currentRepoId}/languages/`);

        if (Object.keys(languages).length > 0) {
            createLanguageChart('languageChart', languages);
        } else {
            document.querySelector('.chart-container').innerHTML = '<div class="empty-state">No language data available</div>';
        }
    } catch (error) {
        document.querySelector('.chart-container').innerHTML = '<div class="empty-state">Failed to load language data</div>';
    }
}

async function loadPullRequests(state = 'all') {
    try {
        const url = state === 'all'
            ? `/api/repositories/${currentRepoId}/pulls/`
            : `/api/repositories/${currentRepoId}/pulls/?state=${state}`;

        const pullRequests = await apiRequest(url);
        displayPullRequests(pullRequests);
    } catch (error) {
        document.getElementById('pullRequestsList').innerHTML = '<div class="empty-state">No pull requests found</div>';
    }
}


async function loadIssues(state = 'all') {
    try {
        const url = state === 'all'
            ? `/api/repositories/${currentRepoId}/issues/`
            : `/api/repositories/${currentRepoId}/issues/?state=${state}`;

        const issues = await apiRequest(url);
        displayIssues(issues);
    } catch (error) {
        document.getElementById('issuesList').innerHTML = '<div class="empty-state">No issues found</div>';
    }
}

function displayIssues(issues) {
    const container = document.getElementById('issuesList');

    if (issues.length === 0) {
        container.innerHTML = '<div class="empty-state">No issues found</div>';
        return;
    }

    container.innerHTML = issues.map(issue => `
        <div class="item-card">
            <div class="item-icon ${issue.state}">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"></circle>
                    ${issue.state === 'open' ? '<line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line>' : '<polyline points="9 11 12 14 22 4"></polyline><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path>'}
                </svg>
            </div>
            <div class="item-content">
                <div class="item-header">
                    <span class="item-number">#${issue.number}</span>
                    <span class="item-title">${escapeHtml(issue.title)}</span>
                </div>
                ${issue.labels.length > 0 ? `
                    <div class="item-labels">
                        ${issue.labels.map(label => `
                            <span class="label-tag" style="background-color: #${label.color}">
                                ${label.name}
                            </span>
                        `).join('')}
                    </div>
                ` : ''}
                <div class="item-meta">
                    <div class="item-author">
                        <img src="${issue.author_avatar_url}" alt="${issue.author_login}" class="author-avatar">
                        ${issue.author_login}
                    </div>
                    <span>opened ${formatDate(issue.created_at)}</span>
                    <span class="stat-badge">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                        </svg>
                        ${issue.comments_count}
                    </span>
                </div>
            </div>
        </div>
    `).join('');
}

async function syncRepository() {
    try {
        showLoading('Syncing repository data...');
        await apiRequest(`/api/repositories/${currentRepoId}/sync/`, 'POST');
        showToast('Sync started! Data will be updated in background', 'success');

        // Reload data after a few seconds
        setTimeout(async () => {
            await loadRepositoryData();
            hideLoading();
        }, 3000);
    } catch (error) {
        hideLoading();
        showToast('Failed to sync repository', 'error');
    }
}

function switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(tabName).classList.add('active');
}

function filterPullRequests(state, event) {
    // Update filter buttons
    document.querySelectorAll('#pulls .filter-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.currentTarget.classList.add('active'); // Use currentTarget

    // Reload PRs with filter
    loadPullRequests(state);
}

function filterIssues(state, event) {
    // Update filter buttons
    document.querySelectorAll('#issues .filter-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.currentTarget.classList.add('active'); // Use currentTarget

    // Reload issues with filter
    loadIssues(state);
}


function formatDate(dateString) {
    if (!dateString) return 'N/A';

    const date = new Date(dateString);
    const now = new Date();
    const diffTime = Math.abs(now - date);
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

    if (diffDays < 1) return 'today';
    if (diffDays === 1) return 'yesterday';
    if (diffDays < 7) return `${diffDays} days ago`;
    if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
    if (diffDays < 365) return `${Math.floor(diffDays / 30)} months ago`;
    return `${Math.floor(diffDays / 365)} years ago`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showLoading(text = 'Loading...') {
    document.getElementById('loadingText').textContent = text;
    document.getElementById('loadingOverlay').classList.remove('hidden');
}

function hideLoading() {
    document.getElementById('loadingOverlay').classList.add('hidden');
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    const container = document.getElementById('toastContainer');
    container.appendChild(toast);

    setTimeout(() => toast.classList.add('show'), 100);

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function displayPullRequests(pullRequests) {
    const container = document.getElementById('pullRequestsList');

    if (pullRequests.length === 0) {
        container.innerHTML = '<div class="empty-state">No pull requests found</div>';
        return;
    }

    container.innerHTML = pullRequests.map(pr => `
        <div class="item-card" data-pr-number="${pr.number}">
            <div class="item-icon ${pr.merged ? 'merged' : pr.state}">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    ${pr.merged
            ? '<circle cx="18" cy="18" r="3"></circle><circle cx="6" cy="6" r="3"></circle><path d="M13 6h3a2 2 0 0 1 2 2v7"></path><line x1="6" y1="9" x2="6" y2="21"></line>'
            : '<circle cx="18" cy="18" r="3"></circle><circle cx="6" cy="6" r="3"></circle><path d="M18 6V5"></path><path d="M18 11v-1"></path><path d="M6 9v12"></path>'}
                </svg>
            </div>
            <div class="item-content">
                <div class="item-header">
                    <span class="item-number">#${pr.number}</span>
                    <span class="item-title">${escapeHtml(pr.title)}</span>
                </div>
                <div class="item-meta">
                    <div class="item-author">
                        <img src="${pr.author_avatar_url || 'https://via.placeholder.com/20'}" 
                             alt="${pr.author_login}" class="author-avatar">
                        ${pr.author_login}
                    </div>
                    <span>opened ${formatDate(pr.created_at)}</span>
                    <div class="item-stats">
                        <span class="stat-badge">💬 ${pr.comments_count}</span>
                        <span style="color: #10b981">+${pr.additions}</span>
                        <span style="color: #ef4444">-${pr.deletions}</span>
                    </div>
                </div>
                <div class="analysis-indicator-slot"></div>
            </div>
        </div>
    `).join('');

    setTimeout(() => {
        if (typeof initializePRIndicators === 'function') {
            initializePRIndicators();
        }
    }, 300);
}


// =============================================================================
// PHASE 5: Widget Initialization
// =============================================================================

function initializePhase5Widgets() {
    if (!currentRepoId) return;

    // Initialize expertise heatmap in the Expertise tab
    const expertiseContainer = document.getElementById('expertiseContainer');
    if (expertiseContainer && typeof ExpertiseHeatmap !== 'undefined') {
        expertiseMap = new ExpertiseHeatmap(currentRepoId);
        expertiseMap.render(expertiseContainer);
    }

    // Add click listeners to PR items for Phase 5 detail widgets
    const pullsList = document.getElementById('pullRequestsList');
    if (pullsList) {
        pullsList.addEventListener('click', (e) => {
            const prItem = e.target.closest('.item-card[data-pr-number]');
            if (!prItem) return;

            const prNumber = parseInt(prItem.dataset.prNumber);
            if (isNaN(prNumber)) return;

            showPRToolsPanel(prNumber, prItem);
        });
    }
}

function showPRToolsPanel(prNumber, prItem) {
    const existing = document.querySelector('.pr-tools-panel');
    if (existing) {
        if (existing.dataset.prNumber === String(prNumber)) {
            existing.remove();
            return;
        }
        existing.remove();
    }

    const panel = document.createElement('div');
    panel.className = 'pr-tools-panel';
    panel.dataset.prNumber = prNumber;
    panel.innerHTML = `
        <div id="pr-desc-container-${prNumber}"></div>
        <div id="pr-reviewer-container-${prNumber}"></div>
    `;

    prItem.insertAdjacentElement('afterend', panel);

    if (typeof PRDescriptionGenerator !== 'undefined') {
        prDescGen = new PRDescriptionGenerator(currentRepoId);
        prDescGen.render(
            document.getElementById(`pr-desc-container-${prNumber}`),
            prNumber
        );
    }

    if (typeof ReviewerRecommender !== 'undefined') {
        reviewerRec = new ReviewerRecommender(currentRepoId);
        reviewerRec.render(
            document.getElementById(`pr-reviewer-container-${prNumber}`),
            prNumber
        );
    }
}