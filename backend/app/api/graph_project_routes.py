"""Project CRUD routes on the graph blueprint."""

from flask import jsonify, request

from . import graph_bp
from ..config import Config
from ..middleware.auth import require_auth
from ..models.project import ProjectManager, ProjectStatus


@graph_bp.route("/project/<project_id>", methods=["GET"])
@require_auth
def get_project(project_id: str):
    """Get project details"""
    project = ProjectManager.get_project(project_id)

    if not project:
        return jsonify({"success": False, "error": f"Project not found: {project_id}"}), 404

    data = project.to_dict()
    if Config.ENABLE_GROUNDING_FEATURES:
        from ..services.grounding_bundle import evaluate_grounding_staleness

        warns, blocked = evaluate_grounding_staleness(project)
        data["grounding_warnings"] = warns
        data["grounding_blocked"] = blocked

    return jsonify({"success": True, "data": data})


@graph_bp.route("/project/list", methods=["GET"])
@require_auth
def list_projects():
    """List all projects"""
    limit = request.args.get("limit", 50, type=int)
    projects = ProjectManager.list_projects(limit=limit)

    return jsonify({"success": True, "data": [p.to_dict() for p in projects], "count": len(projects)})


@graph_bp.route("/project/<project_id>", methods=["DELETE"])
@require_auth
def delete_project(project_id: str):
    """Delete project"""
    success = ProjectManager.delete_project(project_id)

    if not success:
        return jsonify({"success": False, "error": f"Project not found or delete failed: {project_id}"}), 404

    return jsonify({"success": True, "message": f"Project deleted: {project_id}"})


@graph_bp.route("/project/<project_id>/reset", methods=["POST"])
@require_auth
def reset_project(project_id: str):
    """Reset project state (for rebuilding graph)"""
    project = ProjectManager.get_project(project_id)

    if not project:
        return jsonify({"success": False, "error": f"Project not found: {project_id}"}), 404

    if project.ontology:
        project.status = ProjectStatus.ONTOLOGY_GENERATED
    else:
        project.status = ProjectStatus.CREATED

    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    ProjectManager.save_project(project)

    return jsonify({"success": True, "message": f"Project reset: {project_id}", "data": project.to_dict()})
