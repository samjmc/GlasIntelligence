"""Tests for the quantitative-noise node filter."""

from app.services.graph_noise_filter import is_quant_noise, filter_quant_noise


def _node(uuid, name):
    return {"uuid": uuid, "name": name, "labels": ["Organization"], "summary": ""}


def test_pure_numbers_are_noise():
    for name in ("100", "234", "52", "2.7%", "86%", "43%", "19.7%", "2026", "2025/26", "18-25", "26-31"):
        assert is_quant_noise(name), name


def test_currency_amounts_are_noise():
    for name in ("£15", "£17", "$2.5", "€1,200", "£3,636"):
        assert is_quant_noise(name), name


def test_standalone_dates_are_noise():
    for name in ("June 2026", "Mar 2026"):
        assert is_quant_noise(name), name


def test_descriptive_labels_are_kept():
    for name in (
        "NHS England",
        "pharmacies",
        "April 2026 caps",
        "£500 fixed payment",
        "73 patients",
        "3.3 million",
        "NHS guide for 2026",
        "Pharmacy First",
    ):
        assert not is_quant_noise(name), name


def test_filter_drops_nodes_and_dangling_edges():
    nodes = [
        _node("a", "NHS England"),
        _node("b", "2.7%"),
        _node("c", "CPE"),
        _node("d", "2026"),
    ]
    edges = [
        {"source": {"uuid": "a"}, "target": {"uuid": "b"}},  # dangling (b dropped)
        {"source": {"uuid": "a"}, "target": {"uuid": "c"}},  # kept
        {"source": {"uuid": "d"}, "target": {"uuid": "c"}},  # dangling (d dropped)
    ]
    kept_nodes, kept_edges = filter_quant_noise(nodes, edges)
    assert [n["name"] for n in kept_nodes] == ["NHS England", "CPE"]
    assert len(kept_edges) == 1
    assert kept_edges[0]["target"]["uuid"] == "c"


def test_filter_noop_when_clean():
    nodes = [_node("a", "NHS England"), _node("c", "CPE")]
    edges = [{"source": {"uuid": "a"}, "target": {"uuid": "c"}}]
    kept_nodes, kept_edges = filter_quant_noise(nodes, edges)
    assert kept_nodes is nodes  # same list object when nothing dropped
    assert kept_edges is edges
