#!/usr/bin/env python3
"""One-off: clear run_state.json stuck on 'running' when no worker owns the process."""
import json
import glob
import os
from datetime import datetime, timezone

BASE = os.environ.get("GLAS_SIMULATIONS_DIR", "/opt/glas/backend/uploads/simulations")


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    for d in sorted(glob.glob(os.path.join(BASE, "sim_*"))):
        rs = os.path.join(d, "run_state.json")
        st = os.path.join(d, "state.json")
        if not os.path.isfile(rs):
            continue
        try:
            with open(rs, encoding="utf-8") as f:
                r = json.load(f)
        except json.JSONDecodeError as e:
            print(f"{os.path.basename(d)} SKIP corrupt run_state.json: {e}")
            continue
        if r.get("runner_status") != "running":
            continue
        sid = os.path.basename(d)
        sim_completed = False
        if os.path.isfile(st):
            with open(st, encoding="utf-8") as f:
                s = json.load(f)
            sim_completed = s.get("status") == "completed"
        if sim_completed:
            r["runner_status"] = "completed"
            r["twitter_running"] = False
            r["reddit_running"] = False
            r["completed_at"] = r.get("completed_at") or now
            print(f"{sid} run_state -> completed (state.json completed)")
        else:
            r["runner_status"] = "stopped"
            r["twitter_running"] = False
            r["reddit_running"] = False
            r["completed_at"] = now
            msg = "Cleared stale running (no live worker process)"
            r["error"] = f"{r['error']}; {msg}" if r.get("error") else msg
            print(f"{sid} run_state -> stopped")
        r["updated_at"] = now
        with open(rs, "w", encoding="utf-8") as f:
            json.dump(r, f, indent=2, ensure_ascii=False)
    print("done")


if __name__ == "__main__":
    main()
