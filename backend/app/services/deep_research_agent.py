"""
Deep research agent using OpenAI Responses API with web search.
Produces a structured research dossier for simulation grounding.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from openai import OpenAI, RateLimitError, APIStatusError

from ..config import Config
from ..utils.logger import get_logger
from .research_angles import (
    ALL_ANGLE_IDS,
    classify_scenario,
    build_research_prompt,
    get_angles_by_ids,
)

_TRANSIENT_STATUS_CODES = {500, 502, 503}
_MAX_RETRIES = 5
_RETRY_BACKOFFS = [5, 10, 30, 60, 90]
_MAX_OUTPUT_TOKENS = 16000

logger = get_logger("glas.deep_research")


class DeepResearchAgent:
    def __init__(self):
        self.client = OpenAI(
            api_key=Config.LLM_API_KEY,
            base_url="https://api.openai.com/v1",
            max_retries=0,
            # Single Responses API call can run 30–45+ min on complex topics; must exceed Celery soft limit
            timeout=2700.0,
        )
        self.model = Config.DEEP_RESEARCH_MODEL
        self.max_tool_calls = Config.DEEP_RESEARCH_MAX_TOOL_CALLS

    def run(
        self,
        scenario: str,
        context: str = "",
        angle_overrides: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        user_text = (
            "Research this scenario thoroughly. The output will ground a multi-agent simulation: "
            "prioritise verifiable facts, named actors with incentives/constraints, testable if–then "
            "reactions, quantitative anchors with dates/units, and explicit gaps where evidence is weak.\n\n"
            f"{scenario}"
        )
        if context:
            user_text += f"\n\nAdditional context:\n{context}"

        selected_ids = self._resolve_angles(scenario, angle_overrides)
        angles = get_angles_by_ids(selected_ids)
        system_prompt = build_research_prompt(angles)

        logger.info(f"Starting deep research: model={self.model}, angles={selected_ids}, scenario={scenario[:100]}...")

        response = self._call_with_retry(system_prompt, user_text)
        result = self._parse_response(response)
        result["selected_angles"] = selected_ids
        return result

    def _call_with_retry(self, system_prompt: str, user_text: str):
        """Call the Responses API with retry on transient errors."""
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                return self.client.responses.create(
                    model=self.model,
                    max_output_tokens=_MAX_OUTPUT_TOKENS,
                    input=[
                        {
                            "role": "developer",
                            "content": [{"type": "input_text", "text": system_prompt}],
                        },
                        {
                            "role": "user",
                            "content": [{"type": "input_text", "text": user_text}],
                        },
                    ],
                    tools=[{"type": "web_search_preview"}],
                )
            except RateLimitError as e:
                last_exc = e
                wait = _RETRY_BACKOFFS[min(attempt, len(_RETRY_BACKOFFS) - 1)]
                logger.warning(
                    f"Rate limited by OpenAI (attempt {attempt + 1}/{_MAX_RETRIES}), retrying in {wait}s: {e.message}"
                )
                time.sleep(wait)
                continue
            except APIStatusError as e:
                last_exc = e
                if e.status_code not in _TRANSIENT_STATUS_CODES:
                    logger.error(f"API error {e.status_code}: {e}")
                    raise
                wait = _RETRY_BACKOFFS[min(attempt, len(_RETRY_BACKOFFS) - 1)]
                logger.warning(
                    f"Transient API error {e.status_code} (attempt {attempt + 1}/{_MAX_RETRIES}), retrying in {wait}s"
                )
                time.sleep(wait)

        logger.error(f"Deep research failed after {_MAX_RETRIES} attempts")
        raise last_exc  # type: ignore[misc]

    @staticmethod
    def _resolve_angles(
        scenario: str,
        overrides: dict[str, bool] | None,
    ) -> list[str]:
        """Merge LLM-classified angles with explicit user overrides."""
        auto_ids = set(classify_scenario(scenario))

        if not overrides:
            return sorted(auto_ids)

        valid_ids = set(ALL_ANGLE_IDS)
        result = set(auto_ids)
        for angle_id, forced_on in overrides.items():
            if angle_id not in valid_ids:
                continue
            if forced_on:
                result.add(angle_id)
            else:
                result.discard(angle_id)

        return sorted(result)

    def _parse_response(self, response) -> dict[str, Any]:
        # Accumulate text across all output_text blocks. Previously we assigned
        # rather than appended, which silently dropped earlier content if the
        # Responses API emitted multiple message items (e.g. a final empty one).
        text_chunks: list[str] = []
        sources: list[dict[str, str]] = []
        search_queries: list[str] = []
        seen_urls: set = set()

        for item in response.output:
            if getattr(item, "type", None) == "web_search_call":
                query = getattr(item, "query", None) or getattr(item, "input", None)
                if query and isinstance(query, str):
                    search_queries.append(query)

            if getattr(item, "type", None) == "message":
                for block in getattr(item, "content", []):
                    if getattr(block, "type", None) == "output_text":
                        chunk = getattr(block, "text", "") or ""
                        if chunk:
                            text_chunks.append(chunk)
                        for ann in getattr(block, "annotations", []):
                            url = getattr(ann, "url", None)
                            title = getattr(ann, "title", None) or url or ""
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                sources.append({"url": url, "title": title})

        summary_md = "\n\n".join(text_chunks).strip()

        key_facts = self._extract_key_facts(summary_md)
        historical_precedents = self._extract_section(summary_md, "Historical Precedents")
        quantitative_anchors = self._extract_section(summary_md, "Quantitative Anchors")

        structured_precedents = self._structure_precedents(historical_precedents, quantitative_anchors, sources)

        logger.info(
            f"Deep research complete: {len(sources)} sources, "
            f"{len(key_facts)} key facts, {len(search_queries)} searches, "
            f"{len(structured_precedents)} structured precedents"
        )

        return {
            "sources": sources,
            "key_facts": key_facts,
            "historical_precedents": historical_precedents,
            "quantitative_anchors": quantitative_anchors,
            "structured_precedents": structured_precedents,
            "summary_md": summary_md,
            "search_queries": search_queries,
        }

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
                if stripped.startswith("- ") or stripped.startswith("* "):
                    facts.append(stripped[2:].strip())
                elif stripped.startswith("1.") or stripped.startswith("2."):
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
                if stripped.startswith("- ") or stripped.startswith("* "):
                    items.append(stripped[2:].strip())
        return items

    def _structure_precedents(
        self,
        precedents: list[str],
        anchors: list[str],
        sources: list[dict],
    ) -> list[dict]:
        """
        Convert raw markdown precedents into structured objects via LLM.
        Each gets: event, outcome, timeline, relevance_score, key_metric, source_url.
        """
        if not precedents:
            return []

        combined = "\n".join(f"- {p}" for p in precedents)
        anchors_text = "\n".join(f"- {a}" for a in anchors) if anchors else "None"
        source_urls = [s.get("url", "") for s in sources[:10]]

        system = """\
