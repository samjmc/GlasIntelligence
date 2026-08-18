"""
Graph API routes
Project-context based, server-side persistent state
"""

import json
import os
import traceback
import threading
from flask import request, jsonify, g

from . import graph_bp
from ..config import Config
from ..middleware.auth import require_auth
from ..services.ontology_generator import OntologyGenerator
from ..services.graph_builder import GraphBuilderService
from ..services.graph_enrichment_service import GraphEnrichmentService
from ..services.graph_snapshot_cache import (
    CacheOutcome,
    get_graph_data_cached,
    invalidate,
    try_stale_fallback,
    write_snapshot,
)
from ..services.text_processor import TextProcessor
from ..utils.file_parser import FileParser
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from ..models.task import TaskManager, TaskStatus
from ..models.project import ProjectManager, ProjectStatus

logger = get_logger('glas.api')


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    if not filename or '.' not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    return ext in Config.ALLOWED_EXTENSIONS


# ============== Project Management Endpoints ==============

@graph_bp.route('/project/<project_id>', methods=['GET'])
@require_auth
def get_project(project_id: str):
    """
    Get project details
    """
    project = ProjectManager.get_project(project_id)
    
    if not project:
        return jsonify({
            "success": False,
            "error": f"Project not found: {project_id}"
        }), 404
    
    data = project.to_dict()
    if Config.ENABLE_GROUNDING_FEATURES:
        from ..services.grounding_bundle import evaluate_grounding_staleness
        warns, blocked = evaluate_grounding_staleness(project)
        data["grounding_warnings"] = warns
        data["grounding_blocked"] = blocked
    
    return jsonify({
        "success": True,
        "data": data
    })


@graph_bp.route('/project/list', methods=['GET'])
@require_auth
def list_projects():
    """
    List all projects
    """
    limit = request.args.get('limit', 50, type=int)
    projects = ProjectManager.list_projects(limit=limit)
    
    return jsonify({
        "success": True,
        "data": [p.to_dict() for p in projects],
        "count": len(projects)
    })


@graph_bp.route('/project/<project_id>', methods=['DELETE'])
@require_auth
def delete_project(project_id: str):
    """
    Delete project
    """
    success = ProjectManager.delete_project(project_id)
    
    if not success:
        return jsonify({
            "success": False,
            "error": f"Project not found or delete failed: {project_id}"
        }), 404
    
    return jsonify({
        "success": True,
        "message": f"Project deleted: {project_id}"
    })


@graph_bp.route('/project/<project_id>/reset', methods=['POST'])
@require_auth
def reset_project(project_id: str):
    """
    Reset project state (for rebuilding graph)
    """
    project = ProjectManager.get_project(project_id)
    
    if not project:
        return jsonify({
            "success": False,
            "error": f"Project not found: {project_id}"
        }), 404
    
    # Reset to ontology-generated state
    if project.ontology:
        project.status = ProjectStatus.ONTOLOGY_GENERATED
    else:
        project.status = ProjectStatus.CREATED
    
    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    ProjectManager.save_project(project)
    
    return jsonify({
        "success": True,
        "message": f"Project reset: {project_id}",
        "data": project.to_dict()
    })


# ============== Endpoint 1: Upload Files and Generate Ontology ==============

