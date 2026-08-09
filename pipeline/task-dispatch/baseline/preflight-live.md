# 派活链路实机验证纪要(preflight-live)

- 日期:2026-08-08
- 执行:backend-dev(仅取样与判定,未写任何产品代码,未改 prd/design/contract)
- 版本前提:`OpenClaw 2026.7.1-2 (0790d9f)`;实装路径 `/home/ky/.nvm/versions/node/v24.18.0/lib/node_modules/openclaw`
- 源码副本核对:`~/git/source-project/openclaw/openclaw-src/tasks-QPW4uAt4.js` 与实装 `dist/tasks-QPW4uAt4.js` `diff -q` **IDENTICAL**,两者 `package.json` 均为 `2026.7.1-2`,故本文引用的源码行号对实装有效
- 环境:Gateway 运行中(`127.0.0.1:18789`);agent `dev`(workspace `/home/ky/openclaw-workspace`,model `deepseek/deepseek-v4-flash`)
- 期间 Gateway 被并发重启过一次(监听进程 pid 318059 → 327897),重启窗口内出现过一次瞬时读失败;重跑即恢复,不影响以下结论(每条结论均为多次复现)

## 0. 本轮真实派发的四个任务(全部无副作用:纯文本生成,未调用工具、未读写文件、未联网)

| 代号 | session key(自行生成) | taskId | runtime | 终态 | 说明 |
|---|---|---|---|---|---|
| A1 | `agent:dev:voice-agent-cc5ca96e209c` | `143451e8-33f4-4b96-8ee7-f1d854f721cd` | cli | succeeded | 首次连通性验证 |
| B1 | `agent:dev:voice-agent-94935dc26e46` | `888b6b55-4a23-4df4-ad65-114a02f0136b` | cli | succeeded | 对照组:全程不设 notify |
| C1 | `agent:dev:voice-agent-79296061131d` | `952f53df-0101-4331-8aea-be266c38e79a` | cli | succeeded | 实验组:running 期间设 notify done_only |
| D1 | `agent:dev:voice-agent-10b7dc7adace` | `ab850ecc-db46-4d7b-9542-f2a30023b588` | cli | succeeded | notify 竞态复现 |

session key 按 `contract/cases.md` §0.6 规则自行生成:`agent:{agent_id}:voice-agent-{uuid4().hex[:12]}`,`agent_id=dev`。

---

## 1. 验证一 · R-4:`openclaw agent` 是否产出一条可查的 `cli` 运行时任务记录

**结论:成立。** 四次派发四次都落了 `runtime: "cli"` 的任务记录,六条 FR 的共同关联锚点站得住,**不需要改走 `sessions_spawn` 重新设计**。

命令(detached spawn,`setsid nohup`,不等待):

```
openclaw agent --agent dev --session-key "$K" --message-file "$RUN/message.txt" --json
```

派发前存量为 0(design.md P-02 已记录 `tasks list --json` → `count: 0`);派发后:

```
$ openclaw tasks list --runtime cli --json
count= 3 runtime= cli
 - 952f53df-0101-4331-8aea-be266c38e79a cli succeeded silent not_applicable agent:dev:voice-agent-79296061131d
 - 888b6b55-4a23-4df4-ad65-114a02f0136b cli succeeded silent not_applicable agent:dev:voice-agent-94935dc26e46
 - 143451e8-33f4-4b96-8ee7-f1d854f721cd cli succeeded silent not_applicable agent:dev:voice-agent-cc5ca96e209c
```

(第 4 条 D1 在其后产生,末次 `tasks list --json` 为 `count: 4`。)

单条记录原样(B1 终态):

```json
{
  "taskId": "888b6b55-4a23-4df4-ad65-114a02f0136b",
  "runtime": "cli",
  "sourceId": "5209d2c0-1684-468a-a223-4f353e8c698c",
  "requesterSessionKey": "agent:dev:voice-agent-94935dc26e46",
  "ownerKey": "agent:dev:voice-agent-94935dc26e46",
  "scopeKind": "session",
  "childSessionKey": "agent:dev:voice-agent-94935dc26e46",
  "agentId": "dev",
  "requesterAgentId": "dev",
  "runId": "5209d2c0-1684-468a-a223-4f353e8c698c",
  "task": "请写一篇约800字的短文,主题是「水的三态变化」。...",
  "status": "succeeded",
  "deliveryStatus": "not_applicable",
  "notifyPolicy": "silent",
  "createdAt": 1786181755346,
  "startedAt": 1786181755525,
  "endedAt": 1786181763150,
  "lastEventAt": 1786181763139,
  "cleanupAfter": 1786786563138,
  "terminalSummary": "completed"
}
```

**记录创建延迟(spawn → `createdAt`)实测四次:2.66s / 2.76s / 2.57s / 2.56s。** 这段窗口内任务记录尚不存在(见 §2 的负向路径)。

`openclaw agent --json` 自身的 stdout 是合法 JSON(stderr 为空,0 字节),D1 的 stdout 顶层:

```
status= ok  summary= completed  runId= a094a540-abdb-4c2c-a882-1ad8f0955270
payload_text_tail= '...始终涌动着来自浩瀚宇宙的、恒久不息的力量。\n\nPREFLIGHT-OK-D1'
```

---

## 2. 验证二 · C-15 / R-3:`openclaw tasks show <lookup>` 能否用 session key 解析

**结论:成立。C-15 判定通过。**

- 自行生成的 session key 直接作为 lookup 传给 `tasks show`,exit=0 命中。
- `childSessionKey` / `ownerKey` / `requesterSessionKey` **三者都等于**我们生成的 `K`(是**相等**,不是前缀/后缀结构),C-15 要求的"至少一个非空且可关联"满足。
- CLI 自带文档也把 session key 列为一等 lookup 形态:`tasks show` 的 argument 描述为 `"Task id, run id, or session key"`(实装 `dist/register.status-health-sessions-DFp5WAwN.js:311` 附近注册处)。
- `taskId` 形态同样可查,两种 lookup 实测等价。

