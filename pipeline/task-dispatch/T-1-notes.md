# T-1 交付说明

- 任务卡:`pipeline/task-dispatch/tasks/T-1.md`
- 契约:`pipeline/task-dispatch/contract/cases.md`(§0.6/§0.7/§0.8、C-00、C-15)
- 设计:`pipeline/task-dispatch/design.md`(preflight P-04/P-05/P-06、风险 R-2/R-4、难逆点 D-3)
- 执行:backend-dev,2026-08-08

## 任务性质说明

T-1 是"实现开工前的门",产出证据文件而非代码,故本卡不适用常规"改代码使测试变绿"的 TDD 流程。下面的 RED/GREEN 证据按任务卡的实际形态改写为:**RED = 本卡独占产出文件在开工前不存在/门未验证**,**GREEN = 三道门全部现场核验通过、证据文件已落盘**。

## 完成清单(逐条对照任务卡)

| 任务卡条目 | 状态 | 证据 |
|---|---|---|
| C-00 环境前置门(三项)先跑,不满足则停 | 完成,三项全满足 | 见 `baseline/openclaw-agent-task-record-probe.md` C-00 节;本次现场实跑 |
| 门 A:MCP 事件样本存在、`json.tool` 退出码 0、指认两项判据 | 完成,通过 | 同上"门 A"节 |
| 门 A:不产出第三项"原生终态字符串"判据 | 完成(遵守,未新增该判据) | 同上,已显式核对样本顶层字段无该项 |
| 门 B:`openclaw agent`→`tasks show`→`tasks list --runtime cli` 三条命令 & 判据 | 完成,通过 | 同上"门 B"节 |
| 门 B:两种用法(前台等待 / `start_new_session` 起后台再查)需写明实际采用哪种 | 完成 | 已写明:历史派发采用 `setsid nohup` 起后台不等待,本次现场复用其已完成的记录 |
| 门 C:C-15 缓解路径(`childSessionKey`/`ownerKey` 至少一个非空且与 K 可关联) | 完成,通过 | 同上"门 C"节,两者均与 K 精确相等 |
| 停下条件:任一门不通过则停,不带假设往下写解析/派发代码 | 未触发(全部通过) | 未产出任何生产代码 |
| 产出 `baseline/mcp-event-sample.json`(原样,不裁剪不改名不补字段) | 已存在且核验通过,未修改 | 见下方"关于 mcp-event-sample.json 的说明" |
| 产出 `baseline/openclaw-agent-task-record-probe.md` | 已产出 | 本次新增,249 行 |
| 不产出任何 Python 生产代码;探针脚本用完即弃、落 `/tmp` | 遵守 | 探针脚本写在 scratchpad(`/tmp/...`),验证完毕已删除,未进仓库/`server/` |

## 关于 `mcp-event-sample.json` 的说明(重要,请主会话过目)

该文件在本卡开工前**已经存在**(`ls -la` 显示创建于 2026-08-08 17:39,115KB 的姊妹文件 `failure-path-samples.json` 创建于 18:53)。经核对账本(`ledger.md` 2026-08-08T17:30:32 与 18:56:23)与 agent-mem 记忆(`mem_msk9u9x8_...`),这是**同一 backend-dev 角色**在 S2a 定义段内、**用户已显式授权**("可以跑 不用担心费用")下真实派发 4 次任务、真实建立 MCP 连接取得的样本,且记忆库里明确写着"已产实测资产,新会话不要重验"。

本卡执行时做的选择:
1. **门 A 不重新发起新的付费 `openclaw agent` 派发**去重造样本——理由见 `openclaw-agent-task-record-probe.md` 开头"证据来源说明"一节:样本已满足全部可证伪期望;样本用的 session key 与本次门 B/C 现场复验使用的 `K` 是**同一个**,该任务记录此刻仍可查,证明样本描述的关联关系没有过期。
2. 为弥补"未现场重新付费派发"这一点,额外做了一次**零花费**的 MCP bridge 握手复验(`initialize` + `tools/list`,不调 `events_wait`),证明当前时刻 bridge 仍可达、`events_wait` 仍在工具清单内。
3. **C-00、门 B、门 C 的全部判据命令均为本次现场全新实跑**(只读查询,零新增花费),不是引用历史输出。

