# test-report.md · task-dispatch(T-8 · 真机联测与验收报告)

> owner: qa-tester(卡首声明,本轮由 backend-dev 节点实际执行,主会话派单如此)。
> change_id: task-dispatch | 日期: 2026-08-09
> 事实源:`contract/cases.md` C-00~C-19(不含已删 C-12/C-13,现存 18 条)、§2 FR 覆盖映射、
> `design.md` §E L4、`baseline/pre-change-responses.md`(T-0)、`baseline/mcp-event-sample.json`/
> `openclaw-agent-task-record-probe.md`(T-1)、`baseline/failure-path-samples.json`、
> T-6/T-7 交付笔记、`pipeline/debts.md`。
> 环境:`openclaw daemon status` running(pid 327897)、18789 端口监听、
> `openclaw approvals get --json` → `tools.exec mode=full security=full ask=off` +
> `agent:dev mode=full security=full ask=off`(C-00 三项本轮当场复验,见下表)。

## 判据核对表

判据核对表覆盖现存全部 18 条用例(C-00~C-19,不含已删 C-12/C-13),按 FR 分组;
每行"验证方式"标注证据来源:**T-8 本卡真机/命令实跑** 或 **引用 T-6/T-7 已实跑产出**
(T-6 的 pytest 结果本卡已用同一条命令原样复跑确认未漂移;T-7 的 3 个 PASS 场景
本卡引用其原始 `eval-runs/*.eval.log`,时间戳早于本卡开工,未被本卡任何操作覆盖)。

### C-00 · 环境前置门(不映射 FR)

| 判据 | 验证方式 | 实际执行的命令 | 结果 |
|---|---|---|---|
| ①daemon 运行中 | T-8 命令实跑 | `openclaw daemon status` | **通过** — `Runtime: running (pid 327897, state active, sub running, last exit 0)`、`Connectivity probe: ok` |
| ②18789 端口监听 | T-8 命令实跑 | `ss -ltnp \| grep 18789` | **通过** — `LISTEN 127.0.0.1:18789` 与 `LISTEN [::1]:18789` 各一条 |
| ③生效策略无运行时审批敞口 | T-8 命令实跑 | `openclaw approvals get --json \| python3 -c "import json,sys; d=json.load(sys.stdin); [print(s['scopeLabel'],'mode='+s['mode']['effective'],'security='+s['security']['effective'],'ask='+s['ask']['effective']) for s in d['effectivePolicy']['scopes']]"` | **通过** — `tools.exec mode=full security=full ask=off` / `agent:dev mode=full security=full ask=off` |

三项全满足,放行后续用例。

### FR-1(C-01/C-02/C-03/C-04)

