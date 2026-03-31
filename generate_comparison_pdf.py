"""Generate comparison executive summary PDF."""
import markdown
import subprocess
import os
import sys
from datetime import datetime

CSS = """
@page { size: A4; margin: 2cm 2.5cm; }
body {
    font-family: 'Segoe UI', Calibri, Arial, sans-serif;
    font-size: 10.5pt; line-height: 1.6; color: #1a1a1a;
}
h1 {
    font-size: 20pt; color: #0b3d2e;
    border-bottom: 3px solid #0b3d2e; padding-bottom: 8px;
}
h2 {
    font-size: 14pt; color: #0b3d2e; margin-top: 24px;
    border-bottom: 1px solid #ccc; padding-bottom: 4px;
}
h3 { font-size: 11pt; color: #333; margin-top: 16px; }
blockquote {
    border-left: 4px solid #0b3d2e; margin: 10px 0;
    padding: 6px 14px; background: #f4f8f6; font-style: italic;
}
strong { color: #0b3d2e; }
hr { border: none; border-top: 2px solid #0b3d2e; margin: 20px 0; }
table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 9.5pt; }
th { background: #0b3d2e; color: white; padding: 7px 10px; text-align: left; }
td { padding: 7px 10px; border-bottom: 1px solid #ddd; vertical-align: top; }
tr:nth-child(even) td { background: #f9f9f9; }
ol, ul { padding-left: 24px; }
li { margin-bottom: 4px; }
.cover-page {
    page-break-after: always;
    display: flex; flex-direction: column;
    justify-content: center; align-items: center;
    min-height: 85vh; text-align: center;
}
.cover-logo {
    font-size: 28pt; color: #0b3d2e; font-weight: 800;
    letter-spacing: 3px; margin-bottom: 60px;
}
.cover-title {
    font-size: 30pt; color: #0b3d2e; font-weight: 700;
    margin-bottom: 12px; line-height: 1.2;
}
.cover-subtitle {
    font-size: 15pt; color: #555; margin-bottom: 40px;
}
.cover-divider {
    width: 120px; height: 4px; background: #0b3d2e; margin: 30px auto;
}
.cover-meta {
    font-size: 11pt; color: #777; line-height: 2;
}
em { font-size: 9pt; color: #888; }
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

if __name__ == "__main__":
    md_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "comparison_summary.md")
    output_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), "Glas_Intelligence_Scenario_Comparison.pdf")

    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    body_html = markdown.markdown(md_content, extensions=["tables", "fenced_code"])

    date_str = datetime.now().strftime("%B %Y")

    cover = f"""
<div class="cover-page">
    <div class="cover-logo">GLAS INTELLIGENCE</div>
    <div class="cover-divider"></div>
    <div class="cover-title">Scenario Comparison:<br/>Pharmacy First Payment Caps</div>
    <div class="cover-subtitle">Executive Summary &mdash; Two Counterfactual Policy Scenarios</div>
    <div class="cover-divider"></div>
    <div class="cover-meta">
        <div><strong>Prepared by:</strong> Glas Intelligence &mdash; AI Predictive Division</div>
        <div><strong>Date:</strong> {date_str}</div>
        <div><strong>Classification:</strong> Client Confidential</div>
        <div><strong>Methodology:</strong> Multi-Agent Social Simulation (Glas Intelligence/OASIS)</div>
    </div>
</div>
"""

    full_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>{CSS}</style>
</head><body>
{cover}
{body_html}
</body></html>"""

    html_path = output_path.replace(".pdf", ".html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(full_html)

    edge = find_edge()
    if not edge:
        print(f"Edge not found. HTML saved to: {html_path}")
        sys.exit(1)

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
