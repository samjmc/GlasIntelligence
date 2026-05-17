# SearchResearchAgent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `SearchResearchAgent` that calls Tavily for live web search then iteratively refines the output with LLM synthesis and self-critique rounds, replacing the pure-LLM fallback when `TAVILY_API_KEY` is set.

**Architecture:** The agent runs up to 3 rounds: (1) LLM generates 4-6 targeted search queries from the scenario, (2) Tavily executes each query, (3) LLM synthesizes results into a full dossier markdown, (4) LLM self-critiques that dossier returning a JSON score + gap descriptions + follow-up queries, (5) if score < 7.5 and rounds remain, the agent re-searches with the follow-up queries and re-synthesizes. Returns the same dossier dict schema as `LLMResearchAgent` so all downstream consumers work unchanged.

**Tech Stack:** `requests` (Tavily REST API), existing `LLMClient` (`chat()` / `chat_json()`), `Config` class pattern already in `config.py`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `backend/app/utils/tavily_client.py` | Create | HTTP wrapper for Tavily REST API |
| `backend/app/services/search_research_agent.py` | Create | Iterative search + synthesize + critique agent |
| `backend/app/config.py` | Modify | Add `TAVILY_API_KEY`, `SEARCH_RESEARCH_ENABLED`, round/threshold config |
| `backend/app/tasks/research_tasks.py` | Modify | Add third branch: `elif SEARCH_RESEARCH_ENABLED` |
| `backend/tests/test_tavily_client.py` | Create | Unit tests for TavilyClient |
| `backend/tests/test_search_research_agent.py` | Create | Unit tests for SearchResearchAgent |

---

### Task 1: Create TavilyClient

**Files:**
- Create: `backend/app/utils/tavily_client.py`
- Create: `backend/tests/test_tavily_client.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_tavily_client.py
from unittest.mock import patch, MagicMock
import pytest
from app.utils.tavily_client import TavilyClient


def test_search_returns_results():
    client = TavilyClient(api_key="test-key")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "results": [
            {"title": "Article A", "url": "https://example.com/a", "content": "Some content A"},
            {"title": "Article B", "url": "https://example.com/b", "content": "Some content B"},
        ]
    }
    with patch("app.utils.tavily_client.requests.post", return_value=mock_resp) as mock_post:
        results = client.search("test query", max_results=2)

    assert len(results) == 2
    assert results[0]["title"] == "Article A"
    assert results[0]["url"] == "https://example.com/a"
    assert results[0]["content"] == "Some content A"
    call_json = mock_post.call_args.kwargs["json"]
    assert call_json["query"] == "test query"
    assert call_json["max_results"] == 2


def test_search_returns_empty_on_api_error():
    client = TavilyClient(api_key="test-key")
    with patch("app.utils.tavily_client.requests.post", side_effect=Exception("network error")):
        results = client.search("test query")
    assert results == []


def test_search_strips_missing_fields():
    client = TavilyClient(api_key="test-key")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "results": [{"url": "https://example.com/c"}]  # no title or content
    }
    with patch("app.utils.tavily_client.requests.post", return_value=mock_resp):
        results = client.search("q")
    assert results[0]["title"] == ""
    assert results[0]["content"] == ""
    assert results[0]["url"] == "https://example.com/c"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/user/GlasIntelligence/backend
python -m pytest tests/test_tavily_client.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `tavily_client` doesn't exist yet.

- [ ] **Step 3: Write the implementation**

```python
# backend/app/utils/tavily_client.py
"""Thin wrapper around the Tavily Search REST API."""
from __future__ import annotations

import requests

from ..utils.logger import get_logger

logger = get_logger("glas.tavily")

_TAVILY_URL = "https://api.tavily.com/search"


