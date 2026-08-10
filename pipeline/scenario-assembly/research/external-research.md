# 场景装配层 + ServiceSwitcher 外部检索调研纪要

- 检索执行时间:2026-08-10
- 信息范围:pipecat 官方仓本地 clone `~/git/source-project/pipecat`(commit `0db3c9a0a8d4982c997afd073a3f6372e9d44515`,2026-08-04)+ `pipecat-ai-context-hub` 本地文档索引(`indexed_framework_version=1.7.0`,索引落地时间 2026-08-03,比本地 clone 落后 14 个提交,已用源码交叉核验,以源码为准)+ GitHub 公开检索(`gh search` / `gh api`,覆盖 pipecat-ai/pipecat 仓库 issue 与全站公开代码索引)。
- 与 kickoff 命中的同 90 天报告(`2026-08-02-voice-agent-livekit-vs-pipecat`,主题为 LiveKit vs Pipecat 框架横向对比)不重叠 —— 本次是 ServiceSwitcher API 与场景配方层的框架内部机制调研,未复用该报告内容,按新任务全量检索。

---

## 1. ServiceSwitcher 现行 API

**类与模块**
- `ServiceSwitcher`(`src/pipecat/pipeline/service_switcher.py:214`)——继承 `ParallelPipeline`(`ParallelPipeline → BasePipeline → FrameProcessor → BaseObject`)。
- `LLMSwitcher`(`src/pipecat/pipeline/llm_switcher.py:24`)——`ServiceSwitcher[StrategyType]` 的 LLM 专用子类,额外提供 `run_inference()`(一次性推理,绕开 pipeline)、`register_function()` / 已弃用的 `register_direct_function()`(向全体成员 LLM 广播注册,不论是否 active)、以及对 `LLMContextFrame` 的钩子(见第 2 节)。

**构造方式**(`service_switcher.py:233-244`,`llm_switcher.py:32-44`)
```python
switcher = ServiceSwitcher(services=[svc1, svc2], strategy_type=ServiceSwitcherStrategyManual)  # 默认策略即 Manual
llm_switcher = LLMSwitcher(llms=[llm1, llm2], strategy_type=ServiceSwitcherStrategyManual)
```
官方文档确认页面:`https://docs.pipecat.ai/api-reference/server/utilities/service-switchers/service-switcher`、`.../llm-switcher`(2026-08-03 索引)。

**支持的服务类别**:构造参数类型是 `list[FrameProcessor]`,不限定服务种类——官方 example(`examples/features/features-service-switcher.py:87-118`)同时演示了 STT switcher(Cartesia/Deepgram)、TTS switcher(Cartesia/Deepgram)、LLM switcher(OpenAI/Google,用 `LLMSwitcher`)三种,证实 STT/LLM/TTS 均直接支持,STT/TTS 用基类 `ServiceSwitcher` 即可,LLM 建议用专用 `LLMSwitcher`(多了工具广播与 context 同步)。

**触发机制**:纯 frame 驱动,不是调方法。`ManuallySwitchServiceFrame(service=<目标 FrameProcessor 实例>)`(`frames.py:2239`,继承 `ServiceSwitcherFrame`(`frames.py:2232`)→`ControlFrame`)经 `worker.queue_frame(s)` 或从任意 processor `push_frame` 送入 pipeline;`ServiceSwitcher.process_frame` 拦截 `ServiceSwitcherFrame` 交给 `strategy.handle_frame()` 决议(`service_switcher.py:354-360`)。

**切换策略**(均是类,不是实例,传给 `strategy_type=`):
- `ServiceSwitcherStrategyManual`(默认,`service_switcher.py:129-158`)——收到 `ManuallySwitchServiceFrame` 才切,初始 active = 列表第一个。
- `ServiceSwitcherStrategyFailover`(`service_switcher.py:161-208`,继承 Manual,故也保留手动切换能力)——active 服务上报非致命 `ErrorFrame` 时自动轮询切到列表下一个(回绕);失败服务留在列表里,恢复策略留给应用层通过 `on_service_switched` 事件自行处理。
- 自定义策略:子类化 `ServiceSwitcherStrategy`,重写 `handle_frame`/`handle_error`;若想保留 Manual 或 Failover 的能力,应继承对应类而不是基类(官方文档"Custom Strategies"小节明确此建议)。

