import {
  Document,
  Packer,
  Paragraph,
  TextRun,
  HeadingLevel,
  AlignmentType,
  BorderStyle,
  Header,
  Footer,
  PageNumber,
  ShadingType,
} from "docx";

/**
 * NCI Color palette for document styling
 */
const NCI_COLORS = {
  primary: "00205B", // NCI Blue
  secondary: "0070C0", // Accent Blue
  text: "333333", // Body text
  userMessage: "1565C0", // User label (blue)
  assistantMessage: "2E7D32", // Assistant label (green)
  muted: "666666", // Muted text
  codeBackground: "F5F5F5", // Code block background
};

/**
 * Export chat conversation to DOCX format
 *
 * @param {Array} messages - Chat messages array with role and content
 * @param {Object} options - Export options
 * @param {string} [options.title='Conversation Export'] - Document title
 * @param {boolean} [options.includeTimestamps=true] - Include message timestamps
 * @param {string} [options.author='NCI OA Agent'] - Document author metadata
 * @returns {Promise<Blob>} DOCX file as Blob
 */
export async function exportToDocx(messages, options = {}) {
  const {
    title = "Conversation Export",
    includeTimestamps = true,
    author = "NCI OA Agent",
  } = options;

  const children = [];

  // Title
  children.push(
    new Paragraph({
      text: title,
      heading: HeadingLevel.TITLE,
      alignment: AlignmentType.CENTER,
    })
  );

  // Subtitle with export date
  children.push(
    new Paragraph({
      children: [
        new TextRun({
          text: `Exported: ${new Date().toLocaleString()}`,
          italics: true,
          color: NCI_COLORS.muted,
        }),
      ],
      alignment: AlignmentType.CENTER,
      spacing: { after: 400 },
    })
  );

  // Horizontal line separator
  children.push(
    new Paragraph({
      border: {
        bottom: {
          color: "CCCCCC",
          space: 1,
          style: BorderStyle.SINGLE,
          size: 6,
        },
      },
      spacing: { after: 400 },
    })
  );

  // Process each message
  for (const message of messages) {
    const roleLabel = message.role === "user" ? "User" : "Ada (AI Assistant)";
    const roleColor =
      message.role === "user"
        ? NCI_COLORS.userMessage
        : NCI_COLORS.assistantMessage;
    const textContent = extractTextContent(message.content);

    // Skip empty messages
    if (!textContent.trim()) continue;

    // Role header
    children.push(
      new Paragraph({
        children: [
          new TextRun({
            text: roleLabel,
            bold: true,
            color: roleColor,
            size: 24, // 12pt
          }),
        ],
        spacing: { before: 300, after: 100 },
      })
    );

    // Message content - parse markdown to paragraphs
    const paragraphs = markdownToParagraphs(textContent);
    children.push(...paragraphs);

    // Spacer between messages
    children.push(new Paragraph({ spacing: { after: 200 } }));
  }

  // Create document with headers and footers
  const doc = new Document({
    creator: author,
    title: title,
    description: "Chat conversation export from NCI OA Agent",
    sections: [
      {
        properties: {
          page: {
            margin: {
              top: 1440, // 1 inch in twips (1440 twips = 1 inch)
              right: 1080, // 0.75 inch
              bottom: 1440,
              left: 1080,
            },
          },
        },
        headers: {
          default: new Header({
            children: [
              new Paragraph({
                children: [
                  new TextRun({
                    text: "NCI Office of Acquisitions - Chat Export",
                    size: 18, // 9pt
                    color: "888888",
                  }),
                ],
                alignment: AlignmentType.CENTER,
              }),
            ],
          }),
        },
        footers: {
          default: new Footer({
            children: [
              new Paragraph({
                children: [
                  new TextRun({ text: "Page " }),
                  new TextRun({ children: [PageNumber.CURRENT] }),
                  new TextRun({ text: " of " }),
                  new TextRun({ children: [PageNumber.TOTAL_PAGES] }),
                ],
                alignment: AlignmentType.CENTER,
              }),
            ],
          }),
        },
        children: children,
      },
    ],
  });

  // Generate blob
  const blob = await Packer.toBlob(doc);
  return blob;
}

