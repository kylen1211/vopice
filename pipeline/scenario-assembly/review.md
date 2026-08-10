# scenario-assembly · review.md

> change_id: scenario-assembly | 产出: code-reviewer s6 | 日期: 2026-08-10
> 范围: Base `8d11dd2` → HEAD(`cd4d143`),依据 `review-package.diff`(61 files)、`contract/cases.md`、`design.md`、`tasks/T-1..T-4.md`
> 方法: 全量读 diff 的生产代码与测试段;对 diff 内无法裁断的 4 处(`run_bot` 函数体是否残留模块级 `cfg`、`_validate_provider` 报错文案、STT builder 是否读 `c.stt_model`、override 合并字段的测试覆盖)读了 `server/bot.py`/`server/config.py` 原文与 `server/tests/` 做定点核查,已在各条注明。未重跑全量测试。

---

## 一、规格符合裁定

| 维度 | 裁定 | 依据 |
|---|---|---|
| 契约 §0.1 注册表(INV-1/3/4/5) | ✅ | `server/scenarios.py:69-116` import 期自检;INV-5 由 `ScenarioTemplate` 固定字段集结构性保证(注释已说明) |
| 契约 §0.1 INV-2(落 config.py) | ✅ | `server/config.py:94-102` 模块 import 期 `ConfigError`,依赖方向正确(未让 `scenarios` 反向 import `config`) |
| 契约 §0.2 v1 模板集合 + C-1…C-5 文案约束 | ✅ | `server/scenarios.py:120-139`;`server/prompts.py:23-35`(身份段)/`:63-78`(语言段);文案与 `research/tutor-persona-final.md` 一致(qa 已逐字比对) |
| 契约 §0.3 配置(优先级/条件必需/五步校验/assemblyai) | ✅ | `server/config.py:203-283` 五步顺序与契约逐条对应;`_DUAL_BRAIN_REQUIRED_ENV`/`_STT_PROVIDER_REQUIRED_ENV["assemblyai"]` 到位 |
| 契约 §0.3 会话级原子性(两行紧邻无 `await`) | ✅ | `server/bot.py:604-605`,其间无 `await`;`run_bot(…, cfg: Config)` 形参遮蔽模块级 `cfg`,`assemble_pipeline` 实参为会话快照(读 `server/bot.py:546-591` 原文核实) |
| 契约 §0.4 两态装配形状 / 错误归因 / ignored_sources / 问候 | ✅ | `server/bot.py:406-478`;关闭态单链顺序与契约表逐件一致;归因判断式含 `slow_llm is not None`(`:247`) |
| 契约 §0.4 观测日志行 | ⚠️ | 格式逐字符合契约,但 `stt=<model>` 段打的不是生效模型(见 Important-1) |
| 契约 §0.5 段序 / 不可覆盖段 / 防漂移 | ✅ | `server/scenarios.py:152-166`;`OFFICIAL_SECTION`/`SYSTEM_PROMPT` 派生化使 `test_prompts.py` 零改动通过 |
| ADR-8 B-1…B-4 | ✅ | `server/bot.py:115-138` 惰性 import、不传语言参数、不读 `c.stt_model`、不传 `vad_force_turn_endpoint` 四条全中 |
| 越界改动 | ✅(生产/测试侧无越界) | `server/tests/` 仅动 conftest/test_bot/test_config/test_dual_brain,与 design R-6 白名单四条逐条对应;`test_dual_brain.py` 恰 6 处切 fixture、断言一字未动;`test_prompts.py` 零改动 |
| 越界改动(evals + 仓库杂项) | ⚠️ | `server/evals/dual_brain_inject.yaml` 被改(design 影响面表明写"文件不改")、`.gitignore` 与 `pipeline/task-dispatch/baseline/*.json` 混入本变更范围(见 Minor-3/Minor-4) |
| TDD 证据 | ⚠️ | 四卡均为"测试+实现同 commit",无独立 RED commit;RED 证据只存在于实现回执文字(T-1 `file not found`、T-2 `13 deselected`、T-3 `4 failed`),包内不可复核。按纪律不构成打回项,但记 ⚠️ 交派单方知悉 |
| SA-19 音频留痕 / design R-14 | ⚠️ | 契约 SA-19 要求"留存转写与音频";转写已留(`baseline/persona-samples.md:58-64`),音频与 TTS 听感按项目"付费 round-trip 只由用户本人跑"惯例未取,已在 `persona-samples.md:78-102` 如实标注未完成。属用户自测项,不判失败,但放行时应显式承认 SA-19 只完成一半 |
| 契约档位 | ✅ | 见第四节 |

