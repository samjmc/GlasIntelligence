"""Report API: debugging tools, PDF queue, and compare."""

import os
import traceback

from flask import jsonify, request, send_file

from . import report_bp
from ..middleware.auth import require_auth
from ..services.report_agent import ReportManager
from ..utils.logger import get_logger

logger = get_logger("glas.api.report")


@report_bp.route("/tools/search", methods=["POST"])
@require_auth
def search_graph_tool():
    """
    Graph search tool endpoint (for debugging)

    Request (JSON):
        {
            "graph_id": "glas_xxxx",
            "query": "search query",
            "limit": 10
        }
    """
    try:
        data = request.get_json() or {}

        graph_id = data.get("graph_id")
        query = data.get("query")
        limit = data.get("limit", 10)

        if not graph_id or not query:
            return jsonify({"success": False, "error": "Please provide graph_id and query"}), 400

        from ..services.zep_tools import ZepToolsService

        tools = ZepToolsService()
        result = tools.search_graph(graph_id=graph_id, query=query, limit=limit)

        return jsonify({"success": True, "data": result.to_dict()})

    except Exception as e:
        logger.error(f"Graph search failed: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@report_bp.route("/<report_id>/pdf", methods=["POST"])
@require_auth
def generate_pdf(report_id):
    """Generate and download a branded PDF for a report."""
    try:
        report = ReportManager.get_report(report_id)
        if not report:
            return jsonify({"success": False, "error": "Report not found"}), 404

        report_dir = ReportManager._get_report_dir(report_id)
        pdf_path = os.path.join(report_dir, f"{report_id}.pdf")

        if os.path.exists(pdf_path):
            return send_file(pdf_path, as_attachment=True, download_name="Glas_Intelligence_Report.pdf")

        full_report_path = os.path.join(report_dir, "full_report.md")
        if not os.path.exists(full_report_path):
            return jsonify({"success": False, "error": "Report content not found"}), 404

        return jsonify({"success": True, "data": {"status": "pdf_generation_queued", "report_id": report_id}})
    except Exception as e:
        logger.error(f"PDF generation failed: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


@report_bp.route("/tools/statistics", methods=["POST"])
@require_auth
def get_graph_statistics_tool():
    """
    Graph statistics tool endpoint (for debugging)

    Request (JSON):
        {
            "graph_id": "glas_xxxx"
        }
    """
    try:
        data = request.get_json() or {}

        graph_id = data.get("graph_id")

        if not graph_id:
            return jsonify({"success": False, "error": "Please provide graph_id"}), 400

        from ..services.zep_tools import ZepToolsService

        tools = ZepToolsService()
        result = tools.get_graph_statistics(graph_id)

        return jsonify({"success": True, "data": result})

    except Exception as e:
        logger.error(f"Failed to get graph statistics: {str(e)}")
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@report_bp.route("/compare", methods=["POST"])
@require_auth
def compare_reports():
    """Compare multiple report payloads side-by-side."""
    try:
        data = request.get_json() or {}
        report_ids = data.get("report_ids", [])

        if len(report_ids) < 2 or len(report_ids) > 4:
            return jsonify({"success": False, "error": "Provide 2-4 report_ids"}), 400

        reports = []
        for rid in report_ids:
            payload = ReportManager.load_payload_v1(rid)
            if not payload:
                continue
            decision = payload.get("decision", {}) or {}
            quant = payload.get("quant", {}) or {}
            mc = payload.get("monte_carlo", {}) or {}

            metrics = quant.get("metrics", {}) or {}
            sim_metrics = metrics.get("simulation_metrics", {}) or {}
            escalation = metrics.get("escalation_analysis", {}) or {}

            positions = quant.get("positions", {}) or {}
            consensus = positions.get("consensus_metrics", {}) or {}

            scenario_summaries = []
            for s in payload.get("scenarios", []) or []:
                pr = s.get("probability_range", {}) or {}
                scenario_summaries.append(
                    {
                        "name": s.get("name", ""),
                        "probability_mid": pr.get("mid"),
                        "qualitative_only": s.get("qualitative_only", False),
                    }
                )

            mc_composite = mc.get("composite", {}) or {}
            mc_summary = None
            if mc_composite:
                ci95 = (mc_composite.get("confidence_intervals", {}) or {}).get("95%")
                mc_summary = {
                    "mean": mc_composite.get("mean"),
                    "median": mc_composite.get("median"),
                    "ci_95": ci95,
                    "converged": (mc_composite.get("convergence", {}) or {}).get("converged"),
                }

            reports.append(
                {
                    "report_id": rid,
                    "title": payload.get("simulation_requirement", rid)[:100],
                    "verdict": decision.get("verdict", "N/A"),
                    "confidence": decision.get("confidence", "N/A"),
                    "key_drivers": decision.get("key_drivers", []),
                    "scenarios": scenario_summaries,
                    "quant_summary": {
                        "total_actions": sim_metrics.get("total_actions", 0),
                        "total_agents": sim_metrics.get("total_agents", 0),
                        "engagement_rate": sim_metrics.get("engagement_rate", 0),
                        "overall_trend": escalation.get("overall_trend", "unknown"),
                        "polarization_index": consensus.get("polarization_index", 0),
                        "agreement_ratio": consensus.get("agreement_ratio", 0),
                    },
                    "monte_carlo": mc_summary,
                    "time_sensitivity": decision.get("time_sensitivity", ""),
                }
            )

        return jsonify(
            {
                "success": True,
                "data": {
                    "count": len(reports),
                    "reports": reports,
                },
            }
        )

    except Exception as e:
        logger.error(f"Report comparison failed: {e}", exc_info=True)
        return jsonify({"success": False, "error": "Comparison failed"}), 500
