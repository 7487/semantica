# Graph storage backends and feature matrix

Semantica separates graph modeling from physical storage. LPG backends are accessed through `graph_store` adapters; RDF backends are accessed through `triplet_store` adapters.

This page is intentionally conservative: it distinguishes between an adapter existing, a feature being generally available with that model, and a backend needing user-supplied wiring.

## Status labels

- `built-in`: adapter implementation exists in Semantica core.
- `tested`: covered by automated integration fixtures or tests.
- `example-only`: usable example exists, but support is not asserted by integration tests.
- `interface/BYO`: interface or integration point exists; bring your own backend wiring.

## Adapter inventory

| Backend | Model | Adapter | Status | Reference |
| --- | --- | --- | --- | --- |
| Neo4j | LPG | `semantica.graph_store.Neo4jGraphStore` | built-in | `cookbook/introduction/09_Graph_Store.ipynb` |
| Amazon Neptune | LPG | `semantica.graph_store.NeptuneGraphStore` | built-in | `cookbook/introduction/21_Amazon_Neptune_Store.ipynb` |
| Apache AGE | LPG | `semantica.graph_store.AgeGraphStore` | built-in | `docs/graph_stores/apache_age.md` |
| RDF4J | RDF | `semantica.triplet_store.RDF4JStore` | built-in | `cookbook/introduction/20_Triplet_Store.ipynb` |
| Apache Jena | RDF | `semantica.triplet_store.JenaStore` | built-in | `cookbook/introduction/20_Triplet_Store.ipynb` |
| Blazegraph | RDF | `semantica.triplet_store.BlazegraphStore` | built-in | `cookbook/introduction/20_Triplet_Store.ipynb` |
| Anzo | RDF | `semantica.triplet_store.AnzoStore` | interface/BYO | `cookbook/introduction/20_Triplet_Store.ipynb` |

## Feature matrix

`Yes` means the capability is expected to work with the adapter and graph model. `Partial` means the capability works with model-specific constraints. `BYO` means the user must supply or validate wiring for the backend.

| Backend | Model | Ingestion | Context graph construction | Reasoning/analytics | Provenance | Known limitations |
| --- | --- | --- | --- | --- | --- | --- |
| Neo4j | LPG | Yes | Yes | Yes | Partial | Provenance and context metadata are stored as node and edge properties; relationship properties and stable node identifiers are required. |
| Amazon Neptune | LPG | Yes | Yes | Partial | Partial | Use the property-graph endpoint; AWS auth, VPC, and endpoint configuration can affect local tests. Provenance depends on node/edge properties. |
| Apache AGE | LPG | Yes | Yes | Partial | Partial | Runs through PostgreSQL/AGE; Cypher compatibility and property handling can differ from standalone LPG engines. |
| RDF4J | RDF | Yes | Partial | Partial | Partial | Context separation relies on named graphs; triple-level provenance may require reification or graph-level metadata. |
| Apache Jena | RDF | Yes | Partial | Partial | Partial | Named graphs are needed for context separation; backend configuration and transaction behavior matter. |
| Blazegraph | RDF | Yes | Partial | Partial | Partial | Use quads/named graphs for context; IRI stability and graph naming matter for provenance. |
| Anzo | RDF | BYO | BYO | BYO | BYO | Anzo deployments are environment-specific; validate repository/graph naming, named-graph support, and provenance mapping. |

## RDF and LPG differences

- LPG backends store context and provenance as graph elements and properties. If a backend does not support relationship properties, some provenance patterns may be degraded.
- RDF backends rely on IRIs, named graphs, and optional reification. Context graphs and provenance are easiest to preserve when the store supports named graphs/quads.
- Ingestion works across both models, but the physical representation differs: LPG stores nodes/edges directly, while RDF stores subject-predicate-object statements.
- Reasoning and analytics should be validated against the adapter's query capabilities, especially for path traversal, property filters, and named-graph queries.

## Minimal connection examples

Prefer the referenced notebook cells for a working setup. The examples below show the intended adapter entrypoints, not a universal connection DSL.

### Neo4j

```python
from semantica.graph_store import Neo4jGraphStore

store = Neo4jGraphStore(
    uri='bolt://localhost:7687',
    username='neo4j',
    password='password'
)
```

### Amazon Neptune

```python
from semantica.graph_store import NeptuneGraphStore

store = NeptuneGraphStore(
    host='your-neptune-endpoint',
    port=8182
)
```

### Apache AGE

```python
from semantica.graph_store import AgeGraphStore

store = AgeGraphStore(
    dsn='postgresql://user:password@localhost:5432/semantica',
    graph='semantica'
)
```

### RDF4J

```python
from semantica.triplet_store import RDF4JStore

store = RDF4JStore(
    url='http://localhost:8080/rdf4j-server',
    repository='semantica'
)
```

### Apache Jena

```python
from semantica.triplet_store import JenaStore

store = JenaStore(
    url='http://localhost:3030',
    dataset='semantica'
)
```

### Blazegraph

```python
from semantica.triplet_store import BlazegraphStore

store = BlazegraphStore(
    url='http://localhost:9999/blazegraph/sparql'
)
```

### Anzo

```python
from semantica.triplet_store import AnzoStore

store = AnzoStore(
    url='http://anzo-host:10000',
    repository='semantica'
)
```

Replace hostnames, ports, repositories, graphs, and credentials with values from your environment. For regulated or self-hosted deployments, keep credentials in environment variables or secret storage rather than source code.
