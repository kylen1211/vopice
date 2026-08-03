# fast-slow-brain 实现任务

> **全局约束**
> - 技术栈:Python 3.11 / pipecat-ai `==1.6.0`(venv 在 `server/.venv`)/ pytest / ruff / pyright。
> - **跑任何 python(含 `python -c` 临时探查)必须带 `NLTK_DISABLE_IMPORT_SECURITY=1`**;漏带会得到 `ImportError: Blocked import of regex ... for security reasons`,那是环境拦截不是缺依赖,勿误判。
> - 质量线(每组完成信号必含):`pytest` 全绿 + `ruff check .` 零 error + `pyright` 无**新增**错误。
> - **异步测试形态写死(实测,不照做会当场全红)**:venv 内**没有 `pytest-asyncio`**(`server/pyproject.toml` dev 组只有 pyright/ruff/pytest),而 `pipecat.tests.utils.run_test` 是协程。直接写 `async def test_...` 会得到 `async def functions are not natively supported`。**一律用 `unittest.IsolatedAsyncioTestCase`**(plain pytest 原生支持,零新依赖),照抄官方写法 `~/git/pipecat/tests/test_producer_consumer.py`。**禁止**为此加装 `pytest-asyncio`(第 1+ 组禁安装)。
> - **"先红证据"的判定口径(防伪红)**:先红必须是**断言级失败**(用例跑起来了、断言不满足)。**collection 级 / import 级失败不算先红**——`async def functions are not natively supported`、`ModuleNotFoundError`、语法错误都是红的,但它们证明的是"测试没跑",不是"功能没实现"。组末评审核对先红证据时须区分这两类,把后者当先红即为无效证据。
> - **变异验证(用户 2026-08-02 追加,治"测试全绿但验收一堆问题")**:标了"变异验证"的组,组末评审前**必须按组头列出的变异逐项做一次**——故意把实现改坏,确认对应用例**变红**,截取红色输出后 `git checkout` 还原。**不红即该用例无杀伤力**,当场补强,不得以"测试已全绿"结案。历史实证(全局台账 8 条同型):替身构造生产上游产不出的值 → 语音说"拒绝"实际放行仍 16 条全绿;验收断内存属性而非落盘产物 → 同项目同型虚绿三次;期望值取自被验对象自身 → 一行未改也 PASS;负向断言锚点消失 → 840 测试全绿而断言已真空。
> - 官方件优先(拍板 21):不自造官方已有的能力;确需自研须在 design.md 留自证。写任何 pipecat 类名/参数前先查 venv 源码或 codegraph,**不凭记忆**。
> - 代码检索优先 `codegraph explore`(本仓库与 `~/git/pipecat` 均已建索引),grep/Read 作补充。
> - 禁止:改 `openspec/specs/` 事实源;改 1 期既有 eval 场景文件;`git add -A`(只按路径 stage 本任务改动的文件)。
>
> **⚠️ 每个任务节点开工前先做(用户 2026-08-02 明确要求,所有节点共用)**:
> 1. 确认本次任务要用的**数据齐不齐**(接口签名、配置项、依赖的前序产出、测试夹具);
> 2. 确认**方案完不完整**(manifest 圈定节是否够动手、有无未定决策);
> 3. **想清楚再动手**——缺数据或方案有洞,先按四态回报 `NEEDS_CONTEXT`/`BLOCKED`,不要边写边猜。
>
> **事实源**:`proposal.md`(R1–R9)/ `design.md`(§ + §11 RTM)/ 调研留痕 `research.md`(外部方案对照)
> **依赖顺序**:0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9;其中 3/4 可并行——**前提是哨兵落独立文件**(4 组产出 `server/sentinel.py` + `server/tests/test_sentinel.py`,3 组产出 `server/dual_brain.py` + `server/tests/test_dual_brain.py`,两组零文件重叠);6 依赖 5 全绿。
> **执行模式**:L3,M21 **按组评审档**(用户 2026-08-02 裁决:本期口径"整体跑通即可、不做质量把控",逐任务评审开销过重)。具体:
> - 任务仍**逐个**派 fresh 实现 subagent(只给任务书 + manifest 圈定节,不给会话历史);第 0 组除外,主会话执行;
> - **逐个 per-task commit 不省**(回滚点 = B1 强制纪律),提交 message 带任务号;
> - **先红证据不豁免**(测试 commit 早于实现 commit 的 git 时序哈希对);
> - **双裁决(规格符合 ✅/❌ + 代码质量)合并到组末执行一次**,评审对象 = 该组全部 commit 的累积 diff + 该组完成信号的实跑输出;评审体按触碰面选(code-reviewer / python-reviewer / security-reviewer);
> - Critical / Important 修复后仍须复审该组;
> - 全部组完成后走一次全分支终审 → 进门三。
>
> **需要用户出场的只有 4 处**(其余全程不打扰):①任务 0.2 搬两个 API key 要点头;②9.1 M1 音色拍板;③9.2 M6 主测项需真人对话;④中途 `BLOCKED` 且涉及范围/成本/不可逆风险时。

---

## 0. 环境准备 【会话边界: 否 | 建议执行方式: 主会话亲写(安装类,授权链要求主会话执行并粘贴验证输出) | 模型档: 标准 | 完成信号: `uv sync` 成功;`python -c "import pipecat.services.soniox.stt, pipecat.services.elevenlabs.tts"` 无异常;`config.py` 启动校验通过(不报缺 key);`git check-ignore server/.env` 返回 0】
> 入口 manifest: 只读 design.md §1.6 环境准备清单 + §6.2 配置契约 + 全局约束头,不读其余节。

