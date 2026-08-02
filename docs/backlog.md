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

## B4 · 连续追问场景下慢脑会"跑偏"分析最早话题而非当前话题——已批准契约(§5.2/§6.7①)存在缺口

- **现象**:fast-slow-brain 第 7 组 eval 实跑(`dual_brain_interrupt.yaml`/`dual_brain_supersede.yaml`,
  2026-08-03)两次独立复现:深问题(CAP 定理)→ 追问(供 R5-S1 用的一个简单问题 / 供 R7-S1 用的另一个
  同样有深度的问题——区块链原理)之后,慢脑在**追问自己触发的那一轮新分发**里,产出的材料仍是关于
  **CAP 定理**的内容(区块链场景里日志判据字面写的是"该回复明显还在讨论 CAP 定理、可用性与分区容错性
  的权衡"),而不是当前这一轮真正提的问题。
- **根因排查(2026-08-03,主会话独立核实,推翻了实现子代理最初给出的诊断)**:实现该组场景的子代理最初
  判断是"被打断的旧 turn 材料延迟到达、绕过 `aborted`/`basis` 校验放行"的时序竞争问题。逐行核对
  `bot.log` 时间戳后确认**不是这个机制**:`inject turn=3` 的时间戳与 `dispatch turn=3` 相隔约 30 秒,
  与 gemini-3-pro 的真实响应延迟区间(design §13.3 实测 10–50s)吻合,而不是接在 turn=1/2 的 dispatch
  时间点上;且全程**没有任何 `stale-drop` 日志行**——说明 turn=1/2 的调用确实被打断帧干净中止,没有材料
  泄漏。**独立复核 reviewer(2026-08-03)进一步补强了这个结论**——更硬的直接证据其实是同一份
  `bot.log` 里框架自身按次调用打的行:`dual_brain_interrupt` 那次运行里,turn=3 的
  `SlowBrainLLM: Generating chat from context [...]`(`bot.log:91`)显示喂给模型的 context 是
  `[{"role":"user","content":"(会话开始,用户尚未提问)"}, {"role":"user","content":"分布式系统的
  CAP 定理是什么?"}, {"role":"user","content":"现在几点了?"}]`——**三条连续的 `user` 消息,中间零
  条 `assistant` 消息分隔**;且该次调用的 `TTFB: 4.539s`(`:97`)+ `processing time: 29.769s`
  (`:103`)精确对应 turn=3 自己的 dispatch 时刻(`:22.887`)与材料到达时刻(`:52.657`)——不是接在
  turn=1/2 各自早已独立完成的调用(分别 `processing time: 1.734s`/`2.520s`,`:72-73`/`:85-86`)之后。
  真正的材料就是 turn=3(追问自己触发的新一轮分发)的**全新**生成结果,只是模型给出的内容跑偏
  到了更早的话题上。可能成因(合理推测,未逐层穷举验证):①`SLOW_BRAIN_PROMPT`(`prompts.py`)只说
  "对用户的问题做深度分析",没有显式限定"只分析最新一条用户消息、忽略更早的";②追问之前的几轮如果
  慢脑都是零输出(`no-material`),`slow_context` 里会连续堆几条 `role=="user"` 消息、中间没有
  assistant 轮次分隔——这种非常规的对话结构可能进一步削弱了模型"当前该回答哪一条"的判断力。
- **影响**:这触及 design.md 已批准的两处契约假设——**§5.2"位置即归属"**(注入位置对应哪个问题完全靠
  代码判定,前提是慢脑产出的内容确实是针对最新问题的;若模型自己把话题跑偏,位置对了、内容却文不对
  题,快脑会把过时话题的材料当成当前话题的补充说出来)和**§6.7①慢脑 prompt 文本**(可能需要显式加一句
  "只分析最新一条用户消息,不要理会更早的问题")。
- **裁决**:2026-08-03 用户裁决——本期口径"不做质量把控、整体跑通即可"(design.md 开工前已拍板),记
  backlog,不在第 7 组内修复(任务卡范围只允许改 `server/evals/`,不许碰 `dual_brain.py`/`prompts.py`),
  按原计划继续第 8/9 组。后续若要处理,建议路径:先补一次 mini 技术分析(强化 `SLOW_BRAIN_PROMPT` 显式
  限定"只分析最新一条用户消息"+ 视情况在零输出轮次给 `slow_context` 补一条占位 assistant 消息维持角色
  交替),过一轮轻量评审后再改,不当场直接改已批准的 prompt 契约文本。
