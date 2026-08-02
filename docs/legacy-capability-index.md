# 旧项目历史能力查询清单(voice-translate-v2)

> 用途:2 期开发需要参考旧实现时,按本清单**定点定位**,不再整读旧计划文档 / 旧调研 / 旧记忆。
> 旧库 `~/git/voice-translate-v2` 整库冻结只读,git 全历史即备份;下表路径均相对旧库根。
> 事实源 = `openspec/specs/`(14 个能力 spec,实测沉淀);本清单只做导航。建档 2026-08-02。

## 一、能力 → 旧库位置

| 能力 | spec(openspec/specs/) | 关键代码 | 状态备注 |
|---|---|---|---|
| 实时对话回路(pipecat 版) | voice-interaction | `va/scenarios/voice_chat.py`、`va/scenarios/butler.py` | 自动化绿;真机 R1-R6 当时被声学回环阻挡 uncovered |
| **慢脑双路·原版(成功版)** | voice-interaction R7/R8 | **`vt/processors/assist.py`**(674 行):step1 快脑立即简答 + step2 慢脑**独立线程**(`threading.Thread`,name=`assist-step2`)检索+深度分析→回流,支持 `interrupt()`,①②可同引擎共享连接 | 面试场景实测成功;后被 kb-service-foundation 简化 |
| 慢脑·pipecat 化简化版 | 同上 | `va/processors/assist_answer.py`(单路不双路,T2.6 `eec15b8`)+ 工厂 `va/services/llm_factory.py`(config-driven,`[va.brains]`) | 工厂模式可直接参考 |
| 语义轮次 | voice-interaction R6B-R10 | `va/scenarios/butler.py:507` = 官方 `LocalSmartTurnAnalyzerV3` | **非自研**,官方现成件 |
| 回声隔离/音频环境 | audio-environment | `vt/audio/`(capture/passthrough/playback/devices/selfcheck) | 做成的是**路由隔离**(TTS 不自采,R10-S1 实测);OS 级 AEC spec 原文"二期候选,本期不做" |
| 桌面客户端(Qt) | desktop-client、control-panel | `vt/panel/{app,window,bridge,settings_panel}.py` | 防捕获条款已裁决去除(2026-08-02) |
| 派活/管家编排 | assistant-orchestration | `va/orchestration/console_bridge.py` 等 | 有码;真实环境 uncovered(round4 WAIVED) |
| 桌面感知 | desktop-perception | AT-SPI2 探针代码**已不在现库**(随 screenpipe 退役清理);设计留痕 `openspec/changes/archive/2026-07-23-screenpipe-desktop-integration/research.md` | 仅设计留痕 |
| KB 检索服务 | knowledge-retrieval | `kb_service/`(独立服务) | R5-S3 准确性达标;部分场景当时推迟补测 |
| 同声翻译 | translation-control | `vt/processors/translator.py`、`vt/audio/passthrough.py`、`vt/core/wiring.py` | 实测过 |
| 面试辅助 | interview-assist | `main_interview.py` + `vt/processors/assist.py` + kb;核心测试语料 `tests/fixtures/interview_20260715_2050_corpus.md` | 实测过 |
| 供应商抽象 | provider-abstraction | `vt/providers/registry.py` + `vt/providers/{stt,tts,llm}/` | 四类可插拔 |
| 场景装配/开关矩阵 | scenario-assembly、dual-pipeline-core | `va/scenarios/`(配方式装配) | 陪练=换 prompt/LLM 即此层能力 |
| 契约(user/tenant 维度) | base-session-contract | — | 设计约束,随新契约延续 |

## 二、旧文档处置(备份回收结论)

| 文档 | 处置 |
|---|---|
| `docs/decisions/长期路线规划-三场景装配-20260718.md`(v3) | **已过时退役**——R6-A/B/C 划分与 OpenClaw/Hermes 载体已被 2026-08-01 pipecat 重构转向取代;只查"五、沿革"节 |
| `docs/decisions/贾维斯个人助手-资料输入-20260721.md` | 资料存档,按需查 |
| `docs/decisions/实时语音架构调研-关键问题与方案-20260716.md` | 准确性链条(reranker/quote-first/RRF)结论仍有效,面试辅助迁移时查 |
| `docs/backlog.md`(旧库 B1-B25) | 绑旧架构,**未对账**;触碰对应能力迁移时逐条判"作废/转新账" |
| 旧 `openspec/changes/archive/*` | 历史留痕,按变更 ID 查 |

## 三、旧数据引用清单(调研数据,定点引用不整读)

| 数据 | 位置 | 仍有效的部分 |
|---|---|---|
| **pipecat 官方现成件罗盘**(610 行) | `~/research/2026-07-30-pipecat官方现成件盘点/罗盘.md` | 按节定点查:§2 evals 源码卡 / §3 bus+workers(派活骨架)/ §5 AEC / §6 轮次 / §7 UI 工具(whisker PoC)/ §9 supported-services 全表 / §10 文档站最佳实践页清单 / §11 未关缺口 / §12 架构机理+RTVI 全表 |
| qwen-audio-agent 调研 | `~/research/2026-08-01-qwen-audio-agent调研/` | 派活层判据底稿:Work 交付凭据状态机 + 前台六工具白名单;Electron 桌面壳先例 |
| 底座选型调研 | `~/research/2026-07-24-贾维斯底座选型/` | OpenClaw 已退出运行路径,**仅沿革**,不再作依据 |
| pipecat 官方资料地图 | `docs/official-resources-map.md`(本仓库) | 现行,开发期唯一的官方资料导航 |
