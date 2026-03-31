"""Email notification service using Resend."""

import requests
from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('glas.email')

RESEND_API_URL = "https://api.resend.com/emails"


def send_email(to: str, subject: str, html: str) -> bool:
    api_key = Config.RESEND_API_KEY
    from_email = Config.RESEND_FROM_EMAIL

    if not api_key or not from_email:
        logger.warning("Resend not configured, skipping email")
        return False

    try:
        resp = requests.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": from_email,
                "to": [to],
                "subject": subject,
                "html": html,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info(f"Email sent to {to}: {subject}")
            return True
        else:
            logger.error(f"Email failed ({resp.status_code}): {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Email send error: {e}")
        return False


def _brand_wrapper(body_html: str) -> str:
    return f"""
    <div style="font-family: Inter, sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px; background: #0a0a0a; color: #e0e0e0;">
        <div style="text-align: center; margin-bottom: 30px;">
            <h1 style="color: #ffffff; letter-spacing: 0.2em; font-size: 18px;">GLAS INTELLIGENCE</h1>
        </div>
        {body_html}
        <p style="color: #888; font-size: 12px; margin-top: 40px;">
            Glas Intelligence provides structured scenario analysis. It does not issue forecasts or policy recommendations.
        </p>
    </div>
    """


def send_simulation_complete(to: str, simulation_id: str, report_url: str):
    html = _brand_wrapper(f"""
        <h2 style="color: #00c853; font-size: 20px;">Your Simulation is Complete</h2>
        <p>Your scenario simulation has finished processing. The full analysis report is ready to view.</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{report_url}" style="background: #00c853; color: #000; padding: 12px 32px; text-decoration: none; border-radius: 4px; font-weight: 600;">View Report</a>
        </div>
    """)
    send_email(to, "Your Glas Intelligence Report is Ready", html)


def send_credits_low(to: str, credits_remaining: int):
    html = _brand_wrapper(f"""
        <h2 style="color: #ff9800; font-size: 20px;">Low Simulation Balance</h2>
        <p>You have <strong>{credits_remaining}</strong> simulation(s) remaining.</p>
        <p>Purchase more simulations or upgrade your plan to keep running analyses.</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{Config.FRONTEND_URL}/pricing" style="background: #00c853; color: #000; padding: 12px 32px; text-decoration: none; border-radius: 4px; font-weight: 600;">View Plans</a>
        </div>
    """)
    send_email(to, "Low Simulation Balance - Glas Intelligence", html)


def send_welcome(to: str, display_name: str):
    html = _brand_wrapper(f"""
        <h2 style="color: #00c853; font-size: 20px;">Welcome, {display_name}!</h2>
        <p>Your account is ready. Browse our free industry intelligence feed, or upgrade to Pro or Business for custom simulations.</p>
        <p>Describe a scenario, upload documents, and let our multi-agent simulation engine show you how it plays out.</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{Config.FRONTEND_URL}" style="background: #00c853; color: #000; padding: 12px 32px; text-decoration: none; border-radius: 4px; font-weight: 600;">Start Your First Simulation</a>
        </div>
    """)
    send_email(to, "Welcome to Glas Intelligence", html)
