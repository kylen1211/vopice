# pipecat 官方资料地图(开发/测试/部署)

> 目的:2 期开发前把"需要哪些资料、去哪里找"对齐。**只建索引,不搬运全量数据**——需要哪个组件,按下表找到示例/文档/源码再细读。
> 建档 2026-08-02。深层数据(源码级数据卡)已存在于罗盘 `~/research/2026-07-30-pipecat官方现成件盘点/罗盘.md`(610 行),本图只做导航,**罗盘已采过的勿重挖**。

## 0. 四个资料源(总览)

| 源 | 位置 | 版本 | 取数方式 |
|---|---|---|---|
| **本地源码 clone** | `~/git/pipecat`(含 `examples/` `tests/` `src/`) | main `v1.6.0-122-g46a1bd9d3`(罗盘 §0.1 已证:对 1.6.0 结论零影响) | 直接 Read;**已建 codegraph 索引**,结构问题一次 `codegraph_explore` 解决 |
| **运行版** | `server/.venv` 内 `pipecat-ai==1.6.0`(`uv.lock` 锁定,extras: evals/kokoro/openai/runner/silero/webrtc/whisper) | 1.6.0(**已落后:PyPI 2026-08-02 实查最新 1.7.0**,升级影响待评估,升级前 1.6.0 仍是行为地面真值) | 行为地面真值;疑难时以 site-packages 实际代码为准 |
| **官方文档站** | `docs.pipecat.ai`(源仓库 `pipecat-ai/docs`) | 随 main 滚动 | 导航树 = `gh api repos/pipecat-ai/docs/contents/docs.json`(一条命令);**正文页 WebFetch 被本机策略禁**,用 tavily/firecrawl extract 取 |
| **周边仓库** | `pipecat-ai/{voice-ui-kit, whisker, tail, skills}` | — | gh 直查;whisker 接入已 PoC 实测(罗盘 §7.2a) |

## 1. 开发 · 功能组件索引(核心表,需要哪个找哪个)

| 功能组件 | 官方示例 `examples/` | 文档章节 `docs.pipecat.ai/` | 源码 `src/pipecat/` |
|---|---|---|---|
| **入门骨架(渐进教程)** | `getting-started/01-say-one-thing` → `07-function-calling`(01a/03a/06a 为 local-audio 变体) | `pipecat/get-started/quickstart`、`pipecat/learn/your-first-agent` | — |
| **语音管线(STT/LLM/TTS 全链)** | `voice/`(按供应商 60+ 文件,`voice-<供应商>.py`) | `pipecat/learn/{speech-input,speech-to-text,llm,text-to-speech}` | `services/`(按供应商分目录) |
| **打断 / 轮次管理** | `turn-management/`(9 个:smart-turn-local、interruption-config、user-mute-strategy、detect-user-idle、filter-incomplete-turns…) | `pipecat/fundamentals/{interruptions,user-input-muting,detecting-user-idle}`;`api-reference/server/utilities/turn-management/*` | `audio/turn/` |
| **函数调用** | `function-calling/`(按供应商,含 async/stream/advanced-functionschema 变体) | `pipecat/learn/function-calling` | `adapters/` |
| **上下文管理** | `context-summarization/`(4 种)、`persistent-context/`(8 种) | `pipecat/learn/context-management`、`pipecat/fundamentals/context-summarization` | `processors/aggregators/` |
| **实时翻译(场景③直接相关)** | `features/features-live-translation.py`、`features-switch-languages.py` | — | — |
| **服务热切换** | `features/features-service-switcher.py`、`features-pattern-pair-voice-switching.py` | `pipecat/fundamentals/service-settings` | `utils/` |
| **自定义 processor** | `features/features-custom-frame-processor.py` | `pipecat/fundamentals/custom-frame-processor`(含 Best Practices 小节) | `processors/frame_processor.py` |
| **MCP 工具接入** | `mcp/`(stdio、streamable-http、multiple-mcp) | `api-reference/server/utilities/mcp` | `services/mcp_service.py` |
| **RAG / 长期记忆** | `rag/`(mem0、gemini-grounding) | — | `services/`(mem0 等) |
| **多 agent / 派活(2 期核心)** | `multi-worker/`(code-assistant 逐行数据已在罗盘 §3.3) | `pipecat/learn/{multiple-llm-agents,ui-worker,agent-handoff,job-coordination,distributed-agents,proxy-agents}`;`pipecat/fundamentals/{agent-bus,agent-registry-and-discovery,understanding-the-bus-bridge}` | `bus/` + `workers/`(API 形状见罗盘 §3.1) |
| **观测 / 指标** | `observability/`(observer、heartbeats、sentry-metrics) | `pipecat/fundamentals/metrics`;`api-reference/server/utilities/observers/*`(startup-timing、user-bot-latency) | `observers/` |
| **传输层** | `transports/`(small-webrtc、daily、livekit、moq、vonage) | `pipecat/learn/transports`;`client/concepts/choosing-a-transport`(已细读,罗盘 §5) | `transports/` |
| **音频处理** | `audio/`(recording、background-sound、sound-effects) | `pipecat/fundamentals/{recording-audio,saving-transcripts}` | `audio/` |
| **视觉 / 视频 / 数字人** | `vision/`、`video-processing/`、`video-avatar/`、`realtime/` | `pipecat/features/*` | 本期用不上,知道在哪即可 |