You are a research analyst structuring historical precedents for comparison with a scenario simulation.

Return ONLY valid JSON:
{
  "precedents": [
    {
      "event": "Name of the historical event or case",
      "outcome": "What happened — the result or resolution",
      "timeline": "When it occurred and how long it took to resolve",
      "relevance_score": 0.0-1.0,
      "key_metric": "Most important quantitative figure from this precedent",
      "source_url": "URL if identifiable from the sources list, otherwise empty string"
    }
  ]
}

Rules:
- relevance_score: 1.0 = same mechanism and comparable actors/constraints; 0.5 = partial analogy; \
0.0 = surface similarity only. Down-rank analogies that differ on veto players, institutions, or scale.
- key_metric: a specific number, percentage, or financial figure with units if given (e.g. \
"42% market share decline in 18 months"); use empty string if no numeric anchor exists.
- Include ALL precedents from the input, even if relevance is low
- Be concise: event and outcome should each be 1-2 sentences; do not invent facts not in the input \
or source URLs not in the provided list
"""
        user = (
            f"[Historical precedents from research]\n{combined}\n\n"
            f"[Quantitative anchors]\n{anchors_text}\n\n"
            f"[Available source URLs]\n{chr(10).join(source_urls)}"
        )

        try:
            from ..utils.llm_client import LLMClient

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
            result.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            return result
        except Exception as e:
            logger.warning(f"Failed to structure precedents: {e}")
            return [
                {"event": p, "outcome": "", "timeline": "", "relevance_score": 0.5, "key_metric": "", "source_url": ""}
                for p in precedents
            ]

    @staticmethod
    def source_id_from_url(url: str) -> str:
        return "web_" + hashlib.md5(url.encode()).hexdigest()[:12]
