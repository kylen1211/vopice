# T-5 backend-notes · 装配层:`bot.py` 五处挂点 + `AssembledPipeline` 四个新字段 + 三 worker 挂同一 runner

> owner: backend-dev | change: task-dispatch | 日期: 2026-08-08

## 重要更正的应用

按主会话"重要更正"指示,`build_dispatch_stack` 按 `server/task_dispatch.py` 实装签名调用:

```python
def build_dispatch_stack(agent_id: str, *, llm: LLMService[Any], cli_override: str | None = None) -> DispatchStack
```

即 `cfg.openclaw_agent_id`(单值,非整个 `Config`)+ 独立构造的第三个 `LLMService` 实例(`llm=`)+ 函数体内读取的 `TASK_DISPATCH_CLI`。未按 T-5.md 冻结文字里的过期签名调用。

## 完成清单(对照任务卡 Produces 逐条)

- [x] `server/bot.py::assemble_pipeline` 五处挂点全部落地:
  - ① `fast_context = LLMContext(tools=[task_dispatch.dispatch_task, task_dispatch.get_task_status])`(填 K1 缺口)。
  - ② `stack = task_dispatch.build_dispatch_stack(cfg.openclaw_agent_id, llm=dispatch_llm, cli_override=os.environ.get(...))`,`injector = stack.build_injector()` 插入快脑分支**头部**、位于既有 `consumer` 之前。
  - ③ `PipelineWorker(..., app_resources=stack.app_resources)`(填 K3 缺口)。
  - ④ `PipelineWorker(name=task_dispatch_contract.MAIN_WORKER_NAME, ...)`。
  - ⑤ `AssembledPipeline` 追加 `injector` / `dispatch_worker` / `exec_worker` / `dispatch_registry` 四个字段。
- [x] `server/bot.py::run_bot` 一处改动:`worker.app_resources.main_worker = worker`(反向引用回填,design.md 方案 C 步骤5)后 `await runner.add_workers(worker, assembled.dispatch_worker, assembled.exec_worker)`。
- [x] `server/config.py`:`OPENCLAW_AGENT_ID` 加入 `_BASE_REQUIRED_ENV_TO_FIELD`,`Config` 新增 `openclaw_agent_id: str` 字段,写法沿用既有约定(插在非默认值字段区,不破坏 dataclass 字段顺序)。
- [x] `server/.env.example`:新增一行占位符 `OPENCLAW_AGENT_ID=CHANGE_ME_OPENCLAW_AGENT_ID`,必需项计数注释同步从 8 改 9。
- 不产出(遵守边界):未改 `server/evals/fault_run/bot.py`(独立核对见下方"自查发现"倒数第二条);未改 `server/prompts.py`/`server/task_dispatch.py`/`server/task_dispatch_contract.py`(均出独占路径)。

## 派活委托 LLM(TaskDispatchWorker 的第二个 LLM)构造决策

契约/design.md 均未指定这个第三个 `LLMService` 实例该用哪个模型档位,也未说明是否需要 `system_instruction`(这两点在 `pipeline/task-dispatch/` 全部文档里检索为零命中,已用 `grep` 核实)。本卡按以下依据自行敲定,记录在案供评审:

1. **模型**:复用 `cfg.llm_model`(快脑档位),不用 `cfg.slow_llm_model`。理由:`dispatch_task` 工具调用会同步 `await` 这个委托 LLM 的完整一轮推理(`timeout_secs=20.0`,契约 §0.2 T1),而 `slow_llm_model` 是"故意选慢档"(`bot.py` 既有注释原文),用在这里会经常性逼近/超过 20 秒工具超时。
2. **`system_instruction`**:不设置。依据是 T-4 自证脚本(`T-4-notes.md` 附录 `_build_llm`)用完全相同的极简方式构造(仅 `model=`,无 system_instruction)并已端到端跑通;`ui_worker.py::_run_llm_turn` 显示委托轮由 `UIWorker` 自身的 `respond` job 驱动、只把 query 作为 user 消息喂入,唯一挂载的 `reply` 工具 docstring 已足够详尽。本次端到端真机追踪(见下)证实这个决策可行:委托 LLM 正确调用了 `reply(answer=..., tasks=[...])`。
3. 若评审认为委托 LLM 需要独立 `system_instruction`(如强调"善用 fan-out/摘要质量"等),该常量按项目既有 R4 约定应落 `server/prompts.py`,不在本卡独占路径内——留待后续卡处理,已记入 RISKS。

