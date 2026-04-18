"""
Quantitative analysis service for Glas Intelligence prediction reports.

Computes statistics, stance distributions, consensus metrics, escalation trends,
probability estimates, and risk matrices from simulation data. Designed to be
called by the Report Agent as tools alongside the existing qualitative retrieval tools.
"""

import os
import json
import csv
import math
from typing import Any
from dataclasses import dataclass, field
from enum import Enum

from ..config import Config
from ..utils.logger import get_logger
from ..utils.llm_client import LLMClient
from .calibration_guardrails import apply_estimate_guardrails

logger = get_logger("glas.quantitative_analysis")


def _safe_int(val, lo: int, hi: int, default: int) -> int:
    try:
        return min(hi, max(lo, int(val)))
    except (ValueError, TypeError):
        return default


def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


# ═══════════════════════════════════════════════════════════════
# Enums and Types
# ═══════════════════════════════════════════════════════════════


class StancePosition(str, Enum):
    SUPPORTIVE = "supportive"
    OPPOSING = "opposing"
    NEUTRAL = "neutral"
    AMBIVALENT = "ambivalent"


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    SPECULATIVE = "speculative"


class RiskSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"


# ═══════════════════════════════════════════════════════════════
# Result Dataclasses
# ═══════════════════════════════════════════════════════════════


@dataclass
class SimulationMetrics:
    """Aggregated simulation activity statistics."""

    total_actions: int = 0
    twitter_actions: int = 0
    reddit_actions: int = 0
    total_agents: int = 0
    total_rounds: int = 0

    action_type_distribution: dict[str, int] = field(default_factory=dict)
    engagement_rate: float = 0.0
    content_creation_rate: float = 0.0
    platform_ratio: dict[str, float] = field(default_factory=dict)

    most_active_agents: list[dict[str, Any]] = field(default_factory=list)
    agent_type_activity: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_actions": self.total_actions,
            "twitter_actions": self.twitter_actions,
            "reddit_actions": self.reddit_actions,
            "total_agents": self.total_agents,
            "total_rounds": self.total_rounds,
            "action_type_distribution": self.action_type_distribution,
            "engagement_rate": self.engagement_rate,
            "content_creation_rate": self.content_creation_rate,
            "platform_ratio": self.platform_ratio,
            "most_active_agents": self.most_active_agents,
            "agent_type_activity": self.agent_type_activity,
        }

    def to_text(self) -> str:
        lines = [
            "=== Simulation Activity Metrics ===",
            f"Total actions: {self.total_actions}",
            f"  Twitter: {self.twitter_actions} ({self.platform_ratio.get('twitter', 0):.1f}%)",
            f"  Reddit:  {self.reddit_actions} ({self.platform_ratio.get('reddit', 0):.1f}%)",
            f"Active agents: {self.total_agents}",
            f"Simulation rounds: {self.total_rounds}",
            f"Engagement rate: {self.engagement_rate:.1f}% (interactive actions / total)",
            f"Content creation rate: {self.content_creation_rate:.2f} posts per agent per round",
            "",
            "Action Type Breakdown:",
        ]
        for action_type, count in sorted(self.action_type_distribution.items(), key=lambda x: -x[1]):
            pct = (count / max(self.total_actions, 1)) * 100
            lines.append(f"  {action_type}: {count} ({pct:.1f}%)")

        if self.most_active_agents:
            lines.append("")
            lines.append("Most Active Agents (top 5):")
            for agent in self.most_active_agents[:5]:
                lines.append(
                    f"  {agent['agent_name']}: {agent['total_actions']} actions "
                    f"(Twitter: {agent.get('twitter_actions', 0)}, Reddit: {agent.get('reddit_actions', 0)})"
                )

        if self.agent_type_activity:
            lines.append("")
            lines.append("Activity by Entity Type:")
            for etype, data in sorted(self.agent_type_activity.items(), key=lambda x: -x[1].get("total_actions", 0)):
                lines.append(
                    f"  {etype}: {data['agent_count']} agents, "
                    f"{data['total_actions']} actions, "
                    f"{data['avg_actions_per_agent']:.1f} avg per agent"
                )

        return "\n".join(lines)


@dataclass
class AgentStance:
    """Individual agent's classified stance."""

    agent_name: str = ""
    agent_type: str = ""
    country: str = ""
    position: str = "neutral"
    intensity: int = 3
    key_concern: str = ""
    confidence: str = "moderate"

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "country": self.country,
            "position": self.position,
            "intensity": self.intensity,
            "key_concern": self.key_concern,
            "confidence": self.confidence,
        }


@dataclass
class StanceAnalysis:
    """Aggregated stakeholder position analysis."""

    topic: str = ""
    agents_analyzed: int = 0
    stances: list[AgentStance] = field(default_factory=list)
    position_distribution: dict[str, float] = field(default_factory=dict)
    position_counts: dict[str, int] = field(default_factory=dict)
    by_entity_type: dict[str, dict[str, float]] = field(default_factory=dict)
    by_country: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    average_intensity: float = 3.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "agents_analyzed": self.agents_analyzed,
            "stances": [s.to_dict() for s in self.stances],
            "position_distribution": self.position_distribution,
            "position_counts": self.position_counts,
            "by_entity_type": self.by_entity_type,
            "by_country": self.by_country,
            "average_intensity": self.average_intensity,
        }

    def to_text(self) -> str:
        lines = [
            "=== Stakeholder Position Analysis ===",
            f"Topic: {self.topic}",
            f"Agents analyzed: {self.agents_analyzed}",
            "",
            "Position Distribution:",
        ]
        for position in ["opposing", "supportive", "neutral", "ambivalent"]:
            count = self.position_counts.get(position, 0)
            pct = self.position_distribution.get(position, 0)
            if count > 0:
                lines.append(f"  {position.capitalize()}: {pct:.1f}% ({count} agents)")

        lines.append(f"\nAverage Intensity: {self.average_intensity:.1f}/5")

        if self.by_entity_type:
            lines.append("\nBy Entity Type:")
            for etype, dist in self.by_entity_type.items():
                parts = [f"{pos}: {pct:.0f}%" for pos, pct in dist.items() if pct > 0]
                lines.append(f"  {etype}: {', '.join(parts)}")

        if self.by_country:
            lines.append("\nBy Country/Entity:")
            for country, entries in self.by_country.items():
                positions = [e.get("position", "neutral") for e in entries]
                majority = max(set(positions), key=positions.count)
                avg_intensity = sum(e.get("intensity", 3) for e in entries) / len(entries)
                lines.append(
                    f"  {country} ({len(entries)} agents): {majority.capitalize()} "
                    f"(avg intensity {avg_intensity:.1f}/5)"
                )

        return "\n".join(lines)


