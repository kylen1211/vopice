# 2 期能力账单对照表(草稿,待用户核)

> 每项能力 = 旧库参考 + pipecat 官方对应件 + 新骨架现状。2 期迭代方案与门一 PRD 从此表推导。
> 口径(2026-08-02 用户裁决):防捕获去除;**派活与慢脑是两个独立功能**;陪练=配置态不单列;同声翻译+面试辅助是仅有的两个"实际要加的功能",放最后。
> 状态:✅ 新骨架已有 / ⚠️ 有但有债 / ❌ 未做 / 📄 仅设计。旧库定位细节查 `legacy-capability-index.md`,官方资料取数查 `official-resources-map.md`。

## 〇、最终目标(唯一版本)

**桌面客户端**承载:G1 实时语音对话 / G2 慢脑质量升级(快脑先答→慢脑深析→回流补充续接)/ G3 派活(派发任务不中断对话)/ G4 按需监控本机页面内容实时交互。

## 四项核对结论(2026-08-02 查证,以代码为准)

1. **慢脑原版控制方式**(用户记忆吻合):`vt/processors/assist.py`——step1 快脑**立即**出框架式简答(恒不注资料),step2 慢脑在**独立线程**做检索+深度分析,完成后回流播报;支持打断,①②可同引擎共享连接。pipecat **无快慢脑现成件**(罗盘已核),但有 ParallelPipeline / async FrameProcessor 等组装件,须薄装配复刻此逻辑。
2. **语义轮次非自研**:旧库用的就是官方 `LocalSmartTurnAnalyzerV3`(butler.py:507)。VAD(silero)只测声学停顿;Smart Turn 判"话说完没说完"。2 期直接接官方件,零自研——符合"不想自研"。
3. **AEC 实况**:旧库做成的是**回声隔离**(路由层,TTS 不被自采,实测过)——不是外放回声消除;OS 级 AEC spec 原文即"二期候选,本期不做"。关键事实:**Linux 原生 AEC 无解,浏览器 AEC 是兜底**(1 期 research 已录)——网页端白捡;桌面客户端若走 Electron(Chromium 内核),浏览器 AEC 同样白捡(qwen-audio-agent 先例)。
4. **STT/TTS 硬编码是用法问题**:1 期 bot.py 是 quickstart 脚手架形态,不是官方上限。官方正确形态 = 构造时注入任意 service + 运行时 `ServiceSwitcher`(`examples/features/features-service-switcher.py`、docs `fundamentals/service-settings`);旧库 `va/services/llm_factory.py` 的 config-driven 工厂就是同款模式,可直接照搬思路。

## G0 · 载体:桌面客户端

| 子能力 | 旧库参考 | 官方对应件 | 现状 | 备注 |
|---|---|---|---|---|
| 脱浏览器运行的桌面壳 | `vt/panel/`(Qt) | 官方无桌面壳;client SDK 有 JS/React/RN/iOS/Android/C++;Electron 先例=qwen-audio-agent | ❌ | Electron 壳可保浏览器 AEC(核对结论 3) |
| 悬浮面板、双通道分栏 | control-panel spec(防捕获已去除) | voice-ui-kit 组件(现网页端在用) | ❌ | |
| 语音下达任务入口 | desktop-client R6 | RTVI 协议(罗盘 §12.2 全表) | ❌ | |

## G1 · 实时语音对话

| 子能力 | 旧库参考 | 官方对应件 | 现状 | 备注 |
|---|---|---|---|---|
| 基础回路 STT→LLM→TTS、双通道输出、快速失败 | — | 1 期即官方脚手架 | ✅ | 网页端 |
| 打断 | voice-interaction R9-R11 | `fundamentals/interruptions`、`turn-management-interruption-config.py` | ⚠️ | 有但未专测(R2) |
| 语义轮次 | butler.py:507 | **`LocalSmartTurnAnalyzerV3`** + `turn-management-smart-turn-local.py` | ❌ | 已核(2026-08-02):**V3 是框架默认停顿策略**(`turns/user_turn_strategies.py:46`),连显式构造都不用,确认默认生效+调参即可 |
| 外放回声(AEC) | 回声隔离 `vt/audio/` | 浏览器 AEC(网页/Electron 白捡);官方 audio filters 全是**降噪类无 AEC 件**(`KrispVivaFilter`/koala/rnnoise/aic,无 `KrispFilter` 类名) | ⚠️ | 网页端已白捡;桌面端选型定成败 |
| STT/TTS/LLM 可插拔 | `vt/providers/registry.py`、`va/services/llm_factory.py` | service 构造注入 + `ServiceSwitcher` | ❌ | 现硬编码;改造方向明确(核对结论 4) |
| 场景装配/开关(陪练在此层) | `va/scenarios/` 配方 + dual-pipeline-core | 官方无场景配方层;薄装配(llm_factory 模式) | ❌ | **陪练=换 prompt/换 LLM,随此层自然获得** |
| 断连韧性、云 API 失败恢复 | scenario-assembly R17/R18 | `client/concepts/session-lifecycle` | ❌ | B1 断线重连现在还是坏的 |
| 出错口头告知 | — | ErrorFrame→TTS 方向(1 期未验证) | ❌ | REQ-004 backlog |
| TTS 播放完整性 | — | `stop_frame_timeout_s` 调大(修法已验证) | ❌ | B2,已定位根因 |
| 会话上下文、语言模板会话绑定 | voice-interaction R12/R13 | `learn/context-management` | ⚠️ | 新骨架仅单会话 context |
| 音频设备自检/失效检测 | `vt/audio/selfcheck.py`、`devices.py` | — | ❌ | 桌面端才需要 |

