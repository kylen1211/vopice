"""Shared pytest fixtures for server/tests.

`bot_module` (moved here from `test_bot.py` during T5.1, fast-slow-brain
design §8.2 U3/U5): several test files need to `import bot` under a fully
isolated fake env — `test_bot.py` (U4, group 1) and `test_dual_brain.py`
(U3/U5, group 5) both need it, so it lives here once instead of being
duplicated per file.
"""

import importlib
import sys

import pytest

# bot.py 顶层强制读取的必需环境变量（值本身是任意测试假数据——依赖这些值的
# 断言各自在测试文件内用 `_make_config`/`bot_module.cfg` 表达，这里只保证
# `import bot` 顶层的 `load_config()` 能通过校验）。
_FAKE_REQUIRED_ENV = {
    "LLM_BASE_URL": "http://127.0.0.1:8045/v1",
    "LLM_API_KEY": "sk-test-key",
    "LLM_MODEL": "gemini-3.6-flash-high",
    "SLOW_LLM_MODEL": "gemini-3-pro",
    "SONIOX_API_KEY": "soniox-test-key",
    "ELEVENLABS_API_KEY": "elevenlabs-test-key",
    "ELEVENLABS_VOICE_ID": "voice-test-id",
    "ELEVENLABS_MODEL": "eleven_multilingual_v2",
}


@pytest.fixture
def bot_module(monkeypatch):
    """Import (or re-import) server/bot.py under a fully isolated fake env.

    - Sets all required env vars to test-only fake values (load_config() at
      module scope must succeed).
    - Neutralizes dotenv.load_dotenv so bot.py's `load_dotenv(override=True)`
      cannot pull in a real server/.env and override the fake values above.
    - Drops any cached `bot`/`config` modules first so the patches above are
      guaranteed to be in effect while bot.py's top-level code re-executes.
    """
    for key, value in _FAKE_REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)

    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)

    sys.modules.pop("bot", None)
    sys.modules.pop("config", None)
    module = importlib.import_module("bot")
    yield module
    sys.modules.pop("bot", None)
    sys.modules.pop("config", None)
