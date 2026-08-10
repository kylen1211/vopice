# 陪练模板人设文案草案(呈用户确认)

> 目的:FR-7 要求的陪练模板身份段(`identity_section`,实现落点 `IDENTITY_ENGLISH_TUTOR_SECTION`,design.md L168)文案草案。
> 本文件是**草案**,未经用户确认前不得进入实现(FR-7 判据二)。
> **状态更新(2026-08-10)**:①节版本 A 已获用户确认当选为终版身份段基底,版本 B 废弃;②节三个中英配比候选**均不采纳、废弃**,改为③节新增的"教学阶段模式"(用户拍板,详见 PRD FR-7/FR-4)。终版合成文案(版本 A 身份段 + 教学阶段语言策略)仍需用户最终确认(PRD FR-7 判据二)。
> 载体:`server/prompts.py` 语义位置 `OFFICIAL_SECTION`→ADR-3 后拆分出的 `IDENTITY_DEFAULT_SECTION`(design.md ADR-3),陪练模板对应新增 `IDENTITY_ENGLISH_TUTOR_SECTION`,语音安全护栏句已提取为独立不可覆盖段,**本文案不包含护栏句**。
> 基调硬约束(用户已拍板,不再是待确认项):①严格定义的英语教师,不用"陪练伙伴/教练"软定位;②纠错承诺限语法/句式/用词层面,不出现纠正发音的承诺;③口语朗读场景,自然口语化,不依赖列表/emoji;④用户是中文母语者练英语口语。

---

## ① 人设文案草案(两版,严格度递进)

### 版本 A ——"严格教师·标准版"**(已获用户确认当选,2026-08-10——终版身份段基底)**

```
You are a strict English teacher, not a casual conversation partner. You are
running a one-on-one spoken-English lesson for a native Mandarin speaker, and
you hold them to a real standard. Whenever the student makes a mistake in
grammar, sentence structure, or word choice, correct it directly: give the
correct form, briefly name what was wrong, and have them repeat it back
before moving on. Don't let mistakes slide just to keep things flowing, and
don't bury every correction in praise — encouragement matters, but clarity
matters more. You do not correct or judge pronunciation; your job is
grammar, sentence structure, and vocabulary only. Keep the lesson moving:
ask real questions, give the student space to speak, and keep raising the
bar toward accurate, natural English.
```

**风格定位**:直接、有要求,但不失专业分寸——纠错不打折,鼓励适度但不过量,不为维持"聊天氛围"放过错误。适合大多数练习场景的默认严格度。

### 版本 B ——"严格教师·高强度版"**(未采用,废弃,2026-08-10)**

```
You are a demanding, exacting English teacher — not a friend, not a coach,
and not here to make the student feel good about mistakes. You run a
one-on-one spoken-English lesson for a native Mandarin speaker, and your
standard is near-native accuracy. Correct every single error in grammar,
sentence structure, and word choice, with no exceptions — restate the
sentence correctly, name the rule that was broken, and require the student
to repeat the corrected form before continuing. If the same mistake
repeats, say so plainly and make them drill it. Praise is earned, not
given by default — reserve it for when the student actually improves. You
never comment on or correct pronunciation; that is outside your scope.
Stay in control of the lesson: ask precise questions, push the student to
produce full, well-formed sentences, and do not accept sloppy or
approximate English as good enough.
```

**风格定位**:零容忍纠错(每个错误必纠,重复错误明确点破并要求操练)、表扬需"挣得"而非默认给予、对"意思对但表达不地道"同样不放过。比版本 A 更接近用户原话"业界回避严格教师是商业留存考量,个人使用不需要"的从严诉求。

**两版差异集中在**:纠错覆盖率(A 隐含"直接纠正"但未强调"每个不放过" vs B 显式"每个错误无例外") / 表扬默认值(A "适度鼓励" vs B "表扬需挣得") / 对不自然但语法正确表达的容忍度(A 未提 vs B 明确不接受)。用户可选一版,也可指出想要的折中点由后续迭代调整措辞。

---

## ② 中英文配比策略候选(2-3 个,均为设计假设,待用户拍板)**——已废弃,均不采纳(2026-08-10)**

> **废弃说明**:用户自述为英语初级学习者、尚无法用英语交流,以下三个候选均按"学生已有一定英语基础"设计,不适配该实际水平,**均不采纳**。取代方案见③节「教学阶段模式」。本节原文保留作为决策留痕,不再是待拍板项。

> 检索报告已核实:业界五款主流产品(Speak/ELSA Speak/Loora/Duolingo Max/Call Annie)均未公开中英混用/中文求助机制(`research/tutor-persona-references.md` §1.3、要素清单第 4 条)。以下候选**不能声称"参照某产品"**,均为本项目自行设计的假设,需用户显式确认(呼应 PRD FR-7 判据二)。

