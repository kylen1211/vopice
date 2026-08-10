# scenario-assembly · PRD

> 变更:scenario-assembly(**L3**,原 L2,因引入外部服务依赖 AssemblyAI 于 2026-08-10 升级,见 FR-5 变更留痕)。s1b 产出,时间基准 2026-08-10,base_commit 8d11dd2。
> 消费方:ui-designer(本次预期无 UI 改动,见「非目标」)、tech-architect(S2a 设计)。

---

## 问题陈述

**现状盘点(数据,实测,来源 `research/codebase-survey.md`/`research/facts.md`)**

- `Config.scenario` 目前只是一道启动期门禁枚举:白名单仅放行 `voice_chat`,`_PHASE2_SCENARIOS = {interview, translate, companion, butler}` 一律显式拒绝并提示"属后续阶段"。**该字段对装配零消费**——grep 实测命中全部集中在 `config.py` 校验与 `test_config.py`,`client/src` 零命中(facts.md ⑧)。也就是说"场景"这个概念今天只存在于配置校验里,不驱动 prompt、不驱动 STT/TTS/LLM 选择,身份与服务组合对所有会话恒定。
- **provider 层完成度说明(D-008,数据)**:STT(soniox/deepgram)与 TTS(elevenlabs/cartesia)已经是可插拔的——`STT_PROVIDER`/`TTS_PROVIDER` 环境变量驱动 + 条件必需校验 + 惰性 import + 中立字段名收敛厂商差异,能力本身工作且有单测覆盖(`test_bot.py` 4 用例)。但这层能力(commit `73125d7`)是**未经任何需求/设计流程直接合入**的(debts.md D-008),导致能力账单 C2"服务可插拔 + 场景装配层"的记载(❌)与实际(provider 层⚠️已做,装配层仍无)不符。本 PRD 按 D-008 建议的处置方式,借本次触达把真实完成度补进现状说明:**provider 可插拔的地基已具备,本次要建的是在其上再加一层——把"prompt 身份 + provider 组合"从写死的单一组合,升级为可声明、可枚举、可复用的模板**。
- **身份/协议混装现状(数据,实测)**:`prompts.py::SYSTEM_PROMPT` 由 `OFFICIAL_SECTION + CAPABILITY_BOUNDARY_SECTION + LANGUAGE_SECTION + CONCISENESS_SECTION + DUAL_BRAIN_SECTION` 五段拼接而成,顺序被 `test_prompts.py` 断言。其中身份语义(人设,`OFFICIAL_SECTION`)与协议语义(能力边界 `CAPABILITY_BOUNDARY_SECTION`、双脑素材消化协议 `DUAL_BRAIN_SECTION`)混在同一个字符串里——整段替换会连带击穿 R4 能力边界与双脑既有 eval(`r4_*.yaml`、`dual_brain_*.yaml`)。这是本次装配层设计必须显式面对、不能回避的约束。

**核心诉求(访谈,用户原话)**

用户拍板方向为"G1 装配层"(ServiceSwitcher 经调研澄清后**本期不采用**,详见「非目标」),并确认对配方的理解:"这个就是一个可选的模板,不同模板对应不同身份"——即模板 = 身份(prompt 人设)+ 服务选择(LLM/STT/TTS)的组合;切换时机拍板为"不做动态切换:只要切换模板,就是结束当前会话、按新模板重新装配、重开新会话",模板选择发生在会话建立之前,会话运行期间模板不可变;STT/TTS 均为云端 provider,无本地模型诉求;双脑加固明确"不是本期任务"。

用户在 PRD 修订过程中进一步拍板(访谈,2026-08-10,原话大意):"快慢脑方案不成熟,先把慢脑停掉,主要先把快脑功能对接好"。现状核实(数据,实测,`research/codebase-survey.md` §1.1):当前无任何开关——`SLOW_LLM_MODEL` 是必需配置项,双脑 `ParallelPipeline` 分支在 `assemble_pipeline` 中无条件装配。这条拍板是本次新增 FR-12(慢脑默认停用开关)的直接动机:借装配层建成的同一次改动,把双脑机制的默认可用性收敛为"关闭态",只保留快脑主链路默认生效,双脑代码与测试保留、供未来重新开启,不等于取消双脑功能。