class TavilyClient:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        """Search Tavily. Returns list of {title, url, content} dicts; empty list on error."""
        try:
            resp = requests.post(
                _TAVILY_URL,
                json={
                    "api_key": self._api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "advanced",
                    "include_raw_content": False,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                }
                for r in data.get("results", [])
            ]
        except Exception as exc:
            logger.warning("Tavily search failed for query %r: %s", query, exc)
            return []
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/user/GlasIntelligence/backend
python -m pytest tests/test_tavily_client.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/utils/tavily_client.py backend/tests/test_tavily_client.py
git commit -m "feat: add TavilyClient HTTP wrapper"
```

---

### Task 2: Add Tavily config keys

**Files:**
- Modify: `backend/app/config.py` (after the Deep Research block, line ~305)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_config_tavily.py
import importlib
import sys


def _reload_config():
    # Remove cached module so env changes take effect
    for key in list(sys.modules.keys()):
        if "app.config" in key:
            del sys.modules[key]
    import app.config as cfg
    return cfg


def test_tavily_api_key_from_env(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tv-test-key")
    cfg = _reload_config()
    assert cfg.Config.TAVILY_API_KEY == "tv-test-key"
    assert cfg.Config.SEARCH_RESEARCH_ENABLED is True


def test_tavily_disabled_when_no_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    cfg = _reload_config()
    assert cfg.Config.TAVILY_API_KEY == ""
    assert cfg.Config.SEARCH_RESEARCH_ENABLED is False


def test_tavily_max_rounds_default(monkeypatch):
    monkeypatch.delenv("SEARCH_RESEARCH_MAX_ROUNDS", raising=False)
    cfg = _reload_config()
    assert cfg.Config.SEARCH_RESEARCH_MAX_ROUNDS == 3


def test_tavily_quality_threshold_default(monkeypatch):
    monkeypatch.delenv("SEARCH_RESEARCH_QUALITY_THRESHOLD", raising=False)
    cfg = _reload_config()
    assert cfg.Config.SEARCH_RESEARCH_QUALITY_THRESHOLD == 7.5
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/user/GlasIntelligence/backend
python -m pytest tests/test_config_tavily.py -v
```

Expected: `AttributeError` — `Config` has no attribute `TAVILY_API_KEY`.

- [ ] **Step 3: Add the config keys**

In `backend/app/config.py`, after the Deep Research block (after the `RESEARCH_CLASSIFICATION_MODEL` line, ~line 305), add:

```python
    # Tavily Search Research (iterative search + LLM refinement)
    TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
    SEARCH_RESEARCH_ENABLED = bool(os.environ.get("TAVILY_API_KEY", ""))
    SEARCH_RESEARCH_MAX_ROUNDS = _safe_int(
        os.environ.get("SEARCH_RESEARCH_MAX_ROUNDS", "3"),
        3,
        env_key="SEARCH_RESEARCH_MAX_ROUNDS",
    )
    SEARCH_RESEARCH_QUALITY_THRESHOLD = _safe_float(
        os.environ.get("SEARCH_RESEARCH_QUALITY_THRESHOLD", "7.5"),
        7.5,
        env_key="SEARCH_RESEARCH_QUALITY_THRESHOLD",
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/user/GlasIntelligence/backend
python -m pytest tests/test_config_tavily.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_config_tavily.py
git commit -m "feat: add TAVILY_API_KEY and SEARCH_RESEARCH_ENABLED to Config"
```

---

### Task 3: Create SearchResearchAgent

