"""End-to-end pipeline task that chains the full simulation workflow."""

from ..celery_app import celery_app
from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("glas.tasks.pipeline")


@celery_app.task(bind=True, name="glas.run_full_pipeline")
def run_full_pipeline(
    self,
    project_id: str,
    simulation_id: str,
    task_id: str,
    graph_id: str,
    max_rounds: int = None,
    user_plan: str = "pro",
):
    """
    Run the complete simulation pipeline:
    prepare_simulation -> run_simulation -> generate_report -> generate_pdf
    """
    from .simulation_tasks import prepare_simulation_task, run_simulation_task
    from .report_tasks import generate_report_task
    from ..models.task import TaskManager, TaskStatus

    task_manager = TaskManager()
    task_manager.update_task(task_id, status=TaskStatus.PROCESSING, message="Starting full pipeline...")

    _, max_round_cap = Config.simulation_limits(user_plan)

    try:
        logger.info(f"Running full pipeline for project {project_id}, simulation {simulation_id} (plan={user_plan})")

        task_manager.update_task(task_id, message="Preparing simulation...", progress=10)
        prepare_simulation_task(simulation_id, task_id, graph_id, user_plan=user_plan)

        task_manager.update_task(task_id, message="Running simulation...", progress=30)
        effective_rounds = max_rounds if max_rounds is not None else max_round_cap
        run_simulation_task(simulation_id, platform="all", max_rounds=effective_rounds, user_plan=user_plan)

        report_task_id = f"report_{simulation_id}"
        task_manager.create_task("report_generate")
        task_manager.update_task(task_id, message="Generating report...", progress=70)
        generate_report_task(simulation_id, report_task_id)

        task_manager.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            message="Pipeline complete",
            progress=100,
            result={"project_id": project_id, "simulation_id": simulation_id},
        )

        logger.info(f"Full pipeline complete for {simulation_id}")

    except Exception as e:
        logger.error(f"Pipeline failed for {simulation_id}: {e}")
        task_manager.update_task(
            task_id,
            status=TaskStatus.FAILED,
            message=f"Pipeline failed: {e}",
            error=str(e),
        )
        raise
