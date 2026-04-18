"""Stripe billing API routes."""

import stripe
from flask import Blueprint, request, jsonify, g
from ..middleware.auth import require_auth
from ..services.supabase_client import SupabaseDB
from ..config import Config
from ..utils.logger import get_logger
from datetime import UTC

billing_bp = Blueprint("billing", __name__)
logger = get_logger("glas.api.billing")

stripe.api_key = Config.STRIPE_SECRET_KEY

PRICE_IDS = {
    "payg": Config.STRIPE_PRICE_PAYG,
    "pro": Config.STRIPE_PRICE_PRO,
    "business": Config.STRIPE_PRICE_BUSINESS,
    "pack_5": Config.STRIPE_PRICE_PACK_5,
    "pack_10": Config.STRIPE_PRICE_PACK_10,
    "overage_pro": Config.STRIPE_PRICE_OVERAGE_PRO,
    "overage_business": Config.STRIPE_PRICE_OVERAGE_BUSINESS,
    "research_1": Config.STRIPE_PRICE_RESEARCH_1,
    "research_5": Config.STRIPE_PRICE_RESEARCH_5,
}

SUBSCRIPTION_PLANS = {"pro", "business"}

SUBSCRIPTION_SIMULATIONS = {
    "pro": 10,
    "business": 40,
}

SUBSCRIPTION_RESEARCH = {
    "pro": 3,
    "business": 13,
    "enterprise": 33,
}

PACK_QUANTITIES = {
    "pack_5": 5,
    "pack_10": 10,
}

PACK_RESEARCH = {
    "pack_5": 2,
    "pack_10": 5,
}

RESEARCH_PRODUCTS = {
    "research_1": 1,
    "research_5": 5,
}


@billing_bp.route("/checkout", methods=["POST"])
@require_auth
def create_checkout():
    """Create a Stripe Checkout session for subscription, one-off, or pack purchase."""
    if not stripe.api_key:
        return jsonify({"success": False, "error": "Billing not configured"}), 503

    data = request.get_json() or {}
    product = data.get("product")

    if product not in PRICE_IDS or not PRICE_IDS.get(product):
        return jsonify({"success": False, "error": f"Unknown product: {product}"}), 400

    price_id = PRICE_IDS[product]
    mode = "subscription" if product in SUBSCRIPTION_PLANS else "payment"

    profile = SupabaseDB.get_profile(g.user_id)
    customer_id = profile.get("stripe_customer_id") if profile else None

    session_id_param = data.get("session_id", "")

    if product in RESEARCH_PRODUCTS and session_id_param:
        success_url = Config.FRONTEND_URL + f"/?session={session_id_param}&billing=success&auto_research=true"
        cancel_url = Config.FRONTEND_URL + f"/?session={session_id_param}&billing=cancelled"
    else:
        success_url = Config.FRONTEND_URL + "/dashboard?billing=success"
        cancel_url = Config.FRONTEND_URL + "/pricing?billing=cancelled"

    try:
        session_params = {
            "payment_method_types": ["card"],
            "line_items": [{"price": price_id, "quantity": 1}],
            "mode": mode,
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": g.user_id,
            "metadata": {"user_id": g.user_id, "product": product},
        }

        if customer_id:
            session_params["customer"] = customer_id
        else:
            session_params["customer_email"] = g.user_email

        session = stripe.checkout.Session.create(**session_params)

        return jsonify({"success": True, "data": {"url": session.url, "session_id": session.id}})
    except stripe.error.StripeError as e:
        logger.error(f"Stripe checkout failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@billing_bp.route("/portal", methods=["POST"])
@require_auth
def customer_portal():
    """Create a Stripe Customer Portal session for managing subscription."""
    if not stripe.api_key:
        return jsonify({"success": False, "error": "Billing not configured"}), 503

    profile = SupabaseDB.get_profile(g.user_id)
    customer_id = profile.get("stripe_customer_id") if profile else None

    if not customer_id:
        return jsonify({"success": False, "error": "No billing account found"}), 404

    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=Config.FRONTEND_URL + "/dashboard",
        )
        return jsonify({"success": True, "data": {"url": session.url}})
    except stripe.error.StripeError as e:
        return jsonify({"success": False, "error": str(e)}), 500


