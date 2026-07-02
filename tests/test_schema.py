from graph_guard import schema

def test_node_type_from_prefix():
    assert schema.node_type("project_moonshot.md") == "Project"
    assert schema.node_type("feedback_permissions.md") == "Feedback"
    assert schema.node_type("reference_x.md") == "Reference"
    assert schema.node_type("user_profile.md") == "Person"

def test_frontmatter_type_overrides_prefix():
    assert schema.node_type("project_x.md", {"type": "Person"}) == "Person"

def test_unknown_frontmatter_type_falls_back_to_note():
    assert schema.node_type("notes/random.md", {"type": "Sasquatch"}) == "Note"

def test_default_note():
    assert schema.node_type("notes/random.md") == "Note"

def test_predicate_validity():
    assert schema.is_valid_predicate("supersedes")
    assert not schema.is_valid_predicate("frobnicates")

def test_functional_predicates():
    assert "has_status" in schema.FUNCTIONAL
    assert "supersedes" in schema.FUNCTIONAL
    assert schema.FUNCTIONAL <= schema.PREDICATES  # functional preds are valid preds
