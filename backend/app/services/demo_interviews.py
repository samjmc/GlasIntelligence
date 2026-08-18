"""
Canned agent-interview responses for demo mode.

The static demo cannot interview live OASIS agents (the subprocess is gone),
so the backend serves pre-recorded, scenario-grounded Q&As instead. Each
response is written in the agent's persona and grounded in the Pharmacy First
funding-caps scenario (payment caps, the 2026/27 10% funding uplift, workload
absorption). Keyword matching picks the closest canned response; unknown
questions fall back to the agent's opening position with an explicit
"recorded response" note so a visitor never mistakes it for live output.

Shape matches the live ``interview/batch`` contract:
    {"success": true, "data": {"result": {"results": {
        "<platform>_<agent_id>": {"agent_id": N, "response": "...", "platform": "..."}
    }}}}
"""

# Agent ids in the V11 golden tape (0-14), keyed by username for readability.
AGENTS = {
    0: ("pharmacies_532", "the community pharmacy sector"),
    1: ("pharmacy_first_333", "the NHS Pharmacy First service"),
    2: ("care_boards_624", "NHS Integrated Care Boards"),
    3: ("ncpa_211", "independent community pharmacy"),
    4: ("nhs_england_578", "NHS England"),
    5: ("gps_250", "a GP in Leeds"),
    6: ("govuk_677", "GOV.UK"),
    7: ("pharmacists_292", "a community pharmacist"),
    8: ("national_center_for_healthcare_workforce_analysis_366", "workforce analysis"),
    9: ("cpe_867", "Community Pharmacy England"),
    10: ("greater_manchester_356", "community pharmacy in Greater Manchester"),
    11: ("priory_road_pcn_643", "a primary care network"),
    12: ("facebook_678", "Facebook"),
    13: ("the_pharmacist_316", "The Pharmacist publication"),
    14: ("ashp_560", "health-system pharmacy"),
}

# Keyword -> (agent_id, response). Responses are scenario-grounded and
# persona-consistent; the "recorded" phrasing is explicit so visitors know
# these are canned.
CANNED = {
    "cap": (
        0,
        "The payment caps are the crunch point for us. If NHS England pays for a "
        "fixed number of consultations and demand keeps rising, the extra workload "
        "lands on pharmacy teams with no funding behind it. We've absorbed cost "
        "pressures before — staff hours, stock, locum cover — but there's a limit. "
        "A cap without a matching uplift isn't a saving, it's a transfer of NHS "
        "costs onto community pharmacy. (Recorded response from the demo replay.)",
    ),
    "funding": (
        4,
        "The 2026/27 settlement includes a 10% funding uplift for community "
        "pharmacy, which is real progress, but it has to be read against the "
        "caps. The policy intent is to keep Pharmacy First consultations "
        "clinically appropriate rather than volume-driven. We're watching three "
        "metrics: consultation volumes, pharmacy participation, and patient "
        "access times. If caps bite harder than the uplift relieves, we adjust "
        "before the access story turns negative. (Recorded response from the "
        "demo replay.)",
    ),
    "gp": (
        5,
        "From the GP side, Pharmacy First is a genuine relief valve — every "
        "minor ailment that stays in the pharmacy is one less slot in my "
        "clinic. But it only works if the pharmacy can actually absorb that "
        "workload. If caps push consultations back toward general practice, "
        "the pressure we were told would ease comes straight back to us, "
        "with longer waits and more complex patients squeezed into the same "
        "appointments. (Recorded response from the demo replay.)",
    ),
    "workforce": (
        7,
        "The workforce question is the one nobody budgets for. Fourteen years "
        "on the frontline, and every funding round lands as more work per "
        "pharmacist. A consultation cap that reduces reimbursed volume doesn't "
        "reduce the actual demand — it just means the consultations happen "
        "without the payment attached. Pharmacists will stay and deliver "
        "because patients need us, but attrition is real, and it's the "
        "quietest cost in the whole policy. (Recorded response from the demo "
        "replay.)",
    ),
    "access": (
        1,
        "The access story is the good news we have to protect. Patients like "
        "Pharmacy First — no appointment, local, quick. The risk is that caps "
        "or funding pressure make pharmacies step back from delivering it, and "
        "then access reverses faster than it improved. The measure that matters "
        "isn't the cap level, it's whether consultations still happen and "
        "patients still get seen. (Recorded response from the demo replay.)",
    ),
    "independent": (
        3,
        "Independent pharmacies run on very thin margins, and a single "
        "contract change can decide whether a branch stays open. The caps "
        "frame is workable if the funding follows the workload, but if "
        "independents see the fixed payment shrink against rising demand, "
        "you'll see closures in the areas that need access most — the exact "
        "communities Pharmacy First was meant to help. (Recorded response "
        "from the demo replay.)",
    ),
}

DEFAULT_RESPONSE = (
    "That's beyond the questions recorded in this replay, but I can give you "
    "my opening position: the Pharmacy First caps will hold up only if the "
    "funding settlement keeps pace with consultation volumes. If it doesn't, "
    "the workload moves back to GPs, access erodes, and the policy's early "
    "gains get reversed. (Recorded response from the demo replay.)"
)


def _match_agent(agent_id: int) -> str:
    """Return the persona's name for a given agent id (fallback to generic)."""
    return AGENTS.get(int(agent_id), ("the agent", ""))[0]


def canned_response(agent_id: int, prompt: str, platform: str = "reddit") -> dict:
    """Return a canned interview result for one agent, shape-compatible with the live path."""
    prompt_lower = (prompt or "").lower()
    response = DEFAULT_RESPONSE
    for keyword, (kid, text) in CANNED.items():
        if keyword in prompt_lower:
            response = text
            break

    agent = _match_agent(agent_id)
    response = (
        f"[{agent}] {response}" if not response.startswith(f"[{agent}]") else response
    )

    return {
        "agent_id": int(agent_id),
        "response": response,
        "platform": platform,
    }


def canned_batch(simulation_id: str, interviews: list, platform: str | None = None) -> dict:
    """Build the batch result dict — mirrors the live interview/batch return shape."""
    results = {}
    for i, interview in enumerate(interviews):
        agent_id = interview["agent_id"]
        item_platform = interview.get("platform") or platform or "reddit"
        key = f"{item_platform}_{agent_id}"
        results[key] = canned_response(agent_id, interview["prompt"], item_platform)

    return {
        "success": True,
        "data": {
            "interviews_count": len(interviews),
            "result": {
                "interviews_count": len(interviews),
                "results": results,
            },
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        },
    }
