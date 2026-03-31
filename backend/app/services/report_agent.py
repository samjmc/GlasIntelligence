"""
Report Agent Service
Simulation report generation using LangChain + Zep with ReACT pattern

Features:
1. Generate reports based on simulation requirements and Zep graph information
2. Plan outline structure first, then generate section by section
3. Each section uses multi-round ReACT thinking and reflection
4. Supports conversation with users, autonomously invoking retrieval tools during dialogue
"""

import os
import json
import time
import re
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .zep_tools import (
    ZepToolsService, 
    SearchResult, 
    InsightForgeResult, 
    PanoramaResult,
    InterviewResult
)
from .quantitative_analysis_service import QuantitativeAnalysisService
from .report_payload import (
    REPORT_DISCLAIMER_MD,
    build_report_payload_v1,
    generate_scenario_ladder_json,
    payload_preamble_for_prompt,
    render_grounding_markdown,
    render_scenarios_markdown,
    render_decision_markdown,
)
from .grounding_bundle import (
    evaluate_grounding_staleness,
    build_claim_ledger_from_project,
    ingest_dossier_sources,
)

logger = get_logger('glas.report_agent')

# Outline roles for valued-output reports (v1)
OUTLINE_REQUIRED_ROLES = (
    "grounding_and_assumptions",
    "quant_snapshot",
    "stakeholder_impacts",
    "scenarios",
    "risks_actions",
    "decision_recommendation",
)
QUANT_TOOL_NAMES = frozenset({"analyze_metrics", "assess_positions", "estimate_risks", "stakeholder_matrix"})


class ReportLogger:
    """
    Report Agent detailed logger
    
    Generates an agent_log.jsonl file in the report folder, recording each detailed action.
    Each line is a complete JSON object containing timestamp, action type, detailed content, etc.
    """
    
    def __init__(self, report_id: str):
        """
        Initialize the logger
        
        Args:
            report_id: Report ID, used to determine the log file path
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'agent_log.jsonl'
        )
        self.start_time = datetime.now()
        self._ensure_log_file()
    
    def _ensure_log_file(self):
        """Ensure the log file directory exists"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _get_elapsed_time(self) -> float:
        """Get elapsed time from start to now (seconds)"""
        return (datetime.now() - self.start_time).total_seconds()
    
    def log(
        self, 
        action: str, 
        stage: str,
        details: Dict[str, Any],
        section_title: str = None,
        section_index: int = None
    ):
        """
        Record a log entry
        
        Args:
            action: Action type, e.g. 'start', 'tool_call', 'llm_response', 'section_complete', etc.
            stage: Current stage, e.g. 'planning', 'generating', 'completed'
            details: Details dictionary, not truncated
            section_title: Current section title (optional)
            section_index: Current section index (optional)
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(self._get_elapsed_time(), 2),
            "report_id": self.report_id,
            "action": action,
            "stage": stage,
            "section_title": section_title,
            "section_index": section_index,
            "details": details
        }
        
        # Append to JSONL file
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
    
    def log_start(self, simulation_id: str, graph_id: str, simulation_requirement: str):
        """Record report generation start"""
        self.log(
            action="report_start",
            stage="pending",
            details={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "simulation_requirement": simulation_requirement,
                "message": "Report generation task started"
            }
        )
    
    def log_planning_start(self):
        """Record outline planning start"""
        self.log(
            action="planning_start",
            stage="planning",
            details={"message": "Starting report outline planning"}
        )
    
    def log_planning_context(self, context: Dict[str, Any]):
        """Record context information obtained during planning"""
        self.log(
            action="planning_context",
            stage="planning",
            details={
                "message": "Retrieved simulation context information",
                "context": context
            }
        )
    
    def log_planning_complete(self, outline_dict: Dict[str, Any]):
        """Record outline planning completion"""
        self.log(
            action="planning_complete",
            stage="planning",
            details={
                "message": "Outline planning completed",
                "outline": outline_dict
            }
        )
    
    def log_section_start(self, section_title: str, section_index: int):
        """Record section generation start"""
        self.log(
            action="section_start",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={"message": f"Starting section generation: {section_title}"}
        )
    
    def log_react_thought(self, section_title: str, section_index: int, iteration: int, thought: str):
        """Record ReACT thinking process"""
        self.log(
            action="react_thought",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "thought": thought,
                "message": f"ReACT iteration {iteration} thinking"
            }
        )
    
    def log_tool_call(
        self, 
        section_title: str, 
        section_index: int,
        tool_name: str, 
        parameters: Dict[str, Any],
        iteration: int
    ):
        """Record tool call"""
        self.log(
            action="tool_call",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "parameters": parameters,
                "message": f"Calling tool: {tool_name}"
            }
        )
    
    def log_tool_result(
        self,
        section_title: str,
        section_index: int,
        tool_name: str,
        result: str,
        iteration: int
    ):
        """Record tool call result (full content, not truncated)"""
        self.log(
            action="tool_result",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "result": result,  # Full result, not truncated
                "result_length": len(result),
                "message": f"Tool {tool_name} returned result"
            }
        )
    
    def log_llm_response(
        self,
        section_title: str,
        section_index: int,
        response: str,
        iteration: int,
        has_tool_calls: bool,
        has_final_answer: bool
    ):
        """Record LLM response (full content, not truncated)"""
        self.log(
            action="llm_response",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "response": response,  # Full response, not truncated
                "response_length": len(response),
                "has_tool_calls": has_tool_calls,
                "has_final_answer": has_final_answer,
                "message": f"LLM response (tool calls: {has_tool_calls}, final answer: {has_final_answer})"
            }
        )
    
    def log_section_content(
        self,
        section_title: str,
        section_index: int,
        content: str,
        tool_calls_count: int
    ):
        """Record section content generation complete (content only, does not mean entire section is done)"""
        self.log(
            action="section_content",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": content,  # Full content, not truncated
                "content_length": len(content),
                "tool_calls_count": tool_calls_count,
                "message": f"Section {section_title} content generation complete"
            }
        )
    
    def log_section_full_complete(
        self,
        section_title: str,
        section_index: int,
        full_content: str
    ):
        """
        Record section generation complete

        The frontend should listen for this log to determine if a section is truly complete and get the full content
        """
        self.log(
            action="section_complete",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": full_content,
                "content_length": len(full_content),
                "message": f"Section {section_title} generation complete"
            }
        )
    
    def log_report_complete(self, total_sections: int, total_time_seconds: float):
        """Record report generation complete"""
        self.log(
            action="report_complete",
            stage="completed",
            details={
                "total_sections": total_sections,
                "total_time_seconds": round(total_time_seconds, 2),
                "message": "Report generation complete"
            }
        )
    
    def log_error(self, error_message: str, stage: str, section_title: str = None):
        """Record error"""
        self.log(
            action="error",
            stage=stage,
            section_title=section_title,
            section_index=None,
            details={
                "error": error_message,
                "message": f"Error occurred: {error_message}"
            }
        )


class ReportConsoleLogger:
    """
    Report Agent console logger
    
    Writes console-style logs (INFO, WARNING, etc.) to a console_log.txt file in the report folder.
    These logs differ from agent_log.jsonl and are plain-text console output.
    """
    
    def __init__(self, report_id: str):
        """
        Initialize the console logger
        
        Args:
            report_id: Report ID, used to determine the log file path
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'console_log.txt'
        )
        self._ensure_log_file()
        self._file_handler = None
        self._setup_file_handler()
    
    def _ensure_log_file(self):
        """Ensure the log file directory exists"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)
    
    def _setup_file_handler(self):
        """Set up file handler to write logs to file simultaneously"""
        import logging
        
        # Create file handler
        self._file_handler = logging.FileHandler(
            self.log_file_path,
            mode='a',
            encoding='utf-8'
        )
        self._file_handler.setLevel(logging.INFO)
        
        # Use the same concise format as the console
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        self._file_handler.setFormatter(formatter)
        
        # Attach to report_agent related loggers
        loggers_to_attach = [
            'glas.report_agent',
            'glas.zep_tools',
        ]
        
        for logger_name in loggers_to_attach:
            target_logger = logging.getLogger(logger_name)
            # Avoid duplicate handlers
            if self._file_handler not in target_logger.handlers:
                target_logger.addHandler(self._file_handler)
    
    def close(self):
        """Close file handler and remove from loggers"""
        import logging
        
        if self._file_handler:
            loggers_to_detach = [
                'glas.report_agent',
                'glas.zep_tools',
            ]
            
            for logger_name in loggers_to_detach:
                target_logger = logging.getLogger(logger_name)
                if self._file_handler in target_logger.handlers:
                    target_logger.removeHandler(self._file_handler)
            
            self._file_handler.close()
            self._file_handler = None
    
    def __del__(self):
        """Ensure file handler is closed on destruction"""
        self.close()


class ReportStatus(str, Enum):
    """Report status"""
    PENDING = "pending"
    PLANNING = "planning"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReportSection:
    """Report section"""
    title: str
    content: str = ""
    role: str = "general"
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content,
            "role": self.role,
            "description": self.description,
        }

    def to_markdown(self, level: int = 2) -> str:
        """Convert to Markdown format"""
        md = f"{'#' * level} {self.title}\n\n"
        if self.content:
            md += f"{self.content}\n\n"
        return md


@dataclass
class ReportOutline:
    """Report outline"""
    title: str
    summary: str
    sections: List[ReportSection]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "sections": [s.to_dict() for s in self.sections]
        }
    
    def to_markdown(self) -> str:
        """Convert to Markdown format"""
        md = f"# {self.title}\n\n"
        md += f"> {self.summary}\n\n"
        for section in self.sections:
            md += section.to_markdown()
        return md


@dataclass
class Report:
    """Complete report"""
    report_id: str
    simulation_id: str
    graph_id: str
    simulation_requirement: str
    status: ReportStatus
    outline: Optional[ReportOutline] = None
    markdown_content: str = ""
    created_at: str = ""
    completed_at: str = ""
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "simulation_id": self.simulation_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "status": self.status.value,
            "outline": self.outline.to_dict() if self.outline else None,
            "markdown_content": self.markdown_content,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error
        }


# ═══════════════════════════════════════════════════════════════
# Prompt Template Constants
# ═══════════════════════════════════════════════════════════════

# ── Tool Descriptions ──

TOOL_DESC_INSIGHT_FORGE = """\
[Deep Insight Retrieval - Powerful Search Tool]
A powerful retrieval function designed for deep analysis. It will:
1. Automatically decompose your question into multiple sub-questions
2. Retrieve information from the simulation graph across multiple dimensions
3. Integrate semantic search, entity analysis, and relationship chain tracking results
4. Return the most comprehensive and in-depth retrieval content

[Use Cases]
- Need to deeply analyse a topic
- Need to understand multiple aspects of an event
- Need to gather rich material to support a report section

