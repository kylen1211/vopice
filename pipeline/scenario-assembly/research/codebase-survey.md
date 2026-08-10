# scenario-assembly · s1a 现状盘点(codebase-survey)

> 变更:scenario-assembly(L2)。范围:场景装配层(配方 = 场景模板:system prompt 身份 + LLM/STT/TTS 服务选择)+ 运行时 ServiceSwitcher。
> 本文只盘点,不设计、不改代码。所有"实测"条目见末节「已核验事实」(命令 + 输出摘要)。
> 时间基准:2026-08-10。base_commit 8d11dd2。

---

## 1. server 装配现状

### 1.1 bot.py(483 行)——唯一装配路径

模块顶层(D-003 现场):
- `load_dotenv(override=True)` + `cfg = load_config()` 在模块顶层执行(官方脚手架形态)。任何 `import bot` 立刻读真实环境变量,测试只能用 `sys.modules.pop` + `monkeypatch dotenv.load_dotenv` 绕开(`server/tests/conftest.py::bot_module`)。
- `STT_BUILDERS` / `TTS_BUILDERS`:`{provider 名: (Config) -> service}` 两张模块级 dict。每个 builder 内部**惰性 import** 厂商 SDK(`_build_soniox_stt` / `_build_deepgram_stt` / `_build_elevenlabs_tts` / `_build_cartesia_tts`),避免某家 SDK 装不上拖累另一家。
  - 换厂商的既定成本(注释自述):①这里加一行 ②pyproject 加 extras ③改 .env;config.py / 管线 / 测试不动。
  - 构造代码来源约定:照抄 `pipecat/cli/registry/service_metadata.py` 的 `SERVICE_CONFIGS["<name>_stt"]`。

装配函数 `assemble_pipeline(cfg: Config, transport: BaseTransport) -> AssembledPipeline`(bot.py:206-394),是**全项目唯一的 pipeline 组装点**,顺序:
1. `stt = STT_BUILDERS[cfg.stt_provider](cfg)`;`tts = TTS_BUILDERS[cfg.tts_provider](cfg)`(运行时 dict 派发,codegraph 标为 dynamic boundary)。
2. 三个 `OpenAILLMService` 实例,同一网关(`cfg.llm_base_url` / `cfg.llm_api_key`),差别只在 model + system_instruction:
   - `fast_llm`:`model=cfg.llm_model`,`system_instruction=prompts.SYSTEM_PROMPT`
   - `slow_llm`:`name="SlowBrainLLM"`,`model=cfg.slow_llm_model`,`system_instruction=prompts.SLOW_BRAIN_PROMPT`
   - `dispatch_llm`:`name="TaskDispatchLLM"`,`model=cfg.llm_model`,**无 system_instruction**(委派轮由 UIWorker 的 `reply` tool docstring 驱动)
3. `fast_context = LLMContext(tools=[task_dispatch.dispatch_task, task_dispatch.get_task_status])`;`slow_context = LLMContext()`。
4. `stack = task_dispatch.build_dispatch_stack(cfg.openclaw_agent_id, llm=dispatch_llm, cli_override=os.environ.get(ENV_TASK_DISPATCH_CLI))`;`injector = stack.build_injector()`。
5. 两对 `LLMContextAggregatorPair`,均用 `ExternalUserTurnStrategies()`(轮次由公共 VADProcessor/UserTurnProcessor 段统一驱动)。
6. 会话级件:`dual_brain.build_slow_material_filter()`(+`bind_context(slow_context)`)、`build_fast_answer_tap()`、`SentenceAggregator()`、`ProducerProcessor(filter=..., transformer=build_slow_material_transformer(tap), passthrough=True)`、`ConsumerProcessor(producer=...)`、`sentinel.build_sentinel_filter()`、`VADProcessor(SileroVADAnalyzer())`、`UserTurnProcessor()`。
7. 管线形状:`Pipeline([transport.input(), stt, vad_processor, user_turn_processor, ParallelPipeline([快脑分支], [慢脑分支])])`
   - 快脑分支:`injector, consumer, fast_pair.user(), fast_llm, fast_answer_tap, sentinel_filter, tts, transport.output(), fast_pair.assistant()`
   - 慢脑分支:`slow_pair.user(), slow_llm, sentence_aggregator, producer, slow_pair.assistant()`
