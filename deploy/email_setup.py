"""Send Supabase sign-up and reset emails through Resend instead of Supabase's test mailer. Run by Sam.

Supabase's built-in mailer sends only a few emails an hour, so new sign-ups wait for their
confirmation link. This points the shared Supabase project (GlasCore: GlasApp + Glas
Intelligence) at Resend's SMTP server.

    cd backend
    uv run --frozen python ../deploy/email_setup.py domain     # 1. add glasinsight.com to Resend, print DNS records
    #    add the printed records in Cloudflare (DNS only), wait a few minutes
    uv run --frozen python ../deploy/email_setup.py verify     # 2. ask Resend to check the records
    uv run --frozen python ../deploy/email_setup.py smtp       # 3. point Supabase auth email at Resend

Needs in the environment: RESEND_API_KEY (Resend > API Keys, "Sending access") and, for step 3,
SUPABASE_ACCESS_TOKEN (Supabase > Account > Access Tokens). Keys are read from the environment
only; nothing secret is printed.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

DOMAIN = "glasinsight.com"
SENDER = f"noreply@{DOMAIN}"
SENDER_NAME = "Glas"
SUPABASE_REF = "ihecemdupqnxltdyebsh"
EMAILS_PER_HOUR = 30


def _call(method: str, url: str, token: str, body: dict | None = None) -> tuple[int, dict | list | str]:
    req = urllib.request.Request(
        url,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "glas-setup"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]


def _env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        sys.exit(f"Set {name} first.")
    return value


def _resend_domain(key: str) -> dict | None:
    code, body = _call("GET", "https://api.resend.com/domains", key)
    if code != 200 or not isinstance(body, dict):
        sys.exit(f"Resend list domains failed: {code} {body}")
    return next((d for d in body.get("data", []) if d.get("name") == DOMAIN), None)


def domain() -> None:
    key = _env("RESEND_API_KEY")
    d = _resend_domain(key)
    if d is None:
        code, d = _call("POST", "https://api.resend.com/domains", key, {"name": DOMAIN, "region": "eu-west-1"})
        if code not in (200, 201) or not isinstance(d, dict):
            sys.exit(f"Resend add domain failed: {code} {d}")
    code, full = _call("GET", f"https://api.resend.com/domains/{d['id']}", key)
    if code != 200 or not isinstance(full, dict):
        sys.exit(f"Resend get domain failed: {code} {full}")
    print(f"Domain {DOMAIN}: status {full.get('status')}. Add these records in Cloudflare (Proxy: DNS only):")
    for r in full.get("records", []):
        prio = f"  priority {r['priority']}" if r.get("priority") is not None else ""
        print(f"  {r.get('type'):5} {r.get('name'):35} {r.get('value')}{prio}   [{r.get('status')}]")


def verify() -> None:
    key = _env("RESEND_API_KEY")
    d = _resend_domain(key) or sys.exit("Run the 'domain' step first.")
    code, _ = _call("POST", f"https://api.resend.com/domains/{d['id']}/verify", key)
    print(f"Verify requested: {code}. Run 'domain' again in a few minutes to see each record's status.")


def smtp() -> None:
    key = _env("RESEND_API_KEY")
    token = _env("SUPABASE_ACCESS_TOKEN")
    d = _resend_domain(key)
    if not d or d.get("status") != "verified":
        sys.exit(f"{DOMAIN} is not verified in Resend yet (status: {d and d.get('status')}). Run 'verify' first.")
    config = {
        "smtp_host": "smtp.resend.com",
        "smtp_port": "465",
        "smtp_user": "resend",
        "smtp_pass": key,
        "smtp_admin_email": SENDER,
        "smtp_sender_name": SENDER_NAME,
        "rate_limit_email_sent": EMAILS_PER_HOUR,
    }
    url = f"https://api.supabase.com/v1/projects/{SUPABASE_REF}/config/auth"
    code, body = _call("PATCH", url, token, config)
    if code != 200:
        sys.exit(f"Supabase update failed: {code} {body}")
    code, cfg = _call("GET", url, token)
    if code != 200 or not isinstance(cfg, dict):
        sys.exit(f"Supabase read-back failed: {code}")
    print(
        f"Supabase auth email now: host={cfg.get('smtp_host')} sender={cfg.get('smtp_admin_email')} "
        f"name={cfg.get('smtp_sender_name')} limit={cfg.get('rate_limit_email_sent')}/hour"
    )


if __name__ == "__main__":
    steps = {"domain": domain, "verify": verify, "smtp": smtp}
    if len(sys.argv) != 2 or sys.argv[1] not in steps:
        sys.exit(f"Usage: email_setup.py {'|'.join(steps)}")
    steps[sys.argv[1]]()