## 改动文件

- `/home/ky/git/voice-agent/server/bot.py`
- `/home/ky/git/voice-agent/server/config.py`
- `/home/ky/git/voice-agent/server/.env.example`
- `/home/ky/git/voice-agent/server/.env`(本机本地文件,gitignored,不进仓库;补了一行 `OPENCLAW_AGENT_ID=dev` 供本卡真机验收用,`git status --porcelain` 对此无感知)

```
$ git -C /home/ky/git/voice-agent status --porcelain -- server/
 M server/.env.example
 M server/bot.py
 M server/config.py
```
只出现三条独占路径,无其余文件被动。

## TDD 证据

### RED(结构性,改动前对当时的 `bot.py` 取证)

```
$ cd server && NLTK_DISABLE_IMPORT_SECURITY=1 .venv/bin/python -c "
import bot  # (伪造必需 env,监听 dotenv)
print('assemble_pipeline exists:', hasattr(bot, 'assemble_pipeline'))
for f in ('injector','dispatch_worker','exec_worker','dispatch_registry'):
    print(f, 'in AssembledPipeline fields:', f in inspect.getsource(bot.AssembledPipeline))
print('task_dispatch imported in bot.py:', 'task_dispatch' in dir(bot))
"
assemble_pipeline exists: True
injector in AssembledPipeline fields: False
dispatch_worker in AssembledPipeline fields: False
exec_worker in AssembledPipeline fields: False
dispatch_registry in AssembledPipeline fields: False
task_dispatch imported in bot.py: False
```
为什么该失败:改动前 `bot.py` 完全不知道 `task_dispatch` 模块的存在,四个新字段自然不存在——这就是本卡要填的缺口。

### GREEN 1 · 结构性验证(独立脚本,绕开 conftest.py 缺口,见下方"疑虑①")

用 `tests/test_dual_brain.py::TestAssemblePipeline` 同款 `_FakeTransport`(真 `FrameProcessor` 实例,非纯桩)手工驱动 `assemble_pipeline`:

```
TOOLS standard_tools: ['dispatch_task', 'get_task_status']
worker.name: voice-main
app_resources not None: True
main_worker pre-run_bot: None
dispatch_registry: DispatchRegistry 0
dispatch_worker.name: task-dispatch
exec_worker.name: openclaw-exec
fast branch: ['PipelineSource', '_DispatchMaterialInjector', 'ConsumerProcessor', 'LLMUserAggregator', 'OpenAILLMService', '_FastAnswerTap', 'FunctionFilter', 'ElevenLabsTTSService', 'FrameProcessor', 'LLMAssistantAggregator', 'PipelineSink']
slow branch: ['PipelineSource', 'LLMUserAggregator', 'OpenAILLMService', 'SentenceAggregator', 'ProducerProcessor', 'LLMAssistantAggregator', 'PipelineSink']
transport.output() in fast: True
transport.output() in slow: False
```

核对:
- `fast_context.tools` 恰含 `dispatch_task`/`get_task_status` 两个工具(契约 §0.2)。
- 注入器紧跟 `PipelineSource` 之后、`ConsumerProcessor` 之前(快脑分支头部,design.md 方案 C 步骤4②)。
- `worker.name` 等于 `MAIN_WORKER_NAME`("voice-main");`dispatch_worker.name`/`exec_worker.name` 分别等于 `DISPATCH_WORKER_NAME`/`EXEC_WORKER_NAME`(契约 §0.1)。
- `app_resources` 非空,`main_worker` 在 `run_bot` 回填前为 `None`(符合 `AppResources` docstring 约定)。
- `dispatch_registry` 是 `DispatchRegistry` 实例,空(会话级,新构造)。
- 慢脑分支不含 `transport.output()`,仍是唯一含输出的快脑分支——形状不变(design.md `bot.py:278`/`:289` 注释所述结构维持)。

### GREEN 2 · 验收用例1:装配链端到端追踪(坑 P55,硬要求,**真机、非 mock**)

按契约 §1 命令口径驱动,一次性追踪场景 `/tmp/trace_dispatch.yaml`(不落仓库):

```yaml
name: trace_dispatch
turns:
  - expect: [{event: response}]   # 吸收 on_client_ready 问候
  - user: "帮我派一个后台任务:写一句话,内容是「T5-TRACE-OK」,不要做任何其他事,写完就结束。"
    expect: [{event: response}]
```

