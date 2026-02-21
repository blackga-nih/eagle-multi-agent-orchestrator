/**
 * PDF Export Utility
 *
 * Converts chat conversation messages to a professionally formatted PDF document
 * using jsPDF. Supports markdown formatting (headings, bold, italic, code blocks,
 * lists) and NCI branding.
 *
 * @module pdf-export
 */

import { jsPDF } from "jspdf";

// NCI brand colors (hex without # for jsPDF)
const NCI_COLORS = {
  primary: [0, 32, 91], // #00205B - RGB
  userMessage: [21, 101, 192], // #1565C0
  assistantMessage: [46, 125, 50], // #2E7D32
  muted: [102, 102, 102], // #666666
  codeBackground: [245, 245, 245], // #F5F5F5
  black: [0, 0, 0],
  white: [255, 255, 255],
};

// Page layout constants (in mm)
const PAGE = {
  width: 215.9, // Letter width
  height: 279.4, // Letter height
  marginTop: 25,
  marginBottom: 25,
  marginLeft: 20,
  marginRight: 20,
  headerHeight: 15,
  footerHeight: 15,
};

const CONTENT_WIDTH = PAGE.width - PAGE.marginLeft - PAGE.marginRight;
const CONTENT_START_Y = PAGE.marginTop + PAGE.headerHeight;
const CONTENT_END_Y = PAGE.height - PAGE.marginBottom - PAGE.footerHeight;

/**
 * Export conversation messages to PDF format
 *
 * @param {Array} messages - Array of message objects with role and content
 * @param {Object} [options={}] - Export options
 * @param {string} [options.title="Conversation Export"] - Document title
 * @param {string} [options.author="NCI OA Agent"] - Document author
 * @returns {Promise<Blob>} PDF file as Blob
 */
export async function exportToPdf(messages, options = {}) {
  const { title = "Conversation Export", author = "NCI OA Agent" } = options;

  const doc = new jsPDF({
    orientation: "portrait",
    unit: "mm",
    format: "letter",
  });

  // Set document properties
  doc.setProperties({
    title,
    author,
    creator: "NCI OA Agent",
    subject: "Chat Conversation Export",
  });

  let currentY = CONTENT_START_Y;
  let pageNumber = 1;

  // Add header and footer to first page
  addHeader(doc, title);
  addFooter(doc, pageNumber);

  // Add title section
  currentY = addTitleSection(doc, currentY, title);

  // Process each message
  for (const message of messages) {
    const text = extractTextContent(message.content);
    if (!text) continue;

    const role = message.role === "user" ? "User" : "Ada (AI Assistant)";
    const roleColor =
      message.role === "user"
        ? NCI_COLORS.userMessage
        : NCI_COLORS.assistantMessage;

    // Check if we need a new page before starting a message
    if (currentY > CONTENT_END_Y - 30) {
      doc.addPage();
      pageNumber++;
      addHeader(doc, title);
      addFooter(doc, pageNumber);
      currentY = CONTENT_START_Y;
    }

    // Add role label
    doc.setFont("helvetica", "bold");
    doc.setFontSize(11);
    doc.setTextColor(...roleColor);
    doc.text(role, PAGE.marginLeft, currentY);
    currentY += 6;

    // Parse and render markdown content
    currentY = renderMarkdownContent(doc, text, currentY, () => {
      doc.addPage();
      pageNumber++;
      addHeader(doc, title);
      addFooter(doc, pageNumber);
      return CONTENT_START_Y;
    });

    // Add spacing between messages
    currentY += 8;
  }

  // Return as Blob
  return doc.output("blob");
}

/**
 * Add header to the current page
 */
function addHeader(doc, title) {
  doc.setFillColor(...NCI_COLORS.primary);
  doc.rect(0, 0, PAGE.width, PAGE.headerHeight, "F");

  doc.setFont("helvetica", "bold");
  doc.setFontSize(10);
  doc.setTextColor(...NCI_COLORS.white);
  doc.text("NCI Office of Acquisitions", PAGE.marginLeft, 10);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.text(title, PAGE.width - PAGE.marginRight, 10, { align: "right" });
}

