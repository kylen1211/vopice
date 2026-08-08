"""Task-dispatch pipeline (C4 派活): execution + return-flow + decision layers.

Implements the three layers `pipeline/task-dispatch/design.md` assigns to a
single file (原设计表 T-3 执行层 + T-4 回流层 + T-5 决策层, 合卡理由见
`pipeline/task-dispatch/tasks/T-4.md` 卡首):

- **Decision layer** — `TaskDispatchWorker(UIWorker)`, the "task-dispatch"
  worker: runs the second, delegate LLM that turns a fast-brain request into
  zero or more concrete task briefs, subject to the in-flight cap (ADR-8).
- **Execution layer** — `OpenClawExecWorker(BaseWorker)`, the "openclaw-exec"
  worker: detached-spawns `openclaw agent` per task, polls for the resulting
  task record, and runs the standing `openclaw mcp serve` bridge that watches
  for each task's terminal assistant message.
- **Return-flow layer** — `_DispatchMaterialInjector(FrameProcessor)`: drains
  the session-scoped injection queue the exec worker's event loop feeds and
  folds it into the fast brain's context.
- **Fast-brain tools** — `dispatch_task` / `get_task_status`: the two
  function-calling tools registered on `fast_context` (assembled by T-5).
- **Session state** — `DispatchRegistry`: the in-memory index of in-flight
  dispatches (data model §2), and `build_dispatch_stack`, the session-scoped
  factory (R5 约定: 禁模块级单例) that wires all of the above together.

Contract: `pipeline/task-dispatch/contract/cases.md` §0 is the single source
of truth for every literal (worker/job names, payload shapes, argv, field
selection, session-key template, injection template) — this module imports
every constant/dataclass it needs from `task_dispatch_contract` rather than
inlining them, and imports `prompts.INJECT_TASK_TERMINAL_TEMPLATE` rather
than redefining it (T-3).

D-003 守法(账本 2026-08-08 s2a 裁决⑤,契约 §1 用例 10/11): this module reads
no environment variable and never calls `config.load_config()` at any scope
— every value it needs (the OpenClaw agent id, the already-constructed second
LLM, the `TASK_DISPATCH_CLI` test override) is injected through
`build_dispatch_stack`'s parameters, extracted by the caller (T-5's
`bot.py::assemble_pipeline`).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from loguru import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pipecat.adapters.schemas.direct_function import tool_options
from pipecat.bus.messages import BusJobRequestMessage
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    Frame,
    LLMMessagesAppendFrame,
    StartFrame,
)
from pipecat.pipeline.job_context import JobError, JobStatus
from pipecat.pipeline.job_decorator import job
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.registry.types import WorkerReadyData
from pipecat.services.llm_service import FunctionCallParams, LLMService
from pipecat.workers.base_worker import BaseWorker
from pipecat.workers.llm.tool_decorator import tool
from pipecat.workers.ui.ui_worker import UIWorker

import prompts
import task_dispatch_contract as contract
from task_dispatch_contract import (
    CAPACITY_MESSAGE,
    DEGRADED_MCP_BRIDGE_DOWN,
    DEGRADED_TASK_RECORD_NOT_VISIBLE,
    DISPATCH_JOB_NAME,
    MAX_INFLIGHT_TASKS,
    QUERY_PAYLOAD_KEY,
    RESPOND_JOB_NAME,
    SESSION_KEY_TEMPLATE,
    SESSION_KEY_TOKEN_LENGTH,
    AppResources,
    DispatchRegistryEntry,
    ExecDispatchPayload,
    ExecDispatchResponse,
)

# ---------------------------------------------------------------------------
# Module-local implementation constants (NOT contract §0 items — these never
# cross a T-* boundary, so they live here rather than in
# task_dispatch_contract.py; see task card T-4 独占路径 for why that file is
# out of scope for this task).
# ---------------------------------------------------------------------------

# §0.7 硬性约定 7 / D-7: a single `tasks show` call is ~2.3-2.6s (node CLI cold
# start). 10x that is a generous "the CLI process itself hung" backstop —
# 硬规则4 外部调用必设超时。
_TASKS_SHOW_SUBPROCESS_TIMEOUT_SECS = 10.0

# §0.4 额外职责 / design.md 方案 C 步骤9: exec worker 轮询 `tasks show` 直到命中,
# 上限 30 秒。
_LOOKUP_POLL_TIMEOUT_SECS = 30.0

# §0.8 条 3: "超时(默认 30 秒...)" — the value we pass as the events_wait tool's
# own `timeout_ms` argument (server-side wait bound, not a client transport
# timeout — see the +10s margin on `_EVENTS_WAIT_READ_TIMEOUT` below).
_EVENTS_WAIT_TIMEOUT_MS = 30_000
# Client-side belt-and-braces on top of the server's own timeout_ms bound
# above (mcp `ClientSession.call_tool`'s `read_timeout_seconds` defaults to
# "wait forever" — see `mcp/shared/session.py`). Only trips if the bridge
# process itself is wedged, which should never happen if the server honors
# its own timeout_ms.
_EVENTS_WAIT_READ_TIMEOUT = timedelta(milliseconds=_EVENTS_WAIT_TIMEOUT_MS + 10_000)

# §0.9 "{label}"：不超过 40 字的一句话摘要 (§0.4 payload 表)。The exact
# derivation isn't specified by the contract (the `reply` tool only receives
# full task-brief strings, not a separate label field from the second LLM —
# see backend-notes.md "疑虑" for the reasoning) — collapsed-whitespace,
# first-40-chars truncation of the task text is the simplest deterministic
# rule that satisfies the length cap without inventing a summarization step.
_TASK_LABEL_MAX_CHARS = 40


@dataclass(frozen=True)
class _SubprocessResult:
    """Outcome of one `openclaw` subprocess invocation this module made.

    Never raises out of `_run_openclaw_subprocess` — OS/timeout failures are
    folded into `exit_code=1` with a synthetic `stderr` line so every caller
    (the exec worker's lookup poll, `get_task_status`'s per-lookup query) can
    use the exact same "exit_code != 0 → degrade, don't raise" handling
    without its own try/except (硬规则5: 错误不吞, 带上下文交给调用方).
    """

    exit_code: int
    stdout: str
    stderr: str


async def _run_openclaw_subprocess(argv: list[str]) -> _SubprocessResult:
    """Run a short-lived `openclaw` subprocess and capture its output.

    Only used for `CMD_TASKS_SHOW`-shaped calls (§0.7): synchronous, ~2.3-2.6s
    (D-7), read from both streams (§0.7 硬性约定 6: a hit's JSON lands on
    stderr, stdout is empty — the caller decides which stream to parse).
    """
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        return _SubprocessResult(exit_code=1, stdout="", stderr=f"{type(exc).__name__}: {exc}")

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=_TASKS_SHOW_SUBPROCESS_TIMEOUT_SECS
        )
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
            await process.wait()
        return _SubprocessResult(
            exit_code=1,
            stdout="",
            stderr=f"{' '.join(argv)} timed out after {_TASKS_SHOW_SUBPROCESS_TIMEOUT_SECS}s",
        )

    return _SubprocessResult(
        exit_code=process.returncode if process.returncode is not None else 1,
        stdout=stdout_bytes.decode("utf-8", errors="replace"),
        stderr=stderr_bytes.decode("utf-8", errors="replace"),
    )


def _first_stderr_line(stderr_text: str) -> str:
    """First non-empty line of a captured stderr blob, or "" if there is none.

    §0.7 硬性约定1/§0.2 T2 "单条查不到": the CLI's error-reason convention is
    "first stderr line" throughout this contract (`Task not found: ...`).
    """
    stripped = stderr_text.strip()
    return stripped.splitlines()[0] if stripped else ""


def _build_task_view(record: dict[str, Any], lookup: str) -> dict[str, Any]:
    """Select §0.5 `TaskView` fields from a raw `tasks show --json` record.

    D-5: fields are read with `.get()`-equivalent presence checks — the
    "恒在字段" always come through, the three "条件字段" (`error` /
    `progressSummary` / `terminalSummary`) are omitted entirely when absent
    rather than backfilled with `None` (§0.5: "不补默认值").
    """
    view: dict[str, Any] = {}
    for field_name in contract.TASK_VIEW_FIELDS:
        if field_name in ("lookup", "found"):
            continue
        if field_name in record:
            view[field_name] = record[field_name]
    view["lookup"] = lookup
    view["found"] = True
    return view


async def _query_task_view(lookup: str) -> dict[str, Any]:
    """Run one `CMD_TASKS_SHOW` and shape the result per §0.2 T2 / §0.5.

    Never raises — a miss (exit != 0), an unparseable body, or a
    non-dict JSON payload all degrade to the `{"lookup", "found": false,
    "reason"}` shape (§0.2 T2 "单条查不到"), never to an exception.
    """
    result = await _run_openclaw_subprocess(contract.cmd_tasks_show(lookup))
    if result.exit_code != 0:
        return {
            "lookup": lookup,
            "found": False,
            "reason": _first_stderr_line(result.stderr) or "unknown error",
        }
    # D-1: a hit's JSON is on stderr, stdout is empty.
    try:
        record = json.loads(result.stderr)
    except json.JSONDecodeError as exc:
        return {"lookup": lookup, "found": False, "reason": f"unparseable tasks show output: {exc}"}
    if not isinstance(record, dict):
        return {"lookup": lookup, "found": False, "reason": "unexpected tasks show output shape"}
    return _build_task_view(record, lookup)


def _generate_session_key(agent_id: str) -> str:
    """§0.6 relational primary key: `agent:{agent_id}:voice-agent-{token}`."""
    token = uuid.uuid4().hex[:SESSION_KEY_TOKEN_LENGTH]
    return SESSION_KEY_TEMPLATE.format(agent_id=agent_id, token=token)


def _derive_label(task_text: str) -> str:
    """Collapsed-whitespace, ≤40-char label for a task brief (see module-level
    `_TASK_LABEL_MAX_CHARS` docstring for why this is a deterministic
    truncation rather than a second-LLM-supplied summary)."""
    collapsed = " ".join(task_text.split())
    return collapsed[:_TASK_LABEL_MAX_CHARS]


# ---------------------------------------------------------------------------
# §0.2 · fast-brain function-calling tools (module-level, registered on
# fast_context by T-5)
# ---------------------------------------------------------------------------


@tool_options(cancel_on_interruption=False, timeout_secs=20.0)
async def dispatch_task(params: FunctionCallParams, request: str) -> None:
    """Hand a task the user asked for to the background agent. Use it when the user asks for something to be done rather than answered.

    Args:
        request: The user's original request for this turn, verbatim — do
            not rewrite or split it up (splitting is the delegate worker's
            job, not this tool's).
    """
    app_resources: AppResources = params.app_resources
    job_ctx = None
    try:
        if app_resources is None or app_resources.main_worker is None:
            raise RuntimeError("main_worker is not wired into app_resources yet")
        async with app_resources.main_worker.job(
            contract.DISPATCH_WORKER_NAME,
            name=RESPOND_JOB_NAME,
            payload={QUERY_PAYLOAD_KEY: request},
        ) as job_ctx:
            pass
        note = (job_ctx.response or {}).get("answer", "")
        await params.result_callback({"accepted": True, "note": note})
    except Exception as exc:
        # Prefer the dispatch worker's own answer text when the job round
        # trip did complete but with an ERROR status (e.g. ADR-8's capacity
        # rejection, whose CAPACITY_MESSAGE lands in job_ctx.response even
        # though __aexit__ raises JobError) — falls back to str(exc) for
        # genuine transport/timeout failures that never got a response at
        # all. Zero capacity-specific branching (ADR-8): any job error with
        # a response "answer" surfaces it the same way.
        detail = str(exc)
        if job_ctx is not None:
            answer = (job_ctx.response or {}).get("answer")
            if answer:
                detail = answer
        await params.result_callback(
            {"accepted": False, "error": f"{type(exc).__name__}: {detail[:200]}"}
        )


@tool_options(cancel_on_interruption=False, timeout_secs=15.0)
async def get_task_status(params: FunctionCallParams, lookup: str | None = None) -> None:
    """Look up the current state of background tasks dispatched earlier in this conversation.

    Args:
        lookup: A specific task/session lookup key to check. Omit to check
            every task dispatched so far in this conversation.
    """
    app_resources: AppResources = params.app_resources
    registry: DispatchRegistry = app_resources.registry  # type: ignore[assignment]
    lookups = [lookup] if lookup is not None else registry.lookups()

    # §0.2 T2: "不得调用 openclaw tasks list 的无过滤全量列表" — only ever
    # CMD_TASKS_SHOW, one call per lookup, never a bulk listing call.
    views = [await _query_task_view(one) for one in lookups]
    await params.result_callback({"tasks": views})


# ---------------------------------------------------------------------------
# §0.2 数据模型 §2 · DispatchRegistry (session-scoped, R5 工厂约定)
# ---------------------------------------------------------------------------


class DispatchRegistry:
    """Session-scoped index of in-flight dispatches (数据模型 §2).

    Holds no status field of its own (不变量①: 问状态一律现查 OpenClaw),
    isn't persisted (②), is constructed fresh per session by
    `build_dispatch_stack` rather than as a module singleton (③, R5), and
    returns an empty list rather than raising when nothing is in flight (④).
    `len(registry)` (⑤, ADR-8) is the in-flight count `TaskDispatchWorker.
    reply()` checks against `MAX_INFLIGHT_TASKS`.
    """

    def __init__(self) -> None:
        self._entries: dict[str, DispatchRegistryEntry] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def add(self, entry: DispatchRegistryEntry) -> None:
        self._entries[entry.session_key] = entry

    def remove(self, session_key: str) -> DispatchRegistryEntry | None:
        """Remove and return the entry, or None if it wasn't present (idempotent)."""
        return self._entries.pop(session_key, None)

    def get(self, session_key: str) -> DispatchRegistryEntry | None:
        return self._entries.get(session_key)

    def lookups(self) -> list[str]:
        """Session keys of every in-flight entry — ④ empty registry → `[]`, never raises."""
        return list(self._entries.keys())


def build_dispatch_registry() -> DispatchRegistry:
    """Construct a fresh, session-scoped `DispatchRegistry` (R5 约定同 dual_brain.py)."""
    return DispatchRegistry()


# ---------------------------------------------------------------------------
# §0.3 · TaskDispatchWorker(UIWorker) — decision layer
# ---------------------------------------------------------------------------


class TaskDispatchWorker(UIWorker):
    """Decision layer: the "task-dispatch" worker (§0.1, §0.3).

    Receives the built-in `respond` job (`UIWorker`'s own `@job(name=
    "respond", sequential=True)` — not redefined here) with `{"query": ...}`,
    runs its own (second) LLM turn, and completes via the single `reply`
    tool below. This class body never calls any of `UIWorker`'s job-group
    fan-out/cancel APIs (本期不启用, design.md §B) — held to that by C-16's
    grep + static-assertion test, not by convention alone.
    """

    def __init__(
        self,
        name: str,
        *,
        llm: LLMService[Any],
        registry: DispatchRegistry,
        agent_id: str,
    ) -> None:
        # prompt_guide=None: UIWorker's default UI_STATE_PROMPT_GUIDE teaches
        # the LLM a <ui_state>/<ui_event> wire format this worker never uses
        # (本期不启用 UI 能力, design.md §B) — appending it would just be
        # system-prompt bloat with nothing behind it. Every other UIWorker
        # default (auto_inject_ui_state, inject_events, keep_history) is a
        # true no-op with no snapshot ever set, so those stay at default.
        super().__init__(name, llm=llm, prompt_guide=None)
        # NOT `self._registry` — `BaseWorker.__init__` already claims that
        # name for its own `WorkerRegistry` reference (populated later by
        # `attach()`, called from `WorkerRunner.add_workers()`, which runs
        # *after* this constructor and would silently clobber a same-named
        # attribute). Caught by this task card's own driving-script scenario
        # (acceptance case 8 - real run, not mocked): `len(self._registry)`
        # against the real `WorkerRegistry` raises `TypeError` at the first
        # capacity check, hanging the whole reply() call is exactly how it
        # surfaced — see backend-notes.md.
        self._dispatch_registry = registry
        self._agent_id = agent_id

    @tool(cancel_on_interruption=False, timeout_secs=30)
    async def reply(
        self, params: FunctionCallParams, answer: str, tasks: list[str] | None = None
    ) -> None:
        """Finish this delegate turn: report back to the fast brain and, if
        warranted, hand the written task briefs to the background execution
        worker.

        Args:
            answer: One-sentence takeaway handed back to the fast brain
                (e.g. "sent three things off to be done"); the fast brain
                phrases what the user actually hears from this.
            tasks: The fully written task briefs to dispatch now, one per
                background run. Omit or pass an empty list when this turn
                doesn't warrant dispatching anything.
        """
        task_list = list(tasks or [])

        # §0.3 "在途任务上限" 行为约定 1-4 / ADR-8: single checkpoint, right
        # here, before step ① — the only point that sees both the current
        # in-flight count and the full fan-out list at once.
        if len(self._dispatch_registry) + len(task_list) > MAX_INFLIGHT_TASKS:
            logger.warning(
                f"[task-dispatch] capacity-reached inflight={len(self._dispatch_registry)} "
                f"incoming={len(task_list)} max={MAX_INFLIGHT_TASKS}"
            )
            # 约定4: 整批拒绝，不起任何 exec job；不使用第二个 LLM 自己写的 answer。
            await self.respond_to_job(answer=CAPACITY_MESSAGE, status=JobStatus.ERROR)
            await params.result_callback(None)
            return

        # 约定6: 未超限，按原①②次序继续。① 不等待地起 exec job。
        for task_text in task_list:
            session_key = _generate_session_key(self._agent_id)
            label = _derive_label(task_text)
            exec_payload = ExecDispatchPayload(session_key=session_key, label=label, task=task_text)
            self.create_task(
                self._dispatch_one(session_key, asdict(exec_payload)),
                f"{self.name}::dispatch::{session_key}",
            )

        # ② 立即回应，不 await 上面任何一个 exec job 的完成（§0.3 硬约束）。
        await self.respond_to_job(answer)
        await params.result_callback(None)

    async def _dispatch_one(self, session_key: str, payload: dict[str, Any]) -> None:
        """Fire one exec-worker `dispatch` job without waiting on it from `reply()`.

        This coroutine itself *does* wait for the exec worker's response
        (§0.4 出站 job 响应) — just not synchronously from inside `reply()`,
        since it only ever runs inside a `self.create_task(...)` `reply()`
        never awaits (§0.3 硬约束, C-15 acceptance case 8).
        """
        try:
            async with self.job(
                contract.EXEC_WORKER_NAME, name=DISPATCH_JOB_NAME, payload=payload
            ) as job_ctx:
                pass
            logger.info(f"[task-dispatch] exec-dispatched response={job_ctx.response}")
        except JobError as exc:
            logger.warning(
                f"[task-dispatch] exec-dispatch-failed session_key={session_key} error={exc}"
            )


# ---------------------------------------------------------------------------
# §0.4 · OpenClawExecWorker(BaseWorker) — execution layer
# ---------------------------------------------------------------------------


@dataclass
class _CliProcessOutcome:
    """Mutable holder the CLI-exit watcher task fills in once the detached
    `openclaw agent` process exits (§0.7 硬性约定4: detached, never awaited
    from the response path itself).

    Two independent readers need this without awaiting the process
    themselves: the lookup poll's early-failure check (`process.returncode`
    alone doesn't carry stderr text) and the final debug-log line. Per
    ADR-2, the captured `returncode`/stderr are *never* used to judge the
    dispatch outcome once a task record has actually been seen — only to
    detect the "the CLI died before doing any work" case C-04 covers (a bad
    `--agent`), which is a much stronger signal than the "F6-style"
    misleading-success-after-a-real-run case ADR-2 warns about.
    """

    returncode: int | None = None
    stderr_first_line: str = ""
    captured: asyncio.Event = field(default_factory=asyncio.Event)


class OpenClawExecWorker(BaseWorker):
    """Execution layer: the "openclaw-exec" worker (§0.1, §0.4).

    Two independent responsibilities per task card / §0.4:
    - `dispatch` job (`sequential=False`, §0.4): detached-spawn `openclaw
      agent`, poll `tasks show` for the resulting record (≤30s), register
      the entry, and respond.
    - `on_worker_ready`-triggered background asyncio task (§0.8 条1/条5):
      holds the standing `openclaw mcp serve` stdio bridge and feeds
      terminal assistant messages into the injection queue. Started via a
      self-watch (`watch_workers(self.name)`) inside `start()`, so it is
      already running before this worker's first `dispatch` job can even
      arrive — connecting after the fact would silently miss any events
      that landed before the bridge connected (§0.8 条5, D-3).
    """

    def __init__(
        self,
        name: str,
        *,
        agent_id: str,
        registry: DispatchRegistry,
        injection_queue: asyncio.Queue[str],
        cli_override: str | None = None,
    ) -> None:
        super().__init__(name)
        self._agent_id = agent_id
        # See TaskDispatchWorker.__init__ for why this is not `self._registry`
        # — `BaseWorker` already owns that name for its own `WorkerRegistry`.
        self._dispatch_registry = registry
        self._injection_queue = injection_queue
        self._cli_override = cli_override
        self._bridge_ready = False
        self._events_task: asyncio.Task | None = None

    async def start(self) -> None:
        await super().start()
        # Fires on_worker_ready(data) immediately below, synchronously,
        # since this worker is already registered by the time
        # super().start() returns (BaseWorker.start() calls
        # _register_ready() before returning) — see WorkerRegistry.watch()
        # docstring: "If the worker is already registered, the handler
        # fires immediately."
        await self.watch_workers(self.name)

    async def stop(self) -> None:
        if self._events_task is not None:
            await self.cancel_task(self._events_task)
            self._events_task = None
        await super().stop()

    async def on_worker_ready(self, data: WorkerReadyData) -> None:
        await super().on_worker_ready(data)
        if data.worker_name != self.name:
            return
        if self._events_task is None:
            self._events_task = self.create_task(
                self._run_events_loop(), f"{self.name}::events_wait_loop"
            )

    # -- dispatch job --------------------------------------------------

    @job(name=DISPATCH_JOB_NAME, sequential=False)
    async def _dispatch_job(self, message: BusJobRequestMessage) -> None:
        await self._handle_dispatch(message)

    async def _handle_dispatch(self, message: BusJobRequestMessage) -> None:
        payload = message.payload or {}
        session_key = str(payload.get("session_key") or "")
        label = str(payload.get("label") or "")
        task_text = str(payload.get("task") or "")
        if not session_key or not task_text:
            logger.error(f"[openclaw-exec] dispatch-bad-payload job_id={message.job_id}")
            await self.send_job_response(
                message.job_id,
                {"error": "dispatch payload missing session_key/task"},
                status=JobStatus.ERROR,
            )
            return

        tmp_dir = tempfile.mkdtemp(prefix="voice-agent-dispatch-")
        message_file_path = str(Path(tmp_dir) / "task.txt")
        try:
            Path(message_file_path).write_text(task_text, encoding="utf-8")
        except OSError as exc:
            logger.error(
                f"[openclaw-exec] task-file-write-failed session_key={session_key} error={exc}"
            )
            await self.send_job_response(
                message.job_id, {"error": f"{type(exc).__name__}: {exc}"}, status=JobStatus.ERROR
            )
            return

        argv = contract.cmd_agent(self._agent_id, session_key, message_file_path)
        if self._cli_override:
            # §0.10: cli_override only replaces argv[0] (the program name);
            # every other CMD_AGENT argument stays verbatim.
            argv[0] = self._cli_override

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,  # §0.7 约定4: detached, survives worker.cancel().
            )
        except OSError as exc:
            logger.error(f"[openclaw-exec] spawn-failed session_key={session_key} error={exc}")
            with contextlib.suppress(OSError):
                Path(message_file_path).unlink(missing_ok=True)
                Path(tmp_dir).rmdir()
            await self.send_job_response(
                message.job_id, {"error": f"{type(exc).__name__}: {exc}"}, status=JobStatus.ERROR
            )
            return

        outcome = _CliProcessOutcome()
        self.create_task(
            self._watch_cli_process(process, tmp_dir, outcome),
            f"{self.name}::cli-watch::{session_key}",
        )

        found, cli_failed = await self._poll_until_visible(session_key, process, outcome)

        if cli_failed:
            stderr_line = outcome.stderr_first_line or "(no stderr captured)"
            logger.warning(
                f"[openclaw-exec] cli-dispatch-failed session_key={session_key} "
                f"returncode={outcome.returncode} stderr={stderr_line}"
            )
            await self.send_job_response(
                message.job_id,
                {"error": f"openclaw agent exited {outcome.returncode}: {stderr_line}"},
                status=JobStatus.ERROR,
            )
            return

        degraded: str | None = None
        if not self._bridge_ready:
            degraded = DEGRADED_MCP_BRIDGE_DOWN
        elif not found:
            degraded = DEGRADED_TASK_RECORD_NOT_VISIBLE

        self._dispatch_registry.add(
            DispatchRegistryEntry(session_key=session_key, label=label, created_at=time.monotonic())
        )
        logger.info(f"[openclaw-exec] dispatched session_key={session_key} degraded={degraded}")
        response = ExecDispatchResponse(
            session_key=session_key, lookup=session_key, degraded=degraded
        )
        await self.send_job_response(message.job_id, asdict(response), status=JobStatus.COMPLETED)

    async def _poll_until_visible(
        self, session_key: str, process: asyncio.subprocess.Process, outcome: _CliProcessOutcome
    ) -> tuple[bool, bool]:
        """Poll `tasks show <session_key>` until it hits, up to `_LOOKUP_POLL_TIMEOUT_SECS`.

        Returns `(found, cli_failed)`. `cli_failed` is only True when the
        detached process has *already exited* with a non-zero code before
        the record ever became visible (C-04's fast-failure case, e.g. a
        bad `--agent`) — a real long-running dispatch never exits this
        quickly, so this can't misfire on a normal run (ADR-2).
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _LOOKUP_POLL_TIMEOUT_SECS
        while True:
            result = await _run_openclaw_subprocess(contract.cmd_tasks_show(session_key))
            if result.exit_code == 0:
                return True, False
            if process.returncode is not None and process.returncode != 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(outcome.captured.wait(), timeout=2.0)
                return False, True
            if loop.time() >= deadline:
                return False, False

    async def _watch_cli_process(
        self, process: asyncio.subprocess.Process, tmp_dir: str, outcome: _CliProcessOutcome
    ) -> None:
        """Drain the detached CLI's pipes to EOF and clean up its temp file.

        §0.7 约定3: the temp file is deleted "by the asyncio task that
        started the process, after the child exits" — this task is created
        immediately after the spawn inside the same `_handle_dispatch` call,
        and is the one that actually observes the exit (`_handle_dispatch`
        itself returns as soon as it has responded to the job, per ADR-2's
        "不等待"). Continuously draining here (rather than only checking
        `process.returncode`) also avoids a long-running task blocking on a
        full stdout/stderr OS pipe buffer.
        """
        try:
            stdout_bytes, stderr_bytes = await process.communicate()
        except Exception as exc:  # pragma: no cover - communicate() rarely raises
            logger.warning(f"[openclaw-exec] cli-watch-error error={exc}")
            stdout_bytes, stderr_bytes = b"", b""
        outcome.returncode = process.returncode
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")
        outcome.stderr_first_line = _first_stderr_line(stderr_text)
        outcome.captured.set()
        # ADR-2: exit code/stdout are unreliable once the run actually
        # happened (F6: CLI reports ok/completed while the task record is
        # `failed`) — this line is a debug breadcrumb only, never fed into
        # any decision past the early-failure check in `_poll_until_visible`.
        logger.debug(
            f"[openclaw-exec] cli-exited returncode={process.returncode} "
            f"stderr_first_line={outcome.stderr_first_line!r}"
        )
        with contextlib.suppress(OSError):
            Path(tmp_dir).joinpath("task.txt").unlink(missing_ok=True)
            Path(tmp_dir).rmdir()

    # -- MCP bridge / events_wait loop ----------------------------------

    async def _run_events_loop(self) -> None:
        """Standing `openclaw mcp serve` bridge (§0.8). Never registered on
        any LLM (条1) — this is a private asyncio task's own loop.

        No reconnect-on-failure logic: per ADR-5 ("不做兜底状态轮询"), this
        module does not add fallback machinery beyond what the contract
        specifies. If the bridge dies mid-session, `_bridge_ready` drops to
        False (surfaced via `degraded="mcp-bridge-down"` on the next
        dispatch) and this task simply ends — documented as a known
        limitation in backend-notes.md, not silently retried.
        """
        argv = contract.cmd_mcp_serve()
        server_params = StdioServerParameters(command=argv[0], args=argv[1:])
        try:
            async with stdio_client(server_params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    self._bridge_ready = True
                    logger.info(f"[openclaw-exec] mcp-bridge-up worker={self.name}")
                    cursor = 0
                    while True:
                        result = await session.call_tool(
                            "events_wait",
                            {"after_cursor": cursor, "timeout_ms": _EVENTS_WAIT_TIMEOUT_MS},
                            read_timeout_seconds=_EVENTS_WAIT_READ_TIMEOUT,
                        )
                        if result.isError:
                            raise RuntimeError(f"events_wait tool error: {result.content}")
                        structured = result.structuredContent or {}
                        event = structured.get("event")
                        if event is None:
                            continue
                        cursor = event.get("cursor", cursor)
                        await self._maybe_report_terminal_event(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._bridge_ready = False
            logger.error(f"[openclaw-exec] mcp-bridge-down worker={self.name} error={exc}")

    async def _maybe_report_terminal_event(self, event: dict[str, Any]) -> None:
        """§0.8 条 8/9, §0.9 筛选条件: only a `stopReason == "stop"` assistant
        message for a session key this worker is tracking becomes a
        playback item — everything else (tool-use/aborted assistant
        messages, user messages, approval events, unrelated session keys)
        is dropped with no side effect, per FR-3 判据5 / C-18.

        Every field name read here (`sessionKey`, `type`, `role`, `raw`,
        `message`, `stopReason`, `text`, `cursor`) is verified against
        `pipeline/task-dispatch/baseline/mcp-event-sample.json` (T-1) — see
        backend-notes.md acceptance case 9.
        """
        session_key = event.get("sessionKey")
        if not session_key:
            return
        entry = self._dispatch_registry.get(session_key)
        if entry is None:
            return
        if event.get("type") != "message" or event.get("role") != "assistant":
            return
        raw = event.get("raw") or {}
        message = raw.get("message") or {}
        if message.get("stopReason") != "stop":
            return

        agent_text = event.get("text", "")
        rendered = prompts.INJECT_TASK_TERMINAL_TEMPLATE.format(
            label=entry.label, agent_text=agent_text
        )
        await self._injection_queue.put(rendered)
        self._dispatch_registry.remove(session_key)
        logger.info(
            f"[openclaw-exec] terminal-report session_key={session_key} label={entry.label!r}"
        )


# ---------------------------------------------------------------------------
# §0.9 · _DispatchMaterialInjector(FrameProcessor) — return-flow layer
# ---------------------------------------------------------------------------


class _DispatchMaterialInjector(FrameProcessor):
    """Fast-brain-branch-head processor that drains the injection queue
    (ADR-4: "同构而非同实例" — same queue-in/frame-out shape as
    `ConsumerProcessor`, but the source is a worker, not an in-pipeline
    `ProducerProcessor`, so a bespoke ~40-line processor is used instead).

    Passthrough for every frame it sees (never filters/alters the pipeline's
    own frame flow); its own output is exclusively the merged
    `LLMMessagesAppendFrame` pushed from the drain loop. No output component
    lives downstream of this processor by construction — it only pushes into
    the fast-brain context path, never to a transport (FR-3 判据1 structural
    requirement, L2 test).
    """

    def __init__(self, queue: asyncio.Queue[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self._queue = queue
        self._drain_task: asyncio.Task | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, StartFrame):
            self._start()
        elif isinstance(frame, EndFrame):
            await self._cancel_drain_task()
        elif isinstance(frame, CancelFrame):
            await self._cancel_drain_task()

        await self.push_frame(frame, direction)

    async def cleanup(self) -> None:
        await super().cleanup()
        await self._cancel_drain_task()

    def _start(self) -> None:
        if self._drain_task is None:
            self._drain_task = self.create_task(self._drain_loop())

    async def _cancel_drain_task(self) -> None:
        if self._drain_task:
            await self.cancel_task(self._drain_task)
            self._drain_task = None

    async def _drain_loop(self) -> None:
        """§0.9 合并规则: block for the first item, then drain whatever else
        is already queued and merge all of it into **one**
        `LLMMessagesAppendFrame` (FR-3 判据3 — no separate frame per item,
        no double-answering when two tasks finish within the same
        insertion window, C-10)."""
        while True:
            items = [await self._queue.get()]
            while True:
                try:
                    items.append(self._queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            content = "\n".join(items)
            await self.queue_frame(
                LLMMessagesAppendFrame(
                    messages=[{"role": "user", "content": content}], run_llm=True
                ),
                FrameDirection.DOWNSTREAM,
            )


# ---------------------------------------------------------------------------
# Session-scoped factory (R5 约定: 禁模块级单例)
# ---------------------------------------------------------------------------


@dataclass
class DispatchStack:
    """Everything one session's task-dispatch wiring needs, handed back from
    `build_dispatch_stack` for T-5's `assemble_pipeline` to wire in."""

    dispatch_worker: TaskDispatchWorker
    exec_worker: OpenClawExecWorker
    registry: DispatchRegistry
    injection_queue: asyncio.Queue[str]
    app_resources: AppResources

    def build_injector(self) -> _DispatchMaterialInjector:
        """Construct a fresh `_DispatchMaterialInjector` bound to this
        session's injection queue (design.md 方案 C 步骤4②)."""
        return _DispatchMaterialInjector(self.injection_queue)


