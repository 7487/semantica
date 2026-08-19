import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToString } from "react-dom/server";

(globalThis as any).React = React;

import { isSafeUrl, MarkdownContentViewer } from "../src/workspaces/GraphWorkspace/MarkdownContentViewer.tsx";

test("isSafeUrl permits safe http, https, and mailto URLs and relative paths", () => {
  assert.equal(isSafeUrl("https://example.com"), true);
  assert.equal(isSafeUrl("http://localhost:8000"), true);
  assert.equal(isSafeUrl("mailto:user@example.com"), true);
  assert.equal(isSafeUrl("#section-1"), true);
  assert.equal(isSafeUrl("/relative/path"), true);
});

test("isSafeUrl rejects protocol-relative URLs and dangerous schemes", () => {
  // Protocol-relative URLs (must be blocked)
  assert.equal(isSafeUrl("//evil.com"), false);
  assert.equal(isSafeUrl("//localhost:8000"), false);
  assert.equal(isSafeUrl("//"), false);

  // Dangerous schemes
  assert.equal(isSafeUrl("javascript:alert('xss')"), false);
  assert.equal(isSafeUrl("JAVASCRIPT:alert(1)"), false);
  assert.equal(isSafeUrl("data:text/html;base64,PHNjcmlwdD4="), false);
  assert.equal(isSafeUrl("vbscript:MsgBox(1)"), false);
  assert.equal(isSafeUrl(""), false);
  assert.equal(isSafeUrl(undefined), false);
});

test("renders Preview mode with formatted Markdown elements and tabs", () => {
  const markdown = `# Main Title\n\n**Bold Statement**\n\n* Item A\n* Item B`;
  const html = renderToString(React.createElement(MarkdownContentViewer, { content: markdown, defaultMode: "preview" }));

  // Tab buttons are present
  assert.equal(html.includes("Preview"), true);
  assert.equal(html.includes("Source"), true);
  assert.equal(html.includes("Copy"), true);

  // Formatted preview elements
  assert.equal(html.includes("Main Title"), true);
  assert.equal(html.includes("Bold Statement"), true);
  assert.equal(html.includes("<strong>Bold Statement</strong>"), true);
  assert.equal(html.includes("Item A"), true);
  assert.equal(html.includes("Item B"), true);
});

test("renders Source mode with exact unmodified text inside pre/code", () => {
  const markdown = `# Title 🚀\n\n  * Indented item\n\n\`\`\`python\ndef test():\n    return "α + β"\n\`\`\``;
  const html = renderToString(React.createElement(MarkdownContentViewer, { content: markdown, defaultMode: "source" }));

  assert.equal(html.includes("<pre"), true);
  assert.equal(html.includes("<code"), true);
  assert.equal(html.includes("# Title 🚀"), true);
  assert.equal(html.includes("  * Indented item"), true);
  assert.equal(html.includes('return &quot;α + β&quot;'), true);
});

test("renders raw HTML safely as escaped text without executing elements", () => {
  const dangerousHtml = `<script>alert("XSS")</script><iframe src="https://evil.com"></iframe>`;
  const html = renderToString(React.createElement(MarkdownContentViewer, { content: dangerousHtml, defaultMode: "preview" }));

  // Script and iframe tags must NOT be rendered as active DOM tags
  assert.equal(html.includes("<script>"), false);
  assert.equal(html.includes("<iframe"), false);
  // Content is escaped as text
  assert.equal(html.includes("&lt;script&gt;"), true);
});

test("renders safe links as <a> with target blank and unclickable span for unsafe links", () => {
  const content = `[Safe Link](https://getsemantica.ai)\n\n[Unsafe Scheme](javascript:alert(1))\n\n[Protocol Relative](//evil.com)`;
  const html = renderToString(React.createElement(MarkdownContentViewer, { content, defaultMode: "preview" }));

  // Safe link renders as <a> with security attributes
  assert.equal(html.includes('href="https://getsemantica.ai"'), true);
  assert.equal(html.includes('target="_blank"'), true);
  assert.equal(html.includes('rel="noopener noreferrer"'), true);

  // Unsafe links do NOT render as <a> tags
  assert.equal(html.includes('href="javascript:alert(1)"'), false);
  assert.equal(html.includes('href="//evil.com"'), false);
  assert.equal(html.includes("Unsafe Scheme"), true);
  assert.equal(html.includes("Protocol Relative"), true);
});

test("renders remote images as safe placeholder badges instead of <img> tags", () => {
  const content = `![System Diagram](https://example.com/diagram.png)`;
  const html = renderToString(React.createElement(MarkdownContentViewer, { content, defaultMode: "preview" }));

  // No <img> tag rendered
  assert.equal(html.includes("<img"), false);
  // Image placeholder badge rendered
  assert.equal(html.includes("Image:"), true);
  assert.equal(html.includes("System Diagram"), true);
});

test("renders clear empty-state message when content is empty or null", () => {
  const emptyHtml = renderToString(React.createElement(MarkdownContentViewer, { content: "" }));
  assert.equal(emptyHtml.includes("No content available for this node."), true);

  const nullHtml = renderToString(React.createElement(MarkdownContentViewer, { content: null }));
  assert.equal(nullHtml.includes("No content available for this node."), true);
});

test("renders plain text cleanly without requiring Markdown formatting", () => {
  const plainText = "Plain entity summary text without markdown formatting.";
  const html = renderToString(React.createElement(MarkdownContentViewer, { content: plainText, defaultMode: "preview" }));

  assert.equal(html.includes(plainText), true);
});

test("handles very large Markdown content without failure", () => {
  const largeContent = `# Large Knowledge Node\n\n` + "Structured observation paragraph. ".repeat(400);
  assert.equal(largeContent.length > 10000, true);

  const html = renderToString(React.createElement(MarkdownContentViewer, { content: largeContent, defaultMode: "preview" }));
  assert.equal(html.includes("Large Knowledge Node"), true);
});
