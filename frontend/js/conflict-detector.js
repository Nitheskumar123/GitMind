/**
 * Conflict Detector Widget — Phase 7
 * Displays pre-emptive conflict detection results for open PRs.
 */

class ConflictDetector {
    constructor(containerId, repoId) {
        this.container = document.getElementById(containerId);
        this.repoId = repoId;
        this.conflicts = [];
    }

    async init() {
        if (!this.container || !this.repoId) return;
        this.renderSkeleton();
        await this.loadConflicts();
    }

    renderSkeleton() {
        this.container.innerHTML = `
            <div class="conflict-detector-widget">
                <div class="conflict-header">
                    <div class="conflict-header-left">
                        <h2 class="conflict-title">
                            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                                <line x1="12" y1="9" x2="12" y2="13"></line>
                                <line x1="12" y1="17" x2="12.01" y2="17"></line>
                            </svg>
                            PR Conflict Detector
                        </h2>
                        <p class="conflict-subtitle">Pre-emptive detection of overlapping PR changes</p>
                    </div>
                    <button id="checkConflictsBtn" class="conflict-check-btn" onclick="conflictDetector.analyzeConflicts()">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="23 4 23 10 17 10"></polyline>
                            <polyline points="1 20 1 14 7 14"></polyline>
                            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                        </svg>
                        Check Now
                    </button>
                </div>
                <div id="conflictSummary" class="conflict-summary"></div>
                <div id="conflictsList" class="conflicts-list">
                    <div class="conflict-loading">
                        <div class="spinner-small"></div>
                        <span>Scanning for conflicts...</span>
                    </div>
                </div>
            </div>
        `;
    }

    async loadConflicts() {
        try {
            this.conflicts = await apiRequest(`/api/repositories/${this.repoId}/conflicts/`);
            this.render();
            this.updateTabCount();
        } catch (err) {
            console.error('Failed to load conflicts:', err);
            this.renderEmpty();
        }
    }

