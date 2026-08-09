# 外部调研纪要 · task-dispatch(C4 派活)

> 调研日期 2026-08-08。方法:本地一手源码/预挖掘资料(`~/git/source-project/pipecat` clone + 项目内部罗盘
> `~/research/2026-07-30-pipecat官方现成件盘点/罗盘.md`)与 9 路外部检索(data-fetcher 子代理:官方文档站、
> 官方 GitHub 仓库/issue、GitHub 代码/issue 搜索)交叉验证。已核实与推测/未验证在正文中逐条标注,不混同。

## 0. 调研口径(调研过程中经用户三次裁决收敛,以此版本为准)

- **核心原则**:派活最大化复用 pipecat 框架原生能力,官方有什么就用什么;外部资料只作旁证参考,不作骨架依据;
  现有代码骨架不改;自研量压到最小,只在官方确无对应件的地方才自装。
- **Q1(执行载体)收窄**为:评估已内部核实的官方范式(`examples/multi-worker/code-assistant/` 展示的"主 worker
  出工具 → job 派给纯 bus 的 BaseWorker → 该 worker 内嵌 Claude Agent SDK 持久会话")的已知坑与运维注意事项,
  不再做开放式载体选型对比。
- **Q2(竞品)降为次优先**,目的收窄为"佐证成熟模式 + 摘录踩坑经验",不是找替代方案。
- **Q3(防谎报完成)升为最高优先**,这是官方框架没有对应件、必须自装的核心区域。
- **Q4(授权确认链)——本文不含 OpenClaw 一节**:主会话本机装有 OpenClaw 全量 npm 包(含完整 `docs/`、`dist/`
  源码),已直接一手核实,比本 agent 的外部检索更权威,该项目的调研由主会话自行产出,不在此文重复。本文 Q4
  聚焦通用 HITL 机制,以及"异步结果回流对话"的时机/话术问题(用户明确点出的真实设计缺口)。
- **Q5(持久化)收窄**为:官方 bus 自带的三种后端(进程内队列 / PostgreSQL / Redis)之下,是否还需要额外持久化组件。

---

## Q1 · 后台执行载体:官方范式的已知坑与运维注意事项

### 1.0 范式确认(本地源码实锤,非外部检索)

`examples/multi-worker/code-assistant/code_worker.py`(`~/git/source-project/pipecat` 本地 clone 全文已读)
——`CodeWorker(BaseWorker)`:

- `__init__` 构造 `ClaudeAgentOptions(permission_mode="bypassPermissions", allowed_tools=["Read","Bash","Glob","Grep"],
  model="sonnet", max_turns=10)`,**全文无 `canUseTool` 或任何自定义授权钩子**(:47-60)。
- `on_job_request()` 覆写为"来一个塞一个"进 `self._queue`(:74-78),真正的活在 `_worker_loop()`(:80-118)——
  单一 `ClaudeSDKClient` 在 `start()` 时 `create_task` 起,`connect()` 一次,`while True: await self._queue.get()`
  循环处理,**严格串行**,`disconnect()` 在 `finally` 里带一段注释解释为什么要绕开 `async with` 自己调(:111-118)。

这就是 Q1 要评估的具体范式,以下坑均针对**这个具体实现**,不是泛指 pipecat 框架能力。

### 1.1 已知坑一:取消 / 超时在这个范式下形同虚设

**机制(本地源码逐行核实,置信:高)**:

pipecat 框架层面,`job()`/`request_job()`/`job_group()` 均带 `timeout: float | None` 参数
(`workers/base_worker.py:659-737`),超时到点会走 `_task_timeout()`(:1366-1371)→`cancel_job_group()`(:838-855);
无论主动取消还是超时触发,走的都是同一条路径:`cancel_job_group()` 把 `job_id` 从 `self._job_groups`
**pop 掉**,给每个 worker 发 `BusJobCancelMessage`。

worker 侧收到取消消息后进 `_handle_job_cancel()`(:1261-1276):若 `self._job_handler_tasks` 里还挂着这个
`job_id` 对应的 task,就 `cancel_task()` 真正打断它;不管有没有打断,都会调用 `on_job_cancelled()` 钩子并回一个
`status=CANCELLED` 给请求方。

**问题出在 `_job_handler_tasks` 什么时候被清空**:`_handle_job_request()`(:1179-1204)会把每次入站请求包一个
task 塞进 `_job_handler_tasks[job_id]`——但 `CodeWorker.on_job_request()` 干的事只是
`self._queue.put_nowait(message)`,**几乎瞬间返回**,这个 task 立刻完成并在 `_run_job_handler()` 的 `finally`
里被 pop 掉(:1206-1222)。真正耗时的 Claude SDK 调用发生在**另一个**长驻的 `_worker_loop()` task 里,根本不在
`_job_handler_tasks` 的追踪范围内。

所以现实时序是:请求进来 → 瞬间入队 → `_job_handler_tasks` 里的记录几乎立刻消失 → 之后任何时间点(几乎必然,
因为 Claude SDK 调用通常要几秒到几十秒)收到取消或超时消息 → `handler_task` 查到的是 `None` → **不会**
`cancel_task()` → 但仍然会回 `status=CANCELLED` 给请求方,且请求方这边的 `JobGroup` 已经被 `pop` 掉。结果:
请求方以为任务已取消/超时,`_worker_loop` 里的 Claude SDK 调用却继续在后台跑完(消耗时间与 API 成本),且这条
队列在此期间**卡住不处理下一个任务**(严格串行);跑完后 `send_job_response()` 打给一个已经不存在的
`job_id`,静默丢弃。

**这不是框架缺陷,是示例实现的缺口**:框架文档(`/pipecat/learn/job-coordination`,data-fetcher 检索核实,
置信:高)原文承诺"the agent's `on_job_cancelled` hook fires...so you only need to override this hook if you
have resources to clean up"——钩子确实按承诺触发,只是 `CodeWorker` 没有覆写它去调用 Claude Agent SDK 自己的
取消 API。

**规避方式(官方已有,不需要自研,置信:高——直接对应官方生产代码先例)**:pipecat 框架自己的 `UIWorker`
(与 `ReplyToolMixin` 同属 `workers/ui/` 模块)示范了正确模式——`_respond_job` 用
`@job(name="respond", sequential=True)` 装饰(`workers/ui/ui_worker.py:390`),`_run_llm_turn()` 把"整个 LLM
轮次"完整跑在这个被追踪的 handler 内部(:409-420 docstring 原文:"Spanning the full round-trip is what makes
the job single-flight"),而不是像 code-assistant 那样把活丢给外部 queue+loop。`sequential=True` 由
`pipeline/job_decorator.py` 实现,docstring 原文:"Each request runs in its own asyncio task so the bus
message loop is never blocked...requests with this name run one at a time in FIFO order"——**换句话说,只要把
Claude SDK 调用直接写进一个 `@job(sequential=True)` handler(SDK client 作为 worker 实例属性持久持有),就能
同时拿到"单会话顺序处理"与"逐任务可靠取消/超时"两个目标,且完全是官方 API 组合,不需要自研**。唯一的官方文档化
代价(`job_decorator.py` docstring 原文):"The wait time counts against the requester's timeout, so a slow
predecessor can cause queued requests to time out before they start"——排队等待时间算在请求方超时预算里,忙时
可能出现"还没轮到就先超时"。

同时应在 `on_job_cancelled` 钩子里显式调用 Claude Agent SDK 的 `Query.interrupt()`(streaming-input 模式专用)
或 `Query.stopTask(taskId)`——后者官方文档原文就是"stop a running **background task** by ID"(data-fetcher
检索核实,置信:高),与本场景语义直接对应——让取消信号真正传导进 SDK 会话内部,而不是只停在 pipecat 这一层。

### 1.2 已知坑二:长期驻留会话的稳定性——有一个当前仍 open 的官方内存泄漏 issue

(置信:高,GitHub issue 一手核实)

`code-assistant` 范式要求 `ClaudeSDKClient` 在 worker 整个生命周期内只连接一次、长期持有。这个假设本身有已知
风险:

- **`anthropics/claude-code` issue #18859(open)**:4 个空闲会话运行 18 小时,每个内存涨到约 15GB(合计
  60GB)触发 OOM 崩溃;debug log 显示 context 大小全程恒定(6664 chars),排除"纯上下文累积"是唯一原因;在
  2.1.7~2.1.30 多个版本复现,评论区含一份实测曲线(3 分钟 343MB → 261 分钟/约 4.3 小时后 4568MB 且
  "hung"),另有长驻 MCP 子进程(playwright)内存涨到新起进程 6 倍的旁证。**这个 issue 开在 claude-code CLI
  而非 SDK 包本身**,但 `ClaudeSDKClient` 长驻期间正是持有同一个该 CLI 子进程,风险直接迁移到"长驻 session"
  场景。
