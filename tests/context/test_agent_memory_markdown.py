from copy import deepcopy
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import yaml

from semantica.context.agent_memory import AgentMemory


def markdown_document(frontmatter, body=""):
    yaml_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
    return f"---\n{yaml_text}---\n\n{body}"


def required_frontmatter(memory_id="mem_test", **overrides):
    frontmatter = {
        "id": memory_id,
        "created_at": "2026-07-22T09:00:00+00:00",
        "updated_at": "2026-07-22T10:00:00+00:00",
        "type": "note",
    }
    frontmatter.update(overrides)
    return frontmatter


def test_markdown_round_trip_is_lossless_and_deterministic():
    memory = AgentMemory()
    content = "\n# Editable memory\n\n<!-- marker-like body text -->\n\n"
    memory.store(
        content,
        metadata={
            "type": "note",
            "updated_at": "2026-07-22T12:30:00+00:00",
            "source": "caf\u00e9 review",
            "tags": ["alpha", "beta"],
            "id": "metadata-id",
            "kind": "metadata-kind",
        },
        entities=[{"id": "ent_1", "type": "topic", "text": "Memory"}],
        relationships=[
            {
                "source_id": "ent_1",
                "target_id": "ent_2",
                "type": "related_to",
                "confidence": 0.9,
            }
        ],
        memory_id="mem_round_trip",
        timestamp=datetime.fromisoformat("2026-07-22T12:00:00+00:00"),
    )

    exported = memory.export(format="markdown")
    restored = AgentMemory()

    assert restored.import_data(exported, format="markdown") == 1
    assert restored.get("mem_round_trip") == memory.get("mem_round_trip")
    assert restored.export(format="markdown") == exported
    assert "caf\u00e9 review" in exported


def test_markdown_directory_round_trip_uses_one_stable_file_per_memory(tmp_path):
    memory = AgentMemory()
    for index in range(2):
        timestamp = f"2026-07-22T0{index + 8}:00:00"
        memory.store(
            f"Memory {index}",
            metadata={
                "type": "reference",
                "updated_at": timestamp,
                "source": f"source-{index}",
            },
            memory_id=f"mem_{index}",
            timestamp=datetime.fromisoformat(timestamp),
        )

    first_export = tmp_path / "first"
    assert memory.export(format="markdown", destination=first_export) == str(
        first_export
    )
    first_files = sorted(first_export.glob("*.md"))
    assert len(first_files) == 2

    restored = AgentMemory()
    assert restored.import_data(first_export, format="markdown") == 2
    assert set(restored.memory_items) == {"mem_0", "mem_1"}

    second_export = tmp_path / "second"
    restored.export(format="markdown", destination=second_export)
    assert {path.name: path.read_text(encoding="utf-8") for path in first_files} == {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(second_export.glob("*.md"))
    }


def test_multiple_memories_require_a_destination_but_filters_can_select_one():
    memory = AgentMemory()
    for memory_type in ("note", "reference"):
        memory.store(
            memory_type,
            metadata={
                "type": memory_type,
                "updated_at": "2026-07-22T10:00:00",
            },
            memory_id=f"mem_{memory_type}",
            timestamp=datetime(2026, 7, 22, 9, 0, 0),
        )

    with pytest.raises(ValueError, match="destination"):
        memory.export(format="markdown")

    exported = memory.export(format="markdown", type="note")
    assert "id: mem_note" in exported
    assert "id: mem_reference" not in exported


def test_markdown_update_replaces_supported_fields_and_preserves_id():
    memory = AgentMemory()
    memory.store(
        "Original content",
        metadata={
            "type": "note",
            "updated_at": "2026-07-22T09:30:00",
            "remove_me": True,
        },
        memory_id="mem_existing",
        timestamp=datetime(2026, 7, 22, 9, 0, 0),
    )
    edited = markdown_document(
        required_frontmatter(
            "mem_existing",
            created_at="2026-07-22T09:15:00",
            updated_at="2026-07-22T11:00:00",
            type="decision",
            source="manual edit",
        ),
        "Updated content",
    )

    assert memory.import_data(edited, format="markdown") == 1

    updated = memory.get("mem_existing")
    assert memory.count() == 1
    assert updated["memory_id"] == "mem_existing"
    assert updated["content"] == "Updated content"
    assert updated["timestamp"] == "2026-07-22T09:15:00"
    assert updated["metadata"] == {
        "type": "decision",
        "source": "manual edit",
        "updated_at": "2026-07-22T11:00:00",
    }
    assert memory.stats["items_by_type"] == {"decision": 1}
    assert [item.memory_id for item in memory.short_term_memory] == ["mem_existing"]