    async analyzeConflicts() {
        const btn = document.getElementById('checkConflictsBtn');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<div class="spinner-small"></div> Analyzing...';
        }
        try {
            await apiRequest(`/api/repositories/${this.repoId}/conflicts/analyze/`, 'POST');
            // Poll for results after a delay
            setTimeout(async () => {
                await this.loadConflicts();
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = `
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="23 4 23 10 17 10"></polyline>
                            <polyline points="1 20 1 14 7 14"></polyline>
                            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                        </svg>
                        Check Now
                    `;
                }
            }, 5000);
        } catch (err) {
            console.error('Conflict analysis failed:', err);
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Check Now';
            }
        }
    }

    render() {
        if (!this.conflicts || this.conflicts.length === 0) {
            this.renderEmpty();
            return;
        }

        this.renderSummary();
        this.renderConflictCards();
    }

    renderSummary() {
        const summary = document.getElementById('conflictSummary');
        if (!summary) return;

        const critical = this.conflicts.filter(c => c.severity === 'critical').length;
        const high = this.conflicts.filter(c => c.severity === 'high').length;
        const medium = this.conflicts.filter(c => c.severity === 'medium').length;
        const low = this.conflicts.filter(c => c.severity === 'low').length;

        summary.innerHTML = `
            <div class="conflict-summary-grid">
                <div class="conflict-stat conflict-stat-critical">
                    <span class="conflict-stat-number">${critical}</span>
                    <span class="conflict-stat-label">Critical</span>
                </div>
                <div class="conflict-stat conflict-stat-high">
                    <span class="conflict-stat-number">${high}</span>
                    <span class="conflict-stat-label">High</span>
                </div>
                <div class="conflict-stat conflict-stat-medium">
                    <span class="conflict-stat-number">${medium}</span>
                    <span class="conflict-stat-label">Medium</span>
                </div>
                <div class="conflict-stat conflict-stat-low">
                    <span class="conflict-stat-number">${low}</span>
                    <span class="conflict-stat-label">Low</span>
                </div>
            </div>
        `;
    }

    renderConflictCards() {
        const list = document.getElementById('conflictsList');
        if (!list) return;

        list.innerHTML = this.conflicts.map(c => `
            <div class="conflict-card conflict-severity-${c.severity}">
                <div class="conflict-card-header">
                    <span class="severity-badge severity-${c.severity}">${c.severity.toUpperCase()}</span>
                    <span class="conflict-type-badge">${this.formatConflictType(c.conflict_type)}</span>
                </div>
                <div class="conflict-card-body">
                    <div class="conflict-pr-pair">
                        <div class="conflict-pr">
                            <span class="pr-number">PR #${c.pr_1_number}</span>
                            <span class="pr-title">${this.escapeHtml(c.pr_1_title || '')}</span>
                            <span class="pr-author">by ${c.pr_1_author || 'unknown'}</span>
                        </div>
                        <div class="conflict-vs">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <line x1="18" y1="6" x2="6" y2="18"></line>
                                <line x1="6" y1="6" x2="18" y2="18"></line>
                            </svg>
                        </div>
                        <div class="conflict-pr">
                            <span class="pr-number">PR #${c.pr_2_number}</span>
                            <span class="pr-title">${this.escapeHtml(c.pr_2_title || '')}</span>
                            <span class="pr-author">by ${c.pr_2_author || 'unknown'}</span>
                        </div>
                    </div>
                    ${c.affected_files && c.affected_files.length ? `
                        <div class="conflict-files">
                            <strong>Affected Files:</strong>
                            <ul>${c.affected_files.slice(0, 5).map(f => `<li><code>${this.escapeHtml(f)}</code></li>`).join('')}</ul>
                        </div>
                    ` : ''}
                    ${c.resolution_suggestion ? `
                        <div class="conflict-resolution">
                            <strong>💡 Recommendation:</strong>
                            <p>${this.escapeHtml(c.resolution_suggestion)}</p>
                        </div>
                    ` : ''}
                    ${c.merge_order && c.merge_order.length ? `
                        <div class="conflict-merge-order">
                            <strong>📋 Merge Order:</strong>
                            <div class="merge-order-flow">
                                ${c.merge_order.map((pr, i) => `
                                    <span class="merge-step">PR #${pr}</span>
                                    ${i < c.merge_order.length - 1 ? '<span class="merge-arrow">→</span>' : ''}
                                `).join('')}
                            </div>
                        </div>
                    ` : ''}
                </div>
                <div class="conflict-card-actions">
                    <button class="btn-resolve" onclick="conflictDetector.resolveConflict(${c.id})">
                        ✓ Mark Resolved
                    </button>
                    ${!c.notified ? `
                        <button class="btn-notify" onclick="conflictDetector.notifyDevelopers(${c.id})">
                            🔔 Notify Developers
                        </button>
                    ` : '<span class="notified-badge">✓ Notified</span>'}
                </div>
            </div>
        `).join('');
    }

    renderEmpty() {
        const list = document.getElementById('conflictsList');
        const summary = document.getElementById('conflictSummary');
        if (summary) summary.innerHTML = '';
        if (list) {
            list.innerHTML = `
                <div class="conflict-empty">
                    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity="0.3">
                        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                        <polyline points="22 4 12 14.01 9 11.01"></polyline>
                    </svg>
                    <h3>No Conflicts Detected</h3>
                    <p>All open PRs look good! Click "Check Now" to scan for conflicts.</p>
                </div>
            `;
        }
    }

    async resolveConflict(conflictId) {
        try {
            await apiRequest(`/api/conflicts/${conflictId}/resolve/`, 'POST');
            this.conflicts = this.conflicts.filter(c => c.id !== conflictId);
            this.render();
            this.updateTabCount();
        } catch (err) {
            console.error('Failed to resolve conflict:', err);
        }
    }

    async notifyDevelopers(conflictId) {
        try {
            await apiRequest(`/api/conflicts/${conflictId}/notify/`, 'POST');
            const conflict = this.conflicts.find(c => c.id === conflictId);
            if (conflict) conflict.notified = true;
            this.render();
        } catch (err) {
            console.error('Failed to notify:', err);
        }
    }

    updateTabCount() {
        const badge = document.getElementById('conflictCount');
        if (badge) {
            badge.textContent = this.conflicts.length;
            badge.style.display = this.conflicts.length > 0 ? 'inline-flex' : 'none';
        }
    }

    formatConflictType(type) {
        const map = {
            'file_level': 'File',
            'function_level': 'Function',
            'symbol_level': 'Symbol',
            'semantic': 'Semantic',
            'dependency': 'Dependency',
        };
        return map[type] || type;
    }

    escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
}

// Global instance — initialized from repository.js
let conflictDetector = null;
