"""Report-quality guards, one block per defect seen in two live reports (2026-11).

A: Irish EUR 5 disposable-vape minimum price. B: Revolut Mobile launch in Ireland.
Modules are imported whole (not names) so each test fails on its own when its fix is reverted.
No network: the LLM is a MagicMock and the simulation files are patched or written to tmp_path.
"""

import json
import re
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import config as app_config
from app.models.project import Project, ProjectStatus
from app.services import grounding_bundle
from app.services import monte_carlo_engine as mce
from app.services import quantitative_analysis_service as qas
from app.services import report_agent as ra
from app.services import report_payload as rp

# Report B, section "Risk Matrix and Recommendations": the whole section content as shipped.
DSML_FIXTURE = (
    "Let me get first-person risk and mitigation statements from the key agents.\n\n"
    "<｜｜DSML｜｜ calls>\n"
    '<｜｜DSML｜｜ invoke name="interview_agents">\n'
    '<｜｜DSML｜｜ parameter name="topic" string="true">What are the biggest risks you see in '
    "the Revolut Mobile launch, and what would you do to mitigate them?</｜｜DSML｜｜ parameter>\n"
    '<｜｜DSML｜｜ parameter name="max_agents" string="false">6</｜｜DSML｜｜ parameter>\n'
    "</｜｜DSML｜｜ invoke>\n"
    "</｜｜DSML｜｜ calls>"
)
DSML_TOPIC = "What are the biggest risks you see in the Revolut Mobile launch, and what would you do to mitigate them?"
# Same markup, but naming a tool the agent does not have, so it cannot be parsed into a call.
UNKNOWN_TOOL_MARKUP = DSML_FIXTURE.replace('name="interview_agents"', 'name="web_search"')
TOOL_CALL = '<tool_call>{"name": "quick_search", "parameters": {"query": "risks"}}</tool_call>'
FORECAST_WORDS = re.compile(r"forecast|predict", re.IGNORECASE)


def _agent(monkeypatch, responses=(), *, payload_v1=False):
    monkeypatch.setattr(app_config.Config, "ENABLE_REPORT_PAYLOAD_V1", payload_v1)
    llm = MagicMock()
    llm.chat.side_effect = list(responses)
    agent = ra.ReportAgent(
        graph_id="g",
        simulation_id="s",
        simulation_requirement="Revolut Mobile launches in Ireland",
        llm_client=llm,
        zep_tools=MagicMock(),
    )
    return agent, llm


def _run_section(agent):
    section = ra.ReportSection(title="Risk Matrix and Recommendations", role="general")
    outline = ra.ReportOutline(title="Report", summary="Summary", sections=[section])
    return agent._generate_section_react(section=section, outline=outline, previous_sections=[])


def _user_messages(llm):
    return [m["content"] for c in llm.chat.call_args_list for m in c.kwargs["messages"] if m["role"] == "user"]


# ====================================================================== 1. raw tool-call markup


def test_dsml_fixture_parses_into_a_tool_call(monkeypatch):
    agent, _llm = _agent(monkeypatch)
    assert agent._parse_tool_calls(DSML_FIXTURE) == [
        {"name": "interview_agents", "parameters": {"topic": DSML_TOPIC, "max_agents": 6}}
    ]


def test_dsml_tool_call_runs_and_is_never_the_section(monkeypatch):
    agent, llm = _agent(monkeypatch, [TOOL_CALL] * 3 + [DSML_FIXTURE, "Final Answer: Mitigation prose."])
    execute = MagicMock(return_value="tool result")
    monkeypatch.setattr(agent, "_execute_tool", execute)

    assert _run_section(agent) == "Mitigation prose."

    assert execute.call_args_list[3].args[:2] == ("interview_agents", {"topic": DSML_TOPIC, "max_agents": 6})
    assert llm.chat.call_count == 5


