# design · task-dispatch(C4 派活)

> change_id: task-dispatch | 阶段: S2a | 日期: 2026-08-08 | base_commit: cb3e85775a87dee2afbf378ea2d06298e80f0aa8
> 上游冻结件:`prd.md`(hash a3d9e183…,5 条 FR;本轮由旧 6 条 FR 版本修订而来,取代原引用的 e8bdcb24… 版)、`research/architecture-convergence.md`(用户已确认的架构)、`architecture-diagram.json`(用户已过目;架构形态未变,未随本轮 FR 数变化重画)。
> 本文只定意图、边界与不变量,不含实现代码。契约细节全在 `contract/cases.md`,本文不复写。

---

## 现状盘点

### 1. preflight 证据块(坑 P6 / P14 / P54:逐项终端实跑,含负向路径)

版本前提:`OpenClaw 2026.7.1-2 (0790d9f)`;`pipecat-ai 1.6.0`(venv 实装);clone 副本 `~/git/source-project/pipecat` 为 `v1.7.0-36-g0db3c9a0a`。

**P-01 · openclaw CLI 存在性与本次要用到的子命令**

```
$ which openclaw; openclaw --version
/home/ky/.nvm/versions/node/v24.18.0/bin/openclaw
OpenClaw 2026.7.1-2 (0790d9f)

$ openclaw tasks --help          # 截取
Commands:
  audit / cancel / flow / list / maintenance / notify / show
Options: --runtime <name>  Filter by kind (subagent, acp, cron, cli)
         --status <name>   (queued, running, succeeded, failed, timed_out, cancelled, lost)

$ openclaw tasks notify --help   # 截取
Usage: openclaw tasks notify [options] <lookup> <notify>
Arguments: notify   Notify policy (done_only, state_changes, silent)

$ openclaw agent --help          # 截取关键项
  --agent <id> / --session-key <key> / --session-id <id> / -t,--to <number>
  -m,--message <text> / --message-file <path> / --json / --deliver(默认 false)
  --timeout <seconds>   Override agent command timeout (seconds, default 600 or config value)
```

→ 结论:PRD 引用的 `agent` / `tasks show` / `tasks list` / `tasks notify` 四条子命令全部存在,`--timeout` 默认 600 秒属实。

**P-02 · 正向读路径实跑**

```
$ openclaw tasks list --json
{ "count": 0, "runtime": null, "status": null, "tasks": [] }        exit=0

$ openclaw tasks list --status running --json
{ "count": 0, "runtime": null, "status": "running", "tasks": [] }   exit=0

$ openclaw agents list --json     # 截取
[ {"id":"main","identityName":"管家","workspace":"/home/ky/.openclaw/workspace","isDefault":true},
  {"id":"dev","workspace":"/home/ky/openclaw-workspace","isDefault":false} ]
```

**P-03 · 负向 / 边界路径实跑(坑 P54:只验成功路径不算数)**

```
$ openclaw tasks show no-such-task-id-xyz --json
exit=1  stderr: Task not found: no-such-task-id-xyz. Run `openclaw tasks list` to see recent task ids.

$ openclaw tasks notify no-such-task-id-xyz done_only
exit=1  stderr: Task not found: no-such-task-id-xyz. ...

$ openclaw agent --json                      # 缺 message
exit=1  stderr: Error: Missing message. Use openclaw agent --message "..." --agent <id> ...

$ openclaw agent -m probe --timeout 5 --json # 缺目标会话
exit=1  stderr: Error: No target session selected. Use --agent <id>, --session-key <key>, --session-id <id>, or --to <E.164>.

$ openclaw tasks list --status bogus --json
{ "count": 0, "runtime": null, "status": "bogus", "tasks": [] }     exit=0    # 非法值不报错,静默空列表
```

→ 三条设计后果,已写进 `contract/cases.md` §0.7:①未命中类错误统一 exit=1 且错因在 stderr 首行,可作为工具报错路径的判读依据;②`openclaw agent` **必须**带会话目标选择器,这直接决定了本设计"自己生成 session key"的做法;③`--status` 非法值静默返回空,与"确实没有 running 任务"不可区分,因此本项目不使用该过滤器。

**P-04 · MCP bridge 实跑握手(不是文档宣称)**

用 JSON-RPC over stdio 直连 `openclaw mcp serve`,发 `initialize` + `tools/list`:

```
INIT: {"protocolVersion":"2024-11-05","capabilities":{"experimental":{"claude/channel":{},"claude/channel/permission":{}},
       "tools":{"listChanged":true}},"serverInfo":{"name":"openclaw","version":"2026.7.1-2"}}
TOOL_COUNT: 9
 - conversations_list / conversation_get / messages_read / attachments_fetch
 - events_poll / events_wait / messages_send / permissions_list_open / permissions_respond
```

→ `events_wait` 确实存在,PRD FR-3 依赖的事件订阅通路成立。同时暴露出:该 bridge 会把 `messages_send`(可对外发消息)与 `events_wait`(可阻塞)一并列出,这是 ADR-3 不用 `MCPClient.register_tools()` 的直接依据。**本轮更新**:通路能否用,与通路上能读到什么,是两回事——定义段内提前真机实测(`baseline/preflight-live.md`)推翻了"事件含任务终态"这一假设,详见下方 P-12 与 FR-3 回程机制回写;本条 P-04 的握手结论本身不受影响。

**P-05 · 受阻项(不粉饰):OpenClaw Gateway 本机当前未运行**

```
$ systemctl --user list-units --type=service | grep -i claw     # 无输出
$ ps aux | grep -i "[o]penclaw"                                  # 无输出
$ ss -ltnp | grep 18789                                          # no listener on 18789
$ openclaw daemon status        # 截取
Service: systemd user (disabled)
Service file: ~/.config/systemd/user/openclaw-gateway.service
Service config looks out of date or non-standard.
Gateway: bind=loopback (127.0.0.1), port=18789 (service args)
$ openclaw health               # 截取
[openclaw] Reason: gateway closed (1006 abnormal closure (no close frame))
```

→ `architecture-convergence.md` 与 PRD 里"Gateway 以 systemd 常驻运行"这条前提,**在本机当前不成立**(service 处于 disabled)。只读的 `tasks list` / `approvals get` 走本地 sqlite 与本地文件因此仍能返回,`agent` / `mcp serve` 的实际调用会 ECONNREFUSED。**替代方案**:把它降级为验收前置门,落 `contract/cases.md` C-00,由用户在验收前启用服务;不因此改设计。

**P-06 · 受阻项:`events_wait` 事件负载 schema 本轮未实测 —— 已于定义段内提前实测关闭(见下方 P-12)**

`tools/list` 能列出工具是静态的,真正调用需要 Gateway 在位(P-05)。首轮 preflight 时确实没有实测样本。**本轮更新**:环境前置门达标后,用户已授权在定义段内提前真实派发验证(账本 2026-08-08T17:30:32),取得真实 `events_wait` 事件样本并两轮补测失败路径,原样落盘 `baseline/mcp-event-sample.json` / `baseline/failure-path-samples.json`,纪要见 `baseline/preflight-live.md`。P54 残余敞口已关闭,风险节 R-2 相应更新为"已解除"。

**P-07 · 源码核对推翻 PRD 的一处事实陈述(PRD 冻结,不改,记录在此)**

codegraph 实读 `openclaw-src/task-registry-Cws4vLl0.js:1057-1070`:

```javascript
function ensureDeliveryStatus(params) {
	if (params.scopeKind === "system") return "not_applicable";
	return params.ownerKey.trim() ? "pending" : "parent_missing";
}
function ensureNotifyPolicy(params) {
	if (params.notifyPolicy) return params.notifyPolicy;
	return (params.deliveryStatus ?? ensureDeliveryStatus({...})) === "not_applicable" ? "silent" : "done_only";
}
function resolveTaskScopeKind(params) {
	if (params.scopeKind) return params.scopeKind;
	return params.requesterSessionKey.trim() ? "session" : "system";
}
```

→ 默认通知策略并非无条件 `silent`:只有 scope 为 `system`(即没有 requester session key)时才落 `silent`,带会话键的任务默认就是 `done_only`。**本轮更新(推翻上一轮"对设计影响为零"的结论)**:原 PRD FR-4(通知策略显式设置)整条已被用户裁决删除——定义段内提前实测(`baseline/preflight-live.md` §3.4、§4 D-4/D-6)显示:①CLI 派发的任务 `deliveryStatus` 实测恒为 `not_applicable`,`notifyPolicy` 管的是投递到 IM 渠道这件事,本项目从 CLI 派活无 IM 渠道归属,该步骤对本项目零作用;②任务 `running` 期间调用 `tasks notify` 退出码 0 且打印成功消息但策略并未落库(两次独立复现,直到终态仍是设置前的值),退出码不能当作"已生效"的判据。本条 P-07 的源码发现(`ensureNotifyPolicy` 的分支逻辑)本身仍是真实的源码事实,予以保留存档;但其原本服务的 FR-4 及反证用例 C-13 已随之整条删除,不再是本设计的决策依据。

**P-08 · venv 实装 pipecat 与 clone 副本逐文件 diff(引用行号的前提)**

