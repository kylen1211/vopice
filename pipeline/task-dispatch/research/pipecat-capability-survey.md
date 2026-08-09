# pipecat 官方能力核实 · task-dispatch(C4 派活)

> 取数方式:codegraph 查本地 clone `~/git/source-project/pipecat`(**v1.7.0-36-g0db3c9a0a**)+ 直接读示例源码;
> 版本兼容性对照本项目 venv 实装版 **1.6.0**。核实日期 2026-08-08。
> 标注口径:【实锤】= 本次读到 verbatim 源码/文件;【推测】= 由证据推导但未直接验证。

## 0. 版本兼容性(先决问题,已解决)

本项目 `server/pyproject.toml` 锁 `pipecat-ai==1.6.0`,而本地 clone 是 v1.7.0-36。核实结果:

| 项 | clone v1.7.0-36 | venv 实装 1.6.0 | 结论 |
|---|---|---|---|
| `pipecat/workers/` | 有 | **有**(base_worker.py / llm / proxy / ui / runner.py) | 存在 |
| `pipecat/bus/` | 有 | **有**(bus.py / adapters / local / network / serializers / messages.py / queue.py / bridge_processor.py) | 存在 |
| `BaseWorker.job` | :694 | **:694** | 行号完全一致 |
| `BaseWorker.job_group` | :782 | **:782** | 行号完全一致 |

【实锤】**这套多 worker API 在 1.6.0 与 1.7.0 之间未发生位移**,clone 源码可直接作为 1.6.0 的设计依据。
(注:仅核实了上述符号位置一致,不等于整个框架无差异;S2a 若用到其他符号需逐个复核。)

## 1. 官方 worker / bus / job 机制(`src/pipecat/workers/base_worker.py`)

- **worker 类型层次**【实锤】:`BaseWorker` → `PipelineWorker` → `LLMWorker` → `LLMContextWorker` → `UIWorker`。
  `BaseWorker` 可以是**纯 bus worker**(无 pipeline),`run()` 默认实现就是订阅 bus 后等停止信号。
- **job 协作**【实锤】:`@job` 装饰器(:694)、`job_group`(:782);worker 内部维护 `_active_jobs`/`_job_handler_tasks`/`_job_groups`/`_job_locks`,支持**多 job 并发在途**。
- **13 个 job 生命周期事件**【实锤】:`on_job_request` / `on_job_response` / `on_job_update` / `on_job_update_requested` / `on_job_completed` / `on_job_error` / `on_job_stream_start` / `on_job_stream_data` / `on_job_stream_end` / `on_job_cancelled`,外加 `on_worker_ready` / `on_worker_failed` / `on_bus_message`。
- **停止语义**【实锤】`BaseWorker.stop()`(:364-375)原文:取消所有 job group,并把仍在途的 job **以 `JobStatus.CANCELLED` 回报给请求方**,docstring 明写 "so parents aren't left waiting"。
  → 与已拍板底稿的"重启语义诚实而廉价"同向,框架层已给了一半。
- **bus 实现三选**【实锤】:`AsyncQueueBus`(进程内)/ `PgmqBus`(PostgreSQL 消息队列)/ `RedisBus`,均 extends `WorkerBus`;bus 下有 `adapters/`(`ToolsSchemaAdapter`、`LLMContextAdapter`)、`serializers/`(`JSONMessageSerializer`)、`local/`、`network/` 分层。
  → ~~直接关系 Q5 持久化选型:跨进程/持久化不必自研,官方有现成 bus 后端。~~
  **【2026-08-08 更正,本推测有误】** 外部调研经本地源码核实:这三种 bus 后端是**消息投递层,不是结果存储层**——
  `RedisBus.publish()` 就是原生 pub/sub(`redis.py:88-96`),无订阅者在线则消息直接丢,全程零 `SET`/`HSET`;
  `PgmqBus` read 后即 archive 消息本身,无历史重建/回放路径;`AsyncQueueBus` 纯内存,重启即空。
  三者存在的**唯一理由是跨进程/跨机器**,本项目单进程单用户场景根本用不上。
  **bus 后端选型与持久化需求是两件不相交的事**,详见 `external-research.md` Q5。
