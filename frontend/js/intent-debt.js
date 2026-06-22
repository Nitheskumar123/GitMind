/**
 * Intent Debt Tab — Repository Detail Page
 * Renders the intent debt summary + flag list for a repository.
 * Also adds intent-flag badges to PR cards in the Pull Requests tab.
 */

(function () {
    'use strict';

    // Wait for the tab system to be ready
    const originalSwitchTab = window.switchTab;
    window.switchTab = function (tabId) {
        if (originalSwitchTab) originalSwitchTab(tabId);
        if (tabId === 'intent-debt') {
            loadIntentDebtTab();
        }
    };

    // Load summary on page load to update the tab badge
    document.addEventListener('DOMContentLoaded', () => {
        // Delay slightly to ensure repoId is available
        setTimeout(() => {
            const repoId = getRepoIdFromUrl();
            if (repoId) {
                loadIntentSummaryBadge(repoId);
            }
        }, 1500);
    });

    function getRepoIdFromUrl() {
        const params = new URLSearchParams(window.location.search);
        return params.get('id');
    }

    // ── Load badge count ─────────────────────────────────────────────────
    async function loadIntentSummaryBadge(repoId) {
        try {
            const summary = await apiRequest(`/api/repositories/${repoId}/intent-summary/`);
            const badge = document.getElementById('intentPendingCount');
            if (badge && summary.pending_flags > 0) {
                badge.textContent = summary.pending_flags;
                badge.style.display = 'inline-flex';
            }
        } catch (e) {
            // Silent fail — feature may not have data yet
        }
    }

    // ── Load full intent debt tab ────────────────────────────────────────
    async function loadIntentDebtTab() {
        const repoId = getRepoIdFromUrl();
        const container = document.getElementById('intentDebtContainer');
        if (!repoId || !container) return;

        container.innerHTML = `
            <div style="text-align: center; padding: 40px; color: #64748b;">
                <div class="spinner" style="width: 32px; height: 32px; border: 3px solid rgba(139,92,246,0.2); border-top-color: #8b5cf6; border-radius: 50%; animation: spin 0.8s linear infinite; margin: 0 auto 16px;"></div>
                <p>Loading intent debt analysis...</p>
            </div>`;

        try {
            const summary = await apiRequest(`/api/repositories/${repoId}/intent-summary/`);
            renderIntentDebtDashboard(container, summary, repoId);
        } catch (e) {
            container.innerHTML = `
                <div style="text-align: center; padding: 60px 24px; color: #64748b;">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom: 16px;">
                        <path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"></path>
                    </svg>
                    <h3 style="color: #f1f5f9; margin: 0 0 8px;">No Intent Data Yet</h3>
                    <p>Run an intent scan to detect decisions that need documentation.</p>
                    <button onclick="triggerIntentScan()" class="btn-action" style="margin-top: 16px; padding: 10px 24px; background: linear-gradient(135deg, #8b5cf6, #6366f1); color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600;">
                        Run Intent Scan
                    </button>
                </div>`;
        }
    }

    // ── Render dashboard ─────────────────────────────────────────────────
    function renderIntentDebtDashboard(container, summary, repoId) {
        const captureRate = summary.capture_rate || 0;
        const rateColor = captureRate >= 80 ? '#22c55e' : captureRate >= 50 ? '#f59e0b' : '#ef4444';

        let html = `
        <div style="padding: 4px 0;">
            <!-- Summary Cards -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 24px;">
                <div style="background: rgba(139,92,246,0.08); border: 1px solid rgba(139,92,246,0.2); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 2rem; font-weight: 700; color: #c4b5fd;">${summary.total_flags}</div>
                    <div style="font-size: 0.78rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em;">Total Flags</div>
                </div>
                <div style="background: rgba(251,191,36,0.08); border: 1px solid rgba(251,191,36,0.2); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 2rem; font-weight: 700; color: #fbbf24;">${summary.pending_flags}</div>
                    <div style="font-size: 0.78rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em;">Pending</div>
                </div>
                <div style="background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.2); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 2rem; font-weight: 700; color: #4ade80;">${summary.captured_flags}</div>
                    <div style="font-size: 0.78rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em;">Captured</div>
                </div>
                <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="font-size: 2rem; font-weight: 700; color: ${rateColor};">${captureRate}%</div>
                    <div style="font-size: 0.78rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em;">Capture Rate</div>
                </div>
            </div>

            <!-- Actions Row -->
            <div style="display: flex; gap: 12px; margin-bottom: 24px; flex-wrap: wrap;">
                <button onclick="triggerIntentScan()" style="display: inline-flex; align-items: center; gap: 8px; padding: 10px 20px; background: linear-gradient(135deg, #8b5cf6, #6366f1); color: white; border: none; border-radius: 10px; cursor: pointer; font-weight: 600; font-size: 0.88rem; box-shadow: 0 2px 12px rgba(139,92,246,0.25); transition: all 0.2s;">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="23 4 23 10 17 10"></polyline>
                        <polyline points="1 20 1 14 7 14"></polyline>
                        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                    </svg>
                    Run Intent Scan
                </button>
            </div>`;

        // Pending PRs list
        if (summary.pending_by_pr && summary.pending_by_pr.length > 0) {
            html += `
            <h3 style="color: #f1f5f9; font-size: 1rem; margin: 0 0 16px; font-weight: 600;">
                PRs Needing Intent Capture
            </h3>
            <div style="display: flex; flex-direction: column; gap: 10px;">`;

            for (const pr of summary.pending_by_pr) {
                html += `
                <a href="/intent-capture/?repo_id=${repoId}&pr_number=${pr.pr_number}"
                   style="display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; background: rgba(15,23,42,0.6); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; text-decoration: none; transition: all 0.2s; cursor: pointer;"
                   onmouseover="this.style.borderColor='rgba(139,92,246,0.3)'; this.style.boxShadow='0 4px 20px rgba(139,92,246,0.08)'"
                   onmouseout="this.style.borderColor='rgba(255,255,255,0.08)'; this.style.boxShadow='none'">
                    <div>
                        <div style="color: #e2e8f0; font-weight: 600; font-size: 0.9rem; margin-bottom: 4px;">
                            PR #${pr.pr_number}: ${escapeHtmlLocal(pr.pr_title)}
                        </div>
                        <div style="color: #64748b; font-size: 0.8rem;">
                            ${pr.count} decision${pr.count !== 1 ? 's' : ''} awaiting documentation
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="display: inline-flex; align-items: center; padding: 4px 12px; background: rgba(251,191,36,0.12); color: #fbbf24; border-radius: 20px; font-size: 0.78rem; font-weight: 600;">
                            ${pr.count} pending
                        </span>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2">
                            <path d="M5 12h14M12 5l7 7-7 7"/>
                        </svg>
                    </div>
                </a>`;
            }

            html += `</div>`;
        } else if (summary.total_flags === 0) {
            html += `
            <div style="text-align: center; padding: 40px; color: #64748b;">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="margin-bottom: 16px;">
                    <path d="M22 11.08V12a10 10 0 11-5.93-9.14"></path>
                    <polyline points="22 4 12 14.01 9 11.01"></polyline>
                </svg>
                <h3 style="color: #f1f5f9; margin: 0 0 8px;">All Clear!</h3>
                <p>No pending intent flags. Run a scan after new PRs are synced.</p>
            </div>`;
        } else {
            html += `
            <div style="text-align: center; padding: 40px; color: #64748b;">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#4ade80" stroke-width="1.5" style="margin-bottom: 16px;">
                    <path d="M22 11.08V12a10 10 0 11-5.93-9.14"></path>
                    <polyline points="22 4 12 14.01 9 11.01"></polyline>
                </svg>
                <h3 style="color: #f1f5f9; margin: 0 0 8px;">All Intent Captured! 🎉</h3>
                <p>Every flagged decision has been documented. Great work!</p>
            </div>`;
        }

        html += `</div>`;
        container.innerHTML = html;
    }

    // ── Trigger intent scan ──────────────────────────────────────────────
    window.triggerIntentScan = async function () {
        const repoId = getRepoIdFromUrl();
        if (!repoId) return;

        try {
            const result = await apiRequest(`/api/repositories/${repoId}/intent-scan/`, 'POST');
            showToastLocal(result.message || 'Intent scan started!', 'success');

            // Reload tab after a delay
            setTimeout(() => loadIntentDebtTab(), 3000);
        } catch (e) {
            console.error('Intent scan failed:', e);
            showToastLocal('Failed to start intent scan', 'error');
        }
    };

    // ── Helpers ──────────────────────────────────────────────────────────
    function escapeHtmlLocal(text) {
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    }

    function showToastLocal(message, type) {
        if (typeof showToast === 'function') {
            showToast(message, type);
            return;
        }
        // Fallback if showToast not globally available
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        const container = document.getElementById('toastContainer');
        if (container) {
            container.appendChild(toast);
            setTimeout(() => toast.classList.add('show'), 100);
            setTimeout(() => {
                toast.classList.remove('show');
                setTimeout(() => toast.remove(), 300);
            }, 3000);
        }
    }
})();
