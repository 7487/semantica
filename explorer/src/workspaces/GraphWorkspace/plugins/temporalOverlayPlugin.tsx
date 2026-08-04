import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Loader2 } from "lucide-react";
import type Graph from "graphology";

import { graph, type NodeAttributes } from "../../../store/graphStore";
import { GRAPH_THEME } from "../graphTheme";
import { fetchTemporalDiff, type TemporalDiffResult } from "./temporalDiffState";
import type { GraphPlugin, GraphPluginContext } from "./types";

const TEMPORAL_PANEL_ID = "temporal-panel";

function formatTemporalLabel(value: Date | null) {
  if (!value) {
    return "No time selected";
  }
  return `${value.getFullYear()}/${String(value.getMonth() + 1).padStart(2, "0")}`;
}

function isValidDateInput(value: string): boolean {
  return value.trim().length > 0 && !Number.isNaN(new Date(value).getTime());
}

type DiffRequestState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "empty"; result: TemporalDiffResult }
  | { status: "success"; result: TemporalDiffResult };

// Diff highlight colors reuse existing theme tokens rather than introducing new
// hex values: semantic[2] is the codebase's green, dangerText is the one named
// danger/red token already used elsewhere in this workspace (GraphWorkspace.tsx).
const DIFF_ADDED_COLOR = GRAPH_THEME.palette.semantic[2];
const DIFF_REMOVED_COLOR = GRAPH_THEME.ui.control.dangerText;

// Highlighting uses baseColor (the node's fill color), not ringColor/haloColor: those two
// are only read by resolveNodeElementStyle/GraphCanvas's decoration pass for nodes in
// hovered/selected/path visual state (see resolveNodeRingSize, showHalo in graphSceneState.ts
// and the nodesToDecorate set in GraphCanvas.tsx) and are silently discarded by the sigma
// nodeReducer for a node sitting in its default (untouched) state — which is exactly the
// state every diffed node is in here. baseColor is read unconditionally by resolveNodeColor's
// default branch regardless of interaction state or zoom tier, so it is the one attribute
// confirmed to actually render the diff highlight.
//
// Writes go to BOTH the store graph and context.displayGraph:
// - context.displayGraph is the live Graph instance currently bound to Sigma (updated by
//   GraphCanvas.tsx via sigma.setGraph() / runtimeRef.current.displayGraph = displayGraph
//   whenever the display graph is rebuilt). The nodeReducer reads attributes from this
//   instance, so writing here makes the highlight visible in the currently-rendered frame.
// - graph (store singleton) carries the value into the *next* display graph rebuild:
//   aggregateDisplayGraph copies node attributes shallowly from the store graph, so a
//   mutation that only touches context.displayGraph would be lost on the next rebuild.
// Using a type assertion to Graph<NodeAttributes, EdgeAttributes> is consistent with how
// the rest of GraphCanvas/graphSceneState cast the same union when they need to call
// mutation methods; TypeScript cannot resolve setNodeAttribute across the union directly.

function toMutable(g: GraphPluginContext["displayGraph"]) {
  return g as Graph<NodeAttributes>;
}

function writeBaseColor(
  context: GraphPluginContext,
  nodeId: string,
  color: string | undefined,
): void {
  // Write to the store graph first (survives display graph rebuilds).
  if (graph.hasNode(nodeId)) {
    graph.setNodeAttribute(nodeId, "baseColor", color);
  }
  // Write to the current display graph instance Sigma is rendering.
  const dg = toMutable(context.displayGraph);
  if (dg !== graph && dg.hasNode(nodeId)) {
    dg.setNodeAttribute(nodeId, "baseColor", color);
  }
}

function clearDiffHighlight(context: GraphPluginContext, previousColors: Map<string, string | undefined>) {
  previousColors.forEach((color, nodeId) => {
    writeBaseColor(context, nodeId, color);
  });
  context.scene?.requestRender();
}

function applyDiffHighlight(context: GraphPluginContext, result: TemporalDiffResult): Map<string, string | undefined> {
  const previousColors = new Map<string, string | undefined>();
  const paint = (nodeId: string, color: string) => {
    // Capture from the store graph — this is the authoritative source for the node's
    // original baseColor, since aggregateDisplayGraph copies from there.
    if (graph.hasNode(nodeId)) {
      previousColors.set(nodeId, graph.getNodeAttribute(nodeId, "baseColor"));
      writeBaseColor(context, nodeId, color);
    }
  };
  result.added_nodes.forEach((nodeId) => paint(nodeId, DIFF_ADDED_COLOR));
  result.removed_nodes.forEach((nodeId) => paint(nodeId, DIFF_REMOVED_COLOR));
  context.scene?.requestRender();
  return previousColors;
}

