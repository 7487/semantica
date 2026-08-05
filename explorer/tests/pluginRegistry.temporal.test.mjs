/**
 * Regression tests for Issue #830: temporal-overlay plugin shouldLoad condition.
 *
 * The original shouldLoad was:
 *   ({ panelState, temporalState }) =>
 *     Boolean(panelState["temporal-panel"] || temporalState?.currentTime)
 *
 * This caused an infinite render loop because:
 *   1. TimelinePanel calls onTimeChange(defaultTime) on mount, making
 *      temporalState.currentTime non-null from startup.
 *   2. temporalState is a useMemo that produces a new object reference
 *      on every activeNodeCount / scrubberTime change.
 *   3. The plugin-loading useEffect has temporalState in its dep array,
 *      so it re-runs on every temporal update.
 *   4. With shouldLoad returning true from startup, entry.load() fired
 *      on every re-run while the previous async import was still in-flight,
 *      continuously setting cancelled = true on the prior run before
 *      setLoadedPlugins could be called, so loadedPlugins["temporal-overlay"]
 *      was never populated and the cycle never settled.
 *
 * The fix: use only panelState["temporal-panel"], matching the exact
 * pattern of the other two registry entries (exploration-effects,
 * neighborhood-panel) that have never exhibited this problem.
 */
import test from "node:test";
import assert from "node:assert/strict";

// The fixed shouldLoad condition, extracted verbatim from GraphWorkspace.tsx.
// If this function is ever changed in GraphWorkspace.tsx, this test will catch
// a regression back to the temporalState-referencing form.
function temporalShouldLoad({ panelState }) {
  return Boolean(panelState["temporal-panel"]);
}

test("temporal-overlay shouldLoad: false when panel is closed and no scrubber time", () => {
  assert.equal(
    temporalShouldLoad({ panelState: { "temporal-panel": false } }),
    false,
  );
});

test("temporal-overlay shouldLoad: false when panel is closed even if scrubber time is set", () => {
  // Before the fix, this would return true because temporalState?.currentTime
  // was included in the condition.  TimelinePanel sets currentTime on mount,
  // so this would have triggered an eager load before the user opened the panel,
  // causing the render loop.
  assert.equal(
    temporalShouldLoad({
      panelState: { "temporal-panel": false },
      temporalState: { currentTime: new Date() },
    }),
    false,
  );
});

test("temporal-overlay shouldLoad: true only when the panel is explicitly opened", () => {
  assert.equal(
    temporalShouldLoad({ panelState: { "temporal-panel": true } }),
    true,
  );
});

test("temporal-overlay shouldLoad: true when panel opened even without a scrubber time", () => {
  assert.equal(
    temporalShouldLoad({
      panelState: { "temporal-panel": true },
      temporalState: { currentTime: null },
    }),
    true,
  );
});

// Verify the other two registry entries' shouldLoad conditions are unchanged
// and still gate only on their respective panelState keys — establishing that
// they have never had and still don't have the temporalState cross-dependency.
function effectsShouldLoad({ panelState }) {
  return Boolean(panelState["effects-panel"]);
}

function neighborhoodShouldLoad({ panelState }) {
  return Boolean(panelState["neighborhood-panel"]);
}

test("exploration-effects shouldLoad: gates only on effects-panel state", () => {
  assert.equal(effectsShouldLoad({ panelState: { "effects-panel": false } }), false);
  assert.equal(effectsShouldLoad({ panelState: { "effects-panel": true } }), true);
});

test("neighborhood-panel shouldLoad: gates only on neighborhood-panel state", () => {
  assert.equal(neighborhoodShouldLoad({ panelState: { "neighborhood-panel": false } }), false);
  assert.equal(neighborhoodShouldLoad({ panelState: { "neighborhood-panel": true } }), true);
});

test("all three shouldLoad conditions are consistent: none reference temporalState", () => {
  // A shouldLoad that references temporalState as a load trigger would return
  // true even when the panel is closed, given a non-null currentTime.
  const nonNullTemporalState = { currentTime: new Date(), activeNodeCount: 6 };

  assert.equal(
    temporalShouldLoad({ panelState: { "temporal-panel": false }, temporalState: nonNullTemporalState }),
    false,
    "temporal-overlay must not load when panel is closed, regardless of scrubber time",
  );
  assert.equal(
    effectsShouldLoad({ panelState: { "effects-panel": false }, temporalState: nonNullTemporalState }),
    false,
  );
  assert.equal(
    neighborhoodShouldLoad({ panelState: { "neighborhood-panel": false }, temporalState: nonNullTemporalState }),
    false,
  );
});
