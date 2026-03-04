/**
 * Generate a UUID v4 using cryptographically secure random values.
 *
 * crypto.randomUUID() only works in secure contexts (HTTPS or localhost).
 * This fallback uses crypto.getRandomValues() which works everywhere.
 *
 * No Math.random() fallback — all modern browsers support crypto.getRandomValues().
 */
export function generateUUID(): string {
  // Use crypto.randomUUID if available (secure context)
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }

  // Fallback using crypto.getRandomValues (works in non-secure contexts)
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);

    // Set version (4) and variant (RFC 4122)
    bytes[6] = (bytes[6] & 0x0f) | 0x40; // Version 4
    bytes[8] = (bytes[8] & 0x3f) | 0x80; // Variant RFC 4122

    // Convert to hex string with dashes
    const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  // crypto API unavailable — throw rather than fall back to insecure Math.random()
  throw new Error('Crypto API unavailable: cannot generate secure UUID');
}
