"""Unit tests for the STT/TTS provider builder assembly in server/bot.py (T1.4b / U4).

U4 目的：固化"构造后 settings 真的生效"（design §8.2；旧库 B19 就是在这里静默失效）——
断言 STT_BUILDERS/TTS_BUILDERS 用给定 Config 构造出的 service 实例，其
`_settings.language_hints` / `_settings.voice` 确实等于配置里传入的期望值。

放在 test_bot.py 而非 test_dual_brain.py（design §8.2 原稿写的落点）：
test_dual_brain.py 要到第 3 组才创建，本任务提前建它会跟第 3 组"先写测试"步骤冲突；
test_bot.py 测的是 bot.py 里的装配逻辑（builder 字典 + Config → service 实例），
与 test_config.py 测 config.py 的校验逻辑职责边界清楚，故新建本文件。

导入 bot 模块的隔离处理：bot.py 顶层直接执行 `load_dotenv(override=True)` +
`cfg = load_config()`——import bot 这一行本身就会读取真实环境变量甚至真实 .env
文件。为了不依赖 server/.env 是否存在、也不依赖真实环境变量，改用 `bot_module`
fixture（T5.1 起移至 `conftest.py` 复用，见其文档字符串）：
1. 用 monkeypatch.setenv 注入一组自造的必需环境变量（值全是测试专用假数据）；
2. 用 monkeypatch 把 dotenv.load_dotenv 替换成 no-op，阻止它加载/覆盖真实 .env；
3. 强制重新 import（若 bot 已被其它测试文件 import 过则先从 sys.modules 移除），
   保证上面两条 patch 在 bot.py 顶层代码执行时生效。

拿到 bot 模块后，测试本身**不使用模块级的 bot.cfg**——直接构造一个手工 Config
实例传给 STT_BUILDERS["soniox"] / TTS_BUILDERS["elevenlabs"]，断言构造出的
service 的 `_settings` 上关键字段确实等于我们传入的期望值。这样断言完全不依赖
模块级全局状态或 import 时机，比"断言 bot.cfg 的字段"更干净、更隔离。
"""


def _make_config(**overrides):
    """Hand-built Config, independent of bot.py's module-level `cfg`.

    scenario-assembly T-3(修订 R2 白名单第 4 条)：`Config` 新增了
    `template`/`fast_llm_model`/`dual_brain_enabled` 三个必需字段（T-2），
    这里补上缺省默认值——`template` 用注册表的 `voice_chat`（唯一数据源
    `scenarios.TEMPLATES`，不手工构造 `ScenarioTemplate` 绕过它），
    `fast_llm_model` 缺省同 `llm_model`，`dual_brain_enabled` 缺省关闭，均
    只是"让手工 Config 能构造出来"的默认值，不代表任何断言依据。
    """
    from config import Config
    from scenarios import TEMPLATES

    base = dict(
        llm_base_url="http://127.0.0.1:8045/v1",
        llm_api_key="sk-test",
        llm_model="gemini-3.6-flash-high",
        fast_llm_model="gemini-3.6-flash-high",
        dual_brain_enabled=False,
        template=TEMPLATES["voice_chat"],
        slow_llm_model="gemini-3-pro",
        stt_api_key="soniox-test",
        tts_api_key="elevenlabs-test",
        tts_voice="expected-voice-id",
        tts_model="eleven_flash_v2_5",
        stt_model="stt-rt-v5",
        openclaw_agent_id="dev",
    )
    base.update(overrides)
    return Config(**base)


def test_stt_builder_sets_language_hints_to_zh(bot_module):
    """U4: SonioxSTTService 构造后 _settings.language_hints 含 Language.ZH。"""
    from pipecat.transcriptions.language import Language

    config = _make_config()
    stt = bot_module.STT_BUILDERS["soniox"](config)

    assert stt._settings.language_hints == [Language.ZH]


def test_tts_builder_sets_voice_from_config(bot_module):
    """U4: ElevenLabsTTSService 构造后 _settings.voice 等于配置传入的 voice id。"""
    config = _make_config(tts_voice="my-expected-voice-id")
    tts = bot_module.TTS_BUILDERS["elevenlabs"](config)

    assert tts._settings.voice == "my-expected-voice-id"


# 2026-08-03 补：deepgram/cartesia 备用厂商构造器此前零测试覆盖（先红证据纪律
# 缺口，见全局台账 voice-agent-fix-tts-zh-and-llm-repeat-20260803）。断言风格
# 同上——只查 `_settings` 上的关键字段，不断言 api_key（沿用既有 soniox/
# elevenlabs 用例的做法）。同时验证走的是 Config 通用字段（stt_api_key/
# tts_api_key/tts_voice），而不是裸 os.environ 读取。


def test_deepgram_stt_builder_sets_language_and_smart_format(bot_module):
    """U4 同构：DeepgramSTTService 构造后 _settings.language/_settings.smart_format
    确实等于 bot.py 里写死的期望值（zh + smart_format=True）。"""
    from pipecat.transcriptions.language import Language

    config = _make_config(stt_api_key="deepgram-test-key")
    stt = bot_module.STT_BUILDERS["deepgram"](config)

    assert stt._settings.language == Language.ZH
    assert stt._settings.smart_format is True


def test_cartesia_tts_builder_sets_voice_and_language_from_config(bot_module):
    """U4 同构：CartesiaTTSService 构造后 _settings.voice 等于配置传入的
    tts_voice（走 Config 通用字段，不是裸 os.environ["CARTESIA_VOICE_ID"]）。"""
    from pipecat.transcriptions.language import Language

    config = _make_config(tts_api_key="cartesia-test-key", tts_voice="cartesia-voice-id")
    tts = bot_module.TTS_BUILDERS["cartesia"](config)

    assert tts._settings.voice == "cartesia-voice-id"
    assert tts._settings.language == Language.ZH


# scenario-assembly T-3(契约 §0.3 B-1…B-4 / SA-23，修订 R2)：english_tutor
# 模板专用的 assemblyai STT builder——逐条钉死四条硬约束，防止有人"照抄邻居"
# 把 soniox/deepgram 的 Language.ZH 硬锁抄回来（那正是本轮引入它要解决的
# 问题，见 bot.py::_build_assemblyai_stt 注释）。


def test_assemblyai_stt_builder_sets_universal_model_with_no_language_lock(bot_module):
    """SA-23：`_settings.model` 必须是 universal-3-5-pro（B-3，不读
    c.stt_model——它默认值是 Soniox 档位名，混用会连接失败）；
    `_settings.language_code`/`_settings.language_detection` 必须均为
    `None`（B-2，不传任何语言参数，靠模型原生 code-switch）；构造出的
    WebSocket URL 查询串不含任何 language 相关参数（B-2 的运行期证据，防止
    "Settings 上没设但别处偷偷拼进 URL"这类绕过）；`vad_force_turn_endpoint`
    必须是 `True`（B-4，轮次仍由本仓 VADProcessor/UserTurnProcessor 段驱动）。
    """
    config = _make_config(stt_api_key="assemblyai-test-key")
    stt = bot_module.STT_BUILDERS["assemblyai"](config)

    assert stt._settings.model == "universal-3-5-pro"
    assert stt._settings.language_code is None
    assert stt._settings.language_detection is None

    ws_url = stt._build_ws_url()
    query = ws_url.split("?", 1)[1] if "?" in ws_url else ""
    assert "language" not in query, f"WS URL 查询串不得含任何 language 参数，实际: {query!r}"

    assert stt._vad_force_turn_endpoint is True