- [x] 0.1 改 `server/pyproject.toml` 的 extras:**保留 `whisper`**、删显式 `kokoro`,加 `soniox,elevenlabs`,版本保持 `==1.6.0`;**不得动 `evals`**(它蕴含 kokoro/moonshine,harness 侧要用)。⚠️ `whisper` 看似该删(bot 侧不再用它当 STT)但**必须留**——audio eval 靠它把 bot 音频转回中文文字,Moonshine 拿不到中文模型(§1.6 实证)。改完 `uv sync`,粘贴输出 [§1.6]
- [x] 0.2 从 `~/git/voice-translate-v2/.env` 复制 `SONIOX_API_KEY` / `ELEVENLABS_API_KEY` 到 `server/.env`;**先确认 `server/.env` 已被 gitignore**(`git check-ignore server/.env`),再写入 [§1.6][security]
- [x] 0.3 `server/.env` 填 `ELEVENLABS_VOICE_ID` 为一个**真实可用的官方多语音色 ID** 作占位(**不得用 `CHANGE_ME_` 前缀** —— `config.py:31-32` 的 `_is_missing` 会判其为缺失、启动即拒,导致后续所有 pytest/eval 跑不起来);最终值由 M1 试听后替换 [§6.2]
- [x] 0.4 验证:带 `NLTK_DISABLE_IMPORT_SECURITY=1` 跑 `python -c "import pipecat.services.soniox.stt, pipecat.services.elevenlabs.tts; print('ok')"`,粘贴输出 [§1.6]

---

## 1. 配置层与服务装配 【会话边界: 否 | 建议执行方式: 派子代理(单文件机械改动,接口签名已在 design 定死) | 模型档: 标准 | 完成信号: `server/tests/test_config.py` 全绿(含新增 U1/U2/U4/U6)+ 先红证据(测试 commit 早于实现 commit)+ ruff/pyright 通过 + **变异验证**】
> **变异验证项**:①删掉 `STT_PROVIDER`/`TTS_PROVIDER` 的白名单校验 → U6 必红;②把 1.4 的 `settings=` 改成裸构造参数(`SonioxSTTService(api_key=..., language_hints=[...])`)→ **1.4b 的 U4** 必红(这正是旧库 B19 的形态:被 `**kwargs` 静默吞掉、无异常无警告)。
> 入口 manifest: 只读 design.md §6.2 配置契约 + §6.3 服务装配契约 + §8.2 装配断言(U1/U2/U4/U6) + 全局约束头,不读管线/prompt 相关节。

- [x] 1.1 **先写测试**:在 `server/tests/test_config.py` 补 U1(`test_required_env_set_updated`,必需项恰为新 8 项:`LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`/`SLOW_LLM_MODEL`/`SONIOX_API_KEY`/`ELEVENLABS_API_KEY`/`ELEVENLABS_VOICE_ID`/`ELEVENLABS_MODEL`;`OPENAI_MODEL`/`KOKORO_VOICE_ID` 不再必需)、U2(`test_placeholder_rejected`,`CHANGE_ME_` 前缀仍判缺失)、U6(`test_provider_whitelist`,未知 `STT_PROVIDER`/`TTS_PROVIDER` 启动即拒;**放 `test_config.py` 而非 §8.2 写的 `test_dual_brain.py`** —— 本组执行时后者尚不存在,design §8.2 已同步订正),实跑确认**红** [R5/§8.2]
- [x] 1.2 改 `server/config.py`:`_REQUIRED_ENV_TO_FIELD` 换成上述 8 项;`Config` dataclass 增 `slow_llm_model`/`stt_api_key`/`stt_model`(**env 名 `SONIOX_MODEL`,非必需,默认 `stt-rt-v5` —— 旧库在用的型号,§13.1;审核指出原稿该字段无 env 来源,2026-08-02 补**)/`tts_api_key`/`tts_voice`/`tts_model`/`stt_provider`/`tts_provider` 字段;`__repr__` 对所有 `*_api_key` 一律输出 `'***'`(现有仅遮 `llm_api_key`) [R5/§6.2][security]
- [x] 1.3 `config.py` 增 `STT_PROVIDER`/`TTS_PROVIDER` 读取:**有默认值(`soniox`/`elevenlabs`)、不进必需项**,校验值 ∈ 对应 BUILDERS 键,未知值 raise `ConfigError`——沿用 `SCENARIO` 的白名单模式(`config.py:58-69`) [§6.2/§6.3]
- [x] 1.4 `server/bot.py` 增 `STT_BUILDERS` / `TTS_BUILDERS` 两张映射(各只注册在用的一家:`soniox` / `elevenlabs`),构造代码**以 design §6.3 的代码块为准**(⚠️ 审核指出:官方 registry `pipecat/cli/registry/_configs.py` 的 `SERVICE_CONFIGS` 里 soniox 那条是 `SonioxSTTService(api_key=...)` —— **无 settings、无 language_hints,正是 B19 形态**,直接照抄会踩坑;registry 只作 import 路径与 extras 名的参考);**一律走 `settings=`**,禁止把 `language_hints`/`voice`/`model` 当裸构造参数传(旧库 B19:被 `**kwargs` 静默吞掉、无异常无警告)。映射旁写注释说明"换厂商 = 加一行 + 加 extras + 改 .env",不预注册备用厂商 [§6.3][R6/PRD §7-4]
- [x] 1.4b **先写测试 + 实现验证(U4,2026-08-02 审核前移;组末评审二次订正落点)**:实际落点 `server/tests/test_bot.py::test_stt_builder_sets_language_hints_to_zh` / `test_tts_builder_sets_voice_from_config`(非本行原写的 `test_config.py::test_stt_tts_settings_take_effect`——1.4b 执行时 `test_dual_brain.py` 尚不存在,选择新建 `test_bot.py` 而非塞进 `test_config.py`,理由与用例拆分见 design.md §8.2 U4 行订正说明)—— 构造后断言 `stt._settings.language_hints` / `tts._settings.voice` 为期望值。**只断构造结果、不需要管线**,故可在本组完成(原排在第 5 组,导致本组变异项 ② 无从验证)。**先红证据例外**:测试提交(`723fc0f`)晚于 1.4 实现提交(`6681b3f`),组末评审已用独立变异验证确认用例仍有杀伤力,判定可接受 [§8.2 U4]
- [x] 1.5 更新 `server/.env.example`:加新 8 项 + 两个 PROVIDER 项 + `SONIOX_MODEL`(注释说明默认值);`SLOW_LLM_MODEL` 一项写推荐值 `gemini-3-pro`(RTM 会 grep 断言此值),删 `OPENAI_MODEL`/`KOKORO_VOICE_ID`;**只提交 `.env.example`,不提交 `.env`** [§6.2][security]

