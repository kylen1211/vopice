"""Unit tests for server.config.load_config (R5 / P25)."""

import dataclasses
import re

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
#
# task-dispatch (C4 派活) T-5 新增第 9 项必需项 OPENCLAW_AGENT_ID（server/config.py
# §0.6，会话键模板 agent:{agent_id}:... 的 agent_id 段）——T-6 独占路径同步项。
#
# scenario-assembly M-1（expand-contract）：SLOW_LLM_MODEL 从"恒定必需"改为
# "仅 DUAL_BRAIN_ENABLED 为真时必需"，移出这个"任何组合都必需"的基础集合——
# 下方 `DUAL_BRAIN_REQUIRED_ENV` 单列（`_set_new_required_env` 默认走关闭态，
# 不再需要它）。9 项换回新 8 项。
NEW_REQUIRED_ENV = {
    "LLM_BASE_URL": "http://127.0.0.1:8045/v1",
    "LLM_API_KEY": "sk-test-key",
    "LLM_MODEL": "gemini-3.6-flash-high",
    "OPENCLAW_AGENT_ID": "dev",
    "SONIOX_API_KEY": "soniox-test-key",
    "ELEVENLABS_API_KEY": "elevenlabs-test-key",
    "ELEVENLABS_VOICE_ID": "voice-test-id",
    "ELEVENLABS_MODEL": "eleven_multilingual_v2",
}

# scenario-assembly M-1：仅 DUAL_BRAIN_ENABLED=true 时才并入必需集的一项。
DUAL_BRAIN_REQUIRED_ENV = {
    "DUAL_BRAIN_ENABLED": "true",
    "SLOW_LLM_MODEL": "gemini-3-pro",
}


def _set_new_required_env(monkeypatch):
    """默认走关闭态（DUAL_BRAIN_ENABLED 未设置）：只设基础 8 项，不涉及
    SLOW_LLM_MODEL/DUAL_BRAIN_ENABLED——它们各自的必需性由专门用例覆盖。"""
    for key, value in NEW_REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("DUAL_BRAIN_ENABLED", raising=False)
    monkeypatch.delenv("SLOW_LLM_MODEL", raising=False)


def test_missing_key_lists_all_missing(monkeypatch):
    """T1.2 订正(fast-slow-brain design §6.2 明文:"删除 OPENAI_MODEL/
    KOKORO_VOICE_ID...同步删 test_config.py 断言")：必需项集合改用
    NEW_REQUIRED_ENV，不再断言 OPENAI_MODEL/KOKORO_VOICE_ID（它们已不在必需
    项内，永远不会出现在缺失列表里，覆盖已由 U1 test_required_env_set_updated
    接管）；保留的核心信号是"报错列出全部缺失项、已提供项不误报"。

    scenario-assembly M-1：SLOW_LLM_MODEL 关闭态下不在必需集内，断言随之
    移除（其独立覆盖见 test_slow_llm_model_*）。"""
    for key in NEW_REQUIRED_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("DUAL_BRAIN_ENABLED", raising=False)
    monkeypatch.delenv("SLOW_LLM_MODEL", raising=False)
    monkeypatch.setenv("LLM_MODEL", NEW_REQUIRED_ENV["LLM_MODEL"])

    with pytest.raises(ConfigError) as exc_info:
        load_config()

    message = str(exc_info.value)
    assert "LLM_BASE_URL" in message
    assert "LLM_API_KEY" in message
    assert "OPENCLAW_AGENT_ID" in message
    assert "SONIOX_API_KEY" in message
    assert "ELEVENLABS_API_KEY" in message
    assert "ELEVENLABS_VOICE_ID" in message
    assert "ELEVENLABS_MODEL" in message
    # "LLM_MODEL" 是 "SLOW_LLM_MODEL" 的子串，纯 substring 断言会被后者误命中——
    # 用 \b 词边界排除该假阳性；"_" 属 \w，SLOW_ 与 LLM_MODEL 间无边界，故不会误配。
    assert re.search(r"\bLLM_MODEL\b", message) is None  # provided, must not be reported


