# env-runbook · OpenClaw 本机环境启用(C-00 环境前置门)

> change_id: task-dispatch | 产出: devops-engineer | 日期: 2026-08-08
> 目的:把本机 OpenClaw Gateway 从"disabled/未运行"状态调整为满足 `contract/cases.md` C-00 三项判据的状态,供后续用例(C-01~C-17)使用。
> 授权依据:用户原话「没问题 本期不考虑安全问题, 全部按照建议来」+「这个跑起来部署可以交给运维来」(2026-08-08),已明确授权本次操作,无需再回来确认。
> 执行前实测基线见 `pipeline/task-dispatch/design.md` P-05 段(Gateway disabled、18789 无监听、`openclaw health` 报 1006)。

---

## 环境要求

- OpenClaw CLI 已装(`which openclaw` → `/home/ky/.nvm/versions/node/v24.18.0/bin/openclaw`,版本 `2026.7.1-2 (0790d9f)`)。
- systemd --user 可用(`systemctl --user`)。
- 配置文件:`~/.openclaw/openclaw.json`(cli 与 service 共用同一份)。
- 审批文件:`~/.openclaw/exec-approvals.json`(执行主机侧,独立于 config)。
- 端口:18789(loopback,`127.0.0.1` + `[::1]`)。
- **不依赖**:本次不涉及 Node/nvm 版本、系统级 Node 安装(硬边界,见下"遇到的坑"第 1 条)。

---

## 操作步骤(命令原样)

### 步骤 0:改动前备份(先备份再动手)

```bash
DATE=20260808
cp -p ~/.config/systemd/user/openclaw-gateway.service ~/.config/systemd/user/openclaw-gateway.service.bak.$DATE
cp -p ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak.$DATE
cp -p ~/.openclaw/exec-approvals.json ~/.openclaw/exec-approvals.json.bak.$DATE
sha256sum ~/.config/systemd/user/openclaw-gateway.service.bak.$DATE ~/.openclaw/openclaw.json.bak.$DATE ~/.openclaw/exec-approvals.json.bak.$DATE
```

> 注:`openclaw.json.bak.$DATE` 后来被 `openclaw config set`(见步骤 2)自身的备份轮转机制"借用/覆盖"为 `openclaw.json.bak`(无日期后缀),内容经 sha256 核对未丢失,但**文件名不是我们起的那个**——细节见"遇到的坑"第 3 条。已额外另存一份到 `~/.openclaw/openclaw.json.before-gateway-enable-20260808.bak`(与仓库既有 `.before-*.bak` 命名惯例一致,该模式实测不会被工具轮转覆盖)。

### 步骤 1:目标 1/2 —— 启用并启动 Gateway systemd 服务

先修一个允许修的坑:service 文件 PATH 缺 `/home/ky/.local/share/pnpm`(`openclaw daemon status` 报的 4 条 issue 之一,唯一允许修的一条,见硬边界)。

```bash
# 编辑 ~/.config/systemd/user/openclaw-gateway.service 的 Environment=PATH 一行,
# 末尾追加 :/home/ky/.local/share/pnpm(其余不动,尤其不碰 nvm node 路径)
```

改动 diff(实际生效的唯一文件改动):

```diff
--- ~/.config/systemd/user/openclaw-gateway.service.bak.20260808
+++ ~/.config/systemd/user/openclaw-gateway.service
@@ -18,7 +18,7 @@
 Environment=HOME=/home/ky
 Environment=TMPDIR=/tmp
 Environment=NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt
-Environment=PATH=/home/ky/.nvm/versions/node/v24.18.0/bin:/usr/local/bin:/usr/bin:/bin:/home/ky/.bun/bin:/home/ky/.nvm/current/bin:/home/ky/.local/bin:/home/ky/.npm-global/bin:/home/ky/bin:/home/ky/.nix-profile/bin
+Environment=PATH=/home/ky/.nvm/versions/node/v24.18.0/bin:/usr/local/bin:/usr/bin:/bin:/home/ky/.bun/bin:/home/ky/.nvm/current/bin:/home/ky/.local/bin:/home/ky/.npm-global/bin:/home/ky/bin:/home/ky/.nix-profile/bin:/home/ky/.local/share/pnpm
 Environment=OPENCLAW_GATEWAY_PORT=18789
 Environment=OPENCLAW_SYSTEMD_UNIT=openclaw-gateway.service
```

然后加载并启动服务:

```bash
systemctl --user daemon-reload
systemctl --user enable openclaw-gateway.service
systemctl --user start openclaw-gateway.service
```

**实际输出**:

```
$ systemctl --user daemon-reload
(无输出, exit=0)
$ systemctl --user enable openclaw-gateway.service
Created symlink /home/ky/.config/systemd/user/default.target.wants/openclaw-gateway.service → /home/ky/.config/systemd/user/openclaw-gateway.service.
$ systemctl --user start openclaw-gateway.service
(无输出, exit=0)
```

### 步骤 2:目标 3 —— 把 `tools.exec.mode` 配成 `full`(消除运行时审批)

```bash
openclaw config set tools.exec.mode full --dry-run   # 先 dry-run
openclaw config set tools.exec.mode '"full"' --strict-json   # 实际写入
```

