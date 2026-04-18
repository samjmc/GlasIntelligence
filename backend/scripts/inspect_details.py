"""Deep inspect of key actions."""
import json, sys, os

sim_dir = sys.argv[1]
actions_path = os.path.join(sim_dir, "twitter", "actions.jsonl")

print("=== TOOL_* and STATE_* ACTIONS (full JSON) ===")
with open(actions_path) as f:
    for line in f:
        a = json.loads(line)
        at = a.get("action_type", "")
        if at.startswith("TOOL_") or at.startswith("STATE_"):
            print(json.dumps(a, indent=2, default=str)[:600])
            print("---")

print("\n=== SAMPLE 'unknown' ACTIONS (first 3) ===")
count = 0
with open(actions_path) as f:
    for line in f:
        a = json.loads(line)
        at = a.get("action_type", "")
        if not at or at == "unknown":
            if count < 3:
                print(json.dumps(a, indent=2, default=str)[:300])
                print("---")
                count += 1

print(f"\n=== EFFECTS LOG SEARCH ===")
for root, dirs, files in os.walk(sim_dir):
    for fname in files:
        if "effect" in fname.lower():
            print(f"  Found: {os.path.join(root, fname)}")

for root, dirs, files in os.walk(sim_dir):
    for fname in files:
        if fname.endswith(".jsonl") or fname.endswith(".log"):
            print(f"  Log: {os.path.join(root, fname)}")
