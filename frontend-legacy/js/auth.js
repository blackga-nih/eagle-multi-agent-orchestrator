/**
 * auth.js - Cognito Authentication Module
 *
 * Extracts all Amazon Cognito authentication logic into a standalone module.
 * Uses the window.Auth namespace pattern (not ES modules) because the
 * AmazonCognitoIdentity SDK is loaded as a global via CDN script tag.
 *
 * Prerequisites:
 *   - amazon-cognito-identity-js loaded via <script> tag (provides global AmazonCognitoIdentity)
 *   - CONFIG global object defined in index.html with: userPoolId, clientId, region, apiUrl
 *
 * Usage:
 *   Auth.init();
 *   Auth.login(email, password, onSuccess, onError);
 *   Auth.register(formData, onSuccess, onError);
 *   Auth.confirmSignUp(email, verificationCode, tenantId, isAdmin, onSuccess, onError);
 *   Auth.logout();
 *   Auth.getCurrentUser();
 *   Auth.getToken();
 */
(function () {
    'use strict';

    // ---------------------------------------------------------------------------
    // Internal state
    // ---------------------------------------------------------------------------

    /** @type {AmazonCognitoIdentity.CognitoUser|null} */
    var cognitoUser = null;

    /**
     * Authenticated user context.
     * @type {{ email: string, tenant_id: string, subscription_tier: string, user_id: string, token: string }|null}
     */
    var currentUser = null;

    /** @type {AmazonCognitoIdentity.CognitoUserPool|null} */
    var userPool = null;

    // ---------------------------------------------------------------------------
    // Public API
    // ---------------------------------------------------------------------------

    /**
     * Initialize the Cognito User Pool.
     *
     * Must be called after the global CONFIG object is available (typically at
     * page load). Throws if CONFIG or AmazonCognitoIdentity are missing.
     */
    /** @type {boolean} Whether the backend is in DEV_MODE (no Cognito required) */
    var devMode = false;

    function init() {
        if (typeof CONFIG === 'undefined') {
            throw new Error('Auth.init(): CONFIG global is not defined. Define it before calling init().');
        }

        // Check if backend is in DEV_MODE — skip Cognito if so
        try {
            var xhr = new XMLHttpRequest();
            xhr.open('GET', (CONFIG.apiUrl || '') + '/api/health', false); // synchronous
            xhr.send();
            if (xhr.status === 200) {
                var health = JSON.parse(xhr.responseText);
                if (health.features && health.features.dev_mode === true) {
                    devMode = true;
                    currentUser = {
                        email: 'dev@nci.nih.gov',
                        tenant_id: 'dev-tenant',
                        subscription_tier: 'premium',
                        user_id: 'dev-user',
                        token: 'dev-mode-token'
                    };
                    console.log('[Auth] DEV_MODE detected — Cognito bypassed, dev user set');
                    return; // skip Cognito init
                }
            }
        } catch (e) {
            console.warn('[Auth] Could not check health endpoint:', e.message);
        }

        if (typeof AmazonCognitoIdentity === 'undefined') {
            throw new Error('Auth.init(): AmazonCognitoIdentity SDK is not loaded. Include the CDN script tag before this file.');
        }

        var poolData = {
            UserPoolId: CONFIG.userPoolId,
            ClientId: CONFIG.clientId
        };

        userPool = new AmazonCognitoIdentity.CognitoUserPool(poolData);
    }

    /**
     * Register a new user with Cognito.
     *
     * @param {Object} formData - Registration form values.
     * @param {string} formData.firstName   - User's first name (given_name).
     * @param {string} formData.lastName    - User's last name (family_name).
     * @param {string} formData.email       - Email address (also used as the username).
     * @param {string} formData.password    - Chosen password.
     * @param {string} formData.tenantId    - Organization / tenant identifier.
     * @param {string} formData.tier        - Subscription tier (basic | advanced | premium).
     * @param {string} formData.role        - User role (user | admin).
     * @param {Function} onSuccess - Called with (result, isAdmin) on successful sign-up.
     * @param {Function} onError   - Called with (Error) on failure.
     */
    function register(formData, onSuccess, onError) {
        if (!userPool) {
            onError(new Error('Auth not initialized. Call Auth.init() first.'));
            return;
        }

        var attributeList = [
            new AmazonCognitoIdentity.CognitoUserAttribute({
                Name: 'email',
                Value: formData.email
            }),
            new AmazonCognitoIdentity.CognitoUserAttribute({
                Name: 'given_name',
                Value: formData.firstName
            }),
            new AmazonCognitoIdentity.CognitoUserAttribute({
                Name: 'family_name',
                Value: formData.lastName
            }),
            new AmazonCognitoIdentity.CognitoUserAttribute({
                Name: 'custom:tenant_id',
                Value: formData.tenantId
            }),
            new AmazonCognitoIdentity.CognitoUserAttribute({
                Name: 'custom:subscription_tier',
                Value: formData.tier
            })
        ];

        var isAdmin = formData.role === 'admin';

        userPool.signUp(formData.email, formData.password, attributeList, null, function (err, result) {
            if (err) {
                onError(err);
                return;
            }
            onSuccess(result, isAdmin);
        });
    }

    /**
     * Confirm a user's sign-up with the verification code emailed by Cognito.
     *
     * If the user registered as an admin, this function will also call the
     * backend POST /api/admin/add-to-group endpoint to grant admin group
     * membership after successful confirmation.
     *
     * @param {string}   email            - The user's email / username.
     * @param {string}   verificationCode - 6-digit code from email.
     * @param {string}   tenantId         - Tenant identifier for admin group assignment.
     * @param {boolean}  isAdmin          - Whether to request admin group membership.
     * @param {Function} onSuccess        - Called with (message: string) on success.
     * @param {Function} onError          - Called with (Error) on failure.
     */
    function confirmSignUp(email, verificationCode, tenantId, isAdmin, onSuccess, onError) {
        if (!userPool) {
            onError(new Error('Auth not initialized. Call Auth.init() first.'));
            return;
        }

        var userData = {
            Username: email,
            Pool: userPool
        };

        var confirmUser = new AmazonCognitoIdentity.CognitoUser(userData);

        confirmUser.confirmRegistration(verificationCode, true, function (err, result) {
            if (err) {
                onError(err);
                return;
            }

            if (isAdmin) {
                // Attempt to add the confirmed user to the admin group via the backend API
                fetch(CONFIG.apiUrl + '/api/admin/add-to-group', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        email: email,
                        tenant_id: tenantId
                    })
                })
                    .then(function (response) {
                        if (response.ok) {
                            onSuccess('Email verified and admin access granted! You can now login with admin privileges.');
                        } else {
                            onSuccess('Email verified! Admin access pending - contact support.');
                        }
                    })
                    .catch(function () {
                        onSuccess('Email verified! Admin access pending - contact support.');
                    });
            } else {
                onSuccess('Email verified successfully! You can now login.');
            }
        });
    }

    /**
     * Authenticate a user with email and password.
     *
     * On success, extracts the JWT ID token and key claims (email,
     * custom:tenant_id, custom:subscription_tier, sub) and stores them in
     * internal state. The onSuccess callback receives the assembled user object.
     *
     * @param {string}   email     - User's email / Cognito username.
     * @param {string}   password  - User's password.
     * @param {Function} onSuccess - Called with (user: {email, tenant_id, subscription_tier, user_id, token}).
     * @param {Function} onError   - Called with (Error) on failure.
     */
    function login(email, password, onSuccess, onError) {
        if (devMode) {
            // DEV_MODE: skip Cognito, create a mock user from /api/user/me
            currentUser = {
                email: email || 'dev@nci.nih.gov',
                tenant_id: 'dev-tenant',
                subscription_tier: 'premium',
                user_id: 'dev-user',
                token: 'dev-mode-token'
            };
            onSuccess(currentUser);
            return;
        }
        if (!userPool) {
            onError(new Error('Auth not initialized. Call Auth.init() first.'));
            return;
        }

        var authenticationData = {
            Username: email,
            Password: password
        };

        var authenticationDetails = new AmazonCognitoIdentity.AuthenticationDetails(authenticationData);

        var userData = {
            Username: email,
            Pool: userPool
        };

        cognitoUser = new AmazonCognitoIdentity.CognitoUser(userData);

        cognitoUser.authenticateUser(authenticationDetails, {
            onSuccess: function (result) {
                var idToken = result.getIdToken().getJwtToken();
                var payload = result.getIdToken().payload;

                currentUser = {
                    email: payload.email,
                    tenant_id: payload['custom:tenant_id'],
                    subscription_tier: payload['custom:subscription_tier'] || 'basic',
                    user_id: payload.sub,
                    token: idToken
                };

                onSuccess(currentUser);
            },
            onFailure: function (err) {
                onError(err);
            }
        });
    }

    /**
     * Sign out the current Cognito user and clear internal state.
     */
    function logout() {
        if (cognitoUser) {
            cognitoUser.signOut();
        }
        cognitoUser = null;
        currentUser = null;
    }

    /**
     * Return the current authenticated user object, or null if not logged in.
     *
     * @returns {{ email: string, tenant_id: string, subscription_tier: string, user_id: string, token: string }|null}
     */
    function getCurrentUser() {
        return currentUser;
    }

    /**
     * Return the current JWT ID token, or null if not logged in.
     *
     * @returns {string|null}
     */
    function getToken() {
        return currentUser ? currentUser.token : null;
    }

    // ---------------------------------------------------------------------------
    // Expose as window.Auth namespace
    // ---------------------------------------------------------------------------

    /**
     * Whether the backend is in DEV_MODE (Cognito bypassed).
     * @returns {boolean}
     */
    function isDevMode() {
        return devMode;
    }

    window.Auth = {
        init: init,
        register: register,
        confirmSignUp: confirmSignUp,
        login: login,
        logout: logout,
        getCurrentUser: getCurrentUser,
        getToken: getToken,
        isDevMode: isDevMode
    };
})();
