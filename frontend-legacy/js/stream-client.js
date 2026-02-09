/**
 * stream-client.js - SSE (Server-Sent Events) Streaming Client for Chat Responses
 *
 * Implements a streaming chat client that connects to POST /api/chat/stream
 * and processes typed SSE events from the multi-agent backend. The protocol
 * is based on the EAGLE intake app's stream_protocol.py which sends JSON
 * payloads as SSE `data:` lines.
 *
 * Uses the window.StreamClient namespace pattern (not ES modules) to stay
 * consistent with the other frontend modules (Auth, ApiClient, ChatCore).
 *
 * Prerequisites:
 *   - window.Auth   must be loaded and initialized (provides getToken())
 *   - CONFIG.apiUrl  global must be defined (base URL for the backend API)
 *
 * SSE Event Types:
 *   { "type": "text",        "content": "..." }                              - Streaming text chunk
 *   { "type": "reasoning",   "content": "..." }                              - Agent reasoning/thinking
 *   { "type": "tool_use",    "tool": "...", "input": {...} }                 - Tool being called
 *   { "type": "tool_result", "tool": "...", "output": "..." }               - Tool result
 *   { "type": "handoff",     "from_agent": "...", "to_agent": "...", "reason": "..." } - Agent handoff
 *   { "type": "error",       "message": "..." }                              - Error
 *   { "type": "complete",    "usage": {...} }                                 - Stream complete
 *
 * Usage:
 *   StreamClient.streamMessage('Hello', tenantCtx, {
 *       onText: function (content) { ... },
 *       onReasoning: function (content) { ... },
 *       onToolUse: function (tool, input) { ... },
 *       onToolResult: function (tool, output) { ... },
 *       onHandoff: function (fromAgent, toAgent, reason) { ... },
 *       onError: function (message) { ... },
 *       onComplete: function (usage) { ... }
 *   });
 *   StreamClient.abort();
 */