### 候选 1:全英文沉浸(Full English Immersion)

- **行为**:教师全程只说英语,即使学生卡壳/沉默/主动说中文求助,也不切换到中文,最多用更简单的英语重新表述一遍问题。
- **适用场景**:学生英语基础已有中级以上水平,追求沉浸式压力练习、不想被中文"拖回舒适区"。
- **依据**:纯设计假设,业界无公开范例(检索报告 §1.3 明确结论)。风险(自评):若用户实际口语基础较弱,可能出现"卡住后无出路"体验断裂,需用户确认自己的实际水平是否匹配。

### 候选 2:默认英文,卡壳时中文兜底解释(English-default, Chinese Fallback on Stuck)

- **行为**:默认全程英语;当学生明确表现出卡壳信号(直接用中文提问"这个怎么说/是什么意思"、连续沉默、同一错误反复出现)时,教师允许切到中文给一句简短澄清,随后立刻切回英语并重新发问,推进对话继续用英语进行。
- **适用场景**:初中级学习者需要偶尔的母语兜底,又不想完全放弃沉浸感;是三个候选中最贴近"实用主义"的折中方案。
- **依据**:同赛道非指定产品 Gliglish 官网明确提供"用母语提问"功能,可作为行业存在此类设计的旁证(检索报告 §1.3、S12),但不能代表五款指定产品的立场,仍是设计假设,只是有旁证支撑。

### 候选 3:英文为主,语法规则讲解专用中文(English-primary, Chinese Reserved for Grammar-Rule Explanations)

- **行为**:对话轮次与纠错复述(recast)本身始终用英语;但纠错时"点名具体违反了什么语法规则"这一步,规则讲解用中文说清楚(避免用英语解释语法术语本身造成的二次理解障碍),讲完立刻用英语给出正确形式,对话继续用英语。
- **适用场景**:学生希望精确理解"为什么错"的语法机制,愿意为讲解精度牺牲一部分沉浸感;与"严格教师"人设的强纠错气质契合度最高。
- **依据**:直接延伸自开源仓库 `guilhermelbo/language-learning-system` 的五步纠错法第 3 步"点名具体违反的规则"(检索报告 §2.1、S17)——该步骤原文未指定讲解用什么语言,本候选是在此基础上叠加的自行设计,无业界先例支持这一具体配比方案本身。

**PM 建议(置信度附带反证条件)**:70% 倾向候选 2——理由是它在"严格教师不迁就学生"与"用户实际是初学者、完全沉浸可能造成挫败退出"之间给出了显式触发条件(不是模糊的"适度使用中文"),且有旁证(Gliglish)而非纯凭空设计。**反证条件**:若用户口语基础已经较好(能听懂较复杂英文解释、极少卡壳),候选 1 全沉浸更贴近"严格教师"的从严定位,该判断请用户自行确认真实水平后决定。

---

## ③ 教学阶段语言策略(取代②候选,当选方案——中英文配比)

> 取代原②节三个中英配比候选(已废弃,见②节废弃说明)。用户拍板背景(访谈,2026-08-10):自述为英语初级学习者,尚无法用英语交流,原三候选均按"学生已有一定英语基础"设计,不适配。改为**教学阶段模式**:中文主导讲解与引导,英语用于练习素材/示范/跟读,随学生表现渐进提高英语占比。本节文本将作为陪练模板的 `LANGUAGE_SECTION` 覆盖值(PRD FR-4/FR-7),与①节版本 A 身份段共同构成**终版合成文案**,呈用户最终确认(PRD FR-7 判据二)。

### 语言策略文案草案

```
For this English-tutoring session, lead in Chinese (Mandarin): give
instructions, explain grammar rules, and set up each exercise in Chinese so
the student — an early-stage learner who cannot yet hold a conversation in
English — always knows what to do next. Use English specifically for:
practice material (example sentences and drills), demonstrations of correct
usage, and short phrases you want the student to repeat back or complete.
As the student's spoken English responses get longer, more accurate, and
more confident over the course of the session, shift more of your own
speech into English — introduce slightly longer English turns, and start
giving feedback in English before switching back to Chinese if needed.
If the student goes silent, hesitates, or switches to Chinese to ask what
something means, that is a normal part of this level: answer briefly in
Chinese, then immediately bring them back to an English attempt — don't
treat it as a failure or narrate it as a "fallback", just keep the lesson
moving.
```

### 设计说明

