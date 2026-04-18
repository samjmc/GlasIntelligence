"""Extract simulation actions from OASIS SQLite databases into JSON for visualization."""
import sqlite3
import json
import os

import sys

SIM_ID = sys.argv[1] if len(sys.argv) > 1 else "sim_1c08c314bad7"
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIM_DIR = os.path.join(_REPO_ROOT, "backend", "uploads", "simulations", SIM_ID)

def extract_platform(platform):
    db_path = os.path.join(SIM_DIR, f"{platform}_simulation.db")
    if not os.path.exists(db_path):
        return [], {}

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    cur = db.cursor()

    users = {}
    for row in cur.execute("SELECT * FROM user"):
        users[row["user_id"]] = dict(row)

    actions = []

    for row in cur.execute("SELECT * FROM post ORDER BY created_at"):
        r = dict(row)
        actions.append({
            "platform": platform,
            "action_type": "CREATE_POST" if r["original_post_id"] is None else "REPOST",
            "agent_id": r["user_id"],
            "agent_name": users.get(r["user_id"], {}).get("name", f"Agent_{r['user_id']}"),
            "content": r["content"] or "",
            "post_id": r["post_id"],
            "round": r["created_at"] if isinstance(r["created_at"], int) else 0,
            "reply_to_agent": None,
        })

    comment_count = cur.execute("SELECT COUNT(*) FROM comment").fetchone()[0]
    if comment_count > 0:
        cols = [c[1] for c in cur.execute("PRAGMA table_info(comment)").fetchall()]
        for row in cur.execute("SELECT * FROM comment ORDER BY created_at"):
            r = dict(row)
            parent_user = None
            if "post_id" in r and r["post_id"]:
                parent_post = cur.execute("SELECT user_id FROM post WHERE post_id=?", (r["post_id"],)).fetchone()
                if parent_post:
                    parent_user = parent_post["user_id"]
            actions.append({
                "platform": platform,
                "action_type": "CREATE_COMMENT",
                "agent_id": r["user_id"],
                "agent_name": users.get(r["user_id"], {}).get("name", f"Agent_{r['user_id']}"),
                "content": r.get("content", ""),
                "post_id": r.get("comment_id", 0),
                "round": r["created_at"] if isinstance(r["created_at"], int) else 0,
                "reply_to_agent": parent_user,
            })

    for row in cur.execute("SELECT * FROM like"):
        r = dict(row)
        post_author = None
        post = cur.execute("SELECT user_id FROM post WHERE post_id=?", (r["post_id"],)).fetchone()
        if post:
            post_author = post["user_id"]
        actions.append({
            "platform": platform,
            "action_type": "LIKE",
            "agent_id": r["user_id"],
            "agent_name": users.get(r["user_id"], {}).get("name", f"Agent_{r['user_id']}"),
            "content": "",
            "post_id": r["post_id"],
            "round": r["created_at"] if isinstance(r["created_at"], int) else 0,
            "reply_to_agent": post_author,
        })

    db.close()

    profiles = {}
    for uid, u in users.items():
        profiles[str(uid)] = {
            "realname": u["name"],
            "username": u.get("user_name", u["name"]),
            "entity_type": "Unknown",
            "profession": "",
            "bio": u.get("bio", ""),
        }

    return actions, profiles


if __name__ == "__main__":
    all_actions = []
    all_profiles = {}

    for platform in ["twitter", "reddit"]:
        actions, profiles = extract_platform(platform)
        all_actions.extend(actions)
        all_profiles.update(profiles)

    print(f"Extracted {len(all_actions)} actions, {len(all_profiles)} profiles")

    try:
        for a in all_actions:
            if isinstance(a.get("round"), str):
                a["round"] = 0
    except:
        pass

    out_dir = os.path.join(SIM_DIR)
    with open(os.path.join(out_dir, "all_actions.json"), "w", encoding="utf-8") as f:
        json.dump(all_actions, f, ensure_ascii=False, default=str)
    with open(os.path.join(out_dir, "all_profiles.json"), "w", encoding="utf-8") as f:
        json.dump(all_profiles, f, ensure_ascii=False, default=str)

    print(f"Saved to {out_dir}/all_actions.json and all_profiles.json")

    platform_counts = {}
    for a in all_actions:
        p = a["platform"]
        platform_counts[p] = platform_counts.get(p, 0) + 1
    print(f"By platform: {platform_counts}")

    type_counts = {}
    for a in all_actions:
        t = a["action_type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    print(f"By type: {type_counts}")
