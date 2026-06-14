/**
 * API Utility Functions
 * Handles all HTTP requests to the Django backend
 */

const API_BASE_URL = window.location.origin;

/**
 * Get CSRF token from cookies
 * Django requires CSRF token for POST, PUT, DELETE requests
 */
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

/**
 * Make an API request
 * @param {string} endpoint - API endpoint (e.g., '/api/user/me/')
 * @param {string} method - HTTP method (GET, POST, PUT, DELETE)
 * @param {object} data - Request body data (for POST, PUT)
 * @returns {Promise} - Response data
 */
async function apiRequest(endpoint, method = 'GET', data = null) {
    const url = `${API_BASE_URL}${endpoint}`;

    const headers = {
        'Content-Type': 'application/json',
    };

    // Add CSRF token for non-GET requests
    if (method !== 'GET') {
        headers['X-CSRFToken'] = getCookie('csrftoken');
    }

    const options = {
        method: method,
        headers: headers,
        credentials: 'include', // Include cookies for session authentication
    };

    // Add body for POST, PUT requests
    if (data && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
        options.body = JSON.stringify(data);
    }

    try {
        const response = await fetch(url, options);

        // Handle non-JSON responses (like redirects)
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            if (response.ok) {
                return { success: true };
            }
            throw new Error(`HTTP ${response.status}: ${responseData.error || responseData.detail || response.statusText}`);
        }

        const responseData = await response.json();

        if (!response.ok) {
            throw new Error(responseData.error || responseData.detail || `HTTP error! status: ${response.status}`);
        }

        return responseData;
    } catch (error) {
        console.error('API Request Error:', error);
        throw error;
    }
}

/**
 * Specific API methods for common operations
 */
const API = {
    // User operations
    getCurrentUser: () => apiRequest('/api/user/me/', 'GET'),
    logout: () => apiRequest('/api/auth/logout/', 'POST'),

    // Repository operations
    getRepositories: () => apiRequest('/api/repositories/', 'GET'),
    syncRepositories: () => apiRequest('/api/repositories/sync/', 'POST'),

    // Health check
    healthCheck: () => apiRequest('/api/health/', 'GET'),
};

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { apiRequest, API, getCookie };
}
