"""Jev gates on the report writer and the interview path (``jev_report_gates`` and its call sites).

Four sites: report_repetition, report_quant_check, interview_format, interview_selection.
Each must (a) act only when Jev is confident, (b) act at most once so nothing loops,
(c) record only in shadow mode, and (d) be byte-identical to today when Jev is off.
No network: Jev is a scripted fake, the LLM is a MagicMock, the OASIS interview API is patched.
"""

from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from app import config as app_config
from app.services import jev_report_gates as g
from app.services.report_agent import ReportAgent, ReportOutline, ReportSection
from app.services.zep_tools import ZepToolsService
from app.utils.jev_client import JevAnswer, JevClient
from app.utils.jev_metrics import LEDGER


def noul(p: float) -> JevAnswer:
    return JevAnswer("noul", p, max(p, 1.0 - p))


def score(level: int, conf: float = 0.9) -> JevAnswer:
    return JevAnswer("score", float(level), conf)


class ScriptedJev:
    """One scripted answer batch per ``evaluate_many`` call, in order; records every call."""

    def __init__(self, batches):
        self.batches = [list(b) for b in batches]
        self.calls = []

    def evaluate_many(self, items, max_workers=None, *, site="unlabelled"):
        self.calls.append((site, list(items)))
        assert self.batches, f"unexpected Jev call at site {site!r}"
        answers = self.batches.pop(0)
        assert len(answers) == len(items), f"{site}: script has {len(answers)} answers for {len(items)} items"
        return answers


class ExplodingJev:
    def evaluate_many(self, items, max_workers=None, *, site="unlabelled"):
        raise RuntimeError("jev down")


@pytest.fixture(autouse=True)
def _fresh_ledger():
    LEDGER.reset()
    yield
    LEDGER.reset()


@pytest.fixture
def jev_on(monkeypatch):
    """Active mode with a scripted Jev. The repo .env may set JEV_MODE, so pin it."""
    monkeypatch.setattr(app_config.Config, "JEV_MIN_CONFIDENCE", 0.6)
    monkeypatch.setattr(app_config.Config, "JEV_MODE", "active")
    monkeypatch.setattr(app_config.Config, "JEV_DISABLED_SITES", frozenset())

    def _install(*batches, client=None):
        fake = client if client is not None else ScriptedJev(batches)
        monkeypatch.setattr(JevClient, "from_config", classmethod(lambda cls: fake))
        return fake

    return _install


@pytest.fixture
def jev_shadow(monkeypatch, jev_on):
    monkeypatch.setattr(app_config.Config, "JEV_MODE", "shadow")
    return jev_on


@pytest.fixture
def jev_off(monkeypatch):
    monkeypatch.setattr(app_config.Config, "JEV_MODE", "off")
    monkeypatch.setattr(JevClient, "from_config", classmethod(lambda cls: None))


# ====================================================================== gate 1: repetition

PREVIOUS = ["## Grounding\n\nPharmacy First caps bite in Q3. Independents carry the shortfall."]
EVIDENCE = "[analyze_metrics]\nTotal posts: 1,234 (up 18% on the prior window)"


def _hint(state, content="Caps bite in Q3.", role="general", previous=PREVIOUS, evidence=""):
    return g.section_rejection_hint(
        section_role=role, content=content, previous_sections=previous, evidence=evidence, state=state
    )


def test_repetition_rejects_once_then_accepts(jev_on):
    fake = jev_on([{"answer": noul(0.9)}], [{"answer": noul(0.9)}])
    state = g.SectionGateState()

    first = _hint(state)

    assert first is not None and first.startswith("[Rejected] This section largely repeats earlier sections")
    assert "90%" in first
    assert state.repetition_rejections == 1
    assert _hint(state) is None  # capped: no second rejection, and Jev is not even asked again
    assert len(fake.calls) == 1 and fake.calls[0][0] == "report_repetition"
    site = LEDGER.summary()["sites"]["report_repetition"]
    assert (site["items_total"], site["items_jev_confident"]) == (1, 1)