8. `RTVIObserverParams(ignored_sources=[slow_llm, sentence_aggregator, producer], user_llm_enabled=False)` —— **以对象身份列举**,承载"慢脑绝不泄漏到客户端"契约(R2/§5.1.1)。
9. `PipelineWorker(pipeline, name=MAIN_WORKER_NAME, params=PipelineParams(enable_metrics=True, enable_usage_metrics=True), rtvi_observer_params=..., app_resources=stack.app_resources)`,再挂 `on_pipeline_error` = `make_pipeline_error_handler(slow_llm, slow_material_filter)`(以 `frame.processor is slow_llm` 做错误归因)。
10. 返回 `AssembledPipeline` —— 16 字段的**结构性句柄袋**(dataclass,非 frozen),存在理由就是给结构性测试断言。

`run_bot(transport, runner_args)`:调 `assemble_pipeline` → 挂 `worker.rtvi.event_handler("on_client_ready")`(`seed_greeting_messages` + `LLMRunFrame`)+ transport 连接/断开处理 → `worker.app_resources.main_worker = worker` 回填 → `runner.add_workers(worker, dispatch_worker, exec_worker)` → `runner.run()`。
`bot(runner_args)`:`transport_params = {"webrtc": TransportParams, "eval": EvalTransportParams}` → `create_transport` → `run_bot`。

### 1.2 config.py(171 行)——provider 层现状

- `Config` 是 `@dataclass(frozen=True)`,13 字段;`__repr__` 对 `*_api_key` 脱敏。
- `load_config()` 一次性 fail-fast,列全部缺失/占位符项(`CHANGE_ME_` 前缀视同缺失)。
- **provider 驱动方式**:`STT_PROVIDER` / `TTS_PROVIDER` 环境变量 → `_validate_provider(env, default, whitelist)` 白名单校验(默认 soniox / elevenlabs)→ 用选中的 provider 从 `_STT_PROVIDER_REQUIRED_ENV` / `_TTS_PROVIDER_REQUIRED_ENV` 取该厂商的必需 key 表,合并进 `_BASE_REQUIRED_ENV_TO_FIELD` 再校验。**未选中的厂商 key 不强制配置**。
- 各厂商 key 落到**同一组中立字段名**(`stt_api_key` / `tts_api_key` / `tts_voice` / `tts_model`),所以 bot.py 的 builder 不关心选中的是哪家,只读 Config 字段。
- 基础必需项 5 个:`LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`/`SLOW_LLM_MODEL`/`OPENCLAW_AGENT_ID`;可选项 `SONIOX_MODEL`(默认 `stt-rt-v5`)。
- **SCENARIO 现状**:`_ALLOWED_SCENARIO = "voice_chat"` 白名单,`_PHASE2_SCENARIOS = {"interview","translate","companion","butler"}` 显式拒绝并给"属后续阶段"提示;未知值也拒绝。`Config.scenario` 字段**除校验外全项目零消费点**(grep 实测,§已核验事实⑧)——即"场景"目前只是一个门禁枚举,不驱动任何装配差异。这是本变更要填的洞。

### 1.3 prompts.py(100 行)——身份/prompt 管理现状

全部是**模块级常量**,无函数、无参数化入口:
- 快脑身份串由 5 段拼接:`SYSTEM_PROMPT = OFFICIAL_SECTION + CAPABILITY_BOUNDARY_SECTION + LANGUAGE_SECTION + CONCISENESS_SECTION + DUAL_BRAIN_SECTION`(`\n\n` 分隔)。这个**顺序被 test_prompts.py 断言**。
- `SLOW_BRAIN_PROMPT`:独立慢脑 system prompt,不进快脑拼装。
- 四个注入模板常量:`INJECT_POINT_TEMPLATE` / `INJECT_DONE_TEMPLATE` / `INJECT_DONE_WITH_REMINDER_TEMPLATE` / `INJECT_TASK_TERMINAL_TEMPLATE`,被声明为"唯一事实源,禁止内联字面串"。
- **关键约束(装配层设计必须面对)**:身份语义(OFFICIAL/LANGUAGE/CONCISENESS)与协议语义(CAPABILITY_BOUNDARY 能力边界、DUAL_BRAIN_SECTION 慢脑素材消化协议)**混在同一个字符串里**。场景配方若"整串换掉 SYSTEM_PROMPT",会连带丢掉双脑协议段与能力边界段,直接击穿 R4/双脑既有 eval 用例(`evals/r4_*.yaml`、`dual_brain_*.yaml`)。可换的粒度必须在设计段定清楚。

### 1.4 dual_brain / task_dispatch 的接入方式