**实际输出**:

```
$ openclaw config set tools.exec.mode full --dry-run
Dry run note: value mode does not run schema/resolvability checks. Use --strict-json, builder flags, or batch mode to enable validation checks.
Dry run successful: 1 update(s) validated against ~/.openclaw/openclaw.json.

$ openclaw config set tools.exec.mode '"full"' --strict-json
Updated tools.exec.mode. No gateway restart needed.
```

改动后 `~/.openclaw/openclaw.json` 的 `tools` 段:

```json
{
  "exec": {
    "mode": "full"
  }
}
```

`~/.openclaw/exec-approvals.json`(执行主机侧审批文件)**本次未改动**——见"遇到的坑"第 2 条,实测证明当前 `defaults: {}` 为空即会原样继承 config 侧请求策略,不构成"取严合并"降级。

---

## 验证证据(三项目标逐条实跑)

### 目标 1:`openclaw daemon status` 显示服务已启用且在运行

```
$ openclaw daemon status
Service: systemd user (enabled)
...
Runtime: running (pid 318059, state active, sub running, last exit 0, reason 0)
Connectivity probe: ok
Capability: connected-no-operator-scope
Listening: 127.0.0.1:18789, [::1]:18789

$ systemctl --user is-enabled openclaw-gateway.service
enabled
$ systemctl --user is-active openclaw-gateway.service
active
```

`openclaw health` 已从改动前的 `[openclaw] Reason: gateway closed (1006 abnormal closure)` 变为返回真实数据(Telegram/Agents/Session store 等),侧面印证 Gateway 真的在跑,不只是进程存在。

**结论:达成。**

### 目标 2:`ss -ltnp | grep 18789` 有监听进程

```
$ ss -ltnp | grep 18789
LISTEN 0      511        127.0.0.1:18789      0.0.0.0:*    users:(("MainThread",pid=318059,fd=33))
LISTEN 0      511            [::1]:18789         [::]:*    users:(("MainThread",pid=318059,fd=34))
```

**结论:达成。**

### 目标 3:`openclaw approvals get --json` 的 effectivePolicy 中不再有会触发运行时审批的档位

```
$ openclaw approvals get --json | python3 -m json.tool | grep -A2 '"ask"'
                "ask": {
                    "requested": "off",
                    "requestedSource": "tools.exec.mode",
--
                "ask": {
                    "requested": "off",
                    "requestedSource": "tools.exec.mode",
```

完整 `effectivePolicy` 两个 scope(`tools.exec` 与 `agent:dev`)均为:

```
mode: requested=full, effective=full, note="requested mode applies"
security: requested=full, host=full (hostSource="inherits requested tool policy"), effective=full
ask: requested=off, host=off, effective=off
askFallback: effective=deny(默认值,mode=full 时不会被触发到)
```

**结论:达成。** `mode` 的 effective 值为 `full`,不是 `ask`;`security`/`ask` 的 effective 也分别是 `full`/`off`,host 侧(`exec-approvals.json`)因 `defaults: {}` 为空而完全继承 config 侧请求,未被"取严合并"拉回更严的档位——已用 `effectivePolicy` 字段实测验证,不是从配置文件内容推断。

---

## 回滚步骤(与操作步骤逐一对应)

### 回滚目标 3(config 侧 exec 策略)

优先用工具本身回退(比直接覆盖文件更安全,会走 schema 校验):

```bash
openclaw config set tools.exec.mode '"ask"' --strict-json
```

或者直接用改动前快照覆盖(两份等价快照任选其一,内容 sha256 一致 `ce04100e85b28a877210c218444b18a2e32146fc7c08fad8b4576e438b5d50bd`):

```bash
cp -p ~/.openclaw/openclaw.json.before-gateway-enable-20260808.bak ~/.openclaw/openclaw.json
# 或
cp -p ~/.openclaw/openclaw.json.bak ~/.openclaw/openclaw.json
```

验证:`openclaw approvals get --json` 里 `tools.exec` scope 的 `mode.effective` 应回到 `ask`。

### 回滚目标 1/2(systemd 服务)

```bash
systemctl --user stop openclaw-gateway.service
systemctl --user disable openclaw-gateway.service
cp -p ~/.config/systemd/user/openclaw-gateway.service.bak.20260808 ~/.config/systemd/user/openclaw-gateway.service
systemctl --user daemon-reload
```

验证:`openclaw daemon status` 应回到 `Service: systemd user (disabled)` / `Runtime: stopped`;`ss -ltnp | grep 18789` 应无输出。

### exec-approvals.json

本次未改动该文件,无需回滚;`~/.openclaw/exec-approvals.json.bak.20260808` 仍留作以后对照(sha256 与当前文件一致)。

---

## 改动文件与备份清单

