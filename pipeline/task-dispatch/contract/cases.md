# 契约 · task-dispatch(档位 cases)

> change_id: task-dispatch | 产出: tech-architect S2a | 日期: 2026-08-08
> 本文件是**本变更接口契约与验收锚点的唯一事实源**。design.md 只引用本文件,不复写其中任何定义。
> 档位理由见 design.md `## 接口契约`。
> 消费者:backend-dev(照 §0 实现)、qa-tester(照 §1 验收)、code-reviewer(照两者比对)。

---

## §0 契约常量(跨组件唯一事实源)

任何组件不得内联下列字面量,一律引用本节定义的常量名。常量落 `server/task_dispatch_contract.py`(新增,纯常量与 dataclass,无副作用导入)。

### 0.1 worker 名(bus 寻址键)

| 常量名 | 值 | 类 | 归属 |
|---|---|---|---|
| `MAIN_WORKER_NAME` | `"voice-main"` | `PipelineWorker`(既有双脑) | 既有,补 `name=` |
| `DISPATCH_WORKER_NAME` | `"task-dispatch"` | `TaskDispatchWorker(UIWorker)` | 新增 |
| `EXEC_WORKER_NAME` | `"openclaw-exec"` | `OpenClawExecWorker(BaseWorker)` | 新增 |

三者挂同一个 `WorkerRunner`,均为 root worker。

### 0.2 快脑侧 function-calling 工具(挂 `fast_context` 的 `tools=`)

两个工具都是模块级 `async def`,用 `@tool_options(cancel_on_interruption=False, timeout_secs=<下表>)` 修饰。
`cancel_on_interruption=False` 为强制项:用户插话不得撤销已发起的派活(依据 `research/pipecat-worker-source-verification.md` §5.3)。

**T1 `dispatch_task`**

| 项 | 约定 |
|---|---|
| 签名 | `async def dispatch_task(params: FunctionCallParams, request: str) -> None` |
| docstring 首行(即 LLM 见到的描述) | `Hand a task the user asked for to the background agent. Use it when the user asks for something to be done rather than answered.` |
| `request` 参数说明 | 用户这一轮的原始诉求原文,不做改写、不做拆分(拆分由第二个 LLM 负责) |
| `timeout_secs` | `20.0` |
| 内部动作 | `await app_resources.main_worker.job(DISPATCH_WORKER_NAME, payload={"query": request})` |
| `result_callback` 成功载荷 | `{"accepted": true, "note": "<第二个 LLM 给出的 answer 原文>"}` |
| `result_callback` 失败载荷 | `{"accepted": false, "error": "<异常类名>: <消息前 200 字符>"}` |
| 超时/异常 | 不抛出,一律转成失败载荷交回 LLM(FR-1 描述里的"标准工具调用报错路径") |

**T2 `get_task_status`**

| 项 | 约定 |
|---|---|
| 签名 | `async def get_task_status(params: FunctionCallParams, lookup: str | None = None) -> None` |
| docstring 首行 | `Look up the current state of background tasks dispatched earlier in this conversation.` |
| `lookup` 语义 | 省略/`None` → 查本次会话内存注册表里全部在途 lookup;给值 → 只查该 lookup |
| `timeout_secs` | `15.0` |
| 内部动作 | 省略时对注册表逐条跑 `CMD_TASKS_SHOW`;给值时跑一次 `CMD_TASKS_SHOW`。**不得**调用 `openclaw tasks list` 的无过滤全量列表(会带出本会话之外的任务) |
| 成功载荷 | `{"tasks": [ <§0.5 TaskView> , ...]}` |
| 单条查不到 | 该条降级为 `{"lookup": "<key>", "found": false, "reason": "<stderr 首行>"}`,不使整次调用失败 |
| 注册表为空 | `{"tasks": []}` |

> 约束(源自 PRD FR-2 描述,不可违背):`events_wait` 绝不出现在任何 LLM 工具里。本节两个工具只调同步短命令。
>
> **时序提醒(2026-08-08 定义段内实测,`preflight-live.md` D-7;本轮由用户裁决关闭该敞口,替代原"上调 timeout_secs"处置)**:`CMD_TASKS_SHOW` 单次调用固定约 2.3-2.6 秒(node CLI 冷启动)。T2 省略 `lookup` 时对注册表逐条串行调用——**该敞口已由 §0.3 的"在途任务上限"(`MAX_INFLIGHT_TASKS = 3`)关闭**:3 × 2.6s ≈ 7.8 秒,远小于本节 `timeout_secs=15.0`,`timeout_secs` 维持不动,**无联测待办**。

### 0.3 派活 worker(`TaskDispatchWorker(UIWorker)`)对外契约

| 项 | 约定 |
|---|---|
| 入站 job 名 | `"respond"`(`UIWorker` 内置 `@job(name="respond", sequential=True)`,不重定义) |
| 入站 payload | `{"query": "<用户原话>"}`(`UIWorker.render_query` 默认读 `payload["query"]`) |
| 出站 job 响应 | 由 `respond_to_job(answer=...)` 产生,`tts_speak` 保持默认 `False`(措辞归快脑,与 PRD C1 口径一致) |
| 本期禁用能力 | `start_ui_job_group` / `ui_job_group` 四信封 / `__cancel_job_group`。**代码内不得出现这些调用点**,由 C-16 静态断言守住 |
| 自带工具 | 单个 `@tool(cancel_on_interruption=False, timeout_secs=30)` 方法 `reply(self, answer: str, tasks: list[str] | None = None)` |
| `reply.answer` 语义 | 交回快脑的一句话素材(例:已经把三件事派出去了),快脑据此自行措辞 |
| `reply.tasks` 语义 | 第二个 LLM 决定真正要派的任务书列表;`None` 或空列表 = 判断这轮不需要派活 |
| `reply` 内部次序 | **0**(本轮新增,见下方"在途任务上限"块)在①之前先做上限检查,超限则整批拒绝并跳过①②的原次序;未超限时:①对 `tasks` 每项调 `self.create_task(...)` 起一个**不等待**的 `self.job(EXEC_WORKER_NAME, payload=<§0.4>)`;②立即 `await self.respond_to_job(answer)` |

**次序是硬约束**:`reply` 不得 `await` 执行 job 的完成,否则快脑那一轮会被拖住(FR-1 判据 1 当场破功)。

**在途任务上限(2026-08-08 用户裁决新增,替代原"上调 §0.2 T2 timeout_secs"方案)**

> 定位声明:这是**实现约束**,为满足 PRD 既有 FR-2 判据 3("状态查询不拖慢对话")、关闭 D-7 时序敞口而在实现侧加的一条硬上限——**不是新 FR**,PRD 冻结件一个字不改,design/contract 全文不得称其为"FR-6"或暗示 PRD 新增了需求。

| 常量名 | 值 | 说明 |
|---|---|---|
| `MAX_INFLIGHT_TASKS` | `3` | 用户拍定,**不做可配置项**(不进 `.env.example`,不读环境变量);同 §0.1 常量落 `server/task_dispatch_contract.py` |
| `CAPACITY_MESSAGE` | `"In-flight task limit (3) reached; none of the newly requested tasks were dispatched."` | 达上限时替代第二个 LLM 自己写的 `answer`,作为 `respond_to_job` 的载荷文本(英文诊断串,不直接讲给用户——由快脑经既有报错路径自行措辞,与既有 CLI stderr 错因串同一性质) |

