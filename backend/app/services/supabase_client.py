"""Supabase client singleton for database and auth operations."""

import json
import os
from functools import lru_cache
from supabase import create_client, Client
from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('glas.supabase')


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    url = Config.SUPABASE_URL
    key = Config.SUPABASE_SERVICE_KEY
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set")
    return create_client(url, key)


class SupabaseDB:
    """Thin wrapper around the Supabase client for common operations."""

    @staticmethod
    def client() -> Client:
        return get_supabase_client()

    # -- profiles --
    @classmethod
    def get_or_create_profile(cls, user_id: str, email: str = "") -> dict:
        resp = cls.client().table("profiles").select("*").eq("id", user_id).execute()
        if resp.data:
            return resp.data[0]
        row = {"id": user_id, "email": email, "plan": "free", "credits": 1}
        cls.client().table("profiles").insert(row).execute()
        return row

    @classmethod
    def get_profile(cls, user_id: str) -> dict | None:
        resp = cls.client().table("profiles").select("*").eq("id", user_id).execute()
        return resp.data[0] if resp.data else None

    @classmethod
    def update_profile(cls, user_id: str, **fields) -> dict:
        resp = cls.client().table("profiles").update(fields).eq("id", user_id).execute()
        return resp.data[0] if resp.data else {}

    # -- projects --
    @classmethod
    def insert_project(cls, data: dict) -> dict:
        resp = cls.client().table("projects").insert(data).execute()
        return resp.data[0] if resp.data else {}

    @classmethod
    def get_project(cls, project_id: str, user_id: str | None = None) -> dict | None:
        q = cls.client().table("projects").select("*").eq("id", project_id)
        if user_id:
            q = q.eq("user_id", user_id)
        resp = q.execute()
        return resp.data[0] if resp.data else None

    @classmethod
    def list_projects(cls, user_id: str, limit: int = 50) -> list[dict]:
        resp = (cls.client().table("projects")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute())
        return resp.data or []

    @classmethod
    def update_project(cls, project_id: str, **fields) -> dict:
        resp = cls.client().table("projects").update(fields).eq("id", project_id).execute()
        return resp.data[0] if resp.data else {}

    @classmethod
    def delete_project(cls, project_id: str) -> bool:
        cls.client().table("projects").delete().eq("id", project_id).execute()
        return True

    # -- simulations --
    @classmethod
    def insert_simulation(cls, data: dict) -> dict:
        resp = cls.client().table("simulations").insert(data).execute()
        return resp.data[0] if resp.data else {}

    @classmethod
    def get_simulation(cls, simulation_id: str, user_id: str | None = None) -> dict | None:
        q = cls.client().table("simulations").select("*").eq("id", simulation_id)
        if user_id:
            q = q.eq("user_id", user_id)
        resp = q.execute()
        return resp.data[0] if resp.data else None

    @classmethod
    def list_simulations(cls, user_id: str, project_id: str | None = None, limit: int = 50) -> list[dict]:
        q = cls.client().table("simulations").select("*").eq("user_id", user_id)
        if project_id:
            q = q.eq("project_id", project_id)
        resp = q.order("created_at", desc=True).limit(limit).execute()
        return resp.data or []

    @classmethod
    def update_simulation(cls, simulation_id: str, **fields) -> dict:
        resp = cls.client().table("simulations").update(fields).eq("id", simulation_id).execute()
        return resp.data[0] if resp.data else {}

    # -- reports --
    @classmethod
    def insert_report(cls, data: dict) -> dict:
        resp = cls.client().table("reports").insert(data).execute()
        return resp.data[0] if resp.data else {}

    @classmethod
    def get_report(cls, report_id: str, user_id: str | None = None) -> dict | None:
        q = cls.client().table("reports").select("*").eq("id", report_id)
        if user_id:
            q = q.eq("user_id", user_id)
        resp = q.execute()
        return resp.data[0] if resp.data else None

    @classmethod
    def get_report_by_simulation(cls, simulation_id: str, user_id: str | None = None) -> dict | None:
        q = cls.client().table("reports").select("*").eq("simulation_id", simulation_id)
        if user_id:
            q = q.eq("user_id", user_id)
        resp = q.execute()
        return resp.data[0] if resp.data else None

    @classmethod
    def update_report(cls, report_id: str, **fields) -> dict:
        resp = cls.client().table("reports").update(fields).eq("id", report_id).execute()
        return resp.data[0] if resp.data else {}

    # -- credit transactions --
    @classmethod
    def insert_credit_tx(cls, user_id: str, amount: int, tx_type: str, description: str = "") -> dict:
        data = {"user_id": user_id, "amount": amount, "type": tx_type, "description": description}
        resp = cls.client().table("credit_transactions").insert(data).execute()
        return resp.data[0] if resp.data else {}

    @classmethod
    def deduct_credit(cls, user_id: str, description: str = "simulation") -> bool:
        """Atomically deduct one credit. Returns True on success, False if insufficient."""
        try:
            resp = cls.client().rpc(
                "deduct_credit_atomic",
                {"p_user_id": user_id, "p_description": description},
            ).execute()
            result = resp.data
            if isinstance(result, list):
                result = result[0] if result else -1
            return int(result) >= 0
        except Exception:
            logger.warning(f"Atomic deduct RPC unavailable, falling back for user {user_id}")
            profile = cls.get_profile(user_id)
            if not profile or profile.get("credits", 0) < 1:
                return False
            new_credits = profile["credits"] - 1
            resp = (cls.client().table("profiles")
                    .update({"credits": new_credits})
                    .eq("id", user_id)
                    .gte("credits", 1)
                    .execute())
            if not resp.data:
                return False
            cls.insert_credit_tx(user_id, -1, "usage", description)
            return True

    # -- decision bundles --
    @classmethod
    def create_bundle(cls, user_id: str, title: str, decision_context: str,
                      suggested_scenarios: list) -> dict:
        data = {
            "user_id": user_id,
            "title": title,
            "decision_context": decision_context,
            "suggested_scenarios": json.dumps(suggested_scenarios),
            "completed_scenarios": json.dumps([]),
            "status": "in_progress",
        }
        resp = cls.client().table("decision_bundles").insert(data).execute()
        row = resp.data[0] if resp.data else {}
        if row:
            row['suggested_scenarios'] = suggested_scenarios
            row['completed_scenarios'] = []
        return row

    @classmethod
    def _parse_bundle_json_fields(cls, row: dict) -> None:
        for field in ('suggested_scenarios', 'completed_scenarios'):
            val = row.get(field)
            if isinstance(val, str):
                try:
                    row[field] = json.loads(val)
                except json.JSONDecodeError:
                    row[field] = []

    @classmethod
    def get_bundle(cls, bundle_id: str, user_id: str | None = None) -> dict | None:
        q = cls.client().table("decision_bundles").select("*").eq("id", bundle_id)
        if user_id:
            q = q.eq("user_id", user_id)
        resp = q.execute()
        row = resp.data[0] if resp.data else None
        if row:
            cls._parse_bundle_json_fields(row)
        return row

    @classmethod
    def list_bundles(cls, user_id: str, limit: int = 20) -> list[dict]:
        resp = (cls.client().table("decision_bundles")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute())
        rows = resp.data or []
        for row in rows:
            cls._parse_bundle_json_fields(row)
        return rows

    @classmethod
    def update_bundle(cls, bundle_id: str, **fields) -> dict:
        for field in ('suggested_scenarios', 'completed_scenarios'):
            if field in fields and not isinstance(fields[field], str):
                fields[field] = json.dumps(fields[field])
        resp = cls.client().table("decision_bundles").update(fields).eq("id", bundle_id).execute()
        return resp.data[0] if resp.data else {}

    @classmethod
    def delete_bundle(cls, bundle_id: str, user_id: str | None = None) -> bool:
        q = cls.client().table("decision_bundles").delete().eq("id", bundle_id)
        if user_id:
            q = q.eq("user_id", user_id)
        q.execute()
        return True

    # -- simulation reminders --
    @classmethod
    def create_reminder(cls, user_id: str, simulation_id: str, scenario: str,
                        remind_at: str) -> dict:
        data = {
            "user_id": user_id,
            "simulation_id": simulation_id,
            "scenario": scenario,
            "remind_at": remind_at,
            "sent": False,
        }
        resp = cls.client().table("simulation_reminders").insert(data).execute()
        return resp.data[0] if resp.data else {}

    @classmethod
    def list_reminders(cls, user_id: str, limit: int = 20) -> list[dict]:
        resp = (cls.client().table("simulation_reminders")
                .select("*")
                .eq("user_id", user_id)
                .eq("sent", False)
                .order("remind_at", desc=False)
                .limit(limit)
                .execute())
        return resp.data or []

    @classmethod
    def get_due_reminders(cls) -> list[dict]:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        resp = (cls.client().table("simulation_reminders")
                .select("*")
                .eq("sent", False)
                .lte("remind_at", now)
                .execute())
        return resp.data or []

    @classmethod
    def mark_reminder_sent(cls, reminder_id: str) -> dict:
        resp = (cls.client().table("simulation_reminders")
                .update({"sent": True})
                .eq("id", reminder_id)
                .execute())
        return resp.data[0] if resp.data else {}
