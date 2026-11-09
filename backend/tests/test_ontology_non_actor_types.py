"""Only entities that can plausibly act or speak become agents.

Live run 2026-11-09 (Revolut Mobile in Ireland) produced agents for a points scheme
("RevPoints"), an unrelated utility ("ESB") and a French precedent typed
ForeignEntrantPrecedent ("Iliad/Free"), which then "spoke" in the report. Every typed graph
node becomes an agent, so types that name things are dropped from the ontology and those
nodes stay plain "Entity" graph context.
"""

from unittest.mock import MagicMock

from app.services.ontology_generator import ONTOLOGY_SYSTEM_PROMPT, OntologyGenerator, is_agent_entity_type


def _types(*names):
    return [{"name": n, "description": f"{n} type", "attributes": [], "examples": []} for n in names]


def test_non_actor_types_are_dropped_and_real_stakeholder_types_kept():
    llm = MagicMock()
    llm.chat_json.side_effect = [
        {"entities": [{"name": "Revolut", "category": "company", "context": "Fintech"}]},
        {
            "entity_types": _types(
                "MobileOperator",
                "Regulator",
                "ForeignEntrantPrecedent",
                "LoyaltyProgramme",
                "MobileProducts",
                "GovernmentPolicy",
                "PolicyInstitute",
                "Politician",
                "Person",
                "Organization",
            ),
            "edge_types": [
                {
                    "name": "COMPETES_WITH",
                    "description": "Competes",
                    "source_targets": [
                        {"source": "MobileOperator", "target": "MobileOperator"},
                        {"source": "MobileOperator", "target": "ForeignEntrantPrecedent"},
                    ],
                }
            ],
        },
    ]

    result = OntologyGenerator(llm_client=llm).generate(["doc"], "Revolut launches Revolut Mobile in Ireland")

    names = [e["name"] for e in result["entity_types"]]
    assert names == ["MobileOperator", "Regulator", "PolicyInstitute", "Politician", "Person", "Organization"]
    assert result["edge_types"][0]["source_targets"] == [{"source": "MobileOperator", "target": "MobileOperator"}]

    ontology_system = llm.chat_json.call_args_list[1].kwargs["messages"][0]["content"]
    assert "Historical precedents or analogues" in ontology_system
    inventory_system = llm.chat_json.call_args_list[0].kwargs["messages"][0]["content"]
    assert "programs, or initiatives" not in inventory_system
    assert "could not plausibly act or speak" in inventory_system


def test_head_noun_rule_is_conservative():
    for actor in ("Company", "MobileOperator", "PolicyInstitute", "LawFirm", "EventOrganiser", "ProgrammeBoard", "TD"):
        assert is_agent_entity_type(actor), actor
    for thing in ("ForeignEntrantPrecedent", "LoyaltyProgram", "Products", "PriceScheme", "MarketEvent", "Law"):
        assert not is_agent_entity_type(thing), thing


def test_ontology_prompt_tells_the_llm_people_become_roles():
    assert "never under their real names" in ONTOLOGY_SYSTEM_PROMPT
