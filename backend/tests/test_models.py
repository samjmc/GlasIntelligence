"""Unit tests for data models."""

import pytest
from app.models.project import Project, ProjectStatus


class TestProjectStatus:
    def test_status_values(self):
        assert ProjectStatus.CREATED.value == "created"
        assert ProjectStatus.GRAPH_COMPLETED.value == "graph_completed"
        assert ProjectStatus.FAILED.value == "failed"

    def test_status_from_string(self):
        assert ProjectStatus("created") == ProjectStatus.CREATED
        assert ProjectStatus("failed") == ProjectStatus.FAILED


class TestProject:
    def test_create_project(self):
        proj = Project(
            project_id="p1",
            name="Test Project",
            status=ProjectStatus.CREATED,
            created_at="2025-01-01T00:00:00",
            updated_at="2025-01-01T00:00:00",
        )
        assert proj.project_id == "p1"
        assert proj.name == "Test Project"
        assert proj.status == ProjectStatus.CREATED

    def test_to_dict(self):
        proj = Project(
            project_id="p1",
            name="Test",
            status=ProjectStatus.CREATED,
            created_at="2025-01-01",
            updated_at="2025-01-01",
        )
        d = proj.to_dict()
        assert d["project_id"] == "p1"
        assert d["status"] == "created"
        assert d["files"] == []
        assert d["ontology"] is None

    def test_from_dict(self):
        data = {
            "project_id": "p2",
            "name": "From Dict",
            "status": "graph_completed",
            "created_at": "2025-06-01",
            "updated_at": "2025-06-01",
            "chunk_size": 500,
        }
        proj = Project.from_dict(data)
        assert proj.project_id == "p2"
        assert proj.status == ProjectStatus.GRAPH_COMPLETED
        assert proj.chunk_size == 500

    def test_roundtrip_dict(self):
        proj = Project(
            project_id="rt",
            name="Roundtrip",
            status=ProjectStatus.ONTOLOGY_GENERATED,
            created_at="2025-03-01",
            updated_at="2025-03-01",
            grounding_sources=[{"type": "upload", "id": "f1"}],
        )
        restored = Project.from_dict(proj.to_dict())
        assert restored.project_id == proj.project_id
        assert restored.status == proj.status
        assert restored.grounding_sources == proj.grounding_sources

    def test_from_dict_defaults(self):
        data = {"project_id": "min", "status": "created"}
        proj = Project.from_dict(data)
        assert proj.name == "Unnamed Project"
        assert proj.chunk_size == 300
        assert proj.chunk_overlap == 30
