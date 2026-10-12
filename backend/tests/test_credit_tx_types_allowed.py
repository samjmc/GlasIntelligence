"""Every credit_transactions type the app writes must be one the live database accepts.

The live CHECK constraint (read from Supabase 2026-10-12) allows only the types below.
billing.py wrote research_grant, research_purchase and overage AFTER adding the credits,
so the insert raised, the Stripe webhook failed, and Stripe's retries would have added
the credits again on every retry.
"""

from __future__ import annotations

import pathlib
import re

ALLOWED = {"purchase", "usage", "subscription_grant", "refund", "research_usage", "research_refund"}
APP = pathlib.Path(__file__).resolve().parents[1] / "app"
# insert_credit_tx(user, amount, "type", ...) — the type is the third argument
CALL = re.compile(r"insert_credit_tx\(\s*[^,]+,\s*[^,]+,\s*\"(\w+)\"", re.S)


def test_every_written_type_is_allowed_by_the_database():
    found = {}
    for path in APP.rglob("*.py"):
        for m in CALL.finditer(path.read_text(encoding="utf-8")):
            found.setdefault(m.group(1), []).append(path.name)

    assert len(found) >= 4, f"expected to find the app's credit writes, found {found}"
    bad = {t: files for t, files in found.items() if t not in ALLOWED}
    assert not bad, f"types the database CHECK constraint rejects: {bad}"
