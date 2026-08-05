/**
 * Regression tests for Issue #830: plugin registry shouldLoad predicates.
 *
 * The original temporal-overlay shouldLoad was:
 *   ({ panelState, temporalState }) =>
 *     Boolean(panelState["temporal-panel"] || temporalState?.currentTime)
 *
 * This caused an infinite render loop because temporalState.currentTime is
 * non-null from startup (TimelinePanel fires onTimeChange on mount), so the
 * predicate returned true before the panel was ever opened, repeatedly
 * triggering the plugin-loading useEffect during every scrubber update and
 * cancelling in-flight load() calls before they could register the plugin.
 *
 * The fix: each predicate reads only panelState so plugin loading is
 * gated strictly on the user opening the corresponding panel.
 *
 * These tests import the PRODUCTION predicates from pluginRegistryPredicates.ts
 * via tsx so that a future regression in GraphWorkspace.tsx is detected here.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

// tsx is available as a Node loader — use createRequire to exercise the
// TypeScript module from this .mjs file.
const require = createRequire(import.meta.url);

// tsx must be registered before requiring .ts files.  The test:plugin-registry
// script calls this file via `node --import tsx --test`, so tsx is already
// active in the process when this module runs.
const {
  explorationEffectsShouldLoad,
  neighborhoodPanelShouldLoad,
  temporalOverlayShouldLoad,
} = require("../src/workspaces/GraphWorkspace/pluginRegistryPredicates.ts");

// ── temporal-overlay ─────────────────────────────────────────────────────────

test("temporal-overlay shouldLoad: false when panel is closed and no scrubber time", () => {
  assert.equal(
    temporalOverlayShouldLoad({ panelState: { "temporal-panel": false } }),
    false,
  );
});

test("temporal-overlay shouldLoad: false when panel is closed even if scrubber time is set", () => {
  // Before the fix this returned true — TimelinePanel sets currentTime on mount,
  // causing eager loads that continuously reset the cancelled flag and prevented
  // plugin registration.
  assert.equal(
    temporalOverlayShouldLoad({
      panelState: { "temporal-panel": false },
      temporalState: { currentTime: new Date() },
    }),
    false,
  );
});

test("temporal-overlay shouldLoad: true only when the panel is explicitly opened", () => {
  assert.equal(
    temporalOverlayShouldLoad({ panelState: { "temporal-panel": true } }),
    true,
  );
});

test("temporal-overlay shouldLoad: true when panel opened even without a scrubber time", () => {
  assert.equal(
    temporalOverlayShouldLoad({
      panelState: { "temporal-panel": true },
      temporalState: { currentTime: null },
    }),
    true,
  );
});

// ── other entries — confirm they also gate only on panelState ─────────────────

test("exploration-effects shouldLoad: gates only on effects-panel state", () => {
  assert.equal(explorationEffectsShouldLoad({ panelState: { "effects-panel": false } }), false);
  assert.equal(explorationEffectsShouldLoad({ panelState: { "effects-panel": true } }), true);
});

test("neighborhood-panel shouldLoad: gates only on neighborhood-panel state", () => {
  assert.equal(neighborhoodPanelShouldLoad({ panelState: { "neighborhood-panel": false } }), false);
  assert.equal(neighborhoodPanelShouldLoad({ panelState: { "neighborhood-panel": true } }), true);
});

test("all three shouldLoad conditions are consistent: none reference temporalState", () => {
  // A predicate that regressed to reading temporalState?.currentTime would
  // return true here even though every panel is closed — detecting the loop bug.
  const nonNullTemporalState = { currentTime: new Date(), activeNodeCount: 6 };

  assert.equal(
    temporalOverlayShouldLoad({ panelState: { "temporal-panel": false }, temporalState: nonNullTemporalState }),
    false,
    "temporal-overlay must not load when panel is closed, regardless of scrubber time",
  );
  assert.equal(
    explorationEffectsShouldLoad({ panelState: { "effects-panel": false }, temporalState: nonNullTemporalState }),
    false,
  );
  assert.equal(
    neighborhoodPanelShouldLoad({ panelState: { "neighborhood-panel": false }, temporalState: nonNullTemporalState }),
    false,
  );
});