/**
 * Extract text content from message content array
 *
 * @param {Array|string|null} content - Message content (array of content blocks or string)
 * @returns {string} Extracted text content
 */
function extractTextContent(content) {
  if (!content) return "";

  // If content is a string, return it directly
  if (typeof content === "string") return content;

  // If content is an array, extract text from each block
  if (Array.isArray(content)) {
    return content
      .filter((c) => c?.text)
      .map((c) => c.text)
      .join("\n\n");
  }

  return "";
}

/**
 * Convert markdown text to docx Paragraph elements
 *
 * @param {string} markdown - Markdown formatted text
 * @returns {Array<Paragraph>} Array of Paragraph objects
 */
function markdownToParagraphs(markdown) {
  const paragraphs = [];

  // Split into blocks by double newlines, but preserve code blocks
  const blocks = splitMarkdownBlocks(markdown);

  for (const block of blocks) {
    if (!block.trim()) continue;

    // Code blocks (```)
    if (block.startsWith("```")) {
      const codeContent = block.replace(/```\w*\n?/g, "").trim();
      paragraphs.push(
        new Paragraph({
          children: [
            new TextRun({
              text: codeContent,
              font: "Consolas",
              size: 20, // 10pt
            }),
          ],
          shading: {
            type: ShadingType.SOLID,
            color: NCI_COLORS.codeBackground,
          },
          spacing: { before: 100, after: 100 },
        })
      );
    }
    // Heading 1 (#)
    else if (block.startsWith("# ") && !block.startsWith("## ")) {
      paragraphs.push(
        new Paragraph({
          text: block.replace(/^# /, ""),
          heading: HeadingLevel.HEADING_1,
        })
      );
    }
    // Heading 2 (##)
    else if (block.startsWith("## ") && !block.startsWith("### ")) {
      paragraphs.push(
        new Paragraph({
          text: block.replace(/^## /, ""),
          heading: HeadingLevel.HEADING_2,
        })
      );
    }
    // Heading 3 (###)
    else if (block.startsWith("### ") && !block.startsWith("#### ")) {
      paragraphs.push(
        new Paragraph({
          text: block.replace(/^### /, ""),
          heading: HeadingLevel.HEADING_3,
        })
      );
    }
    // Heading 4 (####)
    else if (block.startsWith("#### ") && !block.startsWith("##### ")) {
      paragraphs.push(
        new Paragraph({
          text: block.replace(/^#### /, ""),
          heading: HeadingLevel.HEADING_4,
        })
      );
    }
    // Heading 5 (#####)
    else if (block.startsWith("##### ") && !block.startsWith("###### ")) {
      paragraphs.push(
        new Paragraph({
          text: block.replace(/^##### /, ""),
          heading: HeadingLevel.HEADING_5,
        })
      );
    }
    // Heading 6 (######)
    else if (block.startsWith("###### ")) {
      paragraphs.push(
        new Paragraph({
          text: block.replace(/^###### /, ""),
          heading: HeadingLevel.HEADING_6,
        })
      );
    }
    // Bullet list items
    else if (block.match(/^[-*]\s/)) {
      const listItems = block.split("\n").filter((line) => line.match(/^[-*]\s/));
      for (const item of listItems) {
        const text = item.replace(/^[-*]\s/, "");
        paragraphs.push(
          new Paragraph({
            children: parseInlineFormatting(text),
            bullet: { level: 0 },
            spacing: { after: 100 },
          })
        );
      }
    }
    // Numbered list items
    else if (block.match(/^\d+\.\s/)) {
      const listItems = block.split("\n").filter((line) => line.match(/^\d+\.\s/));
      for (const item of listItems) {
        const text = item.replace(/^\d+\.\s/, "");
        paragraphs.push(
          new Paragraph({
            children: parseInlineFormatting(text),
            numbering: { reference: "default-numbering", level: 0 },
            spacing: { after: 100 },
          })
        );
      }
    }
    // Blockquote
    else if (block.startsWith("> ")) {
      const quoteText = block.replace(/^> ?/gm, "");
      paragraphs.push(
        new Paragraph({
          children: parseInlineFormatting(quoteText),
          indent: { left: 720 }, // 0.5 inch
          border: {
            left: {
              color: "CCCCCC",
              space: 1,
              style: BorderStyle.SINGLE,
              size: 24,
            },
          },
          spacing: { before: 100, after: 100 },
        })
      );
    }
    // Regular paragraphs with inline formatting
    else {
      paragraphs.push(
        new Paragraph({
          children: parseInlineFormatting(block),
          spacing: { after: 200 },
        })
      );
    }
  }

  return paragraphs;
}

/**
 * Split markdown into blocks, preserving code blocks as single units
 *
 * @param {string} markdown - Markdown text
 * @returns {Array<string>} Array of markdown blocks
 */
function splitMarkdownBlocks(markdown) {
  const blocks = [];
  const lines = markdown.split("\n");
  let currentBlock = [];
  let inCodeBlock = false;

  for (const line of lines) {
    if (line.startsWith("```")) {
      if (inCodeBlock) {
        // End of code block
        currentBlock.push(line);
        blocks.push(currentBlock.join("\n"));
        currentBlock = [];
        inCodeBlock = false;
      } else {
        // Start of code block
        if (currentBlock.length > 0) {
          blocks.push(currentBlock.join("\n"));
          currentBlock = [];
        }
        currentBlock.push(line);
        inCodeBlock = true;
      }
    } else if (inCodeBlock) {
      currentBlock.push(line);
    } else if (line.trim() === "") {
      // Empty line - end current block
      if (currentBlock.length > 0) {
        blocks.push(currentBlock.join("\n"));
        currentBlock = [];
      }
    } else {
      currentBlock.push(line);
    }
  }

  // Don't forget the last block
  if (currentBlock.length > 0) {
    blocks.push(currentBlock.join("\n"));
  }

  return blocks;
}

/**
 * Parse inline markdown formatting (bold, italic, code) into TextRun array
 *
 * @param {string} text - Text with inline markdown formatting
 * @returns {Array<TextRun>} Array of TextRun objects
 */
function parseInlineFormatting(text) {
  const runs = [];

  // Regex to match **bold**, *italic*, `code`, and ***bold italic***
  // Order matters: check longer patterns first
  const regex = /(\*\*\*[^*]+\*\*\*|\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    // Text before match
    if (match.index > lastIndex) {
      const plainText = text.slice(lastIndex, match.index);
      if (plainText) {
        runs.push(new TextRun({ text: plainText }));
      }
    }

    const content = match[0];

    // Bold italic (***text***)
    if (content.startsWith("***") && content.endsWith("***")) {
      runs.push(
        new TextRun({
          text: content.slice(3, -3),
          bold: true,
          italics: true,
        })
      );
    }
    // Bold (**text**)
    else if (content.startsWith("**") && content.endsWith("**")) {
      runs.push(
        new TextRun({
          text: content.slice(2, -2),
          bold: true,
        })
      );
    }
    // Italic (*text*)
    else if (content.startsWith("*") && content.endsWith("*")) {
      runs.push(
        new TextRun({
          text: content.slice(1, -1),
          italics: true,
        })
      );
    }
    // Inline code (`text`)
    else if (content.startsWith("`") && content.endsWith("`")) {
      runs.push(
        new TextRun({
          text: content.slice(1, -1),
          font: "Consolas",
          shading: {
            type: ShadingType.SOLID,
            color: "F0F0F0",
          },
        })
      );
    }

    lastIndex = regex.lastIndex;
  }

  // Remaining text after last match
  if (lastIndex < text.length) {
    const remainingText = text.slice(lastIndex);
    if (remainingText) {
      runs.push(new TextRun({ text: remainingText }));
    }
  }

  // If no formatting found, return the whole text as a single run
  return runs.length > 0 ? runs : [new TextRun({ text })];
}
