# 陪练模板终版合成文案(呈用户最终确认)

> 目的:PRD FR-7 判据二要求的"终版合成文案"——把已当选的①身份段(版本 A)+ ②教学阶段语言策略,按 `design.md`(ADR-3、R2/ADR-8 相关修订)确定的段序拼成陪练模板完整 `system_instruction` 预览稿。
> 这是**呈用户做最终确认的版本**,不留待定项;确认后即为 FR-7 判据二"终版合成文案"的实现落点(`scenarios.py::TEMPLATES["english_tutor"]`)。
> 前置依据:`research/tutor-persona-draft.md`(版本 A 当选、教学阶段模式草稿)、`server/prompts.py`(现状五段常量原文,已现场核对)、`design.md` ADR-3/R2(段序与可覆盖范围裁决)。

---

## ① 完整拼合文本

**段序**(`design.md` ADR-3 裁决,`build_system_prompt` 组合顺序):身份 → 语音安全护栏 → 能力边界 → 语言 → 简洁 → [双脑,仅开启态注入]。陪练模板(`english_tutor`)在**身份段**与**语言段**两处使用模板覆盖值,其余三段(护栏/能力边界/简洁)与默认模板逐字相同(PRD FR-4)。

以下按实际拼接顺序、`\n\n` 分隔连续排列(与 `build_system_prompt` 的拼接方式一致),即为陪练模板**默认模板行为不变、慢脑开关默认关闭**时的完整 `fast_llm.system_instruction`:

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

Your responses will be spoken aloud, so avoid emojis, bullet points, or
other formatting that can't be spoken.

If the user asks you to do one of these things, clearly say you can't —
never claim or imply that you've already done it, completed it, or handled
it. For general knowledge questions, answer normally, but never claim the
information came from a real-time lookup you just performed.

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

