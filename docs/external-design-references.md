# 外部方案参考(已核实数据,自含版)

> 用途:**方案参考**——设计期(门二)借鉴外部同类项目的契约与机制,不重开框架选型(pipecat 已定)。
> 本文自含全部关键内容,原始调研目录(`~/research/` 下相关话题)清理后不影响使用。
> 核实方式:GitHub API / gh code search / PyPI / 本地 pipecat clone 源码,核实日期 2026-08-01~02。未核实项显式标注。

## 1. 派活底稿:qwen-audio-agent 的 Work 契约(已拍板采用,不新增其他形式)

来源:`QwenAudio/qwen-audio-agent`(GitHub 实查 2026-08-01;Apache 2.0 可自由借鉴;640★,活跃;JS/Node 栈,**抄契约不抄实现**)。定位与我们同构:语音前台先应答、慢任务派后台 agent、完成后自然回到对话播报。

### 1.1 Work 状态机

- 状态可穷举:`queued → running → completed`;旁支 `delegated → finalizing`、`cancelling → cancelled/failed`。UI 把 queued/running 合并显示为"处理中"。
- Work 凭据 = **交付回执,不镜像后台内部任务图**:只记用户请求、时间戳、最终结果/错误、泛化工具活动、有界权限摘要、通知状态;不记执行模式/子 agent 状态/后台拓扑。
- **重启语义诚实而廉价**:重启后在途 Work 一律置 `failed` 并附明确 restart 原因;只持久化已完成结果与通知投递状态。

### 1.2 投递不变量

- **安全插入窗**:结果播报等安全窗口;用户在说话/有 pending 响应就延后重试;**播完才标 delivered**;重试有界,单条坏结果不阻塞后续。
- **renewable claim**:防两个在线前端重复播报同一结果。
- **进度只观测不播报**:后台进度投影成泛化活动展示,绝不产生口头状态播报。
- **取消是确认制**:`cancelling` 挂住直到确认停止才转 `cancelled`;停不掉转 `failed` 附错。
- **delegation 关联**:只有与 delegation ID 关联的完成事件才能完成 Work;忙目标/空结果/无关更新/旧结果都不能。
- `presentation.speech` 是**语义素材不是逐字稿**,前台按当下对话自适应改写。
- 完成播报唯一来源:**"Is completion spoken only from a final backend Agent result?"**(对方 review checklist 原文)= 我们的"未确认完成绝不报办好了"。

### 1.3 前台工具白名单 + 依赖方向(治耦合)

- 前台只有六个工具:`spawn_thinking / cancel_agent_task / get_agent_task_status / get_current_time / user_memory / respond_agent_permission`;明文禁止前台拥有选/建/续/取消后台 Session、选执行策略、选工具的能力。
- 依赖单向:前台工具不得 import 后台适配器;UI 只消费公开 Work 事件。
- `spawn_thinking(objective)`:objective 是对用户请求的**保守转述**而非执行计划;近期语音上下文单独随信封带给后台;final ASR 是事实源。

### 1.4 佐证

- Linux/Windows 上对方也没解决 AEC(默认半双工、按键打断,全双工要求耳机)——MVP 用耳机/半双工是同行实际选择。

## 2. 快慢脑方案参照(三个,均已核实存在)

| 参照 | 机制 | 实锤 | 用法 |
|---|---|---|---|
| pipecat 组装件 | ParallelPipeline 并行分支 + producer/consumer processor | 本地 clone `pipeline/parallel_pipeline.py`、`processors/{producer,consumer}_processor.py`;**最佳参照示例 `examples/features/features-concurrent-llm-evaluation.py`(双 LLM 并行)**;producer/consumer 官方 examples 零用例,用法读源码 | 我们的实现载体 |
| LiveKit 垫话调度器 | `_FillerScheduler`:慢任务超时自动切入垫话,主任务算完自动接管流;垫话须提取前文实词,避免机械"嗯…" | gh code search 实锤:`livekit-agents/livekit/agents/voice/filler_scheduler.py` + `tests/test_filler.py`(2026-08-02) | **机制设计参考**(触发时长阈值等参数未验证,见 §5) |
| Salesforce VoiceAgentRAG | 预判预拉取:前台 FastTalker 亚毫秒缓存查找,后台 SlowThinker 异步预拉取向量库 | 仓库实锤 `SalesforceAIResearch/VoiceAgentRAG`(2026-07-28 建库,gh 实查) | 思路参考,RAG 场景才用得上 |

另:旧项目成功版快慢脑在 `~/git/voice-translate-v2` 的 `vt/processors/assist.py`(账单 G2 已录)。

## 3. 框架对比结论(kit=LiveKit Agents vs pipecat,选型佐证,已定不重开)

- 1v1 小规模(≤10 管线):**pipecat 最优**——FastAPI 内嵌、零重型 SFU 运维;LiveKit Agents 强绑定自家 SFU/Cloud,仅在强制要标准 WebRTC 全家桶时才选。
- 架构哲学:LiveKit=事件驱动+Job/Session 抽象、打断高度封装开箱即用;pipecat=Frame/Pipeline 数据流、打断显式 Frame 传递、控制粒度细(适合我们自定义快慢脑控制流)。
- 版本事实(PyPI 实查 2026-08-02):`pipecat-ai` 最新 **1.7.0**(我们锁 1.6.0,升级影响门二评估;本地 clone main 已含 1.7 方向代码如 `InterruptionFrame`);`livekit-agents` 1.6.7。stars:pipecat ~13.8k,livekit/agents ~11.6k。
- 许可:pipecat BSD-2 / LiveKit Apache-2.0。

## 4. 评测工具链与业务蓝本(备用)

- pipecat 官方评测:命令口径 `pipecat eval run`(本项目 1 期已在用);`EvalJudge` 在 `evals/judge.py`。
- `ServiceNow/eva`:端到端语音 agent 评估框架(业务履约+音质/延时/WER),仓库实锤。
- `kwindla/aiewf-eval`(Daily 创始人开源):仓库实锤,但其自述是"A long-context eval","多轮语音评测集"定性**待确认**,要用先看 README。
- LiveKit 业务蓝本(examples 实锤,业务形态参考):`frontdesk/`(客服转接)、`survey/`(多节点状态机问卷)、`hotel_receptionist/`(嘈杂环境)。

## 5. 未验证参数(引用前必须先验证,禁直接当事实用)

- Silero VAD 推荐配置 `min_speech_duration_ms=250 / min_silence_duration_ms=400`;
- 垫话触发阈值(一说 >200ms,一说 >250ms,两处来源自相出入);
- "短于 200ms 噪音自动过滤"的 turn detector 行为。
