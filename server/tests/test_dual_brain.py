"""Tests for the dual-brain 慢脑状态与 Producer 谓词 (T3.1, fast-slow-brain design §5.2/§6.1/§8.1/§15).

先红证据口径（全局约束头）：collection/import 级失败不算先红——必须是断言级
失败（用例跑起来了、断言不满足）。`server/dual_brain.py` 当前尚不存在（3.2/3.3/3.4
号任务才创建），直接 `import dual_brain` 会在 collection 阶段就 ModuleNotFoundError，
让整个测试文件收集失败，不算合规先红（第 2 组 commit 1b65d32、第 4 组
test_sentinel.py 都踩过/绕过这个坑）。故这里同样改用
`try: import dual_brain except ModuleNotFoundError: dual_brain = None` +
每个测试方法开头 `assertIsNotNone`/`hasattr` 断言，让"模块/符号未定义"本身
表现为一次真实的 AssertionError。

三个用例的断言意图（design §8.1 R3/R4/R8 派生行、§15 PoC-1/PoC-2 S1）：
1. test_material_lands_only_in_fast_context（固化 PoC-1）：驱动一个最小化的
   `ProducerProcessor(filter=slow_material_filter, transformer=slow_material_transformer,
   passthrough=True)` + `ConsumerProcessor(producer=...)` 场景（照抄官方
   `tests/test_producer_consumer.py` 的 run_test + SleepFrame 写法），验证要点
   最终以 `LLMMessagesAppendFrame(run_llm=False)` 落进 Consumer 侧（代表快脑），
   而 Producer 自身的 passthrough 流（代表慢脑自身历史/输出）里的 `TextFrame`
   内容原封不动、不含任何注入模板痕迹（隔离反证，精确条数断言）。
2. test_failed_slow_turn_emits_no_completion_marker（固化 §5.2 表②的 R8 击穿
   路径 + PoC-2 S1 反向）：慢脑本轮零要点（没有任何 TextFrame）时收到
   `LLMFullResponseEndFrame`，谓词不得产出完成标记——既从帧级验证 Consumer
   侧零 `LLMMessagesAppendFrame`，也直接断言 `slow_material_filter` 对该
   `LLMFullResponseEndFrame` 的返回值严格为 `False`。
3. test_incremental_inject_does_not_trigger（反向/防御，PoC-1 结论的另一半）：
   同一次真实驱动里，transformer 产出的增量要点帧 `run_llm` 字段必须严格为
   `False`，完成标记帧则必须严格为 `True`——防止"任何注入都触发"的短路实现。

三条用例都不依赖/不校验 `basis` 是否与某个真实 `LLMContext` 一致（那是 R7 系列
用例——`test_barge_in_drops_inflight_material` 等——的职责，design §8.1 已把它们
列为单独的用例，不在本任务 T3.1 范围内）。`slow_material_filter` 在真实系统里
如何取得"当时慢脑 context 的最后一条 user 消息"（§5.2 状态迁移落点）不是
`(frame) -> bool` 签名本身能表达的，属于 3.2/3.3 号任务的内部实现细节；本文件
的三个场景都以 `LLMFullResponseStartFrame()` 开场触发状态复位，不依赖具体的
取值机制，因此不受这个实现细节影响。
"""

import unittest

try:
    import dual_brain
except ModuleNotFoundError:
    dual_brain = None

from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMMessagesAppendFrame,
    TextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.consumer_processor import ConsumerProcessor
from pipecat.processors.producer_processor import ProducerProcessor
from pipecat.tests.utils import SleepFrame, run_test

import prompts


