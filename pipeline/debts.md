---
debts:
  - id: D-001
    desc: 断开重连失败——WebRTC 断开后页面内再连,POST /start 返回 200 但客户端不再发 offer,连接卡死
    module: client/
    ttl: 2026-09-30
    source: pipecat-native-p1
  - id: D-002
    desc: TTS 多句应答偶发卡死/重叠(Kokoro 慢速 CPU 场景根因已定位,ElevenLabs 下未复现)
    module: server/bot.py
    ttl: 2026-12-31
    source: pipecat-native-p1
  - id: D-003
    desc: server/bot.py 模块顶层副作用逼测试用 sys.modules 手法绕过,建议改惰性单例
    module: server/bot.py
    ttl: 2026-12-31
    source: fast-slow-brain
  - id: D-004
    desc: 连续追问时慢脑跑偏分析最早话题——击穿 design §5.2"位置即归属"契约假设
    module: server/prompts.py
    ttl: 2026-09-30
    source: fast-slow-brain
  - id: D-005
    desc: 快脑重复作答——_FastAnswerTap 修法已实现但真机联测未确认,不据此关闭
    module: server/dual_brain.py
    ttl: 2026-09-30
    source: fast-slow-brain
  - id: D-006
    desc: M2 慢脑失败面板提示可见性未验证(联测期间慢脑全程未失败,需故障注入或自然触发)
    module: client/
    ttl: 2026-12-31
    source: fast-slow-brain
  - id: D-007
    desc: M8 空输出面板闪现观感未验证(需 D-005 修复后或自然遇到"有素材但判定无需补充"场景)
    module: client/
    ttl: 2026-12-31
    source: fast-slow-brain
  - id: D-008
    desc: Deepgram/Cartesia 多 provider 能力未走任何流程直接合入,无需求与设计留痕
    module: server/config.py
    ttl: 2026-09-30
    source: 73125d7
---

# voice-agent · 项目债务簿

> dev-pipeline 唯一债务载体,跨变更存续。frontmatter 由 `ledger.sh debts-check` /
> `pipeline-check.sh debts` 机检,正文是人读的根因详情。
> 2026-08-08 由已废弃的 `docs/backlog.md`(旧三门流程载体)整体迁入,原文件已删除。
> ttl 是复审到期日,不是承诺修复日;超期且命中变更触达模块时 s0 会阻断(exit 7),
> 清偿或人工豁免后方可继续。

---

## D-001 · 断开重连失败(客户端 SDK 层) ← 原 B1

- **现象**:WebRTC 连接断开后,在同一页面再次点击连接,`POST /start` 正常返回 200,但客户端不再发起
  `/sessions/{id}/api/offer` 请求,连接卡死(浏览器控制台无报错)。
- **范围判断**:`client/` 基本是官方 `@pipecat-ai/voice-ui-kit` + `client-js`/`client-react` 脚手架,
  未见自定义连接状态管理代码——判断是上游客户端 SDK 断开后状态未清理干净导致,不是本项目 server 端
  代码问题。
- **临时规避**:刷新页面(而非用页面内"断开重连")。
- **裁决**:2026-08-01 dogfood 排障期间用户裁决暂不深挖客户端 SDK 源码。
- **对应路线图**:能力账单优化项 O4(断连韧性)。

## D-002 · TTS 多句应答偶发卡死/重叠——根因已定位,暂不修 ← 原 B2

- **现象**:一轮回复被拆成多句 TTS 分别合成时,播放偶发卡死(状态停在"说话中"但实际没声音,需手动打断才能
  解开)或音频重叠。旧库归档变更 `2026-08-01-pipecat-native-p1`(voice-translate-v2 仓库)
  tasks.md 2.3 / 4.4"新发现 1"最早记录的是"重叠",20260801-02 dogfood 期间新发现同一根因还会导致
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
- **复验结论(2026-08-03,fast-slow-brain 第 9 组 M3 人工联测)**:TTS 服务已从本机 Kokoro(纯 CPU)
  切到 ElevenLabs(云端)——**本次真机联测未复现**,多句回复依次播放,面板逐句刷新,用户确认无卡死无
  重叠。**不当作"已解决"关闭本条**:上面的根因分析是针对 Kokoro 场景定位的,ElevenLabs 是云端合成、
  延迟特性完全不同,本次未复现更可能是"触发条件(本机 CPU 慢速合成)不再存在"而非"根因已被修复"——
  若未来又切回本机 TTS/更换到另一个可能慢速合成的 TTS 服务,该根因仍可能重新触发,届时仍应参考上面
  记录的修法(显式调大 `stop_frame_timeout_s`)。
