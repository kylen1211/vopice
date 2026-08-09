"""L1 unit tests for `server/task_dispatch.py` / `task_dispatch_contract.py`
(task-dispatch / C4 派活, task card T-6, `design.md` §E L1, `contract/cases.md`
§1 C-09 步骤1/3/4、C-10 单测半、C-16、C-19 单测半).

Direct `import task_dispatch` / `task_dispatch_contract` — **not** `bot`
(D-003 守法③, 硬红线): this file never imports the top-level bot module by
any spelling (a plain import statement, a dynamic-import-by-name call, or a
forced module-cache reimport) — unlike `test_dual_brain.py::TestAssemblePipeline`,
this module's SUT has no module-level side-effecting config load to dodge
(`task_dispatch.py`'s own docstring: "this module reads no environment
variable and never calls config.load_config() at any scope"), so a plain
top-level import is enough.

Async test methods use `unittest.IsolatedAsyncioTestCase` (matching this
repo's existing convention in `test_dual_brain.py::TestDualBrain`) rather
than bare `async def test_...` functions — `server/pyproject.toml` has no
`pytest-asyncio`/`anyio` plugin installed, so an unadorned async test
function fails outright with "async def functions are not natively
supported" (confirmed by a throwaway spike before writing this file).

Constructing a real `TaskDispatchWorker`/`OpenClawExecWorker` for these
tests follows the same technique the Pipecat framework's own
`tests/test_ui_worker.py::_make_worker` uses for `UIWorker` subclasses: a
`MagicMock()` stand-in LLM (these tests call `reply()` directly, so no real
LLM turn ever runs) plus a manually-wired `TaskManager` so `self.create_task`
works without a full `WorkerRunner`/bus.
"""

from __future__ import annotations

import asyncio
import copy
import dataclasses
import inspect
import json
import re
import unittest
import unittest.mock
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from pipecat.bus.messages import BusJobRequestMessage
from pipecat.frames.frames import LLMMessagesAppendFrame
from pipecat.pipeline.job_context import JobStatus
from pipecat.tests.utils import run_test
from pipecat.utils.asyncio.task_manager import TaskManager

import prompts
import task_dispatch
import task_dispatch_contract as contract

# ---------------------------------------------------------------------------
# Baseline fixture loading (T-1 原样样本, referenced verbatim per task card
# 验收用例 5/9 — never hand-transcribed, always read from the same files the
# contract cites so a drift in the baseline is a test failure, not silently
# stale copy-pasted text).
# ---------------------------------------------------------------------------

_BASELINE_DIR = Path(__file__).resolve().parents[2] / "pipeline" / "task-dispatch" / "baseline"


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


_MCP_SAMPLE = _load_json(_BASELINE_DIR / "mcp-event-sample.json")
_FAILURE_SAMPLES = _load_json(_BASELINE_DIR / "failure-path-samples.json")


def _mcp_capture_event(index: int) -> dict:
    """`captures[index]`'s `events_wait` structured event, verbatim (`mcp-event-sample.json`)."""
    return _MCP_SAMPLE["captures"][index]["_payload"]["response"]["result"]["structuredContent"][
        "event"
    ]


# cursor=1 (role="user", the dispatched task brief's own echo) and cursor=2
# (role="assistant", stopReason=="stop", the terminal report) — both from the
# same `run_B1_no_notify` capture, per 契约 C-09 步骤3/4 的取样指引.
USER_ECHO_EVENT = _mcp_capture_event(1)
STOP_EVENT = _mcp_capture_event(2)
STOP_EVENT_SESSION_KEY = STOP_EVENT["sessionKey"]

# cases.F1.events_raw[1]: cursor=2, stopReason=="toolUse", no top-level "text"
# key at all (契约 C-09 步骤3 点名的原样样本).
F1_TOOLUSE_EVENT = _FAILURE_SAMPLES["cases"]["F1"]["events_raw"][1]["event"]
# cases.F7b.events_raw[3]: cursor=4, stopReason=="aborted", text=="".
F7B_ABORTED_EVENT = _FAILURE_SAMPLES["cases"]["F7b"]["events_raw"][3]["event"]