---

## 二、做得好的

1. **ADR-3 的兼容派生手法把 FR-9 代价压到零**:`prompts.py:37` 把 `OFFICIAL_SECTION` 改成 `IDENTITY_DEFAULT_SECTION + "\n\n" + VOICE_SAFETY_SECTION` 的派生常量,`SYSTEM_PROMPT` 组合式不动,于是 `test_prompts.py` 6 条逐字未改仍通过,同时 `test_scenarios.py::test_drift_system_prompt_matches_build_system_prompt` 把"两处同值"绑死。这是"重构不动既有断言、又不留双事实源"的教科书写法。
2. **错误归因的坑被正面钉死**:`bot.py:247` 的 `slow_llm is not None and frame.processor is slow_llm` 配 `test_scenario_assembly.py::test_error_attribution_processor_none_is_not_slow_failed`,直接复刻关闭态 `(None, None)` 调用形态,断言"不出现 slow-failed + 不向面板 push",而不是只断言"走了 else 分支"。这是本变更最容易埋雷的一处,处理得比契约要求更实。
3. **SA-04 真的走了端到端链路**:`test_scenario_assembly.py::test_template_drives_prompt_and_service_construction` 经 `load_config()` → `assemble_pipeline()` 后用 `isinstance(..., AssemblyAISTTService)` 断言真实构造对象,没有用手工 dataclass 绕过(P55);且身份段用"含/不含"双向锚而不是"整串不相等"蒙混。
4. **AssemblyAI builder 的"防照抄邻居"注释**:`bot.py:115-133` 把"为什么这里故意不锁 `Language.ZH`"写在了后人最可能改错的那一行旁边,而不是只写在设计文档里。SA-23 又用 `_build_ws_url()` 的 query 串做运行期证据,堵住"Settings 上没设但别处偷偷拼进 URL"的绕过。
5. **T-4 在第一现场没有改测试凑绿**:`dual_brain_inject` 首跑失败时 `regression-run.md:68` 明确写"不修改 yaml,记 RISKS 交派单方定夺",等用户拍板后才动手,并补了 10 次真实耗时采样作依据。这是流水线纪律执行到位的样本。

---

## 三、发现

### Critical
无。

### Important

**Important-1 · `[scenario]` 观测行打的 STT 模型不是生效模型,会把 D-020 的排查带偏**

- 位置:`server/bot.py:280-284`(日志行)、`server/bot.py:100-111`(`_build_deepgram_stt`)、`server/bot.py:115-138`(`_build_assemblyai_stt`);现场证据 `pipeline/scenario-assembly/baseline/regression-run.md:130`、`:30`、`:122`
- 问题:该行打 `stt={cfg.stt_provider}/{cfg.stt_model}`,而 `cfg.stt_model` 只被 `_build_soniox_stt`(`bot.py:96`)消费。deepgram 与 assemblyai 两个 builder 都**完全不读**它。真机日志因此出现 `stt=assemblyai/stt-rt-v5`(实际 `universal-3-5-pro`)与 `stt=deepgram/stt-rt-v5`(实际 Deepgram 默认 `nova-3-general`)。
- 影响:这一行是 design ADR-1 第 3 点/契约 §0.4 指定的 FR-3/FR-8 运行期唯一可观测锚,ADR-5 代价一节还专门把它当作"环境变量被静默忽略"的缓解手段——现在它自己成了误导源。具体失败场景已经在队列里:`debts.md` D-020 记的正是 AssemblyAI 中英混说识别准确度,后续谁去查这条债,读到 `stt=assemblyai/stt-rt-v5` 就会去核对一个根本没被使用的模型档位名。
- 归因:**部分计划所致**——契约 §0.4 字面就写 `stt=<provider>/<model>`,而 `Config` 上只有 `stt_model` 一个模型字段,实现是照字面落的。
- 建议:两条路任选。①按 design R-15 已铺好的方向,加一张 per-provider 默认模型表(`{"soniox": cfg.stt_model, "deepgram": "nova-3-general", "assemblyai": "universal-3-5-pro"}`)供日志与 builder 共用一个事实源;②若认为现在做①属超范围,至少在 `debts.md` 记一条"观测行的 stt model 段对非 soniox provider 失真",并把契约 §0.4 该字段的语义从"生效模型"降表述为"`Config.stt_model` 取值"。不建议原样放行且不留痕。

**Important-2 · ADR-5 生效值合并的四条路径里,只有 `stt_provider` 有覆盖用例;`fast_llm_model` 全项目零断言**