## G2 · 慢脑质量升级(独立功能,与派活无关)

| 子能力 | 旧库参考 | 官方对应件 | 现状 | 备注 |
|---|---|---|---|---|
| 快脑先答→慢脑深析→回流补充 | **`vt/processors/assist.py`(成功版)**;简化版 `va/processors/assist_answer.py` | 无现成件;组装件=ParallelPipeline、async FrameProcessor、producer/consumer;**最佳参照实例=`features-concurrent-llm-evaluation.py`(双 LLM 并行,2026-08-02 核出)**;注意 producer/consumer examples 零用例但官方 tests 有 5 用例(`tests/test_producer_consumer.py`,含跨 ParallelPipeline 分支搬运 `test_produce_parallel_pipeline_no_passthrough`,即快慢脑接法;2026-08-02 更正) | ❌ | 2 期核心;NFR 旧标准可参考:首响 ≤1s、衔接静默 ≤2s、不自相矛盾(spec R7/R8) |

## G3 · 派活(独立功能)

| 子能力 | 旧库参考 | 官方对应件 | 现状 | 备注 |
|---|---|---|---|---|
| 任务派发、状态查询、多任务独立、紧急中止 | assistant-orchestration + `va/orchestration/` | **`bus/` + `workers/`**(罗盘 §3 六项能力实测)、`learn/` 多 agent 6 页、`examples/multi-worker/` | ❌ | 执行载体待定;判据底稿=qwen Work 状态机(自含版见 `docs/external-design-references.md` §1,2026-08-02 拍板采用) |
| 派发期间对话不中断 | — | bus 异步派发(processor 异常不致命已实测,罗盘 §3.6) | ❌ | 本次新明确的硬需求 |
| 完成确认铁律、关键节点播报、状态未知处置 | R6B-R3/R4/R5/R5b | 无官方件,文本契约层自装 | ❌ | "未确认完成绝不报办好了" |
| 授权确认链 + 审计 | assistant-orchestration R4-R12 | 无官方件,业务层自装 | ❌ | |
| 手动接管兜底 | R6B-R1c 设计 | — | 📄 | |

## G4 · 本机页面监控/实时交互

| 子能力 | 旧库参考 | 官方对应件 | 现状 | 备注 |
|---|---|---|---|---|
| 浏览器页面采集(只读) | R6-C 设计 | chrome-devtools MCP(本机在用)+ `services/mcp_service.py` | 📄 | |
| 截屏 + VLM 兜底 | R6-C 设计 | `examples/vision/` + VLM services | 📄 | |
| 原生应用 AT-SPI2 | 代码已不在旧库,仅 round5 归档 research 留痕 | 无官方件 | 📄 | |
| 感知降级、注入防线 | desktop-perception R8/R13 | — | 📄 | NFR:采集 ≤200ms、永不阻塞语音回路 |

## 场景层(放最后)

| 场景 | 定性 | 旧库参考 | 官方对应件 | 现状 |
|---|---|---|---|---|
| 陪练 | **配置态**,不是功能 | `va/scenarios/` 配方 | — | 随 G1 装配层获得 |
| **同声翻译** | 真功能① | `vt/processors/translator.py` + 音频直通 + translation-control spec | `features-live-translation.py`、Translation services 类别 | ❌ 最后做 |
| **面试辅助** | 真功能② | `main_interview.py` + `vt/processors/assist.py` + `kb_service/` + interview-assist/knowledge-retrieval specs | 无官方对应(自研业务);KB 可参考 `examples/rag/` | ❌ 最后做 |

## 横切约束

契约字段第一天带 user/tenant(实现单用户)/ 鉴权多用户后置(暴露公网前必补)/ 会话恢复 2 期+候选 / 慢脑 70B 级永远云 API / 官方脚手架结构不动(2026-08-02 口径)/ **STT/TTS 沿用原付费 API,本地语音服务暂停**(2026-08-02 用户拍板)/ **派活流程与状态机直接采用 qwen Work 底稿(状态+投递不变量),不新增其他形式**(2026-08-02 用户拍板)。

## 官方件核对记录(2026-08-02,本地 clone v1.6.0-122 实锤,以源码为准)

逐项核对结论:**账单映射全部核实成立,无一虚指**。实锤路径:

