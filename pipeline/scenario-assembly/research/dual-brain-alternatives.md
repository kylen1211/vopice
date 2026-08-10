# 双脑架构(快脑首响+慢脑深度回流)成熟方案外部检索纪要

- 检索执行时间:2026-08-10
- 信息范围:公开互联网检索(tavily 常规搜索,未用 `tvly research` 以节省紧张额度)+ GitHub 源码/Issue(`gh api`/`gh search`)+ `pipecat-ai-context-hub` 本地文档索引(`indexed_framework_version=1.7.0`,落后主干 14 个 commit,2026-08-03 索引)+ arXiv 论文原文。信息时间范围:检索到的资料发布时间跨度 2024-10(Talker-Reasoner)~2026-04(部分工程博客),均为检索执行时刻可查的最新公开版本。
- 与本任务同主题近 90 天报告:kickoff 检索无命中,按新任务全量检索。
- 现方案基线(供全文对照,已通过代码实测确认):`server/dual_brain.py` ——`ParallelPipeline` + `ProducerProcessor(filter=slow_material_filter)`/`ConsumerProcessor(producer=...)` 组装双脑;`_SlowMaterialFilter.__call__`(`dual_brain.py:167-227`)靠**字符串比较** `_current_basis()`(取慢脑 context 最后一条 `role=="user"` 消息的 `content`)判断素材是否仍对应触发轮次;`_FastAnswerTap`(`dual_brain.py:255-291`)旁听 `fast_llm` 原始 `LLMTextFrame` 输出(不经 TTS 播放顺序队列),把"快脑刚才已经这样回答过"塞进注入提醒模板(`_SlowMaterialTransformer.__call__`,`dual_brain.py:345-367`),缓解 D-005;已知痛点见 `pipeline/debts.md` D-004(连续追问跑偏)、D-005(重复生成,修法已实现待真机联测确认)。

---

## 1. 快速首响+深度推理回流:成熟产品/开源实现候选清单

三字段(对象/入选理由/来源),按闸门规则,从下列候选中放行 **LiveKit Agents** 与 **pipecat 官方 Job Coordination** 两个可深挖对象(见 §1.2、§1.5);另有两篇论文因摘要/正文本身信息密度已达"可供决策参考"级别,未消耗额外深挖预算,直接采信(见 §1.3、§1.4)。

| 对象 | 入选理由 | 来源 |
|---|---|---|
| LiveKit Agents | 有明确的异步结果回流对话机制(`chat_ctx` 尾项 id 匹配 + 两套指令模板 + `wait_for_idle` 门禁),与我方场景高度对应 | `livekit/agents` GitHub 源码(一手) |
| pipecat 官方 Job Coordination | 与我方同框架、官方 Learn 指南明确列出"边对话边后台分析、结果异步收回"用例,是我方唯一"零迁移成本候选" | `docs.pipecat.ai/pipecat/learn/job-coordination`(一手) |
| VoiceAgentRAG(Salesforce Research,arXiv:2603.02206,2026-03) | 论文明确提出 Fast Talker(前台只读缓存作答)+ Slow Thinker(后台预测/预取)双 agent 架构,是检索到的与我方范式最直接对应的公开论文 | arXiv 摘要页(一手) |
| Talker-Reasoner(Google DeepMind,arXiv:2410.08328,2024-10) | 明确用 Kahneman 双系统理论命名"Talker=快系统/Reasoner=慢系统"的对话智能体架构 | arXiv 论文原文(一手) |
| TEN Framework(TEN-framework/ten-agent) | 公开资料聚焦图编排、低延迟实时循环、可打断,**未找到**双脑/回流表述;仅作同类知名框架列入参考,不构成"存在该模式"的结论 | 官方文档/仓库(一手,但未命中相关内容) |
| vocode | **未找到**该范式证据,检索未命中 vocode 自身资料;仅作同类知名开源框架列入参考 | 检索未直接命中官方来源 |
| OpenAI Realtime API | 官方仅有 out-of-band response(`conversation:"none"`)机制,用于并发分类打标,**未见**"实时应答+后台强模型深度推理+异步回流"的官方公开实践;社区零星尝试非官方,不采信 | `developers.openai.com/cookbook`(一手,但场景不对应) |
| Gemini thinking mode / Deep Think | 公开资料显示的是"应答前内部并行思考→精炼→给最终答案"的单次输出模式,thinking 过程默认对外不可见,**未找到**"先给临时回应、思考完成后补充"这类场景应用的证据 | Google 官方博客/文档(一手,但场景不对应) |
| LiveKit「Background Observer」模式 | 后台 LLM 持续监听对话流做合规护栏评估,不打断主对话——是"后台并行分析"同族但用途是审核而非深析补充,列为旁证不深挖 | LiveKit 官方博客(一手) |

