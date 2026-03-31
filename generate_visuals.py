"""
Generate visualizations from Glas Intelligence simulation data.
Produces: sentiment arc, interaction heatmap, stakeholder network diagram.
"""
import json
import os
import sys
import math
from collections import defaultdict

try:
    import requests
except ImportError:
    print("Installing requests...")
    os.system(f"{sys.executable} -m pip install requests")
    import requests

API_BASE = "http://localhost:5001"

def fetch_simulation_data(sim_id):
    """Fetch simulation actions and metadata."""
    resp = requests.get(f"{API_BASE}/api/simulation/{sim_id}")
    sim_data = resp.json()["data"]
    
    actions_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", "uploads", "simulations", sim_id))
    
    actions = []
    profiles = {}
    
    all_actions_file = os.path.join(actions_dir, "all_actions.json")
    all_profiles_file = os.path.join(actions_dir, "all_profiles.json")
    
    if os.path.exists(all_actions_file):
        with open(all_actions_file, "r", encoding="utf-8") as f:
            actions = json.load(f)
        with open(all_profiles_file, "r", encoding="utf-8") as f:
            profiles = json.load(f)
    else:
        for platform in ["twitter", "reddit"]:
            actions_file = os.path.join(actions_dir, f"{platform}_actions.json")
            if os.path.exists(actions_file):
                with open(actions_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for a in data:
                            a["platform"] = platform
                        actions.extend(data)
        
        for platform in ["twitter", "reddit"]:
            profiles_file = os.path.join(actions_dir, f"{platform}_profiles.json")
            if os.path.exists(profiles_file):
                with open(profiles_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        profiles.update(data)
    
    return sim_data, actions, profiles


def generate_sentiment_svg(actions, output_path):
    """Generate a sentiment arc SVG showing sentiment over simulation posts."""
    round_sentiments = defaultdict(list)
    
    content_actions = [a for a in actions if a.get("content")]
    
    batch_size = max(1, len(content_actions) // 30)
    for i, action in enumerate(content_actions):
        round_num = i // batch_size
        content = action.get("content", action.get("text", ""))
        
        positive_words = ["support", "agree", "good", "great", "benefit", "positive", "funding",
                         "welcome", "pleased", "progress", "uplift", "investment", "hope"]
        negative_words = ["crisis", "cut", "fail", "loss", "closure", "threat", "oppose",
                         "concern", "fear", "angry", "frustrated", "underfunded", "shortage",
                         "cap", "unprofitable", "understaffed", "exodus", "rationing"]
        
        content_lower = content.lower()
        pos = sum(1 for w in positive_words if w in content_lower)
        neg = sum(1 for w in negative_words if w in content_lower)
        total = pos + neg
        if total > 0:
            sentiment = (pos - neg) / total
        else:
            sentiment = 0
        
        round_sentiments[round_num].append(sentiment)
    
    avg_sentiments = {}
    for r, sents in sorted(round_sentiments.items()):
        avg_sentiments[r] = sum(sents) / len(sents)
    
    if not avg_sentiments:
        return
    
    width, height = 800, 350
    margin_left, margin_right, margin_top, margin_bottom = 70, 30, 40, 60
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    
    rounds = sorted(avg_sentiments.keys())
    max_round = max(rounds) if rounds else 1
    
    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'style="font-family:Segoe UI,Arial,sans-serif;background:white">',
        f'<text x="{width//2}" y="24" text-anchor="middle" font-size="16" font-weight="bold" fill="#0b3d2e">Sentiment Arc Over Simulation Rounds</text>',
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{height-margin_bottom}" stroke="#ccc" stroke-width="1"/>',
        f'<line x1="{margin_left}" y1="{margin_top + plot_h//2}" x2="{width-margin_right}" y2="{margin_top + plot_h//2}" stroke="#aaa" stroke-width="1" stroke-dasharray="4"/>',
        f'<line x1="{margin_left}" y1="{height-margin_bottom}" x2="{width-margin_right}" y2="{height-margin_bottom}" stroke="#ccc" stroke-width="1"/>',
    ]
    
    for label, val in [("Positive", -1), ("Neutral", 0), ("Negative", 1)]:
        y = margin_top + int((val + 1) / 2 * plot_h)
        svg_lines.append(f'<text x="{margin_left-8}" y="{y+4}" text-anchor="end" font-size="11" fill="#666">{label}</text>')
    
    for i in range(0, max_round + 1, max(1, max_round // 6)):
        x = margin_left + int(i / max(max_round, 1) * plot_w)
        svg_lines.append(f'<text x="{x}" y="{height-margin_bottom+18}" text-anchor="middle" font-size="10" fill="#666">{i}</text>')
    
    svg_lines.append(f'<text x="{width//2}" y="{height-8}" text-anchor="middle" font-size="12" fill="#666">Simulation Round</text>')
    
    points = []
    for r in rounds:
        x = margin_left + int(r / max(max_round, 1) * plot_w)
        y = margin_top + int((-avg_sentiments[r] + 1) / 2 * plot_h)
        points.append(f"{x},{y}")
    
    area_points = points.copy()
    area_points.append(f"{margin_left + int(rounds[-1] / max(max_round, 1) * plot_w)},{margin_top + plot_h//2}")
    area_points.insert(0, f"{margin_left + int(rounds[0] / max(max_round, 1) * plot_w)},{margin_top + plot_h//2}")
    
    svg_lines.append(f'<polygon points="{" ".join(area_points)}" fill="#0b3d2e" fill-opacity="0.1"/>')
    svg_lines.append(f'<polyline points="{" ".join(points)}" fill="none" stroke="#0b3d2e" stroke-width="2.5"/>')
    
    for r in rounds[::max(1, len(rounds)//12)]:
        x = margin_left + int(r / max(max_round, 1) * plot_w)
        y = margin_top + int((-avg_sentiments[r] + 1) / 2 * plot_h)
        svg_lines.append(f'<circle cx="{x}" cy="{y}" r="3.5" fill="#0b3d2e"/>')
    
    svg_lines.append('</svg>')
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(svg_lines))
    print(f"Created: {output_path}")


def generate_heatmap_svg(actions, profiles, output_path):
    """Generate an interaction heatmap SVG showing which agents interact most."""
    interaction_counts = defaultdict(lambda: defaultdict(int))
    agent_names = {}
    
    for action in actions:
        agent_id = str(action.get("agent_id", ""))
        reply_to = str(action.get("reply_to_agent", action.get("parent_agent_id", "")))
        
        if agent_id and agent_id in profiles:
            name = profiles[agent_id].get("realname", profiles[agent_id].get("username", f"Agent {agent_id}"))
            agent_names[agent_id] = name[:20]
        
        if reply_to and reply_to != "" and reply_to != "None" and reply_to in profiles:
            name = profiles[reply_to].get("realname", profiles[reply_to].get("username", f"Agent {reply_to}"))
            agent_names[reply_to] = name[:20]
            interaction_counts[agent_id][reply_to] += 1
    
    all_agents = sorted(set(list(interaction_counts.keys()) + 
                           [a for d in interaction_counts.values() for a in d.keys()]))
    
    top_agents = sorted(all_agents, 
                       key=lambda a: sum(interaction_counts.get(a, {}).values()) + 
                                    sum(d.get(a, 0) for d in interaction_counts.values()),
                       reverse=True)[:15]
    
    if len(top_agents) < 3:
        print(f"Not enough interaction data for heatmap (found {len(top_agents)} agents)")
        return
    
    n = len(top_agents)
    cell_size = 40
    label_space = 160
    width = label_space + n * cell_size + 30
    height = label_space + n * cell_size + 60
    
    max_val = 1
    for a1 in top_agents:
        for a2 in top_agents:
            v = interaction_counts.get(a1, {}).get(a2, 0)
            if v > max_val:
                max_val = v
    
    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'style="font-family:Segoe UI,Arial,sans-serif;background:white">',
        f'<text x="{width//2}" y="24" text-anchor="middle" font-size="16" font-weight="bold" fill="#0b3d2e">Agent Interaction Heatmap</text>',
    ]
    
    for i, agent in enumerate(top_agents):
        name = agent_names.get(agent, f"Agent {agent}")
        x = label_space - 8
        y = 45 + i * cell_size + cell_size // 2 + 4
        svg_lines.append(f'<text x="{x}" y="{y}" text-anchor="end" font-size="9" fill="#333">{name}</text>')
        
        tx = label_space + i * cell_size + cell_size // 2
        ty = 40
        svg_lines.append(f'<text x="{tx}" y="{ty}" text-anchor="end" font-size="9" fill="#333" '
                        f'transform="rotate(-45 {tx} {ty})">{name}</text>')
    
    for i, a1 in enumerate(top_agents):
        for j, a2 in enumerate(top_agents):
            v = interaction_counts.get(a1, {}).get(a2, 0)
            intensity = v / max_val if max_val > 0 else 0
            
            r = int(255 - intensity * (255 - 11))
            g = int(255 - intensity * (255 - 61))
            b = int(255 - intensity * (255 - 46))
            
            x = label_space + j * cell_size
            y = 45 + i * cell_size
            
            svg_lines.append(f'<rect x="{x}" y="{y}" width="{cell_size}" height="{cell_size}" '
                           f'fill="rgb({r},{g},{b})" stroke="white" stroke-width="1"/>')
            if v > 0:
                svg_lines.append(f'<text x="{x + cell_size//2}" y="{y + cell_size//2 + 4}" '
                               f'text-anchor="middle" font-size="9" fill="{"white" if intensity > 0.5 else "#333"}">{v}</text>')
    
    svg_lines.append('</svg>')
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(svg_lines))
    print(f"Created: {output_path}")


def generate_network_svg(actions, profiles, output_path):
    """Generate a stakeholder network diagram SVG."""
    entity_types = defaultdict(set)
    interactions = defaultdict(int)
    activity = defaultdict(int)
    
    for action in actions:
        agent_id = str(action.get("agent_id", ""))
        if agent_id in profiles:
            p = profiles[agent_id]
            etype = p.get("entity_type", p.get("profession", "Unknown"))
            name = p.get("realname", p.get("username", f"Agent {agent_id}"))
            entity_types[etype].add(name[:25])
            activity[name[:25]] += 1
        
        reply_to = str(action.get("reply_to_agent", action.get("parent_agent_id", "")))
        if reply_to and reply_to != "" and reply_to != "None" and reply_to in profiles:
            p2 = profiles[reply_to]
            name1 = profiles[agent_id].get("realname", f"A{agent_id}")[:25] if agent_id in profiles else ""
            name2 = p2.get("realname", p2.get("username", f"A{reply_to}"))[:25]
            if name1 and name2:
                key = tuple(sorted([name1, name2]))
                interactions[key] += 1
    
    top_actors = sorted(activity.items(), key=lambda x: x[1], reverse=True)[:20]
    top_names = {name for name, _ in top_actors}
    
    if len(top_names) < 3:
        print("Not enough data for network diagram")
        return
    
    width, height = 800, 600
    cx, cy = width // 2, height // 2
    radius = 220
    
    type_colors = {
        "GovernmentAgency": "#c0392b", "GovernmentOfficial": "#e74c3c",
        "PharmacyAssociation": "#2980b9", "PharmacyChain": "#3498db",
        "IndependentPharmacy": "#27ae60", "Pharmacist": "#2ecc71",
        "MediaOutlet": "#f39c12", "Patient": "#9b59b6",
        "Person": "#95a5a6", "Organization": "#7f8c8d",
    }
    
    names = list(top_names)
    positions = {}
    for i, name in enumerate(names):
        angle = 2 * math.pi * i / len(names) - math.pi / 2
        size_factor = min(1, activity.get(name, 1) / max(a for _, a in top_actors)) * 0.3 + 0.7
        r = radius * size_factor
        positions[name] = (cx + int(r * math.cos(angle)), cy + int(r * math.sin(angle)))
    
    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'style="font-family:Segoe UI,Arial,sans-serif;background:white">',
        f'<text x="{width//2}" y="28" text-anchor="middle" font-size="18" font-weight="bold" fill="#0b3d2e">Stakeholder Interaction Network</text>',
    ]
    
    for (n1, n2), count in sorted(interactions.items(), key=lambda x: x[1], reverse=True):
        if n1 in positions and n2 in positions:
            x1, y1 = positions[n1]
            x2, y2 = positions[n2]
            opacity = min(0.8, 0.1 + count * 0.05)
            stroke_w = min(4, 0.5 + count * 0.3)
            svg_lines.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                           f'stroke="#0b3d2e" stroke-width="{stroke_w:.1f}" stroke-opacity="{opacity:.2f}"/>')
    
    name_to_type = {}
    for etype, enames in entity_types.items():
        for n in enames:
            if n in top_names:
                name_to_type[n] = etype
    
    for name, (x, y) in positions.items():
        act = activity.get(name, 1)
        r = max(12, min(30, 8 + act * 0.5))
        color = type_colors.get(name_to_type.get(name, ""), "#7f8c8d")
        
        svg_lines.append(f'<circle cx="{x}" cy="{y}" r="{r:.0f}" fill="{color}" stroke="white" stroke-width="2"/>')
        
        label = name if len(name) <= 18 else name[:16] + "..."
        svg_lines.append(f'<text x="{x}" y="{y + r + 14}" text-anchor="middle" font-size="9" fill="#333">{label}</text>')
    
    legend_x, legend_y = 20, height - 120
    svg_lines.append(f'<text x="{legend_x}" y="{legend_y - 10}" font-size="11" font-weight="bold" fill="#333">Entity Types</text>')
    for i, (etype, color) in enumerate(list(type_colors.items())[:6]):
        ly = legend_y + i * 16
        svg_lines.append(f'<circle cx="{legend_x + 6}" cy="{ly}" r="5" fill="{color}"/>')
        svg_lines.append(f'<text x="{legend_x + 16}" y="{ly + 4}" font-size="9" fill="#555">{etype}</text>')
    
    svg_lines.append('</svg>')
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(svg_lines))
    print(f"Created: {output_path}")


