# scenario-assembly · design.md

> 变更:scenario-assembly(L2)。s2a 产出,时间基准 2026-08-10,base_commit 8d11dd2。
> 上游:`prd.md`(冻结,12 条 FR)、`research/{codebase-survey,facts,external-research,tutor-persona-references}.md`。无 ui-spec(本次无 UI)。
> 下游:backend-dev(照本文 + `contract/cases.md` 实现)、qa-tester(照 `contract/cases.md` 验收)、code-reviewer。
> 接口契约唯一事实源 = `pipeline/scenario-assembly/contract/cases.md`;本文不复写其中任何定义。

---

## 现状盘点

### 0. Preflight 证据块(P6/P14:设计依赖的每条外部事实,均为本轮当场实测)

| # | 结论(设计据此) | 命令 | 关键输出 |
|---|---|---|---|
| E-1 | **pipecat dev runner 是"单进程 · 多会话"**:模块只 import 一次,每个 WebRTC offer 在**同一进程**内起一次 `bot(runner_args)`,并发会话默认放行(`ConnectionMode.MULTIPLE`) | 桩 bot(模块级打 `MODULE-LOAD`,`bot()` 内打 `BOT-CALL`)`uv run python stubbot.py -t webrtc --port 7899`,另起 aiortc 客户端并发发两个 `/api/offer` | `MODULE-LOAD pid=846632`(仅 1 行);`BOT-CALL pid=846632 session=ce51f3c9…`、`BOT-CALL pid=846632 session=08732330…`(同 pid,两个 session_id);两次 `status 200` |
| E-2 | 上述行为的源码落点:`/api/offer` → `background_tasks.add_task(bot_module.bot, runner_args)`;`_get_bot_module()` 取 `sys.modules["__main__"]`(不重复 import);eval 通道是 `await bot_module.bot(runner_args)` 一次 | 读 `server/.venv/.../pipecat/runner/run.py:929-939, 459-476, 1455`;`.../smallwebrtc/request_handler.py:100-118, 189-220` | `connection_mode: ConnectionMode = ConnectionMode.MULTIPLE`(默认多连接) |
| E-3 | **`load_dotenv(override=True)` 在函数体内调用与在模块顶层调用,`find_dotenv()` 解析结果一致**,且对"相对路径调用的符号链接脚本"仍解析到脚本自身目录的 `.env`(= `evals/fault_run` 机制不受影响) | 构造 `sub/bot.py -> ../real_bot.py`、`sub/.env -> ../alt.env`,`cd sub && python bot.py` | `MODULE find_dotenv() = …/sub/.env`、`FUNC find_dotenv() = …/sub/.env`,两处 `TPLVAL=from_alt_env` |
| E-4 | **同进程内二次 `load_dotenv(override=True)` 能读到 `.env` 的最新内容**(会话级重读成立) | 同一进程内写 `.env`→load→改写 `.env`→再 load | `session1 TPLVAL = session_A` / `session2 TPLVAL = session_B` |
| E-5 | 语音安全护栏句(`"...spoken aloud, so avoid emojis, bullet points..."`)**只存在于 `OFFICIAL_SECTION` 内**,不在 `LANGUAGE_SECTION`/`CONCISENESS_SECTION` | `grep -rn "spoken aloud" --include=*.py server` | 唯一命中 `server/prompts.py:13` |
| E-6 | 测试基线 = 70 passed(FR-9 起点) | `cd server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run pytest -q` | `70 passed, 37 warnings in 5.13s` |

> E-1/E-2 合并回答 PRD 开放问题①:**部署拓扑就是"一个长驻进程服务多个会话"**,不是"每会话一进程"。裁决见 ADR-1。

### 1. 相关模块与既有约定(来源 `research/codebase-survey.md`,本轮已复核)

