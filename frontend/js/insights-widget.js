/**
 * Insights Widget JavaScript
 * Displays AI-generated insights on dashboard
 */

let currentInsightsTab = 'alerts';
let insights = [];

/**
 * Initialize insights widget
 */
async function initializeInsightsWidget() {
    // Load insights
    await loadInsights();
    
    // Setup event listeners
    setupInsightsEventListeners();
}

/**
 * Setup event listeners for insights widget
 */
function setupInsightsEventListeners() {
    // Refresh button
    const refreshBtn = document.getElementById('insightsRefreshBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', refreshInsights);
    }
    
    // Tab buttons
    document.querySelectorAll('.insights-tab').forEach(tab => {
        tab.addEventListener('click', () => switchInsightsTab(tab.dataset.tab));
    });
    
    // Resolve buttons
    document.addEventListener('click', (e) => {
        if (e.target.closest('.resolve-insight-btn')) {
            const insightId = e.target.closest('.resolve-insight-btn').dataset.insightId;
            resolveInsight(insightId);
        }
    });
}

/**
 * Load insights from API
 */
async function loadInsights() {
    try {
        showInsightsLoading(true);
        
        insights = await apiRequest('/api/insights/');
        
        displayInsights();
        updateInsightsCounts();
        
        showInsightsLoading(false);
    } catch (error) {
        console.error('Failed to load insights:', error);
        showInsightsError();
    }
}

/**
 * Display insights in widget
 */
function displayInsights() {
    const alertsList = document.getElementById('alertsList');
    const suggestionsList = document.getElementById('suggestionsList');
    const winsList = document.getElementById('winsList');
    
    if (!alertsList || !suggestionsList || !winsList) return;
    
    // Filter insights by type
    const alerts = insights.filter(i => i.insight_type === 'alert');
    const suggestions = insights.filter(i => i.insight_type === 'suggestion');
    const wins = insights.filter(i => i.insight_type === 'win');
    
    // Display each category
    alertsList.innerHTML = alerts.length > 0 
        ? alerts.map(insight => createInsightCard(insight)).join('')
        : '<div class="insights-empty"><p>No alerts! Everything looks good 👍</p></div>';
    
    suggestionsList.innerHTML = suggestions.length > 0
        ? suggestions.map(insight => createInsightCard(insight)).join('')
        : '<div class="insights-empty"><p>No suggestions at the moment</p></div>';
    
    winsList.innerHTML = wins.length > 0
        ? wins.map(insight => createInsightCard(insight)).join('')
        : '<div class="insights-empty"><p>No recent wins to celebrate</p></div>';
}

/**
 * Create insight card HTML
 */
function createInsightCard(insight) {
    const icons = {
        'alert': '⚠️',
        'suggestion': '💡',
        'win': '✅',
        'trend': '📈'
    };
    
    const icon = icons[insight.insight_type] || '📌';
    
    let actionsHtml = '';
    
    // Add action buttons
    if (insight.action_url) {
        actionsHtml += `
            <a href="${insight.action_url}" class="insight-action-btn primary" target="_blank">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                    <polyline points="15 3 21 3 21 9"></polyline>
                    <line x1="10" y1="14" x2="21" y2="3"></line>
                </svg>
                Take Action
            </a>
        `;
    }
    
    actionsHtml += `
        <button class="insight-action-btn resolve-insight-btn" data-insight-id="${insight.id}">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="20 6 9 17 4 12"></polyline>
            </svg>
            Mark Resolved
        </button>
    `;
    
    return `
        <div class="insight-card ${insight.insight_type}">
            <div class="insight-icon">${icon}</div>
            <div class="insight-content-area">
                <div class="insight-header-row">
                    <h4 class="insight-title-text">${escapeHtml(insight.title)}</h4>
                    <span class="insight-priority ${insight.priority}">${insight.priority}</span>
                </div>
                <p class="insight-description">${escapeHtml(insight.description)}</p>
                ${insight.recommendation ? `
                    <div class="insight-recommendation">
                        <strong>💡 Recommendation:</strong> ${escapeHtml(insight.recommendation)}
                    </div>
                ` : ''}
                <div class="insight-actions">
                    ${actionsHtml}
                </div>
            </div>
        </div>
    `;
}

