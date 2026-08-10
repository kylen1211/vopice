# facts.md — s1a 已核验事实汇编(机械汇集自三份纪要,原文为准)

> 汇编时间 2026-08-10;来源:codebase-survey.md / external-research.md / dual-brain-alternatives.md,各自末节「已核验事实」原文摘录。设计与实现阶段只引用本文件所列事实;新出现的未验事实回 s1a 补验。

---
## 来源一:codebase-survey.md(现状盘点·实测)
## 5. 已核验事实(命令 + 输出摘要 + 结论)

① **实装 pipecat 版本**
- 命令:`cd server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -c "from importlib.metadata import version; print(version('pipecat-ai'))"`
- 输出:启动横幅 `Pipecat 1.6.0 (Python 3.11.15)`;`pipecat-ai version: 1.6.0`;`pipecat.__file__ = server/.venv/lib/python3.11/site-packages/pipecat/__init__.py`
- 结论:实装 = 1.6.0,与 `server/pyproject.toml` 的 `pipecat-ai[...]==1.6.0` 一致。

② **ServiceSwitcher 存在性、模块路径与签名**
- 命令:`uv run python -c "import pipecat.pipeline.service_switcher as m; print(m.__file__, dir(m)); import inspect; print(inspect.signature(ServiceSwitcher.__init__))"`
- 输出:模块 `pipecat/pipeline/service_switcher.py`;公开符号含 `ServiceSwitcher`、`ServiceSwitcherStrategy`、`ServiceSwitcherStrategyManual`、`ServiceSwitcherStrategyFailover`、`ManuallySwitchServiceFrame`、`ServiceSwitcherFrame`、`ServiceSwitcherRequestMetadataFrame`;`ServiceSwitcher.__init__(self, services: list[FrameProcessor], strategy_type: type[StrategyType] = ServiceSwitcherStrategyManual)`;`ServiceSwitcherStrategyManual.__init__(self, services: list[FrameProcessor])`
- 结论:1.6.0 **已有** ServiceSwitcher。用法:传策略**类**(非实例);属性 `.strategy` / `.services`;策略事件 `on_service_switched`;切换靠下推 `ManuallySwitchServiceFrame(service=<服务实例>)`(`ServiceSwitcherStrategyManual.handle_frame` 只认这个帧类型)。内部实现 = 每个服务包成 `FunctionFilter(DOWNSTREAM) → service → FunctionFilter(UPSTREAM)` 的并行分支,filter 判据是 `service == strategy.active_service`。

③ **LLMSwitcher 存在性与签名**
- 命令:同上 python 内 `from pipecat.pipeline.llm_switcher import LLMSwitcher`
- 输出:`pipecat.pipeline` 包含模块 `llm_switcher`;`LLMSwitcher.__init__(self, llms: list[LLMService], strategy_type=ServiceSwitcherStrategyManual)`;MRO = `LLMSwitcher → ServiceSwitcher → ParallelPipeline → BasePipeline → FrameProcessor`;含 `register_function` / `register_direct_function`
- 结论:换 LLM 用 `LLMSwitcher`(它把工具注册转发到全部成员 LLM,官方示例注释:context 里的 direct functions 会自动注册到每个成员,切换后工具仍可用)。

④ **本地 pipecat 源码副本与实装不一致(引用行号前必查)**
- 命令:`diff ~/git/source-project/pipecat/src/pipecat/pipeline/service_switcher.py server/.venv/.../pipecat/pipeline/service_switcher.py`
- 输出:副本比实装**多出约 44 行** `ServiceUpdateSettingsFrame` 跨非活跃服务派发逻辑(`_update_inactive_services` / `_inactive_update_targets` / `_inactive_service_updates` ring)
- 结论:实装 1.6.0 的 switcher **不会**把 settings 更新同步给非活跃成员服务。引用 switcher 源码一律以 venv 那份为准,不用 `~/git/source-project/pipecat`。

⑤ **嵌套 ParallelPipeline 内放 ServiceSwitcher(构造级)**
- 命令:`uv run python -c "...Pipeline([ParallelPipeline([ServiceSwitcher(services=[a,b])],[x])])..."`
- 输出:`Linking Pipeline#4::Source -> ParallelPipeline#0` / `-> Pipeline#4::Sink`;`nested construct OK`;`active: svcA`
- 结论:构造与链接可通过,初始 active = 列表第一个。**仅构造级证据,运行期帧流转行为未验证**——真要嵌进双脑并行分支,须在设计/实现段补运行期证据。