- `server/bot.py`:模块顶层 `load_dotenv(override=True)` + `cfg = load_config()`(D-003 现场);`STT_BUILDERS`/`TTS_BUILDERS` 两张 provider→构造器 dict(惰性 import);`assemble_pipeline(cfg, transport)` 是全项目唯一装配点,返回 16 字段 `AssembledPipeline`;`run_bot` 只被 `bot()` 调用(grep 实测,无第二调用方)。
- `server/config.py`:`Config` frozen dataclass;`load_config()` 一次性 fail-fast 列全部缺失;`SCENARIO` 白名单只放行 `voice_chat`,`_PHASE2_SCENARIOS` 显式拒绝;provider 白名单 + **条件必需**(未选中的厂商 key 不强制配置);各厂商落同一组中立字段名。
- `server/prompts.py`:纯常量模块(无 import、无副作用);`SYSTEM_PROMPT` = 五段 `\n\n` 拼接,顺序被 `test_prompts.py::test_system_prompt_assembly_order` 断言。
- 既有约定(新代码必须遵守):会话级 `build_*` 工厂禁模块级单例(R5);provider 新增 = builder 加一行 + 条件必需表加一项 + `.env.example` + 单测,**不动管线**;prompt 常量唯一事实源禁内联字面串;官方脚手架目录结构不动;`.env.example` 与 `tests/conftest.py::_FAKE_REQUIRED_ENV` 是必需项的两处镜像,改必需项必须同步。
- 可复用件:`STT_BUILDERS`/`TTS_BUILDERS`(模板选 provider 时直接复用,不新建工厂)、`_validate_provider` 白名单校验、`build_*` 会话级工厂族、`evals/fault_run` 的"符号链接 + 独立 .env"启动画像。

### 2. 影响面(codegraph 爆炸半径,本轮复核)

| 符号/文件 | 生产调用方 | 测试调用方 | 本次触达 |
|---|---|---|---|
| `assemble_pipeline` | `run_bot` ×1 | `test_dual_brain.py` ×6(全部 `bot_module.cfg`) | 函数体改造;签名不变 |
| `STT_BUILDERS`/`TTS_BUILDERS` | `assemble_pipeline` | `test_bot.py` ×4 | 不改(模板经 Config 生效字段驱动) |
| `Config`/`load_config` | `bot.py`、`judge_factory.py`、`evals/fault_run/bot.py`(符号链接,同一文件) | `test_config.py` ×13、`test_bot.py::_make_config` | 新增字段 + 条件必需 + 模板合并 |
| `prompts.SYSTEM_PROMPT` | `assemble_pipeline` ×1 | `test_prompts.py` ×6 | 生产改走组合函数;常量保留为派生兼容别名 |
| `prompts.INJECT_*` | `dual_brain`/`task_dispatch` | eval 负向锚 | **不动** |
| `evals/r4_*.yaml`、`dual_brain_*.yaml`、`dispatch_*.yaml` | — | — | 文件不改,只改运行画像(见 §测试策略) |

---

## 方案

### 总览:三层,一条装配链路

```
scenarios.py(叶子·纯数据+纯函数)      模板注册表 TEMPLATES + build_system_prompt()
        ↑ import                        ↑ import(取身份段常量)
config.py(校验层)  ──────────────→  prompts.py(叶子·纯常量)
        ↑ import
bot.py(装配层)   bot() → 会话级 load_config() → assemble_pipeline(cfg, transport)
```

依赖方向单向向下:`bot → config → scenarios → prompts`。`scenarios`/`prompts` 不 import 任何框架、传输层、config,可脱离 pipecat 单测(hard rule 6)。

### ADR-1 · 装配时机:会话级重读配置,模块级保留为启动预检(回答开放问题①)