# T1.2 订正：test_stt_tts_vars_are_required（原断言 OPENAI_MODEL/KOKORO_VOICE_ID
# 缺失即报错）随 design §6.2 删除这两项必需校验而失去存在依据——按 design.md
# 明文"同步删 test_config.py 断言"整条移除；其"必需项缺失即快速失败"的核心
# 覆盖已由 test_required_env_set_updated（U1）针对新 8 项完整接管。


def test_placeholder_treated_as_missing(monkeypatch):
    _set_new_required_env(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "CHANGE_ME_LLM_API_KEY")

    with pytest.raises(ConfigError) as exc_info:
        load_config()

    assert "LLM_API_KEY" in str(exc_info.value)


def test_empty_string_treated_as_missing(monkeypatch):
    """TEST-002 (门三 20260801): 占位值分支此前只测过 CHANGE_ME_ 前缀，
    config.py:28 的空串分支（`not value`）无对应用例。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "")

    with pytest.raises(ConfigError) as exc_info:
        load_config()

    assert "LLM_API_KEY" in str(exc_info.value)


def test_config_repr_redacts_secrets(monkeypatch):
    """T1.2 订正：新 Config 必需项已换成 NEW_REQUIRED_ENV（原 _set_required_env
    不再能构造出合法 Config，会在 load_config() 里因缺少新必需项抛
    ConfigError）；同时按任务要求把 redaction 断言扩展到全部 *_api_key 字段。"""
    _set_new_required_env(monkeypatch)

    cfg = load_config()

    assert NEW_REQUIRED_ENV["LLM_API_KEY"] not in repr(cfg)
    assert NEW_REQUIRED_ENV["LLM_API_KEY"] not in str(cfg)
    assert NEW_REQUIRED_ENV["SONIOX_API_KEY"] not in repr(cfg)
    assert NEW_REQUIRED_ENV["ELEVENLABS_API_KEY"] not in repr(cfg)


def test_phase2_enum_rejected_with_hint(monkeypatch):
    """scenario-assembly M-2/FR-6：合法值集合改用 `scenarios.template_ids()`，
    但 `_PHASE2_SCENARIOS` 拒绝集与"属后续阶段，暂未开放"文案保持现状不倒退。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.setenv("SCENARIO", "interview")

    with pytest.raises(ConfigError) as exc_info:
        load_config()

    message = str(exc_info.value)
    assert "后续阶段" in message or "暂未开放" in message


def test_unknown_scenario_value_also_rejected(monkeypatch):
    """REQ-003 (门三 20260801): 白名单而非黑名单——不在已知 2 期枚举里的任意
    未知值（如拼错）也必须被拒绝，不能静默放行。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.setenv("SCENARIO", "interviw")  # typo, not in _PHASE2_SCENARIOS

    with pytest.raises(ConfigError):
        load_config()


def test_required_env_set_updated(monkeypatch):
    """T1.1/U1（fast-slow-brain design §6.2/RTM）：必需环境变量项恰为新 8 项
    ——LLM_BASE_URL/LLM_API_KEY/LLM_MODEL/OPENCLAW_AGENT_ID/SONIOX_API_KEY/
    ELEVENLABS_API_KEY/ELEVENLABS_VOICE_ID/ELEVENLABS_MODEL；
    OPENAI_MODEL/KOKORO_VOICE_ID 不再必需。

    scenario-assembly M-1 更新：关闭态（默认）下 SLOW_LLM_MODEL 不在必需集
    内，从断言快照移除（其条件必需性由 test_slow_llm_model_* 单独覆盖）。"""
    for key in set(REQUIRED_ENV) | set(NEW_REQUIRED_ENV) | set(DUAL_BRAIN_REQUIRED_ENV):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ConfigError) as exc_info:
        load_config()

    message = str(exc_info.value)
    for key in NEW_REQUIRED_ENV:
        assert key in message
    assert "OPENAI_MODEL" not in message
    assert "KOKORO_VOICE_ID" not in message
    assert re.search(r"\bSLOW_LLM_MODEL\b", message) is None


def test_placeholder_rejected(monkeypatch):
    """T1.1/U2（fast-slow-brain design §6.2）：CHANGE_ME_ 前缀值在新必需项上
    仍被判定为缺失——沿用 1 期 `_is_missing` 语义（config.py:31-32）。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.setenv("SONIOX_API_KEY", "CHANGE_ME_SONIOX_API_KEY")

    with pytest.raises(ConfigError) as exc_info:
        load_config()

    assert "SONIOX_API_KEY" in str(exc_info.value)