```
K4=agent:dev:voice-agent-10b7dc7adace
TID=ab850ecc-db46-4d7b-9542-f2a30023b588
lookup=[agent:dev:voice-agent-10b7dc7adace] try1 rc=0 out=0 err=913
lookup=[agent:dev:voice-agent-10b7dc7adace] try2 rc=0 out=0 err=913
lookup=[ab850ecc-db46-4d7b-9542-f2a30023b588] try1 rc=0 out=0 err=913
lookup=[ab850ecc-db46-4d7b-9542-f2a30023b588] try2 rc=0 out=0 err=913
```

(`out`/`err` 为 stdout/stderr 字节数 —— 注意 JSON 落在 stderr,见 §4 不符项 D-1。)

**"派发瞬间即持有 lookup"这条设计成立,但有一个必须处理的时间窗**:派发后约 2.6s 内查同一个 K 会拿到未命中:

```
$ openclaw tasks show agent:dev:voice-agent-94935dc26e46 --json     # 派发后立刻
rc=1  stderr: Task not found: agent:dev:voice-agent-94935dc26e46. Run `openclaw tasks list` to see recent task ids.
```

这与 C-08 要验的"lookup 不存在"负向路径**输出完全相同、不可区分**。

`tasks show` 单次调用耗时(`/usr/bin/time`,同一终态任务连测):

```
tasks_show_elapsed=2.52
tasks_show_elapsed=2.60
tasks_show_elapsed=2.50
notfound_elapsed=2.31      # 未命中路径
```

即每次状态查询固定 ~2.3–2.6s 的 node CLI 冷启动开销。

---

## 3. 验证三 · P-06 / R-2:真实 `events_wait` 事件负载

**结论:样本已取到并落盘(P-06 敞口关闭);但 `contract/cases.md` §0.8 条 4 的第二项要求不成立 —— 事件里读不到 OpenClaw 原生终态字符串。**

取样方式:JSON-RPC over stdio 直连 `openclaw mcp serve`,`initialize` + `notifications/initialized` 后循环 `tools/call events_wait`,**在派发之前先连上**(原因见下)。原样 JSON 已落 `pipeline/task-dispatch/baseline/mcp-event-sample.json`。

### 3.1 拿到了什么

对照组 B1(不设 notify)与实验组 C1(设 done_only)各拿到 **2 条事件,形态完全同构**:

```
EVENT cursor=1 type=message role=user      sessionKey=agent:dev:voice-agent-94935dc26e46
EVENT cursor=2 type=message role=assistant sessionKey=agent:dev:voice-agent-94935dc26e46
```

事件对象顶层键(实测,不是推测):

```
['cursor', 'messageId', 'messageSeq', 'raw', 'role', 'sessionKey', 'text', 'type']
```

`events_wait` 命中时的完整响应形状:

```json
{"result": {"content": [{"type": "text", "text": "event 2"}],
            "structuredContent": {"event": { ...上述事件对象... }}},
 "jsonrpc": "2.0", "id": 4}
```

超时(无事件)时的响应形状:

```json
{"result": {"content": [{"type": "text", "text": "timeout"}],
            "structuredContent": {"event": null}},
 "jsonrpc": "2.0", "id": 5}
```

### 3.2 关键否定结论:事件里没有终态

- 事件类型全集(实装 `dist/mcp-cli-CnI7JKSG.js` 的 6 处 `this.enqueue(` 逐一核对):`message` / `claude_permission_request` / `exec_approval_requested` / `exec_approval_resolved` / `plugin_approval_requested` / `plugin_approval_resolved`。**不存在任何任务生命周期/终态事件类型。**
- assistant 事件的 `raw.status` 实测为 `"running"`、`raw.hasActiveRun` 为 `true` —— 这是**会话级**状态且在消息产出瞬间采样,**不是**任务终态;任务此刻的 `tasks show` 状态也确实还是 `running`。
- 因此 §0.9 模板里的 `{status}`(要求填 OpenClaw 原生终态字符串)**无法从事件读出**,必须在收到 assistant 事件后回查 `tasks show <K> --json` 取 `status` / `terminalSummary`。
- 可用于关联的是 `event.sessionKey`(实测等于我们生成的 `K`)与 `raw.activeRunIds`(实测等于任务的 `runId`/`sourceId`)。§0.8 条 4 的第一项(可关联标识)成立。

### 3.3 队列语义(实装源码 + 实测双证,直接决定 T-4 怎么写)

| 事实 | 依据 |
|---|---|
| `events_wait` 返回 `structuredContent.event` **单数**,且**不返回 `next_cursor`** | 实装 `mcp-cli-CnI7JKSG.js:641-655`;实测响应同形 |
| 消费者必须自己从 `event.cursor` 推进游标 | 同上;见下方踩坑 |
| `events_poll` 才返回 `{events: [...], next_cursor}`(复数),且**不消费**队列 | 实装 `mcp-cli-CnI7JKSG.js:294-305`(`pollEvents` 只 filter 不删) |
| 事件队列是**每个 `openclaw mcp serve` 进程各自的内存队列**,cursor 从 1 起自增(`nextCursor()`),`QUEUE_LIMIT = 1000` 条滚动丢弃 | 实装 `mcp-cli-CnI7JKSG.js:95,376-388` |
| **连接建立之前发生的事件看不到**:新起一个 bridge 后 `events_poll(after_cursor=0)` 返回 `events: 0`,B1/C1 的历史事件全部取不回 | 实测(A1 结束后新连接回捞 → `count 0`) |
| `session_key` 过滤是**精确相等**(`event.sessionKey === filter.sessionKey`) | 实装 `mcp-cli-CnI7JKSG.js:72-76` `matchEventFilter` |
| `timeout_ms` 上限 300000(`EVENTS_WAIT_TIMEOUT_LIMIT_MS`),`events_poll` limit 上限 200 | 实装 `mcp-cli-CnI7JKSG.js:98-99` |

