from __future__ import annotations

from doc_inspector.config import AppSettings


def test_server_defaults_to_localhost(monkeypatch) -> None:
    monkeypatch.delenv("GRADIO_SERVER_NAME", raising=False)
    monkeypatch.delenv("GRADIO_SERVER_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)

    settings = AppSettings(_env_file=None)

    assert settings.gradio_server_name == "127.0.0.1"
    assert settings.gradio_server_port == 7861


def test_hosted_server_settings_are_explicit(monkeypatch) -> None:
    monkeypatch.setenv("GRADIO_SERVER_NAME", "0.0.0.0")
    monkeypatch.setenv("PORT", "8080")

    settings = AppSettings(_env_file=None)

    assert settings.gradio_server_name == "0.0.0.0"
    assert settings.gradio_server_port == 8080