def test_provider_whitelist(monkeypatch):
    """T1.1/U6（fast-slow-brain design §6.3，2026-08-02 订正落点：本组执行时
    test_dual_brain.py 尚不存在，改放本文件）：未知的 STT_PROVIDER/TTS_PROVIDER
    值必须启动即拒——沿用 1 期 SCENARIO 白名单模式（config.py:58-69）。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.setenv("STT_PROVIDER", "not_a_real_provider")
    monkeypatch.setenv("TTS_PROVIDER", "not_a_real_provider")

    with pytest.raises(ConfigError):
        load_config()


# 2026-08-03 补：deepgram/cartesia 备用厂商的必需项应"按所选 provider 条件必需"
# ——只在 STT_PROVIDER=deepgram / TTS_PROVIDER=cartesia 时才要求对应 key，默认
# 组合（soniox+elevenlabs）不受影响，也不应误报未选中厂商的 key 缺失。


def test_deepgram_api_key_required_only_when_selected(monkeypatch):
    """STT_PROVIDER=deepgram 时 DEEPGRAM_API_KEY 缺失应报错列出该项，且不应把
    未选中的 SONIOX_API_KEY 也当缺失项报出（它此时不该被校验）。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.setenv("STT_PROVIDER", "deepgram")
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.delenv("SONIOX_API_KEY", raising=False)

    with pytest.raises(ConfigError) as exc_info:
        load_config()

    message = str(exc_info.value)
    assert "DEEPGRAM_API_KEY" in message
    assert "SONIOX_API_KEY" not in message


def test_cartesia_keys_required_only_when_selected(monkeypatch):
    """TTS_PROVIDER=cartesia 时 CARTESIA_API_KEY/CARTESIA_VOICE_ID 缺失应报错
    列出两项，且不应把未选中的 ELEVENLABS_* 三项也当缺失项报出。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.setenv("TTS_PROVIDER", "cartesia")
    monkeypatch.delenv("CARTESIA_API_KEY", raising=False)
    monkeypatch.delenv("CARTESIA_VOICE_ID", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_VOICE_ID", raising=False)
    monkeypatch.delenv("ELEVENLABS_MODEL", raising=False)

    with pytest.raises(ConfigError) as exc_info:
        load_config()

    message = str(exc_info.value)
    assert "CARTESIA_API_KEY" in message
    assert "CARTESIA_VOICE_ID" in message
    assert "ELEVENLABS_API_KEY" not in message
    assert "ELEVENLABS_VOICE_ID" not in message
    assert "ELEVENLABS_MODEL" not in message


def test_deepgram_and_cartesia_selected_together_succeeds(monkeypatch):
    """两个备用厂商同时选中、key 配齐时应正常构造 Config，字段落在与默认厂商
    相同的通用字段名上（stt_api_key/tts_api_key/tts_voice），且不需要默认厂商
    （soniox/elevenlabs）的 key；tts_model 是 elevenlabs 专属，cartesia 路径下
    应为 None（bot.py 的 cartesia 构造器不使用它，吃厂商默认模型）。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.delenv("SONIOX_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_VOICE_ID", raising=False)
    monkeypatch.delenv("ELEVENLABS_MODEL", raising=False)
    monkeypatch.setenv("STT_PROVIDER", "deepgram")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "deepgram-test-key")
    monkeypatch.setenv("TTS_PROVIDER", "cartesia")
    monkeypatch.setenv("CARTESIA_API_KEY", "cartesia-test-key")
    monkeypatch.setenv("CARTESIA_VOICE_ID", "cartesia-test-voice")

    cfg = load_config()

    assert cfg.stt_provider == "deepgram"
    assert cfg.stt_api_key == "deepgram-test-key"
    assert cfg.tts_provider == "cartesia"
    assert cfg.tts_api_key == "cartesia-test-key"
    assert cfg.tts_voice == "cartesia-test-voice"
    assert cfg.tts_model is None


