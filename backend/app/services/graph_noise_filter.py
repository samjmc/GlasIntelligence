"""Filter non-actor nodes out of graph data.

Zep's server-side NER extracts entities from episode text, and it routinely
pulls non-stakeholder content as typed nodes. Two noise families are removed
(observed 2026-08-15, Pharmacy First graph):

1. **Quantitative anchors** — pure numbers, percentages, currency amounts,
   years/fiscal years, age ranges, standalone dates, and quantities with a
   unit word ('3.3 million', '£3.636 billion').
2. **Non-actor nodes** — bare URL domains ('pharmacytimes.com'), and nodes
   Zep did not classify as an actor type whose name is a common-noun phrase
   ('minor illness', 'high street', 'consultations') rather than a proper
   noun.

The graph's purpose is the *stakeholder* graph: actors with typed
relationships. Actor classification is label-based (Zep's own labels) with a
proper-noun fallback for unlabeled names ('England', 'PBM Reform').
Descriptive event labels that happen to be proper-noun-ish are kept; pure
topic phrases are dropped. Deliberately conservative: 'April 2026 caps' and
'£500 fixed payment' are removed as non-actors only when their form is a
common phrase — the exact rule set is below and unit-tested.

This filter is applied at the graph serve point (graph.py _graph_data_response)
and to recorded demo tapes via scripts/filter_graph_noise.py (same module, no
drift).
"""

from __future__ import annotations

import re

# --- Quantitative noise ----------------------------------------------------

# Pure numbers, percentages, currency amounts, years, fiscal years, ranges.
_QUANT_NOISE = re.compile(
    r"^("
    r"\d+([.,]\d+)?%?"            # 100, 2.7, 2.7%, 86%
    r"|[£€$]\s?[\d.,]+%?"         # £15, $2.5, €1,200
    r"|\d{4}(/\d{2})?"            # 2026, 2025/26
    r"|\d+-\d+"                   # 18-25, 26-31
    r")$"
)

# Quantity + unit word, no noun: '3.3 million', '£3.636 billion', '52k'.
_QUANT_UNIT = re.compile(
    r"^[£€$]?\s?\d+([.,]\d+)?\s?(thousand|million|billion|k|m|bn)$",
    re.IGNORECASE,
)

_MONTHS = (
    r"January|February|March|April|May|June|July|August|September|October"
    r"|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
)

# Standalone dates: 'June 2026', 'Mar 2026'.
_DATE_ONLY = re.compile(rf"^({_MONTHS})[a-z]*\.?\s+\d{{4}}$")

# Bare URL domains: 'pharmacytimes.com', 'beckershospitalreview.com'.
_URL_DOMAIN = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+){1,}$", re.IGNORECASE)

# --- Actor classification --------------------------------------------------

# Labels Zep assigns to nodes that can act (post, comment, react).
_ACTOR_LABELS = {
    "Organization",
    "Person",
    "MediaOrJournalist",
    "CommunityGroup",
    "GovernmentOrganization",
    "Company",
    "NGO",
    "Institution",
    "Group",
    "Individual",
}

# Proper-noun-ish name: every word capitalized or all-caps, with short
# lowercase connectors allowed ('The Past, Present, and Future of the …').
_PROPER_NOUN = re.compile(
    r"^(?:[A-Z][a-z'-]*|[A-Z]{2,})(?:\s+(?:[A-Z][a-z'-]*|[A-Z]{2,}|[a-z]{1,3}))*$"
)


def is_quant_noise(name: str) -> bool:
    """True when a node name is purely numeric/currency/date/unit-ish."""
    if not name:
        return False
    name = name.strip()
    return bool(_QUANT_NOISE.match(name) or _QUANT_UNIT.match(name) or _DATE_ONLY.match(name))


def is_non_actor(name: str, labels: list[str] | None) -> bool:
    """True when a node is not a stakeholder: URL domain, or neither an
    actor-labeled node nor a proper-noun name."""
    if not name:
        return False
    name = name.strip()
    if _URL_DOMAIN.match(name):
        return True
    if labels and any(l in _ACTOR_LABELS for l in labels):
        return False
    return not _PROPER_NOUN.match(name)


def filter_quant_noise(nodes: list[dict], edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """Drop noise nodes (quantitative + non-actor) and dangling edges.

    Node identity: the ``uuid`` field. Counts are NOT adjusted here — callers
    update ``node_count``/``edge_count`` from the returned lists.
    """
    dropped = {
        n.get("uuid")
        for n in nodes
        if is_quant_noise(n.get("name") or "") or is_non_actor(n.get("name") or "", n.get("labels"))
    }
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
