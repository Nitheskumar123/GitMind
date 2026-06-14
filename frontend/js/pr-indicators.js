/**
 * PR Analysis Indicators
 * Shows AI analysis badges on PR cards
 */

async function initializePRIndicators() {
    const urlParams = new URLSearchParams(window.location.search);
    const repoId = urlParams.get('id');
    if (!repoId) return;

    // Match the actual class used in displayPullRequests()
    const prCards = document.querySelectorAll('.item-card[data-pr-number]');

    for (const card of prCards) {
        const prNumber = card.dataset.prNumber;
        if (prNumber) {
            await addPRAnalysisIndicator(card, prNumber, repoId);
        }
    }
}

async function addPRAnalysisIndicator(prCard, prNumber, repoId) {
    const slot = prCard.querySelector('.analysis-indicator-slot');
    if (!slot) return;

    try {
        const analysis = await apiRequest(
            `/api/repositories/${repoId}/pulls/${prNumber}/analysis/`
        );

        if (analysis && analysis.security_score !== undefined) {
            slot.innerHTML = createAnalysisIndicatorHTML(analysis, prNumber, repoId);
        }
    } catch (error) {
        // 404 = no analysis yet, show "Analyze" button instead
        if (error.message && error.message.includes('404')) {
            slot.innerHTML = createAnalyzeButtonHTML(prNumber, repoId);
        }
    }
}

function createAnalysisIndicatorHTML(analysis, prNumber, repoId) {
    const securityScore = analysis.security_score;
    const qualityScore = analysis.quality_score;
    const issuesFound = analysis.issues_found;
    const isPosted = analysis.comment_posted;

    let statusClass = 'good';
    let statusIcon = '✅';
    if (securityScore < 60 || qualityScore < 60) {
        statusClass = 'critical';
        statusIcon = '🚨';
    } else if (securityScore < 80 || qualityScore < 80) {
        statusClass = 'warning';
        statusIcon = '⚠️';
    }

    return `
        <div class="analysis-badge ${statusClass}" style="margin-top: 0.75rem;">
            <span class="analysis-icon">${statusIcon}</span>
            <div class="analysis-summary">
                <span class="analysis-title">AI Analysis Complete</span>
                <div class="analysis-scores">
                    <span class="score-item">
                        <span class="score-label">Security:</span>
                        <span class="score-value ${getScoreClass(securityScore)}">${securityScore}/100</span>
                    </span>
                    <span class="score-item">
                        <span class="score-label">Quality:</span>
                        <span class="score-value ${getScoreClass(qualityScore)}">${qualityScore}/100</span>
                    </span>
                    <span class="score-item">
                        <span class="score-label">Issues:</span>
                        <span class="score-value">${issuesFound}</span>
                    </span>
                </div>
            </div>
            <div style="display:flex; gap:0.5rem; flex-shrink:0;">
                <button class="btn-view-analysis" 
                        onclick="viewPRAnalysis(${prNumber}, ${repoId})">
                    View Details
                </button>
                ${!isPosted ? `
                <button class="btn-post-analysis" 
                        onclick="postAnalysisToGitHub(${prNumber}, ${repoId}, this)"
                        style="padding:0.625rem 1rem; background:#10b981; color:white; 
                               border:none; border-radius:0.5rem; font-weight:600; 
                               cursor:pointer;">
                    Post to GitHub
                </button>` : `
                <span style="color:#10b981; font-weight:600; font-size:0.875rem; 
                             display:flex; align-items:center;">
                    ✓ Posted
                </span>`}
            </div>
        </div>
    `;
}

function createAnalyzeButtonHTML(prNumber, repoId) {
    return `
        <div style="margin-top:0.75rem;">
            <button onclick="triggerAnalysis(${prNumber}, ${repoId}, this)"
                    style="padding:0.5rem 1rem; background:var(--primary); color:white;
                           border:none; border-radius:0.5rem; font-weight:600; 
                           cursor:pointer; font-size:0.875rem;">
                🤖 Analyze with AI
            </button>
        </div>
    `;
}

function getScoreClass(score) {
    if (score >= 80) return 'good';
    if (score >= 60) return 'warning';
    return 'danger';
}

async function triggerAnalysis(prNumber, repoId, btn) {
    btn.textContent = '⏳ Analyzing...';
    btn.disabled = true;
    try {
        await apiRequest(
            `/api/repositories/${repoId}/pulls/${prNumber}/analyze/`, 'POST'
        );
        showToast('Analysis started! Refresh in ~15 seconds', 'success');
        setTimeout(() => initializePRIndicators(), 15000);
    } catch (e) {
        showToast('Failed to start analysis', 'error');
        btn.textContent = '🤖 Analyze with AI';
        btn.disabled = false;
    }
}

