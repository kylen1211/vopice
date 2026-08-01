"""Unit tests for server.config.load_config (R5 / P25)."""

import pytest

from config import ConfigError, load_config

REQUIRED_ENV = {
    "LLM_BASE_URL": "http://127.0.0.1:8045/v1",
    "LLM_API_KEY": "sk-test-key",
    "LLM_MODEL": "gemini-3.6-flash-high",
}


def _set_required_env(monkeypatch):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)


def test_missing_key_lists_all_missing(monkeypatch):
    for key in REQUIRED_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LLM_MODEL", REQUIRED_ENV["LLM_MODEL"])

    with pytest.raises(ConfigError) as exc_info:
        load_config()

    message = str(exc_info.value)
    assert "LLM_BASE_URL" in message
    assert "LLM_API_KEY" in message
    assert "LLM_MODEL" not in message  # it was provided, must not be reported as missing


def test_placeholder_treated_as_missing(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "CHANGE_ME_LLM_API_KEY")

    with pytest.raises(ConfigError) as exc_info:
        load_config()

    assert "LLM_API_KEY" in str(exc_info.value)


def test_config_repr_redacts_secrets(monkeypatch):
    _set_required_env(monkeypatch)

    cfg = load_config()

    assert REQUIRED_ENV["LLM_API_KEY"] not in repr(cfg)
    assert REQUIRED_ENV["LLM_API_KEY"] not in str(cfg)


def test_phase2_enum_rejected_with_hint(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("SCENARIO", "interview")

    with pytest.raises(ConfigError) as exc_info:
        load_config()

    message = str(exc_info.value)
    assert "后续阶段" in message or "暂未开放" in message