> **踩坑留档(实现时必须避开)**:因为 `events_wait` 不回 `next_cursor`,我第一版采集器沿用了 `events_poll` 的 `next_cursor` 字段名去推进游标 → 游标恒为 0 → 同一条 event 1 被立刻重复返回(`waitForEvent` 先查 `queue.find(matchEventFilter)`,命中就同步返回、根本不阻塞),形成无 sleep 死循环,**40 秒写出 812MB 日志**。T-4 的事件循环必须以 `event.cursor` 推进,并对"取到事件"与"超时(`event: null`)"分别处理。

### 3.4 `tasks notify` 这一步是否需要、设了有没有变化

**结论:对 FR-3 回流播报**(经 MCP `events_wait`)**不需要,设了也没有任何可观测变化;而且在任务 running 期间设置根本不生效。**

- 事件流对比:C1(设 done_only)与 B1(不设)拿到的事件**逐字段同构**,都是 user + assistant 两条 `type: "message"`,没有多出任何事件。这是可解释的 —— 事件类型全集里就没有任务终态事件,notifyPolicy 管的是 IM 投递(`deliveryStatus`),不是 MCP 事件队列。
- CLI 派发的任务 `deliveryStatus` 实测**恒为 `not_applicable`**,即根本不走投递路径。

**notify 的写入竞态(两次独立复现,C1 与 D1):**

C1 —— 派发后 7.89s(任务 `status=running`)设置:

```
[1786181865.9] NOTIFY_OK after 7.889s :: Updated 952f53df-0101-4331-8aea-be266c38e79a notify policy to done_only.   (exit=0)
随后 tasks show → "status": "running",  "notifyPolicy": "silent"      ← 没生效
任务终态后 tasks show → "status": "succeeded", "notifyPolicy": "silent"  ← 始终没生效
```

D1 —— 派发后 5.09s 设置,再逐秒观察:

```
[t+5.09s]  NOTIFY_OK :: Updated ab850ecc-db46-4d7b-9542-f2a30023b588 notify policy to done_only.   (exit=0)
[t+7.43s]  probe#1 rc=0 status=running   notifyPolicy=silent deliveryStatus=not_applicable
[t+10.84s] probe#2 rc=0 status=running   notifyPolicy=silent deliveryStatus=not_applicable
[t+14.29s] probe#3 rc=0 status=running   notifyPolicy=silent deliveryStatus=not_applicable
[t+17.80s] probe#4 rc=0 status=succeeded notifyPolicy=silent deliveryStatus=not_applicable
POST-TERMINAL read: "status": "succeeded", "deliveryStatus": "not_applicable", "notifyPolicy": "silent"
```

**同一条命令在任务已终态后调用则会持久化**(在 B1、D1 上各验一次):

```
$ openclaw tasks notify agent:dev:voice-agent-94935dc26e46 done_only     # 任务已 succeeded
Updated 888b6b55-4a23-4df4-ad65-114a02f0136b notify policy to done_only.   EXIT=0
$ openclaw tasks show ... --json | grep notifyPolicy    →  "notifyPolicy": "done_only"     ← 生效
$ openclaw tasks notify agent:dev:voice-agent-94935dc26e46 state_changes
Updated 888b6b55-4a23-4df4-ad65-114a02f0136b notify policy to state_changes.   EXIT=0
$ openclaw tasks show ... --json | grep notifyPolicy    →  "notifyPolicy": "state_changes"  ← 生效
```

即:**判别因子是任务是否仍在 running** —— running 期间任务自身的记录写入会覆盖掉 notify 的写入,而 CLI 仍返回 exit=0 并打印 "Updated ...",**退出码不能作为"已生效"的判据**。

---

## 4. 与 `contract/cases.md` 记载不符的实测事实(需回写契约)

> 本节只陈述实测差异,不修改任何冻结文档。

### D-1 · §0.7 `CMD_TASKS_SHOW` 的"stdout 为 JSON"不成立 —— JSON 实际在 stderr(影响最大)

契约原文:`0=命中,stdout 为 JSON;1=未命中,stderr 首行 Task not found: ...`。

实测(同一轮内 A/B 对照,连测 3 轮,结果完全稳定):

```
round1  LIST rc=0 stdout=4006 stderr=0   |   SHOW rc=0 stdout=0 stderr=913
round2  LIST rc=0 stdout=4006 stderr=0   |   SHOW rc=0 stdout=0 stderr=913
round3  LIST rc=0 stdout=4006 stderr=0   |   SHOW rc=0 stdout=0 stderr=913
```

逐命令确认:

| 命令 | exit | JSON/文本落在 |
|---|---|---|
| `tasks show <lookup> --json` | 0 | **stderr**(stdout 0 字节) |
| `tasks show <lookup>`(无 --json) | 0 | stdout |
| `tasks list --json` | 0 | stdout |
| `tasks list --runtime cli --json` | 0 | stdout |
| `tasks show <bogus> --json` | 1 | stderr(`Task not found: ...`) |
| `tasks notify <lookup> <policy>` | 0 | stdout(`Updated ...`) |
| `tasks notify <bogus> done_only` | 1 | stderr(`Task not found: ...`) |
| `agents list --json` | 0 | stdout |
| `agent ... --json` | 0 | stdout(stderr 0 字节) |