| 文件 | 改动内容 | 备份路径 | 备份 sha256 |
|---|---|---|---|
| `~/.config/systemd/user/openclaw-gateway.service` | `Environment=PATH` 追加 `:/home/ky/.local/share/pnpm` | `~/.config/systemd/user/openclaw-gateway.service.bak.20260808` | `c5a715163e28485dce1f9530cf3d50d3b23b87ff62f8538c18799ab503d6630f` |
| `~/.openclaw/openclaw.json` | `tools.exec.mode`: `"ask"` → `"full"` | `~/.openclaw/openclaw.json.before-gateway-enable-20260808.bak`(推荐,不受工具轮转影响)/ `~/.openclaw/openclaw.json.bak`(工具自身轮转产生,内容相同) | `ce04100e85b28a877210c218444b18a2e32146fc7c08fad8b4576e438b5d50bd` |
| `~/.openclaw/exec-approvals.json` | 未改动 | `~/.openclaw/exec-approvals.json.bak.20260808` | `4e7a9bcfcf0c286ca67b432f985ff733c9dc369c64bb1ce3768c7f7baa166903`(与当前文件一致) |

另:systemd 服务的 enable 状态本身也是一处"状态改动"(`disabled`→`enabled`,即 `~/.config/systemd/user/default.target.wants/openclaw-gateway.service` 软链接被创建),回滚步骤里的 `systemctl --user disable` 会清掉该软链接。

---

## 遇到的坑

1. **硬边界触发但未跨越**:`openclaw daemon status` 报的 4 条 service config issue 里,3 条与 Node/nvm 相关(PATH 含版本管理器路径、Node 来自 nvm、未找到系统级 Node 22 LTS/24.15+),按派单硬边界**明确不碰**,只修了第 4 条(PATH 缺 pnpm 目录)。改完后 `openclaw daemon status` 仍会打印这 3 条警告并建议 `openclaw doctor --repair`——**未执行** `doctor --repair`,因为不确认它是否会触发 Node 版本管理器迁移(未做 dry-run 探测其行为,风险边界不明确,遵照"停下来交回问"原则不主动跑)。这 3 条警告不影响 C-00 三项判据(服务照常 enabled+running,端口照常监听),留作已知遗留项。

2. **"取严合并"实测结论**:契约要求配置侧 `tools.exec` 与主机侧 `exec-approvals.json` 交集验证。源码核对(`exec-approvals-effective-D3V7g6Mm.js` `resolveExecPolicyScopeSnapshot`)确认:`effectiveSecurity = minSecurity(请求值, host值)`,`effectiveAsk = maxAsk(请求值, host值)`——两者取更严的一侧生效。当前 `exec-approvals.json` 的 `defaults: {}` 为空、`agents.dev` 只有 `allowlist` 没有 `security/ask/askFallback` 字段,resolver 会用"config 侧请求值"本身作为 host 侧解析结果的兜底(`fallbackSecurity = params.overrides?.security ?? DEFAULT_SECURITY`),因此本机当前状态下"只改 config 侧" 已经等价于"两侧都改到位"。已用 `openclaw approvals get --json` 的 `effectivePolicy` 实测确认(见"验证证据"),不是凭配置文件推断。**如果将来有人往 `exec-approvals.json` 的 `defaults` 或 `agents.dev` 写入更严格的 `security`/`ask`/`askFallback`,会重新变严——这是本机状态相关的结论,不是永久保证**,建议后续每次改动后都用 `effectivePolicy` 复测,不要凭记忆假设。

3. **官方"两侧同步"工具 `openclaw exec-policy set` 与 `tools.exec.mode` 互斥**:尝试用官方推荐的 `openclaw exec-policy set --security full --ask off --ask-fallback full` 同时显式写 host 侧 `defaults`,报错:
   ```
   Config validation failed: tools.exec.mode: tools.exec.mode cannot be combined with tools.exec.security or tools.exec.ask
   ```
   即 schema 层面强制 `mode` 与离散的 `security`/`ask`/`host` 字段二选一,不能共存。已核对该命令失败前未写入任何文件(`openclaw.json` 的 `tools` 段与 `exec-approvals.json` 均确认未变)。因此本次保留 `tools.exec.mode: "full"` 这一单一写法(与派单里"目标是 `tools.exec.mode` 配成 `full`"的字面要求一致),未使用 `exec-policy set`。

4. **CLI 自身的配置备份轮转会"吃掉"自定义命名的备份文件**:`cp -p` 建的 `~/.openclaw/openclaw.json.bak.20260808` 在执行 `openclaw config set` 之后消失,原地多出一个不带日期后缀的 `~/.openclaw/openclaw.json.bak`(内容 sha256 与丢失的那份一致,数据没丢,只是文件名被"占用"/覆盖,具体机制未深挖,不确定是覆盖还是改名)。已改用仓库既有的 `.before-<desc>.bak` 命名(该目录里 `openclaw.json.before-acp-poc.bak` 等历史文件从未被该轮转覆盖)重新落一份确定不会被吃掉的备份。**后续改这个配置文件时,自定义备份名不要用 `xxx.bak.<纯数字或日期>` 这种可能撞上工具轮转规则的模式**,改用 `xxx.before-<场景>.bak`。

5. **`openclaw doctor --lint --all --json` 未把这 3 条 Node/PATH 警告列为 finding**——它们只出现在 `openclaw daemon status` 的输出里,不在 `doctor --lint` 的 51 项检查范围内(`doctor --lint` 覆盖的是 plugin-installs / gateway-daemon / gateway-health / memory-search / security / skills-readiness / workspace-status 这几类 checkId)。意味着"跑 `doctor --lint` 看是否有 Node 相关阻塞项"这条路径本身查不到这 3 条警告,得靠 `daemon status` 的自由文本才能看到——留给后续如果真要处理 Node 迁移时参考。

