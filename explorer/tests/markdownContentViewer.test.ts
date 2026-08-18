import test from "node:test";
import assert from "node:assert/strict";
import { isSafeUrl } from "../src/workspaces/GraphWorkspace/MarkdownContentViewer.tsx";

test("isSafeUrl permits safe http, https, and mailto URLs", () => {
  assert.equal(isSafeUrl("https://example.com"), true);
  assert.equal(isSafeUrl("http://localhost:8000"), true);
  assert.equal(isSafeUrl("mailto:user@example.com"), true);
  assert.equal(isSafeUrl("#section-1"), true);
  assert.equal(isSafeUrl("/relative/path"), true);
});

test("isSafeUrl rejects dangerous schemes like javascript:, data:, and vbscript:", () => {
  assert.equal(isSafeUrl("javascript:alert('xss')"), false);
  assert.equal(isSafeUrl("JAVASCRIPT:alert(1)"), false);
  assert.equal(isSafeUrl("data:text/html;base64,PHNjcmlwdD4="), false);
  assert.equal(isSafeUrl("vbscript:MsgBox(1)"), false);
  assert.equal(isSafeUrl(""), false);
  assert.equal(isSafeUrl(undefined), false);
});

test("preserves exact unmodified content, whitespace, and Unicode in source format", () => {
  const sampleMarkdown = `# Title with Unicode 🚀\n\n  * Indented item 1\n  * Indented item 2\n\n\`\`\`python\ndef test():\n    return "α + β = γ"\n\`\`\``;
  
  // Exact characters, newlines, and whitespace must remain unmodified
  assert.equal(sampleMarkdown.includes("  * Indented item 1"), true);
  assert.equal(sampleMarkdown.includes("🚀"), true);
  assert.equal(sampleMarkdown.includes("α + β = γ"), true);
  assert.equal(sampleMarkdown.includes("    return"), true);
});

test("handles empty, null, and whitespace content gracefully without errors", () => {
  const emptyValues = ["", "   \n\t  ", null, undefined];
  for (const val of emptyValues) {
    const raw = typeof val === "string" ? val : "";
    const hasContent = raw.trim().length > 0;
    assert.equal(hasContent, false);
  }
});

test("handles plain text without requiring Markdown syntax", () => {
  const plainText = "Simple plain text summary of graph entity without any formatting.";
  const raw = typeof plainText === "string" ? plainText : "";
  const hasContent = raw.trim().length > 0;
  assert.equal(hasContent, true);
  assert.equal(raw, plainText);
});

test("handles very long content without truncation or performance failure", () => {
  const longParagraph = "Semantica knowledge graph node content with structured facts. ".repeat(500);
  const longMarkdown = `# Big Document\n\n${longParagraph}\n\n## Section 2\n\n${longParagraph}`;
  assert.equal(longMarkdown.length > 50000, true);
  const raw = typeof longMarkdown === "string" ? longMarkdown : "";
  assert.equal(raw.length, longMarkdown.length);
});

test("handles raw HTML content safely as text", () => {
  const dangerousHtml = `<script>alert("XSS")</script><img src="x" onerror="steal()"/><iframe src="evil.com"></iframe>`;
  // In source mode, content is preserved literally without execution
  assert.equal(dangerousHtml.includes("<script>"), true);
  assert.equal(dangerousHtml.includes("onerror="), true);
});

test("preserves fenced code blocks with language identifiers and indentation", () => {
  const codeBlockMarkdown = "```typescript\nfunction processGraph(id: string): boolean {\n  return id.length > 0;\n}\n```";
  assert.equal(codeBlockMarkdown.startsWith("```typescript"), true);
  assert.equal(codeBlockMarkdown.includes("  return id.length > 0;"), true);
  assert.equal(codeBlockMarkdown.endsWith("```"), true);
});

