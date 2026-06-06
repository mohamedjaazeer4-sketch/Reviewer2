"""Provider-agnostic LLM layer (optional, summary-only).

Important design choice: **the LLM never makes the classification decision.** The
ACMG call and all conflicts come from deterministic code. The LLM is used *only* to
turn the structured dossier into a fluent natural-language summary. This keeps the
science reproducible and means a wrong/unavailable model can never change a verdict —
it just falls back to a deterministic template.

Supported providers (set ``REVIEWER2_LLM_PROVIDER``):
    ollama   (default, local)   — llama3.1 / mistral / qwen2.5 ...
    anthropic                   — claude-*
    openai                      — gpt-*
    gemini                      — gemini-*
    none / template             — deterministic template, zero dependencies

All cloud SDKs are optional extras; importing them is lazy so the core stays light.
"""

from __future__ import annotations

import os
from typing import Protocol


class LLMClient(Protocol):
    model_id: str

    def complete(self, system: str, prompt: str) -> str: ...


class TemplateClient:
    """Zero-dependency fallback. Returns the prompt's pre-rendered deterministic text.

    The pipeline passes a ready-made deterministic summary as the prompt; this client
    simply returns it, so behaviour is identical with or without a model available.
    """

    model_id = "template"

    def complete(self, system: str, prompt: str) -> str:
        return prompt


class OllamaClient:
    """Local models via Ollama's HTTP API. No API key, no cost."""

    def __init__(self, model: str, host: str) -> None:
        import httpx

        self.model_id = f"ollama:{model}"
        self._model = model
        self._host = host.rstrip("/")
        self._httpx = httpx

    def complete(self, system: str, prompt: str) -> str:
        resp = self._httpx.post(
            f"{self._host}/api/chat",
            json={
                "model": self._model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()


class AnthropicClient:
    def __init__(self, model: str, api_key: str) -> None:
        import anthropic

        self.model_id = f"anthropic:{model}"
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete(self, system: str, prompt: str) -> str:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in msg.content if block.type == "text").strip()


class OpenAIClient:
    def __init__(self, model: str, api_key: str) -> None:
        import openai

        self.model_id = f"openai:{model}"
        self._model = model
        self._client = openai.OpenAI(api_key=api_key)

    def complete(self, system: str, prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return (resp.choices[0].message.content or "").strip()


class GeminiClient:
    def __init__(self, model: str, api_key: str) -> None:
        from google import genai

        self.model_id = f"gemini:{model}"
        self._model = model
        self._client = genai.Client(api_key=api_key)

    def complete(self, system: str, prompt: str) -> str:
        resp = self._client.models.generate_content(
            model=self._model,
            contents=f"{system}\n\n{prompt}",
        )
        return (resp.text or "").strip()


def get_llm_client(provider: str | None = None) -> LLMClient:
    """Build the configured client, falling back to the template on any problem.

    We never raise from here: a portfolio demo must run even if Ollama isn't up or a
    key is missing. Failures degrade gracefully to the deterministic template.
    """
    provider = (provider or os.getenv("REVIEWER2_LLM_PROVIDER") or "ollama").lower()

    try:
        if provider in ("none", "template"):
            return TemplateClient()

        if provider == "ollama":
            return OllamaClient(
                model=os.getenv("REVIEWER2_OLLAMA_MODEL", "llama3.1"),
                host=os.getenv("REVIEWER2_OLLAMA_HOST", "http://localhost:11434"),
            )

        if provider == "anthropic":
            key = os.getenv("ANTHROPIC_API_KEY")
            if not key:
                return TemplateClient()
            return AnthropicClient(
                model=os.getenv("REVIEWER2_ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"),
                api_key=key,
            )

        if provider == "openai":
            key = os.getenv("OPENAI_API_KEY")
            if not key:
                return TemplateClient()
            return OpenAIClient(
                model=os.getenv("REVIEWER2_OPENAI_MODEL", "gpt-4o-mini"),
                api_key=key,
            )

        if provider == "gemini":
            key = os.getenv("GEMINI_API_KEY")
            if not key:
                return TemplateClient()
            return GeminiClient(
                model=os.getenv("REVIEWER2_GEMINI_MODEL", "gemini-1.5-flash"),
                api_key=key,
            )
    except Exception:
        # Any import/connection error -> deterministic fallback.
        return TemplateClient()

    return TemplateClient()