def test_unparseable_markup_is_reprompted_not_adopted(monkeypatch):
    agent, llm = _agent(monkeypatch, [TOOL_CALL] * 3 + [UNKNOWN_TOOL_MARKUP, "Final Answer: Clean prose."])
    monkeypatch.setattr(agent, "_execute_tool", MagicMock(return_value="tool result"))

    assert _run_section(agent) == "Clean prose."
    assert ra.REACT_TOOL_MARKUP_MSG in _user_messages(llm)


def test_markup_inside_final_answer_is_reprompted(monkeypatch):
    agent, llm = _agent(
        monkeypatch, [TOOL_CALL] * 3 + ["Final Answer: Intro.\n" + UNKNOWN_TOOL_MARKUP, "Final Answer: Clean."]
    )
    monkeypatch.setattr(agent, "_execute_tool", MagicMock(return_value="tool result"))

    assert _run_section(agent) == "Clean."
    assert ra.REACT_TOOL_MARKUP_MSG in _user_messages(llm)


def test_markup_is_stripped_when_retries_run_out(monkeypatch):
    agent, _llm = _agent(monkeypatch, [UNKNOWN_TOOL_MARKUP] * 9)  # 8 loop turns + the forced final
    monkeypatch.setattr(agent, "_execute_tool", MagicMock(return_value="tool result"))

    content = _run_section(agent)

    assert "DSML" not in content and "Let me" not in content and "invoke" not in content
    assert content == ra.SECTION_UNAVAILABLE_MSG


def test_strip_keeps_real_prose():
    stripped = ra.strip_tool_markup("Operators priced defensively.\n\n" + DSML_FIXTURE)
    assert stripped == "Operators priced defensively."
    assert not ra.contains_tool_markup(stripped)
    assert ra.contains_tool_markup(DSML_FIXTURE) and ra.contains_tool_markup(TOOL_CALL)
    assert not ra.contains_tool_markup("Vodafone's parameters were unchanged; invoke the fallback plan.")


def test_chat_reply_never_shows_tool_markup(monkeypatch):
    agent, _llm = _agent(monkeypatch, ["Operators priced defensively.\n\n" + UNKNOWN_TOOL_MARKUP])
    monkeypatch.setattr(ra.ReportManager, "get_report_by_simulation", classmethod(lambda cls, sid: None))
    assert agent.chat("What are the risks?")["response"] == "Operators priced defensively."


# ====================================================================== 2. forecast framing


def _plan(monkeypatch, llm_outline, *, agents=83, rounds=10):
    agent, llm = _agent(monkeypatch, payload_v1=True)
    llm.chat_json.return_value = llm_outline
    agent.zep_tools.get_simulation_context.return_value = {"graph_statistics": {"total_nodes": 105}}
    monkeypatch.setattr(
        agent.quant_service,
        "simulation_metrics",
        lambda _sid: qas.SimulationMetrics(total_agents=agents, total_rounds=rounds),
    )
    return agent.plan_outline(), llm


def _v1_outline(title, summary):
    return {
        "title": title,
        "summary": summary,
        "sections": [
            {"role": r, "title": r.replace("_", " ").title(), "description": ""} for r in ra.OUTLINE_REQUIRED_ROLES
        ],
    }


def test_llm_forecast_title_is_rewritten(monkeypatch):
    outline, _llm = _plan(
        monkeypatch,
        _v1_outline(
            "Revolut Mobile Ireland Launch: Six-Month Market Reaction Forecast",
            "The predicted net position favours incumbents.",
        ),
    )
    assert outline.title == "Revolut Mobile Ireland Launch: Six-Month Market Reaction Rehearsal"
    assert outline.summary == "The simulated net position favours incumbents."


def test_predictive_title_is_rewritten():
    outline = ra.ReportOutline(
        title="Ireland's EUR 5 Disposable Vape Minimum Price: Predictive Impact Rehearsal (2027)",
        summary="Not a forecast: this is not a forecast of 2027.",
        sections=[ra.ReportSection(title="Predicted retail response")],
    )
    ra.sanitise_outline(outline, None)
    assert outline.title == "Ireland's EUR 5 Disposable Vape Minimum Price: Simulated Impact Rehearsal (2027)"
    assert outline.summary == "Not a forecast: this is not a forecast of 2027."  # negations stay
    assert outline.sections[0].title == "Simulated retail response"


