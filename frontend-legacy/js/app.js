/**
 * app.js - Main Application Orchestrator
 *
 * Wires together all frontend modules and exposes global functions
 * referenced by onclick handlers in index.html. This file is the
 * single entry point that coordinates Auth, ApiClient, ChatCore,
 * UI, and AdminPanels.
 *
 * Uses the window.App namespace pattern (not ES modules) to stay
 * consistent with the rest of the frontend architecture.
 *
 * Prerequisites (loaded as global scripts before this file):
 *   - window.Auth              (init, register, confirmSignUp, login, logout, getCurrentUser, getToken)
 *   - window.ApiClient         (createSession, sendMessage, getUsage, getSessions, etc.)
 *   - window.ChatCore          (init, addMessage, sendMessage, setCurrentSession, clearMessages)
 *   - window.UI                (showView, showError, showSuccess, toggleGovBanner)
 *   - window.AdminPanels       (checkAdminAccess, showUsage, showSessions, etc.)
 *   - window.StreamClient      (streamMessage, abort)
 *   - window.SlashCommands     (init, destroy)
 *   - window.DocumentUpload    (init, getFiles, clearFiles, destroy)
 *   - window.SidebarPanel      (init, toggle, addAgentLog, updateChecklist, updateTools)
 *   - window.ChatEnhancements  (init, showWelcome, hideWelcome, destroy)
 *   - CONFIG global object (userPoolId, clientId, region, apiUrl)
 *   - DOM elements: #loginForm, #registerForm, #chatInterface, #userInfo,
 *     #usageInfo, #adminControls, and all form inputs
 *
 * Usage:
 *   Loaded last in the script order. Self-initializes on DOMContentLoaded.
 */
