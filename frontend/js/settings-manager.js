/**
 * Settings Manager
 * Handles all settings page functionality
 */

let currentRepoId = null;
let globalPreferences = null;
let repositories = [];

document.addEventListener('DOMContentLoaded', async () => {
    // Check authentication
    if (!await checkAuth()) {
        window.location.href = '/';
        return;
    }

    // Load user info
    await loadUserInfo();

    // Setup event listeners
    setupEventListeners();

    // Load initial data
    await loadGlobalPreferences();
    await loadRepositories();

    // Setup logout
    document.getElementById('logoutBtn').addEventListener('click', handleLogout);
});

function setupEventListeners() {
    // Navigation
    document.querySelectorAll('.settings-nav-item').forEach(item => {
        item.addEventListener('click', () => switchSection(item.dataset.section));
    });

    // Global settings save
    document.getElementById('saveGlobalSettings').addEventListener('click', saveGlobalSettings);
    document.getElementById('resetGlobalSettings').addEventListener('click', resetGlobalSettings);

    // Repository selection
    document.getElementById('repoSelect').addEventListener('change', handleRepoSelection);

    // Repository settings
    document.getElementById('repoOverrideGlobal').addEventListener('change', handleOverrideToggle);
    document.getElementById('saveRepoSettings').addEventListener('click', saveRepoSettings);

    // Webhook actions
    document.getElementById('setupWebhookBtn')?.addEventListener('click', setupWebhook);
    document.getElementById('deleteWebhookBtn')?.addEventListener('click', deleteWebhook);

    // Slack webhook toggle
    document.getElementById('slackNotifications').addEventListener('change', handleSlackToggle);

    // Refresh buttons
    document.getElementById('refreshLogsBtn')?.addEventListener('click', loadActivityLogs);
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

function switchSection(sectionId) {
    // Update navigation
    document.querySelectorAll('.settings-nav-item').forEach(item => {
        item.classList.remove('active');
    });
    document.querySelector(`[data-section="${sectionId}"]`)?.classList.add('active');

    // Update content
    document.querySelectorAll('.settings-section').forEach(section => {
        section.classList.remove('active');
    });
    document.getElementById(sectionId)?.classList.add('active');

    // Load section data
    if (sectionId === 'cost') {
        loadCostSummary();
    } else if (sectionId === 'activity') {
        loadActivityLogs();
    }
}

// ============================================
// GLOBAL PREFERENCES
// ============================================

async function loadGlobalPreferences() {
    try {
        showLoading('Loading preferences...');

        globalPreferences = await apiRequest('/api/user/preferences/');

        // Populate form fields
        document.getElementById('autoAnalyzePrs').checked = globalPreferences.auto_analyze_prs;
        document.getElementById('skipDraftPrs').checked = globalPreferences.skip_draft_prs;
        document.getElementById('minLinesForAnalysis').value = globalPreferences.min_lines_for_analysis;
        document.getElementById('autoPostComments').value = globalPreferences.auto_post_comments.toString();

        document.getElementById('autoUpdateDocs').checked = globalPreferences.auto_update_docs;
        document.getElementById('docsUpdateFrequency').value = globalPreferences.docs_update_frequency;
        document.getElementById('docsMinChanges').value = globalPreferences.docs_min_changes;

        document.getElementById('autoGenerateInsights').checked = globalPreferences.auto_generate_insights;
        document.getElementById('insightsFrequency').value = globalPreferences.insights_frequency;

        document.getElementById('emailCriticalIssues').checked = globalPreferences.email_critical_issues;
        document.getElementById('emailDailyDigest').checked = globalPreferences.email_daily_digest;
        document.getElementById('slackNotifications').checked = globalPreferences.slack_notifications;
        document.getElementById('slackWebhookUrl').value = globalPreferences.slack_webhook_url || '';

        document.getElementById('dailyTokenLimit').value = globalPreferences.daily_token_limit;
        document.getElementById('pauseOnLimit').checked = globalPreferences.pause_on_limit;

        // Show/hide Slack webhook input
        handleSlackToggle();

        hideLoading();
    } catch (error) {
        console.error('Failed to load preferences:', error);
        showToast('Failed to load preferences', 'error');
        hideLoading();
    }
}

async function saveGlobalSettings() {
    try {
        showLoading('Saving settings...');

        const data = {
            auto_analyze_prs: document.getElementById('autoAnalyzePrs').checked,
            skip_draft_prs: document.getElementById('skipDraftPrs').checked,
            min_lines_for_analysis: parseInt(document.getElementById('minLinesForAnalysis').value),
            auto_post_comments: document.getElementById('autoPostComments').value === 'true',

            auto_update_docs: document.getElementById('autoUpdateDocs').checked,
            docs_update_frequency: document.getElementById('docsUpdateFrequency').value,
            docs_min_changes: parseInt(document.getElementById('docsMinChanges').value),

            auto_generate_insights: document.getElementById('autoGenerateInsights').checked,
            insights_frequency: document.getElementById('insightsFrequency').value,

            email_critical_issues: document.getElementById('emailCriticalIssues').checked,
            email_daily_digest: document.getElementById('emailDailyDigest').checked,
            slack_notifications: document.getElementById('slackNotifications').checked,
            slack_webhook_url: document.getElementById('slackWebhookUrl').value,

            daily_token_limit: parseInt(document.getElementById('dailyTokenLimit').value),
            pause_on_limit: document.getElementById('pauseOnLimit').checked
        };

        await apiRequest('/api/user/preferences/', 'PUT', data);

        hideLoading();
        showToast('Settings saved successfully!', 'success');

        // Reload preferences
        await loadGlobalPreferences();

    } catch (error) {
        console.error('Failed to save settings:', error);
        hideLoading();
        showToast('Failed to save settings', 'error');
    }
}

async function resetGlobalSettings() {
    if (!confirm('Reset all settings to default values?')) return;

    // Set defaults
    document.getElementById('autoAnalyzePrs').checked = false;
    document.getElementById('skipDraftPrs').checked = true;
    document.getElementById('minLinesForAnalysis').value = 50;
    document.getElementById('autoPostComments').value = 'false';

    document.getElementById('autoUpdateDocs').checked = false;
    document.getElementById('docsUpdateFrequency').value = 'weekly';
    document.getElementById('docsMinChanges').value = 100;

    document.getElementById('autoGenerateInsights').checked = true;
    document.getElementById('insightsFrequency').value = 'daily';

    document.getElementById('emailCriticalIssues').checked = true;
    document.getElementById('emailDailyDigest').checked = false;
    document.getElementById('slackNotifications').checked = false;
    document.getElementById('slackWebhookUrl').value = '';

    document.getElementById('dailyTokenLimit').value = 100000;
    document.getElementById('pauseOnLimit').checked = true;

    await saveGlobalSettings();
}

function handleSlackToggle() {
    const slackEnabled = document.getElementById('slackNotifications').checked;
    document.getElementById('slackWebhookContainer').style.display = slackEnabled ? 'flex' : 'none';
}

// ============================================
// REPOSITORY SETTINGS
// ============================================

async function loadRepositories() {
    try {
        repositories = await apiRequest('/api/repositories/');

        const repoSelect = document.getElementById('repoSelect');
        repoSelect.innerHTML = '<option value="">Select a repository...</option>';

        repositories.forEach(repo => {
            const option = document.createElement('option');
            option.value = repo.id;
            option.textContent = repo.full_name;
            repoSelect.appendChild(option);
        });

    } catch (error) {
        console.error('Failed to load repositories:', error);
        showToast('Failed to load repositories', 'error');
    }
}

async function handleRepoSelection(event) {
    currentRepoId = event.target.value;

    if (!currentRepoId) {
        document.getElementById('repoSettingsContent').style.display = 'none';
        return;
    }

    document.getElementById('repoSettingsContent').style.display = 'block';

    // Update repo name
    const repo = repositories.find(r => r.id == currentRepoId);
    document.getElementById('selectedRepoName').textContent = repo.full_name;

    // Load settings
    await loadRepoSettings();
    await loadWebhookStatus();
}

async function loadRepoSettings() {
    try {
        showLoading('Loading repository settings...');

        const settings = await apiRequest(`/api/repositories/${currentRepoId}/settings/`);

        // Populate form
        document.getElementById('repoOverrideGlobal').checked = settings.override_global;
        document.getElementById('repoEnablePrAnalysis').checked = settings.enable_pr_analysis;
        document.getElementById('repoAutoAnalyzePrs').checked = settings.auto_analyze_prs ?? globalPreferences.auto_analyze_prs;
        document.getElementById('repoEnableDocumentation').checked = settings.enable_documentation;
        document.getElementById('repoEnableInsights').checked = settings.enable_insights;
        document.getElementById('repoEnableWebhooks').checked = settings.enable_webhooks;

        // Show/hide custom settings
        handleOverrideToggle();

        hideLoading();
    } catch (error) {
        console.error('Failed to load repo settings:', error);
        hideLoading();
        showToast('Failed to load repository settings', 'error');
    }
}

async function saveRepoSettings() {
    try {
        showLoading('Saving repository settings...');

        const data = {
            override_global: document.getElementById('repoOverrideGlobal').checked,
            enable_pr_analysis: document.getElementById('repoEnablePrAnalysis').checked,
            auto_analyze_prs: document.getElementById('repoAutoAnalyzePrs').checked,
            enable_documentation: document.getElementById('repoEnableDocumentation').checked,
            enable_insights: document.getElementById('repoEnableInsights').checked,
            enable_webhooks: document.getElementById('repoEnableWebhooks').checked
        };

        await apiRequest(`/api/repositories/${currentRepoId}/settings/`, 'PUT', data);

        hideLoading();
        showToast('Repository settings saved!', 'success');

        // Reload settings
        await loadRepoSettings();

    } catch (error) {
        console.error('Failed to save repo settings:', error);
        hideLoading();
        showToast('Failed to save repository settings', 'error');
    }
}

function handleOverrideToggle() {
    const override = document.getElementById('repoOverrideGlobal').checked;
    document.getElementById('repoCustomSettings').style.display = override ? 'block' : 'none';
}

// ============================================
// WEBHOOK MANAGEMENT
// ============================================
// ============================================
// WEBHOOK MANAGEMENT (FIXED VERSION)
// ============================================
async function loadWebhookStatus() {
    try {
        const response = await apiRequest(`/api/repositories/${currentRepoId}/webhook/status/`);
        console.log("Detailed Webhook Data:", response); // Logs the exact JSON to your F12 console

        const statusBadge = document.getElementById('webhookStatusBadge');
        const statusText = document.getElementById('webhookStatusText');
        const setupBtn = document.getElementById('setupWebhookBtn');
        const deleteBtn = document.getElementById('deleteWebhookBtn');

        // Robust checking for Active status (handles both flat and nested JSON)
        const isConfigured = response.is_configured || response.has_webhook;
        const isActive = response.is_active || (response.webhook && response.webhook.is_active);
        const webhookId = response.github_webhook_id || (response.webhook && response.webhook.github_webhook_id);

        if (isConfigured && isActive) {
            statusBadge.className = 'status-badge active';
            statusBadge.textContent = 'Active';
            statusText.textContent = `✅ Connected to GitHub (ID: ${webhookId || 'Live'})`;
            setupBtn.style.display = 'none';
            deleteBtn.style.display = 'inline-flex';
        } else if (isConfigured && !isActive) {
            statusBadge.className = 'status-badge error';
            statusBadge.textContent = 'Inactive';
            statusText.textContent = 'Webhook setup incomplete or missing payload.';
            setupBtn.style.display = 'inline-flex';
            setupBtn.textContent = 'Fix Connection';
            deleteBtn.style.display = 'inline-flex';
        } else {
            statusBadge.className = 'status-badge inactive';
            statusBadge.textContent = 'Not Configured';
            statusText.textContent = 'No webhook registered for this repository.';
            setupBtn.style.display = 'inline-flex';
            setupBtn.textContent = 'Setup Webhook';
            deleteBtn.style.display = 'none';
        }
    } catch (error) {
        console.error('Failed to fetch webhook status:', error);
    }
}
async function setupWebhook() {
    try {
        showLoading('Communicating with GitHub...');
        const result = await apiRequest(`/api/repositories/${currentRepoId}/webhook/setup/`, 'POST');

        hideLoading();
        showToast('Syncing with GitHub API...', 'success');

        // Poll for status change: once at 2s and once at 5s
        setTimeout(() => loadWebhookStatus(), 2000);
        setTimeout(() => {
            loadWebhookStatus();
            showToast('Webhook status updated!', 'success');
        }, 5000);

    } catch (error) {
        hideLoading();
        showToast('Setup failed. Check Celery logs.', 'error');
    }
}

async function deleteWebhook() {
    if (!confirm('Delete webhook for this repository?')) return;

    try {
        showLoading('Deleting webhook...');

        await apiRequest(`/api/repositories/${currentRepoId}/webhook/delete/`, 'DELETE');

        hideLoading();
        showToast('Webhook deleted', 'success');

        await loadWebhookStatus();

    } catch (error) {
        console.error('Failed to delete webhook:', error);
        hideLoading();
        showToast('Failed to delete webhook', 'error');
    }
}

// ============================================
// COST TRACKING
// ============================================

async function loadCostSummary() {
    try {
        const summary = await apiRequest('/api/cost/summary/');

        // Update cards
        document.getElementById('costToday').textContent = summary.today.tokens.toLocaleString();
        document.getElementById('costTodayAmount').textContent = `$${summary.today.cost.toFixed(4)}`;

        document.getElementById('costWeek').textContent = summary.this_week.tokens.toLocaleString();
        document.getElementById('costWeekAmount').textContent = `$${summary.this_week.cost.toFixed(4)}`;

        document.getElementById('costMonth').textContent = summary.this_month.tokens.toLocaleString();
        document.getElementById('costMonthAmount').textContent = `$${summary.this_month.cost.toFixed(2)}`;

        // Display daily breakdown
        const breakdownContainer = document.getElementById('dailyBreakdown');

        if (summary.daily_breakdown.length === 0) {
            breakdownContainer.innerHTML = '<p class="empty-state">No usage data yet</p>';
            return;
        }

        breakdownContainer.innerHTML = summary.daily_breakdown.map(day => `
            <div class="breakdown-item">
                <div class="breakdown-date">${new Date(day.date).toLocaleDateString()}</div>
                <div class="breakdown-stats">
                    <div class="breakdown-stat">
                        <span class="breakdown-stat-label">Tokens</span>
                        <span class="breakdown-stat-value">${day.tokens_used.toLocaleString()}</span>
                    </div>
                    <div class="breakdown-stat">
                        <span class="breakdown-stat-label">API Calls</span>
                        <span class="breakdown-stat-value">${day.api_calls}</span>
                    </div>
                    <div class="breakdown-stat">
                        <span class="breakdown-stat-label">Cost</span>
                        <span class="breakdown-stat-value">$${parseFloat(day.estimated_cost).toFixed(4)}</span>
                    </div>
                </div>
            </div>
        `).join('');

    } catch (error) {
        console.error('Failed to load cost summary:', error);
        showToast('Failed to load cost data', 'error');
    }
}

// ============================================
// ACTIVITY LOGS
// ============================================

async function loadActivityLogs() {
    try {
        const logs = await apiRequest('/api/automation/logs/');

        const container = document.getElementById('activityLogsList');

        if (logs.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
                        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline>
                    </svg>
                    <h3>No Activity Yet</h3>
                    <p>Automated actions will appear here</p>
                </div>
            `;
            return;
        }

        container.innerHTML = logs.map(log => {
            const icons = {
                'pr_analysis': '🤖',
                'insight_generation': '💡',
                'doc_update': '📚',
                'webhook_event': '🔗',
                'scheduled_task': '⏰'
            };

            return `
                <div class="activity-log-item ${log.status}">
                    <div class="activity-log-icon">${icons[log.action_type] || '📋'}</div>
                    <div class="activity-log-content">
                        <div class="activity-log-header">
                            <span class="activity-log-title">${log.description}</span>
                            <span class="activity-log-status ${log.status}">${log.status}</span>
                        </div>
                        ${log.result_summary ? `<p class="activity-log-description">${log.result_summary}</p>` : ''}
                        ${log.error_message ? `<p class="activity-log-description" style="color: var(--danger);">${log.error_message}</p>` : ''}
                        <div class="activity-log-meta">
                            <span>⏱️ ${log.duration_seconds ? log.duration_seconds.toFixed(2) + 's' : 'N/A'}</span>
                            <span>🎫 ${log.tokens_used.toLocaleString()} tokens</span>
                            <span>🔧 ${log.trigger}</span>
                            <span>📅 ${new Date(log.created_at).toLocaleString()}</span>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

    } catch (error) {
        console.error('Failed to load activity logs:', error);
        showToast('Failed to load activity logs', 'error');
    }
}

// ============================================
// UTILITY FUNCTIONS
// ============================================

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