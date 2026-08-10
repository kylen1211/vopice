# 契约 · scenario-assembly(档位 cases)

> change_id: scenario-assembly | 产出: tech-architect S2a | 日期: 2026-08-10 | base_commit: 8d11dd2
> 本文件是**本变更接口契约与验收锚点的唯一事实源**。design.md 只引用本文件,不复写其中任何定义。
> 档位理由见 design.md `## 接口契约`。消费者:backend-dev(照 §0 实现)、qa-tester(照 §1 验收)、code-reviewer(照两者比对)。
> **修订 R1(2026-08-10,用户追加拍板)**:`LANGUAGE_SECTION` 改为**模板可覆盖**(注册表可选字段 + 缺省回落),护栏段与 `CONCISENESS_SECTION` 锁定不变;同轮修正 INV-2 的自检落点(依赖方向,hard rule 6)。
> **修订 R2(2026-08-10,用户拍板)**:STT provider 白名单 +`assemblyai`;陪练模板 STT = AssemblyAI `universal-3-5-pro`(原生中英 code-switch),默认模板保持 soniox。变更升 L3。
> 用例总数 23 条:SA-01…SA-17、SA-22、SA-23 共 19 条机检(进 S3 生成物),SA-18…SA-21 共 4 条 manual(仍是放行判据)。
> 命令口径(沿用 task-dispatch 契约已复验的三条,勿按记忆改回):跑 pytest 一律 `cd server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest …`;跑 eval 一律**不带** `uv run` 前缀的全局 `pipecat`,且先 `set -a && source .env && set +a` 并设 `PYTHONPATH="$(pwd)"`;本机无 `python` 命令。

---

## §0 契约定义(跨组件唯一事实源)

### §0.1 模板注册表(新增 `server/scenarios.py`,叶子模块:只 import `prompts`,不 import `config`/`bot`/pipecat)

```python
@dataclass(frozen=True)
class ServiceChoice:
    stt_provider: str | None = None      # None = 沿用环境变量/内置默认
    stt_model: str | None = None
    tts_provider: str | None = None
    tts_voice: str | None = None
    tts_model: str | None = None
    fast_llm_model: str | None = None    # 只影响快脑;不影响 dispatch_llm(见 §0.3 优先级表)

@dataclass(frozen=True)
class ScenarioTemplate:
    id: str
    label: str
    identity_section: str                # 身份段 prompt 文本
    language_section: str | None = None  # 语言段覆盖(修订 R1);None = 回落 prompts.LANGUAGE_SECTION 原文
    services: ServiceChoice = ServiceChoice()

TEMPLATES: Mapping[str, ScenarioTemplate]     # 显式注册表 = 全项目模板集合唯一数据源
def get_template(template_id: str) -> ScenarioTemplate      # 未注册 → KeyError(由 config 层转 ConfigError)
def template_ids() -> frozenset[str]
```

**不变式(不满足即启动报错;FR-1/FR-6/FR-5)**

依赖方向(hard rule 6)决定各条的落点:`scenarios.py` 是叶子模块,**不得** import `config` ⇒ 凡涉及 `config` 侧数据的不变式一律落 `config.py`,不落 `scenarios.py`。

| INV | 内容 | 自检落点 |
|---|---|---|
| INV-1 | `TEMPLATES[k].id == k`,且 `id` 全局唯一 | `scenarios.py` import 期 |
| INV-2 | `TEMPLATES.keys()` 与 `_PHASE2_SCENARIOS` 不相交(枚举放行的每个 id 都有实现;未实现的 id 只能出现在 phase2 拒绝集) | **`config.py`**(它是同时看得见两侧的那一层):模块 import 期自检,相交即 `ConfigError`;数据侧断言另在 `tests/test_scenarios.py` 固化 |
| INV-3 | 每个模板声明的 `stt_provider`/`tts_provider`(非 None 时)必须落在云端白名单:STT ∈ {soniox, deepgram, **assemblyai**},TTS ∈ {elevenlabs, cartesia}(修订 R2 加入 assemblyai;白名单仍只含云端 provider,FR-5 不引入本地模型的约束不变) | `scenarios.py` 自带白名单常量做 import 期自检;`config.py` 侧另按生效值复核(§0.3 校验顺序③) |
| INV-4 | `identity_section` 非空且不含护栏段/能力边界段/简洁段/双脑段文本(模板不得夹带不可覆盖段);`language_section` 若提供须非空 | `scenarios.py` import 期 |
| INV-5 | 除 `identity_section`、`language_section`、`services` 外,模板不携带任何 prompt 段字段(v1 结构约束;剩余升级路径见 design ADR-4) | `scenarios.py` import 期 |

