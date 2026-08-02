"""Sentinel gate for the fast/slow-brain feature.

When the fast brain judges that a turn has nothing to add, it is instructed
to emit a single sentinel character (`∅`, U+2205) and nothing else. This
module mutes every `LLMTextFrame` of a turn whose first text frame starts
with the sentinel character, so the turn is never spoken by TTS.

**Production callers (T5.2 pipeline assembly) must use `build_sentinel_filter()`**
— it returns a fresh `FunctionFilter` backed by its own gate instance, so
concurrent sessions in the same process never share mute/turn state. The
module-level `sentinel_gate` singleton below is kept only so T4.1's unit
tests can exercise the predicate directly; it must not be wired into a real
pipeline or shared across sessions (see `build_sentinel_filter`'s docstring
for why).

See `openspec/changes/fast-slow-brain/design.md` §6.6 (sentinel contract)
and §6.4 (structured log-line contract, `sentinel-muted` row) for the full
rationale, including why control frames (`LLMFullResponseStartFrame` /
`LLMFullResponseEndFrame`) must always pass through unmuted.
"""

from loguru import logger
from pipecat.frames.frames import Frame, LLMFullResponseStartFrame, LLMTextFrame
from pipecat.processors.filters.function_filter import FunctionFilter

SENTINEL_CHAR = "∅"


class _SentinelGate:
    """Stateful predicate: `async (Frame) -> bool` for `FunctionFilter`.

    State resets on every `LLMFullResponseStartFrame` (turn boundary). The
    first `LLMTextFrame` seen after a reset decides the turn: if its
    stripped text starts with the sentinel character, every subsequent
    `LLMTextFrame` in that turn is muted (returns False). Every other frame
    type — including the `LLMFullResponseStartFrame`/`LLMFullResponseEndFrame`
    control frames themselves — always passes through (returns True); only
    `LLMTextFrame` is ever subject to muting (design §6.6).
    """

    def __init__(self) -> None:
        self._turn = 0
        self._seen_first_text_frame = False
        self._muted = False

    async def __call__(self, frame: Frame) -> bool:
        if isinstance(frame, LLMFullResponseStartFrame):
            self._turn += 1
            self._seen_first_text_frame = False
            self._muted = False
            return True

        if not isinstance(frame, LLMTextFrame):
            return True

        if not self._seen_first_text_frame:
            self._seen_first_text_frame = True
            self._muted = frame.text.strip().startswith(SENTINEL_CHAR)
            if self._muted:
                logger.info(f"[dual-brain] sentinel-muted turn={self._turn}")

        return not self._muted


# Test-only singleton — do not wire this into a real pipeline (see the
# module docstring and `build_sentinel_filter` below). `sentinel_gate` is a
# stateful callable instance, not a plain function, since the predicate must
# remember state across calls. Safe to reuse across scenarios within a
# single test because it resets its own state on every
# `LLMFullResponseStartFrame`, not because of any process/test isolation.
sentinel_gate = _SentinelGate()


def build_sentinel_filter() -> FunctionFilter:
    """Construct a fresh, session-scoped `FunctionFilter` around a sentinel gate.

    T4.3 (design §6.6): this is the constructor the pipeline assembly step
    (T5.2) calls to wire the sentinel gate into `ParallelPipeline`.

    Deliberately does **not** wrap the module-level `sentinel_gate` singleton.
    `bot(runner_args)` runs once per session (AGENTS.md §1), but nothing
    about the runtime guarantees one OS process per session — the eval
    harness explicitly keeps a single booted bot process alive across many
    scenario runs ("the eval transport keeps the bot alive between runs, so
    boot it once and drive scenario after scenario", AGENTS.md §6), and nothing
    in `WorkerRunner`/`PipelineWorker` (`bot.py`) rules out multiple concurrent
    sessions sharing a process in the future. `_SentinelGate` carries turn
    state (`_turn`/`_seen_first_text_frame`/`_muted`) that must not leak
    across sessions, so each call here builds a brand-new `_SentinelGate`
    instance — state isolation holds regardless of the process model, and
    callers never need to remember a "one filter per session" convention.
    """
    return FunctionFilter(filter=_SentinelGate())