---

## 2. Prompt 契约 【会话边界: 否 | 建议执行方式: 派子代理(纯文本三段,内容已在 design 定死) | 模型档: 便宜 | 完成信号: `server/tests/test_prompts.py` 断言三段常量存在且含关键约束串,全绿 + ruff 通过】
> 入口 manifest: 只读 design.md §6.7 Prompt 契约(三段全文) + §6.6 哨兵契约 + 全局约束头,不读管线/状态相关节。

- [x] 2.1 **先写测试**:新建 `server/tests/test_prompts.py`,断言 `SLOW_BRAIN_PROMPT` 含"每条必须以句号"与"不要输出任何内容";`DUAL_BRAIN_SECTION` 含 `∅` 且**不含** `问题#`(防旧编号口径复活);拼装顺序含四段。实跑确认**红** [§6.7]
- [x] 2.2 `server/prompts.py` 新增 `SLOW_BRAIN_PROMPT`(慢脑 system,含"每条要点以句号结尾"硬约束 + "无深析价值则不要输出任何内容") [R3/§6.7①]
- [x] 2.3 `server/prompts.py` 新增 `DUAL_BRAIN_SECTION`(快脑双脑规则段:素材不得转述原文、按对话顺序理解、无可补充时只输出 `∅`);**不含**任何编号/"只消化编号最大的一组"表述 [R2/R4/§6.7②]
- [x] 2.3b **模板常量落盘(审核补:原稿把模板内联进 3.4,导致 PRD"两处必须一致"无载体)**:`prompts.py` 新增 `INJECT_POINT_TEMPLATE` 与 `INJECT_DONE_TEMPLATE` 两个常量(字面串见 design §6.1);3.4 与 7.x 的 judge 负向锚**都引用它们**,不各写各的 [R2/R3/§6.1]
- [x] 2.4 把 `DUAL_BRAIN_SECTION` 追加进现有 `SYSTEM_PROMPT` 拼装(顺序:`OFFICIAL_SECTION` + `CAPABILITY_BOUNDARY_SECTION` + `LANGUAGE_SECTION` + `DUAL_BRAIN_SECTION`),**不重构现有分段结构**;官方段"回复会被朗读,避免 emoji/项目符号"必须保留 [§6.7]

---

## 3. 慢脑状态与 Producer 谓词 【会话边界: 否 | 建议执行方式: 派子代理(函数级明确、谓词帧路由表已写死) | 模型档: 标准 | 完成信号: `test_dual_brain.py` 中本组 6 条用例全绿 + 先红证据 + ruff/pyright 通过 + **变异验证**】
> **变异验证项**(2026-08-02 审核订正——原列 4 条经回源码核对有 2 条是**假变异**,按假变异做会诱导执行者改废本来正确的用例,已重写):
> - ① 把 `basis` 比对改成恒真(`return True`)→ **`test_stale_material_dropped_before_inject` 必红**。⚠️ **不要**期待 `test_barge_in_drops_inflight_material` 变红——谓词条件是 `not aborted AND basis 一致`,打断路径由 `aborted` 半边拦下,basis 改坏不影响它(§5.2 明写 basis 分支生产帧序下不可达)。
> - ② 把 `basis` 存成 `get_messages()` 返回的**列表引用**而非 content 字符串拷贝 → 同 ①,只有 `test_stale_material_dropped_before_inject` 必红。
> - ③ 把 **`LLMFullResponseStartFrame` 分支里的 `has_material = False` 那行删掉**(而非改 dataclass 默认值——三态在 Start 帧统一重置,改默认值是 no-op)→ `test_failed_slow_turn_emits_no_completion_marker` 必红。
> - ④ 把 `InterruptionFrame` 分支里的 `aborted = True` 删掉 → `test_barge_in_drops_inflight_material` 与 `test_abort_blocks_inject_before_stt_lands` 必红(这才是打断路径的真承重点)。
> 入口 manifest: 只读 design.md §5.2 模块职责与状态迁移落点(**含谓词帧路由表**) + §6.1 注入模板 + §6.4 日志行契约 + §8.1 用例骨架(R3/R7/R8 派生条目) + **§15 PoC 记录(PoC-1/PoC-2 的 `run_test` 帧序写法可直接照搬)** + 全局约束头,不读管线装配/哨兵/eval 节。

