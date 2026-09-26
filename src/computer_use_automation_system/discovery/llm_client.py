"""Ollama adapter behind the `LLMClient` protocol (Phase 5).

The transport is injectable so tests never import or contact Ollama; the
real transport is constructed lazily on first use. Model and base URL come
from explicit arguments, then `OLLAMA_*` env vars, then spec defaults.
"""

import os
from typing import Protocol

DEFAULT_MODEL = "qwen2.5-coder:7b"
DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaTransport(Protocol):
    """Minimal transport: prompt in, text out."""

    def chat(self, model: str, messages: list[dict[str, str]]) -> str: ...


class _LiveOllamaTransport:
    """Talks to a local Ollama server. Imported lazily (CI never loads it)."""

    def __init__(self, host: str) -> None:
        self.host = host

    def chat(self, model: str, messages: list[dict[str, str]]) -> str:
        import ollama

        client = ollama.Client(host=self.host)
        response = client.chat(model=model, messages=messages)
        try:
            return str(response["message"]["content"])
        except (KeyError, TypeError):
            return str(response.message.content)


class OllamaClient:
    """`LLMClient` implementation for the real discovery runs."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        transport: OllamaTransport | None = None,
    ) -> None:
        self.model = model or os.environ.get("OLLAMA_MODEL") or DEFAULT_MODEL
        self.base_url = base_url or os.environ.get("OLLAMA_BASE_URL") or DEFAULT_BASE_URL
        self._transport = transport

    def complete(self, prompt: str) -> str:
        if self._transport is None:
            self._transport = _LiveOllamaTransport(self.base_url)
        return self._transport.chat(self.model, [{"role": "user", "content": prompt}])
