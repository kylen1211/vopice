"""Slow-brain turn state for the fast/slow-brain feature (design §5.2).

`SlowBrainState` is pure data — three fields plus the three judgments they
back — with no scheduling logic and no state-transition graph of its own
(design §5.2 table: "纯数据 + 三个判定,无调度、无状态迁移图"). The
transitions (when each field resets/flips) live in `slow_material_filter`
(T3.3) and `slow_material_transformer` (T3.4), not here.
"""

from dataclasses import dataclass

from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMMessagesAppendFrame,
    TextFrame,
)
from pipecat.processors.aggregators.llm_context import LLMContext

from prompts import INJECT_DONE_TEMPLATE, INJECT_POINT_TEMPLATE


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

    def bind_context(self, context: LLMContext) -> None:
        """Bind (or rebind) the real slow-brain `LLMContext` (T3.5, pipeline assembly)."""
        self._context = context

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
            self._state.has_material = False
            self._state.aborted = False
            self._state.basis = self._current_basis()
            return False

        if isinstance(frame, TextFrame):
            if self._state.aborted or self._current_basis() != self._state.basis:
                return False
            self._state.has_material = True
            return True

        if isinstance(frame, LLMFullResponseEndFrame):
            return (
                self._state.has_material
                and not self._state.aborted
                and self._current_basis() == self._state.basis
            )

        if isinstance(frame, InterruptionFrame):
            self._state.aborted = True
            return False

        return False


# Module-level singleton so `dual_brain.slow_material_filter` is directly
# usable as `ProducerProcessor(filter=dual_brain.slow_material_filter, ...)`
# — mirrors `sentinel.py`'s `sentinel_gate = _SentinelGate()` (module-level
# instance for tests / simple wiring). T5.2's real pipeline-assembly step
# calls `slow_material_filter.bind_context(...)` once the slow-brain
# `LLMContext` exists; a session-scoped factory (mirroring `sentinel.py`'s
# `build_sentinel_filter()`) is that task's concern, not this one's.
slow_material_filter = _SlowMaterialFilter()


async def slow_material_transformer(frame: Frame) -> Frame:
    """Producer `transformer` for the slow-brain branch (T3.4, design §6.1).

    `ProducerProcessor._produce()` calls `transformer` with a single `Frame`
    and awaits a single `Frame` back (`producer_processor.py`: `transformer:
    Callable[[Frame], Awaitable[Frame]]`, invoked once per consumer as
    `new_frame = await self._transformer(frame)`) — no batching, no list
    shape. This function only ever sees frames `slow_material_filter` has
    already let through (`True`), which design §5.2's routing table limits
    to two cases:

    - `TextFrame` (an incremental material point): wrap it as the
      "in-progress" injection using `INJECT_POINT_TEMPLATE`, `run_llm=False`
      — it must not trigger a fast-brain generation by itself (design §6.1).
    - `LLMFullResponseEndFrame` (the turn's completion marker, only produced
      when `has_material and not aborted and basis` still matches): the
      fixed, already-complete `INJECT_DONE_TEMPLATE` text, `run_llm=True` —
      this is the one that lets the fast brain fold the material in.

    No other frame type can reach here under the current filter, so there is
    no third branch to write; a silent fallback would mask a real filter/
    transformer contract mismatch instead of surfacing it, so an unexpected
    frame type raises rather than being coerced into one of the two known
    shapes.
    """
    if isinstance(frame, TextFrame):
        content = INJECT_POINT_TEMPLATE.format(point=frame.text.strip())
        run_llm = False
    elif isinstance(frame, LLMFullResponseEndFrame):
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