- [x] 3.1 **先写测试**:新建 `server/tests/test_dual_brain.py`(用 `unittest.IsolatedAsyncioTestCase`,见全局约束),写 `test_material_lands_only_in_fast_context`、`test_failed_slow_turn_emits_no_completion_marker`、`test_incremental_inject_does_not_trigger`(反向:`run_llm=False` 不得增加生成次数),用官方 `pipecat.tests.utils.run_test` 做帧级断言,实跑确认**红** [R3/R4/R8/§8.1]
- [x] 3.1b **先写测试(RTM 点名、原稿漏列,2026-08-02 审核补)**:`test_both_branches_receive_user_turn`(R1 唯一结构断言:同一 user turn 后两个 context 各含该消息)、**`test_completion_marker_triggers_one_generation`**(R4 唯一结构证明:`run_llm=True` 使快脑生成次数 **1→2,精确值 2 不是 ≥2**)、`test_interruption_reaches_both_branches`(R5:打断帧两分支各收到 1 次),实跑确认**红**。⚠️ 缺 `test_completion_marker_triggers_one_generation` 等于本期唯一要验的"快慢脑配合"链路没有帧级断言,只剩人工 M6 [R1/R4/R5/§8.1]
- [x] 3.2 新建 `server/dual_brain.py`,定义 `SlowBrainState` dataclass:`has_material: bool` / `aborted: bool` / `basis: str`;`basis` 存**最后一条 `role=="user"` 消息 content 的字符串拷贝**——禁止持有 `get_messages()` 返回的列表(它是内部列表**引用非快照**,持有会使比对恒真且测试同样绿),禁止用 `len(messages)-1` 作下标(慢脑 assistant 消息会追加其后,下标会漂) [§5.2]
- [x] 3.3 实现 Producer 谓词 `async def slow_material_filter(frame) -> bool`,**严格按 design §5.2 的帧路由表**:`LLMFullResponseStartFrame`→复位三态并记 `basis`、返回 False;`TextFrame`→校验 `not aborted` 且 `basis` 一致,通过则置 `has_material=True` 返回 True,否则返回 False 并打 `stale-drop`;`LLMFullResponseEndFrame`→按 `has_material and not aborted and basis 一致` 决定;`InterruptionFrame`→置 `aborted=True` 返回 False;其余一律 False。**观测类帧必须返回 False**,否则会被 `_produce` 进快脑分支污染上下文 [R3/R7/R8/§5.2]
- [x] 3.4 实现 transformer:把慢脑要点 `TextFrame` 转成 `LLMMessagesAppendFrame(messages=[{"role":"user","content": INJECT_POINT_TEMPLATE.format(point=...)}], run_llm=False)`(**引用 2.3b 的常量,不内联字面串**),`{point}` 为 strip 后文本;完成标记帧同模板但标 `|已完成|` 且 `run_llm=True` [R3/R4/§6.1]
- [x] 3.5 **先写测试**:补 `test_barge_in_drops_inflight_material`(R7 主力)。**完整帧序写死**(审核指出原稿没说旧要点插在哪一位,放错位置会让正确实现判红):`旧轮 LLMFullResponseStartFrame` → `旧要点 A`(**应注入**)→ `InterruptionFrame` → `旧要点 B`(**应丢弃**,打 `stale-drop reason=aborted`)→ `新问题 TranscriptionFrame` → `新轮 LLMFullResponseStartFrame`。断言 A 注入、B 零注入、`abort` 日志命中;**反向断言**未打断时 B 同样正常注入、`test_stale_material_dropped_before_inject`(防御分支,手工构造"user 消息已变但无 InterruptionFrame"的帧序)、`test_abort_blocks_inject_before_stt_lands`,实跑确认**红** [R7/§8.1]
- [x] 3.6 补齐**本组宿主内**的日志行:`dispatch`/`inject`/`no-material`/`abort`/`stale-drop`(字段顺序与大小写按 §6.4 契约写死)。⚠️ `sentinel-muted` 归 4.2(宿主是 `sentinel_gate`)、`slow-failed` 与 `pipeline-error` 归 6.2(宿主是 `on_pipeline_error` handler)——本组执行者手上没有这两个宿主,不要在此实现;`turn=<n>` 为**纯日志关联序号**(慢脑每次 `LLMFullResponseStartFrame` 自增),不进模板、不承载业务语义 [§6.4]

---

## 4. 哨兵过滤器 【会话边界: 否 | 建议执行方式: 派子代理(单文件、逻辑独立,可与第 3 组并行——不同文件无符号依赖) | 模型档: 标准 | 完成信号: `server/tests/test_sentinel.py::test_sentinel_round_emits_no_text` 两向断言全绿 + 先红证据 + ruff/pyright 通过 + **变异验证**】
> **变异验证项**:①谓词写死 `return True`(全放行)→ 用例必红;②谓词写死 `return False`(全静默)→ 用例的**正向**分支(正常轮全部透出)必红——两个方向都要红,只红一边说明用例是单向的。
> 入口 manifest: 只读 design.md §6.6 哨兵契约 + §8.1 用例骨架(R6 派生条目) + **§5.1 管线结构图(仅为知道 filter 将被挂在快脑 LLM 与 TTS 之间,挂载动作归 5.2)** + §6.4 日志行契约(`sentinel-muted` 一行) + 全局约束头。

- [x] 4.1 **先写测试**:**新建 `server/tests/test_sentinel.py`**(不与第 3 组共用 `test_dual_brain.py`),写 `test_sentinel_round_emits_no_text`——哨兵轮零文本帧透出、正常轮全部透出(**两向**);另断言 `LLMFullResponseStartFrame`/`EndFrame` 在哨兵轮**仍被放行**,实跑确认**红** [R6/§6.6/§8.1]
- [x] 4.2 **新建 `server/sentinel.py`**(独立文件,与第 3 组的 `dual_brain.py` 零重叠,保证两组可并行),实现 `sentinel_gate` 谓词(**并负责 §6.4 的 `sentinel-muted` 日志行**):`LLMFullResponseStartFrame` 重置状态;本轮**首个** `LLMTextFrame` strip 后以 `∅` 开头 → 该轮所有 `LLMTextFrame` 静默;**其余帧类型一律 `return True`** —— `LLMFullResponseStart/EndFrame` 是 `ControlFrame`(`frames.py:1897,1912`),`FunctionFilter` 不自动放行(`function_filter.py:57-71` 只放行 Start/End/Cancel 与 SystemFrame),挡下它们会让快脑 assistant aggregator 收不到轮次起止钩子 [R6/§6.6]
- [x] 4.3 用官方 `FunctionFilter(filter=sentinel_gate)` 承载并从 `sentinel.py` 导出构造函数 `build_sentinel_filter()`;**挂进管线的动作归 5.2**(第 4 组时 `ParallelPipeline` 尚不存在,本组无法验证挂载)。不自造过滤器 [R6/§6.6]

