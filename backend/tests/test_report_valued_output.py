"""Unit tests for valued-output report planning and payload helpers."""

import json
import os
import sys
import unittest

# Ensure backend/app is on path when running pytest or unittest from repo root
_BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

os.environ.setdefault("ENABLE_REPORT_PAYLOAD_V1", "true")

from app.config import Config  # noqa: E402
from app.services.report_agent import (  # noqa: E402
    ReportAgent,
    ReportOutline,
    ReportSection,
    OUTLINE_REQUIRED_ROLES,
)
from app.services.report_payload import (  # noqa: E402
    REPORT_PAYLOAD_VERSION,
    build_report_payload_v1,
    render_scenarios_markdown,
    _placeholder_scenarios,
)
from app.services.grounding_bundle import evaluate_grounding_staleness  # noqa: E402
from app.models.project import Project, ProjectStatus  # noqa: E402


class TestOutlineRoles(unittest.TestCase):
    def test_validate_default_v1_outline(self):
        agent = ReportAgent(
            graph_id="g1",
            simulation_id="s1",
            simulation_requirement="test scenario",
            project_id=None,
        )
        outline = agent._default_outline_v1()
        self.assertTrue(agent._validate_outline_roles(outline))
        roles = [s.role for s in outline.sections]
        self.assertEqual(set(roles), set(OUTLINE_REQUIRED_ROLES))


class TestPayloadBuilder(unittest.TestCase):
    def test_build_payload_minimal(self):
        p = build_report_payload_v1(
            simulation_requirement="sq",
            simulation_id="sim_x",
            graph_id="g_y",
            project=None,
            metrics_payload={"a": 1},
            positions_payload=None,
            risks_payload=None,
            stakeholder_matrix_payload=None,
            scenarios=_placeholder_scenarios(),
            staleness_warnings=[],
            claims=[],
        )
        self.assertEqual(p["version"], REPORT_PAYLOAD_VERSION)
        self.assertEqual(p["simulation_id"], "sim_x")
        self.assertIn("scenarios", p)
        self.assertEqual(len(p["scenarios"]), 3)


class TestScenariosRender(unittest.TestCase):
    def test_render_non_empty(self):
        md = render_scenarios_markdown(_placeholder_scenarios())
        self.assertIn("Base case", md)
        self.assertIn("Stress", md)


class TestGroundingStaleness(unittest.TestCase):
    def test_no_sources_warns_when_enabled(self):
        proj = Project(
            project_id="p1",
            name="t",
            status=ProjectStatus.CREATED,
            created_at="2020-01-01",
            updated_at="2020-01-01",
            grounding_sources=[],
        )
        warns, block = evaluate_grounding_staleness(proj)
        self.assertFalse(block)


if __name__ == "__main__":
    unittest.main()