**三层 why(为什么要建这层,而非直接抄"要做装配层"这个方案)**

1. **表层**:今天每加一个"人设/用途"(如陪练)都得直接改 `bot.py::assemble_pipeline` 硬编码 prompt 拼装与 provider 选择,没有一层可声明、可复用的抽象——改一次就要重新过一遍全部结构性测试与 eval。
2. **中层(数据,`docs/capability-ledger.md` C2 行 + 项目总纲原文)**:路线图已明确未来还有同声翻译、面试辅助两个"真功能"要接入,且总纲原文写明"陪练=配置态(换 prompt/换 LLM),不是功能"——陪练本质是这层机制的第一个配置态验证,不是终点。如果不先把"写死组合"升级为"模板注册表",每接一个新用途都要重复改动核心装配函数,回归风险随场景数线性叠加。
3. **根因(假设,置信 75%)**:`bot.py` 目前是脚手架形态在往生产能力演进,`Config.scenario` 是早期占位但从未被真正消费的半成品(现状盘点事实⑧)。此次是把这块半成品补齐为可扩展骨架的窗口——晚做一次,未来同传/面试落地时要同时补"装配层"和"具体场景内容"两件事,改动面更大、风险叠加。反证条件:若同传/面试的实际人设与工具需求与陪练差异极大(例如需要完全不同的 pipeline 结构而非仅参数),本次建的"仅参数化、结构恒定"骨架可能不够用,需在那时重新评估装配层是否要支持结构性差异化。

---

## 需求清单

> P0 = 本次必须完成;P1 = 应完成但不阻塞验收放行(缺陷记入 test-report 而非拦截)。

### FR-1(P0)模板注册表——唯一数据源

建立显式注册的场景模板清单(recipe registry),每个模板含:`id`、`label`、身份段 prompt 文本、快脑 LLM 选择(model,可选,不填则用现有默认)、STT provider+model、TTS provider+voice+model。

- **Given** 装配层需要读取模板定义,**When** 按已注册的模板 id 查询,**Then** 返回该模板的完整定义(身份段文本 + 快脑 LLM/STT/TTS 组合),且该注册表是全项目模板集合的**唯一**数据源——不存在第二处硬编码模板定义(呼应旧库 `va/scenarios/RECIPES` 显式注册表的既有约定,参见 `research/codebase-survey.md` §2.1)。

### FR-2(P0)模板驱动的差异化装配

`assemble_pipeline` 按选定模板产出对应的身份段 prompt 与服务实例(STT/TTS/快脑 LLM 的 provider+model+voice),不同模板的装配结果必须可观察地不同。

- **Given** 已注册模板"默认"与"陪练"(FR-7),**When** 分别以两者装配 pipeline,**Then** 两者产出的 `fast_llm.system_instruction` 身份段内容不同;且若模板声明了不同的 STT/TTS/快脑 LLM 选择,对应构造出的 service 实例的 model/voice/provider 也随之不同。

### FR-3(P0)不做动态切换——模板选择发生在会话建立之前

不支持运行时/会话内动态切换模板。**切换模板 = 结束当前会话、按新模板重新装配、重开一个新会话**。模板选择发生在会话建立之前;会话运行期间模板不可变。

- **Given** 一个会话已用模板 A 建立并处于运行中,**When** 外部改变了模板选择配置(不论以何种机制),**Then** 当前运行中的会话继续保持模板 A 的身份段与服务组合不变,直至该会话结束。
- **Given** 会话已结束、需要改用模板 B,**When** 重新装配并建立新会话,**Then** 新会话使用模板 B 的完整定义(身份段 + 服务组合),不残留模板 A 的任何构造结果。
- **Given** 会话运行中出现"切换模板"性质的外部请求(例如未来客户端消息),**When** 装配层不支持运行时切换,**Then** 系统必须要么忽略该请求并保持当前模板不变,要么以明确反馈告知不支持——两者选一由 S2a 设计裁决,但**不得**产生"部分字段已切、部分字段未切"的不一致中间状态。

