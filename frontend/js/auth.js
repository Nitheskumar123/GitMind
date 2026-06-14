/**
 * Authentication Utilities
 * Handles GitHub OAuth flow and user session management
 */

/**
 * Check if user is authenticated
 * @returns {Promise<boolean>} - True if authenticated, false otherwise
 */
async function checkAuth() {
    try {
        const user = await apiRequest('/api/user/me/');
        // User is authenticated if they have an id
        return !!user.id;
    } catch (error) {
        // If API call fails, user is not authenticated
        return false;
    }
}

/**
 * Get current user information
 * @returns {Promise<object>} - User data, or null if not authenticated
 */
async function getCurrentUser() {
    try {
        const user = await apiRequest('/api/user/me/');
        // Return user data if authenticated, null otherwise
        return user.id ? user : null;
    } catch (error) {
        console.error('Failed to get current user:', error);
        return null;
    }
}

/**
 * Initiate GitHub OAuth login
 */
function loginWithGitHub() {
    window.location.href = '/api/auth/github/';
}

/**
 * Logout user
 */
async function handleLogout() {
    try {
        await apiRequest('/api/auth/logout/', 'POST');
        window.location.href = '/';
    } catch (error) {
        console.error('Logout failed:', error);
        // Force redirect even if logout fails
        window.location.href = '/';
    }
}

/**
 * Protect page - redirect to home if not authenticated
 * Call this on protected pages (like dashboard)
 */
async function requireAuth() {
    const isAuthenticated = await checkAuth();
    if (!isAuthenticated) {
        window.location.href = '/';
    }
}

/**
 * Store user data in session storage
 * @param {object} user - User data to store
 */
function storeUserData(user) {
    try {
        sessionStorage.setItem('user', JSON.stringify(user));
    } catch (error) {
        console.error('Failed to store user data:', error);
    }
}

/**
 * Get user data from session storage
 * @returns {object|null} - User data or null
 */
function getUserData() {
    try {
        const userData = sessionStorage.getItem('user');
        return userData ? JSON.parse(userData) : null;
    } catch (error) {
        console.error('Failed to get user data:', error);
        return null;
    }
}

/**
 * Clear user data from session storage
 */
function clearUserData() {
    try {
        sessionStorage.removeItem('user');
    } catch (error) {
        console.error('Failed to clear user data:', error);
    }
}

/**
 * Handle OAuth callback
 * This is called on the callback page after GitHub redirects back
 */
function handleOAuthCallback() {
    const urlParams = new URLSearchParams(window.location.search);
    const error = urlParams.get('error');

    if (error) {
        console.error('OAuth error:', error);
        alert('GitHub authentication failed. Please try again.');
        window.location.href = '/';
        return;
    }

    // If no error, the backend should have handled the OAuth flow
    // and set up the session. Redirect to dashboard.
    window.location.href = '/dashboard/';
}

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        checkAuth,
        getCurrentUser,
        loginWithGitHub,
        handleLogout,
        requireAuth,
        storeUserData,
        getUserData,
        clearUserData,
        handleOAuthCallback,
    };
}
