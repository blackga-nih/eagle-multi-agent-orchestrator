/**
 * slash-commands.js - Slash Command Palette for Chat Input
 *
 * Provides a command picker dropdown that appears when the user types '/' at
 * the beginning of the chat input. Commands are filtered as the user continues
 * typing, and can be selected via keyboard (arrow keys + Enter) or mouse click.
 *
 * Uses the window.SlashCommands namespace pattern (not ES modules) to stay
 * consistent with the other frontend modules (Auth, ApiClient, ChatCore, UI).
 *
 * Prerequisites:
 *   - A textarea or input element (typically #messageInput) must exist in the DOM
 *     before calling init().
 *
 * Usage:
 *   SlashCommands.init(document.getElementById('messageInput'), function (cmd) {
 *       console.log('Selected command:', cmd);
 *   });
 *   SlashCommands.destroy();
 */
(function () {
    'use strict';

    // -------------------------------------------------------------------------
    // Built-in commands
    // -------------------------------------------------------------------------

    /** @type {Array<{command: string, description: string, category: string}>} */
    var COMMANDS = [
        { command: '/help', description: 'Show available commands and features', category: 'General' },
        { command: '/research', description: 'Start a research query on a topic', category: 'Research' },
        { command: '/document', description: 'Generate or review acquisition documents', category: 'Documents' },
        { command: '/status', description: 'Check system and agent status', category: 'General' },
        { command: '/costs', description: 'View your cost usage report', category: 'Admin' },
        { command: '/subscription', description: 'View subscription tier details', category: 'Admin' },
        { command: '/clear', description: 'Clear chat history', category: 'General' },
        { command: '/agents', description: 'List available AI agents', category: 'Agents' }
    ];

    // -------------------------------------------------------------------------
    // Internal state
    // -------------------------------------------------------------------------

    /** @type {HTMLTextAreaElement|HTMLInputElement|null} Reference to the input element. */
    var inputElement = null;

    /** @type {Function|null} Callback invoked when a command is selected. */
    var onCommandSelectCallback = null;

    /** @type {HTMLDivElement|null} The picker dropdown element. */
    var pickerElement = null;

    /** @type {number} Index of the currently highlighted item in the filtered list. */
    var activeIndex = 0;

    /** @type {Array<{command: string, description: string, category: string}>} Currently filtered commands. */
    var filteredCommands = [];

    /** @type {HTMLStyleElement|null} The injected style element. */
    var styleElement = null;

    /** @type {Function|null} Bound reference to the input handler for removal. */
    var boundHandleInput = null;

    /** @type {Function|null} Bound reference to the keydown handler for removal. */
    var boundHandleKeydown = null;

    // -------------------------------------------------------------------------
    // CSS injection
    // -------------------------------------------------------------------------

    /**
     * Inject the slash command picker styles into the document head.
     *
     * Creates a <style> element with all necessary CSS rules for the picker
     * and its child elements. The element is stored in `styleElement` so it
     * can be removed on destroy().
     */
    function injectStyles() {
        if (styleElement) {
            return;
        }

        styleElement = document.createElement('style');
        styleElement.setAttribute('data-slash-commands', 'true');
        styleElement.textContent =
            '.slash-command-picker {' +
                'position: absolute;' +
                'bottom: 100%;' +
                'left: 0;' +
                'right: 0;' +
                'max-height: 240px;' +
                'overflow-y: auto;' +
                'background: white;' +
                'border: 1px solid var(--nci-border, #D5DBDB);' +
                'border-radius: 8px;' +
                'box-shadow: 0 -4px 16px rgba(0,0,0,0.12);' +
                'z-index: 100;' +
                'margin-bottom: 4px;' +
                'display: none;' +
            '}' +
            '.slash-command-picker.active {' +
                'display: block;' +
            '}' +
            '.slash-command-item {' +
                'padding: 10px 14px;' +
                'cursor: pointer;' +
                'display: flex;' +
                'align-items: center;' +
                'gap: 12px;' +
                'transition: background 0.15s;' +
            '}' +
            '.slash-command-item:hover,' +
            '.slash-command-item.active {' +
                'background: var(--nci-bg, #FAFAFA);' +
            '}' +
            '.slash-command-name {' +
                'font-weight: 600;' +
                'color: var(--nci-primary, #003149);' +
                'min-width: 110px;' +
                'font-family: monospace;' +
            '}' +
            '.slash-command-desc {' +
                'color: var(--nci-gray, #606060);' +
                'font-size: 13px;' +
                'flex: 1;' +
            '}' +
            '.slash-command-category {' +
                'font-size: 11px;' +
                'padding: 2px 8px;' +
                'border-radius: 10px;' +
                'background: var(--nci-bg, #FAFAFA);' +
                'color: var(--nci-gray, #606060);' +
                'border: 1px solid var(--nci-border, #D5DBDB);' +
            '}';

        document.head.appendChild(styleElement);
    }

    /**
     * Remove the injected style element from the document head.
     */
    function removeStyles() {
        if (styleElement && styleElement.parentNode) {
            styleElement.parentNode.removeChild(styleElement);
        }
        styleElement = null;
    }

    // -------------------------------------------------------------------------
    // Picker rendering
    // -------------------------------------------------------------------------

    /**
     * Create the picker dropdown element and insert it into the DOM.
     *
     * The picker is inserted as a child of the input element's closest
     * `.message-input-group` ancestor (or its direct parent if no such
     * ancestor is found). That ancestor is set to `position: relative`
     * so the absolutely-positioned picker renders correctly above the input.
     *
     * @returns {HTMLDivElement} The created picker element.
     */
    function createPicker() {
        var picker = document.createElement('div');
        picker.className = 'slash-command-picker';

        // Ensure the parent container has relative positioning for the
        // absolutely-positioned picker to anchor correctly.
        var parent = inputElement.closest('.message-input-group');
        if (!parent) {
            parent = inputElement.parentNode;
        }
        parent.style.position = 'relative';
        parent.appendChild(picker);

        return picker;
    }

    /**
     * Render the filtered command items into the picker.
     *
     * Clears all existing children and rebuilds the list from the current
     * `filteredCommands` array. Each item is constructed using safe DOM APIs
     * (createElement / createTextNode) -- no innerHTML is used.
     *
     * The item at `activeIndex` receives the 'active' class for visual
     * highlighting.
     */
    function renderItems() {
        // Remove all existing children
        while (pickerElement.firstChild) {
            pickerElement.removeChild(pickerElement.firstChild);
        }

        for (var i = 0; i < filteredCommands.length; i++) {
            var cmd = filteredCommands[i];

            var item = document.createElement('div');
            item.className = 'slash-command-item';
            if (i === activeIndex) {
                item.className += ' active';
            }

            // Command name span
            var nameSpan = document.createElement('span');
            nameSpan.className = 'slash-command-name';
            nameSpan.appendChild(document.createTextNode(cmd.command));
            item.appendChild(nameSpan);

            // Description span
            var descSpan = document.createElement('span');
            descSpan.className = 'slash-command-desc';
            descSpan.appendChild(document.createTextNode(cmd.description));
            item.appendChild(descSpan);

            // Category badge span
            var catSpan = document.createElement('span');
            catSpan.className = 'slash-command-category';
            catSpan.appendChild(document.createTextNode(cmd.category));
            item.appendChild(catSpan);

            // Attach click handler via closure to capture the correct index
            item.addEventListener('click', (function (index) {
                return function () {
                    selectCommand(index);
                };
            })(i));

            pickerElement.appendChild(item);
        }
    }

    // -------------------------------------------------------------------------
    // Picker visibility
    // -------------------------------------------------------------------------

    /**
     * Show the picker dropdown by adding the 'active' class.
     */
    function showPicker() {
        if (pickerElement) {
            pickerElement.classList.add('active');
        }
    }

    /**
     * Hide the picker dropdown by removing the 'active' class.
     */
    function hidePicker() {
        if (pickerElement) {
            pickerElement.classList.remove('active');
        }
    }

    /**
     * Determine whether the picker is currently visible.
     *
     * @returns {boolean} True if the picker has the 'active' class.
     */
    function isPickerVisible() {
        return pickerElement && pickerElement.classList.contains('active');
    }

    // -------------------------------------------------------------------------
    // Filtering and selection
    // -------------------------------------------------------------------------

    /**
     * Filter the COMMANDS array by the text typed after '/'.
     *
     * Performs a case-insensitive prefix match against the command string.
     * For example, if the user has typed '/he', this will match '/help'.
     *
     * @param {string} query - The text after '/' (e.g. 'he' for '/he').
     * @returns {Array<{command: string, description: string, category: string}>}
     */
    function filterCommands(query) {
        var lowerQuery = query.toLowerCase();
        var results = [];

        for (var i = 0; i < COMMANDS.length; i++) {
            // Match against the command without the leading '/'
            var cmdName = COMMANDS[i].command.substring(1).toLowerCase();
            if (cmdName.indexOf(lowerQuery) === 0) {
                results.push(COMMANDS[i]);
            }
        }

        return results;
    }

    /**
     * Select the command at the given index in the filtered list.
     *
     * Replaces the input element's value with the selected command followed
     * by a space, hides the picker, and invokes the onCommandSelect callback.
     *
     * @param {number} index - Index into the `filteredCommands` array.
     */
    function selectCommand(index) {
        if (index < 0 || index >= filteredCommands.length) {
            return;
        }

        var selected = filteredCommands[index];
        inputElement.value = selected.command + ' ';
        hidePicker();

        // Move cursor to the end of the input
        inputElement.focus();
        if (typeof inputElement.setSelectionRange === 'function') {
            var len = inputElement.value.length;
            inputElement.setSelectionRange(len, len);
        }

        if (typeof onCommandSelectCallback === 'function') {
            onCommandSelectCallback(selected.command);
        }
    }

    /**
     * Scroll the active item into view within the picker, if necessary.
     */
    function scrollActiveIntoView() {
        if (!pickerElement) {
            return;
        }

        var items = pickerElement.querySelectorAll('.slash-command-item');
        if (items.length > 0 && activeIndex >= 0 && activeIndex < items.length) {
            var activeItem = items[activeIndex];
            // scrollIntoView with block: 'nearest' avoids jarring jumps
            if (typeof activeItem.scrollIntoView === 'function') {
                activeItem.scrollIntoView({ block: 'nearest' });
            }
        }
    }

    // -------------------------------------------------------------------------
    // Event handlers
    // -------------------------------------------------------------------------

    /**
     * Handle 'input' events on the textarea.
     *
     * Detects when the user is typing a slash command (input starts with '/')
     * and updates the picker accordingly. If the input no longer starts with
     * '/', the picker is hidden.
     */
    function handleInput() {
        var value = inputElement.value;

        // Check if the input starts with '/'
        if (value.length > 0 && value.charAt(0) === '/') {
            // Extract the query portion after '/'
            // If there is a space, we only care about the first "word" for filtering
            var firstSpaceIndex = value.indexOf(' ');
            var query;

            if (firstSpaceIndex === -1) {
                // No space yet -- still typing the command
                query = value.substring(1);
            } else {
                // Space found -- the user has finished typing the command portion.
                // Hide the picker since they have moved past the command.
                hidePicker();
                return;
            }

            filteredCommands = filterCommands(query);
            activeIndex = 0;

            if (filteredCommands.length > 0) {
                renderItems();
                showPicker();
            } else {
                hidePicker();
            }
        } else {
            hidePicker();
        }
    }

    /**
     * Handle 'keydown' events on the textarea for picker navigation.
     *
     * - ArrowDown: move highlight down
     * - ArrowUp: move highlight up
     * - Enter: select the highlighted command (prevents default newline)
     * - Escape: close the picker
     *
     * These keys are only intercepted when the picker is visible.
     *
     * @param {KeyboardEvent} e - The keydown event.
     */
    function handleKeydown(e) {
        if (!isPickerVisible()) {
            return;
        }

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            activeIndex = (activeIndex + 1) % filteredCommands.length;
            renderItems();
            scrollActiveIntoView();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            activeIndex = (activeIndex - 1 + filteredCommands.length) % filteredCommands.length;
            renderItems();
            scrollActiveIntoView();
        } else if (e.key === 'Enter') {
            e.preventDefault();
            e.stopPropagation();
            selectCommand(activeIndex);
        } else if (e.key === 'Escape') {
            e.preventDefault();
            hidePicker();
        }
    }

    // -------------------------------------------------------------------------
    // Public API
    // -------------------------------------------------------------------------

    /**
     * Initialize the slash command system for a given input element.
     *
     * Injects the required CSS styles, creates the picker dropdown element,
     * and attaches input and keydown event listeners to the textarea.
     *
     * @param {HTMLTextAreaElement|HTMLInputElement} element - The input element
     *     to attach slash commands to (typically #messageInput).
     * @param {Function} onCommandSelect - Callback invoked with the command
     *     string (e.g. '/help') when a command is selected.
     * @throws {Error} If the element parameter is null or undefined.
     */
    function init(element, onCommandSelect) {
        if (!element) {
            throw new Error('SlashCommands.init(): input element is required.');
        }

        // Clean up any previous initialization
        if (inputElement) {
            destroy();
        }

        inputElement = element;
        onCommandSelectCallback = onCommandSelect || null;

        // Inject CSS
        injectStyles();

        // Create the picker dropdown
        pickerElement = createPicker();

        // Create bound handler references for later removal
        boundHandleInput = function () {
            handleInput();
        };
        boundHandleKeydown = function (e) {
            handleKeydown(e);
        };

        // Attach event listeners
        inputElement.addEventListener('input', boundHandleInput);
        inputElement.addEventListener('keydown', boundHandleKeydown);
    }

    /**
     * Tear down the slash command system.
     *
     * Removes event listeners from the input element, removes the picker
     * element from the DOM, removes the injected style element, and resets
     * all internal state.
     */
    function destroy() {
        // Remove event listeners
        if (inputElement && boundHandleInput) {
            inputElement.removeEventListener('input', boundHandleInput);
        }
        if (inputElement && boundHandleKeydown) {
            inputElement.removeEventListener('keydown', boundHandleKeydown);
        }

        // Remove picker element from DOM
        if (pickerElement && pickerElement.parentNode) {
            pickerElement.parentNode.removeChild(pickerElement);
        }

        // Remove injected styles
        removeStyles();

        // Reset internal state
        inputElement = null;
        onCommandSelectCallback = null;
        pickerElement = null;
        activeIndex = 0;
        filteredCommands = [];
        boundHandleInput = null;
        boundHandleKeydown = null;
    }

    // -------------------------------------------------------------------------
    // Expose as window.SlashCommands namespace
    // -------------------------------------------------------------------------

    window.SlashCommands = {
        init: init,
        destroy: destroy
    };
})();
