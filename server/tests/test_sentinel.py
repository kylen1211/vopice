"""Tests for the sentinel gate (T4.1, fast-slow-brain design §6.6/§8.1).

先红证据口径（全局约束头）：collection/import 级失败不算先红——必须是断言级
失败（用例跑起来了、断言不满足）。`server/sentinel.py` 当前尚不存在，直接
`import sentinel` 会在 collection 阶段就 ModuleNotFoundError，让整个测试文件
收集失败，不算合规先红（第 2 组 commit 1b65d32 踩过的坑）。故这里改用
`try: import sentinel except ModuleNotFoundError: sentinel = None` +
每个测试方法开头 `assertIsNotNone`/`hasattr` 断言，让"模块/符号未定义"本身
表现为一次真实的 AssertionError。

断言对象是官方 `FunctionFilter(filter=sentinel.sentinel_gate)`，用官方
`pipecat.tests.utils.run_test` 做帧级测试（design §8.1 R6 派生行的精确定义）。

契约要点（design §6.6，源码已核对 SAME，见下方各处行号复核记录）：
- `FunctionFilter._should_passthrough_frame`（venv `.../filters/function_filter.py:57-71`）
  只自动放行 `StartFrame`/`EndFrame`/`CancelFrame`（管线生命周期帧）与
  `SystemFrame`；`LLMFullResponseStartFrame`/`LLMFullResponseEndFrame` 是
  `ControlFrame`（venv `.../frames/frames.py:1898,1913`），不在自动放行名单
  内 —— 生死完全由 `sentinel_gate` 的返回值决定。
- 谓词语义：`LLMFullResponseStartFrame` 重置状态 → 本轮首个 `LLMTextFrame`
  若 strip 后以 `∅`（U+2205）开头则整轮 `LLMTextFrame` 全部静默，否则整轮
  全部放行；控制帧（Start/End）本身必须始终放行，不受这条状态机影响。

两向覆盖（防谓词是单向实现，比如永远 `return True`）：
1. 哨兵轮：首个 LLMTextFrame 以 ∅ 开头 → 该轮所有 LLMTextFrame 零透出，
   但 LLMFullResponseStartFrame/EndFrame 仍透出。
2. 正常轮（反向）：首个 LLMTextFrame 不以 ∅ 开头 → 该轮所有 LLMTextFrame
   全部透出，Start/End 同样透出。
两个场景各自独立走一次 `run_test` + 独立断言，不共用同一次运行的结果，
防止谓词硬编码某一个方向也能骗过测试。
"""

import unittest

try:
    import sentinel
except ModuleNotFoundError:
    sentinel = None

from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.processors.filters.function_filter import FunctionFilter
from pipecat.tests.utils import run_test


class TestSentinelGate(unittest.IsolatedAsyncioTestCase):
    """哨兵谓词 sentinel_gate 的帧级行为断言。"""

    def _assert_sentinel_module_ready(self):
        self.assertIsNotNone(sentinel, "sentinel 模块尚未定义")
        self.assertTrue(hasattr(sentinel, "sentinel_gate"), "sentinel_gate 尚未定义")

    async def test_sentinel_round_emits_no_text(self):
        """哨兵轮零文本帧透出、正常轮全部透出（两向，含控制帧放行断言）。"""
        self._assert_sentinel_module_ready()
        assert sentinel is not None  # pyright narrowing; runtime already asserted above

        # --- 场景一：哨兵轮 —— 首个 LLMTextFrame strip 后以 ∅ 开头 ---
        sentinel_round_frames = [
            LLMFullResponseStartFrame(),
            LLMTextFrame(text=" ∅"),
            LLMTextFrame(text="这段本不该被朗读出来"),
            LLMFullResponseEndFrame(),
        ]
        (received_down, _) = await run_test(
            FunctionFilter(filter=sentinel.sentinel_gate),
            frames_to_send=sentinel_round_frames,
        )

        # 控制帧必须仍被放行（design §6.6 设计红队 I-M5 的核心断言）。
        self.assertEqual(
            [type(f) for f in received_down],
            [LLMFullResponseStartFrame, LLMFullResponseEndFrame],
            "哨兵轮应放行 Start/End 控制帧，且零 LLMTextFrame 透出",
        )
        # 显式再断言一次零文本帧透出，作为独立、意图更直白的锚点。
        text_frames = [f for f in received_down if isinstance(f, LLMTextFrame)]
        self.assertEqual(len(text_frames), 0, "哨兵轮不应有任何 LLMTextFrame 透出")

        # --- 场景二（反向）：正常轮 —— 首个 LLMTextFrame 不以 ∅ 开头 ---
        normal_round_frames = [
            LLMFullResponseStartFrame(),
            LLMTextFrame(text="你好"),
            LLMTextFrame(text="，很高兴认识你"),
            LLMFullResponseEndFrame(),
        ]
        (received_down_normal, _) = await run_test(
            FunctionFilter(filter=sentinel.sentinel_gate),
            frames_to_send=normal_round_frames,
        )

        self.assertEqual(
            [type(f) for f in received_down_normal],
            [
                LLMFullResponseStartFrame,
                LLMTextFrame,
                LLMTextFrame,
                LLMFullResponseEndFrame,
            ],
            "正常轮应放行 Start/End 控制帧，且全部 LLMTextFrame 透出",
        )
        text_frames_normal = [
            f for f in received_down_normal if isinstance(f, LLMTextFrame)
        ]
        self.assertEqual(len(text_frames_normal), 2, "正常轮应有全部 2 条 LLMTextFrame 透出")
        self.assertEqual(
            [f.text for f in text_frames_normal],
            ["你好", "，很高兴认识你"],
            "正常轮透出的文本内容应与发送内容一致（防止误伤内容本身）",
        )


if __name__ == "__main__":
    unittest.main()