⑥ **运行时改 system_instruction / model / voice 无需重建服务(1.6.0)**
- 命令:`uv run python -c "d=OpenAILLMService.Settings(system_instruction='你是面试助手'); print(d.model); LLMUpdateSettingsFrame(delta=d)"` 及 `inspect.getsource(LLMService._update_settings)`
- 输出:稀疏构造成功,未给字段 = `NOT_GIVEN`;`LLMUpdateSettingsFrame(delta=...)` 构造成功且 `delta.system_instruction` 可读;`_update_settings` 源码含 `if "system_instruction" in changed:` 分支(重新快照 base prompt 并 `_compose_system_instruction()`);frames 模块含 `LLMUpdateSettingsFrame`/`TTSUpdateSettingsFrame`/`STTUpdateSettingsFrame`/`ServiceUpdateSettingsFrame`;`ElevenLabsTTSService.Settings(voice='abc')` 稀疏 delta 同样成立
- 结论:**"换 prompt / 换同网关模型 / 换音色"这条路径不需要 ServiceSwitcher**,推一个 `*UpdateSettingsFrame(delta=...)` 即可;ServiceSwitcher 解决的是"换到另一个 service 类/另一家厂商"。两条路径成本差一个数量级,设计段须分清各自适用面。(以上为源码级 + 构造级证据,未做端到端运行验证。)

⑦ **RTVI 客户端→bot 控制通道存在**
- 命令:`uv run python -c "from pipecat.processors.frameworks.rtvi import RTVIProcessor; inspect.getsource(RTVIProcessor.__init__)"`
- 输出:注册事件 `on_bot_started` / `on_client_ready` / `on_client_message` / `on_ui_message`;模块含 `RTVIClientMessageFrame`、`RTVIServerResponseFrame`
- 结论:运行时切场景/切服务有现成的客户端→bot 通道(`on_client_message`)。本仓当前只用了 `on_client_ready`。

⑧ **`Config.scenario` 无消费点**
- 命令:`grep -rn "SCENARIO\|scenario" --include=*.py --include=*.ts --include=*.tsx server client/src | grep -v .venv`
- 输出:命中全部集中在 `server/config.py`(白名单校验)与 `server/tests/test_config.py`;`client/src` 零命中
- 结论:场景当前只是启动期门禁枚举,不驱动任何装配差异;客户端完全无场景概念。

⑨ **`server/evals/fault_run/bot.py` 是符号链接**
- 命令:`ls -la server/evals/fault_run/`
- 输出:`bot.py -> ../../bot.py`、`.env -> ../fault.env`
- 结论:codegraph 把它当第二份文件报的"双份 bot.py",实际是同一文件,无漂移风险。

⑩ **测试基线**
- 命令:`cd server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run pytest -q` / `... -q --ignore=tests/test_task_dispatch.py`
- 输出:前者 `ERROR tests/test_task_dispatch.py - FileNotFoundError: .../pipeline/task-dispatch/baseline/mcp-event-sample.json` → `Interrupted: 1 error during collection`;后者 `53 passed, 33 warnings in 5.08s`
- 结论:整套测试当前**无法收集**,根因是 commit 8d11dd2 删除了 `pipeline/task-dispatch/baseline/`,而 `tests/test_task_dispatch.py:68` 在 import 期读该 JSON。既有破损,先于本变更存在,须先定夺再开工。

---
## 来源二:external-research.md(ServiceSwitcher 官方资料)
## 已核验事实

1. **结论**:`ServiceSwitcher` 用 `FunctionFilter` 三明治结构实现"只有 active 服务处理帧",但 `StartFrame`/`EndFrame`/`CancelFrame` 对所有候选服务无条件放行,候选服务与 pipeline 同生命周期建连/断连,不是懒加载。
   **来源**:`src/pipecat/pipeline/service_switcher.py:273-345`(本地 clone,commit `0db3c9a0`);`src/pipecat/processors/filters/function_filter.py:57-71`。
   **核验方式**:直接 Read 源码,交叉核对两个文件的过滤逻辑一致。