```
$ cd server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run bot.py -t eval 2>&1 | tee /tmp/pipecat-dispatch.txt &
$ cd server && set -a && source .env && set +a && PYTHONPATH="$(pwd)" NLTK_DISABLE_IMPORT_SECURITY=1 pipecat eval run /tmp/trace_dispatch.yaml -v --logs-dir eval-runs
      turn 0 → (observe)
        ✓ llm_response — "你好，我是你的AI语音助手，可以回答问题、协助日常任务。随时告诉我你需要什么帮助。"
      turn 1 → "帮我派一个后台任务:写一句话,内容是「T5-TRACE-OK」,不要做任何其他事,写完就结束。"
        ✓ llm_response
  ✓ ws://localhost:7860 trace_dispatch (8989ms)
  1/1 passed · 9.0s
```

**逐挂点证据(对照任务卡验收用例1 逐条,原样贴自 `/tmp/pipecat-dispatch.txt`)**:

- **挂点1**(能力边界段):
  ```
  $ python3 -c "import prompts; print('no ability to take real-world actions' in prompts.SYSTEM_PROMPT)"
  False
  ```
- **挂点2、3**(两个新模块):`uv run bot.py -t eval` 全程无 import 异常回溯(`grep -niE "traceback|exception|error" /tmp/pipecat-dispatch.txt` 排除 `ErrorFrame`/GPU探测噪音后零命中)。
- **挂点4**(装配):见上方"GREEN 1"——`fast_context.tools` 长度2、注入器在快脑分支头部、`app_resources` 非空、主 worker `name=="voice-main"`。
- **挂点5**(runner):
  ```
  pipecat.workers.runner:_send_registry:466 - WorkerRunner 'runner-56ca8f06': broadcasting registry: ['voice-main', 'task-dispatch', 'openclaw-exec']
  ```
  三个 root worker,名字与 §0.1 表逐字一致。
- **挂点6**(`dispatch_task` 被调用):
  ```
  pipecat.services.llm_service:_run_function_call:1335 - OpenAILLMService#0 Calling function [dispatch_task:call_47b6526bd0b9fa30] with arguments {'request': '帮我派一个后台任务:写一句话,内容是「T5-TRACE-OK」,不要做任何其他事,写完就结束。'}
  ```
- **挂点7**(第二个 LLM 推理轮次):
  ```
  pipecat.services.openai.base_llm:get_chat_completions:304 - TaskDispatchLLM: Generating chat from context [{'role': 'user', 'content': '帮我派一个后台任务:...'}]
  pipecat.services.llm_service:_run_function_call:1335 - TaskDispatchLLM Calling function [reply:call_8f31d9d6ac9db323] with arguments {'tasks': ['写一句话，内容是「T5-TRACE-OK」。'], 'answer': '已成功派发后台任务。'}
  ```
- **挂点8**(reply 起 exec job 与 respond_to_job 次序):
  ```
  task_dispatch:_dispatch_one:453 - [task-dispatch] exec-dispatched response={'session_key': 'agent:dev:voice-agent-cc35ab3f0ee1', 'lookup': 'agent:dev:voice-agent-cc35ab3f0ee1', 'degraded': None}
  ```
  快脑侧同一秒内(`23:35:12.970`)即拿到 `dispatch_task` 的 `FunctionCallResultFrame`,证明 `reply()` 未等 exec job(真实 CLI 派发耗时到 `23:35:17`)完成就已回应快脑(非阻塞,FR-1 判据1 核心证据)。
- **挂点9**(session key / tasks show 轮询命中):
  ```
  task_dispatch:_handle_dispatch:632 - [openclaw-exec] dispatched session_key=agent:dev:voice-agent-cc35ab3f0ee1 degraded=None
  ```
  `degraded=None` 即代表 `tasks show` 轮询命中(`_poll_until_visible` 返回 `found=True`)。**"detached spawn 的 pid" 这一分句本卡无法提供日志证据**——`task_dispatch.py` 全文 `grep -n pid` 零命中,T-4 实装未记录 spawn pid 到日志,这是任务卡验收文字与 T-4 实际落地之间的差异,超出本卡独占路径(`task_dispatch.py` 不可改),已记 RISKS。
