#!/usr/bin/env python3
"""Merge the verified entity inventory into the final graph snapshot of a demo tape.

The entity knowledge-expansion pass (services/entity_expansion.py) adds verified
real stakeholders to a project's entity_inventory, but Zep only creates graph
nodes via NER from episodes — so the expanded stakeholders often never appear as
nodes (observed 2026-08-18, Pharmacy First R2: 44 in inventory, only 2 became
Zep nodes). A demo tape would then replay a thin, near-empty stakeholder graph.

This tool merges the inventory into the LAST /api/graph/data/:id response of a
tape as nodes, so the replay ends on the full stakeholder set the pipeline
verified. It is the additive mirror of scripts/filter_graph_noise.py: same
"run on a COPY" guard, same tape shape, deterministic demo UUIDs via the
recorder's own hashing so the output looks native to a recorded tape.

The merged nodes are honest: every one comes from the verified inventory
(inventory entries are either extracted from the research text or passed the
live-verification gate). No fabricated relationships — edges are left as
recorded.

Usage:
    python3 scripts/merge_inventory_into_tape.py <tape-in.json> <project.json> <tape-out.json> [graph_id]
"""

import hashlib
import json
import os
import sys

_DEMO_UUID_PREFIX = "demo0000"


def stable_demo_uuid(key: str) -> str:
    """Deterministic demo-style UUID for a name, matching demo_recorder's shape."""
    digest = hashlib.sha256(key.encode()).hexdigest()
    return f"{_DEMO_UUID_PREFIX}-{digest[:4]}-{digest[4:8]}-{digest[8:12]}-{digest[12:24]}"


# Map inventory category -> actor label, aligned with the noise filter's actor set.
_CATEGORY_LABEL = {
    "government": "GovernmentOrganization",
    "industry_body": "Organization",
    "individual": "Person",
    "company": "Organization",
    "professional_association": "Organization",
    "regulator": "Organization",
    "community": "CommunityGroup",
    "ngo": "NGO",
    "media": "MediaOrJournalist",
    "research": "Organization",
    "association": "Organization",
}


def _name_variants(name: str) -> list[str]:
    """Normalized variants of a name, including the parenthetical alias.

    'NHS Business Services Authority (NHSBSA)' -> ['nhs business services authority',
    'nhsbsa', 'nhs business services authority nhsbsa'] so it dedupes against a node
    named exactly 'NHSBSA' without substring-matching distinct orgs like 'NHS England'.
    """
    n = (name or "").lower().strip()
    if not n:
        return []
    variants = [n]
    # Parenthetical alias: "Full Name (ALIAS)"
    if "(" in n and n.rstrip().endswith(")"):
        stem, alias = n.split("(", 1)
        stem = stem.strip().rstrip()
        alias = alias.rstrip(")").strip()
        variants += [stem, alias, f"{stem} {alias}"]
    return [v for v in variants if v]


def _names_collide(a: str, b: str) -> bool:
    """True when normalized names (incl. parenthetical aliases) overlap exactly."""
    va, vb = _name_variants(a), _name_variants(b)
    if not va or not vb:
        return False
    return not set(va).isdisjoint(set(vb))


def build_inventory_nodes(
    inventory: list[dict],
    existing_nodes: list[dict],
    created_at: str,
) -> list[dict]:
    """Turn inventory entries into graph nodes, skipping ones already present."""
    existing_names = [n.get("name", "") for n in existing_nodes]
    merged: list[dict] = []
    used: list[str] = []

    for entry in inventory:
        name = (entry.get("name") or "").strip()
        if not name:
            continue
        if any(_names_collide(name, e) for e in existing_names + used):
            continue

        category = entry.get("category") or "other"
        label = _CATEGORY_LABEL.get(category, "Organization")
        context = (entry.get("context") or "").strip()

        merged.append(
            {
                "uuid": stable_demo_uuid(name),
                "name": name,
                "labels": [label],
                "summary": context,
                "attributes": {"name": name},
                "created_at": created_at,
            }
        )
        used.append(name)

    return merged


def main() -> int:
    if len(sys.argv) not in (4, 5):
        print("usage: merge_inventory_into_tape.py <tape-in.json> <project.json> <tape-out.json> [graph_id]", file=sys.stderr)
        return 2
    tape_in, project_in, tape_out = sys.argv[1], sys.argv[2], sys.argv[3]
    graph_id = sys.argv[4] if len(sys.argv) == 5 else None

    if os.path.abspath(tape_in) == os.path.abspath(tape_out):
        print("error: output must differ from input (run on a copy)", file=sys.stderr)
        return 2

    tape = json.load(open(tape_in))
    project = json.load(open(project_in))
    inventory = project.get("entity_inventory") or []

    # Find the last graph-data response (optionally for a specific graph).
    target_idx = None
    for i, entry in enumerate(tape["entries"]):
        if entry.get("path") != "/api/graph/data/:id":
            continue
        data = entry.get("body", {}).get("data", {})
        if graph_id is not None and data.get("graph_id") != graph_id:
            continue
        target_idx = i

    if target_idx is None:
        print("error: no /api/graph/data/:id entry found" + (f" for graph {graph_id}" if graph_id else ""), file=sys.stderr)
        return 2

    entry = tape["entries"][target_idx]
    data = entry["body"]["data"]
    nodes = data.get("nodes") or []

    # Use a created_at consistent with the tape's recording window.
    created_at = max(
        (n.get("created_at") or "" for n in nodes if n.get("created_at")),
        default="2026-08-18T20:35:00.000Z",
    )

    additions = build_inventory_nodes(inventory, nodes, created_at)
    added_names = [n["name"] for n in additions]

    data["nodes"] = nodes + additions
    data["node_count"] = len(data["nodes"])

    json.dump(tape, open(tape_out, "w"))
    print(f"merged {len(additions)} inventory nodes into final graph snapshot (entry {target_idx})")
    if added_names:
        print("added:")
        for n in added_names:
            print(f"  - {n}")
    print(f"total graph nodes now {len(data['nodes'])}; wrote {tape_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