**行为约定(逐条写死,不留含糊)**:

1. **检查点**:`TaskDispatchWorker.reply()` 内部,在原步骤①(起 exec job)之前。这是唯一能同时看到"当前在途条数"(查 `DispatchRegistry`)与"这批 fan out 出的完整 `tasks` 列表"的时点。
2. **判定条件**:`len(DispatchRegistry) + len(tasks) > MAX_INFLIGHT_TASKS` → 超限。
3. **fan out 一次性超限(第二个 LLM 一次拆出多条 task、合计超过上限)的处置**:**整批全部拒绝,不做部分截断**——即使其中一部分原本在余量之内,`tasks` 列表里的全部条目均不派发,一个 exec job 都不起,不写入注册表。选择"全有全无"而非按余量部分派发的理由:部分派发需要额外定义"选哪几条、弃哪几条"的排序/优先级策略,是无 PRD/实测依据支撑的纯自研判断;全有全无判定简单、确定、可测试,契合"自研面最小"(完整论证见 design.md ADR-8)。
4. **超限时的对外表现**:①**不执行原步骤①**——不起任何 exec job;②`reply()` 改为 `await self.respond_to_job(answer=CAPACITY_MESSAGE, status=JobStatus.ERROR)`(`UIWorker.respond_to_job` 官方原生支持 `status` 关键字参数,`design.md` P-09 已实锤,不引入 `send_job_response`);**不使用第二个 LLM 自己生成的 `answer`**(它是在不知道上限存在的前提下写的,可能与"实际什么都没派"这一事实不符)。
5. **传导路径(复用既有报错路径,零新增措辞层)**:`status=JobStatus.ERROR` 经既有 job 机制传回主 worker 侧、被 `dispatch_task`(§0.2 T1)"超时/异常一律转成失败载荷交回 LLM"这条既有处理原样接住,产出 `{"accepted": false, "error": "In-flight task limit (3) reached; ..."}`;快脑据此**自行措辞**告知用户(与 PRD C1、FR-1 既有报错路径口径一致,不新增专门报错话术层)。用户具体听到什么由快脑决定,本约定只钉死"这次工具调用必须被判定为失败、错误文本是什么"。
6. **未超限**:不受影响,按原①②次序继续。
7. **在途计数递减时点**:与 `DispatchRegistry` 既有"移除时机"一致——收到该任务的结论消息事件(`raw.message.stopReason == "stop"`)后从注册表移除那一刻(design.md 数据模型 §2,本轮同步订正了该表里遗留的过期措辞)。**已知边界(呼应 PRD 非目标条目 11,不新增兜底)**:若某任务落入非目标条目 11 的三种异常形态(前置校验拒绝/precheck 失败/`lost`,均实测确认零 assistant 事件),该任务会永久占用一个上限名额直至本次通话结束——本期不做超时回查兜底,已记入 design.md 风险节 R-10。

### 0.4 执行 worker(`OpenClawExecWorker(BaseWorker)`)对外契约

| 项 | 约定 |
|---|---|
| 入站 job 名 | `"dispatch"`,声明为 `@job(name="dispatch", sequential=False)` |
| 入站 payload | `{"session_key": "<§0.6 生成>", "label": "<不超过 40 字的一句话摘要>", "task": "<完整任务书正文>"}` |
| 出站 job 响应 | `{"session_key": ..., "lookup": ..., "degraded": null|"<原因码>"}`(**本轮删除 `notify_set` 字段**——随原 FR-4 通知策略整条删除,本 worker 不再调用 `tasks notify`) |
| 失败响应 | `send_job_response(job_id, {"error": "..."}, status=JobStatus.ERROR)` |
| 并发 | `sequential=False`,多任务并行在途(FR-4,原 FR-5) |
| 额外职责 | 持有 `openclaw mcp serve` stdio 子进程 + `events_wait` 后台 asyncio task(§0.8) |

`degraded` 原因码封闭集:`"task-record-not-visible"` / `"mcp-bridge-down"`(**本轮删除 `"notify-set-failed"`**,理由同上)。

### 0.5 `TaskView`(工具回给 LLM 的任务视图,只做字段挑选,不新造语义)

从 `openclaw tasks show <lookup> --json` 的输出中挑选下列字段透传,不改名、不改值、不补默认值:

`taskId` / `runtime` / `status` / `notifyPolicy` / `deliveryStatus` / `createdAt` / `startedAt` / `endedAt` / `error` / `progressSummary` / `terminalSummary` / `childSessionKey` / `ownerKey`

**恒在字段 vs 条件字段(2026-08-08 定义段内实测回写,`preflight-live.md` D-5)**:`taskId` / `runtime` / `status` / `notifyPolicy` / `deliveryStatus` / `createdAt` / `startedAt` / `endedAt` / `childSessionKey` / `ownerKey` 为**恒在字段**(实测 succeeded 任务的顶层键逐一核对存在);`error` / `progressSummary` / `terminalSummary` 为**条件字段**(实装"有值才输出",未设置即不出现在记录里——如 F6 案例的 `failed` 记录就没有 `terminalSummary`)。解析一律用 `.get()` 容缺读法,不得按必填字段取;取不到的条件字段在透传给 LLM 的载荷里直接省略该键,不补 `null`/默认值(遵循"不补默认值"的既有约束)。

**本轮删除字段**:`label`——`openclaw agent --help` 与源码双证实测**无** `--label` 参数,该字段无法由外部命令设置,只能由本项目内存里的 `DispatchRegistry.label`(第二个 LLM 给的一句话摘要)承载,不放进 `TaskView`,避免两个不同来源的"label"互相混淆。素材注入模板改用 `DispatchRegistry.label`,见 §0.9。

本项目额外附加两个字段(只为对齐会话内标识,不参与任何判定):`"lookup"`(本次查询用的键)、`"found": true`。

> 字段名来源:openclaw 源码 `openclaw-src/task-registry.store-CssXnO54.js:114-151` `rowToTaskRecord` 的返回对象(2026-08-08 codegraph 实读)。实机 `--json` 输出的顶层结构已实测核对(`preflight-live.md` D-5);另有 `sourceId`/`requesterSessionKey`/`scopeKind`/`agentId`/`requesterAgentId`/`runId`/`task`/`lastEventAt`/`cleanupAfter` 等字段实机存在但本节未选入 `TaskView`,是否纳入留待后续按需扩展,本轮不新增选取范围。

### 0.6 会话键(session key)生成规则 —— 本变更的关联主键

```
SESSION_KEY_TEMPLATE = "agent:{agent_id}:voice-agent-{token}"
```

- `agent_id`:取配置项 `OPENCLAW_AGENT_ID`(`.env`,占位符 `CHANGE_ME_OPENCLAW_AGENT_ID`);本机现有可选值实测为 `main` / `dev`(`openclaw agents list --json`)。
- `token`:`uuid4().hex[:12]`。
- **由 voice-agent 侧先生成、再随 `--session-key` 传给 CLI**,因此派发瞬间即持有 lookup,不必等 CLI 退出。这是 FR-2 / FR-4(原 FR-5)/ FR-5(原 FR-6)共同的关联锚点(**本轮删除对原 FR-4"通知策略设置键"这一用途的引用**,该 FR 已整条删除)。
- **本轮实测确认**(`preflight-live.md` §2):自生成 key 直接作为 `tasks show` 的 lookup 可精确命中(exit=0),`childSessionKey`/`ownerKey`/`requesterSessionKey` 三者均与生成的 key 相等(是相等,不是前缀/后缀关系),本节设计前提成立。

