"""Tests for the scenario template registry and prompt composition
(scenario-assembly T-1, contract/cases.md §0.1/§0.2/§0.5).

Test-name anchors required by contract §1: registry(SA-01) / section,compose
(SA-02) / language_section(SA-22) / drift(SA-03) / template_provider(SA-09,
registry side) / frozen(SA-13, template side) / tutor_persona(SA-16).
"""

from dataclasses import FrozenInstanceError

import pytest

import config
import prompts
import scenarios
from scenarios import TEMPLATES, ScenarioTemplate, ServiceChoice

# ---------------------------------------------------------------------------
# registry (SA-01, FR-1/FR-6): TEMPLATES 是唯一数据源；INV-1/INV-2/INV-3/INV-4。
# ---------------------------------------------------------------------------


def test_registry_template_ids_matches_templates_keys():
    """template_ids() 与 TEMPLATES 的 key 集合一致，无第二处硬编码枚举。"""
    assert scenarios.template_ids() == frozenset(TEMPLATES.keys())


def test_registry_v1_templates_present():
    """v1 模板集合 = {voice_chat, english_tutor}（契约 §0.2）。"""
    assert scenarios.template_ids() == frozenset({"voice_chat", "english_tutor"})


def test_registry_get_template_returns_registered_instance():
    assert scenarios.get_template("voice_chat") is TEMPLATES["voice_chat"]
    assert scenarios.get_template("english_tutor") is TEMPLATES["english_tutor"]


def test_registry_get_template_unknown_id_raises_key_error():
    """未注册 id → KeyError（由 config 层转 ConfigError，不在本模块转译）。"""
    with pytest.raises(KeyError):
        scenarios.get_template("does_not_exist")


def test_registry_inv1_ids_match_registration_key():
    for key, template in TEMPLATES.items():
        assert template.id == key, f"key={key!r} 与 template.id={template.id!r} 不一致"


def test_registry_inv2_ids_disjoint_from_phase2_scenarios():
    """INV-2 数据断言：枚举放行的每个 id 都有实现；TEMPLATES 与 phase2 拒绝集不相交。"""
    assert scenarios.template_ids().isdisjoint(config._PHASE2_SCENARIOS)


def test_registry_inv3_provider_choices_within_cloud_whitelist():
    stt_whitelist = {"soniox", "deepgram", "assemblyai"}
    tts_whitelist = {"elevenlabs", "cartesia"}
    for template in TEMPLATES.values():
        if template.services.stt_provider is not None:
            assert template.services.stt_provider in stt_whitelist
        if template.services.tts_provider is not None:
            assert template.services.tts_provider in tts_whitelist


def test_registry_inv4_identity_sections_nonempty_and_no_forbidden_overlap():
    forbidden = (
        prompts.VOICE_SAFETY_SECTION,
        prompts.CAPABILITY_BOUNDARY_SECTION,
        prompts.CONCISENESS_SECTION,
        prompts.DUAL_BRAIN_SECTION,
    )
    for template in TEMPLATES.values():
        assert template.identity_section, f"{template.id} identity_section 为空"
        for text in forbidden:
            assert text not in template.identity_section, (
                f"{template.id} identity_section 夹带了不可覆盖段原文"
            )
        if template.language_section is not None:
            assert template.language_section, f"{template.id} language_section 声明但为空"


def test_registry_english_tutor_stt_provider_pinned_to_assemblyai():
    """契约 §0.2 修订 R2 钉死：english_tutor.services.stt_provider = 'assemblyai'。"""
    assert TEMPLATES["english_tutor"].services.stt_provider == "assemblyai"


def test_registry_voice_chat_has_no_service_overrides():
    """voice_chat 全 None = 现有默认组合，行为与变更前等价。"""
    assert TEMPLATES["voice_chat"].services == ServiceChoice()


# ---------------------------------------------------------------------------
# section / compose (SA-02, FR-4): 六段独立可寻址 + 组合函数段序与可覆盖性。
# ---------------------------------------------------------------------------


def test_section_constants_are_independently_addressable():
    for name in (
        "IDENTITY_DEFAULT_SECTION",
        "VOICE_SAFETY_SECTION",
        "CAPABILITY_BOUNDARY_SECTION",
        "LANGUAGE_SECTION",
        "CONCISENESS_SECTION",
        "DUAL_BRAIN_SECTION",
    ):
        assert hasattr(prompts, name), f"{name} 尚未定义"
        assert getattr(prompts, name), f"{name} 不得为空"


