# 架构收敛 · task-dispatch(C4 派活)

> 2026-08-08 用户对话中逐条裁决收敛而成,**用户已确认"完美符合需求"**。
> 本文是 S1b 起草 PRD 的直接依据;与早前四份纪要冲突处**以本文为准**(冲突点已在文末逐条标注)。

## 一、最终形态

```
┌─ voice-agent(Python / pipecat,一直开着)────────────────────┐
│                                                              │
│  主 PipelineWorker ── 双脑 ParallelPipeline(骨架原样不动)   │
│      快脑分支:唯一对外输出通道,负责说给用户听               │
│                                                              │
│  派活 worker(BaseWorker,独立挂同一个 WorkerRunner)         │
│      ├─ 派活:subprocess 调 `openclaw agent`                 │
│      └─ 审批:持有一个 `openclaw mcp serve` stdio 子进程      │
│           ├─ 入向 events_wait(长轮询,事件到即返回)         │
│           └─ 出向 permissions_respond(送回批准结果)         │
└──────────────────────────────────────────────────────────────┘
                          ↕ 跨进程
┌─ OpenClaw Gateway(Node,systemd 常驻,已在本机运行)────────┐
│  agent 会话 / 后台任务系统 / 审批体系 / 多渠道               │
└──────────────────────────────────────────────────────────────┘
```

**关键性质**:派活的真实执行体在**另一个进程**(OpenClaw Gateway),voice-agent 只是发起方与播报方。

## 二、能力归属(用户口径:官方有什么用什么,自研压到最小)

| 能力 | 落在哪 | 自研量 |
|---|---|---|
| 派发任务 | `openclaw agent` CLI,一次性阻塞调用(`--timeout` 默认 600s,`0` 关闭) | 零 |
| 任务状态机 | OpenClaw tasks 系统:`queued→running→succeeded/failed/timed_out/cancelled/lost` | 零 |
| 完成通知 | tasks 系统 push-based(直接投递 / 会话排队 + **立即唤醒**)。文档原文:"the usual workflow is **push-based** … Poll task state only when you need debugging, intervention, or an explicit audit" | 零 |
| 通知策略 | `done_only`(默认)/ `state_changes` / `silent`,可运行时改:`openclaw tasks notify <lookup> <policy>` | 零 |
| **审批入向** | MCP `events_wait` 长轮询(默认 30s、上限 300s,**事件到即返回**),事件类型含 `exec_approval_requested` / `plugin_approval_requested` | 零 |
| **审批出向** | MCP `permissions_respond`(`allow-once` / `allow-always` / `deny`) | 零 |
| 待批清单 | MCP `permissions_list_open` | 零 |
| 手动接管 | OpenClaw 会话本身是一等公民,直接在它自己的渠道里对话即可 | 零 |
| 持久化 | **降级不做**——用户 2026-08-08 裁决:对接既有记忆系统 | 零 |
| 桥接层 | **官方 × 官方**:`openclaw mcp serve`(OpenClaw 自带 CLI)↔ pipecat `MCPClient`(`services/mcp_service.py`,支持 stdio/SSE/streamable-http) | 零 |
| **完成确认铁律** | 无官方件 | **自研(唯一)** |

→ **自研面收缩到一条:"未确认完成绝不报办好了"的文本契约层。**

## 三、用户裁决清单(2026-08-08,均为对话中显式拍板)

1. **口径**:派活最大化复用原生能力,官方有什么用什么;参考成熟方案;**骨架不改**;自研压到最小。
2. **形态同构**:派活天然异步;语音只是两端 STT/TTS 转换,**内部流转即文本**,与 IM 渠道同构;"同意/不同意识别不准"属过虑,不作设计假设。
3. **唯一真实设计点**:派活不影响主会话,**任务通知回流时前台要知道怎么说**。
4. **审批实时性**:不需要实时,**通话期间几分钟内通知到即可**。
5. **持久化**:不重要,对接既有记忆系统。
6. **确认**:上述形态"完美符合需求"。