### 0.7 openclaw 外部命令契约(argv / 退出码 / 判读)

以下 argv 形态与退出码均为 2026-08-08 本机实测(证据见 design.md `## 现状盘点` preflight 块),版本前提 `OpenClaw 2026.7.1-2 (0790d9f)`。

| 常量名 | argv | 阻塞性 | 退出码判读 |
|---|---|---|---|
| `CMD_AGENT` | `openclaw agent --agent <agent_id> --session-key <session_key> --message-file <path> --json` | 长(默认 `--timeout` 600 秒);**detached spawn,不等待** | 0=该轮 CLI 调用本身跑完(**仅供旁路日志观测,不进入任何判定路径**——`preflight-live.md` D-11 实测该退出码/stdout 终态可能与任务记录终态互相矛盾,如 F6 案例 CLI 报 `ok`/`completed` 而任务记录为 `failed`,不可用退出码判派活结果);非 0=CLI 层面派发失败(发生在任务被 OpenClaw 状态机接管之前),stderr 首行即错因,经 FR-1 标准工具调用报错路径回流 |
| `CMD_TASKS_SHOW` | `openclaw tasks show <lookup> --json`(`<lookup>` 接受 task id / run id / session key) | 短(同步,固定约 2.3-2.6 秒,见硬性约定 7) | 0=命中,**JSON 写在 stderr、stdout 为空**(见下方硬性约定 6);1=未命中,stderr 首行 `Task not found: <lookup>. ...` |
| `CMD_MCP_SERVE` | `openclaw mcp serve` | 常驻 stdio 子进程 | 进程存活即视为在位;stderr 出现 `MCP server failed to start` 视为 `mcp-bridge-down` |

**本轮删除 `CMD_TASKS_NOTIFY` 常量**(原 `openclaw tasks notify <lookup> done_only`)——随原 FR-4(通知策略显式设置)整条删除,理由见硬性约定 2 与 `preflight-live.md` §3.4、D-4、D-6:CLI 派发的任务 `deliveryStatus` 恒为 `not_applicable`(无 IM 渠道归属,该步骤零作用),且 running 期间调用退出码 0 但策略并未落库。

硬性约定:

1. **不传 `--deliver`**。派活回复不得被投递到任何 IM 渠道(默认 false,保持默认)。
2. **不传 `--timeout`**,沿用 OpenClaw 默认 600 秒。**本轮实测修正(D-8,原表述与实测不符)**:超时中止落的原生终态是 **`cancelled`**,不是 `timed_out`(`timed_out` 本轮全部真机派发一次未出现过);中止的 `stopReason` 映射落 `cancelled`,与显式取消同一终态,只能靠 `error` 文案区分(超时=`"agent run aborted"`,显式取消=`"Cancelled by operator."`)。该次任务的 assistant 事件 `raw.message.stopReason=="aborted"`、`text` 为空串,不满足 §0.9 的播报筛选口径,**不产生播报**,用户不会主动收到超时通知(落入 PRD 非目标条目 11)。
3. `--message-file` 而非 `-m`:任务书正文为任意中文长文本,走文件避免 argv 转义与长度限制。临时文件落 `tempfile.mkdtemp()`,由起进程的那个 asyncio task 在子进程退出后删除。
4. **detached spawn**:`asyncio.create_subprocess_exec(..., start_new_session=True)`,使 voice-agent 侧的 `worker.cancel()` / 进程组信号不连带杀掉 CLI(FR-1 判据 2 的实现前提;是否真的隔开由 C-02 证伪)。
5. `--status` 不做本地合法性校验会静默返回空列表(实测 `--status bogus` exit=0、`count=0`),因此本项目**不使用** `tasks list --status`,一律用 `tasks show <lookup>` 精确查。
6. **`tasks show --json` 的成功输出在 stderr,不在 stdout**。2026-08-08 实测(OpenClaw 2026.7.1-2):同一次命中查询 `2>/dev/null` 后 stdout 为 0 字节,`1>/dev/null` 后 stderr 为 913 字节的完整 JSON;同版本 `tasks list --json` 反而走 stdout(4006 字节),两者不一致。故实现侧捕获 `CMD_TASKS_SHOW` 输出必须读 **stderr**(或合并 `stderr→stdout`),命令行接管道时必须先写 `2>&1`;照 stdout 实现会拿到空串并把每次状态查询都误判成失败。
7. **时序开销(D-7)**:`tasks show` 单次调用固定约 2.3-2.6 秒(node CLI 冷启动,四次实测:2.52/2.60/2.50/2.31)。派发发起后约 2.6 秒内查询同一个刚生成的 lookup 会返回未命中(exit=1,`Task not found: ...`),与真正不存在的 lookup 输出**完全相同、不可区分**——design.md 装配链步骤9(exec worker 派发后轮询 `tasks show` 直到命中,上限 30 秒)与本节 §0.2 T2"单条查不到"降级为 `{"found": false}`(而非报错)的既有处理方式已经能吸收这个窗口,本轮不新增专门的宽限期重试逻辑。

### 0.8 MCP bridge 契约(`openclaw mcp serve` stdio)

2026-08-08 实测握手(JSON-RPC over stdio,`initialize` + `tools/list`)得到的工具清单,共 9 个:

`conversations_list` / `conversation_get` / `messages_read` / `attachments_fetch` / `events_poll` / `events_wait` / `messages_send` / `permissions_list_open` / `permissions_respond`

本期只用 `events_wait`。硬性约定(**本轮全量回写**,2026-08-08 定义段内提前真机验证,`preflight-live.md` §3.3、§8、§10 D-2/D-3/D-10,原样样本 `baseline/mcp-event-sample.json`/`baseline/failure-path-samples.json`,P-06 敞口已关闭):

