/**
 * sidebar-panel.js - Collapsible Right Sidebar with Tabbed Panels
 *
 * Implements a fixed-position right sidebar with three tabbed views:
 *   Tab 0: Document Checklist - progress tracking with status icons
 *   Tab 1: Agent Logs         - streaming events with agent-colored cards
 *   Tab 2: Agent Tools        - MCP tool list with name/description cards
 *
 * The sidebar is 400px wide when open and collapses to a thin toggle
 * strip when closed. A toggle button centered vertically on the right
 * edge of the viewport opens and closes the panel with a CSS transition.
 *
 * Uses the window.SidebarPanel namespace pattern (not ES modules) to stay
 * consistent with the other frontend modules (UI, Auth, StreamClient, etc.).
 *
 * All DOM manipulation uses createElement / createTextNode. The module
 * never sets innerHTML, preventing XSS vulnerabilities.
 *
 * Usage:
 *   SidebarPanel.init();                          // inject CSS + DOM structure
 *   SidebarPanel.toggle();                        // open or close
 *   SidebarPanel.setActiveTab(1);                 // switch to Agent Logs
 *   SidebarPanel.addAgentLog({ type, agent_id, agent_name, content, timestamp });
 *   SidebarPanel.updateChecklist([{ item_id, item_name, status, required }]);
 *   SidebarPanel.updateTools([{ name, description }]);
 *   SidebarPanel.clearLogs();                     // empty the Agent Logs tab
 */
