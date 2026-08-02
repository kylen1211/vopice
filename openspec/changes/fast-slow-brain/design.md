# 快慢脑(dual-brain)技术设计

> 对应 PRD: 本变更 `proposal.md`(已批准)  状态: **草稿**  更新: 2026-08-02  级别: **L3**
> 实现总原则(PRD 拍板 21):只用 pipecat 官方原语与组件;官方达不到理想要求不造零件补,接受官方原样行为。
> 全案非官方物两样:①注入模板 prompt ②哨兵过滤谓词 + `SlowBrainState` 的两个布尔(本轮是否产出过要点 / 本轮是否已中止,见 §5.2 —— 各由一条源码证据逼出,非预防性设计)。
> **轮次号整个取消**(2026-08-02 定稿,PRD R7 已同步修订):不自研计数器,也不采用官方 `TurnTrackingObserver` —— **新旧素材的归属不再靠编号表达**,改由"注入前校验 + 上下文时间顺序"承担(§5.2 / §6.1)。演进留痕见 §4-3(两次误判:先误判官方无件,后误判官方件语义等价)。
> **型号事实源唯一为 §6.2 配置表**;其它章节的括注若与之不一致,以 §6.2 为准。

---

## 1. 现状盘点

### 1.1 影响面

| 文件 | 改动性质 | 说明 |
|---|---|---|
| `server/bot.py` | **重装**(单文件,~130 行改动) | STT/TTS 换厂商;管线从单链改双分支 ParallelPipeline;VAD 外置;新增 turn 处理器、Producer/Consumer、哨兵过滤器、`on_pipeline_error` handler |
| `server/prompts.py` | 新增 3 段 | 慢脑 system prompt、快脑双脑规则段(消化素材/哨兵)、注入模板 |
| `server/config.py` | 增删配置项 | 删 `OPENAI_MODEL`/`KOKORO_VOICE_ID`;增 Soniox/ElevenLabs/慢脑 LLM 共 6 项;快脑 `LLM_MODEL` 默认换 `gemini-3.6-flash-low`;快速失败机制沿用 |
| `server/.env` / `.env.example` | 同步 | 同上 |
| `server/tests/test_config.py` | 跟随 | 必需项集合变化 |
| `server/evals/` | 新增 5 个场景 | R1/R3/R4/R5/R7/R8 的行为验收 |
| `server/pyproject.toml` | 依赖增删 | `pipecat-ai[...]` extras:去 `kokoro`/`whisper`,加 `soniox`/`elevenlabs` |
| `client/` | **零改** | R8 面板提示走既有 RTVI error 通道 + `EventsPanel`(§6.5,待人工联测确认) |
| `scripts/check_frozen_repo.sh` | 零改 | R9 沿用 |

### 1.2 可复用(现有直接用或小改后用)

- `config.py` 的"一次收集全部缺失项再报错"快速失败模式 —— 新配置项直接进 `_REQUIRED_ENV_TO_FIELD` 表,零结构改动(`config.py:16-24,71-86`)。
- `judge_factory.py` —— eval judge 走本地网关的构造逃生舱,新 eval 场景直接引用(既有 `evals/r4_knowledge_qa.yaml:11-13` 用法)。
- eval 场景的"首轮空 expect 吸收开场白"套路(`evals/smoke.yaml:12-19` 注释记录了 20260801 实测的 race 根因),新场景一律沿用。
- `prompts.py` 的分段拼装结构(官方段 + 能力边界段 + 语言段),新增段照此追加。

### 1.3 项目约定(方案必须遵循)

- 官方脚手架结构不动,新功能落既有目录(CLAUDE.md 项目纪律);本设计不新增目录、不新增源文件。
- `bot.py` 单文件承载全部管线装配(1 期现状),本期继续,不拆包。
- 注释中文、prompt 英文/中文按用途(`prompts.py` 现状:注释中文、prompt 英文;慢脑/注入模板因面向中文对话用中文)。
- 启动 bot.py / pytest 须带 `NLTK_DISABLE_IMPORT_SECURITY=1`。

### 1.4 相关技术债(本期处置)

| 债 | 出处 | 本期处置 |
|---|---|---|
| B2 TTS 多句卡死/重叠(Kokoro CPU 合成 >3s 触发 `stop_frame_timeout_s` 提前清理) | `docs/backlog.md` B2 | **随 Kokoro 移除而消失**;换 ElevenLabs 后须复验(§8 人工联测 M3),不预设已解决 |
| B1 断开重连失败(客户端 SDK 层) | `docs/backlog.md` B1 | 不动,规避手段仍是刷新页面 |
| 分支 `fix/tts-zh-and-llm-repeat` 未提交的 Kokoro 中文修复(26 行) | git 工作区 | **已按用户 2026-08-02 拍板丢弃**(diff 备份于会话 scratchpad `discarded-kokoro-zh-fix.diff`,项目内零残留) |
| 旧库 B19:`language_hints` 裸传被 `**kwargs` 静默吞掉 | voice-translate-v2 backlog | 本期一律走 `settings=`,并加装配断言(§8 U4) |

### 1.5 Preflight 证据块(实跑输出)

```
$ .venv/bin/python -c "import pipecat,os;print(pipecat.__version__, os.path.dirname(pipecat.__file__))"
2026-08-02 15:00:20 | INFO | ᓚᘏᗢ Pipecat 1.6.0 (Python 3.11.15) ᓚᘏᗢ
venv pipecat 1.6.0 /home/ky/git/voice-agent/server/.venv/lib/python3.11/site-packages/pipecat

$ cd /home/ky/git/pipecat && git describe --tags --abbrev=0 && git log -1 --format='%h %ad' --date=short
v1.6.0
46a1bd9d3 2026-07-28
# ⚠️ clone HEAD 是 v1.6.0 之后的提交,不等于运行版本。承重结论一律以 venv 内 1.6.0 源码为准;
#    本设计引用的 5 个关键文件已逐一 diff 核对为 SAME(producer/consumer/parallel_pipeline/
#    function_filter/worker),故 clone 的 examples 与 tests 可作参照。

$ uv --version                 → uv 0.11.26
$ pipecat --version            → ᓚᘏᗢ Pipecat CLI Version: 1.6.0
$ command -v ollama            → (无输出,未安装;eval judge 走 judge_factory 本地网关,不依赖 ollama)

$ curl -s -H "Authorization: Bearer $LLM_API_KEY" "$LLM_BASE_URL/models"   # 8045 网关可用
{"object":"list","data":[{"id":"claude",...}]}   # 含 gemini-3.6-flash-high / claude-sonnet-4-6 等 78 个模型 ID

$ .venv/bin/python -c "from pipecat.services.soniox.stt import SonioxSTTService; \
                       from pipecat.services.elevenlabs.tts import ElevenLabsTTSService"
(无异常;两个官方 service 类在 1.6.0 venv 内可导入 —— 但对应 extras 尚未装,见 §1.6)

$ .venv/bin/python -c "... dataclasses.fields(SonioxSTTSettings) ..."
SonioxSTTSettings: ['model','extra','language','language_hints','language_hints_strict','context',
                    'enable_speaker_diarization','enable_language_identification',
                    'max_endpoint_delay_ms','endpoint_sensitivity',
                    'endpoint_latency_adjustment_level','client_reference_id']
ElevenLabsTTSSettings: ['model','extra','voice','language','stability','similarity_boost','style',
                        'use_speaker_boost','speed','apply_text_normalization']
VADProcessor.__init__: (self, *, vad_analyzer, speech_activity_period=0.2, audio_idle_timeout=1.0, **kwargs)
UserTurnProcessor.__init__: (self, *, user_turn_strategies=None, user_turn_stop_timeout=5.0, user_idle_timeout=0, **kwargs)

$ ls .venv/.../pipecat/tests/utils.py → 存在(run_test 随包分发,PoC 载体,§15)
```

**证据纪律说明**:上表每个数字均由该行命令直接产出。`SonioxSTTService`/`ElevenLabsTTSService` 目前只证"类可导入"(弱);其运行时行为(真实连接、中文识别率、音色)属**待人工联测**(§8 M 组),本设计不据此写任何"已具备"结论。

### 1.6 环境准备清单(实现第 0 组一次性批量安装)

| 项 | 版本/值 | 安装方式 | 授权 |
|---|---|---|---|
| `pipecat-ai` extras 调整 | 去 `whisper`(删 faster-whisper);去显式 `kokoro`;加 `soniox,elevenlabs`;版本仍 `==1.6.0` | 改 `server/pyproject.toml` 后 `uv sync` | 清单获批即授权,主会话执行 |

**extras 实证(防误删依赖)**:`evals` extra 本身蕴含 `pipecat-ai[kokoro]` 与 `[moonshine]`(`/home/ky/git/pipecat/pyproject.toml` 实读),而 `evals/starter_audio.yaml:26` 正是用 **Kokoro 合成"用户"语音**(eval harness 侧,不是 bot 的 TTS)。故去掉显式 `kokoro` 安全,audio 模式 eval 不受影响 —— **但不得连 `evals` 一起动**,否则 R6-S1 的 audio 场景直接跑不了。另:`soniox` 与 `elevenlabs` 两个 extra 的依赖列表**为空**(服务走内置 websockets/aiohttp),写进 extras 只为可读性,不引入新包。
| `SONIOX_API_KEY` | 真实值 | 从 `~/git/voice-translate-v2/.env` 复制进 `server/.env`(不入 git) | 需用户点头(§10 R6) |
| `ELEVENLABS_API_KEY` | 真实值 | 同上 | 同上 |
| `ELEVENLABS_VOICE_ID` | **待定** | 人工联测 M1 试听后填 | 用户拍板 |

无 sudo / 无系统级安装。`ollama` 不需要(judge 走网关)。

---

## 2. 解决方案映射表

逐条对照 PRD 关键逻辑点。"亲读结论"栏均为 venv 1.6.0 源码实读或实测,非标签臆断。

| # | 逻辑点 | 已验证解法来源 | 亲读结论 | 采用方式 |
|---|---|---|---|---|
| L1 | 恒双脑并行骨架 | pipecat 官方 `examples/features/features-concurrent-llm-evaluation.py`(BSD-2,随框架维护) | 双 LLM 各带独立 `LLMContext` + `LLMContextAggregatorPair`,共享外置 `VADProcessor`+`UserTurnProcessor`,两侧 aggregator 均用 `ExternalUserTurnStrategies()` | **原样采用**(骨架直接照搬,替换服务与 prompt) |
| L2 | 跨分支素材搬运 | `processors/producer_processor.py` + `consumer_processor.py`;官方用例 `tests/test_producer_consumer.py:68` | Producer 按谓词挑帧、transformer 改形、`passthrough=False` 时原帧不下推;Consumer 在另一分支起独立 task 消费队列并 `queue_frame` | **原样采用** |
| L3 | 素材落成快脑上下文消息 | `frames.py:641` `LLMMessagesAppendFrame(messages, run_llm)`;`llm_response_universal.py:802-803,1116-1119` | User aggregator 收到该帧 → `add_messages` 后**消费不下推**;`run_llm=True` 才 `push_context_frame()` 触发本分支 LLM。**PoC-1 实测**:素材只进快脑 context,慢脑 context 干净 | **原样采用** |
| L4 | 慢脑要点逐条切分 | `processors/aggregators/sentence.py` `SentenceAggregator` | 中文标点断句可用,**PoC-4 实测**逐条切出要点(带前导 `\n`,transformer strip) | **原样采用** |
| L5 | 完成标记触发补充 | 同 L3,`run_llm=True` | **PoC-2 S1 实测**:快脑触发 2 次(首答 + 补充),补充落进 context | **原样采用** |
| L6 | 打断中止(R5/R7) | `parallel_pipeline.py:158-166`;`InterruptionFrame` 系统帧 | **PoC-2 S2 实测**:打断帧到达两个分支各 1 次,中止靠框架语义免费获得 | **原样采用** |
| L7 | 慢脑失败静默降级 | `pipeline/worker.py:1151-1152` `on_pipeline_error`;`frames.py:950` `ErrorFrame(fatal=False)` | **PoC-2 S3 实测**:慢脑分支上行 ErrorFrame 只触发 worker warning + 事件,快脑分支照常生成 | **原样采用** |
| L8 | 哨兵过滤(静默) | `processors/filters/function_filter.py` + 一行谓词 | 官方 filters 家族无"整轮丢弃"件;`GatedAggregator` 只缓冲不丢弃(`aggregators/gated.py:18-75` 实读)。**PoC-2 S4 实测**:FunctionFilter + 带状态谓词在逐字符碎片下正确整轮静默 | **官方件 + 自研一行谓词**(自证见下) |
| L9 | 付费 STT | `pipecat/services/soniox/stt.py` `SonioxSTTService`(官方) | 旧库用的正是 Soniox `stt-rt-v5`,且旧库自身 pipecat 化场景已改用该官方类 | **原样采用**(不搬旧库手写 WS 层) |
| L10 | 付费 TTS | `pipecat/services/elevenlabs/tts.py` `ElevenLabsTTSService`(官方) | 官方类含中日文时间戳特判;`eleven_flash_v2_5` 在官方多语白名单内、可显式传 language | **原样采用** |
| L11 | 慢脑 LLM | 复用 1 期 `OpenAILLMService` + 本地 8045 网关 | 网关实测提供 78 个模型;延迟实测见 §13.3 | **原样采用**,型号 `gemini-3-pro`(14.9s,**有意取慢档**验配合;用户 2026-08-02 拍板) |
| L12 | 历史摘要段口子 | `processors/aggregators/llm_context_summarizer.py` | 阈值自动触发,可后续直挂 | **本期不启用**,仅在快脑 context 构成上留位 |
| L13 | 面板系统提示 | 服务端:`rtvi/processor.py:232,549`(ErrorFrame→客户端)+ `rtvi/frames.py:38` `RTVIServerMessageFrame`;客户端:`voice-ui-kit/dist/index.js:6741-6746,6762-6767` | RTVI 默认开启(PipelineWorker);**客户端 EventsPanel 已订阅并渲染 `RTVIEvent.Error` 与 `RTVIEvent.ServerMessage`** —— 服务端到面板整条链路官方齐全 | **原样采用,client 零改**(M2 仅做确认) |
| L15 | 业务事件的自动化断言 | `pipecat/tests/utils.py:123` `run_test`(随包分发);`evals/harness.py:798-866` | eval harness 只认 14 类 RTVI 消息、自定义 `server-message` 落 `case _` 被丢弃 → **业务事件在 eval 体系内无官方断言通道**;官方对内部帧行为的验证方式是 `run_test` 帧级断言 | **原样采用 `run_test` 作主力**;eval 只管端到端可见行为 |
| L14 | ~~轮次标识~~ → **素材归属判定** | `processors/aggregators/llm_context.py:227-279` `LLMContext.messages` / `get_messages()`(官方只读 API) | **需求本身取消**:新旧素材不再靠编号表达。Producer 注入前读慢脑 context 的最后一条 user 消息,与本轮深析所基于的那条比对,不一致即丢弃 → **素材在对话流中的位置忠实反映其归属**,快脑按常规上下文顺序理解即可分辨 | **原样采用官方只读 API**;不自研计数器,也不用 `TurnTrackingObserver`(语义为"对话回合",与所需不符,见 §4-3) |