def test_public_update_preserves_id_and_statistics():
    memory = AgentMemory()
    memory.store(
        "Original",
        metadata={"type": "note"},
        memory_id="mem_update",
        timestamp=datetime(2026, 7, 22, 9, 0, 0),
    )

    assert memory.update("mem_update", content="Updated", metadata={"type": "decision"})
    assert memory.get("mem_update")["content"] == "Updated"
    assert set(memory.memory_items) == {"mem_update"}
    assert list(memory.memory_index) == ["mem_update"]
    assert memory.stats["total_items"] == 1
    assert memory.stats["items_by_type"] == {"decision": 1}


def test_reimporting_unchanged_markdown_does_not_rewrite_memory():
    memory = AgentMemory()
    document = markdown_document(required_frontmatter(), "Unchanged")
    assert memory.import_data(document, format="markdown") == 1
    before = memory.get("mem_test")

    with patch.object(
        memory, "_replace_memory_item", wraps=memory._replace_memory_item
    ) as replace:
        assert memory.import_data(document, format="markdown") == 1

    replace.assert_not_called()
    assert memory.get("mem_test") == before
    assert memory.count() == 1


def test_kind_is_accepted_as_the_type_alias():
    frontmatter = required_frontmatter()
    frontmatter["kind"] = frontmatter.pop("type")

    memory = AgentMemory()
    assert (
        memory.import_data(
            markdown_document(frontmatter, "Kind alias"), format="markdown"
        )
        == 1
    )
    assert memory.get("mem_test")["metadata"]["type"] == "note"


@pytest.mark.parametrize("missing_field", ["id", "created_at", "updated_at", "type"])
def test_required_frontmatter_fields_are_enforced(missing_field):
    frontmatter = required_frontmatter()
    frontmatter.pop(missing_field)

    with pytest.raises(ValueError, match="missing required"):
        AgentMemory().import_data(
            markdown_document(frontmatter, "Invalid"), format="markdown"
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"id": 123}, "'id' must be a string"),
        ({"created_at": "yesterday"}, "ISO-8601"),
        ({"updated_at": "later"}, "ISO-8601"),
        ({"type": ["note"]}, "must be a string"),
        ({"kind": "decision"}, "must match"),
        ({"metadata": []}, "must be a mapping"),
        ({"entities": {}}, "must be a list"),
        ({"entities": ["entity"]}, "must be a mapping"),
        ({"relationships": [1]}, "must be a mapping"),
        ({"metadata": {"type": "nested"}}, "duplicates reserved"),
        ({"metadata": {"source": "nested"}, "source": "top"}, "defined both"),
    ],
)
def test_invalid_frontmatter_values_return_actionable_errors(overrides, message):
    document = markdown_document(required_frontmatter(**overrides), "Invalid")

    with pytest.raises(ValueError, match=message):
        AgentMemory().import_data(document, format="markdown")


@pytest.mark.parametrize(
    "document",
    [
        "not frontmatter",
        "---\nid: broken",
        "---\nid: [unterminated\n---\n",
        (
            "---\nid: first\nid: second\ncreated_at: 2026-07-22T09:00:00\n"
            "updated_at: 2026-07-22T10:00:00\ntype: note\n---\n"
        ),
    ],
)
def test_malformed_frontmatter_is_rejected(document):
    with pytest.raises(ValueError, match="frontmatter"):
        AgentMemory().import_data(document, format="markdown")


def test_directory_is_fully_validated_before_any_memory_is_changed(tmp_path):
    valid = markdown_document(required_frontmatter("mem_valid"), "Valid")
    invalid_fields = required_frontmatter("mem_invalid")
    invalid_fields.pop("updated_at")
    invalid = markdown_document(invalid_fields, "Invalid")
    (tmp_path / "a-valid.md").write_text(valid, encoding="utf-8")
    (tmp_path / "z-invalid.md").write_text(invalid, encoding="utf-8")

    memory = AgentMemory()
    with pytest.raises(ValueError, match="updated_at"):
        memory.import_data(tmp_path, format="markdown")

    assert memory.count() == 0