[Returns]
- Relevant original facts (can be directly quoted)
- Core entity insights
- Relationship chain analysis"""

TOOL_DESC_PANORAMA_SEARCH = """\
[Broad Search - Full Panorama View]
This tool retrieves the complete overview of simulation results, particularly suited for understanding event evolution. It will:
1. Retrieve all related nodes and relationships
2. Distinguish between currently valid facts and historical/expired facts
3. Help you understand how narratives evolved

[Use Cases]
- Need to understand the complete development arc of events
- Need to compare sentiment changes across different stages
- Need comprehensive entity and relationship information

[Returns]
- Currently valid facts (latest simulation results)
- Historical/expired facts (evolution record)
- All involved entities"""

TOOL_DESC_QUICK_SEARCH = """\
[Simple Search - Quick Retrieval]
A lightweight quick retrieval tool suited for simple, direct information queries.

[Use Cases]
- Need to quickly find specific information
- Need to verify a fact
- Simple information retrieval

[Returns]
- List of facts most relevant to the query"""

TOOL_DESC_INTERVIEW_AGENTS = """\
[Deep Interview - Real Agent Interviews (Dual Platform)]
Calls the OASIS simulation environment's interview API to conduct real interviews with running simulation agents!
This is not LLM simulation -- it calls the actual interview interface to get simulation agents' original responses.
By default interviews are conducted on both Twitter and Reddit platforms simultaneously for more comprehensive viewpoints.

Workflow:
1. Automatically reads persona files to understand all simulation agents
2. Intelligently selects agents most relevant to the interview topic (e.g. pharmacists, officials, patients)
3. Automatically generates interview questions
4. Calls /api/simulation/interview/batch interface for dual-platform real interviews
5. Integrates all interview results, providing multi-perspective analysis

[Use Cases]
- Need to understand event perspectives from different roles (What do pharmacists think? What does the media say? What is the official position?)
- Need to collect multi-party opinions and positions
- Need to get simulation agents' real responses (from the OASIS simulation environment)
- Want to make the report more vivid with "interview transcripts"

[Returns]
- Identity information of interviewed agents
- Each agent's interview responses across Twitter and Reddit platforms
- Key quotes (can be directly cited)
- Interview summary and viewpoint comparison

[Important] Requires the OASIS simulation environment to be running!"""

# ── Outline Planning Prompt ──

PLAN_SYSTEM_PROMPT = """\
You are a "Predictive Analysis Report" writing expert with a "god's-eye view" of the simulation world -- you can observe every agent's behaviour, statements, and interactions.

[Core Concept]
We have built a simulation world and injected a specific "simulation requirement" as a variable. The evolution of the simulation world represents a prediction of what could happen in the future. You are observing not "experimental data" but "a rehearsal of the future".

[Your Task]
Write a "Predictive Analysis Report" that answers:
1. Under the conditions we set, what happened in the future?
2. How did different types of agents (stakeholder groups) react and act?
3. What notable future trends and risks did this simulation reveal?

[Report Positioning]
- This is a simulation-based predictive analysis report, revealing "if this happens, what follows"
- Focus on prediction outcomes: event trajectories, group reactions, emergent phenomena, potential risks
- Agent statements and actions in the simulation world are predictions of future group behaviour
- This is NOT an analysis of the current real-world situation
- This is NOT a generic sentiment overview

[Actionable Insights Requirement]
- Every section MUST end with concrete, actionable recommendations
- Recommendations must reference specific statistics from the simulation
- The report must be useful for decision-making, not just descriptive

[Section Limits]
- Minimum 2 sections, maximum 5 sections
- No sub-sections needed; each section contains complete content
- Content should be concise, focused on core predictive findings
- Section structure is designed by you based on prediction results

Output a JSON report outline in the following format:
{
    "title": "Report title",
    "summary": "Report summary (one sentence summarising core predictive findings)",
    "sections": [
        {
            "title": "Section title",
            "description": "Section content description"
        }
    ]
}

IMPORTANT: The title, summary, section titles, and all content MUST be in English.
Note: the sections array must have minimum 2, maximum 5 elements!"""

PLAN_USER_PROMPT_TEMPLATE = """\
[Prediction Scenario]
Variable injected into the simulation world (simulation requirement): {simulation_requirement}

[Simulation World Scale]
- Number of entities in simulation: {total_nodes}
- Number of relationships between entities: {total_edges}
- Entity type distribution: {entity_types}
- Number of active agents: {total_entities}

[Sample of Predicted Future Facts from Simulation]
{related_facts_json}

Examine this future rehearsal from a god's-eye perspective:
1. Under the conditions we set, what state did the future present?
2. How did different stakeholder groups (agents) react and act?
3. What notable future trends did this simulation reveal?

Design the most appropriate report section structure based on prediction results.

[Reminder] Report sections: minimum 2, maximum 5. Content must be concise and focused on core predictive findings. ALL content MUST be in English."""

PLAN_SYSTEM_PROMPT_V1 = """\
You are a "Predictive Analysis Report" expert planning section structure for a simulation rehearsal.

Each section has a fixed machine **role** (use exactly these role values) plus a user-facing **title** you choose to match the scenario.

Required roles (include each exactly once, in a sensible order — typically grounding first, then quant, stakeholders, scenarios, risks, decision):
- grounding_and_assumptions — sources, freshness, what is user-provided vs simulated
- quant_snapshot — activity, escalation, engagement statistics
- stakeholder_impacts — who is affected how; must reference the stakeholder impact matrix
- scenarios — scenario ladder (base / upside / stress) with probability brackets
- risks_actions — probability ranges, risk matrix, concrete recommendations
- decision_recommendation — structured decision verdict with key drivers and sensitivity

Output JSON only:
{
    "title": "...",
    "summary": "one sentence",
    "sections": [
        { "role": "grounding_and_assumptions", "title": "...", "description": "..." },
        { "role": "quant_snapshot", "title": "...", "description": "..." },
        { "role": "stakeholder_impacts", "title": "...", "description": "..." },
        { "role": "scenarios", "title": "...", "description": "..." },
        { "role": "risks_actions", "title": "...", "description": "..." },
        { "role": "decision_recommendation", "title": "...", "description": "..." }
    ]
}

Rules: exactly 6 sections; roles must match the list above; ALL text in English."""

# ── Section Generation Prompt ──

SECTION_SYSTEM_PROMPT_TEMPLATE = """\
You are a "Predictive Analysis Report" writing expert, currently writing one section of the report.

Report title: {report_title}
Report summary: {report_summary}
Prediction scenario (simulation requirement): {simulation_requirement}

Current section to write: {section_title}
Section role (machine): {section_role}

{payload_preamble}

===============================================================
[Core Concept]
===============================================================

The simulation world is a rehearsal of the future. We injected specific conditions (simulation requirement) into the simulation world. Agent behaviour and interactions in the simulation are predictions of future group behaviour.

Your task is to:
- Reveal what happened in the future under the set conditions
- Predict how different stakeholder groups (agents) reacted and acted
- Discover notable future trends, risks, and opportunities

DO NOT write this as an analysis of the current real-world situation.
DO focus on "what will happen" -- simulation results ARE the predicted future.

===============================================================
[Most Important Rules - Must Follow]
===============================================================

1. [QUANTITATIVE DATA FIRST — Non-Negotiable]
   - BEFORE writing prose, call at least one quantitative tool (analyze_metrics, assess_positions, estimate_risks, or stakeholder_matrix)
   - Embed hard numbers in your analysis: percentages, probability ranges, counts, indices
   - Every claim must be grounded in simulation-derived statistics
   - Tool calling order: QUANTITATIVE FIRST, then qualitative (interview_agents, panorama_search, etc.)

2. [Actionable Recommendations — Required]
   - Each section must end with 1-3 concrete, actionable recommendations
   - Recommendations must reference specific statistics from the simulation
   - Format: "**Actionable Insight:** [specific recommendation backed by simulation data]"

3. [Must Call Tools to Observe the Simulation World]
   - You are observing the future rehearsal from a god's-eye perspective
   - All content must come from events and agent statements/actions in the simulation world
   - Do NOT use your own knowledge to write report content
   - Each section must call tools at least 3 times (maximum 5) to observe the simulation world