### §0.2 v1 模板集合(FR-7)

| id | label | identity_section | language_section(修订 R1) | services 覆盖 |
|---|---|---|---|---|
| `voice_chat` | 默认 | `prompts.IDENTITY_DEFAULT_SECTION`(= 现有官方段去掉护栏句后的人设文本,逐字迁移) | `None`(回落 `prompts.LANGUAGE_SECTION` 原文,逐字不变) | 全 None(= 现有默认组合,行为与变更前等价) |
| `english_tutor` | 英语陪练(严格英语教师) | `prompts.IDENTITY_ENGLISH_TUTOR_SECTION`(**待定稿**:G0 起草 → 用户确认后落常量) | 声明覆盖文本(**待定稿**,PM 起草):语言策略 = 面向初级学习者的教学阶段模式——**中文主导讲解 + 英语练习素材**;必须显式覆盖"何时用中文、何时给英语",不得与默认段的"永远用中文"字面互斥 | `stt_provider="assemblyai"`(修订 R2,必选);其余字段可选 |

> 语言段文案本身不是验收锚:`contract` 只锚"语言段随模板可覆盖、默认模板逐字不变、段序不变"这三件结构事实(SA-22),具体措辞由 PM 定稿并随身份段一并经用户确认(C-4)。

> **"可观察差异"的判定口径(拆卡方提出的歧义,在此定死)**:FR-2 要求的"两个模板装配结果可观察地不同"由**两条独立证据**构成,缺一不可,`language_section` **不计入** `services` 覆盖:
> ① **prompt 面**:`fast_llm` 的 `system_instruction` 身份段不同(`language_section` 若声明,其差异算在 prompt 面,由 SA-22 单独锚,不替代身份段差异);
> ② **服务面**:`services` 至少一项覆盖生效 —— v1 由 `english_tutor.services.stt_provider="assemblyai"` 满足,断言落在**构造出的 STT 实例类型/参数**上(SA-04/SA-23),不是读模板 dataclass 字段。

**`english_tutor` 人设文案硬约束(FR-7,验收锚点)**

| 约束 | 判据 |
|---|---|
| C-1 不承诺发音纠错 | 文本不得出现"纠正发音"/"发音准确度"/"帮你改发音"一类承诺;纠错表述限定语法/句式/用词 |
| C-2 严格教师定位 | 措辞体现严格定义的英语教师,不得滑向"陪练伙伴/教练"式软化表达 |
| C-3 中英文配比策略显式化 | 文案须写明中英混用/中文求助的触发规则(业界无公开范例,属本项目自行设计的假设) |
| C-4 用户确认门 | 文案未经用户确认不得进入实现;确认范围必须显式覆盖 C-3 与 C-2 |
| C-5 不得假设协议段承接 | 身份段不得写"以下是我不能做的事"一类需要后段承接的句式(协议段首句 `If the user asks you to do one of these things…` 的指代已悬空,见 design R-8) |

### §0.3 配置契约(`server/config.py`)

**新增/变更的环境变量**

| 变量 | 必需性 | 默认 | 语义 |
|---|---|---|---|
| `SCENARIO` | 可选 | `voice_chat` | 模板 id;合法值 = `TEMPLATES.keys()`;`_PHASE2_SCENARIOS` 成员 → 保持现状"属后续阶段,暂未开放"提示;其余未知值 → "不是有效值"拒绝 |
| `DUAL_BRAIN_ENABLED` | 可选 | `false`(**关闭**) | 真值集 `{1,true,yes,on}`、假值集 `{0,false,no,off,""}`(大小写不敏感);集合外的值 → `ConfigError` fail-fast,**不得**静默当假 |
| `SLOW_LLM_MODEL` | **条件必需**(仅 `DUAL_BRAIN_ENABLED` 为真时) | — | 关闭态下即使 `.env` 里仍留着该行也不报错、不使用 |