def test_default_outlines_and_prompts_do_not_say_forecast(monkeypatch):
    agent, _llm = _agent(monkeypatch)
    default = agent._default_outline_v1()
    assert not FORECAST_WORDS.search(default.title + default.summary)
    prompts = (ra.PLAN_SYSTEM_PROMPT, ra.PLAN_SYSTEM_PROMPT_V1, ra.PLAN_USER_PROMPT_TEMPLATE)
    for prompt in (*prompts, ra.SECTION_SYSTEM_PROMPT_TEMPLATE):
        assert "Predictive Analysis Report" not in prompt
        assert "ARE the predicted future" not in prompt
        assert "predictions of future group behaviour" not in prompt
    assert "NOT a forecast" in ra.PLAN_SYSTEM_PROMPT_V1


# ====================================================================== 3. simulated quotes


def test_unlabelled_blockquotes_get_the_simulated_label():
    content = (
        "Vodafone's position captures the hedge precisely:\n\n"
        "> We will match any price Revolut sets.\n> Customers will not wait.\n\n"
        "More prose.\n\n"
        '> Simulated response from GoMo (agent): "Prices hold."\n\n'
        "Simulated response from ComReg (agent):\n\n"
        "> Switching rules apply to everyone."
    )
    out = ra.label_simulated_quotes(content)
    assert "> Customers will not wait. " + ra.SIMULATED_QUOTE_LABEL in out
    assert "> We will match any price Revolut sets.\n" in out  # label on the block's last line only
    assert out.count(ra.SIMULATED_QUOTE_LABEL) == 1  # the two labelled quotes are left alone


def test_interview_output_carries_the_simulated_header(monkeypatch):
    agent, _llm = _agent(monkeypatch)
    agent.zep_tools.interview_agents.return_value = SimpleNamespace(to_text=lambda: "transcript")

    out = agent._execute_tool("interview_agents", {"topic": "risks", "max_agents": 6})

    assert out == ra.SIMULATED_INTERVIEW_HEADER + "transcript"
    assert agent.zep_tools.interview_agents.call_args.kwargs["interview_requirement"] == "risks"
    assert "Never name a real individual person" in out


def test_section_prompt_requires_labels_and_role_names():
    prompt = ra.SECTION_SYSTEM_PROMPT_TEMPLATE
    assert "Simulated response from <organisation or role> (agent):" in prompt
    assert "NEVER name a real individual person" in prompt
    assert "legal, regulatory or court finding" in prompt
    assert "Real Agent Interviews" not in ra.TOOL_DESC_INTERVIEW_AGENTS


# ====================================================================== 4. probabilities


def test_mutually_exclusive_ranges_sum_to_100():
    out = mce.normalise_exclusive_ranges([(40, 49.9, 60), (20, 30, 40), (15, 25, 35), (8, 15.8, 25)])
    assert sum(mid for _low, mid, _high in out) == 100
    assert all(low <= mid <= high and isinstance(mid, int) for low, mid, high in out)
    assert mce.normalise_exclusive_ranges([(0, 0, 0)]) is None


def test_scenario_ladder_midpoints_sum_to_100():
    llm = MagicMock()
    llm.chat_json.return_value = {
        "scenarios": [
            {"name": "Base", "probability_range": {"low": 50, "mid": 60, "high": 70}},
            {"name": "Upside", "probability_range": {"low": 25, "mid": 35, "high": 45}},
            {"name": "Stress", "probability_range": {"low": 10, "mid": 20, "high": 30}},
        ]
    }
    scenarios = rp.generate_scenario_ladder_json(llm, "req", "quant", "risk")

    mids = [s["probability_range"]["mid"] for s in scenarios]
    assert sum(mids) == 100 and mids == [52, 31, 17]  # 60/35/20 (115%) scaled by 100/115
    for s in scenarios:
        pr = s["probability_range"]
        assert pr["low"] <= pr["mid"] <= pr["high"]
    assert "sum to 100" in llm.chat_json.call_args.kwargs["messages"][0]["content"]
    assert "midpoints sum to 100%" in rp.render_scenarios_markdown(scenarios)


