"""Agent model config: DeepSeek thinking mode must be off (it 400s multi-turn CAMEL agents)."""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "lib"))

model_factory = pytest.importorskip("model_factory")


def test_deepseek_disables_thinking():
    cfg = model_factory.openai_model_config("https://api.deepseek.com/v1")
    assert cfg["extra_body"] == {"thinking": {"type": "disabled"}}


def test_other_providers_untouched():
    for url in ("https://api.openai.com/v1", "", None):
        assert "extra_body" not in model_factory.openai_model_config(url)


def test_create_model_passes_config_for_deepseek(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "deepseek-flash")
    monkeypatch.delenv("LLM_BOOST_API_KEY", raising=False)
    with patch.object(model_factory.ModelFactory, "create", return_value="model") as create:
        assert model_factory.create_model({}) == "model"
    kwargs = create.call_args.kwargs
    assert kwargs["model_type"] == "deepseek-flash"
    assert kwargs["model_config_dict"]["extra_body"] == {"thinking": {"type": "disabled"}}