function DiffSection({ context }: { context: GraphPluginContext }) {
  const [fromTime, setFromTime] = useState("");
  const [toTime, setToTime] = useState("");
  const [validationMessage, setValidationMessage] = useState<string | null>(null);
  const [requestState, setRequestState] = useState<DiffRequestState>({ status: "idle" });
  const abortRef = useRef<AbortController | null>(null);
  // Maps currently-highlighted node ID -> its baseColor before highlighting, so clearing
  // restores the exact prior value instead of an approximation.
  const previousColorsRef = useRef<Map<string, string | undefined>>(new Map());

  // Cancel any in-flight request and clear stale highlights when the panel unmounts
  // (panel closed) — matches the cancellation pattern used by the snapshot fetch in
  // GraphRuntimeStage.tsx (cancel-on-cleanup) plus AbortController per DecisionWorkspace.tsx.
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      clearDiffHighlight(context, previousColorsRef.current);
      previousColorsRef.current = new Map();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCompare = () => {
    if (!fromTime.trim() || !toTime.trim()) {
      setValidationMessage("Both a from and to time are required.");
      return;
    }
    if (!isValidDateInput(fromTime) || !isValidDateInput(toTime)) {
      setValidationMessage("Enter valid ISO datetimes, e.g. 2024-01-01T00:00:00.");
      return;
    }
    if (new Date(fromTime).getTime() >= new Date(toTime).getTime()) {
      setValidationMessage("From time must be before to time.");
      return;
    }
    setValidationMessage(null);

    // Cancel any request already in flight before starting a new one.
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    clearDiffHighlight(context, previousColorsRef.current);
    previousColorsRef.current = new Map();
    setRequestState({ status: "loading" });

    fetchTemporalDiff(fromTime, toTime, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) {
          return;
        }
        if (!result.added_nodes.length && !result.removed_nodes.length) {
          setRequestState({ status: "empty", result });
          return;
        }
        previousColorsRef.current = applyDiffHighlight(context, result);
        setRequestState({ status: "success", result });
      })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name === "AbortError") {
          return;
        }
        setRequestState({
          status: "error",
          message: error instanceof Error ? error.message : "Temporal diff request failed.",
        });
      });
  };

  const isLoading = requestState.status === "loading";

  return (
    <div style={diffSectionStyle}>
      <div style={panelEyebrowStyle}>Compare two points in time</div>
      <div style={diffInputRowStyle}>
        <input
          value={fromTime}
          onChange={(event) => setFromTime(event.target.value)}
          placeholder="From, e.g. 2024-01-01T00:00:00"
          style={diffInputStyle}
        />
        <input
          value={toTime}
          onChange={(event) => setToTime(event.target.value)}
          placeholder="To, e.g. 2025-06-15T00:00:00"
          style={diffInputStyle}
        />
      </div>
      <button
        type="button"
        onClick={handleCompare}
        disabled={isLoading}
        style={{ ...diffActionButtonStyle, opacity: isLoading ? 0.7 : 1 }}
      >
        {isLoading ? <Loader2 size={13} className="animate-spin" style={{ marginRight: 6 }} /> : null}
        {isLoading ? "Comparing…" : "Compare"}
      </button>

      {validationMessage ? <div style={diffValidationStyle}>{validationMessage}</div> : null}

      {requestState.status === "error" ? (
        <div style={diffErrorStyle}>{requestState.message}</div>
      ) : null}

      {requestState.status === "empty" ? (
        <div style={emptyTextStyle}>No changes between these two points.</div>
      ) : null}

      {requestState.status === "success" ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={detailRowStyle}>
            <span style={detailLabelStyle}>Added</span>
            <span style={{ ...detailValueStyle, color: DIFF_ADDED_COLOR }}>
              {requestState.result.added_nodes.length.toLocaleString()}
            </span>
          </div>
          <div style={detailRowStyle}>
            <span style={detailLabelStyle}>Removed</span>
            <span style={{ ...detailValueStyle, color: DIFF_REMOVED_COLOR }}>
              {requestState.result.removed_nodes.length.toLocaleString()}
            </span>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export const temporalOverlayPlugin: GraphPlugin = {
  id: "temporal-overlay",
  mount: () => {},
  unmount: () => {},
  onStateChange: () => {},
  toolbarItems: (context) => [
    {
      id: "temporal-toggle",
      label: "Temporal",
      title: "Toggle temporal context panel",
      active: context.isPanelOpen(TEMPORAL_PANEL_ID),
      order: 40,
      onClick: () => context.dispatchAction({ type: "togglePanel", panelId: TEMPORAL_PANEL_ID }),
    },
  ],
  renderOverlay: (context) => {
    const temporal = context.getTemporalState();
    if (!temporal?.currentTime) {
      return null;
    }

    const label = formatTemporalLabel(temporal.currentTime);
    return {
      id: "temporal-overlay-chip",
      layer: 1,
      order: 10,
      element: (
        <div
          style={{
            position: "absolute",
            left: 140,
            bottom: 26,
            display: "inline-flex",
            alignItems: "center",
            gap: 10,
            padding: "8px 12px",
            borderRadius: 999,
            border: "1px solid rgba(127, 208, 255, 0.18)",
            background: "linear-gradient(135deg, rgba(6, 15, 27, 0.88), rgba(11, 22, 39, 0.76))",
            boxShadow: "0 12px 30px rgba(0, 0, 0, 0.28)",
            color: "#dce9f8",
            fontSize: 11,
            letterSpacing: "0.05em",
            textTransform: "uppercase",
            pointerEvents: "none",
          }}
        >
          <span style={{ color: "#7fc6ff", fontWeight: 700 }}>Temporal</span>
          <span>{label}</span>
          {typeof temporal.activeNodeCount === "number" ? (
            <span style={{ color: "#8ea4be" }}>{temporal.activeNodeCount.toLocaleString()} active</span>
          ) : null}
        </div>
      ),
    };
  },
  renderPanel: (context) => {
    if (!context.isPanelOpen(TEMPORAL_PANEL_ID)) {
      return null;
    }

    const temporal = context.getTemporalState();
    return {
      id: TEMPORAL_PANEL_ID,
      title: "Temporal Context",
      placement: "bottom",
      order: 30,
      defaultOpen: false,
      preferredWidth: 320,
      preferredHeight: 380,
      content: (
        <div style={panelBodyStyle}>
          <div style={panelEyebrowStyle}>Current scrubber state</div>
          <div style={detailRowStyle}>
            <span style={detailLabelStyle}>Current</span>
            <span style={detailValueStyle}>{formatTemporalLabel(temporal?.currentTime ?? null)}</span>
          </div>
          <div style={detailRowStyle}>
            <span style={detailLabelStyle}>Bounds</span>
            <span style={detailValueStyle}>
              {(temporal?.minDate ?? "1970")} → {(temporal?.maxDate ?? "2030")}
            </span>
          </div>
          <div style={detailRowStyle}>
            <span style={detailLabelStyle}>Active nodes</span>
            <span style={detailValueStyle}>
              {typeof temporal?.activeNodeCount === "number" ? temporal.activeNodeCount.toLocaleString() : "All"}
            </span>
          </div>
          <DiffSection context={context} />
        </div>
      ),
    };
  },
};

const panelBodyStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 10,
};

const panelEyebrowStyle: CSSProperties = {
  color: "#8ea4be",
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};

const detailRowStyle: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  gap: 16,
  padding: "8px 10px",
  borderRadius: 12,
  border: "1px solid rgba(255,255,255,0.06)",
  background: "rgba(255,255,255,0.025)",
};