stderr 里的内容是合法 JSON(`json.load` 直接解析通过,`taskId`/`status` 读出正常)。

后果与处置建议(留给拍板,不擅改):`tasks show --json` 的解析必须读 **stderr**;且因为命中与未命中**都写 stderr**,两者只能靠 **exit code(0 vs 1)** 区分,不能靠流区分。若 T-3/T-5 按契约字面读 stdout,状态查询会恒为空 —— 这是会静默失效的那类 bug。

补注:实装与源码副本 `diff` 一致,源码 `tasksShowCommand` 与 `tasksListCommand` 都走 `runtime.log(JSON.stringify(...))`、注册处也都传同一个 `defaultRuntime`,**从源码读不出这个差异**;此处以实测为准(项目纪律:不一致以实装行为为准)。

### D-2 · §0.8 条 4 第二项("能读出 OpenClaw 原生终态字符串")不成立

`events_wait` 的事件类型全集里没有任务终态事件;唯一与任务相关的信号是 `role=assistant` 的 `type: "message"` 事件,其 `raw.status` 是会话级 `"running"`,不是终态。终态必须回查 `tasks show`。§0.9 模板的 `{status}` 取值来源需要相应改写。

### D-3 · §0.8 未记载、但实现必须依赖的 `events_wait` 细节

- 返回 `structuredContent.event` **单数**;超时为 `{"event": null}`,`content[0].text == "timeout"`,命中时为 `"event <cursor>"`。
- **不返回 `next_cursor`**,游标必须由消费者从 `event.cursor` 推进(否则死循环,见 §3.3 踩坑)。
- 事件队列是 per-`openclaw mcp serve` 进程的内存队列,cursor 从 1 起、上限 1000 条;**连接前的事件不可见** → `OpenClawExecWorker` 的 bridge 必须在派发之前就连上并开始消费,否则会漏掉整个任务的事件。
- `session_key` 过滤是精确相等匹配,传我们生成的 `K` 即可精确订阅单个任务。

### D-4 · §0.7 `CMD_TASKS_NOTIFY` 的"0=已设置"判读在 running 期间不可信

见 §3.4:running 期间 exit=0 且打印 "Updated ...",但策略未落库且不会补上。若 FR-4 仍要保留"显式设策略",要么改到终态后再设(那时已无通知意义),要么放弃该步骤。C-12(通知策略被显式设置)按当前契约在 running 期间**必然失败**。

### D-5 · §0.5 `TaskView` 字段挑选与实机输出不完全对齐

实测 succeeded 的 cli 任务顶层键为:

```
taskId, runtime, sourceId, requesterSessionKey, ownerKey, scopeKind, childSessionKey,
agentId, requesterAgentId, runId, task, status, deliveryStatus, notifyPolicy,
createdAt, startedAt, endedAt, lastEventAt, cleanupAfter, terminalSummary
```

- §0.5 点名要透传但**本轮输出中不存在**的:`label`、`error`、`progressSummary`(实装 `tasks-QPW4uAt4.js:379-381` 显示这三项是"有值才输出",未设置即不出现在记录里)→ 解析必须容缺(`.get()`),不能按必填字段取。
- 实机存在但 §0.5 未列的:`sourceId`、`requesterSessionKey`、`scopeKind`、`agentId`、`requesterAgentId`、`runId`、`task`、`lastEventAt`、`cleanupAfter`(是否纳入 TaskView 由契约方决定,本轮不擅定)。

### D-6 · CLI 派发任务的 `deliveryStatus` 与 design.md P-07 的源码推论不一致

P-07 依 `ensureDeliveryStatus` 推出:`scopeKind !== "system"` 且 `ownerKey` 非空 → `"pending"`。实测四条 cli 任务**全部**是 `scopeKind: "session"`、`ownerKey` 非空,但 `deliveryStatus: "not_applicable"`、`notifyPolicy: "silent"`。即 cli runtime 走的不是 P-07 那条构造路径。(design.md 已冻结,此处仅记录实测事实。)

### D-7 · 契约未记载的两项时序开销(影响 C-07 与工具 timeout 取值)

- `tasks show` 每次调用固定 ~2.3–2.6s(node CLI 冷启动),四次实测:2.52 / 2.60 / 2.50 / 2.31(未命中)。若 `get_task_status` 逐个任务串行调 CLI,N 个在途任务就是 N×2.5s,`timeout_secs=20` 在 N≥8 时会被打穿。
- 派发后 ~2.6s 内 `tasks show <K>` 返回 exit=1 "Task not found",与 C-08 的真未命中输出完全一致、不可区分 → "派发即可查"需要一个宽限期约定(契约未定义)。

---

## 5. 复核入口

- 事件原样样本:`pipeline/task-dispatch/baseline/mcp-event-sample.json`(含 B1/C1 两组的 `events_poll` 基线 + 命中的 `events_wait` 响应 + 超时响应,payload 未裁剪)
- 本轮全部原始跑批产物(临时区,会话结束即弃):`/tmp/claude-1000/-home-ky-git-voice-agent/b85537c3-1926-498f-8f28-5cd06c660f6d/scratchpad/oc/run{1,2,3,4}/`,内含 `timeline.log` / `collector.log` / `show*.json` / `final-task.json` / `agent.stdout`
- 四个任务记录当前仍可查(`cleanupAfter` 约为创建后 7 天),可用上表的 session key 或 taskId 直接复核:
  `openclaw tasks show agent:dev:voice-agent-10b7dc7adace --json 2>&1`(注意 `2>&1`,见 D-1)

---

# 补测 · 失败路径实机验证(2026-08-08 第二轮)