def test_compose_dual_brain_off_removes_only_dual_brain_section():
    """关闭态相对开启态少且仅少 DUAL_BRAIN_SECTION。"""
    template = TEMPLATES["voice_chat"]
    on = scenarios.build_system_prompt(template, dual_brain_enabled=True)
    off = scenarios.build_system_prompt(template, dual_brain_enabled=False)

    assert prompts.DUAL_BRAIN_SECTION in on
    assert prompts.DUAL_BRAIN_SECTION not in off
    assert on == off + "\n\n" + prompts.DUAL_BRAIN_SECTION


def test_compose_voice_safety_section_appears_verbatim_in_any_template():
    """护栏段在任意模板下原样出现，模板不可改写它。"""
    for template in TEMPLATES.values():
        combined = scenarios.build_system_prompt(template, dual_brain_enabled=True)
        assert prompts.VOICE_SAFETY_SECTION in combined


def test_compose_capability_boundary_and_conciseness_sections_uncoverable():
    """能力边界段、简洁段在任意模板下原样出现，不可被模板改写。"""
    for template in TEMPLATES.values():
        combined = scenarios.build_system_prompt(template, dual_brain_enabled=True)
        assert prompts.CAPABILITY_BOUNDARY_SECTION in combined
        assert prompts.CONCISENESS_SECTION in combined


def test_compose_segment_order_dual_brain_on_matches_contract_table():
    """开启态段序 = 契约 §0.5 表：身份 → 语音安全 → 能力边界 → 语言 → 简洁 → 双脑。"""
    template = TEMPLATES["voice_chat"]
    combined = scenarios.build_system_prompt(template, dual_brain_enabled=True)

    identity_pos = combined.index(template.identity_section)
    safety_pos = combined.index(prompts.VOICE_SAFETY_SECTION)
    boundary_pos = combined.index(prompts.CAPABILITY_BOUNDARY_SECTION)
    language_pos = combined.index(prompts.LANGUAGE_SECTION)
    conciseness_pos = combined.index(prompts.CONCISENESS_SECTION)
    dual_pos = combined.index(prompts.DUAL_BRAIN_SECTION)

    assert identity_pos < safety_pos < boundary_pos < language_pos < conciseness_pos < dual_pos


# ---------------------------------------------------------------------------
# language_section (SA-22, FR-4 修订 R1): 语言段可覆盖，结构判据不锚具体文案。
# ---------------------------------------------------------------------------


def test_language_section_default_template_matches_constant_verbatim():
    """①默认模板组合出的语言段与 prompts.LANGUAGE_SECTION 逐字相同。"""
    combined = scenarios.build_system_prompt(TEMPLATES["voice_chat"], dual_brain_enabled=True)
    sections = combined.split("\n\n")
    assert sections[3] == prompts.LANGUAGE_SECTION


def test_language_section_overridden_template_excludes_default_text():
    """②声明了 language_section 的模板组合出的该段 = 模板值且不含默认常量原文。"""
    combined = scenarios.build_system_prompt(TEMPLATES["english_tutor"], dual_brain_enabled=True)
    sections = combined.split("\n\n")
    assert sections[3] == prompts.LANGUAGE_TUTOR_SECTION
    assert prompts.LANGUAGE_SECTION not in combined


def test_language_section_position_and_other_segments_unchanged_across_templates():
    """③两种情况下语言段位置(第 4 段)与其余五段文本均不变。"""
    default_combined = scenarios.build_system_prompt(
        TEMPLATES["voice_chat"], dual_brain_enabled=True
    )
    tutor_combined = scenarios.build_system_prompt(
        TEMPLATES["english_tutor"], dual_brain_enabled=True
    )
    default_sections = default_combined.split("\n\n")
    tutor_sections = tutor_combined.split("\n\n")

    # 语言段固定在第 4 段（index 3）。
    assert default_sections[3] == prompts.LANGUAGE_SECTION
    assert tutor_sections[3] == prompts.LANGUAGE_TUTOR_SECTION

    # 其余五段（身份段除外，身份段本就是模板差异点）文本不变。
    for idx in (1, 2, 4, 5):
        assert default_sections[idx] == tutor_sections[idx]


def test_language_section_none_equivalent_to_unset():
    """④language_section=None 与未声明等价。"""
    explicit_none = ScenarioTemplate(
        id="x",
        label="x",
        identity_section="identity",
        language_section=None,
    )
    unset = ScenarioTemplate(
        id="x",
        label="x",
        identity_section="identity",
    )
    assert scenarios.build_system_prompt(
        explicit_none, dual_brain_enabled=True
    ) == scenarios.build_system_prompt(unset, dual_brain_enabled=True)