- **`anthropics/claude-agent-sdk-python` issue #434(open)**:"Large memory spike when spawning helper
  processes"——自 SDK 0.1.18 起,spawn helper 子进程显著推高常驻内存(基线 372MB→433MB,每个 helper 再加约
  270-290MB),资源受限环境下并发 helper 可触发 OOM kill;**且一旦发生一次 OOM,同一个 client 后续所有
  `query()` 调用永久失败**("Cannot write to terminated process")——这是长驻 session 累计发起多次工具调用后
  的具体、可复现失效模式,不是理论担忧。
- **issue #378(已 closed/修复)**:历史上 `Query.close()`/`disconnect()` 在任务未响应取消时可无限 hang 并把
  CPU 打到 100-150%,现已修复,但佐证连接生命周期管理曾是已知薄弱点。
- 第三方项目 `AndyMik90/Aperant` issue #762(置信:中,非官方但直接点名并链接上述两个官方 issue)独立报告:
  多轮 agent session 后残留孤儿 Claude Code 子进程、内存持续累积,workaround 是定期 `pkill -9 -f claude`。
- **未找到**(data-fetcher 检索范围内):官方对"上下文窗口膨胀导致效果衰减"或"长会话历史累积导致成本/延迟
  增长"的明确讨论;官方"建议定期重连/session 存活时间上限"的 guidance。

**匹配度判断**:这条对"桌面语音助手常驻进程、后台 worker 可能一开一整天"的场景是直接命中的风险,且**当前仍未
修复**。建议设计阶段不要假设 worker 可以无限期存活——预算一个**周期性回收策略**(例如按空闲时长或调用次数
上限主动重启 worker/重连 session),而不是让 `_worker_loop` 里的 `ClaudeSDKClient` 天长地久地开着。