### FR-4(P0)身份段/协议段分层契约

模板**可以**替换身份段中的人设描述文本(`OFFICIAL_SECTION`)与**语言段**(`LANGUAGE_SECTION`,本期新开放,见下方起因留痕)。协议段(`CAPABILITY_BOUNDARY_SECTION` 能力边界;`DUAL_BRAIN_SECTION` 慢脑素材消化协议——**仅当慢脑开关开启时才注入(见 FR-12),关闭时该段不出现在 system_instruction 中;注入时同样不可被模板覆盖**)、简洁风格段(`CONCISENESS_SECTION`),以及**从身份段中独立提取出来的语音安全护栏段**(原句"避免 emoji/项目符号等无法朗读的格式"——**实测位于 `OFFICIAL_SECTION` 身份段内,而非语言/简洁段**;已按设计裁决提取为独立不可覆盖段,紧随身份段之后,详见 `design.md` ADR-3),在任意模板下都必须**原样保留、顺序不变**,不可被模板覆盖。`LANGUAGE_SECTION` 未被模板显式覆盖时,取**现有默认值**(现行中文指令原文),默认模板行为因此不变。

> **起因留痕(PM 实测冲突 + 用户拍板,2026-08-10)**:PM 起草陪练模板人设文案时发现,`LANGUAGE_SECTION` 现有文本("Always reply in Chinese (Mandarin), regardless of the language of the input text.")与英语陪练模板的教学定位(需要用英语讲解/示范/练习)存在**字面指令冲突**(详见 `research/tutor-persona-draft.md` 原开放问题①)。用户拍板:原定"后期"才做的"`LANGUAGE_SECTION`/`CONCISENESS_SECTION` 允许模板覆盖"升级,**提前到本期**,但只提前 `LANGUAGE_SECTION` 一项,走的正是下方设计约束原本就预留的升级路径;`CONCISENESS_SECTION` 与独立护栏段维持不可覆盖,仍是后期候选。

> 产品决策(置信 70%,范围收窄为仅 `CONCISENESS_SECTION`):把 `CONCISENESS_SECTION` 与协议段一起划为"模板不可覆盖",理由是简洁风格一致性暂无按模板区分的实证需求;独立护栏段不可覆盖的理由见上方起因留痕(与"兜底"护栏句无关,是设计裁决的直接结果)。`LANGUAGE_SECTION` 已按用户拍板于本期提前开放模板覆盖(见上方起因留痕),不再适用本条"不可覆盖"决策范围。**反证条件**:若未来某模板确有正当理由需要不同简洁度/详略(如面试场景需要更正式详细的追问),该项应比照 `LANGUAGE_SECTION` 本次的先例开放覆盖,走下方设计约束预留的升级路径。

**设计约束(交 S2a)**:prompt 组合必须做成分段结构——每段在注册表/组合函数层面是独立可寻址的字段与拼接单元,而不是把整体拼成一个不透明字符串常量后再处理。`LANGUAGE_SECTION` 本期从"模板不可覆盖"升级为"模板可覆盖"(见上方起因留痕),正是对这条设计约束的**第一次实证**——该升级的改动应收敛在:①注册表新增可选字段(如 `language_section`,不填则用现有默认值)、②组合函数里该段的取值逻辑(模板值优先、未覆盖则用默认常量)、③对应校验测试三处,不触达管线装配顺序、不触达其余段落、不触达 STT/TTS/LLM 服务选择这条正交轴。**`CONCISENESS_SECTION` 仍维持本约束描述的"未来可能升级"状态**,本期不做,升级时应比照 `LANGUAGE_SECTION` 这次的同一改动面收敛路径。S2a 方案是否满足该约束(尤其 `LANGUAGE_SECTION` 本次改动是否真的收敛在上述三处),是本条的验收依据之一。