- **`PipelineWorker` 关键参数**【实锤】(`src/pipecat/pipeline/worker.py:227-321`):
  - `app_resources`(:233):官方明确"passed to tool handlers as `FunctionCallParams.app_resources`",框架不复制不清理 → **派活跨 handler 共享状态的官方通道**,补上盘点里的缺口 K3。
  - `bridged`(:234):`None`=不桥接;`()`=包上 bus edge processors 接受所有 bridge;`("voice",)`=只接指定 → **现有对话 pipeline 上 bus 的官方开关**。
  - `cancel_runner_on_idle_timeout`(:283-292):docstring 明写 "set to `False` for a sidecar `PipelineWorker` that should self-cancel on idle without bringing down its peers" → **官方明确支持 sidecar worker 模式**。

## 2. 两个决定性官方示例

### 2.1 `examples/multi-worker/code-assistant/` — 回答"执行载体"(118+183 行)

【实锤】架构(README 原文):

```
Main worker (transport + LLM + `ask_code` tool)
  └── job → CodeWorker (Claude Agent SDK)
```

`code_worker.py` 全文 118 行,要点:

- `CodeWorker(BaseWorker)` 是**纯 bus worker,无 pipeline**;`on_job_request` 入队,`_worker_loop` 串行消费。
- 用 `ClaudeSDKClient` + `ClaudeAgentOptions`(`permission_mode` / `allowed_tools=["Read","Bash","Glob","Grep"]` / `model` / `max_turns`)**维持持久 session**,后续问题共享上下文。
- 结果回传:`send_job_response(job_id, {"answer": answer})`;异常回传 `status=JobStatus.ERROR`。
- 派发侧:主 worker 的 tool 里 `worker.job("code-worker", payload=...)`。

→ **Q1(执行载体)有官方答案**:复用 Claude Agent SDK 作后台执行体,官方示例即此形态,集成成本约百行。
  这更新了 `docs/capability-ledger.md` G3 行"执行载体待定"的状态。

> **⚠️ 2026-08-08 重要更正:这个示例不能照搬,它的取消/超时是失效的。**
> 外部调研逐行核实(详见 `external-research.md` Q1 §1.1):`CodeWorker.on_job_request()` 只做入队、瞬间返回,
> 于是框架追踪用的 `_job_handler_tasks[job_id]` 记录立刻被 pop;而真正耗时的 Claude SDK 调用跑在**另一个**
> 长驻 `_worker_loop` task 里,**不在追踪范围内**。后果:收到取消/超时时框架查不到 handler task → 不会真正打断 →
> 却仍回一个 `status=CANCELLED` 给请求方,请求方的 JobGroup 也已被 pop。**任务继续在后台跑完**(继续烧时间与 API 成本)、
> 期间串行队列被卡住,跑完后 `send_job_response()` 打给一个已不存在的 job_id,**静默丢弃**。
> 这不是框架缺陷,是示例实现的缺口(框架的 `on_job_cancelled` 钩子按文档正常触发,只是示例没覆写它)。
>
> **官方现成的正确解法**(不需自研):照 pipecat 自己的 `UIWorker` 写——`@job(name="respond", sequential=True)`
> 装饰(`workers/ui/ui_worker.py:390`),把整个往返完整跑在被追踪的 handler 内部
> (`_run_llm_turn` docstring 原文:"Spanning the full round-trip is what makes the job single-flight"),
> 而不是把活丢给外部 queue+loop。这样同时拿到"单会话顺序处理"与"逐任务可靠取消/超时"。
> 已知代价(`job_decorator.py` docstring):排队等待时间算进请求方的超时预算,忙时可能"还没轮到就先超时"。
> 另需在 `on_job_cancelled` 里显式调用 SDK 的 `Query.interrupt()` / `Query.stopTask(taskId)`,
> 让取消真正传导进 SDK 会话,而不是只停在 pipecat 这一层。

