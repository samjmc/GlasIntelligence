"""Readers after twitter was dropped: a reddit-only run must not show an empty twitter side,
and a run saved before the drop (both platforms) must read exactly as before."""

from __future__ import annotations

from app.services.quantitative_analysis_service import SimulationMetrics
from app.services.zep_tools import platform_response_text


def test_interview_text_reddit_only_has_no_twitter_section():
    assert platform_response_text("", "Fees are too low.") == "[Reddit Platform Response]\nFees are too low."


def test_interview_text_two_platforms_keeps_both_sections():
    assert platform_response_text("Short take.", "Long take.") == (
        "[Twitter Platform Response]\nShort take.\n\n[Reddit Platform Response]\nLong take."
    )


def test_interview_text_no_answer():
    assert platform_response_text("", "") == "(No response received from this platform)"


def _metrics(twitter: int, reddit: int) -> SimulationMetrics:
    total = twitter + reddit
    return SimulationMetrics(
        total_actions=total,
        twitter_actions=twitter,
        reddit_actions=reddit,
        platform_ratio={"twitter": twitter / total * 100, "reddit": reddit / total * 100},
        most_active_agents=[
            {"agent_name": "NHSBSA", "total_actions": total, "twitter_actions": twitter, "reddit_actions": reddit}
        ],
    )


def test_metrics_text_reddit_only_never_mentions_twitter():
    text = _metrics(0, 12).to_text()
    assert "  Reddit: 12 (100.0%)" in text
    assert "NHSBSA: 12 actions\n" in text + "\n"
    assert "Twitter" not in text


def test_metrics_text_two_platforms_keeps_the_split():
    text = _metrics(3, 9).to_text()
    assert "  Twitter: 3 (25.0%)" in text
    assert "  Reddit: 9 (75.0%)" in text
    assert "NHSBSA: 12 actions (Twitter: 3, Reddit: 9)" in text
