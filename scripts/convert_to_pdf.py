import markdown
import subprocess
import os
import time

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
REPORTS_DIR = os.path.join(REPO_ROOT, "docs", "reports")

CSS = """
@page { size: A4; margin: 2cm 2.5cm; }
body {
    font-family: 'Segoe UI', Calibri, Arial, sans-serif;
    font-size: 11pt; line-height: 1.65; color: #1a1a1a;
    max-width: 100%;
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

def md_to_pdf(md_path, pdf_path):
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    html_body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    html_path = md_path.replace(".md", ".html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{html_body}</body></html>")

    edge = find_edge()
    if not edge:
        print(f"Edge not found. HTML saved to: {html_path}")
        return

    file_url = "file:///" + os.path.abspath(html_path).replace("\\", "/")
    pdf_abs = os.path.abspath(pdf_path)

    subprocess.run([
        edge,
        "--headless",
        "--disable-gpu",
        f"--print-to-pdf={pdf_abs}",
        "--no-pdf-header-footer",
        file_url,
    ], capture_output=True, timeout=30)

    if os.path.exists(pdf_abs):
        size_kb = os.path.getsize(pdf_abs) / 1024
        print(f"Created: {pdf_path} ({size_kb:.0f} KB)")
    else:
        print(f"PDF creation failed for {pdf_path}. HTML available at: {html_path}")

files = [
    (
        os.path.join(REPORTS_DIR, "pharmacy_first_caps_report_EN.md"),
        os.path.join(REPORTS_DIR, "Pharmacy_First_Caps_Predictive_Report.pdf"),
    ),
]

for md_file, pdf_file in files:
    md_to_pdf(md_file, pdf_file)
