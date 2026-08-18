"""Filter quantitative-noise nodes out of graph data.

Zep's server-side NER extracts entities from episode text, and it routinely
pulls pure quantitative anchors — '2.7%', '£17', '2026', '18-25' — as typed
nodes (observed 2026-08-15: 13 of 50 nodes in the Pharmacy First graph were
pure numbers/percentages/currency/ranges). The LLM entity inventory is clean;
this filter removes the vendor-NER noise at the serve point so both the live
API and recorded demo tapes present stakeholder-only graphs.

Conservative by design: only drops nodes whose NAME is entirely numeric-ish.
Descriptive labels ('April 2026 caps', '£500 fixed payment', '73 patients')
are kept — they name events or artefacts, not bare quantities.
"""

from __future__ import annotations

import re

# Pure numbers, percentages, currency amounts, years, fiscal years, ranges.
_QUANT_NOISE = re.compile(
    r"^("
    r"\d+([.,]\d+)?%?"            # 100, 2.7, 2.7%, 86%
    r"|[£€$]\s?[\d.,]+%?"         # £15, $2.5, €1,200
    r"|\d{4}(/\d{2})?"            # 2026, 2025/26
    r"|\d+-\d+"                   # 18-25, 26-31
    r")$"
)

_MONTHS = (
    r"January|February|March|April|May|June|July|August|September|October"
    r"|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
)

# Standalone dates: 'June 2026', 'Mar 2026'.
_DATE_ONLY = re.compile(rf"^({_MONTHS})[a-z]*\.?\s+\d{{4}}$")


def is_quant_noise(name: str) -> bool:
    """True when a node name is purely numeric/currency/date-ish."""
    if not name:
        return False
    name = name.strip()
    return bool(_QUANT_NOISE.match(name) or _DATE_ONLY.match(name))


def filter_quant_noise(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """Drop quantitative-noise nodes and any edge referencing a dropped node.

    Node identity: the ``uuid`` field. Counts are NOT adjusted here — callers
    update ``node_count``/``edge_count`` from the returned lists.
    """
    dropped = {n.get("uuid") for n in nodes if is_quant_noise(n.get("name") or "")}
    if not dropped:
        return nodes, edges

    kept_nodes = [n for n in nodes if n.get("uuid") not in dropped]

    def edge_refs(e: dict) -> list[str]:
        return [
            e.get("source", {}).get("uuid") if isinstance(e.get("source"), dict) else e.get("source"),
            e.get("target", {}).get("uuid") if isinstance(e.get("target"), dict) else e.get("target"),
        ]

    kept_edges = [e for e in edges if not (set(edge_refs(e)) & dropped)]
    return kept_nodes, kept_edges
