"""
Research angle registry, LLM-based scenario classifier, and dynamic prompt builder.

The classifier determines which research angles are relevant to a user's scenario
so the deep research agent can prioritise the most valuable lines of inquiry
without the user needing to request them explicitly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("glas.research_angles")


@dataclass
class ResearchAngle:
    id: str
    label: str
    directive: str
    search_hints: list[str] = field(default_factory=list)


RESEARCH_ANGLES: list[ResearchAngle] = [
    ResearchAngle(
        id="historical_precedents",
        label="Historical Precedents",
        directive=(
            "Identify and analyse similar past events or scenarios and their outcomes. "
            "For each precedent, note the timeline, key actors, resolution, and measurable impact. "
            "Quantify how closely each precedent mirrors the current scenario."
        ),
        search_hints=[
            "historical examples of [scenario topic]",
            "past cases similar to [scenario topic] outcome",
            "[scenario topic] precedent analysis",
        ],
    ),
    ResearchAngle(
        id="stock_market",
        label="Stock & Financial Markets",
        directive=(
            "Research relevant stock prices, market capitalisation changes, revenue figures, "
            "analyst ratings, earnings forecasts, and financial performance indicators. "
            "Include price movements tied to key events and any analyst consensus targets."
        ),
        search_hints=[
            "[company/sector] stock price impact",
            "[company] market cap revenue earnings",
            "financial analyst rating [company/sector]",
        ],
    ),
    ResearchAngle(
        id="regulatory",
        label="Regulatory & Legal Landscape",
        directive=(
            "Map the current and pending regulatory environment: active legislation, "
            "proposed rules, enforcement actions, court rulings, and compliance requirements. "
            "Note any regulatory deadlines, comment periods, or upcoming hearings."
        ),
        search_hints=[
            "[topic] regulation legislation 2025 2026",
            "[topic] regulatory compliance requirements",
            "[topic] legal ruling enforcement action",
        ],
    ),
    ResearchAngle(
        id="competitor_analysis",
        label="Competitor Analysis",
        directive=(
            "Identify key competitors and how they have responded or are likely to respond "
            "to this scenario. Compare strategies, market share shifts, and competitive "
            "positioning. Note any first-mover advantages or defensive moves."
        ),
        search_hints=[
            "[company/topic] competitor response strategy",
            "[sector] market share competitive landscape",
            "[company] vs competitors [topic]",
        ],
    ),
    ResearchAngle(
        id="public_sentiment",
        label="Public Sentiment & Media",
        directive=(
            "Gauge public and media sentiment: major press coverage themes, social media "
            "reaction patterns, consumer surveys, brand perception shifts, and any viral "
            "narratives. Note sentiment trajectory (improving, worsening, polarised)."
        ),
        search_hints=[
            "[topic] public opinion sentiment survey",
            "[topic] media coverage reaction",
            "[company/topic] social media response",
        ],
    ),
    ResearchAngle(
        id="macro_economic",
        label="Macroeconomic Context",
        directive=(
            "Provide relevant macroeconomic context: GDP growth, inflation rates, interest "
            "rate environment, unemployment, trade balances, commodity prices, and currency "
            "movements that may influence the scenario's trajectory."
        ),
        search_hints=[
            "[country/region] GDP inflation interest rates",
            "macroeconomic outlook [sector/topic]",
            "[topic] economic impact forecast",
        ],
    ),
    ResearchAngle(
        id="industry_benchmarks",
        label="Industry Benchmarks",
        directive=(
            "Provide sector-level benchmarks: industry averages for key metrics, "
            "best-in-class performance standards, typical timelines for similar initiatives, "
            "and success/failure rates for comparable projects or decisions."
        ),
        search_hints=[
            "[industry] benchmark average metrics",
            "[sector] best practice performance standards",
            "[topic] success rate industry average",
        ],
    ),
    ResearchAngle(
        id="geopolitical",
        label="Geopolitical Context",
        directive=(
            "Assess geopolitical factors: international relations, sanctions, trade "
            "agreements, diplomatic tensions, supply chain dependencies, and cross-border "
            "regulatory divergence that could affect the scenario."
        ),
        search_hints=[
            "[topic] geopolitical risk international relations",
            "[countries] sanctions trade agreement",
            "[topic] supply chain geopolitical",
        ],
    ),
    ResearchAngle(
        id="demographic",
        label="Demographic & Social Trends",
        directive=(
            "Identify relevant demographic and social trends: population shifts, workforce "
            "composition changes, generational behaviour differences, urbanisation patterns, "
            "and consumer behaviour evolution that may shape the scenario's outcome."
        ),
        search_hints=[
            "[topic] demographic trends population",
            "[sector] consumer behaviour generational shift",
            "[topic] workforce trends social change",
        ],
    ),
    ResearchAngle(
        id="tech_landscape",
        label="Technology Landscape",
        directive=(
            "Map the technology landscape: adoption curves for relevant technologies, "
            "disruption risks, patent activity, R&D investment trends, and emerging tech "
            "that could accelerate or derail the scenario."
        ),
        search_hints=[
            "[topic] technology adoption disruption",
            "[sector] emerging tech innovation patents",
            "[topic] digital transformation technology trends",
        ],
    ),
]

_ANGLE_MAP: dict[str, ResearchAngle] = {a.id: a for a in RESEARCH_ANGLES}

ALL_ANGLE_IDS: list[str] = [a.id for a in RESEARCH_ANGLES]


def get_angles_by_ids(ids: list[str]) -> list[ResearchAngle]:
    return [_ANGLE_MAP[aid] for aid in ids if aid in _ANGLE_MAP]


# ---------------------------------------------------------------------------
# Scenario classifier
# ---------------------------------------------------------------------------

_CLASSIFIER_SYSTEM = """\
You are a research-planning assistant. Given a scenario description, decide which \
research angles are relevant and should be prioritised.