@billing_bp.route("/webhook", methods=["POST"])
def stripe_webhook():
    """Handle Stripe webhook events."""
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")
    webhook_secret = Config.STRIPE_WEBHOOK_SECRET

    if not webhook_secret:
        return jsonify({"error": "Webhook not configured"}), 503

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        logger.warning(f"Webhook verification failed: {e}")
        return jsonify({"error": "Invalid signature"}), 400

    event_type = event["type"]
    data = event["data"]["object"]

    logger.info(f"Stripe webhook: {event_type}")

    if event_type == "checkout.session.completed":
        _handle_checkout_complete(data)
    elif event_type == "invoice.paid":
        _handle_invoice_paid(data)
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_cancelled(data)

    return jsonify({"received": True})


def _handle_checkout_complete(session):
    user_id = session.get("client_reference_id") or session.get("metadata", {}).get("user_id")
    product = session.get("metadata", {}).get("product", "")
    customer_id = session.get("customer")

    if not user_id:
        logger.warning("Checkout completed but no user_id found")
        return

    SupabaseDB.update_profile(user_id, stripe_customer_id=customer_id)

    if product in SUBSCRIPTION_SIMULATIONS:
        grant = SUBSCRIPTION_SIMULATIONS[product]
        research_grant = SUBSCRIPTION_RESEARCH.get(product, 0)
        profile = SupabaseDB.get_profile(user_id)
        current = profile.get("credits", 0) if profile else 0
        current_research = profile.get("research_credits", 0) if profile else 0
        SupabaseDB.update_profile(
            user_id,
            plan=product,
            credits=current + grant,
            research_credits=current_research + research_grant,
        )
        SupabaseDB.insert_credit_tx(user_id, grant, "subscription_grant", f"{product.title()} plan activated")
        if research_grant:
            SupabaseDB.insert_credit_tx(
                user_id,
                research_grant,
                "research_grant",
                f"{product.title()} plan — {research_grant} research briefings",
            )
        logger.info(f"Subscription activated: {user_id} -> {product} ({grant} sims, {research_grant} research)")

    elif product == "payg":
        profile = SupabaseDB.get_profile(user_id)
        current = profile.get("credits", 0) if profile else 0
        current_research = profile.get("research_credits", 0) if profile else 0
        SupabaseDB.update_profile(user_id, credits=current + 1, research_credits=current_research + 1)
        SupabaseDB.insert_credit_tx(user_id, 1, "purchase", "Pay-as-you-go simulation")
        SupabaseDB.insert_credit_tx(user_id, 1, "research_grant", "Pay-as-you-go research briefing")
        logger.info(f"PAYG purchased: {user_id} +1 sim, +1 research")

    elif product in PACK_QUANTITIES:
        qty = PACK_QUANTITIES[product]
        research_qty = PACK_RESEARCH.get(product, 0)
        profile = SupabaseDB.get_profile(user_id)
        current = profile.get("credits", 0) if profile else 0
        current_research = profile.get("research_credits", 0) if profile else 0
        SupabaseDB.update_profile(user_id, credits=current + qty, research_credits=current_research + research_qty)
        SupabaseDB.insert_credit_tx(user_id, qty, "purchase", f"Simulation pack ({qty})")
        if research_qty:
            SupabaseDB.insert_credit_tx(
                user_id, research_qty, "research_grant", f"Simulation pack — {research_qty} research briefings"
            )
        logger.info(f"Pack purchased: {user_id} +{qty} sims, +{research_qty} research")

    elif product in RESEARCH_PRODUCTS:
        qty = RESEARCH_PRODUCTS[product]
        profile = SupabaseDB.get_profile(user_id)
        current_research = profile.get("research_credits", 0) if profile else 0
        SupabaseDB.update_profile(user_id, research_credits=current_research + qty)
        SupabaseDB.insert_credit_tx(user_id, qty, "research_purchase", f"Research briefing purchase ({qty})")
        logger.info(f"Research purchased: {user_id} +{qty} research credits")

    elif product.startswith("overage_"):
        profile = SupabaseDB.get_profile(user_id)
        current = profile.get("credits", 0) if profile else 0
        SupabaseDB.update_profile(user_id, credits=current + 1)
        SupabaseDB.insert_credit_tx(user_id, 1, "overage", f"Overage simulation ({product})")
        logger.info(f"Overage simulation: {user_id} +1")


