"""
SPARQL routes backed by an in-memory rdflib projection of the current graph.

Security contract
-----------------
* Only SELECT, ASK, CONSTRUCT, and DESCRIBE are accepted (allowlist enforced
  before graph construction so rejected queries never touch the session).
* Multi-statement injections that start with an allowed keyword (e.g.
  ``SELECT ... ; DROP ALL``) pass the prefix check and reach rdflib, which
  rejects non-SELECT/ASK/CONSTRUCT/DESCRIBE update syntax in the parser.
* The in-memory rdflib graph is a read-only projection — the live
  ``GraphSession`` is never mutated by this route.
"""

import asyncio
import re
from typing import Any, Dict, List, Optional, Tuple

import rdflib
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..dependencies import get_session
from ..session import GraphSession

router = APIRouter(prefix="/api/sparql", tags=["Power User Tools"])

_ALLOWED_QUERY_TYPES = re.compile(
    r"^\s*(SELECT|ASK|CONSTRUCT|DESCRIBE)\b",
    re.IGNORECASE,
)


def _is_read_only_query(query: str) -> bool:
    """Return True only for SELECT / ASK / CONSTRUCT / DESCRIBE queries."""
    return bool(_ALLOWED_QUERY_TYPES.match(query))


class SparqlRequest(BaseModel):
    query: str


class SparqlResponse(BaseModel):
    columns: List[str]
    rows: List[Dict[str, Any]]
    total: int
    truncated: bool = False  # True when _SPARQL_MAX_ROWS was hit
    error: Optional[str] = None
    error_line: Optional[int] = None
    error_column: Optional[int] = None


NS = rdflib.Namespace("http://semantica.local/entity/")
PROP = rdflib.Namespace("http://semantica.local/prop/")


def _build_rdflib_graph(session: GraphSession) -> rdflib.Graph:
    graph = rdflib.Graph()
    graph.bind("ent", NS)
    graph.bind("prop", PROP)

    nodes, _ = session.get_nodes(skip=0, limit=999_999)
    edges, _ = session.get_edges(skip=0, limit=999_999)

    for node in nodes:
        subject = NS[str(node.get("id", ""))]
        node_type = node.get("type", "Entity")
        graph.add((subject, rdflib.RDF.type, NS[node_type]))

        content = node.get("content", "")
        if content:
            graph.add((subject, rdflib.RDFS.label, rdflib.Literal(content)))

        for key, value in node.get("properties", {}).items():
            if key in {"content", "valid_from", "valid_until"}:
                continue
            graph.add((subject, PROP[key], rdflib.Literal(value)))

    for edge in edges:
        source = NS[str(edge.get("source", ""))]
        target = NS[str(edge.get("target", ""))]
        relationship = edge.get("type", "relatedTo")
        graph.add((source, PROP[relationship], target))

    return graph


# ---------------------------------------------------------------------------
# Resource limits (override in tests via patch.object)
# ---------------------------------------------------------------------------
_SPARQL_MAX_ROWS = 5_000     # hard cap on returned rows
_SPARQL_TIMEOUT_S = 30       # seconds before abandoning the await
_SPARQL_MAX_CONCURRENT = 4   # semaphore: max simultaneous executions

# Semaphore caps how many graph.query calls run concurrently so that
# timed-out threads (which keep running in the pool) cannot crowd out
# other requests by exhausting the default ThreadPoolExecutor workers.
_sparql_semaphore = asyncio.Semaphore(_SPARQL_MAX_CONCURRENT)


def _cap_rows(items: Any, row_builder) -> Tuple[List[Dict[str, Any]], bool]:
    """Materialize up to ``_SPARQL_MAX_ROWS`` items via ``row_builder``, reporting truncation.

    Shared by the SELECT and CONSTRUCT/DESCRIBE branches below so the row cap
    is enforced identically regardless of query type.
    """
    rows: List[Dict[str, Any]] = []
    truncated = False
    for item in items:
        if len(rows) >= _SPARQL_MAX_ROWS:
            truncated = True
            break
        rows.append(row_builder(item))
    return rows, truncated


@router.post("", response_model=SparqlResponse)
async def execute_sparql(
    req: SparqlRequest,
    session: GraphSession = Depends(get_session),
):
    if not _is_read_only_query(req.query):
        return SparqlResponse(
            columns=[],
            rows=[],
            total=0,
            error="Only SELECT, ASK, CONSTRUCT, and DESCRIBE queries are permitted.",
        )

    graph = await asyncio.to_thread(_build_rdflib_graph, session)

    async with _sparql_semaphore:
        try:
            query_results = await asyncio.wait_for(
                asyncio.to_thread(graph.query, req.query),
                timeout=_SPARQL_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            return SparqlResponse(
                columns=[],
                rows=[],
                total=0,
                error=f"Query timed out after {_SPARQL_TIMEOUT_S} seconds.",
            )
        except Exception as exc:
            error = str(exc)
            line_match = re.search(r"line[\s:]+(\d+)", error, re.IGNORECASE)
            column_match = re.search(r"col(?:umn)?[\s:]+(\d+)", error, re.IGNORECASE)
            return SparqlResponse(
                columns=[],
                rows=[],
                total=0,
                error=error,
                error_line=int(line_match.group(1)) if line_match else None,
                error_column=int(column_match.group(1)) if column_match else None,
            )

    # ---------------------------------------------------------------------------
    # Serialize results into a type-aware tabular representation.
    # ASK      → single row: {"result": "true"|"false"}
    # CONSTRUCT/DESCRIBE → rows of {"subject", "predicate", "object"} triples
    # SELECT   → rows keyed by projected variable names
    # ---------------------------------------------------------------------------
    query_type: str = query_results.type  # always set by rdflib

    if query_type == "ASK":
        columns = ["result"]
        rows = [{"result": "true" if query_results.askAnswer else "false"}]
        truncated = False

    elif query_type in ("CONSTRUCT", "DESCRIBE"):
        columns = ["subject", "predicate", "object"]
        rows, truncated = _cap_rows(
            query_results,  # rdflib always yields (s, p, o) 3-tuples
            lambda triple: {
                "subject": str(triple[0]),
                "predicate": str(triple[1]),
                "object": str(triple[2]),
            },
        )

    else:  # SELECT
        columns = [str(var) for var in (query_results.vars or [])]
        rows, truncated = _cap_rows(
            query_results,
            lambda row: {
                column: (str(row[index]) if row[index] is not None else None)
                for index, column in enumerate(columns)
            },
        )

    return SparqlResponse(columns=columns, rows=rows, total=len(rows), truncated=truncated)