Available angle IDs:
{angle_list}

Return ONLY a JSON array of the relevant angle IDs. Include an angle only if it \
would materially improve the research quality for this specific scenario. \
Do NOT include angles that are tangential or unlikely to yield useful findings.

Example output: ["historical_precedents", "stock_market", "regulatory"]
"""


def classify_scenario(scenario: str) -> list[str]:
    """Use a cheap LLM call to decide which research angles apply to *scenario*."""
    from ..utils.llm_client import LLMClient

    angle_descriptions = "\n".join(f"- {a.id}: {a.label}" for a in RESEARCH_ANGLES)
    system_prompt = _CLASSIFIER_SYSTEM.format(angle_list=angle_descriptions)

    try:
        llm = LLMClient(model=Config.RESEARCH_CLASSIFICATION_MODEL)
        raw = llm.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Scenario:\n{scenario}"},
            ],
            temperature=0.1,
            max_tokens=200,
        )
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        ids = json.loads(cleaned)
        if not isinstance(ids, list):
            raise ValueError("Expected JSON array")
        valid = [aid for aid in ids if aid in _ANGLE_MAP]
        logger.info(f"Scenario classified — relevant angles: {valid}")
        return valid
    except Exception:
        logger.exception("Scenario classification failed — falling back to all angles")
        return ALL_ANGLE_IDS


# ---------------------------------------------------------------------------
# Dynamic prompt builder
# ---------------------------------------------------------------------------

_BASE_PROMPT = """\
You are a senior research analyst preparing a comprehensive dossier for a multi-agent scenario \
simulation engine. Your dossier will be processed by downstream systems that:
1. Extract every named entity (people, organisations, governments, companies, media outlets, \
advocacy groups, institutions) and turn each into a simulated AI agent.
2. Build a knowledge graph of relationships between those entities.
3. Run a social-media simulation (Twitter and Reddit) where these agents debate, react, and \
influence each other over a configurable time horizon.

The quality of the simulation depends entirely on the depth and specificity of your research. \
Vague summaries produce shallow simulations. Specific names, positions, behavioural patterns, \
and relationship dynamics produce rich, realistic ones.

**Epistemic discipline (non-negotiable):**
- Every non-obvious factual claim should be traceable to a source you found via search; prefer \
primary documents, regulators, companies, courts, official statistics, and reputable news with \
named reporting. If evidence is thin, say so explicitly rather than filling gaps.
- Clearly separate: (a) directly sourced facts, (b) widespread reporting without primary docs, \
(c) analyst or expert inference, (d) your own reasoned scenario assumptions. Label these in-line \
where ambiguity matters.
- Do not invent names, numbers, dates, quotes, poll results, or "typical" statistics. If you \
cannot verify a figure, omit it or give a qualitative range and the uncertainty.
- Where credible sources disagree, summarise the disagreement and what would resolve it.

