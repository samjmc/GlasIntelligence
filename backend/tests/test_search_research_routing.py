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
        patch("app.services.supabase_client.SupabaseDB.get_session",
              return_value={"research_status": "pending"}),
        patch("app.services.supabase_client.SupabaseDB.update_session"),
        patch(
            "app.services.search_research_agent.SearchResearchAgent",
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
            "app.services.llm_research_agent.LLMResearchAgent",
            return_value=_make_mock_agent(_GOOD_DOSSIER),
        ) as MockLLM,
    ):
        from app.tasks.research_tasks import run_deep_research_task
        run_deep_research_task("session-1", "test scenario", "user-1")
        MockLLM.assert_called_once()
