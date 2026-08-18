"""
Graph API routes
Project-context based, server-side persistent state
"""

import json
import os
import threading
import time
import traceback
from flask import request, jsonify, g, make_response

try:
    from zep_cloud.core.api_error import ApiError as ZepApiError
except ImportError:  # pragma: no cover

    class ZepApiError(Exception):
        """Placeholder if zep_cloud is missing."""

        pass


from . import graph_bp
from ..config import Config
from ..middleware.auth import require_auth
from ..services.ontology_generator import OntologyGenerator
from ..services.graph_builder import GraphBuilderService
from ..services.graph_snapshot_cache import (
    CacheOutcome,
    get_graph_data_cached,
    invalidate,
    try_stale_fallback,
    write_snapshot,
)
from ..services.graph_enrichment_service import GraphEnrichmentService
from ..services.text_processor import TextProcessor
from ..utils.file_parser import FileParser
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from ..models.task import TaskManager, TaskStatus
from ..models.project import ProjectManager, ProjectStatus

logger = get_logger("glas.api")

from . import graph_project_routes  # noqa: F401  # registers project routes on graph_bp

# Per-user, per-graph cooldown for ?refresh=true (in-process; see get_graph_data docstring).
_GRAPH_REFRESH_COOLDOWN_SEC = 30.0
_graph_refresh_last: dict[tuple[str, str], float] = {}
_graph_refresh_lock = threading.Lock()


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    if not filename or "." not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    return ext in Config.ALLOWED_EXTENSIONS


def _project_meta_for_graph_id(graph_id: str) -> dict | None:
    """Load project.json for the project that owns this Zep graph_id, if any."""
    for proj in ProjectManager.list_projects(limit=500):
        if proj.graph_id == graph_id:
            meta_path = ProjectManager._get_project_meta_path(proj.project_id)
            try:
                with open(meta_path, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError, TypeError):
                return None
    return None


def _require_graph_ownership(graph_id: str):
    """If project.json records user_id, enforce it matches g.user_id. Returns Flask response tuple or None."""
    meta = _project_meta_for_graph_id(graph_id)
    if meta is None:
        return jsonify({"success": False, "error": "Graph is not linked to any known project"}), 404
    if not isinstance(meta, dict):
        meta = {}
    owner = meta.get("user_id")
    if owner is not None and owner != getattr(g, "user_id", None):
        return jsonify({"success": False, "error": "Forbidden"}), 403
    return None


def _synthesize_dossier_text(dossier: dict) -> str:
    """Convert dossier structured fields into prose for graph building.

    The deep research dossier JSON contains rich structured data (key_facts,
    quantitative_anchors, historical_precedents, structured_precedents, sources)
    that would otherwise be lost because only summary_md is uploaded as a file.
    """
    parts: list[str] = []

    for fact in dossier.get("key_facts") or []:
        if isinstance(fact, str) and fact.strip():
            parts.append(f"- {fact.strip()}")
    if parts:
        parts.insert(0, "Key Facts:")
        parts.append("")

    anchors = dossier.get("quantitative_anchors") or []
    if anchors:
        parts.append("Quantitative Anchors:")
        for anchor in anchors:
            if isinstance(anchor, str) and anchor.strip():
                parts.append(f"- {anchor.strip()}")
            elif isinstance(anchor, dict):
                label = anchor.get("label") or anchor.get("metric") or ""
                value = anchor.get("value") or anchor.get("figure") or ""
                source = anchor.get("source") or ""
                line = f"- {label}: {value}"
                if source:
                    line += f" (source: {source})"
                parts.append(line)
        parts.append("")

    precedents = dossier.get("historical_precedents") or []
    if precedents:
        parts.append("Historical Precedents:")
        for p in precedents:
            if isinstance(p, str) and p.strip():
                parts.append(f"- {p.strip()}")
            elif isinstance(p, dict):
                name = p.get("name") or p.get("event") or "Unnamed"
                summary = p.get("summary") or p.get("description") or ""
                parts.append(f"- {name}: {summary}")
        parts.append("")

    structured = dossier.get("structured_precedents") or []
    if structured:
        parts.append("Structured Precedents:")
        for sp in structured:
            if isinstance(sp, dict):
                event = sp.get("event") or sp.get("name") or "Unknown event"
                outcome = sp.get("outcome") or ""
                metric = sp.get("key_metric") or ""
                line = f"{event}."
                if outcome:
                    line += f" Outcome: {outcome}."
                if metric:
                    line += f" Key metric: {metric}."
                parts.append(line)
        parts.append("")

    sources = dossier.get("sources") or []
    if sources:
        parts.append("Sources:")
        for s in sources:
            if isinstance(s, str) and s.strip():
                parts.append(f"- {s.strip()}")
            elif isinstance(s, dict):
                title = s.get("title") or s.get("name") or ""
                url = s.get("url") or ""
                label = title or url
                if label:
                    parts.append(f"- {label}" + (f" ({url})" if url and title else ""))
        parts.append("")

    summary_md = dossier.get("summary_md") or ""
    if not isinstance(summary_md, str):
        summary_md = ""
    if summary_md.strip():
        parts.append("Research Briefing:")
        parts.append(summary_md.strip())
        parts.append("")

    return "\n".join(parts).strip()


