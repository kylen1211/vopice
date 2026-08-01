"""Unit tests for server.config.load_config (R5 / P25)."""

import pytest

from config import ConfigError, load_config

REQUIRED_ENV = {
    "LLM_BASE_URL": "http://127.0.0.1:8045/v1",
    "LLM_API_KEY": "sk-test-key",
    "LLM_MODEL": "gemini-3.6-flash-high",
    "OPENAI_MODEL": "small",
    "KOKORO_VOICE_ID": "zf_xiaoxiao",
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
    assert "OPENAI_MODEL" in message
    assert "KOKORO_VOICE_ID" in message
    assert "LLM_MODEL" not in message  # it was provided, must not be reported as missing


def test_stt_tts_vars_are_required(monkeypatch):
    """REQ-001 (门三 20260801): OPENAI_MODEL/KOKORO_VOICE_ID 此前不在必需项校验
    内，留空会让服务正常启动、TTS 在运行期每句话静默失败。"""
    _set_required_env(monkeypatch)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("KOKORO_VOICE_ID", raising=False)

    with pytest.raises(ConfigError) as exc_info:
        load_config()

    message = str(exc_info.value)
    assert "OPENAI_MODEL" in message
    assert "KOKORO_VOICE_ID" in message


def test_placeholder_treated_as_missing(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "CHANGE_ME_LLM_API_KEY")

    with pytest.raises(ConfigError) as exc_info:
        load_config()

    assert "LLM_API_KEY" in str(exc_info.value)


def test_empty_string_treated_as_missing(monkeypatch):
    """TEST-002 (门三 20260801): 占位值分支此前只测过 CHANGE_ME_ 前缀，
    config.py:28 的空串分支（`not value`）无对应用例。"""
    _set_required_env(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "")

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


def test_unknown_scenario_value_also_rejected(monkeypatch):
    """REQ-003 (门三 20260801): 白名单而非黑名单——不在已知 2 期枚举里的任意
    未知值（如拼错）也必须被拒绝，不能静默放行。"""
    _set_required_env(monkeypatch)
    monkeypatch.setenv("SCENARIO", "interviw")  # typo, not in _PHASE2_SCENARIOS

    with pytest.raises(ConfigError):
        load_config()