- 位置:`server/config.py:265-274`(四条合并表达式)、`server/bot.py:302`(`model=cfg.fast_llm_model`);覆盖面核查见 `server/tests/`(已 grep `fast_llm_model|stt_model|tts_voice|tts_model`,除 `test_bot.py::_make_config` 的构造默认值外无任何断言)
- 问题:`stt_model = template.services.stt_model or env_stt_model`、`tts_voice = template.services.tts_voice or values.get("tts_voice")`、`tts_model = …`、`fast_llm_model = template.services.fast_llm_model or values["llm_model"]` 这四条是 ADR-5"模板 > 环境变量 > 内置默认"的全部落点。v1 两个模板只声明了 `stt_provider`,所以这四条**没有任何用例走到过模板分支**;`cfg.fast_llm_model` 更是连"等于 `LLM_MODEL`"这种默认路径断言都没有。
- 影响:把 `bot.py:302` 改回 `model=cfg.llm_model`,或把 `config.py:274` 改成 `fast_llm_model = values["llm_model"]`,现有 136 条测试**全绿**。而 ADR-5 单列 `fast_llm_model` 的唯一理由就是防"换个陪练模板静默把派活委派轮模型也换掉"(P50 越界副作用),这条防线现在没有任何机械保障。同理,`tts_voice` 的合并若写反(env 优先于模板),契约"模板覆盖 tts_voice 时凭证仍必需、取值以模板为准"这条也无人发现。
- 归因:**部分计划所致**——契约 SA-04 那句"其余声明了覆盖的字段(model/voice)逐字段等于模板定义"在 v1 模板集合下是空条件,契约没预留验证钩子。
- 建议:在 `tests/test_config.py` 加 1 条用例即可闭合:`monkeypatch.setitem(scenarios.TEMPLATES, "voice_chat", ScenarioTemplate(id="voice_chat", label="x", identity_section=prompts.IDENTITY_DEFAULT_SECTION, services=ServiceChoice(stt_model="m1", tts_voice="v1", tts_model="m2", fast_llm_model="fast-1")))`,然后断言 `cfg.stt_model=="m1" and cfg.tts_voice=="v1" and cfg.tts_model=="m2" and cfg.fast_llm_model=="fast-1" and cfg.llm_model==<env 值>`(最后半句正是 P50 那条防线)。另可在 `test_scenario_assembly.py` 顺带断言 `assembled.fast_llm._settings.model == cfg.fast_llm_model`。

### Minor

**Minor-1 · `dual_brain_inject` 的 `within_ms` 从 6000 收到 800,窗口已窄于它要观测的现象,且 D-012 未同步更新**

- 位置:`server/evals/dual_brain_inject.yaml:38`;依据 `baseline/regression-run.md:84-106`
- 问题:实测慢脑完成 1312-2191ms(n=10),取 800ms 只剩 512ms 余量,而这是一次真实 LLM+网络往返;同时该窗口内是否真的发生过 `done=false` 渐进注入并无 gating 校验(文件头注释自己写明这条是 optional side evidence),窗口越窄这条场景越接近空断言。
- 影响:SA-18 的"行为等价证据"在这一条上被削弱;后续 flaky 复发时容易被再次当成"阈值过时"继续调数值。
- 归因:计划所致(用户拍板放宽)。
- 建议:不必回退本轮改动,但把断言改成事件锚定(断言"第一条 `done=false` 注入 → `done=true` 之间无 `llm_response`")更稳;至少把新的 800ms 依据并进 `debts.md` D-012(该条现仍描述旧的 `dual_brain_inject/interrupt` 时序 flaky,与现状脱节)。

**Minor-2 · 关闭态"保留件 `sentinel_filter`"与单链逐件顺序无断言**

- 位置:`server/tests/test_scenario_assembly.py:120-141`(`test_dual_brain_off_degrades_pipeline_to_single_chain`);契约 §0.4 关闭态表"保留件"一行
- 问题:该用例断言了五个 `None`、无 `ParallelPipeline`、无 `DUAL_BRAIN_SECTION`、`ignored_sources==[]`、`user_llm_enabled is False`,但没断言 `sentinel_filter` 仍在链上,也没逐件核对契约给的 11 段顺序(`injector` 位置由 SA-15 间接覆盖到 `injector < fast_llm` 为止)。
- 影响:若后人"顺手简化"把关闭态的 `sentinel_filter` 摘掉(它在关闭态确实走不到静音分支,是最容易被当作冗余删掉的一件),没有任何用例会红。
- 建议:`assert any(p is assembled_sentinel …)` 需要句柄,最省事的做法是把关闭态 `pipeline.processors` 的类型序列与契约表对一次(`[type(p).__name__ for p in …]`)。属超出 SA-05 字面判据的加固,交派单方定夺。