4. [Must Quote Agents' Original Statements and Actions]
   - Agent statements and behaviours are predictions of future group behaviour
   - Use quotation format in the report to present these predictions, e.g.:
     > "A group of stakeholders expressed: original content..."
   - These quotes are the core evidence of simulation predictions

5. [Language Consistency - WRITE EVERYTHING IN ENGLISH]
   - The entire report MUST be written in English
   - All quotes, analysis, headings, and content must be in English
   - If tool results return content in other languages, translate it to fluent English
   - Maintain the original meaning when translating, ensure natural expression
   - This rule applies to both body text and quote blocks (> format)

6. [Faithfully Present Prediction Results]
   - Report content must reflect the simulation results representing the future
   - Do not add information that does not exist in the simulation
   - If information is insufficient on some aspect, state this honestly

===============================================================
[Format Rules - Extremely Important!]
===============================================================

[One Section = Minimum Content Unit]
- Each section is the smallest unit of the report
- DO NOT use any Markdown headings (#, ##, ###, #### etc.) within a section
- DO NOT add the section's main title at the start of content
- Section titles are added automatically by the system; you only write the body text
- USE **bold text**, paragraph breaks, quotes, and lists to organise content, but do NOT use headings

[Correct Example]
```
This section analyses the trajectory of public discourse around the policy. Through deep analysis of simulation data, we found...

**Initial Reaction Phase**

Twitter served as the primary venue for initial reactions, carrying the core information-sharing function:

> "Twitter contributed 68% of initial discourse volume..."

**Sentiment Amplification Phase**

Reddit further amplified the event's impact:

- Strong visual impact through detailed threads
- High emotional resonance in community discussions
```

[Incorrect Example]
```
## Executive Summary     <- Wrong! Do not add any headings
### 1. Initial Phase     <- Wrong! Do not use ### for sub-sections
#### 1.1 Detailed Analysis  <- Wrong! Do not use #### for fine divisions

This section analyses...
```

===============================================================
[Available Retrieval Tools] (call 3-5 times per section)
===============================================================

{tools_description}

{quant_tools_block}

[Tool Usage Advice - mix different tools, don't use only one type]
- insight_forge: Deep insight analysis, automatically decomposes questions and retrieves facts and relationships across multiple dimensions
- panorama_search: Wide-angle panoramic search, understand the full picture of events, timelines and evolution
- quick_search: Quickly verify a specific piece of information
- interview_agents: Interview simulation agents, get first-person perspectives and real reactions from different roles
- analyze_metrics / assess_positions / estimate_risks / stakeholder_matrix: Quantitative tools (when listed above) — call as required for this section role

===============================================================
[Workflow]
===============================================================

Each response you can only do ONE of the following (not both):

Option A - Call a tool:
Output your thinking, then call a tool using this format:
<tool_call>
{{"name": "tool_name", "parameters": {{"param_name": "param_value"}}}}
</tool_call>
The system will execute the tool and return results. You do not need to and cannot write tool results yourself.

Option B - Output final content:
When you have gathered sufficient information through tools, output section content starting with "Final Answer:".

STRICTLY FORBIDDEN:
- Do not include both a tool call and Final Answer in one response
- Do not fabricate tool return results (Observations); all tool results are injected by the system
- Maximum one tool call per response

===============================================================
[Section Content Requirements]
===============================================================

1. Content must be based on simulation data retrieved through tools
2. Extensively quote original statements to demonstrate simulation findings
3. Use Markdown format (but NO headings):
   - Use **bold text** to mark key points (instead of sub-headings)
   - Use lists (- or 1.2.3.) to organise key points
   - Use blank lines to separate paragraphs
   - DO NOT use #, ##, ###, #### or any heading syntax
4. [Quote Format - Must Be Standalone Paragraphs]
   Quotes must be standalone paragraphs with blank lines before and after:

   CORRECT format:
   ```
   The official response was seen as lacking substance.

   > "The response appeared rigid and slow in the fast-moving social media environment."

   This assessment reflected widespread public dissatisfaction.
   ```

   INCORRECT format:
   ```
   The response was lacking substance. > "The response appeared rigid..." This reflected...
   ```
5. Maintain logical coherence with other sections
6. [Avoid Repetition] Carefully read the completed sections below; do not repeat the same information
7. [Reminder] Do NOT add any headings! Use **bold text** instead of sub-section titles
8. [CRITICAL] Write ALL content in English. ALL quotes, analysis, and text MUST be in English."""

SECTION_USER_PROMPT_TEMPLATE = """\
Completed section content (read carefully, avoid repetition):
{previous_content}

===============================================================
[Current Task] Write section: {section_title}
===============================================================

[Important Reminders]
1. Carefully read the completed sections above to avoid repeating the same content!
2. You must call tools to retrieve simulation data before writing
3. Mix different tools; don't use only one type
4. Write EVERYTHING in English
5. Report content must come from retrieval results; do not use your own knowledge

[Format Warning - Must Follow]
- DO NOT write any headings (#, ##, ###, #### are all forbidden)
- DO NOT write "{section_title}" as the opening
- Section titles are added automatically by the system
- Write body text directly, use **bold text** instead of sub-section titles

Begin:
1. First think (Thought) about what information this section needs
2. Then call tools (Action) to retrieve simulation data
3. After collecting sufficient information, output Final Answer (body text only, no headings)
4. Write EVERYTHING in English"""

# ── ReACT Loop Message Templates ──

REACT_OBSERVATION_TEMPLATE = """\
Observation (retrieval results):

=== Tool {tool_name} returned ===
{result}

===============================================================
Tools called {tool_calls_count}/{max_tool_calls} times (used: {used_tools_str}){unused_hint}
- If information is sufficient: output section content starting with "Final Answer:" (must quote original statements above). Write in English.
- If more information is needed: call another tool to continue retrieval
==============================================================="""

REACT_INSUFFICIENT_TOOLS_MSG = (
    "[Note] You have only called {tool_calls_count} tools, minimum {min_tool_calls} required. "
    "Please call more tools to retrieve additional simulation data before outputting Final Answer.{unused_hint}"
)

REACT_INSUFFICIENT_TOOLS_MSG_ALT = (
    "Currently only {tool_calls_count} tool calls made, minimum {min_tool_calls} required. "
    "Please call tools to retrieve simulation data.{unused_hint}"
)

REACT_TOOL_LIMIT_MSG = (
    "Tool call limit reached ({tool_calls_count}/{max_tool_calls}), no more tool calls allowed. "
    'Please immediately output section content starting with "Final Answer:" based on information gathered. Write in English.'
)

REACT_UNUSED_TOOLS_HINT = "\nTip: You haven't used: {unused_list}. WARNING: If you haven't called any quantitative tool (analyze_metrics, assess_positions, estimate_risks), your Final Answer will be REJECTED. Call a quantitative tool now."

REACT_MISSING_QUANT_MSG = (
    "[REQUIRED] You have not called any quantitative tool yet. "
    "You MUST call at least one of: analyze_metrics, assess_positions, or estimate_risks "
    "before writing your Final Answer. These tools provide the hard statistics, "
    "probability ranges, and risk assessments that the report requires. "
    "Call one now."
)

REACT_FORCE_FINAL_MSG = "Tool call limit reached. Please output Final Answer: and generate section content now. Write in English."

# ── Chat Prompt ──

CHAT_SYSTEM_PROMPT_TEMPLATE = """\
You are a concise and efficient simulation prediction assistant. Answer in English.

[Background]
Prediction conditions: {simulation_requirement}

[Generated Analysis Report]
{report_content}

[Rules]
1. Prioritise answering based on the report content above
2. Answer directly; avoid lengthy deliberation
3. Only call tools for more data when the report content is insufficient
4. Answers should be concise, clear, and well-structured

[Available Tools] (use only when needed, maximum 1-2 calls)
{tools_description}

[Tool Call Format]
<tool_call>
{{"name": "tool_name", "parameters": {{"param_name": "param_value"}}}}
</tool_call>

[Response Style]
- Concise and direct, avoid lengthy essays
- Use > format to quote key content
- Lead with conclusions, then explain reasoning
- Write everything in English"""

CHAT_OBSERVATION_SUFFIX = "\n\nPlease answer the question concisely in English."


def _quant_tools_instruction_block() -> str:
    if not Config.ENABLE_REPORT_PAYLOAD_V1:
        return ""
    return """\
[Quantitative tools — simulation-derived statistics]
- analyze_metrics: activity counts, engagement, escalation curve
- assess_positions: stance distribution, polarization, consensus
- estimate_risks: outcome probability ranges + risk matrix
- stakeholder_matrix: per–stakeholder-type impact table (intensity, activity index, escalation exposure)

These numbers describe the **simulation rehearsal**, not real-world market odds. Use them explicitly in prose.
"""


# ═══════════════════════════════════════════════════════════════
# ReportAgent Main Class
# ═══════════════════════════════════════════════════════════════


class ReportAgent:
    """
    Report Agent - Simulation Report Generation Agent

    Uses ReACT (Reasoning + Acting) pattern:
    1. Planning phase: Analyse simulation requirements, plan report outline structure
    2. Generation phase: Generate content section by section, each section can call tools multiple times
    3. Reflection phase: Check content completeness and accuracy
    """
    
    # Maximum tool calls per section
    MAX_TOOL_CALLS_PER_SECTION = 5
    
    # Maximum reflection rounds
    MAX_REFLECTION_ROUNDS = 3
    
    # Maximum tool calls per chat
    MAX_TOOL_CALLS_PER_CHAT = 2
    
    def __init__(
        self, 
        graph_id: str,
        simulation_id: str,
        simulation_requirement: str,
        llm_client: Optional[LLMClient] = None,
        zep_tools: Optional[ZepToolsService] = None,
        project_id: Optional[str] = None,
    ):
        """
        Initialize Report Agent
        
        Args:
            graph_id: Graph ID
            simulation_id: Simulation ID
            simulation_requirement: Simulation requirement description
            llm_client: LLM client (optional)
            zep_tools: Zep tools service (optional)
            project_id: Optional project ID for grounding bundle / payload
        """
        self.graph_id = graph_id
        self.simulation_id = simulation_id
        self.simulation_requirement = simulation_requirement
        self.project_id = project_id
        
        self.llm = llm_client or LLMClient()
        self.zep_tools = zep_tools or ZepToolsService()
        self.quant_service = QuantitativeAnalysisService(llm_client=self.llm)
        
        # Tool definitions
        self.tools = self._define_tools()
        
        # Logger (initialized in generate_report)
        self.report_logger: Optional[ReportLogger] = None
        # Console logger (initialized in generate_report)
        self.console_logger: Optional[ReportConsoleLogger] = None
        self._quant_tool_cache: Dict[str, str] = {}
        self._payload_dict: Optional[Dict[str, Any]] = None
        self._scenarios_list: List[Dict[str, Any]] = []
        self._staleness_warnings: List[Dict[str, Any]] = []
        self._claims_ledger: List[Dict[str, Any]] = []
        self._grounding_project = None
        
        logger.info(f"ReportAgent initialized: graph_id={graph_id}, simulation_id={simulation_id}")
    
    def _define_tools(self) -> Dict[str, Dict[str, Any]]:
        """Define available tools"""
        tools = {
            "insight_forge": {
                "name": "insight_forge",
                "description": TOOL_DESC_INSIGHT_FORGE,
                "parameters": {
                    "query": "The question or topic you want to deeply analyse",
                    "report_context": "Current report section context (optional, helps generate more precise sub-questions)"
                }
            },
            "panorama_search": {
                "name": "panorama_search",
                "description": TOOL_DESC_PANORAMA_SEARCH,
                "parameters": {
                    "query": "Search query, used for relevance ranking",
                    "include_expired": "Whether to include expired/historical content (default True)"
                }
            },
            "quick_search": {
                "name": "quick_search",
                "description": TOOL_DESC_QUICK_SEARCH,
                "parameters": {
                    "query": "Search query string",
                    "limit": "Number of results to return (optional, default 10)"
                }
            },
            "interview_agents": {
                "name": "interview_agents",
                "description": TOOL_DESC_INTERVIEW_AGENTS,
                "parameters": {
                    "interview_topic": "Interview topic or requirement description (e.g. 'understand students' views on dormitory formaldehyde incident')",
                    "max_agents": "Maximum number of agents to interview (optional, default 5, max 10)"
                }
            },
        }
        if Config.ENABLE_REPORT_PAYLOAD_V1:
            tools["analyze_metrics"] = {
                "name": "analyze_metrics",
                "description": "Simulation activity metrics and escalation trends (quantitative).",
                "parameters": {},
            }
            tools["assess_positions"] = {
                "name": "assess_positions",
                "description": "Stakeholder stance distribution and polarization (quantitative).",
                "parameters": {"topic": "Topic to assess (default: simulation requirement)"},
            }
            tools["estimate_risks"] = {
                "name": "estimate_risks",
                "description": "Outcome probability ranges and risk matrix (quantitative, simulation-derived).",
                "parameters": {"scenario": "Scenario text (default: simulation requirement)"},
            }
            tools["stakeholder_matrix"] = {
                "name": "stakeholder_matrix",
                "description": "Per–entity-type impact matrix: stance mix, intensity, activity index, escalation exposure.",
                "parameters": {"topic": "Topic for stance context (default: simulation requirement)"},
            }
        return tools

    def _valid_tool_names(self) -> set:
        names = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}
        if Config.ENABLE_REPORT_PAYLOAD_V1:
            names |= QUANT_TOOL_NAMES
        return names

    def _role_enforcement_message(self, role: str, used_tools: set) -> Optional[str]:
        """Return a nudge message if the section role requires a tool not yet called, else None."""
        if not Config.ENABLE_REPORT_PAYLOAD_V1:
            return None
        if role == "quant_snapshot" and not (used_tools & QUANT_TOOL_NAMES):
            return (
                "[Required] Call at least one quantitative tool "
                "(analyze_metrics, assess_positions, estimate_risks, or stakeholder_matrix) "
                "before finishing this section."
            )
        if role == "stakeholder_impacts" and "stakeholder_matrix" not in used_tools:
            return "[Required] You must call stakeholder_matrix before finishing this section."
        if role == "risks_actions" and "estimate_risks" not in used_tools:
            return "[Required] You must call estimate_risks before finishing this section."
        return None

    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any], report_context: str = "") -> str:
        """
        Execute a tool call
        
        Args:
            tool_name: Tool name
            parameters: Tool parameters
            report_context: Report context (used for InsightForge)
            
        Returns:
            Tool execution result (text format)
        """
        logger.info(f"Executing tool: {tool_name}, parameters: {parameters}")
        
        try:
            if tool_name in self._quant_tool_cache:
                return self._quant_tool_cache[tool_name]

            if tool_name == "analyze_metrics":
                result = self.quant_service.analyze_metrics(simulation_id=self.simulation_id)
                return result.to_text()

            if tool_name == "assess_positions":
                topic = parameters.get("topic") or self.simulation_requirement
                result = self.quant_service.assess_positions(
                    simulation_id=self.simulation_id,
                    topic=topic,
                    graph_id=self.graph_id,
                    zep_tools=self.zep_tools,
                )
                return result.to_text()

            if tool_name == "estimate_risks":
                scenario = parameters.get("scenario") or self.simulation_requirement
                result = self.quant_service.estimate_risks(
                    simulation_id=self.simulation_id,
                    scenario=scenario,
                    graph_id=self.graph_id,
                    zep_tools=self.zep_tools,
                )
                return result.to_text()

            if tool_name == "stakeholder_matrix":
                topic = parameters.get("topic") or self.simulation_requirement
                result = self.quant_service.stakeholder_impact_matrix(
                    simulation_id=self.simulation_id,
                    graph_id=self.graph_id,
                    topic=topic,
                    zep_tools=self.zep_tools,
                )
                return result.to_text()

            if tool_name == "insight_forge":
                query = parameters.get("query", "")
                ctx = parameters.get("report_context", "") or report_context
                result = self.zep_tools.insight_forge(
                    graph_id=self.graph_id,
                    query=query,
                    simulation_requirement=self.simulation_requirement,
                    report_context=ctx
                )
                return result.to_text()
            
            elif tool_name == "panorama_search":
                # Broad search - get full picture
                query = parameters.get("query", "")
                include_expired = parameters.get("include_expired", True)
                if isinstance(include_expired, str):
                    include_expired = include_expired.lower() in ['true', '1', 'yes']
                result = self.zep_tools.panorama_search(
                    graph_id=self.graph_id,
                    query=query,
                    include_expired=include_expired
                )
                return result.to_text()
            
            elif tool_name == "quick_search":
                # Simple search - quick retrieval
                query = parameters.get("query", "")
                limit = parameters.get("limit", 10)
                if isinstance(limit, str):
                    limit = int(limit)
                result = self.zep_tools.quick_search(
                    graph_id=self.graph_id,
                    query=query,
                    limit=limit
                )
                return result.to_text()
            
            elif tool_name == "interview_agents":
                # Deep interview - call real OASIS interview API to get simulation agent responses (dual platform)
                interview_topic = parameters.get("interview_topic", parameters.get("query", ""))
                max_agents = parameters.get("max_agents", 5)
                if isinstance(max_agents, str):
                    max_agents = int(max_agents)
                max_agents = min(max_agents, 10)
                result = self.zep_tools.interview_agents(
                    simulation_id=self.simulation_id,
                    interview_requirement=interview_topic,
                    simulation_requirement=self.simulation_requirement,
                    max_agents=max_agents
                )
                return result.to_text()
            
            # ========== Backward-compatible legacy tools (internally redirected to new tools) ==========
            
            elif tool_name == "search_graph":
                # Redirect to quick_search
                logger.info("search_graph redirected to quick_search")
                return self._execute_tool("quick_search", parameters, report_context)
            
            elif tool_name == "get_graph_statistics":
                result = self.zep_tools.get_graph_statistics(self.graph_id)
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_entity_summary":
                entity_name = parameters.get("entity_name", "")
                result = self.zep_tools.get_entity_summary(
                    graph_id=self.graph_id,
                    entity_name=entity_name
                )
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            elif tool_name == "get_simulation_context":
                # Redirect to insight_forge since it is more powerful
                logger.info("get_simulation_context redirected to insight_forge")
                query = parameters.get("query", self.simulation_requirement)
                return self._execute_tool("insight_forge", {"query": query}, report_context)
            
            elif tool_name == "get_entities_by_type":
                entity_type = parameters.get("entity_type", "")
                nodes = self.zep_tools.get_entities_by_type(
                    graph_id=self.graph_id,
                    entity_type=entity_type
                )
                result = [n.to_dict() for n in nodes]
                return json.dumps(result, ensure_ascii=False, indent=2)
            
            else:
                return f"Unknown tool: {tool_name}. Please use one of: insight_forge, panorama_search, quick_search"
                
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name}, error: {str(e)}")
            return f"Tool execution failed: {str(e)}"
    
    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """
        Parse tool calls from LLM response

        Supported formats (by priority):
        1. <tool_call>{"name": "tool_name", "parameters": {...}}</tool_call>
        2. Bare JSON (response body or single line is a tool call JSON)
        """
        tool_calls = []

        # Format 1: XML style (standard format)
        xml_pattern = r'<tool_call>\s*(\{.*?\})\s*</tool_call>'
        for match in re.finditer(xml_pattern, response, re.DOTALL):
            try:
                call_data = json.loads(match.group(1))
                tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        if tool_calls:
            return tool_calls

        # Format 2: Fallback - LLM directly outputs bare JSON (without <tool_call> tags)
        # Only attempted when format 1 doesn't match, to avoid false matches in body text
        stripped = response.strip()
        if stripped.startswith('{') and stripped.endswith('}'):
            try:
                call_data = json.loads(stripped)
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
                    return tool_calls
            except json.JSONDecodeError:
                pass

        # Response may contain thinking text + bare JSON, try to extract the last JSON object
        json_pattern = r'(\{"(?:name|tool)"\s*:.*?\})\s*$'
        match = re.search(json_pattern, stripped, re.DOTALL)
        if match:
            try:
                call_data = json.loads(match.group(1))
                if self._is_valid_tool_call(call_data):
                    tool_calls.append(call_data)
            except json.JSONDecodeError:
                pass

        return tool_calls

    def _is_valid_tool_call(self, data: dict) -> bool:
        """Validate whether the parsed JSON is a valid tool call"""
        # Supports both {"name": ..., "parameters": ...} and {"tool": ..., "params": ...} key names
        tool_name = data.get("name") or data.get("tool")
        if tool_name and tool_name in self._valid_tool_names():
            # Normalize key names to name / parameters
            if "tool" in data:
                data["name"] = data.pop("tool")
            if "params" in data and "parameters" not in data:
                data["parameters"] = data.pop("params")
            return True
        return False
    
    def _get_tools_description(self) -> str:
        """Generate tool description text"""
        desc_parts = ["Available tools:"]
        for name, tool in self.tools.items():
            params_desc = ", ".join([f"{k}: {v}" for k, v in tool["parameters"].items()])
            desc_parts.append(f"- {name}: {tool['description']}")
            if params_desc:
                desc_parts.append(f"  Parameters: {params_desc}")
        return "\n".join(desc_parts)

    def _default_outline_v1(self) -> ReportOutline:
        return ReportOutline(
            title="Predictive Analysis Report",
            summary="Simulation-derived forecast with quantitative stakeholders, scenarios, risk framing, and decision recommendation.",
            sections=[
                ReportSection(title="Grounding and assumptions", role="grounding_and_assumptions",
                              description="Sources, freshness, user vs simulated claims"),
                ReportSection(title="Quantitative snapshot", role="quant_snapshot",
                              description="Activity, escalation, engagement statistics"),
                ReportSection(title="Stakeholder impacts", role="stakeholder_impacts",
                              description="Who is affected and how strongly"),
                ReportSection(title="Scenario ladder", role="scenarios",
                              description="Base, upside, and stress paths"),
                ReportSection(title="Risks and actions", role="risks_actions",
                              description="Probability ranges, risk matrix, recommendations"),
                ReportSection(title="Decision recommendation", role="decision_recommendation",
                              description="Structured verdict with key drivers, sensitivity, and flip conditions"),
            ],
        )

    def _outline_from_llm_v1(self, response: Dict[str, Any]) -> ReportOutline:
        sections: List[ReportSection] = []
        for section_data in response.get("sections", []):
            sections.append(
                ReportSection(
                    title=section_data.get("title", "Section"),
                    content="",
                    role=(section_data.get("role") or "general").strip(),
                    description=section_data.get("description", "") or "",
                )
            )
        return ReportOutline(
            title=response.get("title", "Simulation Analysis Report"),
            summary=response.get("summary", ""),
            sections=sections,
        )

    def _validate_outline_roles(self, outline: ReportOutline) -> bool:
        roles = [s.role for s in outline.sections]
        if len(roles) != len(OUTLINE_REQUIRED_ROLES):
            return False
        return set(roles) == set(OUTLINE_REQUIRED_ROLES)
    
    def plan_outline(
        self, 
        progress_callback: Optional[Callable] = None
    ) -> ReportOutline:
        """
        Plan report outline
        
        Use LLM to analyse simulation requirements and plan the report structure
        
        Args:
            progress_callback: Progress callback function
            
        Returns:
            ReportOutline: Report outline
        """
        logger.info("Starting report outline planning...")
        
        if progress_callback:
            progress_callback("planning", 0, "Analysing simulation requirements...")
        
        context = self.zep_tools.get_simulation_context(
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement
        )
        
        if progress_callback:
            progress_callback("planning", 30, "Generating report outline...")
        
        user_prompt = PLAN_USER_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            total_nodes=context.get('graph_statistics', {}).get('total_nodes', 0),
            total_edges=context.get('graph_statistics', {}).get('total_edges', 0),
            entity_types=list(context.get('graph_statistics', {}).get('entity_types', {}).keys()),
            total_entities=context.get('total_entities', 0),
            related_facts_json=json.dumps(context.get('related_facts', [])[:10], ensure_ascii=False, indent=2),
        )

        if not Config.ENABLE_REPORT_PAYLOAD_V1:
            system_prompt = PLAN_SYSTEM_PROMPT
            try:
                response = self.llm.chat_json(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                )
                if progress_callback:
                    progress_callback("planning", 80, "Parsing outline structure...")
                sections = []
                for section_data in response.get("sections", []):
                    sections.append(
                        ReportSection(
                            title=section_data.get("title", ""),
                            content="",
                            role="general",
                            description=section_data.get("description", ""),
                        )
                    )
                outline = ReportOutline(
                    title=response.get("title", "Simulation Analysis Report"),
                    summary=response.get("summary", ""),
                    sections=sections,
                )
                if progress_callback:
                    progress_callback("planning", 100, "Outline planning complete")
                return outline
            except Exception as e:
                logger.error(f"Outline planning failed: {str(e)}")
                return ReportOutline(
                    title="Future Prediction Report",
                    summary="Future trends and risk analysis based on simulation predictions",
                    sections=[
                        ReportSection(title="Prediction Scenarios and Core Findings", role="general"),
                        ReportSection(title="Population Behaviour Prediction Analysis", role="general"),
                        ReportSection(title="Trend Outlook and Risk Alerts", role="general"),
                    ],
                )

        # Valued-output v1 outline (fixed roles)
        system_prompt = PLAN_SYSTEM_PROMPT_V1
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            response = self.llm.chat_json(messages=messages, temperature=0.25)
            outline = self._outline_from_llm_v1(response)
            if not self._validate_outline_roles(outline):
                logger.warning("Outline role validation failed, retrying with repair instruction...")
                messages.append({"role": "assistant", "content": json.dumps(response, ensure_ascii=False)})
                messages.append({
                    "role": "user",
                    "content": (
                        f"Your JSON is invalid: you must output exactly {len(OUTLINE_REQUIRED_ROLES)} sections with these roles "
                        f"(one each): {list(OUTLINE_REQUIRED_ROLES)}. Fix and return JSON only."
                    ),
                })
                response = self.llm.chat_json(messages=messages, temperature=0.2)
                outline = self._outline_from_llm_v1(response)
            if not self._validate_outline_roles(outline):
                logger.warning("Using default v1 outline after failed validation")
                outline = self._default_outline_v1()
            if progress_callback:
                progress_callback("planning", 100, "Outline planning complete")
            logger.info(f"Outline planning complete: {len(outline.sections)} sections (v1)")
            return outline
        except Exception as e:
            logger.error(f"Outline planning failed (v1): {str(e)}")
            return self._default_outline_v1()
    
    def _generate_section_react(
        self, 
        section: ReportSection,
        outline: ReportOutline,
        previous_sections: List[str],
        progress_callback: Optional[Callable] = None,
        section_index: int = 0,
        payload_preamble: str = "",
    ) -> str:
        """
        Generate a single section's content using ReACT pattern
        
        ReACT loop:
        1. Thought - Analyse what information is needed
        2. Action - Call tools to retrieve information
        3. Observation - Analyse tool return results
        4. Repeat until sufficient information or max iterations reached
        5. Final Answer - Generate section content
        
        Args:
            section: Section to generate
            outline: Complete outline
            previous_sections: Content of previous sections (for coherence)
            progress_callback: Progress callback
            section_index: Section index (for logging)
            
        Returns:
            Section content (Markdown format)
        """
        logger.info(f"ReACT generating section: {section.title}")
        
        # Log section start
        if self.report_logger:
            self.report_logger.log_section_start(section.title, section_index)
        
        system_prompt = SECTION_SYSTEM_PROMPT_TEMPLATE.format(
            report_title=outline.title,
            report_summary=outline.summary,
            simulation_requirement=self.simulation_requirement,
            section_title=section.title,
            section_role=section.role,
            payload_preamble=payload_preamble or "(No structured payload for this run.)",
            tools_description=self._get_tools_description(),
            quant_tools_block=_quant_tools_instruction_block(),
        )

        # Build user prompt - each completed section passes in max 4000 chars
        if previous_sections:
            previous_parts = []
            for sec in previous_sections:
                # Each section max 4000 chars
                truncated = sec[:4000] + "..." if len(sec) > 4000 else sec
                previous_parts.append(truncated)
            previous_content = "\n\n---\n\n".join(previous_parts)
        else:
            previous_content = "(This is the first section)"
        
        user_prompt = SECTION_USER_PROMPT_TEMPLATE.format(
            previous_content=previous_content,
            section_title=section.title,
        )
        if Config.ENABLE_REPORT_PAYLOAD_V1:
            pre = self._quant_tool_cache.get("analyze_metrics")
            if pre:
                user_prompt += (
                    "\n\n═══ PRE-LOADED SIMULATION METRICS (from analyze_metrics) ═══\n"
                    + pre[:12000]
                    + "\n═══════════════════════════════════════════════════════════════\n"
                    "You MUST incorporate these statistics into your section. "
                    "Call assess_positions or estimate_risks for additional quantitative data."
                )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # ReACT loop
        tool_calls_count = 0
        max_iterations = 8
        min_tool_calls = 3
        if Config.ENABLE_REPORT_PAYLOAD_V1:
            all_tools = set(self._valid_tool_names())
        else:
            all_tools = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}
        conflict_retries = 0  # Consecutive conflicts where tool call and Final Answer appear together
        used_tools = set()  # Track tool names already called

        # Report context, used for InsightForge sub-question generation
        report_context = f"Section title: {section.title}\nSimulation requirement: {self.simulation_requirement}"
        
        for iteration in range(max_iterations):
            if progress_callback:
                progress_callback(
                    "generating", 
                    int((iteration / max_iterations) * 100),
                    f"Deep retrieval and writing ({tool_calls_count}/{self.MAX_TOOL_CALLS_PER_SECTION})"
                )
            
            # Call LLM
            response = self.llm.chat(
                messages=messages,
                temperature=0.5,
                max_tokens=4096
            )

            # Check if LLM returned None (API error or empty content)
            if response is None:
                logger.warning(f"Section {section.title} iteration {iteration + 1}: LLM returned None")
                # If iterations remain, add message and retry
                if iteration < max_iterations - 1:
                    messages.append({"role": "assistant", "content": "(Response was empty)"})
                    messages.append({"role": "user", "content": "Please continue generating content."})
                    continue
                # Last iteration also returned None, break out to forced conclusion
                break

            logger.debug(f"LLM response: {response[:200]}...")

            # Parse once, reuse results
            tool_calls = self._parse_tool_calls(response)
            has_tool_calls = bool(tool_calls)
            has_final_answer = "Final Answer:" in response

            # ── Conflict handling: LLM output both tool call and Final Answer ──
            if has_tool_calls and has_final_answer:
                conflict_retries += 1
                logger.warning(
                    f"Section {section.title} round {iteration+1}: "
                    f"LLM output both tool call and Final Answer (conflict #{conflict_retries})"
                )

                if conflict_retries <= 2:
                    # First two times: discard this response, ask LLM to re-respond
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": (
                            "[Format Error] You included both a tool call and Final Answer in one response, which is not allowed.\n"
                            "Each response can only do one of the following:\n"
                            "- Call a tool (output a <tool_call> block, do not write Final Answer)\n"
                            "- Output final content (start with 'Final Answer:', do not include <tool_call>)\n"
                            "Please re-respond, doing only one of these."
                        ),
                    })
                    continue
                else:
                    # Third time: degrade, truncate to first tool call, force execution
                    logger.warning(
                        f"Section {section.title}: {conflict_retries} consecutive conflicts, "
                        "degrading to truncated execution of first tool call"
                    )
                    first_tool_end = response.find('</tool_call>')
                    if first_tool_end != -1:
                        response = response[:first_tool_end + len('</tool_call>')]
                        tool_calls = self._parse_tool_calls(response)
                        has_tool_calls = bool(tool_calls)
                    has_final_answer = False
                    conflict_retries = 0

            # Log LLM response
            if self.report_logger:
                self.report_logger.log_llm_response(
                    section_title=section.title,
                    section_index=section_index,
                    response=response,
                    iteration=iteration + 1,
                    has_tool_calls=has_tool_calls,
                    has_final_answer=has_final_answer
                )

            # ── Case 1: LLM output Final Answer ──
            if has_final_answer:
                # Insufficient tool calls, reject and request more tool usage
                if tool_calls_count < min_tool_calls:
                    messages.append({"role": "assistant", "content": response})
                    unused_tools = all_tools - used_tools
                    unused_hint = f"(These tools have not been used yet, consider trying them: {', '.join(unused_tools)})" if unused_tools else ""
                    messages.append({
                        "role": "user",
                        "content": REACT_INSUFFICIENT_TOOLS_MSG.format(
                            tool_calls_count=tool_calls_count,
                            min_tool_calls=min_tool_calls,
                            unused_hint=unused_hint,
                        ),
                    })
                    continue

                role_nudge = self._role_enforcement_message(section.role, used_tools)
                if role_nudge:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": role_nudge})
                    continue

                if (Config.ENABLE_REPORT_PAYLOAD_V1
                        and not (used_tools & QUANT_TOOL_NAMES)
                        and tool_calls_count < self.MAX_TOOL_CALLS_PER_SECTION):
                    logger.info(f"Section {section.title}: rejecting Final Answer — no quantitative tool used (used: {used_tools})")
                    messages.append({"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": REACT_MISSING_QUANT_MSG})
                    continue

                # Normal completion
                final_answer = response.split("Final Answer:")[-1].strip()
                logger.info(f"Section {section.title} generation complete (tool calls: {tool_calls_count})")

                if self.report_logger:
                    self.report_logger.log_section_content(
                        section_title=section.title,
                        section_index=section_index,
                        content=final_answer,
                        tool_calls_count=tool_calls_count
                    )
                return final_answer

            # ── Case 2: LLM attempted tool call ──
            if has_tool_calls:
                # Tool quota exhausted → explicitly notify, request Final Answer
                if tool_calls_count >= self.MAX_TOOL_CALLS_PER_SECTION:
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": REACT_TOOL_LIMIT_MSG.format(
                            tool_calls_count=tool_calls_count,
                            max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        ),
                    })
                    continue

                # Only execute the first tool call
                call = tool_calls[0]
                if len(tool_calls) > 1:
                    logger.info(f"LLM attempted {len(tool_calls)} tool calls, only executing first: {call['name']}")

                if self.report_logger:
                    self.report_logger.log_tool_call(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        parameters=call.get("parameters", {}),
                        iteration=iteration + 1
                    )

                result = self._execute_tool(
                    call["name"],
                    call.get("parameters", {}),
                    report_context=report_context
                )

                if self.report_logger:
                    self.report_logger.log_tool_result(
                        section_title=section.title,
                        section_index=section_index,
                        tool_name=call["name"],
                        result=result,
                        iteration=iteration + 1
                    )

                tool_calls_count += 1
                used_tools.add(call['name'])

                # Build unused tools hint
                unused_tools = all_tools - used_tools
                unused_hint = ""
                if unused_tools and tool_calls_count < self.MAX_TOOL_CALLS_PER_SECTION:
                    unused_hint = REACT_UNUSED_TOOLS_HINT.format(unused_list=", ".join(unused_tools))

                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": REACT_OBSERVATION_TEMPLATE.format(
                        tool_name=call["name"],
                        result=result,
                        tool_calls_count=tool_calls_count,
                        max_tool_calls=self.MAX_TOOL_CALLS_PER_SECTION,
                        used_tools_str=", ".join(used_tools),
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # ── Case 3: Neither tool call nor Final Answer ──
            messages.append({"role": "assistant", "content": response})

            if tool_calls_count < min_tool_calls:
                # Insufficient tool calls, recommend unused tools
                unused_tools = all_tools - used_tools
                unused_hint = f"(These tools have not been used yet, consider trying them: {', '.join(unused_tools)})" if unused_tools else ""

                messages.append({
                    "role": "user",
                    "content": REACT_INSUFFICIENT_TOOLS_MSG_ALT.format(
                        tool_calls_count=tool_calls_count,
                        min_tool_calls=min_tool_calls,
                        unused_hint=unused_hint,
                    ),
                })
                continue

            # Sufficient tool calls, LLM output content without "Final Answer:" prefix
            role_nudge = self._role_enforcement_message(section.role, used_tools)
            if role_nudge:
                messages.append({"role": "user", "content": role_nudge})
                continue

            if (Config.ENABLE_REPORT_PAYLOAD_V1
                    and not (used_tools & QUANT_TOOL_NAMES)
                    and tool_calls_count < self.MAX_TOOL_CALLS_PER_SECTION):
                logger.info(f"Section {section.title}: rejecting implicit final — no quantitative tool used (used: {used_tools})")
                messages.append({"role": "user", "content": REACT_MISSING_QUANT_MSG})
                continue

            logger.info(f"Section {section.title} no 'Final Answer:' prefix detected, adopting LLM output as final content (tool calls: {tool_calls_count})")
            final_answer = response.strip()

            if self.report_logger:
                self.report_logger.log_section_content(
                    section_title=section.title,
                    section_index=section_index,
                    content=final_answer,
                    tool_calls_count=tool_calls_count
                )
            return final_answer
        
        # Reached max iterations, force content generation
        logger.warning(f"Section {section.title} reached max iterations, forcing generation")
        messages.append({"role": "user", "content": REACT_FORCE_FINAL_MSG})
        
        response = self.llm.chat(
            messages=messages,
            temperature=0.5,
            max_tokens=4096
        )

        # Check if LLM returned None during forced conclusion
        if response is None:
            logger.error(f"Section {section.title} LLM returned None during forced conclusion, using default error message")
            final_answer = f"(This section failed to generate: LLM returned empty response, please retry later)"
        elif "Final Answer:" in response:
            final_answer = response.split("Final Answer:")[-1].strip()
        else:
            final_answer = response
        
        # Log section content generation complete
        if self.report_logger:
            self.report_logger.log_section_content(
                section_title=section.title,
                section_index=section_index,
                content=final_answer,
                tool_calls_count=tool_calls_count
            )
        
        return final_answer
    
    def generate_report(
        self, 
        progress_callback: Optional[Callable[[str, int, str], None]] = None,
        report_id: Optional[str] = None
    ) -> Report:
        """
        Generate complete report (real-time section-by-section output)
        
        Each section is saved to the folder immediately after generation, no need to wait for the entire report.
        File structure:
        reports/{report_id}/
            meta.json       - Report metadata
            outline.json    - Report outline
            progress.json   - Generation progress
            section_01.md   - Section 1
            section_02.md   - Section 2
            ...
            full_report.md  - Complete report
        
        Args:
            progress_callback: Progress callback function (stage, progress, message)
            report_id: Report ID (optional, auto-generated if not provided)
            
        Returns:
            Report: Complete report
        """
        import uuid
        
        # Auto-generate report_id if not provided
        if not report_id:
            report_id = f"report_{uuid.uuid4().hex[:12]}"
        start_time = datetime.now()
        
        report = Report(
            report_id=report_id,
            simulation_id=self.simulation_id,
            graph_id=self.graph_id,
            simulation_requirement=self.simulation_requirement,
            status=ReportStatus.PENDING,
            created_at=datetime.now().isoformat()
        )
        
        # Completed section titles list (for progress tracking)
        completed_section_titles = []
        
        try:
            # Initialize: create report folder and save initial state
            ReportManager._ensure_report_folder(report_id)
            
            # Initialize logger (structured log agent_log.jsonl)
            self.report_logger = ReportLogger(report_id)
            self.report_logger.log_start(
                simulation_id=self.simulation_id,
                graph_id=self.graph_id,
                simulation_requirement=self.simulation_requirement
            )
            
            # Initialize console logger (console_log.txt)
            self.console_logger = ReportConsoleLogger(report_id)
            
            ReportManager.update_progress(
                report_id, "pending", 0, "Initializing report...",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            # Phase 1: Plan outline
            report.status = ReportStatus.PLANNING
            ReportManager.update_progress(
                report_id, "planning", 5, "Starting report outline planning...",
                completed_sections=[]
            )
            
            # Log planning start
            self.report_logger.log_planning_start()
            
            if progress_callback:
                progress_callback("planning", 0, "Starting report outline planning...")
            
            outline = self.plan_outline(
                progress_callback=lambda stage, prog, msg: 
                    progress_callback(stage, prog // 5, msg) if progress_callback else None
            )
            report.outline = outline
            
            # Log planning complete
            self.report_logger.log_planning_complete(outline.to_dict())
            
            # Save outline to file
            ReportManager.save_outline(report_id, outline)
            ReportManager.update_progress(
                report_id, "planning", 15, f"Outline planning complete, {len(outline.sections)} sections",
                completed_sections=[]
            )
            ReportManager.save_report(report)
            
            logger.info(f"Outline saved to file: {report_id}/outline.json")

            payload_preamble = ""
            self._decision_payload = None
            if Config.ENABLE_REPORT_PAYLOAD_V1:
                from ..models.project import ProjectManager as PM
                project = PM.get_project(self.project_id) if self.project_id else None
                self._grounding_project = project

                # Safety net: ingest dossier sources if available
                if project and getattr(project, 'research_dossier_path', None):
                    import os as _os
                    if _os.path.isfile(project.research_dossier_path):
                        try:
                            import json as _json
                            with open(project.research_dossier_path, 'r', encoding='utf-8') as _f:
                                _dossier = _json.load(_f)
                            ingest_dossier_sources(project, _dossier)
                        except Exception:
                            logger.debug("Could not ingest dossier sources in generate_report")

                if Config.ENABLE_GROUNDING_FEATURES and project:
                    self._staleness_warnings, block = evaluate_grounding_staleness(project)
                    if block:
                        raise RuntimeError(
                            "Grounding policy: document sources exceed configured max age. "
                            "Re-upload documents or adjust GROUNDING_MAX_AGE_HOURS / GROUNDING_BLOCK_IF_STALE."
                        )
                else:
                    self._staleness_warnings = []
                self._claims_ledger = build_claim_ledger_from_project(project) if project else []

                pre_m = self.quant_service.analyze_metrics(self.simulation_id)
                pos = self.quant_service.assess_positions(
                    self.simulation_id,
                    self.simulation_requirement,
                    self.graph_id,
                    self.zep_tools,
                )
                risks = self.quant_service.estimate_risks(
                    self.simulation_id,
                    self.simulation_requirement,
                    self.graph_id,
                    self.zep_tools,
                    cached_stance=pos.stance,
                    cached_consensus=pos.consensus,
                )
                matrix = self.quant_service.stakeholder_impact_matrix(
                    self.simulation_id,
                    self.graph_id,
                    self.simulation_requirement,
                    self.zep_tools,
                    cached_stance=pos.stance,
                )
                quant_excerpt = pre_m.to_text() + "\n\n" + pos.to_text()
                risk_excerpt = risks.to_text()
                self._scenarios_list = generate_scenario_ladder_json(
                    self.llm, self.simulation_requirement, quant_excerpt, risk_excerpt
                )
                self._quant_tool_cache = {
                    "analyze_metrics": pre_m.to_text(),
                    "assess_positions": pos.to_text(),
                    "estimate_risks": risks.to_text(),
                    "stakeholder_matrix": matrix.to_text(),
                }

                # Decision framework (gated by feature flag)
                decision_payload = None
                if Config.ENABLE_DECISION_LAYER:
                    decision_intake = getattr(project, 'decision_intake', None) if project else None
                    framework = self.quant_service.generate_decision_framework(
                        scenario=self.simulation_requirement,
                        metrics=pre_m,
                        positions=pos,
                        risks=risks,
                        stakeholder_matrix=matrix,
                        decision_intake=decision_intake,
                    )
                    decision_payload = framework.to_dict()
                    logger.info(f"Decision framework generated: verdict={framework.verdict}")
                self._decision_payload = decision_payload

                self._payload_dict = build_report_payload_v1(
                    simulation_requirement=self.simulation_requirement,
                    simulation_id=self.simulation_id,
                    graph_id=self.graph_id,
                    project=project,
                    metrics_payload=pre_m.to_dict(),
                    positions_payload=pos.to_dict(),
                    risks_payload=risks.to_dict(),
                    stakeholder_matrix_payload=matrix.to_dict(),
                    scenarios=self._scenarios_list,
                    staleness_warnings=self._staleness_warnings,
                    claims=self._claims_ledger,
                    decision_payload=decision_payload,
                )
                ReportManager.save_payload_v1(report_id, self._payload_dict)
                payload_preamble = payload_preamble_for_prompt(self._payload_dict)
                logger.info(f"Report payload v1 saved for {report_id}")
            else:
                self._quant_tool_cache = {}
                self._payload_dict = None
                self._scenarios_list = []
                self._staleness_warnings = []
                self._claims_ledger = []
                self._grounding_project = None
            
            # Phase 2: Generate section by section (save each section)
            report.status = ReportStatus.GENERATING
            
            total_sections = len(outline.sections)
            generated_sections = []  # Save content for context
            
            for i, section in enumerate(outline.sections):
                section_num = i + 1
                base_progress = 20 + int((i / total_sections) * 70)
                
                # Update progress
                ReportManager.update_progress(
                    report_id, "generating", base_progress,
                    f"Generating section: {section.title} ({section_num}/{total_sections})",
                    current_section=section.title,
                    completed_sections=completed_section_titles
                )
                
                if progress_callback:
                    progress_callback(
                        "generating", 
                        base_progress, 
                        f"Generating section: {section.title} ({section_num}/{total_sections})"
                    )
                
                if Config.ENABLE_REPORT_PAYLOAD_V1 and section.role == "grounding_and_assumptions":
                    section_content = render_grounding_markdown(
                        self._grounding_project,
                        self._staleness_warnings,
                        self._claims_ledger,
                    )
                elif Config.ENABLE_REPORT_PAYLOAD_V1 and section.role == "scenarios":
                    section_content = render_scenarios_markdown(self._scenarios_list)
                elif Config.ENABLE_REPORT_PAYLOAD_V1 and section.role == "decision_recommendation":
                    section_content = render_decision_markdown(self._decision_payload)
                else:
                    section_content = self._generate_section_react(
                        section=section,
                        outline=outline,
                        previous_sections=generated_sections,
                        progress_callback=lambda stage, prog, msg:
                            progress_callback(
                                stage, 
                                base_progress + int(prog * 0.7 / total_sections),
                                msg
                            ) if progress_callback else None,
                        section_index=section_num,
                        payload_preamble=payload_preamble,
                    )
                
                section.content = section_content
                generated_sections.append(f"## {section.title}\n\n{section_content}")

                # Save section
                ReportManager.save_section(report_id, section_num, section)
                completed_section_titles.append(section.title)

                # Log section complete
                full_section_content = f"## {section.title}\n\n{section_content}"

                if self.report_logger:
                    self.report_logger.log_section_full_complete(
                        section_title=section.title,
                        section_index=section_num,
                        full_content=full_section_content.strip()
                    )

                logger.info(f"Section saved: {report_id}/section_{section_num:02d}.md")
                
                # Update progress
                ReportManager.update_progress(
                    report_id, "generating", 
                    base_progress + int(70 / total_sections),
                    f"Section {section.title} completed",
                    current_section=None,
                    completed_sections=completed_section_titles
                )
            
            # Phase 3: Assemble complete report
            if progress_callback:
                progress_callback("generating", 95, "Assembling complete report...")
            
            ReportManager.update_progress(
                report_id, "generating", 95, "Assembling complete report...",
                completed_sections=completed_section_titles
            )
            
            # Use ReportManager to assemble complete report
            report.markdown_content = ReportManager.assemble_full_report(report_id, outline)
            report.status = ReportStatus.COMPLETED
            report.completed_at = datetime.now().isoformat()
            
            # Calculate total elapsed time
            total_time_seconds = (datetime.now() - start_time).total_seconds()
            
            # Log report complete
            if self.report_logger:
                self.report_logger.log_report_complete(
                    total_sections=total_sections,
                    total_time_seconds=total_time_seconds
                )
            
            # Save final report
            ReportManager.save_report(report)
            ReportManager.update_progress(
                report_id, "completed", 100, "Report generation complete",
                completed_sections=completed_section_titles
            )
            
            if progress_callback:
                progress_callback("completed", 100, "Report generation complete")
            
            logger.info(f"Report generation complete: {report_id}")
            
            # Close console logger
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
            
        except Exception as e:
            logger.error(f"Report generation failed: {str(e)}")
            report.status = ReportStatus.FAILED
            report.error = str(e)
            
            # Log error
            if self.report_logger:
                self.report_logger.log_error(str(e), "failed")
            
            # Save failed state
            try:
                ReportManager.save_report(report)
                ReportManager.update_progress(
                    report_id, "failed", -1, f"Report generation failed: {str(e)}",
                    completed_sections=completed_section_titles
                )
            except Exception:
                pass  # Ignore errors from failed save
            
            # Close console logger
            if self.console_logger:
                self.console_logger.close()
                self.console_logger = None
            
            return report
    
    def chat(
        self, 
        message: str,
        chat_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Chat with Report Agent
        
        During conversation, the Agent can autonomously invoke retrieval tools to answer questions
        
        Args:
            message: User message
            chat_history: Chat history
            
        Returns:
            {
                "response": "Agent reply",
                "tool_calls": [list of tools called],
                "sources": [information sources]
            }
        """
        logger.info(f"Report Agent chat: {message[:50]}...")
        
        chat_history = chat_history or []
        
        # Get generated report content
        report_content = ""
        try:
            report = ReportManager.get_report_by_simulation(self.simulation_id)
            if report and report.markdown_content:
                # Limit report length to avoid excessive context
                report_content = report.markdown_content[:15000]
                if len(report.markdown_content) > 15000:
                    report_content += "\n\n... [Report content truncated] ..."
        except Exception as e:
            logger.warning(f"Failed to get report content: {e}")
        
        system_prompt = CHAT_SYSTEM_PROMPT_TEMPLATE.format(
            simulation_requirement=self.simulation_requirement,
            report_content=report_content if report_content else "(No report available yet)",
            tools_description=self._get_tools_description(),
        )

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add chat history
        for h in chat_history[-10:]:  # Limit history length
            messages.append(h)
        
        # Add user message
        messages.append({
            "role": "user", 
            "content": message
        })
        
        # ReACT loop (simplified)
        tool_calls_made = []
        max_iterations = 2  # Reduced iteration rounds
        
        for iteration in range(max_iterations):
            response = self.llm.chat(
                messages=messages,
                temperature=0.5
            )
            
            # Parse tool calls
            tool_calls = self._parse_tool_calls(response)
            
            if not tool_calls:
                # No tool calls, return response directly
                clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', response, flags=re.DOTALL)
                clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
                
                return {
                    "response": clean_response.strip(),
                    "tool_calls": tool_calls_made,
                    "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
                }
            
            # Execute tool calls (limited quantity)
            tool_results = []
            for call in tool_calls[:1]:  # Max 1 tool call per round
                if len(tool_calls_made) >= self.MAX_TOOL_CALLS_PER_CHAT:
                    break
                result = self._execute_tool(call["name"], call.get("parameters", {}))
                tool_results.append({
                    "tool": call["name"],
                    "result": result[:1500]  # Limit result length
                })
                tool_calls_made.append(call)
            
            # Add results to messages
            messages.append({"role": "assistant", "content": response})
            observation = "\n".join([f"[{r['tool']} result]\n{r['result']}" for r in tool_results])
            messages.append({
                "role": "user",
                "content": observation + CHAT_OBSERVATION_SUFFIX
            })
        
        # Reached max iterations, get final response
        final_response = self.llm.chat(
            messages=messages,
            temperature=0.5
        )
        
        # Clean response
        clean_response = re.sub(r'<tool_call>.*?</tool_call>', '', final_response, flags=re.DOTALL)
        clean_response = re.sub(r'\[TOOL_CALL\].*?\)', '', clean_response)
        
        return {
            "response": clean_response.strip(),
            "tool_calls": tool_calls_made,
            "sources": [tc.get("parameters", {}).get("query", "") for tc in tool_calls_made]
        }


class ReportManager:
    """
    Report Manager
    
    Responsible for report persistence and retrieval
    
    File structure (section-by-section output):
    reports/
      {report_id}/
        meta.json          - Report metadata and status
        outline.json       - Report outline
        progress.json      - Generation progress
        section_01.md      - Section 1
        section_02.md      - Section 2
        ...
        full_report.md     - Complete report
    """
    
    # Report storage directory
    REPORTS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'reports')
    
    @classmethod
    def _ensure_reports_dir(cls):
        """Ensure reports root directory exists"""
        os.makedirs(cls.REPORTS_DIR, exist_ok=True)
    
    @classmethod
    def _get_report_folder(cls, report_id: str) -> str:
        """Get report folder path"""
        return os.path.join(cls.REPORTS_DIR, report_id)
    
    @classmethod
    def _ensure_report_folder(cls, report_id: str) -> str:
        """Ensure report folder exists and return path"""
        folder = cls._get_report_folder(report_id)
        os.makedirs(folder, exist_ok=True)
        return folder
    
    @classmethod
    def _get_report_path(cls, report_id: str) -> str:
        """Get report metadata file path"""
        return os.path.join(cls._get_report_folder(report_id), "meta.json")
    
    @classmethod
    def _get_report_markdown_path(cls, report_id: str) -> str:
        """Get complete report Markdown file path"""
        return os.path.join(cls._get_report_folder(report_id), "full_report.md")
    
    @classmethod
    def _get_outline_path(cls, report_id: str) -> str:
        """Get outline file path"""
        return os.path.join(cls._get_report_folder(report_id), "outline.json")

    @classmethod
    def _get_payload_v1_path(cls, report_id: str) -> str:
        return os.path.join(cls._get_report_folder(report_id), "payload.v1.json")

    @classmethod
    def save_payload_v1(cls, report_id: str, payload: Dict[str, Any]) -> None:
        cls._ensure_report_folder(report_id)
        path = cls._get_payload_v1_path(report_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.info(f"Payload v1 saved: {report_id}")

    @classmethod
    def load_payload_v1(cls, report_id: str) -> Optional[Dict[str, Any]]:
        path = cls._get_payload_v1_path(report_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    @classmethod
    def _get_progress_path(cls, report_id: str) -> str:
        """Get progress file path"""
        return os.path.join(cls._get_report_folder(report_id), "progress.json")
    
    @classmethod
    def _get_section_path(cls, report_id: str, section_index: int) -> str:
        """Get section Markdown file path"""
        return os.path.join(cls._get_report_folder(report_id), f"section_{section_index:02d}.md")
    
    @classmethod
    def _get_agent_log_path(cls, report_id: str) -> str:
        """Get Agent log file path"""
        return os.path.join(cls._get_report_folder(report_id), "agent_log.jsonl")
    
    @classmethod
    def _get_console_log_path(cls, report_id: str) -> str:
        """Get console log file path"""
        return os.path.join(cls._get_report_folder(report_id), "console_log.txt")
    
    @classmethod
    def get_console_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Get console log content
        
        These are console output logs (INFO, WARNING, etc.) during report generation,
        different from the structured logs in agent_log.jsonl.
        
        Args:
            report_id: Report ID
            from_line: Line number to start reading from (for incremental fetch, 0 means from start)
            
        Returns:
            {
                "logs": [list of log lines],
                "total_lines": total line count,
                "from_line": starting line number,
                "has_more": whether more logs are available
            }
        """
        log_path = cls._get_console_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    # Keep original log line, strip trailing newline
                    logs.append(line.rstrip('\n\r'))
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Read to end
        }
    
    @classmethod
    def get_console_log_stream(cls, report_id: str) -> List[str]:
        """
        Get complete console log (fetch all at once)
        
        Args:
            report_id: Report ID
            
        Returns:
            List of log lines
        """
        result = cls.get_console_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def get_agent_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        """
        Get Agent log content
        
        Args:
            report_id: Report ID
            from_line: Line number to start reading from (for incremental fetch, 0 means from start)
            
        Returns:
            {
                "logs": [list of log entries],
                "total_lines": total line count,
                "from_line": starting line number,
                "has_more": whether more logs are available
            }
        """
        log_path = cls._get_agent_log_path(report_id)
        
        if not os.path.exists(log_path):
            return {
                "logs": [],
                "total_lines": 0,
                "from_line": 0,
                "has_more": False
            }
        
        logs = []
        total_lines = 0
        
        with open(log_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                total_lines = i + 1
                if i >= from_line:
                    try:
                        log_entry = json.loads(line.strip())
                        logs.append(log_entry)
                    except json.JSONDecodeError:
                        # Skip lines that fail to parse
                        continue
        
        return {
            "logs": logs,
            "total_lines": total_lines,
            "from_line": from_line,
            "has_more": False  # Read to end
        }
    
    @classmethod
    def get_agent_log_stream(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Get complete Agent log (fetch all at once)
        
        Args:
            report_id: Report ID
            
        Returns:
            List of log entries
        """
        result = cls.get_agent_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def save_outline(cls, report_id: str, outline: ReportOutline) -> None:
        """
        Save report outline
        
        Called immediately after planning phase completes
        """
        cls._ensure_report_folder(report_id)
        
        with open(cls._get_outline_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(outline.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(f"Outline saved: {report_id}")
    
    @classmethod
    def save_section(
        cls,
        report_id: str,
        section_index: int,
        section: ReportSection
    ) -> str:
        """
        Save a single section

        Called immediately after each section is generated, enabling section-by-section output

        Args:
            report_id: Report ID
            section_index: Section index (starting from 1)
            section: Section object

        Returns:
            Saved file path
        """
        cls._ensure_report_folder(report_id)

        # Build section Markdown content - clean up possible duplicate titles
        cleaned_content = cls._clean_section_content(section.content, section.title)
        md_content = f"## {section.title}\n\n"
        if cleaned_content:
            md_content += f"{cleaned_content}\n\n"

        # Save file
        file_suffix = f"section_{section_index:02d}.md"
        file_path = os.path.join(cls._get_report_folder(report_id), file_suffix)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        logger.info(f"Section saved: {report_id}/{file_suffix}")
        return file_path
    
    @classmethod
    def _clean_section_content(cls, content: str, section_title: str) -> str:
        """
        Clean section content
        
        1. Remove Markdown heading lines at the start that duplicate the section title
        2. Convert all ### and lower level headings to bold text
        
        Args:
            content: Original content
            section_title: Section title
            
        Returns:
            Cleaned content
        """
        import re
        
        if not content:
            return content
        
        content = content.strip()
        lines = content.split('\n')
        cleaned_lines = []
        skip_next_empty = False
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Check if this is a Markdown heading line
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title_text = heading_match.group(2).strip()
                
                # Check if this heading duplicates the section title (skip duplicates within first 5 lines)
                if i < 5:
                    if title_text == section_title or title_text.replace(' ', '') == section_title.replace(' ', ''):
                        skip_next_empty = True
                        continue
                
                # Convert all heading levels (#, ##, ###, ####, etc.) to bold
                # Since section titles are added by the system, content should not have any headings
                cleaned_lines.append(f"**{title_text}**")
                cleaned_lines.append("")  # Add empty line
                continue
            
            # If previous line was a skipped heading and current line is empty, skip it too
            if skip_next_empty and stripped == '':
                skip_next_empty = False
                continue
            
            skip_next_empty = False
            cleaned_lines.append(line)
        
        # Remove leading empty lines
        while cleaned_lines and cleaned_lines[0].strip() == '':
            cleaned_lines.pop(0)
        
        # Remove leading separators
        while cleaned_lines and cleaned_lines[0].strip() in ['---', '***', '___']:
            cleaned_lines.pop(0)
            # Also remove empty lines after separator
            while cleaned_lines and cleaned_lines[0].strip() == '':
                cleaned_lines.pop(0)
        
        return '\n'.join(cleaned_lines)
    
    @classmethod
    def update_progress(
        cls, 
        report_id: str, 
        status: str, 
        progress: int, 
        message: str,
        current_section: str = None,
        completed_sections: List[str] = None
    ) -> None:
        """
        Update report generation progress
        
        Frontend can read progress.json to get real-time progress
        """
        cls._ensure_report_folder(report_id)
        
        progress_data = {
            "status": status,
            "progress": progress,
            "message": message,
            "current_section": current_section,
            "completed_sections": completed_sections or [],
            "updated_at": datetime.now().isoformat()
        }
        
        with open(cls._get_progress_path(report_id), 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def get_progress(cls, report_id: str) -> Optional[Dict[str, Any]]:
        """Get report generation progress"""
        path = cls._get_progress_path(report_id)
        
        if not os.path.exists(path):
            return None
        
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @classmethod
    def get_generated_sections(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Get list of generated sections
        
        Returns information for all saved section files
        """
        folder = cls._get_report_folder(report_id)
        
        if not os.path.exists(folder):
            return []
        
        sections = []
        for filename in sorted(os.listdir(folder)):
            if filename.startswith('section_') and filename.endswith('.md'):
                file_path = os.path.join(folder, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Parse section index from filename
                parts = filename.replace('.md', '').split('_')
                section_index = int(parts[1])

                sections.append({
                    "filename": filename,
                    "section_index": section_index,
                    "content": content
                })

        return sections
    
    @classmethod
    def assemble_full_report(cls, report_id: str, outline: ReportOutline) -> str:
        """
        Assemble complete report
        
        Assemble the complete report from saved section files and clean up headings
        """
        folder = cls._get_report_folder(report_id)
        
        # Build report header
        md_content = ""
        if Config.ENABLE_REPORT_PAYLOAD_V1:
            md_content += REPORT_DISCLAIMER_MD + "\n"
        md_content += f"# {outline.title}\n\n"
        md_content += f"> {outline.summary}\n\n"
        md_content += f"---\n\n"
        
        # Read all section files in order
        sections = cls.get_generated_sections(report_id)
        for section_info in sections:
            md_content += section_info["content"]
        
        # Post-process: clean up heading issues in the entire report
        md_content = cls._post_process_report(md_content, outline)
        
        # Save complete report
        full_path = cls._get_report_markdown_path(report_id)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        logger.info(f"Complete report assembled: {report_id}")
        return md_content
    
    @classmethod
    def _post_process_report(cls, content: str, outline: ReportOutline) -> str:
        """
        Post-process report content
        
        1. Remove duplicate headings
        2. Keep report main title (#) and section titles (##), remove other heading levels (###, ####, etc.)
        3. Clean up excess empty lines and separators
        
        Args:
            content: Original report content
            outline: Report outline
            
        Returns:
            Processed content
        """
        import re
        
        lines = content.split('\n')
        processed_lines = []
        prev_was_heading = False
        
        # Collect all section titles from the outline
        section_titles = set()
        for section in outline.sections:
            section_titles.add(section.title)
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Check if this is a heading line
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                
                # Check for duplicate headings (same heading content within 5 consecutive lines)
                is_duplicate = False
                for j in range(max(0, len(processed_lines) - 5), len(processed_lines)):
                    prev_line = processed_lines[j].strip()
                    prev_match = re.match(r'^(#{1,6})\s+(.+)$', prev_line)
                    if prev_match:
                        prev_title = prev_match.group(2).strip()
                        if prev_title == title:
                            is_duplicate = True
                            break
                
                if is_duplicate:
                    # Skip duplicate heading and following empty lines
                    i += 1
                    while i < len(lines) and lines[i].strip() == '':
                        i += 1
                    continue
                
                # Heading level handling:
                # - # (level=1) keep only report main title
                # - ## (level=2) keep section titles
                # - ### and below (level>=3) convert to bold text
                
                if level == 1:
                    if title == outline.title:
                        # Keep report main title
                        processed_lines.append(line)
                        prev_was_heading = True
                    elif title in section_titles:
                        # Section title incorrectly used #, fix to ##
                        processed_lines.append(f"## {title}")
                        prev_was_heading = True
                    else:
                        # Other level-1 headings converted to bold
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                elif level == 2:
                    if title in section_titles or title == outline.title:
                        # Keep section title
                        processed_lines.append(line)
                        prev_was_heading = True
                    else:
                        # Non-section level-2 headings converted to bold
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                else:
                    # ### and below level headings converted to bold text
                    processed_lines.append(f"**{title}**")
                    processed_lines.append("")
                    prev_was_heading = False
                
                i += 1
                continue
            
            elif stripped == '---' and prev_was_heading:
                # Skip separator immediately after heading
                i += 1
                continue
            
            elif stripped == '' and prev_was_heading:
                # Keep only one empty line after heading
                if processed_lines and processed_lines[-1].strip() != '':
                    processed_lines.append(line)
                prev_was_heading = False
            
            else:
                processed_lines.append(line)
                prev_was_heading = False
            
            i += 1
        
        # Clean up consecutive empty lines (keep max 2)
        result_lines = []
        empty_count = 0
        for line in processed_lines:
            if line.strip() == '':
                empty_count += 1
                if empty_count <= 2:
                    result_lines.append(line)
            else:
                empty_count = 0
                result_lines.append(line)
        
        return '\n'.join(result_lines)
    
    @classmethod
    def save_report(cls, report: Report) -> None:
        """Save report metadata and complete report"""
        cls._ensure_report_folder(report.report_id)
        
        # Save metadata JSON
        with open(cls._get_report_path(report.report_id), 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        
        # Save outline
        if report.outline:
            cls.save_outline(report.report_id, report.outline)
        
        # Save complete Markdown report
        if report.markdown_content:
            with open(cls._get_report_markdown_path(report.report_id), 'w', encoding='utf-8') as f:
                f.write(report.markdown_content)
        
        logger.info(f"Report saved: {report.report_id}")
    
    @classmethod
    def get_report(cls, report_id: str) -> Optional[Report]:
        """Get report"""
        path = cls._get_report_path(report_id)
        
        if not os.path.exists(path):
            # Backward compatibility: check files stored directly in reports directory
            old_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
            if os.path.exists(old_path):
                path = old_path
            else:
                return None
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Rebuild Report object
        outline = None
        if data.get('outline'):
            outline_data = data['outline']
            sections = []
            for s in outline_data.get('sections', []):
                sections.append(ReportSection(
                    title=s['title'],
                    content=s.get('content', ''),
                    role=s.get('role', 'general'),
                    description=s.get('description', ''),
                ))
            outline = ReportOutline(
                title=outline_data['title'],
                summary=outline_data['summary'],
                sections=sections
            )
        
        # If markdown_content is empty, try reading from full_report.md
        markdown_content = data.get('markdown_content', '')
        if not markdown_content:
            full_report_path = cls._get_report_markdown_path(report_id)
            if os.path.exists(full_report_path):
                with open(full_report_path, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()
        
        return Report(
            report_id=data['report_id'],
            simulation_id=data['simulation_id'],
            graph_id=data['graph_id'],
            simulation_requirement=data['simulation_requirement'],
            status=ReportStatus(data['status']),
            outline=outline,
            markdown_content=markdown_content,
            created_at=data.get('created_at', ''),
            completed_at=data.get('completed_at', ''),
            error=data.get('error')
        )
    
    @classmethod
    def get_report_by_simulation(cls, simulation_id: str) -> Optional[Report]:
        """Get report by simulation ID"""
        cls._ensure_reports_dir()
        
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # New format: folder
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report and report.simulation_id == simulation_id:
                    return report
            # Backward compatible: JSON file
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report and report.simulation_id == simulation_id:
                    return report
        
        return None
    
    @classmethod
    def list_reports(cls, simulation_id: Optional[str] = None, limit: int = 50) -> List[Report]:
        """List reports"""
        cls._ensure_reports_dir()
        
        reports = []
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # New format: folder
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
            # Backward compatible: JSON file
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
        
        # Sort by creation time descending
        reports.sort(key=lambda r: r.created_at, reverse=True)
        
        return reports[:limit]
    
    @classmethod
    def delete_report(cls, report_id: str) -> bool:
        """Delete report (entire folder)"""
        import shutil
        
        folder_path = cls._get_report_folder(report_id)
        
        # New format: delete entire folder
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            logger.info(f"Report folder deleted: {report_id}")
            return True
        
        # Backward compatible: delete individual files
        deleted = False
        old_json_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
        old_md_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.md")
        
        if os.path.exists(old_json_path):
            os.remove(old_json_path)
            deleted = True
        if os.path.exists(old_md_path):
            os.remove(old_md_path)
            deleted = True
        
        return deleted