1. `events_wait` 只在 `OpenClawExecWorker` 自己的后台 asyncio task 内调用,**不注册给任何 LLM**。
2. **不使用** pipecat `MCPClient.register_tools()` / `register_tools_schema()`——它把 MCP 工具全量注册成 LLM 函数,会同时把 `events_wait`(可阻塞 300 秒)与 `messages_send`(可对外发消息)暴露给模型。理由与替代见 design.md ADR-3。
3. `events_wait` 命中时返回 `structuredContent.event`**单数对象**,顶层键 `cursor`/`messageId`/`messageSeq`/`raw`/`role`/`sessionKey`/`type`,**`text` 为条件键**(工具调用消息顶层无此键,解析须 `.get()` 容缺,依据 D-10);超时(默认 30 秒、单次上限 300 秒 `EVENTS_WAIT_TIMEOUT_LIMIT_MS`)返回 `{"event": null}`,`content[0].text == "timeout"`。
4. **不返回 `next_cursor`**:消费者必须自行从命中事件的 `event.cursor` 字段推进下一次调用的游标(`events_poll` 才返回复数 `events`+`next_cursor`,但它只 filter 不消费队列,本期不用它做事件消费)。**踩坑(实现时必须避开)**:若误把 `events_poll` 的 `next_cursor` 字段名套用到 `events_wait` 上,游标会恒为 0,`waitForEvent` 命中即同步返回、根本不阻塞,形成无 sleep 死循环(实测 40 秒写出 812MB 日志)。
5. 事件队列是**每个 `openclaw mcp serve` 进程各自的内存队列**,cursor 从 1 起自增,上限 1000 条滚动丢弃;**连接建立之前发生的事件取不回**(实测:新起连接后 `events_poll(after_cursor=0)` 返回 0 条)。因此 `OpenClawExecWorker` 的 bridge **必须在派发之前就连上并开始消费**,否则整个任务的事件会全部漏掉——bridge 连接在 worker 就绪(`on_worker_ready`)时即起,不等首次派活触发。
6. `session_key` 过滤是**精确相等**匹配(`event.sessionKey === filter.sessionKey`),传 §0.6 生成的 key 即可精确订阅单个任务。
7. **事件类型全集(实装 6 处 `enqueue` 逐一核对)为 `message` 一种消息事件 + 5 种审批类事件**(`claude_permission_request`/`exec_approval_requested`/`exec_approval_resolved`/`plugin_approval_requested`/`plugin_approval_resolved`)——**不存在任何任务生命周期/终态事件类型**(D-2)。唯一与任务相关的信号是 `type=="message"` 且 `role=="assistant"` 的事件;其 `raw.status` 是消息产出瞬间的**会话级**状态(实测恒为 `"running"`),**不是**任务终态,不得读作终态。
8. `role=="assistant"` 的事件按 `raw.message.stopReason` 分三态(D-10):`toolUse`(工具调用消息,顶层**无 `text` 键**,文本在 `raw.message.content` 内;或过程播报,`text` 为自然语言中间话)、`aborted`(中止瞬间,`text` 为空串 `''`,`raw.message.errorMessage` 有值)、`stop`(收尾结论)。**只有 `stopReason == "stop"` 的事件是要播的结论消息**,其余(含该键缺失)一律丢弃,不注入、不计入任何后续判断——完整筛选规则与承载模板见 §0.9。
9. 事件 → 素材的映射只允许依赖两项:①能标识是哪个任务(`event.sessionKey` 与 §0.6 生成的 key 精确相等);②能判断是否为结论消息的收尾标记(`raw.message.stopReason == "stop"`)。**本轮删除**"能读出 OpenClaw 原生终态字符串"这一项——事件通路上读不出任何 OpenClaw 原生终态字符串(D-2),不再是判据来源。素材本身取自 `event.text` 原文,不解析、不改写。

### 0.9 素材注入契约(回流播报,复用 R3 同构机制)

**本轮全量改写**(原模板依赖的任务终态字符串已被 D-2 证伪,本节不再含任何状态字段):

| 项 | 约定 |
|---|---|
| **筛选条件(FR-3 判据5,坑 P54 强制)** | `event.type == "message"` **and** `event.role == "assistant"` **and** `event.raw.get("message", {}).get("stopReason") == "stop"` → 播;否则(含 `role=="user"`、审批类事件、`stopReason` 为其他值或该键缺失)→ **丢弃**,不入队、不产生任何副作用、也不触发任何 `openclaw tasks show` 调用 |
| 模板常量 | `prompts.INJECT_TASK_TERMINAL_TEMPLATE`,与既有 `INJECT_*_TEMPLATE` 同列,禁内联字面串(既有约定 R4) |
| 模板文本 | `[派活回流|任务:{label}] {agent_text} 这条信息由你自行决定何时、如何说给用户。`(**本轮删除 `{status}`**,依据 D-2——事件通路上读不出任何 OpenClaw 原生终态字符串) |
| `{label}` | 取自 `DispatchRegistry.label`(第二个 LLM 给的一句话摘要),**不是** `TaskView` 的字段(`TaskView` 已删 `label`,见 §0.5) |
| `{agent_text}` | 事件对象的 `event.text` 原文,不摘要、不改写、不翻译(agent 说的话可能很长,样本实测 656/657 字符,要不要摘要属快脑措辞判断范畴,PRD FR-3"沿用不变的约束"已明确,本节不设长度类判据) |
| 承载帧 | `LLMMessagesAppendFrame(messages=[{"role": "user", "content": <模板渲染结果>}], run_llm=True)`,与既有慢脑注入同角色同触发方式 |
| 入口 | 快脑分支头部的 `_DispatchMaterialInjector`(新增 `FrameProcessor`),从会话级 `asyncio.Queue` 取 |
| 合并规则 | 一次取空队列内全部待播报项,拼成**一条** `LLMMessagesAppendFrame`(FR-3 判据 3 的"合并/排队") |
| 安全插入窗 | 沿用既有机制:注入帧进入快脑分支后由既有轮次/打断语义决定播出时机,本变更不新增时序控制 |

### 0.10 测试开关(仅验收期开启,产品路径默认关闭)

下面这个开关只为 §1 用例的前置条件而存在,产品运行路径永远走「未设置」分支。名字常量与 §0 其余常量同处 `server/task_dispatch_contract.py`,任何组件不得内联这个字面串。**本轮删除 `ENV_TASK_DISPATCH_SKIP_NOTIFY` 开关**(原为 C-13 服务,随原 FR-4 通知策略与 C-13 一并删除,`CMD_TASKS_NOTIFY` 已不存在,该开关无对象可跳过)。

| 常量名 | 值(环境变量名,逐字) | 用途 | 取值语义 | 消费方 |
|---|---|---|---|---|
| `ENV_TASK_DISPATCH_CLI` | `"TASK_DISPATCH_CLI"` | C-01 的桩模式开关:把派发那一步换成一条可控的长时命令,用于证明派活期间对话不被阻塞 | 未设 / 空串 → 走真实 `openclaw`(默认);设为可执行文件路径 → 该路径**只替换 §0.7 `CMD_AGENT` argv 的第 0 位**(程序名),argv 其余部分逐字不变,`CMD_TASKS_SHOW` / `CMD_MCP_SERVE` 不受影响 | 读取点:`server/bot.py` 装配期(函数体内读取后以关键字参数下传;派活栈模块内不读环境变量)。验收侧:C-01 前置(桩脚本 `sleep 600` 后退出 0) |

该开关不是产品配置项:不进 `.env.example` 的必填段,不参与 §0.6 会话键生成,也不改变 §0.7 任何一条 argv 的其余部分。

---

## §1 验收用例

判定统一口径:
- 命令一律在 `/home/ky/git/voice-agent` 下执行;凡启动 `bot.py`/`pytest` 必带 `NLTK_DISABLE_IMPORT_SECURITY=1`。
- **命令口径(本节每条命令均于 2026-08-08 在本机实跑复验,以下三点是复验中踩到的真实差异,勿按记忆改回)**:
  1. `pipecat` CLI 是**全局工具**、不在 `server/.venv` 内。`uv run pipecat ...` 会解析到 `server/.venv/bin/pipecat` 并以 exit=1 报 `The Pipecat CLI needs its optional dependencies (the "cli" extra)`——**驱动 eval 一律用不带 `uv run` 前缀的 `pipecat`**,并按 README:109-115 预置 `set -a && source .env && set +a` 与 `PYTHONPATH="$(pwd)"`(`judge_factory` 走 factory judge 时必需)。
  2. `openclaw tasks show --json` 命中时把 JSON 写在 **stderr**(§0.7 硬性约定 6),凡接管道必须先 `2>&1`。
  3. 本机**没有 `python` 命令**(只有 `/usr/bin/python3`),且仓库根目录**没有 `tests/` 与 `evals/`**——两者都在 `server/` 下。故项目内跑 pytest 一律 `cd server && ... uv run python -m pytest ...`,跑 eval 一律 `cd server && ... pipecat eval run evals/<name>.yaml`。
