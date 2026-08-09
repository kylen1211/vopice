# T-0 · 改动前 LLM 行为基线取样 —— backend-notes

> 任务卡:`pipeline/task-dispatch/tasks/T-0.md`;契约:`pipeline/task-dispatch/contract/cases.md` C-17;
> 设计依据:`design.md` R-7(坑 P57)。owner 声明为 qa-tester,本次由 backend-dev 节点实际执行
> (主会话派单如此,任务内容本身不涉及 Python 符号新增,详见 RISKS)。

## 完成清单(对照任务卡逐条)

| 任务卡条目 | 状态 | 说明 |
|---|---|---|
| Consumes:C-17、R-7、既有场景样板、judge_factory | 已读 | 见下方"依据核对" |
| Produces:`server/evals/baseline_probe.yaml` | 完成 | 固定 8 问,judge 只写 `event: response`,无任何语义判据 |
| Produces:`pipeline/task-dispatch/baseline/pre-change-responses.md` | 完成 | 8 条编号回复原文 + 时序证据 + 时间戳 + LLM_MODEL |
| 不产出任何 Python 符号 | 遵守 | 未新增/改动任何 `.py` 文件 |
| 不改既有场景文件 | 遵守 | `starter_text.yaml`/`dual_brain_inject.yaml`/其余既有 `evals/*.yaml` 零改动(见 git status) |
| 验收 1:C-17 步骤 1-3(本卡只做改动前一轮) | 完成 | 步骤 4(改动后取样)不在本卡范围,留给 T-8 |
| 验收 2:双终端命令、第二条命令退出码 0 | 完成 | 见下方 GREEN 证据,exit=0 |
| 验收 3:归档完备性,`grep -c '^## Q'` == 8 | 完成 | 实测输出 `8` |
| 验收 4:8 问构成(2知识/2闲聊/2执行/2追问),执行类被拒答需原样记录 | 完成 | Q5/Q6 拒答措辞已原样归档 |
| 验收 5:时序硬要求,取样时刻 `git status --porcelain server/` 不含 5 个禁改文件 | 完成 | 输出仅含本卡自身产出的 `server/evals/baseline_probe.yaml`,已贴进归档文件头部 |

## 改动文件

- 新增 `server/evals/baseline_probe.yaml`(commit `9db541e`)
- 新增 `pipeline/task-dispatch/baseline/pre-change-responses.md`(commit `b5be4c5`)

无其他文件改动(`git status --porcelain server/` 全程只多出这一个新文件;`pipeline/task-dispatch/` 下其余未跟踪文件均为其他并行任务卡的产出,未被本卡触碰)。

## 依据核对(开工前读的材料)

- `contract/cases.md` C-17:8 问构成(2知识/2闲聊/2执行/2追问)、judge 只写 `event: response`、命令口径(两条,`server/` 下执行)、"不设自动阈值"的理由(第一天暴露既有 LLM 缺陷,不与本次改动混淆归因)。
- `design.md` R-7(坑 P57):本变更同时改 `SYSTEM_PROMPT`/加 `fast_context.tools`/插处理器,只锁确定性指标不足以发现 LLM 侧行为漂移,需在**任何代码改动前**先取一轮真实回复基线。
- 样板参照:`server/evals/starter_text.yaml`(turn 0 无 `user:` 吸收 greeting 的写法)、`server/evals/dual_brain_inject.yaml`(注释块引用 design 依据的写法)、`server/evals/r4_no_false_completion.yaml`(执行类请求措辞样例)。
- `server/judge_factory.py::judge_llm`:已读,确认其 docstring 说明的 gateway 复用机制;本场景全部 8 问 + greeting 共 9 个 turn 均无 `eval:` 语义判据,故未声明 `judge:` 配置块(见下方"自查发现"第 1 条)。

## TDD 证据

### RED

命令:
```
cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run pipecat eval run evals/baseline_probe.yaml -v -d --logs-dir eval-runs
```
输出摘要(`baseline_probe.yaml` 尚未创建):
```
Scenarios:
  baseline_probe:
    (failed to load: [Errno 2] No such file or directory: 'evals/baseline_probe.yaml')
  ✗ ws://localhost:7860 baseline_probe failed to load: [Errno 2] No such file or directory: 'evals/baseline_probe.yaml'
  0/1 passed, 1 failed  ·  0.0s
```
`echo $?` → `1`。为何该失败符合预期:场景文件是本卡的核心产出物,在写入前必然找不到,这是"改动前先证伪"的正确起点。

### GREEN

先起 bot(第一终端):
```
cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run bot.py -t eval 2>&1 | tee /tmp/pipecat-baseline.txt
```
干净启动,无异常(`tee` 日志尾部确认 `PipelineWorker#0: StartFrame#0 reached the end of the pipeline, pipeline is now ready.`)。