@graph_bp.route('/ontology/generate', methods=['POST'])
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
        
        simulation_requirement = request.form.get('simulation_requirement', '')
        project_name = request.form.get('project_name', 'Unnamed Project')
        additional_context = request.form.get('additional_context', '')
        
        # Parse decision intake
        decision_intake = None
        raw_di = request.form.get('decision_intake', '')
        if raw_di:
            try:
                parsed = json.loads(raw_di)
                if isinstance(parsed, dict):
                    decision_intake = parsed
            except (json.JSONDecodeError, TypeError):
                logger.debug("Could not parse decision_intake from form")
        
        # Parse research dossier
        research_dossier = None
        raw_rd = request.form.get('research_dossier', '')
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
            return jsonify({
                "success": False,
                "error": "Please provide simulation_requirement"
            }), 400
        
        uploaded_files = request.files.getlist('files')
        if not uploaded_files or all(not f.filename for f in uploaded_files):
            return jsonify({
                "success": False,
                "error": "Please upload at least one document"
            }), 400
        
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
            dossier_path = os.path.join(project_dir, 'research_dossier.json')
            with open(dossier_path, 'w', encoding='utf-8') as df:
                json.dump(research_dossier, df, ensure_ascii=False, indent=2)
            project.research_dossier_path = dossier_path
        
        logger.info(f"Created project: {project.project_id}")
        
        document_texts = []
        all_text = ""
        
        for file in uploaded_files:
            if file and file.filename and allowed_file(file.filename):
                file_info = ProjectManager.save_file_to_project(
                    project.project_id, 
                    file, 
                    file.filename
                )
                project.files.append({
                    "filename": file_info["original_filename"],
                    "size": file_info["size"]
                })
                
                text = FileParser.extract_text(file_info["path"])
                text = TextProcessor.preprocess_text(text)
                document_texts.append(text)
                all_text += f"\n\n=== {file_info['original_filename']} ===\n{text}"
        
        if not document_texts:
            ProjectManager.delete_project(project.project_id)
            return jsonify({
                "success": False,
                "error": "No documents processed successfully, please check file format"
            }), 400
        
        project.total_text_length = len(all_text)
        ProjectManager.save_extracted_text(project.project_id, all_text)
        logger.info(f"Text extraction complete, {len(all_text)} characters total")
        
        logger.info("Calling LLM to generate ontology definition...")
        generator = OntologyGenerator()
        ontology = generator.generate(
            document_texts=document_texts,
            simulation_requirement=simulation_requirement,
            additional_context=additional_context if additional_context else None
        )
        
        entity_count = len(ontology.get("entity_types", []))
        edge_count = len(ontology.get("edge_types", []))
        inventory_count = len(ontology.get("entity_inventory", []))
        logger.info(f"Ontology generation complete: {entity_count} entity types, {edge_count} edge types, {inventory_count} entities in inventory")
        
        project.ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", [])
        }
        project.entity_inventory = ontology.get("entity_inventory", [])
        project.analysis_summary = ontology.get("analysis_summary", "")
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        from ..services.context_enricher import get_context_enricher
        get_context_enricher().refresh(project)
        ProjectManager.save_project(project)
        logger.info(f"=== Ontology generation complete === Project ID: {project.project_id}")
        
        return jsonify({
            "success": True,
            "data": {
                "project_id": project.project_id,
                "project_name": project.name,
                "ontology": project.ontology,
                "analysis_summary": project.analysis_summary,
                "files": project.files,
                "total_text_length": project.total_text_length
            }
        })
        
    except Exception as e:
        logger.error(f"Ontology generation failed: {e}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": "Ontology generation failed. Please try again."
        }), 500


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


