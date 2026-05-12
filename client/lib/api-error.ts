const HTML_TAG_RE = /<[^>]*>/g;
const HTML_ENTITY_RE = /&(?:[a-z]+|#\d+|#x[\da-f]+);/gi;

export type ApiErrorPayload = {
  detail?: unknown;
  details?: unknown;
  error?: unknown;
  message?: unknown;
};

function looksLikeHtml(value: string): boolean {
  const trimmed = value.trim().toLowerCase();
  return (
    trimmed.startsWith('<!doctype html') ||
    trimmed.startsWith('<html') ||
    /<\s*(html|body|head|center|h1|title)\b/i.test(value)
  );
}

function decodeCommonHtmlEntities(value: string): string {
  return value
    .replace(/&nbsp;/gi, ' ')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&amp;/gi, '&')
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'");
}

export function normalizeApiErrorMessage(
  value: unknown,
  fallback = 'Request failed',
): string {
  if (typeof value !== 'string') return fallback;

  const trimmed = value.trim();
  if (!trimmed) return fallback;

  if (looksLikeHtml(trimmed)) {
    const text = decodeCommonHtmlEntities(trimmed)
      .replace(/<!--[\s\S]*?-->/g, ' ')
      .replace(HTML_TAG_RE, ' ')
      .replace(HTML_ENTITY_RE, ' ')
      .replace(/\s+/g, ' ')
      .trim();

    if (/403\s+forbidden/i.test(text)) {
      return 'Upload failed: access was denied by the backend.';
    }
    return text ? `Request failed: ${text.slice(0, 160)}` : fallback;
  }

  return trimmed.length > 240 ? `${trimmed.slice(0, 237)}...` : trimmed;
}

export function getApiErrorMessage(
  payload: ApiErrorPayload,
  fallback = 'Request failed',
): string {
  return normalizeApiErrorMessage(
    payload.detail ?? payload.details ?? payload.error ?? payload.message,
    fallback,
  );
}

export async function parseBackendError(response: Response): Promise<string> {
  const text = await response.text().catch(() => '');
  if (!text) return `Backend error: ${response.status}`;

  try {
    const parsed = JSON.parse(text) as ApiErrorPayload;
    return getApiErrorMessage(parsed, `Backend error: ${response.status}`);
  } catch {
    return normalizeApiErrorMessage(text, `Backend error: ${response.status}`);
  }
}
