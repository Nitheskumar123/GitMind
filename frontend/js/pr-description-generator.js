/**
 * PR Description Generator
 * Generates AI-powered PR descriptions, previews them, and pushes to GitHub.
 * Uses apiRequest() from api.js for consistent auth handling.
 */

class PRDescriptionGenerator {
    constructor(repoId) {
        this.repoId = repoId;
        this.container = null;
        this.currentPrNumber = null;
        this.descriptionData = null;
    }

    render(container, prNumber) {
        this.container = container;
        this.currentPrNumber = prNumber;

        container.innerHTML = `
            <div class="pr-description-widget" id="pr-desc-widget-${prNumber}">
                <div class="widget-header">
                    <h3><span class="icon">✍️</span> AI PR Description</h3>
                    <div class="widget-actions">
                        <button class="btn-generate" id="btn-generate-desc-${prNumber}" onclick="prDescGen.generate()">
                            <span>⚡</span> Generate
                        </button>
                        <button class="btn-apply" id="btn-apply-desc-${prNumber}" onclick="prDescGen.applyToGithub()" style="display:none;">
                            <span>🚀</span> Apply to GitHub
                        </button>
                    </div>
                </div>
                <div id="desc-content-${prNumber}">
                    <div class="pr-tools-loading">
                        <div class="spinner"></div>
                        Loading existing description...
                    </div>
                </div>
            </div>
        `;

        this.loadExisting();
    }

    async loadExisting() {
        const content = document.getElementById(`desc-content-${this.currentPrNumber}`);
        try {
            const data = await apiRequest(
                `/api/repositories/${this.repoId}/pulls/${this.currentPrNumber}/description/`
            );

            if (data && data.generated_description) {
                this.descriptionData = data;
                this.renderPreview(data);
            } else {
                this.showEmptyState(content);
            }
        } catch (err) {
            // 404 = no description yet, show generate prompt
            this.showEmptyState(content);
        }
    }

    showEmptyState(content) {
        if (!content) content = document.getElementById(`desc-content-${this.currentPrNumber}`);
        if (content) {
            content.innerHTML = `
                <div class="pr-tools-empty">
                    <div class="empty-icon">📝</div>
                    <p>Click <strong>Generate</strong> to create an AI-powered description for this PR.</p>
                </div>
            `;
        }
    }

    async generate() {
        const btn = document.getElementById(`btn-generate-desc-${this.currentPrNumber}`);
        const content = document.getElementById(`desc-content-${this.currentPrNumber}`);

        btn.disabled = true;
        btn.innerHTML = '<span class="spinner" style="width:14px;height:14px;border-width:2px;display:inline-block;"></span> Generating...';

        content.innerHTML = `
            <div class="pr-tools-loading">
                <div class="spinner"></div>
                Analyzing commits and diff with AI...
            </div>
        `;

        try {
            await apiRequest(
                `/api/repositories/${this.repoId}/pulls/${this.currentPrNumber}/description/generate/`,
                'POST'
            );

            // Poll for the result (async Celery task)
            await this.pollForResult();

        } catch (err) {
            content.innerHTML = `
                <div class="pr-tools-empty">
                    <div class="empty-icon">❌</div>
                    <p>Generation failed: ${err.message}</p>
                </div>
            `;
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<span>⚡</span> Regenerate';
        }
    }

    async pollForResult(maxAttempts = 12) {
        // Wait for the Celery task to start
        await new Promise(r => setTimeout(r, 3000));

        for (let i = 0; i < maxAttempts; i++) {
            try {
                const data = await apiRequest(
                    `/api/repositories/${this.repoId}/pulls/${this.currentPrNumber}/description/`
                );

                if (data && data.generated_description) {
                    this.descriptionData = data;
                    this.renderPreview(data);
                    return;
                }
            } catch (err) {
                console.log('Polling description...', i + 1);
            }

            await new Promise(r => setTimeout(r, 2000));
        }

        const content = document.getElementById(`desc-content-${this.currentPrNumber}`);
        if (content) {
            content.innerHTML = `
                <div class="pr-tools-empty">
                    <div class="empty-icon">⏳</div>
                    <p>Generation is taking longer than expected. Refresh the page in a moment.</p>
                </div>
            `;
        }
    }

    renderPreview(data) {
        const content = document.getElementById(`desc-content-${this.currentPrNumber}`);
        const applyBtn = document.getElementById(`btn-apply-desc-${this.currentPrNumber}`);

        let tags = '';
        if (data.features && data.features.length > 0)
            tags += `<span class="change-tag feature">✨ ${data.features.length} features</span>`;
        if (data.bug_fixes && data.bug_fixes.length > 0)
            tags += `<span class="change-tag bugfix">🐛 ${data.bug_fixes.length} fixes</span>`;
        if (data.breaking_changes && data.breaking_changes.length > 0)
            tags += `<span class="change-tag breaking">⚠️ ${data.breaking_changes.length} breaking</span>`;
        if (data.refactors && data.refactors.length > 0)
            tags += `<span class="change-tag refactor">♻️ ${data.refactors.length} refactors</span>`;
        if (data.has_tests)
            tags += `<span class="change-tag test">✅ Tests included</span>`;
        if (data.requires_migration)
            tags += `<span class="change-tag migration">🗃️ Migration required</span>`;

        let statusBadge = data.applied_to_github
            ? '<span class="status-badge applied">✅ Applied</span>'
            : '<span class="status-badge pending">⏳ Not applied</span>';

        content.innerHTML = `
            <div class="change-tags">${tags}</div>
            <div class="description-preview" style="margin-top: 12px;">
                ${this.markdownToHtml(data.generated_description || '')}
            </div>
            <div class="description-meta">
                ${statusBadge}
                <span>🔤 ${data.tokens_used || 0} tokens</span>
                <span>⏱️ ${(data.generation_time || 0).toFixed(1)}s</span>
            </div>
        `;

        if (applyBtn && !data.applied_to_github) {
            applyBtn.style.display = 'flex';
        }
    }

    async applyToGithub() {
        const btn = document.getElementById(`btn-apply-desc-${this.currentPrNumber}`);
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner" style="width:14px;height:14px;border-width:2px;display:inline-block;"></span> Applying...';

        try {
            await apiRequest(
                `/api/repositories/${this.repoId}/pulls/${this.currentPrNumber}/description/apply/`,
                'POST'
            );

            btn.innerHTML = '✅ Applied!';
            btn.style.background = 'rgba(16, 185, 129, 0.2)';
            this.loadExisting();

            if (typeof showToast === 'function') showToast('Description applied to GitHub!', 'success');

        } catch (err) {
            btn.disabled = false;
            btn.innerHTML = '<span>🚀</span> Apply to GitHub';
            if (typeof showToast === 'function') showToast('Failed to apply: ' + err.message, 'error');
        }
    }

    markdownToHtml(md) {
        if (!md) return '';
        return md
            .replace(/^### (.+)$/gm, '<h3>$1</h3>')
            .replace(/^## (.+)$/gm, '<h2>$1</h2>')
            .replace(/^# (.+)$/gm, '<h1>$1</h1>')
            .replace(/^- (.+)$/gm, '<li>$1</li>')
            .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            .replace(/\n{2,}/g, '<br><br>')
            .replace(/\n/g, '<br>')
            .replace(/---/g, '<hr>');
    }
}

// Global instance (initialized per PR)
let prDescGen = null;