再跑场景(第二终端):
```
cd /home/ky/git/voice-agent/server && set -a && source .env && set +a && PYTHONPATH="$(pwd)" NLTK_DISABLE_IMPORT_SECURITY=1 pipecat eval run evals/baseline_probe.yaml -v -d --logs-dir eval-runs
```
输出摘要:
```
      turn 0 → (observe)              ✓ llm_response — "你好！我是你的AI语音助手…"
      turn 1 → "光合作用的基本化学方程式是什么？"        ✓ llm_response
      turn 2 → "居里夫人一共获得过几次诺贝尔奖？…"        ✓ llm_response
      turn 3 → "你好呀，今天心情怎么样？"                ✓ llm_response
      turn 4 → "你平时会不会觉得无聊呀？"                ✓ llm_response
      turn 5 → "帮我把浏览器里正在放的视频暂停一下"      ✓ llm_response
      turn 6 → "帮我订一张明天去上海的机票"              ✓ llm_response
      turn 7 → "她后来是怎么去世的？跟她的研究工作有关系吗？" ✓ llm_response
      turn 8 → "那如果坐高铁去呢，大概要多久？"          ✓ llm_response
  ✓ ws://localhost:7860 baseline_probe (52245ms)
  1/1 passed  ·  52.2s
```
`echo $?` → `0`。

**复跑一次确认可复现**(第二轮 bot 进程 + 第二次场景运行,不带 `-d`):同样 `1/1 passed · 51.5s`,`echo $?` → `0`。两轮回复文本因 LLM 采样存在措辞差异(符合预期的非确定性,不影响判定),两轮均全部 9 个 `llm_response` 事件命中。归档使用第一轮(`-d` 带调试日志)的原始回复文本,取自 `server/eval-runs/baseline_probe.eval.log`(59 行,已核对与终端 `-v` 输出一致)。

### 归档完备性判定

```
grep -c '^## Q' /home/ky/git/voice-agent/pipeline/task-dispatch/baseline/pre-change-responses.md
```
输出:`8`。

### 时序判定

取样时刻:
```
git -C /home/ky/git/voice-agent status --porcelain server/
?? server/evals/baseline_probe.yaml
```
不含 `server/prompts.py`/`server/bot.py`/`server/config.py`/`server/task_dispatch.py`/`server/task_dispatch_contract.py` 任一行,已原样贴进归档文件头部"时序证据"节。

## 自查发现

1. **judge 配置块未声明**:任务卡 Consumes 列出 `judge_factory.py::judge_llm` 作为依赖,但 C-17 步骤 1 原文明确"judge 只写 `event: response` 不加任何语义判据"——本场景全部 9 个 turn 均无 `eval:` 字段,pipecat 框架在这种情况下不会调用任何 judge(实测两轮跑通、退出码均为 0,未触发本地 Ollama 也未触发 `judge_factory`)。故未在 yaml 顶层加 `judge: eval: factory: "judge_factory.judge_llm"` 块——加了也是死配置,不加更贴合"不新增配置面"的契约措辞,且与 `dual_brain_smalltalk.yaml`(同样零 `eval:` 判据、零 `judge:` 声明)既有写法一致。判断依据:实测两轮 GREEN,而非猜测。若裁决认为这里仍应显式声明 judge 块(纯防御性/可读性目的),补一行即可,不影响任何测试结果。
2. **"多轮追问"的落地方式**:任务卡/C-17 原文只给出"2 条多轮追问"这一类别名称,未定义追问对象。为保证"固定 8 问"总量与"2/2/2/2"分类严格吻合,把 Q7/Q8 设计为分别回指 Q2(居里夫人)与 Q6(上海行程)的追问,而不是另起一段独立的 4-turn 小对话(否则总问数会超过 8)。这是本卡在缺口处做出的最小闭合选择,已在 yaml 注释与归档"备注"节写明理由,供 T-8 复用同一份 yaml 时对齐口径。
3. **owner 与实际执行节点不一致**:任务卡 frontmatter 写 `owner: qa-tester`,本次由 backend-dev 节点收到派单并执行。内容本身(建 yaml 场景 + 跑命令 + 写归档 md)不涉及任何 Python 代码改动,backend-dev 身份未构成障碍,按派单原样执行,不视为异常自行处理越权范围。
4. 归档 md 的 Q 小节最初误用三级标题(`### Q1`),与验收判据 `grep -c '^## Q'` 要求的二级标题不符,已在自查阶段发现并订正为 `## Q1`~`## Q8`,复测通过(输出 `8`)。

## 疑虑(供 RISKS)

- 上述自查发现 1(judge 块是否需要显式声明)为唯一实质性疑虑,已给出实测依据与两种选择的影响面,不影响本卡验收通过。
- `pipeline/task-dispatch/baseline/` 目录内已有其他并行任务卡(T-1 等)产出的文件(`mcp-event-sample.json`、`failure-path-samples.json`、`preflight-live.md`、`openclaw-agent-task-record-probe.md`),本卡未触碰、未纳入 commit,仅供留痕说明目录非本卡独占但本卡只写了自己的那一份文件。

## 记忆闭环

- 开工 recall:`agent-mem recall backend-dev "eval baseline pipecat scenario" 5` —— 命中的是同会话内已产生的操作记录(非跨会话历史经验),无可复用的历史踩坑/模式。
- 收工 save:命中"可靠解法模式"类别,已存(`mem_mskfvq0j_c60cacc1aaf6`):"pipecat eval 场景若全部 turn 只写 `event: response`、不带任何 `eval:` 语义判据,则整个 yaml 无需声明 `judge:` 配置块——退出码仍按 event 是否观测到判定"。
