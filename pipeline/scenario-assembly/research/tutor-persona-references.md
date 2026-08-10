# 英语陪练人设参考调研

> 调研目的:为 voice-agent「英语陪练」场景模板的教师人设 system prompt 提供参考底稿。
> 载体约束:实时语音对话(STT→LLM→TTS 级联),TTS 朗读输出,人设文案不能用 emoji/列表/markdown 等念不出来的格式;
> 模板机制只换"身份段"文本 + 服务选择,不改管线结构、不加新工具;用户为中文母语者练口语。
> 本文档是参考底稿,不是成品 prompt;最终人设文案由后续实现阶段起草并呈用户确认。
> 检索执行时间:2026-08-10。实践基准:2026 年中(部分来源发布于 2026-03~2026-07)。

---

## 1. 成熟 AI 英语口语陪练产品的人设与策略

覆盖 Speak、ELSA Speak、Loora、Duolingo Max、Call Annie 五款产品的公开资料(官网/官方博客/官方支持文档/第三方评测)。

### 1.1 角色定位

| 产品 | 官方定位表述 | 定位类型 | 来源 |
|---|---|---|---|
| Speak | "speaking partner";自创方法论"Speak Method"(学短语→练到自动化→真实对话中使用) | 教练式(方法论驱动) | [S1][S2] |
| ELSA Speak | "ELSA's AI Coach" / "AI Conversation Coach",强调 expression/naturalness/clarity | 教练式(而非严格教师) | [S3][S4] |
| Loora | "AI English tutor" / "personal AI English coach" / "speaking partner" 混用;博客强调 "judgment-free"(无评判压力) | 陪伴式 | [S5][S6][S7] |
| Duolingo Max | 具名"世界角色"(Lin、Eddy、Lily)分工:对话伙伴 + 课后点评 avatar,而非笼统"AI 老师" | 角色扮演式 + 分工制 | [S8] |
| Call Annie | 第三方评测/学术论文称"AI tutor"/"virtual assistant"/"speaking partner",官网自述文案单薄 | 不明确(第三方转述为主) | [S9][S10][S11] |

**共识**:五款产品中四款明确回避"严格教师"形象,统一采用"陪练伙伴/教练"式定位;唯 Call Annie 因官方资料薄弱无法确证。

### 1.2 纠错时机策略

- ELSA Speak 官方明确声明:反馈在**每句话说完之后**以图标呈现(非语音实时打断),且聚焦 "naturalness, fluency, grammar, vocabulary, and tone",**不只是发音**。[S4]
- Duolingo Max 官方:Roleplay 对话过程中不打断,结束后由另一具名角色统一给出反馈(官方原文未直接使用"先说完再纠错"措辞,是对其机制的归纳)。[S8]
- Speak / Loora / Call Annie:未找到官方对"何时纠错、是否打断"的明确公开声明。

### 1.3 中英文混用策略

**五款指定产品均未找到官方公开材料**说明对话中的中英混用/中文求助机制;ELSA 的翻译功能仅是课后反馈的文字翻译,不等同于对话内中文求助策略。[S4]
同赛道非指定产品 Gliglish 官网明确提供"用母语提问"功能,可作为行业存在此类设计的旁证,但不能代表五款指定产品的立场。[S12]
**结论**:此项无法作为"已核验最佳实践"呈现,人设文案设计中英配比策略时需作为待确认的设计假设,不能声称"参照 XX 产品"。

### 1.4 难度自适应

- ELSA Speak / Speak / Loora:官方表述均停留在"personalized" / "matched to your level" 等笼统营销措辞,未公开具体机制。[S13][S2][S6][S7]
- Duolingo Max:相对具体——Roleplay 开场提示由人类课程设计师撰写,"aligned with where the learner is in their course"(与学习者当前课程进度对齐)。[S8]
- Call Annie:未找到公开的自适应难度机制描述。

---

## 2. 开源与官方渠道的 English tutor system prompt 范本

### 2.1 GitHub 开源仓库(原文摘录)

**`mustvlad/ChatGPT-System-Prompts`**(★1.2k,MIT license,educational 分类)`prompts/educational/language-learning-coach.md`:
> "You are a language learning coach who helps users learn and practice new languages. Offer grammar explanations, vocabulary building exercises, and pronunciation tips. Engage users in conversations to help them improve their listening and speaking skills and gain confidence in using the language."
[S14][S15]