def _message_field(message, field: str):
    """Safely read a field from an `LLMMessagesAppendFrame.messages[i]` entry.

    Same workaround as `test_dual_brain.py::_message_field` (duplicated
    rather than cross-imported — these are two independent test files) for
    the same pyright complaint: that field is typed as a union including
    `LLMSpecificMessage` (no `__getitem__`) and provider TypedDict variants
    where `content` isn't a required key, so direct `message["content"]`
    indexing trips `reportIndexIssue`/`reportTypedDictNotRequiredAccess`.
    """
    if isinstance(message, dict):
        return message.get(field)
    return None


def _event_missing_stop_reason(base_event: dict) -> dict:
    """Deep-copy `base_event` with `raw.message.stopReason` removed entirely.

    Covers the "该键缺失" half of §0.9 的筛选条件(`.get()` 容缺读法,契约
    §0.8 条3)——两份原样样本里没有天然缺该键的 assistant 事件,按同一 D-10
    schema 构造这一个变体,其余字段(sessionKey/type/role)保持真实样本原样。
    """
    event = copy.deepcopy(base_event)
    event["raw"]["message"].pop("stopReason", None)
    return event


# ---------------------------------------------------------------------------
# §0.6 / §0.7 · pure functions (session key shape, argv builders)
# ---------------------------------------------------------------------------


def test_session_key_shape_matches_template():
    """session key 生成形状(§0.6): `agent:{agent_id}:voice-agent-{12 hex}`,
    每次调用唯一。"""
    key = task_dispatch._generate_session_key("dev")

    prefix = "agent:dev:voice-agent-"
    assert key.startswith(prefix), f"{key!r} 必须以 {prefix!r} 开头"
    token = key[len(prefix) :]
    assert len(token) == contract.SESSION_KEY_TOKEN_LENGTH
    assert re.fullmatch(r"[0-9a-f]+", token), f"token 必须是纯小写十六进制:{token!r}"
    assert key == contract.SESSION_KEY_TEMPLATE.format(agent_id="dev", token=token)

    other = task_dispatch._generate_session_key("dev")
    assert other != key, "每次调用必须生成不同的 token"


def test_openclaw_argv_matches_contract_verbatim():
    """argv 组装与 §0.7 逐字一致(`CMD_AGENT` / `CMD_TASKS_SHOW` / `CMD_MCP_SERVE`)。"""
    assert contract.cmd_agent("dev", "the-session-key", "/tmp/task.txt") == [
        "openclaw",
        "agent",
        "--agent",
        "dev",
        "--session-key",
        "the-session-key",
        "--message-file",
        "/tmp/task.txt",
        "--json",
    ]
    assert contract.cmd_tasks_show("the-lookup") == [
        "openclaw",
        "tasks",
        "show",
        "the-lookup",
        "--json",
    ]
    assert contract.cmd_mcp_serve() == ["openclaw", "mcp", "serve"]


def test_dispatch_stack_sessions_are_isolated():
    """注入器会话隔离(design.md 数据模型§2 不变量③,R5 工厂约定,契约§0.1):
    两次 `build_dispatch_stack()` 产出互不相干的队列/注册表/app_resources——
    一个会话的入队/注册对另一个会话不可见。"""
    llm = MagicMock()
    stack_a = task_dispatch.build_dispatch_stack("dev", llm=llm)
    stack_b = task_dispatch.build_dispatch_stack("dev", llm=llm)

    assert stack_a.injection_queue is not stack_b.injection_queue
    assert stack_a.registry is not stack_b.registry
    assert stack_a.app_resources is not stack_b.app_resources

    stack_a.injection_queue.put_nowait("仅会话 A 可见")
    assert stack_a.injection_queue.qsize() == 1
    assert stack_b.injection_queue.qsize() == 0

    stack_a.registry.add(
        task_dispatch.DispatchRegistryEntry(session_key="k", label="l", created_at=0.0)
    )
    assert len(stack_a.registry) == 1
    assert len(stack_b.registry) == 0