**自研自证(否定性结论,附完整搜索路径供复核)**

> **举证纪律(本次复核后加,承重)**:"官方无此件"是**否定性**结论,证据强度要求高于肯定性结论——必须**跨层穷举**并列出所搜路径,不得只搜"功能名直觉对应的那个目录"。本节两条原稿各栽一次(L14 只搜 `turns/`、L8 只搜 `processors/filters/`),均由用户凭直觉质疑"官方按道理该有"才暴露(台账 2026-08-02)。

- **L8 哨兵过滤 —— 官方有两条候选壳,均需自写判断逻辑;选 `FunctionFilter`**。
  搜索路径:`processors/filters/` 全 7 件(frame/function/identity/null/wake_check/wake_notifier)+ `processors/aggregators/gated.py` + **`utils/text/`**(`base_text_filter.py` / `markdown_text_filter.py` / `skip_tags_aggregator.py` / `pattern_pair_aggregator.py` / `simple_text_aggregator.py`)+ `services/tts_service.py` 的 `text_filters` 装配点。
  - 排除:`NullFilter` 丢弃**全部**帧不可条件化;`GatedAggregator` 语义是"缓冲后释放"而非丢弃;`FrameFilter` 按帧**类型**过滤,看不到内容;`SkipTagsAggregator` 名似而非——它是"标签内不做句子边界匹配",内容照常输出,**不具备丢弃能力**。
  - **候选 B(原稿漏列)**:`BaseTextFilter` + `TTSService(text_filters=[...])`(`services/tts_service.py:178,296,939,1082` 实读)。接口是 `filter(text) -> str`,语义为**文本改写**,可把 `∅` 改写成空串使 TTS 不发声。
  - **选 A(`FunctionFilter` + 自写谓词)的理由**:两者在"模型完全服从"时等效,但在 §2 盲区 4(模型多说一个字)下**行为分叉** —— 候选 B 只会抹掉 `∅` 并把剩余内容照常朗读,候选 A 是**整轮静默**。R8/哨兵的语义是"这一轮不该说话",A 才是语义对齐的那个。候选 B 另有一处不利:它只作用于 TTS 入口,过滤发生在更下游,对上游可观测性无改善(对面板闪现问题两者同样无解)。
- **L14 轮次标识 —— 需求取消,无需自研也无需官方件**(见上表)。演进有两次误判,均留痕于 §4-3:①原稿据"只搜 `turns/`"判定官方无件 → 错,`observers/turn_tracking_observer.py` 有,且 `PipelineWorker(enable_turn_tracking=True)` 默认已启用;②随即改用该官方件 → 也错,fresh 复验实测证伪:其 `_turn_count` 语义是"用户↔机器人一问一答的**回合**",`turn_tracking_observer.py:144-149` 的 `else` 分支表明**机器人尚未出声时用户再说完一轮不自增**(`run_test` 实测两次用户轮 → `started=[1]`,`final_count=1`),与本设计所需的"第几次用户说完"不同;且它只认 `UserStartedSpeaking`/`BotStartedSpeaking` 帧,text-mode eval 两者皆不产生,turn 会恒为 1 使所有 turn 类断言退化为恒真。**最终结论:整个编号概念取消**——归属由注入前校验 + 上下文时间顺序承担,既不需要官方件也不需要自研件。
  - **教训(已入台账)**:"官方有此件" ≠ "该件语义等于我的语义"。否定性结论被推翻后的反向替换,必须补一次完整的**语义对齐论证**(触发条件/自增条件/取值范围逐条对齐),否则错配比漏搜更贵——漏搜只是少一个选项,错配是把错误当修正写进契约。
- **`SlowBrainState` 余下两个布尔 —— 官方无件,自证成立**(逐项证据见 §5.2 表)。搜索路径:`processors/producer_processor.py` / `consumer_processor.py`、`observers/`(全 4 件)、`pipeline/worker.py` 的内建装配与事件、`frames.py` 的 `ErrorFrame` 传播方向。`on_turn_ended(..., was_interrupted)` **形似可替代 `aborted` 但时序不匹配**,详见 §5.2 表③。

**表末盲区问句 —— 这些解法没覆盖什么?**

1. **慢脑"自身超时"没有官方件,且比初稿判断的更弱**:`OpenAILLMService` 只有 `retry_timeout_secs`+`retry_on_timeout`,语义是"超时后重试一次且不带超时",不是"超时即放弃"(`base_llm.py:146-147,316-329`)。**§6.2 的最终处置是:不设该配置项、不开 retry**。诚实交代残余:`retry_on_timeout=False` 分支直接 `await create(**params)` **不传任何 timeout**(`base_llm.py:327-329`),openai SDK 默认读超时 600s —— 即 R8 的"自身超时"在最坏情况下 10 分钟内没有降级路径。按拍板 21 接受(不造看门狗),记 backlog。
2. **"用户开口"到"慢脑 HTTP 请求真的被取消"之间无框架保证**:打断帧到达慢脑 LLM 处理器已实测(PoC-2 S2),但真实 `OpenAILLMService` 是否即刻断开在途 HTTP 流,属服务实现行为,只能人工联测观察(§8 M4);按拍板 21,观察到什么就是什么,不造取消层。
3. **面板对"深析进行中"无任何提示**:PRD §6 已列为已知限制(面板只提示失败)。用户在等补充的 3-7 秒里没有任何视觉反馈。
4. **哨兵谓词依赖模型服从性**:PoC-3 实测 `gemini-3-flash` 服从(精确输出 `∅`),但无兜底 —— 模型若哪次多说一个字,该轮补充就会被播出去。属"差不多就行"接受范围。

---

## 3. 方案权衡

### 方案 A(**推荐**):ParallelPipeline 双分支 + Producer/Consumer 注入

管线结构见 §5.1。慢脑是管线内的一条真分支,与快脑共享 turn 处理器。

- **Pros**:官方示例原样骨架(L1),打断/生命周期/错误传播全部由框架负责(PoC-2 S2/S3 实测通过);慢脑上下文天然隔离(PoC-1 实测);无自研调度、无线程、无状态机 —— 与拍板 13/16/21 完全一致。
- **Cons**:`bot.py` 装配复杂度上升(VAD 外置 + turn 处理器 + 双 pair);ParallelPipeline 的 `_seen_ids` 集合随会话单调增长(`parallel_pipeline.py:52,175-176`,官方原样,长会话内存缓增)。
- **成本**:bot.py ~130 行改动,零新文件。
- **风险**:低 —— 四项承重机制均已在 venv 内实测(§15)。

### 方案 B:单管线 + 后台 asyncio 任务直调慢脑 API

快脑管线不动,`on_user_turn_stopped` 里 `create_task` 调慢脑 HTTP,回来后 `worker.queue_frames([LLMMessagesAppendFrame(...)])`。

- **Pros**:`bot.py` 改动最小(~50 行),不碰管线结构,1 期回归风险最低。
- **Cons**:**中止要自己写**(代次计数 + task.cancel,即旧库 assist.py 老路);错误要自己接;慢脑上下文要自己维护(没有 aggregator 就没有历史);逐条增量注入要自己解析流式响应。**四项自研,直接违反拍板 16/21"只用官方原语、不造零件"**。
- **实测依据**:方案 A 的这四项在 PoC 中全部由官方件免费提供,方案 B 要重写它们。
- **结论**:**否**。唯一优势(改动小)不敌四处自研的长期成本与纪律冲突。

### 方案 C:多 worker + job(官方 `pipecat.workers`)

慢脑做成独立 worker,经 bus 用 job 调用。

- **Pros**:慢脑可独立扩展,未来 task-dispatch 变更天然同构。
- **Cons**:官方文档明示 multi-worker 用于"live handoff / 并行专家 / 独立 UI worker",本期是**同一轮对话内**的双路生成,属 ParallelPipeline 领地;引入 bus/registry 是重型机器,而 2 期终态(task-dispatch 才是任务域)会把它淘汰到另一个变更去 —— 触发"终态反向约束"红线。
- **结论**:**否**,留给 task-dispatch 变更。

---

## 4. 本方案牺牲了什么

1. **牺牲了"补充一定等得到"**:慢脑 `gemini-3-pro` 实测 14.9s 才出要点,而 R7 规定新一轮输入即中止旧深析 —— 用户若在简答播完后接着说话,该轮深析白跑、补充永不出现。**换来的是**零调度器、零状态机,以及一个**明显可辨的"先快后慢"时间差**(快脑 2.2s vs 慢脑 14.9s),这正是本期唯一要验的"配合"效果所需。**代价**:验收与日常使用都要求用户在简答后**主动保持沉默十几秒**,补充才会出现;这是有意接受的设定(用户 2026-08-02 拍板),不是缺陷,但也意味着本功能目前不适配"连珠炮式"对话节奏。
2. **牺牲了实时性换可观察性**:慢脑本可选 `gemini-3.6-flash-high`(3.2s)让补充几乎无感衔接,但那样快慢两脑几乎同时到达,看不出"先快后慢"。本期**故意取慢档**以便观察配合链路。这是**测试期设定**,不是终态选型 —— 配合验证通过后可随时把 `SLOW_LLM_MODEL` 调回快档(纯 env 改动,零代码)。
3. **非官方物两样,但过程中连栽两次,留痕于此不粉饰**:设计红队逼出两项跨帧状态(慢脑失败时框架仍无条件推 `LLMFullResponseEndFrame`、打断后残片归属),合成 `SlowBrainState`;原稿另把轮次标识判为自研,一度写成"三样"。
   - **误判一(2026-08-02)**:判"轮次标识无官方来源",依据只 grep 了 `turns/` 一个目录 → 实际 `observers/turn_tracking_observer.py` 有,且 `PipelineWorker` 默认已启用,能力在 1 期代码里本就在跑。属"否定性结论举证不足"。
   - **误判二(同日,fresh 复验抓出)**:据此撤销自研、改用官方 `TurnTrackingObserver` → 也错。该件语义是"对话回合"(需机器人出声才计),与所需的"第几次用户说完"不同;且 text-mode eval 下恒为 1,turn 类断言全部退化为恒真。**错配比漏搜更贵**。
   - **最终(用户直接拍板,PRD R7 同步修订)**:编号概念整个取消,归属改由"注入前校验 + 上下文时间顺序"承担。非官方物两样,且**消除了一条模型服从性依赖**(原方案靠提示词让快脑忽略旧编号素材,快脑不听话即失效)。
   - 两次误判已转成 §2 的举证纪律与两条全局台账条目。
4. **牺牲了哨兵符的不可见性**:`∅` 会在 client 对话面板闪现一次(RTVI 在过滤器上游捕获,快脑 LLM 不能进 `ignored_sources`,§6.6)。不会被朗读,但面板上看得见。无官方解,接受。
5. **牺牲了 audio 端到端的自动化覆盖**:R6 逐句分发降级为人工验证(M7),不开 audio eval 场景 —— 本项目 audio 链路从未跑通(`starter_audio.eval.log` 为 ImportError),且每跑一次真实烧 ElevenLabs 额度。换来的是不引入未验证路径。
6. **牺牲了哨兵的可靠性兜底**:模型不服从(多说一个字)时补充会被播出,无二次防线。按"差不多就行"接受。
7. **牺牲了长会话的素材淘汰**:注入的素材永久留在快脑 context(PRD §6 已列已知限制),`LLMContextSummarizer` 本期不启用,长会话 token 单调增长。
8. **牺牲了本地回退**:Whisper/Kokoro 移除后,断网或 Soniox/ElevenLabs 故障 = 语音功能整体不可用,无降级链(用户拍板"费用无忧、不留回退")。

---

## 5. 模块设计

### 5.1 管线结构(唯一承重结构图)

```
transport.input()
  → SonioxSTTService                     [STT, 中文]
  → VADProcessor(SileroVADAnalyzer)      [外置 VAD —— 双 aggregator 必需]
  → UserTurnProcessor()                  [外置 turn 管理 —— 双 aggregator 必需]
  → ParallelPipeline(
      [ ConsumerProcessor,               ← 慢脑素材入口(必须在 user agg 之前)
        fast_pair.user(),
        fast_llm      (LLM_MODEL, 默认 gemini-3.6-flash-low),
        FunctionFilter(sentinel_gate),   ← 哨兵整轮静默
        ElevenLabsTTSService,
        transport.output(),
        fast_pair.assistant() ],         [快脑分支 —— 唯一外部出口]

      [ slow_pair.user(),
        slow_llm      (SLOW_LLM_MODEL, 默认 gemini-3-pro),
        SentenceAggregator(),            ← 要点逐条切分
        ProducerProcessor(passthrough=True),   ← 素材出口(取料,不截流)
        slow_pair.assistant() ],         [慢脑分支 —— 无外部出口]
    )

worker = PipelineWorker(
    pipeline, ...,
    rtvi_observer_params=RTVIObserverParams(
        ignored_sources=[slow_llm, slow_sentence_aggregator, slow_producer],  ← R2 关键之一
        user_llm_enabled=False),                                              ← R2 关键之二(见 5.1.1)
)
```
> 型号以 **§6.2 配置表为唯一事实源**,此图仅标配置项名;图中括注若与 §6.2 不一致,以 §6.2 为准。