---

## 5. 管线装配 【会话边界: 是 | 建议执行方式: 派子代理(多文件集成,但接口已由 3/4 组产出定死) | 模型档: 标准 | 完成信号: `bot.py -t eval` 干净启动无异常;U3/U4/U5 装配断言全绿 + 先红证据 + ruff/pyright 通过 + **变异验证**】
> **变异验证项**:①把快脑 LLM 也加进 `ignored_sources` → U5 必红(漏这条 = 面板没有对话);②从 `ignored_sources` 里去掉慢脑三件中任一 → U5 必红(漏这条 = 慢脑原文上面板,违反 R2);③把 Consumer 挪到快脑 user aggregator **之后** → U3 必红。
> 入口 manifest: 只读 design.md §5.1 管线结构(唯一承重结构图) + §5.1.1 RTVI 观测隔离 + §5.3 开场白路径 + §6.3 服务装配 + §8.2 装配断言(U3/U4/U5) + 全局约束头 + 第 3/4 组产出的符号签名,不读 eval/日志细节节。

- [x] 5.1 **先写测试**:补 U3(`test_pipeline_shape`:Consumer 在快脑 user aggregator **之前**;慢脑分支**无输出件**)、U4(`test_stt_tts_settings_take_effect`:构造后 `stt._settings.language_hints` / `tts._settings.voice` 为期望值,固化旧库 B19)、U5(`test_rtvi_ignores_slow_branch`:`ignored_sources` 恰含慢脑三件且**不含**快脑 LLM,**并同时断言 `rtvi_observer_params.user_llm_enabled is False`** —— 审核指出这条承重防线原本零断言,而 §5.1.1 自己写明该泄漏路径 eval 抓不到、判据照样全绿),实跑确认**红** [§8.2]。U4 已在第 1 组(1.4b)先行落地,本组新增 U3/U5(`test_dual_brain.py::TestAssemblePipeline`)+ 一条 T5.2 会话隔离工厂用例(`test_build_slow_material_filter_returns_independent_instances`);`bot_module` fixture 从 `test_bot.py` 挪到新建 `tests/conftest.py` 供两文件复用;三条用例均实跑确认 `AttributeError`(经 `hasattr`)断言级先红,非 import 级
- [x] 5.2 改 `server/bot.py`:按 §5.1 结构图装配 `ParallelPipeline` 双分支——公共段 `transport.input() → STT → VAD → UserTurnProcessor`,快脑分支 `Consumer → 快脑 user aggregator → 快脑 LLM → FunctionFilter(哨兵) → TTS → transport.output() → 快脑 assistant aggregator`,慢脑分支 `慢脑 user aggregator → 慢脑 LLM → SentenceAggregator → Producer → 慢脑 assistant aggregator`;两侧 aggregator 均用 `ExternalUserTurnStrategies()`;骨架照搬官方 `examples/features/features-concurrent-llm-evaluation.py` [R1/§5.1]。新增 `assemble_pipeline()` 把装配逻辑从 `run_bot()` 抽出(供 U3/U5 结构断言在不跑真实 `WorkerRunner` 的情况下直接调用)。**核实第 3 组遗留的会话隔离待办(memory `fast-slow-brain-gate2-status` 第 20/29 条)**:`dual_brain.py` 新增 `build_slow_material_filter()` 会话级工厂(比照 `sentinel.py` `build_sentinel_filter()` 同型修复——第 4 组组末评审已就 `_SentinelGate` 判过一次 HIGH),`assemble_pipeline()` 用它 + `bind_context()` 取代模块级单例,避免同进程多会话共享 `SlowBrainState`
- [x] 5.3 `PipelineWorker(rtvi_observer_params=RTVIObserverParams(ignored_sources=[slow_llm, sentence_agg, producer]))` —— 恰含慢脑三件、**不含**快脑 LLM(漏了就是慢脑原文上面板);**并显式传 `user_llm_enabled=False`**(§5.1.1:注入模板经 `messages[-1]` 泄漏到 `user-llm-text` 的路径,eval 抓不到,只能靠此参数 + U5 断言兜住) [R2/§5.1.1]
- [x] 5.4 按 §5.3 改开场白路径 [§5.3]。**落点按 design.md §5.3 正文(而非本行摘要)执行**:本行摘要"只给快脑加开场白消息"是 §5.3 初稿假设,已被同一份已签核 design.md 正文推翻(PoC-6 实测:慢脑 context 只有 system、无任何 user 消息 → 网关 400)——正文写明两个 context 各加一条(快脑正式开场白 / 慢脑 no-op 消息 `"(会话开始,用户尚未提问)"`),接住零输出分支。新增 `seed_greeting_messages()` 从 `on_client_ready` 抽出,供 5.5 测试直接驱动同一段真实逻辑
- [x] 5.5 **先写测试 + 实现**:`test_greeting_turn_emits_no_material`——开场白轮零注入帧、零完成标记、零 `slow-failed`(日志关联序号被占用属既定口径,不作断言) [§5.3/§8.1]。落点 `test_dual_brain.py::TestAssemblePipeline`;先红确认 `seed_greeting_messages` 未定义 → `AttributeError`;实现后转绿

