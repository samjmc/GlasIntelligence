#!/usr/bin/env python3
"""Strip quantitative-noise nodes from recorded demo tapes.

Applies the same filter the live API uses (app.services.graph_noise_filter)
to every /api/graph/data/:id response in a tape, so recorded graphs match
what the live pipeline now serves. Run on a COPY; the tool refuses to
overwrite in place.

Usage:
    python3 scripts/filter_graph_noise.py <tape-in.json> <tape-out.json>
"""

import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend"))

from app.services.graph_noise_filter import filter_quant_noise  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: filter_graph_noise.py <tape-in.json> <tape-out.json>", file=sys.stderr)
        return 2
    in_path, out_path = sys.argv[1], sys.argv[2]
    if os.path.abspath(in_path) == os.path.abspath(out_path):
        print("error: output must differ from input (run on a copy)", file=sys.stderr)
        return 2

    tape = json.load(open(in_path))
    removed_nodes = 0
    removed_edges = 0
    for entry in tape["entries"]:
        data = entry.get("body", {}).get("data", {})
        if not isinstance(data, dict) or "nodes" not in data or "edges" not in data:
            continue
        nodes, edges = data.get("nodes") or [], data.get("edges") or []
        kept_nodes, kept_edges = filter_quant_noise(nodes, edges)
        if len(kept_nodes) != len(nodes):
            removed_nodes += len(nodes) - len(kept_nodes)
            removed_edges += len(edges) - len(kept_edges)
            data["nodes"] = kept_nodes
            data["edges"] = kept_edges
            data["node_count"] = len(kept_nodes)
            data["edge_count"] = len(kept_edges)

    json.dump(tape, open(out_path, "w"))
    print(f"removed {removed_nodes} noise nodes, {removed_edges} dangling edges")
    print(f"entries {len(tape['entries'])} preserved; wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
