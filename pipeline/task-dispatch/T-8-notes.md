# T-8 backend-notes · 真机联测与验收报告

> owner: qa-tester(卡首声明),本轮由 backend-dev 节点执行(主会话指派)。
> change_id: task-dispatch | 日期: 2026-08-09

## 开工第一步(主会话授权)

已按指示将 T-7 交付的5个 eval 场景文件单独 commit:
```
$ git add server/evals/dispatch_nonblocking.yaml server/evals/dispatch_cli_failure.yaml \
    server/evals/dispatch_terminal_report.yaml server/evals/dispatch_terminal_merge.yaml \
    server/evals/dispatch_capacity_reached.yaml
$ git commit -m "test: add T-7 eval scenarios (dispatch_nonblocking/cli_failure/terminal_report/terminal_merge/capacity_reached)"
```
commit `ab0b44f`,5 files changed, 344 insertions。

## 完成清单(对照任务卡逐条)

| 任务卡条目 | 状态 | 说明 |
|---|---|---|
| 1. C-00 先跑,三项全满足才放行 | 完成 | daemon running / 18789监听 / approvals mode=full security=full ask=off,三项均满足 |
| 2. 真机联测集 C-02/C-05/C-06/C-07/C-14/C-15 | 完成 | 全部真机实跑,详见 test-report.md;C-02 单独会话(需断连),C-05/C-06/C-07/C-14 同一会话,C-15 复用同会话数据 + 与 T-4 早前证据交叉印证 |
| 2b. C-18(不依赖真机 Gateway) | 完成 | 一次性脚本驱动真实 `OpenClawExecWorker`/`_DispatchMaterialInjector`,原样样本取自 `baseline/failure-path-samples.json`,三步全 PASS |
| 3. 回归集 C-03/C-08/C-16 | 完成 | C-03 14场景复跑,失败集合与 T-3 基线逐字一致;C-08 命令层+应用层均实跑;C-16 脚本 PASS |
| 4. C-17 步骤4(改动后取样归档) | 完成 | `baseline/post-change-responses.md` 已产出,8问齐备,差异逐条归因写入该文件"备注"节;发现一项重大行为差异(Q5 真实桌面副作用),已升级进 test-report.md 缺陷清单#5 |
| 5. D-003 守法三条核对 | 完成(有缺口如实记录) | 命令2/3 通过;命令1 因契约基准提交号 `cb85377` 不可解析 + T-5 改动未提交两个因素,原文命令本身无法完整验证,已用推定提交号复跑并记入缺陷清单#3/#4 |
| 6. 报告完备性(18条全覆盖) | 完成 | 判据核对表覆盖 C-00~C-19(不含C-12/C-13)全部18条,逐条有结论,无留空 |
| 7. 结论三选一 | 完成 | **需人工裁决**(理由见 test-report.md"结论"节) |

## 改动文件

- 新增 `pipeline/task-dispatch/test-report.md`(本卡核心产出)
- 新增 `pipeline/task-dispatch/baseline/post-change-responses.md`(本卡核心产出)
- 新增 `pipeline/task-dispatch/T-8-notes.md`(本文件)
- commit `ab0b44f`:5 个 T-7 遗留的 eval 场景文件(按主会话授权)
- `server/.env` 的 `OPENCLAW_AGENT_ID` 曾临时改为 `no-such-agent-xyz`(执行 C-04 前置)
  后已改回 `dev`(gitignore 文件,已用 `grep OPENCLAW_AGENT_ID server/.env` 核对复原,
  `git status` 对该文件无输出)。
- 无其它文件改动;未touch `task_dispatch.py`/`task_dispatch_contract.py`/`bot.py`/
  `prompts.py`/`config.py`/`tests/*.py` 任何一行(硬规则1:走不通停下走RISKS,不擅自改)。

## TDD 证据

本卡性质是验收(qa-tester 角色),不是"先写断言证伪再实现",证据形态是"实际执行的
命令 + 原样输出",全部命令/输出已完整收录在 `test-report.md` 判据核对表与详细证据
小节,此处不重复贴长日志,只列关键命令清单(均可原样复跑):