def test_repetition_state_is_small_and_capped(jev_on):
    fake = jev_on([{"answer": noul(0.1)}])
    previous = [f"section {i} " + "x" * 2000 for i in range(7)]

    assert _hint(g.SectionGateState(), content="y" * 5000, previous=previous) is None

    state, question = fake.calls[0][1][0]
    assert len(state["previous_sections"]) == 5
    assert state["previous_sections"][0].startswith("section 2")  # the most recent five
    assert all(len(s) <= 600 for s in state["previous_sections"])
    assert len(state["new_section"]) == 3000
    assert question["answer"]["type"] == "noul"
    assert "data" in question["answer"]["instructions"]


def test_repetition_below_threshold_accepts(jev_on):
    jev_on([{"answer": noul(0.7)}])  # confident, but under 0.75
    assert _hint(g.SectionGateState()) is None


def test_repetition_unsure_accepts(jev_on):
    jev_on([{"answer": JevAnswer("noul", 0.9, 0.5)}])  # would reject, but confidence under 0.6
    assert _hint(g.SectionGateState()) is None
    site = LEDGER.summary()["sites"]["report_repetition"]
    assert (site["items_jev_confident"], site["items_jev_low_confidence"]) == (0, 1)


def test_repetition_shadow_never_rejects_but_records(jev_shadow):
    fake = jev_shadow([{"answer": noul(0.95)}], [{"answer": noul(0.95)}])
    state = g.SectionGateState()

    assert _hint(state) is None
    assert _hint(state) is None

    assert state.repetition_rejections == 0
    assert len(fake.calls) == 2  # shadow measures every acceptance; no cap is consumed
    site = LEDGER.summary()["sites"]["report_repetition"]
    assert (site["shadow_compared"], site["shadow_agreed"]) == (2, 0)


def test_repetition_off_gate_not_called(jev_off):
    assert _hint(g.SectionGateState()) is None
    assert LEDGER.summary()["sites"] == {}


def test_repetition_disabled_site_not_called(monkeypatch, jev_on):
    fake = jev_on()
    monkeypatch.setattr(app_config.Config, "JEV_DISABLED_SITES", frozenset({"report_repetition"}))
    assert _hint(g.SectionGateState()) is None
    assert fake.calls == []


def test_first_section_skips_repetition(jev_on):
    fake = jev_on()
    assert _hint(g.SectionGateState(), previous=[]) is None
    assert fake.calls == []


def test_jev_exception_accepts_section(jev_on):
    jev_on(client=ExplodingJev())
    assert _hint(g.SectionGateState(), role="quant_snapshot", evidence=EVIDENCE) is None


def test_jev_failed_item_accepts_and_is_counted(jev_on):
    jev_on([None])
    assert _hint(g.SectionGateState()) is None
    assert LEDGER.summary()["sites"]["report_repetition"]["items_jev_failed"] == 1


# ====================================================================== gate 2: numbers from evidence


def test_quant_check_low_probability_rejects_once(jev_on):
    fake = jev_on([{"answer": noul(0.1)}], [{"answer": noul(0.1)}])
    state = g.SectionGateState()

    assert _hint(state, role="quant_snapshot", previous=[], evidence=EVIDENCE) == g.QUANT_CHECK_REJECTION_MSG
    assert _hint(state, role="quant_snapshot", previous=[], evidence=EVIDENCE) is None

    assert state.quant_rejections == 1
    assert len(fake.calls) == 1 and fake.calls[0][0] == "report_quant_check"
    state_sent, _q = fake.calls[0][1][0]
    assert state_sent == {"evidence": EVIDENCE, "section": "Caps bite in Q3."}


def test_quant_check_at_threshold_rejects_above_accepts(jev_on):
    jev_on([{"answer": noul(0.25)}], [{"answer": noul(0.3)}])
    assert _hint(g.SectionGateState(), role="scenarios", previous=[], evidence=EVIDENCE) is not None
    assert _hint(g.SectionGateState(), role="scenarios", previous=[], evidence=EVIDENCE) is None


