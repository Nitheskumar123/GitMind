/**
 * Reviewer Recommender
 * Displays AI-powered reviewer recommendations and allows requesting reviews on GitHub.
 * Uses apiRequest() from api.js for consistent auth handling.
 */

class ReviewerRecommender {
    constructor(repoId) {
        this.repoId = repoId;
        this.container = null;
        this.currentPrNumber = null;
        this.recommendations = [];
    }

    render(container, prNumber) {
        this.container = container;
        this.currentPrNumber = prNumber;

        container.innerHTML = `
            <div class="reviewer-widget" id="reviewer-widget-${prNumber}">
                <div class="widget-header">
                    <h3><span class="icon">👥</span> Smart Reviewer Recommendations</h3>
                    <div class="widget-actions">
                        <button class="btn-generate" id="btn-recommend-${prNumber}" onclick="reviewerRec.recommend()">
                            <span>🔍</span> Find Reviewers
                        </button>
                    </div>
                </div>
                <div id="reviewer-content-${prNumber}">
                    <div class="pr-tools-loading">
                        <div class="spinner"></div>
                        Loading existing recommendations...
                    </div>
                </div>
            </div>
        `;

        this.loadExisting();
    }

    async loadExisting() {
        const content = document.getElementById(`reviewer-content-${this.currentPrNumber}`);
        try {
            const data = await apiRequest(
                `/api/repositories/${this.repoId}/pulls/${this.currentPrNumber}/reviewers/`
            );

            if (Array.isArray(data) && data.length > 0) {
                this.recommendations = data;
                this.renderRecommendations(data);
            } else {
                // No recommendations yet — show empty prompt
                this.showEmptyState(content);
            }
        } catch (err) {
            // 404 or other error — show empty prompt
            this.showEmptyState(content);
        }
    }

    showEmptyState(content) {
        if (!content) content = document.getElementById(`reviewer-content-${this.currentPrNumber}`);
        if (content) {
            content.innerHTML = `
                <div class="pr-tools-empty">
                    <div class="empty-icon">🔎</div>
                    <p>Click <strong>Find Reviewers</strong> to get AI-powered reviewer suggestions.</p>
                </div>
            `;
        }
    }

    async recommend() {
        const btn = document.getElementById(`btn-recommend-${this.currentPrNumber}`);
        const content = document.getElementById(`reviewer-content-${this.currentPrNumber}`);

        btn.disabled = true;
        btn.innerHTML = '<span class="spinner" style="width:14px;height:14px;border-width:2px;display:inline-block;"></span> Analyzing...';

        content.innerHTML = `
            <div class="pr-tools-loading">
                <div class="spinner"></div>
                Analyzing code ownership and expertise...
            </div>
        `;

        try {
            await apiRequest(
                `/api/repositories/${this.repoId}/pulls/${this.currentPrNumber}/reviewers/recommend/`,
                'POST'
            );

            // Wait for task to complete, then show results
            await this.pollForRecommendations();

        } catch (err) {
            content.innerHTML = `
                <div class="pr-tools-empty">
                    <div class="empty-icon">❌</div>
                    <p>Recommendation failed: ${err.message}</p>
                </div>
            `;
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<span>🔍</span> Refresh';
        }
    }

    async pollForRecommendations(maxAttempts = 8) {
        // Wait a bit for the Celery task to finish
        await new Promise(r => setTimeout(r, 4000));

        for (let i = 0; i < maxAttempts; i++) {
            try {
                const data = await apiRequest(
                    `/api/repositories/${this.repoId}/pulls/${this.currentPrNumber}/reviewers/`
                );

                if (Array.isArray(data) && data.length > 0) {
                    this.recommendations = data;
                    this.renderRecommendations(data);
                    return;
                }
            } catch (err) {
                console.log('Polling recommendations...', i + 1);
            }

            // Wait before next attempt
            await new Promise(r => setTimeout(r, 2000));
        }

        // Polling finished without finding recommendations — show "none found"
        const content = document.getElementById(`reviewer-content-${this.currentPrNumber}`);
        if (content) {
            content.innerHTML = `
                <div class="pr-tools-empty">
                    <div class="empty-icon">🤷</div>
                    <p>No reviewer suggestions found. Run <strong>Ownership Analysis</strong> first (Expertise tab) to build the knowledge base.</p>
                </div>
            `;
        }
    }

    renderRecommendations(recommendations) {
        const content = document.getElementById(`reviewer-content-${this.currentPrNumber}`);

        if (!recommendations || recommendations.length === 0) {
            content.innerHTML = `
                <div class="pr-tools-empty">
                    <div class="empty-icon">🤷</div>
                    <p>No reviewer suggestions available. Try running ownership analysis first.</p>
                </div>
            `;
            return;
        }

        let html = '<div class="reviewer-list">';

        for (const rec of recommendations) {
            const confidenceClass = rec.confidence_score >= 60 ? 'high'
                : rec.confidence_score >= 30 ? 'medium' : 'low';

            const avatarUrl = `https://ui-avatars.com/api/?name=${rec.github_username}&background=6366f1&color=fff`;

            const badgeClass = rec.reviewer_type === 'primary' ? 'primary'
                : rec.reviewer_type === 'shadow' ? 'shadow' : 'secondary';

            const requestedIcon = rec.requested_on_github ? '✅' : '';

            html += `
                <div class="reviewer-card">
                    <img class="reviewer-avatar" src="${avatarUrl}" alt="${rec.github_username}" />
                    <div class="reviewer-info">
                        <div class="reviewer-name">${rec.github_username} ${requestedIcon}</div>
                        <div class="reviewer-reason">${rec.recommendation_reason || ''}</div>
                        <div class="reviewer-badges">
                            <span class="reviewer-badge ${badgeClass}">${rec.reviewer_type}</span>
                            ${(rec.expertise_areas || []).slice(0, 3).map(a =>
                `<span class="reviewer-badge secondary">${a}</span>`
            ).join('')}
                        </div>
                    </div>
                    <div style="text-align: center;">
                        <div class="confidence-score">${rec.confidence_score}%</div>
                        <div class="confidence-bar">
                            <div class="confidence-fill ${confidenceClass}" style="width: ${rec.confidence_score}%"></div>
                        </div>
                    </div>
                    ${!rec.requested_on_github ? `
                        <button class="btn-request-review" onclick="reviewerRec.requestReview('${rec.github_username}')">
                            Request
                        </button>
                    ` : ''}
                </div>
            `;
        }

        html += '</div>';
        content.innerHTML = html;
    }

    async requestReview(username) {
        try {
            await apiRequest(
                `/api/repositories/${this.repoId}/pulls/${this.currentPrNumber}/reviewers/request/`,
                'POST',
                { reviewers: [username] }
            );

            if (typeof showToast === 'function') showToast(`Review requested from @${username}`, 'success');
            this.loadExisting();

        } catch (err) {
            if (typeof showToast === 'function') showToast('Failed to request review: ' + err.message, 'error');
        }
    }
}

// Global instance
let reviewerRec = null;
