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
  - id: D-009
    desc: pipecat UIJobGroupContext 官方无覆盖测试,本期以"不启用 ui_job_group"规避,2期G4启用前须先补三组测试
    module: server/task_dispatch.py
    ttl: 2026-12-31
    source: task-dispatch
  - id: D-010
    desc: openclaw 包挂在 ~/.nvm/versions/node/v24.18.0/ 下,该 nvm 版本被卸载会同时废掉 Gateway 与 CLI 入口;根治需 sudo npm install -g openclaw 到系统 Node(新增/重装依赖类操作,未擅自执行)
    module: infra/openclaw
    ttl: 2026-12-31
    source: task-dispatch
  - id: D-011
    desc: 本机 eval 环境缺口致 3 个既有音频/本地模型场景无法执行——starter_audio/dual_brain_audio 因缺 requests 模块(ImportError)、starter_text 因本地 Ollama 未启动;C-03/T-8 复验时须沿用同一失败集合判定不算回归,不要误判为改动引入
    module: server/evals
    ttl: 2026-09-30
    source: task-dispatch
  - id: D-012
    desc: dual_brain_inject/dual_brain_interrupt 两个 eval 场景为已知双脑注入时序 flaky 用例(同一份代码两次运行结果可能不同,已实测复现两侧皆失败/皆通过),给 C-03 类回归判定带来噪音,建议排查断言的时序窗口是否需放宽或改用更鲁棒的判据
    module: server/evals
    ttl: 2026-09-30
    source: task-dispatch
  - id: D-013
    desc: TaskDispatchWorker.reply 工具签名(tasks:list[str])无独立摘要通道,contract §0.9 要求的 DispatchRegistry.label(播报用一句话摘要)实际取"任务书正文折叠空白后前40字符"机械截断,非契约字面"第二个LLM给的摘要";功能等价、未致任何验收用例失败,但多任务播报措辞质量可能不如真摘要,如需严格满足需改 reply 契约签名(新增独立摘要参数)
    module: server/task_dispatch.py
    ttl: 2026-09-30
    source: task-dispatch
  - id: D-014
    desc: TaskDispatchWorker 内部委托的第二个 LLM(reply 工具背后那次推理)构造细节是契约空白处——复用 cfg.llm_model(非 cfg.slow_llm_model)、不设 system_instruction,design.md/contract/prd 全文零命中相关规定;真机验证功能可用,但若需要专门角色设定该 prompt 常量按 R4 约定应落 server/prompts.py,当前实现无该角色设定
    module: server/task_dispatch.py
    ttl: 2026-09-30
    source: task-dispatch
  - id: D-015
    desc: >-
      【高优先级,需设计级复核】OpenClawExecWorker 派发时序存在真实竞态,已真机复现一次:design.md 数据模型§2步骤9的字面顺序是
      "生成session_key → spawn CLI → 轮询tasks show(上限30s)→ 写入DispatchRegistry",而session_key消费方
      events_wait 事件循环(步骤10)在首个派活前就已连接开始收事件;若任务在注册表写入完成前就产出结论消息(极快任务实测可复现,
      如"写一句话"), 步骤11的"sessionKey命中注册表"判定不通过, 事件被静默丢弃且不重试(呼应ADR-5"终态只认push不做兜底"),
      该任务的完成播报永久丢失, 用户只能靠FR-2主动查询才发现任务其实已完成——这直接削弱FR-3(任务完成消息回流播报)对"最快
      最简单"这类任务的核心承诺, 不是非目标条目11/12覆盖的"异常路径", 是正常路径下的竞态。**关键佐证**: contract §0.6 原文明写
      "由voice-agent侧先生成session key、再随--session-key传给CLI, 因此派发瞬间即持有lookup, 不必等CLI退出"——这与design.md
      步骤9把注册表写入排在tasks show轮询成功之后直接矛盾, 即已冻结的contract与design内部自相矛盾, 不是本次新引入的设计决策。
      可能修法方向(未验证, 需设计复核): 把DispatchRegistry写入提前到session_key生成后立即执行(在spawn CLI之前), 与
      §0.6承诺对齐;需一并考虑spawn失败(C-04路径)时如何撤销这条提前写入的记录, 避免幽灵条目。本条不是本会话自行拍板修复,
      按用户裁决"真遇到自己无法处理的异常记录到memory等待处理"归类为此类, 未改动已提交的T-4代码(server/task_dispatch.py,
      commit 244ca66)。复现步骤见 pipeline/task-dispatch/T-5-notes.md RISK 4。
    module: server/task_dispatch.py
    ttl: 2026-08-31
    source: task-dispatch
  - id: D-016
    desc: >-
      【高优先级,需设计级复核。复现率订正(T-8补充数据,2026-08-09): C-04确定性必现 3/3(T-7一次+T-8两次全部失败),
      C-19为概率性 1次通过/3次失败(非此前记录的"2/2必现",C-19 不是每次都撞上)】FR-1"派发调用本身失败时经工具报错
      路径回流"实际不成立: dispatch_task 走
      pipecat 框架级 async_tool 协议, 工具调用发起瞬间快脑先说一句"乐观"话(此时真实结果未到), 真实结果(如 CLI
      失败、§0.3 的 CAPACITY_MESSAGE)到达后触发第二次"纠正"LLM调用——该调用因 context 末尾是 role=developer 的
      async_tool"finished"结果、其后无 user 消息, 被 8045 gateway 以 400 "Requests ending with a model turn
      are not supported" 拒绝(与 bot.py::seed_greeting_messages docstring 已记录的同一类 gateway 限制同源)。
      make_pipeline_error_handler 按设计不重试, 纠正永久丢失, 用户最终只听到那句错误的"乐观"话(内容如"已提交到
      后台处理", 实际什么都没派成)。真机复现2/2次独立全新会话均命中(C-04/C-19 两个 eval 场景各触发一次)。
      **定位**: 不是 dispatch_task/task_dispatch.py(T-4)自身的缺陷——那两处 role=user 的 LLMMessagesAppendFrame
      构造(终态播报/CAPACITY_MESSAGE走的是既有队列注入路径)本身正确, 触发400的是 pipecat 框架自己的 async_tool
      纠正轮机制, 落点大概率在 dual_brain.py 或 bot.py 的 context 组装层——**这两个文件都不在 task-dispatch 变更
      九张任务卡(T-0~T-8)任何一张的独占路径内**, 需要新一轮技术方案裁决(是否要在 async_tool 的 developer"finished"
      消息后补一条占位 user 消息, 参照 seed_greeting_messages 已有绕法;或改用其它承载方式), 且需要先用
      pipecat-context-hub 查证 async_tool 协议的官方行为再动手, 不是本会话能单方面拍板的小补丁。
      **影响面评估**: 不直接违反 PRD C1(乐观话是"已提交"而非"已完成", 不构成虚假完成声明), 但确实是 FR-1 描述
      末段字面要求的功能性缺口——用户在派发失败后永远听不到纠正, 只能靠 FR-2 主动查询才会发现任务其实没跑起来。
      复现细节见 pipeline/task-dispatch/T-7-notes.md RISK 2 与 server/evals/dispatch_cli_failure.yaml、
      server/evals/dispatch_capacity_reached.yaml(两文件判据均按契约原文保留未改, 真机驱动会失败属预期, T-8
      验收报告应如实记录为FAIL不得为了让报告好看而弱化判据)。
    module: dual_brain.py / bot.py(具体落点待裁决,不在本变更任一任务卡独占路径内)
    ttl: 2026-08-31
    source: task-dispatch
  - id: D-017
    desc: >-
      【最高优先级,需用户裁决,T-8真机复验中真实发生,非推演】task-dispatch 委托 LLM(TaskDispatchWorker.reply)对
      "本机桌面操作类"请求缺乏派发前的适用性判断护栏。复现: C-17步骤4改动后基线复验时, 一句日常口语请求"帮我把
      浏览器里正在放的视频暂停一下"被 dispatch_task 真实派给后台 openclaw agent, 委托LLM自行编写了一份跨平台
      "暂停浏览器视频"技术任务书(含macOS AppleScript/Linux playerctl+xdotool/Windows PowerShell三套方案)并被
      真实执行——在运行测试的这台机器上实际调用了xdotool、探测并切换了窗口焦点到Chrome、发送了两次真实的
      XF86AudioPause/XF86AudioPlay合成按键事件。快脑最终未声称"已完成"(不违反PRD C1字面底线,纠正措辞为"我
      无法直接控制你的本地浏览器..."), 但过程中已产生真实的、用户未明确同意的桌面副作用, 且中间约27秒用户已
      听到"已安排后台尝试"这类暗示正在处理的乐观话术。本地开发拓扑下openclaw agent执行环境与本机器是同一台,
      这是真实发生的副作用不是理论推演;生产拓扑下若执行环境与终端用户设备物理隔离则副作用改为发生在agent自己
      的宿主环境, 后果视该环境而定, 但本项目当前未对此做任何设计声明。根因: prompts.py 的 CAPABILITY_BOUNDARY_
      SECTION 在T-3已删除"无执行能力"首句(为落实PRD C1派活能力声明所需, 见T-3任务卡), 但删除后委托LLM侧未
      获得任何替代性的"这类请求是否适合派给后台CLI agent"判断依据, prompt层面完全空白。建议方向(未验证): 在
      TaskDispatchWorker背后委托LLM的prompt里加一条"本机设备/桌面控制类请求不适合背景派活, 应在对话中说明
      做不到"的护栏; 或在dispatch_task工具描述层面收窄适用范围。复现与原样输出见
      pipeline/task-dispatch/test-report.md 缺陷清单#5。
    module: server/prompts.py / server/task_dispatch.py(具体落点待裁决)
    ttl: 2026-08-16
    source: task-dispatch
    ruling: >-
      2026-08-09 用户裁决(原话):"操作问题不用担心,我们目前设置的应该是可以全部放行,所以他怎么操作都
      没问题,但我们前期任务尽量要简单可控,直接操作浏览器难度有点大,其实可以让他写一篇文章,这种难度
      小的我们前期是为了流程打通,只有这样我们后期才可以完善"。判定=接受风险,本轮不加代码护栏(prompts.py/
      task_dispatch.py 均未改动)。管控点从"事后加护栏代码"改为"事前引导任务类型"——后续实际派发给委托
      LLM 的任务应优先选低风险类型(如"写一篇文章"),避免本机设备控制/浏览器操作类高风险类型,目的是先
      打通派活全链路流程,再逐步完善护栏。本条转为方向性指导,不阻塞 task-dispatch 变更合并。
  - id: D-018
    desc: >-
      【中优先级,T-8真机复验新发现】快速连续用户话术下 dispatch_task 可能被同一逻辑请求重复触发: 会话内背靠背
      连续两句话(文本模式下几乎无停顿), 后一句在快脑对前一句处理尚未完全落定时就已送达, 触发快脑对同一句用户话
      先后两次调用dispatch_task(间隔约2.5秒), 委托LLM两次都判定"需要派活"并各自派出一个exec job, 注册表出现
      3条记录(A+B1+B2)而非预期2条。复现: bot日志两组独立reply:call_.../dispatched session_key=记录, 间隔
      约2.5秒。未致任何契约C-*判据结构性失败(C-06'数组长度=注册表条数'判据字面仍成立, 因为3条确实如实反映
      内存状态), 但本例若换成有副作用的真实任务书(而非测试用sleep), 会造成真实的重复执行代价。根因推测(未
      验证): 快脑侧对'同一句用户话是否已在处理中'没有去重/防抖机制。复现细节见
      pipeline/task-dispatch/test-report.md 缺陷清单#2。
    module: server/task_dispatch.py / server/dual_brain.py(具体落点待排查)
    ttl: 2026-09-30
    source: task-dispatch
    ruling: >-
      2026-08-09 用户裁决(原话):"关于任务派发2次应该快慢脑协作问题,之前慢脑是提供帮助的高级辅助,只
      面对回答问题,现在改成了任务,所以他的角色还没调整,这个没问题,后期优化就是专门做这个"。判定根因
      =慢脑角色定位(原设计"高级辅助答疑" -> 现设计"派发任务")转型未跟随调整的架构层面缺口,本轮不修,
      留债后续做"快慢脑协作角色重新定位"专项优化时一并处理。
  - id: D-019
    desc: >-
      CAPABILITY_BOUNDARY_SECTION 首句 "If the user asks you to do one of these things…" 指代悬空——
      其指代的能力枚举句已在 commit e94b874(task-dispatch T-3)随派活能力声明改写时删除;且该段
      "不具备执行类能力"的旧表述与已上线的派活(dispatch_task)能力相左。既有问题,非 scenario-assembly
      引入,s2a 架构评审(2026-08-10)发现。修法方向:重写该段使指代闭合、与派活能力声明一致。
    module: server/prompts.py
    ttl: 2026-09-30
    source: scenario-assembly
    ruling: >-
      2026-08-10 用户批准 scenario-assembly 设计([A])时一并授权登记(随批事项③),本变更不修。
  - id: D-020
    desc: >-
      AssemblyAI universal-3-5-pro 中英 code-switch 真机实测(SA-20,2026-08-10 用户本人真机连接):
      日常随意语速的中英混说场景识别准确度不如纯中文——用户报"纯中文识别比较准";实测复现一例具体误判:
      用户说英文名字 "Kylen",被识别成同音中文"开了"(专有名词/人名类词汇被按读音误转写成中文,而非保留
      英文)。builder 严格遵守 B-1…B-4(不传任何语言参数,靠模型原生 code-switch),配置侧无实现缺陷;
      属模型本身在此类输入下的识别能力限制,design R-12 已知悉"仍要求真机实证"但未预见此类误判模式。
      不阻塞本变更收尾(SA-19 契约判据是"单句英文可被正确转写",范围更窄,已通过)。
    module: server/bot.py
    ttl: 2026-09-30
    source: scenario-assembly
    ruling: >-
      2026-08-10 用户真机验证 SA-20 时口头发现,未要求本轮更换 STT provider 或重新设计,留债后续
      观察/评估(例如引导用户放慢语速、提示词层面减少专有名词依赖,或后续换模型/参数,design R-15
      已铺好"per-provider 模型旋钮"的改动面)。
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

## D-009 · pipecat `UIJobGroupContext` 官方无覆盖测试 —— 启用 `ui_job_group` 前的补测门

- **现象**:codegraph blast radius 实锤(纪要 `pipeline/task-dispatch/research/pipecat-worker-source-verification.md`
  §6 条目 1),pipecat 官方对 `UIJobGroupContext` 无任何覆盖测试。四信封
  (`group_started` / `job_update` / `job_completed` / `group_completed`)是否实际抵达客户端,
  官方未验证过。
- **本期处置(已落地,不是欠账)**:task-dispatch 变更选用 `UIWorker` 但**不启用**该链路,
  由 `pipeline/task-dispatch/contract/cases.md` C-16 守住——`grep -rn
  "start_ui_job_group\|ui_job_group\|__cancel_job_group" server/ --include=*.py` 零命中,
  外加 `server/tests/test_task_dispatch.py` 内一条静态断言测试。
- **欠的是什么**:将来(2 期 G4「按需监控本机页面内容实时交互」,或任何要做客户端任务进度卡的变更)
  启用 `ui_job_group` 之前,必须先自行补齐三组测试,不得以"官方件默认可靠"带过:
  1. 四信封端到端是否实际抵达客户端;
  2. `cancellable=True` / `False` 是否分别生效;
  3. `start_ui_job_group` 是否确实立即返回、不阻塞调用方。
- **触发条件**:任何变更打算移除 C-16 的 grep 零命中约束时。
- **裁决**:用户 2026-08-08 于 task-dispatch s2a 呈批回合批准登记(裁决点④)。
