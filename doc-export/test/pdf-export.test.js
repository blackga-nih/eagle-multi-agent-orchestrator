import test from "../test.js";
import assert from "../assert.js";
import { exportToPdf } from "../../utils/pdf-export.js";

/**
 * Test suite for PDF export utility
 *
 * Tests the exportToPdf function for:
 * - Valid PDF file structure (magic bytes %PDF)
 * - Markdown formatting preservation
 * - Empty message handling
 * - Special character handling
 */
test("PDF Export Utility", async (t) => {
  await t.test("exportToPdf creates valid PDF file", async () => {
    const messages = [
      { role: "user", content: [{ text: "Hello, how are you?" }] },
      {
        role: "assistant",
        content: [{ text: "I am doing well, thank you for asking!" }],
      },
    ];

    const blob = await exportToPdf(messages);

    // Verify it's a Blob
    assert.ok(blob instanceof Blob, "Should return a Blob");
    assert.ok(blob.size > 0, "Blob should have content");

    // Verify PDF magic bytes (%PDF)
    const arrayBuffer = await blob.arrayBuffer();
    const bytes = new Uint8Array(arrayBuffer);
    assert.equal(bytes[0], 0x25, "First byte should be % (0x25)");
    assert.equal(bytes[1], 0x50, "Second byte should be P (0x50)");
    assert.equal(bytes[2], 0x44, "Third byte should be D (0x44)");
    assert.equal(bytes[3], 0x46, "Fourth byte should be F (0x46)");
  });

  await t.test("exportToPdf preserves markdown formatting", async () => {
    const messages = [
      {
        role: "assistant",
        content: [
          {
            text: "# Heading\n\n**Bold** and *italic* text.\n\n```js\nconst x = 1;\n```",
          },
        ],
      },
    ];

    const blob = await exportToPdf(messages);

    // Verify it creates a valid PDF
    assert.ok(blob instanceof Blob, "Should return a Blob");
    assert.ok(blob.size > 1000, "PDF with formatting should have substantial content");

    // Verify PDF structure
    const arrayBuffer = await blob.arrayBuffer();
    const bytes = new Uint8Array(arrayBuffer);
    assert.equal(bytes[0], 0x25, "Should be valid PDF (magic bytes)");
  });

  await t.test("exportToPdf handles empty messages array", async () => {
    const messages = [];

    const blob = await exportToPdf(messages);

    // Should still create a valid PDF
    assert.ok(blob instanceof Blob, "Should return a Blob");
    assert.ok(blob.size > 0, "Blob should have content");

    // Verify PDF magic bytes
    const arrayBuffer = await blob.arrayBuffer();
    const bytes = new Uint8Array(arrayBuffer);
    assert.equal(bytes[0], 0x25, "Should be valid PDF");
  });

  await t.test("exportToPdf handles messages with empty content", async () => {
    const messages = [
      { role: "user", content: [] },
      { role: "assistant", content: [{ text: "" }] },
      { role: "user", content: null },
    ];

    const blob = await exportToPdf(messages);

    // Should still create a valid PDF without errors
    assert.ok(blob instanceof Blob, "Should return a Blob");

    const arrayBuffer = await blob.arrayBuffer();
    const bytes = new Uint8Array(arrayBuffer);
    assert.equal(bytes[0], 0x25, "Should be valid PDF");
  });

  await t.test("exportToPdf handles special characters", async () => {
    const messages = [
      {
        role: "user",
        content: [{ text: "Test with <script>alert('xss')</script> and & < > characters" }],
      },
      {
        role: "assistant",
        content: [{ text: "Response with \"quotes\" and 'apostrophes'" }],
      },
    ];

    const blob = await exportToPdf(messages);

    // Should create valid PDF without errors
    assert.ok(blob instanceof Blob, "Should return a Blob");

    const arrayBuffer = await blob.arrayBuffer();
    const bytes = new Uint8Array(arrayBuffer);
    assert.equal(bytes[0], 0x25, "Should be valid PDF");
    assert.ok(blob.size > 1000, "PDF should have content");
  });

  await t.test("exportToPdf includes document metadata", async () => {
    const messages = [
      { role: "user", content: [{ text: "Test message" }] },
    ];

    const blob = await exportToPdf(messages, {
      title: "Custom Title",
      author: "Test Author",
    });

    // Verify PDF is created with custom options
    assert.ok(blob instanceof Blob, "Should return a Blob");
    assert.ok(blob.size > 0, "Blob should have content");

    // Check PDF content for metadata (jsPDF includes it in the PDF structure)
    const text = await blob.text();
    assert.ok(
      text.includes("Custom Title") || text.includes("/Title"),
      "Should contain title metadata"
    );
  });

  await t.test("exportToPdf performance is acceptable", async () => {
    // Create a larger conversation (50 messages)
    const messages = Array(50)
      .fill(null)
      .map((_, i) => ({
        role: i % 2 === 0 ? "user" : "assistant",
        content: [
          {
            text: `Message ${i}: Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. **Bold text** and *italic text* for formatting.`,
          },
        ],
      }));

    const start = performance.now();
    await exportToPdf(messages);
    const duration = performance.now() - start;

    console.log(`PDF generation for 50 messages: ${duration.toFixed(0)}ms`);

    // Should complete in under 5 seconds
    assert.ok(
      duration < 5000,
      `Should complete in <5s, took ${duration.toFixed(0)}ms`
    );
  });

  await t.test("exportToPdf handles list formatting", async () => {
    const messages = [
      {
        role: "assistant",
        content: [
          {
            text: "Here's a list:\n- Item one\n- Item two\n- Item three\n\nAnd a numbered list:\n1. First\n2. Second\n3. Third",
          },
        ],
      },
    ];

    const blob = await exportToPdf(messages);

    // Verify valid PDF is created
    assert.ok(blob instanceof Blob, "Should return a Blob");
    assert.ok(blob.size > 1000, "PDF with lists should have substantial content");

    const arrayBuffer = await blob.arrayBuffer();
    const bytes = new Uint8Array(arrayBuffer);
    assert.equal(bytes[0], 0x25, "Should be valid PDF");
  });

  await t.test("exportToPdf handles code blocks", async () => {
    const messages = [
      {
        role: "assistant",
        content: [
          {
            text: "Here's some code:\n\n```javascript\nfunction hello() {\n  console.log('Hello');\n}\n```\n\nAnd inline `code` too.",
          },
        ],
      },
    ];

    const blob = await exportToPdf(messages);

    // Verify valid PDF is created
    assert.ok(blob instanceof Blob, "Should return a Blob");
    assert.ok(blob.size > 1000, "PDF with code should have substantial content");

    const arrayBuffer = await blob.arrayBuffer();
    const bytes = new Uint8Array(arrayBuffer);
    assert.equal(bytes[0], 0x25, "Should be valid PDF");
  });

  await t.test("exportToPdf handles blockquotes", async () => {
    const messages = [
      {
        role: "assistant",
        content: [
          {
            text: "Here's a quote:\n\n> This is an important quote\n> that spans multiple lines\n\nAfter the quote.",
          },
        ],
      },
    ];

    const blob = await exportToPdf(messages);

    // Verify valid PDF is created
    assert.ok(blob instanceof Blob, "Should return a Blob");
    assert.ok(blob.size > 500, "PDF with blockquote should have content");

    const arrayBuffer = await blob.arrayBuffer();
    const bytes = new Uint8Array(arrayBuffer);
    assert.equal(bytes[0], 0x25, "Should be valid PDF");
  });

  await t.test("exportToPdf handles multiple headings", async () => {
    const messages = [
      {
        role: "assistant",
        content: [
          {
            text: "# Main Heading\n\nSome text.\n\n## Subheading\n\nMore text.\n\n### Third Level\n\nEven more text.",
          },
        ],
      },
    ];

    const blob = await exportToPdf(messages);

    // Verify valid PDF is created
    assert.ok(blob instanceof Blob, "Should return a Blob");
    assert.ok(blob.size > 1000, "PDF with headings should have substantial content");

    const arrayBuffer = await blob.arrayBuffer();
    const bytes = new Uint8Array(arrayBuffer);
    assert.equal(bytes[0], 0x25, "Should be valid PDF");
  });
});
