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
    InterruptionFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMMessagesAppendFrame,
    SpeechControlParamsFrame,
    TextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMUserAggregator
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

    async def test_both_branches_receive_user_turn(self):
        """R1 穷尽性结构证明：同一 user turn 后，快脑、慢脑两个 context 各含该消息。

        触发帧选择说明：用 `LLMMessagesAppendFrame(run_llm=True)`（照抄官方
        `test_llm_messages_append` 的写法）而不是真实的 VAD/TranscriptionFrame
        触发链路——R1 要证明的是"同一份用户消息能否落进两个独立的
        `LLMUserAggregator`/`LLMContext`"，与"轮次如何被检测到"是两件不同的事
        （后者是 turn-detection 策略的职责，design §5.1 管线图里 STT→user
        aggregator 之前的环节，不在本用例范围）。`LLMMessagesAppendFrame` 直接
        表达"一条用户消息落进 context"这个语义，不依赖 VAD/转写时序，更适合做
        确定性的结构断言。
        """
        # 内容用一个纯 str 常量、每次调用处内联构造消息 dict字面量——避免把
        # dict 字面量先赋给变量再复用导致 pyright 把它推宽为 dict[str, str]
        # (丢失 role 字段的字面量类型，无法匹配 LLMContextMessage 联合类型)。
        user_message_content = "分布式系统的 CAP 定理是什么?"

        fast_context = LLMContext()
        fast_pipeline = Pipeline([LLMUserAggregator(fast_context)])
        await run_test(
            fast_pipeline,
            frames_to_send=[
                LLMMessagesAppendFrame(
                    messages=[{"role": "user", "content": user_message_content}], run_llm=True
                )
            ],
            expected_down_frames=[SpeechControlParamsFrame, LLMContextFrame],
        )

        slow_context = LLMContext()
        slow_pipeline = Pipeline([LLMUserAggregator(slow_context)])
        await run_test(
            slow_pipeline,
            frames_to_send=[
                LLMMessagesAppendFrame(
                    messages=[{"role": "user", "content": user_message_content}], run_llm=True
                )
            ],
            expected_down_frames=[SpeechControlParamsFrame, LLMContextFrame],
        )

        fast_messages = fast_context.get_messages()
        slow_messages = slow_context.get_messages()
        self.assertTrue(
            any(
                isinstance(m, dict)
                and m.get("role") == "user"
                and m.get("content") == user_message_content
                for m in fast_messages
            ),
            "快脑(fast)context 应含该用户消息",
        )
        self.assertTrue(
            any(
                isinstance(m, dict)
                and m.get("role") == "user"
                and m.get("content") == user_message_content
                for m in slow_messages
            ),
            "慢脑(slow)context 应含该用户消息",
        )

    async def test_completion_marker_triggers_one_generation(self):
        """R4 唯一结构证明：完成标记(run_llm=True)使快脑生成次数 1→2(精确值 2)。

        "快脑生成次数"操作化为"下游收到的 LLMContextFrame 个数"——
        `LLMUserAggregator._handle_llm_messages_append` 在 `run_llm=True` 时
        `push_context_frame()`，这正是"即将触发一次 LLM 生成"的信号（官方
        `tests/test_context_aggregators_universal.py::test_llm_messages_append_run`
        同一模式）。第 1 条 `LLMContextFrame` 来自用户本来的提问(基线 1)，第 2
        条来自 `dual_brain.slow_material_transformer` 对 `LLMFullResponseEndFrame`
        的真实产出(不手写字面量,保持与 T3.4 产出一致)。
        """
        self._assert_dual_brain_module_ready()
        assert dual_brain is not None  # pyright narrowing; runtime already asserted above

        fast_context = LLMContext()
        pipeline = Pipeline([LLMUserAggregator(fast_context)])

        user_turn_frame = LLMMessagesAppendFrame(
            messages=[{"role": "user", "content": "介绍一下 CAP 定理。"}],
            run_llm=True,
        )

        done_frame = await dual_brain.slow_material_transformer(LLMFullResponseEndFrame())
        self.assertIsInstance(
            done_frame, LLMMessagesAppendFrame, "slow_material_transformer 对完成标记应产出 LLMMessagesAppendFrame"
        )
        assert isinstance(done_frame, LLMMessagesAppendFrame)  # pyright narrowing
        self.assertIs(True, done_frame.run_llm, "完成标记帧必须 run_llm=True 才能触发快脑生成")

        down, _ = await run_test(
            pipeline,
            frames_to_send=[user_turn_frame, done_frame],
            expected_down_frames=[
                SpeechControlParamsFrame,
                LLMContextFrame,
                LLMContextFrame,
            ],
        )

        context_frames = [f for f in down if isinstance(f, LLMContextFrame)]
        self.assertEqual(
            2,
            len(context_frames),
            "用户提问(基线 1)+ 完成标记(第 2 次)应使快脑生成次数精确为 2,不是 >= 2",
        )

    async def test_interruption_reaches_both_branches(self):
        """R5(PoC-2 S2 固化)：打断帧快脑、慢脑两分支各收到 1 次。

        慢脑侧：`slow_material_filter` 是模块级单例，跨测试方法共享状态——先送
        `LLMFullResponseStartFrame()` 复位三态（不依赖其它测试方法的执行顺序），
        再用"打断前/后对同一类型 TextFrame 的返回值 True→False"这一行为断言
        证明 `InterruptionFrame` 被慢脑分支真实处理（`aborted` 从 False 翻转为
        True，design §5.2 行③）。测试结束前再复位一次，不把 aborted=True 的
        残留状态带给同文件里排在后面的测试方法。

        快脑侧：照抄官方 `test_multiple_responses_interruption`/`test_interruption`
        的模式（打断帧作为 SystemFrame 会被 `FrameProcessor.process_frame`
        基类处理后，`LLMUserAggregator` 自身的 `process_frame` 落入 else 分支
        原样透传下游）——断言 `Pipeline([LLMUserAggregator(context)])` 收到
        `InterruptionFrame()` 后，下游恰好透传 1 次,证明聚合器确实"收到"了它。
        """
        self._assert_dual_brain_module_ready()
        assert dual_brain is not None  # pyright narrowing; runtime already asserted above

        # 慢脑侧：先复位单例状态，不依赖测试执行顺序。
        await dual_brain.slow_material_filter(LLMFullResponseStartFrame())

        before = await dual_brain.slow_material_filter(TextFrame(text="要点一。"))
        self.assertTrue(before, "打断前，正常要点应被放行(True)")

        interruption_result = await dual_brain.slow_material_filter(InterruptionFrame())
        self.assertFalse(interruption_result, "InterruptionFrame 本身永不产出(设计契约:恒 False)")

        after = await dual_brain.slow_material_filter(TextFrame(text="要点二。"))
        self.assertFalse(
            after, "打断后，同一状态对同一类型 TextFrame 的返回应翻转为 False(aborted=True 已生效)"
        )

        # 复位单例状态，不污染文件内排在后面的测试方法。
        await dual_brain.slow_material_filter(LLMFullResponseStartFrame())

        # 快脑侧：InterruptionFrame 经 LLMUserAggregator 恰好透传 1 次下游。
        fast_context = LLMContext()
        fast_pipeline = Pipeline([LLMUserAggregator(fast_context)])
        down, _ = await run_test(
            fast_pipeline,
            frames_to_send=[InterruptionFrame()],
            expected_down_frames=[SpeechControlParamsFrame, InterruptionFrame],
        )
        self.assertEqual(
            1,
            sum(1 for f in down if isinstance(f, InterruptionFrame)),
            "快脑侧应恰好收到并透传 1 次打断帧",
        )


if __name__ == "__main__":
    unittest.main()
