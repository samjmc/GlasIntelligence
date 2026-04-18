import json, sys
c = json.load(open(sys.argv[1]))
for a in c["agent_configs"]:
    hrs = a.get("active_hours", [])
    print(f"Agent {a['agent_id']}: activity={a.get('activity_level','?')}, hours={hrs[:10]}{'...' if len(hrs)>10 else ''}")
tc = c.get("time_config", {})
print(f"\nTime: {tc.get('minutes_per_round',30)}min/round, total={tc.get('total_simulation_hours',72)}h")
print(f"Peak hours: {tc.get('peak_hours', [])}")
print(f"Off-peak: {tc.get('off_peak_hours', [])}")