def test_duplicate_ids_in_a_directory_are_rejected_before_import(tmp_path):
    document = markdown_document(required_frontmatter("mem_duplicate"), "Body")
    (tmp_path / "first.md").write_text(document, encoding="utf-8")
    (tmp_path / "second.markdown").write_text(document, encoding="utf-8")

    memory = AgentMemory()
    with pytest.raises(ValueError, match="Duplicate Markdown memory ID"):
        memory.import_data(tmp_path, format="markdown")

    assert memory.count() == 0


def test_markdown_import_keeps_provenance_out_of_the_context_graph():
    knowledge_graph = MagicMock()
    memory = AgentMemory(knowledge_graph=knowledge_graph)
    fields = required_frontmatter(
        entities=[{"id": "entity_1", "type": "topic"}],
        relationships=[
            {
                "source_id": "entity_1",
                "target_id": "entity_2",
                "type": "related_to",
            }
        ],
    )

    assert (
        memory.import_data(markdown_document(fields, "Provenance"), format="markdown")
        == 1
    )
    assert memory.get("mem_test")["entities"][0]["id"] == "entity_1"
    knowledge_graph.add_nodes.assert_not_called()
    knowledge_graph.add_edges.assert_not_called()


def test_operational_failure_restores_existing_in_memory_state():
    memory = AgentMemory()
    memory.store(
        "Original",
        metadata={
            "type": "note",
            "updated_at": "2026-07-22T09:30:00",
        },
        memory_id="mem_existing",
        timestamp=datetime(2026, 7, 22, 9, 0, 0),
    )
    before_memory = deepcopy(memory.get("mem_existing"))
    before_stats = deepcopy(memory.stats)
    edited_fields = required_frontmatter("mem_existing")
    original_store = memory.store

    def fail_after_store(*args, **kwargs):
        original_store(*args, **kwargs)
        raise RuntimeError("store unavailable")

    with patch.object(memory, "store", side_effect=fail_after_store):
        with pytest.raises(RuntimeError, match="store unavailable"):
            memory.import_data(
                markdown_document(edited_fields, "Edited"), format="markdown"
            )

    assert memory.get("mem_existing") == before_memory
    assert memory.stats == before_stats
    assert list(memory.memory_index) == ["mem_existing"]
    assert [item.memory_id for item in memory.short_term_memory] == ["mem_existing"]


def test_import_does_not_report_retention_pruned_memory_as_successful():
    memory = AgentMemory(retention_policy="1_days")
    fields = required_frontmatter(
        "mem_expired",
        created_at="2000-01-01T00:00:00",
        updated_at="2000-01-01T00:00:00",
    )

    with pytest.raises(RuntimeError, match="did not confirm"):
        memory.import_data(markdown_document(fields, "Expired"), format="markdown")

    assert memory.count() == 0
    assert memory.stats["total_items"] == 0


def test_exported_filenames_cannot_escape_or_collide_with_destination(tmp_path):
    memory = AgentMemory()
    for memory_id in ("../outside", "a/b", "a\\b", "A/B"):
        memory.store(
            memory_id,
            metadata={
                "type": "note",
                "updated_at": "2026-07-22T10:00:00",
            },
            memory_id=memory_id,
            timestamp=datetime(2026, 7, 22, 9, 0, 0),
        )

    destination = tmp_path / "export"
    memory.export(format="markdown", destination=destination)
    exported_files = list(destination.glob("*.md"))

    assert len(exported_files) == 4
    assert len({path.name.casefold() for path in exported_files}) == 4
    assert all(path.parent == destination for path in exported_files)
    assert not (tmp_path / "outside.md").exists()


def test_empty_markdown_export_and_import_are_no_ops():
    memory = AgentMemory()

    assert memory.export(format="markdown") == ""
    assert memory.import_data("", format="markdown") == 0


def test_legacy_dict_import_behavior_is_unchanged():
    memory = AgentMemory()
    data = {
        "memories": [
            {
                "memory_id": "source_id",
                "content": "Legacy import",
                "metadata": {"type": "note"},
                "timestamp": "2000-01-01T00:00:00",
            }
        ]
    }

    assert memory.import_data(data, format="dict") == 1
    assert not memory.exists("source_id")
    imported = next(iter(memory.memory_items.values()))
    assert imported.content == "Legacy import"
    assert imported.metadata == {"type": "note"}


def test_markdown_export_destination_must_be_a_directory(tmp_path):
    destination = tmp_path / "memory.md"
    destination.write_text("occupied", encoding="utf-8")

    with pytest.raises(ValueError, match="not a directory"):
        AgentMemory().export(format="markdown", destination=destination)