**`ParisNeo/lollms-webui`**(★4,783,活跃维护)"Language tutor" 条目:
> "You are a skilled language tutor who helps users learn and practice a new language. Provide lessons on grammar, vocabulary, pronunciation, and conversational skills to enhance their language proficiency."
[S16]

**`guilhermelbo/language-learning-system`**(小众但结构完整的葡英双语教学项目)`backend/src/infrastructure/llm_service.py`:
> "You are a professional, patient, and encouraging bilingual language tutor for Portuguese (Brazilian) and English learners. Your purpose is to guide and teach students—not merely translate."

其 `[Grammar Correction Rules]` 纠错五步法(逐字摘录):
> "1. Acknowledge their intended meaning (show you understand) 2. Recast: naturally provide the corrected form in your response 3. Name the specific rule violated... 4. Keep explanation brief and encouraging—never shame or criticize 5. If the same error appears twice in one session, explicitly note the pattern and offer a quick 2-3 item drill"

基调约束:
> "Never: condescending, impatient, or making the student feel wrong. Reframe mistakes: as learning opportunities, not failures."
[S17]

**`pkuppens/babblr`**(定位 "Duolingo successor")`TUTOR_PROMPT_TEMPLATE`:
> "You are a friendly and encouraging {language} language tutor helping a {level} level student. ... 4. If the student makes errors, gently model the correct form in your response 5. Ask one engaging follow-up question to continue the conversation 6. Be encouraging, patient, and supportive"

附带 CEFR(A1-C2)分级词汇/句法难度对照表。[S18]

**两种纠错路线对比**(均为可考证源码原文,非推测):
- `guilhermelbo`:显式点名语法规则,给出五步纠错流程 + 重复错误插入微练习。
- `babblr`:隐性重塑(gently model the correct form),不直接指出错误,强制每轮以跟进问题收尾。

### 2.2 Anthropic / OpenAI 官方专项示例

- **Anthropic**:检索官方 Prompt Library(`docs.anthropic.com` / `docs.claude.com` 的 `/resources/prompt-library/library`)可见内容中**未出现** language tutor / language teacher 分类或示例;唯一相关命中是无关的营销链接(面向 K-12 教师的产品方案页,非 prompt 范本)。**未找到 Anthropic 官方专项语言教学 system prompt 示例**(置信中等——基于页面可见文本关键词检索,未做站内全文搜索,存在漏检可能)。[S19]
- **OpenAI**:确认 `openai/openai-cookbook`(★75.2k)官方仓库存在,但未能定位到语言教学专项 notebook,搜索仅返回通用 prompting guide 条目。**未能确认排除**该仓库内是否存在未被搜到的语言教学专项内容(置信低,记为缺口)。[S20]

### 2.3 独立技术博客(工程实践类)

未找到专门以"如何写语言学习 AI system prompt"为主题的独立技术博客文章(区别于营销文案)。该问题改由 2.1 中两个开源仓库的代码内文档(spec/注释)间接回答——这是工程实践的代码化沉淀,而非博客体裁。

---

## 3. 语音场景特有的陪练实践

### 3.1 STT→LLM→TTS 级联架构下"发音纠错"的可行边界

**技术约束已被业界明确讨论**:级联架构下 LLM 只能看到 STT 转写文字,结构性丢失语音本身的信息(声调、口音、连读)。Speak 工程团队原话:
> "the text transcript might look correct...but the audio itself contains information about how they said it"
其应对是**按功能分流架构**:发音反馈/带发音打分的辅导环节改用原生 speech-to-speech(S2S),自由对话/角色扮演环节因"意图重于发音"仍用 cascade。[S21]

学术文献佐证(arXiv:2606.26083,2026-06-24,Together AI/Stanford)在解释为何只测 realtime 系统时写明:
> "A cascaded system cannot act on the voice by construction"
需注意:该论文实验对象是四个 realtime S2S 模型,不是 cascade 系统本身;这句话是论文作者陈述的背景论据,非其实验直接结论。[S22]