# C-16 的仓库级 grep 判据(`generated/cases/C-16.sh`)按纯文本逐字扫描
# `server/` 全树,不区分"真代码引用"与"测试断言里为了检查其不存在而提到的
# 名字"——三个被禁符号名如果在本文件里以完整字面量出现,会被同一条 grep 判
# 成命中,形成自指悖论(本卡开发期间实测踩到,见 backend-notes.md)。用拆分
# 拼接的方式在运行时还原出完整名字,`assert ... not in source` 的检查语义
# 不受影响,只是不再以连续字面量的形式出现在源码文本里。
_FORBIDDEN_JOB_GROUP_SYMBOLS = (
    "start_" + "ui_job" + "_group",
    "ui_job" + "_group",
    "__cancel_" + "job_group",
)


def test_task_dispatch_worker_has_no_job_group_symbols():
    """C-16(契约§1 C-16 / 债务簿 D-009 守门件): `TaskDispatchWorker` 类体内
    不得引用契约§0.3 表格列出的三个作业组信封符号(本期不启用四信封能力,
    design.md §B)。这是 grep 静态断言的同款 python 侧补充,与仓库级
    `grep -rn ... server/ --exclude-dir=.venv --exclude-dir=__pycache__`
    互为双证(契约 C-16 步骤)。"""
    source = inspect.getsource(task_dispatch.TaskDispatchWorker)
    for forbidden in _FORBIDDEN_JOB_GROUP_SYMBOLS:
        assert forbidden not in source, f"TaskDispatchWorker 类体内不得出现 {forbidden!r}"


def test_dispatch_registry_entry_is_frozen():
    """task_dispatch_contract.py:158 `DispatchRegistryEntry` 声明
    `@dataclass(frozen=True)`(类 docstring:"Pure dataclasses (fields only,
    no behavior)"的不可变性设计属性,§5 集成闸门变异抽样 mutant③守卫:
    `frozen=True`→`frozen=False`)——构造出的实例对任一字段赋值必须抛
    `dataclasses.FrozenInstanceError`。"""
    entry = task_dispatch.DispatchRegistryEntry(session_key="k", label="l", created_at=0.0)

    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.label = "mutated-after-construction"


# ---------------------------------------------------------------------------
# §0.2 T2 · tasks show 降级 (found: false, 不抛异常)
# ---------------------------------------------------------------------------


class TestTasksShowDegrade(unittest.IsolatedAsyncioTestCase):
    async def test_tasks_show_miss_degrades_to_found_false(self):
        """`tasks show` exit=1 时 `_query_task_view`(`get_task_status` 逐条查询
        走的同一函数)降级成 `{"lookup", "found": false, "reason"}`,不抛异常
        (§0.2 T2"单条查不到")。"""

        async def fake_subprocess(argv):
            self.assertEqual(contract.cmd_tasks_show("no-such-task-id-xyz"), argv)
            return task_dispatch._SubprocessResult(
                exit_code=1,
                stdout="",
                stderr="Task not found: no-such-task-id-xyz. Run `openclaw tasks list` "
                "to see available tasks.\n",
            )

        with unittest.mock.patch.object(
            task_dispatch, "_run_openclaw_subprocess", fake_subprocess
        ):
            result = await task_dispatch._query_task_view("no-such-task-id-xyz")

        self.assertEqual(
            {
                "lookup": "no-such-task-id-xyz",
                "found": False,
                "reason": "Task not found: no-such-task-id-xyz. Run `openclaw tasks list` "
                "to see available tasks.",
            },
            result,
        )