统一走 **"会话级 `build_*` 工厂"约定(R5)**,模块级单例仅供测试:
- `dual_brain.build_slow_material_filter()` / `build_fast_answer_tap()` / `build_slow_material_transformer(tap=None)`
- `task_dispatch.build_dispatch_registry()`、`task_dispatch.build_dispatch_stack(agent_id, llm=..., cli_override=...) -> DispatchStack`(暴露 `app_resources` / `dispatch_worker` / `exec_worker` / `registry` / `build_injector()`)
- 接入点全在 `assemble_pipeline` 内:dual_brain 的件作为 Producer/Consumer 挂在两条分支上;task_dispatch 的 injector 挂在快脑分支头部,两个 tool 挂 `fast_context.tools`,两个额外 worker 由 `run_bot` 交给同一个 `WorkerRunner`。
- 跨 worker 句柄靠 `PipelineWorker(app_resources=...)` + `run_bot` 里回填 `main_worker`,不用全局。

---

## 2. 可复用件与既有约定

### 2.1 旧库对应物(`~/git/voice-translate-v2`,只读)

| 旧库件 | 形态 | 本仓是否已有对应物 |
|---|---|---|
| `va/services/llm_factory.py` | `build_slow_llm(provider, model)` 的 if/elif provider 枚举工厂,顶部集中 import 三家 SDK | **已有更强对应物**:`STT_BUILDERS`/`TTS_BUILDERS` dict 派发 + 惰性 import + config 条件必需校验。不必照搬,本仓已是同款模式的升级版 |
| `va/scenarios/`(`base.py` + 5 个配方 + `__init__.RECIPES`) | `Recipe` Protocol(`id`/`label`/`build()`)、`RecipeDeps`(frozen dataclass,每次 start 新构一份注入)、`BuiltScenario`(task + shutdown_hooks)、`RECIPES` 显式注册表作为 list_scenarios 唯一数据源 | **本仓无对应物**——这正是本变更要建的层 |
| import-linter 分层合同(叶子层禁反依赖装配层) | 工具强约束 | 本仓无分层校验工具;当前 `dual_brain`/`sentinel`/`task_dispatch` 事实上是叶子(不 import bot),靠约定维持 |

旧库配方层里值得沿用的三点约定(仅记录,不做设计):显式注册表作唯一枚举源;配方 id 与配置节同名;装配层单向依赖叶子层。

### 2.2 本仓既有约定(新代码须遵守)

- 会话级 `build_*` 工厂,禁模块级单例(R5)。
- provider 新增 = builder 字典加一行 + config 条件必需表加一项 + `.env.example` 注释 + 单测,**不动管线**。
- 中立字段名收敛厂商差异(`stt_api_key` 等),装配点不感知厂商。
- prompt 模板常量唯一事实源,禁内联字面串。
- 官方脚手架结构不动(`server/`、`client/`、`evals/`、`tests/`、`scripts/`);新增目录须在 S2a 显式批准(CLAUDE.md 项目纪律)。
- `.env.example` 与 `server/tests/conftest.py::_FAKE_REQUIRED_ENV` 是**必需项的两处镜像**,改必需项须同步(T-5 曾漏改一处,由 T-6 补)。

---

## 3. 装配层与 ServiceSwitcher 的候选插入点与影响面

### 3.1 候选插入点

| 位置 | 现状 | 装配层可插入什么 |
|---|---|---|
| `config.py::load_config` | SCENARIO 白名单只放行 `voice_chat`,字段无消费点 | 场景枚举 → 配方 id 的入口;或改由配方注册表反向提供白名单 |
| `bot.py::STT_BUILDERS/TTS_BUILDERS` | provider→builder 两张 dict | 配方指定 provider 时的复用点;ServiceSwitcher 需要**多实例并存**(一次构造 N 家),现状是一次只构一家 |
| `bot.py::assemble_pipeline` | 全项目唯一装配点,一次性构造全部对象 | 配方注入点(prompt/model/provider 选择)+ switcher 包装点 |
| `prompts.py` | 5 段常量拼接的单一 SYSTEM_PROMPT | 身份段可替换 / 协议段恒定的分层点 |
| `PipelineWorker.rtvi` 的 `on_client_message` 事件 | 1.6.0 已注册该事件(实测),客户端目前**未使用**(`client/src` grep 无 server-message/scenario 相关代码) | 运行时"切场景/切服务"的客户端→bot 控制面现成通道 |

### 3.2 影响面(codegraph 爆炸半径 + grep)