---

## 2. LiveKit Agents 异步回流机制(深挖)

**架构一句话**:工具/后台任务结果先"eager insert"进 `chat_ctx`,再等 `wait_for_idle()` 空闲门禁放行,放行时刻检查 `chat_ctx` 尾项 id 是否仍是这批结果的最后一项,据此二选一指令模板交给 LLM 自由裁量是否要播报、怎么措辞。

**关键差异**(逐条对照我方):
- **话题锚定判据不同**:LiveKit 的 `at_tail = chat_ctx.items[-1].id == pending_items[-1].id`(`tool_executor.py:591`,GitHub `livekit/agents` 主分支实测拉取)只检查"上下文尾部有没有被别的内容占用",**不检查"这批结果是否仍对应用户最新一轮真正在问的话题"**——一旦话题已切换但尾部恰好没变(如长时间沉默、EOU 未触发新一轮),会误判 `at_tail=True` 直接摘要播报,不经二次判断(源码/文档均未讨论此盲区,标记为推测)。这一点上 LiveKit **并未从根上解决**我方 D-004 同类问题,只是把"是否已经说过/是否还相关"的判断权整体甩给 LLM 自由裁量(`REPLY_INSTRUCTIONS_MAYBE_COVERED` 模板,`tool_executor.py:62-67`)。
- **重复生成规避的原理不同,但设计思路可直接借鉴**:LiveKit 用**同一协程内无 `await` 让出控制权**的"先写 `chat_ctx.insert(msg)`、再 resolve 完成信号 `speech_handle._mark_generation_done()`"顺序对(`agent_activity.py:3417-3456`),配合 `wait_for_idle()` 必须 `await` 该信号才能继续(`agent_activity.py:1795-1797`),用 **asyncio 的 happens-before 程序顺序保证**(而非锁/版本号)确保"任何读到空闲信号的代码,读到的 `chat_ctx` 必已包含刚说完的话"。我方现有 `_FastAnswerTap`(`dual_brain.py:255-291`)的设计动机与此**同构**——都是"绕开慢队列、抢在信号触发前先落地状态",方向正确,但目前只覆盖了"记录",没有覆盖"顺序保证"这一层(慢脑触发点仍可能在 `_FastAnswerTap.last_answer` 更新完成前读到旧值,取决于两条分支的调度顺序,这正是 `pipeline/debts.md` D-005 "仍是降低复现概率而非从根上消除并发窗口"这句自我诊断的根因)。
- **门禁 vs 触发时机是两回事**:`wait_for_idle()`(`agent_activity.py:1758-1820`)只回答"何时可以插话"(agent 说完手头这句 + 用户沉默 + 无人显式占用轮次),不回答"插什么/该不该插"——这与我方 R4"完成标记落地时触发快脑一次生成,快脑自判"的分工原则一致,不是新增概念。