@pytest.mark.parametrize("role", sorted(g.QUANT_CHECK_ROLES))
def test_quant_check_runs_for_listed_roles(jev_on, role):
    fake = jev_on([{"answer": noul(0.9)}])
    assert _hint(g.SectionGateState(), role=role, previous=[], evidence=EVIDENCE) is None
    assert [site for site, _ in fake.calls] == ["report_quant_check"]


@pytest.mark.parametrize(
    "role", ["general", "grounding_and_assumptions", "stakeholder_impacts", "decision_recommendation"]
)
def test_quant_check_skips_other_roles(jev_on, role):
    fake = jev_on()
    assert _hint(g.SectionGateState(), role=role, previous=[], evidence=EVIDENCE) is None
    assert fake.calls == []


def test_quant_check_needs_evidence(jev_on):
    fake = jev_on()
    assert _hint(g.SectionGateState(), role="quant_snapshot", previous=[], evidence="  ") is None
    assert fake.calls == []


def test_quant_check_evidence_capped(jev_on):
    fake = jev_on([{"answer": noul(0.9)}])
    _hint(g.SectionGateState(), role="risks_actions", previous=[], evidence="9" * 6000)
    assert len(fake.calls[0][1][0][0]["evidence"]) == 4000


def test_quant_check_shadow_records_only(jev_shadow):
    jev_shadow([{"answer": noul(0.05)}])
    assert _hint(g.SectionGateState(), role="quant_snapshot", previous=[], evidence=EVIDENCE) is None
    site = LEDGER.summary()["sites"]["report_quant_check"]
    assert (site["items_total"], site["shadow_compared"], site["shadow_agreed"]) == (1, 1, 0)


def test_quant_check_off_not_called(jev_off):
    assert _hint(g.SectionGateState(), role="quant_snapshot", previous=[], evidence=EVIDENCE) is None
    assert LEDGER.summary()["sites"] == {}


def test_gates_fire_one_at_a_time_and_each_only_once(jev_on):
    fake = jev_on([{"answer": noul(0.9)}], [{"answer": noul(0.2)}])
    state = g.SectionGateState()

    first = _hint(state, role="quant_snapshot", evidence=EVIDENCE)  # repetition rejects; quant not asked yet
    second = _hint(state, role="quant_snapshot", evidence=EVIDENCE)  # repetition capped; quant rejects
    third = _hint(state, role="quant_snapshot", evidence=EVIDENCE)  # both capped; no Jev call

    assert first.startswith("[Rejected] This section largely repeats")
    assert second == g.QUANT_CHECK_REJECTION_MSG
    assert third is None
    assert [site for site, _ in fake.calls] == ["report_repetition", "report_quant_check"]


# ====================================================================== ReACT loop call sites

TOOL_CALL = '<tool_call>{"name": "quick_search", "parameters": {"query": "caps"}}</tool_call>'
QUANT_CALL = '<tool_call>{"name": "analyze_metrics", "parameters": {}}</tool_call>'


def _agent(monkeypatch, responses, *, payload_v1=False):
    monkeypatch.setattr(app_config.Config, "ENABLE_REPORT_PAYLOAD_V1", payload_v1)
    llm = MagicMock()
    llm.chat.side_effect = list(responses)
    agent = ReportAgent(
        graph_id="g",
        simulation_id="s",
        simulation_requirement="Pharmacy First caps",
        llm_client=llm,
        zep_tools=MagicMock(),
    )
    monkeypatch.setattr(agent, "_execute_tool", MagicMock(return_value="tool result"))
    return agent, llm


def _run(agent, role="general", previous=PREVIOUS):
    section = ReportSection(title="Body", role=role)
    outline = ReportOutline(title="Report", summary="Summary", sections=[section])
    return agent._generate_section_react(section=section, outline=outline, previous_sections=previous)


def _all_user_messages(llm):
    return [m["content"] for call in llm.chat.call_args_list for m in call.kwargs["messages"] if m["role"] == "user"]