```
# C-00
openclaw daemon status
ss -ltnp | grep 18789
openclaw approvals get --json | python3 -c "..."

# C-02(K=agent:dev:voice-agent-a6610351f0d3)
pipecat eval run <dispatch sleep200>.yaml -v --logs-dir eval-runs
openclaw tasks show "$K" --json          # 断连前
pipecat eval run --trigger-disconnect <trigger>.yaml -v --logs-dir eval-runs
openclaw tasks show "$K" --json          # 30秒后
openclaw tasks show "$K" --json          # 自然结束后

# C-03(14个既有场景逐个)
cd server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run bot.py -t eval
cd server && set -a && source .env && set +a && PYTHONPATH="$(pwd)" NLTK_DISABLE_IMPORT_SECURITY=1 \
  pipecat eval run evals/<name>.yaml -v --logs-dir eval-runs
# dual_brain_fault 单独:
pipecat eval suite evals/dual_brain_fault.manifest.yaml --name dual_brain_fault-<ts> --runs-dir eval-runs

# C-04(2次独立复跑,前置 OPENCLAW_AGENT_ID=no-such-agent-xyz)
pipecat eval run evals/dispatch_cli_failure.yaml -v --logs-dir eval-runs

# C-05/C-06/C-07/C-14/C-15(同一真机会话)
pipecat eval run <combined 6-turn scenario>.yaml -v --logs-dir eval-runs
openclaw tasks show "$K_A" --json
openclaw tasks show "$K_B1" --json
openclaw tasks show "$K_B2" --json

# C-08
openclaw tasks show no-such-task-id-xyz --json; echo "exit=$?"
pipecat eval run <app-layer lookup query>.yaml -v --logs-dir eval-runs

# C-09 步骤1(引用T-6,本卡复跑确认未漂移)
cd server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest tests/ -q -k AssemblePipeline

# C-10 单测半(引用T-6,本卡复跑确认未漂移)
cd server && NLTK_DISABLE_IMPORT_SECURITY=1 .venv/bin/python -m pytest tests/test_task_dispatch.py -q -k merge

# C-16
bash pipeline/task-dispatch/generated/cases/C-16.sh

# C-17 步骤4
cd server && set -a && source .env && set +a && PYTHONPATH="$(pwd)" NLTK_DISABLE_IMPORT_SECURITY=1 \
  pipecat eval run evals/baseline_probe.yaml -v -d --logs-dir eval-runs

# C-18(一次性脚本,未落仓库文件,逻辑同T-6 tests/test_task_dispatch.py手法)
.venv/bin/python <ephemeral script importing task_dispatch, feeding baseline/failure-path-samples.json>

# C-19(2次独立复跑)
pipecat eval run evals/dispatch_capacity_reached.yaml -v --logs-dir eval-runs

# D-003
git diff --stat cb3e857..HEAD -- server/
python3 -c "<ast TOPLEVEL_ENV_CALLS 脚本>"
grep -rln "^import bot$\|^from bot import\|import_module(\"bot\")\|import_module('bot')" tests/

# 全量 pytest(收工前)
cd server && NLTK_DISABLE_IMPORT_SECURITY=1 .venv/bin/python -m pytest tests/ -q
```

**全量 pytest 最终结果**:`63 passed, 37 warnings in 5.00s`,exit=0,无回归(T-6 记录的
4条 `test_bot.py` 遗留失败已被 T-6 之后的独立 commit `ec547f3` 修复,本卡复跑确认
全绿)。

## 自查发现(报告前过一遍)

1. **完整性**:任务卡验收用例1-7 逐条落实,判据核对表18条无留空;C-00/C-16/C-19
   三项"不映射FR"用例与C-17一并按契约要求纳入表内;C-18作为FR-3判据5独立成行。
2. **质量**:每条"实际执行的命令"均为可原样复跑的具体命令行(不是"应该没问题"的
   主观描述);真机证据全部贴原始日志/JSON片段而非转述。