### 2.2 `examples/multi-worker/ui-worker/async-tasks/` — 回答"派发不中断 + 状态面板 + 取消"(384 行 + 客户端)

【实锤】README 原文要点:

- `start_ui_job_group("wikipedia","news","scholar", payload=..., label=...)` **立即返回**,
  所以 `reply` 工具能先说一句"正在办",**peer workers 在后台跑,主 LLM 可继续接后续轮次**
  → 直接对应 G3 硬需求"派发期间对话不中断",官方现成。
- **四个 `ui-job-group` 信封**自动转发到客户端:`group_started` / `job_update` / `job_completed` / `group_completed`;
  客户端用 `RTVIEvent.UIJobGroup` 消费,按 `job_id` 维护状态图渲染每个 worker 的进度
  → 直接对应"任务状态查询 + 面板",官方现成。
- **取消**:客户端 `client.cancelUIJobGroup(job_id, reason)` → 保留事件 `__cancel_job_group` → `UIWorker` 转成 `cancel_job_group(job_id)`;被取消 worker 报 `cancelled`
  → 直接对应"紧急中止",官方现成。
- **多任务独立**:README 的 "Research the moon, then research Mars" 明示两个 group 并发
  → 直接对应"多任务独立",官方现成。
- peers 是**普通 `BaseWorker`**,在 runner 上启动。
- README 自陈**不覆盖**:真实 worker 集成(示例 peer 是模拟的)、LLM 驱动的 peer、流式分块(`send_job_stream_data`)、worker 间嵌套 fan-out。

### 2.3 `@tool` 装饰器与"schema 强制终结符"模式

- 【实锤】`workers/llm/tool_decorator.py:14` `@tool(cancel_on_interruption=True, timeout_secs=None)`;
  `cancel_on_interruption` **默认 True** → 打断时自动取消工具调用,与本项目既有打断语义需一起评估。
- 【实锤】`workers/ui/ui_tools.py` `ReplyToolMixin.reply`:一轮一次工具调用、不链式;docstring 原文
  "the required `answer` argument is enforced by the API schema so the model cannot omit the terminator"
  → **用 schema 必填字段强制模型必须给出口头答复**,这是 Q3(防谎报/防漏答)可直接借鉴的官方手法。
- 结果回传 `respond_to_job(answer, tts_speak=True)` 支持逐字 TTS 播报。

### 2.4 官方三层架构:主 worker 与 UIWorker 是**并存**,不是二选一【实锤·关键】

`async-tasks/bot.py` 文件头架构注释(:22-38)原文结构:

```
Main worker (PipelineWorker, owns transport + RTVI)
  ↓
ResearchWorker (UIWorker)
  └── @tool reply(answer, research_query=None)
        └── (if research_query) start_ui_job_group("wikipedia", "news", "scholar")
  ↓
Three peer workers (BaseWorker each)
```

要点:

- **UIWorker 不替换主 PipelineWorker**,主 worker 依旧独占 transport + RTVI;UIWorker 是挂在同一 runner 上的另一个 worker,自带 LLM/context,只负责出工具、派 job group、转发生命周期事件。
- peer 实现极轻:`_SimulatedResearcher(BaseWorker)`(:160)做基类,`WikipediaResearcher`/`NewsResearcher`/`ScholarResearcher`(:200/:210/:220)三个子类只换数据。
- `@tool_options(cancel_on_interruption=False, timeout_secs=30)`(:282)——**官方在派活类工具上显式关掉了"打断即取消"**,正是派活场景所需(用户插话不该撤销已派任务)。
- 装配收口在 `PipelineWorker(...)`(:338)+ `runner.add_workers(...)`(:364),与本项目现有 `run_bot` 收口形态一致。
- `tests/test_pipeline_worker_ui_bridge.py` 有 `TestUIBridgeInbound`(:79)/`TestUIBridgeOutbound`(:136)/`TestUISpeakBridge`(:252)三组——**PipelineWorker ↔ UI 的桥接是官方支持且已测的**。

