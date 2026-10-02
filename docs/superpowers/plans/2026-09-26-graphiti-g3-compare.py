"""G3: build the same dossier on Zep and on Graphiti, then compare (migration plan, G3).

Run from backend/ with the backend venv:
    python ../docs/superpowers/plans/2026-09-26-graphiti-g3-compare.py <dir with g0_dossier.txt + g0_ontology.json> {graphiti|zep|compare}

- graphiti: builds on GraphitiGraphStore (NEO4J_*, LLM_*). DeepSeek tokens only.
- zep:      builds on ZepGraphStore (ZEP_API_KEY). COSTS ZEP CREDITS: one per started
            350 bytes per episode; 287 for the pharmacy dossier at the app's 300/30 chunking.
- compare:  reads both saved builds, measures, prints the acceptance table. 0 credits.

Each build writes <dir>/g3_<backend>.json with its graph_id, so compare can run later.
Zep gets the free plan's 5 custom types (Person, Organization + 3 specific); Graphiti
gets all 10, as the plan says. Graphs are kept for inspection; delete them afterwards.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import time

sys.path.insert(0, os.getcwd())

from app.config import Config  # noqa: E402
from app.services.graph_builder import GraphBuilderService  # noqa: E402
from app.services.text_processor import TextProcessor  # noqa: E402

DIR = pathlib.Path(sys.argv[1])
MODE = sys.argv[2]
ZEP_ENTITY_KEEP = ["Person", "Organization", "PharmacyAssociation", "PharmacyChain", "PoliticalLeader"]
ZEP_EDGE_KEEP = ["WORKS_FOR", "REPRESENTS", "REGULATES", "SUPPORTS", "OPPOSES"]


def load():
    text = (DIR / "g0_dossier.txt").read_text(encoding="utf-8")
    ontology = json.loads((DIR / "g0_ontology.json").read_text(encoding="utf-8"))
    return text, ontology


def capped(ontology: dict) -> dict:
    keep_e = set(ZEP_ENTITY_KEEP)
    ents = [e for e in ontology["entity_types"] if e["name"] in keep_e]
    edges = []
    for e in ontology.get("edge_types", []):
        if e["name"] not in ZEP_EDGE_KEEP:
            continue
        st = [p for p in e.get("source_targets", []) if p["source"] in keep_e and p["target"] in keep_e]
        edges.append({**e, "source_targets": st})
    return {"entity_types": ents, "edge_types": edges}


def build(store, ontology: dict, chunk_size: int, overlap: int) -> dict:
    text, _ = load()
    builder = GraphBuilderService(store=store)
    chunks = TextProcessor.split_text(text, chunk_size=chunk_size, overlap=overlap)
    t0 = time.time()
    gid = builder.create_graph(f"G3 {store.backend}")
    builder.set_ontology(gid, ontology)
    ids = builder.add_text_batches(gid, chunks, 3, lambda m, p: print(f"  {m}", flush=True))
    sent_s = time.time() - t0
    builder._wait_for_episodes(ids, lambda m, p: print(f"  {m}", flush=True), timeout=3600)
    out = {
        "backend": store.backend,
        "graph_id": gid,
        "chunks": len(chunks),
        "chunk_size": chunk_size,
        "episode_ids": len(ids),
        "send_s": round(sent_s),
        "total_s": round(time.time() - t0),
        "entity_types_sent": [e["name"] for e in ontology["entity_types"]],
    }
    if store.backend == "graphiti":
        out["llm_usage"] = store.usage.snapshot()
    (DIR / f"g3_{store.backend}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return out


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (name or "").lower()).strip()


def same(a: str, b: str) -> bool:
    a, b = norm(a), norm(b)
    return bool(a) and bool(b) and (a == b or (len(a) > 3 and a in b) or (len(b) > 3 and b in a))


def measure(store, gid: str) -> dict:
    nodes = store.list_nodes(gid)
    edges = store.list_edges(gid)
    typed = [n for n in nodes if any(lab not in ("Entity", "Node") for lab in (n.labels or []))]
    degree: dict[str, int] = {}
    for e in edges:
        for u in (e.source_node_uuid, e.target_node_uuid):
            degree[u] = degree.get(u, 0) + 1
    typed_top = sorted(typed, key=lambda n: -degree.get(n.uuid, 0))
    # Persona grounding: the profile generator's own query, edges scope, RRF, limit 30.
    hits = 0
    probe = typed_top[:20]
    for n in probe:
        q = f"All information, activities, events, relationships, and background about {n.name}"
        facts = [e.fact or "" for e in store.search(gid, q, 30, "edges", "rrf").edges]
        first = norm(n.name).split(" ")[0] if norm(n.name) else ""
        if any(first and first in norm(f) for f in facts):
            hits += 1
    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "typed_nodes": len(typed),
        "top10_typed": [(n.name, [lab for lab in n.labels if lab != "Entity"], degree.get(n.uuid, 0)) for n in typed_top[:10]],
        "typed_names": [n.name for n in typed],
        "grounding_hit_rate": round(hits / max(1, len(probe)), 2),
        "grounding_probed": len(probe),
    }


def main() -> None:
    _, ontology = load()
    if MODE == "graphiti":
        from app.services.graph_store.graphiti_store import GraphitiGraphStore

        build(GraphitiGraphStore.shared(), ontology, Config.GRAPHITI_CHUNK_SIZE, Config.GRAPHITI_CHUNK_OVERLAP)
    elif MODE == "zep":
        from app.services.graph_store.zep_store import ZepGraphStore

        build(ZepGraphStore(Config.ZEP_API_KEY), capped(ontology), Config.DEFAULT_CHUNK_SIZE, Config.DEFAULT_CHUNK_OVERLAP)
    elif MODE == "measure-graphiti":
        from app.services.graph_store.graphiti_store import GraphitiGraphStore

        g = json.loads((DIR / "g3_graphiti.json").read_text(encoding="utf-8"))
        m = measure(GraphitiGraphStore.shared(), g["graph_id"])
        (DIR / "g3_graphiti_measure.json").write_text(json.dumps(m, indent=1, default=str), encoding="utf-8")
        print(f"graphiti: {m['nodes']} nodes, {m['edges']} edges, {m['typed_nodes']} typed, grounding {m['grounding_hit_rate']} of {m['grounding_probed']}")
        for row in m["top10_typed"]:
            print("   ", row)
    elif MODE == "compare":
        from app.services.graph_store.graphiti_store import GraphitiGraphStore
        from app.services.graph_store.zep_store import ZepGraphStore

        g = json.loads((DIR / "g3_graphiti.json").read_text(encoding="utf-8"))
        z = json.loads((DIR / "g3_zep.json").read_text(encoding="utf-8"))
        mg = measure(GraphitiGraphStore.shared(), g["graph_id"])
        mz = measure(ZepGraphStore(Config.ZEP_API_KEY), z["graph_id"])
        zep_top = [n for n, _l, _d in mz["top10_typed"]]
        missed = [n for n in zep_top if not any(same(n, x) for x in mg["typed_names"])]
        only_g = [n for n in mg["typed_names"] if not any(same(n, x) for x in mz["typed_names"])]
        ratio = mg["typed_nodes"] / max(1, mz["typed_nodes"])
        result = {
            "graphiti": {**g, **mg},
            "zep": {**z, **mz},
            "zep_top10_missed_by_graphiti": missed,
            "graphiti_only_typed": only_g[:40],
            "acceptance": {
                "actor_count_within_20pct": 0.8 <= ratio <= 1.2,  # the plan's rule, as written
                "actor_count_at_least_80pct": ratio >= 0.8,  # more actors is not a quality loss
                "actor_ratio_graphiti_over_zep": round(ratio, 2),
                "finds_every_zep_top10": not missed,
                "graphiti_grounding_ge_90pct": mg["grounding_hit_rate"] >= 0.9,
            },
        }
        (DIR / "g3_compare.json").write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
        print(json.dumps({k: v for k, v in result.items() if k not in ("graphiti", "zep")}, indent=1, default=str))
        for side in ("zep", "graphiti"):
            r = result[side]
            print(f"{side}: {r['nodes']} nodes, {r['edges']} edges, {r['typed_nodes']} typed, grounding {r['grounding_hit_rate']}, {r['total_s']}s")
            for row in r["top10_typed"]:
                print("   ", row)
    else:
        raise SystemExit("mode must be graphiti, zep or compare")


main()