---

## 遗留问题 / 待确认红线

- `openclaw daemon status` 仍报 3 条 Node/nvm 相关 service config issue(见"遇到的坑"1),按硬边界未处理,是否要处理留给用户或后续任务节点拍板;`openclaw doctor --repair` 的具体行为(是否会动 Node)本次未探测,如需处理请先单独确认其 dry-run/影响范围。
- `openclaw doctor --lint --all --json` 中还报了一批与本次任务无关的 warning(缺失的 skills 依赖、`openclaw.json` 里的明文 secret 字段、`deepseek` 插件未安装等)——均与 C-00 三项判据无关,按派单"不考虑安全问题/只做派单范围内的事"未处理,原样列出供知悉:`core/doctor/security`(明文 secret)、`core/doctor/skills-readiness`(约 20 条不可用 skill)、`core/doctor/configured-plugin-installs`(deepseek 插件未装)、`core/doctor/memory-search`(缺 OPENAI_API_KEY)。

---

# 第二轮:消除 `openclaw daemon status` 的 3 条 Node/nvm service config issue(2026-08-08 续)

> 执行者:devops-engineer | 日期:2026-08-08(同日续做,接续上面"遗留问题"第 1 条)
> 授权依据:本轮派单目标就是"全部消除"以下 3 条(上一轮任务明确划了硬边界不碰),派单边界原文:"需要 sudo 的操作、以及任何会影响本机其他项目的变更,做之前在回执里说清你要做什么"——本节按此把每一步 sudo 操作和影响面写清楚。
> 执行前基线(`openclaw daemon status` 原样输出):
> ```
> Service config issue: Gateway service PATH includes version managers or package managers; recommend a minimal PATH. (/home/ky/.nvm/versions/node/v24.18.0/bin)
> Service config issue: Gateway service uses Node from a version manager; it can break after upgrades. (/home/ky/.nvm/versions/node/v24.18.0/bin/node)
> Service config issue: System Node 22 LTS (22.22.3+) or Node 24.15+ not found; install it before migrating away from version managers.
> ```

## 诊断(读 openclaw 自身源码,不是猜)

`openclaw` 是用 esbuild 打包发布的,`~/.nvm/versions/node/v24.18.0/lib/node_modules/openclaw/dist/*.js` 里保留了未混淆的函数名/字符串,直接读源码定位了 3 条 issue 的判定逻辑:

- `runtime-paths-C6MOwQ_j.js` `buildSystemNodeCandidates()`(Linux 分支):"系统级 Node" 只认 `/usr/local/bin/node` 或 `/usr/bin/node` 这两个绝对路径,别的地方装了也不算。
- `runtime-guard-CcN7oTJc.js` `isSupportedNodeVersion()`:要求 Node `>=22.22.3 <23` 或 `>=24.15.0 <25` 或 `>=25.9.0`。
- `sqlite-runtime-version-Bwtp8f2j.js` `isSqliteWalResetSafeVersion()`:额外要求该 Node 内置的 `node:sqlite` 的 SQLite 版本 `>=3.51.3`(或退回兼容版 `3.44.6`/`3.50.7`)。
- `runtime-paths-C6MOwQ_j.js` `isNonMinimalServicePathEntry()`:PATH 条目里含 `/.nvm/`、`/.fnm/`、`/.volta/`、`/.asdf/`、`/pnpm/` 等字样即判"非最小化",除非该条目同时也在"期望 PATH 集合"里(见下一条)。
- `daemon-install-plan.shared-DqkY2Emy.js` `resolveDaemonServicePathDirs()`:装/重装服务时,除了 Node 所在目录,还会扫描当前跑 `openclaw gateway install` 那次命令自己的 `PATH` 环境变量,把每一段里能找到、且 realpath 与当前 `openclaw` CLI 脚本一致的目录都塞进服务 PATH——这就是为什么"重装一次"仍然会把 nvm 的 bin 目录带回来:因为重装命令本身是在含 nvm 路径的交互式 shell 里跑的。

结论:要让 `openclaw daemon status`/`openclaw doctor` 认定"已脱离版本管理器",必须同时满足 (a) `/usr/local/bin/node` 或 `/usr/bin/node` 存在且版本达标,(b) 服务的 `ExecStart` 指向该路径,(c) 重装服务那次调用本身的 `PATH` 环境变量里不能再出现 nvm 的 bin 目录(否则会被上面第 5 条的扫描逻辑重新写回服务 PATH)。

## 操作步骤(命令原样,按执行顺序)

### 步骤 1:确认无密码 sudo 可用、且 `/usr/local/bin`、`/usr/local/lib` 干净(无冲突)

```bash
sudo -n true && echo PASSWORDLESS_SUDO_OK
ls -la /usr/local/bin/ /usr/local/lib/
```

**实际输出**:`PASSWORDLESS_SUDO_OK`;两个目录均为空(`/usr/local/lib` 下只有一个无关的 `python3.12`)——确认是纯增量操作,不会覆盖/影响任何已有文件或其他项目。

