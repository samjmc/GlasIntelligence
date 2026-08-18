"""Tests for the graph noise filter (quantitative + non-actor nodes)."""

from app.services.graph_noise_filter import (
    is_quant_noise,
    is_non_actor,
    filter_quant_noise,
)


def _node(uuid, name, labels=None):
    return {"uuid": uuid, "name": name, "labels": labels or [], "summary": ""}


def test_pure_numbers_are_noise():
    for name in ("100", "234", "52", "2.7%", "86%", "43%", "19.7%", "2026", "2025/26", "18-25", "26-31"):
        assert is_quant_noise(name), name


def test_currency_amounts_are_noise():
    for name in ("£15", "£17", "$2.5", "€1,200", "£3,636"):
        assert is_quant_noise(name), name


def test_quantities_with_unit_words_are_noise():
    for name in ("3.3 million", "£3.636 billion", "52k", "2.5m"):
        assert is_quant_noise(name), name


def test_standalone_dates_are_noise():
    for name in ("June 2026", "Mar 2026"):
        assert is_quant_noise(name), name


def test_url_domains_are_non_actors():
    for name in ("pharmacytimes.com", "beckershospitalreview.com", "www.nhs.uk"):
        assert is_non_actor(name, None), name


def test_actor_labeled_nodes_are_actors():
    for labels in (["Organization"], ["Person"], ["MediaOrJournalist"], ["CommunityGroup"]):
        assert not is_non_actor("2.7%", labels), labels


def test_unlabeled_concept_phrases_are_non_actors():
    for name in ("minor illness", "high street", "community", "consultations", "pharmacy funding", "NHS contract information"):
        assert is_non_actor(name, None), name


def test_proper_noun_unlabeled_entities_are_kept():
    for name in ("England", "PBM Reform", "Pharmacy First"):
        assert not is_non_actor(name, None), name


def test_event_labels_with_lowercase_are_non_actors():
    # 'April 2026 caps' and 'NHS guide for 2026' name events/artefacts, not
    # stakeholders — the proper-noun rule drops them.
    assert is_non_actor("April 2026 caps", None)
    assert is_non_actor("NHS guide for 2026", None)


def test_filter_drops_noise_nodes_and_dangling_edges():
    nodes = [
        _node("a", "NHS England", ["Organization"]),
        _node("b", "2.7%"),
        _node("c", "CPE", ["Organization"]),
        _node("d", "2026"),
        _node("e", "pharmacytimes.com"),
        _node("f", "minor illness"),
        _node("g", "England"),
    ]
    edges = [
        {"source": {"uuid": "a"}, "target": {"uuid": "b"}},  # dangling (b)
        {"source": {"uuid": "a"}, "target": {"uuid": "c"}},  # kept
        {"source": {"uuid": "d"}, "target": {"uuid": "c"}},  # dangling (d)
        {"source": {"uuid": "a"}, "target": {"uuid": "g"}},  # kept (England)
        {"source": {"uuid": "e"}, "target": {"uuid": "a"}},  # dangling (e)
    ]
    kept_nodes, kept_edges = filter_quant_noise(nodes, edges)
    assert [n["name"] for n in kept_nodes] == ["NHS England", "CPE", "England"]
    assert len(kept_edges) == 2


def test_filter_noop_when_clean():
    nodes = [_node("a", "NHS England", ["Organization"]), _node("c", "CPE", ["Organization"])]
    edges = [{"source": {"uuid": "a"}, "target": {"uuid": "c"}}]
    kept_nodes, kept_edges = filter_quant_noise(nodes, edges)
    assert kept_nodes is nodes
    assert kept_edges is edges