**STT provider 白名单与条件必需 key(修订 R2)**

| provider | 条件必需 env(选中时) | 落 `Config` 字段 | pyproject extra |
|---|---|---|---|
| `soniox`(默认) | `SONIOX_API_KEY` | `stt_api_key` | `soniox`(既有) |
| `deepgram` | `DEEPGRAM_API_KEY` | `stt_api_key` | `deepgram`(既有) |
| `assemblyai`(**新增**) | `ASSEMBLYAI_API_KEY` | `stt_api_key` | `assemblyai`(**新增声明;该 extra 不带任何第三方包,零新增依赖**) |

**`_build_assemblyai_stt` builder 契约(四条硬约束,ADR-8)**

| # | 约定 | 违反后果 |
|---|---|---|
| B-1 | 惰性 import `from pipecat.services.assemblyai.stt import AssemblyAISTTService`(同 deepgram/cartesia 先例) | 顶部 import 让一家 SDK 拖累全部 |
| B-2 | **不传任何语言参数**(不传 `language`/`language_code`/`language_detection`),靠 `universal-3-5-pro` 原生 code-switch | 传 `language_code="zh"` 即退化成中文锁,陪练英语轮失效——即本次引入它要解的那个问题 |
| B-3 | **不读 `c.stt_model`**(其默认 `stt-rt-v5` 是 Soniox 档位名),显式 `settings=AssemblyAISTTService.Settings(model="universal-3-5-pro")` | 混用厂商档位名 → 连接失败 |
| B-4 | `vad_force_turn_endpoint` 用默认 `True`(轮次由本仓公共 `VADProcessor`/`UserTurnProcessor` 段驱动,与 `ExternalUserTurnStrategies()` 一致);**不得**设 `False` | 设 `False` = AssemblyAI 自管轮次并发 `UserStarted/StoppedSpeakingFrame`,与本仓轮次段打架 |

**生效值优先级(FR-2/FR-5)**:`模板 services 覆盖` > `环境变量` > `内置默认`。合并结果写进 `Config` 的既有中立字段(`stt_provider`/`stt_model`/`tts_provider`/`tts_voice`/`tts_model`),`bot.py` 的 builder 不感知模板。

**`Config` 字段变更**

| 字段 | 变更 |
|---|---|
| `scenario: str` | **删除**,替换为 `template: ScenarioTemplate`(零外部消费者,直接替换) |
| `fast_llm_model: str` | **新增** = 模板覆盖值 or `LLM_MODEL` |
| `llm_model: str` | 语义收窄为"网关默认模型",`dispatch_llm` 用它(模板不得影响派活委派轮模型) |
| `slow_llm_model: str \| None` | 类型放宽,条件必需 |
| `dual_brain_enabled: bool` | **新增** |

**校验顺序(fail-fast 形状,FR-11)**:① `SCENARIO` 解析并取模板(未知/phase2 → `ConfigError`,提示文案保持现状)→ ② 解析 `DUAL_BRAIN_ENABLED` → ③ 计算生效 provider(模板覆盖 > 环境变量,越白名单 → `ConfigError`)→ ④ 按**生效** provider + 开关状态汇总必需 key 表 → ⑤ **一次性**列出全部缺失/占位符项报错。禁止静默回退到默认模板或其它 provider;禁止"字段非空"代理"资源可用"。

**模板覆盖不放松凭证必需性**:模板覆盖 `tts_voice`/`tts_model` 时,对应厂商的环境变量仍在必需集内(取值以模板为准)。

**会话级解析的原子性约束(FR-3,硬约束)**:`bot(runner_args)` 内 `load_dotenv(override=True)` 与 `load_config()` 必须是**紧邻两行、其间无 `await`**;模块顶层的同两行保留,职责为启动预检,其产物**不得**作为 `assemble_pipeline` 的实参。

