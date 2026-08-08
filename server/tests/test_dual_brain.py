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

import asyncio
import contextlib
import unittest

import loguru

try:
    import dual_brain
except ModuleNotFoundError:
    dual_brain = None

from pipecat.frames.frames import (
    EndFrame,
    ErrorFrame,
    InterruptionFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMMessagesAppendFrame,
    LLMTextFrame,
    SpeechControlParamsFrame,
    StartFrame,
    SystemFrame,
    TextFrame,
)
from pipecat.pipeline.parallel_pipeline import ParallelPipeline
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMUserAggregator
from pipecat.processors.consumer_processor import ConsumerProcessor
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame
from pipecat.processors.producer_processor import ProducerProcessor
from pipecat.tests.utils import SleepFrame, run_test

import prompts

# task-dispatch (C4 派活, T-6): `task_dispatch.py` already exists (T-4
# delivered it before this task starts), so no ModuleNotFoundError guard is
# needed here — unlike `dual_brain` above, whose guard dates back to when
# T3.1 was authored before `dual_brain.py` existed.
import task_dispatch


def _message_field(message, field: str):
    """Safely read a field from an `LLMMessagesAppendFrame.messages[i]` entry.

    Pyright types that field as a union including `LLMSpecificMessage`,
    which has no `__getitem__`, and TypedDict variants where `content` isn't
    a required key — direct `message["role"]`/`message["content"]` indexing
    trips `reportIndexIssue`/`reportTypedDictNotRequiredAccess` (組末評審
    HIGH-2 修复,组内其它位置已用 `isinstance(m, dict) and m.get(...)` 这个
    模式,这里统一抽成一个小helper复用,不逐处重复写).
    """
    if isinstance(message, dict):
        return message.get(field)
    return None


@contextlib.contextmanager
def _capture_dual_brain_logs():
    """临时挂一个 loguru sink,只捕获本次 `with` 块内产生的日志文本(T3.5)。

    `caplog`(pytest 内置)捕获不到 loguru 的输出——loguru 有自己独立的 sink
    系统,不经过标准库 `logging` 的 handler 链。这里用 `loguru.logger.add(...)`
    临时挂一个函数 sink,`msg.record["message"]` 取出格式化前的原始消息文本
    (2026-08-02 实测核实:当前 venv `loguru==0.7.3`,该模式可用,见任务卡
    "关键设计提醒 2")。`finally` 里 `logger.remove(sink_id)`,不影响其它测试
    方法或默认 sink。
    """
    captured: list[str] = []
    sink_id = loguru.logger.add(lambda msg: captured.append(msg.record["message"]), level="INFO")
    try:
        yield captured
    finally:
        loguru.logger.remove(sink_id)


