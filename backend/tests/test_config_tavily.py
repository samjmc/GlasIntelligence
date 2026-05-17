import sys
from unittest.mock import patch


def _reload_config(monkeypatch=None):
    # Remove cached module so env changes take effect
    for key in list(sys.modules.keys()):
        if "app.config" in key:
            del sys.modules[key]
    # Suppress load_dotenv so on-disk .env files don't override monkeypatched env vars.
    with patch("dotenv.load_dotenv"):
        import app.config as cfg
    return cfg


def test_tavily_api_key_from_env(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tv-test-key")
    cfg = _reload_config()
    assert cfg.Config.TAVILY_API_KEY == "tv-test-key"
    assert cfg.Config.SEARCH_RESEARCH_ENABLED is True


def test_tavily_disabled_when_no_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    cfg = _reload_config()
    assert cfg.Config.TAVILY_API_KEY == ""
    assert cfg.Config.SEARCH_RESEARCH_ENABLED is False


def test_tavily_max_rounds_default(monkeypatch):
    monkeypatch.delenv("SEARCH_RESEARCH_MAX_ROUNDS", raising=False)
    cfg = _reload_config()
    assert cfg.Config.SEARCH_RESEARCH_MAX_ROUNDS == 3


def test_tavily_quality_threshold_default(monkeypatch):
    monkeypatch.delenv("SEARCH_RESEARCH_QUALITY_THRESHOLD", raising=False)
    cfg = _reload_config()
    assert cfg.Config.SEARCH_RESEARCH_QUALITY_THRESHOLD == 7.5
