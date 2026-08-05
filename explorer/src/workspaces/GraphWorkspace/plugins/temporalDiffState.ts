// Fetch wrapper for GET /api/temporal/diff (see semantica/explorer/routes/temporal.py).
// added_nodes are node IDs active at to_time but not at from_time; removed_nodes are the
// inverse. Both are plain node-ID lists (no edge-level diffing), matching the snapshot
// route's active_node_ids shape used elsewhere in this workspace.
export interface TemporalDiffResult {
  from_time: string;
  to_time: string;
  added_nodes: string[];
  removed_nodes: string[];
}

export async function fetchTemporalDiff(
  fromTime: string,
  toTime: string,
  signal?: AbortSignal,
): Promise<TemporalDiffResult> {
  const params = new URLSearchParams({ from_time: fromTime, to_time: toTime });
  const response = await fetch(`/api/temporal/diff?${params}`, { signal });
  if (!response.ok) {
    throw new Error(`Temporal diff request failed with status ${response.status}`);
  }
  return response.json();
}
