"""
Lightweight research agent backed by the configured LLM (DeepSeek/etc.) instead of
OpenAI's Responses API + web search. Produces the same dossier schema as
DeepResearchAgent so research_tasks and downstream consumers work without changes.
"""

from __future__ import annotations

import time
from typing import Any

from openai import RateLimitError, APIStatusError, APIConnectionError, APITimeoutError

from ..config import Config
from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient
from .research_angles import RESEARCH_ANGLES

logger = get_logger("glas.llm_research")

_MAX_RETRIES = 3
_RETRY_BACKOFFS = [5, 15, 45]
_TRANSIENT_STATUS_CODES = {500, 502, 503, 504}

# Adapted version of the base research prompt — same output structure but
# framed for training-knowledge reasoning rather than live web search.
_SYSTEM_PREAMBLE = """\
You are a senior research analyst preparing a comprehensive dossier for a multi-agent \
scenario simulation engine. Draw on your training knowledge to produce a detailed, \
structured research report.

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
Specific numbers, statistics, financial figures, polling data, trade volumes — anything that \
grounds the scenario in measurable reality. Include units and approximate dates.

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

Write 3000-6000 words. Be specific: name actors, quote known positions, describe incentives. \
Note when a claim is well-established vs. your reasoned inference.
"""

_ANGLE_HEADER = (
    "\nThe following research angles are particularly relevant to this scenario. Include dedicated sections for each:\n"
)