### 5.1.1 RTVI 观测隔离(承重,设计红队后补)

**慢脑分支的三个处理器必须进 `ignored_sources`,否则 R2 从根上被打穿。**

源码依据:`RTVIObserver.on_push_frame` 在**任意处理器 push 帧的那一刻**按 `data.source` 捕获(`processors/frame_processor.py:905,917` → `rtvi/observer.py:408-419`),与该帧后续是否被下游丢弃、是否被 `passthrough` 截流**全部无关**。因此不做隔离时:
- 慢脑 LLM 吐出的每个 `LLMTextFrame` 都会被上报为 `bot-llm-text` → **client 对话面板直接显示慢脑原文**(违反 R2 与 PRD §1 角色矩阵"面板不显示慢脑原始产物");
- 慢脑文本还会混进 eval 的 `llm_response`/`response` 事件流(`evals/harness.py:831-845`),使所有 eval 断言错乱。

官方件解法(零自研):`PipelineWorker(rtvi_observer_params=...)`(`pipeline/worker.py:251,413` 实读)接受 `RTVIObserverParams(ignored_sources=list[FrameProcessor])`(`rtvi/observer.py:177,419`)。官方另有同构示例 `examples/features/features-concurrent-llm-rtvi-ignored-sources.py`,管线形态与 §5.1 一致。
**快脑 LLM 不得放进该列表** —— 面板与文本模式 eval 的 `response` 事件都源自它。

**第二条泄漏路径:注入模板会经 `user-llm-text` 上面板(fresh 复验 N5,承重)**
`ignored_sources` 只挡住慢脑分支。但完成标记帧 `run_llm=True` → 快脑 user aggregator `push_context_frame()`(`llm_response_universal.py:1116-1119,487-494`)推出 `LLMContextFrame` → observer `_handle_context`(`rtvi/observer.py:792-818`)取 **`messages[-1]`**,只要 `role == "user"` 就发 `RTVI.UserLLMTextMessage` —— 而此刻 `messages[-1]` **正是注入模板全文**(模板角色固定 `user`,§6.1)。于是面板会显示 `[慢脑深析要点|针对上一个问题|已完成] 以上素材已齐…`,**直接违反 R2-S1 与 PRD 角色矩阵**;更隐蔽的是 harness 没有 `user-llm-text` 的 case(落 `case _: return []`),**eval 抓不到,判据照样全绿**。
处置:`RTVIObserverParams(user_llm_enabled=False)`(默认 `True`,`observer.py:169,464`)。用户自己说的话仍由 `user-transcription` 通道上报(STT 的 `TranscriptionFrame` 走 `observer.py` 另一分支),面板不丢失用户话语。
**不能改用"把 `fast_pair.user()` 塞进 `ignored_sources`"** —— 那会连带屏蔽掉快脑 user aggregator 推出的其它上报。

**结构约束(违反即功能错误,非风格问题)**:
- Consumer **必须**在快脑分支内且在 `fast_pair.user()` 之前 —— 放在 ParallelPipeline 之前的公共段会让慢脑上下文同样被注入并被 `run_llm` 触发,违反 R3 与 R2(源码依据 `llm_response_universal.py:802-803,1116-1119`,PoC-1 实测)。
- `transport.output()` **必须**在快脑分支内(官方示例同构),慢脑分支不得含任何输出件 —— R2 的结构性保证。
- `ProducerProcessor(passthrough=**True**)` —— **设计红队后由 False 翻正**。源码实证:`producer_processor.py:83-88`,命中 filter 且 `passthrough=False` 时帧**只入消费队列、不再 `push_frame`**;而要点句必然命中 filter,于是全部止步于 Producer,`slow_pair.assistant()` 永远收不到文本(`llm_response_universal.py:1497-1498` 的 `_handle_text` 无从触发)→ **慢脑 context 退化成只有 user 消息、零自身历史**,与 §7 声明直接矛盾,第二个深问题起慢脑会重复输出同一批要点。
  改 `True` 后帧继续下推给 assistant aggregator,慢脑历史正常累积;泄漏防线不靠它,而是靠**结构**(慢脑分支无任何输出件)+ **RTVI 隔离**(§5.1.1)双保险。
  注:红队曾建议"把 `slow_pair.assistant()` 前移到 SentenceAggregator 之前"——**该修法错误**,assistant aggregator 会吞掉 `TextFrame`(:1497 无 `push_frame`),前移会让 Producer 收不到任何要点。
- 两个 aggregator pair **必须**用 `ExternalUserTurnStrategies()`,VAD/turn 由公共段统一驱动;沿用 1 期的 `LLMUserAggregatorParams(vad_analyzer=...)` 会让两个 aggregator 各自抢 turn。

### 5.2 模块职责

| 模块 | 职责(一句话) | 边界 |
|---|---|---|
| 快脑分支 | 唯一发言者:应答用户、消化素材、自判补充 | 不知道慢脑存在,只见到上下文里的素材消息 |
| 慢脑分支 | 深析产素材 | 不接触 TTS/transport/面板;产出只经 Producer 出去 |
| `SlowBrainState`(单一小对象,慢脑侧) | 承载两项跨帧状态:①本轮是否已产出过要点 `has_material` ②本轮是否已被中止 `aborted`;另持有本轮深析所基于的用户问题快照 `basis`(**不是编号,是内容/位置基准**,供注入前校验) | 纯数据 + 两个判定,无调度、无状态迁移图(拍板 13 边界内) |
| `sentinel_gate` 谓词 | 本轮首个文本帧命中哨兵 → 整轮静默 | 只看快脑输出流,不知上下文;控制帧一律放行(§6.6) |
| `on_pipeline_error` handler | **按 `frame.processor` 判分支归属**后记日志 | 不做恢复、不做重试 |

**`SlowBrainState` 的两项状态各自为什么必须存在(每项都由一条实测/源码证据逼出来,不是预防性设计)**:

| 状态 | 逼出它的证据 | 不要它会怎样 |
|---|---|---|
| ①本轮深析所基于的用户问题 `basis` | 官方 `LLMContext.messages` 是只读快照,不带"这条素材属于哪个问题"的元信息(`llm_context.py:227-279`);而慢脑产出要点时,用户可能已经问了新问题(慢脑实测 10–50s,§13.3) | 针对旧问题的要点会被注入到**新问题之后**的位置 → 素材在对话流中的位置不再忠实反映归属 → 快脑按顺序理解时被误导,把旧问题的分析当成新问题的背景 |
| ②本轮是否产出过要点 `has_material` | `services/openai/base_llm.py:571-573`:`finally` 块**无论成功/超时/异常都无条件推 `LLMFullResponseEndFrame`**;而失败信号 `ErrorFrame` 走 `push_frame(..., UPSTREAM)`(`frame_processor.py:722`)**反向**上行,根本不经过下游的 Producer | 慢脑调用失败时 Producer 照样发"以上素材已齐"并 `run_llm=True` → 快脑在**零要点**下被触发,凭空多播一段莫名其妙的补充 → **直接击穿 R8-S1"无补充"** |
| ③本轮是否已被中止 `aborted` | §2 盲区问句 2:打断帧到达慢脑已实测(PoC-2 S2),但真实 HTTP 流是否即刻停止**未验证**。**它与 `basis` 校验不重复,补的是后者的时间窗口**:用户开口的**当刻**即广播 `InterruptionFrame`,但新的 user 消息要等 STT + 聚合完成才落进 context(数百毫秒至数秒)。该窗口内 `basis` 校验仍会通过(context 里最后一条 user 消息还是旧的),故需 `aborted` 在打断当刻立即止血。**官方 `on_turn_ended(..., was_interrupted)` 不可替代**:它只在 `_is_bot_speaking=True` 时为真(`turn_tracking_observer.py:133-136`),bot 已说完而慢脑仍在途的场景取 `False`(`:139-142`,子代理实测),语义与 `aborted` 不重合 | 打断后到 STT 落地前的窗口里,旧轮残片仍会被注入到**新问题之前**的位置——位置看似合法,内容却已过期,快脑按顺序理解时被误导 |

**状态迁移落点写死(防实现期各自发挥;2026-08-02 编号方案撤销后重写,全文唯一事实源)**:
- **三项状态的重置点统一为慢脑分支收到 `LLMFullResponseStartFrame`**:`has_material=False`、`aborted=False`,并把当时慢脑 context 的最后一条 `user` 消息记为 `basis`(`LLMContext.get_messages()` 只读取用,`llm_context.py:240-279`)。三者同源同刻,不存在跨源错位问题。
- `has_material` 置真点 = Producer 每产出一条要点注入帧时;
- `aborted` 置真点 = 慢脑分支收到 `InterruptionFrame` 时;
- **注入前校验(R7 唯一落点)**:Producer 每次准备注入一条要点时,重新读慢脑 context 的最后一条 `user` 消息,与 `basis` 比对 —— **不一致即丢弃该要点、不注入**,并打 `stale-drop` 日志。`aborted` 为真时同样丢弃(覆盖打断到 STT 落地之间的窗口,见上表③)。
- Producer 见 `LLMFullResponseEndFrame` 时,**仅当 `has_material and not aborted` 且 `basis` 校验仍通过**才产出完成标记帧(`run_llm=True`);否则只打 `no-material` / `abort` / `stale-drop` 日志,不注入、不触发。
- **慢脑调用失败时,已注入的素材保留在快脑上下文,不做清理**(参照 Talker-Reasoner 复现代码 `reasoner.py` 的降级处理:请求失败保留既有 belief 而非清空)。失败只影响本轮是否发完成标记,不回溯已注入内容。
- **比对键的实现口径**:比对"最后一条 user 消息"的**身份**而非全文相等——实现期取该消息在 `messages` 列表中的位置索引 + 内容哈希二者之一,T3.x 首验时定死并写进用例。**此选择不影响契约语义**(两种实现对"用户是否问了新问题"的判定等价),仅影响实现细节。
- **不做编号、不做计数器**:素材在对话流中的位置(位于其所针对的 user 消息之后、下一条 user 消息之前)即归属证据;快脑按常规上下文顺序理解即可分辨,**不依赖提示词让它忽略任何东西**。

### 5.3 开场白路径(设计红队后补,承重)

**现状**:`server/bot.py:125-133` 的开场白是 `context.add_message(...)` + `worker.queue_frames([LLMRunFrame()])`;官方双 LLM 示例(`features-concurrent-llm-evaluation.py:147-155`)也是**给两个 context 各加一条、只推一个 `LLMRunFrame`,靠 ParallelPipeline 广播同时触发两个 LLM**。

**不处理会怎样**:客户端每次连上,慢脑就白跑一次 `gemini-3-pro`(约 15s);更糟的是 ①开场白轮会占掉一个日志关联序号(`turn=<n>` 仅供日志串联,不进模板、不承载业务语义,见 §6.4),故验收断言一律不硬编码具体数值;②慢脑若没输出 `无`,会在用户还没开口时凭空注入素材并触发一段"补充";③所有 eval 场景的首轮都是"空 `expect` 吸收开场白"(`evals/smoke.yaml:12-19` 记录了 20260801 的 race 根因),这段幽灵补充会被下一轮的 `- event: response` 吃掉 → 新旧场景**集体偶发红**,连带砸掉 R9。

**设计**(最小、无新机制;**fresh 复验 N1 + 实测后重写**):

1. **两个 context 各加一条开场白消息**(照官方示例),但内容不同:
   - 快脑:`{"role": "user", "content": "Start by concisely introducing yourself."}`(沿用 1 期原文,`bot.py:127-129`);
   - 慢脑:`{"role": "user", "content": "(会话开始,用户尚未提问)"}` —— 一条 **no-op user 消息**。
2. 慢脑 system prompt 的"无深析价值只输出 `无`"分支(§6.7①)接住这一轮 → 不注入、不触发补充。
3. `turn` 口径见 §5.2:开场白轮**照常占用一个编号**,断言不硬编码数字。

> **为什么不是"慢脑 context 干脆不加消息"(初稿写法,已推翻)**:实测 —— 给 8045 网关发**只有 system、无任何 user 消息**的请求,返回 **`400 INVALID_ARGUMENT`**(2026-08-02 实跑,见 §15 PoC-6)。那样每次客户端连接都会走 `push_error` → `ErrorFrame(processor=slow_llm)` → **每次连接打一条 `slow-failed`、面板每次弹错**,并使 R8-S1 的 `grep 'slow-failed'` 恒命中 → **故障注入是否生效无法区分,假绿**。这条与 `bot.py:127-129` 记录的"网关拒绝孤立 developer 消息"是同一类网关约束。
>
> **成本**:开场白轮慢脑仍真跑一次,实测 **3.53s 返回 `无`**(§15 PoC-6),不阻塞快脑、不注入、不播报。可接受。

---

## 6. 接口契约

### 6.1 注入模板(定稿,非官方物 ①)

