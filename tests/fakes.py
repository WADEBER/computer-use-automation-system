"""Shared fakes for Phase 5 tests. CI never opens network, Ollama or Chrome."""

from collections.abc import Callable


class FakeLLMClient:
    """Scripted LLM: pops queued string responses, or delegates to a handler."""

    def __init__(
        self,
        responses: list[str] | None = None,
        handler: Callable[[str], str] | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.handler = handler
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.handler is not None:
            return self.handler(prompt)
        if not self.responses:
            raise AssertionError("FakeLLMClient ran out of scripted responses")
        return self.responses.pop(0)
