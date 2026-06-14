/**
 * Dependency Dashboard Widget — Phase 7
 * Displays dependency analysis results with impact scores.
 */

class DependencyDashboard {
    constructor(containerId, repoId) {
        this.container = document.getElementById(containerId);
        this.repoId = repoId;
        this.dependencies = [];
        this.impactReport = null;
    }

    async init() {
        if (!this.container || !this.repoId) return;
        this.renderSkeleton();
        await this.loadData();
    }

    renderSkeleton() {
        this.container.innerHTML = `
            <div class="dep-dashboard-widget">
                <div class="dep-header">
                    <div class="dep-header-left">
                        <h2 class="dep-title">
                            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <circle cx="12" cy="12" r="10"></circle>
                                <line x1="2" y1="12" x2="22" y2="12"></line>
                                <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
                            </svg>
                            Crystal Ball — Dependency Analyzer
                        </h2>
                        <p class="dep-subtitle">Predict impact of dependency updates before they break your code</p>
                    </div>
                    <button id="checkDepsBtn" class="dep-check-btn" onclick="dependencyDashboard.analyzeDependencies()">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="23 4 23 10 17 10"></polyline>
                            <polyline points="1 20 1 14 7 14"></polyline>
                            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                        </svg>
                        Check Updates
                    </button>
                </div>
                <div id="depSummary" class="dep-summary"></div>
                <div id="depList" class="dep-list">
                    <div class="dep-loading">
                        <div class="spinner-small"></div>
                        <span>Scanning dependencies...</span>
                    </div>
                </div>
            </div>
        `;
    }

    async loadData() {
        try {
            const [deps, report] = await Promise.all([
                apiRequest(`/api/repositories/${this.repoId}/dependencies/`),
                apiRequest(`/api/repositories/${this.repoId}/dependencies/impact-report/`).catch(() => null),
            ]);
            this.dependencies = deps || [];
            this.impactReport = report;
            this.render();
        } catch (err) {
            console.error('Failed to load dependencies:', err);
            this.renderEmpty();
        }
    }