- 执行:backend-dev(仍然只取样与判定,未写任何产品代码,未改 prd/design/contract)
- 背景:上面第 1–5 节那四次真派发**全部 succeeded**,失败路径没有样本。本轮专门造失败,只回答一个问题:**任务没能正常完成时,`events_wait` 那条通路上还会不会来消息。**
- 取样方式与第一轮一致:JSON-RPC over stdio 直连 `openclaw mcp serve`,**bridge 先连上再派发**,游标从 `event.cursor` 推进;本轮 bridge 不加 `session_key` 过滤(抓全量,离线按 sessionKey 归属),因此"没收到"是真没收到,不是被过滤掉。
- 原样事件 JSON:`pipeline/task-dispatch/baseline/failure-path-samples.json`(8 个 case 的 events / tasks show / agent CLI stdout / sqlite 状态变迁 / timeline 全在里面)
- 环境同上:`OpenClaw 2026.7.1-2 (0790d9f)`,Gateway `127.0.0.1:18789`,agent `dev`,model `deepseek/deepseek-v4-flash`
- 新增观测手段:直接只读快照 `~/.openclaw/state/openclaw.sqlite`(copy 出 db+wal+shm 再 `mode=ro` 打开)按 0.3s 轮询 `task_runs` 行 —— 因为 `openclaw tasks show` 单次固定 ~2.5s(见 D-7),粗到看不见状态翻转。

## 6. 八次派发一览(全部无副作用:纯文本生成或 `sleep`,未写任何文件、未联网)

| 代号 | 失败形态 | 怎么造的 | `tasks show` 最终 status | `events_wait` 事件数 | 末条 assistant 的 text |
|---|---|---|---|---|---|
| F1 | 任务做不成,agent 如实汇报 | 让它读一个不存在的文件 | **succeeded** | 3 | `"读取失败。**原因**:文件 ... 不存在(ENOENT ...)"` —— 够用 |
| F2 | 运行超时/被中止 | `--timeout 15` + 需要 120s 的 shell 命令 | **cancelled** | 4 | `''`(空字符串)—— 不够用 |
| F7b | 同上,复现 | `--timeout 25` + 需要 150s 的 shell 命令 | **cancelled** | 4 | `''`(空字符串)—— 不够用 |
| F3 | 派发被前置校验拒绝 | `--model` 给一个不在 agent 白名单里的模型 | **failed** | **0** | 无(连 user 事件都没有) |
| F6 | 运行中失败 | 1,020,109 字节的消息触发 `context_overflow` precheck | **failed** | **0** | 无(连 user 事件都没有) |
| F4 | 显式取消 | running 期间 `openclaw tasks cancel <K>` | succeeded(取消被回滚) | 6 | 采样窗口太短,末条漏采 → 见 F4b |
| F4b | 显式取消,复现+高分辨率 | 同上,叠加 0.3s sqlite 轮询 | succeeded(取消被回滚) | 5 | `'F4B-DONE'` —— 看起来完全成功 |
| F7 | 静默成功(偶发) | 与 F7b 同一条 prompt,模型回了 `NO_REPLY` | **succeeded** | 1(只有 user) | 无 assistant 事件 |

session key 仍按 `contract/cases.md` §0.6 规则自行生成,8 个 key 逐条记在 `failure-path-samples.json` 的 `cases.<id>.session_key`。

## 7. 直接结论(先行,再展开)

**答案:失败时不一定有消息;有消息时内容也不一定够。三种情况都存在,不能只靠一个信号。**

1. **两种 `failed` 形态(F3、F6)在 `events_wait` 上一条事件都没有** —— 连 `role=user` 那条都没有。以 "assistant message 事件" 为唯一触发信号的回流播报,对这两种形态**永远不会触发**,任务会静默消失,用户等到天荒地老。
2. **超时/中止(F2、F7b,独立复现两次)有事件,但末条 assistant 消息的 `text` 是空字符串 `''`。** 照"把 agent 说的那句话转述给用户"直接执行,会播报一段空内容;agent **不会**自己说"我没做成"。真正能判失败的信号在 `event.raw.message.stopReason == "aborted"`,**不在 `text` 里**。
3. **assistant message ≠ 任务完成。** 长任务运行中 agent 会持续产生 assistant 消息:工具调用消息(顶层**连 `text` 键都没有**)、过程播报(`"The command is still running. Let me poll until it completes."`)。F4 一次任务就来了 5 条 assistant 事件,只有最后一条是结论。"收到就转述"会把过程话当结论播出去,而且一条任务播好几次。
4. **任务 status 和"事情有没有办成"是两回事,而且经常反着来:**
   - F1 事情**没办成**(文件读不到),任务 status = `succeeded`;
   - F7 事情**没办成**(活根本没干),任务 status = `succeeded` + `terminalSummary: "completed"`;
   - F4b 事情**办成了**(输出 `F4B-DONE`),中途 status 一度是 `cancelled`。
   靠 `tasks show` 的 status 判断"办没办成",会判反。
5. **唯一"失败且播报内容够用"的形态是 F1** —— agent 跑完流程、自己把失败原因说清楚了。共同点是:**run 正常结束、模型有机会开口**。凡是模型没机会开口的失败(前置拒绝、precheck 失败、被中止),消息通路要么空、要么没有。

## 8. 各形态实测明细

### 8.1 F1 · 任务做不成,agent 如实汇报 → status `succeeded`,消息够用

派发:`openclaw agent --agent dev --session-key $K --message-file message.txt --json`,任务内容是读 `/home/ky/openclaw-workspace/absolutely-missing-file-20260808.txt`(不存在)。

