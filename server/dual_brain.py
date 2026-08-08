"""Slow-brain turn state for the fast/slow-brain feature (design §5.2).

`SlowBrainState` is pure data — three fields plus the three judgments they
back — with no scheduling logic and no state-transition graph of its own
(design §5.2 table: "纯数据 + 三个判定,无调度、无状态迁移图"). The
transitions (when each field resets/flips) live in `slow_material_filter`
(T3.3) and `slow_material_transformer` (T3.4), not here.
"""

from dataclasses import dataclass

from loguru import logger
from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMMessagesAppendFrame,
    LLMTextFrame,
    TextFrame,
)
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from prompts import INJECT_DONE_TEMPLATE, INJECT_DONE_WITH_REMINDER_TEMPLATE, INJECT_POINT_TEMPLATE


@dataclass
class SlowBrainState:
    """Per-turn state for the slow-brain Producer predicate/transformer.

    Deliberately **not** `frozen=True`: `slow_material_filter` mutates these
    fields in place at each transition point (design §5.2 "状态迁移落点"),
    e.g. `state.has_material = True` when a material point lands, or
    resetting all three fields when a new `LLMFullResponseStartFrame`
    arrives. A frozen dataclass would force every transition to reconstruct
    a new instance and rebind whatever held the reference — needless
    ceremony for a single-owner turn-scoped state object with no sharing/
    concurrency concerns that would call for immutability.
    """

    has_material: bool
    """Whether this turn has produced at least one material point so far.

    Set True the moment a point is accepted (design §5.2 predicate table,
    `TextFrame` row). Gates the completion marker: the framework's
    `finally` block unconditionally emits `LLMFullResponseEndFrame` even on
    failure (`services/openai/base_llm.py:571-573`), so without this flag
    the predicate cannot tell a real completion from a zero-material one —
    the false-positive would fire "material ready" with nothing behind it
    (design §5.2 row ②, R8-S1).
    """

    aborted: bool
    """Whether this turn has been interrupted.

    Set True the moment `InterruptionFrame` reaches the slow branch. Covers
    the window between the interruption broadcast (immediate) and the new
    user message actually landing in context after STT + aggregation
    (hundreds of ms to seconds) — during that window a `basis` comparison
    alone would still pass, since context still shows the old user message
    (design §5.2 row ③). `aborted` is the primary defense for R7; `basis`
    below is the defense-in-depth backstop.
    """

    basis: str
    """String *copy* of the user question this turn's analysis is based on.

    Captured as `LLMFullResponseStartFrame` resets the other two fields:
    the `content` of the slow-brain context's last `role == "user"`
    message, copied as a string — never the message object or the list
    returned by `get_messages()`. `get_messages()` returns an internal
    list *reference*, not a snapshot (`llm_context.py:227-279`); holding it
    would make every later comparison trivially equal (and the tests would
    stay green regardless), because the reference keeps following whatever
    the context appends next. Likewise this must never be captured via
    `len(messages) - 1` as a positional index — the slow-brain assistant
    message is appended after it (`llm_response_universal.py:1603`), so the
    "last message" index drifts as soon as that happens. Without a
    faithful, frozen-at-capture-time `basis`, stale material from a
    superseded question could be misattributed to a newer one in the
    conversation flow (design §5.2 row ①).
    """