def test_config_is_frozen(monkeypatch):
    """config.py `Config` 声明 `@dataclass(frozen=True)`(不可变值对象设计
    属性,§5 集成闸门变异抽样 mutant①守卫:`frozen=True`→`frozen=False`)——
    构造出的实例对任一字段赋值必须抛 `dataclasses.FrozenInstanceError`,
    不能被悄悄改动。"""
    _set_new_required_env(monkeypatch)
    cfg = load_config()

    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.llm_model = "mutated-after-construction"


# ============================================================
# scenario-assembly T-2（contract §0.3）新增用例
# ============================================================


def test_slow_llm_model_optional_when_dual_brain_disabled(monkeypatch):
    """SA-07（M-1）：关闭态（默认）下 SLOW_LLM_MODEL 缺失不报错，`Config`
    的字段值为 None。"""
    _set_new_required_env(monkeypatch)

    cfg = load_config()

    assert cfg.dual_brain_enabled is False
    assert cfg.slow_llm_model is None


def test_slow_llm_model_present_but_unused_when_dual_brain_disabled(monkeypatch):
    """SA-07（M-1 兼容处置）：关闭态下 .env 里仍留着 SLOW_LLM_MODEL 这一行也
    不报错、照样读进 Config（只是不被任何装配逻辑使用），防"删了才不报错"
    的伪迁移。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.setenv("SLOW_LLM_MODEL", "gemini-3-pro")

    cfg = load_config()

    assert cfg.dual_brain_enabled is False
    assert cfg.slow_llm_model == "gemini-3-pro"


def test_slow_llm_model_required_when_dual_brain_enabled(monkeypatch):
    """SA-07：开启态下缺 SLOW_LLM_MODEL 必须报错，且缺失列表里列出该项。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.setenv("DUAL_BRAIN_ENABLED", "true")
    monkeypatch.delenv("SLOW_LLM_MODEL", raising=False)

    with pytest.raises(ConfigError) as exc_info:
        load_config()

    assert "SLOW_LLM_MODEL" in str(exc_info.value)


def test_slow_llm_model_placeholder_rejected_when_dual_brain_enabled(monkeypatch):
    """SA-07：开启态下 CHANGE_ME_ 占位符仍按既有 `_is_missing` 语义算缺失。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.setenv("DUAL_BRAIN_ENABLED", "true")
    monkeypatch.setenv("SLOW_LLM_MODEL", "CHANGE_ME_SLOW_LLM_MODEL")

    with pytest.raises(ConfigError) as exc_info:
        load_config()

    assert "SLOW_LLM_MODEL" in str(exc_info.value)


def test_slow_llm_model_set_when_dual_brain_enabled(monkeypatch):
    """SA-07 正向路径：开启态 + SLOW_LLM_MODEL 配齐 → 正常构造 Config。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.setenv("DUAL_BRAIN_ENABLED", "true")
    monkeypatch.setenv("SLOW_LLM_MODEL", "gemini-3-pro")

    cfg = load_config()

    assert cfg.dual_brain_enabled is True
    assert cfg.slow_llm_model == "gemini-3-pro"


@pytest.mark.parametrize("raw", ["1", "true", "yes", "on", "TRUE", "On", "YES", "1 "])
def test_dual_brain_flag_true_values_enable(monkeypatch, raw):
    """SA-08：真值集 {1,true,yes,on} 大小写不敏感（含首尾空白）一律解析为
    True。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.setenv("DUAL_BRAIN_ENABLED", raw)
    monkeypatch.setenv("SLOW_LLM_MODEL", "gemini-3-pro")

    cfg = load_config()

    assert cfg.dual_brain_enabled is True


@pytest.mark.parametrize("raw", ["0", "false", "no", "off", "", "FALSE", "Off", "NO"])
def test_dual_brain_flag_false_values_disable(monkeypatch, raw):
    """SA-08：假值集 {0,false,no,off,空} 大小写不敏感一律解析为 False。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.setenv("DUAL_BRAIN_ENABLED", raw)

    cfg = load_config()

    assert cfg.dual_brain_enabled is False


