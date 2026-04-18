"""Inspect simulation results for validation."""
import json, sys, os

sim_dir = sys.argv[1]

print("=== TWITTER ACTIONS ===")
actions_path = os.path.join(sim_dir, "twitter", "actions.jsonl")
if os.path.exists(actions_path):
    with open(actions_path) as f:
        for line in f:
            a = json.loads(line)
            at = a.get("action_type", "?")
            agent = a.get("agent_id", "?")
            rnd = a.get("round", "?")
            content = str(a.get("content", ""))[:120]
            if at.startswith("STATE_"):
                target = a.get("target_name", "?")
                delta = a.get("new_value", "?")
                cause = a.get("causing_tool", "?")
                print(f"  R{rnd} [{at}] target={target}, new_val={delta}, cause={cause}")
            elif at == "TOOL_CALL":
                tool = a.get("tool_name", "?")
                inp = str(a.get("tool_input", ""))[:80]
                print(f"  R{rnd} Agent {agent} [{at}] tool={tool}, input={inp}")
            else:
                print(f"  R{rnd} Agent {agent} [{at}] {content[:80]}")
else:
    print("  (no actions file)")

print("\n=== TOOL CALLS LOG ===")
tc_path = os.path.join(sim_dir, "tool_calls.jsonl")
if os.path.exists(tc_path):
    with open(tc_path) as f:
        for line in f:
            t = json.loads(line)
            print(f"  Agent {t.get('agent_id','?')} -> {t.get('tool_name','?')}({str(t.get('arguments',''))[:60]}) = {str(t.get('result',''))[:60]}")
else:
    print("  (no tool_calls.jsonl)")

print("\n=== EFFECT LOG ===")
eff_path = os.path.join(sim_dir, "effects.jsonl")
if os.path.exists(eff_path):
    with open(eff_path) as f:
        for line in f:
            e = json.loads(line)
            print(f"  R{e.get('round','?')} {e.get('effect_type','?')} target={e.get('target_name','?')} before={e.get('before','?')} after={e.get('after','?')} cause={e.get('causing_tool','?')}")
else:
    print("  (no effects.jsonl)")

print("\n=== ACTION TYPE COUNTS ===")
if os.path.exists(actions_path):
    counts = {}
    with open(actions_path) as f:
        for line in f:
            a = json.loads(line)
            at = a.get("action_type", "unknown")
            counts[at] = counts.get(at, 0) + 1
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")
