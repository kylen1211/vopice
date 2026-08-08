"""Contract constants and pure data carriers for task-dispatch (C4 派活).

Single source of truth for the cross-component literals defined in
``pipeline/task-dispatch/contract/cases.md`` §0 — worker names, job names,
payload/response keys, ``TaskView`` field selection, the session-key
template, the openclaw external-command argv builders, the in-flight task
cap, and the test-only environment switch name.

No behavior lives here: dispatch, polling, event parsing, and material
injection are all implemented in ``server/task_dispatch.py`` (T-4). This
module only defines constants and plain dataclasses (fields, no methods).

Zero side-effect import (task card T-2 acceptance case 1): this module
reads no environment variables, calls no configuration loader, and imports
no pipecat symbol at runtime (pipecat types are only referenced under
``typing.TYPE_CHECKING``, deferred via ``from __future__ import
annotations``) — a bare interpreter can import it with no venv, no
``.env``, and no ``NLTK_DISABLE_IMPORT_SECURITY``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Type-check-only import: never executed at runtime (see module
    # docstring / acceptance case 1). Matches the existing import path used
    # in server/bot.py ("from pipecat.pipeline.worker import ... PipelineWorker").
    from pipecat.pipeline.worker import PipelineWorker

# ---------------------------------------------------------------------------
# §0.1 · worker names (bus addressing keys)
# ---------------------------------------------------------------------------

MAIN_WORKER_NAME = "voice-main"
DISPATCH_WORKER_NAME = "task-dispatch"
EXEC_WORKER_NAME = "openclaw-exec"

# ---------------------------------------------------------------------------
# §0.3 · dispatch worker (TaskDispatchWorker(UIWorker)) job contract
# ---------------------------------------------------------------------------

# UIWorker's built-in job name/payload key for the "respond" job (not
# redefined by this project, just named here so nobody inlines the string).
RESPOND_JOB_NAME = "respond"
QUERY_PAYLOAD_KEY = "query"

# In-flight task cap (2026-08-08 用户裁决新增, ADR-8). Not a configurable
# item on purpose — §0.3 explicitly forbids reading it from env / .env.example.
MAX_INFLIGHT_TASKS = 3
CAPACITY_MESSAGE = (
    "In-flight task limit (3) reached; none of the newly requested tasks "
    "were dispatched."
)

# ---------------------------------------------------------------------------
# §0.4 · exec worker (OpenClawExecWorker(BaseWorker)) job contract
# ---------------------------------------------------------------------------

DISPATCH_JOB_NAME = "dispatch"

# `degraded` closed set (§0.4; "notify-set-failed" removed this round along
# with the deleted CMD_TASKS_NOTIFY / original FR-4 notify-policy feature).
DEGRADED_TASK_RECORD_NOT_VISIBLE = "task-record-not-visible"
DEGRADED_MCP_BRIDGE_DOWN = "mcp-bridge-down"

# ---------------------------------------------------------------------------
# §0.5 · TaskView field selection (order verbatim per §0.5, plus the two
# project-added fields "lookup" / "found" appended at the end)
# ---------------------------------------------------------------------------

TASK_VIEW_FIELDS: tuple[str, ...] = (
    "taskId",
    "runtime",
    "status",
    "notifyPolicy",
    "deliveryStatus",
    "createdAt",
    "startedAt",
    "endedAt",
    "error",
    "progressSummary",
    "terminalSummary",
    "childSessionKey",
    "ownerKey",
    "lookup",
    "found",
)

# ---------------------------------------------------------------------------
# §0.6 · session key (relational primary key of this whole change)
# ---------------------------------------------------------------------------

SESSION_KEY_TEMPLATE = "agent:{agent_id}:voice-agent-{token}"
# Token generation is `uuid4().hex[:12]` (§0.6); this constant only
# captures the slice length so the "12" is not re-inlined elsewhere.
SESSION_KEY_TOKEN_LENGTH = 12

# ---------------------------------------------------------------------------
# §0.7 · openclaw external command argv builders
#
# Pure functions (no internal state, no subprocess spawning): each takes the
# values it needs and returns the argv list verbatim per §0.7. No component
# other than these three functions may inline an openclaw argv literal.
# ---------------------------------------------------------------------------


def cmd_agent(agent_id: str, session_key: str, message_file_path: str) -> list[str]:
    """Build argv for the long-running dispatch call (§0.7 ``CMD_AGENT``).

    ``openclaw agent --agent <agent_id> --session-key <session_key>
    --message-file <path> --json``
    """
    return [
        "openclaw",
        "agent",
        "--agent",
        agent_id,
        "--session-key",
        session_key,
        "--message-file",
        message_file_path,
        "--json",
    ]


def cmd_tasks_show(lookup: str) -> list[str]:
    """Build argv for the short status-query call (§0.7 ``CMD_TASKS_SHOW``).

    ``openclaw tasks show <lookup> --json`` (``<lookup>`` accepts a task id,
    run id, or session key).
    """
    return ["openclaw", "tasks", "show", lookup, "--json"]


def cmd_mcp_serve() -> list[str]:
    """Build argv for the standing MCP bridge subprocess (§0.7 ``CMD_MCP_SERVE``).

    ``openclaw mcp serve``
    """
    return ["openclaw", "mcp", "serve"]


# ---------------------------------------------------------------------------
# §0.10 · test-only environment switch name (production path: always unset)
# ---------------------------------------------------------------------------

ENV_TASK_DISPATCH_CLI = "TASK_DISPATCH_CLI"


# ---------------------------------------------------------------------------
# Pure dataclasses (fields only, no behavior)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DispatchRegistryEntry:
    """One row of the session-scoped dispatch registry (design.md 数据模型 §2).

    The registry container itself (add/remove/length-check behavior) is
    ``task_dispatch.DispatchRegistry`` (T-4); this is only the record shape
    it holds.
    """

    session_key: str
    label: str
    created_at: float


@dataclass(frozen=True)
class ExecDispatchPayload:
    """Inbound payload of the exec worker's ``dispatch`` job (§0.4)."""

    session_key: str
    label: str
    task: str


@dataclass(frozen=True)
class ExecDispatchResponse:
    """Outbound response of the exec worker's ``dispatch`` job (§0.4).

    ``degraded`` is ``None`` on the happy path, or one of the closed-set
    reason codes above (``DEGRADED_TASK_RECORD_NOT_VISIBLE`` /
    ``DEGRADED_MCP_BRIDGE_DOWN``).
    """

    session_key: str
    lookup: str
    degraded: str | None = None


@dataclass
class AppResources:
    """Carrier passed via ``PipelineWorker(app_resources=...)`` (数据模型 §2).

    Read by the two fast-brain tools (``dispatch_task`` / ``get_task_status``,
    T-4) through ``params.app_resources`` — the official channel, filling
    盘点缺口 K3.

    ``main_worker`` starts unset: ``build_dispatch_stack`` (T-4) constructs
    this object before the main ``PipelineWorker`` exists; ``run_bot``
    (T-5) writes the back-reference in once the worker is constructed
    (design.md 方案 C 节步骤 5).

    ``registry`` holds a ``task_dispatch.DispatchRegistry`` instance at
    runtime; typed as ``object`` here (not ``DispatchRegistry``) because
    this module must not import any other new module of this change
    (task card T-2 符号级依赖) and ``DispatchRegistry`` is defined
    downstream in ``task_dispatch.py``.
    """

    registry: object
    injection_queue: asyncio.Queue[str]
    agent_id: str
    main_worker: PipelineWorker | None = None