class _SlowMaterialFilter:
    """Stateful Producer `filter` predicate for the slow-brain branch (T3.3).

    `ProducerProcessor.filter` is typed `Callable[[Frame], Awaitable[bool]]`
    (`producer_processor.py:40`) — a single positional `Frame` argument, no
    room for an injected `LLMContext`. But design §5.2's state-transition
    contract needs one: on `LLMFullResponseStartFrame` it must snapshot "the
    content of the slow-brain context's last `role == 'user'` message" as
    `basis`, then re-read the same thing on every later `TextFrame` /
    `LLMFullResponseEndFrame` to compare. A plain function has nowhere to
    keep that reference between calls.

    Same shape as `sentinel.py`'s `_SentinelGate` — "predicate signature is
    fixed, but it needs to remember something across calls" — solved the
    same way: a stateful callable class with a module-level singleton
    (`slow_material_filter` below) so `dual_brain.slow_material_filter` is a
    ready-made `filter=...` value. This adds one more dimension beyond
    `_SentinelGate`: the *external* `LLMContext` reference itself, supplied
    late via `bind_context()` rather than at construction — T5.2's pipeline
    assembly step doesn't have the slow-brain context built yet at the point
    the filter needs to be wired into `ProducerProcessor(filter=...)`.

    Until `bind_context()` is called, `_current_basis()` returns `""`. This
    is not a test-only special case: `LLMFullResponseStartFrame` records
    `basis = self._current_basis()` and the later `TextFrame` re-reads the
    same method to compare — with no context bound, both calls return `""`
    and the comparison passes on its own, so the unbound state walks the
    same "happy path" branch a real bound-context run would take when the
    question hasn't changed. `test_dual_brain.py` (T3.1, locked) never binds
    a context and exercises exactly this path.
    """

    def __init__(self, context: LLMContext | None = None) -> None:
        self._context = context
        self._state = SlowBrainState(has_material=False, aborted=False, basis="")
        # Log-only correlation counters (design §6.4): `_turn` increments once
        # per `LLMFullResponseStartFrame` (a new slow-brain turn dispatched);
        # `_seq` increments once per accepted material point *within* the
        # current turn, reset to 0 on every dispatch. Neither carries business
        # semantics — they exist solely so a human reading bot.log can tell
        # which log lines belong to the same turn/point.
        self._turn = 0
        self._seq = 0

    def bind_context(self, context: LLMContext) -> None:
        """Bind (or rebind) the real slow-brain `LLMContext` (T3.5, pipeline assembly)."""
        self._context = context

    @property
    def turn(self) -> int:
        """Read-only view of the log-correlation `_turn` counter (design §6.4).

        Lets `bot.py`'s `on_pipeline_error` handler report `slow-failed`
        under the same turn number as this instance's own dispatch/inject/
        no-material/abort lines, instead of keeping an independent counter
        that would drift out of sync with them (组末评审 MEDIUM,2026-08-03)."""
        return self._turn

    def _current_basis(self) -> str:
        """Snapshot of the last `role == "user"` message's `content`, as `str`.

        Returns `""` when no context is bound, or the bound context has no
        `role == "user"` message — never raises (design §5.2's comparison
        must be total, not partial).

        `get_messages()` returns the context's internal list *reference*,
        not a snapshot (`llm_context.py:227-279`) — holding onto it or a
        message dict from it would make every later comparison trivially
        equal regardless of what actually changed. This method walks the
        list and copies the `content` out as a plain `str` immediately, then
        drops the reference; nothing here is ever retained across calls.
        """
        if self._context is None:
            return ""
        for message in reversed(self._context.get_messages()):
            if not isinstance(message, dict) or message.get("role") != "user":
                continue
            content = message.get("content", "")
            return content if isinstance(content, str) else str(content)
        return ""

    async def __call__(self, frame: Frame) -> bool:
        """Design §5.2 predicate frame-routing table — the sole authority.

        Every branch below is an observation/control frame from the
        slow-brain branch's point of view: `LLMFullResponseStartFrame` /
        `LLMFullResponseEndFrame` / `InterruptionFrame` must always return
        `False` (they must never be `_produce`d into the fast-brain branch,
        which would pollute its context) — only a `TextFrame` that clears
        the `not aborted` + `basis`-match check returns `True`.
        """
        if isinstance(frame, LLMFullResponseStartFrame):
            self._turn += 1
            self._seq = 0
            self._state.has_material = False
            self._state.aborted = False
            self._state.basis = self._current_basis()
            logger.info(f"[dual-brain] dispatch turn={self._turn}")
            return False

        if isinstance(frame, TextFrame):
            # `aborted` is checked before the `basis` comparison (design
            # §5.2 row ③: aborted is the primary defense, basis is the
            # defense-in-depth backstop) — so a dropped point during the
            # interruption window is always attributed to `reason=aborted`,
            # never `reason=basis-mismatch`, even if both would fail.
            if self._state.aborted:
                logger.info(f"[dual-brain] stale-drop turn={self._turn} reason=aborted")
                return False
            if self._current_basis() != self._state.basis:
                logger.info(f"[dual-brain] stale-drop turn={self._turn} reason=basis-mismatch")
                return False
            self._seq += 1
            self._state.has_material = True
            logger.info(f"[dual-brain] inject turn={self._turn} seq={self._seq} done=false")
            return True

        if isinstance(frame, LLMFullResponseEndFrame):
            result = (
                self._state.has_material
                and not self._state.aborted
                and self._current_basis() == self._state.basis
            )
            if result:
                logger.info(f"[dual-brain] inject turn={self._turn} seq={self._seq} done=true")
            elif not self._state.has_material:
                # Only the zero-material case gets `no-material` (design
                # §6.4's only row for this frame). A turn that *did* produce
                # material but fails here because of `aborted`/basis drift
                # was already explained by an `abort` or `stale-drop` line
                # at the point the point was dropped — logging `no-material`
                # here too would misreport "nothing was produced" for a turn
                # that, in fact, produced (and already logged) material.
                logger.info(f"[dual-brain] no-material turn={self._turn}")
            return result

        if isinstance(frame, InterruptionFrame):
            self._state.aborted = True
            logger.info(f"[dual-brain] abort turn={self._turn} reason=interruption")
            return False

        return False


