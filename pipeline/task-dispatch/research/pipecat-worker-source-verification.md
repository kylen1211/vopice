# pipecat worker 源码核对 · task-dispatch(C4 派活)

> 2026-08-08,S1b 呈批回合中用户提问引发的追加核对。
> 用户指示:**"读完差下源码确认"**、**"用 codegraph 查"** —— 文档结论一律以源码复核为准,检索走 codegraph 不走 grep。
> 本文只记**源码实锤**与**由此产生的 S2a 约束**,不含产品决定。

---

## 0. 检索工具纪律(着重声明,后续 agent 照此执行)

**源码检索一律用 codegraph,不用 grep/Read 硬翻。** 本轮核对最初用 grep/sed 做,被用户纠正后改用 codegraph 复核,**codegraph 多给出四类 grep 拿不到的信息**(见 §5),其中一条直接改变了选型建议。

### 查本项目之外的源码必须传 `projectPath`(实操坑)

codegraph 默认查**当前会话项目**(voice-agent)。查任何外部源码都要显式指定该项目根,不传会在 voice-agent 索引里找外部符号,返回空或误命中同名符号。

本轮实际用法:

```
codegraph_explore(
  query="UIWorker _run_llm_turn respond_to_job start_ui_job_group LLMContextWorker BaseWorker job",
  projectPath="/home/ky/git/source-project/pipecat"
)
```

**可查的外部项目清单以 `/home/ky/git/codegraph-registry.md` 为准**(唯一事实源,本文不复制以免漂移);未登记的项目先建索引再登记。

---

## 1. 版本前提(所有下述行号成立的基础)

| 项 | 值 | 证据 |
|---|---|---|
| 项目锁定版本 | `pipecat-ai==1.6.0` | `server/pyproject.toml:7` |
| venv 实装 | `pipecat_ai-1.6.0.dist-info` | `server/.venv/lib/python3.11/site-packages/` |
| clone 副本 | git main `0db3c9a0a` | `~/git/source-project/pipecat` |
| **`workers/ui/ui_worker.py` 两份是否一致** | **逐字节一致,965 行** | `diff` exit=0 |

→ **clone 可直接作为 1.6.0 的核对依据**(就 UIWorker 这一支而言)。
→ 承接 `pipecat-capability-survey.md` §0 的同类结论(`BaseWorker.job`/`job_group` 行号在两版一致),本轮把 UIWorker 也纳入了已核实范围。
→ **仍未逐一核实的符号不得推定一致**,S2a 用到新符号需照此法复核。

---

## 2. UIWorker 的 LLM 确实跑一次完整推理(不是透传)【实锤】

`src/pipecat/workers/ui/ui_worker.py`:

```python
# :390
@job(name="respond", sequential=True)
async def _respond_job(self, message: BusJobRequestMessage) -> None:
    await self._run_llm_turn(message)
```

`_run_llm_turn`(:409-448)的实际动作:

1. 记下 in-flight job(`self._current_job = message`,:425)
2. `keep_history=False` 时清空自己的 context(:428-429 → `_reset_context`,:450)
3. 把 `render_query(message)`(默认读 `payload["query"]`,:407)作为 **`{"role": "user"}`** 消息 append,`run_llm=True`(:436-441)
4. **阻塞** `await self._pending`(:442),等某个 `@tool` 调 `respond_to_job`
5. 拿到结果 `send_job_response(job_id, response=..., status=...)`(:443-445)

**:430-435 注释原文要点**:query 用 `user` 角色是因为它是"要执行的请求";SDK 注入的 `<ui_state>` / `<ui_event>` 才是 `developer` 角色;`user` 角色同时标记 turn 边界,决定 `<ui_state>` 是否注入。

**单飞语义** docstring :419-420 原文:
> Spanning the full round-trip is what makes the job single-flight

→ 正是 `external-research.md` §1.1 认定的"官方正解"(整个往返跑在被追踪的 handler 内,取消才真生效),与 code-assistant 示例的缺陷实现相对照。

---

## 3. 路由机制:job 与 activation **两套并存**(修正早前结论)

**被修正的结论**:本轮早前(未用 codegraph 前)判定"路由是 job,不是 activation"——**太绝对,已推翻**。

**支持新结论的依据**:codegraph blast radius 露出 activation 路线的官方示例群:

- `examples/multi-worker/local-handoff/local-handoff-two-agents-tts.py`
- `examples/multi-worker/distributed-handoff/pgmq-handoff/llm.py`
- `examples/multi-worker/distributed-handoff/redis-handoff/llm.py`
- `examples/flows/multi_worker_handoff.py`

API 是 `LLMWorker.activate_worker(worker_name, *, args, deactivate_self=False, messages=None, result_callback=None)`(`llm_worker.py:208-235`)。

| 机制 | 语义 | 适用 |
|---|---|---|
| **job**(`BaseWorker.job`,:694 / `job_group`,:782) | 派一件事出去、等结果,**主导权不转移** | ✅ 派活场景 |
| **activation**(`activate_worker`) | 把对话主导权整个交给另一个 worker | ❌ 快脑不能交出主导权 |

→ 派活选 **job**,判断不变;但"只有 job"的表述是错的,S2a 文档不得沿用。

---

## 4. `respond_to_job` 两种互斥投递模式【实锤,与 C1/C3 直接相关】

`ui_worker.py:462-507`,docstring 原文:"the two modes are mutually exclusive (one voice per turn)"

