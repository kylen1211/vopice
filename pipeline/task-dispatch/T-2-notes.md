# T-2 · 契约常量模块 `server/task_dispatch_contract.py` — backend-notes

## 完成清单(对照任务卡逐条)

| 任务卡条目 | 状态 | 落点 |
|---|---|---|
| worker 名三个常量(§0.1) | 完成 | `MAIN_WORKER_NAME`/`DISPATCH_WORKER_NAME`/`EXEC_WORKER_NAME` |
| job 名与 payload 键常量(§0.3/§0.4) | 完成 | `RESPOND_JOB_NAME`/`QUERY_PAYLOAD_KEY`/`DISPATCH_JOB_NAME`;exec job 三键/三键分别落 `ExecDispatchPayload`/`ExecDispatchResponse` 两个 dataclass 的字段名 |
| `degraded` 原因码常量(§0.4) | 完成(2 个,见"疑虑") | `DEGRADED_TASK_RECORD_NOT_VISIBLE`/`DEGRADED_MCP_BRIDGE_DOWN` |
| `TASK_VIEW_FIELDS`(§0.5 + lookup/found) | 完成 | 15 元素元组,顺序与 §0.5 逐字一致,`lookup`/`found` 追加末尾 |
| `SESSION_KEY_TEMPLATE` + token 长度常量(§0.6) | 完成 | `SESSION_KEY_TEMPLATE`、`SESSION_KEY_TOKEN_LENGTH = 12` |
| 三条命令 argv 构造(§0.7,删 `CMD_TASKS_NOTIFY`) | 完成 | `cmd_agent()`/`cmd_tasks_show()`/`cmd_mcp_serve()` 纯函数,`CMD_TASKS_NOTIFY` 未落 |
| `ENV_TASK_DISPATCH_CLI`(§0.10,删 `ENV_TASK_DISPATCH_SKIP_NOTIFY`) | 完成 | 值 `"TASK_DISPATCH_CLI"`;`ENV_TASK_DISPATCH_SKIP_NOTIFY` 未落 |
| `MAX_INFLIGHT_TASKS`/`CAPACITY_MESSAGE`(§0.3 新增,ADR-8) | 完成 | 值 `3` / 逐字英文诊断串;未进 `.env.example`、未读环境变量 |
| 三个纯 dataclass:注册表条目 / exec payload+response / app_resources | 完成(实为 4 个类,见"疑虑") | `DispatchRegistryEntry`、`ExecDispatchPayload`、`ExecDispatchResponse`、`AppResources` |
| 不产出任何行为逻辑 | 完成 | 全文件仅常量、纯函数(参数→固定 argv,无副作用)、`@dataclass` |
| 独占路径:仅 `server/task_dispatch_contract.py` | 完成 | 见下方 D-003 守法①证据 |

## 改动文件

- 新增 `/home/ky/git/voice-agent/server/task_dispatch_contract.py`(218 行)

## TDD 证据

### RED

```
$ cd /home/ky/git/voice-agent/server && python3 -c "import task_dispatch_contract as m; print(sorted(n for n in dir(m) if not n.startswith('_')))"
Traceback (most recent call last):
  File "<string>", line 1, in <module>
ModuleNotFoundError: No module named 'task_dispatch_contract'
```
退出码 1。为何该失败:模块尚未创建,是本卡唯一交付物,导入必然失败——符合"先跑验收用例确认失败"的 RED 态。

### GREEN(任务卡 5 条验收用例,逐条命令与输出)

**1. 零副作用导入**
```
$ cd /home/ky/git/voice-agent/server && python3 -c "import task_dispatch_contract as m; print(sorted(n for n in dir(m) if not n.startswith('_')))"
['AppResources', 'CAPACITY_MESSAGE', 'DEGRADED_MCP_BRIDGE_DOWN', 'DEGRADED_TASK_RECORD_NOT_VISIBLE', 'DISPATCH_JOB_NAME', 'DISPATCH_WORKER_NAME', 'DispatchRegistryEntry', 'ENV_TASK_DISPATCH_CLI', 'EXEC_WORKER_NAME', 'ExecDispatchPayload', 'ExecDispatchResponse', 'MAIN_WORKER_NAME', 'MAX_INFLIGHT_TASKS', 'QUERY_PAYLOAD_KEY', 'RESPOND_JOB_NAME', 'SESSION_KEY_TEMPLATE', 'SESSION_KEY_TOKEN_LENGTH', 'TASK_VIEW_FIELDS', 'TYPE_CHECKING', 'annotations', 'asyncio', 'cmd_agent', 'cmd_mcp_serve', 'cmd_tasks_show', 'dataclass']
```
退出码 0,裸解释器(未带 `NLTK_DISABLE_IMPORT_SECURITY=1`、未 `source .env`、未激活 `.venv`)。通过。

