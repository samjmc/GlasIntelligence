"""Tests for the entity knowledge-expansion pass."""

from unittest.mock import patch, MagicMock

from app.services.entity_expansion import expand_entities, _name_in_results


_CANDIDATES = {
    "candidates": [
        {
            "name": "PharmAssist Analytics",
            "type": "company",
            "role": "Pharmacy software vendor.",
            "verify_query": "PharmAssist Analytics pharmacy software UK",
        },
        {
            "name": "Totally Made Up Systems",
            "type": "company",
            "role": "Fake vendor.",
            "verify_query": "Totally Made Up Systems pharmacy",
        },
        {
            "name": "NHS England",
            "type": "regulator",
            "role": "Already in inventory.",
            "verify_query": "NHS England",
        },
    ]
}


def _results(*titles):
    return [{"title": t, "url": "", "content": "x"} for t in titles]


def test_name_match_in_results():
    assert _name_in_results("PharmAssist Analytics", _results("PharmAssist Analytics signs NHS deal"))
    assert not _name_in_results("Totally Made Up Systems", _results("Pharmacy software market report 2026"))


@patch("app.services.entity_expansion.TavilyClient")
@patch("app.services.entity_expansion.LLMClient")
def test_expansion_keeps_only_verified_and_unseen(MockLLM, MockTavily):
    mock_llm = MagicMock()
    MockLLM.return_value = mock_llm
    mock_llm.chat_json.return_value = _CANDIDATES

    mock_tavily = MagicMock()
    MockTavily.return_value = mock_tavily

    def fake_search(query, max_results=5):
        if "PharmAssist" in query:
            return _results("PharmAssist Analytics raises Series A for pharmacy software")
        return []

    mock_tavily.search.side_effect = fake_search

    additions = expand_entities("Pharmacy First scenario", "context", ["NHS England"], target=3)

    assert [a["name"] for a in additions] == ["PharmAssist Analytics"]
    assert additions[0]["category"] == "company"
    assert "Pharmacy software vendor" in additions[0]["context"]


@patch("app.services.entity_expansion.TavilyClient")
@patch("app.services.entity_expansion.LLMClient")
def test_expansion_fail_soft(MockLLM, MockTavily):
    mock_llm = MagicMock()
    MockLLM.return_value = mock_llm
    mock_llm.chat_json.side_effect = RuntimeError("LLM down")

    additions = expand_entities("scenario", "context", [])
    assert additions == []


@patch("app.services.entity_expansion.TavilyClient")
@patch("app.services.entity_expansion.LLMClient")
def test_expansion_deduplicates_case_insensitively(MockLLM, MockTavily):
    mock_llm = MagicMock()
    MockLLM.return_value = mock_llm
    mock_llm.chat_json.return_value = _CANDIDATES

    mock_tavily = MagicMock()
    MockTavily.return_value = mock_tavily
    mock_tavily.search.return_value = _results("nhs england guidance 2026")

    additions = expand_entities("scenario", "context", ["NHS England"], target=3)
    # 'NHS England' candidate is dropped (already in inventory) despite its
    # search matching; the unverified fake is dropped too.
    assert additions == []