@graph_bp.route('/enhance-prompt', methods=['POST'])
@require_auth
def enhance_prompt():
    """Enhance a rough simulation prompt into a concrete prediction scenario."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Request body required"}), 400

    raw_prompt = (data.get('prompt') or '').strip()
    if not raw_prompt:
        return jsonify({"success": False, "error": "Prompt text required"}), 400

    document_names = data.get('document_names', [])

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

@graph_bp.route('/build', methods=['POST'])
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
            return jsonify({
                "success": False,
                "error": "Configuration error: " + "; ".join(errors)
            }), 500
        
        data = request.get_json() or {}
        project_id = data.get('project_id')
        logger.debug(f"Request params: project_id={project_id}")
        
        if not project_id:
            return jsonify({
                "success": False,
                "error": "Please provide project_id"
            }), 400
        
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": f"Project not found: {project_id}"
            }), 404
        
        force = data.get('force', False)
        
        if project.status == ProjectStatus.CREATED:
            return jsonify({
                "success": False,
                "error": "Ontology not yet generated, please call /ontology/generate first"
            }), 400
        
        if project.status == ProjectStatus.GRAPH_BUILDING and not force:
            return jsonify({
                "success": False,
                "error": "Graph build in progress, do not resubmit. To force rebuild, add force: true",
                "task_id": project.graph_build_task_id
            }), 400
        
        if force and project.status in [ProjectStatus.GRAPH_BUILDING, ProjectStatus.FAILED, ProjectStatus.GRAPH_COMPLETED]:
            project.status = ProjectStatus.ONTOLOGY_GENERATED
            project.graph_id = None
            project.graph_build_task_id = None
            project.error = None
        
        graph_name = data.get('graph_name', project.name or 'Glas Intelligence Graph')
        chunk_size = data.get('chunk_size', project.chunk_size or Config.DEFAULT_CHUNK_SIZE)
        chunk_overlap = data.get('chunk_overlap', project.chunk_overlap or Config.DEFAULT_CHUNK_OVERLAP)
        target_entities = data.get('target_entities', project.target_entities or Config.DEFAULT_TARGET_ENTITIES)
        
        project.chunk_size = chunk_size
        project.chunk_overlap = chunk_overlap
        project.target_entities = target_entities
        
        text = ProjectManager.get_extracted_text(project_id)
        if not text:
            return jsonify({
                "success": False,
                "error": "Extracted text not found"
            }), 400
        
        ontology = project.ontology
        if not ontology:
            return jsonify({
                "success": False,
                "error": "Ontology definition not found"
            }), 400
        
        task_manager = TaskManager()
        task_id = task_manager.create_task(f"Build graph: {graph_name}")
        logger.info(f"Created graph build task: task_id={task_id}, project_id={project_id}")
        
        project.status = ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        ProjectManager.save_project(project)
        
        def build_task():
            build_logger = get_logger('glas.build')
            try:
                build_logger.info(f"[{task_id}] Starting graph build...")
                task_manager.update_task(
                    task_id, 
                    status=TaskStatus.PROCESSING,
                    message="Initializing graph build service..."
                )
                
                builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
                
                task_manager.update_task(
                    task_id,
                    message="Chunking text...",
                    progress=5
                )
                chunks = TextProcessor.split_text(
                    text, 
                    chunk_size=chunk_size, 
                    overlap=chunk_overlap
                )
                total_chunks = len(chunks)
                
                task_manager.update_task(
                    task_id,
                    message="Creating Zep graph...",
                    progress=10
                )
                graph_id = builder.create_graph(name=graph_name)
                
                project.graph_id = graph_id
                ProjectManager.save_project(project)
                
                task_manager.update_task(
                    task_id,
                    message="Setting ontology definition...",
                    progress=15
                )
                builder.set_ontology(graph_id, ontology)
                
                def add_progress_callback(msg, progress_ratio):
                    progress = 15 + int(progress_ratio * 35)
                    task_manager.update_task(
                        task_id,
                        message=msg,
                        progress=progress
                    )
                
                task_manager.update_task(
                    task_id,
                    message=f"Adding {total_chunks} text chunks...",
                    progress=15
                )
                
                episode_uuids = builder.add_text_batches(
                    graph_id, 
                    chunks,
                    batch_size=3,
                    progress_callback=add_progress_callback
                )
                
                task_manager.update_task(
                    task_id,
                    message="Waiting for Zep to process data...",
                    progress=50
                )
                
                def wait_progress_callback(msg, progress_ratio):
                    progress = 50 + int(progress_ratio * 25)
                    task_manager.update_task(
                        task_id,
                        message=msg,
                        progress=progress
                    )
                
                builder._wait_for_episodes(episode_uuids, wait_progress_callback)
                
                task_manager.update_task(
                    task_id,
                    message="Fetching graph data...",
                    progress=75
                )
                graph_data = builder.get_graph_data(graph_id)
                node_count = graph_data.get("node_count", 0)
                edge_count = graph_data.get("edge_count", 0)
                build_logger.info(f"[{task_id}] Initial build: {node_count} nodes, {edge_count} edges")
                
                entity_inventory = project.entity_inventory
                if node_count < target_entities and entity_inventory:
                    build_logger.info(
                        f"[{task_id}] Starting enrichment: {node_count} nodes < {target_entities} target, "
                        f"{len(entity_inventory)} entities in inventory"
                    )
                    
                    def enrichment_progress_callback(msg, progress_ratio):
                        progress = 75 + int(progress_ratio * 20)
                        task_manager.update_task(
                            task_id,
                            message=msg,
                            progress=progress
                        )
                    
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
                        node_count = graph_data.get("node_count", 0)
                        edge_count = graph_data.get("edge_count", 0)
                    except Exception as enrich_err:
                        build_logger.warning(f"[{task_id}] Enrichment failed (non-fatal): {enrich_err}")
                
                project.status = ProjectStatus.GRAPH_COMPLETED
                ProjectManager.save_project(project)
                
                build_logger.info(f"[{task_id}] Graph build complete: graph_id={graph_id}, nodes={node_count}, edges={edge_count}")
                
                write_snapshot(graph_id, graph_data)
                
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
                        "chunk_count": total_chunks
                    }
                )
                
            except Exception as e:
                build_logger.error(f"[{task_id}] Graph build failed: {str(e)}")
                build_logger.debug(traceback.format_exc())
                
                project.status = ProjectStatus.FAILED
                project.error = str(e)
                ProjectManager.save_project(project)
                
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message=f"Build failed: {str(e)}",
                    error=traceback.format_exc()
                )
        
        thread = threading.Thread(target=build_task, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True,
            "data": {
                "project_id": project_id,
                "task_id": task_id,
                "message": "Graph build task started, query progress via /task/{task_id}"
            }
        })
        
    except Exception as e:
        logger.error(f"Graph build failed: {e}")
        logger.debug(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": "Graph build failed. Please try again."
        }), 500


# ============== Task Query Endpoints ==============

@graph_bp.route('/task/<task_id>', methods=['GET'])
@require_auth
def get_task(task_id: str):
    """
    Query task status
    """
    task = TaskManager().get_task(task_id)
    
    if not task:
        return jsonify({
            "success": False,
            "error": f"Task not found: {task_id}"
        }), 404
    
    return jsonify({
        "success": True,
        "data": task.to_dict()
    })


@graph_bp.route('/tasks', methods=['GET'])
@require_auth
def list_tasks():
    """
    List all tasks
    """
    tasks = TaskManager().list_tasks()
    
    return jsonify({
        "success": True,
        "data": [t.to_dict() for t in tasks],
        "count": len(tasks)
    })


# ============== Graph Data Endpoints ==============

@graph_bp.route('/data/<graph_id>', methods=['GET'])
@require_auth
def get_graph_data(graph_id: str):
    """
    Get graph data (nodes and edges)

    Uses the on-disk snapshot cache when GRAPH_SNAPSHOT_CACHE_ENABLED=1;
    `refresh=true` forces a Zep fetch and re-primes the cache. Response
    headers X-Glas-Graph-Cache and X-Glas-Graph-Cache-Age report the outcome.
    On Zep failure, serves a stale snapshot within the stale max age.
    """
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "ZEP_API_KEY not configured"
            }), 500
        
        refresh = request.args.get('refresh', 'false').lower() in ('1', 'true', 'yes')
        
        builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
        graph_data, outcome, age = get_graph_data_cached(
            graph_id,
            lambda: builder.get_graph_data(graph_id),
            refresh=refresh,
        )
        
        resp = jsonify({
            "success": True,
            "data": graph_data
        })
        resp.headers["X-Glas-Graph-Cache"] = outcome.value
        if age is not None:
            resp.headers["X-Glas-Graph-Cache-Age"] = str(int(age))
        return resp
        
    except Exception as e:
        logger.error(f"Get graph data failed: {e}")
        stale = try_stale_fallback(graph_id)
        if stale.outcome == CacheOutcome.STALE and stale.data:
            logger.warning(f"Serving stale graph data for {graph_id} after Zep failure: {e}")
            resp = jsonify({
                "success": True,
                "data": stale.data
            })
            resp.headers["X-Glas-Graph-Cache"] = "STALE"
            if stale.age_seconds is not None:
                resp.headers["X-Glas-Graph-Cache-Age"] = str(int(stale.age_seconds))
            return resp
        return jsonify({
            "success": False,
            "error": "Failed to retrieve graph data"
        }), 500


@graph_bp.route('/delete/<graph_id>', methods=['DELETE'])
@require_auth
def delete_graph(graph_id: str):
    """
    Delete Zep graph
    """
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": "ZEP_API_KEY not configured"
            }), 500
        
        builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
        builder.delete_graph(graph_id)
        invalidate(graph_id)
        
        return jsonify({
            "success": True,
            "message": f"Graph deleted: {graph_id}"
        })
        
    except Exception as e:
        logger.error(f"Graph deletion failed: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to delete graph"
        }), 500
