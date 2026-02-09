/**
 * chat-enhancements.js - Enhanced Chat Features Module
 *
 * Adds welcome capability cards, suggested prompt chips, and a backend
 * health indicator to the chat interface. These enhancements provide
 * first-time guidance for users and real-time backend status feedback.
 *
 * Features:
 *   1. Welcome Cards   - 4 capability showcase cards displayed when the
 *                        chat box is empty. Clicking a card inserts a
 *                        suggested prompt into the message input.
 *   2. Suggested Prompts - A row of quick-action pill chips below the
 *                          input area. Clicking a chip populates the
 *                          textarea with the prompt text.
 *   3. Health Indicator  - A small status badge above the chat box that
 *                          polls GET /api/health every 30 seconds and
 *                          shows online/offline status.
 *
 * Uses the window.ChatEnhancements namespace pattern (not ES modules) to
 * stay consistent with the other frontend modules (Auth, ApiClient,
 * ChatCore, UI, SidebarPanel).
 *
 * All DOM manipulation uses createElement / createTextNode. The module
 * never sets innerHTML, preventing XSS vulnerabilities.
 *
 * Prerequisites:
 *   - CONFIG.apiUrl global (base URL for /api/health endpoint)
 *   - DOM elements #chatBox and the .input-area container must exist
 *     before calling init()
 *
 * Usage:
 *   ChatEnhancements.init(chatBoxEl, inputAreaEl);
 *   ChatEnhancements.showWelcome();
 *   ChatEnhancements.hideWelcome();
 *   ChatEnhancements.destroy();
 */