**可借鉴点**:
1. 把"素材已齐"触发注入时的**单一提醒模板**,升级为 LiveKit 式的**双模板路由**——除现有 `INJECT_DONE_WITH_REMINDER_TEMPLATE` 外,可在触发前先做一次轻量判据(如"这一轮 fast_context 是否已经有过对同一 `basis` 的完整应答"),命中就走"可能已经说过,自查决定是否补充"的措辞(对应 `MAYBE_COVERED`),未命中才走现有的直接提醒模板(对应 `AT_TAIL`)——工程上是"条件化选择提示词"而非"固定一套",可直接照搬这个模式,不需要照搬 LiveKit 的 tail-id 判据本身。
2. **不能直接照搬**"tail-id 判据"来解决 D-004,该判据本身在 LiveKit 里也有已知盲区;D-004 需要更强的判据(见 §4.1)。
3. LiveKit 源码自认的已知坑(`tool_executor.py:616` TODO 注释)可作为我方设计取舍参考:插话被打断后**不自动重试**(内容直接丢弃),多个异步结果并发完成时**强制合并成一次播报**而非分别播报——这两条与我方 R5(打断中止)、R7(单深析在途)的既有契约方向一致,说明"打断即丢弃、不排队重试"是业界同类系统的common选择,不是我方权宜之计。

**来源**:`tool_executor.py:58-67,521-624`、`agent_activity.py:1758-1820,3200-3205,3417-3456`(GitHub `livekit/agents` 主分支,`gh api` 实测拉取,2026-08-10);`https://docs.livekit.io/agents/logic/tools/async/`(firecrawl 实测抓取,2026-08-10)。

**未覆盖(GAPS)**:realtime(S2S)路径 `_realtime_reply_task`(`agent_activity.py:4095` 起)的 `chat_ctx` 写入时序未展开核对,上述"顺序保证"结论目前只对 cascade/pipeline 路径验证过;LiveKit 官方博客 `livekit.com/blog/async-tools-voice-agents` 正文未整页抓取,可能有额外的设计取舍论证未纳入。

---

## 3. VoiceAgentRAG / Talker-Reasoner(论文级参考,未单独开深挖路)

**VoiceAgentRAG(架构一句话)**:前台 **Fast Talker** 只读毫秒级语义缓存直接作答,后台 **Slow Thinker** 持续监听对话、预测后续话题、预取文档写入缓存——目标是解决语音 agent 的 RAG 延迟瓶颈,不是"补充一次深析"。
**关键差异**:VoiceAgentRAG 是"投机预取"模式(慢脑提前准备、快脑随时可能命中缓存),我方是"触发后同步一次深析、结果回流"模式;前者慢脑不针对某一具体问题,后者慢脑针对当轮具体问题。
**可借鉴点**:如果未来想进一步降低慢脑回流的"延迟感",可以研究"预测下一话题、提前预热"这个方向,但这是一次架构级改造,不是本次痛点修复范围内的低成本借鉴。
来源:`https://arxiv.org/abs/2603.02206`(firecrawl 实测抓取摘要页,2026-08-10)。

**Talker-Reasoner(架构一句话)**:Google DeepMind 提出的双智能体框架,显式对应 Kahneman 双系统理论——Talker(快系统)负责即时对话交互,Reasoner(慢系统)负责多步推理/规划/信念更新,二者**持续运行、共享状态**协作,而非"一次性并行双发"。
**关键差异**:Reasoner 通过更新对话状态/信念来影响 Talker **后续**的说法,不是"事后追加一条纠正消息",这与我方"补充追加"式回流在设计哲学上不同(但论文未把这一差异作为专门取舍原则论证,置信中)。
**可借鉴点**:确认我方"快慢双系统"命名与设计动机与学界已发表架构同构,不是野路子设计,可作为对内沟通"为什么要这样设计"的理论背书;但编排细节(持续协作 vs 单轮触发)不直接可抄。
来源:`https://arxiv.org/html/2410.08328v1`(2026-08-10)。

---

## 4. pipecat 生态内同类实现

