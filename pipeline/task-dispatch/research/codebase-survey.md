# 现状盘点 · task-dispatch(C4 派活)

> 来源:codegraph_explore 实查 `server/bot.py` / `server/prompts.py` / `server/evals/`,
> base_commit `cb3e857`,盘点日期 2026-08-08。所有行号引自本次实查的 verbatim 源码。

## 1. 现有 pipeline 形态(server/bot.py:270-298)

```
transport.input() → stt → vad_processor(SileroVAD) → user_turn_processor
  → ParallelPipeline(
      [快脑分支] consumer → fast_pair.user() → fast_llm → fast_answer_tap
                 → sentinel_filter → tts → transport.output() → fast_pair.assistant()
      [慢脑分支] slow_pair.user() → slow_llm → sentence_aggregator → producer
                 → slow_pair.assistant()
    )
```

- 快脑分支是**整条 pipeline 唯一对外输出通道**(bot.py:278 注释原文)。
- 两个 context 独立:`fast_context` / `slow_context`,均 `LLMContext()` 无参构造(bot.py:229-230)。
- 两组 aggregator 都用 `ExternalUserTurnStrategies()`,轮次由公共 VAD/UserTurn 段统一驱动(bot.py:232-242)。
- 装配出口 `AssembledPipeline` dataclass(bot.py:136-154)聚合 12 个对象供结构性测试断言。

## 2. 会话生命周期(server/bot.py:358-413)

- `run_bot(transport, runner_args)`:`assemble_pipeline` → 挂 3 个事件处理器 → `WorkerRunner(handle_sigint=False)` → `add_workers(worker)` → `run()`。
- `worker.rtvi.event_handler("on_client_ready")` → `seed_greeting_messages()` + `queue_frames([LLMRunFrame()])`。
- `transport.event_handler("on_client_disconnected")` → `await worker.cancel()`。
- `bot(runner_args)` 入口注册两个 transport:`webrtc`、`eval`(EvalTransportParams)。

## 3. 派活相关的关键缺口(实查确认为"当前不存在")

| # | 缺口 | 证据 |
|---|---|---|
| K1 | **无 function calling / tools** | `LLMContext()` 两处均无 `tools=` 参数(bot.py:229-230);全仓无 `register_function` / `FunctionCallParams` 调用点 |
| K2 | **无 bus / 多 worker** | 只有单个 `PipelineWorker` + `WorkerRunner`(bot.py:310-317, 390-393);未 import `pipecat.bus` / 额外 worker 类型 |
| K3 | **无 app_resources** | `PipelineWorker(...)` 只传 `params` 与 `rtvi_observer_params`,无 `app_resources=`;跨 handler 状态目前靠闭包 |
| K4 | **无任何持久化** | 两个 context 纯内存,进程退出即丢;仓内无 DB/文件状态存储 |
| K5 | **客户端极薄,无任务面板** | `client/src` 合计 277 行(App.tsx 65 / config.ts 101 / main.tsx 66 / TransportSelect.tsx 38),是 voice-ui-kit 脚手架形态 |

## 4. 可复用件(派活可直接接的既有机制)

| # | 件 | 位置 | 派活用法 |
|---|---|---|---|
| R1 | **RTVI 服务端消息通道已通** | bot.py:187-189 `worker.queue_frames([RTVIServerMessageFrame(data={"type": ..., "turn": ...})])` | 任务状态/完成事件推客户端面板的现成通道,协议已跑通(慢脑失败提示在用) |
| R2 | **RTVIObserverParams 泄漏封锁模式** | bot.py:300-308 `ignored_sources=[...]` + `user_llm_enabled=False` | 派活若新增静默分支/processor,按同款模式防内部消息泄漏到客户端转写 |
| R3 | **Producer/Consumer 跨分支搬运** | bot.py:255-261 | 后台结果回流快脑的现成搬运机制(慢脑素材注入即此法) |
| R4 | **注入模板常量单一事实源** | prompts.py:71-85 `INJECT_*_TEMPLATE` | 派活的完成播报素材注入沿用同款常量化约定,禁内联字面串 |
| R5 | **session 级实例工厂约定** | `build_slow_material_filter()` / `build_sentinel_filter()` / `build_fast_answer_tap()` | 派活的状态机实例必须同样 session-scoped,不得模块级单例 |
| R6 | **eval 场景资产 18 个** | `server/evals/*.yaml` | 派活新场景照此形制扩;`judge_factory.judge_llm` 已可用 |

## 5. 硬约束与冲突点(必须在 PRD/设计里正面处理)

- **C1(冲突·最高优先)**:`prompts.py:22-29` `CAPABILITY_BOUNDARY_SECTION` 现在明文声明"无任何执行类能力,禁止出现已完成/已处理表述";
  `evals/r4_no_false_completion.yaml` 就是守这条的验收用例(judge 判据:"回复明确说明自己没有执行操作的能力")。
  **派活一旦落地,这条边界段与该 eval 必须同步改写**——但"未确认完成绝不报办好了"这半条铁律要保留并强化。
  prompts.py:7 原文已写明"能力边界段改动须同步复核 evals/r4_*.yaml"。
- **C2**:`SYSTEM_PROMPT` 是 5 段拼装(官方段/能力边界/语言/简洁/双脑),派活要加段,须评估对既有 R4 与双脑用例的回归影响。
- **C3**:快脑分支是唯一输出通道 → 派活的完成播报只能经快脑说出,不能另开输出分支(否则与 R2 泄漏封锁、打断语义冲突)。
- **C4**:`on_client_disconnected` 直接 `worker.cancel()` → 断连即杀 pipeline;而派活要求"任务不随对话中断",两者语义直接冲突,需定任务与会话的生命周期边界。
- **C5(债务重叠)**:本次触达 `server/bot.py`,与 D-002(TTS 卡死)、D-003(顶层副作用逼测试绕过)同模块;D-003 若不先清偿,派活新增装配代码会继续加重 `sys.modules` 测试绕过。

## 6. 已拍板的外部底稿(docs/external-design-references.md §1,2026-08-02 用户拍板,不新增其他形式)

qwen-audio-agent Work 契约要点(自含版已核实):

- **状态机**:`queued → running → completed`;旁支 `delegated → finalizing`、`cancelling → cancelled/failed`;UI 合并 queued/running 显示"处理中"。
- **Work 凭据 = 交付回执**,不镜像后台内部任务图(只记请求/时间戳/结果/泛化工具活动/权限摘要/通知状态)。
- **重启语义诚实而廉价**:重启后在途 Work 一律置 `failed` 附 restart 原因;只持久化已完成结果与通知投递状态。
- **投递不变量**:安全插入窗(用户在说话就延后)/ 播完才标 delivered / renewable claim 防重复播报 / **进度只观测不播报** / 取消是确认制 / delegation ID 关联才能完成 Work。
- **presentation.speech 是语义素材不是逐字稿**,前台按当下对话自适应改写(与 R4 注入模板约定同构)。
- **前台工具白名单六个**:`spawn_thinking / cancel_agent_task / get_agent_task_status / get_current_time / user_memory / respond_agent_permission`;明文禁止前台选/建/续/取消后台 Session、选执行策略、选工具。
- **依赖单向**:前台工具不得 import 后台适配器;UI 只消费公开 Work 事件。

## 7. 最大未定项(需外部调研 + 用户拍板)

**执行载体待定**(`docs/capability-ledger.md` G3 行原文)。qwen 底稿只给了前台契约与投递不变量,
没有回答"后台真正干活的是谁"。这是 PRD 无法回避的第一决策点,已列入外部调研问题清单。
