"""Entities whose type names a thing (precedent, programme, product) must not become agents.

Seen live on 2026-11-09: a Revolut Mobile run made "Iliad/Free" (type ForeignEntrantPrecedent)
an agent that then "spoke" in the report.
"""

from app.services.simulation_manager import drop_non_actor_entities
from app.services.zep_entity_reader import EntityNode, FilteredEntities


def _node(name: str, entity_type: str) -> EntityNode:
    return EntityNode(uuid=name, name=name, labels=["Entity", entity_type], summary="", attributes={})


def test_precedents_and_programmes_are_dropped_actors_kept():
    filtered = FilteredEntities(
        entities=[
            _node("Vodafone Ireland", "MobileNetworkOperator"),
            _node("ComReg", "TelecomRegulator"),
            _node("Iliad/Free", "ForeignEntrantPrecedent"),
            _node("RevPoints", "LoyaltyProgramme"),
        ],
        entity_types={"MobileNetworkOperator", "TelecomRegulator", "ForeignEntrantPrecedent", "LoyaltyProgramme"},
        total_count=4,
        filtered_count=4,
    )

    drop_non_actor_entities(filtered)

    assert [e.name for e in filtered.entities] == ["Vodafone Ireland", "ComReg"]
    assert filtered.filtered_count == 2
    assert filtered.entity_types == {"MobileNetworkOperator", "TelecomRegulator"}


def test_all_actors_left_untouched():
    nodes = [_node("Eir", "MobileNetworkOperator"), _node("Revolut", "FintechCompany")]
    filtered = FilteredEntities(entities=list(nodes), entity_types={"X"}, total_count=2, filtered_count=2)

    drop_non_actor_entities(filtered)

    assert filtered.entities == nodes
    assert filtered.entity_types == {"X"}