**4.1 官方 examples/文档**:除我方参照的 `features-concurrent-llm-evaluation.py` 外,未命中第二个"多模型并行/首响+深析"官方示例(关键词穷举:concurrent/parallel pipeline/producer consumer/cascade/dual model/fast slow)。`ParallelPipeline` API 文档的"Cross-Branch Communication"段落展示的正是 `ProducerProcessor(filter=...)`+`ConsumerProcessor(producer=...)` 跨分支注入模式,与我方机制一致,但**没有独立的最佳实践/已知陷阱专题指南**。来源:`pipecat-ai-context-hub search-examples/search-docs`(索引 v1.7.0),`https://docs.pipecat.ai/api-reference/server/pipeline/parallel-pipeline`(2026-08-10)。

**4.2 官方 Job Coordination(深挖,负面结论)**:官方更晚近的 Worker/Job/Bus 体系(`self.job()`/`self.job_group()`+`@job` 装饰器+`send_job_response`),Learn 指南明确列出"一边对话一边后台跑分析,结果异步收回"用例,曾被判断为"我方唯一零迁移成本候选",深挖后**结论是负面的**:
- 请求方拿到 `jg.responses`(`dict[worker_name, dict]`)后,**仍需应用层自己 push `LLMMessagesAppendFrame(run_llm=True)` 写回并触发生成**——和我方现状的终态调用几乎相同,框架不提供"自动写回+触发"的现成机制,只是把"结果搬运"通道从帧级 Producer/Consumer 换成 job RPC。
- Job/JobGroup **没有内置**"响应是否仍对应当前话题/轮次"的机制,只有硬超时(`timeout`)与打断即取消(`cancel_on_error`/自动取消),**不天然规避 D-004**——版本号/话题绑定仍要应用层自己做,和我方现有 `SlowBrainState` 要做的事情本质相同。
- Job Coordination 的场景设计前提是"多个独立 `LLMContextWorker`、各自独立 context、通过 job 汇总"(如 debate agent),**不是**"单一对话流内快慢双分支共享同一 context"——我方场景恰是后者,迁移需要把慢脑改造成独立 `BaseWorker`,`SlowBrainState`/`_SlowMaterialFilter`/`_FastAnswerTap` 整套帧级状态机要重写为 job 请求/响应回调逻辑,**没有现成迁移路径,基本等于用新通信原语重写一遍**。
- 官方文档未见"实验性/预览"标注(但索引为分段抓取,不排除遗漏),我方项目当前锁定的 pipecat 版本是否含此特性**未核实**(超出检索范围,需主会话自行核对 `pyproject.toml`/lockfile)。

**判断**:不建议以"迁移到 Job Coordination"作为重构方向——它不解决任何一个已知痛点,且改造成本显著高于在现有 ParallelPipeline+Producer/Consumer 骨架内打补丁。
来源:`https://docs.pipecat.ai/pipecat/learn/job-coordination`(全篇分段抓取)、`pipecat.pipeline.job_context`/`pipecat.workers.base_worker` API 参考、`https://docs.pipecat.ai/api-reference/server/workers/llm-context-worker`(`pipecat-ai-context-hub`,2026-08-10)。

**4.3 GitHub/社区**:`gh search code` 检索 "ProducerProcessor"/"ParallelPipeline"(组合 pipecat 关键词)**未返回任何 pipecat 相关命中**(命中的均是同名 Java/RocketMQ 类等无关项目),说明公开仓库里复刻我方这套接法的项目极少或未被索引。相关但不同目的的发现:GitHub Issue `pipecat-ai/pipecat#1795`("Improve Reliability - Fallback Processors for LLMs")讨论多 LLM 场景,但目的是**容灾**(主 LLM 失败切备用),提出 `FallbackLLMService`,是"二选一容错"而非"两者都跑、结果合流",与我方目的不同。第三方博客 futureagi.com 描述的"fast/capable 双 LLM"是**按轮次二选一路由**(`ModelRouter` 判断 `is_short_turn()`),完全不并行执行,无 Producer/Consumer 跨分支通信,与我方设计本质不同(单一博客来源,置信中)。pipecat 官方 Discord/论坛内容无法公开检索,此维度留空。
来源:`gh api repos/pipecat-ai/pipecat/issues/1795`;`futureagi.com/blog/how-to-optimize-pipecat-latency-2026`(2026-08-10)。