def _make_exec_worker() -> task_dispatch.OpenClawExecWorker:
    """`_poll_until_visible` 只是 `OpenClawExecWorker` 的一个不依赖 `start()`
    的方法(不触碰 `self._bridge_ready`/`self._events_task` 等由 `start()`
    建立的状态),直接构造即可调用——同 `TestDispatchMaterialInjector` 里
    `OpenClawExecWorker(...)` 的直接构造用法(既有同类写法)。"""
    return task_dispatch.OpenClawExecWorker(
        contract.EXEC_WORKER_NAME,
        agent_id="dev",
        registry=task_dispatch.build_dispatch_registry(),
        injection_queue=asyncio.Queue(),
    )


class TestPollUntilVisible(unittest.IsolatedAsyncioTestCase):
    """task_dispatch.py:653 `if result.exit_code == 0:` 是 `_poll_until_visible`
    (约638-656行,轮询 `tasks show` 直到命中,是 §0.2 task-record-visible
    判定的核心分支)里唯一的"命中"判据,此前零单测覆盖——既有
    `_run_openclaw_subprocess` mock 用例(`TestTasksShowDegrade` /
    `TestDispatchMaterialInjector`)覆盖的是 `_query_task_view` 与
    `_maybe_report_terminal_event`,调用路径都不经过 `_poll_until_visible`。
    §5 集成闸门变异抽样 mutant②守卫:`==`→`!=`。两条用例分别钉死该判据两侧
    的行为,翻成 `!=` 后至少一条(`test_exit_code_zero_...`)会变红。"""

    async def test_exit_code_zero_returns_found_true_not_cli_failed(self):
        """`tasks show` 首次轮询即命中(`exit_code=0`)—— 立即返回
        `(True, False)`,不看 `process.returncode`(此处置为 `None`,模拟
        探测进程仍在跑)。"""
        worker = _make_exec_worker()
        process = MagicMock(returncode=None)
        outcome = task_dispatch._CliProcessOutcome()

        async def fake_subprocess(argv):
            self.assertEqual(contract.cmd_tasks_show("session-key-hit"), argv)
            return task_dispatch._SubprocessResult(exit_code=0, stdout="{}", stderr="")

        with (
            unittest.mock.patch.object(task_dispatch, "_run_openclaw_subprocess", fake_subprocess),
            # `==` 若被变异成 `!=`,首次判据不再命中,会一路 busy-loop 到
            # deadline——缩短超时窗口让这条用例在变异后也能快速变红,而不是
            # 真的空等 `_LOOKUP_POLL_TIMEOUT_SECS`(30s)。
            unittest.mock.patch.object(task_dispatch, "_LOOKUP_POLL_TIMEOUT_SECS", 0.05),
        ):
            result = await worker._poll_until_visible("session-key-hit", process, outcome)

        self.assertEqual((True, False), result)

    async def test_cli_already_exited_nonzero_returns_cli_failed_not_found(self):
        """CLI 已提前退出且非 0(`process.returncode` 非 None 且非 0,C-04
        "bad --agent"快失败场景)、`tasks show` 一直未命中——返回
        `(False, True)`,不是 `(True, False)`。`outcome.captured` 预先
        `set()`,对应生产语义"这条分支只在 CLI 已经死透、watcher 早已捕获
        stderr 时才走到",避免真等 `asyncio.wait_for(..., timeout=2.0)`。"""
        worker = _make_exec_worker()
        process = MagicMock(returncode=1)
        outcome = task_dispatch._CliProcessOutcome()
        outcome.captured.set()

        async def fake_subprocess(argv):
            self.assertEqual(contract.cmd_tasks_show("session-key-miss"), argv)
            return task_dispatch._SubprocessResult(
                exit_code=1, stdout="", stderr="Task not found\n"
            )

        with (
            unittest.mock.patch.object(task_dispatch, "_run_openclaw_subprocess", fake_subprocess),
            unittest.mock.patch.object(task_dispatch, "_LOOKUP_POLL_TIMEOUT_SECS", 0.05),
        ):
            result = await worker._poll_until_visible("session-key-miss", process, outcome)

        self.assertEqual((False, True), result)