**Files:**
- Create: `backend/app/services/search_research_agent.py`
- Create: `backend/tests/test_search_research_agent.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_search_research_agent.py
from unittest.mock import patch, MagicMock
import pytest

from app.services.search_research_agent import SearchResearchAgent

_SYNTHESIS_MD = (
    "## Background & Context\nSome background.\n\n"
    "## Key Facts Summary\n- Fact one: 42%\n- Fact two: 100bn\n\n"
    "## Historical Precedents\n- Event A occurred in 2020\n\n"
    "## Quantitative Anchors\n- 42% market share (2023)\n"
)

_PRECEDENTS_RESPONSE = {
    "precedents": [
        {
            "event": "Event A",
            "outcome": "Resolved",
            "timeline": "2020",
            "relevance_score": 0.8,
            "key_metric": "42%",
            "source_url": "",
        }
    ]
}


@patch("app.services.search_research_agent.TavilyClient")
@patch("app.services.search_research_agent.LLMClient")
def test_run_returns_correct_dossier_schema(MockLLM, MockTavily):
    mock_llm = MagicMock()
    MockLLM.return_value = mock_llm
    mock_llm.chat.side_effect = ['["query one", "query two"]', _SYNTHESIS_MD]
    mock_llm.chat_json.side_effect = [
        {"score": 9.0, "gaps": [], "follow_up_queries": []},
        _PRECEDENTS_RESPONSE,
    ]

    mock_tavily = MagicMock()
    MockTavily.return_value = mock_tavily
    mock_tavily.search.return_value = [
        {"title": "Article A", "url": "https://example.com/a", "content": "Content A"},
    ]

    agent = SearchResearchAgent()
    result = agent.run("test scenario about trade wars")

    assert result["summary_md"] == _SYNTHESIS_MD
    assert isinstance(result["sources"], list)
    assert result["sources"][0]["url"] == "https://example.com/a"
    assert isinstance(result["key_facts"], list)
    assert "Fact one: 42%" in result["key_facts"]
    assert isinstance(result["search_queries"], list)
    assert "query one" in result["search_queries"]
    assert isinstance(result["historical_precedents"], list)
    assert isinstance(result["structured_precedents"], list)
    assert isinstance(result["selected_angles"], list)


@patch("app.services.search_research_agent.TavilyClient")
@patch("app.services.search_research_agent.LLMClient")
def test_iterates_when_score_below_threshold(MockLLM, MockTavily):
    mock_llm = MagicMock()
    MockLLM.return_value = mock_llm
    # chat: generate_queries (round1), synthesize (round1), synthesize (round2)
    mock_llm.chat.side_effect = ['["initial query"]', _SYNTHESIS_MD, _SYNTHESIS_MD]
    # chat_json: critique (round1 — low score), critique (round2 — high), structure_precedents
    mock_llm.chat_json.side_effect = [
        {"score": 5.0, "gaps": ["missing GDP data"], "follow_up_queries": ["GDP query"]},
        {"score": 8.5, "gaps": [], "follow_up_queries": []},
        _PRECEDENTS_RESPONSE,
    ]

    mock_tavily = MagicMock()
    MockTavily.return_value = mock_tavily
    mock_tavily.search.return_value = [
        {"title": "T", "url": "https://x.com/1", "content": "C"}
    ]

    agent = SearchResearchAgent()
    result = agent.run("scenario needing iteration")

    # Tavily must have been called for both the initial query AND the gap query
    assert mock_tavily.search.call_count >= 2
    assert result["summary_md"] == _SYNTHESIS_MD


@patch("app.services.search_research_agent.TavilyClient")
@patch("app.services.search_research_agent.LLMClient")
def test_stops_at_max_rounds_even_if_score_low(MockLLM, MockTavily):
    mock_llm = MagicMock()
    MockLLM.return_value = mock_llm
    # Always generates queries and synthesis
    mock_llm.chat.return_value = _SYNTHESIS_MD
    # Always returns low score with follow-up queries
    mock_llm.chat_json.return_value = {
        "score": 3.0,
        "gaps": ["gap"],
        "follow_up_queries": ["follow up"],
    }

    mock_tavily = MagicMock()
    MockTavily.return_value = mock_tavily
    mock_tavily.search.return_value = []

    with patch("app.config.Config.SEARCH_RESEARCH_MAX_ROUNDS", 2):
        agent = SearchResearchAgent()
        result = agent.run("scenario")

    # Should have synthesized exactly max_rounds times, not looped forever
    assert mock_llm.chat.call_count <= 4  # generate_queries + synthesize per round


@patch("app.services.search_research_agent.TavilyClient")
@patch("app.services.search_research_agent.LLMClient")
def test_deduplicates_sources(MockLLM, MockTavily):
    mock_llm = MagicMock()
    MockLLM.return_value = mock_llm
    mock_llm.chat.side_effect = ['["q1"]', _SYNTHESIS_MD, _SYNTHESIS_MD]
    mock_llm.chat_json.side_effect = [
        {"score": 4.0, "gaps": ["g"], "follow_up_queries": ["q2"]},
        {"score": 9.0, "gaps": [], "follow_up_queries": []},
        _PRECEDENTS_RESPONSE,
    ]

    mock_tavily = MagicMock()
    MockTavily.return_value = mock_tavily
    # Both rounds return the same URL
    mock_tavily.search.return_value = [
        {"title": "Same", "url": "https://same.com", "content": "C"}
    ]

    agent = SearchResearchAgent()
    result = agent.run("dedupe test")

    urls = [s["url"] for s in result["sources"]]
    assert urls.count("https://same.com") == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/user/GlasIntelligence/backend
python -m pytest tests/test_search_research_agent.py -v
```