(function () {
    'use strict';

    // -------------------------------------------------------------------------
    // Internal state
    // -------------------------------------------------------------------------

    /**
     * AbortController for the current in-flight stream request.
     * Recreated at the start of each streamMessage() call so that a previous
     * abort does not interfere with new requests.
     * @type {AbortController|null}
     */
    var abortController = null;

    // -------------------------------------------------------------------------
    // Internal helpers
    // -------------------------------------------------------------------------

    /**
     * Build the full URL for the streaming endpoint.
     * @returns {string} Fully-qualified URL to POST /api/chat/stream.
     */
    function buildStreamUrl() {
        var base = CONFIG.apiUrl.replace(/\/+$/, '');
        return base + '/api/chat/stream';
    }

    /**
     * Build request headers including the Bearer token and content type.
     * @returns {Object} Headers dictionary.
     */
    function buildHeaders() {
        return {
            'Authorization': 'Bearer ' + window.Auth.getToken(),
            'Content-Type': 'application/json'
        };
    }

    /**
     * Dispatch a parsed SSE event to the appropriate callback.
     *
     * Silently ignores event types that have no matching callback, so callers
     * are free to supply only the callbacks they care about.
     *
     * @param {Object} event     - Parsed JSON event from the SSE stream.
     * @param {Object} callbacks - Callback map keyed by event type.
     */
    function dispatchEvent(event, callbacks) {
        if (!event || typeof event.type !== 'string') {
            return;
        }

        switch (event.type) {
            case 'text':
                if (typeof callbacks.onText === 'function') {
                    callbacks.onText(event.content);
                }
                break;

            case 'reasoning':
                if (typeof callbacks.onReasoning === 'function') {
                    callbacks.onReasoning(event.content);
                }
                break;

            case 'tool_use':
                if (typeof callbacks.onToolUse === 'function') {
                    callbacks.onToolUse(event.tool, event.input);
                }
                break;

            case 'tool_result':
                if (typeof callbacks.onToolResult === 'function') {
                    callbacks.onToolResult(event.tool, event.output);
                }
                break;

            case 'handoff':
                if (typeof callbacks.onHandoff === 'function') {
                    callbacks.onHandoff(event.from_agent, event.to_agent, event.reason);
                }
                break;

            case 'error':
                if (typeof callbacks.onError === 'function') {
                    callbacks.onError(event.message);
                }
                break;

            case 'complete':
                if (typeof callbacks.onComplete === 'function') {
                    callbacks.onComplete(event.usage);
                }
                break;

            default:
                // Unknown event type -- ignore silently for forward-compatibility
                break;
        }
    }

    /**
     * Process a ReadableStream from the fetch response, parsing SSE-formatted
     * lines and dispatching events to the supplied callbacks.
     *
     * SSE format: each payload line is `data: {json}\n\n`. Lines that do not
     * start with `data: ` are ignored (e.g. comments, keep-alive blanks).
     * The special sentinel `data: [DONE]` is treated as a no-op and skipped.
     *
     * Incomplete lines (those not yet terminated by `\n`) are buffered until
     * the next chunk arrives from the network.
     *
     * @param {ReadableStream} body      - The response.body ReadableStream.
     * @param {Object}         callbacks - Callback map keyed by event type.
     * @returns {Promise<void>} Resolves when the stream is fully consumed.
     */
    async function processStream(body, callbacks) {
        var reader = body.getReader();
        var decoder = new TextDecoder();
        var buffer = '';

        try {
            while (true) {
                var result = await reader.read();
                if (result.done) {
                    break;
                }

                // Append the decoded chunk to the buffer. The { stream: true }
                // option tells the decoder to keep multi-byte character state
                // across calls so we never split a UTF-8 character.
                buffer += decoder.decode(result.value, { stream: true });

                // Split on newline boundaries. The last element may be an
                // incomplete line, so we keep it in the buffer.
                var lines = buffer.split('\n');
                buffer = lines.pop();

                for (var i = 0; i < lines.length; i++) {
                    var line = lines[i];

                    // Only process lines that carry SSE data payloads
                    if (!line.startsWith('data: ')) {
                        continue;
                    }

                    var jsonStr = line.slice(6);

                    // Skip the [DONE] sentinel used by some SSE implementations
                    if (jsonStr === '[DONE]') {
                        continue;
                    }

                    try {
                        var event = JSON.parse(jsonStr);
                        dispatchEvent(event, callbacks);
                    } catch (parseError) {
                        // Malformed JSON -- skip this line rather than breaking the
                        // entire stream. This is expected when the server sends
                        // partial or debug lines.
                        console.warn('StreamClient: skipping malformed SSE data:', jsonStr);
                    }
                }
            }

            // Flush the decoder to handle any remaining bytes
            var remaining = decoder.decode();
            if (remaining) {
                buffer += remaining;
            }

            // Process any final buffered line that was not terminated by a newline
            if (buffer.startsWith('data: ')) {
                var finalJson = buffer.slice(6);
                if (finalJson !== '[DONE]') {
                    try {
                        var finalEvent = JSON.parse(finalJson);
                        dispatchEvent(finalEvent, callbacks);
                    } catch (finalParseError) {
                        console.warn('StreamClient: skipping malformed final SSE data:', finalJson);
                    }
                }
            }
        } finally {
            // Ensure the reader is released even if an error is thrown
            reader.releaseLock();
        }
    }

    // -------------------------------------------------------------------------
    // Public API
    // -------------------------------------------------------------------------

    /**
     * Stream a chat message to the backend and process SSE events via callbacks.
     *
     * Makes a POST fetch request to /api/chat/stream with the supplied message
     * and tenant context. The response body is read as a stream and parsed for
     * SSE-formatted events. Each recognized event type triggers the matching
     * callback from the callbacks object.
     *
     * A new AbortController is created for each call, so any previous stream
     * is not affected. Call StreamClient.abort() to cancel an in-progress stream.
     *
     * @param {string} message       - The user's message text.
     * @param {Object} tenantContext  - Tenant context object (tenant_id, user_id, session_id).
     * @param {Object} callbacks      - Map of callback functions keyed by event type.
     * @param {Function} [callbacks.onText]       - Called with (content: string) for text chunks.
     * @param {Function} [callbacks.onReasoning]  - Called with (content: string) for reasoning chunks.
     * @param {Function} [callbacks.onToolUse]    - Called with (tool: string, input: Object) when a tool is invoked.
     * @param {Function} [callbacks.onToolResult] - Called with (tool: string, output: string) when a tool completes.
     * @param {Function} [callbacks.onHandoff]    - Called with (fromAgent: string, toAgent: string, reason: string) on agent handoff.
     * @param {Function} [callbacks.onError]      - Called with (message: string) on stream error events.
     * @param {Function} [callbacks.onComplete]   - Called with (usage: Object) when the stream completes.
     * @returns {Promise<void>} Resolves when the stream is fully consumed or aborted.
     */
    async function streamMessage(message, tenantContext, callbacks) {
        // Provide a safe default so callers can omit the callbacks object entirely
        var cbs = callbacks || {};

        // Create a fresh AbortController for this request
        abortController = new AbortController();

        var response;
        try {
            response = await fetch(buildStreamUrl(), {
                method: 'POST',
                headers: buildHeaders(),
                body: JSON.stringify({
                    message: message,
                    tenant_context: tenantContext
                }),
                signal: abortController.signal
            });
        } catch (fetchError) {
            // Distinguish user-initiated aborts from genuine network errors
            if (fetchError.name === 'AbortError') {
                console.info('StreamClient: stream aborted by user.');
                return;
            }
            var networkMsg = fetchError && fetchError.message
                ? fetchError.message
                : 'Network request failed.';
            if (typeof cbs.onError === 'function') {
                cbs.onError('Connection error: ' + networkMsg);
            }
            return;
        }

        // Handle non-2xx HTTP responses
        if (!response.ok) {
            var errorBody = '';
            try {
                errorBody = await response.text();
            } catch (_) {
                // Could not read the error body -- proceed with status text
            }
            var httpMsg = 'HTTP ' + response.status + ': ' + (errorBody || response.statusText);
            if (typeof cbs.onError === 'function') {
                cbs.onError(httpMsg);
            }
            return;
        }

        // Guard: the response must have a readable body stream
        if (!response.body) {
            if (typeof cbs.onError === 'function') {
                cbs.onError('Response body is not a readable stream.');
            }
            return;
        }

        // Process the SSE stream
        try {
            await processStream(response.body, cbs);
        } catch (streamError) {
            if (streamError.name === 'AbortError') {
                console.info('StreamClient: stream aborted by user.');
                return;
            }
            var streamMsg = streamError && streamError.message
                ? streamError.message
                : 'Stream processing failed.';
            if (typeof cbs.onError === 'function') {
                cbs.onError('Stream error: ' + streamMsg);
            }
        }
    }

    /**
     * Abort any in-progress streaming request.
     *
     * Safe to call even when no stream is active -- the function is a no-op
     * if there is no current AbortController. After aborting, the controller
     * reference is cleared so it does not interfere with future calls to
     * streamMessage().
     */
    function abort() {
        if (abortController) {
            abortController.abort();
            abortController = null;
        }
    }

    // -------------------------------------------------------------------------
    // Expose as window.StreamClient namespace
    // -------------------------------------------------------------------------

    window.StreamClient = {
        streamMessage: streamMessage,
        abort: abort
    };
})();
