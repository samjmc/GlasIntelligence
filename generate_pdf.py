"""
Generate a polished, branded PDF report from Glas Intelligence simulation output.
Uses Microsoft Edge headless for PDF rendering.
"""
import markdown
import subprocess
import os
import sys
import json
import base64
from datetime import datetime

BRAND_COLOR = "#0b3d2e"
ACCENT_COLOR = "#e8f5e9"

CSS = """
@page { size: A4; margin: 2cm 2.5cm; }
body {
    font-family: 'Segoe UI', Calibri, Arial, sans-serif;
    font-size: 11pt; line-height: 1.65; color: #1a1a1a;
    max-width: 100%; counter-reset: page;
}
h1 {
    font-size: 20pt; color: #0b3d2e;
    border-bottom: 3px solid #0b3d2e; padding-bottom: 8px; margin-top: 0;
}
h2 {
    font-size: 15pt; color: #0b3d2e; margin-top: 28px;
    border-bottom: 1px solid #ccc; padding-bottom: 4px;
}
h3 { font-size: 12pt; color: #333; margin-top: 20px; }
blockquote {
    border-left: 4px solid #0b3d2e; margin: 12px 0;
    padding: 8px 16px; background: #f4f8f6; font-style: italic; color: #333;
}
blockquote p { margin: 4px 0; }
strong { color: #0b3d2e; }
hr { border: none; border-top: 2px solid #0b3d2e; margin: 24px 0; }
table { width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 10pt; }
th { background: #0b3d2e; color: white; padding: 8px 12px; text-align: left; }
td { padding: 8px 12px; border-bottom: 1px solid #ddd; vertical-align: top; }
tr:nth-child(even) td { background: #f9f9f9; }
code, pre {
    background: #f0f0f0; font-family: 'Cascadia Code', Consolas, monospace;
    font-size: 9pt; padding: 8px 12px; border-radius: 4px;
    display: block; white-space: pre-wrap; margin: 12px 0;
}
.cover-page {
    page-break-after: always;
    display: flex; flex-direction: column;
    justify-content: center; align-items: center;
    min-height: 85vh; text-align: center;
}
.cover-title {
    font-size: 32pt; color: #0b3d2e; font-weight: 700;
    margin-bottom: 12px; line-height: 1.2;
}
.cover-subtitle {
    font-size: 16pt; color: #555; margin-bottom: 40px;
}
.cover-meta {
    font-size: 11pt; color: #777; line-height: 2;
}
.cover-logo {
    font-size: 28pt; color: #0b3d2e; font-weight: 800;
    letter-spacing: 3px; margin-bottom: 60px;
}
.cover-divider {
    width: 120px; height: 4px; background: #0b3d2e; margin: 30px auto;
}
.methodology-box {
    background: #f4f8f6; border: 1px solid #0b3d2e; border-radius: 8px;
    padding: 20px; margin: 20px 0;
}
.risk-matrix { page-break-inside: avoid; }
.risk-high { background: #fbe9e7 !important; }
.risk-medium { background: #fff8e1 !important; }
.risk-low { background: #e8f5e9 !important; }
.metric-grid {
    display: grid; grid-template-columns: repeat(4, 1fr);
    gap: 12px; margin: 20px 0;
}
.metric-card {
    background: #f4f8f6; border-radius: 8px; padding: 16px;
    text-align: center; border: 1px solid #ddd;
}
.metric-value {
    font-size: 24pt; font-weight: 700; color: #0b3d2e;
}
.metric-label {
    font-size: 9pt; color: #666; margin-top: 4px;
}
.visual-container {
    text-align: center; margin: 20px 0; page-break-inside: avoid;
}
.visual-container img {
    max-width: 100%; height: auto;
}
.disclaimer {
    font-size: 8pt; color: #999; border-top: 1px solid #ddd;
    padding-top: 12px; margin-top: 40px;
}
"""

EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_edge():
    for p in EDGE_PATHS:
        if os.path.exists(p):
            return p
    return None