- **背景**:E-1/E-2 实测确认单进程多会话。模块顶层 `cfg = load_config()` 只跑一次 ⇒ 若不动,同进程内所有会话共享同一次模板选择,"结束会话 → 换模板 → 重开会话"必须重启进程,与用户拍板的心智模型不符。E-4 实测确认同进程二次 `load_dotenv(override=True)` 能读到 `.env` 最新内容,E-3 确认把它挪进函数体不改变 `find_dotenv()` 的解析语义(`evals/fault_run` 机制不受影响)。
- **决定**:
  1. **保留**模块顶层 `load_dotenv(override=True)` + `cfg = load_config()`,职责收窄为**启动预检**(进程起不来就报错,保住今天的"启动即 fail-fast")与既有测试的 Config 取值口。
  2. **新增**会话级解析:`bot(runner_args)` 内以**紧邻两行、其间不得有 `await`** 的方式执行 `load_dotenv(override=True)` + `session_cfg = load_config()`,再 `run_bot(transport, runner_args, session_cfg)` → `assemble_pipeline(session_cfg, transport)`。
  3. 装配起点打一行 INFO:`[scenario] template=<id> stt=<provider>/<model> tts=<provider>/<voice> fast_model=<model> dual_brain=<on|off>`,作为"这次会话到底用了哪个模板"的现场证据(FR-3/FR-8 的运行期可观测锚)。
- **为什么"其间不得有 await"是硬约束**:`load_dotenv(override=True)` 改的是进程级 `os.environ`。asyncio 单线程事件循环下,两行同步代码之间没有让出点 ⇒ 另一个会话不可能插进来读到半更新的环境。一旦有人在中间插入 `await`,并发会话的模板就可能串台。该约束写进 `contract/cases.md` §0.3,并由代码注释固化。
- **代价**:①`.env` 是进程级共享输入,**并发**会话之间做不到"各自锁定不同 .env 内容"的强隔离——只能保证每个会话在自己启动的那一瞬把配置快照成 frozen `Config`(FR-3 判据 1 由此满足);②同一份配置在进程内被读两次(启动一次、每会话一次),启动快照与会话快照可能不同,故一切装配只许用会话快照,模块级 `cfg` 生产路径**零消费**(评审可机械核对:`assemble_pipeline` 的实参不得是模块级 `cfg`);③D-003 未清偿,但边界比现状更清楚(见 ADR-6)。
- **被否 A**:维持模块级 `cfg` 不动(最小改动)。否因:换模板必须重启进程,与用户拍板的"结束会话→重开会话"不符;PRD 开放问题①明写这条路"代价显著上升"要回来改 FR-3——本方案避免了改 PRD。
- **被否 B**:每会话一进程(拓扑隔离)。否因:与 pipecat dev runner 实测拓扑相悖,要自建进程管理/端口分配,击穿"官方脚手架结构不动"纪律,且难逆。
- **被否 C**:模板选择走 `runner_args.body`(`/api/offer` 的 `request_data` 是现成的每会话通道,源码实测存在)。否因:PRD 非目标明写"本次不新增客户端 UI,模板选择留在服务端配置层";但这条通道**存在且免费**,是未来桌面客户端做模板选择器的落点,记入"演化路径"。

### ADR-2 · 模板注册表:新增 `server/scenarios.py`(单文件,不新建目录)

- **决定**:新增叶子模块 `server/scenarios.py`,含三件:`ServiceChoice`(frozen,全字段可选=覆盖项)、`ScenarioTemplate`(frozen:`id`/`label`/`identity_section`/`services`)、`TEMPLATES` 显式注册表(dict,唯一数据源)+ `get_template()`/`template_ids()`。字段与不变式的完整定义见 `contract/cases.md` §0.1/§0.2。
- **理由**:呼应旧库 `va/scenarios/RECIPES` 的既有约定(显式注册表作唯一枚举源);frozen dataclass 让"会话内模板不可变"成为结构事实而非纪律;放 `server/` 根下单文件,不新建目录(CLAUDE.md 纪律)。
- **代价**:模板集合改动需改代码并重启进程(不支持热加载)。模板数量在个位数、且每个模板都要配套 prompt 文案与 eval,这个代价换来的是启动期就能查出的类型/白名单错误。
- **被否**:模板外置成 YAML/JSON 配置文件。否因:失去 import 期 fail-fast(错误推迟到运行时,正是 P25/P28 的形状);多一层文件路径依赖与解析失败路径(P43:默认路径写错会表现成"能力为零"而非"配置错误");本期没有"用户自助新增模板"的需求(客户端 UI 是非目标)。反证条件:若未来要让用户在客户端里自定义模板,再评估外置。

