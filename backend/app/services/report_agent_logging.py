"""Report agent file/console loggers (extracted from report_agent for maintainability)."""

import json
import os
from datetime import datetime
from typing import Any

from ..config import Config


class ReportLogger:
    """
    Report Agent detailed logger

    Generates an agent_log.jsonl file in the report folder, recording each detailed action.
    Each line is a complete JSON object containing timestamp, action type, detailed content, etc.
    """

    def __init__(self, report_id: str):
        self.report_id = report_id
        self.log_file_path = os.path.join(Config.UPLOAD_FOLDER, "reports", report_id, "agent_log.jsonl")
        self.start_time = datetime.now()
        self._ensure_log_file()

    def _ensure_log_file(self):
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)

    def _get_elapsed_time(self) -> float:
        return (datetime.now() - self.start_time).total_seconds()

    def log(
        self, action: str, stage: str, details: dict[str, Any], section_title: str = None, section_index: int = None
    ):
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(self._get_elapsed_time(), 2),
            "report_id": self.report_id,
            "action": action,
            "stage": stage,
            "section_title": section_title,
            "section_index": section_index,
            "details": details,
        }

        with open(self.log_file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def log_start(self, simulation_id: str, graph_id: str, simulation_requirement: str):
        self.log(
            action="report_start",
            stage="pending",
            details={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "simulation_requirement": simulation_requirement,
                "message": "Report generation task started",
            },
        )

    def log_planning_start(self):
        self.log(action="planning_start", stage="planning", details={"message": "Starting report outline planning"})

    def log_planning_context(self, context: dict[str, Any]):
        self.log(
            action="planning_context",
            stage="planning",
            details={"message": "Retrieved simulation context information", "context": context},
        )

    def log_planning_complete(self, outline_dict: dict[str, Any]):
        self.log(
            action="planning_complete",
            stage="planning",
            details={"message": "Outline planning completed", "outline": outline_dict},
        )

    def log_section_start(self, section_title: str, section_index: int):
        self.log(
            action="section_start",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={"message": f"Starting section generation: {section_title}"},
        )

    def log_react_thought(self, section_title: str, section_index: int, iteration: int, thought: str):
        self.log(
            action="react_thought",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={"iteration": iteration, "thought": thought, "message": f"ReACT iteration {iteration} thinking"},
        )

    def log_tool_call(
        self, section_title: str, section_index: int, tool_name: str, parameters: dict[str, Any], iteration: int
    ):
        self.log(
            action="tool_call",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "parameters": parameters,
                "message": f"Calling tool: {tool_name}",
            },
        )

    def log_tool_result(self, section_title: str, section_index: int, tool_name: str, result: str, iteration: int):
        self.log(
            action="tool_result",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "result": result,
                "result_length": len(result),
                "message": f"Tool {tool_name} returned result",
            },
        )

    def log_llm_response(
        self,
        section_title: str,
        section_index: int,
        response: str,
        iteration: int,
        has_tool_calls: bool,
        has_final_answer: bool,
    ):
        self.log(
            action="llm_response",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "response": response,
                "response_length": len(response),
                "has_tool_calls": has_tool_calls,
                "has_final_answer": has_final_answer,
                "message": f"LLM response (tool calls: {has_tool_calls}, final answer: {has_final_answer})",
            },
        )

    def log_section_content(self, section_title: str, section_index: int, content: str, tool_calls_count: int):
        self.log(
            action="section_content",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": content,
                "content_length": len(content),
                "tool_calls_count": tool_calls_count,
                "message": f"Section {section_title} content generation complete",
            },
        )

    def log_section_full_complete(self, section_title: str, section_index: int, full_content: str):
        self.log(
            action="section_complete",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": full_content,
                "content_length": len(full_content),
                "message": f"Section {section_title} generation complete",
            },
        )

    def log_report_complete(self, total_sections: int, total_time_seconds: float):
        self.log(
            action="report_complete",
            stage="completed",
            details={
                "total_sections": total_sections,
                "total_time_seconds": round(total_time_seconds, 2),
                "message": "Report generation complete",
            },
        )

    def log_error(self, error_message: str, stage: str, section_title: str = None):
        self.log(
            action="error",
            stage=stage,
            section_title=section_title,
            section_index=None,
            details={"error": error_message, "message": f"Error occurred: {error_message}"},
        )


class ReportConsoleLogger:
    """Writes console-style logs to console_log.txt in the report folder."""

    def __init__(self, report_id: str):
        self.report_id = report_id
        self.log_file_path = os.path.join(Config.UPLOAD_FOLDER, "reports", report_id, "console_log.txt")
        self._ensure_log_file()
        self._file_handler = None
        self._setup_file_handler()

    def _ensure_log_file(self):
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)

    def _setup_file_handler(self):
        import logging

        self._file_handler = logging.FileHandler(self.log_file_path, mode="a", encoding="utf-8")
        self._file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")
        self._file_handler.setFormatter(formatter)

        for logger_name in ("glas.report_agent", "glas.zep_tools"):
            target_logger = logging.getLogger(logger_name)
            if self._file_handler not in target_logger.handlers:
                target_logger.addHandler(self._file_handler)

    def close(self):
        import logging

        if self._file_handler:
            for logger_name in ("glas.report_agent", "glas.zep_tools"):
                target_logger = logging.getLogger(logger_name)
                if self._file_handler in target_logger.handlers:
                    target_logger.removeHandler(self._file_handler)
            self._file_handler.close()
            self._file_handler = None

    def __del__(self):
        self.close()