### 步骤 2:下载官方 Node 22 LTS(Jod)最新版并校验 checksum

不用 nvm 装(会继承同样的版本管理器风险),不用 NodeSource 加 apt 源(会往系统级 apt 源列表里加东西,影响面更大、且 Ubuntu 24.04 自带仓库只有 `18.19.1`,达不到 openclaw 的版本要求)。改用官方预编译 tar 包放到 `/usr/local`,是 nodejs.org 官方文档给的标准手动安装方式,不碰包管理器状态。

```bash
curl -fsSL -o node.tar.xz "https://nodejs.org/dist/v22.23.2/node-v22.23.2-linux-x64.tar.xz"
curl -fsSL -o SHASUMS256.txt "https://nodejs.org/dist/v22.23.2/SHASUMS256.txt"
grep "node-v22.23.2-linux-x64.tar.xz" SHASUMS256.txt
sha256sum node.tar.xz
```

**实际输出**(两行一致,校验通过):
```
d60acfe00a2932254bb0ad20e01b0d74397a0875595de719654b214f4b03f307  node-v22.23.2-linux-x64.tar.xz
d60acfe00a2932254bb0ad20e01b0d74397a0875595de719654b214f4b03f307  node.tar.xz
```

本地解压后先用 openclaw 自己的探活逻辑(从源码摘出来原样复用)验证这个 Node 满足上面"诊断"里的两条版本要求,再往系统里装:

```bash
tar -xf node.tar.xz
./node-v22.23.2-linux-x64/bin/node -e '
let sqliteVersion = null;
try {
  const { DatabaseSync } = require("node:sqlite");
  const db = new DatabaseSync(":memory:");
  try { sqliteVersion = db.prepare("SELECT sqlite_version() AS version").get()?.version ?? null; }
  finally { db.close(); }
} catch (e) { console.error("sqlite probe error:", e.message); }
process.stdout.write(JSON.stringify({ nodeVersion: process.versions.node, sqliteVersion }));
'
```

**实际输出**:`{"nodeVersion":"22.23.2","sqliteVersion":"3.51.3"}`——`22.23.2 >= 22.22.3` 达标,`3.51.3 >= 3.51.3` 达标。

### 步骤 3(sudo,新增系统文件,不覆盖任何已有文件):把 Node 22.23.2 装进 `/usr/local`

要做什么:在 `/usr/local/lib/nodejs/` 下新建一个版本化目录存放官方预编译包(FHS 标准的"非包管理器手动安装软件"位置),再在 `/usr/local/bin/` 下建 4 个软链接(`node`/`npm`/`npx`/`corepack`)指过去。不新建 apt 源、不装 apt 包、不改任何已有文件。

```bash
sudo mkdir -p /usr/local/lib/nodejs
sudo cp -a ./node-v22.23.2-linux-x64 /usr/local/lib/nodejs/node-v22.23.2-linux-x64
sudo chown -R root:root /usr/local/lib/nodejs/node-v22.23.2-linux-x64
sudo ln -sf /usr/local/lib/nodejs/node-v22.23.2-linux-x64/bin/node /usr/local/bin/node
sudo ln -sf /usr/local/lib/nodejs/node-v22.23.2-linux-x64/bin/npm /usr/local/bin/npm
sudo ln -sf /usr/local/lib/nodejs/node-v22.23.2-linux-x64/bin/npx /usr/local/bin/npx
sudo ln -sf /usr/local/lib/nodejs/node-v22.23.2-linux-x64/bin/corepack /usr/local/bin/corepack
```

**实际输出**:无报错;`ls -la /usr/local/bin/` 确认 4 个软链接建好;`/usr/local/bin/node -v` → `v22.23.2`。

对本机其他项目的影响评估:交互式 shell 的 `$PATH` 里 `/home/ky/.local/bin`(排第 2 位,指向 nvm 的 node/pnpm)排在 `/usr/local/bin`(排第 12 位)之前(已用 `echo $PATH | tr ':' '\n' | nl` 实测确认顺序),所以任何人在普通终端敲 `node`/`npm` 命令,解析结果完全不受影响,仍然走 nvm。此次改动只在系统级 PATH 上新增了一个之前不存在的候选,不会替换任何东西——`apt-cache policy nodejs` 显示 Ubuntu 24.04 仓库只有 `18.19.1`(不达标,所以没有走 apt),也确认没有别的项目/包管理器已经在用 `/usr/local/bin/node` 这个位置。

### 步骤 4:备份当前 systemd unit(改前先备份)

```bash
TS=$(date +%Y%m%d-%H%M%S)
cp /home/ky/.config/systemd/user/openclaw-gateway.service /home/ky/.config/systemd/user/openclaw-gateway.service.bak.$TS
```

**实际输出**:备份时间戳 `20260808-173558`(这份是本轮改动前的原始状态,sha256 `37d46b468f7a09bea629afe5023852736fe59b313377ec877365ffdf4c2fde14`,用于下方"完全回滚")。

### 步骤 5:新建 `~/.local/bin/openclaw` 软链接(用户目录内,免 sudo,照搬本机已有的 `~/.local/bin/node`/`~/.local/bin/pnpm` 惯例)

