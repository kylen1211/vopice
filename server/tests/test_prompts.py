"""Tests for prompt contract (T2.1).

验证 prompts.py 中的常量符合 fast-slow-brain 设计 §6.1。
当前测试预期会失败（常量尚未定义），属于"先红证据"。
"""

import pytest

from prompts import (
    CAPABILITY_BOUNDARY_SECTION,
    LANGUAGE_SECTION,
    OFFICIAL_SECTION,
    SYSTEM_PROMPT,
)


def test_slow_brain_prompt_contains_period_constraint():
    """T2.1 断言 1: SLOW_BRAIN_PROMPT 含"每条必须以句号"这句约束。"""
    from prompts import SLOW_BRAIN_PROMPT

    assert "每条必须以句号" in SLOW_BRAIN_PROMPT


def test_slow_brain_prompt_contains_no_output_constraint():
    """T2.1 断言 2: SLOW_BRAIN_PROMPT 含"不要输出任何内容"这句约束。"""
    from prompts import SLOW_BRAIN_PROMPT

    assert "不要输出任何内容" in SLOW_BRAIN_PROMPT


def test_dual_brain_section_contains_sentinel():
    """T2.1 断言 3: DUAL_BRAIN_SECTION 含 ∅(U+2205) 哨兵符。"""
    from prompts import DUAL_BRAIN_SECTION

    assert "∅" in DUAL_BRAIN_SECTION


def test_dual_brain_section_no_old_numbering():
    """T2.1 断言 4: DUAL_BRAIN_SECTION 不含"问题#"(防旧编号口径复活)。"""
    from prompts import DUAL_BRAIN_SECTION

    assert "问题#" not in DUAL_BRAIN_SECTION


def test_system_prompt_assembly_order():
    """T2.1 断言 5: SYSTEM_PROMPT 拼装顺序含四段(OFFICIAL/BOUNDARY/LANGUAGE/DUAL_BRAIN)按序。"""
    from prompts import DUAL_BRAIN_SECTION

    prompt = SYSTEM_PROMPT

    # 四段在 SYSTEM_PROMPT 中出现的位置
    official_pos = prompt.index(OFFICIAL_SECTION)
    boundary_pos = prompt.index(CAPABILITY_BOUNDARY_SECTION)
    language_pos = prompt.index(LANGUAGE_SECTION)
    dual_pos = prompt.index(DUAL_BRAIN_SECTION)

    # 验证顺序
    assert (
        official_pos < boundary_pos < language_pos < dual_pos
    ), f"顺序错误: official({official_pos}) < boundary({boundary_pos}) < language({language_pos}) < dual({dual_pos})"
