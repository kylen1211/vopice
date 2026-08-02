"""Tests for `sentinel.build_sentinel_filter` (T4.3, fast-slow-brain design §6.6).

A separate file from `test_sentinel.py` on purpose: the task card for T4.3
forbids modifying `test_sentinel.py` (T4.1's file), so the new constructor
gets its own independent test module rather than a new test function
squeezed into the existing one.

Same collection-safety pattern as `test_sentinel.py` (先红证据口径): if
`sentinel.py` doesn't define `build_sentinel_filter` yet, `hasattr` turns
that into an assertion failure instead of an import-time collection error.

Contract under test (design §6.6, task card T4.3): `build_sentinel_filter()`
returns a `FunctionFilter(filter=...)` wrapping a **fresh** `_SentinelGate`
on every call — never the module-level `sentinel.sentinel_gate` singleton —
so concurrent/successive sessions never share sentinel turn-state.
"""

import unittest

try:
    import sentinel
except ModuleNotFoundError:
    sentinel = None

from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.processors.filters.function_filter import FunctionFilter
from pipecat.tests.utils import run_test


class TestBuildSentinelFilter(unittest.IsolatedAsyncioTestCase):
    """`build_sentinel_filter()` construction and state-isolation checks."""

    def _assert_build_sentinel_filter_ready(self):
        self.assertIsNotNone(sentinel, "sentinel 模块尚未定义")
        self.assertTrue(
            hasattr(sentinel, "build_sentinel_filter"),
            "build_sentinel_filter 尚未定义",
        )

    def test_returns_function_filter_instance(self):
        """Return type must be the official `FunctionFilter`, not a hand-rolled filter."""
        self._assert_build_sentinel_filter_ready()
        assert sentinel is not None  # pyright narrowing; runtime already asserted above

        built = sentinel.build_sentinel_filter()

        self.assertIsInstance(built, FunctionFilter)

    def test_each_call_wraps_a_fresh_gate_not_the_singleton(self):
        """Two calls must return distinct `FunctionFilter`s wrapping distinct
        gate callables, and neither gate may be the module-level singleton
        (`sentinel.sentinel_gate`) — otherwise concurrent sessions in the
        same process would share turn state.
        """
        self._assert_build_sentinel_filter_ready()
        assert sentinel is not None  # pyright narrowing; runtime already asserted above

        filter_a = sentinel.build_sentinel_filter()
        filter_b = sentinel.build_sentinel_filter()

        self.assertIsNot(filter_a, filter_b, "两次调用应返回不同的 FunctionFilter 实例")
        self.assertIsNot(
            filter_a._filter, filter_b._filter, "两个 filter 的哨兵谓词应是不同实例(状态隔离)"
        )
        self.assertIsNot(
            filter_a._filter,
            sentinel.sentinel_gate,
            "不应复用模块级单例 sentinel_gate,否则跨会话状态会互相污染",
        )
        self.assertIsNot(
            filter_b._filter,
            sentinel.sentinel_gate,
            "不应复用模块级单例 sentinel_gate,否则跨会话状态会互相污染",
        )

    async def test_two_built_filters_do_not_share_mute_state(self):
        """Behavioral proof: muting one built filter's turn must not mute
        the other built filter's independent turn (frame-level, via the
        official `run_test` harness — same pattern as `test_sentinel.py`).
        """
        self._assert_build_sentinel_filter_ready()
        assert sentinel is not None  # pyright narrowing; runtime already asserted above

        filter_a = sentinel.build_sentinel_filter()
        filter_b = sentinel.build_sentinel_filter()

        # filter_a enters a sentinel (muted) turn.
        (received_a, _) = await run_test(
            filter_a,
            frames_to_send=[
                LLMFullResponseStartFrame(),
                LLMTextFrame(text="∅"),
                LLMTextFrame(text="不该被朗读"),
                LLMFullResponseEndFrame(),
            ],
        )
        text_frames_a = [f for f in received_a if isinstance(f, LLMTextFrame)]
        self.assertEqual(len(text_frames_a), 0, "filter_a 的哨兵轮应静默全部文本帧")

        # filter_b runs a normal (unmuted) turn — must be unaffected by filter_a.
        (received_b, _) = await run_test(
            filter_b,
            frames_to_send=[
                LLMFullResponseStartFrame(),
                LLMTextFrame(text="你好"),
                LLMFullResponseEndFrame(),
            ],
        )
        text_frames_b = [f for f in received_b if isinstance(f, LLMTextFrame)]
        self.assertEqual(
            [f.text for f in text_frames_b],
            ["你好"],
            "filter_b 应有独立状态,不受 filter_a 静默态影响",
        )


if __name__ == "__main__":
    unittest.main()