### ADR-3 · prompt 分段:护栏句从身份段中提取(**推翻 PRD FR-4 的一处事实前提**)

- **背景(E-5 实测)**:PRD FR-4 的产品决策写"语音安全护栏句就位于 `LANGUAGE_SECTION`/`CONCISENESS_SECTION` 两段之一",据此把这两段划为不可覆盖。**实测:护栏句在 `OFFICIAL_SECTION` 里**,而 `OFFICIAL_SECTION` 恰恰是 FR-4 允许模板整段替换的身份段。照 PRD 字面实现 ⇒ 模板作者写新人设时护栏句直接消失,FR-4 想防的事故反而必然发生(AGENTS.md §4 明写"重写 prompt 时必须把这句带过去")。
- **决定**:把 `OFFICIAL_SECTION` 拆成两段常量——`IDENTITY_DEFAULT_SECTION`(人设,模板可覆盖)与 `VOICE_SAFETY_SECTION`(护栏句,**模板不可覆盖**,由组合函数无条件注入,位置紧随身份段之后)。组合结果的段序:`身份 → 语音安全 → 能力边界 → 语言 → 简洁 → [双脑]`。
- **兼容处置(把 FR-9 的代价压到零)**:`prompts.py` 保留两个**派生**常量——`OFFICIAL_SECTION = f"{IDENTITY_DEFAULT_SECTION}\n\n{VOICE_SAFETY_SECTION}"`、`SYSTEM_PROMPT`(默认模板 + 双脑开启态的组合快照)。因为两段在默认组合里相邻,`test_prompts.py` 的五段顺序断言与其余 5 个用例**逐字不改即通过**。另加一条防漂移断言:`SYSTEM_PROMPT == scenarios.build_system_prompt(TEMPLATES["voice_chat"], dual_brain_enabled=True)`(P36:两处同值不许各自硬编码,必须由测试绑死)。
- **代价**:默认 system_instruction 的文本发生**语义中性但非逐字**的变化(护栏句由"身份段第 2 句"变成"独立第 2 段",段间多一个 `\n\n`)。因此 FR-9 的"行为等价"必须由 `r4_*`/`dual_brain_*` eval 复跑来证明,不能只靠单测(判据见 `contract/cases.md` SA-15)。
- **被否**:护栏句留在身份段内,靠"文案评审清单"保证模板作者不漏。否因:纯纪律型防护,正是坑库 P7(规则存在≠规则被执行);而模板数量会随路线图增长(同传/面试),每加一个都要人肉复核一次。

### ADR-4 · FR-4 的可寻址结构与"未来升级改动面"自证

- 组合函数落 `scenarios.py`(不落 `prompts.py`,否则 `prompts` 要 import `scenarios` 形成环):
  `build_system_prompt(template: ScenarioTemplate, *, dual_brain_enabled: bool) -> str`,内部按段列表拼接,每段取值都是一次独立的"模板值优先、否则默认常量"判断。
- **FR-4 设计约束自证**(把 `LANGUAGE_SECTION`/`CONCISENESS_SECTION` 升级为"模板可覆盖但强制保留护栏句"时的改动面):
  ① `ServiceChoice` 同级新增可选字段 `language_section`/`conciseness_section`(注册表);② `build_system_prompt` 里这两段的取值改成 `template.language_section or LANGUAGE_SECTION`(组合函数,护栏句因为是独立段、无条件注入,天然被保留);③ `tests/test_scenarios.py` 加校验用例。
  **不触达**:`bot.py`(调用点签名不变,模板对象整体传入)、管线装配顺序、STT/TTS/LLM 服务选择这条正交轴。—— 满足 PRD FR-4 的三处收敛判据。

