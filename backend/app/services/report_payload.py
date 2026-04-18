"""
Versioned structured report payload (v1) + scenario ladder generation.
"""

from __future__ import annotations

import json
from typing import Any

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .grounding_bundle import grounding_summary_text

logger = get_logger("glas.report_payload")

REPORT_PAYLOAD_VERSION = 1

REPORT_DISCLAIMER_MD = (
    "**Disclaimer:** Probability ranges and risk scores below are **simulation-derived** "
    "(behavioural rehearsal from the synthetic environment), not market forecasts or "
    "investment advice. Confidence intervals represent the statistical spread given the "
    "model's own uncertainty estimates — they do not guarantee real-world outcomes. "
    "Real-world facts appear only when tied to listed sources in the grounding section.\n\n"
)


def generate_scenario_ladder_json(
    llm: LLMClient,
    simulation_requirement: str,
    quant_summary: str,
    risk_summary: str,
) -> list[dict[str, Any]]:
    """
    LLM produces strict JSON scenario branches aligned with simulation evidence.
    """
    system = """You are a scenario analyst for simulation-based foresight.
Return ONLY valid JSON:
{
  "scenarios": [
    {
      "name": "short label e.g. Base case",
      "assumptions": ["bullet", "bullet"],
      "outcome_narrative": "2-4 sentences tied to simulation themes",
      "probability_range": { "low": 10, "mid": 25, "high": 40 },
      "qualitative_only": false
    }
  ]
}
Rules:
- Provide exactly 3 scenarios: base, upside, stress (or de-escalation).
- probability_range is a subjective simulation-derived bracket; low < mid < high (percentages 0-100).
- Do not claim real stock prices or legal facts not in the provided summaries.
- Write in English.
"""
    user = (
        f"[Simulation requirement]\n{simulation_requirement}\n\n"
        f"[Quantitative summary]\n{quant_summary[:8000]}\n\n"
        f"[Risk / probability summary]\n{risk_summary[:8000]}"
    )
    try:
        data = llm.chat_json(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.25,
            max_tokens=2500,
        )
        scenarios = data.get("scenarios") or []
        if len(scenarios) < 2:
            return _placeholder_scenarios()
        return scenarios[:5]
    except Exception as e:
        logger.warning(f"Scenario ladder LLM failed: {e}")
        return _placeholder_scenarios()


def _placeholder_scenarios() -> list[dict[str, Any]]:
    return [
        {
            "name": "Base case",
            "assumptions": ["Current simulation trajectory continues."],
            "outcome_narrative": "Discourse remains polarised but contained within observed ranges.",
            "probability_range": {"low": 30, "mid": 45, "high": 55},
            "qualitative_only": True,
        },
        {
            "name": "Upside / resolution",
            "assumptions": ["Key stakeholders converge; escalation signals fade."],
            "outcome_narrative": "Activity softens; consensus metrics improve versus baseline.",
            "probability_range": {"low": 15, "mid": 25, "high": 35},
            "qualitative_only": True,
        },
        {
            "name": "Stress case",
            "assumptions": ["Fault lines deepen; aggressive actions dominate later rounds."],
            "outcome_narrative": "Escalation metrics worsen; minority positions harden.",
            "probability_range": {"low": 20, "mid": 30, "high": 40},
            "qualitative_only": True,
        },
    ]


def render_grounding_markdown(project, staleness_warnings: list[dict[str, Any]], claims: list[dict[str, Any]]) -> str:
    lines = [
        "**Grounding and assumptions**",
        "",
        grounding_summary_text(project) if project else "(No project context)",
        "",
    ]
    if staleness_warnings:
        lines.append("**Freshness notices:**")
        for w in staleness_warnings:
            lines.append(f"- {w.get('message', w)}")
        lines.append("")
    if claims:
        lines.append("**Document-backed context (user-provided):**")
        for c in claims[:12]:
            lines.append(f"- {c.get('text', '')} _(source: {c.get('source_id', 'n/a')})_")
        lines.append("")
    lines.append(
        "Hard facts about the real world outside the simulation should only be stated when "
        "they appear in the sources above or are explicitly marked as user assumptions."
    )
    return "\n".join(lines)


