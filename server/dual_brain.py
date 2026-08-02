"""Slow-brain turn state for the fast/slow-brain feature (design §5.2).

`SlowBrainState` is pure data — three fields plus the three judgments they
back — with no scheduling logic and no state-transition graph of its own
(design §5.2 table: "纯数据 + 三个判定,无调度、无状态迁移图"). The
transitions (when each field resets/flips) live in `slow_material_filter`
(T3.3) and `slow_material_transformer` (T3.4), not here.
"""

from dataclasses import dataclass


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