def test_dual_brain_flag_unset_defaults_to_false(monkeypatch):
    """SA-08：未设置该变量时默认关闭。"""
    _set_new_required_env(monkeypatch)

    cfg = load_config()

    assert cfg.dual_brain_enabled is False


def test_dual_brain_flag_outside_value_sets_fail_fast(monkeypatch):
    """SA-08：真/假值集合之外的任意取值必须 fail-fast，不得静默当假。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.setenv("DUAL_BRAIN_ENABLED", "maybe")

    with pytest.raises(ConfigError):
        load_config()


def test_template_provider_assemblyai_key_not_required_when_not_selected(monkeypatch):
    """SA-09 ③：默认模板（voice_chat）不选中 assemblyai 时，不强制配置
    ASSEMBLYAI_API_KEY。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.delenv("ASSEMBLYAI_API_KEY", raising=False)

    cfg = load_config()

    assert cfg.stt_provider == "soniox"


def test_template_provider_fail_fast_when_assemblyai_key_missing(monkeypatch):
    """SA-09 ②：english_tutor 模板固定选中 assemblyai；缺 ASSEMBLYAI_API_KEY
    时报错列出该项，且不得回退默认模板/soniox（FR-11）。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.setenv("SCENARIO", "english_tutor")
    monkeypatch.delenv("ASSEMBLYAI_API_KEY", raising=False)

    with pytest.raises(ConfigError) as exc_info:
        load_config()

    assert "ASSEMBLYAI_API_KEY" in str(exc_info.value)


def test_template_provider_fail_fast_when_assemblyai_key_is_placeholder(monkeypatch):
    """SA-09 ②：ASSEMBLYAI_API_KEY 为 CHANGE_ME_ 占位符时同样按缺失处理。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.setenv("SCENARIO", "english_tutor")
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "CHANGE_ME_ASSEMBLYAI_API_KEY")

    with pytest.raises(ConfigError) as exc_info:
        load_config()

    assert "ASSEMBLYAI_API_KEY" in str(exc_info.value)


def test_template_provider_english_tutor_selects_assemblyai_when_key_present(monkeypatch):
    """SA-09 正向路径：english_tutor + key 配齐 → 生效 provider 是
    assemblyai，落在既有中立字段 stt_api_key 上，构造出的 Config 携带该
    模板对象。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.setenv("SCENARIO", "english_tutor")
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "assemblyai-test-key")
    monkeypatch.delenv("SONIOX_API_KEY", raising=False)

    cfg = load_config()

    assert cfg.stt_provider == "assemblyai"
    assert cfg.stt_api_key == "assemblyai-test-key"
    assert cfg.template.id == "english_tutor"


def test_template_provider_assemblyai_whitelisted_fail_fast_boundary(monkeypatch):
    """SA-09 ①（config.py 侧的白名单复核，ADR-8）：assemblyai 在白名单内，
    STT_PROVIDER 直接设为 assemblyai（不经模板）也应被接受，不因扩容前的
    旧白名单而 fail-fast。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.setenv("STT_PROVIDER", "assemblyai")
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "assemblyai-test-key")
    monkeypatch.delenv("SONIOX_API_KEY", raising=False)

    cfg = load_config()

    assert cfg.stt_provider == "assemblyai"


def test_template_provider_override_wins_over_env_var(monkeypatch):
    """SA-09/ADR-5：模板 services 覆盖 > 环境变量 > 内置默认——english_tutor
    模板固定 stt_provider=assemblyai，即使 STT_PROVIDER 环境变量另设
    deepgram 也不生效（连 DEEPGRAM_API_KEY 都不需要配）。"""
    _set_new_required_env(monkeypatch)
    monkeypatch.setenv("SCENARIO", "english_tutor")
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "assemblyai-test-key")
    monkeypatch.setenv("STT_PROVIDER", "deepgram")
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)

    cfg = load_config()

    assert cfg.stt_provider == "assemblyai"