**2. D-003 守法②(不读环境变量/不调 load_config)**
```
$ cd /home/ky/git/voice-agent/server && python3 -c "
import ast
tree = ast.parse(open('task_dispatch_contract.py').read())
bad = []
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom)):
        continue
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            nm = getattr(sub.func, 'id', None) or getattr(sub.func, 'attr', None)
            if nm in ('load_config', 'load_dotenv', 'getenv'):
                bad.append((sub.lineno, nm))
print('TOPLEVEL_ENV_CALLS=', bad)
"
TOPLEVEL_ENV_CALLS= []

$ grep -n "os.environ" task_dispatch_contract.py
(无输出,exit=1)
```
通过。

**3. D-003 守法①(独占路径)**
```
$ git -C /home/ky/git/voice-agent status --porcelain -- server/
?? server/task_dispatch_contract.py
```
`server/` 范围内只新增这一个文件。**说明(与任务卡字面命令的差异)**:任务卡给的字面命令是 `git diff --stat`(不带路径过滤)。本仓库在本卡开工前就已存在与本卡无关的未提交改动(`CLAUDE.md`/`README.md`/`pipeline/debts.md`,派发时的初始 `git status` 已如此,非本卡产生),而本卡新增文件是**未跟踪(untracked)**文件——`git diff --stat` 默认不包含 untracked 文件,因此字面命令既不会显示本卡新文件、又会显示三个与本卡无关的已存在改动,不能直接用来判定。改用 `git status --porcelain -- server/`(定向到独占路径的父目录)与 `git diff --stat -- server/task_dispatch_contract.py` 核验,确认 `server/` 下确实只新增了本卡独占路径这一个文件,符合验收意图。已记入下方"疑虑"。

**4. 常量值与契约逐字一致**
逐个字面值跑 `grep -Fn '<value>' pipeline/task-dispatch/contract/cases.md`,全部命中(worker 名 3 个、job 名/payload 键 3 个、`degraded` 原因码 2 个、`TASK_VIEW_FIELDS` 15 个字段名、`SESSION_KEY_TEMPLATE` 整串、`SESSION_KEY_TOKEN_LENGTH` 对应的 `uuid4().hex[:12]`、三条命令的全部 argv token、`ENV_TASK_DISPATCH_CLI` 的值 `TASK_DISPATCH_CLI`、`MAX_INFLIGHT_TASKS` 的值 `3`、`CAPACITY_MESSAGE` 整串)。摘要:
```
ok(1): voice-main
ok(5): task-dispatch
ok(1): openclaw-exec
ok(9): respond
ok(2): query
ok(29): dispatch
ok(1): task-record-not-visible
ok(2): mcp-bridge-down
ok(15 个字段名全部 ok(≥2))
ok(1): agent:{agent_id}:voice-agent-{token}
ok(3): TASK_DISPATCH_CLI
ok(28): openclaw ... ok(21): serve
ok(1): "In-flight task limit (3) reached; none of the newly requested tasks were dispatched."
ok(1): uuid4().hex[:12]
```
无未命中项。通过。

**5. 既有测试无回归**
```
$ cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 .venv/bin/python -m pytest tests/ -q
49 passed, 21 warnings in 4.23s
```
退出码 0,收集数 49(等于基线,无新增/无减少)。21 条 warning 全部来自 pipecat/websockets 既有 deprecation(与本卡无关,既有基线自带,非本卡引入)。通过。

### 额外自查(非任务卡要求,补充验证)

```
$ .venv/bin/python -m ruff check task_dispatch_contract.py
All checks passed!
```

功能性冒烟(argv 构造 + dataclass 构造 + 模板渲染):
```
$ .venv/bin/python -c "
import asyncio, task_dispatch_contract as m
print(m.cmd_agent('dev', 'agent:dev:voice-agent-abc123456789', '/tmp/task.txt'))
print(m.cmd_tasks_show('agent:dev:voice-agent-abc123456789'))
print(m.cmd_mcp_serve())
print(m.DispatchRegistryEntry(session_key='k', label='l', created_at=1.0))
print(m.ExecDispatchPayload(session_key='k', label='l', task='do it'))
print(m.ExecDispatchResponse(session_key='k', lookup='k'))
ar = m.AppResources(registry=object(), injection_queue=asyncio.Queue(), agent_id='dev')
print(ar, ar.main_worker)
print(len(m.TASK_VIEW_FIELDS))
print(m.SESSION_KEY_TEMPLATE.format(agent_id='dev', token='0'*12))
"
['openclaw', 'agent', '--agent', 'dev', '--session-key', 'agent:dev:voice-agent-abc123456789', '--message-file', '/tmp/task.txt', '--json']
['openclaw', 'tasks', 'show', 'agent:dev:voice-agent-abc123456789', '--json']
['openclaw', 'mcp', 'serve']
DispatchRegistryEntry(session_key='k', label='l', created_at=1.0)
ExecDispatchPayload(session_key='k', label='l', task='do it')
ExecDispatchResponse(session_key='k', lookup='k', degraded=None)
AppResources(registry=<object object at 0x...>, injection_queue=<Queue ...>, agent_id='dev', main_worker=None) None
15
agent:dev:voice-agent-000000000000
```