/**
 * Add footer to the current page
 */
function addFooter(doc, pageNumber) {
  const footerY = PAGE.height - PAGE.footerHeight + 8;

  doc.setDrawColor(...NCI_COLORS.muted);
  doc.setLineWidth(0.3);
  doc.line(
    PAGE.marginLeft,
    footerY - 5,
    PAGE.width - PAGE.marginRight,
    footerY - 5
  );

  doc.setFont("helvetica", "normal");
  doc.setFontSize(8);
  doc.setTextColor(...NCI_COLORS.muted);

  // Left: Export date
  const dateStr = new Date().toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  doc.text(`Exported: ${dateStr}`, PAGE.marginLeft, footerY);

  // Right: Page number
  doc.text(`Page ${pageNumber}`, PAGE.width - PAGE.marginRight, footerY, {
    align: "right",
  });
}

/**
 * Add title section at the top of the document
 */
function addTitleSection(doc, startY, title) {
  let y = startY;

  // Main title
  doc.setFont("helvetica", "bold");
  doc.setFontSize(18);
  doc.setTextColor(...NCI_COLORS.primary);
  doc.text(title, PAGE.marginLeft, y);
  y += 8;

  // Subtitle
  doc.setFont("helvetica", "normal");
  doc.setFontSize(10);
  doc.setTextColor(...NCI_COLORS.muted);
  const timestamp = new Date().toLocaleString("en-US", {
    dateStyle: "full",
    timeStyle: "short",
  });
  doc.text(`Generated on ${timestamp}`, PAGE.marginLeft, y);
  y += 5;

  // Separator line
  doc.setDrawColor(...NCI_COLORS.muted);
  doc.setLineWidth(0.5);
  doc.line(PAGE.marginLeft, y, PAGE.width - PAGE.marginRight, y);
  y += 10;

  return y;
}

/**
 * Render markdown content to PDF
 */
function renderMarkdownContent(doc, markdown, startY, newPageCallback) {
  let y = startY;
  const blocks = splitMarkdownBlocks(markdown);

  for (const block of blocks) {
    // Check for page break
    if (y > CONTENT_END_Y - 10) {
      y = newPageCallback();
    }

    if (block.type === "heading") {
      y = renderHeading(doc, block.content, block.level, y, newPageCallback);
    } else if (block.type === "code") {
      y = renderCodeBlock(doc, block.content, y, newPageCallback);
    } else if (block.type === "list") {
      y = renderList(doc, block.items, block.ordered, y, newPageCallback);
    } else if (block.type === "blockquote") {
      y = renderBlockquote(doc, block.content, y, newPageCallback);
    } else {
      y = renderParagraph(doc, block.content, y, newPageCallback);
    }

    y += 4; // Spacing between blocks
  }

  return y;
}

/**
 * Split markdown into blocks for rendering
 */
