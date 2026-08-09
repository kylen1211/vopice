# review.md · task-dispatch(s6 代码审查)

> change_id: task-dispatch | 产出: code-reviewer | 日期: 2026-08-09
> 范围:`pipeline/task-dispatch/review-package.diff`(base_commit `cb3e857`..HEAD,21 文件 / +2626 -9),对照 `design.md`、`contract/cases.md`、`pipeline/debts.md`(D-013~D-018)、九张任务卡。
> 已跑验证:`cd server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run python -m pytest tests/ -q` → 67 passed;`.venv/bin/ruff check task_dispatch.py task_dispatch_contract.py tests/test_task_dispatch.py bot.py config.py` → All checks passed;`uv run pyright task_dispatch.py task_dispatch_contract.py` → 0 errors, 0 warnings。
> **最终判决见文末「s6 复评(re-review)」section**——本文件正文(§规格符合表 / §发现)是 s6 初评时点(pass=false)的快照,已按上一轮 Important 发现修复并复核通过(pass=true),正文未回改,以避免抹去审查轨迹。

## 规格符合

| 契约项 | 结果 | 依据 |
|---|---|---|
| §0.1 worker 名/挂同一 WorkerRunner | ✅ | `task_dispatch_contract.py:1808-1810`;`bot.py::run_bot` `runner.add_workers(worker, assembled.dispatch_worker, assembled.exec_worker)` |
| §0.2 T1/T2 工具签名、载荷形状、`timeout_secs` | ✅ | `task_dispatch.py:96-150` 与契约表逐字段核对一致 |
| §0.3 `reply` 次序不变量 + 在途上限(ADR-8) | ✅ | `task_dispatch.py:396-450`;`tests/test_task_dispatch.py::TestTaskDispatchWorkerReply` 直接断言代码次序(a)与不等待(b)两重证据 |
| §0.4 exec worker job 契约、`degraded` 封闭集 | ✅ | `task_dispatch.py:552-660` |
| §0.5 `TaskView` 字段挑选、恒在/条件字段 | ⚠️（见下方"发现"Important项） | 逻辑本身(`_build_task_view:189-204`)读码确认与契约一致,且 T-8 真机会话(test-report.md C-05)有一次实测印证,但 L1 单测零覆盖,回归安全网缺失 |
| §0.6 session key 模板/生成 | ✅ | `_generate_session_key`;`tests/test_task_dispatch.py::test_session_key_shape_matches_template` |
| §0.7 argv/退出码判读(三条命令) | ✅ | `task_dispatch_contract.py::cmd_agent/cmd_tasks_show/cmd_mcp_serve`;`tests/test_task_dispatch.py::test_openclaw_argv_matches_contract_verbatim` |
| §0.8 MCP bridge(事件类型全集/筛选字段/游标推进) | ✅ | `_run_events_loop`/`_maybe_report_terminal_event`(:722-756)与 `baseline/mcp-event-sample.json` 逐字段核对(设计段内已实测,T-8 真机复验有终态播报通过记录) |
| §0.9 素材注入模板/合并规则 | ✅ | `prompts.py::INJECT_TASK_TERMINAL_TEMPLATE`;`_DispatchMaterialInjector._drain_loop`;`tests/test_task_dispatch.py::TestDispatchMaterialInjector` 三条用例(单帧合并/C-09步骤4零回查/C-10并发合并) |
| §0.10 测试开关只在函数体内读取 | ✅ | `bot.py:235` 内 `os.environ.get(task_dispatch_contract.ENV_TASK_DISPATCH_CLI)`,模块顶层零环境变量读取 |
| C-16(不启用 ui_job_group) | ✅ | grep 零命中(注释性说明除外)+ `test_task_dispatch_worker_has_no_job_group_symbols` 静态断言 |
| D-003 守法(不扩大既有债务面) | ✅ | `task_dispatch.py`/`task_dispatch_contract.py` 零 `load_config`/环境变量读取;新增测试文件零 `import bot` |

无 ❌(未发现与契约字面相悖、且未登记为债务的实现缺陷)。§0.5 一项标 ⚠️ 是因为"逻辑正确但缺回归测试"这件事本身不属于"diff 内验不了"的范畴(能在 diff 内直接判定),已单独在下方"发现"里作为 Important 项报出,不算作规格违反。

## 做得好的

