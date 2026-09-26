from proxy_app.app import resolve_config


def test_resolve_config_defaults(monkeypatch) -> None:
    monkeypatch.delenv("PROXY_APP_HOST", raising=False)
    monkeypatch.delenv("PROXY_APP_PORT", raising=False)
    monkeypatch.delenv("PROXY_APP_DEBUG", raising=False)
    host, port, debug = resolve_config()
    assert host == "127.0.0.1"
    assert port == 5000
    assert debug is False


def test_resolve_config_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("PROXY_APP_HOST", "0.0.0.0")
    monkeypatch.setenv("PROXY_APP_PORT", "8080")
    monkeypatch.setenv("PROXY_APP_DEBUG", "true")
    host, port, debug = resolve_config()
    assert host == "0.0.0.0"
    assert port == 8080
    assert debug is True