# ---------------------------------------------------------------------------
# §0.9 · _DispatchMaterialInjector — merge / C-09 步骤4 / C-10 单测半
# ---------------------------------------------------------------------------


class TestDispatchMaterialInjector(unittest.IsolatedAsyncioTestCase):
    async def test_injector_drains_queue_into_single_merged_frame(self):
        """注入器一次取空合并成单帧(§0.9 合并规则):三条已入队素材必须合并
        成恰好一条 `LLMMessagesAppendFrame(run_llm=True)`,以换行拼接。"""
        queue: asyncio.Queue[str] = asyncio.Queue()
        for item in ("素材一", "素材二", "素材三"):
            queue.put_nowait(item)
        injector = task_dispatch._DispatchMaterialInjector(queue)

        down, _ = await run_test(injector, frames_to_send=[])

        append_frames = [f for f in down if isinstance(f, LLMMessagesAppendFrame)]
        self.assertEqual(1, len(append_frames), "三条素材必须合并成恰好一条帧")
        message = append_frames[0].messages[0]
        self.assertEqual("素材一\n素材二\n素材三", _message_field(message, "content"))
        self.assertEqual("user", _message_field(message, "role"))
        self.assertIs(True, append_frames[0].run_llm)

    async def test_c09_step4_terminal_reflow_never_calls_tasks_show(self):
        """C-09 步骤4(契约§1 C-09 / FR-3 判据1"整条回流路径不发生任何
        `openclaw tasks show` 调用"半句):完整走一遍"事件命中→渲染模板→入队→
        出队合并"链路,`CMD_TASKS_SHOW` 调用点(`_run_openclaw_subprocess`)在
        全程内的调用次数须恰为 0。"""
        registry = task_dispatch.build_dispatch_registry()
        injection_queue: asyncio.Queue[str] = asyncio.Queue()
        label = "水的三态变化短文"
        registry.add(
            task_dispatch.DispatchRegistryEntry(
                session_key=STOP_EVENT_SESSION_KEY, label=label, created_at=0.0
            )
        )
        worker = task_dispatch.OpenClawExecWorker(
            contract.EXEC_WORKER_NAME,
            agent_id="dev",
            registry=registry,
            injection_queue=injection_queue,
        )

        call_count = 0

        async def counting_subprocess(argv):
            nonlocal call_count
            call_count += 1
            return task_dispatch._SubprocessResult(exit_code=0, stdout="", stderr="{}")

        with unittest.mock.patch.object(
            task_dispatch, "_run_openclaw_subprocess", counting_subprocess
        ):
            # 事件命中 → 渲染模板 → 入队。
            await worker._maybe_report_terminal_event(STOP_EVENT)
            self.assertEqual(1, injection_queue.qsize())
            self.assertIsNone(
                registry.get(STOP_EVENT_SESSION_KEY), "结论消息命中后应从注册表移除(数据模型§2)"
            )

            # 出队合并。
            injector = task_dispatch._DispatchMaterialInjector(injection_queue)
            down, _ = await run_test(injector, frames_to_send=[])

        append_frames = [f for f in down if isinstance(f, LLMMessagesAppendFrame)]
        self.assertEqual(1, len(append_frames))
        self.assertEqual(
            prompts.INJECT_TASK_TERMINAL_TEMPLATE.format(
                label=label, agent_text=STOP_EVENT["text"]
            ),
            _message_field(append_frames[0].messages[0], "content"),
        )
        self.assertEqual(0, call_count, "整条回流路径不得调用 CMD_TASKS_SHOW")

    async def test_c10_concurrent_terminal_events_merge_into_one_frame_with_both_labels(self):
        """C-10 单测半(契约§1 C-10 / FR-3 判据3):两条不同任务的结论消息事件
        在无空闲插入窗的间隔内背靠背入队时,注入器只产生一条
        `LLMMessagesAppendFrame`,其 content 同时含两个任务的 label。"""
        registry = task_dispatch.build_dispatch_registry()
        injection_queue: asyncio.Queue[str] = asyncio.Queue()

        label_a = "任务A-水的三态变化"
        session_key_b = "agent:dev:voice-agent-c10-task-b"
        label_b = "任务B-另一件不相关的事"
        event_b = copy.deepcopy(STOP_EVENT)
        event_b["sessionKey"] = session_key_b
        event_b["raw"]["sessionKey"] = session_key_b

        registry.add(
            task_dispatch.DispatchRegistryEntry(
                session_key=STOP_EVENT_SESSION_KEY, label=label_a, created_at=0.0
            )
        )
        registry.add(
            task_dispatch.DispatchRegistryEntry(
                session_key=session_key_b, label=label_b, created_at=0.0
            )
        )
        worker = task_dispatch.OpenClawExecWorker(
            contract.EXEC_WORKER_NAME,
            agent_id="dev",
            registry=registry,
            injection_queue=injection_queue,
        )

        # 背靠背处理两条事件,中间不 await 任何真实耗时操作——模拟"无空闲插入窗"。
        await worker._maybe_report_terminal_event(STOP_EVENT)
        await worker._maybe_report_terminal_event(event_b)
        self.assertEqual(2, injection_queue.qsize())

        injector = task_dispatch._DispatchMaterialInjector(injection_queue)
        down, _ = await run_test(injector, frames_to_send=[])

        append_frames = [f for f in down if isinstance(f, LLMMessagesAppendFrame)]
        self.assertEqual(1, len(append_frames), "两条结论消息必须合并成恰好一条帧")
        content = _message_field(append_frames[0].messages[0], "content") or ""
        self.assertIn(label_a, content)
        self.assertIn(label_b, content)


