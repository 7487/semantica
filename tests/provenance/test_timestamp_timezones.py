"""Provenance timestamps must carry a timezone (issue #1114).

The provenance package stamped every record with ``datetime.utcnow()``, which
returns a naive datetime that happens to hold UTC. The exporters stamped theirs
with ``datetime.now()``, which returns a naive datetime holding local time. Both
serialize identically, so a graph mixing the two cannot be ordered, and the
values reach RDF as ``prov:generatedAtTime``/``startedAtTime``/``endedAtTime``
typed ``xsd:dateTime``, where a timezone-qualified SPARQL comparison discards
them. ``datetime.utcnow()`` is also deprecated as of Python 3.12.
"""

import warnings
from datetime import datetime

import pytest

from semantica.provenance.manager import ProvenanceManager
from semantica.provenance.schemas import ProvenanceEntry
from semantica.utils.helpers import utc_now


def assert_offset_aware(value):
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None, f"timezone-naive timestamp: {value!r}"


def test_provenance_entry_default_timestamp_is_offset_aware():
    entry = ProvenanceEntry(entity_id="e1", entity_type="Doc", activity_id="act1")
    assert_offset_aware(entry.timestamp)
    assert datetime.fromisoformat(entry.timestamp) <= utc_now()


def test_creating_an_entry_raises_no_deprecation_warning():
    """datetime.utcnow() is deprecated and scheduled for removal."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        ProvenanceEntry(entity_id="e1", entity_type="Doc", activity_id="act1")


def test_tracked_entity_timestamps_are_offset_aware():
    manager = ProvenanceManager()
    manager.track_entity("e1", source="doc.pdf")

    entry = manager.storage.retrieve_all()[0]
    assert_offset_aware(entry.timestamp)
    for field in ("first_seen", "last_updated"):
        value = getattr(entry, field, None)
        if value:
            assert_offset_aware(value)


def test_prov_o_export_timestamps_are_offset_aware():
    """The values land in RDF typed xsd:dateTime, so the offset is the contract."""
    rdflib = pytest.importorskip("rdflib")
    from rdflib.namespace import XSD

    manager = ProvenanceManager()
    manager.track_entity("e_parent", source="doc.pdf")
    manager.track_entity(
        "e_child", source="doc.pdf", parent_entity_id="e_parent",
        used_entities=["e_parent"], activity_id="act_transform",
    )

    graph = rdflib.Graph()
    graph.parse(data=manager.export_prov(format="turtle"), format="turtle")

    stamps = [o for o in graph.objects()
              if isinstance(o, rdflib.Literal) and o.datatype == XSD.dateTime]
    assert stamps, "no xsd:dateTime literals in the PROV-O export"
    for stamp in stamps:
        assert_offset_aware(str(stamp))


def test_prov_o_timestamps_are_valid_datetimestamp():
    """xsd:dateTimeStamp requires an explicit timezone; these now qualify."""
    rdflib = pytest.importorskip("rdflib")
    from rdflib.namespace import XSD

    manager = ProvenanceManager()
    manager.track_entity("e1", source="doc.pdf")
    graph = rdflib.Graph()
    graph.parse(data=manager.export_prov(format="turtle"), format="turtle")

    for stamp in [o for o in graph.objects()
                  if isinstance(o, rdflib.Literal) and o.datatype == XSD.dateTime]:
        assert rdflib.Literal(str(stamp), datatype=XSD.dateTime).ill_typed is False
        assert datetime.fromisoformat(str(stamp)).utcoffset() is not None