Expected: `ImportError` — `search_research_agent` doesn't exist yet.

- [ ] **Step 3: Write the implementation**

```python
# backend/app/services/search_research_agent.py
"""Research agent: Tavily web search + iterative LLM synthesis/critique loop."""
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

_ANGLE_HEADER = (
    "\nThe following research angles are particularly relevant. Include dedicated sections for each:\n"
)

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


class SearchResearchAgent:
    """Research agent: Tavily search + iterative LLM synthesis and critique."""

    def run(
        self,
        scenario: str,
        context: str = "",
        angle_overrides: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        llm = LLMClient()
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

            search_context = self._format_results(all_sources)
            summary_md = self._synthesize(llm, system_prompt, scenario, context, search_context)

            critique = self._critique(llm, scenario, summary_md)
            score = float(critique.get("score", 10.0))
            follow_up_queries = critique.get("follow_up_queries") or []

            logger.info("Round %d critique score: %.1f", round_num, score)

            if score >= threshold or round_num >= max_rounds or not follow_up_queries:
                break

        if not summary_md.strip():
            raise RuntimeError("SearchResearchAgent returned empty summary_md")

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
        }

    @staticmethod
    def _generate_queries(llm: LLMClient, scenario: str) -> list[str]:
        raw = llm.chat(
            messages=[
                {"role": "system", "content": _QUERY_SYSTEM},
                {"role": "user", "content": f"Scenario: {scenario}"},
            ],
            temperature=0.3,
            max_tokens=512,
        )
        try:
            queries = json.loads(raw)
            if isinstance(queries, list):
                return [str(q) for q in queries[:6] if q]
        except (json.JSONDecodeError, ValueError):
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
            max_tokens=4096,
        )

    @staticmethod
    def _critique(llm: LLMClient, scenario: str, summary_md: str) -> dict:
        try:
            return llm.chat_json(
                messages=[
                    {"role": "system", "content": _CRITIQUE_SYSTEM},
                    {
                        "role": "user",
                        "content": f"Scenario: {scenario}\n\n[Dossier]\n{summary_md[:6000]}",
                    },
                ],
                temperature=0.2,
                max_tokens=512,
            )
        except Exception as exc:
            logger.warning("Critique call failed: %s", exc)
            return {"score": 10.0, "gaps": [], "follow_up_queries": []}

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/user/GlasIntelligence/backend
python -m pytest tests/test_search_research_agent.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/search_research_agent.py backend/tests/test_search_research_agent.py
git commit -m "feat: add SearchResearchAgent with Tavily search and iterative LLM refinement"
```

---

### Task 4: Wire SearchResearchAgent into research_tasks.py

**Files:**
- Modify: `backend/app/tasks/research_tasks.py` (lines 64–71)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_search_research_routing.py
from unittest.mock import patch, MagicMock

_GOOD_DOSSIER = {
    "summary_md": "# Report\n\nContent here",
    "sources": [],
    "key_facts": [],
    "historical_precedents": [],
    "quantitative_anchors": [],
    "structured_precedents": [],
    "search_queries": [],
    "selected_angles": [],
}


def _make_mock_agent(dossier):
    mock_agent = MagicMock()
    mock_agent.run.return_value = dossier
    return mock_agent


