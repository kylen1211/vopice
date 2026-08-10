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
    # scenario-assembly M-1：SLOW_LLM_MODEL 已从"恒定必需"改为"仅
    # DUAL_BRAIN_ENABLED=true 时必需"；这里继续给它一个假值不报错（关闭态下
    # 留着该行"不报错、不使用"是明文兼容行为），default bot_module 走关闭态
    # 也不受影响。
    "SLOW_LLM_MODEL": "gemini-3-pro",
    # task-dispatch (C4 派活) T-5 新增必需项（server/config.py §0.6）——T-6 交接缝隙
    # 修复：T-5 加了这一项但当时未同步这里，主会话核实后追加授权本卡补齐。
    "OPENCLAW_AGENT_ID": "dev",
    "SONIOX_API_KEY": "soniox-test-key",
    "ELEVENLABS_API_KEY": "elevenlabs-test-key",
    "ELEVENLABS_VOICE_ID": "voice-test-id",
    "ELEVENLABS_MODEL": "eleven_multilingual_v2",
    # scenario-assembly M-6（修订 R2）：SCENARIO=english_tutor 的用例（T-3/T-4）
    # 走 `import bot` 会在顶层 `load_config()` 校验 assemblyai 的必需 key——
    # 默认 SCENARIO=voice_chat 不选中它时这项不生效，提前给假值不影响现状。
    "ASSEMBLYAI_API_KEY": "assemblyai-test-key",
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


@pytest.fixture
def bot_module_dual_brain(monkeypatch):
    """Same as `bot_module`, but with the dual-brain switch turned on
    (scenario-assembly ADR-6 open-state).

    T-3/T-4 consumption contract (fixture name and this behavior are fixed
    once defined here, per the scenario-assembly T-2 task card — do not
    rename): several tests need `import bot` under a fully isolated fake env
    with `DUAL_BRAIN_ENABLED=true`, so this lives in conftest.py once
    instead of being duplicated per file, mirroring `bot_module` above.
    """
    for key, value in _FAKE_REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("DUAL_BRAIN_ENABLED", "true")
    monkeypatch.setenv("SLOW_LLM_MODEL", "gemini-3-pro")

    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)

    sys.modules.pop("bot", None)
    sys.modules.pop("config", None)
    module = importlib.import_module("bot")
    yield module
    sys.modules.pop("bot", None)
    sys.modules.pop("config", None)