async function viewPRAnalysis(prNumber, repoId) {
    try {
        const analysis = await apiRequest(
            `/api/repositories/${repoId}/pulls/${prNumber}/analysis/`
        );
        showAnalysisModal(analysis, prNumber, repoId);
    } catch (e) {
        showToast('Failed to load analysis', 'error');
    }
}

async function postAnalysisToGitHub(prNumber, repoId, btn) {
    btn.textContent = '⏳ Posting...';
    btn.disabled = true;
    try {
        await apiRequest(
            `/api/repositories/${repoId}/pulls/${prNumber}/post-analysis/`, 'POST'
        );
        showToast('Comment posted to GitHub! ✅', 'success');
        // Replace button with "Posted" text
        btn.outerHTML = `<span style="color:#10b981; font-weight:600; font-size:0.875rem;">✓ Posted</span>`;
    } catch (e) {
        showToast('Failed to post comment', 'error');
        btn.textContent = 'Post to GitHub';
        btn.disabled = false;
    }
}

function showAnalysisModal(analysis, prNumber, repoId) {
    const existing = document.querySelector('.analysis-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.className = 'analysis-modal';
    modal.innerHTML = `
        <div class="analysis-modal-overlay" onclick="closeAnalysisModal()"></div>
        <div class="analysis-modal-content">
            <div class="analysis-modal-header">
                <h2>🤖 AI Code Review — PR #${prNumber}</h2>
                <button class="modal-close" onclick="closeAnalysisModal()">✕</button>
            </div>
            <div class="analysis-modal-body">
                <div class="analysis-section">
                    <h3>Summary</h3>
                    <p>${analysis.summary}</p>
                </div>
                <div class="analysis-scores-grid">
                    <div class="score-card">
                        <div class="score-card-value ${getScoreClass(analysis.security_score)}">${analysis.security_score}</div>
                        <div class="score-card-label">Security</div>
                    </div>
                    <div class="score-card">
                        <div class="score-card-value ${getScoreClass(analysis.performance_score)}">${analysis.performance_score}</div>
                        <div class="score-card-label">Performance</div>
                    </div>
                    <div class="score-card">
                        <div class="score-card-value ${getScoreClass(analysis.quality_score)}">${analysis.quality_score}</div>
                        <div class="score-card-label">Quality</div>
                    </div>
                    <div class="score-card">
                        <div class="score-card-value">${analysis.complexity_score}</div>
                        <div class="score-card-label">Complexity</div>
                    </div>
                </div>
                ${renderIssuesSection('🔴 Security Issues', analysis.security_issues)}
                ${renderIssuesSection('🚀 Performance Issues', analysis.performance_issues)}
                ${renderIssuesSection('💡 Code Quality', analysis.code_smells)}
                ${analysis.positive_points?.length ? `
                    <div class="analysis-section">
                        <h3>✅ Positive Points</h3>
                        <ul class="positive-points-list">
                            ${analysis.positive_points.map(p => `<li>${p}</li>`).join('')}
                        </ul>
                    </div>` : ''}
                <div class="analysis-metadata">
                    <span>⏱️ ${analysis.analysis_time?.toFixed(2)}s</span>
                    <span>🎫 ${analysis.tokens_used?.toLocaleString()} tokens</span>
                    <span>${analysis.comment_posted ? '✅ Posted to GitHub' : '⏳ Not posted yet'}</span>
                </div>
            </div>
            <div class="analysis-modal-footer">
                ${!analysis.comment_posted ? `
                    <button class="btn-primary" 
                            onclick="postAnalysisToGitHub(${prNumber}, ${repoId}, this); closeAnalysisModal();">
                        Post to GitHub
                    </button>` : ''}
                <button class="btn-secondary" onclick="closeAnalysisModal()">Close</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    setTimeout(() => modal.classList.add('show'), 10);
}

function renderIssuesSection(title, issues) {
    if (!issues || issues.length === 0) return '';
    return `
        <div class="analysis-section">
            <h3>${title}</h3>
            <div class="issues-list">
                ${issues.map(issue => `
                    <div class="issue-card ${issue.severity || 'low'}">
                        <div class="issue-header">
                            <span class="issue-severity">${(issue.severity || 'LOW').toUpperCase()}</span>
                            ${issue.line ? `<span class="issue-line">Line ${issue.line}</span>` : ''}
                        </div>
                        <p class="issue-description"><strong>Issue:</strong> ${issue.issue}</p>
                        ${issue.recommendation ? `
                            <p class="issue-recommendation">
                                <strong>💡 Fix:</strong> ${issue.recommendation}
                            </p>` : ''}
                    </div>`).join('')}
            </div>
        </div>`;
}

function closeAnalysisModal() {
    const modal = document.querySelector('.analysis-modal');
    if (modal) {
        modal.classList.remove('show');
        setTimeout(() => modal.remove(), 300);
    }
}