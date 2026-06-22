/**
 * Intent Capture Page Logic
 * Handles loading pending intent flags, rendering forms, and submitting answers.
 */

document.addEventListener('DOMContentLoaded', async () => {
    if (!await checkAuth()) {
        window.location.href = '/';
        return;
    }

    await loadUserInfo();
    await loadIntentFlags();
});

// ── Globals ──────────────────────────────────────────────────────────────
let currentFlags = [];
let repoId = null;
let prNumber = null;

// ── Parse URL params ─────────────────────────────────────────────────────
function getUrlParams() {
    const params = new URLSearchParams(window.location.search);
    return {
        repoId: params.get('repo_id'),
        prNumber: params.get('pr_number'),
    };
}

// ── Load user info ───────────────────────────────────────────────────────
async function loadUserInfo() {
    try {
        const user = await apiRequest('/api/user/me/');
        const userNameEl = document.getElementById('userName');
        const userAvatarEl = document.getElementById('userAvatar');
        if (userNameEl) userNameEl.textContent = user.github_login || user.username;
        if (userAvatarEl) userAvatarEl.src = user.github_avatar_url || '';
    } catch (e) {
        console.error('Failed to load user info', e);
    }
}

// ── Load intent flags ────────────────────────────────────────────────────
async function loadIntentFlags() {
    const params = getUrlParams();
    repoId = params.repoId;
    prNumber = params.prNumber;

    if (!repoId || !prNumber) {
        document.getElementById('flagsContainer').innerHTML = `
            <div class="empty-state">
                <h3>Missing Parameters</h3>
                <p>Please access this page from a PR with pending intent flags.</p>
                <a href="/dashboard/" class="btn-primary">Go to Dashboard</a>
            </div>`;
        return;
    }

    try {
        const flags = await apiRequest(`/api/repositories/${repoId}/pulls/${prNumber}/intent-flags/`);
        currentFlags = flags;

        // Update header
        const titleEl = document.getElementById('intentTitle');
        const subtitleEl = document.getElementById('intentSubtitle');
        if (titleEl) titleEl.textContent = `Intent Capture — PR #${prNumber}`;
        if (subtitleEl) subtitleEl.textContent = `${flags.length} decision${flags.length !== 1 ? 's' : ''} detected that need your explanation`;

        updateProgress();
        renderFlags();
    } catch (e) {
        console.error('Error loading intent flags:', e);
        document.getElementById('flagsContainer').innerHTML = `
            <div class="empty-state">
                <h3>No Flags Found</h3>
                <p>No intent flags were detected for this PR. The code looks clean! 🎉</p>
                <a href="/dashboard/" class="btn-primary">Back to Dashboard</a>
            </div>`;
    }
}

// ── Update progress ──────────────────────────────────────────────────────
function updateProgress() {
    const total = currentFlags.length;
    const captured = currentFlags.filter(f => f.status === 'captured').length;
    const dismissed = currentFlags.filter(f => f.status === 'dismissed').length;
    const done = captured + dismissed;
    const pending = total - done;
    const pct = total > 0 ? Math.round((done / total) * 100) : 0;

    const pendingEl = document.getElementById('pendingCount');
    const capturedEl = document.getElementById('capturedCount');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');

    if (pendingEl) pendingEl.textContent = pending;
    if (capturedEl) capturedEl.textContent = captured;
    if (progressFill) progressFill.style.width = `${pct}%`;
    if (progressText) progressText.textContent = pending > 0
        ? `${done} of ${total} decisions documented (${pct}%)`
        : 'All decisions documented! ✨';

    // Show all-done state
    if (pending === 0 && total > 0) {
        document.getElementById('flagsContainer').classList.add('hidden');
        document.getElementById('allDoneState').classList.remove('hidden');
    }
}

