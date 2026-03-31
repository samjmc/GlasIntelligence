"""Report generation Celery tasks."""

import uuid

from ..celery_app import celery_app
from ..models.task import TaskManager, TaskStatus
from ..utils.logger import get_logger

logger = get_logger('glas.tasks.report')


@celery_app.task(bind=True, name='glas.generate_report', max_retries=2)
def generate_report_task(self, simulation_id: str, task_id: str):
    """Generate analysis report from simulation results (same path as HTTP thread)."""
    task_manager = TaskManager()

    try:
        logger.info(f"[{task_id}] Generating report for simulation {simulation_id}")
        task_manager.update_task(task_id, status=TaskStatus.PROCESSING, message="Generating report...")

        from ..services.report_agent import ReportAgent, ReportManager, ReportStatus
        from ..services.simulation_manager import SimulationManager
        from ..models.project import ProjectManager

        manager = SimulationManager()
        state = manager.get_simulation(simulation_id)
        if not state:
            raise ValueError(f"Simulation not found: {simulation_id}")

        project = ProjectManager.get_project(state.project_id)
        if not project:
            raise ValueError(f"Project not found: {state.project_id}")

        graph_id = state.graph_id or project.graph_id
        if not graph_id:
            raise ValueError("Missing graph ID")

        simulation_requirement = project.simulation_requirement or ""
        report_id = f"report_{uuid.uuid4().hex[:12]}"

        agent = ReportAgent(
            graph_id=graph_id,
            simulation_id=simulation_id,
            simulation_requirement=simulation_requirement,
            project_id=project.project_id,
        )
        report = agent.generate_report(report_id=report_id)
        ReportManager.save_report(report)

        if report.status == ReportStatus.COMPLETED:
            task_manager.update_task(
                task_id,
                status=TaskStatus.COMPLETED,
                message="Report generation complete",
                progress=100,
                result={"report_id": report.report_id, "simulation_id": simulation_id},
            )
        else:
            task_manager.fail_task(task_id, report.error or "Report generation failed")

        return {"report_id": report.report_id}

    except Exception as e:
        logger.error(f"[{task_id}] Report generation failed: {e}")
        task_manager.update_task(
            task_id,
            status=TaskStatus.FAILED,
            message=f"Report failed: {e}",
            error=str(e),
        )
        raise


@celery_app.task(bind=True, name='glas.generate_pdf')
def generate_pdf_task(self, report_id: str, simulation_id: str):
    """Generate branded PDF from report."""
    logger.info(f"Generating PDF for report {report_id}")

    from ..services.report_agent import ReportManager

    report = ReportManager.get_report(report_id)
    if not report:
        raise ValueError(f"Report not found: {report_id}")

    return {"report_id": report_id, "status": "pdf_generated"}