- **Given** 默认模板且慢脑开关**开启**,**When** 装配出该模板的 `fast_llm.system_instruction`,**Then** `CAPABILITY_BOUNDARY_SECTION`、`DUAL_BRAIN_SECTION`、`LANGUAGE_SECTION`、`CONCISENESS_SECTION`、独立护栏段五段文本与顺序位置和变更前**逐字**一致。
- **Given** 任意已注册模板(含覆盖了 `LANGUAGE_SECTION` 的模板)且慢脑开关**开启**,**When** 装配出该模板的 `fast_llm.system_instruction`,**Then** 独立护栏段、`CAPABILITY_BOUNDARY_SECTION`、`CONCISENESS_SECTION`、`DUAL_BRAIN_SECTION`(注入时)四段文本**逐字**一致、不因模板而变;`LANGUAGE_SECTION` 的**位置顺序**保持不变(即便其内容因模板覆盖而不同于默认值);且现有 `evals/r4_*.yaml`、`evals/dual_brain_*.yaml` 在开启态下都能通过(回归判据,不因模板切换而失效)。慢脑开关**关闭**态下的 `DUAL_BRAIN_SECTION` 行为见 FR-12,不在本条判据范围内。
- **Given** 模板未显式声明 `LANGUAGE_SECTION`(如默认模板),**When** 装配该模板,**Then** `LANGUAGE_SECTION` 取现有默认值(中文指令原文),行为与变更前完全等价,不因新增的"模板可覆盖"能力而意外改变默认模板输出。
- **Given** 模板显式声明了不同的 `LANGUAGE_SECTION`(如陪练模板,教学阶段语言策略,见 FR-7),**When** 装配该模板,**Then** `fast_llm.system_instruction` 中的语言段文本采用模板声明值而非默认中文指令,该差异须能被 FR-10 的行为级样本观察到。
- **Given** S2a 输出的 prompt 组合设计,**When** 检视其数据结构与组合函数,**Then** 五段(身份/能力边界/语言/简洁风格/双脑协议)必须是各自独立的字段/组合单元,不存在"整段常量字符串、无法单独寻址某一段"的实现方式(呼应上方设计约束,防止未来升级时被迫重写整个 prompt 组合层)。

### FR-5(P0)服务选择限定既有云端 provider 白名单