```
$ diff clone/src/pipecat/<f> venv/.../pipecat/<f>
SAME  workers/ui/ui_worker.py (965 行)      SAME  workers/llm/llm_worker.py (316 行)
SAME  workers/base_worker.py (1399 行)      SAME  workers/ui/ui_job_context.py (150 行)
SAME  workers/llm/tool_decorator.py (88 行) SAME  services/mcp_service.py (313 行)
SAME  pipeline/worker.py (1346 行)
DIFF  workers/runner.py  clone=531  venv=532
```

→ 除 `workers/runner.py` 外,本设计要用到的文件在两版逐字节一致,clone 的行号可直接引用;`runner.py` 若需引用行号一律以 venv 实装那份为准。

**P-09 · pipecat 符号存在性实跑(venv 1.6.0,带项目纪律要求的环境变量)**

```
$ NLTK_DISABLE_IMPORT_SECURITY=1 server/.venv/bin/python -c "..."
UIWorker mro: ['UIWorker','LLMContextWorker','LLMWorker','PipelineWorker','BaseWorker','BaseObject','ABC']
BaseWorker.job: (self, worker_name: str, *, name=None, payload: dict|None=None, timeout: float|None=None) -> JobContext
BaseWorker.job_group: (self, *worker_names, name=None, payload=None, timeout=None, cancel_on_error=True) -> JobGroupContext
BaseWorker.send_job_response: (self, job_id, response=None, *, status=JobStatus.COMPLETED, urgent=False) -> None
UIWorker.respond_to_job: (self, answer: str|None=None, *, tts_speak: bool=False, status=JobStatus.COMPLETED) -> None
LLMContext.__init__: (self, messages=None, tools: ToolsSchema|list[FunctionSchema|Callable]=NOT_GIVEN, tool_choice=NOT_GIVEN)
tool_options: (fn=None, *, cancel_on_interruption: bool=True, timeout_secs: float|None=None)
PipelineWorker app_resources: True     WorkerRunner.add_workers: True
BaseWorker.create_task: True  cancel_task: True
```

`tool_options` docstring 原文关键句:"A handler advertised in an ``LLMContext``'s tools — a direct function … is registered automatically with default call options, so the decorator is only needed when you want to override those defaults."
→ 快脑侧的派活工具可以是模块级 `async def` + `@tool_options(cancel_on_interruption=False, …)`,不需要把主 worker 改成 `LLMWorker`。

**P-10 · 受阻项:`mcp` Python 包未装**

```
$ server/.venv/bin/python -c "import mcp"
ModuleNotFoundError: No module named 'mcp'
$ grep -i "Provides-Extra: mcp\|Requires-Dist: mcp" pipecat_ai-1.6.0.dist-info/METADATA
Provides-Extra: mcp
Requires-Dist: mcp[cli]<2,>=1.11.0; extra == "mcp"
```

→ 新增依赖 `pipecat-ai[mcp]`(带出 `mcp[cli]>=1.11.0,<2`)。按通用纪律 10,新增依赖须用户拍板,已列进回执 RISKS。**替代方案**(若不批准装依赖):用 `asyncio` 直接和 `openclaw mcp serve` 子进程做 JSON-RPC over stdio——本次 preflight P-04 已经用标准库跑通了完整握手,可行但要自写约 120 行协议层,与"减少自研"口径相悖,列为备选不推荐。

**P-11 · 本仓测试与 eval 资产实跑**

```
$ cd server && NLTK_DISABLE_IMPORT_SECURITY=1 .venv/bin/python -m pytest --collect-only -q
49 tests collected in 1.16s
$ ls server/evals/*.yaml   # 16 个场景 + fault manifest,含 r4_no_false_completion.yaml
```

**P-12 · 定义段内提前实测复核(`baseline/preflight-live.md`,回写 P-01~P-11 与下方设计判断的事实前提)**

s2a 首轮冻结后,C-00 环境前置门达标(账本 2026-08-08T17:25:54/17:48:44),用户授权在定义段内提前真实派发验证(账本 17:30:32:「可以跑 不用担心费用」),产出 `baseline/preflight-live.md`(§1-5 首轮 4 次真派发 + §6-11 失败路径补测 8 次真派发,原样样本 `baseline/mcp-event-sample.json` / `baseline/failure-path-samples.json`)。与本设计原判断不符或需要回写的事实,逐条编号如下,后续各节按编号引用:

- **D-1**:`openclaw tasks show --json` 命中时 JSON 落在 **stderr**,stdout 恒 0 字节;命中(exit=0)与未命中(exit=1)只能靠**退出码**区分,不能靠输出流区分(`preflight-live.md` §4 D-1)。
- **D-2**:`events_wait` 的事件类型全集里**没有任何任务终态事件**,唯一与任务相关的信号是 `role=assistant` 的 `message` 事件,其 `raw.status` 是消息产出瞬间的**会话级**状态(实测恒为 `"running"`),不是任务终态(`preflight-live.md` §3.2)。
- **D-3**:`events_wait` 返回单数 `structuredContent.event`,**不带 `next_cursor`**,消费者须自行从 `event.cursor` 推进游标;事件队列是每个 `openclaw mcp serve` 进程各自的内存队列(cursor 从 1 起、上限 1000 条滚动丢弃),**连接建立之前发生的事件取不回**,故 bridge **必须在派发之前就连上**(`preflight-live.md` §3.3)。
- **D-7**:`tasks show` 单次调用固定约 2.3-2.6 秒(node CLI 冷启动);派活发起后约 2.6 秒内查同一个 lookup 会返回"未命中",与真实未命中(C-08)输出完全相同、不可区分;在途任务数较多时,`get_task_status` 逐条串行调用会累积逼近工具超时(`preflight-live.md` §2、§4 D-7)。**本轮更新(用户裁决,替代原"留待联测上调 timeout_secs"处置)**:改用范围收窄关闭该敞口——同一会话在途任务数设硬上限 `MAX_INFLIGHT_TASKS = 3`(契约 §0.3 新增),3 × 2.6s ≈ 7.8s,远小于 §0.2 T2 `timeout_secs=15.0`,该数值维持不动、无需联测校准。
- **D-8**:`--timeout` 触发的中止,任务终态落 **`cancelled`**,不是 `timed_out`;`timed_out` 本轮全部真机派发中一次未出现过(`preflight-live.md` §10 D-8)。
- **D-10**:`role=assistant` 的事件按 `raw.message.stopReason` 分三态——`toolUse`(工具调用/过程播报)、`aborted`(中止,`text` 为空串)、`stop`(真结论);只有 `stop` 是要播的结论(`preflight-live.md` §10 D-10)。
- **D-11**:`openclaw agent --json` 的退出码/stdout 终态与任务记录终态会互相矛盾(如 F6:CLI 报 `ok`/`completed`,任务记录为 `failed`),**不可用 CLI 退出码判派活结果**(`preflight-live.md` §10 D-11)。
- **D-12**:六种失败形态里五种在 `events_wait` 通路上无法只靠 assistant 消息发现(`preflight-live.md` §10 D-12),用户已裁决本期异常路径整体不覆盖(PRD 非目标条目 11/12)。

其余实测发现(D-4 通知竞态、D-5 TaskView 字段容缺、D-6 deliveryStatus 与 P-07 源码推论不一致、D-9 `tasks cancel` 对 `cli` 空操作)分别在下方对应节与 `contract/cases.md` 回写,不在此重复。

### 2. 相关模块与既有约定(codegraph 实读)

- 装配收口 `server/bot.py::assemble_pipeline`(:196-336)→ `AssembledPipeline` dataclass(:135-154)聚合 12 个对象供结构性断言;`run_bot`(:358-393)挂三个事件处理器后 `WorkerRunner(handle_sigint=False)` → `add_workers(worker)` → `run()`。
- 快脑分支是整条 pipeline 唯一对外输出通道(:278 注释原文);慢脑分支无输出组件(:289 注释原文)。
- `on_client_disconnected` → `await worker.cancel()`(:385-388)。
- 素材注入既有形态:`ProducerProcessor(filter=…, transformer=…, passthrough=True)`(:256-260)在慢脑分支,`ConsumerProcessor(producer=producer)`(:261)在快脑分支头部。
- 会话级实例工厂约定(R5):`build_slow_material_filter()` / `build_sentinel_filter()` / `build_fast_answer_tap()`,禁模块级单例(`sentinel.py:74-93` docstring 写明理由)。
- 注入模板常量单一事实源(R4):`prompts.py:68-85` 三个 `INJECT_*_TEMPLATE`,禁内联字面串。
- 与派活直接冲突的能力边界段:`prompts.py:22-29` `CAPABILITY_BOUNDARY_SECTION`,原文第一句 "You currently have no ability to take real-world actions…";`SYSTEM_PROMPT` 由 5 段拼装(:87-90)。
- 派活相关缺口(仍成立):无 function calling / 无多 worker / 无 `app_resources` / 无持久化。
- 注意:`server/evals/fault_run/bot.py` 是 `server/bot.py` 的一份故障注入副本,同样含 `assemble_pipeline`/`run_bot`。本变更不动它,但它会因 `prompts.py` 改动而间接受影响,已列进风险节 R-6。

### 3. 可复用件与本变更的用法