按通用纪律 9("生产环境/花钱/... 一律停下写 RISKS 等批准"),若主会话认为门 A 必须在本次执行内重新真实付费派发一次 `openclaw agent` 来产出全新样本,请明确批准,本卡可补跑(已写入 RISKS)。

## 改动文件

- 新增:`pipeline/task-dispatch/baseline/openclaw-agent-task-record-probe.md`(本卡核心产出)
- 未修改:`pipeline/task-dispatch/baseline/mcp-event-sample.json`(已存在,只读核验,未改动一字节)
- 无任何 `server/` 下代码改动

## 证据(RED → GREEN)

**RED(开工前)**:
```
$ ls pipeline/task-dispatch/baseline/
failure-path-samples.json  mcp-event-sample.json  preflight-live.md
```
`openclaw-agent-task-record-probe.md` 不存在,门 A/B/C 本次执行尚未现场核验过。

**GREEN(收工时)**:
1. C-00 三项(daemon status / ss / approvals get)现场实跑,原样输出见 `openclaw-agent-task-record-probe.md`,三项全满足。
2. 门 A:`python3 -m json.tool < mcp-event-sample.json` exit=0;从样本 `captures[2]` 现场提取出 `event.sessionKey == "agent:dev:voice-agent-94935dc26e46"` 与 `event.raw.message.stopReason == "stop"` 两项判据,逐字写入证据文件;另做零花费 MCP 握手复验,`events_wait_present: True`,exit=0。
3. 门 B:`openclaw tasks show "$K" --json 2>&1` exit=0、`runtime=="cli"`;`openclaw tasks list --runtime cli --json` → `count=12 ≥ 1` 且列表含 `K` 对应记录(现场用 python3 核对 `found K record: 1`)。
4. 门 C:`openclaw tasks show "$K" --json 2>&1 | python3 -c "...childSessionKey/ownerKey..."` → 两者均等于 `K`,exit=0。
5. `pipeline/task-dispatch/baseline/openclaw-agent-task-record-probe.md` 落盘,249 行,含四道门的命令/原样输出/退出码/结论。

## 自查

- 完整性:任务卡"验收用例"1-5 条逐条核对完成;"独占路径"两个文件均已就位(一个新增、一个既有核验通过)。
- 质量:证据文件按"命令+原样输出+退出码+结论"结构组织,两项判据字段路径精确写出(`structuredContent.event.sessionKey`、`structuredContent.event.raw.message.stopReason`),未臆造第三项判据。
- 纪律:未越界改动任何 `server/` 代码、未改任何冻结文档(prd/design/contract)、未修改已存在的 `mcp-event-sample.json`;探针脚本用完即删,未入仓库。
- 测试:本卡无"测试"概念,以现场实跑命令的真实退出码/原样输出为证据,非转述、非"应该没问题"。

## 疑虑(写入 RISKS)

1. 门 A 复用了同日早些时候(S2a 定义段)已经过用户授权产出的真实样本,而非本次执行内重新发起一次新的付费 `openclaw agent` 派发去生成全新样本——理由与替代验证已在证据文件"证据来源说明"一节写明。若主会话/用户要求门 A 必须是本次执行内的全新付费派发,请明确批准后可补跑(预计一次短任务的 token 成本)。
2. 账本 2026-08-08T17:48:44 记录了一条环境侧遗留:`openclaw` 包本体仍在 `~/.nvm/versions/node/v24.18.0/` 下,`nvm uninstall v24.18.0` 会同时废掉 Gateway 与 CLI 入口;根治需 `sudo npm install -g openclaw@2026.7.1-2` 到系统 Node(未擅自执行,属新增/重装依赖类操作)。此为环境侧遗留,非本卡产出物问题,提请主会话知悉,与 T-1 本身通过与否无关。
