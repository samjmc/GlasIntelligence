"""Graph building Celery tasks."""

from ..celery_app import celery_app
from ..models.task import TaskManager, TaskStatus
from ..models.project import ProjectManager, ProjectStatus
from ..services.graph_builder import GraphBuilderService
from ..services.graph_snapshot_cache import write_snapshot
from ..services.text_processor import TextProcessor
from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("glas.tasks.graph")


@celery_app.task(bind=True, name="glas.build_graph", max_retries=2)
def build_graph_task(
    self, project_id: str, task_id: str, graph_name: str, chunk_size: int = 500, chunk_overlap: int = 50
):
    """Build knowledge graph from project documents via Zep."""
    task_manager = TaskManager()

    try:
        logger.info(f"[{task_id}] Starting graph build for project {project_id}")
        task_manager.update_task(task_id, status=TaskStatus.PROCESSING, message="Initializing graph build...")

        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        text = ProjectManager.get_extracted_text(project_id)
        if not text:
            raise ValueError("Extracted text not found")

        ontology = project.ontology
        if not ontology:
            raise ValueError("Ontology definition not found")

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
            logger.exception("propagate_graph_id_for_project after graph create failed")

        task_manager.update_task(task_id, message="Setting ontology...", progress=15)
        builder.set_ontology(graph_id, ontology)

        def add_progress_callback(msg, progress_ratio):
            progress = 15 + int(progress_ratio * 40)
            task_manager.update_task(task_id, message=msg, progress=progress)

        task_manager.update_task(task_id, message=f"Adding {total_chunks} text chunks...", progress=15)
        episode_uuids = builder.add_text_batches(
            graph_id, chunks, batch_size=3, progress_callback=add_progress_callback
        )

        task_manager.update_task(task_id, message="Waiting for Zep processing...", progress=55)

        def wait_progress_callback(msg, progress_ratio):
            progress = 55 + int(progress_ratio * 35)
            task_manager.update_task(task_id, message=msg, progress=progress)

        builder._wait_for_episodes(episode_uuids, wait_progress_callback)

        task_manager.update_task(task_id, message="Fetching graph data...", progress=95)
        graph_data = builder.get_graph_data(graph_id)
        write_snapshot(graph_id, graph_data)

        project.status = ProjectStatus.GRAPH_COMPLETED
        ProjectManager.save_project(project)
        try:
            from ..services.supabase_client import SupabaseDB

            SupabaseDB.propagate_graph_id_for_project(project_id, graph_id)
        except Exception:
            logger.exception("propagate_graph_id_for_project after graph complete failed")

        node_count = graph_data.get("node_count", 0)
        edge_count = graph_data.get("edge_count", 0)

        result = {
            "project_id": project_id,
            "graph_id": graph_id,
            "node_count": node_count,
            "edge_count": edge_count,
            "chunk_count": total_chunks,
        }

        task_manager.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            message="Graph build complete",
            progress=100,
            result=result,
        )

        logger.info(f"[{task_id}] Graph build complete: {node_count} nodes, {edge_count} edges")
        return result

    except Exception as e:
        logger.error(f"[{task_id}] Graph build failed: {e}")
        project = ProjectManager.get_project(project_id)
        if project:
            project.status = ProjectStatus.FAILED
            project.error = str(e)
            ProjectManager.save_project(project)

        task_manager.update_task(
            task_id,
            status=TaskStatus.FAILED,
            message=f"Build failed: {e}",
            error=str(e),
        )
        raise