(function () {
    'use strict';

    // -------------------------------------------------------------------------
    // Constants
    // -------------------------------------------------------------------------

    /**
     * Width of the sidebar panel in pixels when open.
     * @type {number}
     */
    var SIDEBAR_WIDTH = 400;

    /**
     * Tab labels displayed at the top of the sidebar.
     * Index position corresponds to the tab index (0, 1, 2).
     * @type {string[]}
     */
    var TAB_LABELS = ['Checklist', 'Agent Logs', 'Tools'];

    /**
     * Unicode symbols used for checklist status icons.
     * Each key maps to a status value passed into updateChecklist().
     * @type {Object.<string, string>}
     */
    var STATUS_ICONS = {
        pending: '\u25CB',      // white circle
        in_progress: '\u25D4',  // circle with upper right quadrant black (spinner look)
        completed: '\u2713',    // check mark
        skipped: '\u2014'       // em dash
    };

    // -------------------------------------------------------------------------
    // Internal state
    // -------------------------------------------------------------------------

    /**
     * Whether the sidebar is currently open.
     * @type {boolean}
     */
    var isOpen = false;

    /**
     * Index of the currently active tab (0, 1, or 2).
     * @type {number}
     */
    var activeTabIndex = 0;

    /**
     * Reference to the root sidebar panel element.
     * @type {HTMLDivElement|null}
     */
    var panelEl = null;

    /**
     * Reference to the toggle button element.
     * @type {HTMLButtonElement|null}
     */
    var toggleBtnEl = null;

    /**
     * Array of tab button elements (length 3).
     * @type {HTMLButtonElement[]}
     */
    var tabBtnEls = [];

    /**
     * Array of tab content container elements (length 3).
     * @type {HTMLDivElement[]}
     */
    var tabContentEls = [];

    // -------------------------------------------------------------------------
    // CSS Injection
    // -------------------------------------------------------------------------

    /**
     * Inject the sidebar stylesheet into the document head.
     *
     * Creates a <style> element with all sidebar-specific CSS rules and
     * appends it to <head>. Uses textContent for safe assignment.
     */
    function injectStyles() {
        var style = document.createElement('style');
        style.setAttribute('data-sidebar-panel', 'true');
        style.textContent =
            '.sidebar-panel {' +
            '  position: fixed;' +
            '  top: 0;' +
            '  right: 0;' +
            '  width: ' + SIDEBAR_WIDTH + 'px;' +
            '  height: 100vh;' +
            '  background: white;' +
            '  box-shadow: -4px 0 20px rgba(0,0,0,0.1);' +
            '  transform: translateX(100%);' +
            '  transition: transform 0.3s ease;' +
            '  z-index: 1000;' +
            '  display: flex;' +
            '  flex-direction: column;' +
            '}' +
            '.sidebar-panel.open {' +
            '  transform: translateX(0);' +
            '}' +
            '.sidebar-toggle {' +
            '  position: fixed;' +
            '  right: 0;' +
            '  top: 50%;' +
            '  transform: translateY(-50%);' +
            '  width: 32px;' +
            '  height: 80px;' +
            '  background: var(--nci-primary, #003149);' +
            '  color: white;' +
            '  border: none;' +
            '  border-radius: 8px 0 0 8px;' +
            '  cursor: pointer;' +
            '  z-index: 1001;' +
            '  display: flex;' +
            '  align-items: center;' +
            '  justify-content: center;' +
            '  font-size: 14px;' +
            '  transition: right 0.3s ease;' +
            '  text-transform: none;' +
            '  letter-spacing: normal;' +
            '  padding: 0;' +
            '}' +
            '.sidebar-panel.open ~ .sidebar-toggle {' +
            '  right: ' + SIDEBAR_WIDTH + 'px;' +
            '}' +
            '.sidebar-tabs {' +
            '  display: flex;' +
            '  border-bottom: 2px solid var(--nci-border, #D5DBDB);' +
            '  background: var(--nci-bg, #FAFAFA);' +
            '  flex-shrink: 0;' +
            '}' +
            '.sidebar-tab {' +
            '  flex: 1;' +
            '  padding: 12px 8px;' +
            '  border: none;' +
            '  background: none;' +
            '  font-size: 12px;' +
            '  font-weight: 600;' +
            '  color: var(--nci-gray, #606060);' +
            '  cursor: pointer;' +
            '  border-bottom: 3px solid transparent;' +
            '  transition: all 0.2s;' +
            '  text-transform: none;' +
            '  letter-spacing: normal;' +
            '}' +
            '.sidebar-tab.active {' +
            '  color: var(--nci-primary, #003149);' +
            '  border-bottom-color: var(--nci-danger, #BB0E3D);' +
            '}' +
            '.sidebar-tab-content {' +
            '  flex: 1;' +
            '  overflow-y: auto;' +
            '  padding: 16px;' +
            '  display: none;' +
            '}' +
            '.sidebar-tab-content.active {' +
            '  display: block;' +
            '}' +
            '.sidebar-header {' +
            '  padding: 12px 16px;' +
            '  background: var(--nci-primary, #003149);' +
            '  color: white;' +
            '  font-weight: 600;' +
            '  font-size: 14px;' +
            '  flex-shrink: 0;' +
            '}' +
            '.agent-log-entry {' +
            '  padding: 8px 12px;' +
            '  margin-bottom: 6px;' +
            '  border-radius: 6px;' +
            '  font-size: 13px;' +
            '  border-left: 3px solid var(--nci-border, #D5DBDB);' +
            '}' +
            '.agent-log-entry.text { border-left-color: var(--nci-primary, #003149); background: #f8f9fa; }' +
            '.agent-log-entry.tool_use { border-left-color: var(--nci-info, #004971); background: #e8f4fd; }' +
            '.agent-log-entry.tool_result { border-left-color: var(--nci-success, #037F0C); background: #e8f7ef; }' +
            '.agent-log-entry.error { border-left-color: var(--nci-danger, #BB0E3D); background: #fdecea; }' +
            '.agent-log-entry.handoff { border-left-color: var(--nci-accent, #7740A4); background: #f3e8fd; }' +
            '.agent-log-entry .log-agent { font-weight: 600; font-size: 11px; text-transform: uppercase; }' +
            '.agent-log-entry .log-time { font-size: 10px; color: var(--nci-gray); float: right; }' +
            '.agent-log-entry .log-content { margin-top: 4px; word-break: break-word; }' +
            '.checklist-item {' +
            '  display: flex;' +
            '  align-items: center;' +
            '  gap: 10px;' +
            '  padding: 10px 0;' +
            '  border-bottom: 1px solid #eee;' +
            '}' +
            '.checklist-status {' +
            '  width: 24px;' +
            '  height: 24px;' +
            '  border-radius: 50%;' +
            '  display: flex;' +
            '  align-items: center;' +
            '  justify-content: center;' +
            '  font-size: 12px;' +
            '  flex-shrink: 0;' +
            '}' +
            '.checklist-status.pending { background: #e0e0e0; color: #666; }' +
            '.checklist-status.in_progress { background: #fff3cd; color: #856404; }' +
            '.checklist-status.completed { background: #d4edda; color: #155724; }' +
            '.checklist-status.skipped { background: #f0f0f0; color: #999; }' +
            '.tool-card {' +
            '  padding: 10px;' +
            '  margin-bottom: 8px;' +
            '  background: var(--nci-bg, #FAFAFA);' +
            '  border: 1px solid var(--nci-border, #D5DBDB);' +
            '  border-radius: 6px;' +
            '}' +
            '.tool-card-name { font-weight: 600; color: var(--nci-primary, #003149); font-size: 13px; }' +
            '.tool-card-desc { font-size: 12px; color: var(--nci-gray, #606060); margin-top: 4px; }';

        document.head.appendChild(style);
    }

    // -------------------------------------------------------------------------
    // DOM Construction
    // -------------------------------------------------------------------------

    /**
     * Build the sidebar DOM structure and append it to document.body.
     *
     * Creates:
     *   - .sidebar-panel (root container)
     *     - .sidebar-header
     *     - .sidebar-tabs (3 tab buttons)
     *     - .sidebar-tab-content x3 (scrollable tab panels)
     *   - .sidebar-toggle (the open/close strip button, sibling of panel)
     *
     * All construction uses createElement and createTextNode.
     */
    function buildDOM() {
        // -- Root panel --
        panelEl = document.createElement('div');
        panelEl.className = 'sidebar-panel';

        // -- Header --
        var header = document.createElement('div');
        header.className = 'sidebar-header';
        header.appendChild(document.createTextNode('Agent Workspace'));
        panelEl.appendChild(header);

        // -- Tabs bar --
        var tabsBar = document.createElement('div');
        tabsBar.className = 'sidebar-tabs';

        var i;
        for (i = 0; i < TAB_LABELS.length; i++) {
            var tabBtn = document.createElement('button');
            tabBtn.className = 'sidebar-tab';
            tabBtn.appendChild(document.createTextNode(TAB_LABELS[i]));
            tabBtn.setAttribute('data-tab-index', String(i));

            // Attach click handler via closure to capture the index
            tabBtn.addEventListener('click', (function (idx) {
                return function () {
                    setActiveTab(idx);
                };
            })(i));

            if (i === activeTabIndex) {
                tabBtn.classList.add('active');
            }

            tabBtnEls.push(tabBtn);
            tabsBar.appendChild(tabBtn);
        }

        panelEl.appendChild(tabsBar);

        // -- Tab content panels --
        for (i = 0; i < TAB_LABELS.length; i++) {
            var content = document.createElement('div');
            content.className = 'sidebar-tab-content';

            if (i === activeTabIndex) {
                content.classList.add('active');
            }

            tabContentEls.push(content);
            panelEl.appendChild(content);
        }

        // -- Toggle button (sibling of panel, not a child) --
        toggleBtnEl = document.createElement('button');
        toggleBtnEl.className = 'sidebar-toggle';
        toggleBtnEl.appendChild(document.createTextNode('\u25C0')); // left-pointing triangle
        toggleBtnEl.addEventListener('click', function () {
            toggle();
        });

        // Append to body: panel first, then toggle (so the CSS sibling
        // selector `.sidebar-panel.open ~ .sidebar-toggle` works)
        document.body.appendChild(panelEl);
        document.body.appendChild(toggleBtnEl);
    }

    // -------------------------------------------------------------------------
    // Tab Management
    // -------------------------------------------------------------------------

    /**
     * Switch the active tab to the given index.
     *
     * Removes the 'active' class from all tab buttons and all tab content
     * panels, then adds 'active' to the button and content panel at the
     * specified index.
     *
     * @param {number} tabIndex - The tab to activate (0 = Checklist,
     *                            1 = Agent Logs, 2 = Tools).
     */
    function setActiveTab(tabIndex) {
        if (tabIndex < 0 || tabIndex >= TAB_LABELS.length) {
            return;
        }

        activeTabIndex = tabIndex;

        var i;
        for (i = 0; i < tabBtnEls.length; i++) {
            tabBtnEls[i].classList.remove('active');
            tabContentEls[i].classList.remove('active');
        }

        tabBtnEls[tabIndex].classList.add('active');
        tabContentEls[tabIndex].classList.add('active');
    }

    // -------------------------------------------------------------------------
    // Sidebar Toggle
    // -------------------------------------------------------------------------

    /**
     * Open or close the sidebar panel.
     *
     * Toggles the 'open' class on the root panel element, updates the
     * toggle button arrow direction, and flips the internal isOpen flag.
     */
    function toggle() {
        isOpen = !isOpen;

        if (isOpen) {
            panelEl.classList.add('open');
        } else {
            panelEl.classList.remove('open');
        }

        // Update the toggle button arrow: right-pointing when closed,
        // left-pointing when open (so the arrow always "points away" to
        // indicate the toggle direction is towards collapsing).
        toggleBtnEl.textContent = '';
        if (isOpen) {
            toggleBtnEl.appendChild(document.createTextNode('\u25B6')); // right-pointing triangle
        } else {
            toggleBtnEl.appendChild(document.createTextNode('\u25C0')); // left-pointing triangle
        }
    }

    // -------------------------------------------------------------------------
    // Agent Logs (Tab 1)
    // -------------------------------------------------------------------------

    /**
     * Format a timestamp for display in log entries.
     *
     * If the event provides a timestamp string, attempts to parse it and
     * return a locale-formatted time string. Falls back to the current
     * time when no timestamp is provided or parsing fails.
     *
     * @param {string|undefined} timestamp - ISO-8601 timestamp or undefined.
     * @returns {string} Formatted time string (e.g. "2:34:05 PM").
     */
    function formatTimestamp(timestamp) {
        if (!timestamp) {
            return new Date().toLocaleTimeString();
        }
        try {
            return new Date(timestamp).toLocaleTimeString();
        } catch (e) {
            return new Date().toLocaleTimeString();
        }
    }

    /**
     * Add a streaming event entry to the Agent Logs tab (tab index 1).
     *
     * Constructs a log entry card styled by event type and appends it to
     * the Agent Logs content panel. After appending, scrolls the panel to
     * the bottom so the latest entry is visible.
     *
     * @param {Object} event             - The streaming event object.
     * @param {string} event.type        - Event type: 'text', 'tool_use',
     *                                     'tool_result', 'error', or 'handoff'.
     * @param {string} [event.agent_id]  - Unique identifier for the agent.
     * @param {string} [event.agent_name]- Display name for the agent.
     * @param {string} [event.content]   - Text content of the event.
     * @param {string} [event.timestamp] - ISO-8601 timestamp.
     */
    function addAgentLog(event) {
        if (!event) {
            return;
        }

        var logsPanel = tabContentEls[1];
        if (!logsPanel) {
            return;
        }

        var entry = document.createElement('div');
        entry.className = 'agent-log-entry';

        // Apply type-specific CSS class for styling
        var eventType = event.type || 'text';
        entry.classList.add(eventType);

        // -- Header row: agent name (left) + timestamp (right) --
        var timeSpan = document.createElement('span');
        timeSpan.className = 'log-time';
        timeSpan.appendChild(document.createTextNode(formatTimestamp(event.timestamp)));
        entry.appendChild(timeSpan);

        var agentSpan = document.createElement('span');
        agentSpan.className = 'log-agent';
        var agentLabel = event.agent_name || event.agent_id || 'system';
        agentSpan.appendChild(document.createTextNode(agentLabel));
        entry.appendChild(agentSpan);

        // -- Content row --
        var contentDiv = document.createElement('div');
        contentDiv.className = 'log-content';
        var contentText = event.content || '';
        contentDiv.appendChild(document.createTextNode(contentText));
        entry.appendChild(contentDiv);

        logsPanel.appendChild(entry);

        // Auto-scroll to the newest entry
        logsPanel.scrollTop = logsPanel.scrollHeight;
    }

    /**
     * Remove all entries from the Agent Logs tab.
     *
     * Clears the text content of the Agent Logs content panel, which
     * removes all child nodes safely.
     */
    function clearLogs() {
        var logsPanel = tabContentEls[1];
        if (logsPanel) {
            logsPanel.textContent = '';
        }
    }

    // -------------------------------------------------------------------------
    // Document Checklist (Tab 0)
    // -------------------------------------------------------------------------

    /**
     * Update the Document Checklist tab (tab index 0) with a new set of items.
     *
     * Clears the existing checklist content and rebuilds it from the
     * supplied items array. Each item is rendered as a row with a status
     * icon circle and a label. The status circle color and icon are
     * determined by the item's status field.
     *
     * @param {Object[]} items               - Array of checklist items.
     * @param {string}   items[].item_id     - Unique identifier for the item.
     * @param {string}   items[].item_name   - Display label for the item.
     * @param {string}   items[].status      - One of: 'pending', 'in_progress',
     *                                         'completed', 'skipped'.
     * @param {boolean}  items[].required    - Whether the item is required.
     */
    function updateChecklist(items) {
        var checklistPanel = tabContentEls[0];
        if (!checklistPanel) {
            return;
        }

        // Clear previous content
        checklistPanel.textContent = '';

        if (!items || items.length === 0) {
            var emptyMsg = document.createElement('div');
            emptyMsg.style.cssText = 'color: var(--nci-gray, #606060); font-size: 13px; text-align: center; padding: 20px 0;';
            emptyMsg.appendChild(document.createTextNode('No checklist items yet.'));
            checklistPanel.appendChild(emptyMsg);
            return;
        }

        // -- Progress summary --
        var completedCount = 0;
        var totalCount = items.length;
        var i;
        for (i = 0; i < items.length; i++) {
            if (items[i].status === 'completed') {
                completedCount++;
            }
        }

        var progressDiv = document.createElement('div');
        progressDiv.style.cssText = 'margin-bottom: 12px; font-size: 12px; color: var(--nci-gray, #606060);';
        progressDiv.appendChild(document.createTextNode(
            completedCount + ' of ' + totalCount + ' items completed'
        ));
        checklistPanel.appendChild(progressDiv);

        // -- Checklist items --
        for (i = 0; i < items.length; i++) {
            var item = items[i];

            var row = document.createElement('div');
            row.className = 'checklist-item';

            // Status icon circle
            var statusCircle = document.createElement('div');
            statusCircle.className = 'checklist-status';
            var statusKey = item.status || 'pending';
            statusCircle.classList.add(statusKey);
            var icon = STATUS_ICONS[statusKey] || STATUS_ICONS.pending;
            statusCircle.appendChild(document.createTextNode(icon));
            row.appendChild(statusCircle);

            // Item label with optional "required" indicator
            var labelDiv = document.createElement('div');
            labelDiv.style.cssText = 'flex: 1; min-width: 0;';

            var nameSpan = document.createElement('span');
            nameSpan.style.cssText = 'font-size: 13px; font-weight: 500;';
            nameSpan.appendChild(document.createTextNode(item.item_name || ''));
            labelDiv.appendChild(nameSpan);

            if (item.required) {
                var reqSpan = document.createElement('span');
                reqSpan.style.cssText = 'font-size: 10px; color: var(--nci-danger, #BB0E3D); margin-left: 6px; font-weight: 600;';
                reqSpan.appendChild(document.createTextNode('REQUIRED'));
                labelDiv.appendChild(reqSpan);
            }

            row.appendChild(labelDiv);
            checklistPanel.appendChild(row);
        }
    }

    // -------------------------------------------------------------------------
    // Agent Tools (Tab 2)
    // -------------------------------------------------------------------------

    /**
     * Update the Agent Tools tab (tab index 2) with a new set of tools.
     *
     * Clears the existing tools content and rebuilds it from the supplied
     * tools array. Each tool is rendered as a card with a bold name and
     * a description underneath.
     *
     * @param {Object[]} tools              - Array of tool descriptors.
     * @param {string}   tools[].name       - Tool name/identifier.
     * @param {string}   tools[].description - Human-readable tool description.
     */
    function updateTools(tools) {
        var toolsPanel = tabContentEls[2];
        if (!toolsPanel) {
            return;
        }

        // Clear previous content
        toolsPanel.textContent = '';

        if (!tools || tools.length === 0) {
            var emptyMsg = document.createElement('div');
            emptyMsg.style.cssText = 'color: var(--nci-gray, #606060); font-size: 13px; text-align: center; padding: 20px 0;';
            emptyMsg.appendChild(document.createTextNode('No tools available.'));
            toolsPanel.appendChild(emptyMsg);
            return;
        }

        // -- Tool count header --
        var countDiv = document.createElement('div');
        countDiv.style.cssText = 'margin-bottom: 12px; font-size: 12px; color: var(--nci-gray, #606060);';
        countDiv.appendChild(document.createTextNode(tools.length + ' tool' + (tools.length !== 1 ? 's' : '') + ' available'));
        toolsPanel.appendChild(countDiv);

        // -- Tool cards --
        for (var i = 0; i < tools.length; i++) {
            var tool = tools[i];

            var card = document.createElement('div');
            card.className = 'tool-card';

            var nameDiv = document.createElement('div');
            nameDiv.className = 'tool-card-name';
            nameDiv.appendChild(document.createTextNode(tool.name || ''));
            card.appendChild(nameDiv);

            if (tool.description) {
                var descDiv = document.createElement('div');
                descDiv.className = 'tool-card-desc';
                descDiv.appendChild(document.createTextNode(tool.description));
                card.appendChild(descDiv);
            }

            toolsPanel.appendChild(card);
        }
    }

    // -------------------------------------------------------------------------
    // Initialization
    // -------------------------------------------------------------------------

    /**
     * Initialize the sidebar panel.
     *
     * Injects the required CSS styles into the document head, constructs
     * the full sidebar DOM tree, and appends it to document.body. Safe to
     * call multiple times -- subsequent calls are no-ops if the sidebar
     * has already been initialized.
     */
    function init() {
        // Guard against double-initialization
        if (panelEl) {
            return;
        }

        injectStyles();
        buildDOM();
    }

    // -------------------------------------------------------------------------
    // Expose as window.SidebarPanel namespace
    // -------------------------------------------------------------------------

    window.SidebarPanel = {
        init: init,
        toggle: toggle,
        addAgentLog: addAgentLog,
        updateChecklist: updateChecklist,
        updateTools: updateTools,
        clearLogs: clearLogs,
        setActiveTab: setActiveTab
    };
})();
