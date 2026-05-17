"""Bundle execution Celery task — runs all scenarios in a bundle sequentially."""

import json
import os
import threading
import time

from ..celery_app import celery_app
from ..config import Config
from ..services.supabase_client import SupabaseDB
from ..utils.logger import get_logger

logger = get_logger("glas.tasks.bundle")

POLL_INTERVAL = 10
MAX_PREPARE_WAIT = 1800
MAX_RUN_WAIT = 7200


def _wait_for_preparation(simulation_id, timeout=MAX_PREPARE_WAIT):
    """Poll until simulation preparation completes, fails, or times out."""
    from ..api.simulation_helpers import check_simulation_prepared
    from ..services.simulation_manager import SimulationManager, SimulationStatus

    mgr = SimulationManager()
    elapsed = 0
    while elapsed < timeout:
        is_prepared, _ = check_simulation_prepared(simulation_id)
        if is_prepared:
            return True
        sim = mgr.get_simulation(simulation_id)
        if sim and sim.status == SimulationStatus.FAILED:
            return False
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
    return False


def _wait_for_completion(simulation_id, timeout=MAX_RUN_WAIT):
    """Poll run_state until the simulation finishes or times out."""
    from ..services.simulation_runner import SimulationRunner

    elapsed = 0
    while elapsed < timeout:
        run_state = SimulationRunner.get_run_state(simulation_id)
        if run_state and run_state.runner_status.value in ("completed", "failed", "stopped"):
            return run_state.runner_status.value
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
    return "timeout"


