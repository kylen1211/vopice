# voice-agent · Backlog

已知限制与待办事项,按发现时间倒序排列。

## B1 · 断开重连失败(客户端 SDK 层)

- **现象**:WebRTC 连接断开后,在同一页面再次点击连接,`POST /start` 正常返回 200,但客户端不再发起
  `/sessions/{id}/api/offer` 请求,连接卡死(浏览器控制台无报错)。
- **范围判断**:`client/` 基本是官方 `@pipecat-ai/voice-ui-kit` + `client-js`/`client-react` 脚手架,
  未见自定义连接状态管理代码——判断是上游客户端 SDK 断开后状态未清理干净导致,不是本项目 server 端
  代码问题。
- **临时规避**:刷新页面(而非用页面内"断开重连")。
- **裁决**:2026-08-01 dogfood 排障期间用户裁决暂不深挖客户端 SDK 源码,记 backlog。

## B2 · TTS 多句应答偶发卡死/重叠——根因已定位,暂不修

- **现象**:一轮回复被拆成多句 TTS 分别合成时,播放偶发卡死(状态停在"说话中"但实际没声音,需手动打断才能
  解开)或音频重叠。归档变更 `openspec/changes/archive/2026-08-01-pipecat-native-p1`(voice-translate-v2
  仓库)tasks.md 2.3 / 4.4"新发现 1"最早记录的是"重叠",20260801-02 dogfood 期间新发现同一根因还会导致
  "彻底卡死不出声"这种更严重的表现。
- **根因(已用 venv 内实际运行的 `pipecat-ai` 1.6.0 源码 + 实测数据核实,非猜测)**:
  `pipecat/services/tts_service.py` 的 `TTSService.__init__` 有个 `stop_frame_timeout_s: float = 3.0`
  参数——`_handle_audio_context` 用 `asyncio.wait_for(queue.get(), timeout=self._stop_frame_timeout_s)`
  等下一段音频,超时就判定"这个 context 播完了"、提前发 `TTSStoppedFrame` 并清理 context;本机 Kokoro 是
  纯 CPU 跑 onnxruntime(无 GPU,R6 阶段"零 GPU 关键路径"设计选择),实测合成速度约 50~65ms/汉字,长句
  (如 68 字)TTFB 能到 3.25s——踩线超过这个 3.0s 默认值,导致提前清理,随后迟到的音频只能 `recreate` 同
  一个 context_id 追加,播放衔接就容易出问题。
- **修法(已验证可行,只是选择先不动)**:`KokoroTTSService`/`_ZhFixedKokoroTTSService` 构造时把
  `stop_frame_timeout_s` 显式调大(如 8~10s)即可——该参数经 `**kwargs` 透传给 `TTSService.__init__`,不
  影响正常收尾判定(正常收尾走显式信号,3s 超时只是没收到显式信号时的兜底),只在本机慢速 CPU 合成长句
  的场景下才会触发。
- **裁决**:2026-08-02 用户裁决记录根因即可,暂不改代码。

## B3 · `server/bot.py` 模块顶层副作用逼测试用 `sys.modules` 手法绕过——建议后续重构

- **现象**:`bot.py` 顶层直接跑 `load_dotenv(override=True)` + `cfg = load_config()`(官方脚手架既定结构),
  任何 `import bot` 都会立刻读取真实环境变量。`server/tests/test_bot.py` 的 `bot_module` fixture 为了在
  不依赖真实 `.env`/环境变量的前提下测 `STT_BUILDERS`/`TTS_BUILDERS`,只能 `monkeypatch.setattr(dotenv,
  "load_dotenv", ...)` + `sys.modules.pop("bot"/"config", None)` 再强制 `importlib.import_module("bot")`。
- **风险**:`sys.modules` 是进程级全局状态操作,依赖 fixture teardown/setup 隐式顺序不出错;若未来引入
  `pytest-xdist` 并行,或其他测试文件也 `import bot`/`import config` 并假设单例语义,可能产生跨测试污染。
  当前(fast-slow-brain 第 1 组,2026-08-02)单文件场景下逻辑已核对正确、测试通过,但手法本身脆弱。
- **根因**:副作用放在模块顶层而非函数内,是官方脚手架产物,不在本组任务卡改动范围内。
- **修法方向(暂不做)**:把 `cfg = load_config()` 挪进 `bot()`/`run_bot()` 函数体或做成惰性单例,届时可去掉
  `test_bot.py` 里的 `sys.modules` 手法,换成更干净的依赖注入测试写法。
- **裁决**:2026-08-02 第 1 组组末双裁决(security-reviewer 视角)MEDIUM 发现,判定不阻塞本组验收,记
  backlog 供后续重构 `bot.py` 顶层结构时一并处理。