function splitMarkdownBlocks(markdown) {
  const blocks = [];
  const lines = markdown.split("\n");
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Heading
    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      blocks.push({
        type: "heading",
        level: headingMatch[1].length,
        content: headingMatch[2],
      });
      i++;
      continue;
    }

    // Code block
    if (line.startsWith("```")) {
      const codeLines = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      blocks.push({ type: "code", content: codeLines.join("\n") });
      i++;
      continue;
    }

    // Unordered list
    if (line.match(/^[-*+]\s+/)) {
      const items = [];
      while (i < lines.length && lines[i].match(/^[-*+]\s+/)) {
        items.push(lines[i].replace(/^[-*+]\s+/, ""));
        i++;
      }
      blocks.push({ type: "list", items, ordered: false });
      continue;
    }

    // Ordered list
    if (line.match(/^\d+\.\s+/)) {
      const items = [];
      while (i < lines.length && lines[i].match(/^\d+\.\s+/)) {
        items.push(lines[i].replace(/^\d+\.\s+/, ""));
        i++;
      }
      blocks.push({ type: "list", items, ordered: true });
      continue;
    }

    // Blockquote
    if (line.startsWith(">")) {
      const quoteLines = [];
      while (i < lines.length && lines[i].startsWith(">")) {
        quoteLines.push(lines[i].replace(/^>\s*/, ""));
        i++;
      }
      blocks.push({ type: "blockquote", content: quoteLines.join("\n") });
      continue;
    }

    // Regular paragraph (skip empty lines)
    if (line.trim()) {
      const paragraphLines = [];
      while (i < lines.length && lines[i].trim() && !lines[i].match(/^[#>`\-*+]|\d+\./)) {
        paragraphLines.push(lines[i]);
        i++;
      }
      if (paragraphLines.length > 0) {
        blocks.push({ type: "paragraph", content: paragraphLines.join(" ") });
      }
      continue;
    }

    i++;
  }

  return blocks;
}

/**
 * Render a heading
 */
function renderHeading(doc, text, level, startY, newPageCallback) {
  let y = startY;

  const sizes = { 1: 16, 2: 14, 3: 12, 4: 11, 5: 10, 6: 10 };
  const size = sizes[level] || 12;

  if (y > CONTENT_END_Y - 15) {
    y = newPageCallback();
  }

  doc.setFont("helvetica", "bold");
  doc.setFontSize(size);
  doc.setTextColor(...NCI_COLORS.primary);
  doc.text(text, PAGE.marginLeft, y);

  return y + size * 0.5 + 2;
}

/**
 * Render a code block with background
 */
function renderCodeBlock(doc, code, startY, newPageCallback) {
  let y = startY;

  doc.setFont("courier", "normal");
  doc.setFontSize(9);
  doc.setTextColor(...NCI_COLORS.black);

  const lines = code.split("\n");
  const lineHeight = 4;
  const padding = 3;
  const blockHeight = lines.length * lineHeight + padding * 2;

  // Check if we need a new page
  if (y + blockHeight > CONTENT_END_Y) {
    y = newPageCallback();
  }

  // Draw background
  doc.setFillColor(...NCI_COLORS.codeBackground);
  doc.roundedRect(
    PAGE.marginLeft,
    y - 3,
    CONTENT_WIDTH,
    blockHeight,
    2,
    2,
    "F"
  );

  // Render code lines
  y += padding;
  for (const line of lines) {
    const wrappedLines = doc.splitTextToSize(line || " ", CONTENT_WIDTH - padding * 2);
    for (const wrappedLine of wrappedLines) {
      if (y > CONTENT_END_Y - 5) {
        y = newPageCallback();
        // Redraw background on new page
        doc.setFillColor(...NCI_COLORS.codeBackground);
      }
      doc.text(wrappedLine, PAGE.marginLeft + padding, y);
      y += lineHeight;
    }
  }

  doc.setFont("helvetica", "normal");
  return y + padding;
}

/**
 * Render a list (ordered or unordered)
 */
function renderList(doc, items, ordered, startY, newPageCallback) {
  let y = startY;
  const indent = 8;
  const lineHeight = 5;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(10);
  doc.setTextColor(...NCI_COLORS.black);

  items.forEach((item, index) => {
    if (y > CONTENT_END_Y - 10) {
      y = newPageCallback();
    }

    const bullet = ordered ? `${index + 1}.` : "\u2022";
    doc.text(bullet, PAGE.marginLeft, y);

    const wrappedLines = doc.splitTextToSize(
      item,
      CONTENT_WIDTH - indent
    );
    wrappedLines.forEach((line, lineIndex) => {
      if (y > CONTENT_END_Y - 5) {
        y = newPageCallback();
      }
      doc.text(line, PAGE.marginLeft + indent, y);
      y += lineHeight;
    });
  });

  return y;
}

