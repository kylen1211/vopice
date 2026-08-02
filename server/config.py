"""Startup-time configuration validation (R5 / P25).

Validates all required environment variables at once and fails fast with a
full list of what's missing, rather than one variable at a time.
"""

import os
from dataclasses import dataclass, fields

_PLACEHOLDER_PREFIX = "CHANGE_ME_"

# 1 期唯一场景；proposal §7 列出的 2 期场景名在此拦截（交接旗⑧ P25）。
_ALLOWED_SCENARIO = "voice_chat"
_PHASE2_SCENARIOS = {"interview", "translate", "companion", "butler"}

# fast-slow-brain design §6.2：必需项从 1 期 5 项换成新 8 项——
# OPENAI_MODEL/KOKORO_VOICE_ID 删除（同步删 .env.example 与 test_config.py 断言），
# 新增慢脑 LLM + Soniox STT + ElevenLabs TTS 共 5 项。
_REQUIRED_ENV_TO_FIELD = {
    "LLM_BASE_URL": "llm_base_url",
    "LLM_API_KEY": "llm_api_key",
    "LLM_MODEL": "llm_model",
    "SLOW_LLM_MODEL": "slow_llm_model",
    "SONIOX_API_KEY": "stt_api_key",
    "ELEVENLABS_API_KEY": "tts_api_key",
    "ELEVENLABS_VOICE_ID": "tts_voice",
    "ELEVENLABS_MODEL": "tts_model",
}

# design §6.2：SONIOX_MODEL 非必需，默认沿用旧库在用型号（§13.1）。
_DEFAULT_STT_MODEL = "stt-rt-v5"

# design §6.3：只注册当前在用的一家，有默认值、不进必需项、白名单校验
# （同构 1 期 SCENARIO 白名单模式，config.py 原 58-69 行）。
_DEFAULT_STT_PROVIDER = "soniox"
_DEFAULT_TTS_PROVIDER = "elevenlabs"
_STT_PROVIDER_WHITELIST = {"soniox"}
_TTS_PROVIDER_WHITELIST = {"elevenlabs"}


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


def _is_missing(value: str | None) -> bool:
    return not value or value.startswith(_PLACEHOLDER_PREFIX)


@dataclass(frozen=True)
class Config:
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    slow_llm_model: str
    stt_api_key: str
    tts_api_key: str
    tts_voice: str
    tts_model: str
    stt_model: str = _DEFAULT_STT_MODEL
    stt_provider: str = _DEFAULT_STT_PROVIDER
    tts_provider: str = _DEFAULT_TTS_PROVIDER
    scenario: str = _ALLOWED_SCENARIO

    def __repr__(self) -> str:
        parts = []
        for f in fields(self):
            value = "'***'" if f.name.endswith("_api_key") else repr(getattr(self, f.name))
            parts.append(f"{f.name}={value}")
        return f"Config({', '.join(parts)})"


def _validate_provider(env_name: str, default: str, whitelist: set[str]) -> str:
    """Read an optional provider env var, falling back to its default and
    rejecting any value outside the whitelist (design §6.3)."""
    raw = os.getenv(env_name)
    value = default if _is_missing(raw) else raw
    assert value is not None
    if value not in whitelist:
        raise ConfigError(
            f"{env_name}={value!r} 不是有效值（当前仅支持 {sorted(whitelist)!r}）"
        )
    return value


def load_config() -> Config:
    """Validate required env vars and return an immutable Config.

    Raises ConfigError listing every missing/placeholder required variable,
    rejecting a 2-期 scenario value with a "not yet available" hint, or
    rejecting an unknown STT_PROVIDER/TTS_PROVIDER value.
    """
    # 门三 20260801(REQ-003)：白名单而非黑名单——只放行已知的 1 期场景值，
    # 未知值(含拼错、未来新增的 2 期名字)一律拒绝，不静默放行。
    scenario = os.getenv("SCENARIO", _ALLOWED_SCENARIO)
    if scenario != _ALLOWED_SCENARIO:
        if scenario in _PHASE2_SCENARIOS:
            raise ConfigError(
                f"SCENARIO={scenario!r} 属后续阶段，暂未开放"
                f"（1 期仅支持 {_ALLOWED_SCENARIO!r}）"
            )
        raise ConfigError(
            f"SCENARIO={scenario!r} 不是有效值（1 期仅支持 {_ALLOWED_SCENARIO!r}）"
        )

    values: dict[str, str] = {}
    missing: list[str] = []
    for env_name, field_name in _REQUIRED_ENV_TO_FIELD.items():
        raw = os.getenv(env_name)
        if _is_missing(raw):
            missing.append(env_name)
        else:
            assert raw is not None
            values[field_name] = raw

    if missing:
        raise ConfigError(
            "缺少必需环境变量：" + ", ".join(missing) + "（参考 server/.env.example）"
        )

    stt_model_raw = os.getenv("SONIOX_MODEL")
    stt_model = _DEFAULT_STT_MODEL if _is_missing(stt_model_raw) else stt_model_raw
    assert stt_model is not None

    stt_provider = _validate_provider(
        "STT_PROVIDER", _DEFAULT_STT_PROVIDER, _STT_PROVIDER_WHITELIST
    )
    tts_provider = _validate_provider(
        "TTS_PROVIDER", _DEFAULT_TTS_PROVIDER, _TTS_PROVIDER_WHITELIST
    )

    return Config(
        scenario=scenario,
        stt_model=stt_model,
        stt_provider=stt_provider,
        tts_provider=tts_provider,
        **values,
    )