为什么要这步:上面"诊断"第 5 条提到,重装服务命令会扫描"调用那次命令自己的 PATH",把能找到 `openclaw` 可执行文件、且 realpath 与当前 CLI 一致的目录都写回服务 PATH。本机当时只有 `~/.nvm/versions/node/v24.18.0/bin/openclaw` 这一个入口,没有其他"看起来正常"的路径能命中。装完 Node 后先跑过一次 `openclaw gateway install --force`(未加 PATH 限制)做验证,结果证实了这一点——ExecStart 和"uses Node from a version manager"两条已经消失,但"PATH includes version managers"这条仍在,detail 精确指向 `/home/ky/.nvm/versions/node/v24.18.0/bin`。于是新增这个软链接,给"重装那次调用"一个不含 `.nvm/` 字样、同时又在 openclaw 自己"期望 PATH 集合"里的入口(`~/.local/bin` 本来就在期望集合里,和 `~/.local/bin/node`/`pnpm` 是同一模式,不是新发明)。

```bash
ln -s /home/ky/.nvm/versions/node/v24.18.0/bin/openclaw /home/ky/.local/bin/openclaw
PATH=/usr/local/bin:/home/ky/.local/bin:/usr/bin:/bin /home/ky/.local/bin/openclaw --version
```

**实际输出**:`OpenClaw 2026.7.1-2 (0790d9f)`——软链接可用,且用限定 PATH 调用时能正常跑起来(`env node` shebang 这时解析到的是 `/usr/local/bin/node`,新装的系统 Node 也扛得住 openclaw CLI 本身的运行,不只是扛得住网关进程)。

### 步骤 6:用限定 PATH 重装 Gateway 服务(触发官方自愈,而不是手改 unit 文件)

```bash
PATH=/usr/local/bin:/home/ky/.local/bin:/usr/bin:/bin /home/ky/.local/bin/openclaw gateway install --force --port 18789
```

**实际输出**:
```
Installed systemd service: /home/ky/.config/systemd/user/openclaw-gateway.service
Previous unit backed up to: /home/ky/.config/systemd/user/openclaw-gateway.service.bak
```

这条命令内部会自动做 `systemctl --user daemon-reload && enable && restart`(源码 `systemd-B4Oq2owH.js` 的 `installSystemdService`,固定顺序,不需要我们手动再跑一遍),执行完服务已经是新配置在跑。

为什么不手改 `.service` 文件、改走官方命令:硬规则第 5 条"先看项目已有设施,增量改";`openclaw gateway install --force` 是官方给的、和 `daemon status`/`doctor` 用的是同一套判定函数的重装工具,手改文件容易和判定逻辑对不上、下次 `openclaw` 自身升级/迁移逻辑跑起来时又冲突。用官方工具还有一个好处:它自带 `daemon-reload+enable+restart`,不用我们自己拼 systemctl 三连。

## 验证证据(四项完成标准逐条实跑)

### 标准 1:`openclaw daemon status` 不再报 3 条 issue

```
$ openclaw daemon status
Service: systemd user (enabled)
File logs: /tmp/openclaw/openclaw-2026-08-08.log
Command: /usr/local/lib/nodejs/node-v22.23.2-linux-x64/bin/node /home/ky/.nvm/versions/node/v24.18.0/lib/node_modules/openclaw/dist/index.js gateway --port 18789
Service file: ~/.config/systemd/user/openclaw-gateway.service
Service env: OPENCLAW_GATEWAY_PORT=18789

Config (cli): ~/.openclaw/openclaw.json
Config (service): ~/.openclaw/openclaw.json

Gateway: bind=loopback (127.0.0.1), port=18789 (service args)
Probe target: ws://127.0.0.1:18789
Dashboard: http://127.0.0.1:18789/
Probe note: Loopback-only gateway; only local clients can connect.

CLI version: 2026.7.1-2 (~/.local/bin/openclaw)
Gateway version: 2026.7.1-2

Runtime: running (pid 327897, state active, sub running, last exit 0, reason 0)
Connectivity probe: ok
Capability: write-capable

Listening: 127.0.0.1:18789, [::1]:18789
Troubles: run openclaw status
Troubleshooting: https://docs.openclaw.ai/troubleshooting
```

无 "Service config issue" 段落、无 "Service config looks out of date or non-standard"、无 "Recommendation: run openclaw doctor" 三行——3 条全部消失。**结论:达成。**

### 标准 2:Gateway 服务仍 enabled + running,18789 仍有监听

```
$ systemctl --user is-enabled openclaw-gateway
enabled
$ systemctl --user is-active openclaw-gateway
active
$ ss -tlnp | grep 18789
LISTEN 0      511        127.0.0.1:18789      0.0.0.0:*    users:(("node",pid=327897,fd=33))
LISTEN 0      511            [::1]:18789         [::]:*    users:(("node",pid=327897,fd=34))
```

`systemctl --user status openclaw-gateway` 补充确认:`Active: active (running) since Sat 2026-08-08 17:39:55 +08`,`Main PID: 327897 (node)`,CGroup 里的进程命令行是新的 `/usr/local/lib/nodejs/node-v22.23.2-linux-x64/bin/node ...`。**结论:达成。**

### 标准 3:`openclaw health` 仍正常

