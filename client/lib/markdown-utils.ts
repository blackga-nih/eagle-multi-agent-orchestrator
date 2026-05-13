/**
 * Markdown utility functions for sanitizing and normalizing content.
 * Shared between MarkdownRenderer and chat message rendering.
 */

/**
 * Normalize emphasis markers in a table cell.
 * Fixes common malformed patterns that cause raw ** to display:
 * - `\*\*text\*\*` → `**text**` (escaped asterisks)
 * - `****text****` → `**text**` (doubled emphasis)
 * - Unbalanced markers
 *
 * Skips content inside backticks (inline code).
 */
function normalizeTableCellEmphasis(cell: string): string {
  // Don't modify cells that are inline code
  if (cell.trim().startsWith('`') && cell.trim().endsWith('`')) {
    return cell;
  }

  let result = cell;

  // Fix escaped asterisks: \*\* → **
  result = result.replace(/\\\*\\\*/g, '**');
  result = result.replace(/\\\*/g, '*');

  // Fix quadruple asterisks (doubled bold): ****text**** → **text**
  result = result.replace(/\*{4,}([^*]+)\*{4,}/g, '**$1**');

  // Fix triple asterisks at boundaries: ***text*** → **text** (treat as bold, not bold+italic)
  result = result.replace(/\*{3}([^*]+)\*{3}/g, '**$1**');

  return result;
}

/**
 * Sanitize malformed markdown tables:
 * - Collapse rows that are mostly empty cells (| | | | |)
 * - Normalize inconsistent column counts
 * - Remove separator-only rows with no header
 * - Normalize emphasis markers in cells (EAGLE-303)
 */
export function sanitizeTables(md: string): string {
  return md.replace(
    // Match a contiguous block of pipe-table lines
    /(?:^[|].*[|]\s*$\n?)+/gm,
    (tableBlock) => {
      const lines = tableBlock.trim().split('\n');
      const cleaned: string[] = [];
      for (const line of lines) {
        // Strip each cell and check if it has content
        const cells = line.split('|').slice(1, -1); // drop outer empty strings
        const hasContent = cells.some((c) => c.trim().length > 0 && !/^[-:]+$/.test(c.trim()));
        const isSeparator = cells.every((c) => /^[\s-:]*$/.test(c));

        if (isSeparator && cleaned.length > 0) {
          // Keep separator rows (---|---) only once after a header
          const prevIsSep =
            cleaned.length > 0 &&
            cleaned[cleaned.length - 1]
              .split('|')
              .slice(1, -1)
              .every((c) => /^[\s-:]*$/.test(c));
          if (!prevIsSep) cleaned.push(line);
        } else if (hasContent) {
          // Normalize emphasis in each cell (EAGLE-303)
          const normalizedCells = cells.map(normalizeTableCellEmphasis);
          cleaned.push('|' + normalizedCells.join('|') + '|');
        }
        // Skip lines that are entirely empty cells
      }
      return cleaned.length > 0 ? cleaned.join('\n') + '\n' : '';
    },
  );
}

/**
 * Pre-process markdown content before rendering.
 * Applies table sanitization and other fixes.
 */
export function preprocessMarkdown(content: string): string {
  if (!content) return content;
  return sanitizeTables(content);
}
