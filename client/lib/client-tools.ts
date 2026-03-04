/**
 * Client-Side Tool Execution for EAGLE
 *
 * Implements browser-side execution for think, code, and editor tools
 * so they run locally without backend round-trips.
 *
 * Security model for government context:
 *   - JS code runs in a Web Worker (no DOM access, no same-origin storage).
 *   - HTML code runs in a sandboxed iframe with sandbox="allow-scripts"
 *     (no allow-same-origin — cannot read cookies, localStorage, or parent DOM).
 *   - editor tool uses a namespaced localStorage key prefix (eagle:file:)
 *     to isolate its virtual filesystem from other app state.
 *
 * Ported and adapted from nci-oa-agent/client/utils/tools.js.
 */

export const CLIENT_SIDE_TOOLS = new Set(['think', 'code', 'editor']);

export interface ClientToolResult {
  success: boolean;
  result: unknown;
  error?: string;
}

// -----------------------------------------------------------------------
// think tool
// -----------------------------------------------------------------------

interface ThinkInput {
  thought: string;
}

/**
 * Store a thought in localStorage under the current session namespace and
 * return the thought text as the result. The key format is:
 *   eagle:thoughts:{sessionId}   (an array of thought strings, LIFO prepend)
 *
 * Falls back to a single global key when no sessionId is available.
 */
export function runThink(input: ThinkInput, sessionId?: string): ClientToolResult {
  const { thought } = input;
  if (!thought) {
    return { success: false, result: null, error: 'thought parameter is required' };
  }

  try {
    const storageKey = `eagle:thoughts:${sessionId ?? 'global'}`;
    const existing = localStorage.getItem(storageKey);
    const thoughts: string[] = existing ? JSON.parse(existing) : [];
    thoughts.unshift(thought);
    // Keep the last 50 thoughts to prevent unbounded growth
    localStorage.setItem(storageKey, JSON.stringify(thoughts.slice(0, 50)));
  } catch {
    // localStorage unavailable (SSR, private mode) — still return success
  }

  return { success: true, result: thought };
}

// -----------------------------------------------------------------------
// editor tool
// -----------------------------------------------------------------------

type EditorCommand = 'view' | 'str_replace' | 'create' | 'insert' | 'undo_edit';

interface EditorInput {
  command: EditorCommand;
  path: string;
  view_range?: [number, number];
  old_str?: string;
  new_str?: string;
  file_text?: string;
  insert_line?: number;
}

/** Prefix that namespaces the virtual filesystem from other localStorage keys. */
const EDITOR_FILE_PREFIX = 'eagle:file:';
const EDITOR_HIST_PREFIX = 'eagle:hist:';

function normalizeNewlines(text: string): string {
  return text.replace(/\r\n/g, '\n');
}

/**
 * localStorage-backed file editor. Supports view, str_replace, create,
 * insert, and undo_edit commands. Ported from nci-oa-agent utils/tools.js.
 */