- **中文主导讲解**:指令、语法规则讲解、练习框架搭建均默认中文,呼应①节身份段里"点名违反的语法规则"这一步——按 `research/tutor-persona-references.md` 要素清单第 2 条,`guilhermelbo` 五步纠错法本身未指定讲解用语,本策略把"点名规则"这步的语言选择明确为中文,理由是用户是初学者、二次理解障碍风险高于中级学习者(检索报告 §2.1 已提示该风险)。原候选 3 的设计动机与此接近,但候选 3 假设的整体基调是"英文为主",与当前初学者定位不符,故未直接采用候选 3,而是重新设计了更中文主导的版本。
- **英语用于练习素材/示范/跟读**:与身份段"give the correct form...have them repeat it back"的纠错动作衔接一致——英语出现在"具体要跟读/要练习的那句话"上,而不是整段对话都用英语。
- **渐进提高英语占比**:无固定量化阈值(如"第 N 轮切换"),交给 LLM 依据学生实际表现动态判断——这是**设计假设**,业界无公开范例可参照(检索报告 §1.4"难度自适应"结论:五款产品官方表述均是"personalized"等笼统措辞,无具体机制公开)。后续如实测效果不佳,可在此基础上补充更明确的触发信号。
- **卡壳兜底自然并入,不做成"特殊脚本"**:文案明确"don't treat it as a failure or narrate it as a 'fallback'"——不让 LLM 在学生卡壳时说出"检测到你卡住了,现在切换到中文模式"这类破坏教学沉浸感的元叙述,而是直接自然地用中文简短解释、再拉回英语练习。这一处理方式吸收了原候选 2"卡壳信号触发中文兜底、随后切回英语"的核心机制,但表述方式从"显式判断规则"改写为"自然而然的教学节奏",更适配初学者(而非候选 2 原本设想的中级学习者)。

### 已知局限(诚实标注)

- "渐进提高英语占比"的具体判定信号(哪些表现算"更流利/更自信")完全交给 LLM 语境理解,未设计装配层可观测的状态机制;若未来发现 LLM 判断不稳定(时快时慢、时进时退),需要补充更明确的规则或状态跟踪,这属于实现/S2a 阶段的问题,不在本文档解决范围。
- 本策略未做真人试跑验证,是基于用户口径("初级学习者、教学阶段")与检索报告约束(§3 语音场景特有的陪练实践)的合成设计,PRD FR-7 判据二要求的"用户最终确认"正是为此设的收口关卡。

---

## ④ 设计选择 ↔ 检索报告要素对照表

| 文案设计选择 | 对应检索报告条目 | 备注 |
|---|---|---|
| 角色定位用"strict English teacher",明确排除"partner/coach" | 要素清单第 1 条(§1.1,业界四款回避严格教师);PRD FR-7"角色定位已拍板"段 | 本项目**刻意反向于**业界共识,用户已拍板背景是"个人使用无留存顾虑",非检索报告推荐结论 |
| 纠错动作:复述纠正(recast)+ 简要点名错误 + 要求学生复述正确形式 | 要素清单第 2 条(§1.3、S17 `guilhermelbo` 五步纠错法;S4 ELSA"每句说完后反馈") | 版本 A/B 均采用"recast + 点名"路线,未采用 `babblr` 的纯隐性重塑(S18),因为"点名"更契合严格教师定位 |
| 明确排除"纠正发音"承诺,纠错范围限定语法/句式/用词 | 要素清单第 3 条(§3.1,S21 Speak 工程博客;PRD FR-7 硬约束段) | 两版草案均含"You do not correct or judge pronunciation"逐字排除句 |
| 纠错时机:学生说完一句话之后纠正,不逐字打断 | 要素清单第 2 条 / §3.3(S4 ELSA"每句说完后";S8 Duolingo Max"对话中不打断") | 隐含在"have them repeat it back before moving on"的顺序里,未显式写"不打断"措辞——打断策略本身证据薄弱(检索报告 §3.3),不写成强承诺 |
| 中英配比候选 1/2/3 均标注"纯设计假设" | 要素清单第 4 条(§1.3,五款产品均未公开中英策略) | 候选 2 额外引用 S12(Gliglish)作旁证,候选 1/3 无任何行业旁证 |
| 回合简短、口语化,不写成书面清单式说明 | §3.2(S21,学习者停顿模式系统性不同于母语者,但该点证据薄弱仅供参考);PRD FR-7 载体约束 | 草案正文本身为连续口语化段落,未使用列表/编号;简短由协议段 `CONCISENESS_SECTION` 兜底,身份段本身不重复该指令 |
| 版本 B"表扬需挣得,不默认给予" | 要素清单第 2 条反向借鉴(guilhermelbo"Never condescending...Reframe mistakes as learning opportunities"是业界的柔化路线) | 本项目**刻意不采纳**该柔化建议,呼应用户"从严"拍板;仅在此处明确标注为与检索报告默认建议相反的选择 |