### §0.4 装配契约(`server/bot.py`)

**`AssembledPipeline` 字段变更**:`slow_llm`/`slow_context`/`sentence_aggregator`/`producer`/`consumer` → Optional;新增 `stt`(STT 服务实例句柄)、`template`(本次装配实际使用的模板对象);`tts` 类型标注放宽为 TTS 基类。其余字段不变。

**开启态(`DUAL_BRAIN_ENABLED=true`)**:管线形状、`ignored_sources`、错误归因与 2026-08-10 基线逐件等价。

**关闭态(默认)**

| 项 | 约定 |
|---|---|
| 不构造 | `slow_llm` / `slow_context` / `slow_pair` / `slow_material_filter` / `sentence_aggregator` / `ProducerProcessor` / `ConsumerProcessor` / `_FastAnswerTap`(对应 `AssembledPipeline` 字段为 `None`) |
| 管线形状 | 单链、无 `ParallelPipeline`:`transport.input() → stt → VADProcessor → UserTurnProcessor → injector → fast_pair.user() → fast_llm → sentinel_filter → tts → transport.output() → fast_pair.assistant()` |
| system_instruction | 不含 `DUAL_BRAIN_SECTION` |
| 保留件 | `sentinel_filter`(防御闸)、`injector` 与两个派活 tool、`user_llm_enabled=False`(挡派活回流注入的第二条泄漏路径,与双脑无关) |
| `ignored_sources` | `[]` |
| 错误归因 | `make_pipeline_error_handler(slow_llm: … \| None, slow_material_filter: … \| None)`,判断式必须是 `slow_llm is not None and frame.processor is slow_llm`;`ErrorFrame(processor=None)` 一律走通用 `pipeline-error` 分支,**不得**推 `slow-brain-failed` 面板消息 |
| 问候 | `seed_greeting_messages(fast_context, slow_context: LLMContext \| None)`,`None` 时只种快脑那条 |

**观测日志行(装配起点,INFO,FR-3/FR-8 的运行期证据)**:
`[scenario] template=<id> stt=<provider>/<model> tts=<provider>/<voice> fast_model=<model> dual_brain=<on|off>`

**运行期切换**:`bot.py` 不注册 `rtvi.event_handler("on_client_message")`;运行期"切模板"请求无接收端 ⇒ 被忽略,且结构上不可能产生"部分字段已切"的中间状态。

### §0.5 prompt 组合契约(`server/prompts.py` + `server/scenarios.py`)

**段与可覆盖性**

| 序 | 段 | 常量 | 模板可覆盖 |
|---|---|---|---|
| 1 | 身份段 | `IDENTITY_DEFAULT_SECTION`(默认模板) | **是**(`ScenarioTemplate.identity_section`) |
| 2 | 语音安全护栏段 | `VOICE_SAFETY_SECTION`(= 原 `OFFICIAL_SECTION` 内的 `"Your responses will be spoken aloud, …"` 一句,逐字迁移) | 否 |
| 3 | 能力边界段 | `CAPABILITY_BOUNDARY_SECTION` | 否 |
| 4 | 语言段 | `LANGUAGE_SECTION`(默认值) | **是**(`ScenarioTemplate.language_section`,修订 R1;`None` → 回落该常量,段序不变) |
| 5 | 简洁段 | `CONCISENESS_SECTION` | 否(v1;剩余升级路径见 design ADR-4) |
| 6 | 双脑协议段 | `DUAL_BRAIN_SECTION` | 否;**仅开启态注入** |

- 组合函数:`scenarios.build_system_prompt(template: ScenarioTemplate, *, dual_brain_enabled: bool) -> str`,段间 `"\n\n"` 连接,顺序即上表。
- 可覆盖段的取值逻辑一律为**模板值优先、缺省回落默认常量**:`template.language_section or prompts.LANGUAGE_SECTION`。禁止在注册表内联一份中文语言指令副本(`prompts.LANGUAGE_SECTION` 仍是默认值唯一事实源)。
- 兼容派生常量(**新代码不得引用**,仅供既有 prompt 契约测试):`OFFICIAL_SECTION = f"{IDENTITY_DEFAULT_SECTION}\n\n{VOICE_SAFETY_SECTION}"`;`SYSTEM_PROMPT` = 默认模板 + 开启态的组合快照。
- 防漂移绑定:必须存在断言 `prompts.SYSTEM_PROMPT == scenarios.build_system_prompt(TEMPLATES["voice_chat"], dual_brain_enabled=True)`。
- `SLOW_BRAIN_PROMPT` 与四个 `INJECT_*` 模板常量**不动**(内容与唯一事实源地位均不变)。

