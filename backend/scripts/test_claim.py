import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.chdir(os.path.join(os.path.dirname(__file__), ".."))
from app.services.supabase_client import SupabaseDB

SID = "4ee6ab9b-262f-4e37-b1a0-9829196dc730"
sb = SupabaseDB.client()

# Check current state
s = sb.table("scenario_sessions").select("id,research_status").eq("id", SID).execute()
print("current:", s.data)

# Test 1: .or_() filter on update
print("\nTest 1: .or_() filter")
r1 = sb.table("scenario_sessions").update({"research_status": "claiming"}).eq("id", SID).or_("research_status.is.null,research_status.eq.none,research_status.eq.failed").execute()
print("result:", r1.data)

# Reset
sb.table("scenario_sessions").update({"research_status": None}).eq("id", SID).execute()

# Test 2: simple update without filter (baseline)
print("\nTest 2: no filter (baseline)")
r2 = sb.table("scenario_sessions").update({"research_status": "claiming"}).eq("id", SID).execute()
print("result:", r2.data)

# Reset
sb.table("scenario_sessions").update({"research_status": None}).eq("id", SID).execute()

# Test 3: .is_() filter for null
print("\nTest 3: .is_() filter")
r3 = sb.table("scenario_sessions").update({"research_status": "claiming"}).eq("id", SID).is_("research_status", "null").execute()
print("result:", r3.data)

# Reset
sb.table("scenario_sessions").update({"research_status": None}).eq("id", SID).execute()

# Test 4: filter with .or_ with just is.null
print("\nTest 4: .or_() with just is.null")
r4 = sb.table("scenario_sessions").update({"research_status": "claiming"}).eq("id", SID).or_("research_status.is.null").execute()
print("result:", r4.data)

# Reset
sb.table("scenario_sessions").update({"research_status": None}).eq("id", SID).execute()

print("\nDone - session reset to NULL")
