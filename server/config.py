"""Startup-time configuration validation (R5 / P25).

Validates all required environment variables at once and fails fast with a
full list of what's missing, rather than one variable at a time.
"""

import os
from dataclasses import dataclass

_PLACEHOLDER_PREFIX = "CHANGE_ME_"

# 1 期唯一场景；proposal §7 列出的 2 期场景名在此拦截（交接旗⑧ P25）。
_ALLOWED_SCENARIO = "voice_chat"
_PHASE2_SCENARIOS = {"interview", "translate", "companion", "butler"}

_REQUIRED_ENV_TO_FIELD = {
    "LLM_BASE_URL": "llm_base_url",
    "LLM_API_KEY": "llm_api_key",
    "LLM_MODEL": "llm_model",
}


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


def _is_missing(value: str | None) -> bool:
    return not value or value.startswith(_PLACEHOLDER_PREFIX)


@dataclass(frozen=True)
class Config:
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    scenario: str = _ALLOWED_SCENARIO

    def __repr__(self) -> str:
        return (
            f"Config(llm_base_url={self.llm_base_url!r}, llm_api_key='***', "
            f"llm_model={self.llm_model!r}, scenario={self.scenario!r})"
        )


def load_config() -> Config:
    """Validate required env vars and return an immutable Config.

    Raises ConfigError listing every missing/placeholder required variable,
    or rejecting a 2-期 scenario value with a "not yet available" hint.
    """
    scenario = os.getenv("SCENARIO", _ALLOWED_SCENARIO)
    if scenario in _PHASE2_SCENARIOS:
        raise ConfigError(
            f"SCENARIO={scenario!r} 属后续阶段，暂未开放"
            f"（1 期仅支持 {_ALLOWED_SCENARIO!r}）"
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

    return Config(scenario=scenario, **values)
