// auth.js — shared auth utilities for non-index pages

/**
 * Returns stored JWT or redirects to sign-in if missing.
 */
function requireAuth() {
    const jwt = localStorage.getItem('jwt');
    if (!jwt) { window.location.href = '/'; return null; }
    return jwt;
}

/**
 * Returns Authorization header object.
 */
function authHeaders() {
    return {
        'Authorization': `Bearer ${localStorage.getItem('jwt')}`,
        'Content-Type': 'application/json'
    };
}

/**
 * Clears session and redirects to sign-in.
 */
function logout() {
    localStorage.clear();
    window.location.href = '/';
}

/**
 * Handles 401 responses — clears session and redirects.
 */
function handle401(res) {
    if (res.status === 401) { logout(); return true; }
    return false;
}