- "证据"列写的是可被第三方复核的可观测事实,不接受主观描述。
- 每条用例结果连同原始输出摘要写进 `test-report.md` 判据核对表。

### C-00 · 环境前置门(不覆盖 FR,是其余用例的前置)

- **前置**:无。
- **步骤**:
  1. `openclaw daemon status`
  2. `ss -ltnp | grep 18789`
  3. `openclaw approvals get --json | python3 -c "import json,sys; d=json.load(sys.stdin); [print(s['scopeLabel'], 'mode='+s['mode']['effective'], 'security='+s['security']['effective'], 'ask='+s['ask']['effective']) for s in d['effectivePolicy']['scopes']]"`(原写法 `python3 -m json.tool | grep -A2 '"ask"'` 只打得出 `requested`/`requestedSource`,打不出期望③要判的 `effective`,故换成直接打生效值)
- **期望**:①`daemon status` 显示服务已启用且在跑;②18789 端口有监听进程;③生效策略中不存在会触发运行时审批的档位(即 `mode` 不为 `ask`,或 `security=allowlist` 且本次任务用到的命令已在白名单内)。
- **判定**:三项全满足才放行后续用例。任一项不满足 → 本轮验收结论直接写"环境未就绪",不得把失败归因到实现代码。
- **反证记录**:2026-08-08 S2a preflight 实测三项均**不满足**(见 design.md P-05/P-06),本条即为此设。
- **复验记录**:同日晚些时候三项已全部满足——`daemon status` 输出 `Service: systemd user (enabled)` + `Runtime: running (pid 327897, ...)` + `Connectivity probe: ok`;`ss -ltnp` 见 127.0.0.1:18789 与 [::1]:18789 两条 LISTEN;步骤 3 输出 `tools.exec mode=full security=full ask=off` 与 `agent:dev mode=full security=full ask=off`。环境是**可变的**,本门仍须在每轮验收当场重跑,不得援引本条复验结果放行。

### C-01 · 派活期间对话不被阻塞(FR-1 判据 1)

- **前置**:C-00 通过;桩模式开启(环境变量 `TASK_DISPATCH_CLI=<桩脚本路径>`,桩脚本 `sleep 600` 后退出 0)。
- **步骤**:
  1. `cd server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run bot.py -t eval 2>&1 | tee /tmp/pipecat-dispatch.txt`
  2. 另一终端:`cd server && set -a && source .env && set +a && PYTHONPATH="$(pwd)" NLTK_DISABLE_IMPORT_SECURITY=1 pipecat eval run evals/dispatch_nonblocking.yaml -v --logs-dir eval-runs`
  3. 场景内容:第 1 轮说一句触发派活的请求;第 2 轮紧接着问一个无关问题。
- **期望**:第 2 轮 `response` 事件在场景默认响应窗内产生;`eval run` 退出码 0;`/tmp/pipecat-dispatch.txt` 内可见派活工具被调用的日志行,且该行时间戳早于第 2 轮 response。
- **判定**:退出码 0 且日志时间戳次序成立 → 通过。桩脚本仍在 `sleep` 期间第 2 轮已答完,是本用例的核心证据。

### C-02 · 断连后任务在 OpenClaw 侧继续(FR-1 判据 2;同时是 PRD C4 处置的证伪点)

- **前置**:C-00 通过;真实 CLI(非桩);派发一个预计运行 3 分钟以上的任务。
- **步骤**:
  1. 通话中派发一个任务,记下日志里打印的 session key `K`。
  2. `openclaw tasks show "$K" --json`(断连前),记录 `status`。
  3. 断开语音客户端(触发 `on_client_disconnected` → `worker.cancel()`)。
  4. 等 30 秒,再次 `openclaw tasks show "$K" --json`。
  5. 再等到该任务自然结束,第三次 `openclaw tasks show "$K" --json`。
- **期望**:第 4 步 `status` 不是 `cancelled`;第 5 步 `status` ∈ {`succeeded`,`failed`,`timed_out`,`lost`}。
- **判定**:两条同时成立 → 通过。若第 4 步为 `cancelled`,则 PRD C4 的处置被证伪,**停止实现、上报主会话**(反证条件已由 PRD C4 写明)。

### C-03 · 既有 eval 场景集无新增失败(FR-1 判据 3;C2 处置)

- **前置**:改动已落地。
- **步骤**:对 `server/evals/` 下除 `r4_no_false_completion.yaml` 外的既有场景逐个执行
  `cd server && set -a && source .env && set +a && PYTHONPATH="$(pwd)" NLTK_DISABLE_IMPORT_SECURITY=1 pipecat eval run evals/<name>.yaml -v --logs-dir eval-runs`。
- **期望**:每个场景退出码 0;失败集合与改动前基线(见 C-17)完全一致。
- **判定**:出现改动前通过、改动后失败的场景 → 不通过,归因 `prompts.py` 或 tools 引入。

### C-04 · 派发调用本身失败时经工具报错路径回流(FR-1 描述末段)

- **前置**:C-00 可跳过;把 `OPENCLAW_AGENT_ID` 设为一个不存在的 agent id(实测负向:缺少可解析目标时 CLI exit=1)。
- **步骤**:运行 `evals/dispatch_cli_failure.yaml`,场景内说一句触发派活的话。
- **期望**:①`OpenClawExecWorker` 的 job 以 `JobStatus.ERROR` 回报,日志含 CLI stderr 首行;②快脑仍产生一次 `response`,且未声称任务已完成。
- **判定**:judge 判据 `回复表达了这件事没能派出去/出了问题,没有声称已经完成或已经处理好` 通过 → 通过。措辞本身不做比对(PRD C1 口径)。

### C-05 · 单任务状态查询(FR-2 判据 1)

- **前置**:C-00 通过;会话内已成功派发过一个任务,内存注册表有一条记录。
- **步骤**:
  1. 通话中问"我那个任务现在怎么样了"。
  2. 旁路核对:`time openclaw tasks show "$K" --json`。
- **期望**:①日志显示 `get_task_status` 被调用一次,回给 LLM 的载荷含 §0.5 全部**恒在字段**;条件字段(`error`/`progressSummary`/`terminalSummary`)按该次任务记录实际存在情况透传,不因某条件字段未出现而判定失败(依据 D-5);②旁路命令 `real` 时间 < 5 秒;③快脑据此产生一次 `response`。
- **判定**:三项成立 → 通过。

### C-06 · 全部在途任务查询(FR-2 判据 2)

- **前置**:同 C-05,且会话内已派发 ≥2 个任务。
- **步骤**:通话中问"我现在有哪些任务在跑"。
- **期望**:`get_task_status` 以 `lookup=None` 被调用一次,返回 `tasks` 数组长度等于内存注册表条数;每条含各自的 `lookup` 与 `status`。
- **判定**:数组长度与注册表条数一致且 lookup 互不相同 → 通过。

