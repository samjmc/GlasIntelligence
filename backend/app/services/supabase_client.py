"""Supabase client singleton for database and auth operations."""

import json
import uuid
from functools import lru_cache
from datetime import datetime, UTC
from supabase import create_client, Client
from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("glas.supabase")


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
        resp = (
            cls.client()
            .table("projects")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
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
            resp = (
                cls.client()
                .rpc(
                    "deduct_credit_atomic",
                    {"p_user_id": user_id, "p_description": description},
                )
                .execute()
            )
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
            resp = (
                cls.client()
                .table("profiles")
                .update({"credits": new_credits})
                .eq("id", user_id)
                .gte("credits", 1)
                .execute()
            )
            if not resp.data:
                return False
            cls.insert_credit_tx(user_id, -1, "usage", description)
            return True

    @classmethod
    def deduct_research_credit(cls, user_id: str, description: str = "deep_research") -> bool:
        """Atomically deduct one research credit. Returns True on success, False if insufficient."""
        try:
            resp = (
                cls.client()
                .rpc(
                    "deduct_research_credit_atomic",
                    {"p_user_id": user_id, "p_description": description},
                )
                .execute()
            )
            result = resp.data
            if isinstance(result, list):
                result = result[0] if result else -1
            return int(result) >= 0
        except Exception:
            logger.warning(f"Research credit RPC unavailable, falling back for user {user_id}")
            profile = cls.get_profile(user_id)
            if not profile or profile.get("research_credits", 0) < 1:
                return False
            new_credits = profile["research_credits"] - 1
            resp = (
                cls.client()
                .table("profiles")
                .update({"research_credits": new_credits})
                .eq("id", user_id)
                .gte("research_credits", 1)
                .execute()
            )
            if not resp.data:
                return False
            cls.insert_credit_tx(user_id, -1, "research_usage", description)
            return True

    @classmethod
    def refund_research_credit(cls, user_id: str, description: str = "research_refund") -> bool:
        """Refund one research credit (e.g. after a failed research run)."""
        try:
            resp = (
                cls.client()
                .rpc(
                    "refund_research_credit",
                    {"p_user_id": user_id, "p_description": description},
                )
                .execute()
            )
            # Mirror the deduct path: check the RPC actually refunded rather
            # than reporting success unconditionally.
            result = resp.data
            if isinstance(result, list):
                result = result[0] if result else -1
            return int(result) >= 0
        except Exception:
            logger.warning(f"Research refund RPC unavailable, falling back for user {user_id}")
            profile = cls.get_profile(user_id)
            if not profile:
                return False
            new_credits = profile.get("research_credits", 0) + 1
            cls.client().table("profiles").update({"research_credits": new_credits}).eq("id", user_id).execute()
            cls.insert_credit_tx(user_id, 1, "research_refund", description)
            return True

    # -- decision bundles --
    @classmethod
    def create_bundle(cls, user_id: str, title: str, decision_context: str, suggested_scenarios: list) -> dict:
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
            row["suggested_scenarios"] = suggested_scenarios
            row["completed_scenarios"] = []
        return row

    @classmethod
    def _parse_bundle_json_fields(cls, row: dict) -> None:
        for field in ("suggested_scenarios", "completed_scenarios"):
            val = row.get(field)
            if isinstance(val, str):
                try:
                    row[field] = json.loads(val)
                except json.JSONDecodeError:
                    row[field] = []
        syn = row.get("synthesis")
        if isinstance(syn, str):
            try:
                row["synthesis"] = json.loads(syn)
            except json.JSONDecodeError:
                row["synthesis"] = None

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
        resp = (
            cls.client()
            .table("decision_bundles")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = resp.data or []
        for row in rows:
            cls._parse_bundle_json_fields(row)
        return rows

    @classmethod
    def update_bundle(cls, bundle_id: str, **fields) -> dict:
        for field in ("suggested_scenarios", "completed_scenarios", "synthesis"):
            val = fields.get(field)
            if val is not None and not isinstance(val, str):
                fields[field] = json.dumps(val)
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
    def create_reminder(cls, user_id: str, simulation_id: str, scenario: str, remind_at: str) -> dict:
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
        resp = (
            cls.client()
            .table("simulation_reminders")
            .select("*")
            .eq("user_id", user_id)
            .eq("sent", False)
            .order("remind_at", desc=False)
            .limit(limit)
            .execute()
        )
        return resp.data or []

    @classmethod
    def get_due_reminders(cls) -> list[dict]:
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        resp = cls.client().table("simulation_reminders").select("*").eq("sent", False).lte("remind_at", now).execute()
        return resp.data or []

    @classmethod
    def mark_reminder_sent(cls, reminder_id: str) -> dict:
        resp = cls.client().table("simulation_reminders").update({"sent": True}).eq("id", reminder_id).execute()
        return resp.data[0] if resp.data else {}

    # -- scenario sessions --
    @classmethod
    def create_session(
        cls,
        user_id: str,
        prompt: str,
        decision_context: dict | None = None,
    ) -> dict:
        row = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "status": "active",
            "prompt": prompt,
            "decision_context": json.dumps(decision_context or {}),
        }
        resp = cls.client().table("scenario_sessions").insert(row).execute()
        result = resp.data[0] if resp.data else row
        cls._parse_session_json(result)
        return result

    @classmethod
    def get_session(cls, session_id: str, user_id: str | None = None) -> dict | None:
        q = cls.client().table("scenario_sessions").select("*").eq("id", session_id)
        if user_id:
            q = q.eq("user_id", user_id)
        resp = q.execute()
        row = resp.data[0] if resp.data else None
        if row:
            cls._parse_session_json(row)
        return row

    ACTIVE_SESSION_COLUMNS = (
        "id,user_id,status,prompt,decision_context,"
        "research_status,research_angles,research_started_at,research_completed_at,"
        "simulation_id,project_id,graph_id,simulation_count,uploaded_files,bundle_config,created_at,updated_at"
    )

    @classmethod
    def propagate_graph_id_for_project(cls, project_id: str, graph_id: str | None) -> None:
        """Copy Zep graph_id onto all scenario_sessions rows linked to this project (recovery / backup)."""
        if not project_id or not graph_id or not str(graph_id).strip():
            return
        gid = str(graph_id).strip()
        try:
            cls.client().table("scenario_sessions").update(
                {"graph_id": gid, "updated_at": datetime.now(UTC).isoformat()}
            ).eq("project_id", project_id).execute()
        except Exception:
            logger.warning(
                "propagate_graph_id_for_project failed project_id=%s (sessions may lack graph_id column until migration)",
                project_id,
                exc_info=True,
            )

    @classmethod
    def get_recent_sessions(cls, user_id: str, limit: int = 20) -> list[dict]:
        """Return the most recent sessions for a user, including completed ones."""
        resp = (
            cls.client()
            .table("scenario_sessions")
            .select(cls.ACTIVE_SESSION_COLUMNS)
            .eq("user_id", user_id)
            .neq("status", "abandoned")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        rows = resp.data or []
        for r in rows:
            cls._parse_session_json(r)
        return rows

    @classmethod
    def get_active_sessions(cls, user_id: str) -> list[dict]:
        resp = (
            cls.client()
            .table("scenario_sessions")
            .select(cls.ACTIVE_SESSION_COLUMNS)
            .eq("user_id", user_id)
            .neq("status", "completed")
            .neq("status", "abandoned")
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )
        rows = resp.data or []
        for r in rows:
            cls._parse_session_json(r)
        return rows

    @classmethod
    def update_session(cls, session_id: str, **fields) -> dict:
        for key in ("decision_context", "uploaded_files", "research_angles", "bundle_config"):
            if key in fields and not isinstance(fields[key], str):
                fields[key] = json.dumps(fields[key])
        if "research_dossier" in fields and not isinstance(fields["research_dossier"], str):
            fields["research_dossier"] = json.dumps(fields["research_dossier"])
        fields["updated_at"] = datetime.now(UTC).isoformat()
        resp = cls.client().table("scenario_sessions").update(fields).eq("id", session_id).execute()
        row = resp.data[0] if resp.data else {}
        if row:
            cls._parse_session_json(row)
        return row

    @classmethod
    def _parse_session_json(cls, row: dict) -> None:
        for field in ("decision_context", "uploaded_files", "research_angles", "bundle_config", "research_dossier"):
            val = row.get(field)
            if isinstance(val, str):
                try:
                    row[field] = json.loads(val)
                except json.JSONDecodeError:
                    row[field] = {} if field != "uploaded_files" else []

    # -- session file storage --
    SESSION_FILES_BUCKET = "session-files"

    @classmethod
    def upload_session_file(cls, session_id: str, file_name: str, file_bytes: bytes, content_type: str) -> str:
        storage_path = f"{session_id}/{file_name}"
        cls.client().storage.from_(cls.SESSION_FILES_BUCKET).upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": content_type},
        )
        return storage_path

    @classmethod
    def get_session_file_url(cls, storage_path: str, expires_in: int = 3600) -> str:
        resp = cls.client().storage.from_(cls.SESSION_FILES_BUCKET).create_signed_url(storage_path, expires_in)
        return resp.get("signedURL", "") if isinstance(resp, dict) else ""

    @classmethod
    def delete_session_files(cls, session_id: str) -> None:
        try:
            listing = cls.client().storage.from_(cls.SESSION_FILES_BUCKET).list(session_id)
            if listing:
                paths = [f"{session_id}/{f['name']}" for f in listing]
                cls.client().storage.from_(cls.SESSION_FILES_BUCKET).remove(paths)
        except Exception:
            logger.warning(f"Failed to clean up session files for {session_id}")
