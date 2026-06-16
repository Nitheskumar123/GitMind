/**
 * Cognitive Debt Dashboard JavaScript
 * Phase 8 — Heat map of codebase comprehension
 *
 * Fetches data from:
 *   GET /api/repositories/<id>/debt/           (all file scores)
 *   GET /api/repositories/<id>/debt/summary/   (dashboard summary)
 *   POST /api/repositories/<id>/debt/analyse/  (trigger analysis)
 */

(function () {
    'use strict';

    // ---- State ----
    let repoId = null;
    let allFiles = [];
    let summary = {};
    let currentFilter = 'all';

    // ---- Init ----
    document.addEventListener('DOMContentLoaded', init);

    function init() {
        repoId = new URLSearchParams(window.location.search).get('id');
        if (!repoId) {
            showError('No repository ID provided. Go back to the dashboard.');
            return;
        }

        bindEvents();
        loadData();
    }

    function bindEvents() {
        // Filter buttons
        document.querySelectorAll('.debt-filter-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                currentFilter = btn.dataset.filter;
                document.querySelectorAll('.debt-filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                renderFileList();
            });
        });

        // Analyze button
        const analyzeBtn = document.getElementById('analyzeBtn');
        if (analyzeBtn) {
            analyzeBtn.addEventListener('click', triggerAnalysis);
        }
    }

    // ---- Data Loading ----
    async function loadData() {
        showLoading();
        try {
            const [summaryData, filesData] = await Promise.all([
                apiRequest(`/api/repositories/${repoId}/debt/summary/`),
                apiRequest(`/api/repositories/${repoId}/debt/`),
            ]);

            summary = summaryData;
            allFiles = filesData;

            renderSummary();
            renderAlerts();
            renderFileList();
            updateFilterCounts();
            hideLoading();
        } catch (err) {
            console.error('Failed to load cognitive debt data:', err);
            hideLoading();
            renderEmptyState();
        }
    }

    // ---- Render Summary Cards ----
    function renderSummary() {
        const cards = document.getElementById('summaryCards');
        if (!cards) return;

        const score = summary.overall_score || 0;
        const red = summary.red_files || 0;
        const amber = summary.amber_files || 0;
        const green = summary.green_files || 0;

        cards.innerHTML = `
            <div class="debt-summary-card critical">
                <div class="debt-card-icon critical">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                        <line x1="12" y1="9" x2="12" y2="13"></line>
                        <line x1="12" y1="17" x2="12.01" y2="17"></line>
                    </svg>
                </div>
                <div class="debt-card-value critical">${red}</div>
                <div class="debt-card-label">Critical — Nobody Understands</div>
            </div>

            <div class="debt-summary-card warning">
                <div class="debt-card-icon warning">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="12" y1="8" x2="12" y2="12"></line>
                        <line x1="12" y1="16" x2="12.01" y2="16"></line>
                    </svg>
                </div>
                <div class="debt-card-value warning">${amber}</div>
                <div class="debt-card-label">At-Risk — Limited Understanding</div>
            </div>

            <div class="debt-summary-card healthy">
                <div class="debt-card-icon healthy">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                        <polyline points="22 4 12 14.01 9 11.01"></polyline>
                    </svg>
                </div>
                <div class="debt-card-value healthy">${green}</div>
                <div class="debt-card-label">Healthy — Team Knows These</div>
            </div>

            <div class="debt-summary-card score">
                <div class="score-gauge" id="scoreGauge">
                    <svg width="48" height="48" viewBox="0 0 48 48">
                        <circle class="score-gauge-track" cx="24" cy="24" r="18" />
                        <circle class="score-gauge-fill" id="scoreGaugeFill" cx="24" cy="24" r="18"
                            stroke-dasharray="113.1" stroke-dashoffset="113.1" />
                    </svg>
                    <div class="score-gauge-text">${score}%</div>
                </div>
                <div class="debt-card-label">Overall Comprehension Score</div>
            </div>
        `;

        // Animate gauge after DOM insert
        requestAnimationFrame(() => updateScoreGauge(score));

        // Last analyzed
        const lastEl = document.getElementById('lastAnalyzed');
        if (lastEl && summary.last_analyzed_at) {
            lastEl.textContent = 'Last analyzed ' + timeAgo(summary.last_analyzed_at);
        } else if (lastEl) {
            lastEl.textContent = 'Not yet analyzed';
        }
    }

    function updateScoreGauge(score) {
        const gauge = document.getElementById('scoreGaugeFill');
        if (!gauge) return;
        const circumference = 2 * Math.PI * 18;  // r=18
        const offset = circumference - (score / 100) * circumference;
        gauge.style.strokeDasharray = circumference;
        gauge.style.strokeDashoffset = offset;

        // Color based on score
        if (score >= 70) gauge.style.stroke = '#10b981';
        else if (score >= 35) gauge.style.stroke = '#f59e0b';
        else gauge.style.stroke = '#ef4444';
    }

    // ---- Render Alerts Panel ----
    function renderAlerts() {
        const panel = document.getElementById('alertsPanel');
        if (!panel) return;

        const alerts = summary.critical_alerts || [];
        if (alerts.length === 0) {
            panel.style.display = 'none';
            return;
        }

        panel.style.display = 'block';
        const container = document.getElementById('alertsList');
        if (!container) return;

        container.innerHTML = alerts.map(alert => `
            <div class="debt-alert-item">
                <div>
                    <span class="debt-alert-file">${escapeHtml(alert.file_path)}</span>
                </div>
                <div class="debt-alert-meta">
                    <span>Score: ${alert.score}/100</span>
                    <span>${alert.ai_pct}% AI-written</span>
                    ${alert.suggested_reviewer
                        ? `<span class="debt-alert-action">Assign to @${escapeHtml(alert.suggested_reviewer)}</span>`
                        : '<span class="debt-alert-action">Needs reviewer</span>'
                    }
                </div>
            </div>
        `).join('');
    }

    // ---- Render File List ----
    function renderFileList() {
        const container = document.getElementById('fileListContainer');
        if (!container) return;

        let filtered = allFiles;
        if (currentFilter !== 'all') {
            filtered = allFiles.filter(f => f.risk_level === currentFilter);
        }

        if (filtered.length === 0) {
            if (allFiles.length === 0) {
                renderEmptyState();
            } else {
                container.innerHTML = `
                    <div class="debt-empty-state" style="padding: 2rem;">
                        <p>No files matching the "${currentFilter}" filter.</p>
                    </div>`;
            }
            return;
        }

        container.innerHTML = `
            <div class="debt-list-header">
                <span></span>
                <span>File</span>
                <span style="text-align:center;">Score</span>
                <span style="text-align:center;">AI %</span>
                <span style="text-align:center;">Human Edits</span>
                <span style="text-align:center;">Devs</span>
                <span>Reviewer</span>
            </div>
            <div class="debt-file-list">
                ${filtered.map((f, i) => renderFileRow(f, i)).join('')}
            </div>
        `;
    }

    function renderFileRow(file, index) {
        const risk = file.risk_level;
        const score = file.comprehension_score;
        const dir = file.file_path.includes('/') 
            ? file.file_path.substring(0, file.file_path.lastIndexOf('/') + 1) 
            : '';
        const name = file.file_path.includes('/')
            ? file.file_path.substring(file.file_path.lastIndexOf('/') + 1)
            : file.file_path;

        const initials = file.suggested_reviewer
            ? file.suggested_reviewer.substring(0, 2).toUpperCase()
            : '??';

        return `
            <div class="debt-file-row entering" style="animation-delay: ${index * 0.03}s">
                <div class="debt-file-indicator ${risk}"></div>
                <div class="debt-file-path" title="${escapeHtml(file.file_path)}">
                    <span class="file-dir">${escapeHtml(dir)}</span>${escapeHtml(name)}
                </div>
                <div class="debt-score-bar-container">
                    <div class="debt-score-bar-track">
                        <div class="debt-score-bar-fill ${risk}" style="width: ${score}%"></div>
                    </div>
                    <div class="debt-score-value ${risk}">${score}/100</div>
                </div>
                <div class="debt-metric">
                    <span class="debt-metric-value">${Math.round(file.ai_authorship_pct)}%</span>
                    <span class="debt-metric-label">AI</span>
                </div>
                <div class="debt-metric">
                    <span class="debt-metric-value">${file.human_edit_count}</span>
                    <span class="debt-metric-label">Edits</span>
                </div>
                <div class="debt-metric">
                    <span class="debt-metric-value">${file.unique_contributors}</span>
                    <span class="debt-metric-label">Devs</span>
                </div>
                <div class="debt-reviewer" title="${escapeHtml(file.suggested_reviewer || 'None')}">
                    <div class="debt-reviewer-avatar">${initials}</div>
                    <span>${escapeHtml(file.suggested_reviewer || 'Unassigned')}</span>
                </div>
            </div>
        `;
    }

    // ---- Update Filter Counts ----
    function updateFilterCounts() {
        const setCount = (id, count) => {
            const el = document.getElementById(id);
            if (el) el.textContent = count;
        };

        setCount('filterAllCount', allFiles.length);
        setCount('filterRedCount', allFiles.filter(f => f.risk_level === 'red').length);
        setCount('filterAmberCount', allFiles.filter(f => f.risk_level === 'amber').length);
        setCount('filterGreenCount', allFiles.filter(f => f.risk_level === 'green').length);
    }

    // ---- Trigger Analysis ----
    async function triggerAnalysis() {
        const btn = document.getElementById('analyzeBtn');
        if (!btn) return;

        btn.disabled = true;
        btn.innerHTML = `
            <svg class="spinner-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 12a9 9 0 1 1-6.219-8.56" />
            </svg>
            Analyzing...
        `;

        try {
            await apiRequest(`/api/repositories/${repoId}/debt/analyse/`, 'POST');
            showToast('Analysis started! Results will appear shortly.', 'success');

            // Poll for results after a short delay
            setTimeout(() => loadData(), 3000);
            setTimeout(() => loadData(), 8000);
            setTimeout(() => {
                loadData();
                btn.disabled = false;
                btn.innerHTML = `
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="23 4 23 10 17 10"></polyline>
                        <polyline points="1 20 1 14 7 14"></polyline>
                        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                    </svg>
                    Run Analysis
                `;
            }, 15000);
        } catch (err) {
            console.error('Analysis trigger failed:', err);
            showToast('Failed to start analysis. Please try again.', 'error');
            btn.disabled = false;
            btn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="23 4 23 10 17 10"></polyline>
                    <polyline points="1 20 1 14 7 14"></polyline>
                    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                </svg>
                Run Analysis
            `;
        }
    }

    // ---- Empty State ----
    function renderEmptyState() {
        const container = document.getElementById('fileListContainer');
        if (!container) return;
        container.innerHTML = `
            <div class="debt-empty-state">
                <div class="debt-empty-icon">
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                        <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22" />
                    </svg>
                </div>
                <h3>No Cognitive Debt Data Yet</h3>
                <p>Click "Run Analysis" to scan your repository's git history and detect which files your team truly understands vs. what AI wrote.</p>
                <button class="btn-analyze" onclick="document.getElementById('analyzeBtn').click()">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="23 4 23 10 17 10"></polyline>
                        <polyline points="1 20 1 14 7 14"></polyline>
                        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                    </svg>
                    Start First Analysis
                </button>
            </div>
        `;
    }

    // ---- Loading ----
    function showLoading() {
        const cards = document.getElementById('summaryCards');
        if (cards) {
            cards.innerHTML = Array.from({length: 4}, () => `
                <div class="debt-summary-card">
                    <div class="debt-skeleton debt-skeleton-card"></div>
                </div>
            `).join('');
        }

        const container = document.getElementById('fileListContainer');
        if (container) {
            container.innerHTML = Array.from({length: 5}, () => `
                <div class="debt-skeleton debt-skeleton-row"></div>
            `).join('');
        }
    }

    function hideLoading() {
        // Loading gets replaced by actual content in render functions
    }

    // ---- Utilities ----
    function timeAgo(dateStr) {
        const now = new Date();
        const date = new Date(dateStr);
        const diff = Math.floor((now - date) / 1000);

        if (diff < 60) return 'just now';
        if (diff < 3600) return Math.floor(diff / 60) + ' min ago';
        if (diff < 86400) return Math.floor(diff / 3600) + ' hours ago';
        if (diff < 604800) return Math.floor(diff / 86400) + ' days ago';
        return date.toLocaleDateString();
    }

    function escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function showToast(message, type) {
        const container = document.getElementById('toastContainer');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.style.cssText = `
            padding: 1rem 1.5rem;
            background: ${type === 'success' ? '#10b981' : '#ef4444'};
            color: white;
            border-radius: 0.75rem;
            font-weight: 600;
            font-size: 0.875rem;
            margin-bottom: 0.5rem;
            box-shadow: 0 4px 16px rgba(0,0,0,0.15);
            animation: fadeInSlide 0.3s ease-out;
        `;
        toast.textContent = message;
        container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(-8px)';
            toast.style.transition = 'all 0.3s ease-out';
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }

    function showError(msg) {
        const container = document.getElementById('fileListContainer');
        if (container) {
            container.innerHTML = `
                <div class="debt-empty-state">
                    <div class="debt-empty-icon" style="background: #fef2f2; color: #ef4444;">
                        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                            <circle cx="12" cy="12" r="10"></circle>
                            <line x1="12" y1="8" x2="12" y2="12"></line>
                            <line x1="12" y1="16" x2="12.01" y2="16"></line>
                        </svg>
                    </div>
                    <h3>Error</h3>
                    <p>${msg}</p>
                </div>
            `;
        }
    }

})();
