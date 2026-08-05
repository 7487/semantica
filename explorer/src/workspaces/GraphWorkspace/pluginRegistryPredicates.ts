/**
 * shouldLoad predicates for the GraphWorkspace lazy plugin registry.
 *
 * Extracted into a pure module so the predicates can be unit-tested without
 * importing the full GraphWorkspace React component (which depends on sigma,
 * React hooks, and browser globals). The corresponding registry entries in
 * GraphWorkspace.tsx must use these functions directly.
 *
 * These predicates gate WHEN each plugin's module is lazily imported.
 * None of them reference temporalState — temporal scrubber updates must not
 * retrigger plugin loading (see issue #830 for the render-loop that resulted
 * from the temporal-overlay entry originally reading temporalState?.currentTime).
 */

export type PluginShouldLoadContext = {
  panelState: Record<string, boolean>;
};

export function explorationEffectsShouldLoad({ panelState }: PluginShouldLoadContext): boolean {
  return Boolean(panelState["effects-panel"]);
}

export function neighborhoodPanelShouldLoad({ panelState }: PluginShouldLoadContext): boolean {
  return Boolean(panelState["neighborhood-panel"]);
}

export function temporalOverlayShouldLoad({ panelState }: PluginShouldLoadContext): boolean {
  return Boolean(panelState["temporal-panel"]);
}