def test_react_repetition_rejection_rewrites_once(monkeypatch, jev_on):
    jev_on([{"answer": noul(0.9)}], [{"answer": noul(0.1)}])
    agent, llm = _agent(monkeypatch, [TOOL_CALL] * 3 + ["Final Answer: first draft", "Final Answer: second draft"])

    assert _run(agent) == "second draft"

    assert llm.chat.call_count == 5
    last = llm.chat.call_args.kwargs["messages"]
    assert last[-2] == {"role": "assistant", "content": "Final Answer: first draft"}
    assert last[-1]["role"] == "user" and last[-1]["content"].startswith("[Rejected] This section largely repeats")


def test_react_implicit_final_is_gated_too(monkeypatch, jev_on):
    jev_on([{"answer": noul(0.9)}], [{"answer": noul(0.1)}])
    agent, llm = _agent(monkeypatch, [TOOL_CALL] * 3 + ["prose without the prefix", "better prose"])

    assert _run(agent) == "better prose"

    # The loop appends to the same list the mock holds, so the accepted answer is already the tail.
    last = llm.chat.call_args.kwargs["messages"]
    assert last[-3] == {"role": "assistant", "content": "prose without the prefix"}
    assert last[-2]["role"] == "user" and last[-2]["content"].startswith("[Rejected]")
    assert last[-1] == {"role": "assistant", "content": "better prose"}


def test_react_off_mode_accepts_first_draft_unchanged(monkeypatch, jev_off):
    agent, llm = _agent(monkeypatch, [TOOL_CALL] * 3 + ["Final Answer: first draft"])

    assert _run(agent) == "first draft"

    assert llm.chat.call_count == 4
    assert not any("[Rejected]" in m for m in _all_user_messages(llm))


def test_react_shadow_accepts_first_draft(monkeypatch, jev_shadow):
    jev_shadow([{"answer": noul(0.99)}])
    agent, llm = _agent(monkeypatch, [TOOL_CALL] * 3 + ["Final Answer: first draft"])

    assert _run(agent) == "first draft"
    assert llm.chat.call_count == 4
    assert LEDGER.summary()["sites"]["report_repetition"]["shadow_compared"] == 1


def test_react_quant_gate_reads_cached_tool_outputs(monkeypatch, jev_on):
    fake = jev_on([{"answer": noul(0.1)}])
    agent, llm = _agent(
        monkeypatch, [QUANT_CALL] * 3 + ["Final Answer: vague prose", "Final Answer: 1,234 posts"], payload_v1=True
    )
    agent._quant_tool_cache = {"analyze_metrics": "Total posts: 1,234"}

    assert _run(agent, role="quant_snapshot", previous=[]) == "1,234 posts"

    # One rejection, then the rewrite is accepted without a second Jev call (per-section cap)
    assert [site for site, _ in fake.calls] == ["report_quant_check"]
    assert fake.calls[0][1][0][0]["evidence"] == "[analyze_metrics]\nTotal posts: 1,234"
    assert llm.chat.call_args.kwargs["messages"][-1]["content"] == g.QUANT_CHECK_REJECTION_MSG


def test_react_jev_failure_never_fails_the_section(monkeypatch, jev_on):
    jev_on(client=ExplodingJev())
    agent, _llm = _agent(monkeypatch, [TOOL_CALL] * 3 + ["Final Answer: first draft"])
    assert _run(agent) == "first draft"


# ====================================================================== gate 3: interview format


def _svc() -> ZepToolsService:
    """A ZepToolsService without the Zep client; ``_llm(svc)`` is its MagicMock LLM."""
    svc = ZepToolsService.__new__(ZepToolsService)  # skip Zep client construction
    svc._llm_client = MagicMock()
    return svc


def _llm(svc: ZepToolsService) -> MagicMock:
    return cast(MagicMock, svc._llm_client)


AGENTS = [{"realname": "Jane Doe", "profession": "Pharmacist"}]
RESULTS = {
    "twitter_3": {"response": '{"tool_name": "create_post", "arguments": {"content": "I think caps hurt."}}'},
    "reddit_3": {"response": "Question 1: As a pharmacist I think caps hurt."},
}
BATCH_PATH = "app.services.simulation_runner.SimulationRunner.interview_agents_batch"
PROMPT = "You are being interviewed. Answer in plain text.\n\n1. Why?"


