"""Startup-time configuration validation (R5 / P25).

Validates all required environment variables at once and fails fast with a
full list of what's missing, rather than one variable at a time.
"""

import os
from dataclasses import dataclass, fields

import scenarios
from scenarios import ScenarioTemplate

_PLACEHOLDER_PREFIX = "CHANGE_ME_"

# scenario-assembly M-2：`SCENARIO` 环境变量名与默认值不变（=默认模板 id）；
# 合法值集合从"唯一 1 期场景"改为 `scenarios.template_ids()`（注册表是唯一
# 数据源，FR-1/FR-6）。`_PHASE2_SCENARIOS` 拒绝集与文案保持现状（FR-6 不倒退）。
_DEFAULT_SCENARIO_ID = "voice_chat"
_PHASE2_SCENARIOS = {"interview", "translate", "companion", "butler"}

# fast-slow-brain design §6.2：1 期 5 项必需项换成新 8 项——
# OPENAI_MODEL/KOKORO_VOICE_ID 删除，新增慢脑 LLM + Soniox STT + ElevenLabs TTS
# 共 5 项。
#
# task-dispatch (C4 派活) design.md 方案 C 步骤4/契约 §0.6：新增 OPENCLAW_AGENT_ID——
# 派活会话键模板 `agent:{agent_id}:voice-agent-{token}` 的 agent_id 段。
#
# scenario-assembly M-1（expand-contract）：SLOW_LLM_MODEL 从"恒定必需"改为
# "仅 DUAL_BRAIN_ENABLED 为真时必需"，从本表移出、单列 `_DUAL_BRAIN_REQUIRED_ENV`
# （§0.3 校验顺序④）。本表剩余 4 项与所选 provider/开关状态均无关，任何组合
# 都必需。
_BASE_REQUIRED_ENV_TO_FIELD = {
    "LLM_BASE_URL": "llm_base_url",
    "LLM_API_KEY": "llm_api_key",
    "LLM_MODEL": "llm_model",
    "OPENCLAW_AGENT_ID": "openclaw_agent_id",
}

# scenario-assembly M-1：`DUAL_BRAIN_ENABLED` 为真时才并入必需项汇总
# （contract §0.3 校验顺序④）。
_DUAL_BRAIN_REQUIRED_ENV = {
    "SLOW_LLM_MODEL": "slow_llm_model",
}

# scenario-assembly ADR-6：真值集/假值集大小写不敏感；集合外任意取值一律
# fail-fast，不得静默当假（FR-12）。未设置视同假值集里的 ""。
_DUAL_BRAIN_TRUE_VALUES = {"1", "true", "yes", "on"}
_DUAL_BRAIN_FALSE_VALUES = {"0", "false", "no", "off", ""}

# 2026-08-03 决议：STT/TTS 各保留可选厂商，用 STT_PROVIDER/TTS_PROVIDER 选。
# 每家厂商的必需 key 只在其被选中时才校验——未选中的厂商不强制配置，默认组合
# （soniox+elevenlabs）用户不必被迫也去配一份用不到的备用厂商 key。所有分支落
# 到同一组通用字段名（stt_api_key/tts_api_key/tts_voice[/tts_model]），bot.py
# 的构造器因此不关心实际选中的是哪家，只读 Config 字段。
#
# scenario-assembly M-6（修订 R2）：新增 assemblyai——`english_tutor` 模板固定
# 选中它（universal-3-5-pro 原生中英 code-switch，ADR-8）；未选中的用户不必
# 配 ASSEMBLYAI_API_KEY。
_STT_PROVIDER_REQUIRED_ENV = {
    "soniox": {"SONIOX_API_KEY": "stt_api_key"},
    "deepgram": {"DEEPGRAM_API_KEY": "stt_api_key"},
    "assemblyai": {"ASSEMBLYAI_API_KEY": "stt_api_key"},
}
_TTS_PROVIDER_REQUIRED_ENV = {
    "elevenlabs": {
        "ELEVENLABS_API_KEY": "tts_api_key",
        "ELEVENLABS_VOICE_ID": "tts_voice",
        "ELEVENLABS_MODEL": "tts_model",
    },
    "cartesia": {
        "CARTESIA_API_KEY": "tts_api_key",
        "CARTESIA_VOICE_ID": "tts_voice",
    },
}

# design §6.2：SONIOX_MODEL 非必需，默认沿用旧库在用型号（§13.1）。
_DEFAULT_STT_MODEL = "stt-rt-v5"

