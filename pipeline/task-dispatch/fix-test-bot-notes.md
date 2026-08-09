# fix-test-bot-notes.md

## 背景

task-dispatch 变更给 `server/config.py` 的 `Config` dataclass 新增了必需字段
`openclaw_agent_id`（无默认值）。`server/tests/test_bot.py` 顶部的
`_make_config(**overrides)` 辅助函数构造 `Config` 时用的 `base` 字典未同步该字段，
导致 4 条测试用例 `TypeError`。

（记忆闭环 recall 命中：T-5 装配时曾同步过 `conftest.py::bot_module` fixture 的
`_FAKE_REQUIRED_ENV`，但 `test_bot.py` 自己的 `_make_config` 是独立于该 fixture
的手工构造路径，未被那次同步覆盖——本次是补齐这处遗漏。）

## 修复

只改一处：`server/tests/test_bot.py` 的 `_make_config()` 函数体内 `base` 字典
新增一行 `openclaw_agent_id="dev"`。不改测试断言逻辑，不碰其他文件。

## RED（改前）

命令：
```
NLTK_DISABLE_IMPORT_SECURITY=1 .venv/bin/python -m pytest tests/test_bot.py -q
```

输出（尾部摘要）：
```
FAILED tests/test_bot.py::test_stt_builder_sets_language_hints_to_zh - TypeError: Config.__init__() missing 1 required positional argument: 'openclaw_agent_id'
FAILED tests/test_bot.py::test_tts_builder_sets_voice_from_config - TypeError: Config.__init__() missing 1 required positional argument: 'openclaw_agent_id'
FAILED tests/test_bot.py::test_deepgram_stt_builder_sets_language_and_smart_format - TypeError: Config.__init__() missing 1 required positional argument: 'openclaw_agent_id'
FAILED tests/test_bot.py::test_cartesia_tts_builder_sets_voice_and_language_from_config - TypeError: Config.__init__() missing 1 required positional argument: 'openclaw_agent_id'
4 failed, 10 warnings in 1.59s
```

确认与任务描述一致：4 条测试均因同一处 `TypeError: Config.__init__() missing 1
required positional argument: 'openclaw_agent_id'` 失败，失败位置均指向
`tests/test_bot.py:44` 的 `return Config(**base)`。

## 变更

`server/tests/test_bot.py` 的 `_make_config()` 函数，`base` 字典新增一行：
```python
openclaw_agent_id="dev",
```

## GREEN（改后，仅 test_bot.py）

命令：
```
cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 .venv/bin/python -m pytest tests/test_bot.py -q
```

输出：
```
....                                                                     [100%]
=============================== warnings summary ===============================
（省略 10 条 DeprecationWarning，均为 pipecat/websockets 库自身警告，与本次改动无关）
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
4 passed, 10 warnings in 1.58s
```

4 条目标测试全绿：
- test_stt_builder_sets_language_hints_to_zh
- test_tts_builder_sets_voice_from_config
- test_deepgram_stt_builder_sets_language_and_smart_format
- test_cartesia_tts_builder_sets_voice_and_language_from_config

## 全量回归

命令：
```
cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 .venv/bin/python -m pytest tests/ -q
```

输出（尾部）：
```
63 passed, 37 warnings in 5.05s
EXIT_CODE=0
```

整个 `tests/` 目录 63 条全部通过，退出码 0，无 failed/error。

## git diff

```
diff --git a/server/tests/test_bot.py b/server/tests/test_bot.py
index ea8d6fa..685e865 100644
--- a/server/tests/test_bot.py
+++ b/server/tests/test_bot.py
@@ -39,6 +39,7 @@ def _make_config(**overrides):
         tts_voice="expected-voice-id",
         tts_model="eleven_flash_v2_5",
         stt_model="stt-rt-v5",
+        openclaw_agent_id="dev",
     )
     base.update(overrides)
     return Config(**base)
```

确认：仅此一处改动，未涉及其他文件、未改测试断言逻辑本身。

## commit

- message: `fix: sync test_bot.py::_make_config with required openclaw_agent_id field`
- SHA: `ec547f334bca02defa3ac6f0fa0452d9f81f2af8`
- 分支：`fix/tts-zh-and-llm-repeat`