def generate_activity_svg(actions, output_path):
    """Generate activity volume per batch as a bar chart."""
    round_counts = defaultdict(int)
    batch_size = max(1, len(actions) // 30)
    for i, action in enumerate(actions):
        r = i // batch_size
        round_counts[r] += 1
    
    if not round_counts:
        return
    
    width, height = 800, 300
    margin_left, margin_right, margin_top, margin_bottom = 60, 20, 40, 50
    plot_w = width - margin_left - margin_right
    plot_h = height - margin_top - margin_bottom
    
    rounds = sorted(round_counts.keys())
    max_round = max(rounds) if rounds else 1
    max_count = max(round_counts.values()) if round_counts else 1
    
    bar_width = max(2, plot_w // (max_round + 1) - 1)
    
    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'style="font-family:Segoe UI,Arial,sans-serif;background:white">',
        f'<text x="{width//2}" y="24" text-anchor="middle" font-size="16" font-weight="bold" fill="#0b3d2e">Simulation Activity Volume by Round</text>',
        f'<line x1="{margin_left}" y1="{height-margin_bottom}" x2="{width-margin_right}" y2="{height-margin_bottom}" stroke="#ccc"/>',
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{height-margin_bottom}" stroke="#ccc"/>',
    ]
    
    for r in rounds:
        x = margin_left + int(r / max(max_round, 1) * plot_w)
        bar_h = int(round_counts[r] / max_count * plot_h)
        y = height - margin_bottom - bar_h
        svg_lines.append(f'<rect x="{x}" y="{y}" width="{bar_width}" height="{bar_h}" fill="#0b3d2e" fill-opacity="0.75"/>')
    
    svg_lines.append(f'<text x="{width//2}" y="{height-8}" text-anchor="middle" font-size="11" fill="#666">Round</text>')
    svg_lines.append(f'<text x="15" y="{height//2}" text-anchor="middle" font-size="11" fill="#666" transform="rotate(-90 15 {height//2})">Actions</text>')
    
    svg_lines.append('</svg>')
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(svg_lines))
    print(f"Created: {output_path}")


if __name__ == "__main__":
    sim_id = sys.argv[1] if len(sys.argv) > 1 else "sim_1c08c314bad7"
    output_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "visuals")
    
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Fetching data for {sim_id}...")
    sim_data, actions, profiles = fetch_simulation_data(sim_id)
    print(f"Found {len(actions)} actions, {len(profiles)} profiles")
    
    if not actions:
        print("No actions found. Check simulation status.")
        sys.exit(1)
    
    generate_sentiment_svg(actions, os.path.join(output_dir, "sentiment_arc.svg"))
    generate_activity_svg(actions, os.path.join(output_dir, "activity_volume.svg"))
    generate_heatmap_svg(actions, profiles, os.path.join(output_dir, "interaction_heatmap.svg"))
    generate_network_svg(actions, profiles, os.path.join(output_dir, "stakeholder_network.svg"))
    
    print(f"\nAll visualizations saved to: {output_dir}")
