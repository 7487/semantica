import { useState, type CSSProperties } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy, Code2, Eye, ExternalLink, Image as ImageIcon } from "lucide-react";
import { GRAPH_THEME } from "./graphTheme";

export interface MarkdownContentViewerProps {
  content?: string | null;
  className?: string;
  defaultMode?: "preview" | "source";
}

export function isSafeUrl(url?: string): boolean {
  if (!url) return false;
  const trimmed = url.trim();
  if (trimmed.startsWith("#") || trimmed.startsWith("/")) return true;
  try {
    const parsed = new URL(trimmed, "http://localhost");
    return ["http:", "https:", "mailto:"].includes(parsed.protocol);
  } catch {
    return false;
  }
}

export function MarkdownContentViewer({
  content,
  className,
  defaultMode = "preview",
}: MarkdownContentViewerProps) {
  const [activeMode, setActiveMode] = useState<"preview" | "source">(defaultMode);
  const [copied, setCopied] = useState(false);

  const rawContent = typeof content === "string" ? content : "";
  const hasContent = rawContent.trim().length > 0;

  const handleCopy = async () => {
    if (!hasContent) return;
    try {
      await navigator.clipboard.writeText(rawContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard write unavailable
    }
  };

  return (
    <div className={className} style={viewerContainerStyle}>
      <div style={viewerHeaderStyle}>
        <div style={{ display: "flex", gap: 4 }} role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeMode === "preview"}
            onClick={() => setActiveMode("preview")}
            style={{ ...tabBtnStyle, ...(activeMode === "preview" ? activeTabBtnStyle : {}) }}
          >
            <Eye size={12} style={{ marginRight: 5 }} />
            Preview
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeMode === "source"}
            onClick={() => setActiveMode("source")}
            style={{ ...tabBtnStyle, ...(activeMode === "source" ? activeTabBtnStyle : {}) }}
          >
            <Code2 size={12} style={{ marginRight: 5 }} />
            Source
          </button>
        </div>

        {hasContent && (
          <button type="button" onClick={() => void handleCopy()} style={copyBtnStyle} title="Copy raw content">
            {copied ? (
              <>
                <Check size={12} color="#3fb950" style={{ marginRight: 4 }} />
                <span style={{ color: "#3fb950", fontSize: 11 }}>Copied</span>
              </>
            ) : (
              <>
                <Copy size={12} style={{ marginRight: 4 }} />
                <span style={{ fontSize: 11 }}>Copy</span>
              </>
            )}
          </button>
        )}
      </div>

      <div style={viewerBodyStyle}>
        {!hasContent ? (
          <div style={emptyTextStyle}>No content available for this node.</div>
        ) : activeMode === "source" ? (
          <pre style={sourcePreStyle}>
            <code style={sourceCodeStyle}>{rawContent}</code>
          </pre>
        ) : (
          <div style={previewStyle}>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ href, children, ...props }) => {
                  if (!isSafeUrl(href)) {
                    return <span style={{ color: GRAPH_THEME.ui.text.muted, textDecoration: "line-through" }}>{children}</span>;
                  }
                  return (
                    <a href={href} target="_blank" rel="noopener noreferrer" style={linkStyle} {...props}>
                      {children}
                      <ExternalLink size={10} style={{ marginLeft: 3, verticalAlign: "middle", display: "inline" }} />
                    </a>
                  );
                },
                img: ({ src, alt }) => (
                  <span style={imageBadgeStyle} title={src || "Image"}>
                    <ImageIcon size={12} style={{ marginRight: 5 }} />
                    <span>Image: {alt || src || "unlabeled"}</span>
                  </span>
                ),
                h1: ({ children }) => <h1 style={h1Style}>{children}</h1>,
                h2: ({ children }) => <h2 style={h2Style}>{children}</h2>,
                h3: ({ children }) => <h3 style={h3Style}>{children}</h3>,
                h4: ({ children }) => <h4 style={h4Style}>{children}</h4>,
                p: ({ children }) => <p style={{ margin: "0 0 8px 0" }}>{children}</p>,
                ul: ({ children }) => <ul style={{ margin: "0 0 8px 0", paddingLeft: 18 }}>{children}</ul>,
                ol: ({ children }) => <ol style={{ margin: "0 0 8px 0", paddingLeft: 18 }}>{children}</ol>,
                li: ({ children }) => <li style={{ marginBottom: 3 }}>{children}</li>,
                blockquote: ({ children }) => <blockquote style={blockquoteStyle}>{children}</blockquote>,
                hr: () => <hr style={{ border: "none", borderTop: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`, margin: "10px 0" }} />,
                table: ({ children }) => (
                  <div style={{ width: "100%", overflowX: "auto", margin: "8px 0", borderRadius: 6, border: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}` }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>{children}</table>
                  </div>
                ),
                thead: ({ children }) => <thead style={{ background: "rgba(255, 255, 255, 0.04)" }}>{children}</thead>,
                tbody: ({ children }) => <tbody>{children}</tbody>,
                tr: ({ children }) => <tr style={{ borderBottom: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}` }}>{children}</tr>,
                th: ({ children }) => <th style={{ padding: "6px 8px", textAlign: "left", fontWeight: 700, color: GRAPH_THEME.ui.text.strong, borderRight: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}` }}>{children}</th>,
                td: ({ children }) => <td style={{ padding: "6px 8px", color: GRAPH_THEME.ui.text.body, borderRight: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}` }}>{children}</td>,
                pre: ({ children }) => <pre style={preBlockStyle}>{children}</pre>,
                code: ({ className: codeClass, children, ...props }) => {
                  const isInline = !codeClass && typeof children === "string" && !children.includes("\n");
                  return (
                    <code style={isInline ? inlineCodeStyle : blockCodeStyle} {...props}>
                      {children}
                    </code>
                  );
                },
              }}
            >
              {rawContent}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Styles ──────────────────────────────────────────────────────── */

const viewerContainerStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  background: "rgba(255, 255, 255, 0.025)",
  border: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`,
  borderRadius: 12,
  overflow: "hidden",
};

const viewerHeaderStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "6px 10px",
  background: "rgba(0, 0, 0, 0.2)",
  borderBottom: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`,
};

const tabBtnStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  padding: "4px 9px",
  borderRadius: 6,
  border: "1px solid transparent",
  background: "transparent",
  color: GRAPH_THEME.ui.text.muted,
  fontSize: 12,
  fontWeight: 600,
  cursor: "pointer",
  transition: "all 150ms ease",
};

const activeTabBtnStyle: CSSProperties = {
  background: GRAPH_THEME.ui.timeline.playheadSoft,
  border: `1px solid ${GRAPH_THEME.ui.control.activeBorder}`,
  color: GRAPH_THEME.ui.timeline.playhead,
};

const copyBtnStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  padding: "3px 8px",
  borderRadius: 6,
  border: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`,
  background: "rgba(255, 255, 255, 0.04)",
  color: GRAPH_THEME.ui.text.subtle,
  fontSize: 11,
  cursor: "pointer",
};

const viewerBodyStyle: CSSProperties = {
  padding: 12,
  maxHeight: 380,
  overflowY: "auto",
};

const emptyTextStyle: CSSProperties = {
  color: GRAPH_THEME.ui.text.muted,
  fontSize: 12,
  lineHeight: 1.5,
  fontStyle: "italic",
};

const sourcePreStyle: CSSProperties = {
  margin: 0,
  padding: 10,
  borderRadius: 8,
  background: "rgba(0, 0, 0, 0.3)",
  border: "1px solid rgba(255, 255, 255, 0.05)",
  overflowX: "auto",
};

const sourceCodeStyle: CSSProperties = {
  fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
  fontSize: 12,
  lineHeight: 1.6,
  color: GRAPH_THEME.ui.text.strong,
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
  userSelect: "text",
};

const previewStyle: CSSProperties = {
  color: GRAPH_THEME.ui.text.body,
  fontSize: 13,
  lineHeight: 1.6,
  wordBreak: "break-word",
};

const h1Style: CSSProperties = {
  fontSize: 16,
  fontWeight: 700,
  color: GRAPH_THEME.ui.text.strong,
  marginTop: 8,
  marginBottom: 6,
  paddingBottom: 3,
  borderBottom: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`,
};

const h2Style: CSSProperties = {
  fontSize: 14,
  fontWeight: 700,
  color: GRAPH_THEME.ui.text.strong,
  marginTop: 8,
  marginBottom: 4,
};

const h3Style: CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  color: GRAPH_THEME.ui.text.strong,
  marginTop: 6,
  marginBottom: 4,
};

const h4Style: CSSProperties = {
  fontSize: 12,
  fontWeight: 600,
  color: GRAPH_THEME.ui.text.strong,
  marginTop: 4,
  marginBottom: 2,
};

const blockquoteStyle: CSSProperties = {
  margin: "8px 0",
  padding: "6px 12px",
  borderLeft: `3px solid ${GRAPH_THEME.ui.timeline.playhead}`,
  background: "rgba(98, 226, 205, 0.05)",
  borderRadius: "0 6px 6px 0",
  color: GRAPH_THEME.ui.text.body,
  fontStyle: "italic",
};

const linkStyle: CSSProperties = {
  color: "#79c0ff",
  textDecoration: "underline",
  textUnderlineOffset: "3px",
  wordBreak: "break-all",
};

const imageBadgeStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  padding: "3px 7px",
  background: "rgba(255, 255, 255, 0.04)",
  border: `1px solid ${GRAPH_THEME.ui.surface.panelBorder}`,
  borderRadius: 6,
  color: GRAPH_THEME.ui.text.muted,
  fontSize: 11,
  margin: "3px 0",
};

const inlineCodeStyle: CSSProperties = {
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: 12,
  padding: "2px 5px",
  borderRadius: 4,
  background: "rgba(255, 255, 255, 0.07)",
  color: "#e6edf3",
  border: "1px solid rgba(255, 255, 255, 0.08)",
};

const preBlockStyle: CSSProperties = {
  margin: "8px 0",
  padding: 10,
  borderRadius: 8,
  background: "rgba(0, 0, 0, 0.35)",
  border: "1px solid rgba(255, 255, 255, 0.08)",
  overflowX: "auto",
};

const blockCodeStyle: CSSProperties = {
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: 12,
  lineHeight: 1.5,
  color: "#e6edf3",
};