```
probe#2 rc=0 status=running   ...
probe#3 rc=0 status=succeeded ... terminalSummary='completed' error=''
EVENT cursor=1 type=message role=user      text='请读取文件 ...'
EVENT cursor=2 type=message role=assistant text=None      <- 工具调用消息,顶层没有 text 键
EVENT cursor=3 type=message role=assistant text='读取失败。\n\n**原因**:文件 `...` 不存在(`ENOENT: no such file or directory`)。...'
```

cursor=2 的事件对象顶层键是 `['cursor','messageId','messageSeq','raw','role','sessionKey','type']` —— **比第一轮记录的形态少了 `text`**;`raw.message.content` 是 `[{"type":"toolCall","name":"read",...}]`。

结论:这一类失败,任务终态是 `succeeded`,但 assistant 文本本身把失败说清楚了,**播报内容够用**。反过来说,判定"办没办成"只能靠这段自然语言,没有任何结构化字段可读。

### 8.2 F2 / F7b · 超时被中止 → status `cancelled`(不是 `timed_out`),末条消息是空串

F7b 派发:`openclaw agent ... --json --timeout 25`,任务是等一条 150s 的 shell 命令。

```
probe#8 rc=0 status=running
probe#9 rc=0 status=cancelled ... error='agent run aborted'      <- t+25s 后
EVENT cursor=1 role=user      text='请用 shell 执行命令:sleep 150 ...'
EVENT cursor=2 role=assistant text="I'll run the sleep command and wait for it to complete."
EVENT cursor=3 role=assistant text='The command is still running. Let me poll until it completes.'
EVENT cursor=4 role=assistant text=''                            <- 中止瞬间这条
```

cursor=4 这条事件的内部字段(原样):

```
raw.message.stopReason = "aborted"
raw.message.content    = [{"type":"text","text":""}]
raw.status             = "running"     <- 会话级,不是任务终态
raw.abortedLastRun     = false
```

同一次派发的 `openclaw agent --json` stdout 顶层:

```json
{"runId":"382ef5dd-86ff-4e40-a235-bee63fc4b810","status":"timeout","summary":"aborted","stopReason":"aborted"}
result.payloads = [{"text":"LLM request timed out."},{"text":"⚠️ 🧰 Process: `brisk-atlas` failed"}]
result.meta.aborted = true, durationMs = 25211
```

注意三方口径全不一样:**CLI 说 `timeout`/`aborted`,任务记录说 `cancelled`,事件里只有 `stopReason: "aborted"`,而播报要用的 `text` 是空串。** "LLM request timed out." 这句人能看懂的话只在 CLI stdout 的 payloads 里,**不在事件通路上**。

F2(`--timeout 15`)是同一形态的独立一次,结论逐条一致,详见样本文件。

### 8.3 F3 · 派发被前置校验拒绝 → status `failed`,事件通路全空

```
$ openclaw agent --agent dev --session-key $K --message-file msg --json \
    --model deepseek/definitely-not-a-real-model-20260808
exit=1  stdout=0 字节
stderr: GatewayClientRequestError: Error: Model override "deepseek/definitely-not-a-real-model-20260808" is not allowed for agent "dev".
```

任务记录**照样建了**(所以 lookup 查得到),终态原样:

```json
{"status": "failed",
 "error": "Error: Model override \"deepseek/definitely-not-a-real-model-20260808\" is not allowed for agent \"dev\".",
 "terminalSummary": "Error: Model override \"...\" is not allowed for agent \"dev\".",
 "createdAt": 1786185106932, "startedAt": 1786185106932, "endedAt": 1786185107051}
```

`createdAt` 到 `endedAt` 只有 **119ms**。bridge 全程在线,采集到的只有两条 `events_wait` 超时响应(`{"event": null}`),**事件数 0**。

好消息是 `error` / `terminalSummary` 两个字段把原因写全了 —— 但只能靠 `tasks show` 回查拿到,事件通路上取不到。

### 8.4 F6 · 运行中失败(context overflow)→ status `failed`,事件通路同样全空

派发一条 1,020,109 字节的消息。状态在 sqlite 里的变迁(0.4s 分辨率):

```
1786185792.847  status=None                       <- 记录还没建
1786185795.347  status=running
1786185797.411  status=failed   error='Agent run failed'
```

任务记录:`"status": "failed", "error": "Agent run failed"`,**没有 `terminalSummary` 字段**(与 F3 不同,解析必须容缺)。

而 `openclaw agent --json` 的 stdout 顶层是:

```json
{"runId":"f0552d51-...","status":"ok","summary":"completed"}
result.payloads = [{"text":"Context overflow: prompt too large for the model. Try /reset (or /new) to start a fresh session, or use a larger-context model."}]
result.meta.error = {"kind":"context_overflow","message":"Context overflow: prompt too large for the model (precheck)."}
```

**CLI 说 `ok`/`completed`,任务记录说 `failed`。** 唯一人能看懂的原因("Context overflow ...")又只在 CLI payloads 里。事件数 **0**,连 user 消息事件都没有 —— 因为 precheck 在用户消息落库之前就把 run 打掉了。

### 8.5 F4 / F4b · `openclaw tasks cancel` 对 cli 任务是个空操作,而且状态会回滚

F4b:派发一条等 45s 的任务,t+15s 执行 `openclaw tasks cancel $K`。

```
HOOK_START  openclaw tasks cancel "$K"
HOOK_EXIT   rc=0  out=Cancelled 58613462-7593-4252-98d7-571a3bd314f8 (cli) run 395c36cb-....
```

sqlite 0.3s 轮询(t 相对派发时刻):

```
t+ 16.90s status=running
t+ 17.52s status=cancelled  error='Cancelled by operator.'  ended_at=1786185536303
t+ 46.95s status=running    error=''                        ended_at=None      <- 被 Gateway 改回来了
t+ 52.07s status=succeeded  terminal_summary='completed'    ended_at=1786185570911
```