def svg_to_data_uri(svg_path):
    """Convert SVG file to data URI for embedding in HTML."""
    if not os.path.exists(svg_path):
        return None
    with open(svg_path, "r", encoding="utf-8") as f:
        svg_content = f.read()
    encoded = base64.b64encode(svg_content.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def generate_cover_page(title, subtitle, scenario, date_str):
    return f"""
<div class="cover-page">
    <div class="cover-logo">GLAS INTELLIGENCE</div>
    <div class="cover-divider"></div>
    <div class="cover-title">{title}</div>
    <div class="cover-subtitle">{subtitle}</div>
    <div class="cover-divider"></div>
    <div class="cover-meta">
        <div><strong>Scenario:</strong> {scenario}</div>
        <div><strong>Prepared by:</strong> Glas Intelligence &mdash; AI Predictive Division</div>
        <div><strong>Date:</strong> {date_str}</div>
        <div><strong>Classification:</strong> Client Confidential</div>
        <div><strong>Methodology:</strong> Multi-Agent Social Simulation (Glas Intelligence/OASIS)</div>
    </div>
</div>
"""


def generate_methodology_section():
    return """
<h2>Methodology &amp; Transparency Disclosure</h2>
<div class="methodology-box">
<h3>How This Report Was Generated</h3>
<p>This predictive analysis was produced using <strong>Glas Intelligence</strong>, a multi-agent social simulation platform developed for anticipatory intelligence.</p>

<p><strong>Process:</strong></p>
<ol>
<li><strong>Knowledge Ingestion:</strong> Official policy documents, financial data, and stakeholder positions were loaded into a knowledge graph (Zep Cloud GraphRAG).</li>
<li><strong>Entity Extraction:</strong> Key stakeholders were automatically identified and profiled from source documents.</li>
<li><strong>Persona Generation:</strong> Each stakeholder was given a detailed AI persona reflecting their known positions, communication style, and institutional constraints.</li>
<li><strong>Social Simulation:</strong> Agents interacted across simulated Twitter and Reddit platforms over 120 rounds using the OASIS engine, responding to each other and to the policy scenario.</li>
<li><strong>Report Generation:</strong> An AI analyst reviewed all simulation data, agent interactions, and emergent patterns to produce this report.</li>
</ol>

<p><strong>Limitations:</strong></p>
<ul>
<li>Simulated behaviours are predictions, not certainties. Real-world outcomes depend on factors not captured in the model.</li>
<li>Agent personas are derived from publicly available information and may not reflect private strategies.</li>
<li>The simulation does not account for exogenous shocks (e.g., pandemic, election results) unless explicitly modelled.</li>
</ul>

<p><strong>Model:</strong> DeepSeek Chat (deepseek-chat) via OpenAI-compatible API<br/>
<strong>Knowledge Graph:</strong> Zep Cloud (GraphRAG)<br/>
<strong>Simulation Engine:</strong> OASIS (camel-ai) parallel Twitter+Reddit</p>
</div>
"""


def generate_risk_matrix(risks=None):
    if risks is None:
        risks = [
            ("Pharmacy closures in underserved areas", "High", "High", "6-12 months",
             "Cap mechanism makes rural pharmacies financially unviable"),
            ("Workforce exodus to GP/hospital roles", "High", "Medium", "3-6 months",
             "Cap frustration accelerates existing recruitment crisis"),
            ("Patient access rationing (informal)", "Medium", "High", "Immediate",
             "Pharmacies limit PFS consultations above cap threshold"),
            ("Political escalation / media campaign", "Medium", "Medium", "3-6 months",
             "CPE/PDA mobilise coordinated media pressure"),
            ("Contract negotiation breakdown", "Low", "High", "6-12 months",
             "Parties fail to agree 2026/27 CPCF terms"),
            ("Chain pharmacy service withdrawal", "Medium", "Medium", "6-12 months",
             "Major chains reduce PFS delivery in unprofitable stores"),
        ]
    
    html = """<div class="risk-matrix">
<h2>Risk Matrix</h2>
<table>
<tr><th>Risk</th><th>Likelihood</th><th>Impact</th><th>Timeline</th><th>Rationale</th></tr>
"""
    for risk, likelihood, impact, timeline, rationale in risks:
        css_class = ""
        if likelihood == "High" or impact == "High":
            css_class = "risk-high"
        elif likelihood == "Medium":
            css_class = "risk-medium"
        else:
            css_class = "risk-low"
        html += f'<tr class="{css_class}"><td><strong>{risk}</strong></td><td>{likelihood}</td><td>{impact}</td><td>{timeline}</td><td>{rationale}</td></tr>\n'
    
    html += "</table></div>"
    return html


def generate_metrics_section(sim_data, actions):
    """Generate key metrics cards from simulation data."""
    total_actions = len(actions)
    rounds = sim_data.get("current_round", 0)
    entities = sim_data.get("entities_count", 0)
    
    platforms = set(a.get("platform", "") for a in actions)
    platform_str = " + ".join(p.capitalize() for p in platforms if p)
    
    return f"""
<div class="metric-grid">
    <div class="metric-card">
        <div class="metric-value">{entities}</div>
        <div class="metric-label">Stakeholder Agents</div>
    </div>
    <div class="metric-card">
        <div class="metric-value">{rounds}</div>
        <div class="metric-label">Simulation Rounds</div>
    </div>
    <div class="metric-card">
        <div class="metric-value">{total_actions:,}</div>
        <div class="metric-label">Total Actions</div>
    </div>
    <div class="metric-card">
        <div class="metric-value">{platform_str or "Twitter + Reddit"}</div>
        <div class="metric-label">Platforms Simulated</div>
    </div>
</div>
"""


def generate_visuals_section(visuals_dir):
    """Embed SVG visualizations into the report."""
    visuals = [
        ("sentiment_arc.svg", "Sentiment Arc Over Simulation Rounds"),
        ("activity_volume.svg", "Activity Volume by Round"),
        ("stakeholder_network.svg", "Stakeholder Interaction Network"),
        ("interaction_heatmap.svg", "Agent Interaction Heatmap"),
    ]
    
    html = "<h2>Data Visualizations</h2>\n"
    for filename, caption in visuals:
        path = os.path.join(visuals_dir, filename)
        data_uri = svg_to_data_uri(path)
        if data_uri:
            html += f"""
<div class="visual-container">
    <img src="{data_uri}" alt="{caption}"/>
    <p style="font-size:9pt;color:#666;margin-top:4px;">{caption}</p>
</div>
"""
    return html


def build_full_report(report_md, sim_data, actions, visuals_dir, output_path,
                      cover_title=None, cover_subtitle=None, custom_risks=None):
    """Build the complete branded PDF."""
    date_str = datetime.now().strftime("%B %Y")
    scenario = sim_data.get("simulation_requirement", "UK Pharmacy First Payment Caps")
    if len(scenario) > 150:
        scenario = scenario[:147] + "..."
    
    report_html = markdown.markdown(report_md, extensions=["tables", "fenced_code"])
    
    cover = generate_cover_page(
        title=cover_title or "Pharmacy First Payment Caps:<br/>Predictive Stakeholder Analysis",
        subtitle=cover_subtitle or "A Multi-Agent Simulation of UK Pharmacy Sector Reactions",
        scenario=scenario,
        date_str=date_str
    )
    
    metrics = generate_metrics_section(sim_data, actions)
    methodology = generate_methodology_section()
    risk_matrix = generate_risk_matrix(custom_risks)
    visuals = generate_visuals_section(visuals_dir)
    
    disclaimer = """
<div class="disclaimer">
<strong>Disclaimer:</strong> This report was generated using AI-powered multi-agent social simulation. 
Predictions represent plausible scenarios based on available data, not certainties. 
Glas Intelligence accepts no liability for decisions made based on this analysis. 
All stakeholder quotes are AI-generated simulations of likely positions, not actual statements.
&copy; Glas Intelligence 2026. All rights reserved.
</div>
"""
    
    full_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>{CSS}</style>
</head><body>
{cover}
<h2>Executive Summary &amp; Key Metrics</h2>
{metrics}
{report_html}
{visuals}
{risk_matrix}
{methodology}
{disclaimer}
</body></html>"""
    
    html_path = output_path.replace(".pdf", ".html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    
    edge = find_edge()
    if not edge:
        print(f"Edge not found. HTML saved to: {html_path}")
        return
    
    file_url = "file:///" + os.path.abspath(html_path).replace("\\", "/")
    pdf_abs = os.path.abspath(output_path)
    
    subprocess.run([
        edge, "--headless", "--disable-gpu",
        f"--print-to-pdf={pdf_abs}",
        "--no-pdf-header-footer",
        file_url,
    ], capture_output=True, timeout=30)
    
    if os.path.exists(pdf_abs):
        size_kb = os.path.getsize(pdf_abs) / 1024
        print(f"Created: {output_path} ({size_kb:.0f} KB)")
    else:
        print(f"PDF creation failed. HTML available at: {html_path}")


if __name__ == "__main__":
    import requests
    
    sim_id = sys.argv[1] if len(sys.argv) > 1 else "sim_1c08c314bad7"
    report_md_path = sys.argv[2] if len(sys.argv) > 2 else None
    visuals_dir = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(__file__), "visuals")
    output_path = sys.argv[4] if len(sys.argv) > 4 else os.path.join(os.path.dirname(__file__), "Glas_Intelligence_Predictive_Report.pdf")
    cover_title = sys.argv[5] if len(sys.argv) > 5 else None
    cover_subtitle = sys.argv[6] if len(sys.argv) > 6 else None
    
    resp = requests.get(f"http://localhost:5001/api/simulation/{sim_id}")
    sim_data = resp.json()["data"]
    
    actions_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "backend", "uploads", "simulations", sim_id))
    
    actions = []
    all_actions_file = os.path.join(actions_dir, "all_actions.json")
    if os.path.exists(all_actions_file):
        with open(all_actions_file, "r", encoding="utf-8") as f:
            actions = json.load(f)
    else:
        for platform in ["twitter", "reddit"]:
            af = os.path.join(actions_dir, f"{platform}_actions.json")
            if os.path.exists(af):
                with open(af, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        actions.extend(data)
    
    if report_md_path and os.path.exists(report_md_path):
        with open(report_md_path, "r", encoding="utf-8") as f:
            report_md = f.read()
    else:
        report_md = "# Report content will be inserted here\n\nWaiting for report generation..."
    
    scenario_flag = sys.argv[7] if len(sys.argv) > 7 else "1"
    custom_risks = None
    if scenario_flag == "2":
        custom_risks = [
            ("CPCF budget exhaustion before year-end", "High", "High", "6-9 months",
             "Uncapped payments accelerate spending against fixed £3.073bn envelope"),
            ("Retrospective payment clawback", "Medium", "High", "9-12 months",
             "NHS England forced to reduce payments retroactively if budget runs out"),
            ("Reintroduction of modified caps", "Medium", "High", "6-12 months",
             "Political backlash if government reverses the uncapping decision"),
            ("Chain pharmacies capturing disproportionate share", "High", "Medium", "3-6 months",
             "Volume-driven inequality widens gap between chains and independents"),
            ("Workforce crisis persists despite improved morale", "Medium", "Medium", "6-12 months",
             "Flat CPCF prevents workforce investment; attrition slows but continues"),
            ("Treasury fiscal pressure on DHSC", "Medium", "High", "6-12 months",
             "Uncapped model conflicts with broader NHS spending controls"),
        ]

    build_full_report(report_md, sim_data, actions, visuals_dir, output_path,
                     cover_title=cover_title, cover_subtitle=cover_subtitle,
                     custom_risks=custom_risks)
