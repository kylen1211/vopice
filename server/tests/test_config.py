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

# fast-slow-brain design §6.2 / RTM：1 期 5 项必需项被新 8 项取代，
# OPENAI_MODEL/KOKORO_VOICE_ID 不再必需（U1/U2/U6 用此常量，见 T1.1）。
NEW_REQUIRED_ENV = {
    "LLM_BASE_URL": "http://127.0.0.1:8045/v1",
    "LLM_API_KEY": "sk-test-key",
    "LLM_MODEL": "gemini-3.6-flash-high",
    "SLOW_LLM_MODEL": "gemini-3-pro",
    "SONIOX_API_KEY": "soniox-test-key",
    "ELEVENLABS_API_KEY": "elevenlabs-test-key",
    "ELEVENLABS_VOICE_ID": "voice-test-id",
    "ELEVENLABS_MODEL": "eleven_multilingual_v2",
}


def _set_required_env(monkeypatch):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)


def _set_new_required_env(monkeypatch):
    for key, value in NEW_REQUIRED_ENV.items():
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


def test_required_env_set_updated(monkeypatch):
    """T1.1/U1（fast-slow-brain design §6.2/RTM）：必需环境变量项恰为新 8 项
    ——LLM_BASE_URL/LLM_API_KEY/LLM_MODEL/SLOW_LLM_MODEL/SONIOX_API_KEY/
    ELEVENLABS_API_KEY/ELEVENLABS_VOICE_ID/ELEVENLABS_MODEL；
    OPENAI_MODEL/KOKORO_VOICE_ID 不再必需。"""
    for key in set(REQUIRED_ENV) | set(NEW_REQUIRED_ENV):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ConfigError) as exc_info:
        load_config()

    message = str(exc_info.value)
    for key in NEW_REQUIRED_ENV:
        assert key in message
    assert "OPENAI_MODEL" not in message
    assert "KOKORO_VOICE_ID" not in message


def test_placeholder_rejected(monkeypatch):
    """T1.1/U2（fast-slow-brain design §6.2）：CHANGE_ME_ 前缀值在新必需项上
    仍被判定为缺失——沿用 1 期 `_is_missing` 语义（config.py:31-32）。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL", REQUIRED_ENV["OPENAI_MODEL"])
    monkeypatch.setenv("KOKORO_VOICE_ID", REQUIRED_ENV["KOKORO_VOICE_ID"])
    monkeypatch.setenv("SONIOX_API_KEY", "CHANGE_ME_SONIOX_API_KEY")

    with pytest.raises(ConfigError) as exc_info:
        load_config()

    assert "SONIOX_API_KEY" in str(exc_info.value)


def test_provider_whitelist(monkeypatch):
    """T1.1/U6（fast-slow-brain design §6.3，2026-08-02 订正落点：本组执行时
    test_dual_brain.py 尚不存在，改放本文件）：未知的 STT_PROVIDER/TTS_PROVIDER
    值必须启动即拒——沿用 1 期 SCENARIO 白名单模式（config.py:58-69）。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL", REQUIRED_ENV["OPENAI_MODEL"])
    monkeypatch.setenv("KOKORO_VOICE_ID", REQUIRED_ENV["KOKORO_VOICE_ID"])
    monkeypatch.setenv("STT_PROVIDER", "not_a_real_provider")
    monkeypatch.setenv("TTS_PROVIDER", "not_a_real_provider")

    with pytest.raises(ConfigError):
        load_config()