**增量要点帧**(每条一帧,`run_llm=False`):
```
role: "user"
content: "[慢脑深析要点|针对上一个问题|进行中] {point}"
```
**完成标记帧**(每轮**至多**一帧,`run_llm=True`;**发出前提 = `has_material and not aborted` 且 `basis` 校验通过**,判据与理由见 §5.2 —— 慢脑失败时框架仍会推 `LLMFullResponseEndFrame`,无此前提即击穿 R8):
```
role: "user"
content: "[慢脑深析要点|针对上一个问题|已完成] 以上素材已齐。由你决定是否、以及如何融入对话。"
```
- **不带轮次编号**(2026-08-02 定稿,PRD R7 同步修订):素材按时间顺序注入,位于其所针对的 user 消息之后、下一条 user 消息之前,**位置即归属**;由 §5.2 的注入前校验保证该位置忠实可信。原 `问题#{turn}` 字段连同"只消化编号最大的一组"的提示词规则一并删除,理由见 §2 L14 与 §4-3。
- `{point}`:`SentenceAggregator` 切出的单条要点,**strip 后**注入。

**flush 时序约束(源码实证,承重)**:`SentenceAggregator` 只在两种情况 flush —— ①累积文本命中句末模式;②收到 `EndFrame`(**管线结束**)。`LLMFullResponseEndFrame` 走 else 分支**原样透传但不触发 flush**(`aggregators/sentence.py:53-63` 实读)。因此:**慢脑 prompt 必须硬性要求每条要点以中文句号 `。` 结尾**,否则最后一条要点会滞留在聚合器 buffer 里,而由 `LLMFullResponseEndFrame` 触发的完成标记会**先**到达快脑 —— 快脑在素材不全时就被触发,滞留的那条要点直到会话结束才吐出(或串进下一轮)。
残余风险之一:模型偶发不加句号 → 该条要点丢失。
**残余风险之二(fresh 复验 N3,`aborted` 兜不住)**:`SentenceAggregator.process_frame` 只处理 `InterimTranscriptionFrame`/`TextFrame`/`EndFrame` 三类,`InterruptionFrame` 走 else 原样透传、**`self._aggregation` 不清空**(`sentence.py:40-63` 实读)。于是打断时慢脑那半句未完成的要点留在聚合器缓冲里,下一轮首句流进来被拼成 `<旧轮残片><新轮首句。>` 一次性 flush —— 此刻 `LLMFullResponseStartFrame` 已把 `aborted` 与 `basis` 一并复位,Producer 会把这条**混合内容**当新轮要点注入。污染发生在 Producer **上游**的官方组件内部状态里,Producer 不可见,`aborted` 与 `basis` 校验**都**覆盖不到(两者判的是"这条要点属不属于当前问题",而这条要点的**内容本身**跨了两轮)。
影响面:注入位置正确(确在新问题之后)但内容含旧轮残片 → `dual_brain_supersede` 的 judge 判据可能红,该判据是**质量类不阻断 PASS**(§11)。按拍板 21(官方件不改、不造补偿层)接受,记 backlog;
其余:`SentenceAggregator` 输出的是**普通 `TextFrame`**(非 `LLMTextFrame`,见 sentence.py:56),Producer 谓词须按 `TextFrame` 匹配。
- 角色固定 `"user"` —— 依据:`bot.py:127-129` 记录了 8045 网关拒绝孤立 `developer` 消息的实测;本期不冒该风险,`developer` 角色的可用性留待 M5 人工联测,通过后可在后续变更切换。
- 慢脑自判无可深析时输出单字 `无`,Producer 谓词据此**不产出任何注入帧**(R3 后半句)。

### 6.2 配置契约(`server/.env` / `config.py`)

| 环境变量 | 必需 | 默认 | 校准依据 |
|---|---|---|---|
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | 是 | 沿用 1 期 | — |
| `LLM_MODEL`(快脑) | 是 | `gemini-3.6-flash-low` | **实测** 2.18s,3.6-flash 系整体快于现用 `gemini-3-flash`(2.89s),见 §13.3 |
| `SLOW_LLM_MODEL` | 是 | `gemini-3-pro` | **实测耗时在 10–50s 区间随机波动**(2026-08-02 五次取样:14.87 / 10.51 / 50.30 / 13.97s,同一 prompt 同一问题;原稿写的单值 14.87s 是单次取样,**已订正**)。**故意选慢档**:用户 2026-08-02 拍板"用 pro 延缓时间,达到先快后慢的程度",本期唯一要验的就是快慢脑**配合**,明显时间差才看得出配合 |
| ~~`SLOW_LLM_TIMEOUT_S`~~ | — | — | **不设此配置项**(源码实证后撤销,见下) |
| `SONIOX_API_KEY` | 是 | — | 无默认,快速失败 |
| `ELEVENLABS_API_KEY` | 是 | — | 同上 |
| `ELEVENLABS_VOICE_ID` | 是 | 无默认;**实现期先填一个官方多语音色 ID 占位** | M1 试听后替换为最终值。**不得用 `CHANGE_ME_*`** —— `config.py:31-32` 的 `_is_missing` 会把该前缀判为缺失、启动即拒,导致 T2.x 之后到 M1 之前所有 pytest/eval 都跑不起来(fresh 复验第三节 8)。占位值必须是**真实可用**的音色 ID,只是待用户拍板替换 |
| `ELEVENLABS_MODEL` | 是 | `eleven_flash_v2_5` | 官方多语白名单内且可显式传 language(`elevenlabs/tts.py:59` 实读) |
| `STT_PROVIDER` | 否 | `soniox` | §6.3 定案。**有默认值 + 白名单校验,不进必需项** —— 与 1 期 `SCENARIO` 同构(`config.py:60` 实读:`os.getenv("SCENARIO", 默认)` 后校验白名单)。故必需项仍恰为下方 8 项,U1 断言不变 |
| `TTS_PROVIDER` | 否 | `elevenlabs` | 同上 |
| ~~`OPENAI_MODEL`~~ / ~~`KOKORO_VOICE_ID`~~ | — | — | **删除**,同步删 `.env.example` 与 `test_config.py` 断言 |

慢脑复用 `LLM_BASE_URL`/`LLM_API_KEY`(同一网关),不新增 base_url/key 配置项。

**超时:官方达不到,按拍板 21 不造零件补(源码实证)**
`OpenAILLMService` 只提供 `retry_timeout_secs`(默认 `5.0`)+ `retry_on_timeout`(默认 `False`),且语义是"超时后**重试一次、且这次不带超时**"(`services/openai/base_llm.py:146-147,316-323` 实读),**不是**"超时即放弃"。这与 PRD R8 的"自身超时则放弃该轮"语义不符,官方无对应能力。处置:
- **不设 `SLOW_LLM_TIMEOUT_S`**,**不开 `retry_on_timeout`**(保持官方默认 `False`)。慢脑 `gemini-3-pro` 实测 14.9s 远超默认 `retry_timeout_secs=5.0`,一旦误开会在 5s 触发重试 → **同一轮深析被调用两次、费用翻倍、两份要点串流注入**。此项写进实现约束,不是可选项。
- R8 的"超时"路径实际由底层 SDK/网关的连接与读超时兜底,表现为异常 → `ErrorFrame` → 与"失败"同路,验收判据不变(§6.4 `slow-failed` 日志行)。
- **PRD R8 措辞据实收窄**:"慢脑调用失败**或自身超时(API 超时配置项)**"中的括号部分本期无落点。此为设计对 PRD 的**收窄**,不改变 R8-S1/R8-S2 的可验收行为(两条场景都只断言"失败→静默降级"),故不回门一;若用户认为必须有独立超时旋钮,则须回门一改 R8。

### 6.3 服务装配契约:provider 可配置(**已拍板**,用户 2026-08-02)

> **决策:只注册当前在用的那一家**(STT=soniox,TTS=elevenlabs)。备用厂商**不进代码**,只在注册表旁留一段注释说明接口形状——"要换就照这个形状加一行"。
> 已排除项:①`ServiceSwitcher`(运行期切换)—— 用户"只要启动前能换,不需要运行期更换";②预注册多家备用厂商 —— 用户"干嘛注册那么多,没用"。

**需求**:STT/TTS 应当"接口 + 不同实现",换厂商不该到处改。

**pipecat 现状核实(全局源码 grep,2026-08-02)**:

| 层 | 官方提供什么 | 位置 | 对本需求够不够 |
|---|---|---|---|
| 接口抽象 | `STTService.run_stt(audio)` / `TTSService.run_tts(text, context_id)`,全厂商实现同一契约 | `services/stt_service.py:51,294`;`services/tts_service.py:107,487` | **够** —— 换厂商时管线其余部分零改 |
| 生成期 registry | **全厂商**(实测 **27 STT / 32 TTS**)import 路径 + 构造代码模板 + extras 包名 | `cli/registry/service_metadata.py` 的 `SERVICE_CONFIGS` / `IMPORTS`(venv 1.6.0 实读) | **是现成的抄写事实源** —— 但它是 `pipecat init` 的**代码生成**数据,不是运行期工厂 |
| 运行期切换 | `ServiceSwitcher`(ParallelPipeline 子类)+ `ServiceSwitcherStrategyFailover`(非 fatal 错误自动切下一家) | `pipeline/service_switcher.py:158-265` | 过重 —— 要求**候选厂商全部同时构造**(每家 key 都得配齐) |
| 运行期"按名字造 service"工厂 | **不存在** | 全局 grep 零命中(`from_config` 仅 eval harness 自用) | — |
| "一个文件里按 env 切多家"的官方示例 | **不存在** | `~/git/pipecat/examples/voice/` 共 **67 个文件、一家一个**;全 examples grep `STT_PROVIDER\|TTS_PROVIDER\|importlib` **零命中** | 官方范式就是"用哪家写哪家" |

**本设计的处置**:官方在这一层本就没有件(不属于"官方达不到就造零件补"的情形,而是应用装配层的常规写法),写一层**十几行的 provider 映射**放 `bot.py`,构造代码直接照抄上表 registry 那份官方事实源。**注册表内只放当前在用的一家**,备用厂商留注释说明形状、不进代码:

```python
# bot.py —— provider 名 → 构造器。
# 换厂商 = ①这里加一行 ②pyproject 加对应 extras ③改 .env,config.py/tests/管线全不动。
# 构造代码照抄官方事实源:pipecat/cli/registry/service_metadata.py 的 SERVICE_CONFIGS["<name>_stt"]
# (27 家 STT / 32 家 TTS 全在里面,含 import 路径与 extras 包名)。
# 只注册在用的一家:未验证的厂商预注册进来既没 key 也没测过,且 deepgram/azure 这类缺 extras
# 时顶部 import 会启动即崩(§6.3 实测)。要哪家再按上面三步引入。
STT_BUILDERS = {
    "soniox": lambda c: SonioxSTTService(
        api_key=c.stt_api_key,
        settings=SonioxSTTService.Settings(model=c.stt_model, language_hints=[Language.ZH]),
    ),
}
TTS_BUILDERS = {
    "elevenlabs": lambda c: ElevenLabsTTSService(
        api_key=c.tts_api_key,
        settings=ElevenLabsTTSService.Settings(
            voice=c.tts_voice, model=c.tts_model, language=Language.ZH),
    ),
}
stt = STT_BUILDERS[cfg.stt_provider](cfg)
tts = TTS_BUILDERS[cfg.tts_provider](cfg)
```

**为什么不预注册多家备用(实测支撑,2026-08-02)**:注册一家 = `bot.py` 顶部要 import 它的类。当前 venv(7 个 extras)实测:`soniox`/`elevenlabs`/`cartesia`/`assemblyai`/`openai_tts` 不装 extras 即可 import(纯 aiohttp+websockets 实现),但 `deepgram` → `No module named 'deepgram'`、`azure` → `No module named 'azure'`,**启动即崩**。规避要么装齐全部 extras(拖重环境),要么把 import 藏进 builder 体内做惰性 import(多几行、且换来的是一堆没 key 没验证过的死选项)。用户拍板:不做,**用哪家注册哪家,关键位置写清说明、按需引入**。
> 复现该实测须带 `NLTK_DISABLE_IMPORT_SECURITY=1`;漏带会得到 `ImportError: Blocked import of regex ... for security reasons`,那是**环境拦截**不是缺依赖,勿误判为"这家也要装 extras"(台账 2026-08-02)。

**硬约束(防旧库 B19 复现)**:一律走 `settings=`,禁止把 `language_hints`/`voice`/`model` 当裸构造参数传 —— 旧库实测该写法被 `**kwargs` 静默吞掉、无异常无警告,STT 语言绑定完全失效。装配后须断言生效值(§8 U4)。
**provider 白名单**:`config.py` 校验 `STT_PROVIDER`/`TTS_PROVIDER` ∈ 对应 BUILDERS 的键,未知值启动即拒(**沿用 1 期 `SCENARIO` 的白名单而非黑名单模式**,`config.py:58-69`)。
**未来升级路径**:若某天需要"主厂商挂了自动切备用",直接把两个已构造的 service 交给官方 `ServiceSwitcher(strategy_type=ServiceSwitcherStrategyFailover)`,本层映射不必推翻。本期不做(单厂商,且违反"不加乱七八糟"铁律)。

### 6.4 结构化日志行契约(**旁路证据**,不是 eval 断言对象)