# design §6.3：只注册当前在用的一家，有默认值、不进必需项、白名单校验
# （同构 1 期 SCENARIO 白名单模式）。
#
# scenario-assembly M-6（修订 R2）：STT 白名单加 assemblyai；仍只含云端
# provider（FR-5 不引入本地模型的约束不变）。
_DEFAULT_STT_PROVIDER = "soniox"
_DEFAULT_TTS_PROVIDER = "elevenlabs"
_STT_PROVIDER_WHITELIST = {"soniox", "deepgram", "assemblyai"}
_TTS_PROVIDER_WHITELIST = {"elevenlabs", "cartesia"}


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


# INV-2（config.py 是唯一同时看得见"已注册模板集合"与"phase2 拒绝集"两侧的
# 层，自检落这里，contract §0.1）：一个 id 不能既是"已实现"又是"未实现"。
# 模块 import 期自检，相交即 `ConfigError`（不得抛未捕获异常）。
_scenario_registry_overlap = scenarios.template_ids() & _PHASE2_SCENARIOS
if _scenario_registry_overlap:
    raise ConfigError(
        f"INV-2 违反：TEMPLATES 与 _PHASE2_SCENARIOS 出现重叠 id "
        f"{sorted(_scenario_registry_overlap)!r}（同一个 id 不能既是已实现模板又是"
        f"未实现的 2 期占位）"
    )


def _is_missing(value: str | None) -> bool:
    return not value or value.startswith(_PLACEHOLDER_PREFIX)


@dataclass(frozen=True)
class Config:
    llm_base_url: str
    llm_api_key: str
    # 网关默认模型（scenario-assembly ADR-5 语义收窄）：`dispatch_llm`（派活委派
    # 轮）继续用它；模板**不得**影响它——换模板不应静默把派活轮模型也换掉
    # （P50 形状）。快脑实际使用的生效模型见 `fast_llm_model`。
    llm_model: str
    openclaw_agent_id: str
    stt_api_key: str
    tts_api_key: str
    tts_voice: str
    # scenario-assembly M-3：生效快脑模型 = 模板覆盖值 or `LLM_MODEL`。
    fast_llm_model: str
    # scenario-assembly ADR-6：慢脑开关，默认关闭。
    dual_brain_enabled: bool
    # scenario-assembly M-2：替换原 `scenario: str`，零外部消费者，直接替换，
    # 无双写期。本次会话实际选中的模板对象（frozen，快照不可变，FR-3）。
    template: ScenarioTemplate
    # scenario-assembly M-1：恒定必需 → 条件必需（仅 dual_brain_enabled 为真时）。
    # 关闭态下即使 .env 里仍留着该行也不报错、不使用。
    slow_llm_model: str | None = None
    # elevenlabs 专属（cartesia 不需要显式 model，吃厂商默认档位）——None 表示
    # 当前选中的 TTS provider 不使用固定模型名。
    tts_model: str | None = None
    stt_model: str = _DEFAULT_STT_MODEL
    stt_provider: str = _DEFAULT_STT_PROVIDER
    tts_provider: str = _DEFAULT_TTS_PROVIDER

    def __repr__(self) -> str:
        parts = []
        for f in fields(self):
            value = "'***'" if f.name.endswith("_api_key") else repr(getattr(self, f.name))
            parts.append(f"{f.name}={value}")
        return f"Config({', '.join(parts)})"


def _resolve_template(scenario_id: str) -> ScenarioTemplate:
    """SCENARIO → 模板（contract §0.3 校验顺序①）。

    合法值 = `scenarios.template_ids()`；`_PHASE2_SCENARIOS` 成员保持现状的
    "属后续阶段，暂未开放"提示；其余未知值保持现状的"不是有效值"拒绝。两者
    都是 `ConfigError`，不得抛未捕获异常（FR-6）。
    """
    if scenario_id in scenarios.template_ids():
        return scenarios.get_template(scenario_id)

    legal = sorted(scenarios.template_ids())
    if scenario_id in _PHASE2_SCENARIOS:
        raise ConfigError(
            f"SCENARIO={scenario_id!r} 属后续阶段，暂未开放（当前支持 {legal!r}）"
        )
    raise ConfigError(f"SCENARIO={scenario_id!r} 不是有效值（当前支持 {legal!r}）")


