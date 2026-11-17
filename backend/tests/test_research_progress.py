"""The research briefing reports its progress, so the page does not sit on one message.

Seen live on 2026-11-17: a web-search briefing ran 3 rounds for about 5 minutes while the page
said "Classifying scenario and selecting research angles..." and promised about 30 seconds.
"""

import inspect
from unittest.mock import MagicMock, patch

from app.services import research_router
from app.services.deep_research_agent import DeepResearchAgent
from app.services.llm_research_agent import LLMResearchAgent
from app.services.search_research_agent import SearchResearchAgent

_SYNTHESIS_MD = "## Background & Context\nSome background.\n\n## Key Facts Summary\n- Fact one: 42%\n"


@patch("app.services.search_research_agent.TavilyClient")
@patch("app.services.search_research_agent.LLMClient")
def test_search_agent_reports_each_round(MockLLM, MockTavily):
    llm = MagicMock()
    MockLLM.return_value = llm
    llm.chat.side_effect = ['["q1", "q2"]', _SYNTHESIS_MD, _SYNTHESIS_MD]
    llm.chat_json.side_effect = [
        {"score": 3.0, "follow_up_queries": ["q3"]},
        {"score": 9.0, "follow_up_queries": []},
        {"precedents": []},
    ]
    MockTavily.return_value.search.return_value = [{"title": "A", "url": "https://example.com/a", "content": "x"}]
    messages: list[str] = []

    SearchResearchAgent().run("Revolut Mobile launches in Ireland", on_progress=messages.append)

    searching = [m for m in messages if m.startswith("Searching the web")]
    assert len(searching) == 2
    assert "round 1 of up to" in searching[0] and "round 2 of up to" in searching[1]
    assert any(m.startswith("Writing the briefing from") for m in messages)


def test_every_agent_in_the_chain_accepts_on_progress():
    # A run() without the parameter raises TypeError, which the chain treats as a failed agent
    # and silently skips to the next one.
    for agent_cls in (SearchResearchAgent, LLMResearchAgent, DeepResearchAgent):
        assert "on_progress" in inspect.signature(agent_cls.run).parameters, agent_cls.__name__


def test_chain_passes_on_progress_to_the_agent(monkeypatch):
    seen = {}

    class FakeAgent:
        def run(self, prompt, context="", angle_overrides=None, on_progress=None):
            seen["cb"] = on_progress
            return {"summary_md": "ok"}

    monkeypatch.setattr(research_router, "research_agent_chain", lambda: [FakeAgent()])
    cb = MagicMock()

    assert research_router.run_research_chain("scenario text", on_progress=cb) == {"summary_md": "ok"}
    assert seen["cb"] is cb