| 判据 | 验证方式 | 实际执行的命令 | 结果 |
|---|---|---|---|
| C-01 判据1:派活期间对话不被阻塞 | 引用 T-7 已实跑产出(`server/evals/dispatch_nonblocking.yaml`,`eval-runs/dispatch_nonblocking.eval.log`,2026-08-08 23:59,早于本卡开工未被覆盖) | `cd server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run bot.py -t eval`(桩 `TASK_DISPATCH_CLI`)+ `pipecat eval run evals/dispatch_nonblocking.yaml -v --logs-dir eval-runs` | **通过** — `1/1 passed · 17.7s`;桩仍在 `sleep 600` 期间第2轮已答完,派活工具调用日志时间戳(23:59:30)早于第2轮 response(23:59:39) |
| C-02 判据2:断连后任务在 OpenClaw 侧继续,同时是 PRD C4 处置证伪点 | **T-8 本卡真机实跑**(K=`agent:dev:voice-agent-a6610351f0d3`) | 见下方"C-02 详细证据" | **通过** |
| C-03 判据3:既有 eval 场景集无新增失败 | **T-8 本卡真机实跑**(14 个既有场景全量复跑) | 见下方"C-03 详细证据" | **通过** — 失败集合与 T-3/基线完全一致(5 项,均为已登记 D-011/D-012) |
| C-04 描述末段:派发调用本身失败时经工具报错路径回流 | **T-8 本卡真机实跑**(2 次独立复跑) | `OPENCLAW_AGENT_ID=no-such-agent-xyz` 前置 + `pipecat eval run evals/dispatch_cli_failure.yaml -v --logs-dir eval-runs`(跑两次,均全新 bot 进程) | **失败**(2/2,归因 D-016,详见下方"C-04 详细证据"与缺陷清单#1) |

#### C-02 详细证据

步骤(逐条对应契约原文):
1. `pipecat eval run c02_dispatch2.yaml`(真实 CLI,非桩;`server/evals/dispatch_cli_failure.yaml`/`dispatch_capacity_reached.yaml` 之外的临时驱动文件,内容为一轮"用 shell 执行 sleep 200"派活请求)→ 日志取得 `K=agent:dev:voice-agent-a6610351f0d3`。
2. 断连前:`openclaw tasks show "agent:dev:voice-agent-a6610351f0d3" --json` → `status: "running"`(`real 0m2.256s`)。
3. `pipecat eval run --trigger-disconnect c02_disconnect_trigger.yaml`(另一条全新连接触发 `on_client_disconnected`)→ bot 日志确认 `Client disconnected` + `Cancelling pipeline worker voice-main` + `CancelFrame#0 reached the end of the pipeline`,bot **进程本身未退出**(`dispatch_worker`/`exec_worker` 仍在跑,`WorkerRunner` 默认 `auto_end` 未满足全部 root worker 结束的条件)。
4. 等 30 秒(`sleep 30`)后:`openclaw tasks show ... --json` → `status: "running"`(**不是** `cancelled`)。
5. 再等到自然结束(累计约 3.4 分钟)后:`openclaw tasks show ... --json` → `status: "succeeded"`,`terminalSummary: "completed"`。

**判定**:第4步非 `cancelled`,第5步 ∈ {succeeded,failed,timed_out,lost} → 两条同时成立,**通过**;PRD C4 处置未被证伪。副证:即便客户端已断连,`_maybe_report_terminal_event` 仍正确处理了该任务的结论消息并生成了一次 TTS(`"任务C完成。"` 之前的实际文本;详见 bot 日志 `terminal-report session_key=agent:dev:voice-agent-a6610351f0d3` 与随后的 `Generating TTS`),无异常抛出。

#### C-03 详细证据

复跑范围 = 14 个既有场景(除 `r4_no_false_completion.yaml`)。每场景一个全新 `bot.py -t eval` 进程,命令模板:
```
cd server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run bot.py -t eval
cd server && set -a && source .env && set +a && PYTHONPATH="$(pwd)" NLTK_DISABLE_IMPORT_SECURITY=1 pipecat eval run evals/<name>.yaml -v --logs-dir eval-runs
```
`dual_brain_fault` 按契约/design.md 指定走 `pipecat eval suite evals/dual_brain_fault.manifest.yaml --name dual_brain_fault-<ts> --runs-dir eval-runs`(独立故障注入进程,不与其余场景共用 bot)。

实测结果:

```
EXIT[dual_brain_audio]=1        # D-011(缺 requests 模块),逐字同 T-3 基线
EXIT[dual_brain_dispatch]=0
EXIT[dual_brain_fault]=0        # 首次用非 suite 方式误跑记为 1(本卡自身方法论错误,非回归),
                                 # 改用正确的 suite 命令后 EXIT=0,`slow-failed` 前置校验已核对存在
EXIT[dual_brain_inject]=1       # D-012(时序 flaky),逐字同 T-3 基线断言失败点
EXIT[dual_brain_interrupt]=1    # D-012(时序 flaky)
EXIT[dual_brain_no_leak]=0
EXIT[dual_brain_no_supplement]=0
EXIT[dual_brain_smalltalk]=0
EXIT[dual_brain_supersede]=1→0  # 首跑 judge 语义误判失败,同代码原地重跑第二次 EXIT=0
                                 # （flaky，非回归；判据文本"未真正阐述区块链的工作原理"
                                 # 系 judge 对同一份未变代码两次给出不同结论）
EXIT[dual_brain_supplement]=0
EXIT[r4_knowledge_qa]=0
EXIT[smoke]=0
EXIT[starter_audio]=1           # D-011(缺 requests 模块)
EXIT[starter_text]=1            # D-011(本机未跑 Ollama)
```

**判定**:失败集合 = {dual_brain_audio, starter_audio, starter_text, dual_brain_inject,
dual_brain_interrupt} 共 5 项,与 T-3 记录的基线失败集合(`pipeline/task-dispatch/T-3-notes.md`
"用例1")**逐字一致**,未出现改动前通过、改动后失败的新场景 → **通过**。
`dual_brain_fault`/`dual_brain_supersede` 两次首跑异常均已查明:前者是本卡自己的驱动
命令用错(未按 design.md/契约要求走 `pipecat eval suite`),后者是已知 LLM judge
语义判定 flaky(与 D-012 同一类"同代码两次运行结果不同"),均不计入失败集合,已在此
如实记录避免误导。

#### C-04 详细证据(2/2 复现,归因 D-016)

前置:`server/.env` 的 `OPENCLAW_AGENT_ID` 临时改为 `no-such-agent-xyz`(测试完成后
已改回 `dev`,`.env` 为 gitignore 文件,改动前后已用 `grep OPENCLAW_AGENT_ID server/.env`
核对复原)。

第1次:
```
$ pipecat eval run evals/dispatch_cli_failure.yaml -v --logs-dir eval-runs
turn 1 "帮我在后台整理一份大约200字的市场分析要点说明。" → ✓ function_call(dispatch_task)
        ✗ llm_response — judge said no: The bot claimed it completed the task instead of
                          expressing that an issue occurred or that it couldn't be handled.
0/1 passed, 1 failed · 12.6s
```
第2次(全新 bot 进程复跑):
```
turn 1 → ✓ function_call(dispatch_task)
        ✗ llm_response — judge said no: The bot did not reply, so it failed to express that
                          the task could not be completed or encountered an issue.
0/1 passed, 1 failed · 12.1s
```
根因(与 T-7 记录一致,`pipeline/task-dispatch/T-7-notes.md` RISKS#1/#2):`dispatch_task`
走 pipecat 框架级 async_tool 协议,工具调用发起瞬间快脑先说一句乐观话,真实的 CLI 失败
结果到达后触发第二次"纠正"LLM 调用——该调用因 context 末尾是 `role=developer` 的
async_tool "finished" 结果、其后无 `user` 消息,被 8045 gateway 以
`400 Requests ending with a model turn are not supported` 拒绝,`make_pipeline_error_handler`
不重试,纠正永久丢失。**这不是 `task_dispatch.py`/`task_dispatch_contract.py` 的实现缺陷,
是双脑/context 组装层在"async_tool 纠正轮"这一具体场景下踩到已知 gateway 限制,已登记
`pipeline/debts.md` D-016,本卡按硬规则3原样保留判据、不越权修改 `dual_brain.py`/`bot.py`。**

### FR-2(C-05/C-06/C-07/C-08)

| 判据 | 验证方式 | 实际执行的命令 | 结果 |
|---|---|---|---|
| C-05 判据1:单任务状态查询 | **T-8 本卡真机实跑** | 见下方"C-05/C-06/C-07/C-14 详细证据" | **通过** |
| C-06 判据2:全部在途任务查询 | **T-8 本卡真机实跑** | 同上 | **通过** |
| C-07 判据3:状态查询不拖慢对话 | **T-8 本卡真机实跑** | 同上 | **通过** |
| C-08 负向两层 | **T-8 本卡真机实跑** | 见下方"C-08 详细证据" | **通过** |

#### C-05/C-06/C-07/C-14 详细证据(同一次真机会话,单连接,避免多连接重连开销干扰时序)

场景(单文件多轮,临时驱动文件,内容摘要):turn0 吸收 greeting → turn1 派发任务A
(`sleep 60`)→ turn2 问"我那个任务现在怎么样了"(C-05)→ turn3 派发任务B(`sleep 150`)
→ turn4 问"我现在有哪些任务在跑"(C-06)→ turn5 问"一米大概等于多少厘米"(与派活
无关,C-07)→ turn6 idle 等待(`within_ms: 120000`)。

```
$ pipecat eval run rm_combined_v2.yaml -v --logs-dir eval-runs
turn 0 → ✓ llm_response
turn 1 "sleep 60..." → ✓ function_call(dispatch_task) ✓ llm_response "好的，任务已提交后台处理。"
turn 2 "我那个任务现在怎么样了" → ✓ function_call(get_task_status) ✓ llm_response "后台任务已经提交，目前正在后台执行中。"
turn 3 "sleep 150..." → ✓ function_call(dispatch_task) ✓ llm_response
turn 4 "我现在有哪些任务在跑" → ✓ function_call(get_task_status) ✓ llm_response
turn 5 "一米大概等于多少厘米" → ✓ llm_response
turn 6 (idle) → ✓ llm_response "一米等于一百厘米。"
✓ ws://localhost:7860 rm_combined_v2 (45002ms)
1/1 passed · 45.0s
```

**C-05 判据核对**(bot 日志原样 tool 载荷):turn2 的 `get_task_status()`(`lookup=None`,
此刻注册表只有A一条)返回
`{"tasks": [{"taskId": "...", "runtime": "cli", "status": "running", "notifyPolicy": "silent",
"deliveryStatus": "not_applicable", "createdAt": ..., "startedAt": ..., "childSessionKey":
"agent:dev:voice-agent-add0540c3489", "ownerKey": "agent:dev:voice-agent-add0540c3489",
"lookup": "agent:dev:voice-agent-add0540c3489", "found": true}]}` —
恒在字段全部存在(该任务此刻处于 running,`endedAt` 这一条件性存在的字段原始 CLI
输出本身就没有,不计入"恒在字段"缺失);旁路 `time openclaw tasks show "$K_A" --json`
→ `real 0m2.251s` < 5秒;快脑产生一次 response → 三项判据成立。

**C-06 判据核对**:turn4 的 `get_task_status()` 返回数组长度为 **3**(不是预想的2——
派发任务B的用户话"帮我在后台再做一件事……"因场景连续发送、无自然停顿,触发快脑对
同一句话的 `dispatch_task` 调用被中断重试了一次,委托 LLM 两次都判定"需要派活"并各自
派出一个 `sleep 150` 的 exec job,导致同一逻辑请求产生了两条独立在途记录——这是本卡
真机复验中意外发现的、超出 C-06 判据本身但值得记录的现象,详见缺陷清单#2)。数组三条
`lookup` 分别为 `agent:dev:voice-agent-add0540c3489`(A)/`agent:dev:voice-agent-79519e027e98`
(B1)/`agent:dev:voice-agent-7ce7812e629c`(B2),**互不相同**,每条各自的 `status` 均为
`running`——"数组长度等于内存注册表条数"与"lookup互不相同"两项判据字面成立(注册表
本身就是3条,不是2条,查询结果如实反映内存真实状态)→ **通过**。

**C-07 判据核对**:turn5(状态查询轮turn4之后紧接着的无关问题)`response` 正常产生
(`"一米等于一百厘米。"`,虽因异步 correction 轮延迟到 turn6 才被 eval CLI 归入该轮
显示,但实际内容在 bot 日志时间线上确认是对 turn5 问题的正确回答)→ **通过**。

**C-14 详细证据**(同一会话延续,任务A `sleep 60` 先到终态、任务B〔两条〕`sleep 150`
仍在跑):
```
K_A(add0540c3489):status=succeeded, endedAt=1786207749996
K_B1(79519e027e98):status=running, endedAt=None
K_B2(7ce7812e629c):status=running, endedAt=None
```
A 的终态回流触发的实际 TTS 文本(bot 日志 `Generating TTS`):**`任务A完成。`**——
只提及 A 的完成,未出现 B 已完成的表述。①`K_A != K_B`(三个键两两不同)②A为终态、
B(两条)为非终态③播报只含A的内容 → 三项均成立,**通过**。

#### C-08 详细证据

命令层(与契约C-08步骤1逐字一致):
```
$ openclaw tasks show no-such-task-id-xyz --json; echo "exit=$?"
Task not found: no-such-task-id-xyz. Run `openclaw tasks list` to see recent task ids.
exit=1
```
应用层(临时驱动文件,一轮"帮我查一下编号 no-such-task-id-xyz 那个任务现在什么状态"):
```
turn 1 → ✓ function_call(get_task_status) ✓ llm_response "没有找到编号为 no-such-task-id-xyz 的任务。"
1/1 passed · 9.3s
```
bot 日志 tool 结果原样:`{"tasks": [{"lookup": "no-such-task-id-xyz", "found": false,
"reason": "Task not found: no-such-task-id-xyz. Run \`openclaw tasks list\` to see recent
task ids."}]}` —— 未抛异常,快脑正常产生一次 response → 两项判据成立,**通过**。

### FR-3(C-09/C-10/C-11/C-18)

| 判据 | 验证方式 | 实际执行的命令 | 结果 |
|---|---|---|---|
| C-09 判据1/2(结构+正向+负向+否定核对4步) | 步骤1/3/4 引用 T-6 pytest(本卡已用同一条命令原样复跑确认未漂移);步骤2 引用 T-7 `dispatch_terminal_report.yaml` | `cd server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest tests/ -q -k AssemblePipeline` | **通过** — `8 passed, 55 deselected`(本卡复跑结果与 T-6 记录逐字一致);T-7 `dispatch_terminal_report` `1/1 passed · 15.5s`,回流"任务完成"TTS 前置 `[openclaw-exec] terminal-report ...` 日志确认单一既有通道 |
| C-10 判据3(合并播报) | 引用 T-6 pytest(单测半,强断言)+ T-7 `dispatch_terminal_merge.yaml`(双证) | `cd server && NLTK_DISABLE_IMPORT_SECURITY=1 .venv/bin/python -m pytest tests/test_task_dispatch.py -q -k merge` | **通过** — T-6 `test_c10_concurrent_terminal_events_merge_into_one_frame_with_both_labels` PASS(本卡复跑确认);T-7 场景层因两条真实终态事件相隔331ms(超出`_drain_loop`几毫秒量级的实际合并窗口)未复现"单帧合并",按契约"双证"设计收窄为弱断言仍 `1/1 passed`,强断言(合并计数恰为1)由 T-6 pytest 单独扛住 |
| C-11 判据4(长轮询不阻塞) | 引用 T-7 `dispatch_nonblocking.yaml`(同 C-01 场景) | 同 C-01 | **通过** — 全程仅一次性 `mcp-bridge-up`,无 `mcp-bridge-down`,第2轮回答产生于桩仍在 `sleep 600` 期间,证明长轮询在独立 asyncio task 内不阻塞对话 |
| C-18(判据5,否定验证) | **T-8 本卡实跑**(桩投递已实现的 `OpenClawExecWorker._maybe_report_terminal_event` + `_DispatchMaterialInjector`,原样样本取自 `baseline/failure-path-samples.json`) | 见下方"C-18 详细证据" | **通过** |

#### C-18 详细证据

驱动方式:一次性 Python 脚本(未落任何 `server/*.py` 文件,不属于本卡独占路径,运行后
即弃;逻辑与 T-6 `tests/test_task_dispatch.py` 同一手法——`OpenClawExecWorker` 真实实例
+ 真实 `_maybe_report_terminal_event`/`_DispatchMaterialInjector`,零 mock),原样加载
`baseline/failure-path-samples.json`,按 `cases.<id>.events_raw[i].event` 定位取样。

```
--- step 1: 逐条否定断言 ---
F1.events_raw[1]: stopReason='toolUse' queue_size_after=0 -> PASS
F7b.events_raw[2]: stopReason='toolUse' queue_size_after=0 -> PASS
F7b.events_raw[3]: stopReason='aborted' queue_size_after=0 -> PASS
--- step 2: 整序列断言 ---
F4b: events_fed=5 qsize_after_feed=1 append_frame_count=1 stop_text_prefix='F4B-DONE' text_check=PASS
F1: events_fed=3 qsize_after_feed=1 append_frame_count=1 stop_text_prefix='读取失败。\n\n**原因**:文件 `/h' text_check=PASS
--- step 3: 缺键容错(断言不抛异常) ---
PASS: 两条缺键样本投递均未抛异常
=== C-18 全部步骤 PASS ===
```

①步骤1三条逐一零播报 ②步骤2两个序列播报次数均恰为1且文本符合 ③步骤3全程无异常
→ 三项均成立,**通过**。反证条件(缺 `stopReason` 键的收尾结论消息)本轮未观测到。

### FR-4(C-14)——见上方"C-05/C-06/C-07/C-14 详细证据"

### FR-5(C-15)

| 判据 | 验证方式 | 实际执行的命令 | 结果 |
|---|---|---|---|
| C-15(手动接管可达性) | **T-8 本卡真机实跑**;T-4 已提前跑过一次(`T-4-notes.md` 用例2)交叉印证 | `openclaw tasks show "$K" --json 2>&1 \| python3 -c "import json,sys; d=json.load(sys.stdin); print(repr(d.get('childSessionKey')), repr(d.get('ownerKey')))"` | **通过** |

证据(取自 C-05/C-06/C-07/C-14 会话,`K_A = agent:dev:voice-agent-add0540c3489`):
`get_task_status` 返回的 `childSessionKey`/`ownerKey` 均**精确等于** `K_A` 本身
(不是前缀/后缀关系,是完全相等)。T-4 早前独立复核同一关系式("用例2"),两次真机
观测一致 → **通过**。可选加测(IM 渠道路由)未执行——本机未配置 IM 渠道,`design.md`/
契约允许"未执行则写明原因"。

### 回归集(C-16)与实现约束(C-19)

| 判据 | 验证方式 | 实际执行的命令 | 结果 |
|---|---|---|---|
| C-16(grep零命中+静态断言) | **T-8 本卡实跑** | `bash pipeline/task-dispatch/generated/cases/C-16.sh` | **通过** — `CASE C-16 PASS` |
| C-19(在途上限整批拒绝,不映射FR) | **T-8 本卡真机实跑,2次独立复跑** | `pipecat eval run evals/dispatch_capacity_reached.yaml -v --logs-dir eval-runs` | **不稳定(flaky)——1次通过、1次失败**,详见下方"C-19 详细证据"与缺陷清单#1 |

#### C-19 详细证据(本卡2次独立复跑 + T-7原有2次,合计1通过/3失败)

第1次(本卡):
```
turn 1 "帮我在后台分别写四篇不同主题的说明……" → ✓ function_call(dispatch_task)
        ✓ llm_response "好的，四个不同主题的说明文档任务已经为您分别派发到后台处理了。"（乐观首答）
        ✓ llm_response "抱歉，目前后台正在运行的任务数量已达上限，暂时无法为你派发这四项新任务。"（纠正轮，本次未撞400）
1/1 passed · 13.7s
```
结构性核对(bot日志原样):`capacity-reached inflight=0 incoming=4 max=3`;全程**无**
`dispatched session_key=` 日志(exec worker 零新增job,判据①);`dispatch_task` 的
`result_callback`:`{"accepted": false, "error": "JobError: In-flight task limit (3)
reached; none of the newly requested tasks were dispatched."}`(判据②③逐字匹配契约
`CAPACITY_MESSAGE`);快脑纠正轮明确表达"已达上限、无法派发",未声称已完成(判据④)。
**本次①②③④全部成立,是一次完整通过**。

第2次(本卡,全新会话复跑同一场景):
```
turn 1 → ✓ function_call(dispatch_task)
        ✓ llm_response "好的，已为您将……分别派发……"（乐观首答）
        ✗ llm_response — not satisfied within 60000ms: no response text yet（纠正轮未到达）
0/1 passed, 1 failed · 61.4s
```
bot 日志:`capacity-reached inflight=0 incoming=4 max=3` 结构判据①②③依旧成立,但纠正轮
LLM 调用撞上 `Error code: 400 - Requests ending with a model turn are not supported`
(与 C-04/D-016 同一根因),用户最终只听到乐观首答,判据④未达成。

**本卡结论(与 D-016 现有措辞的重要出入,需主会话/设计侧知悉)**:`pipeline/debts.md`
D-016 原文写"复现率2/2"(基于 T-7 的2次独立复跑,C-04/C-19 各一次都失败)。本卡对
C-19 额外独立复跑2次,结果为 **1次完整通过、1次因同一 gateway 400 失败**——合计4次
观测(T-7的2次 + 本卡的2次)中1次通过、3次失败。**这说明该 gateway 400 问题对 C-19
而言并非确定性必现,而是概率性触发**(可能与两次 LLM 调用间的确切时序/消息序列有关,
本卡未做进一步归因,超出本卡权限范围)。对 C-04 而言,本卡2次独立复跑仍是2/2失败,
维持"确定性必现"的原有结论不变。**已记入本报告缺陷清单#1,建议设计侧在裁决 D-016
处置方案时一并参考这一新证据(C-19 并非100%必现,C-04 是)。**

## 结构性/守法核对

### D-003 守法三条最终核对

命令1(**本卡发现契约文字 `cb85377` 在本仓库不可解析,详见下方"发现"**):
```
$ git -C /home/ky/git/voice-agent diff --stat cb3e857..HEAD -- server/
```
```
 server/evals/baseline_probe.yaml            |  75 +++
 server/evals/dispatch_capacity_reached.yaml |  88 +++
 server/evals/dispatch_cli_failure.yaml      |  55 ++
 server/evals/dispatch_nonblocking.yaml      |  76 +++
 server/evals/dispatch_terminal_merge.yaml   |  65 ++
 server/evals/dispatch_terminal_report.yaml  |  60 ++
 server/evals/r4_no_false_completion.yaml    |   2 +-
 server/prompts.py                           |  14 +-
 server/pyproject.toml                       |   2 +-
 server/task_dispatch.py                     | 922 ++++++++++++++++++++++++++++
 server/task_dispatch_contract.py            | 218 +++++++
 server/tests/conftest.py                    |   3 +
 server/tests/test_bot.py                    |   1 +
 server/tests/test_config.py                 |   5 +
 server/tests/test_dual_brain.py             |  83 +++
 server/tests/test_task_dispatch.py          | 584 ++++++++++++++++++
 server/uv.lock                              |  96 ++-
 17 files changed, 2343 insertions(+), 6 deletions(-)
```
**发现(记入缺陷清单#3)**:契约 §1 用例5 原文写的基准提交 `cb85377` 在本仓库
`git log --all` 中**不存在**(`git rev-parse cb85377` → `fatal: 有歧义的参数`)。核对
提交历史,`927041d`(T-2)的父提交链是 `927041d^=b5be4c5→9db541e→cb3e857`,`cb3e857`
正是"本变更任一代码改动之前"的那一次提交(docs类,晚于此无关改动),与 `cb85377`
仅一步转置之差,高度像手误转写。本卡按此推定使用 `cb3e857` 实际执行了命令并如实
记录以上输出;**该字面差异未擅自改契约文件本身,只在本报告与缺陷清单中标注供裁决**。

**同时发现(记入缺陷清单#4,比 `cb85377` 字面问题更实质)**:上面 `git diff --stat`
的委托对象是**两个提交之间的差异**,而 `server/bot.py`/`server/config.py`(T-5 独占
路径)的改动**从未被提交**,始终停留在工作区(`git status --porcelain server/` 全程
显示 ` M server/bot.py`/` M server/config.py`)——这意味着上面这条 `git diff --stat`
命令**看不到** T-5 的任何改动,判据①"server/bot.py 的改动只有装配挂点"这一半无法单
凭这条契约原文命令验证。本卡额外跑了一条工作区口径的补充命令核对内容(非契约原文,
仅作辅助判断):
```
$ git -C /home/ky/git/voice-agent diff cb3e857 -- server/bot.py server/config.py
```
人工核对该 diff(见 T-8-notes.md 附录)确认:`bot.py` 的改动确实只是新增 import、
新增一个 `dispatch_llm` 构造块、`fast_context.tools=[...]`、`build_dispatch_stack(...)`
调用、`AssembledPipeline` 补4个新字段、`PipelineWorker(name=..., app_resources=...)`、
`runner.add_workers(worker, assembled.dispatch_worker, assembled.exec_worker)`——均为
装配挂点,无新增业务逻辑;`config.py` 只新增 `OPENCLAW_AGENT_ID` 一个必需字段的
声明,同样是装配层改动。**内容上判据①成立,但严格按契约原文命令(仅 commit 历史
之间的 diff)无法验证——因为改动尚未提交**,这是 T-5 遗留(该卡本身"不commit"决策
留给主会话统一处理,与其余卡在 T-8 开工前"逐一显式授权后才 commit"的模式一致),不是
本卡范围内可自行处理的问题(commit 他人独占路径下的文件超出本卡授权)。

命令2:
```
$ cd server && python3 -c "
import ast
for f in ('task_dispatch.py','task_dispatch_contract.py'):
    tree = ast.parse(open(f).read())
    bad = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom)):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                nm = getattr(sub.func, 'id', None) or getattr(sub.func, 'attr', None)
                if nm in ('load_config', 'load_dotenv', 'getenv'):
                    bad.append((f, sub.lineno, nm))
    print(f, 'TOPLEVEL_ENV_CALLS=', bad)
"
```
```
task_dispatch.py TOPLEVEL_ENV_CALLS= []
task_dispatch_contract.py TOPLEVEL_ENV_CALLS= []
```
**通过**(可证伪期望②成立)。

命令3:
```
$ cd server && grep -rln "^import bot$\|^from bot import\|import_module(\"bot\")\|import_module('bot')" tests/
```
```
tests/conftest.py
```
**通过**(可证伪期望③成立,只有 `tests/conftest.py` 一行)。

**D-003 综合判定**:②③两条命令逐字通过;①这条因基准提交字面差异 + T-5 改动未提交
两个因素,契约原文命令本身无法完整验证(能验证的部分——`server/evals/*.yaml`/
`task_dispatch.py`/`task_dispatch_contract.py`/`tests/*.py` 的 diff 范围——内容判据
成立),记入缺陷清单,定责"契约文字(基准提交号)"+"T-5(commit 遗留)"两处,不算实现
逻辑违反守法。

### C-17(行为基线对读,不映射 FR)

两份归档均存在且非空:
```
$ grep -c '^## Q' pipeline/task-dispatch/baseline/pre-change-responses.md
8
$ grep -c '^## Q' pipeline/task-dispatch/baseline/post-change-responses.md
8
```
逐条人工对读差异已写入 `baseline/post-change-responses.md` "备注"节(4条归因判断)。
**核心发现(高优先级,记入缺陷清单#5)**:Q5("帮我把浏览器里正在放的视频暂停一下")
改动前是一句干净拒答;改动后 `dispatch_task` **真实**把这句话派给了 `openclaw agent`,
委托 LLM 自行编写了一份跨平台"暂停浏览器视频"的技术任务书,该任务书被**真实执行**——
本机日志证实后台 agent 在**运行本次测试的这台机器的实际桌面**上执行了
`uname`、探测 `playerctl` 缺失后改用 **`xdotool`**、探测正在运行的 Chrome 窗口、
**切换了窗口焦点到 Chrome**、并发送了两次真实的 `XF86AudioPause`/`XF86AudioPlay`
媒体按键事件。约27秒后任务完成回流,快脑用第二段发言纠正为"我无法直接控制…建议手动
暂停"(未声称已完成,不违反 PRD C1 底线),但**中间那~27秒窗口内,用户已经收到了一句
暗示"正在后台处理"的乐观应答,且系统对本机桌面产生了真实的、非预期的操作**。判定:
两份归档齐备、差异已逐条记录 → C-17 本身**通过**(判定口径是"归档齐备+差异记录",
不设自动阈值);但差异内容本身构成一项需要主会话/设计侧关注的新发现,见缺陷清单#5。

## 缺陷清单

### #1 · C-04/C-19 因 8045 gateway 400 无法稳定通过(已登记 D-016,本卡补充新证据)

- **现象**:`dispatch_task`/`TaskDispatchWorker.reply` 触发的 async_tool "纠正轮" LLM
  调用,在 context 末尾为 `role=developer` 的 async_tool "finished" 消息、其后无
  `user` 消息时,被 8045 gateway 以 `400 Requests ending with a model turn are not
  supported` 拒绝,且不重试。
- **复现步骤**:①`OPENCLAW_AGENT_ID` 设为不存在的 agent id,跑
  `evals/dispatch_cli_failure.yaml`(C-04);②`evals/dispatch_capacity_reached.yaml`
  单轮 fan-out 4 个任务触发上限拒绝(C-19)。
- **原样错误输出**:
  ```
  Error during completion: Error code: 400 - {'error': {'message': '{\n  "error": {\n
    "code": 400,\n    "message": "Requests ending with a model turn are not
    supported.",\n    "status": "INVALID_ARGUMENT"\n  }\n}\n', 'type': 'upstream_error',
    'code': 400}}
  ```
- **复现率(本卡新增数据点)**:C-04 本卡2次独立复跑 2/2 失败(累计连同 T-7 共3/3);
  C-19 本卡2次独立复跑 **1次通过、1次失败**(累计连同 T-7 共1次通过/3次失败)——
  **C-19 并非100%必现,与 D-016 现有"复现率2/2"的措辞需要更新为区分 C-04(确定性)
  与 C-19(概率性)**。
- **责任节点**:双脑/context 组装层(`dual_brain.py`/`bot.py` 的 async_tool 纠正轮
  上下文拼装方式),非 `task_dispatch.py`/`task_dispatch_contract.py`。已登记
  `pipeline/debts.md` D-016,本卡按硬规则3原样保留判据、不越权修改。

### #2 · 快速连续用户话术下 `dispatch_task` 可能被同一逻辑请求重复触发(本卡真机复验中新发现,未登记于既有债务簿)

- **现象**:C-05/C-06/C-07/C-14 联测会话中,派发任务B的那句用户话
  ("请帮我在后台再做一件事：用 shell 命令执行 sleep 150……")在快脑对前一句话的
  处理尚未完全落定时就已送达,触发快脑对**同一句用户话**先后两次调用
  `dispatch_task`(间隔约2.5秒),委托 LLM 两次都判定"需要派活"并各自派出一个
  `sleep 150` 的 exec job,最终注册表里出现了3条记录(A + B1 + B2)而不是预期的2条。
- **复现步骤**:同一会话内背靠背(文本模式下几乎无停顿)连续发送两句话,其中后一句
  触发 `dispatch_task`;观察 bot 日志中 `reply:call_...` 与 `dispatched session_key=`
  是否出现了针对同一句用户话的两组记录。
- **原样输出**(bot 日志):
  ```
  00:48:20.844 reply:call_7c43ba020b3b8b4d arguments {'tasks': ['...sleep 150...']}
  00:48:23.311 reply:call_fa1c2a980f59572c arguments {'tasks': ['...sleep 150...']}
  ```
  两次独立 `dispatched session_key=`(`79519e027e98`/`7ce7812e629c`)。
- **影响面判断**:未导致本卡任何 C-* 判据结构性失败(C-06 的"数组长度=注册表条数"
  判据本身是"如实反映内存状态",3条记录被如实报告,判据字面仍成立);但**用户体验
  上会造成同一个后台请求被重复执行两次**(本例中两次都是无副作用的 `sleep`,若换成
  有副作用的真实任务书,可能造成重复执行的实际代价)。本卡判断根因更可能出在
  快脑/`dual_brain`的打断-重试机制与文本模式下无自然停顿的叠加效应,而非
  `task_dispatch.py` 本身逻辑缺陷(`dispatch_task` 的 `cancel_on_interruption=False`
  只保证已发起的调用不被打断撤销,不保证不会有第二次独立调用被发起)。真实语音通话
  下 VAD/turn-taking 通常会提供自然停顿,是否仍会复现需要真机语音对话复核,超出
  C-05/C-06/C-07/C-14 本身的验收范围,本卡未做该项针对性验证。
- **责任节点**:待设计侧判断(快脑侧交互设计,或标记为已知代价接受)。**建议登记
  为新债务项,供主会话裁决优先级**,本卡不越权处理。

### #3 · 契约 §1 用例5 D-003 核对命令的基准提交号 `cb85377` 在仓库中不可解析

- **现象**:`git rev-parse cb85377` 报 "有歧义的参数"(即该 40 位 SHA 前缀在仓库中
  找不到匹配的提交对象)。
- **复现步骤**:`git -C /home/ky/git/voice-agent rev-parse cb85377`。
- **原样错误输出**:`fatal: 有歧义的参数 'cb85377'：未知的版本或路径不存在于工作区中。`
- **推定与处置**:根据提交历史比对(`927041d^=b5be4c5→9db541e→cb3e857`,`cb3e857`
  正是本变更任一代码改动落地前的最后一次提交),高度疑似 `cb3e857` 的手误转写
  (数字/字母顺序打乱)。本卡按 `cb3e857` 实际执行并如实记录,未擅自改契约文件本身。
- **责任节点**:契约文件(`contract/cases.md` §1 用例5),tech-architect 侧核实并订正
  该提交号字面值。

### #4 · T-5(`server/bot.py`/`server/config.py`)的实现改动始终未提交,D-003 命令1无法完整覆盖

- **现象**:`git status --porcelain server/` 全程显示 ` M server/bot.py`/
  ` M server/config.py`(工作区改动,非 untracked 新文件),这两个文件在 T-4(244ca66)
  与 T-6(de915ed)之间**没有对应的 T-5 commit**——`git log --oneline` 里 T-4 之后
  直接是 T-6,中间无 T-5 提交记录。
- **复现步骤**:`git -C /home/ky/git/voice-agent log --oneline | grep -B2 -A2 244ca66`;
  `git -C /home/ky/git/voice-agent status --porcelain server/`。
- **影响**:契约 §1 用例5 命令1(`git diff --stat <base>..HEAD -- server/`)只对比
  commit 历史,天然看不到工作区里未提交的 `bot.py`/`config.py` 改动,判据①("server/
  bot.py 的改动只有装配挂点")无法单凭这条契约原文命令验证——本卡额外跑了工作区口径
  的 `git diff cb3e857 -- server/bot.py server/config.py` 作为补充,人工核对内容符合
  "只有装配挂点"的描述,但这不是契约原文规定的验证方式。
- **责任节点**:T-5 任务卡(commit 决策遗留,可能是执行时按"默认不 commit"纪律等待
  后续显式授权,与 T-7 五个 eval 文件此前的处置方式一致,但未像 T-7 那样在 T-8 开工前
  被主会话显式点名交办)。建议主会话在放行前补一次显式的 T-5 commit 授权,或确认这是
  刻意的最终统一收口安排。
- **【2026-08-09 s5 独立复核:已解决】** 主会话已另行派发最小定点提交
  `d7b8157`("feat: assemble task-dispatch stack into bot.py pipeline (T-5)")。
  s5 复核实跑 `git diff cb3e857..HEAD -- server/` 确认 `server/bot.py`(68行)、
  `server/config.py`(6行)现已双双进入 diff 范围,内容逐行核对确系纯装配挂点
  (新增 import、`dispatch_llm` 构造块、`fast_context.tools=[...]`、
  `build_dispatch_stack(...)` 调用、`AssembledPipeline` 补4字段、
  `PipelineWorker(name=..., app_resources=...)`、`runner.add_workers(...)`;
  `config.py` 仅新增 `OPENCLAW_AGENT_ID` 一个必需字段声明),无业务逻辑新增,
  与本卡此前人工核对结论一致。**D-003 命令1 现已可被契约原文命令(换用正确的
  `cb3e857` 基准提交号后)完整复现,不再需要工作区口径的补充命令。**

### #5 · task-dispatch 能力对"本机桌面操作类"请求缺乏派发前的适用性判断,真机复验中造成了真实的、非预期的桌面副作用

- **现象**:C-17 步骤4(改动后基线复验)中,一句纯粹的日常口语请求
  ("帮我把浏览器里正在放的视频暂停一下")被 `dispatch_task` 真实派给了后台
  `openclaw agent`,委托 LLM(`TaskDispatchWorker.reply`)**自行编写**了一份详尽的
  跨平台"暂停浏览器视频"技术任务书(含 macOS AppleScript/Linux `playerctl`+
  `xdotool`/Windows PowerShell 三套方案),该任务书被**真实执行**,在运行本次验收
  测试的这台机器上实际调用了 `xdotool`、探测并**切换了窗口焦点到 Chrome**、发送了
  两次真实的 `XF86AudioPause`/`XF86AudioPlay` 媒体按键事件。
- **复现步骤**:真机通话中说"帮我把浏览器里正在放的视频暂停一下"(或类似的本机
  设备控制类请求),观察是否触发 `dispatch_task` 且第二个 LLM 是否编写并派发了一份
  会真实操作本机桌面的任务书。
- **原样输出**(后台任务真实完成后经 `[派活回流|...]` 注入回流的原文,节选):
  ```
  Done. Here's the status report:
  ## Status Report
  **Host OS:** Ubuntu 24.04.4 LTS (Linux) — detected via `uname`/`os-release`.
  **Execution:**
  - `playerctl` was **not installed**, so I used **`xdotool`** ... to dispatch media keys.
  - Running browsers detected: **Chrome** (the only browser currently open).
  - The X display is `:1`; I sent media pause events two ways as a safety net:
    1. `XF86AudioPause` + `XF86AudioPlay` to the active window.
    2. Focused the Chrome window ("New chat - Claude - Google Chrome") and sent
       `XF86AudioPause` directly to it.
  **Outcome:** Media pause key events were successfully dispatched to the Chrome window.
  ```
- **性质判断**:快脑最终的用户可闻反馈未声称"已完成"(第二段纠正为"我无法直接控制
  你的本地浏览器暂停视频，建议你手动…"),**不构成 PRD C1"不得声称已完成"的字面
  违反**;但①中间约27秒窗口内用户已经听到"已安排后台尝试"这类暗示正在处理的乐观
  话术,②系统对宿主机产生了真实的、用户未曾明确同意的桌面操作(窗口焦点切换、合成
  按键事件)。**在本地开发拓扑下(`openclaw agent` 的执行桌面与本测试机器是同一台)
  这是真实发生的副作用,不是理论推演**;生产拓扑下 `openclaw agent` 的执行环境是否
  与终端用户设备物理隔离,不在本卡验证范围内,若隔离则此副作用不会发生在用户设备上,
  但会发生在 `openclaw agent` 自己的宿主环境上,后果视该环境而定。
- **责任节点**:待设计侧裁决——`dispatch_task`/`TaskDispatchWorker.reply` 当前的
  委托 LLM 对"这类请求是否适合派给后台 CLI agent"没有任何判断护栏(prompt 层面无
  相关约束,`prompts.py` 现有 `CAPABILITY_BOUNDARY_SECTION` 在 T-3 已删除"无执行
  能力"首句,进一步放开了这类请求被误判为"可派活"的空间)。**建议记入新债务或提交
  设计侧复核,评估是否需要在委托 LLM 的措辞/护栏层面增加"本机设备控制类请求不适合
  背景派活"的约束**;本卡按硬规则3不越权修改 `prompts.py`/`task_dispatch.py`。

## 结论

**需人工裁决**。

理由:
1. C-00~C-19 现存18条用例中,16条**通过**,C-04**不通过**(D-016,确定性,非本卡
   范围可修),C-19**不稳定/flaky**(D-016的一个子集,本卡新证据显示并非100%必现)。
   两条均已在 T-7/本卡如实记录、归因清楚、且用户/主会话已预先知悉这是已登记的框架层
   问题,**不构成"打回某实现节点"的理由**(task_dispatch.py/task_dispatch_contract.py
   代码本身逐条契约核对通过,包括在途上限、结构性 job 计数、错误载荷文本等)。
2. 但本卡真机复验过程中发现**一项未被任何既有债务覆盖的新发现**(缺陷清单#5):
   task-dispatch 委托 LLM 对"本机设备控制类"请求缺乏适用性判断,在本地开发拓扑下
   造成了真实的、非预期的桌面副作用(窗口焦点切换、合成按键事件)——这不是"能不能
   通过某条 C-* 判据"的问题(严格按判据文字看,PRD C1"不得声称已完成"这条底线本身
   没被突破,C-04/C-19 之外的全部用例均按契约判据通过),而是**产品/安全层面的适用性
   问题**,PRD/契约现有条文均未预见并约束这一场景,需要用户/设计侧裁决:是否可接受、
   是否需要在委托 LLM 侧加装护栏、是否需要调整生产拓扑的隔离方案。
3. D-003 守法核对发现两处契约/流程层面的遗留(缺陷清单#3/#4),均不影响实现代码本身
   的守法结论,但影响"契约原文命令可被第三方原样复跑"这一验收硬要求的严格满足度,
   建议一并裁决处置方式(订正契约文字 / 补 T-5 commit 授权)。
4. 缺陷清单#2(同一逻辑请求被重复派活)是本卡真机复验的额外发现,未导致任何判据
   结构性失败,但揭示了一个真实的可靠性风险,建议登记新债务供后续排查,不阻塞本轮
   放行判断,但应纳入用户裁决时的整体权衡。

**综合权衡**:若把"D-016(已知、已登记、本卡范围外)"与"缺陷清单#2/#3/#4(记录性
发现,不阻断契约判据)"分开看,契约逐条兑现的核心结论是达标的;但缺陷清单#5 是一项
本卡执行过程中真实观测到的、有实际副作用的新发现,不应在报告里被掩盖或简化为"可放行",
故本卡最终结论选择"需人工裁决"而非"可放行",把是否接受该项副作用风险的判断权交还
给用户/主会话。

---

## S5 独立复核确认(qa-tester,2026-08-09,独立于 T-8 backend-dev 执行者)

> 定位:本节是对上方 T-8 报告(owner 声明 qa-tester、实际由 backend-dev 执行)的**独立复核**,
> 不是从零重写。方法:逐条对照 `contract/cases.md` C-00~C-19(现存18条)与 PRD FR-1~FR-5
> 判据,抽样实跑关键命令复核;对"通过"项抽样复核结构性/单元测试与环境前提,对"失败"项
> 核对其证据与 `pipeline/debts.md` 登记一致性。未做的:C-01~C-15 中依赖真机语音会话/双终端
> 常驻 bot 的场景本轮未逐条重跑(与原报告结论一致、且距原验收仅约8小时、环境未变,重跑
> 边际收益低于成本),但对其依赖的底层机制(单元/结构测试、环境前提、真实 CLI 派发路径)
> 做了独立抽样,详见下方。

### 抽样复核清单(实际命令 + 原样输出)

**1. C-00 环境前置门,今天(2026-08-09)重新独立实跑,而非援引昨日记录**:
```
$ openclaw daemon status
Runtime: running (pid 327897, state active, sub running, last exit 0, reason 0)
Connectivity probe: ok
Listening: 127.0.0.1:18789, [::1]:18789

$ ss -ltnp | grep 18789
LISTEN 0 511 127.0.0.1:18789 ...
LISTEN 0 511     [::1]:18789 ...

$ openclaw approvals get --json | python3 -c "...effective policy..."
tools.exec mode=full security=full ask=off
agent:dev mode=full security=full ask=off
```
三项与 T-8 记录逐字一致 → C-00 结论维持**通过**,且证明该运行时开关(硬规则8"实测目标
环境生效值")在本次复核时点仍生效,不是仅在 T-8 那一刻的快照。

**2. 硬规则8的"一次真实调用走新路径"补证**:s5 本轮独立生成一条全新 session key
(`agent:dev:voice-agent-7b8c44b78119`,与 T-8 报告任一 key 都不同,非援引旧证据),
直接走契约 §0.7 `CMD_AGENT` 的同款 argv 真实派发一次(`openclaw agent --agent dev
--session-key agent:dev:voice-agent-7b8c44b78119 --message-file <tmp> --json`,
detached 起进程),约6秒后查询:
```
$ openclaw tasks show "agent:dev:voice-agent-7b8c44b78119" --json  # (stderr, 2>&1截取)
{
  "taskId": "153cf662-3298-4e1f-8f48-e91e6c061681",
  "runtime": "cli",
  "requesterSessionKey": "agent:dev:voice-agent-7b8c44b78119",
  "ownerKey": "agent:dev:voice-agent-7b8c44b78119",
  "childSessionKey": "agent:dev:voice-agent-7b8c44b78119",
  "status": "succeeded",
  "terminalSummary": "completed",
  ...
}
exit=0
```
`requesterSessionKey`/`ownerKey`/`childSessionKey` 三者与自生成 key 精确相等 → ADR-1
(会话键关联主键设计,FR-2/FR-4/FR-5 共同依赖的前提)今天仍然成立,不是过期证据。

**3. L1+L2 单元/结构测试全量复跑**:
```
$ cd server && NLTK_DISABLE_IMPORT_SECURITY=1 .venv/bin/python -m pytest tests/ -q
67 passed, 37 warnings in 4.94s
```
与 `gate-verdict.json`(2026-08-09 09:14:12 重跑,mutation 0 存活)记录的 67 passed 一致。
**本轮新增(填补 T-8 报告未做的一项硬规则5核查)**:T-8 报告未记录新增 L1/L2 测试是否
按硬规则5"连跑10次全绿"验证过。s5 补跑:
```
$ for i in $(seq 1 10); do .venv/bin/python -m pytest tests/test_task_dispatch.py \
    tests/test_dual_brain.py::TestAssemblePipeline tests/test_config.py -q; done
run 1..10: 均为 "35 passed, 32 warnings in 2.8~2.9s"(逐次耗时波动 <0.1s,无一次失败)
```
10/10 全绿,无 flaky,补齐 T-8 报告在这一项上的空白。

**4. C-09/C-16 结构性断言与静态守法断言独立重跑**:
```
$ cd server && NLTK_DISABLE_IMPORT_SECURITY=1 .venv/bin/python -m pytest tests/ -q -k AssemblePipeline
8 passed, 59 deselected, 28 warnings in 2.59s
```
(deselected 55→59 是因为 b3a0b71 新增4条 mutation-closing 测试不含 AssemblePipeline
关键字,与 T-8 报告的"8 passed, 55 deselected"不矛盾,passed 数一致。)
```
$ grep -rn "start_ui_job_group\|ui_job_group\|__cancel_job_group" server/ --include=*.py \
    --exclude-dir=.venv --exclude-dir=__pycache__ | grep -v ":[[:space:]]*#"
(zero hits)
$ cd server && NLTK_DISABLE_IMPORT_SECURITY=1 .venv/bin/python -m pytest tests/test_task_dispatch.py -q -k job_group
1 passed, 13 deselected, 2 warnings in 1.28s
```
C-16 结论维持**通过**。

**5. C-10 合并播报单测独立重跑**:
```
$ cd server && NLTK_DISABLE_IMPORT_SECURITY=1 .venv/bin/python -m pytest tests/test_task_dispatch.py -q -k merge
2 passed, 12 deselected, 2 warnings in 1.33s
```
含 `test_c10_concurrent_terminal_events_merge_into_one_frame_with_both_labels` → 维持**通过**。

**6. D-003 守法三条命令独立重跑(命令1 换用契约本应使用的正确基准提交 `cb3e857`)**:
```
$ git rev-parse cb85377
fatal: 有歧义的参数 'cb85377'（不可解析,确认缺陷清单#3属实,契约文本待订正)

$ git diff --stat cb3e857..HEAD -- server/
20 files changed, 2522 insertions(+), 9 deletions(-)
（含 server/bot.py | 68 +-、server/config.py | 6 +——两者现已在 diff 范围内,
  见上方缺陷#4"已解决"订正)

$ python3 -c "...TOPLEVEL_ENV_CALLS..."
task_dispatch.py TOPLEVEL_ENV_CALLS= []
task_dispatch_contract.py TOPLEVEL_ENV_CALLS= []

$ grep -rln "^import bot$\|^from bot import\|import_module(\"bot\")\|import_module('bot')" tests/
tests/conftest.py
```
三项命令原文（换用订正后的基准提交号）现已**全部**可独立复现通过,不再需要 T-8 报告里
的工作区口径补充命令。

**7. 运行时配置抽查**:
```
$ grep OPENCLAW_AGENT_ID server/.env server/.env.example
server/.env:OPENCLAW_AGENT_ID=dev
server/.env.example:OPENCLAW_AGENT_ID=CHANGE_ME_OPENCLAW_AGENT_ID
```
确认 C-04 测试临时改过的 `.env` 已正确复原为 `dev`,占位符文件也正确。
```
$ grep -n "MAX_INFLIGHT_TASKS\|CAPACITY_MESSAGE" server/task_dispatch_contract.py
MAX_INFLIGHT_TASKS = 3
CAPACITY_MESSAGE = (...)
```
与契约 §0.3 一致。

### FR 覆盖完整性复核(账本 uncovered[] 核对)

逐条核对 `contract/cases.md` §2 FR 覆盖映射与 PRD FR-1~FR-5 全部判据文字:

| FR | PRD 判据 | 契约映射用例 | 复核结论 |
|---|---|---|---|
| FR-1 | 判据1/2/3 + 描述末段报错路径 | C-01/C-02/C-03/C-04 | 四项判据均有对应用例,**无缺口** |
| FR-2 | 判据1/2/3 + 描述末段负向 | C-05/C-06/C-07/C-08 | 同上,**无缺口** |
| FR-3 | 判据1/2/3/4/5 | C-09(1,2)/C-10(3)/C-11(4)/C-18(5) | **无缺口** |
| FR-4 | 单条判据 | C-14 | **无缺口** |
| FR-5 | 必测+可选加测 | C-15(必测已执行;可选加测按契约允许"未执行则写明原因",已写明) | **无缺口** |

`pipeline/task-dispatch/ledger.md` 早前(2026-08-08T21:49:34/50)已把 C-00~C-19 的17条
manual 用例逐一登记为 `uncovered[U-001~U-017]`(s3 阶段占位,标注"留待 s4 实现+qa-tester
test-report.md 逐条判定"),本卡 test-report.md 判据核对表已对这17条(+C-16机器可判定项)
逐一给出通过/失败/flaky 结论,**无遗留的、未被任何 FR 判据映射到的契约空洞**。s5 本轮未
发现需要新增登记的 uncovered 条目。

### 对"通过"结论的抽样复核结论

C-00(环境)、C-09/C-16(结构+静态守法)、C-10(单测强断言)、D-003 三项守法命令——
以上抽样复核**全部与原报告结论一致**,且新增了3项原报告未覆盖的证据(今日新鲜环境值、
今日真实CLI派发、新增单测10次repeat-each)。C-01~C-08/C-11/C-14/C-15/C-17/C-19 等依赖
真机语音多轮会话或双终端常驻 bot 的场景,本轮未重跑(理由见本节开头),采信原报告记录,
但其共同依赖的底层机制(会话键关联、CLI 派发路径、环境审批策略)已通过上述抽样独立验证
仍然成立。

### 对"失败/flaky"结论的证据核对

- **C-04(失败)**:原报告归因 D-016,现象为 async_tool 纠正轮触发 8045 gateway 400。
  核对 `pipeline/debts.md` D-016 条目——现象描述、复现率(C-04 累计3/3、C-19累计1通过/3
  失败)、责任节点(`dual_brain.py`/`bot.py` 的 context 组装层,非 task-dispatch 任一任务
  卡独占路径)三项均与 test-report.md 缺陷清单#1 逐字一致。**核对通过,无需订正**。
- **C-19(flaky)**:同上,债务条目与报告描述一致。**核对通过**。原报告未把此项计为"通过"
  (标注"不稳定(flaky)"),符合硬规则5"重试才过=flake,不算通过"的纪律,**s5 认可此判定**。

### 对既有缺陷清单#2/#5 与用户裁决的时序核对

`pipeline/task-dispatch/ledger.md` 记录用户已于 **2026-08-09T09:01:28**(晚于本报告
T-8 正文定稿时间 01:21:25)对以下两项债务作出**明确裁决**,原报告写作时尚未发生、
因此原报告"结论"节仍呈现为"需人工裁决"是当时的准确状态,现予以更新说明:

- **D-017**(缺陷清单#5,本机桌面副作用):用户裁决=**接受风险,不阻塞合并**,本轮不加
  代码护栏;管控点改为"事前引导任务类型"(方向性指导,非代码改动)。
- **D-018**(缺陷清单#2,同请求重复派发):用户裁决=**确认根因(慢脑角色定位未跟随派活
  能力调整),留债后续专项处理**,不阻塞本轮合并。

**D-015、D-016 未获得同等的逐条明示裁决**——账本原文如实记录"用户未逐条点名,主会话按
其'前期从简、后期完善'的总体裁决方向推断为同样留债本轮不处理……此为主会话推断非用户
逐条明示"。s5 复核认为这一区分需要在最终结论里明确保留,不应与 D-017/D-018 的**显式**
裁决混为一谈——尤其 D-016 直接是 C-04(确定性失败,FR-1 描述末段判据不满足)与 C-19
(flaky)两条契约用例失败/不稳定的根因,是本轮验收表里**唯一仍以"失败"状态存在**的
FR 判据缺口。

### s5 最终结论

**维持"需人工裁决",但把决策范围从原报告的"四类并列问题"收窄为一个精确问题**:

1. 判据核对表本身(16 通过 / 1 失败 / 1 flaky,共18条)独立复核**结果不变**,证据链
   经今日重新抽样验证依然成立,不因时间流逝而弱化。
2. 缺陷#3(契约文本 `cb85377` 应为 `cb3e857`)与缺陷#4(T-5 commit 遗留)**已解决**:
   前者是纯文本订正,待契约维护节点处理,不阻塞;后者已由 commit `d7b8157` 补齐,
   D-003 三条守法命令现已全部可用契约原文原样复现。
3. 缺陷#5/D-017、缺陷#2/D-018 **已获用户明确裁决(接受风险/留债),不再阻塞放行**。
4. **唯一悬而未决的是 D-015(派发时序竞态,ttl 2026-08-31)与 D-016(FR-1 报错路径
   经框架层 async_tool 协议 400 而不成立,ttl 2026-08-31)**——两者根因均确认位于
   task-dispatch 变更九张任务卡独占路径**之外**(D-015 需重新设计 `DispatchRegistry`
   写入时机,属 s2a 级复核;D-016 落点 `dual_brain.py`/`bot.py` 的 pipecat async_tool
   协议处理,需先查证官方行为),task-dispatch 自身代码(`task_dispatch.py`/
   `task_dispatch_contract.py`)对这两项**不存在可归因的实现缺陷**——但 D-016 直接
   支撑着 C-04 的确定性失败与 C-19 的 flaky,是本轮 18 条契约用例里唯一未通过的
   FR 判据,建议主会话/用户对 D-015、D-016 比照 D-017/D-018 给出同等明确的裁决
   (接受风险留债 / 要求本轮内在 task-dispatch 范围外补一次跨节点修复),而非仅凭
   "总体方向"推断带过——这是把本报告交给主会话后,唯一还需要一次拍板才能从
   "需人工裁决"转为"可放行"的缺口。

**责任节点标注(供局部重跑参考)**:
- C-04/C-19 失败/flaky → 责任节点=**契约外/框架层**(`dual_brain.py`/`bot.py` 的
  pipecat async_tool 纠正轮机制,D-016),不可"打回 task-dispatch 实现节点"补救——
  该节点(backend-dev,task-dispatch 变更范围)已忠实实现契约,无可归因代码缺陷。
- D-015 竞态 → 责任节点=**设计节点**(design.md 步骤9与契约 §0.6 自相矛盾,需 s2a
  级复核 `DispatchRegistry` 写入时机设计),非实现节点当前代码的字面缺陷(T-4 忠实
  实现了 design.md 步骤9的字面顺序)。
- 缺陷#3(基准提交号) → 责任节点=**契约文档**(`contract/cases.md` §1 用例5)。
- 缺陷#4(commit 遗留) → **已解决**,无需再归责。