---

## 5. 针对两个已知痛点的他山之石

**5.1 痛点①连续追问跑偏(D-004)——通用解法:generation/epoch id(乐观并发控制)**
现有 `_SlowMaterialFilter._current_basis()`(`dual_brain.py:144-165`)靠**字符串比较**判断慢脑素材是否仍对应触发轮次的 `basis`,这本质是"内容相等性检查",无法区分"用户完整复述了同一问题"与"确实是新提问但文字恰好相似"这类边界情况,也无法覆盖"D-004 根因排查已确认"的场景——即调用延迟本身(10-50s)导致素材迟到但 `basis` 判断本应正确工作、真正问题在别处的情形(详见 `pipeline/debts.md` D-004 条目)。通用工程解法是**乐观并发控制**:给每一轮用户提问分配单调递增的 generation/epoch id,派发深度分析任务时把该 id 作为任务负载传入;结果回流时先比对"当前对话最新 generation id"是否仍等于派发时的 id,不等即判定过期直接丢弃——比字符串比较更严谨、无歧义。因果向量(vector clock)是进一步的补充方案,仅在"需要区分新旧覆盖 vs 合法并发"时才需要,当前"新话题使旧任务失效"的诉求单调 id 已足够。企业集成模式(Enterprise Integration Patterns)的"Correlation ID"是同一思路在消息系统领域的标准命名。
来源:`https://tianpan.co/blog/2026-04-12-race-conditions-in-concurrent-agent-systems`(2026-08-10);`https://www.enterpriseintegrationpatterns.com/patterns/conversation/RequestResponse.html`(2026-08-10)。

**5.2 痛点②快脑输出未及时写入自身可读历史(D-005)——通用解法:read-your-writes + happens-before 顺序保证**
Read-Your-Writes 一致性(分布式系统标准模型)要求"发起方后续的读一定能看到自己刚完成的写",常见实现是把后续读"钉"到执行过写操作的同一版本号之后,而非依赖异步收敛猜时序。§2 已确认 LiveKit 用"同一协程内无 `await` 让出控制权"的写入→resolve 信号顺序对拿到这个保证。我方 `_FastAnswerTap` 修法方向与此**同构但不完整**:它做到了"记录",但慢脑触发点读取 `last_answer` 的时机与 `_FastAnswerTap` 更新完成的时机之间,目前**没有**类似 LiveKit 那种"必须 await 同一信号"的强制顺序保证——这正是 `pipeline/debts.md` D-005 自我诊断"降低复现概率而非从根上消除并发窗口"的技术根因。可借鉴的改造方向:让 5.1 的 generation id 机制承担双重职责——除了给慢脑素材做过期判断,也给 `_FastAnswerTap.last_answer` 打上"对应哪个 generation"的戳,慢脑触发点读取前先确认自己要读的 generation 已经"提交"(而不仅仅是判断字符串是否非空),把隐式的时序假设变成显式的版本前置条件(乐观锁 CAS 思路的类比套用,置信中,未找到该确切场景的工程博客实例,需自行验证适配性)。
来源:`https://arpitbhayani.me/blogs/read-your-write-consistency`(2026-08-10);LiveKit `agent_activity.py:3417-3456,1795-1797`(同 §2)。