@dataclass
class ConsensusMetrics:
    """Consensus and polarization measurements."""

    agreement_ratio: float = 0.0
    polarization_index: float = 0.0
    majority_position: str = ""
    majority_percentage: float = 0.0
    faction_count: int = 0
    cross_group_alignment: dict[str, str] = field(default_factory=dict)
    key_fault_lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agreement_ratio": self.agreement_ratio,
            "polarization_index": self.polarization_index,
            "majority_position": self.majority_position,
            "majority_percentage": self.majority_percentage,
            "faction_count": self.faction_count,
            "cross_group_alignment": self.cross_group_alignment,
            "key_fault_lines": self.key_fault_lines,
        }

    def to_text(self) -> str:
        pol_label = "Low"
        if self.polarization_index > 0.7:
            pol_label = "High"
        elif self.polarization_index > 0.4:
            pol_label = "Moderate"

        lines = [
            "=== Consensus & Polarization Metrics ===",
            f"Majority position: {self.majority_position.capitalize()} ({self.majority_percentage:.1f}%)",
            f"Agreement ratio: {self.agreement_ratio:.1f}%",
            f"Polarization index: {self.polarization_index:.2f} ({pol_label})",
            f"Distinct factions: {self.faction_count}",
        ]

        if self.cross_group_alignment:
            lines.append("\nCross-Group Alignment:")
            for group, position in self.cross_group_alignment.items():
                lines.append(f"  {group}: {position}")

        if self.key_fault_lines:
            lines.append("\nKey Fault Lines:")
            for fault in self.key_fault_lines:
                lines.append(f"  - {fault}")

        return "\n".join(lines)


@dataclass
class EscalationAnalysis:
    """Temporal escalation trend analysis."""

    total_rounds: int = 0
    intensity_curve: list[dict[str, Any]] = field(default_factory=list)
    escalation_detected: bool = False
    peak_round: int = 0
    peak_intensity: float = 0.0
    turning_points: list[dict[str, Any]] = field(default_factory=list)
    aggression_ratio_trend: list[float] = field(default_factory=list)
    overall_trend: str = "stable"

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_rounds": self.total_rounds,
            "intensity_curve": self.intensity_curve,
            "escalation_detected": self.escalation_detected,
            "peak_round": self.peak_round,
            "peak_intensity": self.peak_intensity,
            "turning_points": self.turning_points,
            "aggression_ratio_trend": self.aggression_ratio_trend,
            "overall_trend": self.overall_trend,
        }

    def to_text(self) -> str:
        lines = [
            "=== Escalation Analysis ===",
            f"Simulation duration: {self.total_rounds} rounds",
            f"Overall trend: {self.overall_trend.upper()}",
            f"Escalation detected: {'Yes' if self.escalation_detected else 'No'}",
            f"Peak activity: Round {self.peak_round} (intensity: {self.peak_intensity:.1f})",
        ]

        if self.turning_points:
            lines.append("\nTurning Points:")
            for tp in self.turning_points:
                lines.append(f"  Round {tp['round']}: {tp['description']} (change: {tp.get('change_pct', 0):+.0f}%)")

        if self.intensity_curve:
            lines.append("\nActivity Timeline:")
            for point in self.intensity_curve:
                bar_len = int(point.get("normalized_intensity", 0) * 20)
                bar = "█" * bar_len + "░" * (20 - bar_len)
                lines.append(f"  R{point['round']:>2}: {bar} {point['total_actions']} actions")

        return "\n".join(lines)


@dataclass
class ProbabilityEstimate:
    """Single outcome probability estimate."""

    outcome: str = ""
    probability_low: float = 0.0
    probability_mid: float = 0.0
    probability_high: float = 0.0
    confidence: str = "moderate"
    supporting_evidence: list[str] = field(default_factory=list)
    key_drivers: list[str] = field(default_factory=list)
    # Pre-guardrail LLM triplets (for A/B vs probability_* after calibration_guardrails).
    raw_low: float = 0.0
    raw_mid: float = 0.0
    raw_high: float = 0.0
    # None = guardrails not applied (disabled or error); list = applied (may be empty).
    guardrail_corrections: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "probability_range": {
                "low": self.probability_low,
                "mid": self.probability_mid,
                "high": self.probability_high,
            },
            "raw_probability_range": {
                "low": self.raw_low,
                "mid": self.raw_mid,
                "high": self.raw_high,
            },
            "guardrail_corrections": self.guardrail_corrections,
            "confidence": self.confidence,
            "supporting_evidence": self.supporting_evidence,
            "key_drivers": self.key_drivers,
        }


@dataclass
class ProbabilityAssessment:
    """Collection of probability estimates for key outcomes."""

    scenario: str = ""
    estimates: list[ProbabilityEstimate] = field(default_factory=list)
    methodology_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "estimates": [e.to_dict() for e in self.estimates],
            "methodology_note": self.methodology_note,
        }

    def to_text(self) -> str:
        lines = [
            "=== Probability Assessment ===",
            f"Scenario: {self.scenario}",
            "",
            "Key Outcome Probabilities:",
        ]

        for est in self.estimates:
            conf_marker = {"high": "★★★", "moderate": "★★☆", "low": "★☆☆", "speculative": "☆☆☆"}.get(
                est.confidence, "★★☆"
            )
            lines.append(f"\n  {est.outcome}")
            lines.append(
                f"    Probability: {est.probability_low:.0f}% - {est.probability_high:.0f}% "
                f"(midpoint: {est.probability_mid:.0f}%)"
            )
            lines.append(f"    Confidence: {est.confidence} {conf_marker}")
            if est.supporting_evidence:
                lines.append(f"    Evidence: {'; '.join(est.supporting_evidence[:3])}")
            if est.key_drivers:
                lines.append(f"    Key drivers: {'; '.join(est.key_drivers[:3])}")

        if self.methodology_note:
            lines.append(f"\nMethodology: {self.methodology_note}")

        return "\n".join(lines)


@dataclass
class RiskItem:
    """Single risk on the matrix."""

    risk: str = ""
    likelihood: int = 3
    impact: int = 3
    severity: str = "moderate"
    mitigation_indicators: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk": self.risk,
            "likelihood": self.likelihood,
            "impact": self.impact,
            "severity": self.severity,
            "mitigation_indicators": self.mitigation_indicators,
        }


@dataclass
class RiskMatrix:
    """Impact x Likelihood risk assessment."""

    risks: list[RiskItem] = field(default_factory=list)
    top_risks: list[RiskItem] = field(default_factory=list)
    risk_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "risks": [r.to_dict() for r in self.risks],
            "top_risks": [r.to_dict() for r in self.top_risks],
            "risk_summary": self.risk_summary,
        }

    def to_text(self) -> str:
        lines = [
            "=== Risk Matrix (Impact × Likelihood) ===",
            "",
            "| Risk | Likelihood (1-5) | Impact (1-5) | Severity |",
            "|------|------------------|--------------|----------|",
        ]

        for r in self.risks:
            sev_label = r.severity.upper()
            lines.append(f"| {r.risk} | {r.likelihood} | {r.impact} | {sev_label} |")

        if self.top_risks:
            lines.append("\nTop Risks:")
            for i, r in enumerate(self.top_risks, 1):
                lines.append(f"  {i}. {r.risk} ({r.severity.upper()})")
                if r.mitigation_indicators:
                    lines.append(f"     Mitigation indicators: {'; '.join(r.mitigation_indicators)}")

        if self.risk_summary:
            lines.append(f"\nSummary: {self.risk_summary}")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# Combined Result Dataclasses (what the report tools return)
