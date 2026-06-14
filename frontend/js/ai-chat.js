/**
 * AI Chat Interface JavaScript
 * Handles WebSocket communication and chat UI
 */

let websocket = null;
let currentConversationId = null;
let currentUser = null;
let isConnected = false;
let currentAssistantMessage = null;

document.addEventListener('DOMContentLoaded', async () => {
    // Check authentication
    if (!await checkAuth()) {
        window.location.href = '/';
        return;
    }

    // Load user info
    await loadUserInfo();

    // Setup event listeners
    setupEventListeners();

    // Connect WebSocket
    connectWebSocket();

    // Load conversations
    await loadConversations();
});

function setupEventListeners() {
    // Logout
    document.getElementById('logoutBtn').addEventListener('click', handleLogout);

    // New chat
    document.getElementById('newChatBtn').addEventListener('click', startNewChat);

    // Clear chat
    document.getElementById('clearChatBtn').addEventListener('click', clearCurrentChat);

    // Chat input
    const chatInput = document.getElementById('chatInput');
    const sendBtn = document.getElementById('sendBtn');

    chatInput.addEventListener('input', handleInputChange);
    chatInput.addEventListener('keydown', handleKeyDown);
    sendBtn.addEventListener('click', sendMessage);

    // Example queries
    document.querySelectorAll('.example-query').forEach(btn => {
        btn.addEventListener('click', () => {
            const query = btn.dataset.query;
            chatInput.value = query;
            handleInputChange();
            sendMessage();
        });
    });
}

async function loadUserInfo() {
    try {
        currentUser = await apiRequest('/api/user/me/');
        document.getElementById('userName').textContent = currentUser.github_login || currentUser.username;
        document.getElementById('userAvatar').src = currentUser.github_avatar_url || 'https://via.placeholder.com/40';
    } catch (error) {
        showToast('Failed to load user info', 'error');
    }
}

function connectWebSocket() {
    // Determine WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/chat/`;

    console.log('Connecting to WebSocket:', wsUrl);

    // Show connecting status
    showConnectionStatus('Connecting...', false);

    try {
        websocket = new WebSocket(wsUrl);

        websocket.onopen = handleWebSocketOpen;
        websocket.onmessage = handleWebSocketMessage;
        websocket.onerror = handleWebSocketError;
        websocket.onclose = handleWebSocketClose;

    } catch (error) {
        console.error('WebSocket connection error:', error);
        showConnectionStatus('Connection failed', true);
        showToast('Failed to connect to chat service', 'error');
    }
}

function handleWebSocketOpen(event) {
    console.log('WebSocket connected');
    isConnected = true;
    showConnectionStatus('Connected', false);

    // Hide status after 2 seconds
    setTimeout(() => {
        document.getElementById('connectionStatus').classList.add('hidden');
    }, 2000);
}

function handleWebSocketMessage(event) {
    try {
        const data = JSON.parse(event.data);
        console.log('WebSocket message:', data.type);

        switch (data.type) {
            case 'connection':
                console.log('Connection confirmed:', data.message);
                break;

            case 'user_message':
                displayUserMessage(data.message, data.timestamp);
                break;

            case 'typing':
                toggleTypingIndicator(data.is_typing);
                break;

            case 'assistant_message_chunk':
                appendAssistantMessageChunk(data.content);
                break;

            case 'assistant_message_complete':
                completeAssistantMessage();
                break;

            case 'history':
                displayConversationHistory(data.messages);
                break;

            case 'new_conversation':
                currentConversationId = data.conversation_id;
                break;

            case 'error':
                showToast(data.message, 'error');
                toggleTypingIndicator(false);
                break;
        }
    } catch (error) {
        console.error('Error parsing WebSocket message:', error);
    }
}

function handleWebSocketError(event) {
    console.error('WebSocket error:', event);
    isConnected = false;
    showConnectionStatus('Connection error', true);
    showToast('Chat connection error', 'error');
}

function handleWebSocketClose(event) {
    console.log('WebSocket closed:', event.code, event.reason);
    isConnected = false;
    showConnectionStatus('Disconnected', true);

    // Attempt to reconnect after 3 seconds
    setTimeout(() => {
        if (!isConnected) {
            console.log('Attempting to reconnect...');
            connectWebSocket();
        }
    }, 3000);
}

