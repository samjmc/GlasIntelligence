"""Every direct chat.completions.create call must switch DeepSeek's reasoning off.

Live 2026-11-04: /source/auto-research (max_tokens=2500) returned 0 characters with
finish_reason=length, all 2500 tokens spent on hidden reasoning; with reasoning off the same
call returned 6148 characters in 1275 tokens. Persona and config generation made the same
uncapped call per agent. LLMClient and the Graphiti wrapper already disable it; raw-client
callers must pass no_thinking_kwargs(...) (or an explicit extra_body).
"""

from __future__ import annotations

import pathlib
import re

from app.utils.llm_client import no_thinking_kwargs

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
# Wrappers that set extra_body themselves before calling create(**kwargs)
HANDLED = {"llm_client.py", "graphiti_clients.py"}


def _create_calls(src: str):
    """Yield the argument text of each `.chat.completions.create(` call (balanced parens)."""
    for m in re.finditer(r"\.chat\.completions\.create\(", src):
        depth, i = 1, m.end()
        while depth and i < len(src):
            depth += {"(": 1, ")": -1}.get(src[i], 0)
            i += 1
        yield src[m.end() : i - 1]


def test_raw_create_calls_disable_reasoning():
    checked, missing = 0, []
    for path in APP.rglob("*.py"):
        if path.name in HANDLED:
            continue
        for args in _create_calls(path.read_text(encoding="utf-8")):
            checked += 1
            if "no_thinking_kwargs(" not in args and "extra_body" not in args:
                missing.append(path.name)
    assert checked >= 4, f"expected the raw create() calls to be found, checked {checked}"
    assert not missing, f"chat.completions.create without reasoning off in: {missing}"


def test_helper_only_targets_deepseek():
    assert no_thinking_kwargs("https://api.deepseek.com/v1") == {"extra_body": {"thinking": {"type": "disabled"}}}
    assert no_thinking_kwargs("https://api.openai.com/v1") == {}
    assert no_thinking_kwargs(None) == {}
