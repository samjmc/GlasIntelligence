"""Zep entity listing routes for the simulation API blueprint."""

import traceback

from flask import jsonify, request

from . import simulation_bp
from ..config import Config
from ..middleware.auth import require_auth
from ..services.zep_entity_reader import ZepEntityReader
from ..utils.logger import get_logger

logger = get_logger("glas.api.simulation")


@simulation_bp.route("/entities/<graph_id>", methods=["GET"])
@require_auth
def get_graph_entities(graph_id: str):
    """
    Get all entities from graph (filtered)

    Returns only nodes matching predefined entity types (nodes whose Labels are not just Entity)

    Query parameters:
        entity_types: Comma-separated list of entity types (optional, for further filtering)
        enrich: Whether to include related edge info (default true)
    """
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({"success": False, "error": "ZEP_API_KEY not configured"}), 500

        entity_types_str = request.args.get("entity_types", "")
        entity_types = [t.strip() for t in entity_types_str.split(",") if t.strip()] if entity_types_str else None
        enrich = request.args.get("enrich", "true").lower() == "true"

        logger.info(f"Getting graph entities: graph_id={graph_id}, entity_types={entity_types}, enrich={enrich}")

        reader = ZepEntityReader()
        result = reader.filter_defined_entities(
            graph_id=graph_id, defined_entity_types=entity_types, enrich_with_edges=enrich
        )

        return jsonify({"success": True, "data": result.to_dict()})

    except Exception as e:
        logger.error(f"Failed to get graph entities: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@simulation_bp.route("/entities/<graph_id>/<entity_uuid>", methods=["GET"])
@require_auth
def get_entity_detail(graph_id: str, entity_uuid: str):
    """Get detailed info for a single entity"""
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({"success": False, "error": "ZEP_API_KEY not configured"}), 500

        reader = ZepEntityReader()
        entity = reader.get_entity_with_context(graph_id, entity_uuid)

        if not entity:
            return jsonify({"success": False, "error": f"Entity not found: {entity_uuid}"}), 404

        return jsonify({"success": True, "data": entity.to_dict()})

    except Exception as e:
        logger.error(f"Failed to get entity detail: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@simulation_bp.route("/entities/<graph_id>/by-type/<entity_type>", methods=["GET"])
@require_auth
def get_entities_by_type(graph_id: str, entity_type: str):
    """Get all entities of a given type"""
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({"success": False, "error": "ZEP_API_KEY not configured"}), 500

        enrich = request.args.get("enrich", "true").lower() == "true"

        reader = ZepEntityReader()
        entities = reader.get_entities_by_type(graph_id=graph_id, entity_type=entity_type, enrich_with_edges=enrich)

        return jsonify(
            {
                "success": True,
                "data": {
                    "entity_type": entity_type,
                    "count": len(entities),
                    "entities": [e.to_dict() for e in entities],
                },
            }
        )

    except Exception as e:
        logger.error(f"Failed to get entities: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500