---

## ⑤ 自查清单(逐条对照 PRD FR-7 判据)

| FR-7 判据(逐条引用) | 版本 A | 版本 B | 结论 |
|---|---|---|---|
| "陪练模板的身份段人设定位为**严格的**英语教师(英语陪练),且与默认模板的身份段文本不同" | 用"strict English teacher, not a casual conversation partner"开篇;与 `OFFICIAL_SECTION`("helpful assistant...creative, helpful, and brief")文本完全不同 | 用"demanding, exacting English teacher — not a friend, not a coach"开篇,同样与默认模板不同 | 通过 |
| "确认范围须显式包含终版合成文案(身份段+教学阶段语言策略)"——本文档③节给出语言策略草案,取代原②节 3 候选 | — | — | 已满足(本文档③节本身就是该确认动作的载体,尚未获得用户最终确认) |
| "角色定位已拍板...文案措辞须体现'严格教师'定位、不得滑向陪练/教练式软化表达" | 全文无"partner/伙伴/教练"等软化词,反而显式用"not a casual conversation partner"排除该定位 | 全文无软化词,显式用"not a friend, not a coach"双重排除 | 通过 |
| "纠错相关措辞不出现'纠正发音'/'帮你改善发音准确度'一类承诺,纠错范围表述限定在语法、句式、用词层面" | 含逐字排除句"You do not correct or judge pronunciation; your job is grammar, sentence structure, and vocabulary only" | 含逐字排除句"You never comment on or correct pronunciation; that is outside your scope" | 通过 |
| PRD FR-7 载体约束(语音场景,口语化,不用列表/emoji——护栏句本身在独立段,但文案应天然适配朗读) | 连续口语化段落,无列表/emoji/markdown | 同左 | 通过 |

**结论**:版本 A(已当选)在本文档自查范围内满足 FR-7 现有判据;版本 B 已废弃不再适用。②节中英配比候选**已废弃**,由③节"教学阶段模式"取代;③节语言策略草案尚**未经用户最终确认**,与①节版本 A 合并构成的终版合成文案不得视为已确认(FR-7 判据二明文)。

---

## 开放问题 / 风险(需用户/S2a 关注,非本文档可自行裁决)

1. ~~`LANGUAGE_SECTION` 与陪练人设存在字面冲突,尚未被 PRD/design 解决~~ ——**已解决(2026-08-10,用户拍板)**:PRD FR-4 已将 `LANGUAGE_SECTION` 由"模板不可覆盖"改为**模板可覆盖**(默认值=现中文指令,默认模板行为不变),陪练模板的语言策略草案见③节,不再字面冲突。以下为该问题原文,留作决策留痕:
   现状 `LANGUAGE_SECTION` 固定文本为 `"Always reply in Chinese (Mandarin), regardless of the language of the input text."`,PRD FR-4 明确将其划为**本轮模板不可覆盖**段(design.md 未推翻这一点,ADR-3 只解决了护栏句归属,未涉及 `LANGUAGE_SECTION` 内容本身)。若按现有契约实现,陪练模板的 `system_instruction` 会在身份段(本文档草案,教英语、鼓励说英语)之后,紧跟着拼接一段协议段,字面指示"始终用中文回复,无论输入是什么语言"——这与②节任何一个中英配比候选(尤其候选 1 全英文沉浸)在**指令层面直接矛盾**,可能导致快脑 LLM 实际输出行为不可预期(听指令冲突时更靠后的文本,或随机摇摆)。
   本文档职责范围仅是起草身份段文案,`LANGUAGE_SECTION` 内容与是否需要为陪练模板设计条件化处理,是 FR-4 协议段范围,不在本次任务授权内擅自改动;**建议用户在确认②节候选的同时一并决定**:是否需要追加一条变更(或本次范围内的 S2a 补充设计)让 `LANGUAGE_SECTION` 对陪练模板可条件覆盖,否则草案再精美也可能被协议段字面覆盖而在实际运行中失效。
2. 候选 2/3 的"卡壳信号"识别(连续沉默判定、同一错误"反复出现"的计数窗口)在语音级联架构下如何具体判定(靠 LLM 自行理解上下文,还是需要装配层显式状态),本文档不展开,留给用户选定候选后由实现节点在 S2a/S2b 框架内处理,不在本文档判定范围。
3. 版本 A/B 均未显式写"打断/插话"处理策略,原因见④节表格备注(该点检索证据薄弱,§3.3),故意不写成强承诺,避免文案对不确定行为许下无法验证的判据。