def _assess(monkeypatch, estimates, **kwargs):
    monkeypatch.setattr(app_config.Config, "ENABLE_CALIBRATION_GUARDRAILS", False)
    llm = MagicMock()
    llm.chat_json.return_value = {"estimates": estimates}
    return qas.QuantitativeAnalysisService(llm_client=llm).probability_assessment("scenario", **kwargs), llm


VAPE_OUTCOMES = [  # Report A: four alternatives summing to ~120%
    ("Implemented as planned", 40, 49.9, 60),
    ("Delayed beyond Jan 2027", 20, 30.0, 40),
    ("Implemented with amendments", 15, 25.0, 35),
    ("Abandoned", 8, 15.8, 25),
]


def test_exclusive_outcomes_are_normalised(monkeypatch):
    result, _llm = _assess(
        monkeypatch,
        [
            {
                "outcome": o,
                "exclusive_group": "implementation",
                "probability_low": lo,
                "probability_mid": mid,
                "probability_high": hi,
            }
            for o, lo, mid, hi in VAPE_OUTCOMES
        ],
    )
    assert sum(e.probability_mid for e in result.estimates) == 100
    text = result.to_text()
    assert "Mutually exclusive alternatives (implementation)" in text
    assert "never add, sum or combine" in text


def test_independent_outcomes_are_kept_and_marked(monkeypatch):
    result, _llm = _assess(
        monkeypatch,
        [
            {
                "outcome": o,
                "exclusive_group": None,
                "probability_low": lo,
                "probability_mid": mid,
                "probability_high": hi,
            }
            for o, lo, mid, hi in VAPE_OUTCOMES
        ],
    )
    assert [e.probability_mid for e in result.estimates] == [49.9, 30.0, 25.0, 15.8]
    assert "Independent outcomes" in result.to_text() and "(midpoint: 50%)" in result.to_text()


def test_monte_carlo_text_has_no_composite_or_convergence():
    est = qas.ProbabilityEstimate(outcome="Abandoned", probability_low=8, probability_mid=16, probability_high=25)
    mc = {
        "per_outcome": [
            None,
            {"outcome": "Abandoned", "monte_carlo": {"mean": 16.1234, "confidence_intervals": {"95%": [9.4, 23.6]}}},
        ],
        "composite": {
            "mean": 32.2,
            "confidence_intervals": {"95%": [30, 34]},
            "convergence": {"converged": True, "relative_error": 0.0009},
        },
    }
    text = qas.RisksToolResult(probabilities=qas.ProbabilityAssessment(estimates=[est]), monte_carlo=mc).to_text()

    assert "Abandoned: 9% to 24%" in text
    for banned in ("Composite", "composite", "Converged", "relative error", "32.2", "16.1"):
        assert banned not in text


def test_prompt_payload_drops_monte_carlo_pseudo_precision():
    mc = {"composite": {"mean": 32.2, "convergence": {"converged": True, "relative_error": 0.0009}}, "per_outcome": []}
    payload = {
        "monte_carlo": mc,
        "quant": {"risks": {"monte_carlo": mc}},
        "scenarios": [{"name": "Base", "_meta": {"probability_sum": 115}}],
    }
    preamble = rp.payload_preamble_for_prompt(payload)
    for banned in ("composite", "relative_error", "converged", "probability_sum"):
        assert banned not in preamble
    assert payload["monte_carlo"] is mc  # the saved payload (and the UI) keep it


# ====================================================================== 5. empty metrics


