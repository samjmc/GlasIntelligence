"""Quick check of the latest simulation config."""
import json
import os

base = "/app/backend/uploads/simulations"
dirs = sorted(
    [d for d in os.listdir(base) if d.startswith("sim_")],
    key=lambda d: os.path.getmtime(os.path.join(base, d)),
    reverse=True,
)

for d in dirs[:3]:
    path = os.path.join(base, d, "simulation_config.json")
    if not os.path.exists(path):
        continue
    c = json.load(open(path))
    req = c.get("simulation_requirement", "")
    agents = len(c.get("agent_configs", []))
    profiles = os.path.exists(os.path.join(base, d, "twitter_profiles.csv"))
    print(f"{d}: agents={agents}, has_requirement={bool(req)}, has_profiles={profiles}")
    if req:
        print(f"  requirement: {req[:150]}")
    print()
