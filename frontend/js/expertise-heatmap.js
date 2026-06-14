/**
 * Expertise Heatmap
 * Displays a visual heatmap of developer expertise and code ownership per repository.
 * Uses apiRequest() from api.js for consistent auth handling.
 */

class ExpertiseHeatmap {
    constructor(repoId) {
        this.repoId = repoId;
        this.container = null;
        this.data = null;
    }

    render(container) {
        this.container = container;

        container.innerHTML = `
            <div class="expertise-widget" id="expertise-widget">
                <div class="widget-header">
                    <h3><span class="icon">🧠</span> Developer Expertise Map</h3>
                    <div class="widget-actions">
                        <button class="btn-generate" id="btn-analyze-ownership" onclick="expertiseMap.analyzeOwnership()">
                            <span>📊</span> Analyze
                        </button>
                    </div>
                </div>
                <div id="expertise-content">
                    <div class="pr-tools-loading">
                        <div class="spinner"></div>
                        Loading expertise data...
                    </div>
                </div>
            </div>
        `;

        this.loadData();
    }

    async loadData() {
        const content = document.getElementById('expertise-content');

        try {
            const data = await apiRequest(`/api/repositories/${this.repoId}/ownership/`);
            this.data = data;

            const expertiseList = data.expertise || data.developers || [];

            if (expertiseList.length === 0) {
                this.showEmptyState(content);
                return;
            }

            this.renderHeatmap(expertiseList);

        } catch (err) {
            console.log('Expertise load error:', err.message);
            this.showEmptyState(content);
        }
    }

    showEmptyState(content) {
        if (!content) content = document.getElementById('expertise-content');
        if (content) {
            content.innerHTML = `
                <div class="pr-tools-empty">
                    <div class="empty-icon">📊</div>
                    <p>No expertise data yet. Click <strong>Analyze</strong> to compute ownership from commit history.</p>
                </div>
            `;
        }
    }

    async analyzeOwnership() {
        const btn = document.getElementById('btn-analyze-ownership');
        const content = document.getElementById('expertise-content');

        btn.disabled = true;
        btn.innerHTML = '<span class="spinner" style="width:14px;height:14px;border-width:2px;display:inline-block;"></span> Analyzing...';

        content.innerHTML = `
            <div class="pr-tools-loading">
                <div class="spinner"></div>
                Analyzing commit history for ownership patterns...
            </div>
        `;

        try {
            await apiRequest(`/api/repositories/${this.repoId}/ownership/analyze/`, 'POST');

            // Poll for results
            await this.pollForData();

        } catch (err) {
            content.innerHTML = `
                <div class="pr-tools-empty">
                    <div class="empty-icon">❌</div>
                    <p>Analysis failed: ${err.message}</p>
                </div>
            `;
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<span>📊</span> Refresh';
        }
    }

    async pollForData(maxAttempts = 10) {
        // Wait for the Celery task to start processing
        await new Promise(r => setTimeout(r, 5000));

        for (let i = 0; i < maxAttempts; i++) {
            try {
                const data = await apiRequest(`/api/repositories/${this.repoId}/ownership/`);
                const expertiseList = data.expertise || data.developers || [];

                if (expertiseList.length > 0) {
                    this.data = data;
                    this.renderHeatmap(expertiseList);
                    return;
                }
            } catch (err) {
                console.log('Polling expertise...', i + 1);
            }

            await new Promise(r => setTimeout(r, 3000));
        }

        // Polling finished without data — show helpful message
        const content = document.getElementById('expertise-content');
        if (content) {
            content.innerHTML = `
                <div class="pr-tools-empty">
                    <div class="empty-icon">⏳</div>
                    <p>Analysis is still running in the background. Refresh the page in a minute to see results.</p>
                </div>
            `;
        }
    }

    renderHeatmap(developers) {
        const content = document.getElementById('expertise-content');

        developers.sort((a, b) => (b.total_commits || 0) - (a.total_commits || 0));

        let html = '<div class="expertise-grid">';

        for (const dev of developers.slice(0, 12)) {
            const avatarUrl = `https://ui-avatars.com/api/?name=${dev.github_username}&background=6366f1&color=fff`;

            let barsHtml = '';
            const expertiseMap = dev.expertise_map || {};
            const sortedDomains = Object.entries(expertiseMap)
                .sort(([, a], [, b]) => b - a)
                .slice(0, 5);

            for (const [domain, score] of sortedDomains) {
                barsHtml += `
                    <div class="expertise-bar-row">
                        <span class="expertise-bar-label">${domain}</span>
                        <div class="expertise-bar">
                            <div class="expertise-bar-fill" style="width: ${Math.min(score, 100)}%"></div>
                        </div>
                        <span class="expertise-bar-score">${score}%</span>
                    </div>
                `;
            }

            if (!barsHtml) {
                barsHtml = '<div style="font-size: 0.8rem; color: var(--text-muted, #6b7280);">No domain data</div>';
            }

            html += `
                <div class="expertise-card">
                    <div class="dev-header">
                        <img class="dev-avatar" src="${avatarUrl}" alt="${dev.github_username}" />
                        <div>
                            <div class="dev-name">${dev.github_username}</div>
                            <div class="dev-stats">
                                ${dev.total_commits || 0} commits · ${dev.total_prs_authored || 0} PRs · ${dev.active_days || 0} active days
                            </div>
                        </div>
                    </div>
                    <div class="expertise-bars">
                        ${barsHtml}
                    </div>
                </div>
            `;
        }

        html += '</div>';
        content.innerHTML = html;
    }
}

// Global instance
let expertiseMap = null;