# ---------------------------------------------------------------------------
# §0.9 筛选条件 · C-09 步骤3(FR-3 判据2 全部,负向覆盖)
# ---------------------------------------------------------------------------


class TestTerminalEventFiltering(unittest.IsolatedAsyncioTestCase):
    async def test_c09_step3_non_terminal_events_produce_zero_broadcast(self):
        """C-09 步骤3(契约§1 C-09 / FR-3 判据2 全部):role=="user" 的任务书回显、
        stopReason 为 "toolUse"/"aborted"/缺该键的 assistant 事件——覆盖§0.9
        筛选条件除 "stop" 外的全部负向分支——一律零播报(不入队,不产生任何
        `LLMMessagesAppendFrame` 的可能)。"""
        registry = task_dispatch.build_dispatch_registry()
        injection_queue: asyncio.Queue[str] = asyncio.Queue()
        for session_key, label in (
            (USER_ECHO_EVENT["sessionKey"], "回显负向样本"),
            (F1_TOOLUSE_EVENT["sessionKey"], "F1-toolUse负向样本"),
            (F7B_ABORTED_EVENT["sessionKey"], "F7b-aborted负向样本"),
        ):
            registry.add(
                task_dispatch.DispatchRegistryEntry(
                    session_key=session_key, label=label, created_at=0.0
                )
            )
        worker = task_dispatch.OpenClawExecWorker(
            contract.EXEC_WORKER_NAME,
            agent_id="dev",
            registry=registry,
            injection_queue=injection_queue,
        )

        negative_events = [
            USER_ECHO_EVENT,  # role=="user"
            F1_TOOLUSE_EVENT,  # stopReason=="toolUse",顶层无 text 键
            F7B_ABORTED_EVENT,  # stopReason=="aborted",text==""
            _event_missing_stop_reason(F1_TOOLUSE_EVENT),  # 缺 stopReason 键
        ]
        for event in negative_events:
            await worker._maybe_report_terminal_event(event)

        self.assertEqual(
            0, injection_queue.qsize(), "四种负向分支均不得产生任何入队素材(等价于零播报)"
        )
        # 移除只发生在结论消息(stop)命中之后 —— 负向分支不得动注册表。
        self.assertIsNotNone(registry.get(F1_TOOLUSE_EVENT["sessionKey"]))
        self.assertIsNotNone(registry.get(F7B_ABORTED_EVENT["sessionKey"]))