export function runEditor(input: EditorInput): ClientToolResult {
  const { command, path } = input;
  if (!path) return { success: false, result: null, error: 'path parameter is required' };
  if (!command) return { success: false, result: null, error: 'command parameter is required' };

  const fileKey = `${EDITOR_FILE_PREFIX}${path}`;
  const histKey = `${EDITOR_HIST_PREFIX}${path}`;

  try {
    switch (command) {
      case 'view': {
        const content = localStorage.getItem(fileKey);
        if (content === null) {
          return { success: false, result: null, error: `File not found: ${path}` };
        }
        const lines = normalizeNewlines(content).split('\n');
        const [start, end] = input.view_range ?? [1, lines.length];
        const startLine = Math.max(1, start);
        const endLine = end === -1 ? lines.length : Math.min(end, lines.length);
        const result = lines
          .slice(startLine - 1, endLine)
          .map((line, idx) => `${startLine + idx}: ${line}`)
          .join('\n');
        return { success: true, result };
      }

      case 'str_replace': {
        const { old_str, new_str } = input;
        if (old_str === undefined) {
          return { success: false, result: null, error: 'old_str is required for str_replace' };
        }
        if (new_str === undefined) {
          return { success: false, result: null, error: 'new_str is required for str_replace' };
        }
        const content = localStorage.getItem(fileKey);
        if (content === null) {
          return { success: false, result: null, error: `File not found: ${path}` };
        }
        const normalized = normalizeNewlines(content);
        const normalizedOld = normalizeNewlines(old_str);
        if (normalizedOld === '') {
          return { success: false, result: null, error: 'old_str cannot be empty for str_replace' };
        }
        // Count occurrences
        let count = 0;
        let pos = 0;
        while (true) {
          pos = normalized.indexOf(normalizedOld, pos);
          if (pos === -1) break;
          count++;
          pos += normalizedOld.length;
        }
        if (count === 0) {
          return { success: false, result: null, error: 'The specified text was not found in the file.' };
        }
        if (count > 1) {
          return { success: false, result: null, error: `Found ${count} occurrences — replacement must match exactly one location.` };
        }
        localStorage.setItem(histKey, content);
        const newContent = normalized.replace(normalizedOld, normalizeNewlines(new_str));
        localStorage.setItem(fileKey, newContent);
        return { success: true, result: 'Successfully replaced text at exactly one location.' };
      }

      case 'create': {
        const fileContent = input.file_text !== undefined ? normalizeNewlines(input.file_text) : '';
        const overwritten = localStorage.getItem(fileKey) !== null;
        localStorage.setItem(fileKey, fileContent);
        return {
          success: true,
          result: overwritten ? `Overwrote existing file: ${path}` : `Successfully created file: ${path}`,
        };
      }

      case 'insert': {
        const { new_str, insert_line } = input;
        if (new_str === undefined) {
          return { success: false, result: null, error: 'new_str is required for insert' };
        }
        if (insert_line === undefined) {
          return { success: false, result: null, error: 'insert_line is required for insert' };
        }
        const content = localStorage.getItem(fileKey);
        if (content === null) {
          return { success: false, result: null, error: `File not found: ${path}` };
        }
        localStorage.setItem(histKey, content);
        const lines = normalizeNewlines(content).split('\n');
        const idx = Math.min(Math.max(0, insert_line), lines.length);
        const toInsert = normalizeNewlines(new_str).split('\n');
        lines.splice(idx, 0, ...toInsert);
        localStorage.setItem(fileKey, lines.join('\n'));
        return { success: true, result: `Successfully inserted text after line ${idx}.` };
      }

      case 'undo_edit': {
        const previous = localStorage.getItem(histKey);
        if (previous === null) {
          return { success: false, result: null, error: `No previous edit found for file: ${path}` };
        }
        localStorage.setItem(fileKey, previous);
        localStorage.removeItem(histKey);
        return { success: true, result: `Successfully reverted last edit for file: ${path}` };
      }

      default:
        return { success: false, result: null, error: `Unknown command: ${command}` };
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return { success: false, result: null, error: `editor error: ${msg}` };
  }
}

// -----------------------------------------------------------------------
// code tool
// -----------------------------------------------------------------------

interface CodeInput {
  language: 'javascript' | 'html';
  source: string;
  timeout?: number;
}

export interface CodeResult {
  logs: string[];
  html?: string;
  height?: number;
  error?: string;
}

/**
 * Console bridge snippet injected into every sandbox.
 *
 * Overrides console.log/warn/error/info/debug so output is forwarded via
 * postMessage. Uses the smallest reliable cross-context postMessage target:
 *   - Worker context: self.postMessage
 *   - iframe context: parent.postMessage
 */
const CONSOLE_BRIDGE = `(()=>{
  const _pm = (typeof self !== 'undefined' && self.postMessage)
    ? self.postMessage.bind(self)
    : (typeof parent !== 'undefined' && parent.postMessage)
      ? parent.postMessage.bind(parent)
      : () => {};
  const _send = (m) => _pm({ type: 'log', msg: m }, '*');
  ['log','warn','error','info','debug'].forEach(k => {
    const orig = console[k];
    console[k] = (...args) => { _send(args.join(' ')); orig.apply(console, args); };
  });
  if (typeof self !== 'undefined') {
    self.onerror = (msg, _u, line) => { _send(msg + ' [line ' + line + ']'); return true; };
  }
})();`;

/**
 * Run JavaScript in a Web Worker with a postMessage console bridge.
 *
 * The Worker runs in a separate thread with no DOM access. The worker
 * is created from a Blob URL and terminated after execution or timeout.
 */
async function runJavaScript(source: string, timeoutMs: number): Promise<CodeResult> {
  return new Promise((resolve) => {
    const logs: string[] = [];

    const workerCode = [
      CONSOLE_BRIDGE,
      source,
      'self.postMessage({ type: "done" });',
    ].join('\n;\n');

    let worker: Worker;
    try {
      const blob = new Blob([workerCode], { type: 'text/javascript' });
      const url = URL.createObjectURL(blob);
      worker = new Worker(url, { type: 'module' });
      URL.revokeObjectURL(url);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return resolve({ logs: [], error: `Worker creation failed: ${msg}` });
    }

    const kill = setTimeout(() => {
      worker.terminate();
      resolve({ logs, error: 'Execution timed out' });
    }, timeoutMs);

    worker.onmessage = (e) => {
      if (e.data?.type === 'log') {
        logs.push(String(e.data.msg));
      }
      if (e.data?.type === 'done') {
        clearTimeout(kill);
        worker.terminate();
        resolve({ logs });
      }
    };

    worker.onerror = (e) => {
      clearTimeout(kill);
      logs.push(e.message || 'Worker error');
      worker.terminate();
      resolve({ logs });
    };
  });
}

/**
 * Run HTML in a sandboxed iframe with sandbox="allow-scripts".
 *
 * The iframe is appended off-screen, receives the HTML via srcdoc, and is
 * removed after execution. A postMessage listener captures console output.
 *
 * Security: allow-scripts only — no allow-same-origin. The iframe cannot
 * read cookies, localStorage, or access the parent DOM.
 */
async function runHtml(source: string, timeoutMs: number): Promise<CodeResult> {
  return new Promise((resolve) => {
    if (typeof document === 'undefined') {
      return resolve({ logs: [], error: 'HTML sandbox requires a browser environment' });
    }

    const logs: string[] = [];

    // Parse the source to inject the console bridge before the first script
    const parser = new DOMParser();
    const doc = parser.parseFromString(source, 'text/html');

    // Inject console bridge at top of <head>
    const bridgeScript = doc.createElement('script');
    bridgeScript.text = CONSOLE_BRIDGE;
    doc.head.prepend(bridgeScript);

    // Append done signal to the last inline script block
    const scripts = Array.from(doc.querySelectorAll('script:not([src])'));
    const lastScript = scripts.find((s) => {
      const type = (s as HTMLScriptElement).type;
      return type === '' || type === 'text/javascript' || type === 'module';
    });
    if (lastScript) {
      lastScript.innerHTML += '\n;parent.postMessage({ type: "done" }, "*");';
    }

    const html = doc.documentElement.outerHTML;

    // Create a sandboxed off-screen iframe
    const frame = document.createElement('iframe');
    frame.setAttribute('sandbox', 'allow-scripts');
    frame.style.cssText = 'position:fixed;left:-9999px;top:-9999px;width:800px;height:600px;border:0;';

    const cleanup = () => {
      clearTimeout(killTimer);
      window.removeEventListener('message', onMessage);

      // Capture rendered height before removal
      let height = 0;
      try {
        const iDoc = frame.contentDocument || (frame.contentWindow as Window | null)?.document;
        if (iDoc) {
          const { body, documentElement } = iDoc;
          height = Math.max(
            body?.scrollHeight ?? 0,
            body?.offsetHeight ?? 0,
            documentElement?.clientHeight ?? 0,
            documentElement?.scrollHeight ?? 0,
            documentElement?.offsetHeight ?? 0,
          );
        }
      } catch {
        // Cross-origin access blocked (expected when sandbox is active)
      }

      frame.remove();
      resolve({ logs, html, height });
    };

    const onMessage = (e: MessageEvent) => {
      if (e.source !== frame.contentWindow) return;
      if (e.data?.type === 'log') logs.push(String(e.data.msg));
      if (e.data?.type === 'done') cleanup();
    };

    const killTimer = setTimeout(cleanup, timeoutMs);
    window.addEventListener('message', onMessage);
    document.body.appendChild(frame);
    frame.srcdoc = html;
  });
}

/**
 * Execute code in a language-appropriate sandbox and return captured output.
 */
export async function runCode(input: CodeInput): Promise<ClientToolResult> {
  const { language, source, timeout = 5000 } = input;

  if (!source) {
    return { success: false, result: null, error: 'source parameter is required' };
  }

  try {
    let result: CodeResult;

    if (language === 'javascript') {
      result = await runJavaScript(source, timeout);
    } else if (language === 'html') {
      result = await runHtml(source, timeout);
    } else {
      return { success: false, result: { logs: [] }, error: `Unsupported language: ${language}` };
    }

    return { success: true, result };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return { success: false, result: { logs: [] }, error: msg };
  }
}

// -----------------------------------------------------------------------
// Dispatcher
// -----------------------------------------------------------------------

/**
 * Execute a client-side tool by name with the given input object.
 *
 * Dispatches to runThink, runCode, or runEditor based on toolName.
 * Returns a normalized ClientToolResult regardless of which tool ran.
 */
export async function executeClientTool(
  toolName: string,
  input: Record<string, unknown>,
  sessionId?: string,
): Promise<ClientToolResult> {
  switch (toolName) {
    case 'think':
      return runThink(input as unknown as ThinkInput, sessionId);

    case 'code':
      return runCode(input as unknown as CodeInput);

    case 'editor':
      return runEditor(input as unknown as EditorInput);

    default:
      return {
        success: false,
        result: null,
        error: `${toolName} is not a client-side tool`,
      };
  }
}