/**
 * Update insight counts in tabs
 */
function updateInsightsCounts() {
    const alerts = insights.filter(i => i.insight_type === 'alert').length;
    const suggestions = insights.filter(i => i.insight_type === 'suggestion').length;
    const wins = insights.filter(i => i.insight_type === 'win').length;
    
    const alertsCount = document.querySelector('[data-tab="alerts"] .insights-tab-count');
    const suggestionsCount = document.querySelector('[data-tab="suggestions"] .insights-tab-count');
    const winsCount = document.querySelector('[data-tab="wins"] .insights-tab-count');
    
    if (alertsCount) alertsCount.textContent = alerts;
    if (suggestionsCount) suggestionsCount.textContent = suggestions;
    if (winsCount) winsCount.textContent = wins;
}

/**
 * Switch insights tab
 */
function switchInsightsTab(tabName) {
    currentInsightsTab = tabName;
    
    // Update active tab
    document.querySelectorAll('.insights-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    document.querySelector(`[data-tab="${tabName}"]`)?.classList.add('active');
    
    // Update active content
    document.querySelectorAll('.insights-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(`${tabName}Content`)?.classList.add('active');
}

/**
 * Refresh insights
 */
async function refreshInsights() {
    const refreshBtn = document.getElementById('insightsRefreshBtn');
    if (refreshBtn) {
        refreshBtn.disabled = true;
        refreshBtn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spinning">
                <polyline points="23 4 23 10 17 10"></polyline>
                <polyline points="1 20 1 14 7 14"></polyline>
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
            </svg>
            Refreshing...
        `;
    }
    
    try {
        // Trigger insight generation
        await apiRequest('/api/insights/generate/', 'POST');
        
        // Wait a bit, then reload
        setTimeout(async () => {
            await loadInsights();
            
            if (refreshBtn) {
                refreshBtn.disabled = false;
                refreshBtn.innerHTML = `
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="23 4 23 10 17 10"></polyline>
                        <polyline points="1 20 1 14 7 14"></polyline>
                        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                    </svg>
                    Refresh
                `;
            }
            
            showToast('Insights refreshed', 'success');
        }, 3000);
        
    } catch (error) {
        console.error('Failed to refresh insights:', error);
        showToast('Failed to refresh insights', 'error');
        
        if (refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="23 4 23 10 17 10"></polyline>
                    <polyline points="1 20 1 14 7 14"></polyline>
                    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                </svg>
                Refresh
            `;
        }
    }
}

/**
 * Resolve insight
 */
async function resolveInsight(insightId) {
    if (!confirm('Mark this insight as resolved?')) return;
    
    try {
        await apiRequest(`/api/insights/${insightId}/resolve/`, 'POST');
        
        // Remove from display
        insights = insights.filter(i => i.id !== parseInt(insightId));
        displayInsights();
        updateInsightsCounts();
        
        showToast('Insight resolved', 'success');
    } catch (error) {
        console.error('Failed to resolve insight:', error);
        showToast('Failed to resolve insight', 'error');
    }
}

/**
 * Show loading state
 */
function showInsightsLoading(show) {
    const widget = document.querySelector('.insights-widget');
    if (!widget) return;
    
    if (show) {
        widget.classList.add('loading');
    } else {
        widget.classList.remove('loading');
    }
}

/**
 * Show error state
 */
function showInsightsError() {
    const alertsList = document.getElementById('alertsList');
    if (alertsList) {
        alertsList.innerHTML = `
            <div class="insights-empty">
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="12" y1="8" x2="12" y2="12"></line>
                    <line x1="12" y1="16" x2="12.01" y2="16"></line>
                </svg>
                <h3>Failed to load insights</h3>
                <p>Please try refreshing</p>
            </div>
        `;
    }
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Show toast notification
 */
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    
    const container = document.getElementById('toastContainer') || document.body;
    container.appendChild(toast);
    
    setTimeout(() => toast.classList.add('show'), 100);
    
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Export functions
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        initializeInsightsWidget,
        loadInsights,
        resolveInsight
    };
}