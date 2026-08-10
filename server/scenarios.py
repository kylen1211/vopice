"""Scenario template registry (scenario-assembly, contract §0.1/§0.2/§0.5).

Leaf module: only imports `prompts`. **不得** import `config` / `bot` / 任何
pipecat 符号，须能在无 pipecat 环境下单测（design.md hard rule 6，依赖方向
`bot → config → scenarios → prompts`）。

`TEMPLATES` 是全项目场景模板集合的唯一数据源；`get_template()`/`template_ids()`
是唯一查询入口。段级 prompt 组合逻辑（`build_system_prompt`）也落在本模块——
放在 `prompts.py` 会让 `prompts` 反向 import `scenarios` 形成环。

INV-2（`TEMPLATES.keys()` 与 config.py 的 `_PHASE2_SCENARIOS` 不相交）依赖
方向上只有 config.py 同时看得见两侧，故其运行期自检落 config.py（T-2）；
本模块只负责 INV-1/INV-3/INV-4，数据侧断言另在 tests/test_scenarios.py 固化。
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

import prompts

# STT/TTS provider 白名单（INV-3，修订 R2）：云端 provider 专用，不引入本地模型
# （FR-5）。这是 scenarios.py 自带的一份独立副本，供本模块 import 期自检使用；
# config.py 按生效值另有一份自己的白名单做复核（同构既有 provider 白名单约定，
# 两处不共享同一个常量对象，避免叶子模块与配置层反向耦合）。
_STT_PROVIDER_WHITELIST: frozenset[str] = frozenset({"soniox", "deepgram", "assemblyai"})
_TTS_PROVIDER_WHITELIST: frozenset[str] = frozenset({"elevenlabs", "cartesia"})

# 模板 identity_section 不得夹带的不可覆盖段文本（INV-4）：护栏 / 能力边界 /
# 简洁 / 双脑，四段一律无条件取常量，模板即使夹带也不生效——在此提前拦截，
# 让"模板作者以为写进身份段就能生效"这个错误在 import 期就报错，而不是运行时
# 悄悄被组合函数忽略。
_FORBIDDEN_IDENTITY_SUBSTRINGS: tuple[tuple[str, str], ...] = (
    ("VOICE_SAFETY_SECTION", prompts.VOICE_SAFETY_SECTION),
    ("CAPABILITY_BOUNDARY_SECTION", prompts.CAPABILITY_BOUNDARY_SECTION),
    ("CONCISENESS_SECTION", prompts.CONCISENESS_SECTION),
    ("DUAL_BRAIN_SECTION", prompts.DUAL_BRAIN_SECTION),
)


@dataclass(frozen=True)
class ServiceChoice:
    """一个模板对 STT/TTS/快脑模型的可选覆盖；每个字段 `None` = 沿用环境变量/内置默认。

    `fast_llm_model` 只影响快脑，不影响 `dispatch_llm`（派活委派轮模型，见
    contract §0.3 优先级表）。
    """

    stt_provider: str | None = None
    stt_model: str | None = None
    tts_provider: str | None = None
    tts_voice: str | None = None
    tts_model: str | None = None
    fast_llm_model: str | None = None


@dataclass(frozen=True)
class ScenarioTemplate:
    """场景模板：id/label + prompt 段覆盖（身份段必选、语言段可选）+ 服务覆盖。"""

    id: str
    label: str
    identity_section: str
    language_section: str | None = None
    services: ServiceChoice = field(default_factory=ServiceChoice)


def _validate_templates(templates: Mapping[str, ScenarioTemplate]) -> None:
    """import 期不变式自检（INV-1/INV-3/INV-4）；不满足即抛 `ValueError`。

    INV-5（模板除 identity_section/language_section/services 外不得携带其它
    prompt 段字段）由 `ScenarioTemplate` 的固定字段集合结构性保证，无需在此
    重复校验；INV-2 落 config.py，不在此处。
    """
    seen_ids: set[str] = set()
    for key, template in templates.items():
        # INV-1
        if template.id != key:
            raise ValueError(
                f"模板注册表 key={key!r} 与 template.id={template.id!r} 不一致（INV-1）"
            )
        if template.id in seen_ids:
            raise ValueError(f"模板 id={template.id!r} 重复注册（INV-1）")
        seen_ids.add(template.id)

        # INV-4：identity_section 非空且不夹带不可覆盖段文本
        if not template.identity_section:
            raise ValueError(f"模板 {template.id!r} 的 identity_section 不得为空（INV-4）")
        for section_name, section_text in _FORBIDDEN_IDENTITY_SUBSTRINGS:
            if section_text in template.identity_section:
                raise ValueError(
                    f"模板 {template.id!r} 的 identity_section 夹带了不可覆盖段 "
                    f"{section_name} 的原文（INV-4）"
                )

        # INV-4：language_section 若提供须非空
        if template.language_section is not None and not template.language_section:
            raise ValueError(f"模板 {template.id!r} 的 language_section 若提供须非空（INV-4）")

        # INV-3：声明的 STT/TTS provider（非 None 时）须落在云端白名单内
        stt_provider = template.services.stt_provider
        if stt_provider is not None and stt_provider not in _STT_PROVIDER_WHITELIST:
            raise ValueError(
                f"模板 {template.id!r} 的 stt_provider={stt_provider!r} 越出白名单 "
                f"{sorted(_STT_PROVIDER_WHITELIST)}（INV-3）"
            )
        tts_provider = template.services.tts_provider
        if tts_provider is not None and tts_provider not in _TTS_PROVIDER_WHITELIST:
            raise ValueError(
                f"模板 {template.id!r} 的 tts_provider={tts_provider!r} 越出白名单 "
                f"{sorted(_TTS_PROVIDER_WHITELIST)}（INV-3）"
            )


# v1 模板集合（contract §0.2）。TEMPLATES 是全项目模板集合唯一数据源，
# 不存在第二处硬编码模板定义（FR-1）。
TEMPLATES: Mapping[str, ScenarioTemplate] = {
    "voice_chat": ScenarioTemplate(
        id="voice_chat",
        label="默认",
        identity_section=prompts.IDENTITY_DEFAULT_SECTION,
        # language_section 缺省 = 回落 prompts.LANGUAGE_SECTION 原文，
        # 现有默认组合行为与变更前完全等价。
        services=ServiceChoice(),
    ),
    "english_tutor": ScenarioTemplate(
        id="english_tutor",
        label="英语陪练(严格英语教师)",
        identity_section=prompts.IDENTITY_ENGLISH_TUTOR_SECTION,
        language_section=prompts.LANGUAGE_TUTOR_SECTION,
        # 契约 §0.2 修订 R2 钉死：陪练模板 STT 必须是 assemblyai
        # （universal-3-5-pro 原生中英 code-switch，解语言轴，ADR-8）。
        services=ServiceChoice(stt_provider="assemblyai"),
    ),
}

_validate_templates(TEMPLATES)


def get_template(template_id: str) -> ScenarioTemplate:
    """按 id 查模板；未注册 → `KeyError`（由 config 层转 `ConfigError`）。"""
    return TEMPLATES[template_id]


def template_ids() -> frozenset[str]:
    """全部已注册模板 id。"""
    return frozenset(TEMPLATES.keys())


def build_system_prompt(template: ScenarioTemplate, *, dual_brain_enabled: bool) -> str:
    """按 contract §0.5 段序拼装完整 system_instruction。

    可覆盖段（身份/语言）取值一律"模板值优先、缺省回落默认常量"；护栏/能力
    边界/简洁三段无条件取常量，模板即使夹带也不生效；双脑段仅开启态注入，
    段间用 "\\n\\n" 连接。
    """
    language_section = template.language_section or prompts.LANGUAGE_SECTION
    sections = [
        template.identity_section,
        prompts.VOICE_SAFETY_SECTION,
        prompts.CAPABILITY_BOUNDARY_SECTION,
        language_section,
        prompts.CONCISENESS_SECTION,
    ]
    if dual_brain_enabled:
        sections.append(prompts.DUAL_BRAIN_SECTION)
    return "\n\n".join(sections)