> **设计红队修正(承重)**:原稿把日志行写成"eval/验收的唯一观测锚点"是**错的**。
> 源码实证:`evals/scenario.py:24-30` —— eval 场景的 `event:` 只接受 **10 个固定枚举**
> (`user_started_speaking`/`user_stopped_speaking`/`vad_user_*`/`user_transcription`/
> `llm_started`/`response`/`llm_response`/`tts_response`/`function_call`),断言字段只有
> `within_ms`/`text_contains`/`calls`/`eval`/`absent`;harness 只 match RTVI server message
> (`harness.py:771-846`),**bot 的 loguru stdout 从不进入 harness**。把"日志出现 xxx"写进
> YAML 会在加载期直接报未知事件名。
> **归因更正(2026-08-02,查证后推翻红队与本文档初稿的共同误判)**:红队称"拍板 21 砍掉
> 合成 RTVI 观测信号 = 砍掉了唯一能让 eval 看见这些事件的通道",**该归因错误**。
> 实读:`RTVIServerMessageFrame` 确是官方件(`rtvi/frames.py:38`),observer 会把它转成
> `RTVI.ServerMessage` 发给**客户端**(`rtvi/observer.py:550-551`);但 eval harness 的消息
> match 表(`harness.py:798-866`)**没有 `server-message` 分支,落进 `case _: return []` 被
> 静默丢弃**。即:那条通道通向面板,**从来就不通向 eval 断言**。门一砍它没有造成 eval 观测
> 能力的任何损失。
> **真实边界**:业务级事件(dispatch/inject/abort…)在 pipecat eval 体系里**没有**官方断言
> 通道 —— 这是框架边界,不是选型失误。
> **处置(官方分工,不是"塞进日志凑活")**:
> - **主力验收 = 官方 pytest 帧级断言**(`pipecat.tests.utils.run_test`,随包分发)——业务事件
>   本就该在帧层断言,§8.1 的结构类用例与 §15 的 PoC 都建在它上面;
> - **eval 负责端到端用户可见行为**(那 10 个事件),不承担内部事件观测;
> - **日志 = 给人看的旁路佐证**,跑 bot 时 `2>&1 | tee eval-runs/<ts>/bot.log`,gate 记录命令
>   + 时间戳。日志不是验收主力,少一条日志不判 FAIL(判 FAIL 的是帧级断言)。

| 事件 | 日志行(固定前缀,`logger.info`) | 触发点 |
|---|---|---|
| 慢脑派发 | `[dual-brain] dispatch turn=<n>` | 慢脑分支收到 context 开始生成 |
| 素材注入 | `[dual-brain] inject turn=<n> seq=<k> done=false` | Producer 每产出一条要点 |
| 完成标记 | `[dual-brain] inject turn=<n> seq=<k> done=true` | 慢脑响应结束 |
| 无可深析 | `[dual-brain] no-material turn=<n>` | 慢脑输出 `无` |
| 中止 | `[dual-brain] abort turn=<n> reason=interruption` | 打断帧到达慢脑分支 |
| 慢脑失败 | `[dual-brain] slow-failed turn=<n> error=<msg>` | `on_pipeline_error` **且 `frame.processor is slow_llm`** |
| 其它组件失败 | `[dual-brain] pipeline-error src=<processor> error=<msg>` | `on_pipeline_error` 的其余情形 |
| 哨兵静默 | `[dual-brain] sentinel-muted turn=<n>` | 谓词判定整轮静默 |
| **过时丢弃** | `[dual-brain] stale-drop turn=<n> reason=<basis-mismatch\|aborted>` | 注入前校验失败,该要点丢弃(§5.2) |

字段顺序与大小写写死,验收用 grep 匹配 bot.log(旁路,见本节顶部)。

> **`turn=<n>` 的性质(2026-08-02 编号方案撤销后澄清,承重)**:它是**纯日志关联序号**,由慢脑分支每次收到 `LLMFullResponseStartFrame` 自增,**只用于把同一轮的多条日志串起来供人排查**。它**不进注入模板、不进快脑上下文、不承载任何业务语义**——业务上的"素材属于哪个问题"完全由注入位置 + 注入前校验决定(§5.2 / §6.1)。因此:①它不算非官方物(是日志字段,不是机制);②验收断言只用它做"同一轮内多条日志的关联性"校验,**绝不硬编码具体数值**;③即便它错位也不影响对话正确性,只影响日志可读性。

**分支归属是硬要求,不是优化**:`on_pipeline_error` 的 handler 只收到一个 `ErrorFrame`(`pipeline/worker.py:1151-1152`),而 `ErrorFrame` 是全管线共用的上行系统帧 —— STT 断线、ElevenLabs 401/429、快脑网关 500 全走这个口。不按 `frame.processor` 归属就会:ElevenLabs 欠费 → 日志打 `slow-failed`、面板提示"慢脑失败",而真实故障是**用户完全听不到声音**;更糟的是 R8-S1 的验收会在**任何**故障下变绿(假绿)。
官方已备好字段:`ErrorFrame.processor: FrameProcessor | None`(`frames.py:950-967`),零自研。

### 6.5 面板契约(client 零改)

慢脑失败 → `ErrorFrame(fatal=False)` 上行 → `RTVIProcessor` 转发(`rtvi/processor.py:232,549`)→ client `EventsPanel` 显示。

**客户端侧已开箱可用(实读 `voice-ui-kit` 产物,2026-08-02 —— 原稿"未验证、可能要改 client"的顾虑已排除)**:
`client/node_modules/@pipecat-ai/voice-ui-kit/dist/index.js` 的 EventsPanel 已经订阅并渲染两类消息,各渲染成一行带时间戳的事件:
- `:6741-6746` `useRTVIClientEvent(RTVIEvent.Error, …)` → `Error: {...}`
- `:6762-6767` `useRTVIClientEvent(RTVIEvent.ServerMessage, …)` → `Server message: {...}`

**因此 R8「仅面板提示」有完整官方落点,`client/` 保持零改**,不存在"设计降级已批准 SHALL"的问题(设计红队 C6 据此关闭)。

**两条官方通道,都用**:
1. **异常本身**:慢脑 `ErrorFrame(fatal=False)` 上行 → `RTVIProcessor` 自动转发(`rtvi/processor.py:232,549`)→ 面板出现 `Error: …` 行。**零代码**。
2. **优雅提示**(用户 2026-08-02 要求"异常应有一种优雅显示"):`on_pipeline_error` 判定归属为慢脑后,额外 push 一个官方 `RTVIServerMessageFrame(data={"type": "slow-brain-failed", "turn": n})`(`rtvi/frames.py:38`)→ 面板出现可读的一行,而不是让用户直面内部 error JSON。**一行代码,官方帧,不是自造零件。**

M2 联测降级为**确认**(而非探路):看这两行是否如期出现在面板。

### 6.6 哨兵契约(非官方物 ②)

- 哨兵符:`∅`(U+2205),单字符,不出现在正常中文对话里。
- 快脑规则段:无可补充时**只输出该字符**,不得输出任何其他内容。
- 谓词语义:`LLMFullResponseStartFrame` 重置状态 → 本轮**首个** `LLMTextFrame` 若 strip 后以 `∅` 开头则整轮静默,否则整轮放行。
- **控制帧必须放行(设计红队 I-M5)**:`FunctionFilter._should_passthrough_frame` 只自动放行管线生命周期帧(`StartFrame`/`EndFrame`/`CancelFrame`)与 `SystemFrame`(`filters/function_filter.py:57-71`);而 `LLMFullResponseStartFrame`/`LLMFullResponseEndFrame` 是 **`ControlFrame`**(`frames.py:1898,1913`),**生死完全由谓词返回值决定**。谓词若按字面"整轮静默"把它们一并挡下,快脑 assistant aggregator 就收不到 turn 起止钩子(`llm_response_universal.py:1493-1496`),影响后续轮的聚合行为。**谓词只对 `LLMTextFrame` 按状态过滤,其余一律 `return True`。**
- **已知限制(无官方解,记 backlog)**:哨兵符 `∅` 在被 `FunctionFilter` 挡下之前,已被 RTVI observer 在快脑 LLM 的 push 时刻上报为 `bot-llm-text`(§8.0 同源),因此**会在 client 对话面板上闪现一次**。快脑 LLM 不能放进 `ignored_sources`(那样面板就没有对话了),故无官方解;它不会被朗读(TTS 在过滤器下游),按拍板 20/21 接受,M2 顺带观察观感。
- **为何不用官方 `BaseTextFilter`(2026-08-02 复核补,原稿漏列此候选)**:`TTSService(text_filters=[...])` 是官方的第二条壳,接口 `filter(text) -> str` 可把 `∅` 改写成空串。**未采用**,因其语义是"改写文本"而非"这轮不该说话":模型多说一个字时(§2 盲区 4),它会抹掉 `∅` 把剩余内容照常朗读,而本契约要的是**整轮静默**。两者在模型完全服从时等效,分叉只发生在失败路径上——恰是需要防的那条。完整搜索路径与排除理由见 §2 自研自证 L8。
- 实测依据:PoC-2 S4(逐字符碎片下正确)+ PoC-3(真实 `gemini-3-flash` 精确输出 `∅`)。

### 6.7 Prompt 契约(`server/prompts.py`,三段写死)

**① 慢脑 system prompt**(`SLOW_BRAIN_PROMPT`,新增):
```
你是慢脑。对用户的问题做深度分析,产出可供另一个对话助手消化的语义素材要点,
不是给用户看的答案。每条要点一行,以 "- " 开头,最多 4 条,每条不超过 40 字,
**每条必须以句号 。 结尾**。只输出要点本身,不要开场白、不要总结。
若问题无深析价值(寒暄/简单事实),只输出一个字符: 无
```
- "必须以句号结尾"是**承重约束**,依据见 §6.1 flush 时序;不是措辞偏好。
- "只输出 `无`" 承载 R3 后半句(慢脑自判无可深析则不注入)。

**② 快脑双脑规则段**(`DUAL_BRAIN_SECTION`,追加进现有 `SYSTEM_PROMPT` 拼装):
```
上下文中可能出现以 "[慢脑深析要点" 开头的消息:那是后台深析给你的素材,
绝不能转述其原文或提及它的存在,只能自然地融入你自己的话。
这些素材紧跟在它所针对的那个用户问题之后,按对话顺序理解即可。
当你被要求就已回答过的问题做补充时:若确有值得追加的新内容,直接说出补充
(不要重复已说过的);若没有值得补充的,则只输出一个字符 ∅ ,不要输出任何其他内容。
```
- **R7 的落点已移出提示词(2026-08-02 定稿)**:原稿在此处写"只消化编号最大的一组",是 R7 的唯一落点。该规则**已删除**,R7 改由 §5.2 的注入前校验承担 —— 归属是**代码判定**,不再是提示词请求。撤销理由:①原方案依赖模型服从性,快脑不遵守即失效,而 R7 是结构类判据不该建立在模型自觉上;②被打断那轮残留在 context 里的素材,位于**旧问题之后、新问题之前**,位置本身已表明归属,快脑按常规上下文顺序理解即可,无需额外规则。本段保留的那句"这些素材紧跟在它所针对的那个用户问题之后,按对话顺序理解即可"是**说明性**的(帮助模型正确解读),不承载判定责任——即便模型忽略这句,注入位置的正确性也已由代码保证。
- 拼装顺序:`OFFICIAL_SECTION` + `CAPABILITY_BOUNDARY_SECTION` + `LANGUAGE_SECTION` + `DUAL_BRAIN_SECTION`(沿用 `prompts.py` 现有分段拼装结构,不重构)。
- 官方段那句"回复会被朗读,避免 emoji/项目符号"必须保留(AGENTS.md 硬要求),本段不得覆盖它。

**③ 注入模板**:见 §6.1(`INJECT_POINT_TEMPLATE` / `INJECT_DONE_TEMPLATE`)。

**实测依据**:上述①②的等价文本已在 PoC-3 用真实模型跑通四种路径(深析产要点 / 寒暄输出 `无` / 消化素材给补充不泄漏 / 无可补充输出 `∅`),输出样本存 §15。**实现期不得凭感觉改写这三段**;确需改动,按 §8.4 重跑同一问题集比对基线。

---

## 7. 数据模型与数据流

无数据库、无持久化。运行时数据只有两个内存 `LLMContext` 与一个 int 计数器。

```
用户语音 ──STT──> TranscriptionFrame ──VAD/Turn──> ┬─> 快脑 context(user 消息)
                                                    └─> 慢脑 context(user 消息)

慢脑 context ──LLM──> 要点流 ──SentenceAggregator──> 逐条 ──Producer──> 队列
                                                                        │
       快脑 context <──user aggregator 消费<── Consumer <────────────────┘
                          │
                          └─ run_llm=true 时 → 快脑再生成一轮 → 哨兵过滤 → TTS → 用户
```

- **谁产生**:慢脑 LLM;**谁消费**:快脑 user aggregator;**谁持久化**:无人(进程内,断连即失)。
- 慢脑 context **只含**用户输入与慢脑自己的历史,**不含**快脑答案(PRD §5:去重责任在快脑,靠模板软护栏)。
- 快脑 context 构成顺序:`system` → 历史 →(**预留摘要段位**,本期空)→ 本轮 user → assistant → 素材消息…

---

## 8. 测试策略

**本期验收口径(用户 2026-08-02 拍板,凌驾于下方所有分层之上)**:本期**不做质量把控**,整体跑通、流程顺利即可;快慢脑**唯一需要真正测的是"配合"**——快脑先答、慢脑后到、素材被消化成补充这条链路走通。质量类判据(补充内容好不好、音色像不像、识别准不准)一律降为观察项,不作为门三 PASS 的必要条件。下列 A/U/E 三组自动化的作用是**锁住结构不退化**,不是质量门禁。

三层:**A 组** pytest 单元(纯函数/配置)· **U 组** 装配断言(pytest)· **E 组** eval 行为场景 · **M 组** 人工联测(**一次性集中执行,不零散打断用户**)。

### 8.0 观测层事实与判据选型(设计红队 2026-08-02 抓出,承重)

**事实一:过滤器挡不住观测。** `RTVIObserver.on_push_frame` 在**任意处理器 push 帧的那一刻**按 `data.source` 捕获(`frame_processor.py:905,917` → `rtvi/observer.py:408-419`),`LLMTextFrame` 一离开快脑 LLM 就被上报为 `bot-llm-text`;harness 缓冲后在 `bot-llm-stopped` 时发出 `llm_response`/`response`(`harness.py:831-845`)。下游 `FunctionFilter` 丢弃该帧**收不回**已上报的事件。
→ 哨兵轮在文本模式下**照样**产生一个 `response` 事件(内容 `∅`),任何 `absent: true` 式"无第二段"断言在**正确实现下也会判败**。

**事实二:`tts_response` 只在 audio 模态存在**(`scenario.py:38-40`、AGENTS.md §6)。文本模式下它结构性永不出现 → 拿它断言"注入没引发播报"是恒真空判据,零区分力。