class LLMResearchAgent:
    """Research agent that uses the standard LLM client (DeepSeek) instead of OpenAI web search."""

    def run(
        self,
        scenario: str,
        context: str = "",
        angle_overrides: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        selected_ids = self._resolve_angles(angle_overrides)
        system_prompt = self._build_system_prompt(selected_ids)

        user_text = (
            "Research this scenario thoroughly using your training knowledge. "
            "The output will ground a multi-agent simulation: prioritise named actors with "
            "incentives and constraints, testable if-then reactions, and quantitative anchors.\n\n"
            f"{scenario}"
        )
        if context:
            user_text += f"\n\nAdditional context:\n{context}"

        logger.info(
            "Starting LLM research: model=%s angles=%s scenario=%.100s...",
            Config.LLM_MODEL_NAME,
            selected_ids,
            scenario,
        )

        llm = LLMClient()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]
        summary_md = self._chat_with_retry(llm, messages)

        if not summary_md.strip():
            raise RuntimeError("LLM research returned empty response")

        key_facts = self._extract_key_facts(summary_md)
        historical_precedents = self._extract_section(summary_md, "Historical Precedents")
        quantitative_anchors = self._extract_section(summary_md, "Quantitative Anchors")
        structured_precedents = self._structure_precedents(historical_precedents, quantitative_anchors)

        logger.info(
            "LLM research complete: %d key facts, %d precedents",
            len(key_facts),
            len(historical_precedents),
        )

        return {
            "sources": [],
            "key_facts": key_facts,
            "historical_precedents": historical_precedents,
            "quantitative_anchors": quantitative_anchors,
            "structured_precedents": structured_precedents,
            "summary_md": summary_md,
            "search_queries": [],
            "selected_angles": selected_ids,
        }

    @staticmethod
    def _chat_with_retry(llm: LLMClient, messages: list[dict]) -> str:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                return llm.chat(messages=messages, temperature=0.3, max_tokens=4096)
            except RateLimitError as e:
                last_exc = e
                wait = max(60, _RETRY_BACKOFFS[min(attempt, len(_RETRY_BACKOFFS) - 1)])
                logger.warning("LLM rate limited (attempt %d/%d), retrying in %ds: %s", attempt + 1, _MAX_RETRIES, wait, e)
                time.sleep(wait)
            except APIStatusError as e:
                last_exc = e
                if e.status_code not in _TRANSIENT_STATUS_CODES:
                    raise
                wait = _RETRY_BACKOFFS[min(attempt, len(_RETRY_BACKOFFS) - 1)]
                logger.warning("Transient API error %s (attempt %d/%d), retrying in %ds", e.status_code, attempt + 1, _MAX_RETRIES, wait)
                time.sleep(wait)
            except (APIConnectionError, APITimeoutError) as e:
                last_exc = e
                wait = _RETRY_BACKOFFS[min(attempt, len(_RETRY_BACKOFFS) - 1)]
                logger.warning("Connection/timeout error (attempt %d/%d), retrying in %ds: %s", attempt + 1, _MAX_RETRIES, wait, type(e).__name__)
                time.sleep(wait)
        raise last_exc  # type: ignore[misc]

    @staticmethod
    def _resolve_angles(overrides: dict[str, bool] | None) -> list[str]:
        # Use all angles; apply any explicit user overrides.
        result = {a.id for a in RESEARCH_ANGLES}
        if overrides:
            for angle_id, forced_on in overrides.items():
                if forced_on:
                    result.add(angle_id)
                else:
                    result.discard(angle_id)
        return sorted(result)

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

    @staticmethod
    def _extract_key_facts(md: str) -> list[str]:
        facts: list[str] = []
        in_facts = False
        for line in md.split("\n"):
            stripped = line.strip()
            lower = stripped.lower()
            if "key fact" in lower and ("#" in line or "**" in stripped):
                in_facts = True
                continue
            if in_facts:
                if stripped.startswith("#") or (stripped.startswith("**") and stripped.endswith("**")):
                    break
                if stripped.startswith(("- ", "* ")):
                    facts.append(stripped[2:].strip())
                elif stripped[:2].rstrip(".").isdigit():
                    dot_idx = stripped.index(".")
                    facts.append(stripped[dot_idx + 1 :].strip())
        return facts

    @staticmethod
    def _extract_section(md: str, heading: str) -> list[str]:
        items: list[str] = []
        in_section = False
        for line in md.split("\n"):
            stripped = line.strip()
            lower = stripped.lower()
            if heading.lower() in lower and ("#" in line or "**" in stripped):
                in_section = True
                continue
            if in_section:
                if stripped.startswith("#") or (stripped.startswith("**") and stripped.endswith("**")):
                    break
                if stripped.startswith(("- ", "* ")):
                    items.append(stripped[2:].strip())
        return items

    @staticmethod
    def _structure_precedents(precedents: list[str], anchors: list[str]) -> list[dict]:
        if not precedents:
            return []
        combined = "\n".join(f"- {p}" for p in precedents)
        anchors_text = "\n".join(f"- {a}" for a in anchors) if anchors else "None"
        system = """\
You are a research analyst structuring historical precedents for a scenario simulation.

Return ONLY valid JSON:
{
  "precedents": [
    {
      "event": "Name of the historical event or case",
      "outcome": "What happened — the result or resolution",
      "timeline": "When it occurred and how long it took to resolve",
      "relevance_score": 0.0,
      "key_metric": "Most important quantitative figure, or empty string",
      "source_url": ""
    }
  ]
}

Rules:
- relevance_score: 1.0 = same mechanism and actors; 0.5 = partial analogy; 0.0 = surface only
- key_metric: specific number with units if known, else empty string
- Include ALL precedents; do not invent facts not in the input
"""
        user = f"[Historical precedents]\n{combined}\n\n[Quantitative anchors]\n{anchors_text}"
        try:
            llm = LLMClient()
            data = llm.chat_json(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.15,
                max_tokens=2000,
            )
            result = data.get("precedents", [])
            for p in result:
                p["relevance_score"] = max(0.0, min(1.0, float(p.get("relevance_score", 0.5))))
                p.setdefault("source_url", "")
            result.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            return result
        except Exception as e:
            logger.warning("Failed to structure precedents: %s", e)
            return [
                {"event": p, "outcome": "", "timeline": "", "relevance_score": 0.5, "key_metric": "", "source_url": ""}
                for p in precedents
            ]