# ============== Endpoint 1: Upload Files and Generate Ontology ==============


@graph_bp.route("/ontology/generate", methods=["POST"])
@require_auth
def generate_ontology():
    """
    Endpoint 1: Upload files, analyze and generate ontology definition

    Request: multipart/form-data

    Parameters:
        files: Uploaded files (PDF/MD/TXT), multiple allowed
        simulation_requirement: Simulation requirement description (required)
        project_name: Project name (optional)
        additional_context: Additional notes (optional)

    Returns:
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "ontology": {
                    "entity_types": [...],
                    "edge_types": [...],
                    "analysis_summary": "..."
                },
                "files": [...],
                "total_text_length": 12345
            }
        }
    """
    try:
        logger.info("=== Starting ontology generation ===")

        simulation_requirement = request.form.get("simulation_requirement", "")
        project_name = request.form.get("project_name", "Unnamed Project")
        additional_context = request.form.get("additional_context", "")

        # Parse decision intake
        decision_intake = None
        raw_di = request.form.get("decision_intake", "")
        if raw_di:
            try:
                parsed = json.loads(raw_di)
                if isinstance(parsed, dict):
                    decision_intake = parsed
            except (json.JSONDecodeError, TypeError):
                logger.debug("Could not parse decision_intake from form")

        # Parse research dossier
        research_dossier = None
        raw_rd = request.form.get("research_dossier", "")
        if raw_rd:
            try:
                parsed = json.loads(raw_rd)
                if isinstance(parsed, dict):
                    research_dossier = parsed
            except (json.JSONDecodeError, TypeError):
                logger.debug("Could not parse research_dossier from form")

        logger.debug(f"Project name: {project_name}")
        logger.debug(f"Simulation requirement: {simulation_requirement[:100]}...")

        if not simulation_requirement:
            return jsonify({"success": False, "error": "Please provide simulation_requirement"}), 400

        uploaded_files = request.files.getlist("files")
        has_files = uploaded_files and any(f.filename for f in uploaded_files)
        if not has_files and not research_dossier:
            return jsonify({"success": False, "error": "Please upload at least one document or run deep research"}), 400

        project = ProjectManager.create_project(name=project_name)
        project.simulation_requirement = simulation_requirement

        if decision_intake:
            project.decision_intake = decision_intake
            decision_summary = (
                f"Decision context — Role: {decision_intake.get('role', 'N/A')}, "
                f"Question: {decision_intake.get('decision', 'N/A')}"
            )
            additional_context = (decision_summary + "\n\n" + additional_context).strip()

        if research_dossier:
            project_dir = ProjectManager._get_project_dir(project.project_id)
            os.makedirs(project_dir, exist_ok=True)
            dossier_path = os.path.join(project_dir, "research_dossier.json")
            with open(dossier_path, "w", encoding="utf-8") as df:
                json.dump(research_dossier, df, ensure_ascii=False, indent=2)
            project.research_dossier_path = dossier_path

        logger.info(f"Created project: {project.project_id}")

        document_texts = []
        all_text = ""

        if research_dossier:
            dossier_supplement = _synthesize_dossier_text(research_dossier)
            if dossier_supplement:
                document_texts.append(dossier_supplement)
                all_text += f"\n\n=== Deep Research Structured Data ===\n{dossier_supplement}"
                logger.info(f"Added {len(dossier_supplement)} chars of dossier structured data")

        for file in uploaded_files:
            if file and file.filename and allowed_file(file.filename):
                file_info = ProjectManager.save_file_to_project(project.project_id, file, file.filename)
                project.files.append({"filename": file_info["original_filename"], "size": file_info["size"]})

                text = FileParser.extract_text(file_info["path"])
                text = TextProcessor.preprocess_text(text)
                document_texts.append(text)
                all_text += f"\n\n=== {file_info['original_filename']} ===\n{text}"

        if not document_texts:
            ProjectManager.delete_project(project.project_id)
            return jsonify(
                {"success": False, "error": "No documents processed successfully, please check file format"}
            ), 400

        project.total_text_length = len(all_text)
        ProjectManager.save_extracted_text(project.project_id, all_text)
        logger.info(f"Text extraction complete, {len(all_text)} characters total")

        logger.info("Calling LLM to generate ontology definition...")
        generator = OntologyGenerator()
        ontology = generator.generate(
            document_texts=document_texts,
            simulation_requirement=simulation_requirement,
            additional_context=additional_context if additional_context else None,
        )

        entity_count = len(ontology.get("entity_types", []))
        edge_count = len(ontology.get("edge_types", []))
        inventory_count = len(ontology.get("entity_inventory", []))
        logger.info(
            f"Ontology generation complete: {entity_count} entity types, {edge_count} edge types, {inventory_count} entities in inventory"
        )

        project.ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", []),
        }
        project.entity_inventory = ontology.get("entity_inventory", [])
        project.analysis_summary = ontology.get("analysis_summary", "")
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        from ..services.context_enricher import get_context_enricher

        get_context_enricher().refresh(project)
        ProjectManager.save_project(project)
        logger.info(f"=== Ontology generation complete === Project ID: {project.project_id}")

        return jsonify(
            {
                "success": True,
                "data": {
                    "project_id": project.project_id,
                    "project_name": project.name,
                    "ontology": project.ontology,
                    "analysis_summary": project.analysis_summary,
                    "files": project.files,
                    "total_text_length": project.total_text_length,
                },
            }
        )

    except Exception as e:
        logger.error(f"Ontology generation failed: {e}")
        logger.debug(traceback.format_exc())
        return jsonify({"success": False, "error": "Ontology generation failed. Please try again."}), 500