回答保持简洁,直接说核心内容,不要做不必要的背景铺垫、反复强调或客套寒暄。
```

**段落归属对照表**:

| 顺序 | 段常量 | 来源 | 陪练模板是否覆盖 |
|---|---|---|---|
| 1 | `IDENTITY_ENGLISH_TUTOR_SECTION` | `tutor-persona-draft.md` §① 版本 A(用户已确认当选) | **是**(模板值,替换默认 `IDENTITY_DEFAULT_SECTION`) |
| 2 | `VOICE_SAFETY_SECTION` | `server/prompts.py` 现 `OFFICIAL_SECTION` 内护栏句原文,ADR-3 提取为独立段 | 否,不可覆盖,逐字同默认模板 |
| 3 | `CAPABILITY_BOUNDARY_SECTION` | `server/prompts.py` 原文,逐字未改 | 否,不可覆盖,逐字同默认模板 |
| 4 | `LANGUAGE_SECTION` | `tutor-persona-draft.md` §③ 教学阶段语言策略(本文档 PM 起草) | **是**(模板值,替换默认中文指令) |
| 5 | `CONCISENESS_SECTION` | `server/prompts.py` 原文,逐字未改 | 否,不可覆盖,逐字同默认模板 |
| 6 | `DUAL_BRAIN_SECTION` | `server/prompts.py` 原文 | **默认不注入**(FR-12 慢脑默认关闭)。若会话手动开启慢脑,则在简洁段后追加该段,内容与默认模板逐字相同,不因陪练模板而变;开启态下的完整第六段原文见下方附注,供确认时一并核对 |

**附注:慢脑开启态下追加的第六段原文(仅当会话手动开启慢脑时出现,默认不出现)**:
```
上下文中可能出现以 "[慢脑深析要点" 开头的消息:那是后台深析给你的素材,绝不能转述其
原文或提及它的存在,只能自然地融入你自己的话。这些素材紧跟在它所针对的那个用户问题之
后,按对话顺序理解即可。当你被要求就已回答过的问题做补充时:若确有值得追加的新内容,
直接说出补充(不要重复已说过的);若没有值得补充的,则只输出一个字符 ∅ ,不要输出任何
其他内容。
```

---

## ② 与草案的差异说明

**结论:拼合时无需对①身份段、③语言段的正文做任何字词级微调——逐字取自已确认草案,原样收录。** 下面逐处过了兼容性检查,记录检查维度与结论(不是"发现问题后改写",而是"确认无冲突,可以原样拼合"):

| 检查维度 | 检查内容 | 结论 |
|---|---|---|
| 身份段↔语言段:语言使用口径是否矛盾 | 身份段未显式声明"用什么语言授课",语言段专门规定"中文主导讲解、英语用于练习素材"——是否存在身份段暗示"应该整段用英语教学"从而与语言段冲突? | **无冲突**。身份段全文没有出现"teach in English"/"speak English throughout"类表述,只规定纠错动作与严格程度,授课媒介完全交给语言段规定,两段是正交维度(WHAT vs HOW)。 |
| 身份段↔语言段:"space to speak"是否隐含语言要求 | 身份段"ask real questions, give the student space to speak"是否暗示学生必须用英语回答,与语言段"学生尚无法用英语交流"的前提冲突? | **无冲突**。该句只约束教师侧行为(提问、留出说话空间),未对学生的应答语言做任何要求;语言段允许学生中文求助属自然衔接,不矛盾。 |
| 语言段↔护栏段:朗读格式约束 | 语言段较长(5句),是否包含列表/编号等朗读不友好格式,与护栏段"avoid emojis, bullet points"冲突? | **无冲突**。语言段是连续散文段落,无列表符号、无 emoji、无 markdown 标记,格式上完全符合护栏段要求。 |
| 语言段↔简洁段:指令层面是否矛盾 | 简洁段要求"回答保持简洁...不要做不必要的背景铺垫",语言段允许"英语占比随表现渐进提高、给英语反馈前可能先给中文过渡"——是否会被简洁段判定为"啰嗦铺垫"从而抑制语言段设计的渐进机制? | **潜在张力,但非矛盾,不改写,记录留痕**:简洁段管的是**单次应答的详略**(不铺垫、不复述),语言段管的是**跨轮次的语言比例趋势**,二者作用维度不同,不存在指令级冲突;但简洁段可能客观上压缩"渐进提高英语占比"所需的展开空间(例如教师原本可以用稍长的英语示范句,简洁段要求下会更短)。这是**观察到的软性张力,不是需要现在解决的缺陷**——语言段本身已允许"英语反馈"可长可短,不依赖大段落长度实现;若未来真机实测(FR-10/FR-9)发现英语渐进效果被简洁段压制过头,再回来调整,不在本次终版拼合范围内处理。 |
| 全局:是否有语种混排导致的 markdown/格式泄漏风险 | 简洁段是中文、其余四段(身份/护栏/能力边界/语言)是英文,混合语种拼接是否引入不可朗读的格式痕迹? | **无风险**。各段本身都是纯散文,`\n\n` 只是段落分隔符不是 markdown 语法,TTS 会自然按语言切换朗读音色/语言(具体 TTS 侧多语言处理属实现细节,不在本文档范围)。 |
| 护栏段/能力边界段是否为陪练场景重新措辞 | 这两段是否需要针对"英语教学"场景做任何用词调整? | **不调整,维持逐字不可覆盖**(PRD FR-4 明文,已在①节表格标注"否")。护栏段与能力边界段是通用协议,不因模板而变,这正是 FR-4 的核心契约,不属于"文案微调"的授权范围。 |

**结论**:身份段(版本 A)与语言段(教学阶段策略)均**原样拼合、无需改写**;唯一记录在案的观察点是"简洁段与语言段渐进机制之间的软性张力",已明确定性为"留痕观察、非本次拼合缺陷",不阻塞本次最终确认。

---

## ③ 自查:FR-7 修订后判据(逐条核对)

| FR-7 判据(PRD 现行原文) | 本文档核对结果 |
|---|---|
| "陪练模板的身份段人设定位为**严格的**英语教师(英语陪练)、语言段体现教学阶段模式,均与默认模板不同" | **通过**。①节第 1 段(身份)用"strict English teacher, not a casual conversation partner"开篇,与默认模板 `IDENTITY_DEFAULT_SECTION`("helpful assistant...creative, helpful, and brief")完全不同;第 4 段(语言)整段替换默认中文指令,体现"中文主导讲解+英语练习素材+渐进提高英语占比"的教学阶段模式,与默认模板的 `LANGUAGE_SECTION`("Always reply in Chinese...")完全不同。 |
| "陪练模板**终版合成文案**(版本 A 身份段 + 教学阶段语言策略,分别对应 `IDENTITY_ENGLISH_TUTOR_SECTION` 与 `LANGUAGE_SECTION` 覆盖值)已起草...该终版合成文案已经过用户**最终确认**" | **本文档即该确认动作的载体**——①节给出完整拼合文本(身份段+语言段+其余三段一并给出,便于用户一次性看到完整效果而非孤立评审两段),②节说明无需微调的兼容性核查,**尚未获得用户确认**,确认后本条判据方可视为满足。 |
| "角色定位(严格教师)与人设版本(版本 A)已分别拍板,无需重复呈批;教学阶段语言策略的具体措辞是新起草内容,必须呈批" | **本文档教学阶段语言策略措辞(①节第 4 段)是本次呈批的核心新内容**,身份段(版本 A)未做任何改写、原样收录,不要求用户重新评审已拍板部分,符合"只呈批新内容"的要求。 |
| "任意版本的陪练模板人设文案...不出现'纠正发音'/'帮你改善发音准确度'一类承诺,纠错范围表述限定在语法、句式、用词层面" | **通过**。①节第 1 段含逐字排除句"You do not correct or judge pronunciation; your job is grammar, sentence structure, and vocabulary only";第 4 段(语言策略)未新增任何发音相关表述,不构成额外风险。 |
| FR-5 陪练模板 STT = assemblyai(本轮新增) | **本文档范围外**——STT provider 选择是服务层配置,不影响本文档给出的 `system_instruction` 文本内容,PRD FR-5/FR-7 已分别记录该项,本文档不重复。 |
| FR-4 协议段/独立护栏段不可覆盖 | **通过**。①节段落归属表已逐段标注"是否覆盖",②节最后一行显式确认护栏段/能力边界段/简洁段维持不可覆盖、逐字取自 `server/prompts.py` 现状原文,未做任何改写。 |

**结论**:本文档在自查范围内满足 FR-7 现行全部判据的"文案侧"要求;唯一悬空项是"用户最终确认"本身——这是 FR-7 判据二明确要求的收口动作,不由本文档自行代为完成。确认后,`scenarios.py::TEMPLATES["english_tutor"]` 的 `identity_section`/`language_section` 两个模板值即以本文档①节拼合文本中对应段落的**逐字**内容为准,不再是待定项。