```
$ openclaw health
Telegram: configured
Gateway event loop: ok max=267ms p99=23ms util=0.051 cpu=0.121
Agents: main (default), dev
Heartbeat interval: 30m (main)
Session store (main): /home/ky/.openclaw/agents/main/sessions/sessions.json (17 entries)
- agent:main:openai-user:vt:default:itest:butler (12914m ago)
- agent:main:main (17160m ago)
...
```

返回真实数据,和改动前(重装前也跑过一次做基线对比)输出结构一致,无异常/无 1006 断连。**结论:达成。**

### 标准 4:`openclaw approvals get --json` 的 effectivePolicy 未回退

改动前后各跑一次 `openclaw approvals get --json`,`hash` 字段(该文件内容的 sha256,工具自己算的)前后完全一致:`4e7a9bcfcf0c286ca67b432f985ff733c9dc369c64bb1ce3768c7f7baa166903`——文件字节都没变过,不用比对字段。`effectivePolicy` 里 `tools.exec` 和 `agent:dev` 两个 scope 仍是:
```
mode:     requested=full, effective=full
security: requested=full, host=full, effective=full
ask:      requested=off,  host=off,  effective=off
```
**结论:达成,未回退。**(本轮改动只涉及 systemd unit 和 `/usr/local` 下的 Node 安装,没碰 `~/.openclaw/exec-approvals.json` 或 `openclaw.json` 的 `tools` 段,这条能保持不变符合预期。)

## 回滚步骤(与操作步骤逐一对应)

### 完全回滚(回到本轮改动前,即仍是 nvm node + 3 条 issue 的状态)

```bash
# 1. 恢复 systemd unit 到本轮改动前快照
systemctl --user stop openclaw-gateway.service
cp -p /home/ky/.config/systemd/user/openclaw-gateway.service.bak.20260808-173558 /home/ky/.config/systemd/user/openclaw-gateway.service
systemctl --user daemon-reload
systemctl --user restart openclaw-gateway.service

# 2.(可选)移除新增的系统 Node 与软链接——不影响 nvm/交互式 shell,纯回收
sudo rm -f /usr/local/bin/node /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack
sudo rm -rf /usr/local/lib/nodejs/node-v22.23.2-linux-x64
rm -f /home/ky/.local/bin/openclaw
```

验证:`openclaw daemon status` 应重新看到本轮开头列的 3 条 issue;`Command:` 行应变回 `/home/ky/.nvm/versions/node/v24.18.0/bin/node ...`;`ss -tlnp | grep 18789` 应仍有监听(回滚只是换回旧 ExecStart,不影响服务本身照常起停)。

### 部分回滚(只想撤掉服务改动,保留系统 Node 装置留着以后用)

只做上面步骤 1,跳过步骤 2 即可——`/usr/local/bin/node` 留着不影响任何东西(见步骤 3 的"影响评估"),之后想重新切回去,重跑步骤 5+6 即可(幂等,`openclaw gateway install --force` 可重复执行,每次都是根据当时环境重新计算渲染,不会因为重复跑而报错或状态错乱)。

## 改动文件与新增资源清单(本轮)

| 路径 | 类型 | 改动 | 备份/可回收方式 |
|---|---|---|---|
| `/usr/local/lib/nodejs/node-v22.23.2-linux-x64/` | 新增(sudo,root:root,204M) | 官方预编译 Node 22.23.2(sha256 `d60acfe00a2932254bb0ad20e01b0d74397a0875595de719654b214f4b03f307` 对应 `node-v22.23.2-linux-x64.tar.xz`,已核对官方 `SHASUMS256.txt`) | `sudo rm -rf` 整个目录即可,纯新增无覆盖 |
| `/usr/local/bin/{node,npm,npx,corepack}` | 新增软链接(sudo) | 指向上一行目录里的对应文件 | `sudo rm -f` 4 个软链接 |
| `/home/ky/.local/bin/openclaw` | 新增软链接(用户态,免 sudo) | 指向 `~/.nvm/versions/node/v24.18.0/bin/openclaw`,照搬本机已有的 `~/.local/bin/node`/`pnpm` 惯例 | `rm -f` |
| `~/.config/systemd/user/openclaw-gateway.service` | 改动(`ExecStart`/`PATH` 两行) | 见下方 diff | `openclaw-gateway.service.bak.20260808-173558`(本轮改动前,sha256 `37d46b468f7a09bea629afe5023852736fe59b313377ec877365ffdf4c2fde14`)、`.bak.20260808-173952`(中间态,过渡产物可忽略) |

