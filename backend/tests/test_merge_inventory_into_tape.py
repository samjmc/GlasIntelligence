"""Tests for the tape inventory-merge script (verified-stakeholder graph merge)."""

import importlib.util
import os

_REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
_SCRIPTS = os.path.join(_REPO, "scripts")
_SPEC = importlib.util.spec_from_file_location("merge_inventory_into_tape", os.path.join(_SCRIPTS, "merge_inventory_into_tape.py"))
_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_mod)

_names_collide = _mod._names_collide
build_inventory_nodes = _mod.build_inventory_nodes
stable_demo_uuid = _mod.stable_demo_uuid


def _node(name):
    return {"uuid": stable_demo_uuid(name), "name": name, "labels": [], "summary": ""}


def _inventory(names_with_cats):
    return [{"name": n, "category": c, "context": f"Context for {n}"} for n, c in names_with_cats]


def test_stable_demo_uuid_is_deterministic_and_native():
    a, b = stable_demo_uuid("PSNC"), stable_demo_uuid("PSNC")
    assert a == b
    assert a.startswith("demo0000-")
    parts = a.split("-")
    assert len(parts) == 5
    assert [len(p) for p in parts[1:]] == [4, 4, 4, 12]


def test_merge_skips_existing_nodes_and_aliases():
    existing = [_node("NHSBSA"), _node("NHS")]
    inv = _inventory(
        [
            ("NHS Business Services Authority (NHSBSA)", "government"),
            ("NHS England", "government"),
            ("PSNC", "association"),
        ]
    )
    out = build_inventory_nodes(inv, existing, "2026-08-18T00:00:00.000Z")
    names = [n["name"] for n in out]
    # NHSBSA already a node; NHS England is a distinct org and must be kept.
    assert "NHS England" in names
    assert "PSNC" in names
    assert all("NHSBSA" not in n["name"] for n in out)


def test_substring_is_not_an_alias_collision():
    # 'NHS' must not swallow distinct orgs whose name merely contains it.
    assert not _names_collide("NHS", "NHS Counter Fraud Authority")
    assert not _names_collide("NHS", "NHS England")
    # True aliases still collide.
    assert _names_collide("NHS Business Services Authority (NHSBSA)", "NHSBSA")
    assert _names_collide("PSNC", "Pharmaceutical Services Negotiating Committee (PSNC)")


def test_category_maps_to_actor_label():
    inv = _inventory([("Department of Health and Social Care", "government"), ("Sigma Pharmaceuticals", "company")])
    out = build_inventory_nodes(inv, [], "2026-08-18T00:00:00.000Z")
    by_name = {n["name"]: n for n in out}
    assert by_name["Department of Health and Social Care"]["labels"] == ["GovernmentOrganization"]
    assert by_name["Sigma Pharmaceuticals"]["labels"] == ["Organization"]


def test_merge_has_no_duplicate_uuids_or_names():
    inv = _inventory([("CCA", "industry_body"), ("RCGP", "association"), ("PSNC", "association")])
    out = build_inventory_nodes(inv, [], "2026-08-18T00:00:00.000Z")
    assert len({n["uuid"] for n in out}) == len(out)
    assert len({n["name"] for n in out}) == len(out)


def test_merge_drops_blank_names():
    inv = [{"name": "  ", "category": "other", "context": ""}, {"name": "Boots", "category": "company"}]
    out = build_inventory_nodes(inv, [], "2026-08-18T00:00:00.000Z")
    assert [n["name"] for n in out] == ["Boots"]
