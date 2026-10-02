"""Write the Step 4 parser fixtures from the backend's own result classes.

The frontend parsers (frontend/src/components/step4/step4ReportParsers.js) read the text
these classes' to_text() produce. The demo tapes record interview and panorama results;
nothing records insight_forge or quick_search, and no tape has a reddit-only interview, so
those three come from here. Re-run after changing any to_text() format, and commit both:

    cd backend && uv run --frozen python scripts/gen_step4_parser_fixtures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.services.zep_tools import (  # noqa: E402
    AgentInterview,
    InsightForgeResult,
    InterviewResult,
    SearchResult,
    platform_response_text,
)

OUT = BACKEND.parent / "frontend" / "src" / "components" / "step4" / "__fixtures__" / "generatedToolResults.json"

FACTS = ["Caps start in March 2026.", "Band 6 is capped at 234."]


def main() -> None:
    insight = InsightForgeResult(
        query="How do pharmacies respond to the caps?",
        simulation_requirement="Pharmacy First payment caps",
        sub_queries=["Which pharmacies cut hours?", "Do GPs see more patients?"],
        semantic_facts=FACTS,
        entity_insights=[
            {"name": "NHSBSA", "type": "Organization", "summary": "Pays pharmacies.", "related_facts": FACTS}
        ],
        relationship_chains=["NHSBSA --[PAYS]--> Pharmacies"],
        total_facts=2,
        total_entities=1,
        total_relationships=1,
    )
    quick = SearchResult(facts=FACTS, edges=[], nodes=[], query="payment caps", total_count=2)
    questions = "1. What changes for you?\n2. What will you do next?"
    interview = InterviewResult(
        interview_topic="Payment caps",
        interview_questions=["What changes for you?", "What will you do next?"],
        selection_reasoning="Both agents handle Pharmacy First payments.",
        summary="Both agents expect fewer consultations.",
        total_agents=8,
        interviewed_count=2,
        interviews=[
            AgentInterview(
                agent_name="NHSBSA",
                agent_role="NHS payments body",
                agent_bio="Pays community pharmacies.",
                question=questions,
                response=platform_response_text(
                    "",
                    "Question 1: Payments are calculated only for consultations up to the cap.\n\n"
                    "Question 2: We will publish the bands.",
                ),
                key_quotes=["Payments are calculated only for consultations up to the cap."],
            ),
            AgentInterview(
                agent_name="Independent pharmacist",
                agent_role="Community pharmacist",
                agent_bio="Runs one rural pharmacy.",
                question=questions,
                response=platform_response_text(
                    "", "Question 1: Fewer paid consultations.\n\nQuestion 2: Cut opening hours."
                ),
            ),
        ],
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "insight_forge": insight.to_text(),
        "quick_search": quick.to_text(),
        "interview_reddit_only": interview.to_text(),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
