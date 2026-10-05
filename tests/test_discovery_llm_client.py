import os

from computer_use_automation_system.discovery.llm_client import OllamaClient


class FakeTransport:
    def __init__(self, content: str = "{}") -> None:
        self.content = content
        self.calls: list[tuple[str, list[dict[str, str]]]] = []

    def chat(self, model: str, messages: list[dict[str, str]]) -> str:
        self.calls.append((model, messages))
        return self.content


def test_complete_returns_transport_content() -> None:
    transport = FakeTransport(content='{"action": "click"}')
    client = OllamaClient(
        model="qwen2.5-coder:7b", base_url="http://localhost:11434", transport=transport
    )
    out = client.complete("do the thing")
    assert out == '{"action": "click"}'
    model, messages = transport.calls[0]
    assert model == "qwen2.5-coder:7b"
    assert messages == [{"role": "user", "content": "do the thing"}]


def test_complete_forwards_long_prompt_unchanged() -> None:
    transport = FakeTransport()
    client = OllamaClient(model="m", base_url="http://x", transport=transport)
    big = "GOAL: find it\nSNAPSHOT: " + "x" * 5000
    client.complete(big)
    assert transport.calls[0][1][0]["content"] == big


def test_model_defaults_come_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "env-model")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://env-host:11434")
    transport = FakeTransport()
    client = OllamaClient(transport=transport)
    client.complete("hi")
    assert transport.calls[0][0] == "env-model"
    assert client.base_url == "http://env-host:11434"


def test_explicit_arguments_win_over_environment(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_MODEL", "env-model")
    transport = FakeTransport()
    client = OllamaClient(model="explicit", base_url="http://explicit:1", transport=transport)
    client.complete("hi")
    assert transport.calls[0][0] == "explicit"


def test_env_defaults_without_env_fall_back_to_spec_values(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    client = OllamaClient(transport=FakeTransport())
    assert client.model == "qwen2.5-coder:7b"
    assert client.base_url == "http://localhost:11434"
    assert os.environ.get("OLLAMA_MODEL") in (None, client.model)


def test_live_transport_builds_one_client_with_an_explicit_timeout(monkeypatch) -> None:
    """One reused `ollama.Client` per transport, never the library default
    (`timeout=None` = wait forever)."""
    import sys
    import types

    class FakeClient:
        def __init__(self, host: str | None = None, timeout: float | None = None) -> None:
            self.host = host
            self.timeout = timeout
            instances.append(self)

        def chat(self, model: str, messages: list[dict[str, str]]) -> dict:
            return {"message": {"content": f"echo:{messages[0]['content']}"}}

    instances: list[FakeClient] = []

    fake_ollama = types.ModuleType("ollama")
    fake_ollama.Client = FakeClient  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "ollama", fake_ollama)

    client = OllamaClient(model="m", base_url="http://ollama:11434", timeout_s=123.0)
    assert client.complete("first") == "echo:first"
    assert client.complete("second") == "echo:second"

    assert len(instances) == 1
    assert instances[0].host == "http://ollama:11434"
    assert instances[0].timeout == 123.0