- **挂点10**(events_wait 后台循环启动):
  ```
  task_dispatch:_run_events_loop:717 - [openclaw-exec] mcp-bridge-up worker=openclaw-exec
  ```
  时间戳 `23:34:12`,早于任何派活请求(`23:35:xx`),证明 bridge 确实在 `on_worker_ready` 时就绪、不等首次派活触发(契约 §0.8 条5)。
- **挂点11**(事件命中注册表并入队/移除,第二次真派发,详见下方"疑虑②"):
  ```
  task_dispatch:_maybe_report_terminal_event:770 - [openclaw-exec] terminal-report session_key=agent:dev:voice-agent-dc741fa63f72 label='写一篇大约400字的短文，主题是「T5装配验收」。 要求： 1. 内容围绕T5装'
  ```
- **挂点12**(注入器合并推下游一条 `LLMMessagesAppendFrame`,随后快脑产生一次 response):`_DispatchMaterialInjector._drain_loop` 本身无日志行(同挂点9同一性质的 T-4 实装缺口,见 RISKS),改用**更直接的功能性证据**——fast_context 在下一次生成前的完整消息列表原样出现渲染后的注入模板:
  ```
  pipecat.services.openai.base_llm:get_chat_completions:304 - OpenAILLMService#0: Generating chat from context [..., {'role': 'user', 'content': '[派活回流|任务:写一篇大约400字的短文，主题是「T5装配验收」。...] T5装配验收是确保产品从装配完成走向交付合格的关键质量关口... 这条信息由你自行决定何时、如何说给用户。'}]
  ```
  且**该轮生成没有任何新的用户输入**(eval 场景当时无新 turn)——是注入帧 `run_llm=True` 自主触发的一次生成,随后 TTS 真实播出:
  ```
  pipecat.services.tts_service:_push_tts_frames:1167 - CartesiaTTSService#0: Generating TTS [关于「T5装配验收」的短文已撰写完毕。]
  pipecat.services.tts_service:_push_tts_frames:1167 - CartesiaTTSService#0: Generating TTS [内容涵盖了零部件核对、精度测量、系统与电气测试、安全合规核验以及记录归档五个主要环节...]
  ```
  全链路(挂点1-12)均为真实调用:真 LLM 网关(快脑/慢脑/委托三路)、真 openclaw daemon(真实 `openclaw agent`/`tasks show` 子进程)、真 `openclaw mcp serve` stdio bridge、真 `events_wait`——无一处 mock。

### GREEN 3 · 验收用例3:冒烟启动

```
$ cd server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run bot.py -t eval 2>&1 | tee /tmp/pipecat-dispatch.txt
...
WorkerRunner 'runner-56ca8f06': added worker 'voice-main'
WorkerRunner 'runner-56ca8f06': added worker 'task-dispatch'
WorkerRunner 'runner-56ca8f06': added worker 'openclaw-exec'
...
voice-main: StartFrame#0 reached the end of the pipeline, pipeline is now ready.
```
无异常回溯,三个 worker 就绪行齐全。

### GREEN 4 · 验收用例4:D-003 守法①边界

```
$ git -C /home/ky/git/voice-agent diff server/bot.py | grep -E "^\+" | grep -v "^+++" | awk '{line=$0; sub(/^\+/,"",line); if (line ~ /^[A-Za-z_]/) print line}'
import os
import task_dispatch
import task_dispatch_contract
```
第0缩进层新增行只有三条 import,其余新增行均在函数/dataclass 体内(非零缩进)。`os.environ.get(task_dispatch_contract.ENV_TASK_DISPATCH_CLI)` 在 `assemble_pipeline` 函数体内读取,未放模块顶层。

### GREEN 5(有条件)· 验收用例5:既有测试无回归 —— **超出任务卡预期的失败面,详见"疑虑①"**

