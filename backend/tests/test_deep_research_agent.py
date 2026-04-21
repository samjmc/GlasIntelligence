"""Tests for DeepResearchAgent._parse_response.

Covers the silent-empty-dossier failure mode: when the Responses API returns an
``incomplete`` response (e.g. it hit ``max_output_tokens`` mid-reasoning before
emitting any ``message`` item), we previously returned an empty ``summary_md``
and persisted a useless dossier. The hardened parser must now:

1. Fall back to ``response.output_text`` when iteration yields no message text.
2. Raise an explicit error when status != "completed" AND no text is available,
   so the Celery task refunds the credit instead of silently succeeding.
3. Keep working for the happy-path case where a message item is present.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.deep_research_agent import DeepResearchAgent


def _block(text: str, annotations: list | None = None) -> SimpleNamespace:
    return SimpleNamespace(type="output_text", text=text, annotations=annotations or [])


def _message(blocks: list[SimpleNamespace]) -> SimpleNamespace:
    return SimpleNamespace(type="message", content=blocks)


def _response(
    output: list,
    status: str = "completed",
    incomplete_reason: str | None = None,
    output_text: str = "",
    output_tokens: int | None = None,
) -> SimpleNamespace:
    incomplete = (
        SimpleNamespace(reason=incomplete_reason) if incomplete_reason else None
    )
    usage = SimpleNamespace(output_tokens=output_tokens) if output_tokens else None
    return SimpleNamespace(
        output=output,
        status=status,
        incomplete_details=incomplete,
        usage=usage,
        output_text=output_text,
    )


@pytest.fixture
def agent():
    """Bare agent — we don't construct via __init__ to avoid OpenAI client init."""
    a = DeepResearchAgent.__new__(DeepResearchAgent)
    a.model = "o4-mini-deep-research"
    a.max_tool_calls = 50
    a.max_output_tokens = 100000
    return a


def test_happy_path_concatenates_message_chunks(agent):
    """Multiple output_text blocks across messages are joined."""
    resp = _response(
        output=[
            _message([_block("First chunk.")]),
            _message([_block("Second chunk.")]),
        ],
        output_tokens=42,
    )
    result = agent._parse_response(resp)
    assert "First chunk." in result["summary_md"]
    assert "Second chunk." in result["summary_md"]


def test_incomplete_with_output_text_falls_back(agent):
    """If iteration finds no message but SDK aggregate has text, use the aggregate."""
    resp = _response(
        output=[SimpleNamespace(type="reasoning", content=[])],
        status="incomplete",
        incomplete_reason="max_output_tokens",
        output_text="Salvaged partial report from aggregate.",
        output_tokens=16000,
    )
    result = agent._parse_response(resp)
    assert result["summary_md"] == "Salvaged partial report from aggregate."


def test_incomplete_with_no_text_raises(agent):
    """status=incomplete + no text anywhere must fail loudly so credit is refunded."""
    resp = _response(
        output=[SimpleNamespace(type="reasoning", content=[])],
        status="incomplete",
        incomplete_reason="max_output_tokens",
        output_text="",
        output_tokens=16000,
    )
    with pytest.raises(RuntimeError, match="status=incomplete"):
        agent._parse_response(resp)


def test_completed_with_empty_message_returns_empty_md(agent):
    """status=completed but no text — return empty md so research_tasks treats as failure."""
    resp = _response(output=[_message([])], status="completed", output_text="")
    result = agent._parse_response(resp)
    assert result["summary_md"] == ""


def test_sources_extracted_from_annotations(agent):
    """URL annotations on output_text blocks become sources."""
    annotations = [
        SimpleNamespace(url="https://example.com/a", title="A"),
        SimpleNamespace(url="https://example.com/b", title="B"),
        SimpleNamespace(url="https://example.com/a", title="dup"),
    ]
    resp = _response(output=[_message([_block("body", annotations=annotations)])])
    result = agent._parse_response(resp)
    urls = [s["url"] for s in result["sources"]]
    assert urls == ["https://example.com/a", "https://example.com/b"]


def test_search_queries_collected(agent):
    """web_search_call items contribute their query string."""
    resp = _response(
        output=[
            SimpleNamespace(type="web_search_call", query="hello world", input=None),
            SimpleNamespace(type="web_search_call", query=None, input="fallback"),
            _message([_block("body")]),
        ]
    )
    result = agent._parse_response(resp)
    assert "hello world" in result["search_queries"]
    assert "fallback" in result["search_queries"]