| 件 | 位置 | 本变更用法 |
|---|---|---|
| R2 RTVI 泄漏封锁 | `bot.py:300-308` | 新增处理器不得进入 RTVI 转写;新增静默处理器按同款 `ignored_sources` 处置 |
| R3 素材注入机制 | `bot.py:255-261` | 终态回流沿用**同构**注入(同角色、同触发帧),但源头是另一个 worker,见 ADR-4 |
| R4 模板常量 | `prompts.py:68-85` | 新增 `INJECT_TASK_TERMINAL_TEMPLATE` 与之同列 |
| R5 会话级工厂 | `dual_brain.py` / `sentinel.py` | 派活的注入器、注册表、worker 一律 session-scoped |
| R6 eval 资产 | `server/evals/` 16 个场景 | 新场景照此形制扩;`judge_factory.judge_llm` 直接可用 |

---

## 方案

### A. 与已确认架构的一致性,以及三处显式偏离

与 `research/architecture-convergence.md`(用户确认"完美符合需求")及 `architecture-diagram.json`(用户已过目)逐项对齐:主 `PipelineWorker` 双脑骨架原样不动;派活 worker 独立挂同一 `WorkerRunner`;派活走 subprocess 调 `openclaw agent`;任务状态机/通知策略/终态语义全部照收 OpenClaw 原生;桥接用 `openclaw mcp serve` stdio;peer worker 隔离 CLI 阻塞;终态事件经素材注入回快脑。

三处偏离,逐条给理由:

1. **偏离一:派活 worker 类由 `BaseWorker` 改为 `UIWorker`。** 收敛纪要写的是 `BaseWorker`;用户 2026-08-08 拍板改 `UIWorker`(账本 15:51:55),理由收窄为 G4 占位 + 复用其 delegation 与第二个 LLM,本期不启用 UI 能力。本设计照拍板执行。
2. **偏离二:桥接层不使用 pipecat `MCPClient` 的工具注册路径。** 收敛纪要把桥接写成"官方×官方:`openclaw mcp serve` ↔ pipecat `MCPClient`"。实读 `services/mcp_service.py`(venv 与 clone 逐字节一致)后发现:该类的公开消费面只有 `get_tools_schema()` / `register_tools_schema()` / `register_tools()`,把 MCP 工具**全量注册成 LLM 函数**;唯一的直接调用入口 `_call_tool` 与会话句柄 `_active_session` 都是私有。而 PRD FR-3 明令 `events_wait` 不得进入任何 LLM 工具,`messages_send` 更是不该给模型。详见 ADR-3:仍用官方 `mcp` SDK 的 `ClientSession`(pipecat 的 `mcp` extra 带出的同一个包),只是不经 `MCPClient` 这层包装。桥接的两端仍然都是官方件。
3. **偏离三:审批链相关节点整体不存在。** 收敛纪要含审批入向/出向两条边;PRD 二次收窄已把审批整体移出本期(降级为 OpenClaw 侧权限配置)。架构图已按最终范围重画。本设计与图一致,不含任何审批组件。

### B. 本期启用与不启用范围(worker 选型已由用户拍板)

**启用**:`UIWorker` 的 `@job(name="respond", sequential=True)` 入口、`_run_llm_turn` 的第二次完整 LLM 推理、`@tool` 机制、`respond_to_job` 的**默认**模式(job 响应交回快脑措辞)。
**不启用**:`start_ui_job_group` / `ui_job_group` 四信封 / `__cancel_job_group` / `tts_speak=True` 逐字念 / `auto_inject_ui_state` 相关的屏幕能力。不启用由 `contract/cases.md` C-16 用 grep + 静态断言测试守住,防止后续无意启用绕过官方无覆盖测试这条已知缺口。

### C. 端到端装配链(坑 P55:每个挂点写明,不接受"单测能过就行")

一条派活请求从触发到播报,经过的挂点逐个列出。每个挂点在 `## 任务拆分` 里都有明确归属的任务卡。

**去程(同步,快脑不等任务做完)**

1. `server/prompts.py::CAPABILITY_BOUNDARY_SECTION` — 最小改动:删掉"无执行能力"这一句表述本身,使其不再与派活矛盾;不新增任何转述内容约束(PRD C1 已两次裁决)。
2. `server/task_dispatch_contract.py`(新增)— 契约常量与 dataclass,零副作用导入。
3. `server/task_dispatch.py`(新增)— `dispatch_task` / `get_task_status` 两个模块级工具函数、`TaskDispatchWorker(UIWorker)`、`OpenClawExecWorker(BaseWorker)`、`_DispatchMaterialInjector(FrameProcessor)`、`DispatchRegistry`、`build_dispatch_stack(cfg)` 工厂。
4. `server/bot.py::assemble_pipeline` — ①`fast_context = LLMContext(tools=[dispatch_task, get_task_status])`(K1 缺口在此被填);②`injector = stack.build_injector()` 插入快脑分支**头部**(在既有 `consumer` 之前);③`PipelineWorker(..., app_resources=stack.app_resources)`(K3 缺口在此被填);④`PipelineWorker(name=MAIN_WORKER_NAME, ...)`;⑤`AssembledPipeline` 追加 `injector` / `dispatch_worker` / `exec_worker` / `dispatch_registry` 四个字段,供结构性断言。
5. `server/bot.py::run_bot` — `await runner.add_workers(worker, stack.dispatch_worker, stack.exec_worker)`;并把主 worker 的反向引用写进 `app_resources`(工具函数据此拿到 `worker.job`)。
6. 快脑 LLM 判定该轮要交出去 → 调 `dispatch_task` → `worker.job("task-dispatch", payload={"query": …})`。
7. `TaskDispatchWorker` 的第二个 LLM 完整跑一轮推理,决定派什么、要不要拆成多条 → 调自己的 `reply(answer, tasks=[…])` 工具。
8. `reply` **本轮新增前置检查**:查 `DispatchRegistry` 当前在途条数,若加上这批 `tasks` 会超过 `MAX_INFLIGHT_TASKS = 3`,整批拒绝(不起任何 exec job、`respond_to_job` 改走固定失败文案),否则按原次序继续。详见契约 §0.3 与 ADR-8。未超限时:对每条 task **不等待地**发一个 job 给 `openclaw-exec`,随后立刻 `respond_to_job(answer)` → job 响应回到快脑的工具调用 → 快脑自行措辞说"已经派出去了"。
9. `OpenClawExecWorker` 的 `dispatch` job:生成 session key → 写任务书临时文件 → detached spawn `openclaw agent --agent … --session-key … --message-file … --json` → 轮询 `openclaw tasks show <session_key> --json` 直到命中(上限 30 秒;命中判读靠退出码,JSON 落在 stderr,依据 D-1)→ 把 `(session_key, label)` 记进会话内存注册表 → `send_job_response(...)`。**本轮删除原"设通知策略"一步**(原 FR-4 通知策略整条已作废,依据 D-4/D-6,详见上方 P-07 回写)。

**回程(异步,原 job 早已结束)**

10. `OpenClawExecWorker` 在 `on_worker_ready` 起一个独立 asyncio task(`self.create_task(...)`,BaseObject 官方 API),**在首个派活任务发起前**就持有 `openclaw mcp serve` stdio 子进程并开始循环调 `events_wait`——连接前发生的事件不可见,必须先连后派(依据 D-3);循环内以命中事件的 `event.cursor` 自行推进下一次调用的游标(`events_wait` 不返回 `next_cursor`,依据 D-3)。
11. **(本轮据 D-2/D-10 整段改写)** 收到 `sessionKey` 命中注册表内某条记录、`type=="message"`、`role=="assistant"`、且 `raw.message.stopReason == "stop"` 的事件 → 取该事件的 `event.text` 原文 → 渲染 `prompts.INJECT_TASK_TERMINAL_TEMPLATE`(模板不再含状态字段,直接承载 agent 自述,见 §0.9 回写)→ put 进会话级注入队列 → 从注册表移除该条。`stopReason` 为其他值(`toolUse`/`aborted`)或该键缺失的 assistant 事件、以及任何 `role=="user"`/审批类事件**一律丢弃**——不注入、不产生任何副作用,也**不触发任何 `openclaw tasks show` 调用**(回程链路不回查任务状态,呼应用户裁决"人家已经报了就不用再确认")。原设计"收到终态事件→渲染 status"的前提已被 D-2 证伪(事件通路没有任何任务生命周期/终态事件类型),故不再读取、不再渲染任何状态字段。
12. `_DispatchMaterialInjector` 在快脑分支头部把队列**一次取空**、合并成**一条** `LLMMessagesAppendFrame(run_llm=True)` 推下游 → 快脑在既有轮次/打断语义下的下一个安全插入窗自然带出。

对外输出通道数量在整条链路上没有变化:唯一含 `transport.output()` 的仍是快脑分支。注入器只往下游推消息帧,不含任何输出组件——这正是 FR-3 判据 1 结构性验证要断言的形状。

### D. 关键决策(ADR)