def test_search_agent_selected_when_tavily_key_set():
    with (
        patch("app.config.Config.DEEP_RESEARCH_ENABLED", False),
        patch("app.config.Config.SEARCH_RESEARCH_ENABLED", True),
        patch("app.config.Config.TAVILY_API_KEY", "tv-test"),
        patch("app.services.supabase_client.SupabaseDB.get_session",
              return_value={"research_status": "pending"}),
        patch("app.services.supabase_client.SupabaseDB.update_session"),
        patch(
            "app.tasks.research_tasks.SearchResearchAgent",
            return_value=_make_mock_agent(_GOOD_DOSSIER),
        ) as MockSearch,
    ):
        from app.tasks.research_tasks import run_deep_research_task
        run_deep_research_task("session-1", "test scenario", "user-1")
        MockSearch.assert_called_once()


def test_llm_agent_selected_when_no_tavily_key():
    with (
        patch("app.config.Config.DEEP_RESEARCH_ENABLED", False),
        patch("app.config.Config.SEARCH_RESEARCH_ENABLED", False),
        patch("app.services.supabase_client.SupabaseDB.get_session",
              return_value={"research_status": "pending"}),
        patch("app.services.supabase_client.SupabaseDB.update_session"),
        patch(
            "app.tasks.research_tasks.LLMResearchAgent",
            return_value=_make_mock_agent(_GOOD_DOSSIER),
        ) as MockLLM,
    ):
        from app.tasks.research_tasks import run_deep_research_task
        run_deep_research_task("session-1", "test scenario", "user-1")
        MockLLM.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/user/GlasIntelligence/backend
python -m pytest tests/test_search_research_routing.py -v
```

Expected: first test fails — `SearchResearchAgent` import branch doesn't exist in `research_tasks.py`.

- [ ] **Step 3: Update research_tasks.py**

Replace lines 64–71 in `backend/app/tasks/research_tasks.py` (the `if/else` agent selection block):

```python
        if Config.DEEP_RESEARCH_ENABLED:
            from ..services.deep_research_agent import DeepResearchAgent

            agent = DeepResearchAgent()
        elif Config.SEARCH_RESEARCH_ENABLED:
            from ..services.search_research_agent import SearchResearchAgent

            agent = SearchResearchAgent()
        else:
            from ..services.llm_research_agent import LLMResearchAgent

            agent = LLMResearchAgent()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/user/GlasIntelligence/backend
python -m pytest tests/test_search_research_routing.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
cd /home/user/GlasIntelligence/backend
python -m pytest tests/ -v --ignore=tests/integration
```

Expected: all existing tests pass, 4 new test files pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/tasks/research_tasks.py backend/tests/test_search_research_routing.py
git commit -m "feat: route research tasks through SearchResearchAgent when TAVILY_API_KEY set"
```

---

## Self-Review

**Spec coverage:**
- ✅ `TavilyClient` HTTP wrapper for Tavily REST API
- ✅ LLM generates initial 4-6 search queries from scenario
- ✅ Tavily search executed per query, results collected
- ✅ LLM synthesizes full dossier markdown from search results
- ✅ LLM self-critique returns JSON `{score, gaps, follow_up_queries}`
- ✅ Loop re-searches with follow-up queries if score < 7.5
- ✅ Max 3 rounds cap enforced
- ✅ Returns identical dossier schema to `LLMResearchAgent`
- ✅ `TAVILY_API_KEY` config key; `SEARCH_RESEARCH_ENABLED` auto-derived
- ✅ `SEARCH_RESEARCH_MAX_ROUNDS` and `SEARCH_RESEARCH_QUALITY_THRESHOLD` configurable
- ✅ `research_tasks.py` third branch wires it all together
- ✅ Source deduplication by URL

**Placeholder scan:** No TODOs, TBDs, or "similar to above" references found.

**Type consistency:**
- `TavilyClient.search()` → `list[dict]` with keys `title`, `url`, `content` — consistent across client, agent formatting, and tests
- `LLMClient.chat()` → `str`; `LLMClient.chat_json()` → `dict` — used correctly throughout
- Dossier dict keys: `sources`, `key_facts`, `historical_precedents`, `quantitative_anchors`, `structured_precedents`, `summary_md`, `search_queries`, `selected_angles` — exactly match `LLMResearchAgent.run()` return value
- `LLMResearchAgent._resolve_angles`, `._extract_key_facts`, `._extract_section`, `._structure_precedents` are `@staticmethod` — called correctly as `LLMResearchAgent._method(...)` without `self`