### ADR-5 · 模板与环境变量的优先级:模板 > 环境变量 > 内置默认

- **决定**:`ScenarioTemplate.services` 的每个字段都是**可选覆盖**;`load_config()` 在选定模板后计算"生效值"并写进 `Config` 的既有中立字段(`stt_provider`/`stt_model`/`tts_provider`/`tts_voice`/`tts_model`),再据**生效 provider** 取条件必需 key 表做校验。`bot.py` 的 builder 因此**完全不感知模板**(既有"中立字段名收敛厂商差异"约定不变)。
- **快脑模型单列字段**:新增 `Config.fast_llm_model`(= 模板覆盖值 or `LLM_MODEL`);`Config.llm_model` 保持"网关默认模型"语义,`dispatch_llm` 继续用它。理由:`dispatch_llm` 的注释明写它要用"快脑同款(快)模型"而非慢脑模型,但那是"要快",不是"要跟着人设走";若合并成一个字段,换个陪练模板会静默把派活委派轮的模型也换掉——这是 P50 形状的越界副作用。默认模板下两者相等。
- **凭证必需性不因模板放松**:模板覆盖 `tts_voice`/`tts_model` 时,对应厂商的环境变量**仍在必需集内**(只是取值以模板为准)。理由:不为了少配一个变量而削弱 fail-fast;模板换 provider 时,新 provider 的凭证进入必需集(FR-11 的正向路径)。
- **代价**:`STT_PROVIDER=deepgram` 这类环境变量在"模板声明了 provider"时会被静默忽略。缓解:装配起点的 INFO 行打印**生效**组合(ADR-1 第 3 点),现场一眼可见谁赢了。

### ADR-6 · 慢脑开关(FR-12)的装配分支

- **配置**:新增可选环境变量 `DUAL_BRAIN_ENABLED`,**默认关闭**;取值解析白名单化(`1/true/yes/on` ↔ `0/false/no/off/空`,其余值 `ConfigError` fail-fast,不静默当假);落 `Config.dual_brain_enabled: bool`。`SLOW_LLM_MODEL` 由**恒定必需**改为**按开关条件必需**(复用既有 provider 条件必需机制),字段类型 `str | None`。
- **关闭态装配**(逐项,判据见 `contract/cases.md` §0.4):
  - 不构造:`slow_llm` / `slow_context` / `slow_pair` / `slow_material_filter` / `sentence_aggregator` / `ProducerProcessor` / `ConsumerProcessor` / `_FastAnswerTap`(它只为 D-005 存在,D-005 是双脑专属现象)。`AssembledPipeline` 对应字段为 `None`。
  - 管线形状退化为**单链**(无 `ParallelPipeline`):`transport.input() → stt → vad → user_turn → injector → fast_pair.user() → fast_llm → sentinel_filter → tts → transport.output() → fast_pair.assistant()`。
  - `build_system_prompt(..., dual_brain_enabled=False)` ⇒ `DUAL_BRAIN_SECTION` 不出现。
  - **保留** `sentinel_filter`:它是"首帧以 ∅ 开头就整轮静音"的防御闸,关闭态下快脑没有 ∅ 指令、天然走不到静音分支;保留可让快脑分支形状在两态间只差双脑件,少一个条件分支。
  - **保留** `user_llm_enabled=False`:该项挡的是**派活回流注入模板**经 `user-llm-text` 泄漏(第二条泄漏路径),与双脑是否挂载无关。`ignored_sources` 在关闭态为空列表。
  - `make_pipeline_error_handler` 签名放宽为 `(slow_llm: OpenAILLMService | None, slow_material_filter: … | None)`,归因判断改为 `slow_llm is not None and frame.processor is slow_llm`。**这是本条最容易踩的坑**:直接传 `None` 而不加前半句,`ErrorFrame(processor=None)` 会被误判成 `slow-failed` 并向客户端推面板消息(P50/P55 形状),`contract/cases.md` SA-14 专测此点。
  - `seed_greeting_messages(fast_context, slow_context: LLMContext | None)`:`None` 时只种快脑那条。
