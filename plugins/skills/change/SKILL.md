---
name: change
description: Inspect graph changes over time and ontology version diffs in Semantica. Uses ContextGraph.state_at for point-in-time graph state and change_management.VersionManager for ontology versioning.
---

# /semantica:change

Track what changed. Usage: `/semantica:change <task> [args]`

> Two distinct mechanisms cover this, and they are **not** interchangeable:
>
> | Question | Tool |
> | --- | --- |
> | "What did the *graph* look like on date X?" | `ContextGraph.state_at()` |
> | "What changed between *ontology* versions?" | `change_management.VersionManager` |

---

## `graph-at <timestamp>` — point-in-time graph state

```python
from semantica.context import ContextGraph

graph = ContextGraph()
graph.load_from_file("~/.semantica/kg.json")

snapshot = graph.state_at("2026-06-01")      # str | int | float | datetime
```

Diff two moments by taking two snapshots and comparing node/edge sets:

```python
before = graph.state_at("2026-06-01")
after  = graph.state_at("2026-09-01")
added  = set(after["nodes"]) - set(before["nodes"])
```

For richer temporal work (scrubbing, evolution, temporal patterns) use
`/semantica:temporal`, which wraps the same layer.

---

## `node-history <node_id>` — who touched this node

Node-level history is provenance, not change management:

```python
from semantica.provenance import ProvenanceManager

pm = ProvenanceManager(storage_path="~/.semantica/prov.db")
history = pm.revision_history(node_id)
log     = pm.audit_log(since="2026-01-01")
```

---

## `versions` / `diff <v1> <v2>` — ontology versioning

```python
from semantica.change_management import VersionManager

vm = VersionManager()
vm.create_version("1.1.0", ontology)
vm.list_versions()
vm.get_latest_version()

delta = vm.compare_versions("1.0.0", "1.1.0")
delta = vm.diff_ontologies(base_ontology, target_ontology)
migrated = vm.migrate_ontology("1.0.0", "1.1.0", ontology)
```

`TemporalVersionManager` and `OntologyVersionManager` are also exported for
time-scoped and ontology-specific variants.
