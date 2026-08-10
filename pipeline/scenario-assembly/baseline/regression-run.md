# T-4 · 回归与行为等价证据(SA-17 / SA-18)

> change_id: scenario-assembly | 产出: backend-dev T-4 | 日期: 2026-08-10

## SA-17 · 全量 pytest（FR-9）

命令:
```bash
cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest -q
```
结果(交付前最后一次实测，本卡未改任何 server/*.py 或既有测试，只新增/改了 server/evals/ 下文件):
```
136 passed, 55 warnings in 5.84s
```
退出码 0。不劣于基线 70 passed(基线 = 2026-08-10 实测 70 passed),T-1/T-2/T-3 累计新增 66 条,无新增失败。

## SA-18 · 开启态复跑 r4_*/dual_brain_*（FR-4/FR-9,manual）

运行画像:`SCENARIO=voice_chat`(默认模板)、`DUAL_BRAIN_ENABLED=true`(仅本次运行导出的环境变量,`server/.env` 本身不含该键,未被修改)。

启动命令:
```bash
cd /home/ky/git/voice-agent/server
set -a && source .env && set +a
export DUAL_BRAIN_ENABLED=true NLTK_DISABLE_IMPORT_SECURITY=1 SCENARIO=voice_chat
uv run python bot.py -t eval
```
启动日志确认开启态生效:
```
[scenario] template=voice_chat stt=deepgram/stt-rt-v5 tts=cartesia/... fast_model=gemini-3.6-flash-low dual_brain=on
```

复跑命令(单进程内连跑,eval transport 会话间保持同一 bot):
```bash
set -a && source .env && set +a
export NLTK_DISABLE_IMPORT_SECURITY=1 PYTHONPATH="$(pwd)"
pipecat eval run \
  evals/r4_knowledge_qa.yaml evals/r4_no_false_completion.yaml \
  evals/dual_brain_dispatch.yaml evals/dual_brain_inject.yaml \
  evals/dual_brain_interrupt.yaml evals/dual_brain_no_leak.yaml \
  evals/dual_brain_no_supplement.yaml evals/dual_brain_smalltalk.yaml \
  evals/dual_brain_supersede.yaml evals/dual_brain_supplement.yaml -v
```

**说明:`evals/dual_brain_audio.yaml` 排除在本次复跑之外**——该文件头部本身写明"DO NOT RUN THIS SCENARIO...every run burns real paid ElevenLabs quota...only the user may execute a cost-incurring run"，这是本项目既有的、独立于本次变更的约定，本卡不越权代跑，非本卡遗漏。

原样输出摘要(逐场景):

| 场景 | 结果 | 备注 |
|---|---|---|
| r4_knowledge_not_realtime | ✓ passed (9128ms) | |
| r4_refuse_action_request | ✓ passed (15659ms) | |
| dual_brain_dispatch | ✓ passed (7361ms) | |
| dual_brain_inject | **✗ failed** (10137ms/8616ms，两次复现一致) | 见下方根因分析 |
| dual_brain_interrupt | ✓ passed (78351ms) | |
| dual_brain_no_leak | ✓ passed (10979ms) | |
| dual_brain_no_supplement(`simple_question_silent`) | ✓ passed (34636ms) | |
| dual_brain_smalltalk | ✓ passed (27079ms) | |
| dual_brain_supersede | ✓ passed (16317ms) | |
| dual_brain_supplement | ✓ passed (12748ms) | |

汇总:第一次批跑 `9/10 passed, 1 failed · 3m 42s`；对 `dual_brain_inject` 单独复跑一次确认非偶发:`0/1 passed, 1 failed · 8.6s`，两次失败原文一致:
```
turn 2 expectation 0 (llm_response): expected no 'llm_response' within 6000ms, but one arrived:
  补充来看，工程实践中常结合BASE理论，通过最终一致性来换取高可用性。
```

**根因分析(边界判定,design.md 停下条件②)**:`dual_brain_inject.yaml` 断言"慢脑补充轮不得在 6000ms 内到达"，该阈值是该文件作者在设计期按"慢脑最快观测完成时间"手工估算写死的常量（见该文件自身注释："a within_ms window that's clearly inside the... period, well under the slow brain's fastest observed completion"）。本次两次复跑里，`SentenceAggregator`/`SlowBrainLLM` 链路本身未被 T-1/T-2/T-3 触碰（契约 §0.4 只改 `assemble_pipeline` 的分支装配，不改 `dual_brain.py` 内部流式/时序逻辑，`SLOW_BRAIN_PROMPT` 契约锁定"内容与唯一事实源地位均不变"，本次启动日志中的 `SlowBrainLLM` system_instruction 与历史值逐字一致），失败原因是**当前 `SLOW_LLM_MODEL` 配置的模型响应速度快于该 6000ms 窗口**，与本次变更改动的护栏句位置（R-2）、模板/prompt 装配逻辑均无关——不满足"eval 复跑失败且根因指向护栏句位置变更"的打回条件，因此本卡不打回 T-1/T-2/T-3，也不修改 `dual_brain_inject.yaml`（既有 eval 内容锁定，不在本卡改动范围）。已记入下方 RISKS，交派单方定夺（例如另开小任务把该阈值改成基于事件而非固定毫秒数，或核实 `SLOW_LLM_MODEL` 是否被换成了明显更快的模型）。

R8 故障场景(`dual_brain_fault`,独立 fault_run 进程):
```bash
set -a && source .env && set +a
PYTHONPATH="$(pwd)" pipecat eval suite evals/dual_brain_fault.manifest.yaml \
  --name dual_brain_fault-20260810_184504
```
结果:`1/1 passed · 52.1s`。硬性前置校验(design §8.1.1):
```bash
grep 'slow-failed' eval-runs/dual_brain_fault-20260810_184504/logs/*.log
```
命中 3 行(turn=1/2/3 均记录 `[dual-brain] slow-failed`，含 token 配额错误原文)，确认故障注入真实生效，非静默失效。

**SA-18 结论**:11 个复跑场景中 10 个通过（含 R8 故障场景），`dual_brain_inject` 1 个失败，根因是模型响应速度与硬编码时序阈值的匹配问题（环境/配置层面），与本次护栏句位置变更（R-2）及模板/装配改动均无因果关系，已如实记录，不代为改测试凑绿。

## 补充:`dual_brain_inject` 阈值修复与复跑(2026-08-10,用户拍板顺手解决,不留债务)

上述失败被用户拍板确认为"时序断言假设过时"（非本次装配变更引入的回归），要求直接放宽 `within_ms` 阈值解决。修复过程与依据:

启动同一开启态 bot(命令同 SA-18 上方"启动命令"),用
```bash
set -a && source .env && set +a
export NLTK_DISABLE_IMPORT_SECURITY=1 PYTHONPATH="$(pwd)"
pipecat eval run evals/dual_brain_inject.yaml -v
```
连续复跑 10 次采集真实耗时,grep bot 日志 `[dual-brain] dispatch turn=` 与 `[dual-brain] inject turn=.* done=true` 的时间差(问题派发到完成标记触发合法第二轮的间隔):

```
1529ms, 2151ms, 2191ms, 1383ms, 1783ms, 1519ms, 1756ms, 1402ms, 1784ms, 1312ms
```

最快观测完成时间 = 1312ms(当前 `SLOW_LLM_MODEL=gemini-3.6-flash-high`),远低于原 6000ms 安全窗口,证实根因确系阈值假设过时,与本次场景装配改动(护栏句位置/模板/装配逻辑)无关。

**处置**:`server/evals/dual_brain_inject.yaml` 的 `within_ms` 由 `6000` 改为 `800`(留出约 39% 安全边际,明显低于 10 次实测最快完成时间 1312ms),同步更新文件顶部注释以反映新的实测依据,不再是设计期的手工估算值。

**复跑验证**:改后连续复跑 3 次,均 `1/1 passed`(退出码 0),`turn 2` 断言显示 `no 'llm_response' for 800ms`,不再 flaky。

若后续 `SLOW_LLM_MODEL` 更换为更快的模型,该阈值需重新实测下调,而非直接调大掩盖问题(已在 yaml 注释中留言提醒)。

## 附:`dual_brain_fault.manifest.yaml` 注释同步(R-5)

已在该文件注释里补充"前提条件":慢脑默认停用，`evals/fault.env` 必须显式含 `DUAL_BRAIN_ENABLED=true`（本机由用户手工加，未改真实内容，只改了注释）；顺带修正该文件注释里一处过期命令（`eval suite` 不接受 `-v`，去掉了这个已确认会报错的旧参数）。

## 附:环境修复记录(非项目依赖变更)

`server/evals/scenario_persona_english_tutor_audio_en.yaml` 首次运行时，全局 `pipecat-ai` CLI 工具自身的 venv 缺 `requests`/`kokoro_onnx`/`moonshine-voice` 等 evals 可选依赖（`uv tool install pipecat-ai[cli]` 未带 `evals` extra），已用 `uv tool install "pipecat-ai[cli,evals]==1.6.0"` 补齐（同版本号重装，未升级 pipecat 版本，不影响 `server/` 项目自身的 `pyproject.toml`/`uv.lock`，纯粹是本机全局工具环境的缺口修复，非本次变更的项目依赖）。