**ADR-1 · 会话键由 voice-agent 侧先生成,作为全变更的关联主键**
- 背景:`openclaw agent` 实测**必须**带会话目标选择器(P-03),且它是长阻塞调用——若等它退出才拿 task id,FR-2(状态查询)/FR-4(多任务互不串扰,原 FR-5)/FR-5(手动接管可达性,原 FR-6)均没有关联锚点。**本轮更新**:原文本提到的"FR-4 派发后设通知策略"已随原 FR-4(通知策略)整条删除而作废,不再是本决策的驱动因素之一。
- 决定:按 `agent:{agent_id}:voice-agent-{uuid4hex12}` 自行生成 session key,随 `--session-key` 传入;`openclaw tasks show <lookup>` 官方支持"by task id, run id, or session key",于是同一个 key 同时充当派发参数、状态查询键、多任务隔离键、人工接管地址(**本轮删除"通知策略设置键"这一用途**,依据同上)。
- 代价:引入一条本项目自定的命名约定(虽然形状由 OpenClaw 规定)。**本轮更新**:原"`tasks show` 能用 session key 解析"这一依赖**已实机验证成立**(`preflight-live.md` §2:四次真派发,`childSessionKey`/`ownerKey`/`requesterSessionKey` 三者均等于自生成的 key,`tasks show` 用该 key 精确命中,exit=0),原风险 R-3 已解除,详见下方风险清单 R-3。
- 被否方案:派发后轮询 `tasks list --runtime cli --json`、按 `createdAt` + 任务正文文本反查 task id。否因:并发派多条时靠时间戳与文本相似度关联本身就是新造的关联逻辑,且 `--status` 非法值静默返回空(P-03)已经说明这套过滤接口不适合当关联依据。

**ADR-2 · 派活 CLI 以 detached subprocess 起,且全程不等待它退出**
- 背景:CLI 默认最长阻塞 600 秒(P-01);而 `on_client_disconnected` 会 `worker.cancel()`(`bot.py:385-388`),PRD FR-1 判据 2 要求任务不随断连中止。
- 决定:`start_new_session=True` 起进程,不 `await` 其退出;job 在"拿到 lookup"后即回响应(**本轮更新**:原"设好通知策略"这一等待条件已随原 FR-4 通知策略整条删除而不存在)。真实执行体在 Gateway 进程,CLI 只是它的 WS 客户端。
- 代价:CLI 的退出码/stdout 终态只能被一个旁路 waiter task 观测,**且不可信**——`preflight-live.md` §10 D-11 实测:该退出码/stdout 与任务记录终态会互相矛盾(如 F6 案例 CLI 报 `ok`/`completed` 而任务记录为 `failed`),因此**不进入任何判定路径**,仅供调试日志参考,派活结果一律以 `openclaw tasks show` 轮询命中的任务记录为准;voice-agent 先退出时临时任务书文件会残留在 `/tmp`。
- 被否方案:`await` 子进程退出后再回 job 响应。否因:快脑那一轮会被拖住最长 600 秒,FR-1 判据 1 当场破功。
- **难逆性**:低。改回等待只需改一处 await。

**ADR-3 · MCP 侧只用官方 `mcp` SDK 的 `ClientSession`,不走 pipecat `MCPClient` 的工具注册路径**
- 背景:`services/mcp_service.py`(venv 与 clone 一致)公开面只有三个注册类方法,直接调用入口 `_call_tool`、会话句柄 `_active_session` 均为私有;而 P-04 实测该 bridge 一次列出 9 个工具,其中 `events_wait` 会阻塞最长 300 秒、`messages_send` 能对外发消息。PRD FR-3 明令 `events_wait` 不得进 LLM 工具。
- 决定:用 `mcp` SDK 的 `stdio_client` + `ClientSession` 直接建连并只调 `events_wait`,不注册任何工具给任何 LLM。
- 代价:多一个直接依赖(`pipecat-ai[mcp]` extra,见 P-10,待用户批准);与收敛纪要"用 pipecat MCPClient"的字面表述不一致(偏离二已说明)。
- 被否方案 A:用 `MCPClient.register_tools()` 后靠 prompt 约束模型别调 `events_wait`。否因:把一个可阻塞 300 秒、且能对外发消息的能力交给模型自律,是拿对话可用性与外发消息赌 prompt 依从性。
- 被否方案 B:自写 JSON-RPC over stdio 协议层(preflight P-04 已经用标准库跑通)。否因:约 120 行自研协议代码,与用户"减少自研、官方有什么用什么"口径相悖;只有在依赖不获批准时才回退到它。

**ADR-4 · 回流注入用"同构而非同实例":新增一个快脑分支头部的注入处理器,而不是复用既有 Producer 实例**
- 背景:PRD C3 与架构图都要求复用 R3 素材注入机制。但实读 `processors/producer_processor.py`:`ProducerProcessor` 只在**自身作为管线内处理器、有帧流经它**时才通过 `_produce()` 向消费者队列投递;`add_consumer()`(:60)返回队列、`_produce()`(:90)是私有。我们的事件源是一个**不在任何分支里**的 worker,官方件在这个形状上没有对应入口。
- 检索留痕(硬规则 8):查过 pipecat `ProducerProcessor` / `ConsumerProcessor` / `bus` 桥接三条路线。`ConsumerProcessor` 必须绑定一个在管线内的 `ProducerProcessor`;`bus` 桥接要给主 `PipelineWorker` 开 `bridged=()`,而这会在主管线上包一层 bus edge processors,对既有 RTVI 泄漏封锁(`ignored_sources` + `user_llm_enabled=False`)的影响未经评估(`pipecat-capability-survey.md` §6 条 3 明确列为未评估项)。两条都不契合,故自写一个约 40 行的注入处理器。
- 决定:新增 `_DispatchMaterialInjector(FrameProcessor)`,持一个会话级 `asyncio.Queue`,用 `self.create_task()` 起排空循环,把合并后的 `LLMMessagesAppendFrame` 推下游。语义与 `ConsumerProcessor` 同构(队列进、帧出),只是源头换成 worker。
- 代价:多一个本项目自有处理器,需自带单元测试(合并规则、会话隔离、不产生输出组件三条)。
- **难逆性**:低。它是快脑分支头部的一个独立处理器,拆掉即回到改动前形状。