**Operational realism (what makes agents behave believably):**
- For major actors, specify incentives, constraints, audiences they answer to, veto points, \
escalation/de-escalation triggers, and what they would lose or gain from each plausible path.
- Include concrete decision rules where known (e.g. legal thresholds, board or parliamentary \
steps, treaty clauses) and mark when you are inferring behaviour.

Your task:
1. Search the web thoroughly for the most current, relevant information about the scenario.
2. Produce a structured research report covering AT MINIMUM:

   - **Background & Context**: Key facts, recent developments, current state of play, and \
the core tensions or decisions at stake.

   - **Key Stakeholders (CRITICAL — this drives agent generation)**:
     Name every significant actor across ALL of these categories where relevant:
     * Heads of state, senior officials, military leaders
     * Companies, CEOs, and corporate decision-makers
     * International organisations (UN, NATO, EU, IMF, etc.)
     * Regulatory bodies and courts
     * NGOs, advocacy groups, and lobby organisations
     * Think tanks and policy institutes
     * Major media outlets and influential journalists
     * Public figures, activists, and social media voices
     * Affected populations and interest groups
     For EACH actor, provide: their stated position, underlying interests, influence level \
(high/medium/low), communication style (aggressive, diplomatic, populist, technocratic, etc.), \
and known rhetorical patterns or quotes. Aim for 20-40 named entities.

   - **Reaction Chains & Decision Dynamics**: For the most important actors, describe how they \
would likely react to key developments. Use "if X then Y" framing: "If sanctions are imposed, \
Iran is likely to..." / "If oil prices exceed $X, OPEC will..." This is critical for simulation \
realism.

   - **Public Opinion Landscape**: Identify the major camps of public discourse. What are the \
dominant narratives on each side? What hashtags, slogans, or talking points define each camp? \
How polarised is opinion? Which narratives are gaining or losing traction?

   - **Information Flow & Influence Networks**: Who amplifies whom? Which media outlets back \
which actors? Which think tanks brief which governments? How does information cascade from \
official statements to public discourse?

   - **Quantitative Anchors**: Specific numbers, statistics, market data, financial figures, \
polling data, trade volumes, military capabilities — anything that grounds the scenario in \
measurable reality. For each anchor, include units, as-of date or period, geography, and whether \
the figure is from a primary source, official statistics, or media reporting.

   - **Historical Precedents**: Similar past scenarios and their outcomes, including the actors \
involved and the timeline of events.

   - **Key Risk Factors & Wildcards**: What could go wrong, uncertainty sources, low-probability \
high-impact events, and which actors are most exposed.

   - **Timeline & Inflection Points**: Key upcoming dates, deadlines, elections, hearings, \
treaty expirations, or scheduled events that could shift the scenario's trajectory.

   - **Relationships & Alliances**: Explicit mapping of alliances, rivalries, dependencies, \
supply chains, treaty obligations, and regulatory oversight between the key actors.

   - **Known Unknowns & Information Gaps**: What is not public, what is contested, and which \
assumptions the simulation would need to vary (sensitivity) because evidence is weak.

   - **Simulation Parameters (explicit)**: A short, numbered list of the top 8–12 levers a \
modeller would toggle (e.g. price of X, policy choice Y, court outcome Z) with plausible ranges \
or discrete options **only** when supported by sources or clearly marked as illustrative.

Requirements:
- Use specific names, dates, figures, and citations throughout. Never say "some analysts" — \
name the analyst, institution, and date.
- Prefer recent data (last 12 months) over older sources.
- Include URLs for all sources referenced.
- Write up to 15000 words. Depth and specificity are valued over brevity — cover every angle thoroughly.
- Structure with clear markdown headings.
- Conclude with a **Key Facts Summary** section (markdown heading must contain the words "Key Facts"): \
10–15 bullets of the most important **quantitative** facts, each with a source or URL where possible.
"""

_ANGLE_SECTION_HEADER = """
Additionally, the following research angles have been identified as particularly \
relevant to this scenario. You MUST include dedicated sections for each:
"""


def build_research_prompt(relevant_angles: list[ResearchAngle]) -> str:
    """Assemble a dynamic system prompt from the base template + relevant angles."""
    if not relevant_angles:
        return _BASE_PROMPT

    parts = [_BASE_PROMPT, _ANGLE_SECTION_HEADER]
    for angle in relevant_angles:
        parts.append(f"\n### {angle.label}\n{angle.directive}")
        if angle.search_hints:
            hints = ", ".join(f'"{h}"' for h in angle.search_hints)
            parts.append(f"Consider search queries like: {hints}")

    return "\n".join(parts)