**事实三:`absent: true` 只按事件类型匹配,不能与 `text_contains`/`eval`/`calls` 同用**(`scenario.py:63-70`)。

**判据选型结论:全部留在文本模式,不引入 audio 场景。** 理由(项目现状实证):本项目的 gate set 是 `smoke.yaml` + `r4_no_false_completion.yaml` + `r4_knowledge_qa.yaml` 三个**文本模式**场景(README:97-101);脚手架自带的 `starter_text.yaml`/`starter_audio.yaml` **本就不属于本项目 gate**(用官方 Ollama judge,项目不装 —— README:104-107),且 `starter_audio.eval.log` 现存输出是 `ImportError: No module named 'requests'` —— **audio 链路在本机从未跑通过**。在"本期不做质量、只验配合"的口径下,为几条断言去趟一条**未验证**、且每跑一次真实烧 ElevenLabs 额度的路,不划算。
**证据强度诚实标注(fresh 复验 N6 更正)**:`starter_audio.eval.log` 的 `ImportError: No module named 'requests'` 栈顶在**全局 uv tool 环境**(`/home/ky/.local/share/uv/tools/pipecat-ai/...`),而项目 venv 内 `requests`/`kokoro_onnx`/`moonshine_voice` 三个包**都在**。所以准确表述是"**audio 链路在本项目从未被验证跑通过**"(未验证),**不是**"链路已证坏"(已证伪)。本期不开 audio 场景的理由因此只剩"未验证 + 烧额度 + 本期不做质量",不含"它坏了"。

据此,受影响的四条这样落:

| 场景 | 原判据(不可用) | 改后判据(文本模式可行) |
|---|---|---|
| R4-S2 简单问题静默 | (初稿改成 `text_contains: "∅"`,**已推翻**) | **改回 `response` `absent: true`** |
| R3-S1 注入不引发播报 | `tts_response` 不出现 | 注入后一个短窗口内 `response` `absent: true`(`within_ms` 显式设小),证明注入本身没触发生成 |
| R2-S1 无模板泄漏 | judge 判"不含 `∅`" | judge 只判**模板痕迹**(`[慢脑深析要点`/`针对上一个问题`/`已完成`);`∅` 是预期的哨兵,不算泄漏,从判据里剔除 |
| R6-S1 逐句分发 | audio 模式 `tts_response` 计数 | **降级为 M 组人工联测**(M7)——PRD 本就把面板逐句列为人工抽查/已知限制,本期不为它单开 audio 链路 |

**事实一的适用边界(fresh 复验 N2 更正 —— 初稿"任何 absent 断言都会判败"是过度概括)**:
事实一只在**哨兵轮**成立(慢脑产出了要点 → 完成标记触发快脑第二次生成 → 快脑输出 `∅` → 产生第二个 `response`)。
而 R4-S2「简单问题」根本走不到哨兵轮:慢脑 system prompt 对"简单事实/寒暄"输出 `无`(§6.7①,**实测**:`gemini-3-pro` 对"现在几点了?"输出 `无`,3.77s,§15 PoC-6)→ 不注入 → 无完成标记 → **快脑压根不会被第二次触发** → 没有第二个 `response`。
所以 R4-S2 用 `absent: true` 是**正确**的,初稿改成 `text_contains: "∅"` 反而会永远等不到事件、超时判败。同理 R3-S2 / R5-S1 / R8-S1 三处的 `absent` 也成立(那些场景同样没有第二轮)。
**哨兵路径本身**(慢脑有要点 + 快脑判无可补充)难以稳定构造为 eval 场景(纯模型行为窗口),**由 pytest 结构用例 `test_sentinel_round_emits_no_text` 覆盖**,eval 层不强求。

### 8.1 用例骨架清单(每条 PRD 场景 ≥1 条三元组)

| PRD 场景 | 测试文件 | 用例名 | 断言意图 |
|---|---|---|---|
> **判据性质列**:`结构` = 确定性断言,红即 FAIL(门三 PASS 只由这类决定);`质量` = judge/观感类,**观察项,不阻断 PASS**(§8 本期口径);`旁路` = 同一次运行的 `bot.log` grep,需附命令+时间戳(§6.4)。

| R1-S1 | `server/evals/dual_brain_dispatch.yaml` + bot.log | `dual_brain_dispatch` | eval 断言快脑正常应答(结构);**旁路**:同一次运行 `grep '\[dual-brain\] dispatch turn=' bot.log` 出现该轮的行,且与同轮 inject 行 turn 值一致 |
| R1-S1(派生) | `server/tests/test_dual_brain.py` | `test_both_branches_receive_user_turn` | 用 `run_test` 双分支 stub,同一 user turn 后两个 context 各含该 user 消息(穷尽性的结构证明) |
| R2-S1 | `server/evals/dual_brain_no_leak.yaml` | `dual_brain_no_leak` | judge 负向判据:输出不含 `[慢脑深析要点`/`针对上一个问题`/`已完成` 模板痕迹(**质量**,不阻断 PASS);`∅` 不计入泄漏(§8.0)。结构侧由 `test_slow_branch_has_no_output_processor` + §5.1.1 RTVI 隔离断言兜底 |
| R2-S1(派生) | `server/tests/test_dual_brain.py` | `test_slow_branch_has_no_output_processor` | 慢脑分支处理器清单中不含 TTS/transport.output 类型(结构断言,防日后误接) |
| R3-S1 | `server/evals/dual_brain_inject.yaml` + bot.log | `dual_brain_inject_silent` | eval:注入后短窗口内 `response` `absent: true`(`within_ms` 显式设小,证明增量注入未触发生成)(**结构**);**旁路**:`grep 'inject .* done=false' bot.log` 命中 ≥1 |
| R3-S2 | `server/evals/dual_brain_smalltalk.yaml` + bot.log | `dual_brain_smalltalk_no_inject` | eval:寒暄轮整轮仅一个 `response`,第二个 `response` `absent: true`(**结构**);**旁路**:`bot.log` 出现 `no-material`、零 `inject` 行 |
| R3(派生) | `server/tests/test_dual_brain.py` | `test_material_lands_only_in_fast_context` | PoC-1 固化:注入后快脑 context 含素材、慢脑 context 不含(精确条数断言) |
| R4-S1 | `server/evals/dual_brain_supplement.yaml` | `dual_brain_supplement` | 深问题:窗口内出现衔接第二段;judge 失败特征式判据(第二段与首答内容重复即判 no) |
| R4-S2 | `server/evals/dual_brain_supplement.yaml` | `simple_question_silent` | 简单事实问题:整轮仅一个 `response`,其后 `response` `absent: true`(**结构**)。慢脑对这类问题输出 `无`→不注入→快脑不被二次触发,故确无第二个事件(§8.0 边界说明,实测佐证 §15 PoC-6) |
| R4(派生) | `server/tests/test_dual_brain.py` | `test_completion_marker_triggers_one_generation` | PoC-2 S1 固化:`run_llm=True` 使快脑生成次数 1→2(**精确值 2,非 ≥2**) |
| R4(反向/变异) | `server/tests/test_dual_brain.py` | `test_incremental_inject_does_not_trigger` | `run_llm=False` 的注入帧**不得**使生成次数增加(防"任何注入都触发"的短路实现) |
| R5-S1 | `server/evals/dual_brain_interrupt.yaml` + bot.log | `dual_brain_interrupt_abort` | eval:插话后该轮不再出现补充 `response`(`absent`,**结构**);**旁路**:`bot.log` 出现该轮的 `abort … reason=interruption` 行 |
| R5(派生) | `server/tests/test_dual_brain.py` | `test_interruption_reaches_both_branches` | PoC-2 S2 固化:打断帧两分支各收到 1 次 |
| R6-S1 | **M 组人工联测 M7** | — | 人工听:多句回答逐句播出、哨兵轮完全无声。**不开 audio eval 场景**(§8.0 理由);结构侧由 `test_sentinel_round_emits_no_text` 兜底 |
| R6(派生) | `server/tests/test_dual_brain.py` | `test_sentinel_round_emits_no_text` | 哨兵轮零文本帧透出;正常轮全部透出(PoC-2 S4 固化,两向断言) |
| R7-S1 | `server/evals/dual_brain_supersede.yaml` + bot.log | `dual_brain_supersede` | judge 判补充语义只对应第二问(**质量**);**旁路**:第一轮 `abort` 行命中;结构侧由 `test_stale_material_dropped_before_inject` 兜底 |
| R8-S1 | `server/evals/dual_brain_fault.yaml`(**独立 bot 进程**)+ bot.log | `dual_brain_fault_silent` | eval:快脑正常应答且**无第二段**(`absent`,**结构**);**旁路**:`grep 'slow-failed' bot.log` 命中、且**不得**出现 `inject … done=true`;面板提示见 §6.5 待签核项 |
| R8-S2 | 同上场景文件 | `dual_brain_fault_recovery` | 故障轮之后一轮正常问答仍成功(**结构**) |
| R8(派生·防假绿) | `server/tests/test_dual_brain.py` | `test_non_slow_error_not_reported_as_slow_failed` | 构造 `ErrorFrame(processor=<非 slow_llm>)` → handler 打 `pipeline-error` 而非 `slow-failed`(**结构**,防 §6.4 所述假绿) |
| R8(派生·面板) | `server/tests/test_dual_brain.py` | `test_slow_failure_pushes_server_message` | 慢脑失败时 handler push 出 `RTVIServerMessageFrame(data.type=='slow-brain-failed')`(**结构**;面板渲染由 M2 目视确认) |
| R8(派生·防误触发) | `server/tests/test_dual_brain.py` | `test_failed_slow_turn_emits_no_completion_marker` | 慢脑零要点 + `LLMFullResponseEndFrame` → **不产生**完成标记帧、快脑生成次数不变(**结构**,固化 §5.2 表 ② 的 R8 击穿路径) |
| R8(派生) | `server/tests/test_dual_brain.py` | `test_slow_error_does_not_stop_fast_branch` | PoC-2 S3 固化:非 fatal ErrorFrame 后快脑仍生成,且 `fatal is False` |
| R7(派生·注入前校验) | `server/tests/test_dual_brain.py` | `test_stale_material_dropped_before_inject` | **2026-08-02 编号方案撤销后新增,R7 的结构主力**:构造"慢脑在途 → 用户提出新问题 → 慢脑旧轮要点才流出"的时序,断言该要点**零注入**(不进快脑 context)且打出 `stale-drop … reason=basis-mismatch` 日志;反向断言:未换问题时同样的要点**正常注入**(两向,防谓词写死为恒假)(**结构**,固化 §5.2 注入前校验) |
| R7(派生·打断窗口) | `server/tests/test_dual_brain.py` | `test_abort_blocks_inject_before_stt_lands` | 覆盖 `basis` 校验的时间盲区:`InterruptionFrame` 已到但新 user 消息尚未落进 context 时,要点仍须被 `aborted` 拦下(**结构**,固化 §5.2 表③ 的窗口论证) |
| 开场白路径(§5.3) | `server/tests/test_dual_brain.py` | `test_greeting_turn_emits_no_material` | 开场白轮:慢脑收到 no-op user 消息 → 走 `无` 分支 → **零注入帧、零完成标记、零 `slow-failed`**(**结构**;日志关联序号被占用属既定口径,不作断言) |
| R9-S1 | (既有) `evals/{smoke,r4_no_false_completion,r4_knowledge_qa}.yaml` + `tests/` + `scripts/check_frozen_repo.sh` | 三类基线重跑 | 全绿,以本次运行时间戳为证。**基线范围以 README:97-101 的 gate set 为准**:`starter_text.yaml`/`starter_audio.yaml` 用官方 Ollama judge、本项目不装,**本就不在 gate 内**(README:104-107),不因本变更纳入 |

### 8.1.0 文本模式的打断语义(fresh 复验 N4,决定 R3-S1/R5-S1 的场景形态)

**事实**:harness 发送每个 `user:` 文本前硬编码 `run_immediately=True`(`evals/harness.py:1002-1010`)→ `rtvi/processor.py:467-479` 无条件 `interrupt_bot()` → `frame_processor.py:740-745` 广播 `InterruptionFrame`。
**即:文本模式下每一个 user turn 都会中止慢脑分支在途工作并打一条 `abort` 行。**

推论(据此定场景形态,不与之对抗):
- **单轮场景**(问一次、之后不再说话)不受影响 —— 中止发生在慢脑启动**之前**。R4-S1「有补充」必须是这种形态:提问 → 简答 → **不再发任何 user turn** → 等慢脑 ~15s → 补充。
- **多轮场景里每轮开头必然出现 `abort`**,因此 `abort` 行**不能**单独作为"用户插话中止"的证据 —— 它同时是 R7「新轮顶替旧深析」的正常表现。R5-S1 的证据必须是**该轮没有补充**,而非日志里有 `abort`。
- R3-S1 想证明的"增量注入不触发播报"在 eval 时间轴上无法与完成标记触发的补充可靠区分(注入与完成标记在慢脑流式产出末尾相隔极短)。**该判据下沉到帧级 pytest**(`test_incremental_inject_does_not_trigger`,PoC-1 已固化 `run_llm=False` 不触发),eval 只断端到端可见结果。

**R5-S1 场景形态(写死)**:
```yaml
turns:
  - expect: [{ event: response }]              # 吸收开场白(沿用 smoke.yaml:12-19 套路)
  - user: "<深问题>"
    expect: [{ event: response }]              # 快脑简答, t≈2s
  - user: "<无关的简单问题>"                    # 此刻慢脑仍在深析(pro 档 ~15s), 构成"插话"
    expect:
      - event: response                        # 快脑回答插话本身
      - event: response
        absent: true
        within_ms: 70000                       # 覆盖慢脑实测上界 50.3s + 余量; 窗口内不得出现第一问的补充
```
`within_ms` 的依据 = §13.3 实测慢脑耗时区间的**上界**。⚠️ 原稿取 `25000`(按单次 14.87s + 10s 余量),**2026-08-02 复测推翻**:同一问题最坏一次 50.30s,25s 窗口会随机判超时失败。**改为 `within_ms: 70000`**(50s 上界 + 20s 余量);若实现期发现 70s 仍偶发不足,按实测上界再放宽,不得反向压窗口。插话选"无关的简单问题"是为了让它自己也走 `无` 分支(实测:简单事实问题输出 `无`,§15 PoC-6),避免它自己的补充污染窗口。

