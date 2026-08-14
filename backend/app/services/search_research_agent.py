"""Research agent: Tavily web search + iterative LLM synthesis/critique loop.

This is the Claude research chain: query generation -> live Tavily search ->
synthesis -> critique with follow-up queries -> re-search -> final verification
pass. Runs on whatever the configured LLM is; an ``sk-ant-`` key routes through
Anthropic via LLMClient.
"""

from __future__ import annotations

import json
from typing import Any

from ..config import Config
from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient
from ..utils.tavily_client import TavilyClient
from .research_angles import RESEARCH_ANGLES
from .llm_research_agent import LLMResearchAgent

logger = get_logger("glas.search_research")

_SYSTEM_PREAMBLE = """\
You are a senior research analyst preparing a comprehensive dossier for a multi-agent \
scenario simulation engine. You have been provided with live web search results below. \
Use the search results together with your background knowledge to produce a detailed, \
structured research report. Prioritise figures and facts from the search results over \
your training knowledge wherever they differ.

Your dossier drives three downstream processes:
1. Entity extraction — every named actor becomes a simulated AI agent with its own persona.
2. Knowledge graph construction — relationships between actors become graph edges.
3. A social-media simulation (Twitter/Reddit) where agents debate and react over time.

The simulation quality depends entirely on the depth and specificity of your research. \
Vague summaries produce shallow agents. Specific names, positions, incentives, and \
relationship dynamics produce rich, realistic ones.

**Required output sections (use these exact markdown headings):**

## Background & Context
Key facts, current state of play, and the core tensions at stake.

## Key Stakeholders
Name every significant actor: heads of state, executives, regulators, NGOs, think tanks, \
media outlets, activists, affected populations. For EACH provide: stated position, underlying \
interests, influence level (high/medium/low), communication style, and known rhetorical patterns. \
Aim for 20-40 named entities — this section directly determines agent quality.

## Reaction Chains & Decision Dynamics
For the most important actors, describe how they would react to key developments. \
Use "if X then Y" framing: "If sanctions are imposed, X is likely to..."

## Public Opinion Landscape
The major camps of public discourse: dominant narratives, hashtags/slogans, polarisation level, \
which narratives are gaining or losing traction.

## Information Flow & Influence Networks
Who amplifies whom. Which media outlets back which actors. How information cascades \
from official statements to public discourse.

## Quantitative Anchors
Specific numbers, statistics, financial figures, polling data — use current figures from \
the search results where available. Include units and approximate dates.

## Historical Precedents
Similar past scenarios and their outcomes, including actors involved and timeline.

## Key Risk Factors & Wildcards
What could go wrong, low-probability high-impact events, which actors are most exposed.

## Timeline & Inflection Points
Key upcoming dates, deadlines, elections, hearings, or events that could shift the trajectory.

## Relationships & Alliances
Explicit mapping of alliances, rivalries, dependencies, treaty obligations, and regulatory \
oversight between the key actors.

## Known Unknowns & Information Gaps
What is contested or uncertain, and which assumptions the simulation would need to vary.

## Simulation Parameters
A numbered list of 8-12 levers a modeller would toggle (e.g. price of X, policy choice Y) \
with plausible ranges or discrete options.

## Key Facts Summary
10-15 bullet points of the most important quantitative facts with units and approximate dates. \
This heading MUST contain the words "Key Facts".

Write 3000-6000 words. Be specific: name actors, cite search sources where relevant, \
describe incentives. Note when a claim is from the search results vs. your reasoned inference.\
"""

_ANGLE_HEADER = "\nThe following research angles are particularly relevant. Include dedicated sections for each:\n"

_QUERY_SYSTEM = """\
You are a research strategist. Given a scenario description, generate 4-6 precise web search \
queries that will retrieve the most useful current data: named individuals, recent statistics, \
latest policy developments, and current market figures.

Return ONLY a JSON array of strings — the queries, nothing else. Example:
["US tariffs on Chinese semiconductors 2025", "TSMC revenue breakdown by customer 2024"]
"""

