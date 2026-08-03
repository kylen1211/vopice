"""Tests for prompt contract (T2.1, fast-slow-brain design §6.7).

先红证据口径（全局约束头）：collection/import 级失败不算先红——必须是断言级
失败（用例跑起来了、断言不满足）。`from prompts import SLOW_BRAIN_PROMPT` 在
符号不存在时会在 collection 阶段直接 ImportError，整个测试文件收集失败，
不算合规的先红。故这里改用 `import prompts`（模块本身一定存在）+
`hasattr` 断言，让"符号尚未定义"本身表现为一次真实的 AssertionError。
"""

import prompts


def test_slow_brain_prompt_contains_period_constraint():
    """SLOW_BRAIN_PROMPT 含"每条必须以句号"这句约束。"""
    assert hasattr(prompts, "SLOW_BRAIN_PROMPT"), "SLOW_BRAIN_PROMPT 尚未定义"
    assert "每条必须以句号" in prompts.SLOW_BRAIN_PROMPT


def test_slow_brain_prompt_contains_no_output_constraint():
    """SLOW_BRAIN_PROMPT 含"不要输出任何内容"这句约束。"""
    assert hasattr(prompts, "SLOW_BRAIN_PROMPT"), "SLOW_BRAIN_PROMPT 尚未定义"
    assert "不要输出任何内容" in prompts.SLOW_BRAIN_PROMPT


def test_dual_brain_section_contains_sentinel():
    """DUAL_BRAIN_SECTION 含 ∅(U+2205) 哨兵符。"""
    assert hasattr(prompts, "DUAL_BRAIN_SECTION"), "DUAL_BRAIN_SECTION 尚未定义"
    assert "∅" in prompts.DUAL_BRAIN_SECTION


def test_dual_brain_section_no_old_numbering():
    """DUAL_BRAIN_SECTION 不含"问题#"(防旧编号口径复活)。

    先断言符号存在，避免"符号不存在→内容判空→not in 空串恒真"这类
    对负向断言无杀伤力的假绿（testing.md 负向断言锚点纪律）。
    """
    assert hasattr(prompts, "DUAL_BRAIN_SECTION"), "DUAL_BRAIN_SECTION 尚未定义"
    assert "问题#" not in prompts.DUAL_BRAIN_SECTION


def test_system_prompt_assembly_order():
    """SYSTEM_PROMPT 拼装顺序含五段(OFFICIAL/BOUNDARY/LANGUAGE/CONCISENESS/DUAL_BRAIN)按序。"""
    assert hasattr(prompts, "DUAL_BRAIN_SECTION"), "DUAL_BRAIN_SECTION 尚未定义"
    assert hasattr(prompts, "CONCISENESS_SECTION"), "CONCISENESS_SECTION 尚未定义"

    prompt = prompts.SYSTEM_PROMPT
    official_pos = prompt.index(prompts.OFFICIAL_SECTION)
    boundary_pos = prompt.index(prompts.CAPABILITY_BOUNDARY_SECTION)
    language_pos = prompt.index(prompts.LANGUAGE_SECTION)
    conciseness_pos = prompt.index(prompts.CONCISENESS_SECTION)
    dual_pos = prompt.index(prompts.DUAL_BRAIN_SECTION)

    assert official_pos < boundary_pos < language_pos < conciseness_pos < dual_pos, (
        f"顺序错误: official({official_pos}) < boundary({boundary_pos}) "
        f"< language({language_pos}) < conciseness({conciseness_pos}) < dual({dual_pos})"
    )


def test_conciseness_section_instructs_brevity():
    """CONCISENESS_SECTION 明确要求简洁、拒绝啰嗦(B5 backlog 提到的配合缓解手段：
    缩短快脑回答的音频时长，从而缩小慢脑补充触发时的竞争窗口)。"""
    assert hasattr(prompts, "CONCISENESS_SECTION"), "CONCISENESS_SECTION 尚未定义"
    assert "简洁" in prompts.CONCISENESS_SECTION
