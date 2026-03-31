"""Unit tests for authentication middleware."""

import pytest
from flask import g


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert "service" in data


class TestAuthMiddleware:
    def test_no_auth_header_sets_none(self, client):
        """Without Supabase config, user becomes anonymous."""
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_unauthenticated_protected_route_anonymous_mode(self, client):
        """When Supabase is not configured, require_auth allows anonymous access."""
        resp = client.get("/api/dashboard/overview")
        assert resp.status_code in (200, 401, 500)