**底层实现**:`ServiceSwitcher` 把每个服务包成 `FunctionFilter → Service → FunctionFilter` 三明治(`service_switcher.py:273-301`),filter 函数判断 `service == strategy.active_service`,`filter_system_frames=True` 意味着连系统帧也按 active 状态过滤——**但** `FunctionFilter._should_passthrough_frame`(`processors/filters/function_filter.py:57-71`)把 `StartFrame`/`EndFrame`/`CancelFrame` 硬编码为"无条件放行,不受 filter_system_frames 影响"。**这意味着 switcher 里的全部候选服务(不论是否 active)都会在 pipeline 启动时收到 StartFrame 并建立连接,pipeline 结束时一起收到 EndFrame/CancelFrame 断开——不是按需懒连接。** 对"一个 switcher 里塞多个候选服务"的设计有直接的连接数/费用含义(源码 `service_switcher.py:303-321` 的 `push_frame` docstring 也印证:"StartFrame causes the service to generate ServiceMetadataFrame"这一现象正是因为所有 filter 都放行了 StartFrame)。

**约束与已知坑**(逐条标注状态):
1. **已修复**——`ServiceUpdateSettingsFrame` 默认只送达 active 服务。GitHub issue `pipecat-ai/pipecat#5150`(closed,state_reason=completed,2026-07-31)报告:failover 后新 active LLM 未同步 turn-completion 配置,导致用户轮次判定永久失效退化为超时兜底;根因是设置类 frame 走与普通帧一样的 active-only 过滤。修复 PR `#5155`("Deliver settings updates to inactive services behind a ServiceSwitcher")落地为现在能看到的 `ServiceUpdateSettingsFrame.reach_inactive_services: bool`(`frames.py:2109`)——**必须显式传 `reach_inactive_services=True`** 才能让设置更新(含 `system_instruction`)同时下发给所有候选服务,默认仍是只有 active 收到;测试覆盖见 `tests/test_service_switcher.py:635-800`(`test_settings_update_reaches_every_service`、`test_inactive_service_is_configured_before_failover` 等)。**设计含义:场景装配层若要保证"不管当前哪个服务 active,身份/配置都保持一致",在推送设置更新时必须显式带上该 flag,否则只在当前用户看到的那一路生效,切走的候选服务默认停留旧配置。**
2. **已修复**——`ServiceSwitcherStrategyFailover` 长通话下错误归因不准,issue `#4139`(closed/completed):把某一个服务(如 ElevenLabs TTS)的 WebSocket 断连误判为多个服务同时报错。PR `#4149` 修复后,现源码 `ServiceSwitcher.push_frame`(`service_switcher.py:341-343`)显式判断 `frame.processor == self.strategy.active_service` 才转发给 `strategy.handle_error`,只有真正来自 active 服务的错误才会触发 failover。当前 clone 已是修复后版本。
3. **仍开放,低概率 edge case**——issue `#4834`(open,标签 `code-scan-issue-found`,自动代码扫描发现,截至 2026-08-10 无人评论跟进):`ParallelPipeline`(`ServiceSwitcher` 的父类)在同步 `StartFrame/EndFrame/CancelFrame` 时,若某分支内部处理器**自行**(而非由外部驱动)推送生命周期帧,其帧 id 不在 `_frame_counter` 里,会绕过同步机制直接放行并把 `_synchronizing` 清 False,可能导致 `_buffered_frames` 提前 flush、`on_pipeline_finished` 被多次触发。触发条件是"分支内部处理器自主推送生命周期帧",常规的 `ManuallySwitchServiceFrame` 手动切换路径不会触发此问题,记为已知但优先级低的坑。
4. **文档与源码不一致**(源码交叉核验发现,未见 issue 跟踪,建议按源码为准)——`on_service_switched` 事件是在 `ServiceSwitcherStrategy.__init__` 里 `_register_event_handler("on_service_switched")`(`service_switcher.py:65`),挂在**策略实例**上,不是 `ServiceSwitcher` 本身。官方文档"Constructor"/"Custom Strategies"/`ServiceSwitcherStrategyFailover` 源码 docstring(`service_switcher.py:179`)都用 `@switcher.strategy.event_handler(...)`,但同一文档页"Event Handlers"小节示例写的是 `@switcher.event_handler("on_service_switched")`(直接挂在 switcher 上)。经查 `BaseObject.add_event_handler`(`utils/base_object.py:195-206`):若该事件名未在这个实例上 `_register_event_handler` 过,只会打一条 `logger.warning` 静默丢弃 handler,不抛异常——照抄文档"Event Handlers"小节的写法会导致回调**永远不触发且没有任何报错提示**。设计与实现时一律用 `switcher.strategy.event_handler(...)`。
5. **按设计的静默行为**——`_set_active_if_available`(`service_switcher.py:109-126`):切换目标若不在该 switcher 的 `services` 列表里,请求被静默忽略(返回 `None`),不报错。这是特意为了让同一 pipeline 里多个 switcher 共存、`ManuallySwitchServiceFrame` 广播时互不干扰;但也意味着如果应用层传错了服务实例,不会有任何提示。