| 模式 | 行为 | 源码 |
|---|---|---|
| **默认** | job 响应 `{"answer": answer}`,**交请求方的快脑去措辞** | :505-506 |
| **`tts_speak=True`** | `answer` 由请求方 TTS **逐字念出**(`BusTTSSpeakMessage`, `append_to_context=True`),job 响应 `None`,快脑不重复说 | :494-504 |

`append_to_context=True` 保证快脑知道自己"说过"这句,不会重复。

**与既有裁决的关系(只陈述,不重开争论)**:用户 2026-08-08 已两次裁决"完成真实性归 OpenClaw,本项目不核验不改写其转述"(见 `ledger.md` 与 PRD 硬约束 C1),默认模式即该裁决对应的路径。`tts_speak=True` 是官方现成的另一条投递方式,**S2a 选型时它是台面上的选项,是否采用由用户决定**,本文不做倾向性建议。

---

## 5. codegraph 独有发现(grep 拿不到,四条)

### 5.1 完整继承链(含早前遗漏的一层)

```
UIWorker → LLMContextWorker → LLMWorker → PipelineWorker → BaseWorker → BaseObject / BusSubscriber
```

**`LLMWorker` 本身就是 `PipelineWorker`** —— `llm_worker.py:106`:`pipeline = Pipeline([self._llm])`,且 `enable_rtvi=bridged is None`(:113,默认开)。

→ "第二个 LLM"不是裸调用,它是**又一个带完整 pipeline 与 RTVI 的 root worker**,与主 worker 平级挂在同一 `WorkerRunner` 上。

### 5.2 工具执行期的帧延迟机制【对派活关键】

`defer_tool_frames=True` 为默认(`llm_worker.py:76`)。`_track_tool_call`(:264-275)+ `_flush_deferred_frames`(:277-286):**工具执行期间 queue 的所有 frame 被 hold,等最后一个工具完成才统一 flush**。

→ 派活工具跑 subprocess 期间不会有半截输出插队。这条是既有能力,不需自研。

### 5.3 `@tool` 的注册路径与取消/超时开关

`_register_tools`(`llm_worker.py:254-262`)原文:

```python
llm._register_direct_function(
    tracked,
    cancel_on_interruption=method._pipecat_cancel_on_interruption,
    timeout_secs=method._pipecat_timeout_secs,
)
```

→ 印证 `pipecat-capability-survey.md` §2.4 的 `@tool_options(cancel_on_interruption=False, timeout_secs=30)` 有真实开关支撑,非文档说法。派活工具**必须**设 `cancel_on_interruption=False`(用户插话不该撤销已派任务)。

### 5.4 测试覆盖缺口【S2a 必须处置】

codegraph blast radius 标注:

| 符号 | 覆盖情况 |
|---|---|
| `BaseWorker`(`base_worker.py:102`) | `tests/test_base_worker.py` ✓ |
| `respond_to_job`(`ui_worker.py:462`) | 5 个官方示例覆盖 ✓ |
| `LLMWorker`(`llm_worker.py:51`) | 7 个 handoff/multi-worker 示例覆盖 ✓ |
| **`UIJobGroupContext`(`ui_job_context.py:29`)** | **⚠️ no covering tests found** |

而四信封里的 `group_started` / `group_completed` 正是它发的(`__aenter__ → BusUIJobGroupStartedMessage`、`__aexit__ → BusUIJobGroupCompletedMessage`)。

---

## 6. 必须带进 S2a 的约束

1. **[测试·硬要求]** 若选 `UIWorker` 并使用 `ui_job_group` 进度卡链路,**必须自行补测试**——官方在该链路上无覆盖。至少覆盖:四信封(`group_started`/`job_update`/`job_completed`/`group_completed`)是否实际抵达客户端、`cancellable=True/False` 是否分别生效、`start_ui_job_group` 是否确实立即返回不阻塞调用方。测试策略段须显式列出这几条,不得以"官方件默认可靠"带过。
2. **[选型]** 三选一,不是二选一:`BaseWorker`(无第二 LLM)/ `LLMContextWorker`(有第二 LLM,无进度卡)/ `UIWorker`(有进度卡 + 屏幕能力)。UIWorker 的**本职是驱动客户端 GUI**(docstring :77-81),C4 用不上其屏幕能力;选它的理由是为 2 期 G4「按需监控本机页面内容实时交互」提前占位,代价即 §5.4 的补测试。
3. **[必设]** 派活类 `@tool` 设 `cancel_on_interruption=False`,理由见 §5.3。
4. **[不得沿用]** "路由只有 job 没有 activation"的表述已被推翻,见 §3。
5. **[检索纪律]** 后续任何 pipecat/openclaw 源码核对,走 codegraph + `projectPath`,见 §0。

---

## 7. 本轮未核实(诚实标注,不得推定)

- `start_ui_job_group` 的四信封**实际抵达客户端**的端到端行为——只核实了服务端 `send_bus_message` 的发送侧(`_maybe_forward_job_update`:707 / `_maybe_forward_job_completed`:727,`target=None` 广播),客户端 `RTVIEvent.UIJobGroup` 消费侧未核实。
- 主 worker(我们的双脑 `PipelineWorker`)向 UIWorker 派 job 的**具体接线方式**——docstring :96 称 `PipelineWorker connects a UIWorker to the client automatically when RTVI is enabled -- no extra wiring`,本项目 `bot.py:316` 已传 `rtvi_observer_params`,但"自动连接"的确切含义与所需代码未逐行核实。
- 1.6.0 与 main 在 `ui_worker.py` 之外的差异(`llm_worker.py` / `base_worker.py` / `ui_job_context.py` 未做 diff)。