def _parse_dual_brain_enabled() -> bool:
    """`DUAL_BRAIN_ENABLED` → bool（contract §0.3 校验顺序②）。

    真值集/假值集大小写不敏感；未设置视同假值集里的 ""；集合外任意取值一律
    `ConfigError` fail-fast，不得静默当假（FR-12）。
    """
    raw = os.getenv("DUAL_BRAIN_ENABLED")
    normalized = (raw or "").strip().lower()
    if normalized in _DUAL_BRAIN_TRUE_VALUES:
        return True
    if normalized in _DUAL_BRAIN_FALSE_VALUES:
        return False
    raise ConfigError(
        f"DUAL_BRAIN_ENABLED={raw!r} 不是有效值"
        f"（真值集 {sorted(_DUAL_BRAIN_TRUE_VALUES)!r}，"
        f"假值集 {sorted(_DUAL_BRAIN_FALSE_VALUES)!r}，大小写不敏感）"
    )


def _validate_provider(
    env_name: str, template_value: str | None, default: str, whitelist: set[str]
) -> str:
    """计算一个 provider 的生效值（contract §0.3 校验顺序③，ADR-5 优先级：
    模板 services 覆盖 > 环境变量 > 内置默认），越白名单即 `ConfigError`。
    """
    if template_value is not None:
        value = template_value
    else:
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

    校验顺序严格按 contract §0.3 五步：① 取模板 → ② 解析开关 →
    ③ 计算生效 provider → ④ 按生效 provider + 开关状态汇总必需 key 表 →
    ⑤ 一次性列出全部缺失/占位符项报错。禁止静默回退默认模板或默认 provider。
    """
    # ① SCENARIO → 模板
    scenario_id = os.getenv("SCENARIO", _DEFAULT_SCENARIO_ID)
    template = _resolve_template(scenario_id)

    # ② DUAL_BRAIN_ENABLED → bool
    dual_brain_enabled = _parse_dual_brain_enabled()

    # ③ 生效 provider（模板覆盖 > 环境变量 > 内置默认）
    stt_provider = _validate_provider(
        "STT_PROVIDER", template.services.stt_provider, _DEFAULT_STT_PROVIDER, _STT_PROVIDER_WHITELIST
    )
    tts_provider = _validate_provider(
        "TTS_PROVIDER", template.services.tts_provider, _DEFAULT_TTS_PROVIDER, _TTS_PROVIDER_WHITELIST
    )

    # ④ 按生效 provider + 开关状态汇总必需 key 表（模板覆盖不放松凭证必需性：
    # 即使模板覆盖了 tts_voice/tts_model，对应厂商的环境变量仍在必需集内）。
    required_env_to_field = {
        **_BASE_REQUIRED_ENV_TO_FIELD,
        **_STT_PROVIDER_REQUIRED_ENV[stt_provider],
        **_TTS_PROVIDER_REQUIRED_ENV[tts_provider],
    }
    if dual_brain_enabled:
        required_env_to_field = {**required_env_to_field, **_DUAL_BRAIN_REQUIRED_ENV}

    # ⑤ 一次性列出全部缺失/占位符项
    values: dict[str, str] = {}
    missing: list[str] = []
    for env_name, field_name in required_env_to_field.items():
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

    # M-1 兼容处置：关闭态下 SLOW_LLM_MODEL 不在必需表内，但 .env 里若仍留着
    # 该行，读进来即可（不报错、不使用），防止"删了才不报错"的伪迁移。
    slow_llm_model = values.get("slow_llm_model")
    if slow_llm_model is None and not dual_brain_enabled:
        slow_llm_model = os.getenv("SLOW_LLM_MODEL")

    # 生效值合并（ADR-5：模板覆盖 > 环境变量 > 内置默认），写进既有中立字段。
    stt_model_raw = os.getenv("SONIOX_MODEL")
    env_stt_model = _DEFAULT_STT_MODEL if _is_missing(stt_model_raw) else stt_model_raw
    assert env_stt_model is not None
    stt_model = template.services.stt_model or env_stt_model

    tts_voice = template.services.tts_voice or values.get("tts_voice")
    assert tts_voice is not None
    tts_model = template.services.tts_model or values.get("tts_model")

    fast_llm_model = template.services.fast_llm_model or values["llm_model"]

    return Config(
        llm_base_url=values["llm_base_url"],
        llm_api_key=values["llm_api_key"],
        llm_model=values["llm_model"],
        openclaw_agent_id=values["openclaw_agent_id"],
        stt_api_key=values["stt_api_key"],
        tts_api_key=values["tts_api_key"],
        tts_voice=tts_voice,
        fast_llm_model=fast_llm_model,
        dual_brain_enabled=dual_brain_enabled,
        template=template,
        slow_llm_model=slow_llm_model,
        tts_model=tts_model,
        stt_model=stt_model,
        stt_provider=stt_provider,
        tts_provider=tts_provider,
    )