def build_dispatch_stack(
    agent_id: str,
    *,
    llm: LLMService[Any],
    cli_override: str | None = None,
) -> DispatchStack:
    """Session-scoped factory for the whole task-dispatch stack (R5 约定).

    Args:
        agent_id: The OpenClaw agent id (`.env` `OPENCLAW_AGENT_ID`, §0.6) —
            **not** the project's `Config` object. This module never reads
            `server/config.py` field names (D-003 守法②, task card T-4 P56
            "配置字段级" 依赖点): T-5 extracts the one config value this
            stack needs and passes it positionally, exactly as it already
            extracts (and passes in) `llm` — the already-constructed second
            LLM service, built the same way `bot.py::assemble_pipeline`
            builds `fast_llm`/`slow_llm` today, not re-derived here.
        llm: The already-constructed second LLM service for
            `TaskDispatchWorker`'s delegate turn.
        cli_override: §0.10 `ENV_TASK_DISPATCH_CLI` test-only value (already
            read from the environment by the caller — this module never
            reads env vars itself, D-003 守法②). `None`/omitted is the
            production path.

    Returns:
        A `DispatchStack` holding both new workers, the session's
        `DispatchRegistry`, its injection queue, and the `app_resources`
        bag the two fast-brain tools read via `params.app_resources`.
        `app_resources.main_worker` starts unset — T-5 fills it in once the
        main `PipelineWorker` exists (design.md 方案 C 步骤5).
    """
    registry = build_dispatch_registry()
    injection_queue: asyncio.Queue[str] = asyncio.Queue()
    app_resources = AppResources(
        registry=registry, injection_queue=injection_queue, agent_id=agent_id
    )

    dispatch_worker = TaskDispatchWorker(
        contract.DISPATCH_WORKER_NAME, llm=llm, registry=registry, agent_id=agent_id
    )
    exec_worker = OpenClawExecWorker(
        contract.EXEC_WORKER_NAME,
        agent_id=agent_id,
        registry=registry,
        injection_queue=injection_queue,
        cli_override=cli_override,
    )

    return DispatchStack(
        dispatch_worker=dispatch_worker,
        exec_worker=exec_worker,
        registry=registry,
        injection_queue=injection_queue,
        app_resources=app_resources,
    )