---

## §1 验收用例

判定口径:
- 命令一律在 `/home/ky/git/voice-agent` 下执行;启动 `bot.py`/`pytest` 必带 `NLTK_DISABLE_IMPORT_SECURITY=1`。
- `-k` 关键字是**契约要求的用例命名锚**:实现节点须让对应用例名包含该关键字,便于 qa 与 reviewer 定位。
- "证据"写可被第三方复核的可观测事实(命令 + 原始输出摘要),不接受主观描述;结果逐条进 `test-report.md`。
- 标 `manual: true` 的用例需真机 LLM/网关或人工判断,不进 S3 自动生成物,但**仍是放行判据**,须在 test-report 逐条给证据。

| ID | FR | 断言要点 |
|---|---|---|
| SA-01 | FR-1/FR-6 | 注册表是唯一数据源:`template_ids()` 与 `TEMPLATES` 一致;INV-1/INV-2/INV-3/INV-4 全部成立;不存在"合法值但查无实现" |
| SA-02 | FR-4 | 六段各自独立可寻址;`build_system_prompt` 开启态段序 = §0.5 表;关闭态少且仅少 `DUAL_BRAIN_SECTION`;护栏段、能力边界段、简洁段在**任意**模板下原样出现且不可被模板改写 |
| SA-03 | FR-4 | 防漂移:`SYSTEM_PROMPT == build_system_prompt(TEMPLATES["voice_chat"], dual_brain_enabled=True)` |
| SA-04 | FR-2/FR-8 | **经 `load_config()` 产 Config → `assemble_pipeline` 走完整装配 → 读真实构造对象**:两模板的 `fast_llm` settings 的 `system_instruction` 身份段不同;`voice_chat` 装出的 `stt` 是 Soniox 实例、`english_tutor` 装出的 `stt` 是 `AssemblyAISTTService` 实例(§0.2 判定口径②),其余声明了覆盖的字段(model/voice)逐字段等于模板定义,不是默认残留值。**禁止**手工构造 Config/模板 dataclass 绕过 `load_config` 作为本条唯一证据(P55) |
| SA-05 | FR-12 | 关闭态:`slow_llm`/`slow_context`/`sentence_aggregator`/`producer`/`consumer` 均为 `None`;管线无 `ParallelPipeline`;`fast_llm` 的 `system_instruction` 不含 `DUAL_BRAIN_SECTION` 文本;`ignored_sources == []`;`user_llm_enabled is False` |
| SA-06 | FR-12/FR-9 | 开启态:双脑分支照常挂载,`DUAL_BRAIN_SECTION` 照常注入,`ignored_sources` 仍以对象身份列 `slow_llm`/`sentence_aggregator`/`producer` |
| SA-07 | FR-12 | 关闭态缺 `SLOW_LLM_MODEL` 时 `load_config()` 成功;开启态缺它时报错并在缺失列表里列出该项 |
| SA-08 | FR-12 | `DUAL_BRAIN_ENABLED` 取值解析:真值集/假值集按 §0.3;集合外取值 → `ConfigError`,不静默当假 |
| SA-09 | FR-5/FR-11 | 模板声明越白名单 provider → import/启动期即报错;`assemblyai` 在白名单内且被 `english_tutor` 选中时,缺 `ASSEMBLYAI_API_KEY`(或值为 `CHANGE_ME_`)→ `load_config()` 报错并在缺失列表里列出该项,**不**回退默认模板/soniox;未选中 `assemblyai` 时不强制配置该 key |
| SA-23 | FR-5/FR-2 | AssemblyAI builder 契约(§0.3 B-1…B-4):`STT_BUILDERS["assemblyai"]` 构造出的实例 `_settings.model == "universal-3-5-pro"`,`_settings.language_code is None` 且 `_settings.language_detection is None`,`_build_ws_url()` 产出的 query 串**不含任何 language 参数**;`vad_force_turn_endpoint` 为 `True` |
| SA-10 | FR-6 | `SCENARIO=interview`/`translate` 等 phase2 值 → 与现状一致的"属后续阶段,暂未开放"提示;未知值 → "不是有效值";两者均非未捕获异常 |
| SA-11 | FR-3 | 会话级重读:同一进程内改 `.env` 的 `SCENARIO` 后再次解析,得到新模板;先前已产出的 `Config`/`AssembledPipeline` 快照不受影响(旧会话仍是旧模板) |
| SA-12 | FR-3 | 无运行时切换接收端:`server/bot.py` 内不存在 `on_client_message` 注册 |
| SA-13 | FR-3 | `Config`/`ScenarioTemplate`/`ServiceChoice` 均 frozen,赋值抛 `FrozenInstanceError` |
| SA-14 | FR-12 | 关闭态错误归因:`ErrorFrame(processor=None)` 与非慢脑来源的 `ErrorFrame` 均走通用 `pipeline-error`,不产生 `slow-brain-failed` 面板消息 |
| SA-15 | FR-12 | 关闭态派活不受影响:`injector` 仍在快脑链路头部,`fast_context.tools` 仍含两个派活 tool,`dispatch_worker`/`exec_worker` 仍返回 |
| SA-16 | FR-7 | 陪练身份段负向锚:不含 C-1 禁用措辞;含 C-2/C-3 要素(锚点由定稿文案确定)。**语言相关判据不锚具体文案**,只锚 SA-22 的结构事实 |
| SA-22 | FR-4 | 语言段可覆盖(修订 R1):①默认模板组合出的语言段与 `prompts.LANGUAGE_SECTION` 逐字相同;②声明了 `language_section` 的模板组合出的该段等于模板值、不含默认常量原文;③两种情况下语言段的**位置(第 4 段)与其余五段文本均不变**;④`language_section=None` 与未声明等价 |
| SA-17 | FR-9 | 全量 pytest 不劣于基线 70 passed,无新增失败 |
| SA-18 | FR-4/FR-9 | 开启态下 `r4_*.yaml`、`dual_brain_*.yaml` 逐个复跑通过(护栏句位置变更后的行为等价证据);R8 故障场景前须在 `evals/fault.env` 加 `DUAL_BRAIN_ENABLED=true`,且日志必须见 `slow-failed` 才算注入生效 |
| SA-19 | FR-10 | 两模板行为级样本:同一固定问题集(含"你是谁"/"帮我做个决定")分别对 `voice_chat` 与 `english_tutor` 跑 text 模式 eval,`response` 输出可被 judge/字符串锚区分为不同人设,运行结果留存为本次行为基线;陪练那次**另加一轮 audio 模式英语输入**,留存转写与音频作为 AssemblyAI 中英 code-switch 的真机证据 |
| SA-20 | FR-3/FR-8 | 端到端换模板:同一进程内先以模板 A 建一次会话(日志见 `[scenario] template=…`),结束后改 `.env` 的 `SCENARIO`,重开会话,日志显示新模板;运行中的会话不受影响 |
| SA-21 | FR-7 | 人设文案已经用户确认(确认范围显式含 C-2 与 C-3);未确认不得放行 |