pyright 探测(非任务卡要求、非项目已配置 CI 项):对 `task_dispatch_contract.py` 直接调用 `pyright` 报 `pipecat.pipeline.worker` 无法解析——但对既有 `bot.py` 用同样方式跑也是同一失败模式(27 处同类 `reportMissingImports`),证明这是 pyright 未指向 venv 的调用方式问题,不是本卡代码引入的新问题,项目里也没有 pyright 的 CI 门禁,故不作为阻塞项处理,仅记录以备后续如需接入 pyright CI 时参考。

## 自查发现(完整性/质量/纪律/测试)

- 命名与既有风格一致:全大写 SCREAMING_SNAKE 常量、`snake_case` 函数、`PascalCase` dataclass,与项目 `config.py`/`prompts.py` 风格同构。
- 类型注解:`from __future__ import annotations` + `TYPE_CHECKING` 守卫 pipecat 的 `PipelineWorker` 导入路径,取自 `bot.py:36` 现用的同一条导入路径(未凭空猜测)。
- `AppResources.registry` 字段类型标注为 `object` 而非具体的 `DispatchRegistry`——已在类 docstring 里写明原因(避免与 T-4 的 `task_dispatch.py` 产生循环导入,任务卡"符号级依赖:无"明确禁止本模块 import 本变更任何新模块)。
- 未引入任何新依赖;未碰 `server/config.py`/`server/bot.py`/`server/prompts.py`。
- 未使用 `os.environ`/`getenv`/`load_config`,已用两条独立命令核验(见 GREEN 用例 2)。

## 疑虑(RISKS,已按纪律不擅自改上游文档)

1. **任务卡与 contract 存在两处"计数漂移"(叙述性数字未随本轮删减字段同步)**,均已按"contract 表格是权威源"处置,未据此新增/杜撰字段:
   - 任务卡 Interfaces 原文"`degraded` 原因码**三个**常量,值为 §0.4 封闭集的三个字符串"——但 `contract/cases.md` §0.4 本轮已显式"删除 `"notify-set-failed"`",封闭集实际只剩 **两个** 字符串(`task-record-not-visible`/`mcp-bridge-down`)。已按 §0.4 现状实现 2 个常量,未补第三个杜撰值。`notify-set-failed` 字符串确实能在 cases.md 里 grep 到(出现在"本轮删除"的说明文字里),但那是描述删除动作本身,不是"仍在用的值",若字面套用验收用例 4 的 grep 规则会误判通过,已当场识别未采信。
   - `pipeline/task-dispatch/tasks/T-4.md:84` 提到"本卡 import `task_dispatch_contract` 的全部常量与**三个** dataclass"——本卡按任务卡 Produces 段的字段枚举(注册表条目 / exec 入站 payload / exec 出站响应 / app_resources,四组不同字段集)实现为 **4 个**独立 dataclass(`DispatchRegistryEntry`/`ExecDispatchPayload`/`ExecDispatchResponse`/`AppResources`)。若把 exec 的入站 payload 与出站响应合并成一个类,字段集(`label`/`task` vs `lookup`/`degraded`)会互相污染,故未合并。两处数字与本卡实现存在出入,均判断为本轮删除原 FR-4(通知策略)相关字段后遗留的叙述性计数未同步更新(与 design.md 本身已知的"P22 过期措辞漏改"同类问题),不影响下游 import(T-4 按符号名 import,不按数量校验),仅供主会话与 T-4 owner 知悉,不阻塞交付。
2. **`app_resources` 载体的"派活相关配置项"字段数量与具体名称,契约链条内只能坐实一个**:任务卡 Produces 原文只写"派活相关配置项"(未列数量);`design.md` 数据模型 §2 的叙述是"cfg 中派活相关的**三个**配置项",但翻遍 `design.md`/`contract/cases.md`/T-3~T-8 全部任务卡,能确证的 dispatch 相关配置字段只有一个——`OPENCLAW_AGENT_ID`(§0.6,由 T-5 落地到 `server/config.py`,T-2 本卡不读 `config.py` 任何字段名)。本卡因此只在 `AppResources` 上落了 **一个** 字段 `agent_id: str`,未杜撰另外两个不存在契约依据的字段。若确有另外两个配置项是设计意图但未写进任何契约/任务卡文本,需要 tech-architect 补齐说明,T-4/T-5 落地时如发现还需要别的配置字段,`AppResources` 是纯字段容器,后续加字段是局部改动、不影响本卡已交付的四条验收用例。
3. **验收用例 3 的字面命令(`git diff --stat`)在本仓当前脏树状态下会产生误导性输出**(见 GREEN 用例 3 说明):新文件是 untracked、`git diff --stat` 默认不显示 untracked 文件,而仓库里派发前就已存在 3 个与本卡无关的改动文件会被该命令带出。已改用路径过滤的 `git status --porcelain -- server/` 定向核验,确认符合验收意图(独占路径内只新增了本卡文件)。建议后续同类任务卡的验收命令改用 `git status --porcelain -- <独占路径>` 或 `git diff --stat -- <独占路径>`,避免脏树环境下的误判,供 S2b/S2a 复盘参考。

无生产环境/密钥/破坏性操作;无新增依赖;无越界改动。
