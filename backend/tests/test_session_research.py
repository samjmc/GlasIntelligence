"""Tests for the session-scoped deep-research start endpoint.

Focus: PR #13 introduces the rule that a session marked ``research_status=completed``
but with an empty/missing ``research_dossier.summary_md`` should be treated as a
retryable failure (no credit charged), instead of returning 409.
"""

from unittest.mock import patch


class _ClaimChain:
    """Mimic the supabase-py UPDATE chain ending in .execute() with .data set."""

    def __init__(self, returned_data, capture_payload):
        self._returned_data = returned_data
        self._capture_payload = capture_payload

    def eq(self, *_a, **_k):
        return self

    def is_(self, *_a, **_k):
        return self

    def execute(self):
        class _Resp:
            data = self._returned_data

        return _Resp()


class _ClaimTable:
    def __init__(self, captured):
        self._captured = captured

    def update(self, payload):
        self._captured["payload"] = payload
        return _ClaimChain([{"id": "sess-1"}], self._captured)


class _ClaimClient:
    def __init__(self, captured):
        self._captured = captured

    def table(self, _name):
        return _ClaimTable(self._captured)


def _patch_research_dependencies(captured, session_payload, *, deduct_returns=True):
    """Patch the symbols used by start_research to make the endpoint testable."""
    from app.services import supabase_client as sb_mod
    from app.tasks import research_tasks as rt_mod

    patches = [
        patch.object(sb_mod.SupabaseDB, "get_session", return_value=session_payload),
        patch.object(sb_mod.SupabaseDB, "client", return_value=_ClaimClient(captured)),
        patch.object(sb_mod.SupabaseDB, "deduct_research_credit", return_value=deduct_returns),
        patch.object(sb_mod.SupabaseDB, "get_profile", return_value={"plan": "pro", "research_credits": 5}),
        patch.object(sb_mod.SupabaseDB, "update_session", return_value=None),
        patch.object(rt_mod.run_deep_research_task, "apply_async", return_value=type("R", (), {"id": "task-1"})()),
    ]
    return patches


def _enable_deep_research(monkeypatch):
    from app import config as app_config

    monkeypatch.setattr(app_config.Config, "DEEP_RESEARCH_ENABLED", True)


class TestStartResearchEmptyCompleted:
    def test_completed_with_real_dossier_returns_409(self, client, monkeypatch):
        """Original behaviour: completed + non-empty dossier still rejects."""
        _enable_deep_research(monkeypatch)
        captured = {}
        session = {
            "id": "sess-1",
            "user_id": "anon",
            "prompt": "test prompt",
            "research_status": "completed",
            "research_dossier": {"summary_md": "Real research output here."},
        }
        patches = _patch_research_dependencies(captured, session)
        for p in patches:
            p.start()
        try:
            resp = client.post("/api/session/sess-1/research", json={})
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 409
        body = resp.get_json()
        assert "already completed" in body["error"].lower()
        assert "payload" not in captured  # never reached the claim step

    def test_completed_with_empty_dossier_allows_retry(self, client, monkeypatch):
        """New behaviour: completed + empty dossier is treated as retryable."""
        _enable_deep_research(monkeypatch)
        captured = {}
        session = {
            "id": "sess-1",
            "user_id": "anon",
            "prompt": "test prompt",
            "research_status": "completed",
            "research_dossier": {"summary_md": ""},
        }
        patches = _patch_research_dependencies(captured, session)
        for p in patches:
            p.start()
        try:
            resp = client.post("/api/session/sess-1/research", json={})
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.get_json()}"
        # Claim should also have wiped the stale empty dossier so the user
        # doesn't keep seeing an empty card if the retry also fails.
        assert captured["payload"]["research_status"] == "claiming"
        assert captured["payload"]["research_dossier"] is None

    def test_completed_with_missing_summary_field_allows_retry(self, client, monkeypatch):
        """Defensive: dossier dict without summary_md key is also retryable."""
        _enable_deep_research(monkeypatch)
        captured = {}
        session = {
            "id": "sess-1",
            "user_id": "anon",
            "prompt": "test prompt",
            "research_status": "completed",
            "research_dossier": {"sources": []},  # no summary_md at all
        }
        patches = _patch_research_dependencies(captured, session)
        for p in patches:
            p.start()
        try:
            resp = client.post("/api/session/sess-1/research", json={})
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 200
        assert captured["payload"]["research_dossier"] is None

    def test_completed_with_null_dossier_allows_retry(self, client, monkeypatch):
        """Defensive: research_dossier=None on a completed row is also retryable."""
        _enable_deep_research(monkeypatch)
        captured = {}
        session = {
            "id": "sess-1",
            "user_id": "anon",
            "prompt": "test prompt",
            "research_status": "completed",
            "research_dossier": None,
        }
        patches = _patch_research_dependencies(captured, session)
        for p in patches:
            p.start()
        try:
            resp = client.post("/api/session/sess-1/research", json={})
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 200

    def test_processing_still_returns_409(self, client, monkeypatch):
        """In-flight research is unaffected by the empty-dossier carve-out."""
        _enable_deep_research(monkeypatch)
        captured = {}
        session = {
            "id": "sess-1",
            "user_id": "anon",
            "prompt": "test prompt",
            "research_status": "processing",
            "research_dossier": None,
        }
        patches = _patch_research_dependencies(captured, session)
        for p in patches:
            p.start()
        try:
            resp = client.post("/api/session/sess-1/research", json={})
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 409

    def test_empty_completed_retry_does_not_charge_credit(self, client, monkeypatch):
        """is_retry=True for empty-completed → deduct_research_credit must NOT be called."""
        _enable_deep_research(monkeypatch)
        captured = {}
        session = {
            "id": "sess-1",
            "user_id": "anon",
            "prompt": "test prompt",
            "research_status": "completed",
            "research_dossier": {"summary_md": "   \n  "},  # whitespace-only
        }
        from app.services import supabase_client as sb_mod
        from app.tasks import research_tasks as rt_mod

        deduct_mock = patch.object(sb_mod.SupabaseDB, "deduct_research_credit", return_value=True)
        patches = [
            patch.object(sb_mod.SupabaseDB, "get_session", return_value=session),
            patch.object(sb_mod.SupabaseDB, "client", return_value=_ClaimClient(captured)),
            deduct_mock,
            patch.object(sb_mod.SupabaseDB, "get_profile", return_value={"plan": "pro", "research_credits": 5}),
            patch.object(sb_mod.SupabaseDB, "update_session", return_value=None),
            patch.object(rt_mod.run_deep_research_task, "apply_async", return_value=type("R", (), {"id": "task-1"})()),
        ]
        started = [p.start() for p in patches]
        try:
            resp = client.post("/api/session/sess-1/research", json={})
        finally:
            for p in patches:
                p.stop()

        assert resp.status_code == 200
        # The deduct mock corresponds to started[2]
        assert started[2].call_count == 0, "empty-completed retry should be free"