(function () {
    'use strict';

    // -------------------------------------------------------------------------
    // Constants
    // -------------------------------------------------------------------------

    /**
     * Polling interval for the health check endpoint, in milliseconds.
     * @type {number}
     */
    var HEALTH_POLL_INTERVAL_MS = 30000;

    /**
     * Welcome card definitions. Each card describes an agent capability
     * and provides a suggested prompt that is inserted on click.
     * @type {Object[]}
     */
    var WELCOME_CARDS = [
        {
            title: 'Acquisition Assistance',
            description: 'Get guidance on procurement requirements, FAR/DFAR regulations, and contract vehicles.',
            prompt: 'I need help understanding the procurement requirements and available contract vehicles for a new IT services acquisition.'
        },
        {
            title: 'Document Generation',
            description: 'Generate SOWs, IGCEs, acquisition plans, and supporting documents.',
            prompt: 'Help me draft a Statement of Work (SOW) for a new software development contract.'
        },
        {
            title: 'Knowledge Search',
            description: 'Search regulatory databases, past performance records, and market research.',
            prompt: 'Search for relevant FAR clauses and past performance records related to cloud computing services.'
        },
        {
            title: 'Compliance Review',
            description: 'Review acquisition packages for FAR compliance and policy adherence.',
            prompt: 'Review my acquisition package for FAR compliance issues and suggest any missing required elements.'
        }
    ];

    /**
     * Suggested prompt chip definitions. Each entry is a short query
     * that populates the message textarea when clicked.
     * @type {string[]}
     */
    var SUGGESTED_PROMPTS = [
        'What contract vehicles are available?',
        'Help me draft a SOW',
        'Check FAR compliance',
        'Generate an IGCE',
        'Review acquisition package'
    ];

    // -------------------------------------------------------------------------
    // Internal state
    // -------------------------------------------------------------------------

    /**
     * Reference to the chat box container element.
     * @type {HTMLElement|null}
     */
    var chatBoxEl = null;

    /**
     * Reference to the input area container element.
     * @type {HTMLElement|null}
     */
    var inputAreaEl = null;

    /**
     * Reference to the <style> element injected into <head>.
     * @type {HTMLStyleElement|null}
     */
    var styleEl = null;

    /**
     * Reference to the health indicator element.
     * @type {HTMLDivElement|null}
     */
    var healthIndicatorEl = null;

    /**
     * Reference to the welcome cards container element.
     * @type {HTMLDivElement|null}
     */
    var welcomeCardsEl = null;

    /**
     * Reference to the suggested prompts container element.
     * @type {HTMLDivElement|null}
     */
    var suggestedPromptsEl = null;

    /**
     * ID returned by setInterval for the health polling timer.
     * @type {number|null}
     */
    var healthTimerId = null;

    /**
     * MutationObserver watching the chatBox for child additions to
     * auto-hide the welcome cards when the first message appears.
     * @type {MutationObserver|null}
     */
    var chatObserver = null;

    /**
     * Whether the module has been initialized.
     * @type {boolean}
     */
    var initialized = false;

    // -------------------------------------------------------------------------
    // CSS Injection
    // -------------------------------------------------------------------------

    /**
     * Inject the chat enhancements stylesheet into the document head.
     *
     * Creates a <style> element with all enhancement-specific CSS rules
     * and appends it to <head>. Uses textContent for safe assignment.
     * The element is tagged with a data attribute for easy identification
     * and cleanup.
     */
    function injectStyles() {
        styleEl = document.createElement('style');
        styleEl.setAttribute('data-chat-enhancements', 'true');
        styleEl.textContent =
            /* Welcome Cards */
            '.welcome-cards {' +
            '  display: grid;' +
            '  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));' +
            '  gap: 16px;' +
            '  padding: 20px;' +
            '}' +
            '.welcome-card {' +
            '  background: var(--nci-white, #FFFFFF);' +
            '  border: 2px solid var(--nci-border, #D5DBDB);' +
            '  border-radius: 12px;' +
            '  padding: 20px;' +
            '  cursor: pointer;' +
            '  transition: all 0.3s ease;' +
            '}' +
            '.welcome-card:hover {' +
            '  border-color: var(--nci-primary, #003149);' +
            '  transform: translateY(-2px);' +
            '  box-shadow: 0 4px 12px rgba(0,0,0,0.1);' +
            '}' +
            '.welcome-card h4 {' +
            '  font-size: 15px;' +
            '  color: var(--nci-primary, #003149);' +
            '  margin-bottom: 8px;' +
            '}' +
            '.welcome-card p {' +
            '  font-size: 13px;' +
            '  color: var(--nci-gray, #606060);' +
            '  line-height: 1.5;' +
            '}' +

            /* Suggested Prompts */
            '.suggested-prompts {' +
            '  display: flex;' +
            '  flex-wrap: wrap;' +
            '  gap: 8px;' +
            '  padding: 12px 0;' +
            '}' +
            '.prompt-chip {' +
            '  background: var(--nci-bg, #FAFAFA);' +
            '  border: 1px solid var(--nci-border, #D5DBDB);' +
            '  border-radius: 20px;' +
            '  padding: 6px 14px;' +
            '  font-size: 12px;' +
            '  color: var(--nci-primary, #003149);' +
            '  cursor: pointer;' +
            '  transition: all 0.2s;' +
            '  font-family: \'Inter\', sans-serif;' +
            '}' +
            '.prompt-chip:hover {' +
            '  background: var(--nci-primary, #003149);' +
            '  color: var(--nci-white, #FFFFFF);' +
            '  border-color: var(--nci-primary, #003149);' +
            '}';

        document.head.appendChild(styleEl);
    }

    // -------------------------------------------------------------------------
    // Health Indicator
    // -------------------------------------------------------------------------

    /**
     * Build the health indicator DOM element.
     *
     * Creates a small pill badge with a colored dot and status text.
     * The indicator starts in the "offline" state and will be updated
     * after the first health poll completes.
     *
     * @returns {HTMLDivElement} The constructed health indicator element.
     */
    function buildHealthIndicator() {
        var indicator = document.createElement('div');
        indicator.className = 'health-indicator offline';
        indicator.setAttribute('data-chat-enhancements-health', 'true');

        var dot = document.createElement('span');
        dot.className = 'health-dot';

        var label = document.createElement('span');
        label.className = 'health-label';
        label.appendChild(document.createTextNode('Checking...'));

        indicator.appendChild(dot);
        indicator.appendChild(label);

        return indicator;
    }

    /**
     * Update the health indicator to reflect the current status.
     *
     * Switches the CSS class between 'online' and 'offline' and updates
     * the label text accordingly.
     *
     * @param {boolean} isOnline - Whether the backend is reachable.
     */
    function updateHealthStatus(isOnline) {
        if (!healthIndicatorEl) {
            return;
        }

        // Find the label span inside the indicator
        var label = healthIndicatorEl.querySelector('.health-label');

        if (isOnline) {
            healthIndicatorEl.className = 'health-indicator online';
            if (label) {
                label.textContent = '';
                label.appendChild(document.createTextNode('Multi-Agent Online'));
            }
        } else {
            healthIndicatorEl.className = 'health-indicator offline';
            if (label) {
                label.textContent = '';
                label.appendChild(document.createTextNode('Backend Offline'));
            }
        }
    }

    /**
     * Perform a single health check by fetching GET /api/health.
     *
     * Uses the CONFIG.apiUrl base URL to construct the endpoint path.
     * On success (HTTP 200 OK), updates the indicator to "online".
     * On any error (network, non-200 status), updates to "offline".
     */
    function checkHealth() {
        var base = CONFIG.apiUrl.replace(/\/+$/, '');
        var url = base + '/api/health';

        fetch(url, { method: 'GET' })
            .then(function (response) {
                updateHealthStatus(response.ok);
            })
            .catch(function () {
                updateHealthStatus(false);
            });
    }

    /**
     * Start the periodic health polling interval.
     *
     * Performs an immediate check, then schedules subsequent checks
     * at the configured interval.
     */
    function startHealthPolling() {
        // Run an immediate check
        checkHealth();

        // Schedule periodic checks
        healthTimerId = setInterval(checkHealth, HEALTH_POLL_INTERVAL_MS);
    }

    /**
     * Stop the periodic health polling interval.
     */
    function stopHealthPolling() {
        if (healthTimerId !== null) {
            clearInterval(healthTimerId);
            healthTimerId = null;
        }
    }

    // -------------------------------------------------------------------------
    // Welcome Cards
    // -------------------------------------------------------------------------

    /**
     * Build the welcome cards grid container with all capability cards.
     *
     * Each card is a clickable div containing a title (h4) and
     * description (p). When clicked, the card's associated prompt text
     * is inserted into the message input textarea.
     *
     * @returns {HTMLDivElement} The constructed welcome cards container.
     */
    function buildWelcomeCards() {
        var container = document.createElement('div');
        container.className = 'welcome-cards';
        container.setAttribute('data-chat-enhancements-welcome', 'true');

        var i;
        for (i = 0; i < WELCOME_CARDS.length; i++) {
            var cardData = WELCOME_CARDS[i];

            var card = document.createElement('div');
            card.className = 'welcome-card';

            // Title
            var title = document.createElement('h4');
            title.appendChild(document.createTextNode(cardData.title));
            card.appendChild(title);

            // Description
            var desc = document.createElement('p');
            desc.appendChild(document.createTextNode(cardData.description));
            card.appendChild(desc);

            // Click handler via closure to capture the prompt string
            card.addEventListener('click', (function (prompt) {
                return function () {
                    insertPrompt(prompt);
                };
            })(cardData.prompt));

            container.appendChild(card);
        }

        return container;
    }

    /**
     * Show the welcome cards in the chat box.
     *
     * If the chat box already contains message elements (children other
     * than the welcome cards themselves), this is a no-op. Otherwise,
     * the welcome cards grid is built and prepended into the chat box.
     */
    function showWelcome() {
        if (!chatBoxEl) {
            return;
        }

        // Do not show if welcome cards are already present
        if (welcomeCardsEl && welcomeCardsEl.parentNode) {
            return;
        }

        // Do not show if the chat box already has message content
        if (hasMessages()) {
            return;
        }

        welcomeCardsEl = buildWelcomeCards();
        chatBoxEl.appendChild(welcomeCardsEl);
    }

    /**
     * Remove the welcome cards from the chat box.
     *
     * Safely removes the welcome cards container from its parent node
     * if it is currently attached to the DOM.
     */
    function hideWelcome() {
        if (welcomeCardsEl && welcomeCardsEl.parentNode) {
            welcomeCardsEl.parentNode.removeChild(welcomeCardsEl);
        }
        welcomeCardsEl = null;
    }

    /**
     * Check whether the chat box contains any message elements.
     *
     * Inspects the child nodes of chatBoxEl for elements that have the
     * 'message' CSS class, which is the class applied by ChatCore when
     * rendering user, agent, or system messages.
     *
     * @returns {boolean} True if at least one .message child exists.
     */
    function hasMessages() {
        if (!chatBoxEl) {
            return false;
        }

        var children = chatBoxEl.children;
        var i;
        for (i = 0; i < children.length; i++) {
            if (children[i].classList.contains('message')) {
                return true;
            }
        }

        return false;
    }

    // -------------------------------------------------------------------------
    // Suggested Prompts
    // -------------------------------------------------------------------------

    /**
     * Build the suggested prompts container with pill chip buttons.
     *
     * Creates a flex-wrap container of small pill-shaped buttons, each
     * labeled with a suggested query. Clicking a chip inserts its text
     * into the message textarea.
     *
     * @returns {HTMLDivElement} The constructed suggested prompts container.
     */
    function buildSuggestedPrompts() {
        var container = document.createElement('div');
        container.className = 'suggested-prompts';
        container.setAttribute('data-chat-enhancements-prompts', 'true');

        var i;
        for (i = 0; i < SUGGESTED_PROMPTS.length; i++) {
            var promptText = SUGGESTED_PROMPTS[i];

            var chip = document.createElement('button');
            chip.className = 'prompt-chip';
            chip.appendChild(document.createTextNode(promptText));

            // Click handler via closure to capture the prompt string
            chip.addEventListener('click', (function (text) {
                return function () {
                    insertPrompt(text);
                };
            })(promptText));

            container.appendChild(chip);
        }

        return container;
    }

    // -------------------------------------------------------------------------
    // Prompt Insertion
    // -------------------------------------------------------------------------

    /**
     * Insert a prompt string into the message input textarea.
     *
     * Locates the #messageInput element, sets its value to the provided
     * text, and focuses the textarea so the user can immediately edit
     * or send the message.
     *
     * @param {string} text - The prompt text to insert.
     */
    function insertPrompt(text) {
        var input = document.getElementById('messageInput');
        if (!input) {
            return;
        }

        input.value = text;
        input.focus();

        // Trigger an input event so any listeners (e.g. auto-resize) are notified
        var event;
        if (typeof Event === 'function') {
            event = new Event('input', { bubbles: true });
        } else {
            // IE fallback
            event = document.createEvent('Event');
            event.initEvent('input', true, true);
        }
        input.dispatchEvent(event);
    }

    // -------------------------------------------------------------------------
    // MutationObserver for Auto-Hide Welcome
    // -------------------------------------------------------------------------

    /**
     * Set up a MutationObserver on the chat box to auto-hide the welcome
     * cards when the first real message is added.
     *
     * Watches for childList mutations. When a .message element is detected
     * among the added nodes, the welcome cards are removed and the
     * observer disconnects itself.
     */
    function observeChatBox() {
        if (!chatBoxEl) {
            return;
        }

        chatObserver = new MutationObserver(function (mutations) {
            var i, j;
            for (i = 0; i < mutations.length; i++) {
                var addedNodes = mutations[i].addedNodes;
                for (j = 0; j < addedNodes.length; j++) {
                    var node = addedNodes[j];
                    // Check if the added node is a message element (not our welcome cards)
                    if (node.nodeType === Node.ELEMENT_NODE &&
                        node.classList.contains('message')) {
                        hideWelcome();
                        // Disconnect after first message; no need to keep observing
                        if (chatObserver) {
                            chatObserver.disconnect();
                            chatObserver = null;
                        }
                        return;
                    }
                }
            }
        });

        chatObserver.observe(chatBoxEl, { childList: true });
    }

    // -------------------------------------------------------------------------
    // Initialization
    // -------------------------------------------------------------------------

    /**
     * Initialize all chat enhancements.
     *
     * Performs the following setup steps in order:
     *   1. Injects the CSS stylesheet into <head>
     *   2. Creates the health indicator and inserts it before the chat box
     *   3. Creates suggested prompt chips below the input area
     *   4. Shows welcome cards if the chat box is empty
     *   5. Starts the health polling interval
     *   6. Sets up a MutationObserver to auto-hide welcome cards
     *
     * Safe to call multiple times; subsequent calls are no-ops if the
     * module has already been initialized.
     *
     * @param {HTMLElement} chatBox   - The #chatBox container element.
     * @param {HTMLElement} inputArea - The .input-area container element.
     */
    function init(chatBox, inputArea) {
        // Guard against double initialization
        if (initialized) {
            return;
        }

        // Validate required parameters
        if (!chatBox) {
            console.warn('ChatEnhancements.init(): chatBox element is required.');
            return;
        }
        if (!inputArea) {
            console.warn('ChatEnhancements.init(): inputArea element is required.');
            return;
        }

        chatBoxEl = chatBox;
        inputAreaEl = inputArea;

        // Step 1: Inject CSS styles
        injectStyles();

        // Step 2: Create and insert health indicator before the chat box
        healthIndicatorEl = buildHealthIndicator();
        var chatBoxParent = chatBoxEl.parentNode;
        if (chatBoxParent) {
            chatBoxParent.insertBefore(healthIndicatorEl, chatBoxEl);
        }

        // Step 3: Create suggested prompts and append after the input area
        suggestedPromptsEl = buildSuggestedPrompts();
        var inputAreaParent = inputAreaEl.parentNode;
        if (inputAreaParent) {
            // Insert the prompts after the input area element
            if (inputAreaEl.nextSibling) {
                inputAreaParent.insertBefore(suggestedPromptsEl, inputAreaEl.nextSibling);
            } else {
                inputAreaParent.appendChild(suggestedPromptsEl);
            }
        }

        // Step 4: Show welcome cards if chat box is empty
        if (!hasMessages()) {
            showWelcome();
        }

        // Step 5: Start health polling
        startHealthPolling();

        // Step 6: Observe chat box for message additions
        observeChatBox();

        initialized = true;
    }

    // -------------------------------------------------------------------------
    // Cleanup
    // -------------------------------------------------------------------------

    /**
     * Destroy all enhancements and clean up resources.
     *
     * Removes all DOM elements created by this module, stops the health
     * polling interval, disconnects the MutationObserver, and removes
     * the injected stylesheet. After calling destroy(), init() can be
     * called again to re-initialize.
     */
    function destroy() {
        // Stop health polling
        stopHealthPolling();

        // Disconnect the MutationObserver
        if (chatObserver) {
            chatObserver.disconnect();
            chatObserver = null;
        }

        // Remove the welcome cards from the DOM
        hideWelcome();

        // Remove the health indicator from the DOM
        if (healthIndicatorEl && healthIndicatorEl.parentNode) {
            healthIndicatorEl.parentNode.removeChild(healthIndicatorEl);
        }
        healthIndicatorEl = null;

        // Remove the suggested prompts from the DOM
        if (suggestedPromptsEl && suggestedPromptsEl.parentNode) {
            suggestedPromptsEl.parentNode.removeChild(suggestedPromptsEl);
        }
        suggestedPromptsEl = null;

        // Remove the injected stylesheet from <head>
        if (styleEl && styleEl.parentNode) {
            styleEl.parentNode.removeChild(styleEl);
        }
        styleEl = null;

        // Clear element references
        chatBoxEl = null;
        inputAreaEl = null;

        // Reset initialization flag
        initialized = false;
    }

    // -------------------------------------------------------------------------
    // Expose as window.ChatEnhancements namespace
    // -------------------------------------------------------------------------

    window.ChatEnhancements = {
        init: init,
        showWelcome: showWelcome,
        hideWelcome: hideWelcome,
        destroy: destroy
    };
})();