**ADR-5 · 不做兜底状态轮询,终态只认 push**
- 背景:MCP 事件队列是 live-only 内存队列,进程重启期间的事件会丢(PRD FR-3 已认这条边界)。加一条周期性 `tasks show` 轮询可以兜住。
- 决定:本期不做。OpenClaw 官方文档原文即"the usual workflow is push-based … Poll task state only when you need debugging, intervention, or an explicit audit"。**本轮更新论证依据(原引用的 FR-4 反证用例 C-13 已随通知策略整条删除,不再成立)**:PRD 非目标条目 11/12(依据 `preflight-live.md` §6-§9 失败路径实测,用户裁决原话「失败不会报很正常,他都失败了怎么报」+「我们本期只做核心流程,异常情况很多不可能都处理得了」)已明确裁决"任务未产出结论消息的异常路径整体不覆盖,本期不做任何兜底"——加一层轮询本质上就是在做非目标条目 11/12 明确排除的兜底,与该裁决直接冲突。
- 代价:重启空窗内完成的任务不会被播报(PRD 非目标 #2 已认)。
- 被否方案:push + 轮询双通道并以先到者为准。否因:两条通道会各自触发一次播报,需要再造一层去重,自研面反而扩大;且与上一条判据冲突。

**ADR-6 · `--timeout` 沿用默认 600 秒,不传 `0`**
- 背景:CLI 支持 `--timeout 0` 关闭超时。
- 决定:不传该参数,沿用默认。**本轮实测修正(D-8,原表述与实测不符)**:超时中止落的原生终态是 **`cancelled`**,不是 `timed_out`——`timed_out` 本轮全部真机派发一次未出现过;中止的 `stopReason` 经 `buildAgentRunTerminalOutcome`/`mapAgentRunTerminalOutcomeToTaskStatus` 映射落 `cancelled`,与显式取消同一终态,只能靠 `error` 文案区分(超时=`"agent run aborted"`,显式取消=`"Cancelled by operator."`)。该次任务的 assistant 事件 `stopReason=="aborted"`、`text` 为空串,不满足 FR-3 新筛选口径(§0.9),**不产生播报**——不是"照原样播报",这与"只用外部原生状态、不新造判定"的全局口径依然一致,只是不再有"播报超时状态"这个动作;用户不会主动收到超时通知,落入 PRD 非目标条目 11 的范围,只能靠 FR-2 主动查询发现。
- 代价:超过 10 分钟的长任务会被 OpenClaw 中止(终态 `cancelled`);且中止后 assistant 消息通路读不到可播报的结论(`text` 为空串),用户不会主动收到通知。
- 被否方案:传 `--timeout 0`。否因:任务可无限期挂着,而本项目没有任何本地状态可以发现它,`lost` 之外没有兜底。

**ADR-7 · 结论消息筛选口径:只认 `raw.message.stopReason == "stop"`,不做定时器/状态机(本轮新增,替代原"收到终态事件"机制)**
- 背景:原设计假设"收到 OpenClaw 终态事件"来触发播报,该前提已被 D-2 证伪——事件类型全集(实装 6 处 `enqueue` 逐一核对)只有 `message` 一种消息事件 + 5 种审批类事件,不存在任何任务生命周期/终态事件类型。而 `role=="assistant"` 的 `message` 事件本身又不是"一收到就该播"的单一形态:D-10 实测其按 `raw.message.stopReason` 分三态(`toolUse` 工具调用/过程播报、`aborted` 中止、`stop` 真结论),不筛选会把中间过程当结论播、同一任务播好几次(实测反例:F4b 一次派发产生 5 条 assistant 事件,仅末条是结论)。
- 决定:后台事件循环只处理 `sessionKey` 命中、`type=="message"`、`role=="assistant"`、且 `raw.message.stopReason == "stop"` 的事件,直接把该事件的 `event.text` 作为素材转述,不解析、不改写;其余一律丢弃。不引入定时器、不引入状态机、不回查任务状态——这是用户裁决原话「人家已经给你报了你还确认啥,只要知道什么任务完毕就行了」的直接落地,也与 PRD C1(完成真实性归 OpenClaw)同向。
- 代价:若某次派发的真实结论消息恰好缺失 `stopReason` 键(两份原样样本共 19 条 assistant 事件全部带该键,但样本量不保证覆盖全部形态),该次任务会静默丢失播报,落入 PRD 非目标条目 11(未产出结论消息的异常路径,本期不覆盖);PRD FR-3 判据 5 已就此写明反证条件(置信度约 85%),若联测阶段观测到该形态,应回来放宽筛选口径,而不是实现时私自加分支。
- 被否方案 A:收到 assistant 事件后回查 `openclaw tasks show` 取结构化 `status`/`terminalSummary` 判定。否因:与用户裁决"不用再确认"直接冲突,且 D-11 已证明 CLI/任务记录/事件三方口径可能互相矛盾,回查不能提高确定性,只会多一次 ~2.5 秒的阻塞式调用(D-7)。
- 被否方案 B:引入一个"派发后计时,超时未收到结论消息则自动回查"的兜底状态机。否因:PRD 非目标条目 11/12 已明确裁决"本期只做核心流程,异常情况很多不可能都处理得了",该兜底属于非目标范围内的能力,不在本轮自研——若后续要做,PRD 已给出后加成本估计,留给未来变更。
- **难逆性**:低。筛选条件是后台事件循环内的一个 `if`,不涉及持久化或跨会话状态,收紧或放宽筛选口径都是局部改动。

**ADR-8 · 在途任务上限(`MAX_INFLIGHT_TASKS = 3`)只在 `reply()` 一处检查,不在 `dispatch_task` 设早期短路(本轮新增,用户裁决落地)**
- 背景:用户裁决(替代原"上调 timeout_secs"方案)——「不需要调,本期只做核心能力,可以把任务限定在3个以内」。这是**实现约束,不是新 FR**:为满足 PRD 既有 FR-2(状态查询)判据 3"不拖慢对话"、关闭 D-7 敞口而在实现侧加的一条硬上限,不写进 PRD、不暗示新增需求。上限值 3 由用户直接拍定,不做可配置项(多一个配置项即多一份自研面,与"本期只做核心能力"口径相悖)。
- 决定:检查点唯一放在 `TaskDispatchWorker.reply()` 内、起 exec job(步骤①)之前——这是唯一能同时看到"当前在途条数"与"这批 fan out 出的完整 tasks 列表"的时点(`dispatch_task` 调用时第二个 LLM 尚未决定 fan out 几条,查不全;`OpenClawExecWorker` 逐条处理时已经晚了,拦不住整批)。**fan out 一次性超限的处置(用户明确要求写死,不留给实现者临场发挥)**:检测到 `当前在途条数 + len(tasks) > 3` 时**整批全部拒绝、不做部分截断**——不起任何一条 exec job(哪怕其中一部分原本在余量之内),`reply()` 改用固定文案调 `respond_to_job(answer=CAPACITY_MESSAGE, status=JobStatus.ERROR)`(`UIWorker.respond_to_job` 官方原生支持 `status` 参数,P-09 已实锤,不必新引入 `send_job_response`),**不使用第二个 LLM 自己写的 `answer`**(它是在不知道上限的前提下生成的,可能与实际动作不符)。该 ERROR 状态经既有 job 机制传回 `dispatch_task` 的 `await ...job(...)`,被 `dispatch_task` 已有的"超时/异常一律转成失败载荷交回 LLM"处理原样接住(§0.2 T1,零新增代码),快脑据此自行措辞告知用户,不新增专门报错话术层(与 FR-1/C1 既有报错路径同构)。未超限时不受影响,按原次序①②继续。
- 代价:唯一检查点意味着"已经在途 3 个"时,`dispatch_task` 仍会先完整跑一轮第二个 LLM 推理(可达 `timeout_secs=20` 量级)才在 `reply()` 处被拒绝——用户会经历一次可感知的等待才听到"派不了"的答复,而不是当场秒拒。全有全无(不做部分截断)意味着"注册表还有 1 个空位、这次 fan out 了 2 条"这种情况会把那 1 个空位也一并浪费掉(整批 2 条都不派),而不是先派 1 条、拒 1 条。
- 被否方案 A:在 `dispatch_task`(§0.2 T1)也加一次早期短路检查(注册表已满 3 → 不调 `worker.job(...)` 直接拒绝),作为 `reply()` 检查之外的优化层。否因:两处各自维护一份"当前在途条数"的读取逻辑,且请求发出到第二个 LLM 决策完成之间存在时间窗口(另一路径可能并发新增派发),`reply()` 处的检查始终是不可省的最终关口;双检查点是纯优化、不解决 fan out 场景,反而多一处需要保持同步的自研代码,与"自研面最小、单一权威检查点"口径相悖,故不做。
- 被否方案 B:超限时按余量部分派发(如余 1 个位置、fan out 2 条,派前 1 条、拒后 1 条)。否因:需要额外定义"按什么顺序/优先级选择派哪几条"的策略,是纯自研判断且无 PRD/实测依据支撑;全有全无判定简单、确定、可测试,且用户裁决原话未要求部分派发的精细化处理。
- **难逆性**:低。这是 `reply()` 内部的一个前置 `if` 分支 + 一个常量,拆掉或调数值都是局部改动,不影响其余装配。

### E. 测试策略(可执行)

分四层,判据落点写明。全部命令在仓库根或 `server/` 下执行,凡启动 `bot.py`/`pytest` 一律带 `NLTK_DISABLE_IMPORT_SECURITY=1`。

**L1 单元(新增 `server/tests/test_task_dispatch.py`)**
```
cd server && NLTK_DISABLE_IMPORT_SECURITY=1 .venv/bin/python -m pytest tests/ -q
```
覆盖:session key 生成形状;argv 组装与 `contract/cases.md` §0.7 逐字一致;`tasks show` exit=1 时降级成 `found: false` 而不抛;注入器一次取空合并成单帧;注入器会话隔离(两个实例互不可见);`TaskDispatchWorker.reply` 的次序不变量(先起 job 再 `respond_to_job`,且不 await job 完成);**在途任务上限**(本轮新增,ADR-8):达 `MAX_INFLIGHT_TASKS = 3` 时整批拒绝、不起任何 exec job、`respond_to_job` 走 `status=JobStatus.ERROR` 与固定文案 `CAPACITY_MESSAGE`;C-16 的静态断言(类体内不引用 `ui_job_group` 系符号)。判据落点:pytest 退出码 0,且既有 49 条测试无回归。

**L2 结构(扩 `server/tests/test_dual_brain.py::TestAssemblePipeline` 既有结构断言,本轮修正落点)**
覆盖:对外输出分支数量与改动前一致(仅快脑分支含 `transport.output()`);注入器位于快脑分支头部且不含任何输出组件;`fast_context.tools` 恰含两个工具;`app_resources` 非空;`AssembledPipeline` 新增四字段可取。判据落点:同 L1 命令,退出码 0。

**本轮实测修正(主会话过目发现,坑 P55/P2/P53——契约两端到位、中间挂点指错;引用了未实测的既有件)**:design 原表述"扩 `test_bot.py` 既有 `AssembledPipeline` 断言模式"与实机不符——`grep -rn "AssembledPipeline" server/tests/` **零命中**;`server/tests/test_bot.py` 实测只有 4 条 provider builder 测试(`.venv/bin/python -m pytest tests/test_bot.py --collect-only -q` → `4 tests collected`),不含任何结构断言。真正的管线结构断言在 **`server/tests/test_dual_brain.py::TestAssemblePipeline`**(`.venv/bin/python -m pytest tests/ -q -k AssemblePipeline` → `5 passed, 44 deselected, exit=0`),其中既有的 `test_pipeline_shape` 方法断言"consumer 必须在快脑分支内、且在 `fast_pair.user()` 之前;慢脑分支不得含 `transport.output()`/TTS"——与本轮 FR-3 判据 1 要断言的"对外输出分支数量不变 + 新增的 `_DispatchMaterialInjector` 位于快脑分支且不含输出组件"是同一形状的直接延伸。本轮**改为在该既有类内扩写/新增测试方法**,不另起一套、不改用 `test_bot.py`。**D-003 守法核对(不违反守法③"不新增 `import bot` 的测试文件")**:`test_dual_brain.py` 用的 `bot_module` fixture 已在 T5.1 挪至 `tests/conftest.py`(实测 `grep -c sys.modules`:`conftest.py`=4、`test_bot.py`=1、`test_dual_brain.py`=**0**),`test_dual_brain.py` 自身不含任何 `sys.modules` 手法,是直接吃 conftest 现成 fixture 的既有文件——扩写它的既有类属于"扩写既有文件",不构成新增 `import bot` 的测试文件,守法③不受影响。

**L3 行为 eval(新增 6 个场景 + 复跑既有 15 个)**
```
cd server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run bot.py -t eval 2>&1 | tee /tmp/pipecat-dispatch.txt
cd server && set -a && source .env && set +a && PYTHONPATH="$(pwd)" NLTK_DISABLE_IMPORT_SECURITY=1 pipecat eval run evals/<name>.yaml -v --logs-dir eval-runs
```
**本轮修正(坑 P42,跨文件扩散的坏命令)**:`pipecat` CLI 是全局工具、不在 `server/.venv` 内,`uv run pipecat ...` 会解析到 `server/.venv/bin/pipecat` 并以 exit=1 报缺 cli extra;正确写法见上,以 `contract/cases.md` §1 命令口径与 §0.10 前后说明为准,本节不再另编一套。
新增场景:`dispatch_nonblocking` / `dispatch_cli_failure` / `dispatch_terminal_report` / `dispatch_terminal_merge` / `dispatch_capacity_reached`(本轮新增,对应 C-19)/ `baseline_probe`。既有场景复跑范围与判据见 `contract/cases.md` C-03。判据落点:每个场景退出码 0;失败集合与 C-17 基线一致。

**L4 真机联测(依赖 C-00 环境前置门)**
覆盖 C-02 / C-05 / C-06 / C-14 / C-15 / C-18,全部以 `openclaw tasks show <lookup> --json` 的原样输出(或 `baseline/failure-path-samples.json` 原样样本,C-18)为证据。**本轮删除 C-12/C-13**(随原 FR-4 通知策略一并作废),**新增 C-18**(FR-3 判据5 的否定验证补齐覆盖)。判据落点:`test-report.md` 判据核对表逐条贴命令与原始输出。

---

## 接口契约

档位**终定为 `cases`**,与 s0 预判一致,无不一致处。

理由:本变更对外不暴露任何 HTTP 端点、不新增本项目自己的 CLI、本期无界面呈现(S1b 已判定不产 ui-spec.md),因此 openapi.yaml / cli.md / ui.md 三档均无对应物;验收锚点是"一串可执行的行为用例",正是 cases 档的形状。本变更确实消费一个外部 CLI(openclaw)与一个外部 MCP bridge,但那是被消费的依赖而非本项目产出的接口,其 argv / 退出码 / 字段约定作为**契约常量**写在 cases 档的 §0 节内,与用例同文件、单一事实源。

契约文件(唯一事实源,本节不复写其中任何定义):

- `pipeline/task-dispatch/contract/cases.md`
  - §0 契约常量:worker 名、快脑侧两个工具的签名与语义、派活 worker 与执行 worker 的 job 约定、`TaskView` 字段挑选、session key 生成规则、openclaw 外部命令 argv 与退出码判读、MCP bridge 约定、素材注入模板与合并规则。
  - §1 验收用例 C-00 ~ C-18(本轮新增 C-18,FR-3 判据 5 否定验证补齐覆盖),每条含前置条件、可执行步骤、可证伪期望、判定方式。
  - §2 FR 覆盖映射(FR-1 ~ FR-5 全覆盖,无空洞)。
  - §3 明确不覆盖范围(与 PRD 非目标一致)。

实现节点与验收节点均以该文件为准;与本设计正文表述冲突时,以契约文件为准。

---

## 数据模型

本变更**不建任务状态机、不持久化任何任务状态**(PRD 全局口径,用户已裁决只用外部原生状态)。本节把三类数据分开写清楚:哪些是外部原生结构的引用、本项目内存里持有什么、生命周期与边界在哪。

### 1. 外部原生结构(只引用,不复制、不镜像、不改名)

**OpenClaw `TaskRecord`** —— 唯一的任务事实源,存活在 OpenClaw 的 sqlite 任务注册表里,本项目**只读、不写**。**本轮更新**:原"除通过 `tasks notify` 改一个策略字段"这一例外已随原 FR-4(通知策略)整条删除而不成立——本项目本轮起对 `TaskRecord` 不做任何写操作。字段集来自 codegraph 实读 `openclaw-src/task-registry.store-CssXnO54.js:114-151` `rowToTaskRecord`:

`taskId` / `runtime` / `taskKind` / `sourceId` / `requesterSessionKey` / `ownerKey` / `scopeKind` / `childSessionKey` / `parentFlowId` / `parentTaskId` / `agentId` / `requesterAgentId` / `runId` / `label` / `task` / `status` / `deliveryStatus` / `notifyPolicy` / `createdAt` / `startedAt` / `endedAt` / `lastEventAt` / `cleanupAfter` / `error` / `progressSummary` / `terminalSummary` / `terminalOutcome`

原生枚举(同文件 :26-55,原样使用,本项目不新增、不归并、不翻译):

- `TASK_RUNTIMES` = subagent / acp / **cli** / cron —— 本项目派发的任务落 `cli`。
- `TASK_STATUSES` = queued / running / succeeded / failed / timed_out / cancelled / lost
- `TASK_NOTIFY_POLICIES` = done_only / state_changes / silent
- `TASK_DELIVERY_STATUSES` = pending / delivered / session_queued / failed / parent_missing / not_applicable
- `TASK_SCOPE_KINDS` = session / system

本项目对这些值只做一件事:经 FR-2 状态查询工具透传给 LLM(`contract/cases.md` §0.5 字段挑选)。不做映射表、不做状态归并、不做"是否真的完成"的二次判定(PRD C1 已裁决完成真实性归 OpenClaw)。**本轮更新(推翻原"渲染进注入模板"这一用途)**:FR-3 回流播报**不读取**这些字段——依据 D-2,事件通路上读不出任何 OpenClaw 原生终态字符串,回流播报只转述 assistant 结论消息的 `event.text`,详见下方 MCP 事件对象与 §0.9 回写。

**MCP 事件对象** —— `events_wait` 的返回体。**本轮更新**:schema 已于定义段内提前实测(P-06 已关闭,详见上方 P-12;原样样本 `baseline/mcp-event-sample.json`/`baseline/failure-path-samples.json`)。顶层键 `cursor`/`messageId`/`messageSeq`/`raw`/`role`/`sessionKey`/`type`,**`text` 为条件键**(工具调用消息顶层无此键,依据 D-10)。事件里读不出任何 OpenClaw 原生终态字符串(`raw.status` 是消息产出瞬间的会话级状态,不是任务终态,依据 D-2)——因此回流播报只允许依赖两项:①任务可关联标识(`event.sessionKey`,精确等于 §0.6 生成的 key);②收尾判据 `raw.message.stopReason == "stop"`(依据 D-10,用于区分"结论"与"工具调用/过程播报/中止"三种非结论形态)。不读取、不解析任何其余字段。

### 2. 本项目内存持有物(全部 session-scoped,进程退出即消失)

**`DispatchRegistry`** —— 一个会话级对象,持有本次通话已派发任务的最小索引。

| 字段 | 类型 | 含义 | 写入时机 | 移除时机 |
|---|---|---|---|---|
| `session_key` | `str` | ADR-1 生成的关联主键,同时是 lookup | `dispatch` job 拿到 lookup 后 | 该任务的结论消息事件(`raw.message.stopReason == "stop"`)到达后 |
| `label` | `str` | 第二个 LLM 给的一句话摘要,只用于播报措辞与多任务区分 | 同上 | 同上 |
| `created_at` | `float` | 单调时钟时间戳,仅用于日志排序 | 同上 | 同上 |

**本轮订正(P22:结论被推翻后过程文档未同步)**:"移除时机"原文写的是"该任务终态事件到达后",沿用的是已被 D-2 证伪的旧回程机制表述(design 上一轮已把整条回程机制改写为"结论消息事件",但这张表当时漏改);现已订正为与 FR-3/ADR-7 一致的措辞,行为本身未变(仍是同一个"收到那条会被播报的消息"的时点)。

不变量:①不含任何状态字段——问状态一律现查 OpenClaw;②不落盘、不进 context、不进任何跨会话结构;③按 R5 约定由工厂函数构造,禁模块级单例;④注册表为空时 `get_task_status` 返回空数组而不是报错;⑤**本轮新增**:同一会话在途条数(注册表长度)受 `MAX_INFLIGHT_TASKS = 3` 硬上限约束,详见 §0.3 回写与 ADR-8。

**注入队列** —— 会话级 `asyncio.Queue`,元素是**已渲染好的字符串**(模板渲染在入队前完成),不是事件对象。它是"投递调度"缓冲,不构成也不定义任何新任务状态(PRD 全局口径已把这条标为唯一例外边界并说明其性质)。上限:不设长度上限,但注入器一次取空并合并成单帧,队列不会累积跨轮次。

**`app_resources`** —— 一个 dataclass,持有 `main_worker` 反向引用、`DispatchRegistry`、注入队列、`cfg` 中派活相关的三个配置项。经 `PipelineWorker(app_resources=…)` 传入,工具函数经 `params.app_resources` 读取(官方通道,补上盘点缺口 K3)。

### 3. 已有数据的迁移策略

本变更**不触碰任何已有持久化数据**——本项目此前就没有数据库、没有文件状态存储(盘点 K4),两个 `LLMContext` 是纯内存。因此不存在 expand-contract 意义上的数据迁移。

唯一带"迁移"性质的是一处**文本契约**变更:`prompts.py::CAPABILITY_BOUNDARY_SECTION` 删除"无执行能力"这一句。它的下游消费者是 `SYSTEM_PROMPT` 与 `evals/r4_no_false_completion.yaml` 的 judge 判据文本。按 expand-contract 的次序处理:

1. **expand**:先把 `r4_no_false_completion.yaml` 的 judge 判据改成不再引用"没有执行操作的能力"这一表述、只保留"没有声称已经完成/已经处理/已经改好"这半条(该半条在删除前后都成立)。
2. **migrate**:再删 `CAPABILITY_BOUNDARY_SECTION` 里的那句表述。
3. **contract**:改动落地后复跑 C-03 的既有场景集与 C-17 的基线对读,确认删除没有波及其余四段。

这个次序的意义:两步之间的任何一个中间态,r4 场景都不会因为"判据引用了已删表述"而假失败。

---

## 任务拆分

粗粒度切分,每项写清独占路径与依赖。S2b 据此落 `tasks/T-*.md`,届时按此表做并行组声明(坑 P56:独占路径互斥,重叠的必须双双 worktree)。

| # | 任务 | owner | 独占路径 | 依赖 | 覆盖 FR / 用例 |
|---|---|---|---|---|---|
| T-0 | 行为基线取样:建 `baseline_probe.yaml`,改动前跑一轮存档真实回复 | qa-tester | `server/evals/baseline_probe.yaml`、`pipeline/task-dispatch/baseline/` | 无 | C-17 |
| T-1 | MCP 事件样本取样 + bridge 连通:起 `openclaw mcp serve`、跑一次真实 `events_wait`、存档事件 JSON | backend-dev | `pipeline/task-dispatch/baseline/mcp-event-sample.json` | C-00 环境前置门 | 解 P-06 敞口;FR-3 前置 |
| T-2 | 契约常量模块:`task_dispatch_contract.py`(常量 + dataclass,零副作用导入) | backend-dev | `server/task_dispatch_contract.py` | 无 | `contract/cases.md` §0 |
| T-3 | 执行层:`OpenClawExecWorker`(session key 生成、detached spawn、lookup 轮询、job 响应;**本轮删除"设通知策略"步骤**) | backend-dev | `server/task_dispatch.py`(与 T-4/T-5 同文件,见下方说明) | T-1, T-2 | FR-1 / FR-5(原 FR-6);C-02 C-04 C-15 |
| T-4 | 回流层:MCP 事件循环 + `_DispatchMaterialInjector` + 注入模板常量 | backend-dev | 同 T-3 文件 + `server/prompts.py` 的新增常量 | T-1, T-2, T-3 | FR-3;C-09 C-10 C-11 |
| T-5 | 决策层:`TaskDispatchWorker(UIWorker)` + 快脑两个工具 + `DispatchRegistry` | backend-dev | 同 T-3 文件 | T-2, T-3 | FR-1 / FR-2 / FR-4(原 FR-5);C-01 C-05 C-06 C-07 C-08 C-14 |
| T-6 | 装配层:`bot.py` 的五处挂点 + `AssembledPipeline` 四个新字段 + `add_workers` 三 worker | backend-dev | `server/bot.py` | T-3, T-4, T-5 | 装配链端到端;C-09 结构性半 |
| T-7 | 提示词迁移:`CAPABILITY_BOUNDARY_SECTION` 最小改动 + r4 场景 expand-contract 两步 | backend-dev | `server/prompts.py`、`server/evals/r4_no_false_completion.yaml` | T-0(基线须先取) | PRD C1 / C2;C-03 |
| T-8 | 测试层:`test_task_dispatch.py` 新建 + `test_dual_brain.py::TestAssemblePipeline` 结构断言扩写(**本轮修正落点**,原表述误指 `test_bot.py`,该文件实测无结构断言、仅 4 条 provider builder 测试,见 §E L2 回写) | backend-dev | `server/tests/test_task_dispatch.py`、`server/tests/test_dual_brain.py` | T-2 ~ T-7 | L1 / L2;C-16 |
| T-9 | eval 场景层:五个新场景(**本轮增 `dispatch_capacity_reached.yaml`**) | qa-tester | `server/evals/dispatch_*.yaml` | T-6 | C-01 C-04 C-09 C-10 C-11 C-19 |
| T-10 | 真机联测与报告 | qa-tester | `pipeline/task-dispatch/test-report.md` | 全部 + C-00 | C-02 C-05 C-06 C-14 C-15 C-18(**本轮删 C-12/C-13、增 C-18**) |

**关于 T-3/T-4/T-5 共用 `server/task_dispatch.py`**:三者是同一条派活链路的三段,拆成三个文件会把 `DispatchRegistry`、注入队列、契约常量的引用关系摊成一张互相 import 的网。建议 S2b 把三者合成**一张任务卡**(单 owner 串行),而不是三卡 + worktree 隔离——本变更的并行收益主要在 T-0/T-1/T-9(可与实现并行)与 T-7(独立文件),不在这三段之间。若 S2b 仍拆卡,三卡必须**双双声明 worktree** 才过机检。

**并行组建议**:第一组 T-0 ‖ T-1 ‖ T-2(互不重叠路径);第二组 T-3+T-4+T-5(合卡)‖ T-7 ‖ T-9;第三组 T-6;第四组 T-8;第五组 T-10。

---

## 风险与难逆点

### 难逆点(单列)

**D-1 · `prompts.py` 能力边界段的语义放开(中等难逆)**
- 一旦删掉"无执行能力"这句,快脑就获得了"我可以把事情交出去"的自我认知。回退需要同步回退 r4 场景判据与 tools 注册,且回退后如果 tools 还在,模型会看到工具却被 prompt 告知做不到,处于自相矛盾状态。
- 理由:PRD C1 判定为"必须改,不可回避"的冲突项,无绕过路径。
- 缓解:expand-contract 两步次序(见数据模型 §3)+ C-17 基线对读,把这次语义放开对既有 20 条场景的影响在第一天暴露出来。

**D-2 · 引入多 worker 与 bus 运行时(中等难逆)**
- `WorkerRunner` 从挂 1 个 worker 变成挂 3 个,worker 间的 job 语义、停止次序、失败传播都进入了运行画面。回退不是删代码那么简单:`run_bot` 的收口形状与 `AssembledPipeline` 的断言面都会跟着变。
- 理由:PRD 已把两级决策(快脑路由 + 第二个 LLM)定为 FR-1 的形态,用户对 worker 选型已拍板;单 worker 内实现两级决策等于自研 delegation,与"减少自研"口径冲突。
- 缓解:三个 worker 都是 root worker、彼此只经 job 通信;主 worker 不开 `bridged`,既有双脑管线内部不受 bus 影响。

**D-3 · 自行生成 session key 这条命名约定(低难逆,已实测降低风险;此编号为 design 内部难逆点序号,不同于上方引用的 `preflight-live.md` 证据编号 D-1..D-12)**
- 原风险:五条 FR 都挂在这个 key 上。若 C-15 证伪"`tasks show` 能用 session key 解析",关联主键要整体换成派发后反查 task id,ADR-1 的被否方案会重新上桌,T-3/T-5 需返工。
- **本轮更新(已实测验证,风险解除)**:C-15 已提前跑过(`preflight-live.md` §2)——四次真派发的 `childSessionKey`/`ownerKey`/`requesterSessionKey` 均等于自生成的 key,`tasks show` 用该 key 精确命中(exit=0)。ADR-1 的设计前提成立,不再需要在 T-3 完成时另行提前验证。

### 风险清单

**R-1 · 环境前置未满足(当前已实测为未满足,最高优先)**
- 现象:Gateway 未运行(P-05);exec 审批生效策略实测为 `mode=ask` / `security=allowlist` / `ask=on-miss` / `askFallback=deny`,agent `dev` 的白名单只有两条(`/usr/bin/cat` 与一条 node-command 哈希)。
- 后果:PRD"前提假设"一节要求的"不触发运行时审批"当前**不成立**——派活任务一旦跑到白名单外的命令就会挂起等审批,而本期没有任何机制处理它,按 `askFallback` 默认 `deny` 超时终局拒绝,任务失败且用户在通话中得不到解释。
- 处置:落 `contract/cases.md` C-00 环境前置门,验收前由用户完成两件事(策略两侧都要配,取严合并的坑见 PRD 前提假设节)。**不改设计**。
- 归属:需用户处置,已列进回执。

**R-2 · `events_wait` 事件负载 schema 未实测(P54 残余敞口)—— 本轮已实测解除**
- 原后果:若实现按猜测写字段名,回流播报会在真机上静默失效。
- **解除依据**:定义段内已提前实测取样(`preflight-live.md` §3/§8/§10,原样样本 `baseline/mcp-event-sample.json`/`baseline/failure-path-samples.json`),字段形状与筛选口径已写入契约 §0.8/§0.9(D-2/D-3/D-10)。T-1 的产出物(样本文件)已经就位,T-4 实现时直接消费该样本对齐解析代码,不再是"先取样再写解析"这个开工前的门。

**R-3 · "`tasks show` 支持 session key 解析"—— 本轮已实测验证,解除敞口**
- 原依据:源码侧有 `taskIdsByRelatedSessionKey` 索引(索引 `ownerKey` 与 `childSessionKey`),但 CLI 层的 lookup 解析次序未逐行核实。
- **解除依据**:`preflight-live.md` §2(C-15 前移验证结论:成立,C-15 判定通过)——四次真派发,session key 直接作 lookup 传 `tasks show` 均 exit=0 命中,`childSessionKey`/`ownerKey`/`requesterSessionKey` 三者均等于生成的 key。ADR-1 的关联主键设计成立,不再是敞口。

**R-4 · `openclaw agent` 是否真的产出一条可查的 `cli` 运行时任务记录 —— 本轮已实测验证,解除敞口**
- 原依据:`TASK_RUNTIMES` 含 `"cli"`(源码实读),但本机当时无存量数据佐证。
- **解除依据**:`preflight-live.md` §1(R-4 结论:成立)——四次真派发四次都落 `runtime: "cli"` 的任务记录(`tasks list --runtime cli` 由 0 条变 4 条),记录创建延迟 2.56-2.76 秒(即 D-7 时序开销的来源)。派发形态无需改走 `sessions_spawn`,原设计维持不变。

**R-5 · 第二个 LLM 的 token 成本与延迟**
- `UIWorker` 自带完整二次推理(`ui_worker.py:409-448` 实锤)。用户已明示不考虑 token 成本;但延迟会叠加在 `dispatch_task` 工具调用上(工具 `timeout_secs=20`)。
- 处置:C-01 的判据是"后续轮次不被阻塞",不是"派活工具本身很快";若二次推理常态超过 20 秒,调大 `timeout_secs` 并在 test-report 记录实测分布。

**R-6 · `server/evals/fault_run/bot.py` 是 `bot.py` 的副本,会因 `prompts.py` 改动间接受影响**
- 本变更不动它(不在派单范围)。但它 import 同一个 `prompts`,`CAPABILITY_BOUNDARY_SECTION` 改动会传导过去。
- 处置:C-03 的既有场景复跑范围含 `dual_brain_fault`,能覆盖到;若发现该副本与主文件已漂移,记 RISKS 不动手。

**R-7 · 坑 P57 的处置(改动触及 prompt / 上下文 / 引擎装配)**
- 本变更同时触及三者:改 `SYSTEM_PROMPT` 的一段、给 `fast_context` 加 tools、往快脑分支头部插处理器。只锁确定性指标(分支表、耗时、结构断言)不足以发现 LLM 侧行为漂移,也无法把本次改动与既有存量缺陷(如 D-004 慢脑跑偏、D-005 快脑重复作答)分开归因。
- 处置:C-17 固定问题集基线,**改动前先跑一轮存真实回复原文**(T-0,排在所有实现任务之前),改动后同样跑一轮,两份归档逐条人工对读,差异写进 test-report.md。不设自动阈值——目的是第一天暴露存量缺陷,不是拦门。

**R-8 · 新增依赖待批**
- `pipecat-ai[mcp]` extra(带出 `mcp[cli]>=1.11.0,<2`),依据 P-10。不批准则回退到 ADR-3 被否方案 B(自写协议层),需重估 T-1/T-4 工作量。

**R-9 · 状态查询命令的时序开销(D-7,本轮新增)**
- 现象:`tasks show` 单次调用固定约 2.3-2.6 秒(node CLI 冷启动)。①`get_task_status` 省略 lookup 时对内存注册表逐条串行跑该命令,在途任务数较多时累计耗时可能逼近或超过契约 §0.2 T2 的工具超时;②派活发起后约 2.6 秒内查询同一个刚生成的 lookup 会返回"未命中"(exit=1),与真实不存在的 lookup 输出完全相同、不可区分。
- 处置:①不属于本轮需要新增自研逻辑的问题——契约 §0.2 T2"单条查不到"本就统一降级为 `{"found": false}` 而不抛异常,该既有处理方式已经自然吸收"短窗内查不到"这一现象,不需要额外的重试/宽限期定时器;②**本轮已由用户裁决关闭(替代"上调 timeout_secs")**:改用 `MAX_INFLIGHT_TASKS = 3` 从根本上收窄在途任务数上限——3 × 2.6s ≈ 7.8s,远小于 `timeout_secs=15.0`,该数值维持不动,**无联测待办**。检查点、fan out 场景处置、达上限行为约定见契约 §0.3、装配链步骤 8、ADR-8。

**R-10 · 在途上限与"未产出结论消息的异常路径"(非目标条目 11)叠加后,一个名额可能被永久占用(本轮新增,推理结论非实测,如实标注)**
- 现象(推理,非实测——按既有事实链条推出,标注置信度中等):`DispatchRegistry` 的移除时机是"收到该任务的结论消息事件后"(见数据模型 §2 本轮订正);PRD 非目标条目 11 已认定三种失败形态(前置校验拒绝 `failed`、运行中 precheck 失败 `failed`、维护扫描判定 `lost`)**实测确认零条 assistant 事件产生**,即这类任务永远等不到会触发移除的那条消息。叠加本轮新增的 `MAX_INFLIGHT_TASKS = 3` 上限后,若某次派发落入这三种形态之一,它会**占用一个上限名额直至本次通话结束**,而不会像正常任务那样在完成后腾出空位——极端情况下(同一通话内连续 3 次都撞上这三种形态之一)会导致后续所有派活请求都被 ADR-8 的"整批拒绝"挡住,即便实际上没有任何任务真的还在跑。
- 处置:**本期不做修复,已经用户在 s2a 呈批回合当面裁决"不管"(2026-08-08,原话「写清楚不管,避免后面有歧义」),此项已关闭,不是待办、不留悬念、不进债务簿**。后续任何节点(实现、验收、评审)读到本条一律照"不修"执行,**不得**因"看起来像个缺口"而自行补兜底逻辑;若确要改判,须由用户重新拍板并走回 s2a 修订流程,不得在实现期私自加。
  - 与 PRD 非目标条目 11"本期只做核心流程,异常情况很多不可能都处理得了"的既有裁决同向——修复需要一个不依赖消息事件的兜底回收机制(如超时后自动回查 `tasks show` 并按终态清理注册表),这正是非目标条目 11 已经明确排除、留给后加的能力。
  - 不处理的后果范围(呈批时已如实告知用户后其才作出上述裁决):影响面为"小概率下派活能力在**本次通话内**暂时性收紧",不是数据丢失、不是错误播报;`DispatchRegistry` 为 session-scoped(见数据模型 §2),通话结束即清零,不跨会话累积;且三种静默失败形态多属配置错误类可稳定复现的问题(如 agent id 写错),不是随机偶发。

### `research/pipecat-worker-source-verification.md` §6 条目 1(补测试硬要求)的落实位置

原要求:若选 `UIWorker` 并使用 `ui_job_group` 进度卡链路,必须自行补测试——官方在 `UIJobGroupContext` 上无覆盖测试(codegraph blast radius 实锤)。

本期落实方式,三处都写死,不以"官方件默认可靠"带过:

1. **本期不启用该链路**(PRD 选型说明已定),因此四信封端到端测试**本期不需要写**。
2. **不启用这件事本身要被守住**:`contract/cases.md` C-16 = `grep -rn "start_ui_job_group\|ui_job_group\|__cancel_job_group" server/ --include=*.py` 零命中 + `test_task_dispatch.py` 内一条静态断言测试。落在 T-8。
3. **启用前置门**:将来(2 期 G4)启用 `ui_job_group` 前,必须先补齐四信封(`group_started` / `job_update` / `job_completed` / `group_completed`)是否实际抵达客户端、`cancellable=True/False` 是否分别生效、`start_ui_job_group` 是否确实立即返回不阻塞调用方这三组测试。本条建议由主会话登记进 `pipeline/debts.md`,本节只作记录,不代改债务簿。

### D-003 是否先偿:建议**不先偿**,理由与守法

- D-003 内容:`server/bot.py` 模块顶层 `load_dotenv(override=True)` + `cfg = load_config()`,逼 `test_bot.py` 用 `sys.modules.pop` + `importlib.import_module` 绕过。TTL 2026-12-31,未超期;s0 的 debts-check 也未阻断。
- 建议不先偿,三条理由:①本变更已同时触及 `bot.py` 装配、`prompts.py` 文本契约、新增两个 worker 与一个处理器,再叠一次配置加载重构会把 diff 拉进 `config.py` 与 `test_bot.py`,评审与回滚都变难,而这两件事之间没有技术依赖;②D-003 的危害面是"测试用 `sys.modules` 全局手法、并行跑测试时可能污染",本变更不引入 `pytest-xdist`、也不新增 `import bot` 的测试文件,危害面不扩大;③PRD C5 对本变更的要求只是"新增代码不因图省事而进一步扩大该模块现有债务面",不是要求清偿。
- 不先偿的**守法**(写进任务卡验收项,不是口头承诺):新增逻辑一律落 `server/task_dispatch.py` 与 `server/task_dispatch_contract.py`,两者**不得**在模块顶层读环境变量或调 `load_config()`,全部经函数参数注入;新增单元测试直接 import 这两个模块,**不得**新增任何 `import bot` 的测试文件,因此 `sys.modules` 手法的使用面维持在现有一处不增加。`bot.py` 内的改动限于装配挂点(五处)与 `run_bot` 的一行,由既有 `bot_module` fixture 覆盖。
- **最终由用户裁决**;若用户选择先偿,建议单独起一个变更做,不并入本次。