同一次的 `openclaw agent --json` stdout:`status: ok`,`summary: completed`,`payloads=[{"text":"F4B-DONE"}]`,`meta.aborted=false`,`durationMs=49259` —— **run 根本没被打断,活照干完了**。事件通路上最后一条是 `text='F4B-DONE'`,和成功任务完全无法区分。

也就是说:`tasks cancel` 退出码 0、打印 "Cancelled ...",但对 `runtime: cli` 的任务(1)**不会中止实际的 run**,(2)写进去的 `cancelled` 会在 Gateway 下一次写这条记录时被**覆盖回 running**,最终变成 `succeeded`。窗口期实测约 **29 秒**(t+17.5 → t+47),这期间 `tasks show` 会如实返回 `cancelled` —— 一个会骗人的中间态。

第一次做的 F4 采样窗口设短了,末条事件漏采;F4b 是这一形态的权威样本,两次的取消行为一致。

### 8.6 F7 · 静默成功:活没干、status `succeeded`、一条 assistant 事件都没有

和 F7b 是**同一条 prompt、同一组参数**,只是模型这一次直接回了静默哨兵:

```
result.meta.finalAssistantRawText     = 'NO_REPLY'
result.meta.finalAssistantVisibleText = 'NO_REPLY'
result.payloads = []              <- 空
result.meta.durationMs = 1729     <- 1.7 秒,那条 sleep 150 根本没跑
result.meta.executionTrace = {"attempts":[{"provider":"deepseek","model":"deepseek-v4-flash","result":"success","stage":"assistant"}]}
```

任务记录:`"status": "succeeded", "terminalSummary": "completed"`。
事件通路:**只有 cursor=1 那条 user 消息,零条 assistant 事件**,bridge 又多守了 90 秒,再没来任何东西。

机制在实装 `agent-runner.runtime-DtdxZiBX.js:2022-2023`:回复文本命中 `NO_REPLY` 时 `return { skip: true }`,消息不投递、也就不产生 `session.message`,MCP 事件队列自然什么都收不到。

这一条只出现 1 次(n=1,同 prompt 的 F7b 就正常跑了),但它是最危险的形态:**任务记录说办好了、播报通路一声不吭、活其实没干。**

## 9. `lost` 形态:本轮未复现,给出机制与不复现的理由

- `lost` 只由维护扫描写入(实装 `task-registry-Cws4vLl0.js:1761 markTaskLostById`,唯一调用点 `task-registry.maintenance-CeBupGdg.js:424 markTaskLost`),条件是 `shouldMarkLost` = 任务仍活跃 **且** 距 `lastEventAt` 超过 `TASK_RECONCILE_GRACE_MS = 5 分钟` **且** 没有 backing session。
- 对 `runtime: cli`,`hasBackingSession` 先看 `hasActiveCliRun(task)`(查**执行扫描的那个进程**内存里的 agent run 上下文)。Gateway 进程里 run 还活着 → 判定 retained;而 `openclaw tasks maintenance` 跑在 CLI 进程里,那里永远查不到 → 判定 backing_session_missing。
- 实测:running 期间从 CLI 侧 `openclaw tasks audit --json`,`byCode.lost = 0`、`stale_running = 0`(两条 warning 全是历史遗留的 task_flow,与本轮无关)。原因是健康的长任务每 ≤30s 就刷新一次 `lastEventAt`(F4b sqlite 实测:t+16.7 → t+46.8 → t+48.6 → t+50.3),**5 分钟宽限期永远走不完**。
- 因此 `lost` 只在"记录还是 running、但那个 run 已经没了"的孤儿场景出现(Gateway 崩溃/重启留下的残留记录)。造这个样本需要**杀掉用户正在跑的 Gateway**,不在授权范围,已放弃;另一条路 `openclaw tasks maintenance --apply` 也已放弃 —— 先跑了只读预览,它会顺带 `taskFlows.pruned: 88`,那是用户的历史数据:

```
$ openclaw tasks maintenance --json      # 只读预览,没有 --apply
{"mode":"preview","maintenance":{"tasks":{"reconciled":0,"recovered":0,"cleanupStamped":0,"pruned":0},
                                 "taskFlows":{"reconciled":0,"pruned":88}, ...}}
```

- 对本轮要回答的问题,`lost` 的答案可以从结构上确定:`markTaskLostById` 只改任务注册表,不产生 `session.message`;而 MCP 事件队列的 6 个入队点(第一轮 §3.2 已逐一核对)里只有 `session.message` 会变成 `type: "message"` 事件。**所以 `lost` 一定不会在 `events_wait` 上产生任何消息。**

## 10. 本轮新增的、与 `contract/cases.md` / `design.md` 不符或未记载的事实

> 同样只陈述实测差异,不修改任何冻结文档。编号接第 4 节的 D-1..D-7。

### D-8 · 超时不落 `timed_out`,落 `cancelled`

`--timeout N` 是传给 Gateway 的(`agent-via-gateway-_KoeINns.js:427 timeout: timeoutSeconds`),中止发生在服务端。但中止的 `stopReason` 是 `"aborted"`,经 `buildAgentRunTerminalOutcome`(`agent-run-terminal-outcome-Dv8Iorx2.js:91-96`,`aborted` 分支优先于 `input.status === "timeout"`)得到 `reason: "aborted"`,再经 `mapAgentRunTerminalOutcomeToTaskStatus`(`task-registry-Cws4vLl0.js:1108-1109`)映射为 **`cancelled`**。

后果:**`timed_out` 在 CLI 派活这条路上本轮一次都没出现过**;把"超时"和"被取消"当成两种状态去分支处理是错的,两者在记录里长得一模一样(都是 `status: cancelled`),只能靠 `error` 文案区分:超时 = `"agent run aborted"`,显式取消 = `"Cancelled by operator."`。