# Celery: acks_late=True so the message is acked only after the task body finishes — if the
# worker dies mid-run, the task is redelivered. max_retries=0 is intentional: bundle runs are
# long, partially mutate state (credits, simulations), and are not idempotent — automatic
# retries would risk double-charging or duplicate sims. Failures surface in bundle status;
# operators/users must explicitly re-run if needed.
@celery_app.task(
    bind=True,
    name="glas.run_bundle",
    acks_late=True,
    max_retries=0,
    soft_time_limit=14400,
    time_limit=14700,
)
def run_bundle_task(self, bundle_id, session_id, user_id):
    """Execute all scenarios in a decision bundle sequentially.

    For each scenario:
      1. Create a new simulation under the same project/graph
      2. Prepare it (entity extraction + config generation)
      3. Run the simulation
      4. Wait for completion
      5. Record result in the bundle's completed_scenarios
    """
    bundle = SupabaseDB.get_bundle(bundle_id, user_id=user_id)
    if not bundle:
        if SupabaseDB.get_bundle(bundle_id) is None:
            logger.error(f"Bundle {bundle_id} not found")
            SupabaseDB.update_bundle(bundle_id, status="failed", error="Bundle not found")
        else:
            logger.error(
                f"Bundle {bundle_id} ownership mismatch — row may be stuck as running; manual intervention required."
            )
        return

    active_task = bundle.get("celery_task_id")
    if active_task and active_task != self.request.id:
        logger.warning(
            f"Bundle {bundle_id}: stale task {self.request.id} "
            f"(active={active_task}), aborting to prevent duplicate execution"
        )
        return

    scenarios = bundle.get("suggested_scenarios", [])
    if not isinstance(scenarios, list):
        SupabaseDB.update_bundle(bundle_id, status="failed", error="Invalid scenarios format")
        return
    if not scenarios:
        SupabaseDB.update_bundle(bundle_id, status="failed", error="No scenarios to run")
        return

    session = SupabaseDB.get_session(session_id)
    if not session:
        SupabaseDB.update_bundle(bundle_id, status="failed", error="Session not found")
        return

    from ..models.project import ProjectManager
    from ..models.task import TaskManager, TaskStatus
    from ..services.simulation_manager import SimulationManager, SimulationStatus
    from ..services.simulation_runner import SimulationRunner

    sim_id_from_session = session.get("simulation_id")
    if not sim_id_from_session:
        SupabaseDB.update_bundle(bundle_id, status="failed", error="No simulation_id on session — start engine first")
        return

    manager = SimulationManager()
    base_state = manager.get_simulation(sim_id_from_session)
    if not base_state:
        SupabaseDB.update_bundle(bundle_id, status="failed", error=f"Base simulation {sim_id_from_session} not found")
        return

    project_id = base_state.project_id
    graph_id = base_state.graph_id

    project = ProjectManager.get_project(project_id)
    if not project:
        SupabaseDB.update_bundle(bundle_id, status="failed", error=f"Project {project_id} not found")
        return

    document_text = ProjectManager.get_extracted_text(project_id) or ""

    profile = SupabaseDB.get_profile(user_id)
    user_plan = Config.normalize_plan(profile.get("plan", "free") if profile else "free")

    completed_scenarios = []
    had_failure = False
    bundle_time_scale_override = None
    profile_source_sim_id = None

    for i, scenario in enumerate(scenarios):
        if not isinstance(scenario, dict):
            logger.warning(
                f"Bundle {bundle_id}: skipping scenario index {i} (expected dict, got {type(scenario).__name__})"
            )
            completed_scenarios.append(
                {
                    "scenario_index": i,
                    "status": "skipped",
                    "title": "",
                    "error": "Invalid scenario format",
                    "failed": True,
                }
            )
            had_failure = True
            continue
        scenario_title = scenario.get("title", f"Scenario {i + 1}")
        scenario_prompt = scenario.get("scenario", "")
        if not scenario_prompt:
            scenario_prompt = scenario.get("change_summary", scenario_title)

        logger.info(f"Bundle {bundle_id}: starting scenario {i + 1}/{len(scenarios)} — {scenario_title}")

        SupabaseDB.update_bundle(bundle_id, current_scenario_index=i, current_simulation_id=None)

        try:
            if not SupabaseDB.deduct_credit(user_id, f"Bundle sim: {scenario_title[:60]}"):
                entry = {
                    "scenario_index": i,
                    "title": scenario_title,
                    "simulation_id": None,
                    "failed": True,
                    "error": "insufficient_credits",
                }
                completed_scenarios.append(entry)
                SupabaseDB.update_bundle(bundle_id, completed_scenarios=completed_scenarios)
                logger.warning(f"Bundle {bundle_id}: insufficient credits at scenario {i}")
                had_failure = True
                break

            sim_state = manager.create_simulation(
                project_id=project_id,
                graph_id=graph_id,
                enable_twitter=base_state.enable_twitter,
                enable_reddit=base_state.enable_reddit,
            )
            sim_id = sim_state.simulation_id
            SupabaseDB.update_bundle(bundle_id, current_simulation_id=sim_id)
            logger.info(f"Bundle {bundle_id}: created sim {sim_id} for scenario {i}")

            task_manager = TaskManager()
            task_id = task_manager.create_task(
                task_type="simulation_prepare",
                metadata={"simulation_id": sim_id, "project_id": project_id, "bundle_id": bundle_id},
            )

            sim_state.status = SimulationStatus.PREPARING
            manager._save_simulation_state(sim_state)

            def run_prepare(s_id, s_req, doc_text, t_id, u_plan, tmgr, smgr, ts_override, src_sim):
                try:
                    tmgr.update_task(t_id, status=TaskStatus.PROCESSING, progress=0, message="Preparing...")
                    result = smgr.prepare_simulation(
                        simulation_id=s_id,
                        simulation_requirement=s_req,
                        document_text=doc_text,
                        use_llm_for_profiles=True,
                        user_plan=u_plan,
                        time_scale_override=ts_override,
                        profile_source_sim_id=src_sim,
                    )
                    tmgr.complete_task(
                        t_id, result=result.to_simple_dict() if hasattr(result, "to_simple_dict") else {}
                    )
                except Exception as e:
                    logger.error(f"Prepare failed for {s_id}: {e}")
                    tmgr.fail_task(t_id, str(e))
                    state = smgr.get_simulation(s_id)
                    if state:
                        state.status = SimulationStatus.FAILED
                        state.error = str(e)
                        smgr._save_simulation_state(state)

            t = threading.Thread(
                target=run_prepare,
                args=(
                    sim_id,
                    scenario_prompt,
                    document_text,
                    task_id,
                    user_plan,
                    task_manager,
                    manager,
                    bundle_time_scale_override,
                    profile_source_sim_id,
                ),
                daemon=True,
            )
            t.start()

            if not _wait_for_preparation(sim_id):
                t.join(timeout=5)
                raise TimeoutError(f"Preparation failed or timed out for {sim_id}")

            # All bundle scenarios share the first scenario's time scale (after prepare, before run).
            if i == 0 and bundle_time_scale_override is None:
                cfg_path = os.path.join(manager.SIMULATION_DATA_DIR, sim_id, "simulation_config.json")
                try:
                    with open(cfg_path, encoding="utf-8") as cf:
                        cfg0 = json.load(cf)
                    tc = cfg0.get("time_config")
                    if isinstance(tc, dict) and tc:
                        bundle_time_scale_override = tc
                        logger.info(
                            "Bundle %s: locked time_config for remaining scenarios from scenario 1 (time_scale=%s)",
                            bundle_id,
                            (tc.get("time_scale") or {}),
                        )
                except Exception:
                    # Exception text omitted from message for a clear operator-facing consequence.
                    # For stack traces in production logs without binding `e`, add exc_info=True here.
                    logger.warning(
                        "Bundle %s: failed to read time_config for scenario 0 after "
                        "prepare — bundle_time_scale_override not set, subsequent "
                        "scenarios will generate independent time configs and may use "
                        "inconsistent time scales",
                        bundle_id,
                    )

            run_state = SimulationRunner.start_simulation(
                simulation_id=sim_id,
                platform="parallel",
                user_plan=user_plan,
            )
            sim_state.status = SimulationStatus.RUNNING
            manager._save_simulation_state(sim_state)
            logger.info(f"Bundle {bundle_id}: simulation {sim_id} started running")

            final_status = _wait_for_completion(sim_id)
            logger.info(f"Bundle {bundle_id}: scenario {i} finished with status={final_status}")

            report_id_val = ""
            if final_status == "completed":
                sim_state.status = SimulationStatus.COMPLETED
                if Config.ENABLE_BUNDLE_SYNTHESIS and Config.ENABLE_REPORT_PAYLOAD_V1:
                    try:
                        import uuid

                        from ..services.report_agent import ReportAgent, ReportManager, ReportStatus

                        rid = f"report_{uuid.uuid4().hex[:12]}"
                        agent = ReportAgent(
                            graph_id=graph_id,
                            simulation_id=sim_id,
                            simulation_requirement=scenario_prompt,
                            project_id=project_id,
                        )
                        report = agent.generate_report(report_id=rid)
                        if report.status == ReportStatus.COMPLETED and ReportManager.load_payload_v1(rid):
                            report_id_val = rid
                        else:
                            logger.warning(
                                "Bundle %s: scenario %s report missing payload or incomplete",
                                bundle_id,
                                i,
                            )
                    except Exception as rep_exc:
                        logger.exception(
                            "Bundle %s: report generation failed for scenario %s: %s",
                            bundle_id,
                            i,
                            rep_exc,
                        )
            elif final_status in ("failed", "timeout"):
                sim_state.status = SimulationStatus.FAILED
                sim_state.error = f"Simulation {final_status}"
            manager._save_simulation_state(sim_state)

            entry = {
                "scenario_index": i,
                "title": scenario_title,
                "simulation_id": sim_id,
                "report_id": report_id_val if final_status == "completed" else "",
                "failed": final_status != "completed",
                "status": final_status,
            }
            completed_scenarios.append(entry)
            SupabaseDB.update_bundle(bundle_id, completed_scenarios=completed_scenarios)

            if final_status == "completed" and not profile_source_sim_id:
                profile_source_sim_id = sim_id
                logger.info(f"Bundle {bundle_id}: locked profile source to {sim_id}")

            if final_status != "completed":
                had_failure = True

        except Exception as e:
            logger.error(f"Bundle {bundle_id}: scenario {i} failed: {e}", exc_info=True)
            entry = {
                "scenario_index": i,
                "title": scenario_title,
                "simulation_id": None,
                "failed": True,
                "error": str(e),
            }
            completed_scenarios.append(entry)
            SupabaseDB.update_bundle(bundle_id, completed_scenarios=completed_scenarios)
            had_failure = True

    final_status = "completed" if not had_failure else "completed_with_errors"
    successful = sum(1 for c in completed_scenarios if not c.get("failed"))
    if successful == 0:
        final_status = "failed"

    synthesis_data = None
    if (
        Config.ENABLE_BUNDLE_SYNTHESIS
        and Config.ENABLE_REPORT_PAYLOAD_V1
        and successful >= 2
        and final_status in ("completed", "completed_with_errors")
    ):
        from ..services.bundle_synthesis import build_bundle_synthesis, load_payloads_from_bundle

        temp_bundle = {
            "title": bundle.get("title"),
            "description": bundle.get("decision_context"),
            "suggested_scenarios": scenarios,
            "completed_scenarios": completed_scenarios,
        }
        payloads_by_index = load_payloads_from_bundle(temp_bundle)
        if len(payloads_by_index) >= 2:
            scenario_meta = []
            for ent in completed_scenarios:
                if ent.get("failed"):
                    continue
                si = ent.get("scenario_index")
                if not isinstance(si, int) or si not in payloads_by_index:
                    continue
                sc = scenarios[si] if 0 <= si < len(scenarios) and isinstance(scenarios[si], dict) else {}
                scenario_meta.append(
                    {
                        "scenario_index": si,
                        "title": ent.get("title") or "",
                        "prompt": sc.get("scenario") or sc.get("change_summary") or "",
                    }
                )
            try:
                synthesis_data = build_bundle_synthesis(temp_bundle, payloads_by_index, scenario_meta)
            except Exception as syn_exc:
                logger.exception("Bundle %s: synthesis build failed: %s", bundle_id, syn_exc)

    update_kw = {
        "status": final_status,
        "completed_scenarios": completed_scenarios,
        "current_scenario_index": None,
        "current_simulation_id": None,
    }
    if synthesis_data is not None:
        update_kw["synthesis"] = synthesis_data
    SupabaseDB.update_bundle(bundle_id, **update_kw)

    SupabaseDB.update_session(
        session_id,
        status="completed" if final_status == "completed" else "sim_failed",
    )

    logger.info(f"Bundle {bundle_id}: finished — {successful}/{len(scenarios)} succeeded, status={final_status}")