# ═══════════════════════════════════════════════════════════════


@dataclass
class MetricsToolResult:
    """Combined result for the analyze_metrics tool."""

    metrics: SimulationMetrics | None = None
    escalation: EscalationAnalysis | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {}
        if self.metrics:
            result["simulation_metrics"] = self.metrics.to_dict()
        if self.escalation:
            result["escalation_analysis"] = self.escalation.to_dict()
        return result

    def to_text(self) -> str:
        parts = []
        if self.metrics:
            parts.append(self.metrics.to_text())
        if self.escalation:
            parts.append(self.escalation.to_text())
        return "\n\n".join(parts)


@dataclass
class PositionsToolResult:
    """Combined result for the assess_positions tool."""

    stance: StanceAnalysis | None = None
    consensus: ConsensusMetrics | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {}
        if self.stance:
            result["stance_analysis"] = self.stance.to_dict()
        if self.consensus:
            result["consensus_metrics"] = self.consensus.to_dict()
        return result

    def to_text(self) -> str:
        parts = []
        if self.stance:
            parts.append(self.stance.to_text())
        if self.consensus:
            parts.append(self.consensus.to_text())
        return "\n\n".join(parts)


@dataclass
class RisksToolResult:
    """Combined result for the estimate_risks tool."""

    probabilities: ProbabilityAssessment | None = None
    risk_matrix: RiskMatrix | None = None
    monte_carlo: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {}
        if self.probabilities:
            result["probability_assessment"] = self.probabilities.to_dict()
        if self.risk_matrix:
            result["risk_matrix"] = self.risk_matrix.to_dict()
        if self.monte_carlo:
            result["monte_carlo"] = self.monte_carlo
        return result

    def to_text(self) -> str:
        parts = []
        if self.probabilities:
            parts.append(self.probabilities.to_text())
        if self.risk_matrix:
            parts.append(self.risk_matrix.to_text())
        if self.monte_carlo:
            mc = self.monte_carlo
            per_outcome = mc.get("per_outcome", [])
            composite = mc.get("composite")
            if per_outcome or composite:
                lines = ["=== Monte Carlo Analysis ==="]
                for item in per_outcome:
                    if item is None:
                        continue
                    mc_data = item.get("monte_carlo", {})
                    cis = mc_data.get("confidence_intervals", {})
                    ci95 = cis.get("95%", [0, 0])
                    lines.append(
                        f"  {item.get('outcome', '')}: "
                        f"mean={mc_data.get('mean', 0):.1f}%, "
                        f"95% CI=[{ci95[0]:.1f}%, {ci95[1]:.1f}%]"
                    )
                if composite:
                    c_cis = composite.get("confidence_intervals", {})
                    c_ci95 = c_cis.get("95%", [0, 0])
                    lines.append(
                        f"\n  Composite: mean={composite.get('mean', 0):.1f}%, "
                        f"95% CI=[{c_ci95[0]:.1f}%, {c_ci95[1]:.1f}%]"
                    )
                    conv = composite.get("convergence", {})
                    lines.append(
                        f"  Converged: {conv.get('converged', False)} "
                        f"(relative error: {conv.get('relative_error', 0):.4f})"
                    )
                parts.append("\n".join(lines))
        return "\n\n".join(parts)


# ═══════════════════════════════════════════════════════════════
# Service
# ═══════════════════════════════════════════════════════════════

INTERACTIVE_ACTIONS = {
    "LIKE_POST",
    "DISLIKE_POST",
    "REPOST",
    "QUOTE_POST",
    "CREATE_COMMENT",
    "LIKE_COMMENT",
    "DISLIKE_COMMENT",
    "FOLLOW",
}
CONTENT_CREATION_ACTIONS = {"CREATE_POST", "QUOTE_POST"}
AGGRESSIVE_ACTIONS = {"DISLIKE_POST", "DISLIKE_COMMENT", "MUTE"}
POSITIVE_ACTIONS = {"LIKE_POST", "LIKE_COMMENT", "REPOST", "FOLLOW"}


@dataclass
class StakeholderImpactRow:
    entity_type: str = ""
    stance_majority: str = ""
    stance_label: str = ""
    avg_intensity: float = 0.0
    activity_index: float = 0.0
    escalation_exposure: float = 0.0
    voice_share_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "stance_majority": self.stance_majority,
            "stance_label": self.stance_label,
            "avg_intensity": self.avg_intensity,
            "activity_index": self.activity_index,
            "escalation_exposure": self.escalation_exposure,
            "voice_share_pct": self.voice_share_pct,
        }


@dataclass
class StakeholderImpactMatrix:
    rows: list[StakeholderImpactRow] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"rows": [r.to_dict() for r in self.rows]}

    def to_text(self) -> str:
        lines = [
            "=== Stakeholder impact matrix (by entity type) ===",
            "| Type | Stance mix | Majority | Avg intensity | Activity index* | Escalation exposure** | Voice share |",
            "|------|------------|----------|---------------|-----------------|----------------------|-------------|",
        ]
        for r in self.rows:
            lines.append(
                f"| {r.entity_type} | {r.stance_label} | {r.stance_majority} | {r.avg_intensity} | "
                f"{r.activity_index} | {r.escalation_exposure}% | {r.voice_share_pct}% |"
            )
        lines.append("")
        lines.append("*Activity index = avg actions per agent in type / global avg actions per agent.")
        lines.append("**Escalation exposure = share of aggressive-type actions within that type's volume.")
        return "\n".join(lines)


@dataclass
class KeyDriver:
    """A single key driver influencing the decision verdict."""

    name: str = ""
    direction: str = ""  # e.g. "positive", "negative", "neutral"
    magnitude: str = ""  # e.g. "strong", "moderate", "weak"

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "direction": self.direction, "magnitude": self.magnitude}


@dataclass
class SensitivityRow:
    """What-if sensitivity: how changing a variable shifts the verdict."""

    variable: str = ""
    base_value: str = ""
    swing_pct: str = ""
    impact_on_verdict: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "variable": self.variable,
            "base_value": self.base_value,
            "swing_pct": self.swing_pct,
            "impact_on_verdict": self.impact_on_verdict,
        }


@dataclass
class RecommendedAction:
    """A prioritized action from the decision framework."""

    action: str = ""
    priority: str = ""  # "critical", "high", "medium", "low"
    rationale: str = ""
    timeline: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "priority": self.priority,
            "rationale": self.rationale,
            "timeline": self.timeline,
        }


@dataclass
class MonitoringIndicator:
    """A metric or signal to watch for changes."""

    indicator: str = ""
    current_state: str = ""
    threshold: str = ""
    action_if_triggered: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "indicator": self.indicator,
            "current_state": self.current_state,
            "threshold": self.threshold,
            "action_if_triggered": self.action_if_triggered,
        }