> **变异验证(4 项,含任务卡原定②)全部实跑确认**:①`ignored_sources` 加入快脑 LLM → U5 必红(已验证:`assert set(ignored) == {...}` 失败);②`ignored_sources` 去掉慢脑三件之一(去掉 `producer`)→ U5 必红(已验证:同一断言失败);③ Consumer 挪到快脑 user aggregator 之后 → U3 必红(已验证:`Consumer 必须在快脑 user aggregator 之前`);④(本组新增,针对 5.5)`seed_greeting_messages` 去掉慢脑 no-op 消息 → `test_greeting_turn_emits_no_material` 必红(已验证:`开场白必须把慢脑 no-op 消息写入 slow_context`)。四项均已 `git diff --stat` 确认改坏 → 复原,复原后 `pytest`(33 passed)/`ruff`/`pyright` 全绿。`bot.py -t eval` 干净启动无异常(实跑日志核对 `Linking` 序列与 §5.1 结构图逐段一致,慢脑分支无 `transport.output()`/TTS)。

---

## 6. 错误处理与面板 【会话边界: 否 | 建议执行方式: 派子代理(单文件、handler 逻辑明确) | 模型档: 标准 | 完成信号: R8 三条派生用例全绿 + 先红证据 + ruff/pyright 通过 + **变异验证**】
> **变异验证项**:把 handler 里 `frame.processor is slow_llm` 的判断去掉(任何 `ErrorFrame` 都记 `slow-failed`)→ `test_non_slow_error_not_reported_as_slow_failed` 必红。这条是**防假绿专用**用例,它自己不红就等于没有。
> 入口 manifest: 只读 design.md §6.4 日志行契约 + §6.5 面板契约 + §8.1 用例骨架(R8 派生条目) + **§5.2(`has_material` 与失败时保留已注入素材的口径)** + 第 5 组产出的 `bot.py` 中 `slow_llm` 符号名 + 全局约束头,不读 eval 节。

- [x] 6.1 **先写测试**:补 `test_slow_error_does_not_stop_fast_branch`、`test_non_slow_error_not_reported_as_slow_failed`(构造 `ErrorFrame(processor=<非 slow_llm>)` → 打 `pipeline-error` 而非 `slow-failed`,**防假绿**)、`test_slow_failure_pushes_server_message`,实跑确认**红** [R8/§8.1]
- [x] 6.2 注册 `worker.on_pipeline_error` handler:**按 `frame.processor is slow_llm` 判分支归属**后记日志——**本任务负责 §6.4 的 `slow-failed` 与 `pipeline-error` 两行**(3.6 已明确不在那里实现);不做恢复、不做重试;慢脑失败时**保留已注入素材不清理**(参照 Talker-Reasoner 降级处理) [R8/§5.2/§6.4]
- [x] 6.3 慢脑失败时 push `RTVIServerMessageFrame(data={"type":"slow-brain-failed",...})`;**client 零改**(`voice-ui-kit` 的 EventsPanel 已订阅渲染 `RTVIEvent.Error` 与 `ServerMessage`) [R8/§6.5]

---

## 7. eval 场景 【会话边界: 否 | 建议执行方式: 派子代理(YAML 场景,判据已在 §8.1 定死) | 模型档: 便宜 | 完成信号: **9 个**新场景文件产出;**结构类**场景(dispatch/inject/smalltalk/supplement 的 R4-S2 支/interrupt/fault/audio)退出码 0;**质量类** judge 场景(no_leak / supersede / supplement 的 R4-S1 支)记录 judge 结论但**不阻断**(§8 本期口径:judge 判据为观察项);运行日志与时间戳留 `eval-runs/<ts>/`】
> 入口 manifest: 只读 design.md §8.0 观测层事实与判据选型 + §8.1 用例骨架清单 + §8.1.0 文本模式打断语义 + §8.1.1 eval 执行约定 + 全局约束头,不读实现代码节。