```diff
--- openclaw-gateway.service.bak.20260808-173558 (本轮改动前)
+++ openclaw-gateway.service (当前)
@@
-ExecStart=/home/ky/.nvm/versions/node/v24.18.0/bin/node /home/ky/.nvm/versions/node/v24.18.0/lib/node_modules/openclaw/dist/index.js gateway --port 18789
+ExecStart=/usr/local/lib/nodejs/node-v22.23.2-linux-x64/bin/node /home/ky/.nvm/versions/node/v24.18.0/lib/node_modules/openclaw/dist/index.js gateway --port 18789
@@
-Environment=PATH=/home/ky/.nvm/versions/node/v24.18.0/bin:/usr/local/bin:/usr/bin:/bin:/home/ky/.bun/bin:/home/ky/.nvm/current/bin:/home/ky/.local/bin:/home/ky/.npm-global/bin:/home/ky/bin:/home/ky/.nix-profile/bin:/home/ky/.local/share/pnpm
+Environment=PATH=/usr/local/lib/nodejs/node-v22.23.2-linux-x64/bin:/home/ky/.local/bin:/usr/local/bin:/usr/bin:/bin:/home/ky/.bun/bin:/home/ky/.nvm/current/bin:/home/ky/.npm-global/bin:/home/ky/bin:/home/ky/.nix-profile/bin:/home/ky/.local/share/pnpm
```

`~/.openclaw/openclaw.json`、`~/.openclaw/exec-approvals.json`——本轮未改动(sha256 前后一致,见"标准 4")。

## 遇到的坑(本轮新增)

6. **"装了系统 Node"和"重装服务就会用上"是两回事**:第一次单纯装好 `/usr/local/bin/node` 后原地跑 `openclaw gateway install --force`(在正常交互式 shell、未限定 PATH),`daemon status` 立刻从 3 条 issue 降到 1 条(`ExecStart` 和"来自版本管理器"两条消失),但"PATH includes version managers"这条纹丝不动,detail 还是指向 nvm 的 bin 目录。读源码才搞清楚:这条不是看 `ExecStart` 用的 Node 在哪,而是看重装那次调用命令本身的 PATH 环境变量里有没有残留 nvm 路径(`daemon-install-plan.shared-DqkY2Emy.js` 的 `resolveDaemonOpenClawBinDir()` 会扫描调用时的 `$PATH`,找 `openclaw` 可执行文件所在目录写回服务 PATH)。单纯"删掉 nvm 目录再也不用"不现实(还要用 nvm 管理其他 Node 项目),于是用"给 `openclaw` 一个不含 `.nvm/` 字样的入口(`~/.local/bin/openclaw`)+ 重装那条命令本身也限定 PATH"的方式解决,不影响 nvm 本身。

7. **`openclaw` 这个包本身仍然物理装在 nvm 管理的目录里**:本轮只解决了 `ExecStart` 用的解释器(`node` 二进制)不再依赖 nvm,但 `ExecStart` 的脚本参数(`/home/ky/.nvm/versions/node/v24.18.0/lib/node_modules/openclaw/dist/index.js`)本身仍然物理存放在 nvm 管理的 `v24.18.0` 版本目录下——因为 `openclaw` 包当初是在 nvm 的 node v24.18.0 环境下 `npm install -g` 装的。`openclaw daemon status`/`doctor` 的判定逻辑只检查解释器路径,不检查脚本路径,所以这条不会被现有检查项抓到,但派单背景风险描述的"nvm 升级或切版本后该路径失效,Gateway 起不来"这个根因没有 100% 消除:如果将来在这台机器上执行 `nvm uninstall v24.18.0`(把这个具体版本目录整个删掉),网关脚本本身会连带被删,即使解释器已经换成 `/usr/local/bin/node` 也救不回来。完全消除这条残留风险需要把 `openclaw` 这个 npm 包本身也重新装到系统 Node 下(类似 `sudo /usr/local/bin/npm install -g openclaw@2026.7.1-2`),但这属于"新增依赖"类操作(公共纪律第 10 条),本轮未做,也未经批准——列进下方"遗留问题"等拍板,不擅自做。

8. **`gateway install`(不带 `--force`)不会做任何事**:第一次不带 `--force` 跑,报 `Gateway service already ...`,直接返回不重装。必须带 `--force` 才会真正重新渲染 unit 文件——这不是幂等性问题(带 `--force` 本身是幂等的,可反复跑),只是"检测到没变化就跳过"的默认行为,记录一下避免以后误判"命令没生效"。

## 遗留问题 / 待确认红线(更新——不改上面第一轮的原文,这里是本轮新增/更新的判断)

- 上面第一轮"遗留问题"第 1 条("3 条 Node/nvm issue 留作已知遗留项")本轮已处理完毕,`openclaw daemon status` 实测已不再报这 3 条,证据见本节"验证证据"。
- **新的待拍板项**(即"遇到的坑"第 7 条):`openclaw` 这个 npm 包本体仍物理托管在 `~/.nvm/versions/node/v24.18.0/`,若将来执行 `nvm uninstall v24.18.0` 会导致网关重新起不来(和本轮要解的问题同源,但不在 `daemon status` 的检测范围内,所以没体现在完成标准里)。彻底根除需要把 `openclaw` 包重新装到系统 Node 下——这是一次新增依赖 + 覆盖当前"能跑"配置的操作,按公共纪律第 10 条留给用户/后续任务拍板是否要做,本轮未擅自执行。近期的低成本规避方式:不要对 `v24.18.0` 这个具体版本跑 `nvm uninstall`(用 `nvm ls` 确认 alias default 指向即可,不需要删旧版本目录)。
- `openclaw doctor --lint --all --json` 里的其他既有 warning(明文 secret、skills 依赖缺失等)与本轮任务无关,不在本轮范围内,维持第一轮"遗留问题"第 2 条的结论不变。