_CRITIQUE_SYSTEM = """\
You are a research quality reviewer. Evaluate the provided research dossier on a scale of 0-10:
- 10: all key actors have current verified data, all quantitative claims are sourced and recent, \
no significant gaps, sufficient to ground a high-quality simulation.
- 7.5: minor gaps, mostly current data, simulation would work but could be richer.
- 5: notable gaps in either current data or named actors.
- Below 5: major sections lack specifics or data is clearly stale.

Identify specific factual gaps and suggest targeted follow-up search queries to fill them.

Return ONLY valid JSON — no markdown, no explanation:
{
  "score": 7.5,
  "gaps": ["gap description 1", "gap description 2"],
  "follow_up_queries": ["specific search query 1", "specific search query 2"]
}
"""

_VERIFICATION_SYSTEM = """\
You are the final verification step in a research pipeline. A dossier was drafted from live \
web search results. Cross-check the dossier's quantitative and factual claims against the \
provided search results and report what is supported and what is not.

Rules:
- A claim is "verified" if the search results contain the same figure, date, or named fact. \
Approximate agreement is fine for figures; dates must match.
- A claim is "unverified" if it is absent from the results, contradicts them, or appears to \
come from training knowledge only.
- "corrections" is for claims where the results contradict the dossier — give the corrected \
wording and what the source actually says.
- Never invent source URLs. Only use URLs present in the results.
- Be specific but concise; 3-8 claims per list is plenty.

Return ONLY valid JSON:
{
  "verified_claims": [{"claim": "short claim", "source_url": "url from results"}],
  "unverified_claims": [{"claim": "short claim", "note": "why it could not be verified"}],
  "corrections": [{"original": "claim as written", "corrected": "corrected claim", "reason": "what the source says instead"}]
}
"""