- **对应路线图**:能力账单优化项 O5。

## D-003 · `server/bot.py` 模块顶层副作用逼测试用 `sys.modules` 手法绕过 ← 原 B3

- **现象**:`bot.py` 顶层直接跑 `load_dotenv(override=True)` + `cfg = load_config()`(官方脚手架既定结构),
  任何 `import bot` 都会立刻读取真实环境变量。`server/tests/test_bot.py` 的 `bot_module` fixture 为了在
  不依赖真实 `.env`/环境变量的前提下测 `STT_BUILDERS`/`TTS_BUILDERS`,只能 `monkeypatch.setattr(dotenv,
  "load_dotenv", ...)` + `sys.modules.pop("bot"/"config", None)` 再强制 `importlib.import_module("bot")`。
- **风险**:`sys.modules` 是进程级全局状态操作,依赖 fixture teardown/setup 隐式顺序不出错;若未来引入
  `pytest-xdist` 并行,或其他测试文件也 `import bot`/`import config` 并假设单例语义,可能产生跨测试污染。
  当前(fast-slow-brain 第 1 组,2026-08-02)单文件场景下逻辑已核对正确、测试通过,但手法本身脆弱。
- **根因**:副作用放在模块顶层而非函数内,是官方脚手架产物,不在当时任务卡改动范围内。
- **修法方向(暂不做)**:把 `cfg = load_config()` 挪进 `bot()`/`run_bot()` 函数体或做成惰性单例,届时可去掉
  `test_bot.py` 里的 `sys.modules` 手法,换成更干净的依赖注入测试写法。
- **裁决**:2026-08-02 第 1 组组末双裁决(security-reviewer 视角)MEDIUM 发现,判定不阻塞当期验收。

## D-004 · 连续追问场景下慢脑"跑偏"分析最早话题——已批准契约(§5.2/§6.7①)存在缺口 ← 原 B4

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
- **裁决**:2026-08-03 用户裁决——当期口径"不做质量把控、整体跑通即可"(design.md 开工前已拍板),
  不在第 7 组内修复(任务卡范围只允许改 `server/evals/`,不许碰 `dual_brain.py`/`prompts.py`)。
  后续若要处理,建议路径:先补一次 mini 技术分析(强化 `SLOW_BRAIN_PROMPT` 显式限定"只分析最新一条
  用户消息"+ 视情况在零输出轮次给 `slow_context` 补一条占位 assistant 消息维持角色交替),过一轮轻量
  评审后再改,不当场直接改已批准的 prompt 契约文本。

## D-005 · 快脑自己的应答未写入 context 就被慢脑补充触发重新生成 ← 原 B5

- **修法已实现(2026-08-03,`_FastAnswerTap` 旁听录音机)**:插在 `fast_llm` 和
  `sentinel_filter`/TTS 之间(`bot.py::assemble_pipeline`),不经 TTS 那条按播放顺序释放的队列,直接
  旁听快脑原始 `LLMTextFrame` 输出,记入 `last_answer`。慢脑`素材已齐`触发重新生成时
  (`dual_brain._SlowMaterialTransformer`),若 `last_answer` 非空,注入文案换成
  `prompts.INJECT_DONE_WITH_REMINDER_TEMPLATE`,带上"你刚才已经这样回答过:……"的提醒,交给快脑自己
  判断补充还是不重答。**不改变** R4 已批准的触发时机契约(何时触发慢脑注入这件事一行未动),只改注入
  消息的**内容**。全套单测 + ruff + pyright 当时全绿。
- **仍是"降低复现概率"而非"从根上消除并发窗口"**:调研已确认官方
  `LLMAssistantPushAggregationFrame` 方案证伪(聚合器的内容本身也被同一条 TTS 播放顺序队列拖住,提前
  提交只是交白卷),"等真正落盘再触发"方案会正面推翻已批准的 R4 契约、需重新走评审——均已排除,旁听
  录音机是当前唯一可行路径。真实效果(尤其"提醒是否真的让快脑放弃整段重答"这个语用层面的判断,取决于
  快脑对提醒句的理解,不是机制层面能 100% 保证)**待下次真机联测确认,不据此关闭本条**。
- **现象**:第 9 组 M6 人工真机联测(2026-08-03)实测发现——用户问"Java 分布式锁有什么方案"并追加
  "说核心内容、不要太多",快脑先给出一句简短(且明显被截断,只提了 ZooKeeper、漏了 Redis)的回答;
  约 8 秒后慢脑补充素材注入完成(`role: "user"`,§6.1 当期固定角色)触发快脑重新生成,快脑却把整个
  问题从头完整重答了一遍(Redis + ZooKeeper 都完整讲了),用户听感是"同一条信息说了两遍"。
- **根因(2026-08-03 主会话逐行核对 `bot.log`,turn=13)**:快脑自己那句简答在 `10:58:58.243`
  就已生成完毕(`OpenAILLMService#0 processing time: 1.682s`),距慢脑注入完成(`10:59:06.981`,
  `SlowBrainLLM processing time: 10.422s`)有 8 秒富余——按 design.md:189"换快档已知限制"条给出的
  "慢脑 10–50s ≫ 快脑 2.2s,顺序安全"的论证,这本该来得及把快脑的 assistant 消息写入 context。但
  `10:59:06.982` 触发的新一轮生成实际喂给模型的 context 里,**完全没有那句简答**——从用户上一句
  "介绍。"直接跳到慢脑注入的 `user` 消息,快脑因此"看不到自己已经答过",无法执行 R4 契约要求的
  "结合慢脑要点判断要不要在已答内容基础上补充"这一步,只能把问题当全新的从头作答。**这与 design.md:189
  记录的场景不是同一个触发条件**(那条限制的前提是"换成更快的慢脑档位"才会让顺序不安全;本次复现
  用的仍是当前配置的 gemini-3-pro 慢档,顺序时间差本该充裕),说明"快脑 assistant 消息何时真正落进
  context"这件事本身还有另一个未查明的丢失路径(推测但未验证:紧邻的两轮对话——turn=12 与
  turn=13——间隔仅约 1.6 秒,turn=12 的用户话音很短且几乎同时被 turn=13 的下一句打断,可能是这次
  写入竞争/覆盖的诱因,未逐层穷举验证)。
