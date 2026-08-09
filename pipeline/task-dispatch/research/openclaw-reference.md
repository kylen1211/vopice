# OpenClaw 参考 · 授权确认链与手动接管(task-dispatch 自研区的成熟方案底稿)

> 用户 2026-08-08 点名提供的参考方案。**一手材料**:本机全局 npm 包
> `~/.nvm/versions/node/v24.18.0/lib/node_modules/openclaw/`,版本 `2026.7.1-2`,**许可 MIT**
> (`LICENSE` 实读),自带完整 `docs/` 文档树与 `dist/` 产物。
> 定位(package.json 原文):"Multi-channel AI gateway with extensible messaging integrations"。
>
> **成熟度分级(必读,不可混用)**:
> - 【已实现】= `docs/tools/`、`docs/cli/`、`docs/plugins/` 下的用户文档,描述在跑的能力;
> - 【规格态】= `docs/specs/` 下的设计文档,含 Implementation Plan / Open Questions 章节,**不等于已落地**。

---

## 一、授权确认链【已实现】(`docs/tools/exec-approvals.md`, 517 行)

### 1.1 五档权限模式(`tools.exec.mode`)

| 值 | 行为 |
|---|---|
| `deny` | 全禁 |
| `allowlist` | 只跑白名单,不问 |
| `ask` | 白名单策略 + 未命中就问 |
| `auto` | 白名单命中直接跑;**未命中先过自动审查器**,再落人工审批路径 |
| `full` | 不问 |

→ 对本项目:派活的动作分级可直接照搬这五档,`auto` 档的"先机器审、审不过才惊动人"尤其值得抄。

### 1.2 策略取严合并(核心安全设计)

原文:"Effective policy is the **stricter** of `tools.exec.*` and approvals defaults:
approvals can only **tighten** config-derived security/ask, **never loosen** them."

两层策略源:请求侧配置 + 执行主机本地审批文件;**取更严者生效**。
主机侧 `ask: "always"` 能压过会话/配置侧的 `ask: "on-miss"`。

→ 对本项目:授权策略必须是"多源取严",不能让会话级设置放松全局约束。

### 1.3 `ask` 三态与超时兜底

- `ask`:`off`(从不问)/ `on-miss`(未命中才问)/ `always`(每次都问)。
  关键细节:`always` 时,`allow-always` 的持久信任**不抑制提示**。
- `askFallback`(需要提示但无 UI 可达、或提示超时时的裁决):`deny` / `allowlist` / `full`,**省略时默认 `deny`**。
- 超时语义【已实现,advanced.md:165-169】:无决定到达 → 视为 approval timeout → **终局拒绝**;
  **pending 审批默认 30 分钟过期**。

→ 对本项目:直接回答了"用户不答怎么办"——默认拒绝、有明确过期时限,不是无限挂起。

### 1.4 批准的有效范围与隔离

- 三档决定:`allow-once` / `allow-always` / `deny`。
- `allow-always` 持久化进 allowlist,条目字段:`pattern` / `argPattern`(argv 正则)/ `id` /
  `source` / `commandText` / `lastUsedAt` / `lastUsedCommand` / `lastResolvedPath`。
- **白名单按 agent 隔离**,原文:"Per-agent allowlists prevent one agent's approvals from leaking into others."

### 1.5 防"批准后漂移"(最值得抄的一条)

审批记录绑定**冻结的执行计划**,而非模糊意图:

- 绑定 canonical execution context:cwd、精确 argv、env binding、pinned executable path。
- 对脚本/解释器调用还绑定一个具体本地文件;**该文件在批准后、执行前发生变化 → 拒绝执行**
  (原文:"the run is denied instead of executing drifted content")。
- 若无法唯一确定文件,**宁可拒绝发放审批**,也不假装覆盖
  (原文:"refuses to mint an approval-backed run rather than pretend full coverage")。