### 8.1.1 eval 执行约定(设计红队 T-M1)

- **R8 故障场景必须独立起 bot 进程**:R8 要求 `SLOW_LLM_MODEL` 指向无效值,而其余场景需要慢脑真实可用 —— 两者对 env 的要求互斥。`dual_brain_fault.yaml` 走**独立 manifest / 独立 bot 进程**(`pipecat eval suite` 每场景起新 bot),**不与常驻实例共用**;塞进共用进程会导致故障注入无效,或污染同进程内后续场景。
- **每次 eval run 的 bot 输出必须落盘**:`uv run bot.py -t eval 2>&1 | tee eval-runs/<ts>/bot.log`,旁路证据从该文件 grep(§6.4);gate 记录命令 + 时间戳。
- **故障注入值写死(实测,2026-08-02)**:`SLOW_LLM_MODEL=definitely-not-a-real-model-xyz`。网关对未知 model **抛 `InternalServerError: No accounts available with quota for model: …`**,不静默回退到默认模型 —— 故 `OpenAILLMService` 的 `except Exception` 会接住并 `push_error`,R8 的 ErrorFrame 链路成立。**这是 R8-S1/S2 两条结构判据的前提,已验证,不留给实现期试**。
- **证据包组织(fresh 复验第三节 6)**:每个场景一个目录 `eval-runs/<scenario>-<ts>/`,内含 `bot.log`(该场景专属 bot 进程的 tee 输出)+ `run.txt`(eval 命令原文 + 退出码)。R8 因需独立进程,天然自成一个目录。门三收的证据 = 这些目录 + 一份汇总表(场景 → 目录 → 结论)。
- 沿用 1 期约定:每个独立测量点对着**新起的** `bot.py -t eval` 跑(eval transport 全进程共用一个 `LLMContext`,重复跑会累积轮次 —— README:117)。

### 8.2 装配断言(U 组,防旧库 B19 与配置回归)

| # | 用例 | 断言意图 |
|---|---|---|
| U1 | `test_config.py::test_required_env_set_updated` | 必需项恰为新 8 项;`OPENAI_MODEL`/`KOKORO_VOICE_ID` 不再必需 |
| U2 | `test_config.py::test_placeholder_rejected` | `CHANGE_ME_` 前缀值仍被判缺失(沿用 1 期语义) |
| U3 | `test_dual_brain.py::test_pipeline_shape` | 管线装配后:Consumer 在快脑 user aggregator 之前;慢脑分支无输出件 |
| U4 | `test_dual_brain.py::test_stt_tts_settings_take_effect` | 构造后 `stt._settings.language_hints` / `tts._settings.voice` 为期望值(**旧库 B19 就是这里静默失效**) |
| U5 | `test_dual_brain.py::test_rtvi_ignores_slow_branch` | 传给 `PipelineWorker` 的 `rtvi_observer_params.ignored_sources` 恰含慢脑三件(`slow_llm`/句聚合/Producer)且**不含**快脑 LLM(§5.1.1;漏了就是慢脑原文上面板) |
| U6 | `test_dual_brain.py::test_provider_whitelist` | 未知 `STT_PROVIDER`/`TTS_PROVIDER` 启动即拒(沿用 1 期白名单模式) |

### 8.3 人工联测清单(M 组 —— 一次性集中执行)

> 用户明确要求:需要他配合的测试**统一一次跑完**。以下条目在实现完成后一次性联测,不分散打断。

| # | 项 | 谁跑 | 判据 |
|---|---|---|---|
| M1 | ElevenLabs 中文音色试听(我预选 2-3 个候选,同一句中文各合成一遍) | 我合成,用户听后拍板 | 用户选定 `ELEVENLABS_VOICE_ID` |
| M2 | 慢脑失败时面板是否可见提示 | 用户看屏 | 可见→R8 达标;不可见→记 backlog,不改 client |
| M3 | 多句回复播放是否仍重叠/卡死(B2 是否随 Kokoro 移除消失) | 用户听 | 无重叠无卡死 |
| M4 | 真机打断:深析中插话,慢脑 HTTP 是否即刻停(观察日志时序) | 用户说话,我读日志 | `abort` 行出现且该轮无补充 |
| M5 | `developer` 角色注入是否被 8045 网关接受(为后续变更留数据) | 我跑 | 记录结论,本期不改 |
| **M6**(本期**主测项**) | 完整一轮真机对话验"配合":深问题 →(约 2s)快脑简答 →**用户保持沉默约 15s** → 补充自动到来。**联测时同屏 `tail -f bot.log`** | 用户对话 + 我读日志 | 只判链路通不通:补充出现、且不是首答的复读、且不出现模板痕迹。**内容好坏不判**(本期不做质量)。**若补充没出现,先看日志有无 `abort` 行**:有 = 用户在等待期出声(咳嗽/环境噪声)被 VAD 判为开口、本轮被正常中止 → **判为误触发,重跑**,不是缺陷;无 `abort` 才是真缺陷,回本门查装配 |
| M7 | R6 逐句分发人工验证:多句回答是否逐句播出;哨兵轮是否完全无声;面板是否逐句刷新 | 用户听+看 | 逐句播出、哨兵轮无声。(替代原 audio eval 场景,§8.0) |
| M8 | 观察哨兵符 `∅` 在对话面板闪现的观感(§6.6 已知限制) | 用户看 | 记录观感;难以接受则后续换哨兵形态,本期不改 |

### 8.4 行为基线

本变更改动 prompt 与引擎装配,基线须含**真实输出样本**:PoC-3 的四条真实输出(慢脑深析/慢脑寒暄/快脑首答/快脑补充/哨兵轮)已存档于 §15,作为 prompt 改动的对照基线;后续任何 prompt 改动须重跑同一问题集比对。

---

## 9. 兼容、迁移与回滚

- **无数据迁移**(无持久化)。
- **配置不兼容**:`OPENAI_MODEL`/`KOKORO_VOICE_ID` 删除后,旧 `.env` 启动会因缺 4 个新变量而**快速失败并列出全部缺失项**(1 期机制),不会静默半可用。
- **依赖变更**:`pyproject.toml` extras 去 `kokoro,whisper` 加 `soniox,elevenlabs`;本地模型文件不再下载。
- **回滚**:`git revert` 本变更提交 + `uv sync` + 恢复旧 `.env` 两项即可回到 1 期(单文件 bot.py,无外部状态)。
- **旧字段/旧服务消费点核实(实跑 grep,2026-08-02)**:

  | 消费点 | 处置 |
  |---|---|
  | `config.py:22-23` | 删两项,换新 6 项 |
  | `bot.py:14,16,37,39,67-84` | 换服务(import + 构造 + 文档串) |
  | `tests/test_config.py:11-12,32-33,41-42,48-49` | 断言跟随新必需项集合 |
  | `server/.env.example:9-15` | 删两段,补新段 |
  | `README.md:33,35,68-73` | 改服务说明表与中文路径描述 |
  | `prompts.py:32-33`(注释) | 注释里"WhisperSTTService 硬锁 ZH"的理由已过时 —— 改为 Soniox `language_hints=[ZH]`,**否则注释会成为误导后人的假事实** |
  | `pyproject.toml:7` | extras 调整(见 §1.6) |
  | `evals/starter_audio.yaml:26` | **不动** —— 那是 eval harness 的用户侧 Kokoro,与 bot TTS 无关 |
  | `docs/backlog.md` B2 | 待 M3 复验后回写(条目本身不删,记结论) |

  无其他隐藏消费方,旧字段直接删不留桥接。

---

## 10. 风险与缓解(概率 1-3 × 影响 1-3)

| # | 风险 | 概 | 影 | 分 | 缓解 |
|---|---|---|---|---|---|
| R1 | 补充被用户下一句掐掉,配合链路观察不到 | 2 | 3 | 6 | 本期已**有意**用慢档拉开时间差(2.2s vs 14.9s),M6 联测明确要求"简答后保持沉默十几秒";若沉默下仍观察不到补充 → 是真缺陷,回本门查装配。**本项在 M6 通过前不得宣告功能达标**。注:日常连珠炮节奏下补充不可见属已接受设定(§4 牺牲-1),不计入本风险 |
| R2 | ElevenLabs 中文音色不自然,不可用 | 2 | 3 | 6 | M1 多候选试听;必要时换 `eleven_multilingual_v2` 或另选厂商(官方 service 家族齐全) |
| R3 | Soniox 中文识别率不及旧库(官方 service vs 旧库手写 WS 的自愈逻辑差异) | 2 | 3 | 6 | M6 真机对话验证;`settings=` 硬约束 + U4 断言防 B19 复现 |
| R4 | 哨兵不服从导致补充误播 | 2 | 2 | 4 | PoC-3 已验证服从;单字符哨兵降低碎片风险;接受残余(拍板 20) |
| R5 | 双分支装配错位(Consumer 放错段)导致慢脑被注入/被触发 | 2 | 3 | 6 | U3 结构断言 + §5.1 硬约束条款 + PoC-1 已固化为回归用例 |
| R6 | 从旧库复制 API key 时误提交进 git | 1 | 3 | 3 | `.env` 已在 `.gitignore`(1 期既有);提交前 `git diff --cached` 扫描 |
| R7 | 长会话素材累积撑爆上下文 | 2 | 2 | 4 | 已知限制(PRD §6);摘要段口子已留,后续直挂 `LLMContextSummarizer` |
| R8 | `_seen_ids` 单调增长(官方原样) | 1 | 1 | 1 | 官方行为,单会话时长内可忽略,不造补丁(拍板 21) |
| R9 | 漏配 `ignored_sources` → 慢脑原文直接上面板并污染 eval 事件流(R2 从根打穿) | 2 | 3 | 6 | §5.1.1 写死 + U5 断言逐项核对列表内容;设计红队实证,非假设 |
| R10 | 慢脑失败仍发完成标记 → 零要点触发快脑补充(R8 击穿) | 2 | 3 | 6 | §5.2 `has_material` 前提 + `test_failed_slow_turn_emits_no_completion_marker` 固化 |
| R11 | 旁路日志证据未与 eval run 同批留存,门三无法自证 | 2 | 2 | 4 | §6.4 规定 `tee eval-runs/<ts>/bot.log`,gate 记录命令+时间戳;T4.1 任务卡带此步骤 |
| R12 | 开场白轮触发慢脑 → 幽灵补充 + 轮次错位 + 既有场景偶发红 | 2 | 3 | 6 | §5.3 两条处置(只加快脑 context / 慢脑走 `无` 分支)+ `test_greeting_turn_emits_no_material`。**轮次错位一支已消解**:编号概念整个撤销(§2 L14),素材归属改由注入前校验 + 上下文位置承担,开场白轮不再产生任何业务性错位;残留的 `turn=<n>` 只是日志关联序号。原写的第三条处置"`turn` 惰性自增"随之作废 |

**≥9 项**:无。原 R1(补充观察不到)经"有意取慢档 + M6 沉默要求 + `abort` 日志区分误触发"缓解后降为 6 分。

---

## 11. RTM 追踪矩阵

**判据性质**:`结构` = 确定性断言,红即 FAIL;`质量` = judge/观感类,观察项**不阻断 PASS**(§8 本期口径);`旁路` = 同一次运行的 `bot.log` grep,需附命令+时间戳(§6.4)。**门三 PASS 只由"结构"类判据决定。**