```yaml
cases:
  - id: SA-01
    fr: FR-1,FR-6
    cmd: cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest tests/test_scenarios.py -q -k "registry"
    expect_exit: 0
    expect_out: "passed"
  - id: SA-02
    fr: FR-4
    cmd: cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest tests/test_scenarios.py -q -k "section or compose"
    expect_exit: 0
    expect_out: "passed"
  - id: SA-03
    fr: FR-4
    cmd: cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest tests/test_scenarios.py tests/test_prompts.py -q -k "drift or assembly_order"
    expect_exit: 0
    expect_out: "passed"
  - id: SA-04
    fr: FR-2,FR-8
    cmd: cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest tests/test_scenario_assembly.py -q -k "template_drives"
    expect_exit: 0
    expect_out: "passed"
  - id: SA-05
    fr: FR-12
    cmd: cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest tests/test_scenario_assembly.py -q -k "dual_brain_off"
    expect_exit: 0
    expect_out: "passed"
  - id: SA-06
    fr: FR-12,FR-9
    cmd: cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest tests/test_scenario_assembly.py tests/test_dual_brain.py -q -k "dual_brain_on or TestAssemblePipeline"
    expect_exit: 0
    expect_out: "passed"
  - id: SA-07
    fr: FR-12
    cmd: cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest tests/test_config.py -q -k "slow_llm_model"
    expect_exit: 0
    expect_out: "passed"
  - id: SA-08
    fr: FR-12
    cmd: cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest tests/test_config.py -q -k "dual_brain_flag"
    expect_exit: 0
    expect_out: "passed"
  - id: SA-09
    fr: FR-5,FR-11
    cmd: cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest tests/test_config.py tests/test_scenarios.py -q -k "template_provider or fail_fast"
    expect_exit: 0
    expect_out: "passed"
  - id: SA-10
    fr: FR-6
    cmd: cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest tests/test_config.py -q -k "phase2 or unknown_scenario"
    expect_exit: 0
    expect_out: "passed"
  - id: SA-11
    fr: FR-3
    cmd: cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest tests/test_scenario_assembly.py -q -k "session_config"
    expect_exit: 0
    expect_out: "passed"
  - id: SA-12
    fr: FR-3
    cmd: bash -c '! grep -q "on_client_message" /home/ky/git/voice-agent/server/bot.py'
    expect_exit: 0
  - id: SA-13
    fr: FR-3
    cmd: cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest tests/test_config.py tests/test_scenarios.py -q -k "frozen"
    expect_exit: 0
    expect_out: "passed"
  - id: SA-14
    fr: FR-12
    cmd: cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest tests/test_scenario_assembly.py -q -k "error_attribution"
    expect_exit: 0
    expect_out: "passed"
  - id: SA-15
    fr: FR-12
    cmd: cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest tests/test_scenario_assembly.py -q -k "dispatch_unaffected"
    expect_exit: 0
    expect_out: "passed"
  - id: SA-16
    fr: FR-7
    cmd: cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest tests/test_scenarios.py -q -k "tutor_persona"
    expect_exit: 0
    expect_out: "passed"
  - id: SA-23
    fr: FR-5,FR-2
    cmd: cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest tests/test_bot.py -q -k "assemblyai"
    expect_exit: 0
    expect_out: "passed"
  - id: SA-22
    fr: FR-4
    cmd: cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest tests/test_scenarios.py -q -k "language_section"
    expect_exit: 0
    expect_out: "passed"
  - id: SA-17
    fr: FR-9
    cmd: cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest -q
    expect_exit: 0
    expect_out: "passed"
  - id: SA-18
    fr: FR-4,FR-9
    manual: true
    reason: 需真机网关与 LLM judge;开启态逐个复跑 r4_*/dual_brain_* eval,R8 故障场景另需在本机 gitignored 的 evals/fault.env 加 DUAL_BRAIN_ENABLED=true 并核 slow-failed 日志
  - id: SA-19
    fr: FR-10
    manual: true
    reason: 行为级样本需真跑两次 text 模式 eval(两个模板各一次 bot 启动)并留存 response 输出,判据含 judge 自然语言评价,不可确定性生成;陪练那次**必须含至少一轮英语输入**(audio 模式)以实证 AssemblyAI 中英 code-switch 与中文 TTS 念英语素材的真机表现(design R-12/R-14)
  - id: SA-20
    fr: FR-3,FR-8
    manual: true
    reason: 需真机起 bot 进程、两次客户端连接并在两次之间改 .env,核对 [scenario] 日志行的模板切换与旧会话不受影响
  - id: SA-21
    fr: FR-7
    manual: true
    reason: 人设文案的用户确认是人工门,确认范围须显式覆盖中英文配比策略(C-3)与严格教师定位(C-2)
```
