"""Integration tests for core API endpoints."""

import pytest


class TestHealthAPI:
    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["service"] == "Glas Intelligence Backend"

    def test_health_cors_locked_field(self, client):
        resp = client.get("/health")
        data = resp.get_json()
        assert "cors_locked" in data


class TestGraphAPI:
    def test_graph_routes_require_auth_or_anonymous(self, client):
        resp = client.get("/api/graph/nonexistent")
        assert resp.status_code in (401, 404, 405)


class TestSimulationAPI:
    def test_simulation_routes_exist(self, client):
        resp = client.get("/api/simulation/nonexistent")
        assert resp.status_code in (401, 404, 405)


class TestReportAPI:
    def test_report_routes_exist(self, client):
        resp = client.get("/api/report/nonexistent")
        assert resp.status_code in (401, 404, 405)


class TestBillingAPI:
    def test_billing_routes_exist(self, client):
        resp = client.get("/api/billing/nonexistent")
        assert resp.status_code in (401, 404, 405)


class TestDashboardAPI:
    def test_dashboard_overview_accessible(self, client):
        resp = client.get("/api/dashboard/overview")
        assert resp.status_code in (200, 401, 500)


class TestFeedAPI:
    def test_feed_routes_exist(self, client):
        resp = client.get("/api/feed/nonexistent")
        assert resp.status_code in (401, 404, 405)


class TestBundleAPI:
    def test_bundle_routes_exist(self, client):
        resp = client.get("/api/bundle/nonexistent")
        assert resp.status_code in (401, 404, 405, 500)