```
$ cd server && NLTK_DISABLE_IMPORT_SECURITY=1 .venv/bin/python -m pytest tests/ -q
FAILED tests/test_config.py::test_config_repr_redacts_secrets - config.ConfigError: 缺少必需环境变量：OPENCLAW_AGENT_ID
FAILED tests/test_config.py::test_deepgram_and_cartesia_selected_together_succeeds
ERROR tests/test_bot.py::test_stt_builder_sets_language_hints_to_zh - config.ConfigError: 缺少必需环境变量：OPENCLAW_AGENT_ID
ERROR tests/test_bot.py::test_tts_builder_sets_voice_from_config
ERROR tests/test_bot.py::test_deepgram_stt_builder_sets_language_and_smart_format
ERROR tests/test_bot.py::test_cartesia_tts_builder_sets_voice_and_language_from_config
ERROR tests/test_dual_brain.py::TestAssemblePipeline::test_pipeline_shape
ERROR tests/test_dual_brain.py::TestAssemblePipeline::test_rtvi_ignores_slow_branch
ERROR tests/test_dual_brain.py::TestAssemblePipeline::test_greeting_turn_emits_no_material
ERROR tests/test_dual_brain.py::TestAssemblePipeline::test_non_slow_error_not_reported_as_slow_failed
ERROR tests/test_dual_brain.py::TestAssemblePipeline::test_slow_failure_pushes_server_message
2 failed, 38 passed, 15 warnings, 9 errors in 3.84s
```
退出码非0。根因单一且确定:全部11条失败/错误的报错原文都是同一行 `config.ConfigError: 缺少必需环境变量：OPENCLAW_AGENT_ID`——`server/tests/conftest.py::bot_module` fixture 的 `_FAKE_REQUIRED_ENV` 字典未包含新必需项(该 fixture 供 `test_bot.py`/`test_dual_brain.py::TestAssemblePipeline` 共用),`test_config.py` 自己手写的 `Config(...)`/必需项断言列表同理未同步。详见下方"疑虑①"——这是**范围比任务卡文字预期更大**的已知类别失败,不是本卡代码逻辑缺陷。

改动前基线(RED,供对比):
```
$ cd server && NLTK_DISABLE_IMPORT_SECURITY=1 .venv/bin/python -m pytest tests/ -q
49 passed, 21 warnings in 4.17s
```

### GREEN 6 · 验收用例6:副本不动

```
$ git -C /home/ky/git/voice-agent status --porcelain server/evals/fault_run/
(无输出)
```

### 静态检查

```
$ cd server && .venv/bin/python -m ruff check bot.py config.py
All checks passed!
$ .venv/bin/python -m ruff format --check bot.py config.py
(与本卡改动无关的既有格式差异,改动前后同样存在,见"自查发现")
$ .venv/bin/pyright bot.py config.py
27 errors (全部 reportMissingImports,pyright 未感知 .venv 位置——与 T-4-notes.md 记录的同一环境缺口,数字完全一致,非本卡引入)
```

## 自查发现

- **完整性**:五处装配挂点、`run_bot` 一处改动、`config.py`/`.env.example` 逐条落地;边界情况(main_worker 起始为 None、快脑分支形状不变、慢脑分支无输出组件)均已结构性验证。
- **质量**:命名、注释风格贴合既有 `dual_brain`/`prompts`/`sentinel` 模块级 `import xxx` 惯例(未用 `from x import y` 打散引用面);`AssembledPipeline` 新字段类型标注复用既有"跨模块引用私有类名"惯例(`dual_brain._SlowMaterialFilter` 已是先例,`task_dispatch._DispatchMaterialInjector` 同构)。
- **纪律**:`git status --porcelain -- server/` 只有三条独占路径文件;`ruff format --check` 的既有格式差异经 `git stash` 对比确认与本卡改动无关(改动前后行号/内容一致,未新增)。
- **测试**:全部验证走真实调用(真 LLM 网关三路、真 openclaw daemon、真 mcp bridge),仅结构性检查(GREEN 1)使用纯 `FrameProcessor` 桩(与既有 `test_dual_brain.py::TestAssemblePipeline._FakeTransport` 同款手法,非 mock 被测代码本身)。

## 疑虑(RISKS,供裁决)