- [x] 7.0 **所有新场景的公共前置(审核补:原稿 6 个场景全缺 judge 配置,默认会去找本机没装的 Ollama)**:凡带 `eval:` 自然语言判据的场景,必须写 `judge: {eval: {factory: "judge_factory.judge_llm"}}`(照抄 `evals/r4_knowledge_qa.yaml:11-13`);运行命令固定为 `set -a && source .env && set +a && PYTHONPATH=$(pwd) uv run pipecat eval run <file> -v`(`pipecat` CLI 是全局工具、不在项目 venv,factory judge 需要这两个前置,README:104-118)[§1.2/§8.1.1]。**执行期订正**:`uv run pipecat` 实测会解析到 `server/.venv/bin/pipecat`(项目依赖只声明了 `pipecat-ai[...]`,未含 `cli` extra),报 "needs its optional dependencies (the cli extra)" 而非跑通;真正可用的是全局工具本身,即直接 `pipecat`(`/home/ky/.local/bin/pipecat`,不带 `uv run` 前缀),`PYTHONPATH=$(pwd)` 前置不变,已用 9 个场景实测确认
- [x] 7.1 新建 `server/evals/dual_brain_dispatch.yaml`(R1-S1:快脑正常应答) [R1/§8.1] —— 实跑 PASS(退出码 0),`bot.log` 命中 `[dual-brain] dispatch turn=` 2 次
- [x] 7.1b 新建 `server/evals/dual_brain_no_leak.yaml`(**R2-S1 唯一 eval 落点,原稿漏列**):judge 负向判据——输出不含模板痕迹,**锚串引自 2.3b 的常量字面值**;`∅` 不计入泄漏(§8.0)[R2/§8.1] —— 实跑 PASS(退出码 0),judge 结论 yes(未见模板痕迹)
- [x] 7.2 新建 `server/evals/dual_brain_inject.yaml`(R3-S1:注入后短窗口内 `response` `absent: true`,`within_ms` 显式设小) [R3/§8.1] —— 实跑 PASS(退出码 0,`within_ms: 6000`)
- [x] 7.3 新建 `server/evals/dual_brain_smalltalk.yaml`(R3-S2:寒暄轮整轮仅一个 `response`) [R3/§8.1] —— 实跑 PASS(退出码 0),`bot.log` 命中 2 条 `no-material`、0 条 `inject`
- [x] 7.4 新建 `server/evals/dual_brain_supplement.yaml`(R4-S1,judge)+ `server/evals/dual_brain_no_supplement.yaml`(R4-S2,结构,**拆成独立文件**——原稿建议"同一文件两轮先后测",实测发现同文件混判会让 judge 的 no 掐断后续结构轮的评估,遂拆分,避免质量类观察项误伤结构类判据) [R4/§8.1] —— R4-S2 实跑 PASS(退出码 0);R4-S1 两次实跑 judge 均给 no(快脑两次都选择输出 ∅ 无补充,合法模型行为,按§8政策记录不阻断)
- [x] 7.5 新建 `server/evals/dual_brain_interrupt.yaml`(R5-S1)与 `dual_brain_supersede.yaml`(R7-S1):**`within_ms: 70000`**(慢脑实测上界 50.3s + 余量;原 25000 会随机判超时失败) [R5/R7/§8.1] —— **两个场景文件均已按规格建好并实跑,但结构类判据 R5-S1 实测 FAIL(退出码 1)**:窗口内出现了本不该出现的第二段内容,内容对应第一个问题(CAP 定理)而非当前这一轮真正的问题。**根因(2026-08-03 主会话逐行核对 `bot.log` 时间戳后订正,推翻实现子代理最初给出的诊断)**:最初判断是"被打断的旧 turn 材料延迟到达、绕过 `aborted`/`basis` 校验放行"的时序竞争,**核实后不成立**——`inject turn=3` 距 `dispatch turn=3` 约 30 秒,与 gemini-3-pro 真实响应延迟(§13.3 实测 10–50s)吻合,并非接在 turn=1/2 的 dispatch 时间点上;且全程零 `stale-drop` 日志,说明 turn=1/2 确实被打断帧干净中止、没有材料泄漏。真正的材料就是 turn=3(当前这一轮追问自己触发的新分发)的**全新生成结果**,只是慢脑模型自己把话题内容跑偏回了更早的话题——即 `dual_brain.py` 的状态机/校验本身工作正常,缺口在于 `SLOW_BRAIN_PROMPT` 未显式限定"只分析最新一条用户消息",且连续零输出轮会让 `slow_context` 里堆出无 assistant 轮次分隔的连续 user 消息,可能进一步削弱模型对"当前该答哪一条"的判断。R7-S1(质量类 judge)同一现象,judge 也判 no(明确指出内容还在讲 CAP 定理)。**这触及已批准的 design.md §5.2"位置即归属"假设与 §6.7① 慢脑 prompt 契约,不在本组任务卡范围内修复**(本组任务卡明确不许碰 `dual_brain.py`/`prompts.py`),已记入 `docs/backlog.md` B4,2026-08-03 用户裁决:按本期"不做质量把控、整体跑通即可"口径记 backlog,不阻塞第 8/9 组
- [x] 7.6 新建 `server/evals/dual_brain_fault.yaml` + 独立 manifest(R8 故障注入)。⚠️ **注入会被 `.env` 吃掉,必须绕开**:`bot.py:45` 是 `load_dotenv(override=True)`,`.env` 值**覆盖** shell env,所以 `SLOW_LLM_MODEL=xxx uv run bot.py` 起的进程仍用 `.env` 里的真型号、注入无效但表面全绿。做法:建 `server/evals/fault.env`(整份 `.env` 副本,仅 `SLOW_LLM_MODEL=definitely-not-a-real-model-xyz`),manifest 的 `spawn` 指向它(manifest schema 无 per-run `env:` 字段,只有 `spawn:` 命令模板)。**前置校验**:日志出现 `slow-failed` 才算注入生效,否则该场景结论无效 [R8/§8.1.1][外部依赖] —— **不改 `bot.py` 的绕开方案已用最小 PoC 验证并实跑确认**:`server/evals/fault_run/{bot.py,.env}` 均为符号链接(`bot.py -> ../../bot.py`,`.env -> ../fault.env`),manifest 的 `spawn:` 先 `cd` 进该目录再以相对路径启动 bot——Python 对相对路径调用的脚本,`__file__` 就是那个相对路径本身、不解析符号链接,python-dotenv 的 `find_dotenv()` 因此从 `fault_run/` 找到并加载 fault.env 而非真实 `.env`;`dual_brain`/`prompts`/`sentinel`/`config` 靠 spawn 命令导出的 `PYTHONPATH` 指回真实 `server/` 导入,零副本零陈旧风险。实跑退出码 0,`slow-failed` 命中 3 次(turn=1/2/3),0 条虚假 `inject...done=true`,R8-S1/R8-S2 均 PASS
- [x] 7.8 新建 `server/evals/dual_brain_audio.yaml`(R6-S1 逐句分发):`user.modality: audio` + `judge.modality: audio` + **`transcription.service: whisper`**(不可用 moonshine——中文转写乱码,§1.6);断言 `tts_response` 事件次数 = 句数(确定性计数,不经 judge)。⚠️ 该场景会让 bot 真调 ElevenLabs,**每跑一次烧付费额度**,不纳入每次改动的快速回归,只在组末与门三各跑一次 [R6/§8.1][外部依赖·花钱] —— **仅写文件,未执行**(按任务边界,花钱操作留给用户本人在真实终端跑)

---