**Minor-3 · `server/evals/dual_brain_inject.yaml` 的改动落在 design 明写"文件不改"的清单内**

- 位置:commit `5f4c26d`;`design.md` 影响面表 `evals/r4_*.yaml、dual_brain_*.yaml、dispatch_*.yaml | 文件不改，只改运行画像`;`tasks/T-4.md:18` 同款措辞
- 问题:同轮的 `dual_brain_fault.manifest.yaml` 改动是被 design R-5 显式授权的("注释同步"),`dual_brain_inject.yaml` 不是。虽有用户口头拍板,但 design.md 的这一行未随之修订,留下"文档说不改、仓库已改"的不一致。
- 建议:在 `design.md` 影响面表或 `ledger.md` 补一行修订记录点明该例外及其拍板出处,别让下一次 review 重新纠结一遍。

**Minor-4 · 与本变更无关的历史产物混进了本变更的 commit 区间**

- 位置:commit `ce1d961`(s1a) 引入 `pipeline/task-dispatch/baseline/failure-path-samples.json`(3110 行)、`pipeline/task-dispatch/baseline/mcp-event-sample.json`(663 行)、`.gitignore` 新增 `graphify-out/` `.obsidian/`
- 问题:这三项属上一变更/环境杂项,占了本次评审包 8418 行新增里的 ~45%,也让"revert 本变更"的边界变糊。已扫过两份 JSON 无密钥类字符串(`sk-*`/`api_key`/`bearer`/`token` 模式零命中),无安全问题。
- 建议:纯卫生项,后续 s1 阶段的仓库整理与变更提交分开 commit 即可。

**Minor-5(nit)· `.env.example` 的 AssemblyAI 占位符大小写与全文不一致**

- 位置:`server/.env.example:75` `# ASSEMBLYAI_API_KEY=CHANGE_ME_assemblyai_api_key`
- 问题:同文件其余占位符一律 `CHANGE_ME_大写`(如 `CHANGE_ME_SONIOX_API_KEY`)。`_is_missing()` 只判前缀,功能无影响。
- 建议:改成 `CHANGE_ME_ASSEMBLYAI_API_KEY`。

---

## 四、契约档位复核

- design.md 声明档位 = `cases`,`ledger.md::contract_tier = cases`。
- 实际改动面:零 HTTP 接口、零新增 CLI 命令、零 UI(`client/` 未触达)。对外可见面 = 环境变量 → 模板 → 装配出的服务对象与 prompt,与 design「接口契约」一节的定档理由一致。
- 契约产物齐备:`contract/cases.md` 含 §0.1–§0.5 + §1 共 23 条用例(19 机检 + 4 manual),19 条已生成 `generated/cases/SA-*.sh` 且 qa 实测 19/19。
- **结论:无降档,档位判定与实现面匹配。**

---

## 五、总裁定

**BLOCK(pass=false)**——无 Critical,存在 2 条 Important。

两条 Important 都是**增量补丁**、不涉及返工:Important-1 是一行日志的事实源问题(改代码或改契约+记债二选一),Important-2 是补 1 条 config 用例把 ADR-5 的 P50 防线钉住。其余 5 条 Minor 与 3 处 ⚠️(TDD 无独立 RED commit、SA-19 音频留痕缺失、`dual_brain_inject.yaml` 与 design 文档不一致)交派单方定夺,不构成阻断。

实现质量整体高于本项目均线:契约 23 条判据逐条落到可执行用例、既有测试白名单零越界、`test_prompts.py` 逐字未改通过、危险处(错误归因、builder 语言锁、会话级原子性)都用注释把"为什么不能这么改"钉在了改错的必经之路上。

---

# 复评 · 第 1 轮修复(code-reviewer,2026-08-10)

> 范围: 只裁定上轮 2 条 Important 与修复 diff `pipeline/scenario-assembly/fix-round1.diff`(Fix base `cd4d143` → Head `adc523b`,3 文件 +101/-1)。不重新全量评审。
> 方法: 读 diff 全文 + 读 `server/bot.py:91-165/295-302`、`server/config.py:255-283` 原文;核实生效模型表的两个字面值来源;实跑 `cd server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest -q` → `138 passed`、`uv run ruff check` → `All checks passed`。

## 一、逐条裁定

