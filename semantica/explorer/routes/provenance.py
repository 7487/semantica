"""
Provenance routes for lineage visualization and exportable reports.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import networkx as nx
from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse, Response

from ..dependencies import get_session
from ..schemas import ProvenanceEdge, ProvenanceNode, ProvenanceResponse
from ..session import GraphSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/provenance", tags=["Power User Tools"])

_AGENT_TYPES = {"person", "organization", "system", "agent"}
_ACTIVITY_TYPES = {"action", "event", "process", "activity", "decision", "publication"}


def _classify_prov(node_type: str) -> tuple[str, str]:
    lowered = node_type.lower()
    if lowered in _AGENT_TYPES:
        return "Agent", "group_agent"
    if lowered in _ACTIVITY_TYPES:
        return "Activity", "group_activity"
    return "Entity", "group_entity"


def _transform_audit_lineage(lineage: Dict[str, Any], node_id: str) -> Dict[str, Any]:
    # Mapping decision (W3C PROV-O to frontend swim-lanes):
    # Every ProvenanceEntry maps to a node classified by _classify_prov(entry["entity_type"]),
    # placing documents/chunks/entities in 'group_entity' (prov_type='Entity'), persons/systems
    # in 'group_agent', and actions/processes in 'group_activity'.
    # For derivation relationships (parent_entity_id and used_entities), we connect
    # parent -> child directly with edge label set to activity_id (or 'wasDerivedFrom'),
    # keeping the lineage graph scannable without cluttering it with intermediate activity
    # nodes when activity_id is an operational label.
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    seen_nodes = set()
    seen_edges = set()

    chain = lineage.get("lineage_chain") or lineage.get("entries") or []
    for entry in chain:
        if not isinstance(entry, dict):
            continue
        eid = str(entry.get("entity_id") or "")
        if not eid or eid in seen_nodes:
            continue
        seen_nodes.add(eid)
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        label = str(metadata.get("title") or metadata.get("label") or eid)
        prov_type, parent_id = _classify_prov(str(entry.get("entity_type", "entity")))
        nodes.append({
            "id": eid,
            "label": label,
            "prov_type": prov_type,
            "parent_id": parent_id,
        })

    for entry in chain:
        if not isinstance(entry, dict):
            continue
        eid = str(entry.get("entity_id") or "")
        if not eid:
            continue
        parents = []
        if entry.get("parent_entity_id"):
            parents.append(str(entry.get("parent_entity_id")))
        used = entry.get("used_entities")
        if isinstance(used, list):
            for u in used:
                if u and str(u) not in parents:
                    parents.append(str(u))

        activity = str(entry.get("activity_id") or "wasDerivedFrom")
        for src in parents:
            edge_key = (src, eid)
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)

            # NOTE: ProvenanceManager.get_lineage() currently only traces upstream
            # ancestor chains via parent_entity_id and used_entities. It does not perform
            # reverse lookups for downstream descendants. Consequently, 'direction = "downstream"'
            # is unreachable in practice for this audit path until reverse lookup is supported
            # by ProvenanceManager. All ancestor derivation edges are upstream lineage.
            if src == node_id:
                direction = "downstream"
            else:
                direction = "upstream"

            edges.append({
                "id": f"{src}-{eid}",
                "source": src,
                "target": eid,
                "label": activity,
                "direction": direction,
            })

    for edge in edges:
        for endpoint in (edge["source"], edge["target"]):
            if endpoint not in seen_nodes:
                seen_nodes.add(endpoint)
                prov_type, parent_id = _classify_prov("entity")
                nodes.append({
                    "id": endpoint,
                    "label": endpoint,
                    "prov_type": prov_type,
                    "parent_id": parent_id,
                })

    return {"nodes": nodes, "edges": edges, "source": "audit"}


def _build_provenance(session: GraphSession, node_id: Optional[str] = None) -> dict:
    """Build provenance lineage for a node, attempting the audit-grade store first.

    NOTE: The audit path (source='audit') shows verified upstream lineage only.
    For descendant/downstream relationships, the naive graph-traversal fallback
    remains the only source until ProvenanceManager gains a reverse lookup.
    """
    if not node_id:
        return {"nodes": [], "edges": [], "source": "graph_traversal"}

    try:
        manager = getattr(session, "provenance_manager", None)
        if manager is not None:
            lineage = manager.get_lineage(node_id)
            if lineage and lineage.get("entity_count", 0) > 0:
                return _transform_audit_lineage(lineage, node_id)
    except Exception as exc:
        logger.warning(
            f"ProvenanceManager get_lineage failed for {node_id}, falling back to graph traversal: {exc}"
        )

    if node_id not in session.graph.nodes:
        return {"nodes": [], "edges": [], "source": "graph_traversal"}

    graph = nx.DiGraph()
    graph.add_node(node_id)

    hop_nodes = {node_id}
    for edge in session.graph.edges:
        if edge.source_id == node_id or edge.target_id == node_id:
            graph.add_edge(edge.source_id, edge.target_id, label=edge.edge_type)
            hop_nodes.add(edge.source_id)
            hop_nodes.add(edge.target_id)

    for edge in session.graph.edges:
        if edge.source_id in hop_nodes or edge.target_id in hop_nodes:
            graph.add_edge(edge.source_id, edge.target_id, label=edge.edge_type)

    subgraph = nx.ego_graph(graph, node_id, radius=2, undirected=True)
    provenance_nodes: List[Dict[str, Any]] = []
    for graph_node_id in subgraph.nodes():
        node = session.graph.nodes.get(graph_node_id)
        if node is None:
            continue
        prov_type, parent_id = _classify_prov(node.node_type)
        provenance_nodes.append(
            {
                "id": graph_node_id,
                "label": node.content or graph_node_id,
                "prov_type": prov_type,
                "parent_id": parent_id,
            }
        )

    provenance_edges: List[Dict[str, Any]] = []
    for source, target, data in subgraph.edges(data=True):
        if target == node_id:
            direction = "upstream"
        elif source == node_id:
            direction = "downstream"
        else:
            direction = "lateral"
        provenance_edges.append(
            {
                "id": f"{source}-{target}",
                "source": source,
                "target": target,
                "label": data.get("label", "related_to"),
                "direction": direction,
            }
        )

    return {"nodes": provenance_nodes, "edges": provenance_edges, "source": "graph_traversal"}


def _build_report(session: GraphSession, node_id: str) -> Dict[str, Any]:
    node = session.get_node(node_id)
    provenance = _build_provenance(session, node_id)
    return {
        "node_id": node_id,
        "label": node.get("content", node_id) if node else node_id,
        "type": node.get("type", "entity") if node else "entity",
        "properties": node.get("metadata", node.get("properties", {})) if node else {},
        "lineage": provenance,
        "source": provenance.get("source", "graph_traversal"),
    }


def _render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        f"# Provenance Report: {report['label']}",
        "",
        f"- Node ID: `{report['node_id']}`",
        f"- Type: `{report['type']}`",
        "",
        "## Properties",
    ]
    properties = report.get("properties", {})
    if properties:
        for key, value in properties.items():
            lines.append(f"- **{key}**: {value}")
    else:
        lines.append("- No properties recorded")

    lines.extend(["", "## Lineage Nodes"])
    for node in report.get("lineage", {}).get("nodes", []):
        lines.append(f"- `{node['id']}` ({node['prov_type']}): {node['label']}")

    edges = report.get("lineage", {}).get("edges", [])
    grouped_edges: Dict[str, List] = {"upstream": [], "downstream": [], "lateral": []}
    for edge in edges:
        direction = edge.get("direction", "lateral")
        if direction not in grouped_edges:
            direction = "lateral"
        grouped_edges[direction].append(edge)

    if grouped_edges["upstream"]:
        lines.extend(["", "## Upstream"])
        for edge in grouped_edges["upstream"]:
            lines.append(f"- `{edge['source']}` -[{edge['label']}]-> `{edge['target']}`")

    if grouped_edges["downstream"]:
        lines.extend(["", "## Downstream"])
        for edge in grouped_edges["downstream"]:
            lines.append(f"- `{edge['source']}` -[{edge['label']}]-> `{edge['target']}`")

    if grouped_edges["lateral"]:
        lines.extend(["", "## Lateral"])
        for edge in grouped_edges["lateral"]:
            lines.append(f"- `{edge['source']}` -[{edge['label']}]-> `{edge['target']}`")

    return "\n".join(lines)


@router.get("", response_model=ProvenanceResponse)
@router.get("/", response_model=ProvenanceResponse, include_in_schema=False)
async def get_provenance_lineage(
    node_id: Optional[str] = None,
    session: GraphSession = Depends(get_session),
):
    data = await asyncio.to_thread(_build_provenance, session, node_id)
    return ProvenanceResponse(
        nodes=[ProvenanceNode(**node) for node in data["nodes"]],
        edges=[ProvenanceEdge(**edge) for edge in data["edges"]],
        source=data.get("source", "graph_traversal"),
    )


@router.get("/report")
async def export_provenance_report(
    node_id: str = Query(..., description="Node ID to export"),
    format: str = Query("json", description="json or markdown"),
    session: GraphSession = Depends(get_session),
):
    report = await asyncio.to_thread(_build_report, session, node_id)
    if format.lower() in {"md", "markdown"}:
        content = _render_markdown(report)
        return PlainTextResponse(
            content,
            headers={"Content-Disposition": f'attachment; filename="{node_id}_provenance.md"'},
        )

    content = json.dumps(report, indent=2, default=str)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{node_id}_provenance.json"'},
    )
