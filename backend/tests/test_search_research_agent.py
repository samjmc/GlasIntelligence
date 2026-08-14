from unittest.mock import patch, MagicMock

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
    mock_tavily.search.return_value = [{"title": "T", "url": "https://x.com/1", "content": "C"}]

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
    # Always returns a query list and synthesis
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

    # Patch via the search_research_agent module's own Config reference so the patch
    # survives test_config_tavily's _reload_config() which replaces app.config.Config.
    with patch("app.services.search_research_agent.Config.SEARCH_RESEARCH_MAX_ROUNDS", 2):
        agent = SearchResearchAgent()
        result = agent.run("scenario")

    # Round 1: 1 (generate_queries fallback) + 1 (synthesize) = 2
    # Round 2: 0 (uses follow_up_queries) + 1 (synthesize) = 1
    # Total: 3 chat calls with max_rounds=2
    assert mock_llm.chat.call_count == 3


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
    mock_tavily.search.return_value = [{"title": "Same", "url": "https://same.com", "content": "C"}]

    agent = SearchResearchAgent()
    result = agent.run("dedupe test")

    urls = [s["url"] for s in result["sources"]]
    assert urls.count("https://same.com") == 1


_VERIFICATION_RESPONSE = {
    "verified_claims": [
        {"claim": "Fact one: 42%", "source_url": "https://example.com/a"},
    ],
    "unverified_claims": [
        {"claim": "Fact two: 100bn", "note": "not present in search results"},
    ],
    "corrections": [
        {"original": "42% market share", "corrected": "43% market share", "reason": "source reports 43%"},
    ],
}


@patch("app.services.search_research_agent.TavilyClient")
@patch("app.services.search_research_agent.LLMClient")
def test_verification_pass_appends_notes_to_dossier(MockLLM, MockTavily):
    mock_llm = MagicMock()
    MockLLM.return_value = mock_llm
    mock_llm.chat.side_effect = ['["query one"]', _SYNTHESIS_MD]
    mock_llm.chat_json.side_effect = [
        {"score": 9.0, "gaps": [], "follow_up_queries": []},
        _VERIFICATION_RESPONSE,
        _PRECEDENTS_RESPONSE,
    ]

    mock_tavily = MagicMock()
    MockTavily.return_value = mock_tavily
    mock_tavily.search.return_value = [
        {"title": "Article A", "url": "https://example.com/a", "content": "Content A"},
    ]

    agent = SearchResearchAgent()
    result = agent.run("test scenario about trade wars")

    assert "## Verification Notes" in result["summary_md"]
    assert "### Verified against search results" in result["summary_md"]
    assert "- Fact one: 42% — https://example.com/a" in result["summary_md"]
    assert "### Unverified claims" in result["summary_md"]
    assert "### Corrected claims" in result["summary_md"]
    assert "→ 43% market share" in result["summary_md"]
    assert result["verification"]["corrections"][0]["corrected"] == "43% market share"


@patch("app.services.search_research_agent.TavilyClient")
@patch("app.services.search_research_agent.LLMClient")
def test_verification_skipped_when_no_sources(MockLLM, MockTavily):
    mock_llm = MagicMock()
    MockLLM.return_value = mock_llm
    mock_llm.chat.side_effect = ['["query one"]', _SYNTHESIS_MD]
    mock_llm.chat_json.side_effect = [
        {"score": 9.0, "gaps": [], "follow_up_queries": []},
        _PRECEDENTS_RESPONSE,
    ]

    mock_tavily = MagicMock()
    MockTavily.return_value = mock_tavily
    mock_tavily.search.return_value = []

    agent = SearchResearchAgent()
    result = agent.run("scenario with no search hits")

    assert result["verification"] == {}
    assert "## Verification Notes" not in result["summary_md"]
    assert result["summary_md"] == _SYNTHESIS_MD


@patch("app.services.search_research_agent.TavilyClient")
@patch("app.services.search_research_agent.LLMClient")
def test_verification_failure_does_not_fail_run(MockLLM, MockTavily):
    mock_llm = MagicMock()
    MockLLM.return_value = mock_llm
    mock_llm.chat.side_effect = ['["query one"]', _SYNTHESIS_MD]
    mock_llm.chat_json.side_effect = [
        {"score": 9.0, "gaps": [], "follow_up_queries": []},
        RuntimeError("verification LLM down"),
        _PRECEDENTS_RESPONSE,
    ]

    mock_tavily = MagicMock()
    MockTavily.return_value = mock_tavily
    mock_tavily.search.return_value = [
        {"title": "Article A", "url": "https://example.com/a", "content": "Content A"},
    ]

    agent = SearchResearchAgent()
    result = agent.run("scenario")

    assert result["verification"] == {}
    assert result["summary_md"] == _SYNTHESIS_MD
