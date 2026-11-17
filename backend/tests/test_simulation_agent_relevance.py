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
        self.result, self.error, self.prompts, self.thinking = result, error, [], []

    def chat_json(self, messages, temperature=0.3, max_tokens=4096, thinking=False):
        self.prompts.append(messages[0]["content"])
        self.thinking.append(thinking)
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


def _cats(*pairs: tuple[int, str], reason: str = "r") -> dict:
    return {"entities": [{"index": i, "category": c, "reason": reason} for i, c in pairs]}


KEEP_ALL_BUT_3_4 = ((0, "market_actor"), (1, "market_actor"), (2, "public_body"), (5, "market_actor"))


def test_rules_and_foreign_analogues_are_dropped():
    filtered = _filtered(*LIVE_LIST)
    llm = FakeLLM(_cats(*KEEP_ALL_BUT_3_4, (3, "thing"), (4, "not_in_market")))

    drop_irrelevant_agents(filtered, SCENARIO, llm=llm)

    assert [e.name for e in filtered.entities] == ["Vodafone Ireland", "Eir", "ComReg", "Revolut Mobile"]
    assert filtered.filtered_count == 4
    assert "Organization" not in filtered.entity_types
    assert SCENARIO in llm.prompts[0] and "3 | EU roaming rules | Organization" in llm.prompts[0]


def test_keep_categories_never_drop_even_with_a_drop_sounding_reason():
    # Live 2026-11-17: the old format let the model list Sky Mobile under "drop" with the reason
    # "...so KEEP - actually keep", and it was dropped. Only the category decides now.
    # Only 2 of 6 are market_actor, so a broken rule that dropped them stays under the half guard
    # and this test goes red (all-market_actor input would hide it behind the guard).
    filtered = _filtered(*LIVE_LIST)
    llm = FakeLLM(
        _cats(
            (0, "market_actor"),
            (1, "media"),
            (2, "public"),
            (3, "civil_society"),
            (4, "market_actor"),
            (5, "person_role"),
            reason="not active, drop",
        )
    )

    drop_irrelevant_agents(filtered, SCENARIO, llm=llm)

    assert len(filtered.entities) == 6


def test_public_bodies_and_media_are_kept_sources_and_platforms_dropped():
    filtered = _filtered(
        ("Vodafone Ireland", "MobileNetworkOperator"),
        ("CCPC", "Regulator"),
        ("Department of Communications", "GovernmentBody"),
        ("RTE", "Media"),
        ("Kehoe thread", "Organization"),
        ("YouTube", "Platform"),
        ("Eir", "MobileNetworkOperator"),
    )
    llm = FakeLLM(
        _cats(
            (0, "market_actor"),
            (1, "public_body"),
            (2, "public_body"),
            (3, "media"),
            (4, "source_or_platform"),
            (5, "source_or_platform"),
            (6, "market_actor"),
        )
    )

    drop_irrelevant_agents(filtered, SCENARIO, llm=llm)

    assert [e.name for e in filtered.entities] == [
        "Vodafone Ireland",
        "CCPC",
        "Department of Communications",
        "RTE",
        "Eir",
    ]


def test_unknown_or_missing_category_keeps_the_entity():
    filtered = _filtered(*LIVE_LIST)
    llm = FakeLLM({"entities": [{"index": 3, "category": "drop_me"}, {"index": 4}]})

    drop_irrelevant_agents(filtered, SCENARIO, llm=llm)

    assert len(filtered.entities) == 6


def test_llm_failure_keeps_everyone():
    filtered = _filtered(*LIVE_LIST)

    drop_irrelevant_agents(filtered, SCENARIO, llm=FakeLLM(error=ValueError("bad json")))

    assert len(filtered.entities) == 6


def test_dropping_more_than_half_keeps_everyone():
    filtered = _filtered(*LIVE_LIST)
    llm = FakeLLM(_cats(*((i, "thing") for i in range(4))))

    drop_irrelevant_agents(filtered, SCENARIO, llm=llm)

    assert len(filtered.entities) == 6


def test_out_of_range_indexes_are_ignored():
    filtered = _filtered(*LIVE_LIST)

    drop_irrelevant_agents(filtered, SCENARIO, llm=FakeLLM(_cats((99, "thing"))))

    assert len(filtered.entities) == 6


def test_no_scenario_text_skips_the_call():
    filtered = _filtered(*LIVE_LIST)
    llm = FakeLLM(_cats((3, "thing")))

    drop_irrelevant_agents(filtered, "   ", llm=llm)

    assert llm.prompts == [] and len(filtered.entities) == 6