## 8. 回归验证 【会话边界: 否 | 建议执行方式: 主会话亲写(需全局视角判断回归范围) | 模型档: 标准 | 完成信号: 1 期三类基线全绿并附**本次运行**时间戳;`scripts/check_frozen_repo.sh` 通过;pytest + ruff + pyright 全绿】
> 入口 manifest: 只读 design.md §8.4 行为基线 + §9 兼容迁移与回滚 + 仓库根 `README.md:97-101`(gate set 三条命令)+ `:104-118`(starter 不在 gate 的说明 + factory judge 运行前置) + 全局约束头。

- [x] 8.1 重跑 1 期既有 eval 场景(`smoke` / `r4_no_false_completion` / `r4_knowledge_qa`),全绿;**基线范围以 README:97-101 的 gate set 为准**,`starter_text`/`starter_audio` 本就不在 gate 内(需官方 Ollama judge,本项目不装),不因本变更纳入 [R9/§8.4] —— **2026-08-03 08:19:07–08:20:40 全绿**(smoke_basic_qa 1/1 8.0s;r4_refuse_action_request judge=yes 9.3s;r4_knowledge_not_realtime judge=yes 10.1s;bot 后台日志无 traceback),日志见 `server/eval-runs/*.eval.log`
- [x] 8.2 全量 `pytest` + `ruff check .` + `pyright`,粘贴输出与时间戳 [R9] —— **2026-08-03 08:19:08–08:19:26 三项全绿**:pytest 36 passed(21 条框架自身 DeprecationWarning,非本次改动引入);ruff `All checks passed!`;pyright `0 errors, 0 warnings, 0 informations`
- [x] 8.3 跑 `scripts/check_frozen_repo.sh` 确认旧库冻结未被触碰 [R9] —— 首次运行(2026-08-03 08:19:14)误报 FAIL,主会话独立核查证实系脚本 `BASELINE_SHA` 过期导致假阳性(见 design.md §1.1 脚注),经用户批准订正基线后于 **2026-08-03 08:30:32 通过**(commit `d2939d7`)
- [ ] 8.4 **文档消费点收口(§9 点名、原稿漏列)**:①更新仓库根 `README.md:33,35,68-73` 的服务说明表(Whisper/Kokoro → Soniox/ElevenLabs)——门三 G1 回执会查"README 反映现状";②删除 `server/prompts.py:32-33` 那条已过时的注释("WhisperSTTService 硬锁 ZH",design §9 明写留着会成为误导后人的假事实);③`docs/backlog.md` 的 B2 条目按 M3 联测结论回写 [§9] —— **①②已完成**(commit `c1de027`,2026-08-03;B2 段落改写为"待 M3 复验",未下结论);**③待第 9 组 M3 人工联测结论后回写,本条暂不勾选**。附带发现 README.md:19"5 个必填环境变量"表述亦过期(实际 8 个,缺 `SLOW_LLM_MODEL` 一行),超出①②点名范围,组末评审判 MEDIUM 后已顺手修复(commit `e249422`),已记入台账(通用教训仍保留,不因本例修复而撤销)

---

## 9. M 组人工联测 【会话边界: 是 | 建议执行方式: 主会话亲写(需与用户实时交互) | 模型档: 标准 | 完成信号: M1 音色拍板并回填 `ELEVENLABS_VOICE_ID`;M6 主测项判通;M2/M3/M4/M5/M7/M8 结论逐条记录】
> 入口 manifest: 只读 design.md §8.3 人工联测清单 + §6.6 哨兵已知限制 + 全局约束头。
> **纪律**:用户明确要求需他配合的测试**一次性集中做完**,不得分散打断。开跑前先确认前 8 组全部完成且基线全绿。

- [ ] 9.1 M1 音色试听:预选 2–3 个 ElevenLabs 中文候选音色,同一句中文各合成一遍供用户拍板,回填 `ELEVENLABS_VOICE_ID` [§8.3]
- [ ] 9.2 **M6 本期主测项**:完整一轮真机对话验"配合"——深问题 →(约 2s)快脑简答 → 用户保持沉默约 15s → 补充自动到来;同屏 `tail -f bot.log`。只判链路通不通(补充出现、非首答复读、无模板痕迹),**不判内容好坏**。若补充没出现先看日志有无 `abort` 行:有 = 等待期被环境噪声触发 VAD、本轮正常中止 → 判误触发重跑,不是缺陷 [§8.3]
- [ ] 9.3 M2 慢脑失败面板提示可见性 / M3 多句回复无重叠卡死(**顺带目视面板是否逐句刷新**,原 M7 并入此项)/ M4 真机打断日志时序 / M8 `∅` 面板闪现观感——逐条记录结论。**M7 已删**:逐句分发改由 `dual_brain_audio.yaml` 自动断言(§8.1) [§8.3]
- [ ] 9.4 M5 `developer` 角色注入是否被 8045 网关接受:跑一次记录结论,**本期不据此改动**(为后续变更留数据) [§8.3/§6.1]

---

## 待入台账

> 实现期发现的流程/规则问题写此栏,门三 retro 从此栏 flush 进 `~/docs-project/process-issues-global.md`。

- 2026-08-02 第 3 组组末评审(python-reviewer 独立复现):T3.1b 三条用例(`ebba943`)commit message 写"实跑确认红",但用 `git worktree` 复现该提交点显示当时 6 passed、从未经历红色阶段(`dual_brain.py` 的 dataclass/谓词/transformer 在 T3.1b 之前均已落地)。用例本身不是重言式(已被独立变异验证证明有鉴别力),判定为过程证据表述失实而非功能缺陷,不阻断本组 PASS,记台账留痕。拟改规则:RTM 点名补录类"针对已存在实现补断言"场景,commit message 应如实写"补断言,无先红阶段"而非套用先红模板措辞。
