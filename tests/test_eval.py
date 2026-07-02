from eval.eval_multihop import run

def test_graph_finds_multihop_note_flat_misses():
    r = run()
    assert r["flat_found_apex"] is False   # flat lexical misses the answer note
    assert r["graph_found_apex"] is True   # graph traversal surfaces it (one typed hop away)