// ── Render flags ─────────────────────────────────────────────────────────
function renderFlags() {
    const container = document.getElementById('flagsContainer');

    const pendingFlags = currentFlags.filter(f => f.status === 'pending');
    const capturedFlags = currentFlags.filter(f => f.status === 'captured' || f.status === 'dismissed');

    if (pendingFlags.length === 0 && capturedFlags.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
                    <path d="M22 11.08V12a10 10 0 11-5.93-9.14"></path>
                    <polyline points="22 4 12 14.01 9 11.01"></polyline>
                </svg>
                <h3>No Pending Flags</h3>
                <p>All intent has been captured for this PR.</p>
            </div>`;
        return;
    }

    let html = '';

    // Pending flags
    for (const flag of pendingFlags) {
        html += renderFlagCard(flag);
    }

    // Captured flags (collapsed)
    if (capturedFlags.length > 0) {
        html += `
        <div class="captured-section">
            <h3 class="captured-section-title" onclick="this.parentElement.classList.toggle('expanded')">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="6 9 12 15 18 9"></polyline>
                </svg>
                ${capturedFlags.length} Already Documented
            </h3>
            <div class="captured-section-content">`;
        for (const flag of capturedFlags) {
            html += renderCapturedCard(flag);
        }
        html += `</div></div>`;
    }

    container.innerHTML = html;
}

// ── Render a pending flag card ───────────────────────────────────────────
function renderFlagCard(flag) {
    const typeLabels = {
        'magic_number': '🔢 Magic Number',
        'timeout': '⏱️ Timeout / Limit',
        'threshold': '📊 Threshold',
        'algorithm_choice': '🧮 Algorithm Choice',
        'string_assumption': '🔤 String Assumption',
    };

    const typeLabel = typeLabels[flag.flag_type] || flag.flag_type;
    const confidence = Math.round((flag.ai_confidence || 0) * 100);

    return `
    <div class="flag-card" id="flag-${flag.id}">
        <div class="flag-card-header">
            <div class="flag-type-badge">${typeLabel}</div>
            <div class="flag-location">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z"></path>
                    <polyline points="13 2 13 9 20 9"></polyline>
                </svg>
                ${flag.file_path}:${flag.line_number}
            </div>
            ${confidence > 0 ? `<div class="ai-confidence-badge" title="AI confidence: ${confidence}%">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"></circle>
                    <path d="M12 16v-4M12 8h.01"></path>
                </svg>
                AI: ${confidence}%
            </div>` : ''}
        </div>

        <div class="flag-code-snippet">
            <code>${escapeHtml(flag.code_snippet || '')}</code>
        </div>

        <div class="flag-question">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3M12 17h.01"></path>
            </svg>
            <span>${escapeHtml(flag.question)}</span>
        </div>

        <div class="flag-form">
            <textarea id="intent-text-${flag.id}" class="intent-textarea"
                placeholder="Explain the reasoning behind this decision..."
                rows="3"></textarea>

            <div class="flag-form-row">
                <select id="constraint-type-${flag.id}" class="constraint-select">
                    <option value="other">Category...</option>
                    <option value="legal">⚖️ Legal Requirement</option>
                    <option value="business_rule">💼 Business Rule</option>
                    <option value="performance">⚡ Performance Decision</option>
                    <option value="security">🔒 Security Policy</option>
                    <option value="ux">🎨 UX / Design Decision</option>
                    <option value="other">📝 Other</option>
                </select>

                <label class="review-checkbox">
                    <input type="checkbox" id="review-required-${flag.id}">
                    <span>Require review before changing</span>
                </label>
            </div>

            <div class="flag-actions">
                <button class="btn-capture" onclick="captureIntent(${flag.id})">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                    Save Intent
                </button>
                <button class="btn-dismiss" onclick="dismissIntent(${flag.id})">
                    Skip
                </button>
            </div>
        </div>
    </div>`;
}

// ── Render a captured flag card ──────────────────────────────────────────
function renderCapturedCard(flag) {
    const record = flag.intent_record;
    const statusIcon = flag.status === 'captured' ? '✅' : '⏭️';
    const statusLabel = flag.status === 'captured' ? 'Captured' : 'Dismissed';

    return `
    <div class="flag-card captured">
        <div class="flag-card-header">
            <div class="flag-type-badge captured">${statusIcon} ${statusLabel}</div>
            <div class="flag-location">${flag.file_path}:${flag.line_number}</div>
        </div>
        <div class="flag-question compact">
            <span>${escapeHtml(flag.question)}</span>
        </div>
        ${record ? `
        <div class="captured-answer">
            <div class="captured-answer-text">"${escapeHtml(record.intent_text)}"</div>
            <div class="captured-answer-meta">
                — ${record.author}
                ${record.review_required ? '<span class="review-badge">⚠️ Review Required</span>' : ''}
            </div>
        </div>` : ''}
    </div>`;
}

// ── Capture intent ───────────────────────────────────────────────────────
async function captureIntent(flagId) {
    const intentText = document.getElementById(`intent-text-${flagId}`).value.trim();
    if (!intentText) {
        showToast('Please provide an explanation', 'error');
        return;
    }

    const constraintType = document.getElementById(`constraint-type-${flagId}`).value;
    const reviewRequired = document.getElementById(`review-required-${flagId}`).checked;

    const btn = document.querySelector(`#flag-${flagId} .btn-capture`);
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner-small"></div> Saving...';

    try {
        await apiRequest(`/api/intent-flags/${flagId}/capture/`, 'POST', {
            intent_text: intentText,
            constraint_type: constraintType,
            review_required: reviewRequired,
        });

        // Update local state
        const flag = currentFlags.find(f => f.id === flagId);
        if (flag) {
            flag.status = 'captured';
            flag.intent_record = {
                intent_text: intentText,
                constraint_type: constraintType,
                review_required: reviewRequired,
                author: document.getElementById('userName')?.textContent || 'You',
            };
        }

        showToast('Intent captured successfully! 🎯', 'success');
        updateProgress();
        renderFlags();
    } catch (e) {
        console.error('Error capturing intent:', e);
        showToast('Failed to save intent', 'error');
        btn.disabled = false;
        btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg> Save Intent`;
    }
}

// ── Dismiss intent ───────────────────────────────────────────────────────
async function dismissIntent(flagId) {
    try {
        await apiRequest(`/api/intent-flags/${flagId}/dismiss/`, 'POST');

        const flag = currentFlags.find(f => f.id === flagId);
        if (flag) flag.status = 'dismissed';

        showToast('Flag dismissed', 'info');
        updateProgress();
        renderFlags();
    } catch (e) {
        console.error('Error dismissing flag:', e);
        showToast('Failed to dismiss flag', 'error');
    }
}

// ── Helpers ──────────────────────────────────────────────────────────────
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
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