function handleInputChange() {
    const input = document.getElementById('chatInput');
    const sendBtn = document.getElementById('sendBtn');

    // Enable/disable send button
    sendBtn.disabled = !input.value.trim();

    // Auto-resize textarea
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 150) + 'px';
}

function handleKeyDown(event) {
    // Send on Enter (without Shift)
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

function sendMessage() {
    const input = document.getElementById('chatInput');
    const message = input.value.trim();

    if (!message || !isConnected) return;

    // Clear input
    input.value = '';
    handleInputChange();

    // Hide welcome message if visible
    const welcomeMsg = document.querySelector('.welcome-message');
    if (welcomeMsg) {
        welcomeMsg.remove();
    }

    // Send via WebSocket
    websocket.send(JSON.stringify({
        type: 'chat_message',
        message: message,
        conversation_id: currentConversationId
    }));
}

function displayUserMessage(message, timestamp) {
    const messagesContainer = document.getElementById('chatMessages');

    const messageEl = document.createElement('div');
    messageEl.className = 'message user';
    messageEl.innerHTML = `
        <div class="message-avatar">
            <img src="${currentUser.github_avatar_url || 'https://via.placeholder.com/36'}" alt="You">
        </div>
        <div class="message-content">
            <div class="message-bubble">
                <div class="message-text">${processMessageContent(message, true)}</div>
            </div>
            <div class="message-timestamp">${formatTimestamp(timestamp)}</div>
        </div>
    `;

    messagesContainer.appendChild(messageEl);
    scrollToBottom();
}

function appendAssistantMessageChunk(chunk) {
    const messagesContainer = document.getElementById('chatMessages');

    // Create message element if doesn't exist
    if (!currentAssistantMessage) {
        currentAssistantMessage = document.createElement('div');
        currentAssistantMessage.className = 'message assistant';
        currentAssistantMessage.innerHTML = `
            <div class="message-avatar">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="3"></circle>
                    <path d="M12 1v6m0 6v6m5.2-13.2l-4.2 4.2m0 6l4.2 4.2M23 12h-6m-6 0H5m13.2 5.2l-4.2-4.2m0-6l4.2-4.2"></path>
                </svg>
            </div>
            <div class="message-content">
                <div class="message-bubble">
                    <div class="message-text"></div>
                </div>
                <div class="message-timestamp">${formatTimestamp(new Date().toISOString())}</div>
            </div>
        `;
        messagesContainer.appendChild(currentAssistantMessage);
    }

    // Append chunk to message text
    const messageText = currentAssistantMessage.querySelector('.message-text');
    const currentText = messageText.dataset.rawContent || '';
    const newText = currentText + chunk;
    messageText.dataset.rawContent = newText;

    // Render markdown
    messageText.innerHTML = processMessageContent(newText, false);

    // Highlight code blocks
    highlightCodeBlocks();

    scrollToBottom();
}

function completeAssistantMessage() {
    currentAssistantMessage = null;
    toggleTypingIndicator(false);
}

function displayConversationHistory(messages) {
    const messagesContainer = document.getElementById('chatMessages');
    messagesContainer.innerHTML = '';

    messages.forEach(msg => {
        if (msg.role === 'user') {
            displayUserMessage(msg.content, msg.timestamp);
        } else {
            const messageEl = document.createElement('div');
            messageEl.className = 'message assistant';
            messageEl.innerHTML = `
                <div class="message-avatar">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="3"></circle>
                        <path d="M12 1v6m0 6v6m5.2-13.2l-4.2 4.2m0 6l4.2 4.2M23 12h-6m-6 0H5m13.2 5.2l-4.2-4.2m0-6l4.2-4.2"></path>
                    </svg>
                </div>
                <div class="message-content">
                    <div class="message-bubble">
                        <div class="message-text">${processMessageContent(msg.content, false)}</div>
                    </div>
                    <div class="message-timestamp">${formatTimestamp(msg.timestamp)}</div>
                </div>
            `;
            messagesContainer.appendChild(messageEl);
        }
    });

    highlightCodeBlocks();
    scrollToBottom();
}

function toggleTypingIndicator(show) {
    const indicator = document.getElementById('typingIndicator');
    if (show) {
        indicator.classList.remove('hidden');
    } else {
        indicator.classList.add('hidden');
    }
    scrollToBottom();
}

function scrollToBottom() {
    const messagesContainer = document.getElementById('chatMessages');
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

async function loadConversations() {
    try {
        const conversations = await apiRequest('/api/conversations/');
        displayConversations(conversations);
    } catch (error) {
        console.error('Failed to load conversations:', error);
        document.getElementById('conversationsList').innerHTML =
            '<div class="empty-state">No conversations yet</div>';
    }
}

function displayConversations(conversations) {
    const container = document.getElementById('conversationsList');

    if (conversations.length === 0) {
        container.innerHTML = '<div class="empty-state">No conversations yet</div>';
        return;
    }

    container.innerHTML = conversations.map(conv => `
        <div class="conversation-item ${conv.id === currentConversationId ? 'active' : ''}" 
             data-id="${conv.id}"
             onclick="loadConversation(${conv.id})">
            <div class="conversation-title">${escapeHtml(conv.title)}</div>
            <div class="conversation-meta">
                ${conv.message_count} messages • ${formatDate(conv.updated_at)}
            </div>
        </div>
    `).join('');
}

async function loadConversation(conversationId) {
    try {
        currentConversationId = conversationId;

        // Update active state
        document.querySelectorAll('.conversation-item').forEach(item => {
            item.classList.remove('active');
        });
        document.querySelector(`[data-id="${conversationId}"]`)?.classList.add('active');

        // Request history from WebSocket
        websocket.send(JSON.stringify({
            type: 'load_history',
            conversation_id: conversationId
        }));

    } catch (error) {
        showToast('Failed to load conversation', 'error');
    }
}

function startNewChat() {
    // Clear current chat
    currentConversationId = null;
    currentAssistantMessage = null;

    // Clear messages
    const messagesContainer = document.getElementById('chatMessages');
    messagesContainer.innerHTML = `
        <div class="welcome-message">
            <div class="welcome-icon">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                </svg>
            </div>
            <h2>New Conversation</h2>
            <p>Ask me anything about your repositories!</p>
        </div>
    `;

    // Clear active conversation
    document.querySelectorAll('.conversation-item').forEach(item => {
        item.classList.remove('active');
    });

    // Request new conversation from server
    websocket.send(JSON.stringify({
        type: 'new_conversation'
    }));
}
// ai-chat.js
async function clearCurrentChat() {
    if (!currentConversationId) {
        startNewChat();
        return;
    }

    if (!confirm('Are you sure you want to delete this conversation entirely?')) {
        return;
    }

    try {
        // 1. Delete from backend
        await apiRequest(`/api/conversations/${currentConversationId}/delete/`, 'DELETE');

        // 2. Clear local tracking
        currentConversationId = null;
        currentAssistantMessage = null;

        // 3. Clear the sidebar list in the UI immediately so it doesn't look "stuck"
        const sidebarList = document.getElementById('conversationsList');
        sidebarList.innerHTML = '<div class="loading-state">Updating...</div>';

        // 4. Force a refresh of the sidebar from the server
        await loadConversations();

        // 5. Reset main chat window to welcome screen
        startNewChat();

        showToast('Conversation deleted permanently', 'success');
    } catch (error) {
        console.error('Delete error:', error);
        showToast('Failed to delete conversation', 'error');
    }
}
function showConnectionStatus(message, isError) {
    const statusEl = document.getElementById('connectionStatus');
    const statusText = document.getElementById('statusText');

    statusText.textContent = message;
    statusEl.classList.remove('hidden');

    if (isError) {
        statusEl.classList.add('error');
        statusEl.classList.remove('connected');
    } else if (message === 'Connected') {
        statusEl.classList.add('connected');
        statusEl.classList.remove('error');
    } else {
        statusEl.classList.remove('error', 'connected');
    }
}

function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;

    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;

    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatDate(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diffTime = Math.abs(now - date);
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

    if (diffDays < 1) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays} days ago`;

    return date.toLocaleDateString();
}

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

function handleLogout() {
    if (confirm('Are you sure you want to logout?')) {
        apiRequest('/api/auth/logout/', 'POST')
            .then(() => {
                window.location.href = '/';
            })
            .catch((error) => {
                console.error('Logout failed:', error);
                showToast('Logout failed', 'error');
            });
    }
}