## 四、两个早前疑点:因架构变化而消解

| 早前疑点 | 现状 |
|---|---|
| **接管面与回执面的张力**(可接管要求内部可观测 vs 底稿要求只暴露交付回执) | **消解**。执行体是 OpenClaw 的会话,接管发生在 OpenClaw 自己的渠道里;voice-agent 语音面只收交付回执。两个面天然分属两个系统,不必在同一契约里调和。 |
| **`worker.cancel()` 是否只杀单个 worker**(决定断连后任务能否续跑) | **消解**。任务跑在 OpenClaw Gateway **另一个进程**,pipecat 的 `worker.cancel()` 够不着它。断连即杀 pipeline 不再与"任务不随对话中断"冲突(硬约束 C4 自然满足)。 |

## 五、必须带进 S2a 的实现约束(均源码/文档实锤)

1. **`silent` 是 CLI 任务的默认通知策略** —— 用 `openclaw agent` 派活后必须显式 `openclaw tasks notify <lookup> done_only`,否则完成不通知。
2. **`events_wait` 绝不能写进 LLM 的 function call** —— 会卡住那一轮对话最长 300 秒。必须待在后台 worker 的独立 asyncio task 里,拿到事件后经**素材注入**递给快脑说出(复用慢脑回流的现成机制,不另开输出通道,守住硬约束 C3)。
3. **审批超时两套,别用错**:plugin 审批默认 pending **120 秒**(上限可配 600s);exec 审批 **30 分钟**;`askFallback` 省略时**默认 deny**。按"几分钟级"响应要求,应走 exec 路径或把 plugin 超时调至上限。
4. **`openclaw approvals` CLI 不能裁决待处理审批** —— 它只有 `get`/`set`(策略配置)与 `allowlist add|remove`。裁决只能走 MCP `permissions_respond` 或 Gateway RPC。~~**这是"必须常连 MCP bridge"的根因。**~~
   > **【2026-08-08 s1b 订正】** 划掉的这句在本期已不成立:用户裁决审批链本期不做(降级为 OpenClaw 侧权限配置,见 `prd.md` 前提假设节),`permissions_respond` 本期不使用。
   > **MCP bridge 仍然必需,但根因改为"接收任务终态事件"**(`events_wait` 长轮询,`prd.md` FR-3/FR-4 依赖)。
   > 本条其余事实(approvals CLI 的能力边界)不变;审批链后加时,该 CLI 仍不能用于裁决。
5. **MCP bridge 的事件队列是 live-only 内存队列** —— bridge 连上才开始,断开即失;历史要用 `messages_read` 读。对本项目影响有限(pipecat 本就常驻),但重启后的空窗要认。
6. **prompts.py 的能力边界段必须改写**(硬约束 C1):现声明"无任何执行类能力",与派活直接冲突;`evals/r4_no_false_completion.yaml` 需同步改。**"未确认完成绝不报办好了"这半条要保留并强化**。
7. **D-003 债务重叠**:落地要往 `bot.py` 加 `add_workers()` 与新 worker 类,与顶层副作用债务同模块,S2a 需判断是否先偿还。

## 六、与早前纪要的冲突标注(以本文为准)

- `pipecat-capability-survey.md` 曾把 `code-assistant`(Claude Agent SDK 内嵌)作为执行载体答案 → **已不采用**。改由 OpenClaw Gateway 承载执行,该示例的取消缺陷与 SDK 内存泄漏 issue 随之**不再是本项目风险**(它们属于"自己内嵌 SDK"路线的坑)。
- `external-research.md` Q5 关于本地持久化的结论 → **降级不做**(用户裁决对接记忆系统)。
- `external-research.md` Q1 关于执行载体的全部坑位分析 → 仅在"未来改回自己内嵌 SDK"时才重新适用。
- `openclaw-reference.md` §4 手动接管的定性(选型即得)→ **成立且已实现**,本架构下天然满足。
