---
name: query
description: Query Semantica knowledge graphs — in-memory ContextGraph search, SPARQL over RDF triple stores, and Cypher over LPG backends.
---

# /semantica:query

Query the graph. Usage: `/semantica:query <task> [args]`

> Which API you want depends on where the graph lives.

---

## `search "<keywords>"` — the in-memory ContextGraph

This is the one that works with no external server.

```python
from semantica.context import ContextGraph

graph = ContextGraph()
graph.load_from_file("~/.semantica/kg.json")

results = graph.query("vendor selection", skip=0, limit=20)
```

Related lookups on the same object:

```python
graph.find_nodes(...)          graph.find_node(...)
graph.find_related_nodes(...)  graph.get_neighbors(node_id)
graph.find_similar_nodes(...)  graph.get_nodes_by_label(label)
```

Decision-specific queries belong to `/semantica:decision`.

---

## `sparql "<query>"` — RDF triple stores

```python
from semantica.triplet_store import TripletStore

store = TripletStore(backend="oxigraph")       # embedded; needs semantica[tripletstore-oxigraph]
# or backend="blazegraph" | "jena" | "rdf4j" with endpoint="http://..."
result = store.execute_query(sparql)
```

For query planning, optimisation, and caching over a backend:

```python
from semantica.triplet_store import QueryEngine

qe = QueryEngine()
plan   = qe.plan_query(sparql)
tuned  = qe.optimize_query(sparql)
result = qe.execute_query(sparql, store_backend=store)
stats  = qe.get_query_statistics()
```

Blazegraph / Jena / RDF4J need **no** extra — `semantica.triplet_store` speaks
SPARQL over HTTP using the core `requests` dependency.

---

## `cypher "<query>"` — labeled property graphs

```python
from semantica.graph_store import Neo4jStore    # needs semantica[graph-neo4j]

store = Neo4jStore(uri=..., user=..., password=...)
```

Also available: `FalkorDBStore`, `ApacheAgeStore`, `AmazonNeptuneStore`,
and `GraphManager` / `GraphStore` for backend-agnostic access.

**Not installed in this environment** — add the backend extra first, e.g.
`pip install "semantica[graph-neo4j]"`.