2. **结论**:`ServiceUpdateSettingsFrame` 默认只送达 active 服务;需要传 `reach_inactive_services=True` 才能让设置(含 `system_instruction`)同时下发给所有候选服务,该字段是 2026-07-31 修复 issue `#5150` 时新增的。
   **来源**:`src/pipecat/frames/frames.py:2081-2109`;`tests/test_service_switcher.py:635-800`;GitHub `pipecat-ai/pipecat#5150`(state_reason=completed)+ 关联 PR `#5155`。
   **核验方式**:源码字段存在性 Read 确认;issue 状态与关联 PR 通过 `gh api repos/pipecat-ai/pipecat/issues/5150` 与 `/timeline` 查询确认(cross-referenced #5155)。

3. **结论**:`ServiceSwitcherStrategyFailover` 的错误归因(哪个服务真正报错触发 failover)问题已在 PR `#4149` 修复,当前源码已判断 `frame.processor == active_service` 才转发 `handle_error`。
   **来源**:`src/pipecat/pipeline/service_switcher.py:341-343`;GitHub `pipecat-ai/pipecat#4139`(closed/completed)含维护者评论确认修复方案。
   **核验方式**:issue 评论区(`gh api .../issues/4139/comments`)与当前源码逻辑比对一致。

4. **结论**:官方文档 "Event Handlers" 小节示例 `@switcher.event_handler("on_service_switched")` 与源码实际注册对象不符——事件实际注册在 `ServiceSwitcherStrategy` 实例上,直接挂 `switcher.event_handler` 会被 `BaseObject.add_event_handler` 静默丢弃(仅打 warning,不报错,回调不触发)。
   **来源**:`src/pipecat/pipeline/service_switcher.py:65`;`src/pipecat/utils/base_object.py:195-206`;文档页 `https://docs.pipecat.ai/api-reference/server/utilities/service-switchers/service-switcher`(`get-doc` 抓取全文比对"Custom Strategies"与"Event Handlers"两小节示例代码不一致)。
   **核验方式**:源码逐行读取 `_register_event_handler` 调用位置 + `add_event_handler` 的静默丢弃分支;文档全文通过 `pipecat-ai-context-hub get-doc` 抓取后人工比对两处示例代码。

5. **结论**:`LLMSetToolsFrame` 存在且是官方"运行时换工具集"的机制;不存在专门的"LLMSetSystemInstructionFrame",系统提示热更走 `LLMUpdateSettingsFrame(delta=LLMSettings(system_instruction=...))`。
   **来源**:`src/pipecat/frames/frames.py:690-702`(`LLMSetToolsFrame`);全仓 `grep -n "system_instruction\|SystemInstruction" src/pipecat/frames/frames.py` 零命中;`src/pipecat/services/llm_service.py:541-579`(`_update_settings` 处理 `system_instruction` 变更)。
   **核验方式**:全文件 grep 排除法 + 源码 Read 确认替代机制存在且逻辑自洽(重新快照 base + 重新拼接框架追加指令)。

6. **结论**:LLM 切换不丢对话上下文,是因为官方两个 example 都把 `LLMContext`/聚合器实例放在 switcher **外层共享**,而不是每个 LLM 各自持有 context。
   **来源**:`examples/features/features-service-switcher.py:123-137`;`examples/flows/llm_switching.py:191-224`。
   **核验方式**:通读两个官方 example 全文,确认 context/aggregator 构造与 pipeline 组装顺序。

7. **结论**:官方样例明确"在工具调用回调里触发 LLM 切换"必须从 `context_aggregator.assistant()` 以 `FrameDirection.UPSTREAM` push `ManuallySwitchServiceFrame`,而不能直接从 worker 顶层入队,否则切换时序会晚于工具调用结果回流。
   **来源**:`examples/flows/llm_switching.py:110-124`(含官方代码注释显式说明原因)。
   **核验方式**:Read 源码与随附注释,注释本身即维护者对该坑的书面说明。

8. **结论**:Pipecat Flows 的 `NodeConfig` 不含 STT/TTS 服务选择字段,"prompt+LLM+STT+TTS"一体化场景配方没有官方现成件;官方最接近的组合是 `NodeConfig`(prompt+工具)与 `LLMSwitcher`(LLM 实例)的正交拼接(`examples/flows/llm_switching.py`),STT/TTS 联动仍需应用层自研。
   **来源**:`examples/flows/llm_switching.py` 全文;`pipecat-ai-context-hub search-docs "flows node config persona switching"` 返回的 `/api-reference/pipecat-flows/flow-manager` 等页面未见 STT/TTS 字段。
   **核验方式**:官方 example 通读 + 文档检索关键词覆盖 `NodeConfig`/`FlowManager` 相关全部索引页,人工确认无 STT/TTS 配置项。

9. **结论**:GitHub 公开检索未发现"pipecat 场景配方层(prompt+服务组合)"的社区成熟实践或设计讨论,现有 `ServiceSwitcher`/`LLMSwitcher` 相关 issue 全部是缺陷修复类。
   **来源**:`gh search issues "ServiceSwitcher"` / `"LLMSwitcher"`(pipecat-ai/pipecat,2026-08-10 执行,约 15 条命中,逐条人工过一遍标题分类);`gh search code "ScenarioConfig"` / `"PersonaConfig pipecat"` / `"scenario_profile"` / `"NodeConfig role_message ServiceSwitcher"`(全站,2026-08-10 执行)。
   **核验方式**:命令直接执行并逐条人工核对结果相关性;负向结果(未命中)只能证明"未见公开实践",已在第 3 节明确标注该证据边界(私有仓库不可见)。

10. **结论**:issue `#4834`(ParallelPipeline 内部生命周期帧同步问题)截至 2026-08-10 仍为 open 状态,是自动代码扫描工具发现、无人工评论跟进的边缘场景,常规手动切换路径不受影响。
    **来源**:GitHub `pipecat-ai/pipecat#4834`(`gh api repos/pipecat-ai/pipecat/issues/4834`,`state: open`,标签 `code-scan-issue-found`)。
    **核验方式**:直接查询 issue 当前状态与标签,判定其性质(自动扫描而非人工复现报告)。

---
## 来源三:dual-brain-alternatives.md(双脑方案检索)
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