- 转发时复用存储的 plan;调用方在审批后改动 `command`/`rawCommand`/`cwd`/`agentId`/`sessionKey`
  → 按 **approval mismatch 拒绝**。

→ 对本项目:**用户批准的必须是一个被冻结的具体任务计划,不是一句"你去办吧"**;
派发凭据与批准记录必须绑定,事后被改就作废。这条同时服务于"完成确认铁律"。

### 1.6 审批事件协议【已实现】

- gateway 广播 `exec.approval.requested` 给 operator clients;
- 客户端以 `exec.approval.resolve` 裁决;
- gateway 再把已批准请求转发到执行主机;
- **审批 id 用于关联** pending 请求与其完成/拒绝消息(`Exec finished (gateway id=...)` / `Exec denied (...)`)。

---

## 二、通知回流:异步审批/完成如何回到对话【已实现】(advanced.md:165-181)

**这一节直接对应用户 2026-08-08 点出的唯一真实设计点——"接到通知时得知道怎么说"。**

- 已批准的异步 exec 完成后 → 向**同一会话**发一个 followup **`agent` turn**。
- 被拒绝的异步审批 → **走同一条主会话 followup 路径**回报拒绝状态,但不注册 elevated handoff、不跑命令。
- 超时/拒绝且有原始会话 → **resume 该会话并注入 internal followup**,
  目的原文:"so the agent observes that the command did not run **instead of later repairing a missing result**"
  → 即:主动告知失败,避免 agent 事后"补救一个不存在的结果"(这正是谎报完成的温床)。
- **投递目标解析四规则**:
  1. 有可投递外部渠道 + 目标 `to` → 走该渠道;
  2. 纯 webchat / 内部会话无外部目标 → **session-only(`deliver: false`)**;
  3. 调用方显式要求严格外部投递但无可解析渠道 → 失败 `INVALID_REQUEST`;
  4. 开启 `bestEffortDeliver` 且无外部渠道 → **降级 session-only,而不是失败**。
- 进行中通知【exec-approvals.md:466-469】:批准后经过 `tools.exec.approvalRunningNoticeMs`
  (默认 `10000` ms,`0` 关闭)才发"正在跑"提示。
- **子会话隔离**:subagent 与 cron 会话的拒绝**不回灌**到那些会话。

→ 对本项目:回流播报的目标解析与降级策略可整套照搬;
"进行中通知有延迟阈值"正好实现底稿里"进度只观测不播报"的克制;
"主 agent 会话回灌、子会话不回灌"回答了通知该进哪条上下文。

---

## 三、多渠道审批转发【已实现】(advanced.md:183-269)

配置形状(exec 与 plugin 两套独立同构):

```json5
approvals: {
  exec: {
    enabled: true,
    mode: "session",          // "session" | "targets" | "both"
    agentFilter: ["main"],
    sessionFilter: ["discord"],
    targets: [{ channel: "telegram", to: "123456789" }],
  },
  plugin: { /* 同构,独立开关 */ },
}
```

- 聊天内裁决:`/approve <id> allow-once|allow-always|deny`。
- `/approve` 同时服务 exec 与 plugin 审批;ID 不匹配时自动回退查 plugin,
  但**该回退仅限于"审批未找到"**,真实的拒绝/错误不会被静默重试成另一类审批。
- **支持交互按钮的渠道渲染按钮;不支持的回退为纯文本 + `/approve` 指令**。
- plugin 审批可**限定可用决定集**,Gateway 拒绝提交未被提供的决定。
- **same-chat approvals**:审批请求从哪个可投递聊天面发起,那个聊天就能直接 `/approve`,
  沿用该会话正常的渠道鉴权模型——**无需为"让审批挂住"而专门做一个原生投递适配器**。
- native approval clients(Discord/Slack/Telegram/Matrix/QQ)额外提供 approver DM、origin-chat fanout。
- 明确的 agent 行为约束:有原生审批 UI 时,**agent 不应再重复回显 `/approve` 文本命令**,
  除非工具结果表明聊天审批不可用。