- **开启态**:与 2026-08-10 基线逐件等价(慢脑分支、`DUAL_BRAIN_SECTION`、`SLOW_LLM_MODEL` 必需性)。
- **被否**:只摘慢脑分支、`DUAL_BRAIN_SECTION` 照旧注入(改动更小)。否因:prompt 会指示快脑"没有可补充时只输出 ∅",而关闭态没有任何素材来源,一旦快脑照做,`sentinel_filter` 会把整轮静音 ⇒ 用户听到**空白应答**,直接违反 FR-12 判据三。

### ADR-7 · FR-3 第三条:运行期"切模板"请求的处置 = 无接收端

- **决定**:选择 PRD 给的"忽略"分支,并且用**结构性**方式实现:`bot.py` 不注册 `rtvi.event_handler("on_client_message")`(今天也没有),因此运行期任何"切模板"性质的客户端消息在服务端没有接收端,连"部分字段已切"的中间状态都无从产生。会话内的模板/配置全部是 frozen 快照。
- **可机械核对**:`grep -q "on_client_message" server/bot.py` 必须无命中(`contract/cases.md` SA-08a)。
- **代价**:客户端发这类消息不会收到"不支持"的显式反馈。PRD 允许二选一,选忽略是零代码零风险;未来做客户端模板选择器时(ADR-1 被否 C 的通道),再补显式反馈。

---

## 接口契约

- **档位:`cases`**(可执行验收用例清单),与 s0 预判**一致**,`ledger.md::contract_tier = cases` 无需改判。
- **理由**:本变更零 HTTP 接口(排除 openapi)、零新增 CLI 命令(排除 cli)、零 UI(排除 ui,PRD 非目标已明写不动客户端)。对外可见面是"环境变量 → 模板 → 装配出的服务对象与 prompt"这条内部装配链路,其契约只能以"跑一遍装配、读真实构造对象"的可执行用例来固化——正是 cases 档的适用面,也正面回应 FR-8 与坑库 P55(不接受"单测直接构造 dataclass 传参绕过装配层"当唯一证据)。
- **唯一事实源**:`pipeline/scenario-assembly/contract/cases.md`,含:
  - §0.1 模板注册表数据结构与不变式(`ServiceChoice`/`ScenarioTemplate`/`TEMPLATES`)
  - §0.2 v1 模板集合(`voice_chat` / `english_tutor`)与人设文案硬约束
  - §0.3 配置契约(新增/变更的环境变量、优先级、条件必需、fail-fast 报错形状、会话级重读的原子性约束)
  - §0.4 装配契约(`AssembledPipeline` 字段、两种开关态的管线形状、错误归因、RTVI 泄漏项、观测日志行)
  - §0.5 prompt 组合契约(段列表、顺序、不可覆盖段、组合函数签名)
  - §1 验收用例(SA-01…SA-18,含机器可执行 yaml 块与 manual 项及其理由)
- 本设计文档不内联上述任何定义;两处不一致时以 `contract/cases.md` 为准。

---

## 数据模型

无数据库。本变更的"数据模型"= 进程配置模型 + 内存注册表,全部为 frozen dataclass。字段级定义见 `contract/cases.md` §0.1/§0.3;此处只给**迁移策略**。

### M-1 `Config.slow_llm_model`:恒定必需 → 条件必需(expand-contract)