- **D-003 守法执行到位**:`task_dispatch.py`/`task_dispatch_contract.py` 全程零 `config.load_config()`/环境变量读取,新增单测直接 `import task_dispatch`,未新增任何 `import bot` 的测试文件——严格兑现了 design.md"不先偿 D-003"段落写下的承诺,没有把新债务面悄悄扩大。
- **契约常量零内联**:`grep -n '"openclaw"\|"agent"\|"tasks"\|"mcp"' server/task_dispatch.py` 零命中裸字面量,三条 openclaw 命令与全部结构化字段名都经 `task_dispatch_contract.py` 统一导出,单一事实源纪律执行得很干净。
- **异常边界处理规范**:`dispatch_task`/`get_task_status`/`_run_openclaw_subprocess`/`_query_task_view` 全部走"不裸抛、转成带上下文的失败载荷或降级结构"这条路线(`server/task_dispatch.py:96-131`、`:207-224`),没有一处裸 `except:`,也没有吞异常。
- **RTVI 泄漏防线复用得当**:新增的 `_DispatchMaterialInjector` 往 `fast_context` 追加消息帧,理论上是第二条"进入注册表的第二泄漏路径"(design §5.1.1),但既有 `user_llm_enabled=False`(`bot.py:354`)是管线级设置,天然覆盖了新注入器,不需要额外改动即可维持 R2 契约——审查确认这条防线确实生效,不是巧合遗漏。
- **测试厚度与质量**:`tests/test_task_dispatch.py` 670 行,覆盖次序不变量(含真实调度、非 mock 的后台任务未完成断言)、会话隔离、C-16 静态断言(用字符串拼接规避 grep 判据自指悖论,是个巧妙的细节)、C-09/C-10/C-18 的正负向筛选;ruff/pyright 全绿,67 个测试全过。
- **债务记录质量高**:D-013~D-018 每条都附具体复现步骤、原样日志/输出片段、责任节点归属与处置建议,是这批文档里少见的高质量踩坑记录,极大降低了本轮审查的重复调查成本。

## 发现

### Important

1. **`_build_task_view`/`_query_task_view` 的命中(`found: true`)路径零单测覆盖** — `server/task_dispatch.py:189`(`_build_task_view`)、`:208`(`_query_task_view`)
   - **失败场景**:这两个函数实现的是契约 §0.5 的核心语义——从 `tasks show --json` 原始记录里挑出恒在字段、把三个条件字段(`error`/`progressSummary`/`terminalSummary`)在缺失时**整个键省略**而不是补 `None`,并在末尾追加 `lookup`/`found`。`server/tests/test_task_dispatch.py` 里唯一直接测这两个函数的用例是 `TestTasksShowDegrade`(约 :225-249),只覆盖 `exit_code != 0` 的降级分支;`grep -n "_build_task_view" server/tests/test_task_dispatch.py` 零命中。任何未来改动(例如给 `TASK_VIEW_FIELDS` 加字段、调整省略逻辑、或误把 `.get()` 换成 `[]` 直接取值)都不会被 L1 层任何一条测试挡住,只能等到 eval/真机联测才可能暴露,而这条路径又恰好是 FR-2 判据1"条件字段按实际存在情况透传,不因未出现而判定失败"的直接实现。
   - **现有防线为何拦不住**:s5 集成闸门(变异抽样)当轮确实抓到过同一文件内另外两处同类缺口(`_poll_until_visible` 的 `if result.exit_code == 0` 分支、`DispatchRegistryEntry` 的 `frozen=True`)并要求补测——说明变异抽样这条防线**是按采样命中率生效的**,这次没抽中 `_build_task_view` 纯属采样运气,不能依赖它兜底所有分支;T-8 的真机复验(test-report.md C-05)确实实测验证过一次这条路径行为正确,但那是单次人工真机会话,不是可重复回归的自动化用例。
   - **怎么改**:仿照 `TestTasksShowDegrade` 的写法加一条正向用例——构造一份含全部恒在字段、但缺 `error`/`progressSummary`/`terminalSummary` 的 raw record,mock `_run_openclaw_subprocess` 返回 `exit_code=0` 且该 record 的 JSON 落在 `stderr`,断言 `_query_task_view` 返回的 dict 里这三个键确实不存在(而不是值为 `None`),且 `lookup`/`found` 正确追加在末尾、顺序与 `contract.TASK_VIEW_FIELDS` 一致。与 s5 集成闸门当时用的"只补测试、不改产线代码"修复环是同一条路径,成本很低。

### Minor

1. **在途任务上限(ADR-8)的检查窗口存在已被间接证实的竞态,建议把措辞补进已有债务而非新开条目** — `server/task_dispatch.py:416`(`TaskDispatchWorker.reply` 的容量检查)与 `:629`(`OpenClawExecWorker._handle_dispatch` 里 `self._dispatch_registry.add(...)`)
   - `reply()` 的容量判断只读 `len(self._dispatch_registry)`,而该注册表要等 exec worker 完成 CLI spawn + `tasks show` 轮询命中之后(D-7:2.6s~最长30s)才会写入;这个窗口内已经 `create_task` 发出但还未注册的 dispatch,不会被下一次 `reply()` 调用计入。`debts.md` D-018 的真机复现日志(两次背靠背 `dispatch_task` 调用间隔约 2.5 秒,注册表出现预期外的第 3 条记录)已经间接证明这个窗口在生产条件下真实可达——同一机制下,连续几次调用若恰好都落在各自"已发出、未注册"的窗口内,ADR-8"硬上限 3、不做可配置项"的承诺理论上可能被绕过,进而影响 §0.2 T2 依赖的"3 × 2.6s ≈ 7.8s < 15s"这条时序假设(D-7 的关闭依据)。
   - 这不是一个需要本轮新开工单的独立发现,而是 D-015(注册表写入时点滞后)已知机制的一个更精确的推论;D-015/D-018 均已由用户在 s5 明确裁决本轮不修、留后续设计级复核(账本 2026-08-09T09:26:09)。建议:下次触达这两个债务条目时,在描述里补一句"同一时间窗口下,ADR-8 的硬上限本身也可能被绕过,不只是'同一请求被重复派发'",避免未来读者误以为二者是互不相关的两个问题。不建议本轮为此单独返工或阻塞合并。