→ 对本项目:语音渠道天然没有交互按钮,**正好落在官方已支持的"纯文本 fallback"路径上**,
不是需要额外发明的东西;`mode`/`agentFilter`/`sessionFilter`/`targets` 这套配置形状可直接借鉴。
Matrix 的 emoji 快捷(✅ once / ♾️ always / ❌ deny)说明"决定集可按渠道给不同 affordance",
语音侧对应的就是三个口头意图。

---

## 四、手动接管

> **本节结论已于 2026-08-08 用户指正后重写。** 早前版本把手动接管整体归为"自研区/规格态",
> 那是**找错了机制**——去看 fleet 监督规格(`claw-supervisor.md`),而真正的答案在会话模型里。

### 4.1 真正的机制:子任务即独立会话 + 线程绑定【已实现】

**用户 2026-08-08 原话**:按 OpenClaw 的设计,每个 agent 都是独立的会话窗口;主 agent 派活
不过是**调度了一次跟它的交互**,它自己的会话依然完整存在于自己的窗口里——
除非它属于内部进程、没有产生自己的会话窗口。

三路证据均成立:

**证据一(本地落盘结构实锤,最硬)**:

| 形态 | 落盘位置 | 能否直接接管 |
|---|---|---|
| 本项目 Claude Code 内部派的子代理 | `~/.claude/projects/<项目>/<主会话uuid>/subagents/agent-<id>.jsonl` — **主会话的附属物** | ✗ 无独立会话身份 |
| OpenClaw 调度产生的会话 | `~/.claude/projects/-home-ky--openclaw-workspace/<uuid>.jsonl` — **顶层独立会话,无子目录** | ✓ 与人手动跑的会话同构同位 |

→ 实测:OpenClaw workspace 目录下**全是顶层 `<uuid>.jsonl`、没有 `subagents/` 子目录**,
即它派生的每个 agent 都持有一个**一等公民会话**,可被常规方式恢复接管。

**证据二(设计文档)**:`docs/channels/broadcast-groups.md:113` 原文
"**Each agent has its own session key and isolated context.**";
`docs/refactor/database-first.md:338` 有 per-agent session identity 的 canonical `sessions` 根表;
`docs/channels/telegram.md:564` 显示 session key 是结构化命名(形如 `agent:<id>:telegram:group:<gid>:topic:<n>`)
——**会话身份是一等公民,不是任务的附属字段**。

**证据三(接管的完整已实现机制)**:`docs/tools/subagents.md` §Thread-bound sessions(:284-337)

- `sessions_spawn` 带 `thread: true` → OpenClaw 在活跃渠道**创建或绑定一个 thread 到该 session**;
- 此后**用户在该 thread 里的后续消息直接路由到那个 sub-agent session**
  (原文:"follow-up user messages in that thread keep routing to the same sub-agent session")
  → **这就是"人工接管":不是接管一个黑盒进程,而是直接跟这个本来就存在的子会话对话**;
- 支持渠道:注册了 conversation binding adapter 的 Discord / iMessage / Matrix / Telegram;
- **手动控制命令(已实现)**:

| 命令 | 效果 |
|---|---|
| `/focus <target>` | 把当前线程绑定(或新建)到某个 sub-agent / session 目标 |
| `/unfocus` | 解除当前绑定 |
| `/agents` | 列出活跃 run 与绑定状态(`binding:<id>` / `unbound` / `bindings unavailable`) |
| `/session idle` | 查看/设置空闲自动解绑 |
| `/session max-age` | 查看/设置硬上限 |

- 配套开关:`session.threadBindings.enabled` / `idleHours` / `maxAgeHours`。

**其他相关已实现设计**(同文档):

- **Context modes**(:113-124):`isolated`(默认,干净子 transcript,省 token)/ `fork`(把请求方 transcript 分支进子会话)。
- **任务投递透明**(:146):子代理在**第一条可见的 `[Subagent Task]` 消息**里收到任务,
  系统提示只带运行规则与路由上下文,**不藏一份重复任务**
  → 保证人接进去时 transcript 自解释、看得懂来龙去脉。这是可接管性的前提。