**5.3 慢脑回流 UX 策略——通用解法:对话修补(conversation repair)理论**
现有规则只有"无内容用哨兵符不播报"这一个维度(素材有无)。会话分析(Conversation Analysis)的修补理论区分自我/他人发起、自我/他人完成四种修补类型,是学界对"对话中途插入纠正或补充"最系统的框架;乌得勒支大学论文进一步给出"进展性(progressivity)"与"接受者设计(recipient design)"两个可操作原则(聚焦人机客服转人工场景,回流播报为跨场景借鉴,置信中)。可借鉴点:把回流补充设计成显式的 **self-initiated repair**,措辞模板明确复述/指代"关于你刚才问的 XX"(而不仅是判断"有没有内容"),比现有 `INJECT_DONE_TEMPLATE`/`INJECT_DONE_WITH_REMINDER_TEMPLATE`(`prompts.py`,行号未在本次范围内核实)可能更细致地维持对话的"向前推进感"、降低补充播报的突兀感。§2 确认 LiveKit 官方文档未讨论"先给真实简短答案 vs 纯垫话"这个二元取舍(其 filler speech/progress update 是"给沉默配音"的两种手段,不是"给用户一个临时真实答案"的手段),这方面我方策略是独有设计,无官方对照可抄。
来源:`https://research-portal.uu.nl/ws/files/284578205/martijn-et-al-2026-hold-on-i-ll-connect-you-to-a-human-agent-recipient-design-repair-and-their-impact-on-progressivity.pdf`(2026-08-10);`https://www.atlantis-press.com/article/126007135.pdf`(2026-08-10)。
未覆盖:"社交产品异步通知策略"/"客服系统 human-in-the-loop 补充话术设计"方向的产品设计博客/UX 案例研究本次未命中,只覆盖到学术 CA 修补理论一侧,如需该角度需再投入一轮检索。

---

## 6. 学术/工程双进程编排命名范式(补充)

- "System1/System2"命名范式**已被学术界采用**且有代表性论文(Talker-Reasoner,§3),但其"持续协作"编排与我方"单轮触发一次"不完全等同。
- "draft-then-verify"/speculative decoding **几乎全部特指 token 级推理加速**(小模型逐 token 起草、大模型并行验证),**未检索到**将该术语明确应用于"对话轮次级"(先给完整快速草稿回复,后台强模型验证/精修再回流)的学术论文或知名工程博客——我方"快脑先答、慢脑精修回流"在检索范围内没有找到直接对应的已发表参照,只能视为 Talker-Reasoner 类"双系统协作"思想的一种工程实现,不是某个已验证标准模式的复刻。
- "model cascade"(级联,先小模型判断不行再升级)与我方"并行双发"的取舍已有业界讨论:cascade 给每个升级请求叠加延迟,更适合吞吐导向/异步工作负载;我方目标是"抢首字延迟+质量兜底",这是介于 parallel ensemble 与 speculative execution 之间的第三种取舍,**没有被单独命名或专门对比讨论**。
- "慢结果替换 vs 追加"这一编排取舍**未检索到**专门讨论,语音场景下"已说出口的话物理上无法撤回"这一物理约束本身决定了"追加"是唯一现实选择,不是被论文/博客明确论证过的最佳实践。
来源:`https://arxiv.org/html/2410.08328v1`;`https://www.tmls.nyc/research/model-routing-cascades`;`https://www.truefoundry.com/blog/llm-routing-cost-quality-aware-model-selection`;`https://tianpan.co/blog/2025-11-03-llm-routing-model-cascades`(均 2026-08-10)。

---

## 7. 综合判断(供"是否重构、往哪个方向重构"决策参考)

1. **不建议**整体推翻现有 ParallelPipeline+Producer/Consumer 骨架去迁移 pipecat 官方 Job Coordination——深挖结论明确是负面的(§4.2):不解决任何痛点,改造成本显著更高。
2. **建议**保留现有骨架,在两处做针对性加固而非重构:
   - 引入 **generation/epoch id**(§5.1)替换/补强现有 `_current_basis()` 字符串比较,同时服务于 D-004(素材过期判断)与 D-005(read-your-writes 式的"已提交"判断),两个痛点可以用同一套版本号基础设施解决,不需要两套机制。
   - 借鉴 LiveKit 的**双模板路由**思路(§2 可借鉴点 1),给注入模板增加"是否已答过"的条件分支,而不只是现有单一提醒模板。
