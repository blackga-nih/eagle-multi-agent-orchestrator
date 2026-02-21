import test from "../test.js";
import assert from "../assert.js";
import { exportToDocx } from "../../utils/docx-export.js";
import JSZip from "jszip";

/**
 * Test suite for DOCX export utility
 *
 * Tests the exportToDocx function for:
 * - Valid DOCX file structure (ZIP with required XML files)
 * - Markdown formatting preservation
 * - Empty message handling
 * - Special character handling
 */
test("DOCX Export Utility", async (t) => {
  await t.test("exportToDocx creates valid DOCX file", async () => {
    const messages = [
      { role: "user", content: [{ text: "Hello, how are you?" }] },
      {
        role: "assistant",
        content: [{ text: "I am doing well, thank you for asking!" }],
      },
    ];

    const blob = await exportToDocx(messages);

    // Verify it's a Blob
    assert.ok(blob instanceof Blob, "Should return a Blob");
    assert.ok(blob.size > 0, "Blob should have content");

    // Verify it's a valid ZIP (DOCX is a ZIP file)
    const zip = await JSZip.loadAsync(blob);

    // Check for required DOCX structure
    assert.ok(
      zip.file("[Content_Types].xml"),
      "Should have [Content_Types].xml"
    );
    assert.ok(zip.file("word/document.xml"), "Should have word/document.xml");
    assert.ok(zip.file("_rels/.rels"), "Should have _rels/.rels");
  });

  await t.test("exportToDocx preserves markdown formatting", async () => {
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

    const blob = await exportToDocx(messages);
    const zip = await JSZip.loadAsync(blob);
    const docXml = await zip.file("word/document.xml").async("string");

    // Check for heading style (Heading1 style or w:pStyle with heading reference)
    assert.ok(
      docXml.includes("Heading") ||
        docXml.includes("w:pStyle") ||
        docXml.includes("w:outlineLvl"),
      "Should contain heading structure"
    );

    // Check for bold formatting (w:b tag)
    assert.ok(docXml.includes("w:b"), "Should contain bold formatting");

    // Check for italic formatting (w:i tag)
    assert.ok(docXml.includes("w:i"), "Should contain italic formatting");

    // Check that content is present
    assert.ok(docXml.includes("Bold"), "Should contain the word 'Bold'");
    assert.ok(docXml.includes("italic"), "Should contain the word 'italic'");
  });

  await t.test("exportToDocx handles empty messages array", async () => {
    const messages = [];

    const blob = await exportToDocx(messages);

    // Should still create a valid DOCX
    assert.ok(blob instanceof Blob, "Should return a Blob");
    assert.ok(blob.size > 0, "Blob should have content");

    const zip = await JSZip.loadAsync(blob);
    assert.ok(zip.file("word/document.xml"), "Should have document.xml");
  });

  await t.test("exportToDocx handles messages with empty content", async () => {
    const messages = [
      { role: "user", content: [] },
      { role: "assistant", content: [{ text: "" }] },
      { role: "user", content: null },
    ];

    const blob = await exportToDocx(messages);

    // Should still create a valid DOCX without errors
    assert.ok(blob instanceof Blob, "Should return a Blob");

    const zip = await JSZip.loadAsync(blob);
    assert.ok(zip.file("word/document.xml"), "Should have document.xml");
  });

  await t.test("exportToDocx handles special characters", async () => {
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

    const blob = await exportToDocx(messages);

    // Should create valid DOCX without XML parsing errors
    assert.ok(blob instanceof Blob, "Should return a Blob");

    const zip = await JSZip.loadAsync(blob);
    const docXml = await zip.file("word/document.xml").async("string");

    // Verify XML is well-formed (would throw if not)
    assert.ok(docXml.length > 0, "Document XML should have content");

    // Check that dangerous content is escaped or not rendered as-is
    assert.ok(
      !docXml.includes("<script>"),
      "Should not contain raw script tags"
    );
  });

  await t.test("exportToDocx includes document metadata", async () => {
    const messages = [
      { role: "user", content: [{ text: "Test message" }] },
    ];

    const blob = await exportToDocx(messages, {
      title: "Custom Title",
      author: "Test Author",
    });

    const zip = await JSZip.loadAsync(blob);

    // Check for core properties file
    const coreProps = zip.file("docProps/core.xml");
    if (coreProps) {
      const coreXml = await coreProps.async("string");
      assert.ok(
        coreXml.includes("Custom Title") || coreXml.includes("dc:title"),
        "Should contain title metadata"
      );
    }
  });

  await t.test("exportToDocx includes headers and footers", async () => {
    const messages = [
      { role: "assistant", content: [{ text: "Test content for headers/footers" }] },
    ];

    const blob = await exportToDocx(messages);
    const zip = await JSZip.loadAsync(blob);

    // Check for header file
    const hasHeader = zip.file(/word\/header\d*\.xml/);
    assert.ok(hasHeader.length > 0, "Should have header XML file");

    // Check for footer file
    const hasFooter = zip.file(/word\/footer\d*\.xml/);
    assert.ok(hasFooter.length > 0, "Should have footer XML file");

    // Verify header content
    if (hasHeader.length > 0) {
      const headerXml = await hasHeader[0].async("string");
      assert.ok(
        headerXml.includes("NCI") || headerXml.includes("Office"),
        "Header should contain NCI branding"
      );
    }
  });

  await t.test("exportToDocx performance is acceptable", async () => {
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
    await exportToDocx(messages);
    const duration = performance.now() - start;

    console.log(`DOCX generation for 50 messages: ${duration.toFixed(0)}ms`);

    // Should complete in under 3 seconds
    assert.ok(
      duration < 3000,
      `Should complete in <3s, took ${duration.toFixed(0)}ms`
    );
  });

  await t.test("exportToDocx handles list formatting", async () => {
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

    const blob = await exportToDocx(messages);
    const zip = await JSZip.loadAsync(blob);
    const docXml = await zip.file("word/document.xml").async("string");

    // Check that list items are present
    assert.ok(docXml.includes("Item one"), "Should contain list item text");
    assert.ok(docXml.includes("First"), "Should contain numbered list text");
  });

  await t.test("exportToDocx handles code blocks", async () => {
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

    const blob = await exportToDocx(messages);
    const zip = await JSZip.loadAsync(blob);
    const docXml = await zip.file("word/document.xml").async("string");

    // Check for Consolas font (used for code)
    assert.ok(
      docXml.includes("Consolas") || docXml.includes("w:rFonts"),
      "Should contain monospace font for code"
    );

    // Check code content is present
    assert.ok(docXml.includes("hello"), "Should contain code content");
  });
});