# Test-only singleton — do not wire this into a real pipeline (see
# `build_slow_material_filter` below, same rationale as `sentinel.py`'s
# `sentinel_gate`). Mirrors `sentinel.py`'s `sentinel_gate = _SentinelGate()`
# (module-level instance for tests / simple wiring).
slow_material_filter = _SlowMaterialFilter()


def build_slow_material_filter() -> _SlowMaterialFilter:
    """Construct a fresh, session-scoped `_SlowMaterialFilter` (T5.2, pipeline assembly).

    Deliberately does **not** wrap the module-level `slow_material_filter`
    singleton above. `bot(runner_args)` runs once per session (AGENTS.md
    §1), but nothing about the runtime guarantees one OS process per
    session — the same reasoning `sentinel.py`'s `build_sentinel_filter()`
    documents (and the 4th group's end-of-group review already flagged as a
    HIGH for `_SentinelGate`). `_SlowMaterialFilter` carries turn state
    (`_state.has_material`/`_state.aborted`/`_state.basis`) that must not
    leak across sessions sharing a process, so `bot.py::assemble_pipeline`
    calls this once per session to get its own instance, then calls
    `.bind_context(...)` on it once the session's slow-brain `LLMContext`
    exists — the module singleton is reserved for direct unit-test use only.
    """
    return _SlowMaterialFilter()