- `assemble_pipeline`:生产调用点仅 `run_bot` 1 处;测试调用点 8 处(全在 `tests/test_dual_brain.py` U 组结构性断言)。改管线形状 → 直接牵动这 8 处。
- `STT_BUILDERS`/`TTS_BUILDERS`:`tests/test_bot.py` 4 个用例直接按名索引调用。
- `Config`:6 个调用方(`bot.py`、`judge_factory.py`、`config.py` 自身、`evals/fault_run/bot.py`);测试 `test_config.py`(13 用例)+ `test_bot.py`。
- `server/evals/fault_run/bot.py` 是指向 `../../bot.py` 的**符号链接**(实测),不是副本 → 不存在双份漂移;但同目录 `.env → ../fault.env` 会换掉环境变量集。
- **RTVI 泄漏契约**:`RTVIObserverParams.ignored_sources` 按对象身份列 `slow_llm`/`sentence_aggregator`/`producer`。若慢脑 LLM 被包进 switcher,ignored_sources 必须列**每个成员服务实例**而非 switcher 本身,否则慢脑输出可能经 RTVI 泄漏到客户端(R2 契约)。设计段须显式核这一条。
- **ErrorFrame 通路叠加**:`make_pipeline_error_handler` 以 `frame.processor is slow_llm` 归因;`ServiceSwitcher.push_frame` 对 `非 fatal 且 processor == active_service` 的 ErrorFrame 调 `strategy.handle_error(...)` 后**仍继续向上传播**(源码已读),两者可共存,但 Failover 策略会静默改变 active service,和"慢脑失败 → 面板消息"的语义要在设计段界定谁负责什么。
- **嵌套 ParallelPipeline**:`ServiceSwitcher` 本身就是 `ParallelPipeline` 子类。本仓管线已有一层 `ParallelPipeline`(双脑),把 TTS/LLM switcher 放进快脑分支 = 嵌套并行。构造级实测可通过(见已核验事实⑤),但**运行期行为无证据**,属设计段/spike 要点。
- **D-003 关联**:模块顶层 `cfg = load_config()` 使"按会话/按请求选场景"不成立(场景在 import 期就定死)。若配方需运行时可选,必然触达 D-003 修法边界。
- **D-008 关联**:provider 层已实装但无需求/设计留痕,账单 C2 记载与实际不符。本变更是 debts.md 建议的"下次触达 config.py/bot.py 时补现状说明"的那一次。

---

## 4. 相关测试现状(`server/tests/`)

| 文件 | 与本变更相关的内容 |
|---|---|
| `conftest.py` | `bot_module` fixture:`sys.modules.pop("bot"/"config")` + 中和 `dotenv.load_dotenv` + `_FAKE_REQUIRED_ENV`(10 项假环境变量)。D-003 的现场;新增必需环境变量必须同步这里 |
| `test_bot.py` | 4 个 builder 用例:soniox 语言提示 = ZH、elevenlabs voice 取自 config、deepgram language+smart_format、cartesia voice+language。手法是"用假 Config 调 builder,断言构造出的 service 实例属性",不碰模块全局 |
| `test_config.py` | 13 个用例:缺失项全量列举、占位符/空串视同缺失、repr 脱敏、2 期 scenario 拒绝 + 未知 scenario 拒绝、必需项集合快照、provider 白名单、deepgram/cartesia 条件必需、两家同时选中、frozen 断言 |
| `test_dual_brain.py` | U 组结构性装配断言(8 处调 `assemble_pipeline`),外加"每次调用返回全新实例"的会话隔离断言 |
| `test_prompts.py` | 6 个 prompt 契约用例,含 **SYSTEM_PROMPT 五段顺序断言**、慢脑约束句、∅ 哨兵符、负向锚"问题#" |
| `test_sentinel.py` / `test_sentinel_filter.py` | 哨兵过滤,与装配层无直接耦合 |
| `test_task_dispatch.py` | **当前 collection 失败**(见下) |

**基线破损(既有,非本变更引入)**:`uv run pytest -q` 整套在 collection 阶段就中断——`tests/test_task_dispatch.py` 在 import 期读 `pipeline/task-dispatch/baseline/mcp-event-sample.json`,该目录已被 commit 8d11dd2("清理 task-dispatch 流程过程产物")删除。排除该文件后 53 passed。本变更开工前需先由主会话定夺修法(恢复 fixture / 内联样本 / 改读路径)。

eval 侧(`server/evals/`,22 个 yaml):`r4_*.yaml` 锚定能力边界段语义,`dual_brain_*.yaml` 锚定慢脑素材不泄漏 + 注入模板痕迹,`dispatch_*.yaml` 锚定派活。**任何对 SYSTEM_PROMPT 分段的改动都会打到 r4_* 与 dual_brain_* 这两组**。

---

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