模板中的 STT/TTS provider 取值必须来自现有云端 provider 白名单(STT: soniox/deepgram/**assemblyai**;TTS: elevenlabs/cartesia),不引入本地模型/本地 provider(用户已澄清"STT 跟 TTS 都是云端的")。

> **变更留痕(用户拍板引入 AssemblyAI,2026-08-10;变更升级为 L3)**:用户亲测 AssemblyAI 中英识别可用,拍板加入 STT 白名单,解决陪练模板"soniox 硬锁中文识别语言提示与英语陪练冲突"的正交缺口。架构已在本地 pipecat 1.6.0 现场核实(证据见 `design.md` preflight E-7/E-8/E-9):`AssemblyAISTTService` 类存在、`pipecat-ai[assemblyai]` extra 为空(**零新增 Python 包**)、条件必需环境变量 `ASSEMBLYAI_API_KEY`、默认模型 `universal-3-5-pro` **原生中英 code-switch**、零配置即不发送任何语言锁参数。**新增的是外部服务依赖**(账号、密钥、计费),不是代码依赖——这是本变更从 L2 升级为 **L3** 的触发点。

- **Given** 一个模板定义声明的 STT/TTS provider 不在现有白名单内,**When** 装配层加载该模板,**Then** 必须 fail-fast 报出清晰错误(复用现状 `config.py` 白名单校验机制),不得进入运行时才暴露。
- **Given** 陪练模板声明 `stt_provider = "assemblyai"` 且当前环境未配置 `ASSEMBLYAI_API_KEY`,**When** 装配该模板,**Then** 按 FR-11 fail-fast 报出缺失项,不静默回退到 soniox/deepgram(呼应"新增外部服务依赖"这条代价,账号与配额由用户自行持有,不在本流水线内代为申请)。

### FR-6(P0,关联坑库 P25)模板 id 枚举与注册表实现一一对应

模板 id 的合法值枚举必须与"实际已在注册表中实现的模板"一一对应,不得出现"枚举放行但装配层无对应实现"的半成品状态。

- **Given** 白名单中列出的每一个模板 id,**When** 装配层查注册表,**Then** 都能找到对应的完整模板定义;不存在"合法值但查无实现"的情况。
- **Given** 一个已知但本期未实现的场景 id(如 `interview`/`translate`),**When** 配置选中它,**Then** 收到与现状一致的"该功能属未来阶段,暂未开放"明确拒绝提示,而不是装配阶段抛出未捕获异常(延续现状 `_PHASE2_SCENARIOS` 的既有正确模式,不倒退)。

### FR-7(P0)v1 落地模板集合:默认 + 陪练

至少落地两个模板:①**默认模板**——迁移现有 `voice_chat` 行为原样成为一个模板(身份段 = 现有 `OFFICIAL_SECTION` 原文,`LANGUAGE_SECTION` = 现有默认值,服务选择 = 现有 provider 默认值,STT = soniox);②**陪练模板**——语义钉为**英语陪练(英语教师人设)**(用户澄清,访谈),新身份段人设文本 + 新 `LANGUAGE_SECTION` 覆盖值(教学阶段语言策略,见下)+ **STT = assemblyai**(FR-5 新增白名单项,解中英识别语言锁冲突),可选择不同的快脑 LLM model 和/或不同的 TTS 服务组合。

**人设文案来源约定**:具体文案内容仍不在本 PRD 给出。已核实旧库 `~/git/voice-translate-v2` 的 `va/scenarios/` 无现成陪练/英语教师人设可复用(该目录只有 `butler`/`interview`/`translate`/`voice_chat` 四个配方,均非教师/陪练语义)。文案将由外部检索参考(纪要落 `pipeline/scenario-assembly/research/tutor-persona-references.md`)后起草,最终文案在实现前须呈用户确认,不由实现节点自行拍板发挥。

**人设文案硬约束(来源 `research/tutor-persona-references.md`,已核验;定性经用户订正)**:文案**不得承诺"纠正发音"**。理由**不是**"技术上结构性做不到"——用户指出发音纠错技术上可行(经专用发音评测工具提取音素级规律/指标,再喂给对话层),只是这属于**后期高级功能,本期不接入该工具链**。当前架构 STT→LLM→TTS 级联下,对话 LLM 自身看不到语音本身(声调/口音/连读等信息在 STT 转写阶段已丢失)——Speak 工程博客一手证据仍可作为"对话 LLM 自身无法感知发音"这一点的依据,但结论不是"不可能",而是"需要专用音素评测工具链、且本期不做"(该工具链见「非目标」)。纠错承诺范围限定在**语法/句式/用词层面**,不得出现"我会帮你纠正发音"一类本期做不到的承诺。

**角色定位已拍板(访谈,2026-08-10)**:采用**严格定义的英语教师人设**,不采用业界"陪练伙伴/教练"式倾向(用户原话大意:"业界回避严格教师是商业做法、担心客户留存率;我自己是个人使用,需要严格定义的[教师]")。业界对比信息(Speak/ELSA Speak/Loora/Duolingo Max/Call Annie 五款主流产品中四款明确回避严格教师形象,`research/tutor-persona-references.md` §1.1)仅作决策背景留痕,不代表本项目采纳该倾向;这一项**不再是待用户确认的设计假设**。

**人设文案版本已拍板(访谈,2026-08-10)**:草案(`research/tutor-persona-draft.md` §①)"版本 A——严格教师·标准版"已获用户确认,作为陪练模板身份段(`IDENTITY_ENGLISH_TUTOR_SECTION`)的**终版基底**;"版本 B——高强度版"不采用,标记废弃。

**语言策略改为"教学阶段模式",取代原三个中英配比候选(访谈,2026-08-10)**:用户自述为英语初级学习者、尚无法用英语交流,原 `research/tutor-persona-draft.md` §② 三个中英配比候选(全英文沉浸/默认英文卡壳兜底/英文为主语法中文讲解)均不适配该实际水平,**一律不采纳、标记废弃**。改为**教学阶段模式**:中文主导讲解与引导,英语用于练习素材/示范/跟读,随学生表现渐进提高英语占比。具体策略文本由 PM 基于该原则起草(草案见 `research/tutor-persona-draft.md` 新增节),纳入陪练模板的 `LANGUAGE_SECTION` 覆盖值——该段本期已由 FR-4 改为模板可覆盖,起因正是本文案与原锁定的中文指令字面冲突(见 FR-4 起因留痕)。

- **Given** 系统内置模板注册表,**When** 列出全部已注册模板,**Then** 至少包含"默认"与"陪练"两个 id,陪练模板的身份段人设定位为**严格的**英语教师(英语陪练)、语言段体现教学阶段模式,均与默认模板不同。
- **Given** 陪练模板**终版合成文案**(版本 A 身份段 + 教学阶段语言策略,分别对应 `IDENTITY_ENGLISH_TUTOR_SECTION` 与 `LANGUAGE_SECTION` 覆盖值)已起草,**When** 提交实现之前,**Then** 该终版合成文案已经过用户**最终确认**——角色定位(严格教师)与人设版本(版本 A)已分别拍板,无需重复呈批;教学阶段语言策略的具体措辞是新起草内容,必须呈批。未经此最终确认,文案不得视为已确认,不接受实现节点直接杜撰或对已拍板内容二次改写后不再复核。
- **Given** 任意版本的陪练模板人设文案,**When** 检查其纠错相关措辞,**Then** 不出现"纠正发音"/"帮你改善发音准确度"一类承诺,纠错范围表述限定在语法、句式、用词层面(呼应上方硬约束)。

### FR-8(P0,关联坑库 P55)端到端装配链路一致性

模板选择必须真正贯穿到 `assemble_pipeline` 实际构造的服务对象与 prompt 上,验证方式必须是"运行装配后读取真实构造对象属性",不接受"单测直接构造模板 dataclass 传参、绕过 `assemble_pipeline`"作为唯一证据。

- **Given** 选定陪练模板,**When** 调用 `assemble_pipeline` 走完整装配路径,**Then** 检视其返回的 `AssembledPipeline` 中 `fast_llm.system_instruction`、STT/TTS service 实例的构造参数(model/voice),逐字段与陪练模板定义一致,而非默认模板遗留值。

### FR-9(P1)现有测试/eval 基线不回归

引入模板机制后,现有非 `test_task_dispatch.py` 的用例(`test_bot.py`/`test_config.py`/`test_dual_brain.py`/`test_prompts.py` 等)与相关 eval(`r4_*`/`dual_brain_*`)必须继续通过,行为与变更前等价——其中 `test_dual_brain.py` 与 `dual_brain_*.yaml` 覆盖的是慢脑逻辑本身,须在**慢脑开关开启态**下运行验证(呼应 FR-12;默认关闭不代表这些用例失效或可删除,双脑代码与测试保留);其余用例在默认模板、默认(关闭)开关态下验证。

- **Given** 默认模板等价于变更前 `SCENARIO=voice_chat` 行为,且慢脑开关按各测试原有假设设置(`test_dual_brain.py`/`dual_brain_*.yaml` 在开启态运行,其余用例默认关闭态运行),**When** 运行 `cd server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run pytest -q`(`tests/test_task_dispatch.py` 的 collection 阻塞已解决,见下方开放问题②备注,全量 pytest 可直接跑),**Then** 结果不劣于变更前基线(70 passed 或更多,不出现新增失败)。

### FR-10(P1,关联坑库 P57)行为级输出样本基线

除结构性断言(FR-2/FR-4/FR-8)外,须新增至少一组端到端 eval 场景(文本模式,参照现有 `r4_*`/`dual_brain_*` 命名与手法),用固定问题集分别跑默认模板与陪练模板,留存真实 LLM 输出样本,作为"身份差异确已生效"的行为级证据——不能只锁"耗时/分支"这类确定性指标,也不能只查 `system_instruction` 字符串包含预期文本这类静态断言。

- **Given** 默认模板与陪练模板均已装配,**When** 对同一固定问题集(如"你是谁"/"帮我做个决定")分别跑 `pipecat eval run`(text 模式),**Then** 两个模板的 `response` 输出在人设风格上可被判据(eval judge 或字符串锚点)区分为不同人设,该运行结果留存为本次变更的行为基线样本。

### FR-11(P0,异常路径,关联坑库 P28)资源缺失时 fail-fast,不静默回退

若选定模板要求的 provider/凭证在当前环境未配置齐全,装配阶段必须 fail-fast 报出清晰缺失项,**不允许**静默回退到默认模板或其它 provider——避免用户误以为在用模板 B、实际却在用模板 A 或默认服务("配置存在≠资源加载成功",不得用"字段非空"代理"真正可用")。

- **Given** 陪练模板声明需要 provider X 的凭证,**When** 当前 `.env` 未提供该凭证(`CHANGE_ME_` 占位符或缺失),**Then** `load_config()`/装配阶段立即报错并列出缺失项(复用现有 fail-fast 机制),不启动会话,不静默使用默认模板顶替。

### FR-12(P0)慢脑默认停用开关

背景(访谈,用户原话大意,2026-08-10):"快慢脑方案不成熟,先把慢脑停掉,主要先把快脑功能对接好"。现状核实(数据,实测,`research/codebase-survey.md` §1.1):当前**无任何开关**——`SLOW_LLM_MODEL` 是必需配置项,双脑 `ParallelPipeline` 分支在 `assemble_pipeline` 中无条件装配。

新增一个全局配置开关控制慢脑启停,**默认关闭**:
- **关闭时**:装配不挂双脑分支(`slow_llm`/`slow_context`/`slow_pair`/`ProducerProcessor`/`ConsumerProcessor` 等慢脑专属件不构造),`fast_llm.system_instruction` 不注入 `DUAL_BRAIN_SECTION`(见 FR-4),`SLOW_LLM_MODEL` 相应不再是必需配置项。
- **开启时**:行为与本次变更前(2026-08-10 基线)等价——双脑分支照常挂载,`DUAL_BRAIN_SECTION` 照常注入,`SLOW_LLM_MODEL` 仍是必需项。
- 双脑相关代码与测试**保留不删**,`test_dual_brain.py`/`dual_brain_*.yaml` 改为在**开关开启态**下运行验证(呼应 FR-9),不因默认关闭被判定失效。

- **Given** 开关处于默认关闭态,**When** 装配 pipeline(任意模板),**Then** 返回的 `AssembledPipeline` 不含双脑分支专属句柄(`slow_llm`/`slow_pair`/`producer`/`consumer` 等不存在或为 None),且 `fast_llm.system_instruction` 不含 `DUAL_BRAIN_SECTION` 对应文本。
- **Given** 开关处于默认关闭态且 `.env` 未提供 `SLOW_LLM_MODEL`,**When** 调用 `load_config()`,**Then** 不因缺失 `SLOW_LLM_MODEL` 而报错(该项从"恒定必需"改为"按开关条件必需",呼应现有 provider 条件必需校验的既定模式)。
- **Given** 关闭态下的快脑,**When** 用户与其对话,**Then** 快脑独立作答(不等待/不依赖慢脑输出),行为等价于"单脑"对话,不因慢脑缺失出现报错、卡顿或空白应答。
- **Given** 开关手动开启,**When** 装配 pipeline,**Then** 行为与本次变更前基线等价:双脑分支照常挂载、`DUAL_BRAIN_SECTION` 照常注入、`SLOW_LLM_MODEL` 仍是必需项;现有 `test_dual_brain.py`/`dual_brain_*.yaml` 在此开启态下继续通过(而非被删除或跳过)。
- **Given** 关闭态,**When** 用户通过派活(G3)能力发起任务派发,**Then** 派活不受影响——派活是独立 worker(`dispatch_worker`/`exec_worker`),`dispatch_llm` 使用快脑同款模型(非慢脑模型),不依赖双脑分支是否挂载(codegraph 实测,`research/codebase-survey.md` §1.4 佐证派活接入点独立于双脑 `ParallelPipeline` 分支)。

**异常路径小结(呼应 D-002/hard rule 7)**:失败——见 FR-6/FR-11(枚举拒绝 + 凭证缺失均 fail-fast);超时——不适用(装配发生在会话建立前,是同步一次性构造过程,不涉及网络等待型超时);并发冲突——是否存在"同一进程内多会话各自选不同模板"的并发场景,取决于部署拓扑,已列入「开放问题」;回退——见 FR-11(禁止静默回退)。

---

## 非目标

- **ServiceSwitcher / 运行时热切换**:同一会话内切场景、切服务(含 `ManuallySwitchServiceFrame`/`LLMSwitcher`/`ServiceSwitcher`)不在本次范围。用户已拍板"不做动态切换";这条路径若未来需要,走独立变更评估(`research/external-research.md` 已核验的 API/坑点可直接复用,不必重新调研)。
- **双脑(slow_llm)/派活(dispatch_llm)的内容与协议加固**:本次范围仅新增"慢脑默认停用开关"这一装配层能力(FR-12),不涉及双脑机制本身的加固、优化或重新设计——`SLOW_BRAIN_PROMPT` 文本内容、`dispatch_llm` 的行为(无 system_instruction、由 UIWorker tool docstring 驱动)均保持不变,模板机制也不改变这两者的身份/协议内容。用户已拍板"双脑加固不是本期任务";**默认停用是本次新增范围**,不代表对双脑逻辑本身做任何修改。
- **pipeline 结构性差异化**:管线形状(双脑 `ParallelPipeline` 分支、派活注入点等)对所有模板恒定,模板只变参数(身份段文本 + provider/model/voice)不变结构。"某模板关闭双脑分支/派活分支"这类结构性差异化不在本期范围。
- **桌面客户端 / 模板选择器 UI**:能力账单 C1(桌面客户端载体)尚未起,`client/src` 当前无任何场景相关代码。本次不新增客户端 UI,模板选择机制留在服务端配置层(具体机制——环境变量/启动参数等——由 S2a 设计裁决,不在 PRD 层规定)。
- **`interview`/`translate` 场景的具体内容**:这两个 id 仍留在 `_PHASE2_SCENARIOS` 继续被拒绝(FR-6)。本次只是把装配层机制建成、让它们"未来有地方挂",具体人设/工具/服务组合内容不在本次范围。
- **`tests/test_task_dispatch.py` 既有 collection 失败的修复**:该问题由 commit `8d11dd2`(清理 task-dispatch 流程过程产物)引入,与本变更无关,不算本次 FR 范围;**已在本 PRD 起草期间解决**(见下方开放问题②备注),不再需要本变更处理。
- **发音评测/纠错(专用音素评测工具链)**:技术上可行(经专用发音评测工具提取音素级规律/指标喂给对话层),但属**后期高级功能**,本期不接入该工具链、不在陪练模板中承诺该能力(见 FR-7 人设文案硬约束)。用户已预告为后期候选,非本次范围,也非"永久不做"。

---

## 开放问题

1. **部署拓扑决定 FR-3 落地方式**:当前架构下 `cfg = load_config()` 在 `bot.py` 模块顶层一次性执行(D-003),"模板选择发生在会话建立之前"这一诉求,若实际部署是"一个长驻进程服务多个并发会话",则同进程内所有会话会被迫共享同一次模板选择,无法做到"每个会话各自在建立时点独立选模板";若实际部署是"每次会话对应独立进程/独立 `bot()` 调用重新读取配置",则现状机制已经满足,无需触达 D-003。**谁来答**:tech-architect 在 S2a 现场核实 pipecat dev runner/生产部署的实际拓扑后裁决;若是前者,方案代价会显著上升,需回来更新本 PRD 的 FR-3 判据。
2. ~~`tests/test_task_dispatch.py` 修复时机~~ ——**已解决(2026-08-10,行为证据)**:主会话拍板后已从归档 commit `726ba43` 恢复 `pipeline/task-dispatch/baseline/` 下两个 json,全量 `uv run pytest -q` 实测 **70 passed** 无失败(不再需要 `--ignore`)。FR-9 的回归判据已改为以此为起点(见 FR-9)。