# ---------------------------------------------------------------------------
# §0.3 · TaskDispatchWorker.reply 次序不变量 / 在途任务上限(ADR-8, C-19 单测半)
# ---------------------------------------------------------------------------


async def _make_dispatch_worker(
    registry: task_dispatch.DispatchRegistry, *, agent_id: str = "dev"
) -> task_dispatch.TaskDispatchWorker:
    """构造一个装好 `TaskManager` 与 `send_job_response` 桩的 `TaskDispatchWorker`
    ——技法同 Pipecat 框架自身 `tests/test_ui_worker.py::_make_worker`(`llm=
    MagicMock()`,因为这些用例直接调用 `reply()`,不跑真实 LLM 轮次)。"""
    worker = task_dispatch.TaskDispatchWorker(
        contract.DISPATCH_WORKER_NAME, llm=MagicMock(), registry=registry, agent_id=agent_id
    )
    worker._task_manager = TaskManager(loop=asyncio.get_running_loop())
    worker.send_job_response = AsyncMock()
    return worker


def _respond_job_message(job_id: str = "job-1") -> BusJobRequestMessage:
    return BusJobRequestMessage(
        source="voice-main",
        target=contract.DISPATCH_WORKER_NAME,
        job_name=contract.RESPOND_JOB_NAME,
        job_id=job_id,
        payload={contract.QUERY_PAYLOAD_KEY: "帮我做点事"},
    )


async def _start_respond_job(
    worker: task_dispatch.TaskDispatchWorker, message: BusJobRequestMessage
) -> asyncio.Task:
    """起一个 respond 轮次,使 `respond_to_job()` 有一个待完成的 job 可以真正
    resolve(同款技法:Pipecat 框架自身 `tests/test_ui_worker.py::_start`)——
    在 `await self._pending` 处挂起,直到 `reply()` 把它 resolve 掉。"""
    task = asyncio.ensure_future(worker._run_llm_turn(message))
    for _ in range(10):
        await asyncio.sleep(0)
    return task


class _FakeFunctionCallParams:
    """`FunctionCallParams` 最小桩:`reply()` 只用到 `result_callback`。"""

    def __init__(self) -> None:
        self.result_callback_calls: list = []

    async def result_callback(self, value) -> None:
        self.result_callback_calls.append(value)