# ---------------------------------------------------------------------------
# drift (SA-03, FR-4): 防漂移绑定。
# ---------------------------------------------------------------------------


def test_drift_system_prompt_matches_build_system_prompt():
    assert prompts.SYSTEM_PROMPT == scenarios.build_system_prompt(
        TEMPLATES["voice_chat"], dual_brain_enabled=True
    )


# ---------------------------------------------------------------------------
# template_provider (SA-09 注册表侧, FR-5/FR-11): 越白名单 provider → 报错。
# ---------------------------------------------------------------------------


def test_template_provider_outside_stt_whitelist_raises_value_error():
    bad_templates = {
        "bogus": ScenarioTemplate(
            id="bogus",
            label="bogus",
            identity_section="identity",
            services=ServiceChoice(stt_provider="not_a_real_provider"),
        )
    }
    with pytest.raises(ValueError):
        scenarios._validate_templates(bad_templates)


def test_template_provider_outside_tts_whitelist_raises_value_error():
    bad_templates = {
        "bogus": ScenarioTemplate(
            id="bogus",
            label="bogus",
            identity_section="identity",
            services=ServiceChoice(tts_provider="not_a_real_provider"),
        )
    }
    with pytest.raises(ValueError):
        scenarios._validate_templates(bad_templates)


def test_template_provider_assemblyai_is_whitelisted_for_stt():
    """修订 R2：assemblyai 在 STT 白名单内，不触发 fail-fast。"""
    ok_templates = {
        "ok": ScenarioTemplate(
            id="ok",
            label="ok",
            identity_section="identity",
            services=ServiceChoice(stt_provider="assemblyai"),
        )
    }
    scenarios._validate_templates(ok_templates)  # 不抛异常


def test_template_provider_mismatched_id_raises_value_error():
    """INV-1 也走同一条 fail-fast 通道：注册表 key 与 template.id 不一致即报错。"""
    bad_templates = {
        "key_a": ScenarioTemplate(id="key_b", label="x", identity_section="identity"),
    }
    with pytest.raises(ValueError):
        scenarios._validate_templates(bad_templates)


# ---------------------------------------------------------------------------
# frozen (SA-13 模板侧, FR-3): ScenarioTemplate / ServiceChoice 均 frozen。
# ---------------------------------------------------------------------------


def test_frozen_scenario_template_raises_on_assignment():
    template = TEMPLATES["voice_chat"]
    with pytest.raises(FrozenInstanceError):
        template.id = "mutated"  # type: ignore[misc]


def test_frozen_service_choice_raises_on_assignment():
    choice = ServiceChoice()
    with pytest.raises(FrozenInstanceError):
        choice.stt_provider = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# tutor_persona (SA-16, FR-7): C-1 负向锚 / C-2/C-3 正向锚 / C-5。
# ---------------------------------------------------------------------------


def test_tutor_persona_c1_no_pronunciation_correction_promise():
    """C-1：不承诺发音纠错，纠错范围限定语法/句式/用词；且显式自我声明不纠音。"""
    identity = prompts.IDENTITY_ENGLISH_TUTOR_SECTION
    assert "You do not correct or judge pronunciation" in identity
    for forbidden in (
        "correct your pronunciation",
        "fix your pronunciation",
        "improve your pronunciation",
        "pronunciation accuracy",
    ):
        assert forbidden not in identity


def test_tutor_persona_c2_strict_teacher_positioning():
    """C-2：措辞体现严格定义的英语教师，不滑向"陪练伙伴/教练"式软化表达。"""
    identity = prompts.IDENTITY_ENGLISH_TUTOR_SECTION
    assert "strict English teacher" in identity
    assert "not a casual conversation partner" in identity
    for softened in ("your practice buddy", "your coach", "your language partner"):
        assert softened not in identity


def test_tutor_persona_c3_language_ratio_strategy_explicit():
    """C-3：语言段须写明中英混用/中文求助的触发规则。"""
    language = prompts.LANGUAGE_TUTOR_SECTION
    assert "lead in Chinese" in language
    assert "Use English specifically for" in language
    assert "shift more of your own speech into English" in language


def test_tutor_persona_c5_identity_section_has_no_dangling_protocol_reference():
    """C-5：身份段不得写"以下是我不能做的事"一类需要后段承接的悬空句式。"""
    identity = prompts.IDENTITY_ENGLISH_TUTOR_SECTION
    assert "one of these things" not in identity
    assert "the following" not in identity