**四条可行替代做法**(按证据强度排序):
1. **独立音素级发音评估模型,完全绕开 LLM** —— Azure Speech "Pronunciation Assessment"(逐音素 AccuracyScore)、基于 Kaldi GOP-Speechocean 配方的方案,均为可查证的产品/工程案例。这类方案与对话 LLM 链路并行运行,把发音分数作为独立数据源反馈给用户。(置信高,产品级证据)[S23][S24]
2. **架构上仅对"发音判分"功能切到 S2S,其余仍用 cascade** —— Speak 的混合架构选型是目前查到的最直接、最具体的公开实践。(置信高)[S21]
3. **弱化发音判分、转向语法/句式纠错** —— Talkio AI、LinguaLive 等产品页宣称"实时纠正语法和发音",但均未公开架构细节,不排除背后用的是 S2S 而非纯 cascade。(置信低,未证实技术实现,标记为推理判断)[S25]
4. **让用户复述确认(repeat-back)/提示清晰重复某词** —— 仅查到通用型"ASR 置信度低时让用户复述关键片段"设计原则,**未查到专门针对发音纠正场景讨论该模式**的公开资料。(置信低,推理判断,证据不足)[S26]

**对 voice-agent 项目的直接含义**(推理判断,非查证事实):当前 cascade 架构下,人设文案不应承诺"我会纠正你的发音",应改写为语法/句式/用词层面的纠错承诺;若未来要做真发音纠正需要独立评估模型,不在本次模板范围内。

### 3.2 回合节奏控制

Speak 工程博客明确指出:标准 300–500ms 静音判停的 VAD/turn-detection 阈值对语言学习者会导致两类问题——"单句被切成多个转写碎片"(损伤 ASR 准确率)和"AI 过早打断学习者"(学习者停顿模式系统性不同于母语者)。其应对是按功能分流:需要精确转写的环节用手动 push-to-talk;需要免提体验的环节用理解对话语境的语义级 turn detection 而非纯静音时长。**团队公开承认这仍是未解决的开放问题**。(置信高,官方工程博客明确陈述)[S21]

"AI 简短回应、鼓励用户多说"这一原则**未查到语言陪练场景下的权威公开设计文档**;仅一篇个人开发者博客描述了按"用户停顿>4秒重复出现/频繁问词义/切回母语/回复变短"等信号动态调整难度和话轮的做法(置信低,单一非权威来源)。[S27]

### 3.3 打断/插话(barge-in)在语言学习场景的处理

**未查到专门针对语言学习场景**讨论"说错时该不该立即打断纠正"的公开资料。通用语音 Agent 的 barge-in 处理原则(区分"打断内容是否相关/紧急"决定是否立即响应)可作旁证,但属于类比迁移而非语言学习专用结论。(置信低,推理判断)[S28][S29]

### 3.4 pipecat 官方是否有语言教学参考

`docs.pipecat.ai` 示例分类(Telephony / Local / Web & Mobile / Video Avatar / Distributed / Logging & Analytics / Getting Started / Flows / WebSocket Audio)**不含语言学习类目**;GitHub code search 在 `pipecat-ai/pipecat` 与 `pipecat-ai/pipecat-examples` 两仓库检索 "tutor"、"pronunciation" 均为 **0 命中**。(置信高,负向结论有直接检索证据)[S30]

---

## 4. 提炼:英语教师人设文案要素清单

> 每条给"要写什么" + "为什么"(来源依据),供后续实现阶段起草人设文案时参考;非成品文案。

**1. 角色定位用"陪练伙伴/教练",不用"严格教师"**
依据:Speak"speaking partner"+ 教练方法论[S1][S2],ELSA"AI Conversation Coach"[S3][S4],Loora"judgment-free"陪伴式[S5-S7],开源 `guilhermelbo` prompt 明确"guide and teach—not merely translate"[S17]。5+ 来源一致,证据强度高。

**2. 纠错策略用"复述纠正法"(recast),不逐句打断,不指出每个小错**
依据:ELSA 官方"每句说完后"反馈、聚焦 naturalness/fluency/grammar 而非逐字纠音[S4];Duolingo Max 对话中不打断、结束后统一反馈[S8];开源 `guilhermelbo` 的五步纠错法(先共情理解→自然复述纠正形式→点名规则→简短鼓励不羞辱→重复错误插微练习)[S17];`babblr` 的隐性重塑"gently model the correct form"[S18]。两种开源实现路线(显式点名 vs 隐性重塑)可任选其一或折中,均有源码级证据支持。

