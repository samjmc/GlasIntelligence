"""Simulation Celery tasks."""

from ..celery_app import celery_app
from ..models.task import TaskManager, TaskStatus
from ..utils.logger import get_logger

logger = get_logger("glas.tasks.simulation")


@celery_app.task(bind=True, name="glas.prepare_simulation", max_retries=2)
def prepare_simulation_task(self, simulation_id: str, task_id: str, graph_id: str, user_plan: str = "pro"):
    """Prepare simulation: extract entities, generate profiles and config."""
    task_manager = TaskManager()

    try:
        logger.info(f"[{task_id}] Preparing simulation {simulation_id} (plan={user_plan})")
        task_manager.update_task(task_id, status=TaskStatus.PROCESSING, message="Preparing simulation environment...")

        from ..services.simulation_manager import SimulationManager

        manager = SimulationManager()

        result = manager.prepare_simulation(simulation_id, user_plan=user_plan)

        task_manager.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            message="Simulation preparation complete",
            progress=100,
            result=result if isinstance(result, dict) else {"status": "complete"},
        )

        return result

    except Exception as e:
        logger.error(f"[{task_id}] Simulation preparation failed: {e}")
        task_manager.update_task(
            task_id,
            status=TaskStatus.FAILED,
            message=f"Preparation failed: {e}",
            error=str(e),
        )
        raise


@celery_app.task(bind=True, name="glas.run_simulation", soft_time_limit=3600, time_limit=3900)
def run_simulation_task(self, simulation_id: str, platform: str = "all", max_rounds: int = 40, user_plan: str = "pro"):
    """Run the OASIS simulation."""
    logger.info(f"Running simulation {simulation_id} on {platform} for {max_rounds} rounds (plan={user_plan})")

    from ..services.simulation_runner import SimulationRunner

    runner = SimulationRunner()

    result = runner.start_simulation(simulation_id, platform=platform, max_rounds=max_rounds, user_plan=user_plan)
    return result
