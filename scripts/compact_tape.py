#!/usr/bin/env python3
"""Lossless-for-replay tape compaction, original schema.

The golden demo tape is a time-indexed JSON array of entries
({t_ms, method, path, status, body}) recorded from a real run. A fresh
recording is huge (the Pharmacy First golden run was 633MB) because
long-polling and cursor-poll endpoints repeat the same body for the same
(method, path) key many times per second.

The in-browser replay (frontend/src/demo/tape.js) serves, per key, the
last snapshot with t_ms <= elapsed — so identical bodies for the same key
are replay-equivalent no matter how interleaved. This tool therefore drops
every repeated identical body per (method, path) key, keeping only the
FIRST occurrence. Query strings stay part of the path, so cursor entries
like /api/report/:id/agent-log?from_line=N are kept separately per cursor
value. Entries remain in the original format; schema_version, scenario,
duration_ms and replay semantics are unchanged.

Usage:
    python3 scripts/compact_tape.py <in> [out]

If [out] is omitted the input file is rewritten in place. Prints the
entries and size before -> after.

See docs/demo-mode-plan.md (tape/replay section) for the full workflow:
record fresh -> scrub -> compact -> replay-verify -> commit.
"""
import argparse
import json
import os
import sys


def compact(entries):
    """Return entries with the first occurrence of each distinct body per
    (method, path) key kept; all later repeats dropped."""
    seen = set()
    kept = []
    for e in entries:
        sig = json.dumps(e.get("body"), sort_keys=True, ensure_ascii=False)
        key = (e["method"], e["path"], sig)
        if key in seen:
            continue
        seen.add(key)
        kept.append(e)
    return kept


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="compact_tape.py",
        description=(
            "Deduplicate a recorded demo tape losslessly-for-replay: keeps the "
            "first occurrence of each identical body per (method, path) key, "
            "preserving the original tape schema."
        ),
        epilog=(
            "Replay-equivalence: resolve() serves the last snapshot with "
            "t_ms <= elapsed per key, so repeated identical bodies are "
            "interchangeable; only the first is kept."
        ),
    )
    parser.add_argument("in_path", metavar="<in>", help="input tape.json")
    parser.add_argument(
        "out_path",
        metavar="[out]",
        nargs="?",
        help="output path (default: overwrite <in> in place)",
    )
    args = parser.parse_args(argv)

    in_path = args.in_path
    out_path = args.out_path or in_path

    before_bytes = os.path.getsize(in_path)
    with open(in_path) as f:
        tape = json.load(f)
    entries = tape["entries"]
    n_before = len(entries)

    tape["entries"] = compact(entries)

    with open(out_path, "w") as f:
        json.dump(tape, f)
    after_bytes = os.path.getsize(out_path)

    print(
        f"entries {n_before} -> {len(tape['entries'])}"
        f" | {before_bytes / 1e6:.1f}MB -> {after_bytes / 1e6:.1f}MB"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