**出处一览**(本节)
- 源码:`src/pipecat/pipeline/service_switcher.py`(全文件,行号已标注)、`src/pipecat/pipeline/llm_switcher.py`、`src/pipecat/frames/frames.py:2232-2239,2081-2109`、`src/pipecat/processors/filters/function_filter.py`、`src/pipecat/utils/base_object.py:195-206`、`tests/test_service_switcher.py:635-800`。
- 官方 example:`examples/features/features-service-switcher.py`。
- 官方文档:`https://docs.pipecat.ai/api-reference/server/utilities/service-switchers/service-switcher`、`.../llm-switcher`、`https://docs.pipecat.ai/api-reference/server/frames/control-frames`。
- GitHub issue/PR:`pipecat-ai/pipecat#5150`(+PR#5155)、`#4139`(+PR#4149)、`#4834`(open)。

---

## 2. 运行时切换"身份"与行为的官方机制

**热更 system prompt**:官方**没有**专门的 `LLMSetSystemInstructionFrame` 类(全仓搜索 `frames.py` 未命中)。正确路径是走通用的 Settings 机制:推 `LLMUpdateSettingsFrame(delta=LLMSettings(system_instruction="..."), reach_inactive_services=...)`(`ServiceUpdateSettingsFrame` 的 LLM 特化子类,`frames.py:2112-2116`)。`LLMService._update_settings`(`services/llm_service.py:541-579`)检测到 `system_instruction` 变化后,把新值重新快照为 `_base_system_instruction`,再调 `_compose_system_instruction()`(`llm_service.py:520-539`)——该方法把"用户基础 prompt + 框架内部追加项(轮次完成指令、异步工具取消指令等)"重新拼接,保证热替换不会把框架自己拼进去的指令冲掉。另有 `append_system_instruction()` 方法(`llm_service.py:502-518`)用于**追加**(不是替换)一段持久文本,且是**直接调用服务实例方法**,不是推 frame——这是框架内部组件(如 `UIWorker`)专用的例外,文档/AGENTS.md 强调的"改运行中 pipeline 用推帧不用直接调方法"原则对应用层身份切换仍然适用,场景装配层做整段身份替换应该用 `LLMUpdateSettingsFrame`,不要模仿 `append_system_instruction` 的直接调用方式。
- 若身份切换发生在 `LLMSwitcher` 之上(多 LLM 候选),要覆盖"未来变成 active 的服务"就必须带 `reach_inactive_services=True`(见第 1 节坑 1),否则设置只打在当前 active 的那一个 LLM 上。

**热更工具集**:`LLMSetToolsFrame(tools=...)`(`frames.py:690-702`)——"Used to change the set of tools advertised to the LLM mid-conversation",接受 `ToolsSchema`/函数列表/`FunctionSchema` 列表/provider 原生 dict 列表/`NOT_GIVEN`(清空工具)。`LLMSwitcher.process_frame`(`llm_switcher.py:46-63`)额外监听 `LLMContextFrame`,把 `frame.context.tools` 广播同步到**全体成员 LLM 的 handler 注册表**(不论是否 active),这样 `LLMContext(tools=[...])` 声明的工具即使在 LLM 切换后依然可调用,不需要应用层手动重复注册。

**cascade pipeline 下热切换 LLM/STT/TTS 的注意事项**:
- **上下文保留**:官方两个 example(`features-service-switcher.py:123-137`、`examples/flows/llm_switching.py:191-224`)都是**单一共享的 `LLMContext` / `LLMContextAggregatorPair` 实例包在 switcher 外层**,即 `user_aggregator → llm_switcher → tts` 结构里 context 对象本身不属于任何一个 LLM 实例,LLM 只是"读这个共享 context 做一次推理"的可替换执行体——所以 LLM 切换本身天然不丢上下文,不需要额外搬运逻辑;需要额外处理的只是"哪些 LLM 该看到哪些工具/配置"(上面两条)。
- **STT/TTS 无上下文保留概念**(它们不持有对话历史),需要关注的是**连接生命周期**:见第 1 节"底层实现"——switcher 内的所有候选服务与 pipeline 同生命周期建立/断开连接,不是按需连接。场景装配层如果给每个场景配一套 STT/TTS 候选,注意这些候选会在 pipeline 启动时**全部**建连,而不是切到哪个才连哪个。
- **工具调用内触发切换的时序坑**(官方样例明确标注,非直觉):`examples/flows/llm_switching.py:110-124` 的 `switch_llm()` 工具处理函数里显式写明——不能直接 `worker.queue_frames([ManuallySwitchServiceFrame(...)])`,因为工具调用结果要经过 assistant context aggregator 才能回流给 LLM,若从 worker 顶层入队,切换帧的时序会晚于工具调用结果的产出,导致"结果已经用旧 LLM 处理完了才切"。正确做法是 `await context_aggregator.assistant().push_frame(ManuallySwitchServiceFrame(service=new_llm), FrameDirection.UPSTREAM)`,从聚合器**上游方向**推送,确保切换先于工具结果回流生效。若场景装配层用"LLM 工具调用"驱动场景/服务切换(例如 G3 派活场景里模型自己决定换 profile),这个时序坑必须复现官方这个 upstream-push 写法。

**出处**:`src/pipecat/frames/frames.py:690-702,2112-2116`、`src/pipecat/services/llm_service.py:502-579`、`src/pipecat/pipeline/llm_switcher.py:46-73`、`examples/features/features-service-switcher.py:123-137`、`examples/flows/llm_switching.py:95-224`、文档 `https://docs.pipecat.ai/pipecat/fundamentals/service-settings`、`https://docs.pipecat.ai/api-reference/server/frames/control-frames`。

---

## 3. "场景 profile/配方层"是否有官方 example 或社区成熟实践

**结论:"官方无现成件"仍然成立**(2026-08-10 复核,未被推翻),但比背景假设描述的更精确一层——官方给出的是**两块可以正交拼接的积木**,不是一体化配方:

1. **Pipecat Flows 的 `NodeConfig`**(`pipecat.flows`)管"prompt + 工具集"这半层——`role_message`(持久身份)、`task_messages`(本轮/本节点指令,走 `developer` role)、`functions`、`context_strategy`(节点切换时的上下文处理策略:APPEND / RESET_WITH_SUMMARY 等)。文档:`https://docs.pipecat.ai/api-reference/pipecat-flows/flow-manager`(`set_node_from_config`/`initialize`)。
2. **`LLMSwitcher`** 管"LLM 实例选择"这半层(第 1、2 节)。
3. 官方**专门给出了这两块组合使用的 example**:`examples/flows/llm_switching.py`——每个 `NodeConfig` 里声明一个 `switch_llm` 工具(`llm_switching.py:95-124`),由 Flow 的对话内容驱动模型自己调用工具换 LLM,`create_main_node()`(`llm_switching.py:156-175`)则演示了同一个 node 配方如何根据 `summarize` 参数分叉出不同的 `task_messages`/`context_strategy`,是目前离"场景配方"概念最近的官方参考实现。

**但这个组合明确止步于 LLM**:`NodeConfig` 数据结构本身**不含 STT/TTS 选择字段**(经 context-hub 文档检索 `NodeConfig` 相关页面,以及 `llm_switching.py` 全文通读,均未见 STT/TTS 相关配置项)。如果场景配方要连带切 STT/TTS(即背景里描述的"prompt 身份 + LLM/STT/TTS 服务选择"三元组一体配方),Flows 层不管这一段,需要应用层自己在 node 的工具 handler /`on_node_entered` 之类的钩子里,对着独立的 STT-`ServiceSwitcher`、TTS-`ServiceSwitcher` 再各推一次 `ManuallySwitchServiceFrame`——这一层官方样例未演示,是"场景装配层"设计里真正需要自研的部分。

**社区实践排查**(GitHub 公开检索,`gh search issues/code`,覆盖 pipecat-ai/pipecat 仓库全部 issue 与全站公开代码索引,执行于 2026-08-10):
- 搜索 `ServiceSwitcher`/`LLMSwitcher` 相关 issue 共命中约 15 条,清一色是 bug 报告/修复(已在第 1 节列出关键几条),**没有一条是"场景配方层/多维度联动配置"的功能讨论或 RFC**。
- 分别搜索代码 `ScenarioConfig`、`PersonaConfig pipecat`、`scenario_profile`、`"NodeConfig role_message ServiceSwitcher"` 未命中任何将 pipecat 的 `NodeConfig`/`ServiceSwitcher` 与"场景/人设配方"组合的公开代码库。命中的同名符号(如 `TUM-VT/FleetPy`、`elizaOS/eliza` 等仓库的 `ScenarioConfig`/`scenario_profile`)均与语音/pipecat 场景无关,属于命名巧合。
- **该"未找到"的证据边界**:GitHub 代码搜索只覆盖公开推送、且被 GitHub 索引到的仓库,私有仓库/未推送分支不可见,不能排除有人已经这么做但没开源;结论只能是"未见公开成熟实践",不是"确定不存在"。

**设计参考建议**(供 S2a 架构设计引用,非结论,标注为推测):若要一体化"配方=prompt+LLM+STT+TTS",大概率需要在应用层自建一个"场景配方"数据结构,内部各自持有到 LLM-`LLMSwitcher`、STT-`ServiceSwitcher`、TTS-`ServiceSwitcher` 三个独立 switcher 的目标服务引用,配方切换时依次:①（可选)用 Flows `NodeConfig`/或直接 `LLMUpdateSettingsFrame` 换 prompt;②对三个 switcher 分别推 `ManuallySwitchServiceFrame`;③视需要推 `LLMSetToolsFrame` 换工具集。三步都是各自独立的 frame,不存在"一个 frame 打包三件事"的官方原语。

**出处**:`examples/flows/llm_switching.py`(全文件)、context-hub 文档检索 `flow-manager`/`context-strategies`/`state-management` 相关页(`https://docs.pipecat.ai/api-reference/pipecat-flows/flow-manager` 等,索引时间 2026-08-03)、GitHub 检索:`gh search issues "ServiceSwitcher"`/`"LLMSwitcher"`(2026-08-10 执行,pipecat-ai/pipecat 仓库)、`gh search code "ScenarioConfig"`/`"PersonaConfig pipecat"`/`"scenario_profile"`/`"NodeConfig role_message ServiceSwitcher"`(2026-08-10 执行,全站公开索引)。

---

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
