"""The agent check uses a stronger model with reasoning, sees graph facts, and drops historical or unclear
entities.

Seen live on 2026-11-17: with the small default model and only a 200-character summary, "O2" (merged into
Three in 2015) and "Worldov" (unidentifiable) stayed as agents.
"""

from unittest.mock import MagicMock, patch

from app.config import Config
from app.services import simulation_manager as sm
from app.services.zep_entity_reader import EntityNode, FilteredEntities

SCENARIO = "Revolut launches 5G SIM-only plans in Ireland. How will Irish operators and ComReg react?"


def _filtered(*rows):
    nodes = [
        EntityNode(
            uuid=name,
            name=name,
            labels=["Entity", etype],
            summary="",
            attributes={},
            related_edges=[{"fact": f} for f in facts],
        )
        for name, etype, facts in rows
    ]
    return FilteredEntities(
        entities=nodes, entity_types={r[1] for r in rows}, total_count=len(nodes), filtered_count=len(nodes)
    )


ROWS = (
    ("Vodafone Ireland", "MobileNetworkOperator", []),
    ("Eir", "MobileNetworkOperator", []),
    ("ComReg", "Regulator", []),
    ("O2", "MobileNetworkOperator", ["O2 Ireland merged into Three Ireland in 2015", "f2", "f3", "f4"]),
    ("Worldov", "Organization", []),
    ("Revolut Mobile", "MVNOBrand", []),
)


def _answer(*pairs):
    return {"entities": [{"index": i, "category": c, "reason": "r"} for i, c in pairs]}


def test_historical_and_unclear_are_dropped_and_reasoning_is_on():
    filtered = _filtered(*ROWS)
    llm = MagicMock()
    llm.chat_json.return_value = _answer(
        (0, "market_actor"),
        (1, "market_actor"),
        (2, "public_body"),
        (3, "historical"),
        (4, "unclear"),
        (5, "market_actor"),
    )

    sm.drop_irrelevant_agents(filtered, SCENARIO, llm=llm)

    assert [e.name for e in filtered.entities] == ["Vodafone Ireland", "Eir", "ComReg", "Revolut Mobile"]
    assert llm.chat_json.call_args.kwargs["thinking"] is True
    assert llm.chat_json.call_args.kwargs["max_tokens"] >= 8000  # room for the reasoning


def test_prompt_carries_up_to_three_graph_facts_per_entity():
    filtered = _filtered(*ROWS)
    llm = MagicMock()
    llm.chat_json.return_value = {"entities": []}

    sm.drop_irrelevant_agents(filtered, SCENARIO, llm=llm)

    prompt = llm.chat_json.call_args.kwargs["messages"][0]["content"]
    assert "O2 Ireland merged into Three Ireland in 2015 ; f2 ; f3" in prompt
    assert "f4" not in prompt
    assert "historical:" in prompt and "unclear:" in prompt


def test_stronger_model_is_used_and_default_model_is_the_fallback():
    filtered = _filtered(*ROWS)
    clients = []

    def make_client(model=None):
        client = MagicMock()
        client.model = model
        if model == Config.AGENT_CHECK_MODEL:
            client.chat_json.side_effect = ValueError("bad json")
        else:
            client.chat_json.return_value = _answer((3, "historical"))
        clients.append(client)
        return client

    with patch.object(sm, "LLMClient", side_effect=make_client):
        sm.drop_irrelevant_agents(filtered, SCENARIO)

    assert [c.model for c in clients] == [Config.AGENT_CHECK_MODEL, None]
    assert clients[0].chat_json.call_args.kwargs["thinking"] is True
    assert "O2" not in [e.name for e in filtered.entities]


def test_agent_check_model_defaults_to_deepseek_pro_on_deepseek():
    from app.config import agent_check_model

    assert agent_check_model("", "https://api.deepseek.com/v1", "deepseek-flash") == "deepseek-v4-pro"
    assert agent_check_model("", "https://api.openai.com/v1", "gpt-4o-mini") == "gpt-4o-mini"
    assert agent_check_model("my-model", "https://api.deepseek.com/v1", "deepseek-flash") == "my-model"
