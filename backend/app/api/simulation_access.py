"""
Owner check for the simulation, graph and report APIs.

Ownership lives on disk: ``ProjectManager.create_project`` stamps the creating user's id
into ``project.json``, and simulations, reports and graphs belong to their project's owner.
(The Supabase ``projects`` / ``simulations`` tables are never written, so they cannot answer
this.) A run whose project has no recorded owner is refused while auth is on.

``require_owner`` runs before every route of the three blueprints and checks each id the
request names (path, query string or JSON body, singly or as a ``<field>s`` list). List
routes filter their rows with ``caller_may_see``. Not-found and not-yours get the same 404,
so the check does not reveal which ids exist. With auth off (no Supabase configured, one
local user) nothing is checked, like ``require_auth``.
"""

import json
import os
from collections.abc import Callable

from flask import g, jsonify, request

from ..middleware.auth import auth_enabled
from ..models.project import ProjectManager
from ..services.report_agent import ReportManager
from ..services.simulation_manager import SimulationManager
from . import graph_bp, report_bp, simulation_bp


def _safe_id(value) -> bool:
    # A bare directory name only: every id below is joined onto a path.
    return isinstance(value, str) and bool(value) and os.path.basename(value) == value and value not in (".", "..")


def project_owner(project_id: str) -> str | None:
    project = ProjectManager.get_project(project_id)
    return project.user_id if project else None


def simulation_owner(simulation_id: str) -> str | None:
    # Read state.json directly: SimulationManager.get_simulation creates a directory for any id.
    try:
        with open(
            os.path.join(SimulationManager.SIMULATION_DATA_DIR, simulation_id, "state.json"), encoding="utf-8"
        ) as f:
            project_id = json.load(f).get("project_id")
    except (OSError, json.JSONDecodeError):
        return None
    return project_owner(project_id) if _safe_id(project_id) else None


def report_owner(report_id: str) -> str | None:
    report = ReportManager.get_report(report_id)
    return simulation_owner(report.simulation_id) if report and _safe_id(report.simulation_id) else None


def graph_owners(graph_id: str) -> set[str]:
    return {p.user_id for p in ProjectManager.list_projects(limit=None) if p.graph_id == graph_id and p.user_id}


def caller_may_see(owner: str | None) -> bool:
    """For list routes: keep a row only if it belongs to the caller (everything when auth is off)."""
    return not auth_enabled() or (owner is not None and owner == g.user_id)


# Request field -> (label for the 404, owners of that id)
OWNED_FIELDS: dict[str, tuple[str, Callable[[str], set]]] = {
    "simulation_id": ("Simulation", lambda i: {simulation_owner(i)}),
    "project_id": ("Project", lambda i: {project_owner(i)}),
    "report_id": ("Report", lambda i: {report_owner(i)}),
    "graph_id": ("Graph", graph_owners),
}


def _named_ids() -> list[tuple[str, object]]:
    body = request.get_json(silent=True)
    sources = [request.view_args or {}, request.args, body if isinstance(body, dict) else {}]
    named = []
    for src in sources:
        for field in OWNED_FIELDS:
            if src.get(field):
                named.append((field, src[field]))
            plural = src.get(f"{field}s")
            if isinstance(plural, list):
                named.extend((field, value) for value in plural)
    return named


def require_owner():
    if not auth_enabled():
        return None
    named = _named_ids()
    if not named:
        return None
    if not getattr(g, "user_id", None):
        return jsonify({"success": False, "error": "Authentication required"}), 401
    for field, value in named:
        label, owners = OWNED_FIELDS[field]
        if not _safe_id(value) or g.user_id not in owners(value):
            return jsonify({"success": False, "error": f"{label} not found: {value}"}), 404
    return None


for _bp in (simulation_bp, graph_bp, report_bp):
    _bp.before_request(require_owner)