**3. "发音纠正"承诺要改写为语法/句式纠错,不承诺纠音准确度**
依据(强推理判断 + 间接产品证据):voice-agent 当前是 STT→LLM→TTS cascade 架构,LLM 结构性看不到原始音频[S21][S22];Speak 工程实践是把真发音判分挪到独立 S2S/独立音素模型,不经过对话 LLM[S21][S23][S24]。人设文案若写"我会帮你纠正发音"会作出技术上兑现不了的承诺,应改写为"帮你把句子说得更准确、更地道"一类语法/表达层面的措辞。

**4. 中英语言配比策略需自行设计,标注为待确认假设**
依据:五款主流产品均未公开中英混用机制[S4];仅非指定产品 Gliglish 的"母语提问"功能作为行业旁证[S12]。不能声称"参照 XX 产品的中英策略",实现阶段应把配比规则作为设计假设呈用户确认。

**5. 回合要短、避免固定长静音判停的粗暴打断,但打断策略本身证据薄弱**
依据:Speak 官方明确指出学习者语音停顿模式系统性不同于母语者,标准 300-500ms VAD 阈值会导致断句碎片化或过早打断,团队仍在迭代[S21]。但"AI 应简短回应""说错是否该立即打断"两点均缺乏语言学习专项权威依据[S27][S28][S29],仅供参考,不要当作成熟共识写入文案措辞。

---

## 检索局限(汇总)

- Call Annie 官网自述薄弱,相关结论主要靠第三方评测转述,置信降级。
- 中英混用策略、"AI 简短回应"、"打断策略"三项在语言学习专项场景下证据均薄弱或缺失,已在正文逐条标注置信度。
- OpenAI cookbook 是否存在语言教学专项示例未能完全排除(未做仓库全量关键词核对)。
- 未做中文语料检索(国内语伴 App/工程博客的一手资料),可能遗漏国内产品的公开实践。
- 未做浏览器交互抓取,各产品博客/帮助中心可能有更深层未逐一抓取的分页内容。

---

## 已核验事实

逐条列出可复核的结论,标注来源与核验方式(区分官方一手资料 vs 第三方转述 vs 推理判断)。

1. **结论**:Speak 官网及 OpenAI 官方专访将其 AI 定位为 "speaking partner",并自创"Speak Method"教练方法论。
   **来源**:https://www.speak.com ;https://openai.com/index/speak-connor-zwick
   **核验方式**:官网抓取 + OpenAI 官方专访原文比对(两个独立一手来源互证)。

2. **结论**:ELSA Speak 官方支持文档明确说明实时反馈在"每句话说完后"以图标呈现(非语音打断),聚焦 naturalness/fluency/grammar/vocabulary/tone,不只是发音。
   **来源**:https://elsanow.freshdesk.com/en/support/solutions/articles/31000177727-real-time-feedback-for-ai-conversations
   **核验方式**:firecrawl 抓取官方支持文档全文,直接引用原文。

3. **结论**:Loora 官网与 App Store 页面明确使用 "judgment-free" 陪伴式定位表述。
   **来源**:https://www.loora.com ;Google Play(com.loora.app)
   **核验方式**:官网 + 应用商店页面抓取,两处独立表述互证。

4. **结论**:Duolingo Max 官方博客(2023-03-14)明确 Roleplay 采用对话中不打断、结束后由具名角色统一反馈的机制,开场提示由课程设计师撰写并对齐学习者课程进度。
   **来源**:https://blog.duolingo.com/duolingo-max
   **核验方式**:firecrawl 抓取官方博客全文,直接引用原文。

5. **结论**:GitHub 仓库 `mustvlad/ChatGPT-System-Prompts`(★1.2k,MIT)在 educational 分类下的 `language-learning-coach.md` 原文已核实并全文摘录。
   **来源**:https://raw.githubusercontent.com/mustvlad/ChatGPT-System-Prompts/main/prompts/educational/language-learning-coach.md
   **核验方式**:直接读取 GitHub raw 文件原文(非转述)。

