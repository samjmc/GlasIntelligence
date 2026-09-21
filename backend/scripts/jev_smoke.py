"""Smoke-test the Jev connection using the JEV_* settings from .env.

Sends one small typed evaluation and prints the answers. Prints only derived
facts about the credential (provider, key length) — never the key itself.

    cd backend && uv run --frozen python scripts/jev_smoke.py

Exit code 0 = Jev answered; 1 = not configured; 2 = the call failed.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.jev_client import JevClient, JevError  # noqa: E402

STATE = (
    "Independent pharmacy contractor, 3 branches. Says the new Pharmacy First payment cap "
    "means the service no longer covers staff time and it will stop offering consultations "
    "from next quarter unless the cap is lifted."
)

QUESTIONS = {
    "stance": JevClient.choice_q(
        "What is this actor's stance on the payment cap?",
        {"supportive": "backs the cap", "opposing": "wants it lifted", "neutral": "no clear view"},
    ),
    "intensity": JevClient.score_q(
        "How strongly held is that stance?",
        ["1 - weak", "2 - mild", "3 - moderate", "4 - strong", "5 - extreme"],
    ),
    "will_exit": JevClient.noul_q("Will this actor withdraw from the service?"),
}


def main() -> int:
    client = JevClient.from_config()
    if client is None:
        print(
            "Jev is not configured. In the repo-root .env set JEV_ENABLED=true, JEV_API_KEY, "
            "JEV_PROVIDER (typesafe | cloudflare | vercel) and, for cloudflare, CLOUDFLARE_ACCOUNT_ID."
        )
        return 1

    print(f"provider={client.provider} model={client.model} base_url={client.base_url} key_len={len(client.api_key)}")
    try:
        answers = client.evaluate(STATE, QUESTIONS)
    except JevError as e:
        print(f"Jev call FAILED: {e}")
        return 2

    for name, a in answers.items():
        value = f"{a.value:.3f}" if isinstance(a.value, float) else a.value
        print(f"  {name:<10} {a.kind:<7} value={value:<12} confidence={a.confidence:.2f}")
    print("OK - Jev answered.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
