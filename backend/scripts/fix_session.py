"""Fix the broken session that was marked completed with a degraded dossier."""
import json
import os
from supabase import create_client

url = os.environ["SUPABASE_URL"]
key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ["SUPABASE_KEY"]
c = create_client(url, key)

session_id = "4ee6ab9b-262f-4e37-b1a0-9829196dc730"

resp = c.table("scenario_sessions").update({
    "status": "active",
    "research_status": "failed",
    "research_dossier": None,
    "research_completed_at": None,
}).eq("id", session_id).execute()

if resp.data:
    print(f"Fixed session {session_id}: status=active, research_status=failed")
else:
    print(f"No rows updated for {session_id}")