def render_scenarios_markdown(scenarios: list[dict[str, Any]]) -> str:
    lines = ["**Scenario ladder** (simulation-derived brackets)", ""]
    for s in scenarios:
        name = s.get("name", "Scenario")
        pr = s.get("probability_range") or {}
        lo, mid, hi = pr.get("low"), pr.get("mid"), pr.get("high")
        rng = f"{lo}–{mid}–{hi}%" if lo is not None else "n/a"
        lines.append(f"**{name}** _(indicative range {rng})_")
        for a in s.get("assumptions") or []:
            lines.append(f"- {a}")
        lines.append("")
        lines.append(s.get("outcome_narrative", "").strip())
        lines.append("")
    return "\n".join(lines).strip()


def render_financial_summary_markdown(financial_summary: dict[str, Any] | None) -> str:
    """Render financial estimate ranges as a markdown table when applicable."""
    if not financial_summary or not financial_summary.get("applicable"):
        return ""

    lines = [
        "**Financial Estimates** (simulation-derived ranges)",
        "",
        "| Metric | Low | High | Unit |",
        "|--------|-----|------|------|",
    ]
    for key, label in [("revenue_range", "Revenue"), ("cost_range", "Costs"), ("profit_range", "Profit")]:
        rng = financial_summary.get(key)
        if rng:
            lines.append(f"| {label} | {rng.get('low', 'n/a')} | {rng.get('high', 'n/a')} | {rng.get('unit', '')} |")

    be = financial_summary.get("break_even")
    th = financial_summary.get("time_horizon")
    if be:
        lines.extend(["", f"**Break-even:** {be}"])
    if th:
        lines.append(f"**Time horizon:** {th}")
    lines.append("")
    return "\n".join(lines)


def render_causal_chain_markdown(causal_chain: list[dict[str, Any]] | None) -> str:
    """Render the causal reasoning chain as a markdown flow."""
    if not causal_chain:
        return ""
    lines = [
        "**Why This Makes Sense**",
        "",
    ]
    for link in causal_chain:
        cause = link.get("cause", "")
        effect = link.get("effect", "")
        conf = link.get("confidence", "")
        conf_label = f" _{conf} confidence_" if conf else ""
        lines.append(f"- **{cause}** \u2192 {effect}{conf_label}")
    lines.append("")
    return "\n".join(lines)


def render_decision_markdown(decision_payload: dict[str, Any] | None) -> str:
    """Render the decision framework as a report section in markdown."""
    if not decision_payload:
        return "*Decision recommendation not available for this simulation.*"

    conf_rationale = decision_payload.get("confidence_rationale", "")
    conf_line = f"(Confidence: {decision_payload.get('confidence', 'N/A')})"
    if conf_rationale:
        conf_line += f" — _{conf_rationale}_"

    lines = [
        f"**Verdict: {decision_payload.get('verdict', 'N/A')}** {conf_line}",
        "",
        decision_payload.get("reasoning", ""),
        "",
    ]

    drivers = decision_payload.get("key_drivers") or []
    if drivers:
        lines.append("**Key Drivers**")
        lines.append("")
        lines.append("| Driver | Direction | Magnitude |")
        lines.append("|--------|-----------|-----------|")
        for d in drivers:
            lines.append(f"| {d.get('name', '')} | {d.get('direction', '')} | {d.get('magnitude', '')} |")
        lines.append("")

    causal_md = render_causal_chain_markdown(decision_payload.get("causal_chain"))
    if causal_md:
        lines.append(causal_md)

    sensitivity = decision_payload.get("sensitivity") or []
    if sensitivity:
        lines.append("**Sensitivity Analysis**")
        lines.append("")
        lines.append("| Variable | Base Value | Swing | Impact on Verdict |")
        lines.append("|----------|------------|-------|-------------------|")
        for s in sensitivity:
            lines.append(
                f"| {s.get('variable', '')} | {s.get('base_value', '')} | "
                f"{s.get('swing_pct', '')} | {s.get('impact_on_verdict', '')} |"
            )
        lines.append("")

    flips = decision_payload.get("flip_conditions") or []
    if flips:
        lines.append("**Conditions That Would Reverse This Verdict**")
        lines.append("")
        for fc in flips:
            lines.append(f"- {fc}")
        lines.append("")

    actions = decision_payload.get("recommended_actions") or []
    if actions:
        lines.append("**Recommended Actions**")
        lines.append("")
        lines.append("| Priority | Action | Rationale | Timeline |")
        lines.append("|----------|--------|-----------|----------|")
        for a in actions:
            lines.append(
                f"| {a.get('priority', '').upper()} | {a.get('action', '')} | "
                f"{a.get('rationale', '')} | {a.get('timeline', '')} |"
            )
        lines.append("")

    criteria = decision_payload.get("decision_criteria") or []
    if criteria:
        lines.append("**Decision Criteria** (validate before acting)")
        lines.append("")
        for dc in criteria:
            lines.append(f"- [ ] {dc}")
        lines.append("")

    indicators = decision_payload.get("monitoring_indicators") or []
    if indicators:
        lines.append("**Monitoring Indicators**")
        lines.append("")
        lines.append("| Indicator | Current State | Threshold | Action if Triggered |")
        lines.append("|-----------|---------------|-----------|---------------------|")
        for m in indicators:
            lines.append(
                f"| {m.get('indicator', '')} | {m.get('current_state', '')} | "
                f"{m.get('threshold', '')} | {m.get('action_if_triggered', '')} |"
            )
        lines.append("")

    ts = decision_payload.get("time_sensitivity")
    if ts:
        lines.append(f"**Time Sensitivity:** {ts}")
        lines.append("")

    fin_md = render_financial_summary_markdown(decision_payload.get("financial_summary"))
    if fin_md:
        lines.append(fin_md)

    return "\n".join(lines)


