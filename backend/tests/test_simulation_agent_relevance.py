"""The agent list is checked against the scenario by the LLM.

Seen live on 2026-11-10 (Revolut Mobile Ireland run): "EU roaming rules" (a regulation typed as an
organisation) and Giffgaff / Rakuten Mobile (operators that do not sell in Ireland) became agents.
A type rule cannot catch these, so one LLM call decides, and the check fails open.
"""

from app.services.simulation_manager import drop_irrelevant_agents
from app.services.zep_entity_reader import EntityNode, FilteredEntities

SCENARIO = "Revolut launches 5G SIM-only plans in Ireland. How will Irish operators and ComReg react?"


def _filtered(*pairs: tuple[str, str]) -> FilteredEntities:
    nodes = [EntityNode(uuid=n, name=n, labels=["Entity", t], summary="", attributes={}) for n, t in pairs]
    return FilteredEntities(
        entities=nodes, entity_types={t for _, t in pairs}, total_count=len(nodes), filtered_count=len(nodes)
    )


class FakeLLM:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.prompts = result, error, []

    def chat_json(self, messages, temperature=0.3, max_tokens=4096):
        self.prompts.append(messages[0]["content"])
        if self.error:
            raise self.error
        return self.result


LIVE_LIST = (
    ("Vodafone Ireland", "MobileNetworkOperator"),
    ("Eir", "MobileNetworkOperator"),
    ("ComReg", "TelecomRegulator"),
    ("EU roaming rules", "Organization"),
    ("Giffgaff", "MobileNetworkOperator"),
    ("Revolut Mobile", "MVNOBrand"),
)


def test_rules_and_foreign_analogues_are_dropped():
    filtered = _filtered(*LIVE_LIST)
    llm = FakeLLM({"drop": [{"index": 3, "reason": "a regulation"}, {"index": 4, "reason": "UK only"}]})

    drop_irrelevant_agents(filtered, SCENARIO, llm=llm)

    assert [e.name for e in filtered.entities] == ["Vodafone Ireland", "Eir", "ComReg", "Revolut Mobile"]
    assert filtered.filtered_count == 4
    assert "Organization" not in filtered.entity_types
    assert SCENARIO in llm.prompts[0] and "3 | EU roaming rules | Organization" in llm.prompts[0]


def test_llm_failure_keeps_everyone():
    filtered = _filtered(*LIVE_LIST)

    drop_irrelevant_agents(filtered, SCENARIO, llm=FakeLLM(error=ValueError("bad json")))

    assert len(filtered.entities) == 6


def test_dropping_more_than_half_keeps_everyone():
    filtered = _filtered(*LIVE_LIST)
    llm = FakeLLM({"drop": [{"index": i, "reason": "x"} for i in range(4)]})

    drop_irrelevant_agents(filtered, SCENARIO, llm=llm)

    assert len(filtered.entities) == 6


def test_out_of_range_indexes_are_ignored():
    filtered = _filtered(*LIVE_LIST)

    drop_irrelevant_agents(filtered, SCENARIO, llm=FakeLLM({"drop": [{"index": 99, "reason": "x"}]}))

    assert len(filtered.entities) == 6


def test_no_scenario_text_skips_the_call():
    filtered = _filtered(*LIVE_LIST)
    llm = FakeLLM({"drop": [{"index": 3, "reason": "x"}]})

    drop_irrelevant_agents(filtered, "   ", llm=llm)

    assert llm.prompts == [] and len(filtered.entities) == 6
