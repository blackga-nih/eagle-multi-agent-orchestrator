/**
 * ui-components.js - Reusable DOM Helper Functions
 *
 * Provides a set of utility functions for common DOM operations such as
 * showing/hiding views, displaying error and success messages, creating
 * badges, stat items, and info panels. All functions use safe DOM APIs
 * (createElement, createTextNode) and never set innerHTML, preventing
 * XSS vulnerabilities.
 *
 * Uses the window.UI namespace pattern (not ES modules) to stay
 * consistent with the rest of the frontend architecture.
 *
 * Usage:
 *   UI.showView('chatInterface');
 *   UI.showError('loginError', 'Invalid credentials');
 *   UI.showSuccess('registerSuccess', 'Account created!');
 *   UI.clearPanel('usageInfo');
 *   UI.createInfoPanel('Usage Stats', function (panel) { ... });
 *   var badge = UI.createBadge('Premium', 'badge-premium');
 *   var stat  = UI.createStatItem('Total Messages', '42');
 *   var div   = UI.createStyledDiv('padding: 20px; background: #fff;');
 *   UI.toggleGovBanner();
 */
(function () {
    'use strict';

    // -------------------------------------------------------------------------
    // View Management
    // -------------------------------------------------------------------------

    /**
     * Show a single view and hide all others.
     *
     * Removes the 'active' class from every element matching the
     * `.login-form` and `.chat-interface` selectors, then adds 'active'
     * to the element identified by viewId.
     *
     * @param {string} viewId - The DOM id of the element to activate.
     */
    function showView(viewId) {
        var loginForms = document.querySelectorAll('.login-form');
        var chatInterfaces = document.querySelectorAll('.chat-interface');
        var i;

        for (i = 0; i < loginForms.length; i++) {
            loginForms[i].classList.remove('active');
        }

        for (i = 0; i < chatInterfaces.length; i++) {
            chatInterfaces[i].classList.remove('active');
        }

        var target = document.getElementById(viewId);
        if (target) {
            target.classList.add('active');
        }
    }

    // -------------------------------------------------------------------------
    // Message Display
    // -------------------------------------------------------------------------

    /**
     * Display an error message inside a container element.
     *
     * Sets the text content of the element matching containerId. Uses
     * textContent (not innerHTML) for security.
     *
     * @param {string} containerId - The DOM id of the error container element.
     * @param {string} message     - The error message text to display.
     */
    function showError(containerId, message) {
        var container = document.getElementById(containerId);
        if (container) {
            container.textContent = message;
        }
    }

    /**
     * Display a success message inside a container element.
     *
     * Sets the text content of the element matching containerId. Uses
     * textContent (not innerHTML) for security.
     *
     * @param {string} containerId - The DOM id of the success container element.
     * @param {string} message     - The success message text to display.
     */
    function showSuccess(containerId, message) {
        var container = document.getElementById(containerId);
        if (container) {
            container.textContent = message;
        }
    }

    // -------------------------------------------------------------------------
    // Panel Utilities
    // -------------------------------------------------------------------------

    /**
     * Clear a panel's content and make it visible.
     *
     * Gets the element by panelId, sets its textContent to an empty string,
     * and sets display to 'block' so it becomes visible.
     *
     * @param {string} panelId - The DOM id of the panel to clear and show.
     */
    function clearPanel(panelId) {
        var panel = document.getElementById(panelId);
        if (panel) {
            panel.textContent = '';
            panel.style.display = 'block';
        }
    }

    /**
     * Create a titled info panel inside the #usageInfo element.
     *
     * Retrieves the #usageInfo element, clears its content, makes it visible
     * (display: block), appends an h3 heading with the 'card-title' class,
     * then invokes contentFn so the caller can append additional content.
     *
     * @param {string}   title     - The heading text for the panel.
     * @param {Function} contentFn - Callback that receives the panel element
     *                               so the caller can append child nodes.
     */
    function createInfoPanel(title, contentFn) {
        var panel = document.getElementById('usageInfo');
        if (!panel) {
            return;
        }

        panel.textContent = '';
        panel.style.display = 'block';

        var heading = document.createElement('h3');
        heading.className = 'card-title';
        heading.textContent = title;
        panel.appendChild(heading);

        if (typeof contentFn === 'function') {
            contentFn(panel);
        }
    }

    // -------------------------------------------------------------------------
    // Element Factories
    // -------------------------------------------------------------------------

    /**
     * Create a badge span element.
     *
     * Returns a <span> with class "badge {badgeClass}" and the given text.
     * Uses textContent for safe text assignment.
     *
     * @param {string} text       - The label text for the badge.
     * @param {string} badgeClass - Additional CSS class (e.g. 'badge-premium').
     * @returns {HTMLSpanElement} The constructed badge element.
     */
    function createBadge(text, badgeClass) {
        var span = document.createElement('span');
        span.className = 'badge ' + badgeClass;
        span.textContent = text;
        return span;
    }

    /**
     * Create a stat item paragraph with a bold label and a value.
     *
     * Constructs a <p> containing a <strong> with the label text followed
     * by a colon, then a text node with a space and the value.
     *
     * @param {string} label - The stat label (e.g. 'Total Messages').
     * @param {string} value - The stat value (e.g. '42').
     * @returns {HTMLParagraphElement} The constructed stat item element.
     */
    function createStatItem(label, value) {
        var p = document.createElement('p');

        var strong = document.createElement('strong');
        strong.textContent = label + ':';
        p.appendChild(strong);

        var text = document.createTextNode(' ' + value);
        p.appendChild(text);

        return p;
    }

    /**
     * Create a div element with inline CSS styles.
     *
     * @param {string} cssText - CSS text to apply via style.cssText.
     * @returns {HTMLDivElement} The constructed div element.
     */
    function createStyledDiv(cssText) {
        var div = document.createElement('div');
        div.style.cssText = cssText;
        return div;
    }

    // -------------------------------------------------------------------------
    // Government Banner
    // -------------------------------------------------------------------------

    /**
     * Toggle the expanded state of the government banner.
     *
     * Toggles the 'active' class on the #govBannerExpanded element, which
     * controls its visibility via CSS.
     */
    function toggleGovBanner() {
        var expanded = document.getElementById('govBannerExpanded');
        if (expanded) {
            expanded.classList.toggle('active');
        }
    }

    // -------------------------------------------------------------------------
    // Expose as window.UI namespace
    // -------------------------------------------------------------------------

    window.UI = {
        showView: showView,
        showError: showError,
        showSuccess: showSuccess,
        clearPanel: clearPanel,
        createInfoPanel: createInfoPanel,
        createBadge: createBadge,
        createStatItem: createStatItem,
        createStyledDiv: createStyledDiv,
        toggleGovBanner: toggleGovBanner
    };
})();