def test_interview_format_non_plain_answer_retried_once_with_reminder(jev_on):
    fake = jev_on(
        [
            {"plain_text": noul(0.1), "in_persona": noul(0.8)},  # twitter: retry
            {"plain_text": noul(0.95), "in_persona": noul(0.9)},  # reddit: fine
        ]
    )
    batch = MagicMock(return_value={"success": True, "result": {"results": {"twitter_3": {"response": "Caps hurt."}}}})

    with patch(BATCH_PATH, batch):
        merged = _svc()._retry_malformed_interview_answers("sim", [3], AGENTS, RESULTS, PROMPT)

    assert merged["twitter_3"] == {"response": "Caps hurt."}
    assert merged["reddit_3"] is RESULTS["reddit_3"]
    batch.assert_called_once()
    assert batch.call_args.kwargs["simulation_id"] == "sim"
    interviews = batch.call_args.kwargs["interviews"]
    assert [(i["agent_id"], i["platform"]) for i in interviews] == [(3, "twitter")]
    assert interviews[0]["prompt"] == f"{g.INTERVIEW_FORMAT_REMINDER}\n{PROMPT}"  # reminder + original prompt
    # Jev saw the cleaned answer as data, labelled with the actor, two nouls in one request
    assert fake.calls[0][0] == "interview_format"
    state, questions = fake.calls[0][1][0]
    assert state == {"actor": "Jane Doe", "answer": "I think caps hurt."}
    assert set(questions) == {"plain_text", "in_persona"}
    site = LEDGER.summary()["sites"]["interview_format"]
    assert (site["items_total"], site["items_jev_confident"]) == (2, 2)


def test_interview_format_plain_answers_not_retried(jev_on):
    jev_on([{"plain_text": noul(0.9), "in_persona": noul(0.9)}] * 2)
    batch = MagicMock()
    with patch(BATCH_PATH, batch):
        merged = _svc()._retry_malformed_interview_answers("sim", [3], AGENTS, RESULTS, "1. Why?")
    assert merged is RESULTS
    batch.assert_not_called()


@pytest.mark.parametrize(
    "retry_result",
    [
        {"success": False, "error": "env down"},
        {"success": True, "result": {"results": {"twitter_3": {"response": ""}}}},
        {"success": True, "result": {"results": {}}},
    ],
)
def test_interview_format_failed_retry_keeps_original(jev_on, retry_result):
    jev_on([{"plain_text": noul(0.1), "in_persona": noul(0.8)}, {"plain_text": noul(0.9), "in_persona": noul(0.9)}])
    with patch(BATCH_PATH, MagicMock(return_value=retry_result)):
        merged = _svc()._retry_malformed_interview_answers("sim", [3], AGENTS, RESULTS, "1. Why?")
    assert merged == RESULTS


def test_interview_format_shadow_records_only(jev_shadow):
    jev_shadow([{"plain_text": noul(0.1), "in_persona": noul(0.8)}, {"plain_text": noul(0.9), "in_persona": noul(0.9)}])
    batch = MagicMock()
    with patch(BATCH_PATH, batch):
        merged = _svc()._retry_malformed_interview_answers("sim", [3], AGENTS, RESULTS, "1. Why?")
    assert merged is RESULTS
    batch.assert_not_called()
    site = LEDGER.summary()["sites"]["interview_format"]
    assert (site["shadow_compared"], site["shadow_agreed"]) == (2, 1)


def test_interview_format_off_identical(jev_off):
    batch = MagicMock()
    with patch(BATCH_PATH, batch):
        merged = _svc()._retry_malformed_interview_answers("sim", [3], AGENTS, RESULTS, "1. Why?")
    assert merged is RESULTS
    batch.assert_not_called()
    assert LEDGER.summary()["sites"] == {}


