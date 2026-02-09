/**
 * chat-core.js - Chat UI Rendering and Message Management Module
 *
 * Handles rendering chat messages into the DOM, managing the current session,
 * and orchestrating send/receive flow through the ApiClient.
 *
 * Uses the window.ChatCore namespace pattern (not ES modules) to stay
 * consistent with the other frontend modules (Auth, ApiClient).
 *
 * Prerequisites:
 *   - window.Auth   must be loaded and initialized (provides getCurrentUser())
 *   - window.ApiClient must be loaded (provides sendMessage())
 *   - window.StreamClient (optional) enables SSE streaming when available
 *   - DOM elements #chatBox and #messageInput must exist before calling init()
 *
 * Usage:
 *   ChatCore.init();
 *   ChatCore.addMessage('user', 'Hello');
 *   ChatCore.addMessage('agent', 'Hi there!');
 *   ChatCore.addMessage('system', 'Session created.');
 *   ChatCore.clearMessages();
 *   ChatCore.setCurrentSession(sessionObj);
 *   ChatCore.getCurrentSession();
 *   ChatCore.sendMessage();
 */
(function () {
    'use strict';

    // -------------------------------------------------------------------------
    // Internal state
    // -------------------------------------------------------------------------

    /** @type {HTMLElement|null} Reference to the #chatBox container element. */
    var chatBox = null;

    /** @type {HTMLTextAreaElement|HTMLInputElement|null} Reference to the #messageInput element. */
    var messageInput = null;

    /**
     * The active chat session object.
     * Expected shape: { session_id: string, ... }
     * @type {Object|null}
     */
    var currentSession = null;

    // -------------------------------------------------------------------------
    // Internal helpers
    // -------------------------------------------------------------------------

    /**
     * Derive a human-readable label from a sender identifier.
     *
     * @param {string} sender - One of 'user', 'agent', or 'system'.
     * @returns {string} Display label (e.g. "You", "Agent", "System").
     */
    function getSenderLabel(sender) {
        switch (sender) {
            case 'user':
                return 'You';
            case 'agent':
                return 'Agent';
            case 'system':
                return 'System';
            default:
                return sender;
        }
    }

    // -------------------------------------------------------------------------
    // Public API
    // -------------------------------------------------------------------------

    /**
     * Initialize the ChatCore module.
     *
     * Acquires references to the required DOM elements (#chatBox and
     * #messageInput) and attaches an Enter-key listener to #messageInput
     * so pressing Enter triggers sendMessage().
     *
     * @throws {Error} If #chatBox or #messageInput cannot be found in the DOM.
     */
    function init() {
        chatBox = document.getElementById('chatBox');
        messageInput = document.getElementById('messageInput');

        if (!chatBox) {
            throw new Error('ChatCore.init(): #chatBox element not found in the DOM.');
        }
        if (!messageInput) {
            throw new Error('ChatCore.init(): #messageInput element not found in the DOM.');
        }

        // Send on Enter key press (without Shift for multi-line support)
        messageInput.addEventListener('keypress', function (e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    }

    /**
     * Add a message to the chat box.
     *
     * Creates a styled message bubble using safe DOM APIs (createElement /
     * createTextNode) -- no innerHTML is used. The message element receives
     * the CSS classes "message" and the sender identifier (e.g. "user",
     * "agent", "system") which are styled in the page stylesheet. The
     * fadeIn animation class is applied via the existing CSS animation on
     * the .message class.
     *
     * After appending, the chat box is automatically scrolled to the bottom
     * so the newest message is visible.
     *
     * @param {string} sender  - One of 'user', 'agent', or 'system'.
     * @param {string} message - The text content of the message.
     */
    function addMessage(sender, message) {
        if (!chatBox) {
            console.warn('ChatCore.addMessage(): chatBox is not initialized. Call ChatCore.init() first.');
            return;
        }

        // Create the message container div
        var messageDiv = document.createElement('div');
        messageDiv.className = 'message ' + sender;

        // Create the sender label
        var senderLabel = document.createElement('strong');
        senderLabel.appendChild(document.createTextNode(getSenderLabel(sender) + ':'));
        messageDiv.appendChild(senderLabel);

        // Create the message text node
        var messageText = document.createTextNode(message);
        messageDiv.appendChild(messageText);

        // Append to chat box and scroll to bottom
        chatBox.appendChild(messageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    /**
     * Clear all messages from the chat box.
     *
     * Removes every child node from #chatBox, effectively resetting the
     * conversation display.
     */
    function clearMessages() {
        if (!chatBox) {
            console.warn('ChatCore.clearMessages(): chatBox is not initialized. Call ChatCore.init() first.');
            return;
        }

        while (chatBox.firstChild) {
            chatBox.removeChild(chatBox.firstChild);
        }
    }

    /**
     * Send the current message from the input field.
     *
     * Reads text from #messageInput, validates that it is non-empty, displays
     * it as a 'user' message, clears the input, then sends via StreamClient
     * (SSE streaming) when available, falling back to ApiClient.sendMessage().
     *
     * When streaming, text chunks are progressively appended to a single
     * agent message bubble. Tool use, handoff, and reasoning events are
     * forwarded to the SidebarPanel if available.
     *
     * Requires:
     *   - A current session (set via setCurrentSession)
     *   - window.Auth.getCurrentUser() to return a valid user object
     *   - window.ApiClient.sendMessage() or window.StreamClient.streamMessage()
     */
    async function sendMessage() {
        // Guard: ensure we have an active session
        if (!currentSession) {
            addMessage('system', 'No active session. Please create a session first.');
            return;
        }

        // Guard: ensure messageInput is available
        if (!messageInput) {
            console.warn('ChatCore.sendMessage(): messageInput is not initialized. Call ChatCore.init() first.');
            return;
        }

        // Read and validate the input text
        var text = messageInput.value.trim();
        if (!text) {
            return;
        }

        // Display the user's message immediately
        addMessage('user', text);

        // Clear the input field
        messageInput.value = '';

        // Build the tenant context from the authenticated user and session
        var user = window.Auth.getCurrentUser();
        var tenantContext = {
            tenant_id: user.tenant_id,
            user_id: user.user_id,
            session_id: currentSession.session_id
        };

        // Use StreamClient for SSE streaming when available, otherwise fall back
        if (window.StreamClient) {
            sendMessageStreaming(text, tenantContext);
        } else {
            sendMessageNonStreaming(text, tenantContext);
        }
    }

    /**
     * Send message using SSE streaming via StreamClient.
     *
     * Creates a placeholder agent message div and progressively appends
     * text chunks as they arrive. Forwards tool/handoff/reasoning events
     * to SidebarPanel when available.
     *
     * @param {string} text - The user's message text.
     * @param {Object} tenantContext - { tenant_id, user_id, session_id }
     */
    function sendMessageStreaming(text, tenantContext) {
        // Create a streaming message container
        var messageDiv = document.createElement('div');
        messageDiv.className = 'message agent';

        var senderLabel = document.createElement('strong');
        senderLabel.appendChild(document.createTextNode('Agent:'));
        messageDiv.appendChild(senderLabel);

        var contentSpan = document.createElement('span');
        contentSpan.className = 'stream-content';
        messageDiv.appendChild(contentSpan);

        chatBox.appendChild(messageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;

        var accumulatedText = '';

        window.StreamClient.streamMessage(text, tenantContext, {
            onText: function (content) {
                accumulatedText += content;
                contentSpan.textContent = accumulatedText;
                chatBox.scrollTop = chatBox.scrollHeight;
            },
            onReasoning: function (content) {
                if (window.SidebarPanel) {
                    window.SidebarPanel.addAgentLog({
                        type: 'reasoning',
                        agent: 'Agent',
                        content: content
                    });
                }
            },
            onToolUse: function (tool, input) {
                if (window.SidebarPanel) {
                    window.SidebarPanel.addAgentLog({
                        type: 'tool_use',
                        agent: 'Agent',
                        tool: tool,
                        input: input
                    });
                }
            },
            onToolResult: function (tool, output) {
                if (window.SidebarPanel) {
                    window.SidebarPanel.addAgentLog({
                        type: 'tool_result',
                        agent: 'Agent',
                        tool: tool,
                        output: output
                    });
                }
            },
            onHandoff: function (fromAgent, toAgent, reason) {
                if (window.SidebarPanel) {
                    window.SidebarPanel.addAgentLog({
                        type: 'handoff',
                        from: fromAgent,
                        to: toAgent,
                        reason: reason
                    });
                }
                // Update the sender label to reflect the new agent
                senderLabel.textContent = toAgent + ':';
            },
            onError: function (message) {
                if (!accumulatedText) {
                    // No text received yet - show error in the message div
                    contentSpan.textContent = 'Error: ' + message;
                    messageDiv.className = 'message system';
                } else {
                    // Had partial text - append error as system message
                    addMessage('system', 'Stream error: ' + message);
                }
            },
            onComplete: function () {
                // If no text came through at all, show a fallback
                if (!accumulatedText) {
                    contentSpan.textContent = '(No response received)';
                }
            }
        });
    }

    /**
     * Send message using non-streaming API call (fallback).
     *
     * @param {string} text - The user's message text.
     * @param {Object} tenantContext - { tenant_id, user_id, session_id }
     */
    async function sendMessageNonStreaming(text, tenantContext) {
        try {
            var result = await window.ApiClient.sendMessage(text, tenantContext);
            addMessage('agent', result.response);
        } catch (error) {
            var errorText = error && error.message ? error.message : 'An unexpected error occurred.';
            addMessage('system', 'Error: ' + errorText);
        }
    }

    /**
     * Store the current session object.
     *
     * The session object is expected to have at least a `session_id` property
     * which is used when building the tenant_context for API calls.
     *
     * @param {Object} session - Session object (e.g. { session_id: '...' }).
     */
    function setCurrentSession(session) {
        currentSession = session;
    }

    /**
     * Return the current session object, or null if no session is active.
     *
     * @returns {Object|null} The current session object.
     */
    function getCurrentSession() {
        return currentSession;
    }

    // -------------------------------------------------------------------------
    // Expose as window.ChatCore namespace
    // -------------------------------------------------------------------------

    window.ChatCore = {
        init: init,
        addMessage: addMessage,
        clearMessages: clearMessages,
        sendMessage: sendMessage,
        setCurrentSession: setCurrentSession,
        getCurrentSession: getCurrentSession
    };
})();