- expand:新增 `DUAL_BRAIN_ENABLED`(可选,默认 `false`);`slow_llm_model` 类型改 `str | None`,仅当开关开启时进必需集。
- 兼容性:现存 `.env` 里已有的 `SLOW_LLM_MODEL=` **继续有效**(关闭态被读进来但不使用,不报错、不警告——防止"删了才不报错"的伪迁移)。
- contract:无删除动作。`.env.example` 与 `tests/conftest.py::_FAKE_REQUIRED_ENV` 两处镜像同步(既有约定;T-5 曾漏改一处的原地重演风险)。

### M-2 `Config.scenario: str` → `Config.template: ScenarioTemplate`(直接替换,无迁移窗口)

- 依据:grep 实测该字段全项目零消费点(仅 `config.py` 自身赋值;`test_config.py` 只测拒绝路径,不读字段)。无外部消费者 ⇒ 不需要 expand-contract 双写期。
- 环境变量名 `SCENARIO` **不变**(用户 `.env` 零改动),`SCENARIO=voice_chat` 语义不变(=默认模板 id)。
- `_PHASE2_SCENARIOS`(`interview`/`translate`/`companion`/`butler`)的拒绝提示与文案**保持现状**(FR-6:不倒退)。新增 import 期不变式:`TEMPLATES.keys()` 与 `_PHASE2_SCENARIOS` 必须不相交,相交即启动报错(P25 的机械化兜底)。

### M-3 `Config` 新增字段

`fast_llm_model: str`(生效快脑模型)、`dual_brain_enabled: bool`、`template: ScenarioTemplate`。`__repr__` 脱敏规则不变(新字段无密钥;`template` 内也不含密钥)。

### M-4 `AssembledPipeline` 字段变更

`slow_llm`/`slow_context`/`sentence_aggregator`/`producer`/`consumer` 改 Optional;新增 `stt`(FR-8 要断言 STT 实例的构造参数,今天没有句柄)、`template`(装配实际用的那一份,P55 的端到端锚点);`tts` 的类型标注从具体厂商类放宽为 TTS 基类(模板可选 cartesia 后原标注即失真)。该 dataclass 的存在理由就是给结构性测试断言,扩字段属其设计意图内。

---

## 任务拆分

全部为 backend-dev 的活(无前端)。**前置阻塞**:陪练人设文案须先经用户确认(FR-7),未确认前 G1 的 `IDENTITY_ENGLISH_TUTOR_SECTION` 不得由实现节点自行发挥。

| 组 | 内容 | 主要产出 | 依赖 |
|---|---|---|---|
| G0 | 陪练人设文案定稿(起草 → 呈用户确认,含中英文配比策略与"严格教师"定位一致性检查) | 文案文本(交 G1 落常量) | 无(用户拍板) |
| G1 | `prompts.py` 分段拆分 + 派生兼容常量;新增 `scenarios.py`(注册表 + `build_system_prompt`);`tests/test_scenarios.py` | FR-1/FR-4/FR-7 结构面 | G0(仅陪练文案字段) |
| G2 | `config.py`:模板合并、生效值计算、条件必需、`DUAL_BRAIN_ENABLED` 解析、import 期不变式自检;`.env.example` + `conftest._FAKE_REQUIRED_ENV` 同步;`test_config.py` 增改 | FR-5/FR-6/FR-11/FR-12(配置面) | G1 |
| G3 | `bot.py`:会话级 config 解析、`assemble_pipeline` 模板驱动、慢脑开关两态装配、错误归因放宽、观测日志行、`AssembledPipeline` 扩字段;`tests/test_scenario_assembly.py`(经 `load_config` 走真实装配链路) | FR-2/FR-3/FR-8/FR-12(装配面) | G2 |
| G4 | 回归与行为基线:全量 pytest;`test_dual_brain.py` 6 处切开启态 fixture;`r4_*`/`dual_brain_*`/`dispatch_*` eval 按新运行画像复跑;新增 2 个模板对照 eval 场景并留存输出样本 | FR-9/FR-10 + FR-4 回归判据 | G3 |

