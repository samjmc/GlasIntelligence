"""
Multi-scenario bundle executive synthesis: structural LLM output, math marginals, narrative.
"""

from __future__ import annotations

import json
import logging
import math
import re
from typing import Any, Optional

from ..config import Config
from ..utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

# Branch weight bounds (match plan)
_BRANCH_P_MIN = 0.05
_BRANCH_P_MAX = 0.85


def load_payloads_from_bundle(bundle: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Load payload.v1.json for each completed scenario that has report_id."""
    from ..services.report_agent import ReportManager

    out: dict[int, dict[str, Any]] = {}
    for e in bundle.get("completed_scenarios") or []:
        if e.get("failed"):
            continue
        rid = str(e.get("report_id") or "").strip()
        si = e.get("scenario_index")
        if not rid or not isinstance(si, int):
            continue
        pl = ReportManager.load_payload_v1(rid)
        if pl:
            out[si] = pl
    return out


def _slug(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")[:80] or "outcome"


def _payload_estimates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        qa = payload.get("quantitative_analysis") or {}
        risks = qa.get("risks") or {}
        pa = risks.get("probability_assessment") or {}
        est = pa.get("estimates")
        return est if isinstance(est, list) else []
    except Exception:
        return []


def _estimate_mid_percent(est: dict[str, Any]) -> Optional[float]:
    try:
        pr = est.get("probability_range") or {}
        mid = pr.get("mid")
        if mid is not None:
            return float(mid)
        lo = float(pr.get("low") or 0)
        hi = float(pr.get("high") or 0)
        return (lo + hi) / 2.0
    except (TypeError, ValueError):
        return None


def _estimate_variance_percent_sq(est: dict[str, Any]) -> float:
    """Rough variance on 0-100 scale from range width (uniform approx)."""
    try:
        pr = est.get("probability_range") or {}
        lo = float(pr.get("low") or 0)
        hi = float(pr.get("high") or 0)
        w = max(0.0, hi - lo)
        # Var(uniform) = (b-a)^2/12
        return (w * w) / 12.0
    except (TypeError, ValueError):
        return 400.0  # ~ wide default


def _scenario_compact_payload(
    scenario_index: int,
    scenario_title: str,
    scenario_prompt: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    estimates = _payload_estimates(payload)
    est_snips = []
    for i, e in enumerate(estimates):
        outcome = (e.get("outcome") or "")[:200]
        mid = _estimate_mid_percent(e)
        pr = e.get("probability_range") or {}
        est_snips.append(
            {
                "estimate_index": i,
                "outcome": outcome,
                "mid_percent": mid,
                "low": pr.get("low"),
                "high": pr.get("high"),
            }
        )
    verdict = (payload.get("decision_verdict") or "")[:500]
    mc = payload.get("monte_carlo") or {}
    composite = mc.get("composite_mean")
    cons = payload.get("consensus") or {}
    return {
        "scenario_index": scenario_index,
        "title": (scenario_title or "")[:200],
        "simulation_requirement_excerpt": (scenario_prompt or "")[:1200],
        "decision_verdict_excerpt": verdict,
        "composite_mean": composite,
        "consensus_polarization": cons.get("polarization_index"),
        "escalation_trend": cons.get("escalation_trend"),
        "estimates": est_snips,
    }


def normalize_branch_weights(
    scenario_indices: list[int],
    raw: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Clamp each weight to [_BRANCH_P_MIN, _BRANCH_P_MAX], renormalize to sum 1."""
    n = len(scenario_indices)
    if n == 0:
        return []
    out: list[dict[str, Any]] = []
    for pos, si in enumerate(scenario_indices):
        row = next((r for r in raw if int(r.get("scenario_index", -999)) == si), None)
        if row is None:
            row = next((r for r in raw if int(r.get("scenario_index", -999)) == pos), None)
        p = float(row.get("p_branch", 1.0 / n)) if row else 1.0 / n
        p = max(_BRANCH_P_MIN, min(_BRANCH_P_MAX, p))
        rationale = (row.get("rationale") or "")[:500] if row else ""
        out.append({"scenario_index": si, "p_branch": p, "rationale": rationale})
    s = sum(x["p_branch"] for x in out)
    if s <= 0:
        eq = 1.0 / n
        for x in out:
            x["p_branch"] = eq
    else:
        for x in out:
            x["p_branch"] = float(x["p_branch"] / s)
    return out


def _resolve_mapping_mid(
    scenario_index: int,
    estimate_index: int,
    payloads_by_index: dict[int, dict[str, Any]],
) -> tuple[Optional[float], float]:
    payload = payloads_by_index.get(scenario_index) or {}
    estimates = _payload_estimates(payload)
    if estimate_index < 0 or estimate_index >= len(estimates):
        return None, 400.0
    est = estimates[estimate_index]
    mid = _estimate_mid_percent(est)
    var = _estimate_variance_percent_sq(est)
    return mid, var


def compute_marginals_and_recalc(
    canonical_outcomes: list[dict[str, Any]],
    branch_weights: list[dict[str, Any]],
    payloads_by_index: dict[int, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Returns (outcomes_with_marginal, recalc_data rows per outcome_id).
    Marginal mean on 0-100 scale; variance on (percent)^2 for display math.
    """
    w_by_idx = {int(b["scenario_index"]): float(b["p_branch"]) for b in branch_weights}
    outcomes_out: list[dict[str, Any]] = []
    recalc_rows: list[dict[str, Any]] = []

    for co in canonical_outcomes:
        oid = co.get("outcome_id") or _slug(co.get("label", ""))
        label = co.get("label") or oid
        mapping = co.get("mapping") or []
        per_branch_means: list[dict[str, Any]] = []
        mus: list[float] = []
        vars_cond: list[float] = []
        weights_used: list[float] = []

        for m in mapping:
            try:
                si = int(m.get("scenario_index", -1))
                ei = int(m.get("estimate_index", 0))
            except (TypeError, ValueError):
                continue
            mid, var = _resolve_mapping_mid(si, ei, payloads_by_index)
            if mid is None:
                continue
            w = w_by_idx.get(si, 0.0)
            if w <= 0:
                continue
            mu = mid / 100.0
            per_branch_means.append(
                {
                    "scenario_index": si,
                    "estimate_index": ei,
                    "mean_0_1": round(mu, 6),
                    "variance_0_1_sq": round(var / 10000.0, 8),
                }
            )
            mus.append(mu)
            vars_cond.append(var / 10000.0)
            weights_used.append(w)

        if not mus:
            outcomes_out.append(
                {
                    "outcome_id": oid,
                    "label": label,
                    "marginal_mid_percent": None,
                    "marginal_ci_low_percent": None,
                    "marginal_ci_high_percent": None,
                    "mapping": mapping,
                }
            )
            recalc_rows.append({"outcome_id": oid, "per_branch": []})
            continue

        # Renormalize weights over branches that contributed
        sw = sum(weights_used)
        if sw <= 0:
            sw = 1.0
        wn = [wi / sw for wi in weights_used]
        mean_01 = sum(wn[i] * mus[i] for i in range(len(mus)))
        # Law of total variance on 0-1 scale: E[V|B] + Var(E|B)
        e_var = sum(wn[i] * vars_cond[i] for i in range(len(mus)))
        e_mu = sum(wn[i] * mus[i] for i in range(len(mus)))
        var_mu_branches = sum(wn[i] * (mus[i] - e_mu) ** 2 for i in range(len(mus)))
        var_01 = e_var + var_mu_branches
        std_01 = math.sqrt(max(var_01, 0.0))
        mid_pct = mean_01 * 100.0
        lo_pct = max(0.0, (mean_01 - 1.96 * std_01) * 100.0)
        hi_pct = min(100.0, (mean_01 + 1.96 * std_01) * 100.0)

        outcomes_out.append(
            {
                "outcome_id": oid,
                "label": label,
                "marginal_mid_percent": round(mid_pct, 2),
                "marginal_ci_low_percent": round(lo_pct, 2),
                "marginal_ci_high_percent": round(hi_pct, 2),
                "mapping": mapping,
            }
        )
        recalc_rows.append({"outcome_id": oid, "per_branch": per_branch_means})

    return outcomes_out, recalc_rows


def recompute_marginals_from_weights(
    synthesis: dict[str, Any],
    new_branch_weights: list[dict[str, Any]],
    payloads_by_index: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    """Deep-ish update: replace branch_weights and recompute outcome marginals + recalc_data."""
    co = synthesis.get("canonical_outcomes") or []
    scenario_indices = sorted(payloads_by_index.keys())
    normalized = normalize_branch_weights(scenario_indices, new_branch_weights)
    prev_rat = {
        int(b["scenario_index"]): (b.get("rationale") or "")[:500]
        for b in (synthesis.get("branch_weights") or [])
        if b.get("scenario_index") is not None
    }
    for b in normalized:
        if not b.get("rationale") and prev_rat.get(int(b["scenario_index"])):
            b["rationale"] = prev_rat[int(b["scenario_index"])]
    out_m, recalc = compute_marginals_and_recalc(co, normalized, payloads_by_index)
    updated = dict(synthesis)
    updated["branch_weights"] = normalized
    updated["outcomes"] = out_m
    updated["recalc_data"] = recalc
    updated["llm_assigned_weights"] = False
    return updated


STRUCTURAL_SYSTEM = """You are synthesizing multiple scenario forecasts into one executive bundle view.
Return ONLY valid JSON (no markdown fences) matching this schema:
{
  "branch_weights": [ {"scenario_index": int, "p_branch": float 0-1, "rationale": string} ],
  "canonical_outcomes": [
    {
      "outcome_id": string (short snake_case),
      "label": string (human readable),
      "mapping": [ {"scenario_index": int, "estimate_index": int} ]
    }
  ],
  "robust_conclusions": [ string ],
  "contingent_conclusions": [ string ],
  "early_warnings": [ {"indicator": string, "signal_meaning": string, "source": string} ],
  "decision_matrix": [ {"scenario_index": int, "verdict": string, "confidence": string, "key_drivers_summary": string} ],
  "narrative_md": string (markdown executive summary, 3-8 short paragraphs)
}
Rules:
- branch_weights: one entry per scenario_index provided; values should reflect likelihood each scenario represents the true branch; they will be clamped to [0.05,0.85] and renormalized.
- canonical_outcomes: 3-8 distinct outcomes across scenarios; merge synonyms; mapping lists which scenario's probability estimate (by estimate_index from that scenario's estimates list) corresponds to this outcome.
- If a scenario has no good estimate for an outcome, omit that scenario_index for that outcome.
- narrative_md: actionable exec summary referencing branch uncertainty and robust vs contingent findings.
"""


def build_bundle_synthesis(
    bundle: dict[str, Any],
    payloads_by_index: dict[int, dict[str, Any]],
    scenario_meta: list[dict[str, Any]],
    llm: Optional[LLMClient] = None,
) -> Optional[dict[str, Any]]:
    """
    bundle: row dict with title, description, suggested_scenarios, completed_scenarios
    payloads_by_index: scenario_index -> full report payload v1
    scenario_meta: list of {scenario_index, title, prompt} for indices present
    """
    if not Config.ENABLE_BUNDLE_SYNTHESIS:
        return None
    if len(payloads_by_index) < 2:
        return None

    client = llm or LLMClient()
    compact = []
    for meta in sorted(scenario_meta, key=lambda x: x["scenario_index"]):
        si = meta["scenario_index"]
        pl = payloads_by_index.get(si)
        if not pl:
            continue
        compact.append(
            _scenario_compact_payload(
                si,
                meta.get("title") or "",
                meta.get("prompt") or "",
                pl,
            )
        )
    user_msg = json.dumps(
        {
            "bundle_title": bundle.get("title"),
            "bundle_description": (bundle.get("description") or "")[:2000],
            "scenarios": compact,
        },
        ensure_ascii=False,
    )

    try:
        data = client.chat_json(
            messages=[
                {"role": "system", "content": STRUCTURAL_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.25,
            max_tokens=4096,
        )
    except Exception as e:
        logger.exception("bundle synthesis LLM failed: %s", e)
        return None

    if not isinstance(data, dict):
        return None

    scenario_indices = sorted(c["scenario_index"] for c in compact)
    raw_weights = data.get("branch_weights")
    if raw_weights is None:
        raw_weights = []
    if not isinstance(raw_weights, list) or not all(isinstance(x, dict) for x in raw_weights):
        logger.warning(
            "bundle synthesis: branch_weights must be a list of dicts; rejecting malformed LLM output",
        )
        return None
    normalized = normalize_branch_weights(list(scenario_indices), raw_weights)

    canonical = data.get("canonical_outcomes")
    if canonical is None:
        canonical = []
    if not isinstance(canonical, list) or not all(isinstance(x, dict) for x in canonical):
        logger.warning(
            "bundle synthesis: canonical_outcomes must be a list of dicts; rejecting malformed LLM output",
        )
        return None
    if not canonical:
        return None

    outcomes, recalc = compute_marginals_and_recalc(canonical, normalized, payloads_by_index)

    synthesis: dict[str, Any] = {
        "version": 1,
        "branch_weights": normalized,
        "canonical_outcomes": canonical,
        "outcomes": outcomes,
        "recalc_data": recalc,
        "robust_conclusions": data.get("robust_conclusions") or [],
        "contingent_conclusions": data.get("contingent_conclusions") or [],
        "early_warnings": data.get("early_warnings") or [],
        "decision_matrix": data.get("decision_matrix") or [],
        "narrative_md": (data.get("narrative_md") or "").strip(),
        "llm_assigned_weights": True,
        "source_scenario_indices": list(scenario_indices),
    }
    return synthesis