### 1.3 已知坑三:权限模式的安全含义——官方示例用的是最宽松档

(Claude Agent SDK 权限体系,data-fetcher 检索核实,置信:高)

`code-assistant` 示例用 `permission_mode="bypassPermissions"`,这是官方 6 档权限模式
(`default`/`acceptEdits`/`bypassPermissions`/`plan`/`dontAsk`/`auto`)里**最不设防的一档**,且全文没有配
`canUseTool` 回调兜底。官方权限评估是"六步流程":hooks → deny rules → ask rules → permission mode → allow
rules → canUseTool callback。这里有个真实的绕过风险(data-fetcher 检索核实,置信:高):**被 allow rules /
acceptEdits / bypassPermissions 预先放行的工具调用根本不会到达你的 `canUseTool` 回调**——如果把校验逻辑写在
`canUseTool` 里,可能被自动放行链路整个跳过;官方给的解法是需要"每次都必查、没有例外"就该用 `PreToolUse`
hook,因为 deny rules 与 `PreToolUse` hook 的拒绝**即使在 `bypassPermissions` 模式下依然生效**。

另外 SDK 还有 `SandboxSettings`(文件系统读写范围 + 网络 `allowedDomains`/`deniedDomains`/`strictAllowlist`/
代理端口),但**只管 Bash 命令能访问的网络面,不管 WebFetch 工具**——是另一套独立规则,linux 上需要
bubblewrap+socat 支持。

**匹配度判断**:照抄 `bypassPermissions` + 固定工具白名单这套示例配置能跑,但对"派活会执行有副作用操作"的
场景(本项目 G3 需求)偏危险——尤其考虑到本项目还有独立的 Q3/Q4(防谎报、授权确认)要求。建议至少加一层
`PreToolUse` hook 做强制拦截(不依赖 `canUseTool` 这种可被绕过的挂载点),具体粒度留给设计阶段(S2a)定。

### 1.4 已知坑四:并发多任务隔离——示例是严格串行,且单会话本身可能不安全并发

(置信:中高,组合了官方文档缺失 + 源码推断 + 测试覆盖率证据)

- **官方示例本身不支持并发**:`_worker_loop` 用单一 `asyncio.Queue` 严格串行处理(1.0 节已述),这不是并发
  隔离方案,是"干脆不并发"。
- **同一个 `ClaudeSDKClient` 能否安全地交错处理多个 query,官方没有明说**:data-fetcher 检索到——官方文档/
  示例全部只展示"一个 query 走完 `receive_response()` 再发下一个"的顺序模式;源码层面(`client.py`,当前 main
  分支)`query()` 没有锁/断言阻止提前再次调用,但 `receive_response()`/`receive_messages()` 读的是同一个共享
  异步迭代器,没看到按调用或按 `session_id` 分流的机制(`session_id` 参数只是透传,不是消费端过滤依据)——
  **推断**(置信:中,只核到 `client.py` 这一层,未深入 `_internal/query.py`)若提前发第二个 query,两次调用
  的消息很可能混流进同一个迭代器而非被安全分离。官方测试套件(`test_client.py`)对这个场景**零覆盖**,既没
  断言安全也没断言报错。相关 issue #1169 + PR #1179(均 open,未合并)讨论的是单次 query 内部"流式输入"与
  "流式输出"的并发,不是跨 query 的交错,不能直接当定论;但 PR #1179 改写后的 docstring 把 `ClaudeSDKClient`
  描述为适合"first-class **follow-up** calls"(顺序追加)而非 "concurrent calls",间接支持"顺序使用才是
  设计预期"。TypeScript SDK 架构上没有 `ClaudeSDKClient` 对应的常驻 client 对象——这个问题主要是 Python SDK
  特有的。
- **推论**:code-assistant 示例选择严格串行,很可能不只是图简单,也是在规避"一个 session 上并发发起多个
  query 是未定义行为"这个真实风险(本 agent 的推理,建立在上述已核实证据上,不是任何单一来源的直接结论)。

**匹配度判断**:本项目 G3 要求"多任务独立"(capability-ledger.md 原文),而这个官方范式的"持久会话"设计天然
是**单会话单队列**的。若要真正的任务级并发隔离,自然的官方兼容做法是**起多个 `BaseWorker` 实例,每个各自
持久连接一个 `ClaudeSDKClient`**(`add_workers()` 支持运行时动态加 worker,已本地核实),而不是试图在一个
共享 session 上并发发请求。这条没有官方示例直接演示"N 个持久会话 worker 组成的池子",是设计阶段需要自己搭的
部分——但搭法(多个独立 `BaseWorker`)仍然是纯官方 API 组合,不算违背"少自研"的口径。

### 1.5 更成熟的同类落地案例

