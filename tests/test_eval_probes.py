from graph_guard.eval_probes import Probe, RELATIONAL, multi_hop_probes, simple_lookup_probes
from graph_guard.store import TripleStore


def test_relational_excludes_mentions():
    assert "mentions" not in RELATIONAL
    assert "supersedes" in RELATIONAL


def test_multi_hop_gold_is_edge_target():
    s = TripleStore()
    s.upsert_node({"id": "project_apollo.md", "type": "Project", "name": "project_apollo",
                   "note_path": "project_apollo.md"})
    s.upsert_node({"id": "reference_zenith.md", "type": "Reference", "name": "reference_zenith",
                   "note_path": "reference_zenith.md"})
    s.upsert_edge({"src": "project_apollo.md", "predicate": "supersedes", "dst": "reference_zenith.md"})

    probes, discarded = multi_hop_probes(s)

    assert discarded == 0
    assert len(probes) == 1
    p = probes[0]
    assert p.family == "multi_hop"
    assert p.query == "apollo"
    assert p.gold_id == "reference_zenith.md"


def test_multi_hop_high_overlap_discarded():
    s = TripleStore()
    s.upsert_node({"id": "apex1", "type": "Project", "name": "apex protocol v1", "note_path": "apex1.md"})
    s.upsert_node({"id": "apex2", "type": "Project", "name": "apex protocol v2", "note_path": "apex2.md"})
    s.upsert_edge({"src": "apex1", "predicate": "supersedes", "dst": "apex2"})

    probes, discarded = multi_hop_probes(s)

    assert probes == []
    assert discarded == 1


def test_multi_hop_excludes_mentions():
    s = TripleStore()
    s.upsert_node({"id": "project_apollo.md", "type": "Project", "name": "project_apollo",
                   "note_path": "project_apollo.md"})
    s.upsert_node({"id": "reference_zenith.md", "type": "Reference", "name": "reference_zenith",
                   "note_path": "reference_zenith.md"})
    s.upsert_edge({"src": "project_apollo.md", "predicate": "mentions", "dst": "reference_zenith.md"})

    probes, discarded = multi_hop_probes(s)

    assert probes == []
    assert discarded == 0  # excluded by predicate, not by the overlap filter


def test_multi_hop_only_real_notes():
    s = TripleStore()
    s.upsert_node({"id": "project_apollo.md", "type": "Project", "name": "project_apollo",
                   "note_path": "project_apollo.md"})
    # dst registered as a node but has no note_path -- not a real note (e.g. an external entity)
    s.upsert_node({"id": "ghost", "type": "Reference", "name": "ghost zenith"})
    s.upsert_edge({"src": "project_apollo.md", "predicate": "supersedes", "dst": "ghost"})
    # src registered as a node but has no note_path -- must be filtered the same way
    s.upsert_edge({"src": "ghost", "predicate": "supersedes", "dst": "project_apollo.md"})
    # src id never registered as a node at all
    s.upsert_edge({"src": "phantom", "predicate": "supersedes", "dst": "project_apollo.md"})

    probes, discarded = multi_hop_probes(s)

    assert probes == []
    assert discarded == 0


def test_simple_lookup_gold_is_self():
    s = TripleStore()
    s.upsert_node({"id": "c.md", "type": "Note", "name": "project_charlie", "note_path": "c.md"})
    s.upsert_node({"id": "a.md", "type": "Note", "name": "project_alpha", "note_path": "a.md"})
    s.upsert_node({"id": "b.md", "type": "Note", "name": "project_bravo", "note_path": "b.md"})
    # a non-note entity must never be sampled
    s.upsert_node({"id": "ghost", "type": "Note", "name": "ghost"})

    all_probes = simple_lookup_probes(s)
    assert [p.gold_id for p in all_probes] == ["a.md", "b.md", "c.md"]
    for p in all_probes:
        assert p.family == "simple_lookup"
    assert all_probes[0].query == "alpha"

    limited = simple_lookup_probes(s, n=2)
    assert [p.gold_id for p in limited] == ["a.md", "b.md"]


def test_determinism():
    s = TripleStore()
    s.upsert_node({"id": "project_apollo.md", "type": "Project", "name": "project_apollo",
                   "note_path": "project_apollo.md"})
    s.upsert_node({"id": "reference_zenith.md", "type": "Reference", "name": "reference_zenith",
                   "note_path": "reference_zenith.md"})
    s.upsert_node({"id": "apex1", "type": "Project", "name": "apex protocol v1", "note_path": "apex1.md"})
    s.upsert_node({"id": "apex2", "type": "Project", "name": "apex protocol v2", "note_path": "apex2.md"})
    s.upsert_edge({"src": "project_apollo.md", "predicate": "supersedes", "dst": "reference_zenith.md"})
    s.upsert_edge({"src": "apex1", "predicate": "depends_on", "dst": "apex2"})

    assert multi_hop_probes(s) == multi_hop_probes(s)
    assert simple_lookup_probes(s) == simple_lookup_probes(s)
    assert simple_lookup_probes(s, n=2) == simple_lookup_probes(s, n=2)


def test_probe_is_frozen_dataclass():
    p = Probe(family="multi_hop", query="q", gold_id="g")
    assert (p.family, p.query, p.gold_id) == ("multi_hop", "q", "g")
    try:
        p.query = "x"
        assert False, "Probe must be frozen"
    except Exception:
        pass