@dataclass
class DecisionFramework:
    """Structured decision recommendation from simulation analysis."""

    verdict: str = ""
    confidence: str = ""
    confidence_rationale: str = ""
    reasoning: str = ""
    key_drivers: list[KeyDriver] = field(default_factory=list)
    sensitivity: list[SensitivityRow] = field(default_factory=list)
    flip_conditions: list[str] = field(default_factory=list)
    financial_summary: dict[str, Any] | None = None
    causal_chain: list[dict[str, str]] = field(default_factory=list)
    recommended_actions: list[RecommendedAction] = field(default_factory=list)
    monitoring_indicators: list[MonitoringIndicator] = field(default_factory=list)
    time_sensitivity: str = ""
    decision_criteria: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "verdict": self.verdict,
            "confidence": self.confidence,
            "confidence_rationale": self.confidence_rationale,
            "reasoning": self.reasoning,
            "key_drivers": [d.to_dict() for d in self.key_drivers],
            "sensitivity": [s.to_dict() for s in self.sensitivity],
            "flip_conditions": self.flip_conditions,
            "causal_chain": self.causal_chain,
            "recommended_actions": [a.to_dict() for a in self.recommended_actions],
            "monitoring_indicators": [m.to_dict() for m in self.monitoring_indicators],
            "time_sensitivity": self.time_sensitivity,
            "decision_criteria": self.decision_criteria,
        }
        if self.financial_summary is not None:
            result["financial_summary"] = self.financial_summary
        return result


