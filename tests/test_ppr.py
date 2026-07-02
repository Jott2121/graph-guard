from graph_guard.ppr import personalized_pagerank, node_specificity

def test_ppr_favors_seed_neighborhood():
    adj = {"A": {"B": 1.0}, "B": {"A": 1.0, "C": 1.0}, "C": {"B": 1.0},
           "D": {"E": 1.0}, "E": {"D": 1.0}}
    r = personalized_pagerank(adj, ["A"])
    assert r["B"] > r["D"]  # B is one hop from seed A; D is disconnected from A
    assert r["A"] > 0

def test_ppr_empty_graph():
    assert personalized_pagerank({}, ["X"]) == {}

def test_ppr_no_valid_seeds_falls_back_uniform():
    adj = {"A": {"B": 1.0}, "B": {"A": 1.0}}
    r = personalized_pagerank(adj, ["Z"])  # seed absent -> plain PageRank
    assert set(r) == {"A", "B"} and abs(r["A"] - r["B"]) < 1e-6

def test_scores_sum_to_about_one():
    adj = {"A": {"B": 1.0}, "B": {"A": 1.0, "C": 1.0}, "C": {"B": 1.0}}
    r = personalized_pagerank(adj, ["A"])
    assert abs(sum(r.values()) - 1.0) < 1e-3

def test_node_specificity_downweights_hubs():
    adj = {"hub": {"a": 1.0, "b": 1.0, "c": 1.0},
           "a": {"hub": 1.0}, "b": {"hub": 1.0}, "c": {"hub": 1.0}}
    spec = node_specificity(adj)
    assert spec["hub"] < spec["a"]

def test_node_specificity_uses_single_degree_count():
    # symmetric adjacency: A-B-C ; B has degree 2, A/C degree 1
    adj = {"A": {"B": 1.0}, "B": {"A": 1.0, "C": 1.0}, "C": {"B": 1.0}}
    spec = node_specificity(adj)
    import math
    assert abs(spec["B"] - 1.0 / (1.0 + math.log(1.0 + 2))) < 1e-9  # degree 2, not 4
