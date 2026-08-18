"""Entity knowledge-expansion pass: name additional REAL stakeholders beyond
the research text, grounded by live search verification.

The research dossier constrains everything downstream: NER, the inventory
pre-scan and graph enrichment all read the same text, so stakeholders absent
from the research (sector-adjacent software vendors, consultancies, analysts,
trade press, adjacent regulators) never enter the graph. This pass has the
LLM name candidates from domain knowledge, then verifies each with a live
Tavily search — a candidate survives only if a distinctive token of its name
appears in an actual result. Unverified candidates are dropped, never merged.

Fail-soft by design: any failure returns [] so the graph build is never
blocked by the enhancement.
"""

from __future__ import annotations

import re
from typing import Any

from ..config import Config
from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient
from ..utils.tavily_client import TavilyClient

logger = get_logger("glas.entity_expansion")

_SYSTEM_PROMPT = """\
You are a domain research analyst expanding a stakeholder inventory for a scenario \
simulation. You have been given a scenario and the stakeholders ALREADY identified \
from the research text. Your job: name additional REAL stakeholders that the research \
text does not mention but that matter for this scenario.

Target the classes research often misses:
- Software / platform / technology vendors serving the sector
- Consultancies and advisory firms active in the sector
- Analysts, data providers, and research bodies
- Trade press and specialist media
- Adjacent regulators, inspectorates, and standards bodies
- Industry bodies, associations, and unions not already listed
- Major adjacent commercial players (retail, manufacturing, logistics)

Rules:
- ONLY real, operating entities. Never invent names. If unsure, do not include.
- Scope to the country/region of the scenario (e.g. UK) unless a candidate is \
genuinely international and relevant.
- Do NOT repeat any name from the existing inventory list.
- Prefer entities with public web presence (verification will search for them).

Return ONLY valid JSON:
{
  "candidates": [
    {
      "name": "Full official name",
      "type": "company | consultancy | analyst | media | regulator | association | other",
      "role": "one sentence: who they are and why they matter to this scenario",
      "verify_query": "a precise search query that would surface this entity in the \
context of the scenario (region-scoped, include the entity name)"
    }
  ]
}
"""

_TOKEN_RE = re.compile(r"[A-Za-z]{4,}")


def _distinctive_tokens(name: str) -> list[str]:
    """Tokens long enough to identify the entity in search results (acronyms
    like 'RWA' are too short to match verbatim)."""
    return [t.lower() for t in _TOKEN_RE.findall(name) if len(t) >= 4]


def _name_in_results(name: str, results: list[dict]) -> bool:
    tokens = _distinctive_tokens(name)
    if not tokens:
        return False
    haystack = " ".join(f"{r.get('title', '')} {r.get('content', '')}".lower() for r in results)
    return any(t in haystack for t in tokens)


def _generate_candidates(
    llm: LLMClient, scenario: str, context: str, existing_names: list[str], target: int
) -> list[dict]:
    user = (
        f"Scenario: {scenario}\n\n"
        f"Target number of new candidates: {target}\n\n"
        f"Already identified stakeholders (do NOT repeat):\n"
        f"{chr(10).join('- ' + n for n in existing_names) if existing_names else '(none)'}\n\n"
        f"Research context (first 6000 chars):\n{context[:6000]}"
    )
    data = llm.chat_json(
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        temperature=0.3,
        max_tokens=2500,
    )
    candidates = data.get("candidates") if isinstance(data, dict) else None
    if not isinstance(candidates, list):
        raise ValueError("expansion LLM returned no candidates list")
    return [c for c in candidates if isinstance(c, dict) and c.get("name")]


def expand_entities(
    scenario: str,
    context: str,
    existing_names: list[str],
    target: int | None = None,
    api_key: str | None = None,
) -> list[dict]:
    """Return verified additional stakeholders in the inventory shape
    {name, category, context}. Never raises; [] on any failure."""
    try:
        target = target or Config.ENTITY_EXPANSION_TARGET
        llm = LLMClient(api_key=api_key)
        tavily = TavilyClient(api_key=api_key or Config.TAVILY_API_KEY)

        existing = {n.strip().lower() for n in existing_names if n}
        candidates = _generate_candidates(llm, scenario, context, sorted(existing), target)

        verified: list[dict[str, Any]] = []
        for c in candidates:
            name = (c.get("name") or "").strip()
            if not name or name.lower() in existing:
                continue
            query = (c.get("verify_query") or name).strip()
            results = tavily.search(query, max_results=3)
            if not results or not _name_in_results(name, results):
                logger.info("Entity expansion: DROPPED %r (no verification match)", name)
                continue
            existing.add(name.lower())
            verified.append(
                {
                    "name": name,
                    "category": (c.get("type") or "other").strip(),
                    "context": (c.get("role") or "").strip(),
                }
            )
            logger.info("Entity expansion: VERIFIED %r (%s)", name, query[:60])

        logger.info(
            "Entity expansion complete: %d/%d candidates verified",
            len(verified),
            len(candidates),
        )
        return verified
    except Exception as exc:
        # Fail-soft: the expansion is an enhancement, never a blocker.
        logger.warning("Entity expansion failed (%s: %s) — continuing without additions", type(exc).__name__, exc)
        return []