def test_empty_stance_and_consensus_say_no_data():
    stance = qas.StanceAnalysis(topic="vapes", agents_analyzed=0).to_text()
    consensus = qas.ConsensusMetrics().to_text()
    assert qas.NO_DATA_NOTE in stance and "Agents analyzed: 0" not in stance
    assert qas.NO_DATA_NOTE in consensus and "Polarization index" not in consensus and "factions" not in consensus


def test_all_unknown_entity_types_say_no_data():
    metrics = qas.SimulationMetrics(
        total_agents=83,
        agent_type_activity={"Unknown": {"agent_count": 83, "total_actions": 242, "avg_actions_per_agent": 2.9}},
    ).to_text()
    matrix = qas.StakeholderImpactMatrix(rows=[qas.StakeholderImpactRow(entity_type="Unknown")]).to_text()
    assert qas.NO_DATA_NOTE in metrics and "Unknown: 83 agents" not in metrics
    assert qas.NO_DATA_NOTE in matrix and "| Unknown |" not in matrix


def test_known_types_still_render():
    matrix = qas.StakeholderImpactMatrix(rows=[qas.StakeholderImpactRow(entity_type="Company")]).to_text()
    assert "| Company |" in matrix and qas.NO_DATA_NOTE not in matrix


def test_empty_stance_is_not_evidence_for_probabilities(monkeypatch):
    _result, llm = _assess(monkeypatch, [], stance=qas.StanceAnalysis(), consensus=qas.ConsensusMetrics())
    evidence = llm.chat_json.call_args.kwargs["messages"][1]["content"]
    assert "Polarization index" not in evidence and "stance distribution" not in evidence


def test_prompt_payload_marks_empty_positions_as_no_data():
    payload = {
        "quant": {
            "positions": {
                "stance_analysis": {"agents_analyzed": 0, "stances": []},
                "consensus_metrics": {"polarization_index": 0},
            },
            "stakeholder_matrix": {"rows": [{"entity_type": "Unknown"}]},
        }
    }
    view = json.loads(rp.payload_preamble_for_prompt(payload).split("\n", 1)[1].rsplit("\n", 1)[0])
    assert view["quant"]["positions"] == qas.NO_DATA_NOTE
    assert view["quant"]["stakeholder_matrix"] == qas.NO_DATA_NOTE
    assert "NO DATA" in ra.SECTION_SYSTEM_PROMPT_TEMPLATE


# ====================================================================== 6. empty decision section


def test_missing_decision_drops_the_section(monkeypatch):
    agent, _llm = _agent(monkeypatch)
    outline = agent._default_outline_v1()

    assert ra.omit_empty_decision_section(outline, None) is True
    assert "decision_recommendation" not in [s.role for s in outline.sections]
    assert len(outline.sections) == len(ra.OUTLINE_REQUIRED_ROLES) - 1
    assert rp.render_decision_markdown(None) == ""


def test_present_decision_keeps_the_section(monkeypatch):
    agent, _llm = _agent(monkeypatch)
    outline = agent._default_outline_v1()
    assert ra.omit_empty_decision_section(outline, {"verdict": "Go"}) is False
    assert "decision_recommendation" in [s.role for s in outline.sections]


# ====================================================================== 7. round and agent counts


def _timeline(rounds):
    return [{"round_num": r, "total_actions": 5, "action_types": {"CREATE_POST": 5}} for r in rounds]


def test_round_zero_is_not_counted(monkeypatch):
    from app.services.simulation_runner import SimulationRunner

    monkeypatch.setattr(SimulationRunner, "get_timeline", classmethod(lambda cls, sid: _timeline(range(0, 11))))
    agents = [{"agent_name": f"a{i}", "total_actions": 1, "action_types": {}} for i in range(19)]
    monkeypatch.setattr(SimulationRunner, "get_agent_stats", classmethod(lambda cls, sid: agents))
    svc = qas.QuantitativeAnalysisService(llm_client=MagicMock())
    monkeypatch.setattr(svc, "_load_agent_profiles", lambda sid: [])

    assert svc.simulation_metrics("s").total_rounds == 10
    assert svc.escalation_analysis("s").total_rounds == 10