def normalize_scenario_probabilities(
    scenarios: list[dict[str, Any]],
    mc_data: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Post-process scenario probabilities for consistency:
    1. If MC data exists for outcomes, align scenario brackets with MC CIs.
    2. Flag scenarios where probabilities don't make directional sense.
    3. Add a normalized flag for transparency.
    """
    if not scenarios:
        return scenarios

    total_mid = sum((s.get("probability_range") or {}).get("mid", 0) for s in scenarios)

    for s in scenarios:
        pr = s.get("probability_range") or {}
        low = pr.get("low", 0)
        mid = pr.get("mid", 0)
        high = pr.get("high", 0)

        if low > mid:
            pr["low"] = mid
        if mid > high:
            pr["high"] = mid

        s["probability_range"] = pr

    if total_mid > 0:
        for s in scenarios:
            s.setdefault("_meta", {})["raw_mid"] = (s.get("probability_range") or {}).get("mid", 0)
            s["_meta"]["probability_sum"] = round(total_mid, 1)
            s["_meta"]["non_exhaustive"] = total_mid < 85 or total_mid > 115

    if mc_data and mc_data.get("per_outcome"):
        per_outcome = mc_data["per_outcome"]
        for s in scenarios:
            s_name = (s.get("name") or "").lower()
            for mc_item in per_outcome:
                if mc_item is None:
                    continue
                mc_outcome = (mc_item.get("outcome") or "").lower()
                if _fuzzy_match(s_name, mc_outcome):
                    mc_cis = mc_item.get("monte_carlo", {}).get("confidence_intervals", {})
                    ci95 = mc_cis.get("95%")
                    if ci95:
                        s.setdefault("_meta", {})["mc_ci_95"] = ci95
                        s["_meta"]["mc_mean"] = mc_item["monte_carlo"].get("mean")
                    break

    return scenarios


def _fuzzy_match(a: str, b: str) -> bool:
    """Simple word-overlap match for scenario-to-outcome alignment."""
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return False
    overlap = len(words_a & words_b)
    return overlap >= 2 or (overlap >= 1 and min(len(words_a), len(words_b)) <= 3)


def cross_validate_estimates(
    probability_assessment: dict[str, Any] | None,
    scenarios: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """
    Check directional consistency between ProbabilityAssessment outcomes
    and scenario ladder probabilities. Returns a list of warning strings.
    """
    warnings: list[dict[str, str]] = []
    if not probability_assessment:
        return warnings

    estimates = probability_assessment.get("estimates", [])
    if not estimates or not scenarios:
        return warnings

    for est in estimates:
        est_mid = est.get("probability_range", {}).get("mid", 0)
        est_outcome = (est.get("outcome") or "").lower()

        for s in scenarios:
            s_name = (s.get("name") or "").lower()
            if not _fuzzy_match(est_outcome, s_name):
                continue

            s_mid = (s.get("probability_range") or {}).get("mid", 0)
            if abs(est_mid - s_mid) > 20:
                warnings.append(
                    {
                        "type": "probability_mismatch",
                        "message": (
                            f"Scenario '{s.get('name')}' has midpoint {s_mid}% but "
                            f"the probability assessment estimates '{est.get('outcome')}' at {est_mid}% — "
                            f"a gap of {abs(est_mid - s_mid):.0f} percentage points."
                        ),
                    }
                )

    return warnings


def _load_structured_precedents(project) -> list[dict[str, Any]]:
    """Load structured precedents from the research dossier on disk."""
    import os

    dossier_path = getattr(project, "research_dossier_path", None) if project else None
    if not dossier_path or not os.path.isfile(dossier_path):
        return []
    try:
        with open(dossier_path, encoding="utf-8") as f:
            dossier = json.load(f)
        return dossier.get("structured_precedents", [])
    except (json.JSONDecodeError, OSError):
        return []


def build_report_payload_v1(
    simulation_requirement: str,
    simulation_id: str,
    graph_id: str,
    project,
    metrics_payload: dict[str, Any] | None,
    positions_payload: dict[str, Any] | None,
    risks_payload: dict[str, Any] | None,
    stakeholder_matrix_payload: dict[str, Any] | None,
    scenarios: list[dict[str, Any]],
    staleness_warnings: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    decision_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    grounding_text = grounding_summary_text(project) if project else ""

    monte_carlo = None
    if risks_payload and risks_payload.get("monte_carlo"):
        monte_carlo = risks_payload["monte_carlo"]

    normalized_scenarios = normalize_scenario_probabilities(scenarios, monte_carlo)

    prob_assessment = risks_payload.get("probability_assessment") if risks_payload else None
    consistency_warnings = cross_validate_estimates(prob_assessment, normalized_scenarios)

    payload: dict[str, Any] = {
        "version": REPORT_PAYLOAD_VERSION,
        "simulation_requirement": simulation_requirement,
        "simulation_id": simulation_id,
        "graph_id": graph_id,
        "project_id": getattr(project, "project_id", None) if project else None,
        "grounding": {
            "summary_text": grounding_text,
            "staleness_warnings": staleness_warnings,
            "claims": claims,
        },
        "quant": {
            "metrics": metrics_payload,
            "positions": positions_payload,
            "risks": risks_payload,
            "stakeholder_matrix": stakeholder_matrix_payload,
        },
        "scenarios": normalized_scenarios,
        "flags": {
            "enable_report_payload_v1": Config.ENABLE_REPORT_PAYLOAD_V1,
            "enable_grounding": Config.ENABLE_GROUNDING_FEATURES,
            "enable_decision_layer": Config.ENABLE_DECISION_LAYER,
        },
    }
    if monte_carlo is not None:
        payload["monte_carlo"] = monte_carlo
    if consistency_warnings:
        payload["consistency_warnings"] = consistency_warnings

    structured_precedents = _load_structured_precedents(project)
    if structured_precedents:
        payload["historical_comparison"] = {
            "precedents": structured_precedents,
            "count": len(structured_precedents),
        }

    if decision_payload is not None:
        payload["decision"] = decision_payload
    return payload


def payload_preamble_for_prompt(payload: dict[str, Any], max_chars: int = 12000) -> str:
    """Inject into section system prompt — model must not contradict these tables."""
    try:
        s = json.dumps(payload, ensure_ascii=False, indent=2)
    except Exception:
        s = str(payload)
    if len(s) > max_chars:
        s = s[: max_chars - 3] + "..."
    return (
        "═══ STRUCTURED REPORT PAYLOAD (authoritative tables; do not contradict) ═══\n"
        f"{s}\n"
        "═══════════════════════════════════════════════════════════════════════════"
    )