3. **纪律**:全程未修改 `task_dispatch.py`/`task_dispatch_contract.py`/`bot.py`/
   `prompts.py`/`config.py`/既有 `tests/*.py`——即使 C-04/C-19 撞上已知的 D-016
   gateway 问题,也严格按硬规则3原样保留判据、不越权"修好它"。发现的坏味道(缺陷
   清单#2/#3/#4/#5)一律记录不动手。
4. **测试真实性**:全部真机用例(C-02/C-04/C-05/C-06/C-07/C-08/C-14/C-15/C-17/C-19)
   都是真实 `openclaw agent` CLI + 真实 `bot.py -t eval` 进程 + 真实 8045 LLM 网关,
   零 mock;唯一非"全真机"的是 C-18(按契约原文本就允许"不依赖真机 Gateway",用
   已实现的真实 Python 对象 + 原样历史样本驱动,同样零 mock,只是不需要 daemon 在线)。
5. **意外发现主动升级**:C-17 步骤4 过程中发现的"任务真实操作本机桌面"(缺陷清单#5)
   与 C-06 联测中发现的"同一逻辑请求被重复派活两次"(缺陷清单#2)均超出对应用例判据
   字面要求的范围,但判断其对用户/主会话决策有实质影响,主动记入缺陷清单并在回执
   RISKS 中突出,而不是因为"判据字面上还是过了"就略去。
6. **方法论修正(过程中发现即改)**:①最初驱动 `dual_brain_fault` 时误用非-suite方式
   跑在真实(非故障注入)bot上,导致假失败,发现后按design.md/契约指定的
   `pipecat eval suite` 方式重跑,得到正确结果,已在报告中如实说明两次尝试及原因,
   不是简单地把假失败结果藏起来重跑到"侥幸通过";②早期几条真机命令用了
   `... | tail -N; echo EXIT=$?` 的写法,`$?` 实际捕获的是 `tail` 的退出码而非
   `pipecat eval run` 本身——发现后对所有需要引用退出码的关键证据均改用"重定向到
   文件 + 单独取 `$?`"的写法重新取证(C-04/C-19/C-02/C-08等的最终引用证据均为
   修正后的取值方式),此前已经看到的"N/M passed"人类可读文本本身不受此问题影响
   (那才是我据以判断通过/失败的依据),但为了报告中出现的"退出码"字样准确无误,
   已重新核实。

## 疑虑(供 RISKS)

已在 test-report.md"缺陷清单"逐条展开,此处只列条目索引与优先级供回执引用:

1. **[高优先级,已登记D-016,本卡补充新证据]** C-04/C-19 因8045 gateway 400——C-04
   本卡2次复跑2/2失败(确定性);**C-19 本卡2次复跑1通过1失败**(与debts.md现有
   "复现率2/2"措辞不完全吻合,C-19并非100%必现),建议主会话/设计侧更新D-016措辞
   或据此重新评估处置优先级。
2. **[中优先级,未登记于既有债务簿,建议新开]** 同一逻辑请求在无自然停顿的连续对话
   下可能被 `dispatch_task` 重复派活两次(C-05/C-06/C-07/C-14 联测中意外发现,3条
   独立session_key而非预期2条)。未致任何判据结构性失败,但是真实的可靠性风险。
3. **[需契约方订正]** 契约§1用例5 D-003核对命令1的基准提交号`cb85377`在本仓库不可
   解析,推定为`cb3e857`的手误转写,本卡按推定值执行,已记录差异不擅自改契约文件。
4. **[需主会话裁决]** `server/bot.py`/`server/config.py`(T-5独占路径)的实现改动
   始终未提交(T-4→T-6之间无T-5 commit),导致D-003命令1无法完整覆盖这两个文件的
   改动,本卡用工作区口径补充验证内容判据①成立,但契约原文命令本身验证不了。
5. **[高优先级,本卡新发现,超出既有债务簿覆盖范围,直接影响本卡最终结论]**
   task-dispatch的委托LLM对"本机设备控制类"请求无适用性判断护栏,C-17步骤4复验中
   一句"帮我暂停浏览器视频"的日常请求被真实派发,后台agent在**测试机器本身**上真实
   执行了`xdotool`发送合成按键、切换Chrome窗口焦点。这是本卡"结论"选择"需人工裁决"
   而非"可放行"的核心原因,详见test-report.md缺陷清单#5与"结论"节完整论证。
6. **记忆闭环**:开工前 `agent-mem recall backend-dev "task-dispatch T-8 真机联测验收" 5`
   命中一条历史决策记忆(D-015竞态提醒,建议选耗时稍长任务),已在本卡真机任务措辞
   选择中采纳(全部用"写一段说明"/"sleep N"而非"回复ok"式极短任务)。收工时按纪律
   补存:本卡"C-19并非100%必现,与C-04的确定性失败不同"这一新发现值得存入
   agent-mem 供后续任务参考。