def test_interview_format_jev_failure_keeps_answers(jev_on):
    jev_on(client=ExplodingJev())
    with patch(BATCH_PATH, MagicMock()) as batch:
        assert _svc()._retry_malformed_interview_answers("sim", [3], AGENTS, RESULTS, "1. Why?") is RESULTS
    batch.assert_not_called()


def test_check_interview_answers_unsure_and_failed_do_not_retry(jev_on):
    jev_on([None, {"plain_text": JevAnswer("noul", 0.1, 0.5), "in_persona": noul(0.5)}])
    verdicts = g.check_interview_answers([("A", "x"), ("B", "y")])
    assert [v.retry for v in verdicts] == [False, False]
    assert verdicts[1].plain_text_p == 0.1 and not verdicts[1].confident
    site = LEDGER.summary()["sites"]["interview_format"]
    assert (site["items_jev_failed"], site["items_jev_low_confidence"]) == (1, 1)


def test_check_interview_answers_empty_and_off():
    assert g.check_interview_answers([]) == []


# ====================================================================== gate 4: interview selection


def _profiles(stances=None):
    base = [
        {"realname": "NHS England", "profession": "Regulator", "bio": "b", "interested_topics": ["policy"]},
        {"realname": "Jane Doe", "profession": "Pharmacist", "bio": "b", "interested_topics": ["pay"]},
        {"realname": "The Guardian", "profession": "Journalist", "bio": "b", "interested_topics": ["news"]},
        {"realname": "Bob Patient", "profession": "Patient", "bio": "b", "interested_topics": ["access"]},
    ]
    if stances:
        for profile, stance in zip(base, stances, strict=True):
            profile["stance"] = stance
    return base


def _select(svc, profiles, max_agents=2):
    return svc._select_agents_for_interview(profiles, "Pharmacy First caps", "sim background", max_agents)


def _selection_prompt(svc: ZepToolsService) -> str:
    return str(_llm(svc).chat_json.call_args.kwargs["messages"][1]["content"])


def test_selection_jev_scores_rank_and_llm_only_for_unsure(jev_on):
    fake = jev_on(
        [
            {"relevance": score(4)},
            {"relevance": score(3)},
            {"relevance": score(0, conf=0.3)},  # unsure -> LLM
            {"relevance": score(2)},
        ]
    )
    svc = _svc()
    _llm(svc).chat_json.return_value = {"selected_indices": [2], "reasoning": "media matters"}

    agents, indices, reasoning = _select(svc, _profiles())

    # Jev "central" (idx 0) and the LLM pick (idx 2, synthetic top score) beat Jev "relevant" (idx 1); ties by index
    assert indices == [0, 2]
    assert [a["realname"] for a in agents] == ["NHS England", "The Guardian"]
    assert reasoning.startswith("Ranked by Jev relevance score")
    prompt = _selection_prompt(svc)
    assert "The Guardian" in prompt and "NHS England" not in prompt and "Jane Doe" not in prompt
    assert fake.calls[0][0] == "interview_selection"
    state, question = fake.calls[0][1][0]
    assert state["requirement"] == "Pharmacy First caps" and state["agent"]["name"] == "NHS England"
    assert question["relevance"]["type"] == "score" and question["relevance"]["criteria"] == g.RELEVANCE_LEVELS
    site = LEDGER.summary()["sites"]["interview_selection"]
    assert (site["items_jev_confident"], site["items_jev_low_confidence"], site["items_llm"]) == (3, 1, 1)
    assert site["llm_calls"] == 1 and site["llm_prompt_chars"] > 0


def test_selection_all_confident_skips_llm(jev_on):
    jev_on([{"relevance": score(1)}, {"relevance": score(4)}, {"relevance": score(2)}, {"relevance": score(3)}])
    svc = _svc()

    _agents, indices, _reasoning = _select(svc, _profiles())

    assert indices == [1, 3]
    _llm(svc).chat_json.assert_not_called()