6. **结论**:GitHub 仓库 `guilhermelbo/language-learning-system` 的 `llm_service.py` 中 `SYSTEM_PROMPT` 与 `[Grammar Correction Rules]` 五步纠错法原文已核实。
   **来源**:`repos/guilhermelbo/language-learning-system/contents/backend/src/infrastructure/llm_service.py`
   **核验方式**:`gh api` 读取仓库 raw 文件原文。

7. **结论**:GitHub 仓库 `pkuppens/babblr` 的 `TUTOR_PROMPT_TEMPLATE`(含 CEFR A1-C2 分级)原文已核实。
   **来源**:`repos/pkuppens/babblr/contents/backend/app/services/llm/providers/ollama.py`
   **核验方式**:`gh api` 读取仓库 raw 文件原文。

8. **结论**:Anthropic 官方 Prompt Library 页面未见 language tutor 专项分类或示例。
   **来源**:https://docs.anthropic.com/en/resources/prompt-library/library
   **核验方式**:页面抓取 + 关键词核对;**局限**:未做站内全文搜索,置信中等,不排除漏检。

9. **结论**:GitHub code search 在 `pipecat-ai/pipecat` 与 `pipecat-ai/pipecat-examples` 两仓库检索 "tutor"、"pronunciation" 均为 0 命中,pipecat 官方示例分类不含语言学习类目。
   **来源**:`gh api search/code -f q="tutor+repo:pipecat-ai/pipecat-examples"` 等命令;docs.pipecat.ai 示例总览页
   **核验方式**:GitHub Code Search API 直接查询,负向结论有直接证据支持。

10. **结论**:Speak 工程博客明确说明 STT→LLM→TTS 级联架构无法把发音特征传给 LLM,发音判分类环节改用独立 S2S 而非 cascade。
    **来源**:https://www.speak.com/blog/building-speaks-voice-agent-platform
    **核验方式**:firecrawl 抓取工程博客全文,直接引用原文。

11. **结论**:arXiv:2606.26083(2026-06-24,Together AI/Stanford)陈述"级联系统在结构上无法处理语音本身"。
    **来源**:https://arxiv.org/html/2606.26083v1
    **核验方式**:firecrawl 抓取论文全文;**局限**:该陈述是论文作者的背景论据,论文实验对象是 realtime S2S 模型而非 cascade 系统本身,不可外推为该论文对 cascade 系统的实测结论。

12. **结论**:Azure AI Speech 官方文档确认 "Pronunciation Assessment" 功能提供音素级 AccuracyScore,是独立于对话 LLM 的发音评估方案。
    **来源**:https://github.com/MicrosoftDocs/azure-ai-docs/blob/main/articles/ai-services/speech-service/how-to-pronunciation-assessment.md
    **核验方式**:官方文档原文核对。

13. **结论**:Speak 工程博客明确指出标准 300-500ms 静音 VAD 阈值对语言学习者造成断句碎片化与过早打断问题,团队公开承认该问题仍是未解难题。
    **来源**:https://www.speak.com/blog/building-speaks-voice-agent-platform
    **核验方式**:firecrawl 抓取工程博客全文,直接引用原文(与第 10 条同源不同段落)。

---

## 来源清单(合并编号)

