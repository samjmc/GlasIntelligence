"""Quick diagnostic: list recent scenario sessions."""
import json
import os
from supabase import create_client

url = os.environ["SUPABASE_URL"]
key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ["SUPABASE_KEY"]
c = create_client(url, key)

rows = (
    c.table("scenario_sessions")
    .select("id,status,research_status,created_at")
    .order("created_at", desc=True)
    .limit(5)
    .execute()
)
for r in rows.data:
    print(json.dumps(r))