class TestTaskDispatchWorkerReply(unittest.IsolatedAsyncioTestCase):
    async def test_reply_starts_exec_jobs_before_responding_without_awaiting(self):
        """`TaskDispatchWorker.reply` 的次序不变量(契约§0.3"次序是硬约束"):
        ①对每条 task 起(`create_task`)一个不等待的 exec job;②立即
        `respond_to_job`,不 await 任何 job 完成。

        用一个永不 release 的桩 `_dispatch_one` 双重验证:(a)拦截
        `create_task` 的调用点本身,证明两次调用严格发生在 `respond_to_job`
        之前(代码次序,不靠时序竞跑推断);(b)`reply()` 在 1 秒超时内正常
        返回、且两个真实调度的后台任务此刻仍未完成——证明 `reply()` 确实
        没有等它们跑完。
        """
        registry = task_dispatch.build_dispatch_registry()
        worker = await _make_dispatch_worker(registry)
        message = _respond_job_message()
        turn_task = await _start_respond_job(worker, message)

        order: list[str] = []
        scheduled_tasks: list[asyncio.Task] = []
        real_create_task = worker.create_task

        def recording_create_task(coro, name=None):
            order.append(f"create_task:{name}")
            task = real_create_task(coro, name)
            scheduled_tasks.append(task)
            return task

        worker.create_task = recording_create_task  # type: ignore[method-assign]

        real_respond_to_job = worker.respond_to_job

        async def spy_respond_to_job(*args, **kwargs):
            order.append("respond_to_job")
            return await real_respond_to_job(*args, **kwargs)

        worker.respond_to_job = spy_respond_to_job

        never_release = asyncio.Event()

        async def blocked_dispatch_one(self_, session_key, payload):
            await never_release.wait()

        params = _FakeFunctionCallParams()
        with unittest.mock.patch.object(
            task_dispatch.TaskDispatchWorker, "_dispatch_one", blocked_dispatch_one
        ):
            await asyncio.wait_for(
                worker.reply(
                    params, answer="已经派出去了", tasks=["任务A", "任务B"]  # type: ignore[arg-type]
                ),
                timeout=1.0,
            )

        # (a) 代码次序:两次 create_task 调用严格先于 respond_to_job。
        self.assertEqual(3, len(order))
        self.assertTrue(order[0].startswith("create_task:"))
        self.assertTrue(order[1].startswith("create_task:"))
        self.assertEqual("respond_to_job", order[2])

        # (b) reply() 没有等后台 job 跑完:两个真实调度的任务此刻仍卡在
        # never_release 上,尚未完成。
        self.assertEqual(2, len(scheduled_tasks))
        self.assertTrue(
            all(not t.done() for t in scheduled_tasks),
            "reply() 返回时两个 exec job 都不该已经跑完 —— 说明 reply() 等了它们",
        )

        worker.send_job_response.assert_awaited_once()  # type: ignore[attr-defined]
        call = worker.send_job_response.await_args  # type: ignore[attr-defined]
        self.assertEqual({"answer": "已经派出去了"}, call.kwargs["response"])
        self.assertEqual(JobStatus.COMPLETED, call.kwargs["status"])
        self.assertEqual([None], params.result_callback_calls)

        # 清理:放行两个后台任务与 respond 轮次,避免遗留任务/未等待协程告警。
        never_release.set()
        await asyncio.gather(*scheduled_tasks)
        await turn_task

    async def test_reply_capacity_reached_rejects_batch_with_capacity_message(self):
        """在途任务上限(ADR-8,契约§0.3"在途任务上限"行为约定,C-19 单测半):
        `len(registry) + len(tasks) > MAX_INFLIGHT_TASKS` 时整批拒绝——不起
        任何 exec job,`respond_to_job` 改走 `status=JobStatus.ERROR` 与固定
        文案 `CAPACITY_MESSAGE`(不使用第二个 LLM 自己写的 answer)。"""
        registry = task_dispatch.build_dispatch_registry()
        for i in range(contract.MAX_INFLIGHT_TASKS):
            registry.add(
                task_dispatch.DispatchRegistryEntry(
                    session_key=f"agent:dev:voice-agent-inflight-{i}",
                    label=f"在途任务{i}",
                    created_at=0.0,
                )
            )
        worker = await _make_dispatch_worker(registry)
        message = _respond_job_message()
        turn_task = await _start_respond_job(worker, message)

        create_task_calls: list[str | None] = []

        def rejecting_create_task(coro, name=None):
            create_task_calls.append(name)
            coro.close()  # 不得被调用到 —— 若被调用,关掉协程避免"从未 await"告警。
            return MagicMock()

        worker.create_task = rejecting_create_task  # type: ignore[method-assign]

        params = _FakeFunctionCallParams()
        await asyncio.wait_for(
            worker.reply(
                params,  # type: ignore[arg-type]
                answer="第二个LLM自己写的、上限存在前提未知的答案",
                tasks=["新任务"],
            ),
            timeout=1.0,
        )
        await turn_task

        self.assertEqual([], create_task_calls, "达上限时不得起任何 exec job(约定4①)")
        worker.send_job_response.assert_awaited_once()  # type: ignore[attr-defined]
        call = worker.send_job_response.await_args  # type: ignore[attr-defined]
        self.assertEqual({"answer": contract.CAPACITY_MESSAGE}, call.kwargs["response"])
        self.assertEqual(JobStatus.ERROR, call.kwargs["status"])
        self.assertEqual([None], params.result_callback_calls)