- **`delegationMode`**(:152-159):`suggest`(默认)/ `prefer`——`prefer` 让主 agent
  "保持响应,把比直接回复更复杂的事都通过 `sessions_spawn` 派出去"
  → **正是 G3 的"派发期间对话不中断",这是配置项而非自研逻辑**。
- 并发与超时:`maxConcurrent`(示例值 4)、`runTimeoutSeconds`(默认 `0` 即不超时)。

### 4.1.1 对本项目的决定性推论

**手动接管不是一个要自研的功能,而是"执行体是否持有独立会话"这个选型的自然结果。**

| 执行体形态 | 接管成本 |
|---|---|
| Claude Agent SDK 持久会话(pipecat `code-assistant` 范式) | 会话落 `~/.claude/projects/` 顶层,**天然可 `claude --resume <session-id>` 接管,零自研** |
| 自写纯内部 `BaseWorker` 循环(无 agent 会话) | **无会话窗口,接管必须自研** |

→ **这给执行载体选型提供了一个决定性理由**:选带独立会话的 agent SDK 作执行体,
手动接管白拿;选纯内部 worker,就要自己造一套接管机制。与用户"减少自研"的口径一致。
S2a 据此收敛选型,不必再做开放式对比。

### 4.2 旁支:fleet 监督规格【规格态,非已实现】(`docs/specs/claw-supervisor.md`, 247 行)

⚠️ 该文件位于 `docs/specs/`,含 "Implementation Plan"(:189)与 "Open Questions"(:241)章节,
**属设计规格,不能当作已验证的既有能力引用**。它解决的是**多主机 fleet 级监督**
(监督一批 Codex 会话),与 §4.1 的单会话接管不是一回事,本项目当前范围用不到。
作为设计范式了解即可。

### 4.3 成熟度补充核实(2026-08-08,两路证据)

**证据一(外部调研方报告,待核实)**:OpenClaw 的"人工接管"是**尚未解决的 open issue #35208**,
现状只有手动 `/pause`/`/resume`,无自动检测、无并发一致性保证。
→ issue 编号本地无法验证(需访问 GitHub),标注为**调研方单方报告**。

**证据二(主会话本地文档实查,可验证)**:

- 在 `docs/` 全树中,`takeover` / `attach to the session` / `human handoff` 三类关键词,
  **非 `specs/` 目录下唯一命中的是 `docs/tools/chrome-extension.md`**(浏览器扩展语境,与 agent 接管无关)。
  → 佐证:**确无"人工接管"的已实现能力文档**。
- 但存在一条**已实现**的相关控制面(`docs/concepts/agent-runtimes.md:91` 原文):
  "Codex bind/control/thread/resume/**steer**/stop -> native `/codex` command surface
  when the bundled `codex` plugin is enabled."
  → 即已实现的是 **bind / control / resume / steer / stop** 这组命令,
  比调研方所说的"只有 `/pause`/`/resume`"更丰富,**该单方描述不完全准确**。
- 另有 `docs/tools/lobster.md:29` 原文:"approve/resume is a durable, built-in primitive"
  → 审批-恢复是持久化内建原语,与 §一/§二 的审批体系一致。

**合并结论**:方向判断成立——**OpenClaw 的"人工接管"不是成熟可抄的能力**,§四整节只能当范式,
不能当实现依据;但"完全没有控制手段"的说法不成立,`steer`/`stop`/`resume` 是已实现的控制原语,
可作为"接管"的最小构件参考。本项目的手动接管兜底**必须按自研对待**,不得假设有现成件。

Goal 原文关键句:supervisor 可以 "read the session, steer it, **interrupt it**, spawn related
sessions, and **accept handoffs**"。

**三角色模型**:

| 角色 | 含义 |
|---|---|
| Human-attached | 人正在交互的会话 |
| **Autonomous** | supervisor 派生的自主线程,**人可以随后 attach 上去** ← 即手动接管 |
| Supervisor | 常驻监督 agent,持有 fleet state / transcript 读取 / steering / interruption / spawning / handoff 工具 |

**设计哲学(:18,最值得抄的一句)**:
"OpenClaw **supervises** Codex rather than **hiding** Codex inside an opaque OpenClaw subagent."
外部契约是**一个可 attach 的会话 + 线程 id**,而不是不透明的子代理。

supervisor 侧组件含 "Policy engine for autonomous actions, approvals, and **loop prevention**"
——防循环与审批、自主动作同属策略引擎。

→ 对本项目:手动接管的前提是**后台任务不能是黑盒**——必须是有稳定 id、transcript 可读、
可被中断、可被 attach 的实体。这与已拍板底稿"Work 凭据=交付回执,不镜像后台内部任务图"
存在**张力**:底稿要求对外只暴露回执、不暴露内部拓扑,而可接管要求内部可观测可介入。
**S2a 需就此裁决**:可能的调和是"对话面按回执口径,接管面另开一条运维/调试通道"。

---

## 五、对本项目自研区的映射结论

| 自研项 | OpenClaw 可借鉴部分 | 成熟度 |
|---|---|---|
| 授权确认链 | 五档模式 / 取严合并 / ask 三态 / askFallback 默认 deny / 30 分钟过期 / 三档决定 / per-agent 隔离 / **计划冻结防漂移** / 审批 id 关联 | 【已实现】可放心抄 |
| 通知回流话术与时机 | followup `agent` turn / 拒绝也走同一路径 / 投递目标四规则 + 降级 / 进行中通知延迟阈值 / 主会话回灌而子会话不回灌 | 【已实现】可放心抄 |
| 完成确认铁律 | "主动告知未执行,避免事后修复缺失结果"的反谎报设计;审批 id ↔ 完成/拒绝消息强关联 | 【已实现】可放心抄 |
| 手动接管兜底 | **已重新定性(§4.1):不是自研功能,是"执行体持有独立会话"的自然结果**。机制=子任务即一等公民会话 + `thread: true` 线程绑定 + `/focus`·`/unfocus`·`/agents`·`/session idle`·`/session max-age` | 【已实现】机制清晰;本项目**成本取决于执行载体选型**:选带独立会话的 agent SDK 则零自研,选纯内部 worker 则须自研 |

## 六、本轮未取、留给 S2a 的

1. `dist/` 源码未读——上述均来自官方文档;若 S2a 要抄具体实现细节需下钻 `dist/`。
2. `docs/plugins/plugin-permission-requests.md`(195 行)未读——plugin 审批的请求字段与决定语义。
3. `docs/cli/approvals.md`(151 行)未读——CLI 侧完整参数。
4. `claw-supervisor.md` 的 Session Registry(:74)/ Control Surface(:118)/ Security(:178)
   / Acceptance Tests(:229)四节未读,手动接管若进入范围需补读。
5. OpenClaw 的审批是**命令级**(exec)粒度,我们的派活是**任务级**粒度,
   粒度映射关系需 S2a 明确(一个任务可能触发多条命令审批)。

---

## 七、源码核对(codegraph,2026-08-08)

> 用户 2026-08-08 指示"不能只看文档,需要通过源码核对"。已把包复制到
> `~/git/source-project/openclaw` 并建 codegraph 索引(7,427 文件 / 155,250 节点 / 550,657 边),
> 已登记 `codegraph-registry.md`。
> 注:codegraph 内置默认排除 `dist/`(与 `node_modules`/`.git`/`build`/`target` 同列,其源码注释
> 原文 "never node_modules/dist/… via include",即 include 规则也加不回来),故副本内 `dist/` 已改名
> 为 `openclaw-src/` 后才索引成功——**原 npm 包未动,不影响本机 OpenClaw 运行**。