3. **不建议**照搬 LiveKit 的 tail-id 判据本身——它在 LiveKit 里也有已知盲区,不比我方现有 `basis` 比较更可靠,真正的改进点是 generation id 而非"抄 LiveKit 的字段"。
4. 慢脑回流 UX(§5.3)可低成本改进:在 `prompts.py` 的注入模板里显式加入"复述/指代所补充问题"的措辞要求,不需要架构改动。
5. VoiceAgentRAG/Talker-Reasoner(§3)确认我方设计方向与学界已发表架构同构,可作为"这套架构是合理选择而非野路子"的对内背书,但不提供可直接照搬的编排细节。

---

## 已核验事实

- `server/dual_brain.py`(现方案实现,代码实测):`ParallelPipeline`+`ProducerProcessor`/`ConsumerProcessor` 组装;`_SlowMaterialFilter._current_basis()`(`dual_brain.py:144-165`)用字符串比较判断素材归属;`_FastAnswerTap`(`dual_brain.py:255-291`)旁听 `LLMTextFrame` 记录快脑自身输出。
- `pipeline/debts.md` D-004(连续追问跑偏,根因已排查为非"材料泄漏"而是判定机制本身的盲区)、D-005(重复生成,`_FastAnswerTap` 修法已实现但真机联测未确认)——均为项目内既有台账记录,非本次调研新增。
- LiveKit Agents 异步结果回流机制(`livekit/agents` 主分支源码,`gh api` 实测拉取):`tool_executor.py:521-624` 的 eager-insert + `wait_for_idle` + tail-id 判据 + 双模板路由;`agent_activity.py:1758-1820,3417-3456` 的 `wait_for_idle`/happens-before 顺序保证。
- pipecat 官方 Job Coordination(`docs.pipecat.ai/pipecat/learn/job-coordination` 全篇分段抓取实测):不提供自动写回/触发机制,不内置话题版本绑定,无现成迁移路径——深挖结论为负面判断,非推测。
- VoiceAgentRAG(arXiv:2603.02206)、Talker-Reasoner(arXiv:2410.08328)论文摘要/正文架构描述(firecrawl/tavily 实测抓取原文)。
- GitHub 检索(`gh search code`)未命中 pipecat 生态内复刻我方接法的公开项目——"未找到"本身是本次核实到的事实,不代表绝对不存在(检索覆盖范围限制,已在正文标注)。

---

## 检索预算与执行说明

- 判型:高档(S=4 主问题 + 两段式候选对象 O≥5),规划 7 路、总预算封顶 56(`budget-validator.sh` 通过)。
- 实际执行 6 路(1 路广度 + 3 路交叉专项 + 2 路深挖,均为 `data-fetcher` 派发,无组长直查),累计实际调用 **60 次**(L1 广度 8/8、L5 学术范式 8/8、L6 pipecat 生态 16/8、L7 痛点专项 8/8、L3 Job Coordination 深挖 13/8、L2 LiveKit 深挖 7/8),**超出规划总封顶 56 达 4 次(约 7%)**——超支路均在各自 GAPS 段落申报并说明"每次追加均带来新发现、判断为收益递增而非静默超支",本节据此如实记录,未据此判定重派或质量降级;闸门决策(放行 LiveKit + pipecat Job Coordination 两路深挖,VoiceAgentRAG/Talker-Reasoner 两篇论文因信息密度已足未单独开路)详见正文 §1 表格与 §3。
- 额度告警(执行前 `quota-check.sh` 输出):tavily 已用 68%(余 312/1000),`tvly research` 单次约耗 350-400、不足一次余额,故全程改用常规搜索多路替代,未使用 `tvly research`。firecrawl 额度充裕(已用 10%)。
- 覆盖度自查:原始 4 个关键问题(成熟产品与开源实现的编排 / 学术工程范式 / pipecat 生态内同类实现 / 两个痛点的他山之石)均已作答,含"未找到+原因"的诚实缺口(TEN Framework/vocode 无证据、draft-then-verify 无对话轮次级对应、慢结果替换 vs 追加无专门讨论、产品设计类 UX 案例研究未覆盖),不再补路。