def test_summary_uses_the_agent_count(monkeypatch):
    outline, llm = _plan(
        monkeypatch, _v1_outline("Vape Price Rehearsal", "A 105-entity simulation shows retailers split."), agents=83
    )
    assert outline.summary == "An 83-agent simulation shows retailers split."
    prompt = llm.chat_json.call_args_list[0].kwargs["messages"][1]["content"]
    assert "Simulated agents: 83" in prompt and "Rounds executed: 10" in prompt
    assert "Knowledge-graph nodes (background entities, NOT agents): 105" in prompt


# ====================================================================== 8. time horizon


def test_basis_states_the_compressed_horizon():
    basis = rp.simulation_basis(10, 19, {"scenario_horizon_hours": 4380, "hours_represented_per_round": 438})
    assert basis["statement"] == (
        "19 simulated agents over 10 rounds, each round standing for about 18 days of the "
        "6-month horizon the scenario asks about (compressed time)."
    )


@pytest.mark.parametrize("time_config", [None, "garbage", {"total_simulation_hours": 10, "minutes_per_round": 60}])
def test_basis_without_horizon_claims_none(time_config):
    statement = rp.simulation_basis(10, 19, time_config)["statement"]
    assert "10 rounds of compressed simulated time" in statement
    assert "horizon the scenario" not in statement and "18 days" not in statement


def test_basis_reaches_the_grounding_section(monkeypatch, tmp_path):
    (tmp_path / "simulation_config.json").write_text(
        json.dumps({"time_config": {"scenario_horizon_hours": 4380, "hours_represented_per_round": 438}}),
        encoding="utf-8",
    )
    agent, _llm = _agent(monkeypatch)
    monkeypatch.setattr(agent.quant_service, "_sim_dir", lambda _sid: str(tmp_path))
    monkeypatch.setattr(
        agent.quant_service, "simulation_metrics", lambda _sid: qas.SimulationMetrics(total_agents=19, total_rounds=10)
    )

    basis = agent._compute_simulation_basis()
    md = rp.render_grounding_markdown(None, [], [], basis)

    assert "**Simulation basis:** 19 simulated agents over 10 rounds, each round standing for about 18 days" in md
    assert "Simulation basis" not in rp.render_grounding_markdown(None, [], [])
    assert (
        rp.build_report_payload_v1("r", "s", "g", None, None, None, None, None, [], [], [], basis=basis)[
            "simulation_basis"
        ]
        == basis
    )


# ====================================================================== 9. auto-written briefing


def _project(label):
    return Project(
        project_id="p1",
        name="t",
        status=ProjectStatus.CREATED,
        created_at="2026-11-09",
        updated_at="2026-11-09",
        grounding_sources=[
            {"source_id": "upload_p1_ab12cd34.md", "kind": "upload", "label": label, "retrieved_at": "2026-11-09"},
            {"source_id": "upload_p1_ef56.pdf", "kind": "upload", "label": "Q3 plan.pdf", "retrieved_at": "2026-11-09"},
        ],
    )


@pytest.mark.parametrize("label", ["briefing_Revolut_Mobile_launch.md", "deep_research_vapes.md"])
def test_auto_briefing_is_not_labelled_user_provided(label):
    project = _project(label)
    claims = rp.label_auto_briefing_claims(project, grounding_bundle.build_claim_ledger_from_project(project))

    md = rp.render_grounding_markdown(project, [], claims)

    assert f"{rp.AUTO_BRIEFING_LABEL}: {label}" in md
    assert f"[upload] {label}" not in md
    assert f"User-provided document in scope: {label}" not in md
    assert "User-provided document in scope: Q3 plan.pdf" in md  # a real upload keeps its label
    assert "not verified facts" in md
    assert (
        f"[upload] {label}"
        not in rp.build_report_payload_v1("r", "s", "g", project, None, None, None, None, [], [], claims)["grounding"][
            "summary_text"
        ]
    )