class _FastAnswerTap(FrameProcessor):
    """Passthrough tap that shadows the fast brain's own text output (B5 修法).

    D-005 根因(`pipeline/debts.md`,原 B5)：快脑自己那句回答要真正写进 `fast_context`，
    依赖 `LLMFullResponseEndFrame` 被 TTS 内部按音频播放顺序释放的队列放行
    ——这个延迟跟回答长度成正比。慢脑"素材已齐"的注入若在这个窗口内触发，
    快脑因看不到自己已经答过，会把问题从头重答一遍。

    这个类插在 `fast_llm` 和 `sentinel_filter`/TTS 之间（`bot.py::
    assemble_pipeline`），直接旁听 `fast_llm` 的原始 `LLMTextFrame` 输出——
    不经过 TTS 那条按播放顺序释放的队列，所以不受播放时长影响。全程只做
    记录，不吞帧、不改帧、不加帧，原样透传下游：不改变任何既有触发时机/
    契约，只新增一个只读旁路组件。

    `last_answer` 在每一轮 `LLMFullResponseEndFrame` 到达时更新为该轮完整
    拼接文本；新一轮 `LLMFullResponseStartFrame` 只清空累积缓冲区，不清空
    `last_answer`——保证任意时刻读到的都是"最近一次已完整落地的回答"，不会
    在下一轮生成过程中被清空成空字符串或半截内容。
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._buffer: list[str] = []
        self.last_answer: str = ""

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, LLMFullResponseStartFrame):
            self._buffer = []
        elif isinstance(frame, LLMTextFrame):
            self._buffer.append(frame.text)
        elif isinstance(frame, LLMFullResponseEndFrame):
            self.last_answer = "".join(self._buffer)

        await self.push_frame(frame, direction)


def build_fast_answer_tap() -> _FastAnswerTap:
    """Construct a fresh, session-scoped `_FastAnswerTap` (B5 修法, pipeline assembly).

    Same session-isolation rationale as `build_sentinel_filter()`
    (`sentinel.py`) / `build_slow_material_filter()` above — every call
    returns a brand-new instance, so concurrent sessions never share
    `last_answer` state.
    """
    return _FastAnswerTap()


class _SlowMaterialTransformer:
    """Stateful Producer `transformer` for the slow-brain branch (T3.4, design §6.1; B5 修法新增绑定).

    `ProducerProcessor._produce()` calls `transformer` with a single `Frame`
    and awaits a single `Frame` back (`producer_processor.py`: `transformer:
    Callable[[Frame], Awaitable[Frame]]`, invoked once per consumer as
    `new_frame = await self._transformer(frame)`) — no batching, no list
    shape. A class instance with `__call__` satisfies this same callable
    shape as the original plain function did (same trick as
    `_SlowMaterialFilter`/`slow_material_filter` above).

    This only ever sees frames `slow_material_filter` has already let
    through (`True`), which design §5.2's routing table limits to two cases:

    - `TextFrame` (an incremental material point): wrap it as the
      "in-progress" injection using `INJECT_POINT_TEMPLATE`, `run_llm=False`
      — it must not trigger a fast-brain generation by itself (design §6.1).
    - `LLMFullResponseEndFrame` (the turn's completion marker, only produced
      when `has_material and not aborted and basis` still matches): `run_llm=True`
      — this is the one that lets the fast brain fold the material in. The
      text itself is `INJECT_DONE_TEMPLATE` when no `_FastAnswerTap` is bound
      or its `last_answer` is empty (identical to the pre-B5 behavior, so
      T3.1's locked assertions keep passing unchanged); when a tap is bound
      *and* has content, it switches to `INJECT_DONE_WITH_REMINDER_TEMPLATE`
      so the fast brain can see what it already said before deciding whether
      to add more (B5 修法).

    No other frame type can reach here under the current filter, so there is
    no third branch to write; a silent fallback would mask a real filter/
    transformer contract mismatch instead of surfacing it, so an unexpected
    frame type raises rather than being coerced into one of the two known
    shapes.
    """

    def __init__(self, tap: _FastAnswerTap | None = None) -> None:
        self._tap = tap

    def bind_tap(self, tap: _FastAnswerTap) -> None:
        """Bind (or rebind) a `_FastAnswerTap` instance (B5 修法, pipeline assembly)."""
        self._tap = tap

    async def __call__(self, frame: Frame) -> Frame:
        if isinstance(frame, TextFrame):
            content = INJECT_POINT_TEMPLATE.format(point=frame.text.strip())
            run_llm = False
        elif isinstance(frame, LLMFullResponseEndFrame):
            if self._tap is not None and self._tap.last_answer:
                content = INJECT_DONE_WITH_REMINDER_TEMPLATE.format(
                    answer=self._tap.last_answer
                )
            else:
                content = INJECT_DONE_TEMPLATE
            run_llm = True
        else:
            raise TypeError(
                f"slow_material_transformer received an unexpected frame type: "
                f"{type(frame).__name__} (filter should only pass TextFrame or "
                "LLMFullResponseEndFrame)"
            )

        return LLMMessagesAppendFrame(
            messages=[{"role": "user", "content": content}],
            run_llm=run_llm,
        )


# Test-only singleton — same rationale as `slow_material_filter` above.
# Unbound (`tap=None`), so its behavior is byte-for-byte identical to the
# pre-B5 plain-function version: existing T3.1 tests keep passing unchanged.
slow_material_transformer = _SlowMaterialTransformer()


def build_slow_material_transformer(
    tap: _FastAnswerTap | None = None,
) -> _SlowMaterialTransformer:
    """Construct a fresh, session-scoped `_SlowMaterialTransformer` (B5 修法, pipeline assembly).

    Same session-isolation rationale as `build_slow_material_filter()` above.
    """
    return _SlowMaterialTransformer(tap=tap)
