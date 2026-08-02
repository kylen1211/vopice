"""Sentinel gate for the fast/slow-brain feature.

When the fast brain judges that a turn has nothing to add, it is instructed
to emit a single sentinel character (`∅`, U+2205) and nothing else. This
module provides the `sentinel_gate` predicate — used as
`FunctionFilter(filter=sentinel_gate)` — that mutes every `LLMTextFrame` of
a turn whose first text frame starts with the sentinel character, so the
turn is never spoken by TTS.

See `openspec/changes/fast-slow-brain/design.md` §6.6 (sentinel contract)
and §6.4 (structured log-line contract, `sentinel-muted` row) for the full
rationale, including why control frames (`LLMFullResponseStartFrame` /
`LLMFullResponseEndFrame`) must always pass through unmuted.
"""

from loguru import logger
from pipecat.frames.frames import Frame, LLMFullResponseStartFrame, LLMTextFrame

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


# Module-level singleton so `FunctionFilter(filter=sentinel.sentinel_gate)`
# works directly — `sentinel_gate` is a stateful callable instance, not a
# plain function, since the predicate must remember state across calls.
sentinel_gate = _SentinelGate()