class TestDualBrain(unittest.IsolatedAsyncioTestCase):
    """慢脑状态(SlowBrainState) + Producer 谓词/transformer 的帧级行为断言。"""

    def _assert_dual_brain_module_ready(self):
        self.assertIsNotNone(dual_brain, "dual_brain 模块尚未定义")
        self.assertTrue(hasattr(dual_brain, "SlowBrainState"), "SlowBrainState 尚未定义")
        self.assertTrue(hasattr(dual_brain, "slow_material_filter"), "slow_material_filter 尚未定义")
        self.assertTrue(
            hasattr(dual_brain, "slow_material_transformer"), "slow_material_transformer 尚未定义"
        )

    async def _run_slow_branch(self, points: list[str]) -> list:
        """驱动最小化的慢脑分支 Producer/Consumer 场景，返回 Consumer 下游收到的帧。

        帧序：`LLMFullResponseStartFrame`（复位三态、记 basis）→ 每条 `points`
        各一个 `TextFrame`（SentenceAggregator 切出的要点句）→
        `LLMFullResponseEndFrame`。每次可能触发 Producer `_produce()` 的帧后都
        插一个 `SleepFrame()`，照抄官方 `tests/test_producer_consumer.py` 的写法
        ——给 Consumer 的后台任务一个机会把队列里的帧提前推到下游，避免
        `EndFrame` 到达时队列里还有帧没被 `ConsumerProcessor` 取走就被取消。
        """
        producer = ProducerProcessor(
            filter=dual_brain.slow_material_filter,
            transformer=dual_brain.slow_material_transformer,
            passthrough=True,
        )
        consumer = ConsumerProcessor(producer=producer)
        pipeline = Pipeline([producer, consumer])

        frames_to_send = [LLMFullResponseStartFrame(), SleepFrame()]
        for point in points:
            frames_to_send.append(TextFrame(text=point))
            frames_to_send.append(SleepFrame())
        frames_to_send.append(LLMFullResponseEndFrame())
        frames_to_send.append(SleepFrame())

        received_down, _ = await run_test(pipeline, frames_to_send=frames_to_send)
        return list(received_down)

    async def test_material_lands_only_in_fast_context(self):
        """PoC-1 固化：要点落进 Consumer(快脑)侧，慢脑自身 passthrough 流不含注入痕迹。"""
        self._assert_dual_brain_module_ready()

        point = "分区容错是分布式系统的刚性约束。"
        down = await self._run_slow_branch([point])

        # Consumer(代表快脑)侧应恰好收到 2 条 LLMMessagesAppendFrame：
        # 一条增量要点、一条完成标记——精确条数，不用 >=。
        material_frames = [f for f in down if isinstance(f, LLMMessagesAppendFrame)]
        self.assertEqual(
            2, len(material_frames), "应恰好产出 1 条增量要点帧 + 1 条完成标记帧"
        )

        increment_frames = [f for f in material_frames if f.run_llm is False]
        completion_frames = [f for f in material_frames if f.run_llm is True]
        self.assertEqual(1, len(increment_frames), "应恰有 1 条 run_llm=False 的增量帧")
        self.assertEqual(1, len(completion_frames), "应恰有 1 条 run_llm=True 的完成标记帧")

        increment = increment_frames[0]
        self.assertEqual(1, len(increment.messages))
        self.assertEqual("user", increment.messages[0]["role"])
        self.assertEqual(
            prompts.INJECT_POINT_TEMPLATE.format(point=point),
            increment.messages[0]["content"],
        )

        completion = completion_frames[0]
        self.assertEqual(1, len(completion.messages))
        self.assertEqual("user", completion.messages[0]["role"])
        self.assertEqual(prompts.INJECT_DONE_TEMPLATE, completion.messages[0]["content"])

        # 隔离反证：慢脑自身的 passthrough 流里只有原样的 TextFrame，
        # 内容与条数都精确——不含被注入快脑的模板痕迹。
        slow_side_text_frames = [f for f in down if isinstance(f, TextFrame)]
        self.assertEqual(1, len(slow_side_text_frames), "慢脑自身流应恰好保留 1 条原样 TextFrame")
        self.assertEqual(point, slow_side_text_frames[0].text)
        for marker in ("已完成", "针对上一个问题", "慢脑深析要点"):
            self.assertNotIn(
                marker,
                slow_side_text_frames[0].text,
                "慢脑自身输出流不得含注入模板的痕迹",
            )

        # 控制帧原样透出，条数精确。
        self.assertEqual(
            1, sum(1 for f in down if isinstance(f, LLMFullResponseStartFrame))
        )
        self.assertEqual(1, sum(1 for f in down if isinstance(f, LLMFullResponseEndFrame)))

    async def test_failed_slow_turn_emits_no_completion_marker(self):
        """§5.2 表②/PoC-2 S1 反向：零要点 + LLMFullResponseEndFrame 不得产出完成标记。"""
        self._assert_dual_brain_module_ready()
        assert dual_brain is not None  # pyright narrowing; runtime already asserted above

        # 慢脑本轮零输出（框架失败路径的 finally 块仍会推 LLMFullResponseEndFrame，
        # 但中间没有任何 TextFrame——has_material 全程保持 False）。
        down = await self._run_slow_branch([])

        material_frames = [f for f in down if isinstance(f, LLMMessagesAppendFrame)]
        self.assertEqual(0, len(material_frames), "零要点时不得产出任何注入/完成标记帧")

        self.assertEqual(
            1, sum(1 for f in down if isinstance(f, LLMFullResponseStartFrame))
        )
        self.assertEqual(1, sum(1 for f in down if isinstance(f, LLMFullResponseEndFrame)))

        # 直接核对谓词契约本身：稳态(has_material=False, aborted=False)下，
        # 对 LLMFullResponseEndFrame 的返回值必须严格为 False（design §5.2 帧路由表）。
        result = await dual_brain.slow_material_filter(LLMFullResponseEndFrame())
        self.assertFalse(result, "零要点时 slow_material_filter 对 EndFrame 必须返回 False")

    async def test_incremental_inject_does_not_trigger(self):
        """反向/防御(PoC-1 结论的另一半)：增量帧 run_llm 严格 False,完成帧严格 True。"""
        self._assert_dual_brain_module_ready()

        point = "慢脑深析要点乙。"
        down = await self._run_slow_branch([point])

        material_frames = [f for f in down if isinstance(f, LLMMessagesAppendFrame)]
        self.assertEqual(2, len(material_frames), "应恰好产出 1 条增量要点帧 + 1 条完成标记帧")

        increment_frames = [
            f
            for f in material_frames
            if f.messages[0]["content"] == prompts.INJECT_POINT_TEMPLATE.format(point=point)
        ]
        completion_frames = [
            f for f in material_frames if f.messages[0]["content"] == prompts.INJECT_DONE_TEMPLATE
        ]
        self.assertEqual(1, len(increment_frames))
        self.assertEqual(1, len(completion_frames))

        # 防"任何注入都触发"的短路实现：两者必须严格区分 True/False（用 assertIs
        # 而非真值判断，防止 None 之类的假实现蒙混过关）。
        self.assertIs(
            False,
            increment_frames[0].run_llm,
            "增量要点帧 run_llm 必须严格为 False,不得触发快脑再生成",
        )
        self.assertIs(
            True,
            completion_frames[0].run_llm,
            "完成标记帧 run_llm 必须严格为 True,与增量帧形成对照",
        )


if __name__ == "__main__":
    unittest.main()