class SearchResearchAgent:
    """Research agent: Tavily search + iterative LLM synthesis and critique."""

    def run(
        self,
        scenario: str,
        context: str = "",
        angle_overrides: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        llm = LLMClient(model=Config.SEARCH_RESEARCH_MODEL)
        tavily = TavilyClient(api_key=Config.TAVILY_API_KEY)
        selected_ids = LLMResearchAgent._resolve_angles(angle_overrides)
        system_prompt = self._build_system_prompt(selected_ids)

        max_rounds = Config.SEARCH_RESEARCH_MAX_ROUNDS
        threshold = Config.SEARCH_RESEARCH_QUALITY_THRESHOLD

        all_sources: list[dict] = []
        all_queries: list[str] = []
        summary_md = ""
        follow_up_queries: list[str] = []

        for round_num in range(1, max_rounds + 1):
            if round_num == 1:
                queries = self._generate_queries(llm, scenario)
            else:
                queries = follow_up_queries

            all_queries.extend(queries)
            logger.info("Round %d/%d: running %d queries", round_num, max_rounds, len(queries))

            new_results: list[dict] = []
            for q in queries:
                new_results.extend(tavily.search(q, max_results=5))
            all_sources.extend(new_results)

            search_context = self._format_results(all_sources)[:40_000]
            summary_md = self._synthesize(llm, system_prompt, scenario, context, search_context)

            critique = self._critique(llm, scenario, summary_md)
            raw_score = critique.get("score", 10.0)
            try:
                score = float(raw_score)
            except (TypeError, ValueError):
                logger.warning("Critique returned non-numeric score %r — assuming pass", raw_score)
                score = 10.0
            follow_up_queries = (critique.get("follow_up_queries") or [])[:6]

            logger.info("Round %d critique score: %.1f", round_num, score)

            if score >= threshold or round_num >= max_rounds or not follow_up_queries:
                break

        if not summary_md.strip():
            raise RuntimeError("SearchResearchAgent returned empty summary_md")

        verification: dict = {}
        if all_sources:
            verification = self._verify(llm, scenario, summary_md, search_context)
            summary_md = self._append_verification_notes(summary_md, verification)

        key_facts = LLMResearchAgent._extract_key_facts(summary_md)
        historical_precedents = LLMResearchAgent._extract_section(summary_md, "Historical Precedents")
        quantitative_anchors = LLMResearchAgent._extract_section(summary_md, "Quantitative Anchors")
        structured_precedents = LLMResearchAgent._structure_precedents(historical_precedents, quantitative_anchors)

        seen_urls: set[str] = set()
        unique_sources: list[dict] = []
        for s in all_sources:
            if s["url"] not in seen_urls:
                seen_urls.add(s["url"])
                unique_sources.append(s)

        return {
            "sources": unique_sources,
            "key_facts": key_facts,
            "historical_precedents": historical_precedents,
            "quantitative_anchors": quantitative_anchors,
            "structured_precedents": structured_precedents,
            "summary_md": summary_md,
            "search_queries": all_queries,
            "selected_angles": selected_ids,
            "verification": verification,
        }

    @staticmethod
    def _generate_queries(llm: LLMClient, scenario: str) -> list[str]:
        try:
            raw = llm.chat(
                messages=[
                    {"role": "system", "content": _QUERY_SYSTEM},
                    {"role": "user", "content": f"Scenario: {scenario}"},
                ],
                temperature=0.3,
                max_tokens=512,
            )
            queries = json.loads(raw)
            if isinstance(queries, list):
                return [str(q) for q in queries[:6] if q]
        except Exception:
            pass
        return [scenario[:200]]

    @staticmethod
    def _format_results(results: list[dict]) -> str:
        parts = []
        for i, r in enumerate(results, 1):
            parts.append(f"[{i}] {r['title']}\nURL: {r['url']}\n{r['content']}")
        return "\n\n".join(parts)

    @staticmethod
    def _synthesize(
        llm: LLMClient,
        system_prompt: str,
        scenario: str,
        context: str,
        search_context: str,
    ) -> str:
        user_text = f"Scenario: {scenario}\n\n[Search results]\n{search_context}"
        if context:
            user_text += f"\n\n[Additional context]\n{context}"
        return llm.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            temperature=0.3,
            max_tokens=12000,
        )

    @staticmethod
    def _critique(llm: LLMClient, scenario: str, summary_md: str) -> dict:
        try:
            data = llm.chat_json(
                messages=[
                    {"role": "system", "content": _CRITIQUE_SYSTEM},
                    {
                        "role": "user",
                        "content": f"Scenario: {scenario}\n\n[Dossier]\n{summary_md[:32000]}",
                    },
                ],
                temperature=0.2,
                max_tokens=2048,
            )
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.warning("Critique call failed: %s", exc)
            return {"score": 10.0, "gaps": [], "follow_up_queries": []}

    @staticmethod
    def _verify(llm: LLMClient, scenario: str, summary_md: str, search_context: str) -> dict:
        """Final pass: cross-check the dossier's claims against the search results.

        Never raises — a verification failure must not fail the whole run. Returns
        an empty dict, which the caller treats as "no notes to append".
        """
        try:
            data = llm.chat_json(
                messages=[
                    {"role": "system", "content": _VERIFICATION_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"Scenario: {scenario}\n\n[Dossier]\n{summary_md[:32000]}"
                            f"\n\n[Search results]\n{search_context[:32000]}"
                        ),
                    },
                ],
                temperature=0.1,
                max_tokens=4096,
            )
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.warning("Verification pass failed: %s", exc)
            return {}

    @staticmethod
    def _append_verification_notes(summary_md: str, verification: dict) -> str:
        """Append a transparent Verification Notes section to the dossier markdown."""
        verified = verification.get("verified_claims") or []
        unverified = verification.get("unverified_claims") or []
        corrections = verification.get("corrections") or []
        if not (verified or unverified or corrections):
            return summary_md

        lines = ["", "## Verification Notes"]
        if corrections:
            lines.append("### Corrected claims")
            for c in corrections:
                lines.append(f"- ~~{c.get('original', '')}~~ → {c.get('corrected', '')} ({c.get('reason', '')})")
        if unverified:
            lines.append("### Unverified claims (training-knowledge only)")
            for u in unverified:
                lines.append(f"- {u.get('claim', '')} — {u.get('note', '')}")
        if verified:
            lines.append("### Verified against search results")
            for v in verified:
                lines.append(f"- {v.get('claim', '')} — {v.get('source_url', '')}")
        return f"{summary_md}\n{chr(10).join(lines)}".strip()

    @staticmethod
    def _build_system_prompt(selected_ids: list[str]) -> str:
        angle_map = {a.id: a for a in RESEARCH_ANGLES}
        angles = [angle_map[aid] for aid in selected_ids if aid in angle_map]
        if not angles:
            return _SYSTEM_PREAMBLE
        parts = [_SYSTEM_PREAMBLE, _ANGLE_HEADER]
        for angle in angles:
            parts.append(f"\n### {angle.label}\n{angle.directive}")
        return "\n".join(parts)