const detailLabelStyle: CSSProperties = {
  color: "#8ea4be",
  fontSize: 12,
};

const detailValueStyle: CSSProperties = {
  color: "#f3f7fd",
  fontSize: 12,
  fontWeight: 600,
};

const diffSectionStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 8,
  marginTop: 4,
  paddingTop: 10,
  borderTop: "1px solid rgba(255,255,255,0.06)",
};

const diffInputRowStyle: CSSProperties = {
  display: "flex",
  gap: 8,
};

const diffInputStyle: CSSProperties = {
  flex: 1,
  minWidth: 0,
  background: "rgba(5, 7, 10, 0.52)",
  border: "1px solid rgba(211, 205, 190, 0.13)",
  color: "#f3f7fd",
  borderRadius: 12,
  padding: "9px 11px",
  fontSize: 12,
  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.035)",
};

const diffActionButtonStyle: CSSProperties = {
  background: GRAPH_THEME.ui.control.primaryBg,
  color: GRAPH_THEME.ui.control.primaryText,
  border: `1px solid ${GRAPH_THEME.ui.control.primaryBorder}`,
  borderRadius: 12,
  padding: "9px 12px",
  cursor: "pointer",
  fontWeight: 700,
  fontSize: 12,
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.07), 0 10px 24px rgba(0,0,0,0.18)",
};

const diffValidationStyle: CSSProperties = {
  color: GRAPH_THEME.ui.control.dangerText,
  fontSize: 12,
  lineHeight: 1.5,
};

const diffErrorStyle: CSSProperties = {
  color: GRAPH_THEME.ui.control.dangerText,
  fontSize: 12,
  lineHeight: 1.5,
};

const emptyTextStyle: CSSProperties = {
  color: "#8ea4be",
  fontSize: 12,
  lineHeight: 1.5,
};