### 7.1 文档结论被源码证实的部分

| 文档结论 | 源码实锤 |
|---|---|
| 三档决定 `allow-once`/`allow-always`/`deny` | `openclaw-src/plugin-approvals-D2muXfhg.js:6-10` `DEFAULT_PLUGIN_APPROVAL_DECISIONS` |
| 决定集可被限定,非法值不予接受 | 同文件 `:22-28` `resolvePluginApprovalRequestAllowedDecisions` 显式白名单过滤,空则回退默认 |
| 纯文本 `/approve` 回退路径 | 同文件 `:43` 原文拼接 `Reply with: /approve ${request.id} ${...join("|")}` |
| 审批会过期 | 同文件 `:41` `expiresAtMs` 倒计时、`:51-53` `buildPluginApprovalExpiredMessage` |

### 7.2 源码比文档更细/更准的部分(**文档单看会得出不完整结论**)

1. **超时是两套,不是一套**。文档只提 exec 审批 30 分钟过期;源码显示 **plugin 审批另有一套**:
   `DEFAULT_PLUGIN_APPROVAL_TIMEOUT_MS = 12e4`(**默认 120 秒**)、`MAX_PLUGIN_APPROVAL_TIMEOUT_MS = 6e5`
   (**上限 600 秒**),`resolvePluginApprovalTimeoutMs` 用 `Math.min(MAX, Math.max(1, ...))` 夹逼,
   非数/非有限值回退默认(防御式)。
   → 对本项目:**审批超时应按审批类型分档设定,不是全局一个值**。

2. **决定档不止三个**。`provider-capabilities-CYpG67go.js:1101-1110` `commandApprovalDecision` 还有
   **`acceptForSession`(会话级批准,介于 once 与 always 之间)**,以及
   `findAvailableCommandAmendmentDecision`(修正后再批准)。文档的"三档"描述不完整。
   → 对本项目:批准范围至少该考虑 **单次 / 本会话 / 永久** 三级,而非二选一。

3. **allow-always 的防漂移比文档写的更狠**(`exec-approvals-allowlist-D_bloa3O.js`):
   - `resolveAllowAlwaysPatternEntries` docstring 原文(:1696-1700):
     "When a command is wrapped in a shell (for example `zsh -lc \"<cmd>\"`),
     **persist the inner executable(s) rather than the shell binary**."
     → 批准被 shell 包装的命令时,**落盘的是里层真正的可执行文件,不是 shell 本身**——
     防"批准了一次 `zsh -lc` 等于永久放行任意命令"。文档完全没提这层。
   - `collectAllowAlwaysPatterns` 有 **`depth >= 3` 递归深度上限**(:1629),防嵌套 shell 无限展开。
   - `resolveAllowAlwaysPatternCoverage` 返回 `complete` 标志(:1022):**只有每个命令段都被成功表示**
     才算完整覆盖;`persistAllowAlwaysPatterns` 仅在 `coverage.complete && patterns.length > 0` 时
     才落一条整命令 pattern(:1043)。
     → 这就是文档那句"宁可拒绝发放审批也不假装覆盖"在源码里的实现方式。
   - `resolveAllowAlwaysPatternArgv`:包管理器目标 `kind === "blocked"` 时直接返回 `null`(:1625),
     即**包管理器命令被特殊阻断**,不允许被 allow-always 固化。

4. **审批请求消息带风险分级**:severity `critical`🚨 / `info`ℹ️ / `warning`🛡️(默认 warning),
   标题上限 80 字符、描述上限 512 字符,并向用户显示 `Expires in: Ns` 倒计时。

### 7.3 方法论结论

本节全部内容**无法从 `docs/` 得到**——文档描述方向正确,但在超时分档、决定档数量、
allow-always 的 shell 解包与覆盖完整性判定上均不完整。
**S2a 若要落地授权链,须以 `openclaw-src/` 源码为准,文档只作导航。**