## 契约档位复核

`design.md`『接口契约』小节的档位理由(本变更未新增本项目自己的 HTTP 端点、CLI 或 UI;消费的 `openclaw` CLI 与 `openclaw mcp serve` bridge 是被消费的外部依赖,不是本项目对外产出的接口;argv/退出码/字段挑选/session key 等契约常量已落在 cases 档 §0 节)在实现落地后复核仍然成立——`task_dispatch.py` 新增的 `TaskDispatchWorker(UIWorker)`/`OpenClawExecWorker(BaseWorker)`/MCP `ClientSession` job 通信全部是**项目内部**的 worker 间协作与对外部依赖的消费,不产生任何本项目自己的对外接口面。**维持 cases 档,不降级不升级**,design.md 无需就此改动。

## 总裁定

`review-verdict.json` 与本文件一致:存在 1 条 Important(`_build_task_view`/`_query_task_view` 命中路径零单测覆盖)→ **pass=false**,建议走与 s5 集成闸门同款的"只补一条测试、不改产线逻辑"修复环,复核通过后无需再评审全量 diff。其余 1 条 Minor(在途上限竞态措辞建议)与已登记债务 D-015/D-018 同根同源,不阻塞本轮合并,建议顺路把描述补一句即可。规格符合表无 ❌;安全红线检查(密钥/注入/日志泄露)全部通过;契约档位维持 `cases` 不变。

---

## s6 复评(re-review)· 2026-08-09

> 范围:仅复核上一轮 1 条 Important 发现是否闭合(派单限定),不重新评审全量 diff;上一轮其余 5 项 pass=true 与 1 条 Minor 维持不变。独立验证,不采信提交说明自述。

**修复交回**:commit `b7ea61b`「test: cover _build_task_view/_query_task_view found=true 命中路径 (task-dispatch s6 fix)」。

**验证过程与结论**:

1. **diff 范围核实**——`git show b7ea61b --stat` 确认改动仅 `server/tests/test_task_dispatch.py`(+83/-0);`git diff --stat server/task_dispatch.py server/task_dispatch_contract.py` 与 `git status --short` 均为空,production 代码确认零改动,与提交说明相符。
2. **语义覆盖核实(读码,非采信自述)**——对照 `server/task_dispatch.py:189-205`(`_build_task_view` 实现:`if field_name in record: view[field_name] = record[field_name]`,三个条件字段缺失时整体不写入 key)与新增测试:
   - `TestBuildTaskView::test_conditional_fields_absent_when_missing_from_record` 直接调用 `_build_task_view`,record 只含恒在字段,断言 `error`/`progressSummary`/`terminalSummary` 三个 key **不在**结果 dict 中(`assertNotIn`,不是判等 `None`)——精确命中上一轮"整个键省略而不是补 None"这条语义。
   - `TestBuildTaskView::test_all_fields_pass_through_when_present_in_record` 反向用例,全字段存在时逐一透传核对。
   - `TestQueryTaskViewHit::test_query_task_view_hit_matches_build_task_view` mock `_run_openclaw_subprocess` 返回 `exit_code=0`、record JSON 落在 `stderr`(符合 D-1 "命中结果在 stderr" 约定),断言 `_query_task_view` 返回值与直接调用 `_build_task_view(record, lookup)` 完全一致——证明命中路径确实会调用到 `_build_task_view`,不是只测了纯函数本身、绕开了调用链。
   三条用例合起来覆盖了上一轮"怎么改"建议的全部要点(正向缺失用例 + mock exit_code=0/JSON 在 stderr + 断言键整体缺失)。
3. **实跑验证**——`cd server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run pytest tests/test_task_dispatch.py -q` → `17 passed`(含 3 条新用例,针对性子集 `-k "TestBuildTaskView or TestQueryTaskViewHit"` 单独跑同样 3 passed)。
4. **变异测试(验证测试不是空转)**——临时把 `_build_task_view` 里 `if field_name in record: view[field_name] = record[field_name]` 改回上一轮描述的缺陷写法 `view[field_name] = record.get(field_name)`(条件字段无条件补 `None`),重跑同一子集:`test_conditional_fields_absent_when_missing_from_record` 按预期失败(`AssertionError: 'error' unexpectedly found in {...}`),另外两条仍通过(符合预期,它们不测缺失场景)。确认新测试对目标语义是真实的回归防线。改动已还原,`git diff --stat server/task_dispatch.py` 确认工作树干净、无残留。

**结论**:上一轮 Important 发现(`_build_task_view`/`_query_task_view` 命中路径零单测覆盖)已闭合,证据充分。`review-verdict.json` 翻转为 `pass: true`。上一轮 1 条 Minor(在途上限竞态措辞建议,D-015/D-018 同根同源,不阻塞合并)按派单要求维持不变,未重新复核。
