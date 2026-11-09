"""A briefing written without web search says so in the document itself.

Live 2026-11-09: TAVILY_API_KEY is not set on the server, so the no-upload "research briefing"
was pure LLM text with no sources, yet its claims ("GoMo frequently runs €9.99-€12.99 offers")
were later treated as retrieved facts. The filename prefixes (briefing_ / deep_research_) stay.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.api import source_agent
from app.services.llm_research_agent import UNVERIFIED_BRIEFING_HEADER, UNVERIFIED_FACT_PREFIX, LLMResearchAgent
from app.services.supabase_client import SupabaseDB

_MD = "## Background & Context\nGoMo frequently runs €9.99 offers.\n\n## Key Facts Summary\n- GoMo: €9.99/month\n"


@patch("app.services.llm_research_agent.LLMClient")
def test_llm_only_dossier_carries_the_unverified_header_and_flags_its_facts(MockLLM):
    llm = MagicMock()
    MockLLM.return_value = llm
    llm.chat.return_value = _MD
    llm.chat_json.return_value = {"precedents": []}

    result = LLMResearchAgent().run("Revolut launches Revolut Mobile in Ireland")

    assert result["summary_md"].splitlines()[0] == UNVERIFIED_BRIEFING_HEADER
    assert "not checked against web sources. Treat figures as unverified." in UNVERIFIED_BRIEFING_HEADER
    assert result["sources"] == []
    assert result["key_facts"] == [UNVERIFIED_FACT_PREFIX + "GoMo: €9.99/month"]
    system_prompt = llm.chat.call_args.kwargs["messages"][0]["content"]
    assert "NO web access" in system_prompt and "(unverified)" in system_prompt


def test_auto_research_briefing_document_starts_with_the_unverified_header(api, monkeypatch):
    monkeypatch.setattr(SupabaseDB, "get_profile", classmethod(lambda cls, uid: {"plan": "pro"}))
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=_MD))]
    )
    monkeypatch.setattr(source_agent, "_get_llm_client", lambda: client)

    resp = api.post("/api/source/auto-research", json={"prompt": "Revolut launches Revolut Mobile in Ireland"})

    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()["data"]
    assert data["content_md"].splitlines()[0] == UNVERIFIED_BRIEFING_HEADER
    assert data["content_md"].endswith(_MD)
    assert data["filename"].startswith("briefing_")
    system_prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "NO web access" in system_prompt
