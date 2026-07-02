from graph_guard.extract import parse_frontmatter, extract_note, build_graph
from graph_guard.store import TripleStore

def test_parse_frontmatter_scalar_and_list():
    fm, body = parse_frontmatter("---\ntype: Project\ntags: [ai, ml]\n---\nbody here")
    assert fm["type"] == "Project" and fm["tags"] == ["ai", "ml"] and body.strip() == "body here"

def test_no_frontmatter():
    fm, body = parse_frontmatter("just body")
    assert fm == {} and body == "just body"

def test_extract_wikilinks_as_mentions():
    nodes, edges = extract_note("project_x.md", "see [[Bow]] and [[Ghost|the scout]]")
    ids = {n["id"] for n in nodes}
    assert "Bow" in ids and "Ghost" in ids
    preds = {(e["src"], e["predicate"], e["dst"]) for e in edges}
    assert ("project_x.md", "mentions", "Bow") in preds
    assert ("project_x.md", "mentions", "Ghost") in preds  # alias stripped

def test_note_typed_from_prefix():
    nodes, _ = extract_note("project_x.md", "hi")
    note = [n for n in nodes if n["id"] == "project_x.md"][0]
    assert note["type"] == "Project"

def test_frontmatter_tags_and_status():
    _, edges = extract_note("n.md", "---\ntags: [hunting]\nstatus: LIVE\n---\nbody")
    preds = {(e["predicate"], e["dst"]) for e in edges}
    assert ("about", "hunting") in preds and ("has_status", "LIVE") in preds

def test_heading_types_decision_edges():
    _, edges = extract_note("n.md", "## Decisions\n- picked [[OptionA]]")
    assert any(e["predicate"] == "decides" and e["dst"] == "OptionA" for e in edges)

def test_build_graph_over_dir(tmp_path):
    (tmp_path / "project_a.md").write_text("about [[B]]")
    (tmp_path / "b.md").write_text("plain")
    s = TripleStore()
    counts = build_graph([str(tmp_path)], s)
    assert counts["notes"] == 2 and s.counts()["edges"] >= 1

def test_llm_fn_triples_filtered(tmp_path):
    (tmp_path / "a.md").write_text("x")
    s = TripleStore()
    def llm(note_id, text): return [(note_id, "supersedes", "old"), (note_id, "BOGUS", "y")]
    build_graph([str(tmp_path)], s, llm_fn=llm)
    preds = {e["predicate"] for e in s.all_edges()}
    assert "supersedes" in preds and "BOGUS" not in preds