### D-9 · `tasks cancel` 对 `runtime: cli` 任务不生效,且退出码同样不可信

见 §8.5。CLI 侧 `cancelDetachedTaskRunById` 在没有注册 detached runtime 时退化成 `cancelTaskById`(`task-executor-CQNBvXzo.js:388-396`),只改记录不碰 run;而 Gateway 内存里那份记录随后会把 `cancelled` 覆盖掉。这与 D-4(`tasks notify` 在 running 期间被覆盖)是**同一类竞态**:CLI 侧写、Gateway 侧覆盖。

若 PRD 里有"取消已派出去的任务"这类能力,按当前实装**做不到**,需要另找路径(或走 Gateway 的 `tasks.cancel` RPC —— 但 `tryCancelGatewayOwnedTaskViaGateway` 在 `tasks-QPW4uAt4.js:153` 明确只对 `cron`/`acp` 生效,`cli` 直接 return null)。

### D-10 · `role=assistant` 的事件有三种形态,消费端必须先分辨再播报

| 形态 | 顶层 `text` | `raw.message.content` | `raw.message.stopReason` | 什么时候来 |
|---|---|---|---|---|
| 工具调用 | **键不存在** | `[{"type":"toolCall",...}]` | `toolUse` | 每次调工具 |
| 过程播报 | 有,是自然语言 | `[{"type":"text",...}]` | `toolUse` | 边干边说 |
| 中止 | 有,是 `''` | `[{"type":"text","text":""}]` | **`aborted`** | 被中止瞬间 |
| 真结论 | 有,是自然语言 | `[{"type":"text",...}]` | `stop` / 无 | 收尾 |

`design.md` 现在的"收到 assistant message 就把 agent 说的那句话转述给用户"落到实装上会:对工具调用消息取到 `None`、对中止消息取到 `''`、对过程播报把中间话当结论播。**至少要按 `raw.message.stopReason` 与 `text` 非空来筛**;`stopReason == "aborted"` 是目前唯一能在事件内部读出的失败信号。

补充:第一轮 §3.1 记录的"事件对象顶层键固定 8 个(含 `text`)"**不成立** —— 工具调用事件没有 `text` 键,解析必须 `.get()` 容缺。

### D-11 · `openclaw agent --json` 的退出码与 stdout 终态,和任务记录终态互相矛盾

| case | CLI exit | CLI stdout `status`/`summary` | 任务记录 `status` |
|---|---|---|---|
| F2 / F7b | 0 | `timeout` / `aborted` | `cancelled` |
| F3 | 1 | (stdout 空,报错在 stderr) | `failed` |
| F6 | 0 | **`ok` / `completed`** | **`failed`** |
| F4b | 0 | `ok` / `completed` | `succeeded`(中途一度 `cancelled`) |
| F7 | 0 | `ok` / `completed` | `succeeded`(活没干) |

F6 那行是最要命的:**CLI 报告成功、任务记录是 failed**。任何"用 detached spawn 的退出码判断派活成没成"的做法都不成立。真正的原因文本(`Context overflow ...` / `LLM request timed out.`)只在 stdout 的 `result.payloads[]` 里,而 detached 派发根本不会去读它。

### D-12 · 失败形态与"消息通路有没有信号"的对应关系(直接决定 FR-3 的兜底设计)

| 失败形态 | 任务终态 | 事件通路 | 能否只靠 assistant 消息发现 |
|---|---|---|---|
| agent 跑完、如实报告做不成 | `succeeded` | 有,文本够用 | **能** |
| 超时/被中止 | `cancelled` | 有,但 `text=''` | **不能**(要读 `stopReason`) |
| 前置校验拒绝 | `failed` | **无** | **不能** |
| 运行中 precheck 失败 | `failed` | **无** | **不能** |
| `NO_REPLY` 静默成功 | `succeeded` | 只有 user 事件 | **不能** |
| 维护扫描判定 `lost` | `lost` | **无**(源码可确定) | **不能** |

即:**"assistant message 事件"作为唯一触发信号,覆盖不了 6 种形态里的 5 种。** 六条 FR 里凡是承诺"未确认完成绝不报办好了"的,都需要一个不依赖消息事件的兜底(超时兜底 + 回查 `tasks show`),否则失败任务会永远停在"在办"状态、既不播报也不收口。这条留给契约方拍板,本轮不擅定。

## 11. 复核入口(第二轮)

- 原样样本:`pipeline/task-dispatch/baseline/failure-path-samples.json`
  - `cases.<id>.events_raw[].event` = `events_wait` 返回的 `structuredContent.event` 原样对象,未裁剪
  - `cases.<id>.final_tasks_show` = `openclaw tasks show <K> --json` 的 **stderr**(见 D-1)
  - `cases.<id>.store_transitions` = sqlite `task_runs` 行的状态变迁(0.3–0.4s 分辨率)
  - `cases.<id>.timeline` = 该 case 的完整跑批时间线
- 本轮全部原始跑批产物(临时区,会话结束即弃):`/tmp/claude-1000/-home-ky-git-voice-agent/b85537c3-1926-498f-8f28-5cd06c660f6d/scratchpad/fail/{F1,F2,F3,F4,F4b,F6,F7,F7b}/`,含 `collector.log` / `events.jsonl` / `store.jsonl` / `agent.stdout` / `show.*.err` / `final.err`
- 8 条任务记录当前仍可查(`cleanupAfter` 约为创建后 7 天),用样本文件里的 session key 直接复核:
  `openclaw tasks show <session_key> --json 2>&1`(注意 `2>&1`,见 D-1)