def test_selection_diversity_cap_prefers_another_stance(jev_on):
    jev_on([{"relevance": score(4)}, {"relevance": score(3)}, {"relevance": score(2)}, {"relevance": score(1)}])
    _agents, indices, _r = _select(_svc(), _profiles(["supportive", "supportive", "opposing", "neutral"]))
    assert indices == [0, 2]  # cap ceil(2/2)=1 per stance: the second supporter yields to the best opposer


def test_selection_diversity_cap_only_when_alternatives_exist(jev_on):
    jev_on([{"relevance": score(4)}, {"relevance": score(3)}, {"relevance": score(2)}, {"relevance": score(1)}])
    _agents, indices, _r = _select(_svc(), _profiles(["supportive"] * 4))
    assert indices == [0, 1]


def test_rank_with_diversity_unit():
    scores = {0: 4, 1: 4, 2: 3, 3: 2, 4: 1}
    stances = {0: "a", 1: "a", 2: "a", 3: "b", 4: None}
    assert g.rank_with_diversity(scores, stances, 3) == [0, 1, 3]  # cap 2 of "a", then the best other
    assert g.rank_with_diversity(scores, {}, 2) == [0, 1]
    assert g.rank_with_diversity(scores, stances, 0) == []


def test_selection_shadow_llm_decides_and_agreement_recorded(jev_shadow):
    fake = jev_shadow(
        [{"relevance": score(4)}, {"relevance": score(3)}, {"relevance": score(0)}, {"relevance": score(2)}]
    )
    svc = _svc()
    _llm(svc).chat_json.return_value = {"selected_indices": [0, 2], "reasoning": "llm says so"}

    agents, indices, reasoning = _select(svc, _profiles())

    assert (indices, reasoning) == ([0, 2], "llm says so")
    assert [a["realname"] for a in agents] == ["NHS England", "The Guardian"]
    assert len(fake.calls[0][1]) == 4  # Jev still scored everyone
    assert "(4 agents)" in _selection_prompt(svc)
    # Jev would pick {0, 1}; LLM picked {0, 2}: agree on 0 (in) and 3 (out), disagree on 1 and 2
    site = LEDGER.summary()["sites"]["interview_selection"]
    assert (site["shadow_compared"], site["shadow_agreed"]) == (4, 2)


def test_selection_off_calls_llm_once_over_all_agents(jev_off):
    svc = _svc()
    _llm(svc).chat_json.return_value = {"selected_indices": [1, 3, 9], "reasoning": "r"}

    agents, indices, reasoning = _select(svc, _profiles())

    assert (indices, reasoning) == ([1, 3], "r")  # 9 is out of range and dropped, as before
    assert [a["realname"] for a in agents] == ["Jane Doe", "Bob Patient"]
    _llm(svc).chat_json.assert_called_once()
    prompt = _selection_prompt(svc)
    assert "(4 agents)" in prompt
    assert all(name in prompt for name in ("NHS England", "Jane Doe", "The Guardian", "Bob Patient"))
    assert "Select up to 2 agents" in prompt


def test_selection_off_llm_failure_keeps_default_strategy(jev_off):
    svc = _svc()
    _llm(svc).chat_json.side_effect = RuntimeError("boom")
    profiles = _profiles()

    agents, indices, reasoning = _select(svc, profiles)

    assert agents == profiles[:2] and indices == [0, 1]
    assert reasoning == "Using default selection strategy"


def test_selection_disabled_site_forces_llm(monkeypatch, jev_on):
    fake = jev_on()
    monkeypatch.setattr(app_config.Config, "JEV_DISABLED_SITES", frozenset({"interview_selection"}))
    svc = _svc()
    _llm(svc).chat_json.return_value = {"selected_indices": [3], "reasoning": "r"}

    _agents, indices, _r = _select(svc, _profiles())

    assert indices == [3]
    assert fake.calls == []


def test_selection_jev_exception_falls_back_to_llm(jev_on):
    jev_on(client=ExplodingJev())
    svc = _svc()
    _llm(svc).chat_json.return_value = {"selected_indices": [2], "reasoning": "r"}
    _agents, indices, reasoning = _select(svc, _profiles())
    assert (indices, reasoning) == ([2], "r")
