"""The app's ontology dict -> Graphiti's entity_types / edge_types / edge_type_map.

The dict is what ontology_generator produces and what the Zep store also takes:
``{"entity_types": [{"name", "description", "attributes": [{"name", "description"}]}],
"edge_types": [{"name", "description", "attributes", "source_targets": [{"source", "target"}]}]}``.

Graphiti stores no ontology, so these are passed on every add.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

# Graphiti raises EntityTypeValidationError when a custom attribute clashes with a
# node field. Zep's list (graph_builder, pre-G1) lacked labels, attributes and
# name_embedding. The rename matches Zep's: "name" -> "entity_name".
RESERVED_ATTRIBUTE_NAMES = frozenset(
    {"uuid", "name", "group_id", "labels", "created_at", "summary", "attributes", "name_embedding"}
)

EntityTypes = dict[str, type[BaseModel]]
EdgeTypes = dict[str, type[BaseModel]]
EdgeTypeMap = dict[tuple[str, str], list[str]]


def safe_attr_name(name: str) -> str:
    return f"entity_{name}" if name.lower() in RESERVED_ATTRIBUTE_NAMES else name


def _model(name: str, description: str, attributes: list[dict[str, Any]]) -> type[BaseModel]:
    annotations: dict[str, Any] = {}
    fields: dict[str, Any] = {}
    for attr in attributes:
        attr_name = safe_attr_name(attr["name"])
        annotations[attr_name] = Optional[str]  # noqa: UP045 - pydantic reads this at runtime
        fields[attr_name] = Field(default=None, description=attr.get("description", attr_name))
    return type(name, (BaseModel,), {"__annotations__": annotations, "__doc__": description, **fields})


def build_graphiti_types(ontology: dict[str, Any] | None) -> tuple[EntityTypes, EdgeTypes, EdgeTypeMap]:
    ontology = ontology or {}
    entity_types: EntityTypes = {}
    for e in ontology.get("entity_types", []):
        entity_types[e["name"]] = _model(
            e["name"], e.get("description", f"A {e['name']} entity."), e.get("attributes", [])
        )

    edge_types: EdgeTypes = {}
    edge_type_map: EdgeTypeMap = {}
    for e in ontology.get("edge_types", []):
        edge_types[e["name"]] = _model(
            e["name"], e.get("description", f"A {e['name']} relationship."), e.get("attributes", [])
        )
        for st in e.get("source_targets", []):
            pair = (st.get("source", "Entity"), st.get("target", "Entity"))
            edge_type_map.setdefault(pair, []).append(e["name"])
    if edge_types:
        # Any pair not listed may still use any declared edge type.
        edge_type_map.setdefault(("Entity", "Entity"), list(edge_types))
    return entity_types, edge_types, edge_type_map