1. **验收用例5"既有测试无回归"的失败面比任务卡文字预期更大**(优先级最高,建议主会话核实归属)。任务卡原文只提到"`tests/test_config.py` 若因新增必需项失败,修正归 T-6"。实测根因确实单一(`OPENCLAW_AGENT_ID` 未进 `_FAKE_REQUIRED_ENV`),但该字典定义在 `server/tests/conftest.py`——这个文件**既不在 T-5 独占路径,也不在 T-6.md 独占路径列表内**(T-6.md `独占路径` 只列 `test_task_dispatch.py`/`test_dual_brain.py`/`test_config.py` 三个,`conftest.py` 在 T-6"Consumes"节被明确标注为"本卡不扩大其使用面,亦不新增定义点"——即 T-6 本身也不打算改它)。级联后果:除 `test_config.py` 的 2 条断言外,还有 `test_bot.py` 4 条、`test_dual_brain.py::TestAssemblePipeline` 5 条(共用同一 fixture)一并失败——总计 2 failed + 9 errors,而非任务卡文字暗示的"仅 test_config.py 局部失败"。本卡按边界纪律未touch `conftest.py`(不在本卡独占路径),原样记录、不跨卡改文件。**建议**:主会话在派 T-6 时明确把 `server/tests/conftest.py::_FAKE_REQUIRED_ENV` 补充 `OPENCLAW_AGENT_ID` 一并纳入其任务范围(或另开一张最小卡),否则 T-6 完工前 `pytest tests/ -q` 会持续非 0 退出码。
2. **委托 LLM 的模型选型与"无 system_instruction"是本卡在契约/design.md 均未明确指定的情况下自行敲定的**(检索 `pipeline/task-dispatch/{design.md,contract/cases.md,prd.md,tasks/T-5.md,tasks/T-4.md}` 全部零命中 `system_instruction`/`prompt_guide`/委托 LLM 模型选型相关文字)。已在上方"派活委托 LLM 构造决策"节写明依据(复用 `cfg.llm_model` 而非 `cfg.slow_llm_model`,理由是同步阻塞快脑工具调用、`timeout_secs=20`;不设 `system_instruction`,依据是 T-4 自证脚本同款写法已跑通)。本轮真机追踪(GREEN 2 挂点7)证实委托 LLM 在无 system_instruction 情况下正确调用了 `reply()` 并给出合理的 `answer`/`tasks` 拆分——功能上可用,但若评审认为委托 LLM 需要专门的角色设定(如强调任务书撰写规范、多任务拆分策略),该常量按 R4 约定应新增进 `server/prompts.py`,不在本卡独占路径内,需另立变更或扩大后续卡范围。
3. **任务卡验收用例1 两处日志证据的字面预期与 T-4 实际落地有出入**(均已在上方"逐挂点证据"用替代证据补齐,不影响功能正确性判断):
   - 挂点9"detached spawn 的 pid"——`task_dispatch.py` 全文无任何 pid 日志(`grep -n pid` 零命中)。
   - 挂点12"日志出现注入器一次取空、合并、推下游一条 LLMMessagesAppendFrame 的行"——`_DispatchMaterialInjector._drain_loop` 本身无 logger 调用。
   两者均是 `server/task_dispatch.py`(T-4 独占路径)的实现细节,本卡无法补日志(出独占路径)。已用功能性证据(fast_context 消息列表原样出现渲染后的注入模板 + 无新用户输入下的自主生成)顶替,证明链路确实打通,但字面"某一行日志"意义上的证据缺失,如实标注供裁决是否需要另立最小卡给 `task_dispatch.py` 补两行 debug 日志。
4. **真机追踪过程中发现一个未被任何文档记录的时序竞态(功能上不算 bug,已用测试设计规避,原样记录)**:`OpenClawExecWorker._handle_dispatch` 要等 `tasks show` 轮询确认任务记录可见后才把 `session_key` 写入 `DispatchRegistry`(§0.4/design.md 步骤9 既定次序),而 `events_wait` 的结论事件是并发到达的独立通道;若真实 openclaw 任务完成得比这套"派发→轮询确认可见→注册表写入"链路还快(第一次追踪用"写一句话"这种极简任务,`session_key=agent:dev:voice-agent-cc35ab3f0ee1` 派发确实复现了这个窗口:`_handle_dispatch` 完成于 `23:35:17.867`,而 `openclaw tasks show` 旁路核对显示该任务此时已是 `succeeded` 终态),其结论事件会在 `registry.add()` 之前抵达 MCP 流,被 `_maybe_report_terminal_event` 的 `entry is None` 分支静默丢弃(无日志、不重试——设计如此,ADR-5 不做兜底轮询)。第二次追踪改用耗时稍长的"400字短文"任务后正常复现挂点11/12。这不是本卡代码问题(装配逻辑与此无关,竞态发生在 T-4 独占的 `task_dispatch.py` 内部),但可能是此前 T-4 自证测试(用 `WorkerRunner` 直接调用、非真实 LLM 触发的极快场景)未覆盖到的边界,记录供主会话评估是否值得登记进 `pipeline/debts.md`(本卡不越权直接登记)。
5. **`server/.env` 本地追加了一行 `OPENCLAW_AGENT_ID=dev`**(供本卡真机验收用,已确认 `.env` 在 `.gitignore` 内、不进仓库、不影响 git 状态)。
