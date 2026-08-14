"""Tests for research_agent_chain() config-driven agent selection."""

from unittest.mock import patch

from app.services.research_router import research_agent_chain


def test_deep_research_selected_when_enabled():
    with (
        patch("app.config.Config.DEEP_RESEARCH_ENABLED", True),
        patch("app.config.Config.SEARCH_RESEARCH_ENABLED", False),
    ):
        agents = research_agent_chain()

    assert len(agents) == 1
    assert type(agents[0]).__name__ == "DeepResearchAgent"


def test_search_chain_selected_when_tavily_key_set():
    with (
        patch("app.config.Config.DEEP_RESEARCH_ENABLED", False),
        patch("app.config.Config.SEARCH_RESEARCH_ENABLED", True),
    ):
        agents = research_agent_chain()

    names = [type(a).__name__ for a in agents]
    assert names == ["SearchResearchAgent", "LLMResearchAgent"]


def test_llm_agent_selected_when_no_search_backend():
    with (
        patch("app.config.Config.DEEP_RESEARCH_ENABLED", False),
        patch("app.config.Config.SEARCH_RESEARCH_ENABLED", False),
    ):
        agents = research_agent_chain()

    assert len(agents) == 1
    assert type(agents[0]).__name__ == "LLMResearchAgent"