→ **本项目现有双脑 `ParallelPipeline` 可原样保留为主 PipelineWorker,派活以"加 worker"而非"改骨架"的方式接入**,符合项目纪律"官方脚手架结构不动"与用户口径"骨架不改"。

## 3. G3 子能力 → 官方件映射(更新 capability-ledger 的判断)

| G3 子能力 | 官方件 | 结论 |
|---|---|---|
| 任务派发 | `worker.job()` / `start_ui_job_group()` | **现成** |
| 状态查询 | 13 个 job 事件 + 四信封转发 | **现成** |
| 多任务独立 | 多 job 并发在途 + 并发 job group | **现成** |
| 紧急中止 | `cancel_job_group` + `JobStatus.CANCELLED` | **现成** |
| 派发期间对话不中断 | `start_ui_job_group` 立即返回 | **现成** |
| 后台执行载体 | `BaseWorker` + Claude Agent SDK(code-assistant) | **现成范式** |
| 完成确认铁律 / 关键节点播报 / 状态未知处置 | 无官方件 | **自装**(可借 2.3 的 schema 强制模式) |
| 授权确认链 + 审计 | 无官方件 | **自装** |
| 手动接管兜底 | 无官方件 | **自装** |

【推测】按此映射,本变更的自研量主要落在"文本契约 + 授权审计"层,而非任务编排层——
编排层照搬官方即可。这会显著影响 S2a 的设计取舍与工作量估计,但**结论待 PRD 确认范围后在 S2a 复核**。

## 4. 与现状盘点(codebase-survey.md §5)的交叉

- **对 C3(快脑分支是唯一输出通道)**:【实锤,更正本文早前的推测】按 §2.4 的官方三层架构,UIWorker 与主 PipelineWorker 是**并存**关系,
  主 worker 仍独占 transport + RTVI,因此引入 UIWorker **不会**新增第二条对外输出通道,与 C3 不冲突。
  两个示例不是互斥路线:`code-assistant` 示范"执行体怎么写",`async-tasks` 示范"派发/状态/取消怎么串",可同时取用。
  S2a 需裁决的实际是"派活工具挂主 worker 还是挂独立 UIWorker",而非"要不要重构双脑骨架"。
- **对 C4(`on_client_disconnected` 直接 `worker.cancel()`)**:
  `cancel_runner_on_idle_timeout=False` 的 sidecar 模式给了"会话断开但后台 worker 存活"的官方开关,
  是 C4 冲突的候选解法【推测,需 S2a 验证语义是否覆盖显式 disconnect 而不只是 idle timeout】。
- **对 K3(无 app_resources)**:`PipelineWorker(app_resources=...)` 直接补齐,无需自造全局状态。
- **对 K1(无 function calling)**:需从零引入 tools;`@tool` 的 `cancel_on_interruption` 默认值要与既有打断行为一起测。

## 5. 可直接复用的官方测试资产【实锤】

`tests/`:`test_base_worker.py`、`test_bus.py`、`test_bus_json_serializer.py`、`test_bus_network.py`、
`test_job_group.py`、`test_llm_worker.py`、`test_pgmq_bus.py`、`test_redis_bus.py`、
`test_ui_job_lifecycle.py`、`test_ui_worker.py`、`test_pipeline_worker_ui_bridge.py`

`examples/multi-worker/`:`code-assistant`、`async-tasks`、`deixis`、`document-review`、`form-fill`、
`hello-snapshot`、`shopping-list`、`parallel-debate`、`local-handoff`、`distributed-handoff`(pgmq/redis 两版)、
`remote-proxy-assistant`、`sensor-controller`

## 6. 本轮未查、留给 S2a 的问题

1. `async-tasks/bot.py` 全文(384 行)未逐行读——job group 的实际装配写法待 S2a 取用。
2. `UIWorker` 与现有 `ParallelPipeline` 双脑架构的融合可行性未验证。
3. `bridged=()` 后 bus edge processors 对现有 RTVI 泄漏封锁(`ignored_sources`)的影响未评估。
4. 1.6.0 与 clone 的差异只核实了 4 个符号,其余符号 S2a 用到时须逐个复核。