window.App = (function () {
    'use strict';

    // -------------------------------------------------------------------------
    // Initialization
    // -------------------------------------------------------------------------

    /**
     * Initialize the application.
     *
     * Called once on DOMContentLoaded. Sets up Auth and ChatCore modules,
     * then wires all global functions that index.html onclick handlers
     * reference.
     */
    function init() {
        Auth.init();
        ChatCore.init();

        // Initialize slash commands on the message input
        var messageInput = document.getElementById('messageInput');
        if (messageInput && window.SlashCommands) {
            SlashCommands.init(messageInput, function (command) {
                // When a slash command is selected, insert it into the input
                messageInput.value = command.prompt || command.label;
                messageInput.focus();
            });
        }

        // Initialize sidebar panel
        if (window.SidebarPanel) {
            SidebarPanel.init();
        }

        wireGlobalFunctions();

        // DEV_MODE: auto-login and skip to chat interface
        if (Auth.isDevMode()) {
            Auth.login(null, null, function () {
                showChatInterface();
            }, function () {});
        }
    }

    // -------------------------------------------------------------------------
    // Authentication Handlers
    // -------------------------------------------------------------------------

    /**
     * Handle the registration form submission.
     *
     * Collects values from the registration form fields, calls
     * Auth.register() with the assembled form data. On success,
     * shows a verification code input and verify button so the
     * user can confirm their email. On error, displays the error
     * message in #registerError.
     */
    function handleRegister() {
        var formData = {
            firstName: document.getElementById('regFirstName').value,
            lastName: document.getElementById('regLastName').value,
            email: document.getElementById('regEmail').value,
            password: document.getElementById('regPassword').value,
            tenantId: document.getElementById('regTenant').value,
            tier: document.getElementById('regTier').value,
            role: document.getElementById('regRole').value
        };

        Auth.register(
            formData,
            function onSuccess(result, isAdmin) {
                var successDiv = document.getElementById('registerSuccess');
                successDiv.textContent = 'Registration successful! Please check your email for verification code.';

                // Show admin notice if applicable
                if (isAdmin) {
                    var adminMsg = document.createElement('div');
                    var strongEl = document.createElement('strong');
                    strongEl.style.color = 'var(--nci-danger)';
                    strongEl.textContent = 'Admin access will be granted after verification';
                    adminMsg.appendChild(strongEl);
                    successDiv.appendChild(adminMsg);
                }

                // Create verification code input
                var verificationInput = document.createElement('input');
                verificationInput.type = 'text';
                verificationInput.id = 'verificationCode';
                verificationInput.placeholder = 'Enter verification code';
                verificationInput.style.cssText = 'margin: 10px 0; padding: 8px; width: 100%; border: 1px solid #ccc; border-radius: 4px;';

                // Create verify button
                var verifyButton = document.createElement('button');
                verifyButton.textContent = 'Verify';
                verifyButton.style.cssText = 'margin-top: 10px; padding: 8px 16px; background: var(--nci-primary); color: white; border: none; border-radius: 4px; cursor: pointer;';
                verifyButton.onclick = function () {
                    var code = document.getElementById('verificationCode').value;
                    Auth.confirmSignUp(
                        formData.email,
                        code,
                        formData.tenantId,
                        isAdmin,
                        function onVerifySuccess(message) {
                            UI.showSuccess('registerSuccess', message);
                        },
                        function onVerifyError(err) {
                            UI.showError('registerError', err.message);
                        }
                    );
                };

                successDiv.appendChild(verificationInput);
                successDiv.appendChild(verifyButton);

                // Clear any previous error
                UI.showError('registerError', '');
            },
            function onError(err) {
                UI.showError('registerError', err.message);
            }
        );
    }

    /**
     * Handle the login form submission.
     *
     * Collects email and password from the login form, calls
     * Auth.login(). On success, transitions to the chat interface.
     * On error, displays the error message in #loginError.
     */
    function handleLogin() {
        var email = document.getElementById('email').value;
        var password = document.getElementById('password').value;

        Auth.login(
            email,
            password,
            function onSuccess() {
                showChatInterface();
            },
            function onError(err) {
                UI.showError('loginError', err.message);
            }
        );
    }

    // -------------------------------------------------------------------------
    // Chat Interface
    // -------------------------------------------------------------------------

    /**
     * Transition from the login view to the chat interface.
     *
     * Hides the login and registration forms, shows the chat interface,
     * renders the user info card with email, organization, subscription
     * badge, and user ID. Then checks for admin access and creates a
     * new chat session.
     */
    function showChatInterface() {
        UI.showView('chatInterface');

        var user = Auth.getCurrentUser();

        // Determine badge class based on subscription tier
        var tierBadge = user.subscription_tier === 'premium' ? 'badge-premium' :
                        user.subscription_tier === 'advanced' ? 'badge-advanced' : 'badge-basic';

        // Build the user info card using safe DOM APIs (no innerHTML)
        var userInfoDiv = document.getElementById('userInfo');
        userInfoDiv.textContent = '';

        // Email row
        var emailP = document.createElement('p');
        var emailStrong = document.createElement('strong');
        emailStrong.textContent = 'Email:';
        emailP.appendChild(emailStrong);
        emailP.appendChild(document.createTextNode(' ' + user.email));

        // Organization row
        var orgP = document.createElement('p');
        var orgStrong = document.createElement('strong');
        orgStrong.textContent = 'Organization:';
        orgP.appendChild(orgStrong);
        orgP.appendChild(document.createTextNode(' ' + user.tenant_id));

        // Subscription row with badge
        var subP = document.createElement('p');
        var subStrong = document.createElement('strong');
        subStrong.textContent = 'Subscription:';
        subP.appendChild(subStrong);
        subP.appendChild(document.createTextNode(' '));
        var badge = document.createElement('span');
        badge.className = 'badge ' + tierBadge;
        badge.textContent = user.subscription_tier;
        subP.appendChild(badge);

        // User ID row
        var userIdP = document.createElement('p');
        var userIdStrong = document.createElement('strong');
        userIdStrong.textContent = 'User ID:';
        userIdP.appendChild(userIdStrong);
        userIdP.appendChild(document.createTextNode(' ' + user.user_id));

        userInfoDiv.appendChild(emailP);
        userInfoDiv.appendChild(orgP);
        userInfoDiv.appendChild(subP);
        userInfoDiv.appendChild(userIdP);

        // Check admin access (appends role badge to userInfoDiv if admin)
        AdminPanels.checkAdminAccess(userInfoDiv);

        // Initialize chat enhancements (welcome cards, health indicator, suggested prompts)
        if (window.ChatEnhancements) {
            var chatBoxEl = document.getElementById('chatBox');
            var inputAreaEl = document.querySelector('.input-area');
            if (chatBoxEl && inputAreaEl) {
                ChatEnhancements.init(chatBoxEl, inputAreaEl);
            }
        }

        // Initialize document upload below the input area
        if (window.DocumentUpload) {
            var inputArea = document.querySelector('.input-area');
            if (inputArea) {
                DocumentUpload.init(inputArea);
            }
        }

        // Create a new chat session
        createNewSession();
    }

    /**
     * Create a new chat session via the API.
     *
     * Calls ApiClient.createSession(). On success, stores the session
     * in ChatCore and displays a system message with the session ID.
     * On error, displays a system error message.
     */
    async function createNewSession() {
        try {
            var session = await ApiClient.createSession();
            ChatCore.setCurrentSession(session);
            ChatCore.addMessage('system', 'Session created: ' + session.session_id);
        } catch (error) {
            var errorText = error && error.message ? error.message : 'Unknown error';
            ChatCore.addMessage('system', 'Error creating session: ' + errorText);
        }
    }

    // -------------------------------------------------------------------------
    // Logout
    // -------------------------------------------------------------------------

    /**
     * Handle user logout.
     *
     * Signs out through Auth, hides the chat interface, shows the
     * login form, clears the chat messages, hides the usage info
     * panel, and hides admin controls.
     */
    function handleLogout() {
        Auth.logout();

        // Cleanup enhanced modules
        if (window.ChatEnhancements) {
            ChatEnhancements.destroy();
        }
        if (window.DocumentUpload) {
            DocumentUpload.destroy();
        }
        if (window.StreamClient) {
            StreamClient.abort();
        }

        UI.showView('loginForm');

        ChatCore.clearMessages();

        var usageInfo = document.getElementById('usageInfo');
        if (usageInfo) {
            usageInfo.textContent = '';
            usageInfo.style.display = 'none';
        }

        var adminControls = document.getElementById('adminControls');
        if (adminControls) {
            adminControls.style.display = 'none';
        }
    }

    // -------------------------------------------------------------------------
    // Form Toggling
    // -------------------------------------------------------------------------

    /**
     * Switch from the login form to the registration form.
     */
    function showRegisterForm() {
        UI.showView('registerForm');
    }

    /**
     * Switch from the registration form to the login form.
     */
    function showLoginForm() {
        UI.showView('loginForm');
    }

    // -------------------------------------------------------------------------
    // Global Function Wiring
    // -------------------------------------------------------------------------

    /**
     * Wire up all global functions referenced by onclick handlers in
     * index.html.
     *
     * Each window-level function maps to either an App method or
     * delegates directly to the appropriate module method.
     */
    function wireGlobalFunctions() {
        // Auth actions
        window.login = handleLogin;
        window.register = handleRegister;
        window.logout = handleLogout;

        // Form navigation
        window.showRegisterForm = showRegisterForm;
        window.showLoginForm = showLoginForm;

        // Chat
        window.sendMessage = function () {
            ChatCore.sendMessage();
        };

        // Government banner toggle
        window.toggleGovBanner = function () {
            UI.toggleGovBanner();
        };

        // User-level panels
        window.getUsage = function () {
            AdminPanels.showUsage(Auth.getCurrentUser().tenant_id);
        };

        window.getSessions = function () {
            AdminPanels.showSessions(Auth.getCurrentUser().tenant_id);
        };

        window.getSubscriptionInfo = function () {
            AdminPanels.showSubscription(Auth.getCurrentUser().tenant_id);
        };

        // Admin-level panels
        window.getAdminOverallCost = function () {
            AdminPanels.showAdminOverallCost(Auth.getCurrentUser().tenant_id);
        };

        window.getAdminPerUserCost = function () {
            AdminPanels.showAdminPerUserCost(Auth.getCurrentUser().tenant_id);
        };

        window.getAdminServiceCost = function () {
            AdminPanels.showAdminServiceCost(Auth.getCurrentUser().tenant_id);
        };

        window.getComprehensiveReport = function () {
            AdminPanels.showComprehensiveReport(Auth.getCurrentUser().tenant_id);
        };
    }

    // -------------------------------------------------------------------------
    // Public API
    // -------------------------------------------------------------------------

    return {
        init: init,
        handleRegister: handleRegister,
        handleLogin: handleLogin,
        showChatInterface: showChatInterface,
        createNewSession: createNewSession,
        handleLogout: handleLogout,
        showRegisterForm: showRegisterForm,
        showLoginForm: showLoginForm
    };
})();

// ---------------------------------------------------------------------------
// Bootstrap on page load
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', function () {
    App.init();
});