**Important-1 · `[scenario]` 观测行打的 STT 模型不是生效模型 —— ADDRESSED**

- 修法落地:`server/bot.py:155-157` 新增 `_STT_EFFECTIVE_MODEL_OVERRIDES`,`:161-163` 新增 log-only 的 `_effective_stt_model(cfg)`(soniox 走 `cfg.stt_model`,其余查表);`server/bot.py:300` 日志行改用该函数。
- 原缺陷不复存在:非 soniox provider 下观测行不再打 `cfg.stt_model` 这个没人消费的 soniox 档位名。
- 表值经独立核实(不采信回执宣称):`server/.venv/lib/python3.11/site-packages/pipecat/services/deepgram/stt.py:352` 的 `default_settings` 确为 `model="nova-3-general"`,与 `_build_deepgram_stt` 不传 model 的写法一致;`universal-3-5-pro` 与 `server/bot.py:138` 写死值一致。
- B-3 硬约束未被破坏:`server/bot.py:91-141` 三家 builder 构造参数一字未动,新函数不出现在任何 Service 构造路径上。
- 回归护栏:`server/tests/test_scenario_assembly.py:248-278` 三种 provider 逐一核对返回值,并用 `_capture_logs()` 断言真实日志行含 `stt=deepgram/nova-3-general` —— 把日志行改回 `cfg.stt_model` 会直接变红。

**Important-2 · ADR-5 生效值合并四条路径零覆盖、`fast_llm_model` 全项目无断言 —— ADDRESSED**

- 修法落地:`server/tests/test_config.py:470-501` 用 `monkeypatch.setitem(scenarios.TEMPLATES, "voice_chat", ScenarioTemplate(..., services=ServiceChoice(stt_model="m1", tts_voice="v1", tts_model="m2", fast_llm_model="fast-1")))`,断言四个字段全等于模板覆盖值。
- 原缺陷不复存在:`server/config.py:261-267` 四条合并表达式的**模板覆盖分支**现在被真实走到(断言值只有走该分支才成立);`fast_llm_model` 从"全项目零断言"变为两处覆盖 —— 合并结果(config 层)+ 落地到构造对象(`server/tests/test_scenario_assembly.py:117-118` 断言 `assembled.fast_llm._settings.model == cfg.fast_llm_model`)。
- P50 防线钉住:同一用例断言 `cfg.llm_model == NEW_REQUIRED_ENV["LLM_MODEL"]`,即"模板覆盖 `fast_llm_model` 不得连带改派活委派轮模型"这条 ADR-5 单列理由现在有机械保障。

## 二、修复 diff 内新引入的破坏

- **Critical:无。Important:无。**
- **Minor · 生效模型表的两个字面值与真实来源无机械绑定**
  - 位置:`server/bot.py:156-157`;对照 `server/bot.py:138`、`server/.venv/lib/python3.11/site-packages/pipecat/services/deepgram/stt.py:352`
  - 失败场景:pipecat 升级把 Deepgram 默认模型从 `nova-3-general` 换掉(该默认历史上换过档),或有人改 `_build_assemblyai_stt` 里写死的 `universal-3-5-pro` —— 观测行重新说谎,而 `test_scenario_assembly.py:262/271` 断言的是同一份字面值,不会变红。这正是 Important-1 修掉的那类失真,只是从"两处不一致"变成"三处需手工同步"。
  - 建议(非阻断):assemblyai 侧最省事 —— 断言 `assembled.stt._settings.model == bot_module._effective_stt_model(cfg)`,把表和构造对象绑在一起;deepgram 侧要么在测试里实例化一次 `DeepgramSTTService` 取其默认值比对,要么让 builder 显式传 model(属行为变更,须派单方拍板)。
- 其余检查:commit `adc523b` 只含 3 个文件,与回执一致;无越界改动、无密钥类字符串、无未改动代码被顺手重构。

## 三、范围外观察

- 无新增。上轮 5 条 Minor 与 3 处 ⚠️(TDD 无独立 RED commit、SA-19 音频留痕半完成、`dual_brain_inject.yaml` 与 design 文档不一致)本轮 diff 未触及,按派单不重新裁定,仍为非阻断遗留项。

## 四、轮裁定

**全清(pass=true)** —— 2 条 Important 均 ADDRESSED,修复 diff 内无新增 Critical/Important 破坏,全量 138 passed(修复前 136)+ ruff 全过。唯一新增的 Minor(生效模型表字面值无机械绑定)与上轮遗留项一并交派单方定夺,不构成阻断、不延长修复环。