    async analyzeDependencies() {
        const btn = document.getElementById('checkDepsBtn');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<div class="spinner-small"></div> Analyzing...';
        }
        try {
            await apiRequest(`/api/repositories/${this.repoId}/dependencies/analyze/`, 'POST');
            setTimeout(async () => {
                await this.loadData();
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = `
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="23 4 23 10 17 10"></polyline>
                            <polyline points="1 20 1 14 7 14"></polyline>
                            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
                        </svg>
                        Check Updates
                    `;
                }
            }, 8000);
        } catch (err) {
            console.error('Dependency analysis failed:', err);
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Check Updates';
            }
        }
    }

    render() {
        if (!this.dependencies || this.dependencies.length === 0) {
            this.renderEmpty();
            return;
        }
        this.renderSummary();
        this.renderDependencyCards();
    }

    renderSummary() {
        const summary = document.getElementById('depSummary');
        if (!summary || !this.impactReport) return;

        const s = this.impactReport.summary || {};
        const ib = this.impactReport.impact_breakdown || {};

        summary.innerHTML = `
            <div class="dep-summary-grid">
                <div class="dep-summary-stat">
                    <span class="dep-stat-number">${s.total_dependencies || 0}</span>
                    <span class="dep-stat-label">Total Packages</span>
                </div>
                <div class="dep-summary-stat dep-stat-updates">
                    <span class="dep-stat-number">${s.updates_available || 0}</span>
                    <span class="dep-stat-label">Updates Available</span>
                </div>
                <div class="dep-summary-stat dep-stat-breaking">
                    <span class="dep-stat-number">${s.breaking_changes || 0}</span>
                    <span class="dep-stat-label">Breaking Changes</span>
                </div>
                <div class="dep-summary-stat dep-stat-safe">
                    <span class="dep-stat-number">${s.safe_updates || 0}</span>
                    <span class="dep-stat-label">Safe Updates</span>
                </div>
            </div>
            ${this.impactReport.estimated_total_refactor_hours ? `
                <div class="dep-refactor-estimate">
                    ⏱️ Estimated refactoring time: <strong>${this.impactReport.estimated_total_refactor_hours} hours</strong>
                </div>
            ` : ''}
        `;
    }

    renderDependencyCards() {
        const list = document.getElementById('depList');
        if (!list) return;

        // Sort: breaking first, then by impact score descending
        const sorted = [...this.dependencies].sort((a, b) => {
            if (a.has_breaking_changes && !b.has_breaking_changes) return -1;
            if (!a.has_breaking_changes && b.has_breaking_changes) return 1;
            return (b.impact_score || 0) - (a.impact_score || 0);
        });

        const highImpact = sorted.filter(d => d.impact_score >= 30 || d.has_breaking_changes);
        const safeUpdates = sorted.filter(d => d.impact_score < 30 && !d.has_breaking_changes && d.current_version !== d.latest_version);
        const upToDate = sorted.filter(d => d.current_version === d.latest_version || d.update_type === 'current');

        let html = '';

        if (highImpact.length > 0) {
            html += `<h3 class="dep-section-title dep-section-danger">⚠️ High Impact Updates (${highImpact.length})</h3>`;
            html += highImpact.map(d => this.renderDepCard(d)).join('');
        }

        if (safeUpdates.length > 0) {
            html += `<h3 class="dep-section-title dep-section-safe">✅ Safe Updates (${safeUpdates.length})</h3>`;
            html += safeUpdates.map(d => this.renderDepCard(d)).join('');
        }

        if (upToDate.length > 0) {
            html += `<h3 class="dep-section-title dep-section-current">📦 Up to Date (${upToDate.length})</h3>`;
            html += upToDate.map(d => this.renderDepCard(d, true)).join('');
        }

        list.innerHTML = html;
    }

    renderDepCard(dep, minimal = false) {
        const impactColor = this.getImpactColor(dep.impact_score || 0);
        const updateBadge = this.getUpdateTypeBadge(dep.update_type);

        if (minimal) {
            return `
                <div class="dep-card dep-card-current">
                    <div class="dep-card-header">
                        <span class="dep-name">${this.escapeHtml(dep.package_name)}</span>
                        <span class="dep-version">${dep.current_version}</span>
                        <span class="dep-status-badge dep-up-to-date">✓ Current</span>
                    </div>
                </div>
            `;
        }

        return `
            <div class="dep-card ${dep.has_breaking_changes ? 'dep-card-breaking' : ''}">
                <div class="dep-card-header">
                    <div class="dep-card-info">
                        <span class="dep-name">${this.escapeHtml(dep.package_name)}</span>
                        ${updateBadge}
                    </div>
                    <div class="dep-version-info">
                        <span class="dep-version dep-version-current">${dep.current_version}</span>
                        <span class="dep-version-arrow">→</span>
                        <span class="dep-version dep-version-latest">${dep.latest_version || '?'}</span>
                    </div>
                </div>
                <div class="dep-card-body">
                    <div class="dep-impact-bar">
                        <div class="dep-impact-label">Impact Score</div>
                        <div class="dep-impact-track">
                            <div class="dep-impact-fill" style="width: ${dep.impact_score || 0}%; background: ${impactColor}"></div>
                        </div>
                        <span class="dep-impact-value" style="color: ${impactColor}">${dep.impact_score || 0}/100</span>
                    </div>
                    ${dep.has_breaking_changes && dep.breaking_changes && dep.breaking_changes.length ? `
                        <div class="dep-breaking-changes">
                            <strong>🔥 Breaking Changes:</strong>
                            <ul>
                                ${dep.breaking_changes.slice(0, 3).map(bc => `
                                    <li>
                                        <span>${this.escapeHtml(typeof bc === 'string' ? bc : bc.description || JSON.stringify(bc))}</span>
                                        ${bc.fix ? `<span class="dep-fix-hint">Fix: ${this.escapeHtml(bc.fix)}</span>` : ''}
                                    </li>
                                `).join('')}
                            </ul>
                        </div>
                    ` : ''}
                    ${dep.files_affected && dep.files_affected.length ? `
                        <div class="dep-affected-files">
                            <strong>📁 Affected Files (${dep.files_affected.length}):</strong>
                            <div class="dep-files-list">
                                ${dep.files_affected.slice(0, 5).map(f => `<code>${this.escapeHtml(f)}</code>`).join('')}
                                ${dep.files_affected.length > 5 ? `<span class="dep-more">+${dep.files_affected.length - 5} more</span>` : ''}
                            </div>
                        </div>
                    ` : ''}
                    ${dep.estimated_refactor_hours ? `
                        <div class="dep-refactor-time">
                            ⏱️ Est. refactor: <strong>${dep.estimated_refactor_hours}h</strong>
                        </div>
                    ` : ''}
                    ${dep.latest_safe_version && dep.latest_safe_version !== dep.current_version ? `
                        <div class="dep-safe-version">
                            🛡️ Safe upgrade: <strong>${dep.latest_safe_version}</strong>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }

    renderEmpty() {
        const list = document.getElementById('depList');
        const summary = document.getElementById('depSummary');
        if (summary) summary.innerHTML = '';
        if (list) {
            list.innerHTML = `
                <div class="dep-empty">
                    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity="0.3">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="2" y1="12" x2="22" y2="12"></line>
                        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path>
                    </svg>
                    <h3>No Dependencies Analyzed</h3>
                    <p>Click "Check Updates" to scan your project's dependencies.</p>
                </div>
            `;
        }
    }

    getImpactColor(score) {
        if (score >= 80) return '#ff4757';
        if (score >= 60) return '#ff6b35';
        if (score >= 30) return '#ffa502';
        return '#2ed573';
    }

    getUpdateTypeBadge(type) {
        const map = {
            'major': '<span class="dep-update-badge dep-update-major">Major</span>',
            'minor': '<span class="dep-update-badge dep-update-minor">Minor</span>',
            'patch': '<span class="dep-update-badge dep-update-patch">Patch</span>',
            'current': '',
        };
        return map[type] || '';
    }

    escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
}

// Global instance — initialized from repository.js
let dependencyDashboard = null;