/**
 * Render a blockquote
 */
function renderBlockquote(doc, text, startY, newPageCallback) {
  let y = startY;
  const indent = 8;

  if (y > CONTENT_END_Y - 15) {
    y = newPageCallback();
  }

  // Draw left border
  doc.setDrawColor(...NCI_COLORS.muted);
  doc.setLineWidth(1);

  doc.setFont("helvetica", "italic");
  doc.setFontSize(10);
  doc.setTextColor(...NCI_COLORS.muted);

  const wrappedLines = doc.splitTextToSize(text, CONTENT_WIDTH - indent);
  const lineHeight = 5;
  const blockHeight = wrappedLines.length * lineHeight;

  doc.line(PAGE.marginLeft, y - 2, PAGE.marginLeft, y + blockHeight);

  for (const line of wrappedLines) {
    if (y > CONTENT_END_Y - 5) {
      y = newPageCallback();
    }
    doc.text(line, PAGE.marginLeft + indent, y);
    y += lineHeight;
  }

  doc.setFont("helvetica", "normal");
  return y;
}

/**
 * Render a paragraph with inline formatting
 */
function renderParagraph(doc, text, startY, newPageCallback) {
  let y = startY;

  doc.setFont("helvetica", "normal");
  doc.setFontSize(10);
  doc.setTextColor(...NCI_COLORS.black);

  // Parse inline formatting and render
  const segments = parseInlineFormatting(text);

  // Build plain text for wrapping calculation
  const plainText = segments.map((s) => s.text).join("");
  const wrappedLines = doc.splitTextToSize(plainText, CONTENT_WIDTH);

  // Simple rendering - jsPDF doesn't support mixed formatting per line easily
  // So we render with basic bold/italic detection
  const lineHeight = 5;

  for (const line of wrappedLines) {
    if (y > CONTENT_END_Y - 5) {
      y = newPageCallback();
    }

    // Detect if line has formatting markers and apply
    let renderText = line;
    let fontStyle = "normal";

    // Simple bold detection (text surrounded by **)
    if (line.includes("**") || text.includes("**")) {
      renderText = line.replace(/\*\*/g, "");
      if (text.includes(`**${renderText.trim()}**`)) {
        fontStyle = "bold";
      }
    }

    // Simple italic detection (text surrounded by single *)
    if (line.includes("*") && !line.includes("**")) {
      renderText = line.replace(/\*/g, "");
      if (fontStyle === "bold") {
        fontStyle = "bolditalic";
      } else {
        fontStyle = "italic";
      }
    }

    // Inline code detection
    if (line.includes("`")) {
      renderText = line.replace(/`/g, "");
      doc.setFont("courier", "normal");
    } else {
      doc.setFont("helvetica", fontStyle);
    }

    doc.text(renderText, PAGE.marginLeft, y);
    y += lineHeight;
  }

  doc.setFont("helvetica", "normal");
  return y;
}

/**
 * Parse inline formatting (bold, italic, code)
 */
function parseInlineFormatting(text) {
  const segments = [];
  let remaining = text;

  // Simple regex-based parsing
  const patterns = [
    { regex: /\*\*(.+?)\*\*/g, style: "bold" },
    { regex: /\*(.+?)\*/g, style: "italic" },
    { regex: /`(.+?)`/g, style: "code" },
  ];

  // For simplicity, just strip formatting markers and return plain text
  // jsPDF doesn't handle mixed inline styles well without manual x positioning
  let plainText = remaining;
  for (const pattern of patterns) {
    plainText = plainText.replace(pattern.regex, "$1");
  }

  segments.push({ text: plainText, style: "normal" });
  return segments;
}

/**
 * Extract text content from message content array
 */
function extractTextContent(content) {
  if (!content) return "";
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";

  return content
    .map((block) => {
      if (typeof block === "string") return block;
      if (block?.text) return block.text;
      return "";
    })
    .filter(Boolean)
    .join("\n\n");
}