## 2. 开发规范(写码前看)

- **代码风格**:`~/git/pipecat/CONTRIBUTING.md` §Code Style——Ruff lint + format;**Google-style docstring** 三套模板(普通类 / dataclass / enum,原文 180-395 行有完整示例)。
- **changelog fragment 制度**(CONTRIBUTING §Changelog Entries):仅向上游贡献 PR 时需要,本项目内部开发不用。
- **我们已对齐的门禁**:ruff / pyright / pytest / `pipecat eval`(1 期 T4.3 已建立,2 期沿用)。
- **examples 运行方法**(官方 README):在 `~/git/pipecat` 仓库根 `uv sync --group dev --all-extras --no-extra gstreamer --no-extra local` → `cp env.example .env` 填 key → `uv run python getting-started/01-say-one-thing.py` → 浏览器开 `localhost:7860/client`。多数示例支持 `-t daily`/`-t twilio` 换传输层。
- **API Reference**:文档站 `api-reference/server/`(Services 按 STT/LLM/TTS/Memory/Translation 等 15 类分组;Utilities 按 Observers/Smart-Turn/MCP 等 14 类分组)。

## 3. 测试与评测

- **单测范式**:`~/git/pipecat/tests/`(200+ 文件,`test_<模块名>.py` 一一对应;集成测试单独在 `tests/integration/`)。**写新测试前,先找同模块的官方测试文件当模板**。
- **evals 文档**:`pipecat/evals/{overview,lifecycle,quickstart,scenarios,suites,library,the-eval-loop}`(页目录已知,**原文未细读**=罗盘缺口 G3;要用时按需 extract)。
- **evals 源码级事实**(已采,查罗盘 §2):`EvalSession` Python API 可绕 CLI 直接 pytest 内调用(§2.2)、scenario 可断言事件全表(§2.3)、官方标准用法(§2.4)。
- **我们的既有件**:`server/evals/*.yaml` 5 个(自研 3 件计门禁 + starter 2 件不计)、`server/tests/test_config.py`。注意:eval transport 是长驻单进程,独立测量前先杀旧进程(1 期记忆)。
- **第三方评测平台**:`pipecat/evals/platforms/{arize,bluejay,cekura,coval,roark}`(cekura 有 18+ 预置场景,罗盘 §10)。
- **调试工具**:whisker(实时管线调试器,接入实测通过,罗盘 §7.2a)、tail(终端面板,未装)。

## 4. 部署(现阶段只需知道在哪,产品化前不动)

- **文档站 Deployment 10 页**:`pipecat/deployment/{overview,running-bots-locally,running-bots-in-production,telephony-in-production}` + 三种生产托管模式 `patterns/{vm-per-session,warm-pool-subprocess,managed-runtime}` + 平台指南 `platforms/{fly,cerebrium,modal}`。
- **Pipecat Cloud**(托管档):`pipecat-cloud/fundamentals/{deploy,agent-images,secrets,scaling,health-checks,logging,error-codes}`。
- **CLI**:`pipecat init`(脚手架,自带 Dockerfile)/ `pipecat cloud deploy` 等,命令参考 `api-reference/cli/*`。
- **本项目现状**:本机自用,`uv run bot.py`(:7860)+ `npm run dev`(:5174),启动细节见根 README。

## 5. 取数口诀

1. 源码 / 示例 / 测试范式 → 本地 clone 直接读(codegraph 可结构化查)。
2. 文档正文 → tavily/firecrawl extract `https://docs.pipecat.ai/<本图路径>`(WebFetch 被禁)。
3. 文档导航是否有新章节 → `gh api repos/pipecat-ai/docs/contents/docs.json --jq .content | base64 -d`。
4. evals / bus-workers / AEC / 轮次 / UI 工具 / 架构机理的**深数据** → 先查罗盘对应 §,勿重挖。