| 编号 | URL / 出处 | 标题 | 检索时间 |
|---|---|---|---|
| S1 | https://www.speak.com | Speak 官网 | 2026-08-10 |
| S2 | https://openai.com/index/speak-connor-zwick | Speak is personalizing language learning with AI(OpenAI 官方专访) | 2026-08-10 |
| S3 | https://elsaspeak.com/en | ELSA Speak 官网 | 2026-08-10 |
| S4 | https://elsanow.freshdesk.com/en/support/solutions/articles/31000177727-real-time-feedback-for-ai-conversations | Real-Time Feedback for AI Conversations(ELSA 官方支持文档) | 2026-08-10 |
| S5 | https://www.loora.com | Loora 官网 | 2026-08-10 |
| S6 | Google Play: com.loora.app | Loora 官方 App 页 | 2026-08-10 |
| S7 | https://www.loora.com/learn/conversational-english/daily-english-speaking-practice | Loora 官方博客 | 2026-08-10 |
| S8 | https://blog.duolingo.com/duolingo-max | Introducing Duolingo Max(官方博客 2023-03-14) | 2026-08-10 |
| S9 | https://www.tooljunction.io/ai-tools/call-annie | Call Annie Review(第三方评测) | 2026-08-10 |
| S10 | https://oh-yeah-sarah.medium.com/what-happened-to-the-call-annie-app-972a9cc20d6e | 第三方 Medium 文章 | 2026-08-10 |
| S11 | https://www.researchgate.net/publication/377191075 | Using Call Annie as a GenAI Speaking Partner(学术论文摘要) | 2026-08-10 |
| S12 | https://gliglish.com | Gliglish 官网(旁证,非指定产品) | 2026-08-10 |
| S13 | https://elsaspeak.com/en/efficacy | ELSA Efficacy 页 | 2026-08-10 |
| S14 | https://github.com/mustvlad/ChatGPT-System-Prompts | GitHub repo(★1.2k,MIT) | 2026-08-10 |
| S15 | https://raw.githubusercontent.com/mustvlad/ChatGPT-System-Prompts/main/prompts/educational/language-learning-coach.md | 原始文件 | 2026-08-10 |
| S16 | GitHub code search: ParisNeo/lollms-webui(★4,783) | Language tutor prompt 条目 | 2026-08-10 |
| S17 | repos/guilhermelbo/language-learning-system/.../llm_service.py | GitHub 原始文件 | 2026-08-10 |
| S18 | repos/pkuppens/babblr/.../ollama.py | GitHub 原始文件 | 2026-08-10 |
| S19 | https://docs.anthropic.com/en/resources/prompt-library/library | Anthropic 官方 Prompt Library | 2026-08-10 |
| S20 | github.com/openai/openai-cookbook(★75.2k) | OpenAI 官方 cookbook(存在性核验) | 2026-08-10 |
| S21 | https://www.speak.com/blog/building-speaks-voice-agent-platform | Building Speak's Voice Agent Platform(2026-03-24) | 2026-08-10 |
| S22 | https://arxiv.org/html/2606.26083v1 | Real-Time Voice AI Hears but Does Not Listen(2026-06-24) | 2026-08-10 |
| S23 | MicrosoftDocs/azure-ai-docs: how-to-pronunciation-assessment.md | Azure Pronunciation Assessment 官方文档 | 2026-08-10 |
| S24 | https://rudderanalytics.com/case-studies/phoneme-level-pronunciation-assessment-for-a-major-language-learning-platform | Rudder Analytics 案例 | 2026-08-10 |
| S25 | https://www.lingualive.ai ;https://www.talkio.ai | LinguaLive / Talkio AI 产品官网 | 2026-08-10 |
| S26 | https://orvera.ai/blog/ai-voice-agent-interruption-handling | AI Voice Agent Interruption Handling Guide(Orvera) | 2026-08-10 |
| S27 | https://www.vladsnewsletter.com/p/i-built-a-ai-language-tutor-app-with | 个人开发者博客 | 2026-08-10 |
| S28 | https://hamming.ai/resources/voice-agent-interruption-handling-runbook | Voice Agent Interruption Handling(Hamming AI) | 2026-08-10 |
| S29 | https://futureagi.com/blog/voice-ai-barge-in-turn-taking-2026 | Voice AI Barge-In and Turn-Taking 2026 Guide(FutureAGI) | 2026-08-10 |
| S30 | GitHub code search: pipecat-ai/pipecat, pipecat-ai/pipecat-examples;docs.pipecat.ai 示例总览页 | pipecat 官方仓库/文档 | 2026-08-10 |

---

## 检索执行说明

- 检索执行时间:2026-08-10。实践基准年份:2026(部分一手来源发布于 2026-03~2026-07)。
- 三路并行检索,预算 30/40(中等档封顶);实际调用:商业产品人设路 10/10、开源 prompt 范本路 11/10(超 1 次,已在该路 GAPS 说明原因)、语音场景实践路 10/10,合计 31/30。
- tavily 月度信用已用 71%(710/1000,余 290),本次检索避免使用 `tvly research`(单次约耗 350-400 信用),全部改用常规 tavily-search + firecrawl,不影响本报告结论。
- 本报告与同主题近期报告无重叠(kickoff 检索的 90 天 INDEX 中无"英语陪练/tutor 人设"相关条目,全新调研,非增量)。