class QuantitativeAnalysisService:
    """Computes quantitative metrics from Glas Intelligence simulation data."""

    def __init__(self, llm_client: LLMClient | None = None):
        self._llm = llm_client

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = LLMClient()
        return self._llm

    # ───────────────────────────────────────────────────────────
    # 1. Simulation Metrics (pure aggregation, no LLM)
    # ───────────────────────────────────────────────────────────

    def simulation_metrics(self, simulation_id: str) -> SimulationMetrics:
        from .simulation_runner import SimulationRunner

        agent_stats = SimulationRunner.get_agent_stats(simulation_id)
        timeline = SimulationRunner.get_timeline(simulation_id)
        profiles = self._load_agent_profiles(simulation_id)

        result = SimulationMetrics()
        result.total_agents = len(agent_stats)
        result.total_rounds = len(timeline)

        action_types: dict[str, int] = {}
        for agent in agent_stats:
            result.total_actions += agent["total_actions"]
            result.twitter_actions += agent.get("twitter_actions", 0)
            result.reddit_actions += agent.get("reddit_actions", 0)
            for atype, count in agent.get("action_types", {}).items():
                action_types[atype] = action_types.get(atype, 0) + count

        result.action_type_distribution = action_types

        if result.total_actions > 0:
            interactive = sum(action_types.get(a, 0) for a in INTERACTIVE_ACTIONS)
            result.engagement_rate = (interactive / result.total_actions) * 100

            total = max(result.total_actions, 1)
            result.platform_ratio = {
                "twitter": (result.twitter_actions / total) * 100,
                "reddit": (result.reddit_actions / total) * 100,
            }

        if result.total_agents > 0 and result.total_rounds > 0:
            creation_count = sum(action_types.get(a, 0) for a in CONTENT_CREATION_ACTIONS)
            result.content_creation_rate = creation_count / (result.total_agents * result.total_rounds)

        result.most_active_agents = agent_stats[:5]

        name_to_type = self._build_agent_type_map(profiles)
        type_stats: dict[str, dict[str, Any]] = {}
        for agent in agent_stats:
            atype = name_to_type.get(agent["agent_name"], "Unknown")
            if atype not in type_stats:
                type_stats[atype] = {"agent_count": 0, "total_actions": 0}
            type_stats[atype]["agent_count"] += 1
            type_stats[atype]["total_actions"] += agent["total_actions"]

        for atype, data in type_stats.items():
            data["avg_actions_per_agent"] = data["total_actions"] / max(data["agent_count"], 1)
        result.agent_type_activity = type_stats

        return result

    # ───────────────────────────────────────────────────────────
    # 2. Stance Analysis (LLM-assisted classification)
    # ───────────────────────────────────────────────────────────

    def stance_analysis(
        self,
        simulation_id: str,
        topic: str,
        graph_id: str,
        zep_tools=None,
    ) -> StanceAnalysis:
        profiles = self._load_agent_profiles(simulation_id)
        if not profiles:
            return StanceAnalysis(topic=topic, agents_analyzed=0)

        facts_text = ""
        if zep_tools and graph_id:
            try:
                search_result = zep_tools.quick_search(graph_id=graph_id, query=topic, limit=30)
                facts_text = "\n".join(search_result.facts[:30])
            except Exception as e:
                logger.warning(f"Failed to retrieve graph facts for stance analysis: {e}")

        agent_summaries = []
        for i, profile in enumerate(profiles):
            agent_summaries.append(
                {
                    "index": i,
                    "name": profile.get("realname", profile.get("username", f"Agent_{i}")),
                    "country": profile.get("country", "Unknown"),
                    "entity_type": profile.get("source_entity_type", profile.get("profession", "Unknown")),
                    "bio": profile.get("bio", "")[:200],
                    "persona": profile.get("persona", "")[:300],
                }
            )

        system_prompt = (
            "You are a quantitative analyst classifying stakeholder positions in a geopolitical simulation.\n\n"
            "For each agent, determine their stance on the given topic based on their persona and any "
            "available simulation facts.\n\n"
            "Return JSON:\n"
            "{\n"
            '  "stances": [\n'
            "    {\n"
            '      "agent_index": 0,\n'
            '      "position": "supportive|opposing|neutral|ambivalent",\n'
            '      "intensity": 1-5,\n'
            '      "key_concern": "one sentence",\n'
            '      "confidence": "high|moderate|low"\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Rules:\n"
            "- position MUST be one of: supportive, opposing, neutral, ambivalent\n"
            "- intensity is 1 (weak) to 5 (extreme)\n"
            "- confidence reflects how clearly the persona/facts indicate their stance\n"
            "- Classify ALL agents provided\n"
        )

        user_prompt = (
            f"Topic: {topic}\n\n"
            f"Simulation facts:\n{facts_text[:2000] if facts_text else 'No facts available.'}\n\n"
            f"Agents to classify:\n{json.dumps(agent_summaries, ensure_ascii=False, indent=1)}"
        )

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=4096,
            )
        except Exception as e:
            logger.error(f"LLM stance classification failed: {e}")
            return StanceAnalysis(topic=topic, agents_analyzed=0)

        result = StanceAnalysis(topic=topic, agents_analyzed=len(profiles))

        for item in response.get("stances", []):
            idx = item.get("agent_index", -1)
            if 0 <= idx < len(agent_summaries):
                agent = agent_summaries[idx]
                stance = AgentStance(
                    agent_name=agent["name"],
                    agent_type=agent["entity_type"],
                    country=agent["country"],
                    position=item.get("position", "neutral"),
                    intensity=_safe_int(item.get("intensity", 3), 1, 5, 3),
                    key_concern=item.get("key_concern", ""),
                    confidence=item.get("confidence", "moderate"),
                )
                result.stances.append(stance)

        self._compute_stance_aggregates(result)
        return result

    # ───────────────────────────────────────────────────────────
    # 3. Consensus Metrics (pure computation from StanceAnalysis)
    # ───────────────────────────────────────────────────────────

    def consensus_metrics(self, stance: StanceAnalysis) -> ConsensusMetrics:
        result = ConsensusMetrics()
        if not stance.stances:
            return result

        counts = stance.position_counts
        total = max(stance.agents_analyzed, 1)

        majority_pos = max(counts, key=counts.get) if counts else "neutral"
        majority_count = counts.get(majority_pos, 0)

        result.majority_position = majority_pos
        result.majority_percentage = (majority_count / total) * 100
        result.agreement_ratio = result.majority_percentage

        non_zero = {k: v for k, v in counts.items() if v > 0}
        result.faction_count = len(non_zero)

        if total > 0 and non_zero:
            proportions = [v / total for v in non_zero.values()]
            max_entropy = math.log(len(StancePosition))
            entropy = -sum(p * math.log(p) for p in proportions if p > 0)
            result.polarization_index = round(entropy / max_entropy, 2) if max_entropy > 0 else 0.0

        type_positions: dict[str, str] = {}
        for s in stance.stances:
            if s.agent_type not in type_positions:
                type_positions[s.agent_type] = s.position
        result.cross_group_alignment = type_positions

        type_stances: dict[str, list[str]] = {}
        for s in stance.stances:
            type_stances.setdefault(s.agent_type, []).append(s.position)

        fault_lines = []
        types = list(type_stances.keys())
        for i in range(len(types)):
            for j in range(i + 1, len(types)):
                t1, t2 = types[i], types[j]
                majority_t1 = max(set(type_stances[t1]), key=type_stances[t1].count)
                majority_t2 = max(set(type_stances[t2]), key=type_stances[t2].count)
                if majority_t1 != majority_t2 and majority_t1 != "neutral" and majority_t2 != "neutral":
                    fault_lines.append(f"{t1} ({majority_t1}) vs {t2} ({majority_t2})")
        result.key_fault_lines = fault_lines[:5]

        return result

    # ───────────────────────────────────────────────────────────
    # 4. Escalation Analysis (pure computation from timeline)
    # ───────────────────────────────────────────────────────────

    def escalation_analysis(self, simulation_id: str) -> EscalationAnalysis:
        from .simulation_runner import SimulationRunner

        timeline = SimulationRunner.get_timeline(simulation_id)
        result = EscalationAnalysis(total_rounds=len(timeline))

        if not timeline:
            return result

        max_actions = max(r["total_actions"] for r in timeline) if timeline else 1

        for r in timeline:
            total = r["total_actions"]
            normalized = total / max(max_actions, 1)
            aggressive = sum(r.get("action_types", {}).get(a, 0) for a in AGGRESSIVE_ACTIONS)
            positive = sum(r.get("action_types", {}).get(a, 0) for a in POSITIVE_ACTIONS)
            aggression_ratio = aggressive / max(aggressive + positive, 1)

            result.intensity_curve.append(
                {
                    "round": r["round_num"],
                    "total_actions": total,
                    "normalized_intensity": round(normalized, 3),
                    "active_agents": r.get("active_agents_count", 0),
                    "aggression_ratio": round(aggression_ratio, 3),
                }
            )
            result.aggression_ratio_trend.append(round(aggression_ratio, 3))

        peak_point = max(result.intensity_curve, key=lambda x: x["total_actions"])
        result.peak_round = peak_point["round"]
        result.peak_intensity = peak_point["normalized_intensity"]

        for i in range(1, len(result.intensity_curve)):
            prev = result.intensity_curve[i - 1]["total_actions"]
            curr = result.intensity_curve[i]["total_actions"]
            if prev > 0:
                change_pct = ((curr - prev) / prev) * 100
                if abs(change_pct) >= 50:
                    direction = "Surge" if change_pct > 0 else "Drop"
                    result.turning_points.append(
                        {
                            "round": result.intensity_curve[i]["round"],
                            "description": f"{direction} in activity ({prev} → {curr} actions)",
                            "change_pct": round(change_pct),
                        }
                    )

        if len(result.intensity_curve) >= 3:
            first_half = result.intensity_curve[: len(result.intensity_curve) // 2]
            second_half = result.intensity_curve[len(result.intensity_curve) // 2 :]
            avg_first = sum(p["total_actions"] for p in first_half) / max(len(first_half), 1)
            avg_second = sum(p["total_actions"] for p in second_half) / max(len(second_half), 1)

            if avg_second > avg_first * 1.3:
                result.overall_trend = "escalating"
                result.escalation_detected = True
            elif avg_second < avg_first * 0.7:
                result.overall_trend = "de-escalating"
            else:
                result.overall_trend = "stable"
        elif len(result.intensity_curve) > 0:
            result.overall_trend = "insufficient data"

        return result

    # ───────────────────────────────────────────────────────────
    # 5. Probability Assessment (LLM-assisted estimation)
    # ───────────────────────────────────────────────────────────

    def probability_assessment(
        self,
        scenario: str,
        stance: StanceAnalysis | None = None,
        consensus: ConsensusMetrics | None = None,
        escalation: EscalationAnalysis | None = None,
    ) -> ProbabilityAssessment:
        evidence_parts = [f"Scenario: {scenario}"]

        if stance:
            evidence_parts.append(f"Stakeholder stance distribution: {json.dumps(stance.position_distribution)}")
            evidence_parts.append(f"Average stance intensity: {stance.average_intensity}/5")

        if consensus:
            evidence_parts.append(f"Polarization index: {consensus.polarization_index}")
            evidence_parts.append(f"Agreement ratio: {consensus.agreement_ratio:.1f}%")
            evidence_parts.append(
                f"Majority position: {consensus.majority_position} ({consensus.majority_percentage:.1f}%)"
            )
            if consensus.key_fault_lines:
                evidence_parts.append(f"Key fault lines: {'; '.join(consensus.key_fault_lines)}")

        if escalation:
            evidence_parts.append(f"Escalation trend: {escalation.overall_trend}")
            evidence_parts.append(f"Peak round: {escalation.peak_round}/{escalation.total_rounds}")
            if escalation.turning_points:
                tp_desc = [f"Round {tp['round']}: {tp['description']}" for tp in escalation.turning_points]
                evidence_parts.append(f"Turning points: {'; '.join(tp_desc)}")

        evidence_text = "\n".join(evidence_parts)

        system_prompt = (
            "You are a probabilistic forecasting analyst for geopolitical simulation predictions.\n\n"
            "Given quantitative evidence from a simulation, identify 3-5 key outcomes and estimate "
            "their probabilities.\n\n"
            "Return JSON:\n"
            "{\n"
            '  "estimates": [\n'
            "    {\n"
            '      "outcome": "clear description of the outcome",\n'
            '      "probability_low": 10,\n'
            '      "probability_mid": 25,\n'
            '      "probability_high": 40,\n'
            '      "confidence": "high|moderate|low|speculative",\n'
            '      "supporting_evidence": ["evidence point 1", "evidence point 2"],\n'
            '      "key_drivers": ["driver that would increase probability", "driver that would decrease it"]\n'
            "    }\n"
            "  ],\n"
            '  "methodology_note": "Brief note on the basis for these estimates"\n'
            "}\n\n"
            "Rules:\n"
            "- probability_low, probability_mid, probability_high are percentages (0-100)\n"
            "- low < mid < high always\n"
            "- confidence reflects uncertainty: high = strong data support, speculative = minimal data\n"
            "- Ground estimates in the provided evidence, not general knowledge\n"
            "- Be honest about uncertainty; avoid false precision\n"
            "- Identify 3-5 distinct, non-overlapping outcomes\n"
        )

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": evidence_text},
                ],
                temperature=0.3,
                max_tokens=3000,
            )
        except Exception as e:
            logger.error(f"LLM probability assessment failed: {e}")
            return ProbabilityAssessment(scenario=scenario)

        result = ProbabilityAssessment(
            scenario=scenario,
            methodology_note=response.get("methodology_note", ""),
        )

        for item in response.get("estimates", []):
            raw_low = _safe_float(item.get("probability_low", 0))
            raw_mid = _safe_float(item.get("probability_mid", 0))
            raw_high = _safe_float(item.get("probability_high", 0))

            guardrail_corrections: list[str] | None = None
            if Config.ENABLE_CALIBRATION_GUARDRAILS:
                try:
                    guard = apply_estimate_guardrails(raw_low, raw_mid, raw_high)
                    guardrail_corrections = list(guard.corrections)
                    if guard.corrections:
                        logger.info(
                            "Guardrails applied to '%s': %s",
                            (item.get("outcome", "") or "")[:60],
                            "; ".join(guard.corrections),
                        )
                    final_low, final_mid, final_high = guard.low, guard.mid, guard.high
                except Exception as e:
                    logger.warning(
                        "Guardrails failed (using raw triplets): scenario=%r outcome=%r raw=(%s,%s,%s): %s",
                        (scenario or "")[:120],
                        (item.get("outcome") or "")[:80],
                        raw_low,
                        raw_mid,
                        raw_high,
                        e,
                    )
                    guardrail_corrections = None
                    final_low, final_mid, final_high = raw_low, raw_mid, raw_high
            else:
                final_low, final_mid, final_high = raw_low, raw_mid, raw_high

            est = ProbabilityEstimate(
                outcome=item.get("outcome", ""),
                probability_low=final_low,
                probability_mid=final_mid,
                probability_high=final_high,
                confidence=item.get("confidence", "moderate"),
                supporting_evidence=item.get("supporting_evidence", []),
                key_drivers=item.get("key_drivers", []),
                raw_low=raw_low,
                raw_mid=raw_mid,
                raw_high=raw_high,
                guardrail_corrections=guardrail_corrections,
            )
            result.estimates.append(est)

        return result

    # ───────────────────────────────────────────────────────────
    # 6. Risk Matrix (LLM-assisted, built from probability data)
    # ───────────────────────────────────────────────────────────

    def risk_matrix(
        self,
        scenario: str,
        probabilities: ProbabilityAssessment | None = None,
        escalation: EscalationAnalysis | None = None,
    ) -> RiskMatrix:
        context_parts = [f"Scenario: {scenario}"]

        if probabilities:
            for est in probabilities.estimates:
                context_parts.append(
                    f"Outcome: {est.outcome} "
                    f"(probability: {est.probability_low}-{est.probability_high}%, "
                    f"confidence: {est.confidence})"
                )

        if escalation:
            context_parts.append(f"Escalation trend: {escalation.overall_trend}")
            context_parts.append(f"Escalation detected: {escalation.escalation_detected}")

        system_prompt = (
            "You are a risk analyst assessing a geopolitical simulation.\n\n"
            "Given the scenario and outcome probabilities, construct a risk matrix.\n\n"
            "Return JSON:\n"
            "{\n"
            '  "risks": [\n'
            "    {\n"
            '      "risk": "description of the risk",\n'
            '      "likelihood": 1-5,\n'
            '      "impact": 1-5,\n'
            '      "mitigation_indicators": ["indicator 1", "indicator 2"]\n'
            "    }\n"
            "  ],\n"
            '  "risk_summary": "One sentence overall risk assessment"\n'
            "}\n\n"
            "Rules:\n"
            "- likelihood: 1=very unlikely, 2=unlikely, 3=possible, 4=likely, 5=very likely\n"
            "- impact: 1=negligible, 2=minor, 3=moderate, 4=major, 5=catastrophic\n"
            "- Identify 4-6 distinct risks\n"
            "- mitigation_indicators: what signals would reduce this risk\n"
            "- Ground assessments in provided data\n"
        )

        try:
            response = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "\n".join(context_parts)},
                ],
                temperature=0.3,
                max_tokens=2000,
            )
        except Exception as e:
            logger.error(f"LLM risk matrix failed: {e}")
            return RiskMatrix()

        result = RiskMatrix(risk_summary=response.get("risk_summary", ""))

        for item in response.get("risks", []):
            likelihood = min(5, max(1, int(item.get("likelihood", 3))))
            impact = min(5, max(1, int(item.get("impact", 3))))
            score = likelihood * impact
            if score >= 16:
                severity = RiskSeverity.CRITICAL.value
            elif score >= 10:
                severity = RiskSeverity.HIGH.value
            elif score >= 5:
                severity = RiskSeverity.MODERATE.value
            else:
                severity = RiskSeverity.LOW.value

            risk_item = RiskItem(
                risk=item.get("risk", ""),
                likelihood=likelihood,
                impact=impact,
                severity=severity,
                mitigation_indicators=item.get("mitigation_indicators", []),
            )
            result.risks.append(risk_item)

        result.risks.sort(key=lambda r: r.likelihood * r.impact, reverse=True)
        result.top_risks = result.risks[:3]

        return result

    # ───────────────────────────────────────────────────────────
    # Composite tool methods (called by report agent)
    # ───────────────────────────────────────────────────────────

    def analyze_metrics(self, simulation_id: str) -> MetricsToolResult:
        """Tool: analyze_metrics — returns activity stats + escalation analysis."""
        metrics = self.simulation_metrics(simulation_id)
        escalation = self.escalation_analysis(simulation_id)
        return MetricsToolResult(metrics=metrics, escalation=escalation)

    def assess_positions(
        self,
        simulation_id: str,
        topic: str,
        graph_id: str,
        zep_tools=None,
    ) -> PositionsToolResult:
        """Tool: assess_positions — returns stance distribution + consensus metrics."""
        stance = self.stance_analysis(simulation_id, topic, graph_id, zep_tools)
        consensus = self.consensus_metrics(stance)
        return PositionsToolResult(stance=stance, consensus=consensus)

    def estimate_risks(
        self,
        simulation_id: str,
        scenario: str,
        graph_id: str,
        zep_tools=None,
        cached_stance: StanceAnalysis | None = None,
        cached_consensus: ConsensusMetrics | None = None,
    ) -> RisksToolResult:
        """Tool: estimate_risks — returns probability estimates + risk matrix + Monte Carlo."""
        if cached_stance is not None and cached_consensus is not None:
            stance = cached_stance
            consensus = cached_consensus
        else:
            stance = self.stance_analysis(simulation_id, scenario, graph_id, zep_tools)
            consensus = self.consensus_metrics(stance)
        escalation = self.escalation_analysis(simulation_id)
        probs = self.probability_assessment(scenario, stance, consensus, escalation)
        risk = self.risk_matrix(scenario, probs, escalation)

        mc_result = None
        if probs and probs.estimates:
            try:
                from .monte_carlo_engine import (
                    run_monte_carlo_on_estimates,
                    run_composite_monte_carlo,
                )

                est_dicts = [e.to_dict() for e in probs.estimates]
                per_outcome = run_monte_carlo_on_estimates(est_dicts)
                composite = run_composite_monte_carlo(est_dicts)
                mc_result = {
                    "per_outcome": per_outcome,
                    "composite": composite,
                }
            except Exception as e:
                logger.warning(f"Monte Carlo analysis failed: {e}")

        return RisksToolResult(probabilities=probs, risk_matrix=risk, monte_carlo=mc_result)

    def stakeholder_impact_matrix(
        self,
        simulation_id: str,
        graph_id: str,
        topic: str,
        zep_tools=None,
        cached_stance: StanceAnalysis | None = None,
    ) -> StakeholderImpactMatrix:
        """
        Per-entity-type impact table: stance mix, intensity, activity vs mean, aggression share.
        """
        stance = cached_stance or self.stance_analysis(simulation_id, topic, graph_id, zep_tools)
        from .simulation_runner import SimulationRunner

        agent_stats = SimulationRunner.get_agent_stats(simulation_id)
        profiles = self._load_agent_profiles(simulation_id)
        name_to_type = self._build_agent_type_map(profiles)

        global_mean = 0.0
        if agent_stats:
            global_mean = sum(a["total_actions"] for a in agent_stats) / max(len(agent_stats), 1)

        type_agg: dict[str, dict[str, float]] = {}
        for a in agent_stats:
            atype = name_to_type.get(a["agent_name"], "Unknown")
            if atype not in type_agg:
                type_agg[atype] = {"actions": 0, "agents": 0, "aggr": 0.0, "total_actions": 0.0}
            type_agg[atype]["actions"] += a["total_actions"]
            type_agg[atype]["agents"] += 1
            aggr = sum(a.get("action_types", {}).get(t, 0) for t in AGGRESSIVE_ACTIONS)
            type_agg[atype]["aggr"] += aggr
            type_agg[atype]["total_actions"] += a["total_actions"]

        rows: list[StakeholderImpactRow] = []
        types_seen = set(stance.by_entity_type.keys()) | set(type_agg.keys())

        for etype in sorted(types_seen):
            dist = stance.by_entity_type.get(etype, {})
            if dist:
                majority = max(dist.items(), key=lambda x: x[1])[0]
                parts = [f"{k}:{v:.0f}%" for k, v in sorted(dist.items(), key=lambda x: -x[1]) if v > 0]
                stance_label = ", ".join(parts) if parts else "n/a"
            else:
                majority = "unknown"
                stance_label = "n/a"

            type_stances = [s for s in stance.stances if s.agent_type == etype]
            avg_int = sum(s.intensity for s in type_stances) / max(len(type_stances), 1) if type_stances else 0.0

            ta = type_agg.get(etype, {})
            n_agents = max(int(ta.get("agents", 0)), 1)
            avg_actions = ta.get("actions", 0) / n_agents
            activity_index = (avg_actions / global_mean) if global_mean > 0 else 0.0
            type_total_act = max(ta.get("total_actions", 0), 1)
            esc = (ta.get("aggr", 0) / type_total_act) * 100.0
            voice = (len(type_stances) / max(len(stance.stances), 1)) * 100.0 if stance.stances else 0.0

            rows.append(
                StakeholderImpactRow(
                    entity_type=etype,
                    stance_majority=majority,
                    stance_label=stance_label,
                    avg_intensity=round(avg_int, 2),
                    activity_index=round(activity_index, 2),
                    escalation_exposure=round(esc, 1),
                    voice_share_pct=round(voice, 1),
                )
            )

        return StakeholderImpactMatrix(rows=rows)

    # ───────────────────────────────────────────────────────────
    # Helpers
    # ───────────────────────────────────────────────────────────

    def _load_agent_profiles(self, simulation_id: str) -> list[dict[str, Any]]:
        """Load agent persona files (mirrors ZepTools._load_agent_profiles)."""
        sim_dir = os.path.join(
            os.path.dirname(__file__),
            f"../../uploads/simulations/{simulation_id}",
        )

        reddit_path = os.path.join(sim_dir, "reddit_profiles.json")
        if os.path.exists(reddit_path):
            try:
                with open(reddit_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read reddit_profiles.json: {e}")

        twitter_path = os.path.join(sim_dir, "twitter_profiles.csv")
        if os.path.exists(twitter_path):
            try:
                profiles = []
                with open(twitter_path, encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        profiles.append(
                            {
                                "realname": row.get("name", ""),
                                "username": row.get("username", ""),
                                "bio": row.get("description", ""),
                                "persona": row.get("user_char", ""),
                                "profession": "Unknown",
                            }
                        )
                return profiles
            except Exception as e:
                logger.warning(f"Failed to read twitter_profiles.csv: {e}")

        return []

    def _build_agent_type_map(self, profiles: list[dict[str, Any]]) -> dict[str, str]:
        """Map agent name -> entity type from profiles."""
        name_to_type: dict[str, str] = {}
        for profile in profiles:
            name = profile.get("realname", profile.get("username", ""))
            etype = profile.get("source_entity_type", profile.get("profession", "Unknown"))
            if name:
                name_to_type[name] = etype
        return name_to_type

    def _compute_stance_aggregates(self, result: StanceAnalysis) -> None:
        """Compute distribution and grouping aggregates on a StanceAnalysis."""
        if not result.stances:
            return

        total = len(result.stances)
        counts: dict[str, int] = {}
        for s in result.stances:
            counts[s.position] = counts.get(s.position, 0) + 1

        result.position_counts = counts
        result.position_distribution = {k: (v / total) * 100 for k, v in counts.items()}
        result.average_intensity = sum(s.intensity for s in result.stances) / total

        type_counts: dict[str, dict[str, int]] = {}
        for s in result.stances:
            type_counts.setdefault(s.agent_type, {})
            type_counts[s.agent_type][s.position] = type_counts[s.agent_type].get(s.position, 0) + 1

        for etype, pos_counts in type_counts.items():
            etype_total = sum(pos_counts.values())
            result.by_entity_type[etype] = {k: (v / etype_total) * 100 for k, v in pos_counts.items()}

        for s in result.stances:
            if s.country and s.country != "Unknown":
                result.by_country.setdefault(s.country, []).append(
                    {
                        "position": s.position,
                        "intensity": s.intensity,
                        "confidence": s.confidence,
                    }
                )

    def generate_decision_framework(
        self,
        scenario: str,
        metrics: SimulationMetrics,
        positions: StanceAnalysis,
        risks: RisksToolResult,
        stakeholder_matrix: StakeholderImpactMatrix,
        decision_intake: dict[str, Any] | None = None,
    ) -> DecisionFramework:
        """Synthesize a structured decision recommendation from all analysis data."""
        intake_block = ""
        if decision_intake:
            intake_block = (
                f"\n\nDecision context (from user):\n"
                f"- Role: {decision_intake.get('role', 'Not specified')}\n"
                f"- Decision question: {decision_intake.get('decision', 'Not specified')}\n"
                f"- Constraints: {decision_intake.get('constraints', 'None')}\n"
                f"- Flip conditions: {decision_intake.get('flip_conditions', 'None')}\n"
            )

        system = """\
You are a decision analyst synthesizing simulation results into a structured recommendation.

Return ONLY valid JSON:
{
  "verdict": "Go / No-Go / Proceed with caution / Conditional go",
  "confidence": "high / moderate / low",
  "confidence_rationale": "1 sentence explaining why confidence is at this level, citing data sources or consensus strength",
  "reasoning": "2-4 sentences explaining the verdict based on simulation evidence",
  "key_drivers": [
    {"name": "driver name", "direction": "positive|negative|neutral", "magnitude": "strong|moderate|weak"}
  ],
  "causal_chain": [
    {"cause": "input condition or event", "effect": "downstream consequence", "confidence": "high"}
  ],
  "sensitivity": [
    {"variable": "variable name", "base_value": "current value", "swing_pct": "±X%", "impact_on_verdict": "description"}
  ],
  "flip_conditions": ["condition that would reverse the verdict"],
  "recommended_actions": [
    {"action": "specific action to take", "priority": "critical|high|medium|low", "rationale": "why this action matters", "timeline": "immediate|1-2 weeks|1 month|3 months"}
  ],
  "monitoring_indicators": [
    {"indicator": "what to watch", "current_state": "where it is now", "threshold": "trigger level", "action_if_triggered": "what to do"}
  ],
  "decision_criteria": ["condition that should be true before acting on this verdict"],
  "time_sensitivity": "How long this analysis remains valid and why (e.g. '2-4 weeks — stakeholder positions may shift after upcoming policy announcement')",
  "financial_summary": {
    "applicable": true,
    "revenue_range": {"low": "$X", "high": "$Y", "unit": "USD/year"},
    "cost_range": {"low": "$X", "high": "$Y", "unit": "USD/year"},
    "profit_range": {"low": "$X", "high": "$Y", "unit": "USD/year"},
    "break_even": "9-14 months",
    "time_horizon": "12 months"
  }
}

Rules:
- Base verdict strictly on simulation data, not speculation.
- Include 3-5 key drivers, 2-4 sensitivity rows, 1-3 flip conditions.
- confidence_rationale: explain what drives the confidence level (e.g. number of data sources, \
stakeholder consensus strength, data recency).
- causal_chain: provide 3-5 cause-effect links that explain the logical reasoning chain from \
input conditions to the verdict. Each link should connect a cause to its downstream effect. \
The chain should read as a narrative: condition A leads to B, which causes C. \
Confidence per link should be "high", "moderate", or "low".
- recommended_actions: provide 3-5 prioritized actions the decision-maker should take. Each \
action must be specific and actionable (not generic advice). Priority reflects urgency and impact. \
Timeline indicates when the action should be completed.
- monitoring_indicators: provide 3-4 signals the decision-maker should watch over time. Each \
should have a concrete threshold that would trigger a reassessment or course correction.
- decision_criteria: 2-4 preconditions that should hold true before acting on the verdict. \
These are sanity checks the user can validate independently.
- time_sensitivity: a single sentence explaining the shelf life of this analysis and what \
events could invalidate it.
- If user provided flip conditions, evaluate them against simulation results.
- financial_summary: set "applicable" to true ONLY when the scenario involves quantifiable \
financial outcomes (revenue, costs, profit, investment returns). For pure policy, social, or \
geopolitical scenarios where financial ranges would be speculative, set "applicable" to false \
and omit the range fields.
- When applicable, provide concrete ranges grounded in simulation evidence.
- Write in English.
"""
        user = (
            f"[Scenario]\n{scenario}\n"
            f"{intake_block}\n"
            f"[Quantitative metrics]\n{metrics.to_text()[:4000]}\n\n"
            f"[Stance analysis]\n{positions.to_text()[:4000]}\n\n"
            f"[Risk assessment]\n{risks.to_text()[:4000]}\n\n"
            f"[Stakeholder matrix]\n{stakeholder_matrix.to_text()[:4000]}"
        )

        try:
            data = self.llm.chat_json(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
                max_tokens=2000,
            )
            fin = data.get("financial_summary")
            if not isinstance(fin, dict) or not fin.get("applicable", False):
                fin = None

            raw_chain = data.get("causal_chain", [])
            causal = raw_chain if isinstance(raw_chain, list) else []

            return DecisionFramework(
                verdict=data.get("verdict", "Insufficient data"),
                confidence=data.get("confidence", "low"),
                confidence_rationale=data.get("confidence_rationale", ""),
                reasoning=data.get("reasoning", ""),
                key_drivers=[
                    KeyDriver(
                        name=d.get("name", ""),
                        direction=d.get("direction", ""),
                        magnitude=d.get("magnitude", ""),
                    )
                    for d in data.get("key_drivers", [])
                ],
                sensitivity=[
                    SensitivityRow(
                        variable=s.get("variable", ""),
                        base_value=s.get("base_value", ""),
                        swing_pct=s.get("swing_pct", ""),
                        impact_on_verdict=s.get("impact_on_verdict", ""),
                    )
                    for s in data.get("sensitivity", [])
                ],
                flip_conditions=data.get("flip_conditions", []),
                financial_summary=fin,
                causal_chain=causal,
                recommended_actions=[
                    RecommendedAction(
                        action=a.get("action", ""),
                        priority=a.get("priority", "medium"),
                        rationale=a.get("rationale", ""),
                        timeline=a.get("timeline", ""),
                    )
                    for a in data.get("recommended_actions", [])
                ],
                monitoring_indicators=[
                    MonitoringIndicator(
                        indicator=m.get("indicator", ""),
                        current_state=m.get("current_state", ""),
                        threshold=m.get("threshold", ""),
                        action_if_triggered=m.get("action_if_triggered", ""),
                    )
                    for m in data.get("monitoring_indicators", [])
                ],
                time_sensitivity=data.get("time_sensitivity", ""),
                decision_criteria=data.get("decision_criteria", []),
            )
        except Exception as e:
            logger.warning(f"Decision framework generation failed: {e}")
            return DecisionFramework(
                verdict="Unable to generate",
                confidence="low",
                reasoning="Decision framework generation encountered an error.",
            )
