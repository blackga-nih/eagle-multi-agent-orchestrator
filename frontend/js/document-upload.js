/**
 * document-upload.js - Drag-and-Drop Document Upload Module
 *
 * Provides a collapsible file upload zone that can be injected into any
 * container element. Supports drag-and-drop and click-to-browse with
 * validation for file type and size. Designed for acquisition document
 * uploads (PDF, DOCX, XLSX, CSV, TXT, MD, images).
 *
 * Uses the window.DocumentUpload namespace pattern (not ES modules) to
 * stay consistent with the rest of the frontend architecture.
 *
 * Prerequisites:
 *   - window.Auth.getCurrentUser() for authenticated user context and token
 *   - CONFIG global object with apiUrl property for base URL
 *
 * Usage:
 *   DocumentUpload.init(containerElement);
 *   var files = DocumentUpload.getFiles();
 *   DocumentUpload.clearFiles();
 *   DocumentUpload.destroy();
 */
(function () {
    'use strict';

    // -------------------------------------------------------------------------
    // Constants
    // -------------------------------------------------------------------------

    /** Accepted MIME-type extensions (lowercase, with leading dot). */
    var ALLOWED_EXTENSIONS = [
        '.pdf', '.docx', '.doc', '.xlsx', '.xls',
        '.csv', '.txt', '.md', '.png', '.jpg', '.jpeg'
    ];

    /** Accept attribute value for the hidden file input. */
    var ACCEPT_STRING = ALLOWED_EXTENSIONS.join(',');

    /** Maximum file size in bytes (25 MB). */
    var MAX_FILE_SIZE = 25 * 1024 * 1024;

    /** Maximum number of files allowed at once. */
    var MAX_FILE_COUNT = 5;

    /** Duration in milliseconds before error messages auto-dismiss. */
    var ERROR_DISMISS_MS = 3000;

    /** Unique id for the injected <style> element so it can be removed on destroy. */
    var STYLE_ELEMENT_ID = 'document-upload-styles';

    // -------------------------------------------------------------------------
    // Internal State
    // -------------------------------------------------------------------------

    /** @type {File[]} Currently selected files. */
    var selectedFiles = [];

    /** @type {HTMLElement|null} The container element passed to init(). */
    var containerEl = null;

    /** @type {HTMLElement|null} Root element created by this module. */
    var rootEl = null;

    /** @type {HTMLInputElement|null} Hidden file input element. */
    var fileInputEl = null;

    /** @type {HTMLElement|null} The dropzone element. */
    var dropzoneEl = null;

    /** @type {HTMLElement|null} The file list container. */
    var fileListEl = null;

    /** @type {HTMLElement|null} The toggle button. */
    var toggleBtnEl = null;

    /** @type {boolean} Whether the dropzone is currently expanded. */
    var isExpanded = false;

    /** @type {number[]} Active error timeout IDs for cleanup. */
    var errorTimeouts = [];

    // -------------------------------------------------------------------------
    // File Type Icon Map
    // -------------------------------------------------------------------------

    /**
     * Return a short text label representing the file type icon.
     *
     * Maps known extensions to concise uppercase labels. Falls back to
     * "FILE" for unrecognized extensions (should not occur due to
     * validation, but provides a safe default).
     *
     * @param {string} filename - The file name including extension.
     * @returns {string} A short text icon label (e.g. "PDF", "DOC", "IMG").
     */
    function getFileIcon(filename) {
        var ext = getExtension(filename);
        var map = {
            '.pdf': 'PDF',
            '.docx': 'DOC',
            '.doc': 'DOC',
            '.xlsx': 'XLS',
            '.xls': 'XLS',
            '.csv': 'CSV',
            '.txt': 'TXT',
            '.md': 'TXT',
            '.png': 'IMG',
            '.jpg': 'IMG',
            '.jpeg': 'IMG'
        };
        return map[ext] || 'FILE';
    }

    // -------------------------------------------------------------------------
    // Utility Functions
    // -------------------------------------------------------------------------

    /**
     * Extract the lowercase file extension from a filename.
     *
     * @param {string} filename - The file name (e.g. "report.PDF").
     * @returns {string} The lowercase extension with leading dot (e.g. ".pdf"),
     *                   or an empty string if no extension is found.
     */
    function getExtension(filename) {
        var dotIndex = filename.lastIndexOf('.');
        if (dotIndex === -1) {
            return '';
        }
        return filename.slice(dotIndex).toLowerCase();
    }

    /**
     * Format a byte count into a human-readable string (KB or MB).
     *
     * Values under 1 MB are displayed in KB with one decimal place.
     * Values at or above 1 MB are displayed in MB with one decimal place.
     *
     * @param {number} bytes - The file size in bytes.
     * @returns {string} Formatted size string (e.g. "14.2 KB", "3.1 MB").
     */
    function formatFileSize(bytes) {
        if (bytes >= 1024 * 1024) {
            return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
        }
        return (bytes / 1024).toFixed(1) + ' KB';
    }

    /**
     * Check whether a file extension is in the allowed list.
     *
     * @param {string} filename - The file name to validate.
     * @returns {boolean} True if the extension is allowed.
     */
    function isAllowedType(filename) {
        var ext = getExtension(filename);
        return ALLOWED_EXTENSIONS.indexOf(ext) !== -1;
    }

    // -------------------------------------------------------------------------
    // CSS Injection
    // -------------------------------------------------------------------------

    /**
     * Inject the upload component stylesheet into the document head.
     *
     * Creates a <style> element with a known id so it can be found and
     * removed later by destroy(). If a style element with that id already
     * exists, this function is a no-op.
     */
    function injectStyles() {
        if (document.getElementById(STYLE_ELEMENT_ID)) {
            return;
        }

        var style = document.createElement('style');
        style.id = STYLE_ELEMENT_ID;
        style.type = 'text/css';

        var css =
            '.upload-zone-container {' +
            '  margin-top: 12px;' +
            '}' +
            '.upload-toggle {' +
            '  background: none;' +
            '  border: 1px solid var(--nci-border, #D5DBDB);' +
            '  border-radius: 6px;' +
            '  padding: 8px 14px;' +
            '  font-size: 13px;' +
            '  color: var(--nci-gray, #606060);' +
            '  cursor: pointer;' +
            '  display: flex;' +
            '  align-items: center;' +
            '  gap: 6px;' +
            '  text-transform: none;' +
            '  letter-spacing: normal;' +
            '  font-weight: 500;' +
            '  transition: all 0.2s;' +
            '}' +
            '.upload-toggle:hover {' +
            '  border-color: var(--nci-primary, #003149);' +
            '  color: var(--nci-primary, #003149);' +
            '}' +
            '.upload-dropzone {' +
            '  display: none;' +
            '  margin-top: 8px;' +
            '  border: 2px dashed var(--nci-border, #D5DBDB);' +
            '  border-radius: 8px;' +
            '  padding: 24px;' +
            '  text-align: center;' +
            '  cursor: pointer;' +
            '  transition: all 0.2s;' +
            '  background: var(--nci-bg, #FAFAFA);' +
            '}' +
            '.upload-dropzone.active {' +
            '  display: block;' +
            '}' +
            '.upload-dropzone.dragover {' +
            '  border-color: var(--nci-primary, #003149);' +
            '  background: rgba(0, 49, 73, 0.05);' +
            '}' +
            '.upload-dropzone-text {' +
            '  color: var(--nci-gray, #606060);' +
            '  font-size: 14px;' +
            '}' +
            '.upload-dropzone-hint {' +
            '  color: #999;' +
            '  font-size: 12px;' +
            '  margin-top: 4px;' +
            '}' +
            '.upload-file-list {' +
            '  margin-top: 8px;' +
            '}' +
            '.upload-file-item {' +
            '  display: flex;' +
            '  align-items: center;' +
            '  gap: 10px;' +
            '  padding: 8px 10px;' +
            '  background: var(--nci-bg, #FAFAFA);' +
            '  border: 1px solid var(--nci-border, #D5DBDB);' +
            '  border-radius: 6px;' +
            '  margin-bottom: 4px;' +
            '  font-size: 13px;' +
            '}' +
            '.upload-file-icon {' +
            '  width: 24px;' +
            '  text-align: center;' +
            '  flex-shrink: 0;' +
            '}' +
            '.upload-file-name {' +
            '  flex: 1;' +
            '  overflow: hidden;' +
            '  text-overflow: ellipsis;' +
            '  white-space: nowrap;' +
            '  color: var(--nci-primary, #003149);' +
            '}' +
            '.upload-file-size {' +
            '  color: var(--nci-gray, #606060);' +
            '  font-size: 11px;' +
            '  flex-shrink: 0;' +
            '}' +
            '.upload-file-remove {' +
            '  background: none;' +
            '  border: none;' +
            '  color: var(--nci-danger, #BB0E3D);' +
            '  cursor: pointer;' +
            '  font-size: 16px;' +
            '  padding: 0 4px;' +
            '  text-transform: none;' +
            '  letter-spacing: normal;' +
            '}' +
            '.upload-error {' +
            '  background: #fdecea;' +
            '  color: var(--nci-danger, #BB0E3D);' +
            '  padding: 8px 12px;' +
            '  border-radius: 6px;' +
            '  font-size: 12px;' +
            '  margin-top: 4px;' +
            '  animation: fadeIn 0.3s ease;' +
            '}' +
            '@keyframes fadeIn {' +
            '  from { opacity: 0; }' +
            '  to { opacity: 1; }' +
            '}';

        style.appendChild(document.createTextNode(css));
        document.head.appendChild(style);
    }

    /**
     * Remove the injected stylesheet from the document head.
     */
    function removeStyles() {
        var style = document.getElementById(STYLE_ELEMENT_ID);
        if (style && style.parentNode) {
            style.parentNode.removeChild(style);
        }
    }

    // -------------------------------------------------------------------------
    // DOM Construction
    // -------------------------------------------------------------------------

    /**
     * Build the complete upload UI and return the root element.
     *
     * Creates the following structure (all via createElement/createTextNode):
     *   div.upload-zone-container
     *     button.upload-toggle   ("Attach Documents")
     *     div.upload-dropzone
     *       div.upload-dropzone-text
     *       div.upload-dropzone-hint
     *       input[type=file]     (hidden)
     *     div.upload-file-list
     *
     * @returns {HTMLElement} The root container element.
     */
    function buildUI() {
        // Root container
        var container = document.createElement('div');
        container.className = 'upload-zone-container';

        // Toggle button
        var toggleBtn = document.createElement('button');
        toggleBtn.className = 'upload-toggle';
        toggleBtn.type = 'button';

        var paperclipText = document.createTextNode('Attach Documents');
        toggleBtn.appendChild(paperclipText);

        toggleBtnEl = toggleBtn;

        // Dropzone
        var dropzone = document.createElement('div');
        dropzone.className = 'upload-dropzone';

        var dzText = document.createElement('div');
        dzText.className = 'upload-dropzone-text';
        dzText.appendChild(document.createTextNode('Drag & drop files here or click to browse'));

        var dzHint = document.createElement('div');
        dzHint.className = 'upload-dropzone-hint';
        dzHint.appendChild(document.createTextNode(
            'PDF, DOCX, XLSX, CSV, TXT, MD, PNG, JPG \u2014 Max 25 MB per file, up to 5 files'
        ));

        // Hidden file input
        var fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.multiple = true;
        fileInput.accept = ACCEPT_STRING;
        fileInput.style.display = 'none';
        fileInputEl = fileInput;

        dropzone.appendChild(dzText);
        dropzone.appendChild(dzHint);
        dropzone.appendChild(fileInput);
        dropzoneEl = dropzone;

        // File list
        var fileList = document.createElement('div');
        fileList.className = 'upload-file-list';
        fileListEl = fileList;

        // Assemble
        container.appendChild(toggleBtn);
        container.appendChild(dropzone);
        container.appendChild(fileList);

        return container;
    }

    // -------------------------------------------------------------------------
    // Event Handlers
    // -------------------------------------------------------------------------

    /**
     * Handle click on the toggle button.
     *
     * Toggles the expanded state of the dropzone. When expanding, adds the
     * 'active' class to show the dropzone. When collapsing, removes it.
     */
    function handleToggleClick() {
        isExpanded = !isExpanded;
        if (isExpanded) {
            dropzoneEl.classList.add('active');
        } else {
            dropzoneEl.classList.remove('active');
        }
    }

    /**
     * Handle click on the dropzone area.
     *
     * Opens the native file picker by programmatically clicking the hidden
     * file input element.
     *
     * @param {MouseEvent} e - The click event.
     */
    function handleDropzoneClick(e) {
        // Prevent triggering if the user clicked on the file input itself
        if (e.target === fileInputEl) {
            return;
        }
        fileInputEl.click();
    }

    /**
     * Handle files selected via the file input's change event.
     *
     * Reads the FileList from the input, processes each file through
     * validation, then resets the input value so the same file can be
     * re-selected later.
     *
     * @param {Event} e - The change event from the file input.
     */
    function handleFileInputChange(e) {
        var files = e.target.files;
        if (files && files.length > 0) {
            processFiles(files);
        }
        // Reset input so re-selecting the same file triggers change again
        fileInputEl.value = '';
    }

    /**
     * Handle dragover on the dropzone.
     *
     * Prevents the default browser behavior and adds the visual highlight
     * class to indicate the dropzone is a valid drop target.
     *
     * @param {DragEvent} e - The dragover event.
     */
    function handleDragOver(e) {
        e.preventDefault();
        e.stopPropagation();
        dropzoneEl.classList.add('dragover');
    }

    /**
     * Handle dragleave on the dropzone.
     *
     * Removes the visual highlight class when the dragged item leaves
     * the dropzone boundary.
     *
     * @param {DragEvent} e - The dragleave event.
     */
    function handleDragLeave(e) {
        e.preventDefault();
        e.stopPropagation();
        dropzoneEl.classList.remove('dragover');
    }

    /**
     * Handle drop on the dropzone.
     *
     * Prevents default behavior, removes the highlight, and processes the
     * dropped files through validation.
     *
     * @param {DragEvent} e - The drop event.
     */
    function handleDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        dropzoneEl.classList.remove('dragover');

        var files = e.dataTransfer && e.dataTransfer.files;
        if (files && files.length > 0) {
            processFiles(files);
        }
    }

    // -------------------------------------------------------------------------
    // File Processing & Validation
    // -------------------------------------------------------------------------

    /**
     * Process a FileList by validating each file and adding valid ones.
     *
     * Iterates through the provided FileList. For each file, checks:
     *   1. Whether the max file count would be exceeded.
     *   2. Whether the file extension is in the allowed list.
     *   3. Whether the file size is within the 25 MB limit.
     *   4. Whether a file with the same name is already selected.
     *
     * Valid files are added to the selectedFiles array and the file list
     * UI is re-rendered. Invalid files trigger a temporary error message.
     *
     * @param {FileList} fileList - The list of files to process.
     */
    function processFiles(fileList) {
        var i;
        for (i = 0; i < fileList.length; i++) {
            var file = fileList[i];

            // Check max count
            if (selectedFiles.length >= MAX_FILE_COUNT) {
                showError('Maximum of ' + MAX_FILE_COUNT + ' files allowed.');
                break;
            }

            // Check file type
            if (!isAllowedType(file.name)) {
                showError('File type not supported: ' + file.name);
                continue;
            }

            // Check file size
            if (file.size > MAX_FILE_SIZE) {
                showError('File too large (max 25 MB): ' + file.name);
                continue;
            }

            // Check for duplicate file name
            var isDuplicate = false;
            for (var j = 0; j < selectedFiles.length; j++) {
                if (selectedFiles[j].name === file.name) {
                    isDuplicate = true;
                    break;
                }
            }
            if (isDuplicate) {
                showError('File already selected: ' + file.name);
                continue;
            }

            selectedFiles.push(file);
        }

        renderFileList();
    }

    /**
     * Remove a file from the selected files by index.
     *
     * Splices the file out of the selectedFiles array and re-renders the
     * file list UI.
     *
     * @param {number} index - The zero-based index of the file to remove.
     */
    function removeFile(index) {
        if (index >= 0 && index < selectedFiles.length) {
            selectedFiles.splice(index, 1);
            renderFileList();
        }
    }

    // -------------------------------------------------------------------------
    // Rendering
    // -------------------------------------------------------------------------

    /**
     * Re-render the file list from the current selectedFiles array.
     *
     * Clears the file list container and builds a new file item element
     * for each file. Each item displays an icon label, the file name,
     * the formatted size, and a remove button.
     */
    function renderFileList() {
        if (!fileListEl) {
            return;
        }

        // Clear existing items
        while (fileListEl.firstChild) {
            fileListEl.removeChild(fileListEl.firstChild);
        }

        for (var i = 0; i < selectedFiles.length; i++) {
            var file = selectedFiles[i];
            var item = buildFileItem(file, i);
            fileListEl.appendChild(item);
        }
    }

    /**
     * Build a single file item element for the file list.
     *
     * Creates a div.upload-file-item containing:
     *   - span.upload-file-icon  (text icon label like "PDF", "DOC")
     *   - span.upload-file-name  (truncated filename)
     *   - span.upload-file-size  (formatted byte size)
     *   - button.upload-file-remove (remove/close button)
     *
     * @param {File}   file  - The File object to represent.
     * @param {number} index - The index in selectedFiles (used by remove handler).
     * @returns {HTMLElement} The constructed file item element.
     */
    function buildFileItem(file, index) {
        var item = document.createElement('div');
        item.className = 'upload-file-item';

        // Icon
        var icon = document.createElement('span');
        icon.className = 'upload-file-icon';
        icon.appendChild(document.createTextNode(getFileIcon(file.name)));

        // File name
        var name = document.createElement('span');
        name.className = 'upload-file-name';
        name.title = file.name;
        name.appendChild(document.createTextNode(file.name));

        // File size
        var size = document.createElement('span');
        size.className = 'upload-file-size';
        size.appendChild(document.createTextNode(formatFileSize(file.size)));

        // Remove button
        var removeBtn = document.createElement('button');
        removeBtn.className = 'upload-file-remove';
        removeBtn.type = 'button';
        removeBtn.title = 'Remove file';
        removeBtn.appendChild(document.createTextNode('\u00D7'));

        // Closure to capture the correct index at creation time.
        // We re-render the entire list on each change, so the index
        // is always accurate for the current render cycle.
        removeBtn.addEventListener('click', (function (idx) {
            return function (e) {
                e.stopPropagation();
                removeFile(idx);
            };
        })(index));

        item.appendChild(icon);
        item.appendChild(name);
        item.appendChild(size);
        item.appendChild(removeBtn);

        return item;
    }

    // -------------------------------------------------------------------------
    // Error Display
    // -------------------------------------------------------------------------

    /**
     * Show a temporary error message below the dropzone.
     *
     * Creates a div.upload-error with the provided message text and appends
     * it to the root container. The error auto-dismisses after
     * ERROR_DISMISS_MS milliseconds.
     *
     * @param {string} message - The error text to display.
     */
    function showError(message) {
        if (!rootEl) {
            return;
        }

        var errorDiv = document.createElement('div');
        errorDiv.className = 'upload-error';
        errorDiv.appendChild(document.createTextNode(message));

        rootEl.appendChild(errorDiv);

        var timeoutId = setTimeout(function () {
            if (errorDiv.parentNode) {
                errorDiv.parentNode.removeChild(errorDiv);
            }
            // Remove timeout ID from tracking array
            var idx = errorTimeouts.indexOf(timeoutId);
            if (idx !== -1) {
                errorTimeouts.splice(idx, 1);
            }
        }, ERROR_DISMISS_MS);

        errorTimeouts.push(timeoutId);
    }

    // -------------------------------------------------------------------------
    // Event Binding
    // -------------------------------------------------------------------------

    /**
     * Attach all event listeners to the upload UI elements.
     *
     * Binds click, change, dragover, dragleave, and drop events to
     * the appropriate elements. All handlers are named functions defined
     * in this module so they can be cleanly removed by unbindEvents().
     */
    function bindEvents() {
        if (toggleBtnEl) {
            toggleBtnEl.addEventListener('click', handleToggleClick);
        }
        if (dropzoneEl) {
            dropzoneEl.addEventListener('click', handleDropzoneClick);
            dropzoneEl.addEventListener('dragover', handleDragOver);
            dropzoneEl.addEventListener('dragleave', handleDragLeave);
            dropzoneEl.addEventListener('drop', handleDrop);
        }
        if (fileInputEl) {
            fileInputEl.addEventListener('change', handleFileInputChange);
        }
    }

    /**
     * Remove all event listeners from the upload UI elements.
     *
     * Mirrors bindEvents() to ensure every listener is cleanly removed
     * during destroy().
     */
    function unbindEvents() {
        if (toggleBtnEl) {
            toggleBtnEl.removeEventListener('click', handleToggleClick);
        }
        if (dropzoneEl) {
            dropzoneEl.removeEventListener('click', handleDropzoneClick);
            dropzoneEl.removeEventListener('dragover', handleDragOver);
            dropzoneEl.removeEventListener('dragleave', handleDragLeave);
            dropzoneEl.removeEventListener('drop', handleDrop);
        }
        if (fileInputEl) {
            fileInputEl.removeEventListener('change', handleFileInputChange);
        }
    }

    // -------------------------------------------------------------------------
    // Public API
    // -------------------------------------------------------------------------

    /**
     * Initialize the document upload UI.
     *
     * Injects the component stylesheet, builds the DOM structure, attaches
     * event listeners, and appends the upload zone to the given container
     * element. If init() has already been called, the previous UI is
     * destroyed first to prevent duplicates.
     *
     * @param {HTMLElement} container - The parent element to inject the upload
     *                                  UI into (typically below the chat input).
     */
    function init(container) {
        if (!container) {
            throw new Error('DocumentUpload.init(): container element is required.');
        }

        // Clean up any previous instance
        if (rootEl) {
            destroy();
        }

        containerEl = container;

        injectStyles();

        rootEl = buildUI();
        bindEvents();

        containerEl.appendChild(rootEl);
    }

    /**
     * Return an array of the currently selected File objects.
     *
     * Returns a shallow copy of the internal array so callers cannot
     * mutate the module state directly.
     *
     * @returns {File[]} Array of selected File objects.
     */
    function getFiles() {
        return selectedFiles.slice();
    }

    /**
     * Clear all selected files and re-render the empty file list.
     */
    function clearFiles() {
        selectedFiles = [];
        renderFileList();
    }

    /**
     * Remove the upload UI from the DOM and clean up all resources.
     *
     * Unbinds event listeners, clears pending error timeouts, removes
     * the injected stylesheet, removes the root element from its parent,
     * and resets all internal state to null.
     */
    function destroy() {
        // Remove event listeners
        unbindEvents();

        // Clear any pending error dismiss timeouts
        for (var i = 0; i < errorTimeouts.length; i++) {
            clearTimeout(errorTimeouts[i]);
        }
        errorTimeouts = [];

        // Remove the root element from the DOM
        if (rootEl && rootEl.parentNode) {
            rootEl.parentNode.removeChild(rootEl);
        }

        // Remove injected styles
        removeStyles();

        // Reset internal state
        selectedFiles = [];
        containerEl = null;
        rootEl = null;
        fileInputEl = null;
        dropzoneEl = null;
        fileListEl = null;
        toggleBtnEl = null;
        isExpanded = false;
    }

    // -------------------------------------------------------------------------
    // Expose as window.DocumentUpload namespace
    // -------------------------------------------------------------------------

    window.DocumentUpload = {
        init: init,
        getFiles: getFiles,
        clearFiles: clearFiles,
        destroy: destroy
    };
})();