- **影响**:直接击穿 R4"补充自判"契约的前提假设(design.md §737 行:补充需以"快脑看得见自己已答"为
  基础)——不是补充逻辑判断错了,而是判断赖以依据的输入(自己说过的话)在特定时序下会丢失,导致快脑
  退化成"从头重答",与 design.md:189 已知限制同源但触发条件更宽(不需要换快档就能复现)。
- **后续建议**:先精确定位"快脑 assistant 消息丢失"的触发路径(相邻两轮间隔过短导致的写入竞争 vs
  其他机制),而非直接改 R4 触发条件或注入时机。

## D-006 · M2 慢脑失败面板提示可见性未验证 ← fast-slow-brain gate.yml uncovered

- **原因**:2026-08-03 门三真机联测期间慢脑全程未失败(`bot.log` 零 `slow-failed` 命中),该观察项未触发。
- **触发条件**:下次人工故障注入,或生产环境自然触发慢脑失败时验证。
- **裁决**:用户 2026-08-03 批准 WAIVED 放行,不为专门验证另行补测。

## D-007 · M8 空输出面板闪现观感未验证 ← fast-slow-brain gate.yml uncovered

- **原因**:2026-08-03 门三会话零 ∅ 输出(素材有内容但被 D-005 缺陷导致误判为需要重答,而非判断
  "无需补充"),该 UI 观感场景未触发。
- **触发条件**:D-005 修复后,或自然遇到"有素材但快脑判定无需补充"场景时验证。
- **裁决**:用户 2026-08-03 批准 WAIVED 放行。

## D-008 · Deepgram/Cartesia 多 provider 能力未走流程直接合入

- **现象**:提交 `73125d7`(feat,新增 deepgram STT 与 cartesia TTS)、`c9d6be9`(fix,按 provider
  条件校验必需项)、`964eb3b`(docs)已合入分支,能力本身工作且带单测,但**未经任何需求/设计流程**,
  也未登记进任何需求事实源。
- **影响**:能力账单里 C2(服务可插拔 + 场景装配层)的实际完成度与文档记载不一致——账单标 ❌,
  实际 provider 层已可插拔,但装配层(场景配方、运行时 `ServiceSwitcher`)仍未做。
- **建议处置**:下次触达 `server/config.py`/`server/bot.py` 的变更里补一段现状说明,把 C2 的真实完成度
  写进当次 prd.md 的现状盘点,不必倒补一份完整需求文档。
