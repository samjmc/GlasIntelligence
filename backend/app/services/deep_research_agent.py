"""
Deep research agent using OpenAI Responses API with web search.
Produces a structured research dossier for simulation grounding.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from openai import OpenAI

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('glas.deep_research')

RESEARCH_SYSTEM_PROMPT = """\
You are a senior research analyst preparing a comprehensive dossier for a scenario simulation engine.

Your task:
1. Search the web thoroughly for the most current, relevant information about the scenario.
2. Produce a structured research report covering:
   - **Background & Context**: Key facts, recent developments, regulatory landscape.
   - **Key Stakeholders**: Major players, their positions, interests, and power dynamics.
   - **Quantitative Anchors**: Specific numbers, statistics, market data, financial figures.
   - **Historical Precedents**: Similar past scenarios and their outcomes.
   - **Key Risk Factors**: What could go wrong, uncertainty sources.

Requirements:
- Use specific names, dates, figures, and citations.
- Prefer recent data (last 12 months) over older sources.
- Include URLs for all sources referenced.
- Write 1500-2500 words.
- Structure with clear markdown headings.
- Conclude with a "Key Facts Summary" section: 5-10 bullet points of the most important quantitative facts.
"""


class DeepResearchAgent:
    def __init__(self):
        self.client = OpenAI(
            api_key=Config.LLM_API_KEY,
            base_url="https://api.openai.com/v1",
        )
        self.model = Config.DEEP_RESEARCH_MODEL
        self.max_tool_calls = Config.DEEP_RESEARCH_MAX_TOOL_CALLS

    def run(self, scenario: str, context: str = "") -> Dict[str, Any]:
        user_text = f"Research this scenario thoroughly:\n\n{scenario}"
        if context:
            user_text += f"\n\nAdditional context:\n{context}"

        logger.info(f"Starting deep research: model={self.model}, scenario={scenario[:100]}...")

        try:
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {
                        "role": "developer",
                        "content": [{"type": "input_text", "text": RESEARCH_SYSTEM_PROMPT}],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": user_text}],
                    },
                ],
                tools=[{"type": "web_search_preview"}],
                reasoning={"summary": "auto"},
            )
            return self._parse_response(response)

        except Exception:
            logger.exception("Deep research failed")
            return {
                "sources": [],
                "key_facts": [],
                "historical_precedents": [],
                "quantitative_anchors": [],
                "summary_md": "Deep research encountered an error. Please try again.",
                "search_queries": [],
                "error": True,
            }

    def _parse_response(self, response) -> Dict[str, Any]:
        summary_md = ""
        sources: List[Dict[str, str]] = []
        search_queries: List[str] = []
        seen_urls: set = set()

        for item in response.output:
            if getattr(item, "type", None) == "web_search_call":
                query = getattr(item, "query", None) or getattr(item, "input", None)
                if query and isinstance(query, str):
                    search_queries.append(query)

            if getattr(item, "type", None) == "message":
                for block in getattr(item, "content", []):
                    if getattr(block, "type", None) == "output_text":
                        summary_md = getattr(block, "text", "")
                        for ann in getattr(block, "annotations", []):
                            url = getattr(ann, "url", None)
                            title = getattr(ann, "title", None) or url or ""
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                sources.append({"url": url, "title": title})

        key_facts = self._extract_key_facts(summary_md)
        historical_precedents = self._extract_section(summary_md, "Historical Precedents")
        quantitative_anchors = self._extract_section(summary_md, "Quantitative Anchors")

        logger.info(
            f"Deep research complete: {len(sources)} sources, "
            f"{len(key_facts)} key facts, {len(search_queries)} searches"
        )

        return {
            "sources": sources,
            "key_facts": key_facts,
            "historical_precedents": historical_precedents,
            "quantitative_anchors": quantitative_anchors,
            "summary_md": summary_md,
            "search_queries": search_queries,
        }

    @staticmethod
    def _extract_key_facts(md: str) -> List[str]:
        facts: List[str] = []
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
    def _extract_section(md: str, heading: str) -> List[str]:
        items: List[str] = []
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

    @staticmethod
    def source_id_from_url(url: str) -> str:
        return "web_" + hashlib.md5(url.encode()).hexdigest()[:12]