**授权修改的既有测试清单**(白名单,清单外的既有用例不许改,防止"改测试凑绿"):
1. `tests/conftest.py`:新增开启态 fixture(如 `bot_module_dual_brain`),`_FAKE_REQUIRED_ENV` 按 M-1 同步。
2. `tests/test_dual_brain.py`:6 处 `assemble_pipeline(bot_module.cfg, …)` 改用开启态 fixture(断言内容不动)。
3. `tests/test_config.py::test_required_env_set_updated`:必需项集合快照按 M-1 更新(`SLOW_LLM_MODEL` 移出默认必需集,新增开启态下的对应断言)。
4. `tests/test_bot.py::_make_config`:补齐新增字段的构造默认值(断言不动)。
其余既有用例(含 `test_prompts.py` 全部 6 条)**必须逐字不改通过**。

---

## 风险与难逆点

| # | 项 | 性质 | 处置 |
|---|---|---|---|
| R-1 | **PRD FR-4 的事实前提有误**(护栏句实际在 `OFFICIAL_SECTION`,不在 LANGUAGE/CONCISENESS) | 契约缺口 | 已按 ADR-3 裁决(提取为独立不可覆盖段),PRD 该句需回改;交主会话/PM 确认 |
| R-2 | 默认 system_instruction 文本发生语义中性变化(护栏句位置) | 可逆(单文件常量) | 必须以 `r4_*`/`dual_brain_*` eval 复跑作为等价证据(SA-15),不接受单测代替 |
| R-3 | 会话级 `load_dotenv(override=True)` 改进程级 `os.environ` | 可逆;**并发下有理论串台窗口** | 硬约束:两行之间不得有 `await`(ADR-1);超出个人单会话用途前须重评 |
| R-4 | 模板 id 一旦写进用户 `.env`,改名要动用户配置 | 弱难逆 | v1 只定 `voice_chat`/`english_tutor` 两个,命名一次定死;新增走注册表 |
| R-5 | `evals/fault.env`(gitignored,本机真实密钥明文)需人工加 `DUAL_BRAIN_ENABLED=true`,否则 R8 故障 eval 在关闭态下无慢脑可失败,场景静默失去意义 | 运维步骤 | 写进 G4 的运行画像;`dual_brain_fault.manifest.yaml` 注释同步 |
| R-6 | `judge_factory.judge_llm` 也调 `load_config()`,会连带校验所选模板的 provider 凭证 | 低 | 跑 eval 时 shell 已 `source .env`(凭证齐全);若 judge 报缺失,按提示补该 provider 的 key |
| R-7 | 关闭态错误归因 `frame.processor is None` 误判 | 已识别的实现陷阱 | SA-14 专测;code-reviewer 逐字核对判断式含 `slow_llm is not None` |
| R-8 | `CAPABILITY_BOUNDARY_SECTION` 首句 `"If the user asks you to do one of these things…"` 指代悬空(枚举句已在 commit `e94b874` 随派活迁移删除) | 既有缺陷,非本次引入 | 不修(范围外);但陪练身份段文案**不得**假设协议段会承接自己的枚举;建议记债务 |
| R-9 | 模板声明 provider 后,环境变量 `STT_PROVIDER`/`TTS_PROVIDER` 被静默忽略 | 设计取舍 | 装配起点 INFO 行打印生效组合;`.env.example` 注释写明优先级 |
| R-10 | 陪练文案未定稿即开工 | 流程阻塞 | G0 为 G1 的硬前置;实现节点不得自行拟定文案上线(FR-7) |

**难逆决策标注**:本设计**无**难以回退的决策。最"重"的一项是 `Config.scenario → template` 字段替换(M-2),因零外部消费者(grep 实测)而可一次性完成,回退 = revert 单个 commit。ADR-1 的会话级解析是新增路径、模块级路径原样保留,回退成本 = 删两行 + 改一处实参。
