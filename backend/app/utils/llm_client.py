"""
LLM client wrapper — supports OpenAI-compatible APIs and Anthropic natively.

Auto-detects Anthropic keys (sk-ant-*) and routes through the Anthropic SDK;
everything else uses the OpenAI SDK with a configurable base_url.
"""

import json
import re
from typing import Any

from ..config import Config


def _is_anthropic_key(api_key: str) -> bool:
    return api_key.startswith("sk-ant-")


class LLMClient:
    """Unified LLM client — OpenAI-compatible providers and Anthropic."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None, model: str | None = None):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME

        if not self.api_key:
            raise ValueError("LLM_API_KEY not configured")

        self._anthropic = _is_anthropic_key(self.api_key)

        if self._anthropic:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=self.api_key)
        else:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> str:
        if self._anthropic:
            return self._chat_anthropic(messages, temperature, max_tokens, response_format)
        return self._chat_openai(messages, temperature, max_tokens, response_format)

    def _chat_openai(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        response_format: dict | None,
    ) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        response = self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        # Strip <think> reasoning blocks (e.g. MiniMax M2.5)
        content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
        return content

    def _chat_anthropic(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        response_format: dict | None,
    ) -> str:
        # Anthropic keeps system prompt separate from the messages array
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        user_messages = [m for m in messages if m["role"] != "system"]
        system = "\n\n".join(system_parts) if system_parts else None

        # Anthropic JSON mode: prepend instruction to system prompt
        if response_format and response_format.get("type") == "json_object":
            json_instruction = "Respond with valid JSON only. Do not include markdown code fences."
            system = f"{system}\n\n{json_instruction}" if system else json_instruction

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": user_messages,
        }
        if system:
            kwargs["system"] = system

        response = self._client.messages.create(**kwargs)
        return response.content[0].text

    def chat_json(
        self, messages: list[dict[str, str]], temperature: float = 0.3, max_tokens: int = 4096
    ) -> dict[str, Any]:
        response = self.chat(
            messages=messages, temperature=temperature, max_tokens=max_tokens, response_format={"type": "json_object"}
        )
        cleaned = response.strip()
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON format returned by LLM: {cleaned}")