### C-07 · 状态查询不拖慢对话(FR-2 判据 3)

- **前置**:同 C-05。
- **步骤**:同一次通话内,在状态查询轮之后紧接着问一个无关问题。
- **期望**:后一轮 `response` 正常产生,退出码 0。
- **判定**:与 C-01 同口径。

### C-08 · lookup 不存在的负向路径(FR-2 描述末段)

- **前置**:无。
- **步骤**:
  1. 命令层:`openclaw tasks show no-such-task-id-xyz --json; echo "exit=$?"`
  2. 应用层:在通话中问一个不存在的任务号的状态。
- **期望**:①命令层 exit=1,stderr 首行为 `Task not found: no-such-task-id-xyz. Run ...`;②应用层工具返回 `{"lookup": ..., "found": false, "reason": ...}` 而**不是**抛异常,快脑仍产生一次 `response`。
- **判定**:两项成立 → 通过。本条是 P54 负向路径的强制覆盖项。

### C-09 · 结论消息回流播报走单一既有通道(FR-3 判据 1、判据 2;本轮据 D-2/D-10 整段重写)

- **前置**:C-00 通过。
- **步骤**:
  1. 结构性验证:`cd server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest tests/ -q -k AssemblePipeline`(**本轮修正落点**,主会话过目实测发现原命令 `tests/test_bot.py -q -k assembled` exit=5、0 命中——`grep -rn "AssembledPipeline" server/tests/` 零命中,`test_bot.py` 实测只有 4 条 provider builder 测试、不含任何结构断言;真正的管线结构断言在 `server/tests/test_dual_brain.py::TestAssemblePipeline`,新命令实测 `5 passed, 44 deselected, exit=0`)。**在该既有类内扩写/新增测试方法**(不新起断言文件、不新增 `import bot` 的测试文件——D-003 守法③,`test_dual_brain.py` 的 `bot_module` fixture 已在 T5.1 挪至 `tests/conftest.py`、自身零 `sys.modules` 用法,详见 design.md §E L2 回写),断言 `AssembledPipeline` 里对外输出分支数量与派活前一致(仍只有快脑分支含 `transport.output()`),且新增的 `_DispatchMaterialInjector` 位于快脑分支且不含任何输出组件——与该类既有 `test_pipeline_shape` 方法断言的"consumer 必须在快脑分支内、慢脑分支不得含 `transport.output()`/TTS"是同一形状的直接延伸。
  2. 行为验证(判据 1,正向):桩投递一条 `stopReason=="stop"` 的结论消息事件(取 `baseline/mcp-event-sample.json` 里 cursor=2 的原样样本,该样本 `raw.message.stopReason` 实测即为 `"stop"`),直接向会话级注入队列 put,跑 `evals/dispatch_terminal_report.yaml`。
  3. 行为验证(判据 2,负向):桩投递同一次派发的 `role=="user"` 的 `message` 事件(取同一样本 cursor=1),断言不产生任何播报、不注入任何素材。
  4. 否定核对(判据 1"不回查任务状态"半句):对 CLI 调用层打桩计数,断言步骤 2 的回流路径中 `openclaw tasks show` 调用次数为 0。
- **期望**:①pytest 通过;②步骤 2 观测到恰好一次 `response`,内容与该任务相关;③步骤 3 零播报;④步骤 4 计数为 0。
- **判定**:四项成立 → 通过。播报措辞不做语义比对(PRD FR-3 判据 1 明写)。

### C-10 · 并发结论消息合并播报(FR-3 判据 3)

- **前置**:同 C-09。
- **步骤**:在没有空闲插入窗的间隔内(两次 put 间隔 < 200ms)向注入队列连续 put 两条不同任务的结论消息事件(均为 `stopReason=="stop"`),跑 `evals/dispatch_terminal_merge.yaml`。
- **期望**:①`_DispatchMaterialInjector` 只产生**一条** `LLMMessagesAppendFrame`,其 content 同时含两个任务的 label;②只观测到一次 `response`,未出现两次抢话。
- **判定**:注入帧计数 == 1 且 response 计数 == 1 → 通过。计数由单元测试直接断言 + eval 日志双证。

### C-11 · 后台长轮询不阻塞对话(FR-3 判据 4)

- **前置**:C-00 通过;MCP bridge 在位且当前无事件(`events_wait` 处于等待态)。
- **步骤**:在 bridge 处于等待态期间跑 `evals/dispatch_nonblocking.yaml` 的第二轮提问部分。
- **期望**:提问正常获得 `response`,退出码 0;`/tmp/pipecat-dispatch.txt` 中同期可见 `events_wait` 仍在等待的日志行。
- **判定**:两项同时成立 → 通过。证明长轮询确实在独立 asyncio task 内。

> **本轮删除 C-12/C-13**(原"通知策略被显式设置(FR-4 正向)"/"不设策略则静默失效(FR-4 反证)")——随原 FR-4(通知策略显式设置)整条删除,依据 `preflight-live.md` §3.4、D-4、D-6:CLI 派发的任务 `deliveryStatus` 恒为 `not_applicable`,该步骤对本项目零作用;running 期间调用 `tasks notify` 退出码 0 但策略未落库。§0.7 的 `CMD_TASKS_NOTIFY` 常量与 §0.10 的 `ENV_TASK_DISPATCH_SKIP_NOTIFY` 开关同步删除。

### C-14 · 多任务互不串扰(FR-4,原 FR-5)

- **前置**:C-00 通过。
- **步骤**:
  1. 同一通话内先后派发任务 A、B,分别记 `K_A`、`K_B`(两者必须不同)。
  2. 让 A 先到终态,B 仍在跑。
  3. `openclaw tasks show "$K_A" --json` 与 `openclaw tasks show "$K_B" --json` 各查一次。
  4. 观察播报。
- **期望**:①`K_A != K_B`;②A 为终态、B 为非终态;③播报里出现的 label 是 A 的 label,且未出现 B 已完成的表述。
- **判定**:三项成立 → 通过。

### C-15 · 手动接管可达性(FR-5,原 FR-6)

- **前置**:C-00 通过;已完成一次派发,持有 `K`。
- **步骤**:`openclaw tasks show "$K" --json 2>&1 | python3 -c "import json,sys; d=json.load(sys.stdin); print(repr(d.get('childSessionKey')), repr(d.get('ownerKey')))"`(`2>&1` 不可省,理由见 §0.7 硬性约定 6)
- **期望**:至少一个为具体非空字符串,且与 §0.6 生成的 `K` 可关联(相等,或以 `K` 为前缀/后缀的结构化键)。
- **判定**:成立 → 通过。可选加测(IM 渠道路由)按 PRD FR-5(原 FR-6)原文由 QA 依现有渠道配置决定是否执行,不做则在报告里写明未执行及原因。

### C-16 · 本期未启用 ui_job_group 链路(落实 `research/pipecat-worker-source-verification.md` §6 条目 1)