class _ErrorEmitter(FrameProcessor):
    """最小故障桩(第 6 组,design §15 PoC-2 S3 固化用)。

    对任何非 `StartFrame`/`EndFrame`/`SystemFrame` 的帧 `push_error("boom",
    fatal=False)`——控制帧原样透传下游,其余帧只报错、不继续下推(本用例里它
    是分支内唯一/最后一个处理器,不下推不影响分支间同步,见
    `test_slow_error_does_not_stop_fast_branch` docstring)。这条桩测的是
    `ParallelPipeline` 框架本身的分支隔离行为,不是本组新写的代码。
    """

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, (StartFrame, EndFrame, SystemFrame)):
            await self.push_frame(frame, direction)
            return
        await self.push_error("boom", fatal=False)


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
        assert dual_brain is not None  # pyright narrowing; callers already assert module readiness
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
        self.assertEqual("user", _message_field(increment.messages[0], "role"))
        self.assertEqual(
            prompts.INJECT_POINT_TEMPLATE.format(point=point),
            _message_field(increment.messages[0], "content"),
        )

        completion = completion_frames[0]
        self.assertEqual(1, len(completion.messages))
        self.assertEqual("user", _message_field(completion.messages[0], "role"))
        self.assertEqual(
            prompts.INJECT_DONE_TEMPLATE, _message_field(completion.messages[0], "content")
        )

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
        """§5.2 表②/PoC-2 S1 反向：零要点 + LLMFullResponseEndFrame 不得产出完成标记。

        组末评审 HIGH-1 修复：原版只驱动"稳态下零要点"这一条路径——`down =
        await self._run_slow_branch([])` 用的是模块级共享单例
        `dual_brain.slow_material_filter`，而按 `unittest` 字母序执行，本用例
        是文件里第一个真正触达该单例状态的用例，`has_material` 此刻本就还是
        `__init__` 时的默认值 `False`。于是"`LLMFullResponseStartFrame` 必须把
        `has_material` 复位为 `False`"这条 §5.2 明写的转移语义，从未被真正验证
        过——删掉复位那一行代码，本用例（连同全套件）依然全绿（已用真实变异
        独立复现确认）。下面新增一段：先用一个**独立** `_SlowMaterialFilter()`
        实例人为造出"上一轮曾经 has_material=True"的前置状态，再验证新一轮
        `LLMFullResponseStartFrame` 到达后确实被复位、且零要点的这一轮不产出
        完成标记——直接断言内部状态字段，不依赖单例默认值或测试执行顺序。
        """
        self._assert_dual_brain_module_ready()
        assert dual_brain is not None  # pyright narrowing; runtime already asserted above

        # --- 原有路径：稳态（单例默认值）下零要点，验证帧级行为 ---
        # 慢脑本轮零输出（框架失败路径的 finally 块仍会推 LLMFullResponseEndFrame，
        # 但中间没有任何 TextFrame——has_material 全程保持 False）。
        down = await self._run_slow_branch([])

        material_frames = [f for f in down if isinstance(f, LLMMessagesAppendFrame)]
        self.assertEqual(0, len(material_frames), "零要点时不得产出任何注入/完成标记帧")

        self.assertEqual(
            1, sum(1 for f in down if isinstance(f, LLMFullResponseStartFrame))
        )
        self.assertEqual(1, sum(1 for f in down if isinstance(f, LLMFullResponseEndFrame)))

        # --- 新增路径：独立实例，人为造脏状态，直接验证 Start 帧的复位转移点 ---
        filt = dual_brain._SlowMaterialFilter()

        # Turn 1：产出一条要点，让 has_material 真的变成 True（前置条件，
        # 用断言证明而非假设）。
        await filt(LLMFullResponseStartFrame())
        accepted = await filt(TextFrame(text="turn-1 的要点，用于弄脏状态。"))
        self.assertTrue(accepted, "前置条件：turn 1 的要点应被正常接受")
        self.assertTrue(
            filt._state.has_material, "前置条件：turn 1 结束前 has_material 应已为 True"
        )
        turn1_completion = await filt(LLMFullResponseEndFrame())
        self.assertTrue(turn1_completion, "turn 1 有材料，完成标记应正常产出")

        # Turn 2：全新一轮，零要点。新的 LLMFullResponseStartFrame 必须把
        # has_material 复位为 False——这正是被变异③证明此前未被覆盖的那一步。
        await filt(LLMFullResponseStartFrame())
        self.assertFalse(
            filt._state.has_material,
            "新一轮 LLMFullResponseStartFrame 到达后，has_material 必须被复位为 "
            "False，即便上一轮曾经为 True(§5.2 状态迁移落点)",
        )
        turn2_result = await filt(LLMFullResponseEndFrame())
        self.assertFalse(
            turn2_result, "turn 2 零要点，即便上一轮遗留过 True，完成标记也不得产出"
        )

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
            if _message_field(f.messages[0], "content")
            == prompts.INJECT_POINT_TEMPLATE.format(point=point)
        ]
        completion_frames = [
            f
            for f in material_frames
            if _message_field(f.messages[0], "content") == prompts.INJECT_DONE_TEMPLATE
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

    async def test_barge_in_drops_inflight_material(self):
        """R7 主力(design §5.2 主次两道闸、§8.1 R7 派生·主力,tasks.md T3.5)。

        正向(打断)完整帧序,任务卡写死、不得自行调整:
        旧轮 `LLMFullResponseStartFrame` → 旧要点 A(应注入)→ `InterruptionFrame`
        → 旧要点 B(应丢弃,打 `stale-drop reason=aborted`)→ 新问题落进 context
        (模拟 STT+聚合落地,§5.2 表③的"新 user 消息")→ 新轮
        `LLMFullResponseStartFrame`(basis 应随之更新到新问题)。

        不复用模块级单例 `dual_brain.slow_material_filter`——本文件已有 6 条
        用例在共享它(见 `test_failed_slow_turn_emits_no_completion_marker`/
        `test_interruption_reaches_both_branches`),本用例还需要在驱动过程中
        修改 context 内容来触发 basis 校验分支，与共享单例的复位纪律耦合、
        且会给同文件其它用例留下状态残留风险；改用每条用例自己的
        `_SlowMaterialFilter()` 全新实例(私有类但模块内可直接实例化)+
        自己的 `LLMContext()`,状态完全隔离。

        `LLMContext(messages=[...])` 构造与 `add_message()`/`get_messages()`
        接口都很简单(`llm_context.py:103-122,380-386`实读)，直接用真实
        `LLMContext`，不再自造 stub。

        "新问题落进 context"只用 `context.add_message(...)` 模拟(`_current_basis()`
        只依赖 `get_messages()` 的内容，不关心是谁调用的 `add_message`)。
        design §5.2 帧路由表只列了 4 种帧(`LLMFullResponseStartFrame`/
        `TextFrame`/`LLMFullResponseEndFrame`/`InterruptionFrame`)，
        `TranscriptionFrame` 不在表内。但 `TranscriptionFrame` 是 `TextFrame`
        的子类(`frames.py:446`)——若真的把它送进 `filter.__call__`，
        `isinstance(frame, TextFrame)` 会先命中，落进"要点材料"分支而不是
        "其余一律 False"分支，这与任务卡的前提假设相反、会把一条不相关的
        `TranscriptionFrame` 误判成慢脑要点、还会在 aborted 状态下多打一条
        `stale-drop`。为了不引入这个语义混淆，这里选择跳过发送
        `TranscriptionFrame`，只用 `context.add_message(...)` 表达"新问题已
        落进 context"这一件事——这正是 `_current_basis()` 唯一关心的东西。
        """
        self._assert_dual_brain_module_ready()
        assert dual_brain is not None  # pyright narrowing

        context = LLMContext(messages=[{"role": "user", "content": "旧问题"}])
        filt = dual_brain._SlowMaterialFilter()
        filt.bind_context(context)

        with _capture_dual_brain_logs() as captured:
            await filt(LLMFullResponseStartFrame())

            result_a = await filt(TextFrame(text="旧要点A。"))
            self.assertTrue(result_a, "打断前，旧要点 A 应被正常注入")

            interruption_result = await filt(InterruptionFrame())
            self.assertFalse(interruption_result, "InterruptionFrame 本身恒 False")

            result_b = await filt(TextFrame(text="旧要点B。"))
            self.assertFalse(result_b, "打断后，在途的旧要点 B 应被丢弃(零注入)")

        # 日志断言：当前 dual_brain.py 尚未实现打日志(3.6 号任务范围)，
        # 这里预期是红——`captured` 此刻必然为空列表，`any(...)` 恒 False。
        self.assertTrue(
            any("abort" in m for m in captured),
            "应打印 abort 日志行(当前预期红，等 T3.6 落地打日志后才会绿)",
        )
        self.assertTrue(
            any("stale-drop" in m and "reason=aborted" in m for m in captured),
            "旧要点 B 被丢弃时应打 stale-drop reason=aborted"
            "(当前预期红，等 T3.6 落地打日志后才会绿)",
        )

        # 模拟"新问题落进 context"：STT + 聚合完成后，新的 user 消息追加进
        # 慢脑 context——不送 TranscriptionFrame（理由见 docstring）。
        context.add_message({"role": "user", "content": "新问题"})

        # 新一轮开场：aborted/has_material 复位，basis 应随 context 更新为新问题。
        await filt(LLMFullResponseStartFrame())
        result_c = await filt(TextFrame(text="新要点C。"))
        self.assertTrue(
            result_c,
            "新一轮复位后（aborted=False 且 basis 已随 context 更新为新问题），"
            "新要点应能正常注入",
        )

        # 反向：同样的要点 A/B 序列，跳过 InterruptionFrame，证明谓词不是
        # 被写死为恒假——未打断时 B 也应正常注入。用全新的 filter/context
        # 实例，不与上面的正向驱动共享状态。
        context_rev = LLMContext(messages=[{"role": "user", "content": "旧问题"}])
        filt_rev = dual_brain._SlowMaterialFilter()
        filt_rev.bind_context(context_rev)

        await filt_rev(LLMFullResponseStartFrame())
        result_a_rev = await filt_rev(TextFrame(text="旧要点A。"))
        self.assertTrue(result_a_rev, "反向(未打断)：旧要点 A 应被正常注入")
        result_b_rev = await filt_rev(TextFrame(text="旧要点B。"))
        self.assertTrue(
            result_b_rev,
            "反向(未打断)：旧要点 B 同样应被正常注入——证明谓词不是恒假",
        )

    async def test_stale_material_dropped_before_inject(self):
        """防御分支(design §5.2 basis 校验，§8.1 R7 派生·防御分支)。

        手工构造"context 里 user 消息已变但未收到 `InterruptionFrame`"的帧序
        ——design §5.2 明写真实管线不会产生这个序列(basis 变了必然意味着打断已
        发生，打断已先清空队列)；这是一条纯防御性单测，锁住这道防线不被后续
        改动误删,不代表生产会走到。
        """
        self._assert_dual_brain_module_ready()
        assert dual_brain is not None  # pyright narrowing

        context = LLMContext(messages=[{"role": "user", "content": "问题甲"}])
        filt = dual_brain._SlowMaterialFilter()
        filt.bind_context(context)

        with _capture_dual_brain_logs() as captured:
            await filt(LLMFullResponseStartFrame())  # basis = "问题甲"

            # 就地修改 context：user 消息已变成"问题乙"，但没有经过
            # InterruptionFrame——真实管线不会产生这个序列，这里手工构造。
            context.add_message({"role": "user", "content": "问题乙"})

            result = await filt(TextFrame(text="要点。"))

        self.assertFalse(result, "basis 已不匹配(问题乙 != 问题甲)时应丢弃该要点")

        # 日志断言：当前预期红(3.6 号任务落地打日志后才会绿)。
        self.assertTrue(
            any("stale-drop" in m and "reason=basis-mismatch" in m for m in captured),
            "basis 不匹配时应打 stale-drop reason=basis-mismatch"
            "(当前预期红，等 T3.6 落地打日志后才会绿)",
        )

    async def test_abort_blocks_inject_before_stt_lands(self):
        """打断窗口(design §5.2 表③论证，§8.1 R7 派生·打断窗口)。

        覆盖 basis 校验的时间盲区：`InterruptionFrame` 已到但新 user 消息
        *尚未* 落进 context（STT + 聚合还没完成，context 仍显示旧问题，
        basis 校验本身会通过）——此时仍须靠 `aborted` 单独拦下要点，
        证明 `aborted` 不是靠 basis 顺带生效、而是独立的第一道闸。
        """
        self._assert_dual_brain_module_ready()
        assert dual_brain is not None  # pyright narrowing

        context = LLMContext(messages=[{"role": "user", "content": "问题甲"}])
        filt = dual_brain._SlowMaterialFilter()
        filt.bind_context(context)

        with _capture_dual_brain_logs() as captured:
            await filt(LLMFullResponseStartFrame())  # basis = "问题甲"

            interruption_result = await filt(InterruptionFrame())
            self.assertFalse(interruption_result, "InterruptionFrame 本身恒 False")

            # context 故意不改动：新 user 消息还没落地，basis 校验本身仍会通过。
            self.assertEqual(
                "问题甲",
                filt._current_basis(),
                "STT 尚未落地时，context 仍显示旧问题——basis 校验本身应仍然通过，"
                "这正是本用例要证明 aborted 独立拦截的前提",
            )

            result = await filt(TextFrame(text="要点。"))

        self.assertFalse(
            result,
            "即便 basis 仍然匹配，aborted=True 也必须单独拦下该要点"
            "(不是靠 basis 不匹配才被拦下)",
        )

        # 日志断言：当前预期红(3.6 号任务落地打日志后才会绿)。
        self.assertTrue(
            any("stale-drop" in m and "reason=aborted" in m for m in captured),
            "打断窗口内被拦下的要点应打 stale-drop reason=aborted"
            "(当前预期红，等 T3.6 落地打日志后才会绿)",
        )

    async def test_build_slow_material_filter_returns_independent_instances(self):
        """T5.2 会话隔离(比照 sentinel.py `build_sentinel_filter()` 同型修复)。

        `bot(runner_args)` 每会话跑一次(AGENTS.md §1),但没有任何机制保证
        "一进程一会话"——第 4 组组末评审已就 `sentinel.py` 的同构问题判过一次
        HIGH(模块级单例被多会话共享会互相污染状态)。`dual_brain.py` 的
        `_SlowMaterialFilter` 同样带跨调用状态(`SlowBrainState`),模块级单例
        `slow_material_filter` 只应供测试直接用(见其模块内注释),生产装配
        (T5.2 `bot.py::assemble_pipeline`)必须走一个"每次调用返回全新实例"的
        工厂,不能把模块单例接进真实管线——否则并发的两个会话会共享同一份
        `has_material`/`aborted`/`basis`。
        """
        self._assert_dual_brain_module_ready()
        assert dual_brain is not None  # pyright narrowing
        self.assertTrue(
            hasattr(dual_brain, "build_slow_material_filter"),
            "dual_brain.build_slow_material_filter 尚未定义",
        )

        filter_a = dual_brain.build_slow_material_filter()
        filter_b = dual_brain.build_slow_material_filter()
        self.assertIsNot(filter_a, filter_b, "每次调用必须返回互不相同的新实例")
        self.assertIsNot(
            filter_a,
            dual_brain.slow_material_filter,
            "工厂产出的实例不应是模块级测试单例本身",
        )

        # 状态隔离：filter_a 弄脏后，filter_b 的状态必须完全不受影响。
        await filter_a(LLMFullResponseStartFrame())
        await filter_a(TextFrame(text="要点。"))
        self.assertTrue(filter_a._state.has_material, "前置条件：filter_a 应已被弄脏")
        self.assertFalse(
            filter_b._state.has_material,
            "两个由工厂产出的实例，状态必须完全独立，不得互相污染",
        )

    async def test_slow_error_does_not_stop_fast_branch(self):
        """design §15 PoC-2 S3 固化(§8.1 R8 派生)：`ParallelPipeline` 分支隔离
        本身——慢脑分支上行的非 fatal `ErrorFrame` 不得拖垮快脑分支的正常产出。

        这条测的是官方 `ParallelPipeline` 的框架行为，不是本组(第 6 组)新写
        的代码——本组唯一新代码是 `bot.make_pipeline_error_handler`，这条用例
        不驱动它。**允许它在 6.2/6.3 实现之前就是绿的**：它的价值是把 PoC-2 S3
        的实测结论钉成永久回归锁，和本文件 `test_stale_material_dropped_before_inject`
        的写法是同一先例——"绿不证明生产正确，仅锁住该防线不被后续改动误删"，
        不要因为它一开始就绿而怀疑实现有问题。
        """
        fast_context = LLMContext()
        pipeline = Pipeline(
            [
                ParallelPipeline(
                    [LLMUserAggregator(fast_context)],
                    [_ErrorEmitter()],
                )
            ]
        )

        down, up = await run_test(
            pipeline,
            frames_to_send=[
                LLMMessagesAppendFrame(
                    messages=[{"role": "user", "content": "深问题"}], run_llm=True
                )
            ],
        )

        context_frames = [f for f in down if isinstance(f, LLMContextFrame)]
        self.assertEqual(
            1,
            len(context_frames),
            "快脑分支应恰好产出 1 条 LLMContextFrame，不受慢脑分支的错误拖累",
        )

        error_frames = [f for f in up if isinstance(f, ErrorFrame)]
        self.assertTrue(error_frames, "慢脑分支的 ErrorFrame 应上行可见")
        for frame in error_frames:
            self.assertFalse(
                frame.fatal, "PoC-2 S3 固化：非 fatal 的慢脑错误不得导致管线终止"
            )


class TestFastAnswerTap(unittest.IsolatedAsyncioTestCase):
    """B5 修法(旁听录音机):不经 TTS 排队,直接捕获快脑原始文本供慢脑注入提醒用。

    B5 根因(backlog.md)：快脑自己那句回答要真正写进 `fast_context`，要等
    `LLMFullResponseEndFrame` 被 TTS 那条按播放顺序释放的队列放行——播放耗时
    与回答长度成正比。慢脑"素材已齐"的注入若在这个窗口内触发，快脑看不到
    自己已经答过，会把问题从头重答一遍。`_FastAnswerTap` 插在 `fast_llm` 和
    `sentinel_filter`/TTS 之间，不经过那条队列，全程只做旁路记录 + 原样透传，
    不改变任何帧的流向或时机。
    """

    async def test_tap_captures_completed_answer_and_passes_frames_through(self):
        self.assertTrue(hasattr(dual_brain, "_FastAnswerTap"), "_FastAnswerTap 尚未定义")
        assert dual_brain is not None  # pyright narrowing

        tap = dual_brain._FastAnswerTap()
        pipeline = Pipeline([tap])

        frames_to_send = [
            LLMFullResponseStartFrame(),
            LLMTextFrame(text="今天"),
            LLMTextFrame(text="天气不错。"),
            LLMFullResponseEndFrame(),
        ]
        down, _ = await run_test(pipeline, frames_to_send=frames_to_send)

        self.assertEqual(
            "今天天气不错。", tap.last_answer, "应把同一轮的所有 LLMTextFrame 拼接成完整回答"
        )

        # 透传验证：旁听不得吞帧或加帧，条数必须与发送时完全一致。
        self.assertEqual(1, sum(1 for f in down if isinstance(f, LLMFullResponseStartFrame)))
        self.assertEqual(2, sum(1 for f in down if isinstance(f, LLMTextFrame)))
        self.assertEqual(1, sum(1 for f in down if isinstance(f, LLMFullResponseEndFrame)))

    async def test_tap_keeps_last_answer_until_new_turn_completes(self):
        """新一轮开始但尚未 End 时，last_answer 必须仍是上一轮的完整内容——
        不能被清空成空字符串，也不能被半截生成中的文本覆盖。这正是慢脑的
        注入消息读取这个值时唯一关心的时机点。"""
        self.assertTrue(hasattr(dual_brain, "_FastAnswerTap"), "_FastAnswerTap 尚未定义")
        assert dual_brain is not None  # pyright narrowing

        tap = dual_brain._FastAnswerTap()
        pipeline = Pipeline([tap])

        frames_to_send = [
            LLMFullResponseStartFrame(),
            LLMTextFrame(text="第一轮答案。"),
            LLMFullResponseEndFrame(),
            LLMFullResponseStartFrame(),
            LLMTextFrame(text="第二轮进行中"),
        ]
        await run_test(pipeline, frames_to_send=frames_to_send)

        self.assertEqual(
            "第一轮答案。",
            tap.last_answer,
            "新一轮尚未 End 时，last_answer 不应被清空或被半截内容覆盖",
        )

    async def test_build_fast_answer_tap_returns_independent_instances(self):
        """会话隔离(同型比照 build_sentinel_filter/build_slow_material_filter)。"""
        self.assertTrue(
            hasattr(dual_brain, "build_fast_answer_tap"), "build_fast_answer_tap 尚未定义"
        )
        assert dual_brain is not None  # pyright narrowing

        tap_a = dual_brain.build_fast_answer_tap()
        tap_b = dual_brain.build_fast_answer_tap()
        self.assertIsNot(tap_a, tap_b, "每次调用必须返回互不相同的新实例")

        pipeline = Pipeline([tap_a])
        await run_test(
            pipeline,
            frames_to_send=[
                LLMFullResponseStartFrame(),
                LLMTextFrame(text="脏状态。"),
                LLMFullResponseEndFrame(),
            ],
        )
        self.assertEqual("脏状态。", tap_a.last_answer)
        self.assertEqual("", tap_b.last_answer, "两个实例状态必须完全独立")


class TestSlowMaterialTransformerWithTap(unittest.IsolatedAsyncioTestCase):
    """B5 修法：完成帧文案在绑定 tap 且有内容时应带上"快脑刚才说过什么"的提醒。"""

    async def test_transformer_without_tap_matches_existing_done_template(self):
        """未绑定 tap（模块级单例现状）时，完成帧文案必须与之前完全一致——
        向后兼容，不破坏 T3.1 已锁定的断言。"""
        assert dual_brain is not None  # pyright narrowing

        frame = await dual_brain.slow_material_transformer(LLMFullResponseEndFrame())
        self.assertIsInstance(frame, LLMMessagesAppendFrame)
        assert isinstance(frame, LLMMessagesAppendFrame)
        self.assertEqual(
            prompts.INJECT_DONE_TEMPLATE,
            _message_field(frame.messages[0], "content"),
            "未绑定 tap 时不得改变现有完成帧文案",
        )

    async def test_transformer_with_tap_includes_reminder_of_fast_answer(self):
        self.assertTrue(
            hasattr(dual_brain, "build_slow_material_transformer"),
            "build_slow_material_transformer 尚未定义",
        )
        assert dual_brain is not None  # pyright narrowing

        tap = dual_brain._FastAnswerTap()
        tap.last_answer = "已经答过的内容示例。"
        transformer = dual_brain.build_slow_material_transformer(tap)

        frame = await transformer(LLMFullResponseEndFrame())
        self.assertIsInstance(frame, LLMMessagesAppendFrame)
        assert isinstance(frame, LLMMessagesAppendFrame)
        content = _message_field(frame.messages[0], "content")
        assert isinstance(content, str)  # pyright narrowing
        self.assertIn(
            "已经答过的内容示例。",
            content,
            "绑定 tap 且有内容时，完成帧文案应带上快脑刚才说过的内容",
        )
        self.assertIs(True, frame.run_llm, "完成帧仍必须 run_llm=True，不改变触发时机")

    async def test_transformer_with_empty_tap_matches_existing_done_template(self):
        """tap 绑定但本轮快脑还没答完（last_answer 为空）时，退回现状文案。"""
        assert dual_brain is not None  # pyright narrowing

        tap = dual_brain._FastAnswerTap()
        transformer = dual_brain.build_slow_material_transformer(tap)

        frame = await transformer(LLMFullResponseEndFrame())
        assert isinstance(frame, LLMMessagesAppendFrame)
        self.assertEqual(
            prompts.INJECT_DONE_TEMPLATE,
            _message_field(frame.messages[0], "content"),
            "tap 内容为空时应退回现状文案，不产出空提醒",
        )

    async def test_transformer_still_handles_text_frame_increment_unaffected(self):
        """回归防护：绑定 tap 不改变增量要点帧(TextFrame→INJECT_POINT_TEMPLATE)的既有行为。"""
        assert dual_brain is not None  # pyright narrowing

        tap = dual_brain._FastAnswerTap()
        tap.last_answer = "无关内容"
        transformer = dual_brain.build_slow_material_transformer(tap)

        point = "一个慢脑要点。"
        frame = await transformer(TextFrame(text=point))
        assert isinstance(frame, LLMMessagesAppendFrame)
        self.assertEqual(
            prompts.INJECT_POINT_TEMPLATE.format(point=point),
            _message_field(frame.messages[0], "content"),
        )
        self.assertIs(False, frame.run_llm)


class TestAssemblePipeline:
    """U3/U5(design §8.2)：`bot.assemble_pipeline()` 的结构性装配断言。

    用纯 pytest 风格函数(而非 unittest.TestCase)，直接吃 `bot_module`
    fixture（`conftest.py`，T5.1 从 `test_bot.py` 挪出以便本文件复用）——与
    `TestDualBrain` 的 `unittest.IsolatedAsyncioTestCase` 风格不同，但两者可
    在同一测试文件内共存，pytest 会分别正确收集。
    """

    class _FakeTransport:
        """最小 transport 桩：只暴露 `assemble_pipeline()` 实际用到的
        `input()`/`output()`，返回稳定的 FrameProcessor 实例（供 identity
        比较），不需要真实网络/IO（design §8.2 U3/U5 只测结构，不测传输）。
        """

        def __init__(self):
            self._input = FrameProcessor(name="fake-transport-input")
            self._output = FrameProcessor(name="fake-transport-output")

        def input(self):
            return self._input

        def output(self):
            return self._output

    class _FakeWorker:
        """最小 worker 桩(第 6 组)：只暴露 `make_pipeline_error_handler` 返回的
        handler 实际调用到的 `queue_frames()`,把送进来的帧原样收集供断言
        (design §6.5 面板契约——只验证 handler 是否 push 了正确的帧,不需要
        真实 `PipelineWorker`/RTVI 事件循环)。
        """

        def __init__(self):
            self.queued = []

        async def queue_frames(self, frames):
            self.queued.extend(frames)

    def test_pipeline_shape(self, bot_module):
        """U3：Consumer 必须在快脑分支内、且在 fast_pair.user() 之前；
        慢脑分支不得含任何输出件(transport.output()/TTS)。"""
        assert hasattr(bot_module, "assemble_pipeline"), "assemble_pipeline 尚未定义"

        transport = self._FakeTransport()
        assembled = bot_module.assemble_pipeline(bot_module.cfg, transport)

        top_level_processors = assembled.pipeline.processors
        parallel = next(p for p in top_level_processors if isinstance(p, ParallelPipeline))
        branches = parallel.processors
        assert len(branches) == 2, "ParallelPipeline 必须恰好两个分支(快脑/慢脑)"

        fast_branch = branches[0].processors
        slow_branch = branches[1].processors

        consumer_idx = next(
            i for i, p in enumerate(fast_branch) if isinstance(p, ConsumerProcessor)
        )
        fast_user_idx = fast_branch.index(assembled.fast_user_aggregator)
        assert consumer_idx < fast_user_idx, "Consumer 必须在快脑 user aggregator 之前"

        assert transport.output() in fast_branch, "transport.output() 必须在快脑分支内"
        assert transport.output() not in slow_branch, "慢脑分支不得含 transport.output()"
        assert assembled.tts in fast_branch, "TTS 必须在快脑分支内"
        assert assembled.tts not in slow_branch, "慢脑分支不得含 TTS"

    def test_rtvi_ignores_slow_branch(self, bot_module):
        """U5：ignored_sources 恰含慢脑三件(slow_llm/句聚合/Producer)且不含快脑
        LLM；并显式断言 `user_llm_enabled is False`(§5.1.1 第二条泄漏路径——
        注入模板经 `messages[-1]` 走 `user-llm-text` 上面板,eval 抓不到,只能
        靠这个参数 + 本条断言兜住)。"""
        assert hasattr(bot_module, "assemble_pipeline"), "assemble_pipeline 尚未定义"

        transport = self._FakeTransport()
        assembled = bot_module.assemble_pipeline(bot_module.cfg, transport)

        params = assembled.rtvi_observer_params
        ignored = list(params.ignored_sources)
        assert set(ignored) == {
            assembled.slow_llm,
            assembled.sentence_aggregator,
            assembled.producer,
        }, "ignored_sources 必须恰含慢脑三件"
        assert len(ignored) == 3, "ignored_sources 不得含重复/多余项"
        assert assembled.fast_llm not in ignored, "快脑 LLM 绝不能进 ignored_sources"
        assert params.user_llm_enabled is False, "user_llm_enabled 必须显式为 False"

    def test_greeting_turn_emits_no_material(self, bot_module):
        """T5.5(design §5.3/§8.1)：开场白轮零注入帧、零完成标记帧、零 slow-failed。

        真实网关是否对开场白 no-op 消息("(会话开始,用户尚未提问)")返回零字符是
        运行期 LLM 行为(由 `prompts.SLOW_BRAIN_PROMPT` 的"无深析价值则零输出"
        约束,§8.3 M6 / design §15 PoC-6 已实测验证,3.53s 返回空),不是单测能力
        范围。本用例验证的是：零输出发生时(等价帧序——`LLMFullResponseStartFrame`
        后无任何 `TextFrame` 直接收到 `LLMFullResponseEndFrame`)，开场白 basis
        (真实 seed 消息，非任意占位内容)不会让 `assemble_pipeline()` 真实装配出
        的 Producer/filter 意外产出材料——把第 3 组已证的通用机制
        (`test_failed_slow_turn_emits_no_completion_marker`)钉死在真实开场白流程
        写入的 `slow_context` 上，而不是任意占位内容。

        `slow-failed` 本身要到第 6 组(`on_pipeline_error` handler)才会被打印；
        这里断言它不出现，在第 6 组落地前后都应恒成立(零要点turn 不是 pipeline
        error)——先钉住这条契约，不等第 6 组补测。

        用 `asyncio.run()` 包一层同步入口，不用 `async def` + pytest-asyncio：
        venv 未装该插件(见本文件模块头 unittest.IsolatedAsyncioTestCase 的同型
        选择理由)，`TestAssemblePipeline` 用纯 pytest 风格是为了直接吃
        `bot_module` fixture，两者结合就只能这样绕。
        """
        assert hasattr(bot_module, "assemble_pipeline"), "assemble_pipeline 尚未定义"
        assert hasattr(bot_module, "seed_greeting_messages"), "seed_greeting_messages 尚未定义"

        transport = self._FakeTransport()
        assembled = bot_module.assemble_pipeline(bot_module.cfg, transport)
        bot_module.seed_greeting_messages(assembled.fast_context, assembled.slow_context)

        slow_messages = assembled.slow_context.get_messages()
        assert any(
            isinstance(m, dict)
            and m.get("role") == "user"
            and m.get("content") == "(会话开始,用户尚未提问)"
            for m in slow_messages
        ), "开场白必须把慢脑 no-op 消息写入 slow_context(design §5.3)"

        async def _drive():
            pipeline = Pipeline([assembled.producer, assembled.consumer])
            with _capture_dual_brain_logs() as captured:
                down, _ = await run_test(
                    pipeline,
                    frames_to_send=[
                        LLMFullResponseStartFrame(),
                        SleepFrame(),
                        LLMFullResponseEndFrame(),
                        SleepFrame(),
                    ],
                )
            return list(down), captured

        down, captured = asyncio.run(_drive())

        material_frames = [f for f in down if isinstance(f, LLMMessagesAppendFrame)]
        assert material_frames == [], "开场白轮(零 TextFrame)必须零注入帧、零完成标记帧"
        assert not any("slow-failed" in m for m in captured), "开场白轮不得出现 slow-failed"

    def test_non_slow_error_not_reported_as_slow_failed(self, bot_module):
        """R8 派生·防假绿(design §6.4 分支归属表,§8.1 R8 派生·防假绿)。

        非慢脑组件(STT 断线/TTS 401 等)触发的 `ErrorFrame` 必须打
        `pipeline-error`,绝不能被误报成 `slow-failed`——否则真实故障(比如用户
        完全听不到声音)会被 R8 的验收判据吞掉、误判成"慢脑降级正常工作"。
        """
        assert hasattr(bot_module, "make_pipeline_error_handler"), (
            "make_pipeline_error_handler 尚未定义"
        )

        assert dual_brain is not None  # pyright narrowing; hasattr check above already confirmed module

        slow_llm = FrameProcessor(name="fake-slow-llm")
        other_processor = FrameProcessor(name="fake-tts")
        # 独立新实例，不用模块级单例——与本文件其它用例的隔离纪律一致
        # （见 test_barge_in_drops_inflight_material 的同型说明）。
        material_filter = dual_brain._SlowMaterialFilter()
        handler = bot_module.make_pipeline_error_handler(slow_llm, material_filter)
        worker = self._FakeWorker()

        error_frame = ErrorFrame(error="boom", processor=other_processor, fatal=False)

        with _capture_dual_brain_logs() as captured:
            asyncio.run(handler(worker, error_frame))

        assert any("pipeline-error" in m for m in captured), "非慢脑组件失败应打 pipeline-error"
        assert not any("slow-failed" in m for m in captured), "非慢脑组件失败绝不能打 slow-failed"
        assert worker.queued == [], "非慢脑组件失败不应向面板 push 任何消息"

    def test_slow_failure_pushes_server_message(self, bot_module):
        """R8 派生·面板(design §6.4 `slow-failed` 行,§6.5 面板契约)。

        慢脑分支的 `ErrorFrame` 必须打 `slow-failed` 日志,且恰好向面板 push 1
        个 `RTVIServerMessageFrame(data={"type": "slow-brain-failed", ...})`——
        官方 `RTVIProcessor` 会把这个帧转发给 client 的 `EventsPanel`(§6.5,
        `client/` 零改)。
        """
        assert hasattr(bot_module, "make_pipeline_error_handler"), (
            "make_pipeline_error_handler 尚未定义"
        )

        assert dual_brain is not None  # pyright narrowing; hasattr check above already confirmed module

        slow_llm = FrameProcessor(name="fake-slow-llm")
        material_filter = dual_brain._SlowMaterialFilter()
        handler = bot_module.make_pipeline_error_handler(slow_llm, material_filter)
        worker = self._FakeWorker()

        error_frame = ErrorFrame(error="boom", processor=slow_llm, fatal=False)

        async def _drive():
            # 先真实派发一轮(LLMFullResponseStartFrame 使 material_filter.turn
            # 从 0 变为 1),模拟"这次失败的正是刚派发的这一轮"——验证
            # slow-failed 行与 material_filter 自己的 dispatch/inject/no-material
            # 行共享同一个 turn 值(组末评审 MEDIUM 修复:此前 handler 自建独立
            # 计数器,与 dual_brain 的会话级 _turn 脱节)。
            await material_filter(LLMFullResponseStartFrame())
            with _capture_dual_brain_logs() as captured:
                await handler(worker, error_frame)
            return captured

        captured = asyncio.run(_drive())

        assert any("slow-failed turn=1" in m for m in captured), (
            "慢脑组件失败应打 slow-failed,且 turn 必须与 material_filter 自己的计数器一致(此处为 1)"
        )
        assert len(worker.queued) == 1, "慢脑失败应恰好向面板 push 1 条消息"
        pushed = worker.queued[0]
        assert isinstance(pushed, RTVIServerMessageFrame), "push 的帧类型必须是 RTVIServerMessageFrame"
        assert pushed.data["type"] == "slow-brain-failed", "面板消息 data.type 必须是 slow-brain-failed"
        assert pushed.data["turn"] == 1, "面板消息里的 turn 必须与日志行、material_filter.turn 三者一致"

    # -- task-dispatch (C4 派活, T-6) L2 结构断言 --------------------------
    #
    # C-09 步骤1(契约 §1 / design.md §E L2):在本既有类内扩写,沿用
    # `test_pipeline_shape`/`test_rtvi_ignores_slow_branch` 同款
    # "assemble_pipeline() 一次、断言其返回结构" 手法,不新起断言文件、不新增
    # 模块缓存强制重载手法(D-003 守法③;`bot_module` fixture 的重载定义点
    # 唯一落在 `conftest.py`,本类自身不新增该手法,详见 task 卡 T-6 Interfaces 节)。

    @staticmethod
    def _fast_and_slow_branches(assembled):
        """解析 `ParallelPipeline` 的两个分支(快脑/慢脑),与
        `test_pipeline_shape` 内联的同一手法抽成 helper,供本轮新增的多个
        测试方法复用,不重复解析逻辑。"""
        parallel = next(
            p for p in assembled.pipeline.processors if isinstance(p, ParallelPipeline)
        )
        branches = parallel.processors
        return branches[0].processors, branches[1].processors

    def test_dispatch_injector_at_fast_branch_head(self, bot_module):
        """C-09 步骤1 / design.md §E L2:新增的 `_DispatchMaterialInjector`
        位于快脑分支头部,且对外输出分支数量与改动前一致(仍仅快脑分支含
        `transport.output()`/TTS)——与本类既有 `test_pipeline_shape` 断言
        "consumer 必须在快脑分支内、慢脑分支不得含输出件"是同一形状的直接
        延伸(task 卡 T-6 Interfaces 节)。"""
        assert hasattr(bot_module, "assemble_pipeline"), "assemble_pipeline 尚未定义"

        transport = self._FakeTransport()
        assembled = bot_module.assemble_pipeline(bot_module.cfg, transport)

        fast_branch, slow_branch = self._fast_and_slow_branches(assembled)
        # `fast_branch[0]` 是分支内部的 `PipelineSource` 标记(框架内部实现细
        # 节,非"真实"处理器),同款既有断言手法(`test_pipeline_shape` 的
        # `consumer_idx`)用相对次序而非硬编码下标 0 —— 这里同样断言注入器
        # 是分支内最早出现的真实处理器,严格早于既有 consumer。
        consumer_idx = next(
            i for i, p in enumerate(fast_branch) if isinstance(p, ConsumerProcessor)
        )
        injector_idx = fast_branch.index(assembled.injector)
        assert injector_idx < consumer_idx, "注入器必须在快脑分支头部,位于既有 consumer 之前"
        assert assembled.injector not in slow_branch, "注入器不得出现在慢脑分支"
        assert transport.output() in fast_branch, "transport.output() 必须仍在快脑分支内"
        assert transport.output() not in slow_branch, "慢脑分支不得含 transport.output()"
        assert assembled.tts in fast_branch, "TTS 必须仍在快脑分支内"
        assert assembled.tts not in slow_branch, "慢脑分支不得含 TTS"

    def test_dispatch_tools_registered_on_fast_context(self, bot_module):
        """`fast_context.tools` 恰含两个派活工具(契约 §0.2 T1/T2,design.md
        §E L2:"fast_context.tools 恰含两个工具")。"""
        assert hasattr(bot_module, "assemble_pipeline"), "assemble_pipeline 尚未定义"

        transport = self._FakeTransport()
        assembled = bot_module.assemble_pipeline(bot_module.cfg, transport)

        tools_schema = assembled.fast_context.tools
        registered = {wrapper.function for wrapper in tools_schema.direct_functions}
        assert registered == {task_dispatch.dispatch_task, task_dispatch.get_task_status}, (
            "fast_context.tools 必须恰含 dispatch_task 与 get_task_status 两个工具"
        )
        assert len(tools_schema.direct_functions) == 2, "fast_context.tools 不得含重复/多余项"

    def test_dispatch_app_resources_and_new_fields(self, bot_module):
        """`app_resources` 非空;`AssembledPipeline` 新增四字段可取(契约
        §0.1/数据模型 §2,design.md §E L2)。"""
        assert hasattr(bot_module, "assemble_pipeline"), "assemble_pipeline 尚未定义"

        transport = self._FakeTransport()
        assembled = bot_module.assemble_pipeline(bot_module.cfg, transport)

        app_resources = assembled.worker.app_resources
        assert app_resources is not None, "app_resources 必须非空"
        assert app_resources.registry is assembled.dispatch_registry
        assert isinstance(assembled.injector, task_dispatch._DispatchMaterialInjector)
        assert isinstance(assembled.dispatch_worker, task_dispatch.TaskDispatchWorker)
        assert isinstance(assembled.exec_worker, task_dispatch.OpenClawExecWorker)
        assert isinstance(assembled.dispatch_registry, task_dispatch.DispatchRegistry)


if __name__ == "__main__":
    unittest.main()