- 打断:`examples/turn-management/turn-management-interruption-config.py`(同目录 9 例)✅
- 语义轮次:`audio/turn/smart_turn/local_smart_turn_v3.py:28`,且为默认策略 ✅(增量发现①)
- 可插拔:`pipeline/service_switcher.py:211` `ServiceSwitcher`(Manual/Failover 策略)+ `features-service-switcher.py` ✅
- 出错告知:`frames/frames.py:950` `ErrorFrame` ✅;TTS 完整性:`services/tts_service.py` `stop_frame_timeout` ✅
- 上下文:`context-summarization/` 4 例 + `persistent-context/` 8 例 ✅
- G2 组装件:`pipeline/parallel_pipeline.py`、`processors/{producer,consumer}_processor.py` ✅(增量发现②:`features-concurrent-llm-evaluation.py` 双 LLM 并行最佳参照;增量发现③更正:producer/consumer examples 零用例但官方 tests 有 5 用例(`tests/test_producer_consumer.py`,含跨 ParallelPipeline 分支搬运 `test_produce_parallel_pipeline_no_passthrough`,即快慢脑接法;2026-08-02 更正))
- G3:`src/pipecat/bus/` + `src/pipecat/workers/` + `examples/multi-worker/` 7 例 ✅
- G4:`services/mcp_service.py` + `examples/mcp/` 4 例 + `examples/vision/` 7 例 ✅
- 无官方件确认(自装,与账单一致):场景装配层、音频设备自检、完成确认铁律/授权链、AT-SPI2/注入防线
- 文档级待取:`client/concepts/session-lifecycle`(断连韧性,要用时 tavily extract)

### 0802 参考资料(livekit-vs-pipecat 调研)核对结论(2026-08-02)

逐条核对 0802 调研资料(核实后的自含版已落 `docs/external-design-references.md`,原始调研目录待用户清理),结果:**实体断言基本属实,4 处出入**。

已核实为真:PyPI pipecat-ai=1.7.0、livekit-agents=1.6.7(curl 实查);stars 量级吻合;LiveKit `_FillerScheduler`(`voice/filler_scheduler.py`,gh code search 实锤);LiveKit examples frontdesk/survey/hotel_receptionist 均在;`SalesforceAIResearch/VoiceAgentRAG`(2026-07-28 新库)、`ServiceNow/eva`、`kwindla/aiewf-eval` 三仓库真实;本地实锤 `InterruptionFrame`(frames.py:1019)、`EvalJudge`(evals/judge.py:107)、`01a-local-audio.py`、`update-settings/`。

4 处出入:①报告所有"源码链接"均错挂 `file:///home/ky/git/data-foundation-agent`(链接坏,所指文件本身真实);②运行命令应为 `pipecat eval run`(`python -m pipecat.evals` 有 `__main__.py` 可跑但非官方口径);③"Pipecat 原生内置快慢脑"措辞过强——实为组装件(ParallelPipeline)存在,无快慢脑现成件,与罗盘结论一致;④aiewf-eval 实际描述是"A long-context eval",报告"多轮语音评测集"说法待确认。Silero VAD 参数(250/400ms)未验证。

**连带发现**:我们资料地图原口径"1.6.0 无落后"已过时(PyPI 已出 1.7.0),地图已更正;本地 clone(main v1.6.0-122)已含 1.7.0 方向代码(如 InterruptionFrame),锁定版 1.6.0 升级影响待门二评估。

## 能力二分:核心能力 vs 优化方案(草稿,待用户核,2026-08-02)

> 口径:**核心能力** = 构成最终目标 G0-G4 与场景真功能的新建能力;**优化方案** = 围绕既有 G1 回路的质量/健壮性/体验改进。后续迭代围绕此二分推进。

### 核心能力

| # | 能力 | 出处 |
|---|---|---|
| C1 | 桌面客户端载体(壳 + 悬浮面板 + 语音任务入口) | G0 全部 |
| C2 | 服务可插拔 + 场景装配层(使能层:陪练配置态、同传/面试均挂此层) | G1 |
| C3 | 快慢脑(快答→深析→回流续接) | G2 全部 |
| C4 | 派活(派发/状态/多任务/中止 + 不中断 + 完成确认铁律 + 授权审计 + 手动接管) | G3 全部 |
| C5 | 页面监控(浏览器采集 + 截屏 VLM + AT-SPI2 + 感知降级/注入防线) | G4 全部 |
| C6 | 同声翻译(真功能①,放最后) | 场景层 |
| C7 | 面试辅助(真功能②,放最后) | 场景层 |

### 优化方案

| # | 项 | 出处 | 依赖 |
|---|---|---|---|
| O1 | 打断专测(有但未专测) | G1 | — |
| O2 | 语义轮次:确认 V3 默认生效 + 调参 | G1 | — |
| O3 | AEC:网页已白捡;桌面端随 C1 选型连带定 | G1 | C1 |
| O4 | 断连韧性(B1 重连修复 + 云 API 失败恢复) | G1 | — |
| O5 | TTS 播放完整性(B2,`stop_frame_timeout_s` 修法已验证) | G1 | — |
| O6 | 出错口头告知(ErrorFrame→TTS) | G1 | — |
| O7 | 会话上下文 / 语言模板会话绑定增强 | G1 | — |
| O8 | 音频设备自检/失效检测(桌面端才需要) | G1 | C1 |