def _handle_invoice_paid(invoice):
    customer_id = invoice.get("customer")
    if not customer_id:
        return

    profiles = SupabaseDB.client().table("profiles").select("*").eq("stripe_customer_id", customer_id).execute()
    if not profiles.data:
        return

    profile = profiles.data[0]
    user_id = profile["id"]
    plan = Config.normalize_plan(profile.get("plan", "free"))

    sims = SUBSCRIPTION_SIMULATIONS.get(plan, 0)
    research = SUBSCRIPTION_RESEARCH.get(plan, 0)
    if sims > 0:
        SupabaseDB.update_profile(user_id, credits=sims, research_credits=research)
        SupabaseDB.insert_credit_tx(user_id, sims, "subscription_grant", f"Monthly {plan} renewal ({sims} simulations)")
        if research:
            SupabaseDB.insert_credit_tx(
                user_id, research, "research_grant", f"Monthly {plan} renewal ({research} research briefings)"
            )
        logger.info(f"Subscription renewed: {user_id} -> {sims} sims, {research} research")


def _handle_subscription_cancelled(subscription):
    customer_id = subscription.get("customer")
    if not customer_id:
        return

    profiles = SupabaseDB.client().table("profiles").select("*").eq("stripe_customer_id", customer_id).execute()
    if not profiles.data:
        return

    user_id = profiles.data[0]["id"]
    SupabaseDB.update_profile(user_id, plan="free", research_credits=0)
    logger.info(f"Subscription cancelled: {user_id} -> free (research credits zeroed)")


@billing_bp.route("/status", methods=["GET"])
@require_auth
def billing_status():
    """Get current user's billing status."""
    profile = SupabaseDB.get_profile(g.user_id)
    if not profile:
        return jsonify({"success": True, "data": {"plan": "free", "credits": 0, "research_credits": 0}})

    return jsonify(
        {
            "success": True,
            "data": {
                "plan": Config.normalize_plan(profile.get("plan", "free")),
                "credits": profile.get("credits", 0),
                "research_credits": profile.get("research_credits", 0),
                "has_billing": bool(profile.get("stripe_customer_id")),
            },
        }
    )


@billing_bp.route("/can-research", methods=["GET"])
@require_auth
def can_research():
    """Pre-flight check for research eligibility."""
    profile = SupabaseDB.get_profile(g.user_id)
    plan = Config.normalize_plan(profile.get("plan", "free") if profile else "free")
    research_credits = profile.get("research_credits", 0) if profile else 0

    return jsonify(
        {
            "success": True,
            "data": {
                "can_research": research_credits > 0,
                "research_credits": research_credits,
                "plan": plan,
            },
        }
    )


@billing_bp.route("/can-simulate", methods=["GET"])
@require_auth
def can_simulate():
    """Lightweight pre-flight check for simulation eligibility."""
    profile = SupabaseDB.get_profile(g.user_id)
    plan = Config.normalize_plan(profile.get("plan", "free") if profile else "free")
    credits = profile.get("credits", 0) if profile else 0

    can_run = credits > 0
    if not can_run and plan == "free":
        can_run = _has_free_simulation_remaining(g.user_id)

    return jsonify(
        {
            "success": True,
            "data": {
                "can_simulate": can_run,
                "credits": credits,
                "plan": plan,
            },
        }
    )


def _has_free_simulation_remaining(user_id):
    """Check if a free-tier user has their 1 monthly simulation remaining."""
    from datetime import datetime

    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    try:
        result = (
            SupabaseDB.client()
            .table("credit_transactions")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .gte("created_at", month_start)
            .in_("type", ["usage"])
            .execute()
        )
        used = result.count if result.count is not None else len(result.data or [])
        return used < 1
    except Exception as e:
        logger.warning(f"Free simulation check failed for {user_id}: {e}")
        return False