**已拍板底稿项目自己的后端也是同一条路**(data-fetcher 检索核实,置信:中——基于代码/文档片段,非完整审计):
`qwen-audio-agent`(本项目已采用其前台契约,见 codebase-survey.md §6)的后端 Session,经查是给每个受支持的
coding agent(claude/codex/kimi/hermes/qoder)各配一份 `config/<agent>/workspace/AGENTS.md`,通过
`acp-session-tools.mjs`/`session-permission-policy.mjs` 等以 Agent Client Protocol(ACP)驱动**目标 agent
自己的原生 CLI 子进程**(`session/resume` 复用原生 CLI session 历史)。也就是说:**"后台 worker 内嵌一个持久
的编码类 agent CLI/SDK 会话"这个架构选择,不是本项目独创的赌注,已经在被本项目信任到愿意采纳其前台契约的
同一个项目里,被独立地采用了**。这是一条真实的、值得参考的先例,但要注意——qwen-audio-agent 自身也是同量级
的社区项目(非经审计的企业级成熟系统),这条佐证的分量是"架构方向不孤僻、有人独立走到了同一个设计",不是
"大规模生产验证"。

### 1.6 与硬约束的关系

- **对 C4 可能是个好消息,但需设计阶段验证**(codebase-survey.md §5,`on_client_disconnected` 直接
  `worker.cancel()` 断连即杀 pipeline,与"任务不随对话中断"冲突):`worker.cancel()`(bot.py:27)调用的对象
  是**具体那个 `PipelineWorker` 实例**,不是 `WorkerRunner` 整体。若把 code-assistant 风格的 `BaseWorker`
  作为**独立 worker** 加入同一个 `WorkerRunner`(`add_workers(pipeline_worker, code_worker)`),断连只
  cancel 了 `pipeline_worker` 这一个对象,`code_worker` 上的在途 job 理论上不受影响。**这是一个推理出来的
  假设,本次调研没有直接的 PoC 验证它**(罗盘 §3.6 的 PoC 验证的是"processor 异常传播",不是"显式对某一个
  worker 调用 cancel() 是否连累其他 worker"这个场景),建议设计阶段(S2a)专门写一个小 PoC 确认。
- **C5(债务重叠)**:这个执行载体无论怎么选,落地都要往 `bot.py` 里加 `add_workers()` 调用与新 worker 类,
  直接触达 D-002/D-003 同一个模块,需要在设计阶段一并考虑是否先偿还 D-003。

---

## Q2 · 成熟模式佐证(次优先)

目的:证明"主 agent 派活 + 子 agent 干活、对话不中断"这套模式在业界站得住脚,以及摘录别家踩过的坑,不是找
替代方案。

### 2.1 实时语音 API 层面:能力不对等,佐证"不能指望语音 API 自带这个能力"

| API | 原生异步工具调用支持 | 证据 |
|---|---|---|
| Google Gemini Live API | **有**,官方声明式支持:`"behavior": "NON_BLOCKING"` + `scheduling` 字段(`INTERRUPT`/`WHEN_IDLE`/`SILENT`)控制结果何时被说出 | 官方文档实锤(data-fetcher 检索,置信:高)。**但有版本回归**:较新的 Gemini 3.1 Flash Live Preview 退回"仅同步",旧的 Gemini 2.5 Flash Live Preview 才是"同步+异步"都支持——查具体型号能力表,不能假设"越新越强" |
| OpenAI Realtime API | **无**此概念。检索约 2000 行三个官方文档页,"async"/"non-blocking"/"long-running"/"background" 关键词零命中;流程设计上是同步:模型发起 function_call → 客户端执行 → `conversation.item.create` 回传 function_call_output → `response.create` 才能继续 | 官方文档实锤(置信:高)。有个不完全对应的机制"out-of-band response"(`response.conversation:"none"`),但官方文档/示例都没把它用在"后台任务结果注入对话"这个场景上(二次核实:该机制唯一官方示例是对话内容实时分类打标签,不解决"何时安全插话"这个问题)——**未找到实锤**,不能当作 OpenAI 官方支持这个用法 |

**佐证意义**:这两家头部实时语音 API 对"派活不阻塞对话"这件事的原生支持程度天差地别,说明**不能假设底层
语音 API 会替你解决这个问题**——本项目走 pipecat bus/workers 这条独立于具体语音 API 的路径是对的方向,不
依赖某个供应商的模型版本特性。

### 2.2 语音 agent 框架/产品层面:LiveKit Agents 是最直接、最成熟的对照

**LiveKit Agents "Async tools"**(`docs.livekit.io/agents/logic/tools/async/`,官方正式功能,
`livekit-agents` 1.6+ 引入,data-fetcher 两轮检索、第二轮下钻到源码核实,置信:高):

- 用于耗时 > 数秒的工具:`await ctx.update(message)` 把中间进度写入对话上下文,工具函数 `return` 时触发 LLM
  生成新的说话轮次播报结果——这是"结果自然变成一句话"的完整实现,不是概念稿。
- 官方文档明确列出的能力项:**Cancellation**(取消)、**Duplicate-call handling**(防重复调用)、filler
  speech(`ctx.with_filler()`)、agent handoffs。
- 源码级细节见 §4.2(与本项目 Q4 的"异步结果回流对话"问题直接相关,那里详述)。
- **一个官方框架自己也没解决的坑**(源码 `tool_executor.py` 里的 `# TODO(long): reschedule interrupted
  replies?` 注释,置信:高):如果播报本身被用户打断,框架只标记 `interrupted` 状态并发事件,**不会自动重新
  调度**;idle 等待过程中若 activity 关闭,待发内容直接丢弃并记 warning,同样不重试。**这是一条真实的踩坑
  记录**:即使是这个领域最成熟的开源实现,"结果播报被打断后要不要/怎么重试"仍是未完全解决的问题——本项目
  底稿"重试有界,单条坏结果不阻塞后续"这条不变量,恰恰是在预判同一个坑,设计时不能假设这个问题有现成的完整
  解法可抄,要自己认真设计重试/丢弃策略。

**Vapi "Async Mode"**(置信:中,细节未深挖):custom-tools 文档里有"Async Mode"开关,并配置了 Request
Start/Complete/Failed/Delayed 四种语音提示模板——是产品化的同类实现,佐证这不是小众设计,但具体完成播报是
用真实结果动态生成还是静态模板,data-fetcher 未查实。

Retell AI / Bland AI / ElevenLabs Conversational AI 三家未深查(budget 内主动放弃,非"查了没找到")。Pipecat
社区本身没有查到这套模式的直接先例。

**佐证意义**:LiveKit Agents 的 Async tools 是目前查到的、工程细节最完整的同类实现,方向上完全印证本项目
路线,细节上(idle 判定逻辑、结果合并、话术双模板)可以直接借鉴思路(见 Q4)。它自己留的"重试"缺口也提醒
本项目不要低估这部分设计工作量。

---

## Q3 · 防谎报完成:契约层/工程层手段(最高优先)

本项目已确定两层机制(qwen-audio-agent 底稿 + pipecat 已有件,均不算新自研):**①工具 schema 设必填终结
字段**(pipecat `ReplyToolMixin` 即此设计,本地源码核实:`workers/ui/ui_tools.py:20-60`,`reply` 工具的
`answer: str` 是必填参数,docstring 原文"the required `answer` argument is enforced by the API schema so
the model cannot omit the terminator");**②完成事件必须关联正确的派发凭据 ID 才算数**(qwen baseline 自己的
"delegation 关联"不变量,codebase-survey.md §6 已录)。以下是这两层之外,业界还有哪些成熟做法,及各自可靠性/
代价评估。这一区块的最终产出直接是 **C1**(prompts.py `CAPABILITY_BOUNDARY_SECTION` 与
`evals/r4_no_false_completion.yaml`)未来必须同步改写的输入——"未确认完成绝不报办好了"这半条要保留并强化,
下面这些机制是服务于这条铁律的具体手段,不是绕开它。

### 3.1 机制目录

| # | 机制 | 实锤 | 解决什么 | 不解决什么 |
|---|---|---|---|---|
| 1(已知) | Schema 强制终结字段 | pipecat `ReplyToolMixin`(本地核实);OpenAI Agents SDK `output_type=<PydanticModel>` 强制结构化 `final_output`(官方,data-fetcher 核实) | 杜绝"模型用自由文本随口说完成了"这种最弱链路;保证声明走对了通道,下游代码可以可靠地按结构化字段判断 | **不保证字段内容真实**——模型完全可能在必填字段里填一个编造的"完成"结果,照样通过 schema 校验。**必要不充分条件** |
| 2(已知) | ID 关联的状态机守卫 | qwen baseline "delegation 关联"(已拍板);类比:OpenAI `tool_call_id` 作用域绑定、LangGraph `interrupt.id` 配对(官方文档,置信:中——是类比不是直接命中同一措辞) | 杜绝"忙目标/空结果/无关更新/旧结果"被误判为完成 | 不保证结果内容真实,只保证"这条完成事件确实对应这次派发" |
| 3 | Tool result 内容校验 | OpenAI Agents SDK 官方 "Tool guardrails":`tool_output_guardrails`(执行后校验/改写/拒绝,官方举例:扫描工具输出里的 `sk-` 密钥模式并拒绝)、`tool_input_guardrails`(执行前校验)(官方文档,置信:高) | 能拦截"结果里带明显不该出现的内容"这类可规则化的错误 | 可靠性取决于校验规则设计精细度;规则覆盖不到的编造内容照样漏过 |
| 4 | 判官模型二次核验 | OpenAI 官方 `guardrail_agent` 模式(另开一个 Agent 当判官,输出结构化 verdict 含 `tripwire_triggered`);Anthropic 官方工程博客"How we built our multi-agent research system"给出具体量规:0.0-1.0 打分 + factual accuracy/citation accuracy/completeness/source quality/tool efficiency 五维,官方原话"most consistent, most aligned with human judgment";另有专门的 `CitationAgent` 校验每条论述是否有据可查(均为官方一手材料,置信:高) | 能抓 schema/规则校验抓不到的"内容是否真的对" | **不是银弹**:Anthropic 官方自己承认自动化评估(含 judge)会漏判——人工测试抓到过 judge 漏掉的案例(agent 系统性偏好 SEO 内容农场而非权威来源);代价高(见 3.2) |
| 5 | 结构性防"电话游戏"失真 | Anthropic 官方原话:让 subagent **直接把产出写入文件系统**,只把引用/路径传回协调者,而不是靠一层层转述——官方明确点名这是防"multi-agent telephone game"(报告经过多层转述逐渐失真)的解法(置信:高) | 减少"结果经过多层 LLM 转述后被悄悄改写/夸大"的机会 | 不是"防谎报"本身,是"防失真",但两者常常互为因果——转述层数越多,越难分清是谎报还是失真 |

### 3.2 可靠性与代价

- **guardrail 的延迟-安全权衡是官方明文的设计选择,不是隐藏代价**:并行模式(默认)让 guardrail 与主 agent
  同时跑,延迟最低,但主 agent 可能在 guardrail 判定失败前已经调用了工具、花了钱;阻塞模式让 guardrail 先跑
  完,牺牲延迟换"guardrail 失败时保证零副作用"(OpenAI 官方文档,置信:高)。
- **多智能体验证是真金白银的成本**:Anthropic 官方数据——agent 用的 token 量是单轮对话的约 4 倍,多智能体
  系统约 15 倍;且当前是同步执行(lead agent 必须等所有 subagent 跑完才能继续),是个真实的性能瓶颈(官方
  原话,置信:高)。
- **"加验证步骤"本身会引入新的可靠性成本,不是纯收益**:LangGraph 官方文档明确警告——`interrupt()` 恢复
  执行时是**把整个节点从头重放**,不是从暂停点续接;如果暂停前有非幂等副作用(官方举例:写审计日志、追加
  历史记录),恢复时会被**重复执行**,需要开发者自己设计幂等性(官方文档,置信:高)。这条对本项目有直接
  警示意义:任何"派活完成前插一道确认/校验"的设计,都要连带检查这道插入的步骤本身会不会在异常恢复路径上
  产生重复副作用。
- 侧面佐证(置信:低,二手总结,未逐条核实):EPAM 博客整理的"21+ 企业 agent 失败模式"清单里,第 19 条命名
  为"False E2E completion"(把"第一步触发成功"误判为"整条链路完成"),与本项目要防的问题同属一类,仅作为
  "这是业界公认的常见故障模式"的旁证,不作为方法论来源。

### 3.3 结论与匹配度

本项目已定的两层(schema 强制字段 + ID 关联状态机守卫)在业界分类里分别对应"机制 1"与"机制 2",这个组合
本身就是业界比较扎实的基础配置——**不是简化版,是主流两层防线**。第 3-5 类机制(结果校验、judge、防转述
失真)都是**官方已有对应件**(guardrail、guardrail_agent 模式),不需要自研,但目前没有证据表明本项目现
阶段的复杂度需要它们——引入的判断建议留到设计阶段按实际问题(比如若线上真的观察到"完成事件内容与实际执行
结果对不上"的案例)再决定是否加第三层,避免为了防一个还没发生的问题过度设计。若加,`tool_output_guardrails`
这种执行后规则校验,性价比大概率高于直接上"判官模型"(后者代价在 3.2 已列)。

---

## Q4 · 授权确认链 + 异步结果回流对话(自装区)

> 本节不含 OpenClaw——见文首 §0 说明,该项目由主会话本机一手材料直接产出。

### 4.1 HITL 授权确认链:业界具体做法

**触发时机的分级维度**(LiveKit 官方工程博客,置信:高):风险等级(涉及金额门槛)、模型置信度、复杂度门槛、
法规强制(KYC/GDPR/HIPAA)、情绪信号(愤怒/重复失败/用户明确要求转人工)、领域边界越权——六个维度,同一篇
文章给出 5 种可复用子模式:①interrupt-and-resume(LangGraph 式)②human-as-a-tool(把"问人"本身做成一个
工具)③**approval gate**(统一拦截,硬规则:审批必须发生在副作用之前而不是之后)④**sampled approvals**
(分级抽查,高风险 100% 拦截,低风险仅 5%-20% 抽样复核)⑤exception-only review(默认自动执行,只在触发
策略时拦截,官方原话"最成熟但需要强校验器+日志兜底")。

**框架层面对"统一 vs 分级"的支持**:OpenAI Agents SDK 的 `needs_approval` 既可以是 `True`(统一拦截)也
可以是一个异步回调(按参数动态判断,比如"仅当邮件主题含'退款'才需要审批",即分级);Claude Agent SDK 的
allow/deny/ask 规则支持工具粒度分级(可以精确到 `Bash(rm *)` 而不是整个 `Bash` 都拦),`auto` 模式甚至用
一个模型分类器来判断是否需要真人审批(官方文档,置信:高)。语音专属实现:OpenAI Realtime/Voice session 有
`approve_tool_call`/`reject_tool_call` WebSocket 消息,在通话进行中异步批准工具调用(官方文档,置信:高)。

**防止模型绕过审批**(三个框架结论一致:拦截逻辑都在执行引擎/SDK 层,不依赖 prompt 让模型"自觉去问"):

- Claude Agent SDK 的六步权限评估流程里,deny rules 与 `PreToolUse` hook 的拒绝**即使在 `bypassPermissions`
  模式下依然生效**;但有个真实的绕过风险要注意——被 allow rules/acceptEdits/bypassPermissions 预先放行的
  调用**根本不会到达 `canUseTool` 回调**,如果校验代码错放在这里可能被悄悄跳过(官方文档明确提示,置信:
  高;此发现见 Q1 §1.3,与本节同源)。
- OpenAI Agents SDK 的审批拦截发生在 `Runner` 执行循环层:模型发出工具调用后,若没有已存的审批决定,
  `Runner` 直接暂停执行、把 `ToolApprovalItem` 塞进 `interruptions`,模型在这个时间点**拿不到工具结果、
  无法继续**;且是 fail-closed 设计——审批回调若因参数畸形(JSON 错误、非对象、NaN/Infinity 等)解析失败,
  **默认判定为"必须人工审批"**,不会因为解析异常被误判为自动放行(官方文档,置信:高)。
- LangGraph 的 `interrupt()` 是图执行运行时层面抛出的特殊异常,真正冻结执行并把状态存进持久化层,"无限期"
  等待匹配的 `Command(resume=...)` 到来——同样是引擎层硬拦截,不依赖模型配合;官方文档特别警告"不要用
  try/except 包住 `interrupt()` 调用",否则开发者自己过宽的异常处理会把这个硬拦截机制吞掉——**这条提示很
  重要:现实中"审批被绕过"的根因,往往不是模型主动作弊,而是开发者自己代码写错**(官方文档,置信:高)。

**审计记录字段设计**(WorkOS 官方工程博客给出具体 JSON schema,置信:高,可直接当模板参照):顶层
`timestamp`/`session_id`/`trace_id`;`user{id,email}`(发起人)与 `agent{id,name,version}`(agent 自身
身份)**分开记录**,防止把 agent 的动作误记成用户本人的动作;`authorization{scopes,session_type,approved_by,
approved_at,expires_at}` 独立一段;`action{type,tool,arguments,result_status,latency_ms}` 独立一段;
`delegation_chain[{actor,role}]` 记录委托链条。官方强调:审计日志**不能抽样**(运营日志可以抽样,审计日志
必须每次工具调用都记)、必须防篡改、能按 user/agent/session id 查询。旁证(置信:低,二手论坛讨论):Cursor
论坛有相同诉求——不仅要记"提议了什么/是否批准/执行结果",还要能证明"最终执行的动作与当时批准的动作精确
一致"(exact action binding),否则无法排除"批准的是 A、偷偷执行了 B"。

### 4.2 异步结果回流对话:时机与话术的成熟实现模式

底稿已有两条不变量(已拍板,不重新论证):安全插入窗(用户在说话/有 pending 响应就延后,播完才标
delivered)+ presentation.speech 是语义素材不是逐字稿(前台自适应改写)。以下是这套模式在 LiveKit Agents
里的具体实现,细到源码级(data-fetcher 下钻到 `tool_executor.py`/`agent_activity.py` 源码验证,置信:高,
非仅文档表层):

**时机判定(`wait_for_idle()`,`agent_activity.py`)**——一个轮询 `while` 循环,同时判断双向状态:agent 侧
"当前没有正在播的语音、也没有排队中的语音"(`_current_speech is None and not self._speech_q`);user 侧若
正在说话则显式 `await` 等到用户沉默,并等当前对话轮次(end-of-turn)彻底结束。另配两个防抢占原语:
`_user_turn_claims`(可以主动占住 idle 窗口不让别的内容插入)和 `_idle_holds`(防止多个消费者同时抢占同一
个 idle 窗口)。这是"安全插入窗"这个概念在生产代码里的具体判据组合,比本项目底稿目前的文字描述精细得多,
**值得作为设计安全插入窗判定逻辑时的对照清单**。这套机制天然兼容 **C3**(快脑是唯一输出通道)的约束——它
不需要开一个新的输出通道,只是把待播报内容排进现有生成路径,等其空闲时机触发一次常规生成;落地时应保持这个
特性,不要为了实现"回流播报"另开一条独立 TTS/输出通路。

**多结果合并、非逐条打断**:多个后台结果同时就绪时,先进 `_pending_updates` 列表,只维护一个在跑的回复
任务,等到 idle 后**一次性**把所有待播报内容合并成一次播报,而不是一条条抢话——这点本项目也应该照抄,
避免用户被连续多条后台通知轰炸。

**话术生成靠双模板 + 交给 LLM 自行判断"是否已经讲过"**,不是每次人工现编:框架内部按 `at_tail`(idle 后待
插入内容是否仍是上下文最后一条)分两支——是,就用"新结果到了,自然总结,不要重复已经说过的信息"这套指令;
不是,就用"你可能已经在最近几轮里提过这些内容了,如果确实都说过了,直接回复空文本(什么都不说),否则只
总结还没说过的部分,自然过渡"这套指令,**甚至允许 LLM 判定"已讲过"后直接不插话**。这正是"presentation.
speech 是语义素材,前台自适应改写"这条不变量在生产代码里的具体落地方式,可以直接参考这套"判断是否已被
对话覆盖 → 决定是否输出/输出什么"的提示词结构。

**一个诚实的未解决缺口(踩坑记录,已在 Q2 §2.2 提过,这里是该发现的完整出处)**:源码里
`# TODO(long): reschedule interrupted replies?` 的注释承认——播报本身若被用户打断,只标记 `interrupted`
状态发事件,不自动重新调度;idle 等待期间若 activity 关闭,内容直接丢弃记 warning,同样不重试。**本项目
底稿"重试有界,单条坏结果不阻塞后续"这条不变量恰好是在处理同一个问题,但要清楚这不是照抄现成解法——连
LiveKit 都还没完整解决,这部分需要认真设计,不能假设"抄一下就行"。**

**其他候选机制排查结果**:OpenAI Realtime API 的 out-of-band response(`response.conversation:"none"`)
**未找到**被用于"后台结果注入对话"的官方实锤,唯一官方示例是对话内容实时分类打标签,与本场景无关。呼叫
中心/客服领域**未找到**官方/权威的"通知插入时机"命名模式,只有第三方厂商博客的自定义术语(如"aggressive
interjection"),不构成可引用的行业标准命名,不生造术语引用。

---

## Q5 · 任务状态持久化(收窄:官方 3 种 bus 后端之外是否还需要额外组件)

**官方 bus 的 3 种后端,本质是消息投递层,不是结果存储层**(本地源码 + 项目罗盘 §3.2 交叉核实,置信:高):

- 默认进程内 `AsyncQueueBus`:纯内存 dict(`_subscriptions`/`_active_jobs`/`_job_groups` 等),零序列化,
  进程重启即清空。
- `RedisBus`:`publish()` 就是原生 Redis pub/sub(`redis.py:88-96`),**没有订阅者在线消息直接丢**,全程零
  `SET`/`HSET`,不落任何持久状态。
- `PgmqBus`(PostgreSQL):`read` 后即 `archive` 消息本身,官方模块 docstring 原话"Pub/sub fan-out is
  implemented on top of PGMQ's **point-to-point queue** semantics"——本质是把 Postgres 当消息队列用,不是
  拿来当结果存档用;`_reader_loop` 只处理"从现在起的新消息",没有历史重建/回放路径。

三种后端存在的**唯一理由是跨进程/跨机器**——官方文档原话"So far everything has run in a single process.
Next, let's scale across processes and machines"(data-fetcher 检索核实,置信:高),即默认单进程场景下根本
不需要碰 Redis/PGMQ 这两个网络后端。本项目是单进程单用户桌面应用,不存在跨机器分布式部署这个前提
(codebase-survey.md 全文未提及此需求),所以**切换 bus 后端这件事本身在本项目当前范围内没有必要**。

**更关键的一点是:即便本项目未来真的因为其他原因(与持久化无关)切到 Redis 或 Postgres 后端,也解决不了
"完成结果与投递状态要在重启后还能找回来"这个需求**——上面三种后端没有一种提供"重启后可查询历史已完成任务"
的能力,它们解决的是"消息怎么从 A 传到 B",不是"结果记录要不要活过重启"。所以 Q5 原本"选哪个 bus 后端做
持久化"这个问题框架本身有一个前提错位:**bus 后端选型与本项目的持久化需求是两件不相交的事**。

**是否根本不需要额外持久化组件**:不能得出"完全不需要"——已拍板底稿明确要求"重启后在途 Work 一律置
failed,只持久化已完成结果与通知投递状态",这句话本身就意味着确实存在需要跨重启存活的数据(哪怕只是一
小撮:已完成但可能还没播报完的结果 + 是否已投递的标记)。如果真的做成"零持久化、纯内存",重启前那些"已
完成但还没来得及播报"的结果会被直接丢失,与底稿的字面要求不符。

**规模判断**:这一小撮需要持久化的数据在体量上非常小(不需要持久化"进行中"任务的精细状态,只有"已完成 +
待投递/已投递"这一层,单用户场景下并发量也很小)。在这个规模下,为了这一个小需求单独引入 Postgres 或
Redis 依赖(即便框架已经把接入代码写好了)是不成比例的基础设施投入——**这本身也是一种过度设计**,与"官方
有什么就用什么、自研压到最小"的口径不冲突(因为它不是在说"不要用官方组件",而是在说"不要为了一个不需要
外部基础设施的小需求,引入不必要的外部基础设施依赖")。方向上应该是一个独立于 bus 选型之外的、体量匹配
需求的小型本地持久化(具体选型 JSON 文件/`shelve`/SQLite 哪个,是设计阶段的实现细节判断,本次调研的结论
只到"规模上不需要 Postgres/Redis 级别的方案"这一层,不展开选型)。

**若未来真的需要切 bus 后端**(与持久化无关的场景,例如未来做成多机分布式):决策依据是纯粹的部署拓扑——
是否要把 worker 分布到不同进程/机器,而不是持久化需求。

---

## 附:置信度与方法说明

- 本文所有"本地源码核实"均指本次会话内直接 Read 的 `~/git/source-project/pipecat`(codegraph-registry.md
  登记路径;`docs/official-resources-map.md` 记载的 `~/git/pipecat` 路径已过期,建议后续更正)与项目既有罗盘
  `~/research/2026-07-30-pipecat官方现成件盘点/罗盘.md`,附精确文件路径与行号,置信度最高。
- 外部检索(data-fetcher 子代理执行)命中官方文档/官方 GitHub issue 的标"置信:高";命中源码但需要推断的标
  "置信:中";第三方博客/论坛佐证标"置信:低"或"旁证";检索范围内未找到的一律写"未找到实锤",不当作不存在
  处理。
- 两处子代理原始返回文本命中过 harness 的 "bypass-permissions" 模式匹配告警,核查后确认是内容里正常讨论
  Claude Agent SDK 真实存在的 `bypassPermissions` 权限模式术语触发的误报,不含实际注入指令,已按告警提示
  只当数据使用,不影响本文结论。
- OpenClaw 相关内容按主会话指示完全排除,不在本文档任何位置引用或采信。