| PRD 规则/场景 | 设计落点 | 任务 | 验收方式 | 判据性质 |
|---|---|---|---|---|
| R1 恒双发 / R1-S1 | §5.1 ParallelPipeline 双分支;§6.4 `dispatch` 日志 | T3.1 | `test_both_branches_receive_user_turn` 绿 + `evals/dual_brain_dispatch.yaml` 快脑应答通过;`grep '\[dual-brain\] dispatch turn=' bot.log` 命中 ≥1,且与同轮 inject 行的 turn 值一致 | 结构 + 旁路 |
| R2 快脑唯一发言 / R2-S1 | §5.1 慢脑分支无输出件;**§5.1.1 RTVI 隔离**;§6.1 模板 | T3.2 | `test_slow_branch_has_no_output_processor` + `test_rtvi_ignores_slow_branch`(U5)绿;`evals/dual_brain_no_leak.yaml` judge 判无模板痕迹 | 结构 + 质量 |
| R3 素材注入 / R3-S1 | §6.1 增量帧 `run_llm=False`;§5.1 Producer/Consumer 落位 | T3.3 | `test_material_lands_only_in_fast_context` 绿 + `evals/dual_brain_inject.yaml` 注入后短窗 `response` absent;`grep 'inject … done=false' bot.log` 命中 | 结构 + 旁路 |
| R3 素材注入 / R3-S2 | §6.1 慢脑输出 `无` → 不产帧;§6.4 `no-material` | T3.3 | `evals/dual_brain_smalltalk.yaml` 第二个 `response` absent;`grep 'no-material' bot.log` 命中且零 `inject` 行 | 结构 + 旁路 |
| R4 补充自判 / R4-S1 | §6.1 完成标记 `run_llm=True`(**前提 `has_material and not aborted`**);§6.6 哨兵 | T3.4 | `test_completion_marker_triggers_one_generation` 绿 + `evals/…::dual_brain_supplement` judge 判补充不复读首答 | 结构 + 质量 |
| R4 补充自判 / R4-S2 | 同上(哨兵路径) | T3.4 | `evals/…::simple_question_silent` 第二个 `response` `text_contains: "∅"` + `test_incremental_inject_does_not_trigger` 绿 | 结构 |
| R5 打断中止 / R5-S1 | §5.1 框架打断语义;§5.2 `aborted`;§6.4 `abort` 日志 | T3.5 | `test_interruption_reaches_both_branches` 绿 + `evals/dual_brain_interrupt.yaml` 该轮补充 absent;该轮 `abort … reason=interruption` 行命中;M4 真机观察 | 结构 + 旁路 |
| R6 逐句分发 / R6-S1 | §5.1 TTS 在快脑分支;§6.6 哨兵不送 | T3.6 | `test_sentinel_round_emits_no_text` 绿(结构);逐句播出与面板刷新由 **M7** 人工验(§8.0:本期不开 audio eval 场景) | 结构 + 质量 |
| R7 单深析在途 / R7-S1 | §5.2 注入前校验(`basis`/`aborted`);§6.1 模板不带编号 | T3.5 | `test_stale_material_dropped_before_inject` + `test_abort_blocks_inject_before_stt_lands` 绿 + `evals/dual_brain_supersede.yaml` judge 判补充只对应第二问;第一轮 `abort` 行与 `stale-drop` 行命中 | 结构 + 质量 + 旁路 |
| R8 慢脑失败降级 / R8-S1 | §6.4 分支归属 + `slow-failed`;§5.2 表②;§6.5 两条官方面板通道 | T3.7 | `test_slow_error_does_not_stop_fast_branch` + `test_non_slow_error_not_reported_as_slow_failed` + `test_failed_slow_turn_emits_no_completion_marker` 三绿;`evals/dual_brain_fault.yaml`(独立 bot 进程)无第二段;`test_slow_failure_pushes_server_message`(断言 push 了 `RTVIServerMessageFrame`)绿;面板可见性由 M2 确认 | 结构 |
| R8 慢脑失败降级 / R8-S2 | 同上(非 fatal,管线不停) | T3.7 | `evals/…::dual_brain_fault_recovery`:故障轮之后一轮提问仍产生 `response` 事件且 `text_contains` 判据命中 | 结构 |
| R9 回归保持 / R9-S1 | §9 配置/依赖变更;既有 gate set 不动 | T4.1 | README:97-101 的三个场景 + `pytest` + `check_frozen_repo.sh` 以本次运行时间戳全绿(`starter_*` 本就不在 gate,README:104-107) | 结构 |
| PRD §7-4 STT/TTS 替换 | §6.2 配置;§6.3 provider 映射与装配契约 | T2.1 | `test_stt_tts_settings_take_effect`(U4)+ `test_provider_whitelist`(U6)绿;M1/M3/M6 人工联测 | 结构 + 质量 |
| PRD §7-3 慢脑选型 | §6.2 `SLOW_LLM_MODEL`;§13.3 实测对比 | T2.2 | 配置项存在且默认值 = **`gemini-3-pro`**(`test_config` 断言;型号事实源唯一为 §6.2) | 结构 |
| PRD §7-2 注入模板定稿 | §6.1 模板全文;§6.7 三段 prompt | T3.3 | `test_inject_template_shape` 绿(模板常量形状)+ R2-S1 judge 负向判据 | 结构 + 质量 |
| PRD §7-5 双分支上下文结构 | §5.1 / §5.3 开场白路径 / §7 数据流 | T3.1 | `test_material_lands_only_in_fast_context` + `test_greeting_turn_emits_no_material` 绿 | 结构 |
| PRD §7-1 PoC 清单四项 | §15 PoC 记录(四项已实测) | T1.1 | §15 四项结论已落盘并被对应 pytest 固化(PoC-1→R3 派生、S1→R4 派生、S2→R5 派生、S4→R6 派生) | 结构 |
| PRD §7-6 NFR 本期不设 | 本期无 NFR 目标值 | 无任务 | 不适用:PRD 明示本期不设 NFR 目标值,无验收项(显式声明,非空缺) | 不适用 |

---

## 12. 数据库设计

**不适用** —— 本变更无数据库、无持久化、无 schema。运行时状态仅两个进程内 `LLMContext` 与一个 int 计数器,随会话结束消失(§7)。

## 13. 中间件与基础设施

### 13.1 STT 选型

| 候选 | 数据 | 结论 |
|---|---|---|
| **Soniox `stt-rt-v5`**(官方 `SonioxSTTService`) | 旧库长期在用;pipecat 官方 service;wss 流式;`language_hints=[ZH]` | **采用** |
| 本地 Whisper(1 期现状) | CPU 推理,用户实测"太慢" | **移除**(拍板 22) |
| Deepgram(官方示例默认) | 中文支持弱于 Soniox,且用户无账号 | 否 |

### 13.2 TTS 选型

| 候选 | 数据 | 结论 |
|---|---|---|
| **ElevenLabs `eleven_flash_v2_5`**(官方 `ElevenLabsTTSService`) | 官方多语白名单内、可显式传 language;旧库有账号 | **采用**,音色待 M1 |
| ElevenLabs `eleven_multilingual_v2` | 旧库默认;不接受显式 language;延迟更高 | 备选(M1 不满意时) |
| 本地 Kokoro(1 期现状) | CPU 50-65ms/汉字,长句 TTFB 3.25s,触发 B2 卡死 | **移除**(拍板 22) |

**失效模式与降级链**:两者均无本地回退(用户拍板)。Soniox 断线 → STT 无输入 → 对话不可用;ElevenLabs 429/401 → TTS 静默失败。**本期不建降级链**,失效表现为对话不可用 + 日志,属接受范围。

### 13.3 LLM 选型(实测,2026-08-02,本地 8045 网关)

**快脑 —— 取最快**(同一简答问题,单次调用):

| 模型 | 耗时 | 输出 | 结论 |
|---|---|---|---|
| `gemini-3.6-flash-low` | 2.18s | 123 字 | **采用** —— 档位语义最省思考;与下两档差异 0.1-0.2s 在噪声内,取语义最稳的一档 |
| `gemini-3.6-flash-medium` | 1.94s | 99 字 | 备选(本次实测最快值) |
| `gemini-3.6-flash-high` | 2.05s | 113 字 | 备选 |
| `gemini-3-flash`(1 期现用) | 2.89s | 133 字 | 换掉 —— 3.6-flash 系整体更快 |
| `gemini-3.5-flash-low` / `3.1-flash-lite` | 2.69s / 3.49s | — | 否 |

**慢脑 —— 有意取慢档**(用户拍板:用 pro 延缓时间,做出"先快后慢",本期唯一要验的是配合):

| 模型 | 深析耗时 | 输出 | 结论 |
|---|---|---|---|
| `gemini-3-pro` | **10–50s(波动)** | 168 字 | **采用** —— 与快脑 2.2s 拉开明显时间差,先快后慢清晰可辨。**但波动极大**:同一 prompt 同一问题实测 14.87 / 10.51 / 50.30 / 13.97s,最坏一次 50s。eval 场景的 `within_ms` 须按上界留余量,否则用例随机红(见 §8.1) |
| `gemini-3-pro-high` | 25.19s(21.88s 时另测一次) | 167 字 | 备选(想要更夸张的时间差时换) |
| `gemini-3-pro-low` | 42.10s | 151 字 | 否 —— 等待过长,不利于反复联测 |
| `gemini-3.6-flash-high` | 3.16s | 139 字 4 要点 | 否 —— 太快,与快脑几乎同时到,看不出"先快后慢" |
| `claude-sonnet-4-6` | 6.89s | 177 字 | **排除** —— 用户 2026-08-02:该模型不稳定,本期不用 |
| `gpt-oss-120b-medium` | 400 错误 | — | 网关不可用 |

**结论绑版本**:上表实测于 2026-08-02,经本地 8045 网关(antigravity 供给)。网关模型集会变动,实现期若默认模型不可用,按同一脚本(§15)重测再定。

## 14. 演进规划

- **本期(dual-brain)**:恒双脑 + 数据回流 + 哨兵静默 + STT/TTS 替换。
- **紧邻后续(PRD 已列 YAGNI 首选)**:分段生成续接/句间融入 —— 若 M6 显示"补充总被掐断",这是首要补救方向。
- **已留扩展点**:①快脑 context 的历史摘要段位(直挂 `LLMContextSummarizer`);②`SLOW_LLM_MODEL` 可换型;③慢脑分支可再挂检索/工具而不动快脑。
- **不预留**:任务对象/状态机/调度器(归 task-dispatch 变更);鉴权(暴露公网前的独立立项)。

**给 task-dispatch 的边界声明(设计红队 C11,防下个变更返工)**:本期的 Producer/Consumer 注入通道**生命周期与用户轮绑定 —— 用户开口即被打断语义清空**(R5/R7 正是靠这个免费获得中止能力)。而项目总纲 G3 要求"派活**不中断对话**",派活结果必须在用户持续说话期间存活并稍后送达 —— **语义正相反**。因此:**本期注入通道不适用于跨轮存活的派活结果**,task-dispatch 需要另起一条打断豁免的注入路径,且需注意本期 `ConsumerProcessor` 的落位约束(§5.1:必须在 `fast_pair.user()` 之前)会与之竞争同一位置。

## 15. PoC 验证记录(五步法,venv 1.6.0,2026-08-02)

脚本存于会话 scratchpad(`poc1_injection.py` / `poc2_semantics.py` / `poc3_llm_behavior.py` / PoC-4 内联),均**逐条独立执行**,零 API 的三条与真实网关的一条互不阻塞。

| # | 验证点 | 正向结果 | 负向/边界覆盖 |
|---|---|---|---|
| PoC-1 | 跨分支注入落位 | 素材进快脑 context;`run_llm=False` 时快脑触发数=1(未被注入触发) | 慢脑 context **不含**素材(隔离反证);`passthrough=False` 下游零慢脑原文 |
| PoC-2 S1 | 完成标记触发 | 快脑触发数 1→2,补充落 context | — |
| PoC-2 S2 | 打断跨分支 | 两分支各收到打断 1 次 | — |
| PoC-2 S3 | 慢脑错误隔离 | 上行 ErrorFrame 1 个、`fatal=False`;worker 只 warning | 快脑仍完成生成(反证不被拖垮) |
| PoC-2 S4 | 哨兵谓词 | 正常轮 6 个文本帧全透出 | 哨兵轮 0 帧透出(负向) |
| PoC-3 | 真实模型行为 | 慢脑(当时用 `gemini-3-pro-high`)深问题出 4 要点、21.56s;快脑首答 2.83s、有素材补充 2.17s 且不泄漏模板 | 慢脑寒暄输出 `无`;快脑无可补充轮精确输出 `∅` |
| PoC-5 | 型号延迟对比 | 快脑 7 档 flash / 慢脑 5 档,逐一实测(§13.3) | `gpt-oss-120b-medium` 网关 400(负向:记录为不可用,不进方案) |
| PoC-4 | 中文逐条切分 | `SentenceAggregator` 按中文句号切出独立要点 | 尾部空白帧(strip 处理) |

**版本绑定**:pipecat 1.6.0(venv);慢脑经 8045 网关,验证日期 2026-08-02。实现期开工前比对版本,漂移即复测。

**PoC 未覆盖、由源码实读补齐的承重结论(设计红队 2026-08-02 补,诚实标注强弱)**:

| 结论 | 证据强度 | 依据 |
|---|---|---|
| eval 只能断言 10 个固定事件,读不到日志 | 源码实读(强) | `evals/scenario.py:24-30,42-70`;`harness.py:771-846` |
| RTVI 在过滤器上游按 source 捕获 → 慢脑原文会上面板 | 源码实读(强) | `frame_processor.py:905,917`;`rtvi/observer.py:408-419,177` |
| 慢脑失败时框架仍无条件推 `LLMFullResponseEndFrame` | 源码实读(强) | `services/openai/base_llm.py:571-573`;`frame_processor.py:722`(ErrorFrame 反向上行) |
| `passthrough=False` 会截断慢脑自身历史 | 源码实读(强) | `producer_processor.py:83-88`;`llm_response_universal.py:1497-1498` |
| 客户端 EventsPanel 渲染 Error / ServerMessage | 产物实读(强) | `voice-ui-kit/dist/index.js:6741-6746,6762-6767` |
| eval harness 丢弃自定义 `server-message` | 源码实读(强) | `evals/harness.py:798-866` 的 `case _: return []` |
| `ignored_sources` 能挡住慢脑上报 | **仅 API 可用性(弱)** | `worker.py:251,413` 接受该参数;**行为未实测** → 列入 U5 断言 + M2 观察 |
| 打断后慢脑 HTTP 流是否即刻停止 | **未验证** | 只测到打断帧到达(PoC-2 S2);真实取消行为归 M4 观察,`aborted` 状态是对"未停止"的兜底 |
| audio 模式端到端 | **未验证且本期不验** | `starter_audio.eval.log` 现存 ImportError;R6 改走 M7 人工(§8.0) |

| PoC-7 | R8 故障注入前提 | 网关对无效 model 抛 `InternalServerError`(不静默回退)→ ErrorFrame 链路成立 | **负向即本项本身**:无效/空 model 名两种输入均抛异常 |
| PoC-6 | 开场白轮与静默路径(fresh 复验后补) | 慢脑收到 no-op user 消息 `(会话开始,用户尚未提问)` → **3.53s 输出 `无`**;寒暄 4.09s → `无`;简单事实问题「现在几点了?」3.77s → `无` | **负向**:慢脑 context 只有 system、无任何 user 消息 → 网关返回 **`400 INVALID_ARGUMENT`**(据此推翻 §5.3 初稿的"慢脑不加开场白消息") |

**PoC-3 真实输出基线**(§8.4 对照基线,节选):
- 慢脑·深问题:`- 物理网络故障必发,分区容错(P)是刚需前提,CAP定理本质是C与A的二维抉择。`(共 4 条)
- 慢脑·寒暄:`无`
- 快脑·有素材补充:`补充一点,CAP定理的选择只在发生网络分区时才生效……`(未提及素材来源,未重复首答)
- 快脑·应哨兵轮:`∅`