- **前置**:无。
- **步骤**:`grep -rn "start_ui_job_group\|ui_job_group\|__cancel_job_group" server/ --include=*.py --exclude-dir=.venv --exclude-dir=__pycache__`(两个 `--exclude-dir` **不可省**:本仓 venv 落在 `server/.venv`,内含框架自身的 `ui_job_group` 源码;2026-08-08 实测不排除时命中 34 行、排除后 0 行,零命中永不可达。与下方 yaml 块的 `cmd` 逐字一致)
- **期望**:零命中(除注释性说明外)。同时 `tests/test_task_dispatch.py` 内有一条静态断言测试直接断言 `TaskDispatchWorker` 的类体内不引用这些符号。
- **判定**:grep 零命中且该测试通过 → 通过。
- **说明**:官方对 `UIJobGroupContext` 无覆盖测试,本期以"不启用"规避;将来启用前必须先补四信封端到端测试,见 design.md 风险节。

### C-17 · LLM 行为基线(固定问题集真实输出样本,坑 P57)

- **前置**:在**任何代码改动之前**执行一次。
- **步骤**:
  1. 建 `server/evals/baseline_probe.yaml`,内含固定 8 问(2 条知识问答 / 2 条闲聊 / 2 条执行类请求 / 2 条多轮追问),judge 只写 `event: response` 不加语义判据。
  2. `cd server && set -a && source .env && set +a && PYTHONPATH="$(pwd)" NLTK_DISABLE_IMPORT_SECURITY=1 pipecat eval run evals/baseline_probe.yaml -v -d --logs-dir eval-runs`
  3. 把 8 条真实回复原文归档到 `pipeline/task-dispatch/baseline/pre-change-responses.md`。
  4. 改动落地后同样跑一次,归档到 `pipeline/task-dispatch/baseline/post-change-responses.md`。
- **期望**:两份归档都存在且非空;逐条人工对读,把差异记进 test-report.md。
- **判定**:两份归档齐备且差异已逐条记录 → 通过。**不设自动阈值**:本条的目的是让既有 LLM 侧缺陷在第一天暴露、不与本次改动混淆归因。

### C-18 · 非结论 assistant 事件一律丢弃(FR-3 判据 5,本轮新增,坑 P54 负向路径强制覆盖)

- **前置**:C-00 可跳过(用样本桩投递,不必真机在线)。
- **步骤**(全部素材取自 `baseline/failure-path-samples.json`,按 `cases.<id>.events_raw[i].event` 定位,原样投递不改字段):
  1. 逐条否定断言:依次桩投递 `cases.F1.events_raw[1]`(cursor=2,`stopReason="toolUse"`,顶层无 `text` 键,`raw.message.content[0].type=="toolCall"`)、`cases.F7b.events_raw[2]`(cursor=3,`stopReason="toolUse"`,`text="The command is still running. Let me poll until it completes."`)、`cases.F7b.events_raw[3]`(cursor=4,`stopReason="aborted"`,`text=""`,`raw.message.errorMessage="This operation was aborted"`),每条分别断言零播报。
  2. 整序列断言:把 `cases.F4b.events_raw` 全部 5 条(1 条 `role=user` + 3 条 `toolUse` + 1 条 `stop`)按 cursor 升序全量投递,断言播报次数恰为 1 且素材文本等于 `"F4B-DONE"`;同样把 `cases.F1.events_raw` 全部 3 条投递,断言播报次数恰为 1 且素材文本以 `"读取失败。"` 开头。
  3. 缺键容错:投递上述工具调用样本(顶层无 `text` 键、`role=user` 事件的 `raw.message` 无 `stopReason` 键)时断言不抛异常。
- **期望**:①步骤 1 三条逐一零播报;②步骤 2 两个序列播报次数均恰为 1 且文本符合;③步骤 3 全程无异常。
- **判定**:三项成立 → 通过。**反证条件(置信度约 85%,PRD FR-3 判据 5 原文)**:本用例把"结论"钉死在 `stopReason == "stop"` 上,依据是两份原样样本共 19 条 assistant 事件全部带该键、且每次派发恰有 0 或 1 条 `stop`;若实现或联测阶段观测到一条缺 `stopReason` 键、或取其他值的收尾结论消息,应回来放宽 §0.9 的筛选口径,而不是在实现里私自加分支。

### C-19 · 在途任务达上限时整批拒绝(本轮新增,实现约束验收,不映射任何 FR;支撑 FR-2 判据 3 的时序安全)

- **前置**:C-00 可跳过;会话内已有 3 个任务处于在途状态(`DispatchRegistry` 计数为 3,可用测试桩直接构造,不要求全部走真机派发)。
- **步骤**:
  1. 用测试桩使 `DispatchRegistry` 内含 3 条记录。
  2. 运行 `evals/dispatch_capacity_reached.yaml`,场景内说一句触发第 4 次派活的话(单任务或诱导第二个 LLM fan out 出多条均可,只要 `当前在途数 + len(tasks) > 3`)。
  3. 核对 `TaskDispatchWorker.reply()` 的行为:是否跳过起任何 `exec` job(exec worker 收到的新 job 计数为 0)、`respond_to_job` 是否以 `status=JobStatus.ERROR` 与 `CAPACITY_MESSAGE` 回应(日志核对)。
  4. 核对快脑侧:`dispatch_task` 的 `result_callback` 是否为 `{"accepted": false, "error": "...In-flight task limit (3) reached..."}`,快脑是否仍产生一次 `response`。
- **期望**:①exec worker 未收到任何新 job;②`respond_to_job` 调用参数核对通过(`status=JobStatus.ERROR`、文本为 `CAPACITY_MESSAGE`);③`dispatch_task` 失败载荷核对通过;④快脑产生一次 `response`,且未声称任务已派发。
- **判定**:judge 判据 `回复表达了现在派不了新任务/已经有任务在跑,没有声称已经派发或已经完成` 通过,且①②③的结构性/日志核对通过 → 通过。措辞本身不做比对(PRD C1 口径,同 C-04)。

### 机器可读用例清单(gen-contract.sh 消费)

本块是上面 C-00~C-19 的**机器可读表示**(本轮:因原 FR-4 通知策略整条删除,C-12/C-13 一并移除;因新 PRD FR-3 判据 5 的否定验证要求,新增 C-18 补齐覆盖;本轮再新增 C-19,验收"在途任务上限 3"这条实现约束——它支撑 FR-2 判据 3 但本身不映射任何 FR),不留孤儿用例、不留指向已删 FR 的行。分档标准:整条用例的全部步骤与期望都能由一条命令的退出码/输出判定的,写 `cmd` + `expect_exit`;凡含真人通话、需常驻 `bot.py` 的双终端驱动、需等待真机 OpenClaw 任务生命周期、或含人工判读分支的,写 `manual: true` + `reason`,由 qa-tester 按上文步骤人工执行并把结果写进 `test-report.md`。`cmd` 的工作目录为 `/home/ky/git/voice-agent`(与 §1 判定口径一致)。

