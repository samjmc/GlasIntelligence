"""Jev client: request building per provider, answer parsing, retry, config gating. No network."""

import pytest

from app import config as app_config
from app.utils import jev_client as jc
from app.utils.jev_client import JevClient, JevError


class _Resp:
    def __init__(self, status: int, payload=None, text: str = ""):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


class _Session:
    """Scripted stand-in for requests.Session: pops one canned response per post."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return self.responses.pop(0)


CHOICE = {
    "type": "choice",
    "choice": "billing",
    "probabilities": {"billing": 0.85, "technical": 0.10, "sales": 0.05},
    "confidence": 0.82,
}
SCORE = {"type": "score", "score": 2.97, "probabilities": {"0": 0, "1": 0, "2": 0.03, "3": 0.97}, "confidence": 0.95}
NOUL = {"type": "noul", "noul": 0.9}
BOOLEAN = {"type": "boolean", "probability": 0.1}


def _client(provider="typesafe", responses=(), **kw):
    session = _Session(responses)
    account_id = "acct-123" if provider == "cloudflare" else None
    return JevClient(provider=provider, api_key="k", session=session, account_id=account_id, **kw), session


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(jc.time, "sleep", lambda _s: None)


# ---------------------------------------------------------------- request shapes


def test_typesafe_request_shape_and_choice_answer():
    client, session = _client(responses=[_Resp(200, {"answers": {"q": CHOICE}})])
    q = {"q": JevClient.choice_q("Route it", {"billing": "money", "technical": "bugs", "sales": "deals"})}

    answers = client.evaluate("state text", q)

    call = session.calls[0]
    assert call["url"] == "https://api.typesafe.ai/v1/systemone"
    assert call["json"] == {"model": "jev-latest", "state": "state text", "questions": q}
    assert call["headers"]["Authorization"] == "Bearer k"
    assert answers["q"].kind == "choice"
    assert answers["q"].value == "billing"
    assert answers["q"].confidence == 0.82
    assert answers["q"].probabilities["technical"] == 0.10


def test_cloudflare_wraps_input_and_unwraps_result_envelope():
    envelope = {"result": {"model": "jev-1.13.0", "answers": {"q": CHOICE}}, "success": True, "errors": []}
    client, session = _client("cloudflare", responses=[_Resp(200, envelope)])
    q = {"q": JevClient.choice_q("Route it", {"billing": "", "technical": "", "sales": ""})}

    answers = client.evaluate("s", q)

    call = session.calls[0]
    assert call["url"] == "https://api.cloudflare.com/client/v4/accounts/acct-123/ai/run"
    assert call["json"] == {"model": "typesafe/jev", "input": {"state": "s", "questions": q}}
    assert answers["q"].value == "billing"


def test_cloudflare_double_wrapped_job_envelope_is_unwrapped():
    """Measured live 2026-09-21: Cloudflare returns {result: {state: Completed, result: {answers}}}."""
    live_shape = {
        "result": {"state": "Completed", "result": {"model": "jev-1.13.0", "answers": {"q": CHOICE}}},
        "success": True,
        "errors": [],
        "messages": [],
    }
    client, _ = _client("cloudflare", responses=[_Resp(200, live_shape)])
    assert client.evaluate("s", {"q": JevClient.choice_q("i", {"billing": ""})})["q"].value == "billing"


def test_cloudflare_incomplete_job_state_raises_clearly():
    pending = {"result": {"state": "Queued", "result": {}}, "success": True}
    client, _ = _client("cloudflare", responses=[_Resp(200, pending)])
    with pytest.raises(JevError, match="state='Queued'"):
        client.evaluate("s", {"q": JevClient.noul_q("i")})


def test_cloudflare_also_accepts_unwrapped_native_response():
    client, _ = _client("cloudflare", responses=[_Resp(200, {"answers": {"q": CHOICE}})])
    assert client.evaluate("s", {"q": JevClient.choice_q("i", {"billing": ""})})["q"].value == "billing"


def test_vercel_translates_noul_to_boolean_both_ways():
    client, session = _client("vercel", responses=[_Resp(200, {"answers": {"yes": BOOLEAN, "pick": CHOICE}})])
    q = {"yes": JevClient.noul_q("Is it?"), "pick": JevClient.choice_q("Which", {"billing": ""})}

    answers = client.evaluate("s", q)

    call = session.calls[0]
    assert call["url"] == "https://ai-gateway.vercel.sh/v1/evaluate"
    assert call["json"]["model"] == "typesafe-ai/jev"
    assert call["json"]["questions"]["yes"]["type"] == "boolean"
    assert call["json"]["questions"]["pick"]["type"] == "choice"
    assert answers["yes"].kind == "noul"
    assert answers["yes"].value == 0.1
    assert answers["yes"].confidence == pytest.approx(0.9)


def test_cloudflare_requires_account_id():
    with pytest.raises(ValueError, match="CLOUDFLARE_ACCOUNT_ID"):
        JevClient(provider="cloudflare", api_key="k", session=_Session([]))


def test_unknown_provider_rejected():
    with pytest.raises(ValueError, match="JEV_PROVIDER"):
        JevClient(provider="openai", api_key="k", session=_Session([]))


# ---------------------------------------------------------------- answer parsing


def test_score_answer_level_and_confidence():
    client, _ = _client(responses=[_Resp(200, {"answers": {"q": SCORE}})])
    a = client.evaluate("s", {"q": JevClient.score_q("rate", ["a", "b", "c", "d"])})["q"]
    assert a.kind == "score"
    assert a.value == 2.97
    assert a.level == 3
    assert a.confidence == 0.95


def test_native_noul_confidence_is_distance_from_coin_flip():
    client, _ = _client(responses=[_Resp(200, {"answers": {"q": NOUL}})])
    a = client.evaluate("s", {"q": JevClient.noul_q("is?")})["q"]
    assert a.value == 0.9
    assert a.confidence == pytest.approx(0.9)


def test_choice_without_confidence_falls_back_to_its_probability():
    raw = {k: v for k, v in CHOICE.items() if k != "confidence"}
    client, _ = _client(responses=[_Resp(200, {"answers": {"q": raw}})])
    assert client.evaluate("s", {"q": JevClient.choice_q("i", {"billing": ""})})["q"].confidence == 0.85


def test_missing_answers_map_raises():
    client, _ = _client(responses=[_Resp(200, {"model": "jev"})])
    with pytest.raises(JevError, match="no answers"):
        client.evaluate("s", {"q": JevClient.noul_q("i")})


def test_score_q_level_count_bounds():
    with pytest.raises(ValueError):
        JevClient.score_q("i", ["only one"])
    with pytest.raises(ValueError):
        JevClient.score_q("i", [str(i) for i in range(11)])
    assert len(JevClient.score_q("i", ["a", "b"])["criteria"]) == 2


# ---------------------------------------------------------------- retry


def test_retries_429_then_succeeds():
    client, session = _client(responses=[_Resp(429, text="slow down"), _Resp(200, {"answers": {"q": NOUL}})])
    assert client.evaluate("s", {"q": JevClient.noul_q("i")})["q"].value == 0.9
    assert len(session.calls) == 2


def test_401_is_not_retried():
    client, session = _client(responses=[_Resp(401, text="bad key")])
    with pytest.raises(JevError, match="HTTP 401"):
        client.evaluate("s", {"q": JevClient.noul_q("i")})
    assert len(session.calls) == 1


def test_retries_exhausted_raise():
    client, session = _client(responses=[_Resp(529), _Resp(529), _Resp(529)])
    with pytest.raises(JevError, match="after 3 attempts"):
        client.evaluate("s", {"q": JevClient.noul_q("i")})
    assert len(session.calls) == 3


# ---------------------------------------------------------------- evaluate_many


def test_evaluate_many_preserves_order_and_isolates_failures():
    client, session = _client(
        responses=[
            _Resp(200, {"answers": {"q": CHOICE}}),
            _Resp(400, text="validation"),
            _Resp(200, {"answers": {"q": SCORE}}),
        ]
    )
    items = [("a", {"q": JevClient.choice_q("i", {"billing": ""})})] * 3

    out = client.evaluate_many(items, max_workers=1)  # serial so the scripted responses line up

    assert len(out) == 3
    assert out[0]["q"].value == "billing"
    assert out[1] is None
    assert out[2]["q"].level == 3
    assert len(session.calls) == 3


def test_evaluate_many_empty():
    client, _ = _client()
    assert client.evaluate_many([]) == []


# ---------------------------------------------------------------- config gating


def test_from_config_none_when_disabled(monkeypatch):
    monkeypatch.setattr(app_config.Config, "JEV_ENABLED", False)
    monkeypatch.setattr(app_config.Config, "JEV_API_KEY", "k")
    assert JevClient.from_config() is None


def test_from_config_none_without_key(monkeypatch):
    monkeypatch.setattr(app_config.Config, "JEV_ENABLED", True)
    monkeypatch.setattr(app_config.Config, "JEV_API_KEY", "")
    assert JevClient.from_config() is None


def test_from_config_none_for_cloudflare_without_account(monkeypatch):
    monkeypatch.setattr(app_config.Config, "JEV_ENABLED", True)
    monkeypatch.setattr(app_config.Config, "JEV_API_KEY", "k")
    monkeypatch.setattr(app_config.Config, "JEV_PROVIDER", "cloudflare")
    monkeypatch.setattr(app_config.Config, "CLOUDFLARE_ACCOUNT_ID", "")
    assert JevClient.from_config() is None


def test_from_config_builds_provider_client(monkeypatch):
    monkeypatch.setattr(app_config.Config, "JEV_ENABLED", True)
    monkeypatch.setattr(app_config.Config, "JEV_API_KEY", "k")
    monkeypatch.setattr(app_config.Config, "JEV_PROVIDER", "vercel")
    monkeypatch.setattr(app_config.Config, "JEV_MODEL", "")
    monkeypatch.setattr(app_config.Config, "JEV_BASE_URL", "")
    client = JevClient.from_config()
    assert client is not None
    assert client.provider == "vercel"
    assert client.model == "typesafe-ai/jev"
    assert client.base_url == "https://ai-gateway.vercel.sh"
