"""Create the Stripe products, prices and webhook the app's billing code expects. Run by Sam.

    cd backend
    uv run --frozen python ../deploy/stripe_setup.py            # uses STRIPE_SECRET_KEY from the environment

Safe to run again: prices are found by `lookup_key` and the webhook by its URL, so nothing is
created twice. Prices are those on the Pricing page (USD). Change amounts in the Stripe
dashboard later if needed; the app only stores the price IDs.

Output: the price IDs (not secret) and, for a NEW webhook only, its signing secret, which this
script saves to your Windows user environment as STRIPE_WEBHOOK_SECRET without printing it.
The price IDs are saved the same way (STRIPE_PRICE_*), so deploy/push-secrets.ps1 sends them all.
"""

from __future__ import annotations

import os
import sys

import stripe

WEBHOOK_URL = os.environ.get("GLAS_WEBHOOK_URL", "https://app.glasinsight.com/api/billing/webhook")
WEBHOOK_EVENTS = ["checkout.session.completed", "invoice.paid", "customer.subscription.deleted"]

# env name -> (lookup_key, product name, amount in cents, monthly?)
PRICES = {
    "STRIPE_PRICE_PAYG": ("glas_payg", "Pay-as-you-go simulation", 3900, False),
    "STRIPE_PRICE_PRO": ("glas_pro_monthly", "Pro plan", 9900, True),
    "STRIPE_PRICE_BUSINESS": ("glas_business_monthly", "Business plan", 29900, True),
    "STRIPE_PRICE_PACK_5": ("glas_pack_5", "Simulation pack (5)", 5900, False),
    "STRIPE_PRICE_PACK_10": ("glas_pack_10", "Simulation pack (10)", 9900, False),
    "STRIPE_PRICE_OVERAGE_PRO": ("glas_overage_pro", "Extra simulation (Pro)", 1200, False),
    "STRIPE_PRICE_OVERAGE_BUSINESS": ("glas_overage_business", "Extra simulation (Business)", 1000, False),
    "STRIPE_PRICE_RESEARCH_1": ("glas_research_1", "Research briefing", 700, False),
    "STRIPE_PRICE_RESEARCH_5": ("glas_research_5", "Research briefings (5)", 3500, False),
}


def save_user_env(name: str, value: str) -> None:
    """Store in the Windows user environment (no value on any command line or in output)."""
    if os.name != "nt":
        return
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)


def main() -> int:
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not key:
        print("Set STRIPE_SECRET_KEY first (Stripe dashboard > Developers > API keys > Secret key).")
        return 1
    stripe.api_key = key
    mode = "LIVE" if key.startswith(("sk_live_", "rk_live_")) else "TEST"
    print(f"Stripe mode: {mode}")

    existing = {p.lookup_key: p for p in stripe.Price.list(lookup_keys=[v[0] for v in PRICES.values()], limit=100).data}
    for env_name, (lookup_key, name, amount, monthly) in PRICES.items():
        price = existing.get(lookup_key)
        if price is None:
            product = stripe.Product.create(name=f"Glas Intelligence: {name}")
            params = {"product": product.id, "currency": "usd", "unit_amount": amount, "lookup_key": lookup_key}
            if monthly:
                params["recurring"] = {"interval": "month"}
            price = stripe.Price.create(**params)
            print(f"  created {env_name} = {price.id}")
        else:
            print(f"  exists  {env_name} = {price.id}")
        save_user_env(env_name, price.id)

    hooks = [h for h in stripe.WebhookEndpoint.list(limit=100).data if h.url == WEBHOOK_URL]
    if hooks:
        print(
            f"Webhook exists for {WEBHOOK_URL} ({hooks[0].id}). If STRIPE_WEBHOOK_SECRET is not set yet, copy its"
            " signing secret from Stripe > Workbench > Webhooks into that user environment variable."
        )
    else:
        hook = stripe.WebhookEndpoint.create(url=WEBHOOK_URL, enabled_events=WEBHOOK_EVENTS)
        save_user_env("STRIPE_WEBHOOK_SECRET", hook.secret)
        print(f"Webhook created for {WEBHOOK_URL} ({hook.id}); signing secret saved to STRIPE_WEBHOOK_SECRET.")

    print("Done. Open a NEW PowerShell window (so it sees the new variables) and run deploy/push-secrets.ps1.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