# ============== Prompt Enhancer ==============

ENHANCE_SYSTEM_PROMPT = """\
You are a simulation scenario designer. The user will give you a rough idea for a \
geopolitical, economic, or social prediction scenario. Your job is to rewrite it into \
a concrete, structured simulation prompt.

Rules:
- 2-4 sentences maximum
- Start with a clear triggering event or condition
- Name specific real-world stakeholders, institutions, companies, or governments
- Include a time horizon (e.g., "over the following 6 months")
- End with explicit prediction questions: "How do [actors] react?" or "Predict the impact on [domain]"
- Do NOT use bullet points or markdown formatting -- write flowing prose
- Do NOT add disclaimers or caveats
- Output ONLY the enhanced prompt text, nothing else"""


@graph_bp.route("/enhance-prompt", methods=["POST"])
@require_auth
def enhance_prompt():
    """Enhance a rough simulation prompt into a concrete prediction scenario."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    raw_prompt = (data.get("prompt") or "").strip()
    if not raw_prompt:
        return jsonify({"success": False, "error": "Prompt text required"}), 400

    document_names = data.get("document_names", [])
    if not isinstance(document_names, list):
        document_names = []

    user_content = f"Rough prompt: {raw_prompt}"
    if document_names:
        user_content += f"\nUploaded documents: {', '.join(document_names)}"

    try:
        llm = LLMClient()
        enhanced = llm.chat(
            messages=[
                {"role": "system", "content": ENHANCE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.5,
            max_tokens=500,
        )
        return jsonify({"success": True, "enhanced_prompt": enhanced.strip()})
    except Exception as e:
        logger.error(f"Prompt enhancement failed: {e}")
        return jsonify({"success": False, "error": "Prompt enhancement failed"}), 500


# ============== Endpoint 2: Build Graph ==============


@graph_bp.route("/build", methods=["POST"])
@require_auth
def build_graph():
    """
    Endpoint 2: Build graph from project_id

    Request (JSON):
        {
            "project_id": "proj_xxxx",  // required, from endpoint 1
            "graph_name": "Graph name", // optional
            "chunk_size": 500,          // optional, default 500
            "chunk_overlap": 50         // optional, default 50
        }

    Returns:
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "task_id": "task_xxxx",
                "message": "Graph build task started"
            }
        }
    """
    try:
        logger.info("=== Starting graph build ===")

        errors = []
        if not Config.ZEP_API_KEY:
            errors.append("ZEP_API_KEY not configured")
        if errors:
            logger.error(f"Configuration error: {errors}")
            return jsonify({"success": False, "error": "Configuration error: " + "; ".join(errors)}), 500

        data = request.get_json() or {}
        project_id = data.get("project_id")
        logger.debug(f"Request params: project_id={project_id}")

        if not project_id:
            return jsonify({"success": False, "error": "Please provide project_id"}), 400

        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({"success": False, "error": f"Project not found: {project_id}"}), 404

        force = data.get("force", False)

        if project.status == ProjectStatus.CREATED:
            return jsonify(
                {"success": False, "error": "Ontology not yet generated, please call /ontology/generate first"}
            ), 400

        if project.status == ProjectStatus.GRAPH_BUILDING and not force:
            return jsonify(
                {
                    "success": False,
                    "error": "Graph build in progress, do not resubmit. To force rebuild, add force: true",
                    "task_id": project.graph_build_task_id,
                }
            ), 400

        if force and project.status in [
            ProjectStatus.GRAPH_BUILDING,
            ProjectStatus.FAILED,
            ProjectStatus.GRAPH_COMPLETED,
        ]:
            project.status = ProjectStatus.ONTOLOGY_GENERATED
            project.graph_id = None
            project.graph_build_task_id = None
            project.error = None

        graph_name = data.get("graph_name", project.name or "Glas Intelligence Graph")
        chunk_size = data.get("chunk_size", project.chunk_size or Config.DEFAULT_CHUNK_SIZE)
        chunk_overlap = data.get("chunk_overlap", project.chunk_overlap or Config.DEFAULT_CHUNK_OVERLAP)
        if not isinstance(chunk_size, int) or isinstance(chunk_size, bool) or chunk_size <= 0:
            chunk_size = project.chunk_size or Config.DEFAULT_CHUNK_SIZE
        if not isinstance(chunk_overlap, int) or isinstance(chunk_overlap, bool) or chunk_overlap < 0:
            chunk_overlap = project.chunk_overlap or Config.DEFAULT_CHUNK_OVERLAP
        target_entities = data.get("target_entities", project.target_entities or Config.DEFAULT_TARGET_ENTITIES)
        if not isinstance(target_entities, int) or isinstance(target_entities, bool) or target_entities <= 0:
            target_entities = Config.DEFAULT_TARGET_ENTITIES

        user_plan = "free"
        if getattr(g, "user_id", None) and g.user_id != "anonymous":
            from ..services.supabase_client import SupabaseDB

            profile = SupabaseDB.get_profile(g.user_id)
            if profile:
                user_plan = Config.normalize_plan(profile.get("plan", "free"))
        max_agents, _ = Config.simulation_limits(user_plan)
        target_entities = min(target_entities, max_agents)
        logger.info(f"Plan={user_plan}, clamped target_entities={target_entities} (cap={max_agents})")

        project.chunk_size = chunk_size
        project.chunk_overlap = chunk_overlap
        project.target_entities = target_entities

        text = ProjectManager.get_extracted_text(project_id)
        if not text:
            return jsonify({"success": False, "error": "Extracted text not found"}), 400

        ontology = project.ontology
        if not ontology:
            return jsonify({"success": False, "error": "Ontology definition not found"}), 400

        task_manager = TaskManager()
        task_id = task_manager.create_task(
            f"Build graph: {graph_name}",
            metadata={"user_id": getattr(g, "user_id", None)},
        )
        logger.info(f"Created graph build task: task_id={task_id}, project_id={project_id}")

        project.status = ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        ProjectManager.save_project(project)

        def build_task():
            build_logger = get_logger("glas.build")
            try:
                build_logger.info(f"[{task_id}] Starting graph build...")
                task_manager.update_task(
                    task_id, status=TaskStatus.PROCESSING, message="Initializing graph build service..."
                )

                builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)

                task_manager.update_task(task_id, message="Chunking text...", progress=5)
                chunks = TextProcessor.split_text(text, chunk_size=chunk_size, overlap=chunk_overlap)
                total_chunks = len(chunks)

                task_manager.update_task(task_id, message="Creating Zep graph...", progress=10)
                graph_id = builder.create_graph(name=graph_name)

                project.graph_id = graph_id
                ProjectManager.save_project(project)
                try:
                    from ..services.supabase_client import SupabaseDB

                    SupabaseDB.propagate_graph_id_for_project(project_id, graph_id)
                except Exception:
                    build_logger.exception("propagate_graph_id_for_project after graph create failed")

                task_manager.update_task(task_id, message="Setting ontology definition...", progress=15)
                builder.set_ontology(graph_id, ontology)

                def add_progress_callback(msg, progress_ratio):
                    progress = 15 + int(progress_ratio * 35)
                    task_manager.update_task(task_id, message=msg, progress=progress)

                task_manager.update_task(task_id, message=f"Adding {total_chunks} text chunks...", progress=15)

                episode_uuids = builder.add_text_batches(
                    graph_id, chunks, batch_size=3, progress_callback=add_progress_callback
                )

                task_manager.update_task(task_id, message="Waiting for Zep to process data...", progress=50)

                def wait_progress_callback(msg, progress_ratio):
                    progress = 50 + int(progress_ratio * 25)
                    task_manager.update_task(task_id, message=msg, progress=progress)

                builder._wait_for_episodes(episode_uuids, wait_progress_callback)

                task_manager.update_task(task_id, message="Fetching graph data...", progress=75)
                graph_data = builder.get_graph_data(graph_id)
                write_snapshot(graph_id, graph_data)
                node_count = graph_data.get("node_count", 0)
                edge_count = graph_data.get("edge_count", 0)

                typed_node_count = sum(
                    1
                    for n in graph_data.get("nodes", [])
                    if any(l not in ("Entity", "Node") for l in (n.get("labels") or []))
                )
                build_logger.info(
                    f"[{task_id}] Initial build: {node_count} nodes ({typed_node_count} typed), {edge_count} edges"
                )

                entity_inventory = project.entity_inventory
                if typed_node_count < target_entities and entity_inventory:
                    build_logger.info(
                        f"[{task_id}] Starting enrichment: {typed_node_count} typed nodes < {target_entities} target, "
                        f"{len(entity_inventory)} entities in inventory"
                    )

                    def enrichment_progress_callback(msg, progress_ratio):
                        progress = 75 + int(progress_ratio * 20)
                        task_manager.update_task(task_id, message=msg, progress=progress)

                    try:
                        enrichment_service = GraphEnrichmentService(
                            zep_client=builder.client,
                            llm_client=LLMClient(),
                        )
                        enrichment_result = enrichment_service.enrich_graph(
                            graph_id=graph_id,
                            source_text=text,
                            entity_inventory=entity_inventory,
                            target_entities=target_entities,
                            max_rounds=Config.MAX_ENRICHMENT_ROUNDS,
                            progress_callback=enrichment_progress_callback,
                        )
                        build_logger.info(
                            f"[{task_id}] Enrichment done: {enrichment_result.initial_nodes} → "
                            f"{enrichment_result.final_nodes} nodes ({enrichment_result.stopped_reason})"
                        )
                        graph_data = builder.get_graph_data(graph_id)
                        write_snapshot(graph_id, graph_data)
                        node_count = graph_data.get("node_count", 0)
                        edge_count = graph_data.get("edge_count", 0)
                    except Exception as enrich_err:
                        build_logger.warning(f"[{task_id}] Enrichment failed (non-fatal): {enrich_err}")

                project.status = ProjectStatus.GRAPH_COMPLETED
                ProjectManager.save_project(project)
                try:
                    from ..services.supabase_client import SupabaseDB

                    SupabaseDB.propagate_graph_id_for_project(project_id, graph_id)
                except Exception:
                    build_logger.exception("propagate_graph_id_for_project after graph complete failed")

                build_logger.info(
                    f"[{task_id}] Graph build complete: graph_id={graph_id}, nodes={node_count}, edges={edge_count}"
                )

                task_manager.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED,
                    message="Graph build complete",
                    progress=100,
                    result={
                        "project_id": project_id,
                        "graph_id": graph_id,
                        "node_count": node_count,
                        "edge_count": edge_count,
                        "chunk_count": total_chunks,
                    },
                )

            except Exception as e:
                build_logger.error(f"[{task_id}] Graph build failed: {str(e)}")
                build_logger.debug(traceback.format_exc())

                project.status = ProjectStatus.FAILED
                project.error = str(e)
                ProjectManager.save_project(project)

                task_manager.update_task(
                    task_id, status=TaskStatus.FAILED, message=f"Build failed: {str(e)}", error=traceback.format_exc()
                )

        thread = threading.Thread(target=build_task, daemon=True)
        thread.start()

        return jsonify(
            {
                "success": True,
                "data": {
                    "project_id": project_id,
                    "task_id": task_id,
                    "message": "Graph build task started, query progress via /task/{task_id}",
                },
            }
        )

    except Exception as e:
        logger.error(f"Graph build failed: {e}")
        logger.debug(traceback.format_exc())
        return jsonify({"success": False, "error": "Graph build failed. Please try again."}), 500


# ============== Task Query Endpoints ==============


@graph_bp.route("/task/<task_id>", methods=["GET"])
@require_auth
def get_task(task_id: str):
    """
    Query task status
    """
    task = TaskManager().get_task(task_id)

    if not task:
        return jsonify({"success": False, "error": f"Task not found: {task_id}"}), 404

    task_owner = (task.metadata or {}).get("user_id")
    if task_owner is not None and task_owner != getattr(g, "user_id", None):
        return jsonify({"success": False, "error": "Forbidden"}), 403

    return jsonify({"success": True, "data": task.to_dict()})


@graph_bp.route("/tasks", methods=["GET"])
@require_auth
def list_tasks():
    """
    List all tasks
    """
    # Scope to caller via task metadata. build_graph passes metadata["user_id"] on create_task.
    # Tasks created elsewhere without that field are invisible to this filter.
    uid = getattr(g, "user_id", None)
    if not uid or uid == "anonymous":
        tasks = []
    else:
        tasks = [t for t in TaskManager().list_tasks() if t.get("metadata", {}).get("user_id") == uid]

    return jsonify({"success": True, "data": tasks, "count": len(tasks)})


# ============== Graph Data Endpoints ==============


def _graph_data_response(graph_data: dict, outcome: CacheOutcome, age_seconds: float | None):
    # Zep NER pulls quantitative anchors ('2.7%', '£17', '2026') as typed
    # nodes; filter them at the serve point so every cache outcome and the
    # demo tapes present stakeholder-only graphs.
    from ..services.graph_noise_filter import filter_quant_noise

    nodes, edges = graph_data.get("nodes") or [], graph_data.get("edges") or []
    filtered_nodes, filtered_edges = filter_quant_noise(nodes, edges)
    if len(filtered_nodes) != len(nodes):
        graph_data["nodes"] = filtered_nodes
        graph_data["edges"] = filtered_edges
        graph_data["node_count"] = len(filtered_nodes)
        graph_data["edge_count"] = len(filtered_edges)

    resp = make_response(jsonify({"success": True, "data": graph_data}))
    resp.headers["X-Glas-Graph-Cache"] = outcome.value
    if age_seconds is not None:
        resp.headers["X-Glas-Graph-Cache-Age"] = str(max(0, int(age_seconds)))
    return resp


@graph_bp.route("/data/<graph_id>", methods=["GET"])
@require_auth
def get_graph_data(graph_id: str):
    """
    Get graph data (nodes and edges).
    Query: refresh=true forces Zep fetch and re-primes cache (max once per user/graph per 30s).
    Headers: X-Glas-Graph-Cache = HIT | MISS | STALE | BYPASS | DISABLED
    """
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({"success": False, "error": "ZEP_API_KEY not configured"}), 500

        denied = _require_graph_ownership(graph_id)
        if denied is not None:
            return denied

        refresh_requested = request.args.get("refresh", "").lower() in ("1", "true", "yes")
        refresh = refresh_requested
        if refresh_requested:
            uid_key = str(getattr(g, "user_id", None) or "anonymous")
            key = (uid_key, graph_id)
            now = time.monotonic()
            with _graph_refresh_lock:
                last = _graph_refresh_last.get(key)
                if last is not None and (now - last) < _GRAPH_REFRESH_COOLDOWN_SEC:
                    refresh = False
                    logger.debug(
                        "graph refresh throttled for user=%s graph=%s (cooldown=%ss)",
                        uid_key,
                        graph_id,
                        int(_GRAPH_REFRESH_COOLDOWN_SEC),
                    )
                else:
                    _graph_refresh_last[key] = now
                    cutoff = now - _GRAPH_REFRESH_COOLDOWN_SEC
                    stale_keys = [k for k, t in _graph_refresh_last.items() if t < cutoff]
                    for k in stale_keys:
                        del _graph_refresh_last[k]

        builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)

        def fetch_from_zep():
            return builder.get_graph_data(graph_id)

        try:
            graph_data, outcome, age = get_graph_data_cached(graph_id, fetch_from_zep, refresh=refresh)
            return _graph_data_response(graph_data, outcome, age)
        except ZepApiError as e:
            status = getattr(e, "status_code", None) or 502
            stale = try_stale_fallback(graph_id)
            if stale.data and stale.outcome == CacheOutcome.STALE:
                logger.warning("Serving stale graph cache for %s after Zep error (status=%s)", graph_id, status)
                return _graph_data_response(stale.data, CacheOutcome.STALE, stale.age_seconds)

            body = getattr(e, "body", None)
            detail = body if isinstance(body, str) else (str(body) if body is not None else str(e))
            detail = (detail or "Zep API error")[:500]
            if status == 429:
                logger.warning("Zep graph rate limit for %s: %s", graph_id, detail)
                return jsonify(
                    {
                        "success": False,
                        "error": "zep_rate_limited",
                        "detail": detail,
                    },
                ), 429
            logger.error("Zep graph API error (%s) for %s: %s", status, graph_id, detail)
            return jsonify(
                {"success": False, "error": "Failed to retrieve graph data", "detail": detail},
            ), 502

    except Exception as e:
        logger.error(f"Get graph data failed: {e}", exc_info=True)
        detail = (str(e) or "unknown error")[:500]
        return jsonify(
            {"success": False, "error": "Failed to retrieve graph data", "detail": detail},
        ), 500


@graph_bp.route("/delete/<graph_id>", methods=["DELETE"])
@require_auth
def delete_graph(graph_id: str):
    """
    Delete Zep graph
    """
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({"success": False, "error": "ZEP_API_KEY not configured"}), 500

        denied = _require_graph_ownership(graph_id)
        if denied is not None:
            return denied

        builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
        builder.delete_graph(graph_id)
        invalidate(graph_id)

        return jsonify({"success": True, "message": f"Graph deleted: {graph_id}"})

    except Exception as e:
        logger.error(f"Graph deletion failed: {e}")
        return jsonify({"success": False, "error": "Failed to delete graph"}), 500