```yaml
cases:
  - id: C-00
    manual: true
    reason: '环境前置门,不覆盖 FR。判据③(生效策略中不存在会触发运行时审批的档位,或 allowlist 已覆盖本次命令)需人工判读 approvals 输出;且任一项不满足时结论是环境未就绪而非用例失败,归因不同,不能折成单条退出码'
  - id: C-01
    fr: FR-1
    manual: true
    reason: '需双终端:一端带 TASK_DISPATCH_CLI 桩常驻 bot.py -t eval,另一端跑 eval 场景;判据还含 /tmp/pipecat-dispatch.txt 内派活日志行早于第 2 轮 response 的时间戳次序比对'
  - id: C-02
    fr: FR-1
    manual: true
    reason: '真机多步:通话中派发取会话键、断开语音客户端触发 worker.cancel()、等 30 秒与自然终态各查一次 tasks show;并含证伪分支(第 4 步为 cancelled 则停止实现并上报主会话)'
  - id: C-03
    fr: FR-1
    manual: true
    reason: '需先常驻 bot.py -t eval 再逐场景驱动;判据是失败集合与改动前基线(C-17 归档)完全一致,依赖人工对读,不是单次退出码'
  - id: C-04
    fr: FR-1
    manual: true
    reason: '需把 OPENCLAW_AGENT_ID 设为不存在的 agent id 后常驻 bot 再由 eval 驱动;判据①要在 bot 日志核对 JobStatus.ERROR 与 CLI stderr 首行,判据②由 LLM judge 语义判定'
  - id: C-05
    fr: FR-2
    manual: true
    reason: '需在真人通话中提问触发 get_task_status,并与旁路 time openclaw tasks show 对照;前置要求同一会话内已成功派发过任务、内存注册表非空'
  - id: C-06
    fr: FR-2
    manual: true
    reason: '需同一会话内已派发不少于 2 个任务后在通话中提问;判据是返回数组长度与会话内存注册表条数一致,而注册表只在运行中的 bot 进程内可见'
  - id: C-07
    fr: FR-2
    manual: true
    reason: '需在同一次通话内于状态查询轮之后紧接着追问,判据是对话轮次时序而非命令退出码'
  - id: C-08
    fr: FR-2
    manual: true
    reason: '步骤 1 命令层确定性,但步骤 2 应用层(通话中问一个不存在的任务号)必须在通话内驱动;两项判据同时成立才算通过,只跑步骤 1 会让另一半判据假通过'
  - id: C-09
    fr: FR-3
    manual: true
    reason: '步骤 1 的 pytest 结构断言可自动化;步骤 2/3 需常驻 bot、向会话级注入队列桩注入结论消息事件与 role=user 事件后跑 eval 并核对播报/零播报;步骤 4 需对 CLI 调用层打桩计数核对 tasks show 调用次数为 0;多项同时成立才通过'
  - id: C-10
    fr: FR-3
    manual: true
    reason: '需在两次 put 间隔小于 200ms 的窗口内向运行中会话的注入队列连续投两条结论消息事件,并取单元测试的注入帧计数与 eval 日志双证'
  - id: C-11
    fr: FR-3
    manual: true
    reason: '需 MCP bridge 处于 events_wait 等待态期间驱动 eval,并在同期日志中核对 events_wait 仍在等待的日志行'
  - id: C-14
    fr: FR-4
    manual: true
    reason: '需同一通话内先后派发 A、B,等 A 先到终态而 B 仍在跑,再核对播报里出现的是 A 的 label 且未出现 B 已完成的表述'
  - id: C-15
    fr: FR-5
    manual: true
    reason: '命令本身确定性,但依赖前置真机派发产出的会话键 K,且「与 K 可关联」允许相等或以 K 为前缀/后缀的结构化键,含人工判读'
  # C-16 判据两半: ①server 自有 .py 源码零命中(注释行不计) ②静态断言测试通过 —— 两半都在下面这条 cmd 里
  # grep 加 --exclude-dir=.venv/__pycache__: 本仓 venv 落在 server/.venv,内含框架自身的 ui_job_group 源码,不排除则零命中永不可达(2026-08-08 实测 34 行 vs 0 行;§1 C-16 步骤行已同步为同一条命令)
  # 静态断言测试以 -k job_group 选取;选不中时 pytest 以 exit=5 显性失败,不会假通过
  - id: C-16
    cmd: |-
      hits=$(grep -rn "start_ui_job_group\|ui_job_group\|__cancel_job_group" server/ --include=*.py --exclude-dir=.venv --exclude-dir=__pycache__ | grep -v ":[[:space:]]*#"); if [ -n "$hits" ]; then echo "C-16 grep 命中(非注释行):"; echo "$hits"; exit 1; fi; cd server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest tests/test_task_dispatch.py -q -k job_group
    expect_exit: 0
  - id: C-17
    manual: true
    reason: '需在改动前后各跑一次 8 问基线并归档两份文件,判定是差异已逐条记录进 test-report.md 的人工对读;原文明确不设自动阈值'
  - id: C-18
    fr: FR-3
    manual: true
    reason: '需要已实现的 _DispatchMaterialInjector 与桩投递机制,以 baseline/failure-path-samples.json 原样样本逐条/整序列投递并断言零播报或播报次数恰为 1,含 85% 置信度反证条件的人工判读,不是单次退出码可判定'
  - id: C-19
    manual: true
    reason: '不映射 FR(实现约束验收);需常驻 bot、桩构造 DispatchRegistry 计数为 3 后驱动 eval 触发第 4 次派活,核对 exec worker 零新增 job、respond_to_job 的 status/文本、dispatch_task 失败载荷三项结构性事实,并由 LLM judge 判定快脑回复未声称已派发'
```

---

## §2 FR 覆盖映射

**本轮按新 PRD FR-1~FR-5 重建**(原 FR-4 通知策略整条删除;原 FR-5→现 FR-4;原 FR-6→现 FR-5;FR-3 判据数由 3 条扩为 5 条)。

| FR | 覆盖用例 |
|---|---|
| FR-1 | C-01(判据1)、C-02(判据2)、C-03(判据3)、C-04(描述末段报错路径) |
| FR-2 | C-05(判据1)、C-06(判据2)、C-07(判据3)、C-08(负向) |
| FR-3 | C-09(判据1、判据2)、C-10(判据3)、C-11(判据4)、C-18(判据5) |
| FR-4(原 FR-5) | C-14 |
| FR-5(原 FR-6) | C-15 |

无未覆盖 FR。原 FR-4(通知策略显式设置)已随 PRD 修订整条删除,原对应用例 C-12/C-13 一并删除(依据见 §0.7/§0.10 回写)。另有四条不映射 FR 的用例:C-00(环境前置门)、C-16(补测试硬要求的本期落实)、C-17(行为基线)、**C-19(本轮新增,在途任务上限 3 这条实现约束的验收,支撑 FR-2 判据 3 但本身不是任何 FR 的判据,不写作 FR-6)**。

## §3 明确不覆盖的范围(与 PRD 非目标一致,不重复论证)

任务中止/取消、审批链三项、客户端进度卡、记忆系统读写对接、鉴权多用户、**通知策略设置(原 FR-4,本轮整条删除)**、**任务终态的结构化状态判定**(非目标条目9)、**任务未产出结论消息的异常路径整体不覆盖**(非目标条目11:前置校验拒绝/运行中 precheck 失败/维护扫描判定 `lost` 三种形态均实测确认无 assistant 事件产生,不设兜底用例)、**"任务看起来成功、实际没办成"的识别**(非目标条目12:含 `NO_REPLY` 静默成功、`tasks cancel` 被回滚两种形态)——均为 PRD 非目标条目,本文件不设用例。C-18 只覆盖"收到非结论 assistant 事件时正确丢弃"这一正常筛选逻辑,不构成对上述异常路径的覆盖或兜底。
