/**
 * Markdown Renderer with Code Highlighting
 * Converts markdown to HTML and highlights code blocks
 */

// Configure marked.js
if (typeof marked !== 'undefined') {
    marked.setOptions({
        breaks: true,
        gfm: true,
        headerIds: false,
        mangle: false
    });
}

/**
 * Render markdown to HTML
 * @param {string} markdown - Markdown text
 * @returns {string} - HTML string
 */
function renderMarkdown(markdown) {
    if (!markdown) return '';

    try {
        // Convert markdown to HTML
        let html = marked.parse(markdown);

        // Wrap code blocks for better styling
        html = wrapCodeBlocks(html);

        return html;
    } catch (error) {
        console.error('Error rendering markdown:', error);
        return escapeHtml(markdown);
    }
}

/**
 * Wrap code blocks with header and copy button
 * @param {string} html - HTML string
 * @returns {string} - HTML with wrapped code blocks
 */
function wrapCodeBlocks(html) {
    // Find all <pre><code> blocks
    const codeBlockRegex = /<pre><code class="language-(\w+)">([\s\S]*?)<\/code><\/pre>/g;

    return html.replace(codeBlockRegex, (match, language, code) => {
        return `
            <div class="code-block-wrapper">
                <div class="code-block-header">
                    <span class="code-language">${language}</span>
                    <button class="btn-copy-code" onclick="copyCode(this)">Copy</button>
                </div>
                <pre><code class="language-${language}">${code}</code></pre>
            </div>
        `;
    });
}

/**
 * Highlight all code blocks on page
 */
function highlightCodeBlocks() {
    if (typeof hljs !== 'undefined') {
        document.querySelectorAll('pre code').forEach((block) => {
            // Only highlight if not already highlighted
            if (!block.dataset.highlighted) {
                hljs.highlightElement(block);
                block.dataset.highlighted = 'yes';
            }
        });
    }
}

/**
 * Copy code to clipboard
 * @param {HTMLElement} button - Copy button element
 */
function copyCode(button) {
    const codeBlock = button.closest('.code-block-wrapper').querySelector('code');
    const code = codeBlock.textContent;

    navigator.clipboard.writeText(code).then(() => {
        const originalText = button.textContent;
        button.textContent = 'Copied!';
        button.classList.add('copied');

        setTimeout(() => {
            button.textContent = originalText;
            button.classList.remove('copied');
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy code:', err);
    });
}

/**
 * Escape HTML special characters
 * @param {string} text - Text to escape
 * @returns {string} - Escaped text
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Process message content for display
 * @param {string} content - Message content
 * @param {boolean} isUser - Is user message (don't render markdown)
 * @returns {string} - Processed HTML
 */
function processMessageContent(content, isUser = false) {
    if (isUser) {
        // User messages: just escape HTML, preserve line breaks
        return escapeHtml(content).replace(/\n/g, '<br>');
    } else {
        // AI messages: render markdown
        return renderMarkdown(content);
    }
}

// Export functions
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        renderMarkdown,
        highlightCodeBlocks,
        processMessageContent,
        copyCode
    };
}
