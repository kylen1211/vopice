# T-4 · SA-19 人设行为基线样本

> change_id: scenario-assembly | 产出: backend-dev T-4 | 日期: 2026-08-10
> 契约来源:`pipeline/scenario-assembly/contract/cases.md` SA-19(FR-10,manual)。
> 场景文件(命名未被契约钉死,已定名,`server/evals/`,text/audio 两个模态各自独立文件,原因见下):
> - `server/evals/scenario_persona_voice_chat.yaml`(默认模板,text 模式)
> - `server/evals/scenario_persona_english_tutor.yaml`(陪练模板,text 模式,与上者同一固定问题集)
> - `server/evals/scenario_persona_english_tutor_audio_en.yaml`(陪练模板,英语 audio 输入轮,AssemblyAI 中英 code-switch 真机证据)
>
> 三文件而非两文件的原因:pipecat eval 的 `user:` 模态块是**场景级**(整份 yaml 共用同一投递模态),没有逐轮覆盖机制(已用 `pipecat-context-hub get-doc /pipecat/evals/scenarios` 现场核对);为了让 voice_chat/english_tutor 的文本对照保持"同一固定问题集、同为 text 模式"的公平对比,陪练模板的英语 audio 输入轮只能落在单独一个文件里。
>
> 运行条件:两个 bot 均以 `DUAL_BRAIN_ENABLED` 默认(关闭)状态启动 —— SA-19 验的是模板行为基线,不是双脑分支,避免慢脑补充轮混入样本增加噪音。

## ① 固定问题集(同一份问题集用于两模板 text 场景)

1. "你是谁？"
2. "帮我做个决定，晚饭吃火锅还是烤肉？"
3. "Can you teach me one English sentence?"(第三题用来在同一固定问题集里同时压出 SA-22/FR-4 语言段结构差异的可观察证据)

## ② voice_chat（默认模板）— text 模式,原样 `llm_response`

启动日志确认:`[scenario] template=voice_chat stt=deepgram/stt-rt-v5 tts=cartesia/6eb8965c-e295-47bd-a9e4-3eeebb3abcff fast_model=gemini-3.6-flash-low dual_brain=off`

| 轮次 | 用户输入 | bot `llm_response`（原样） |
|---|---|---|
| 0（问候，无用户输入） | — | 你好，我是你的智能语音助手，可以回答问题并随时为你提供帮助。 |
| 1 | 你是谁？ | 我是你的智能语音助手，可以为你解答问题和提供帮助。有什么我可以协助你的吗？ |
| 2 | 帮我做个决定，晚饭吃火锅还是烤肉？ | 建议选火锅！有汤有菜特别暖和。如果你今天特别想大口吃肉，那就选烤肉吧。 |
| 3 | Can you teach me one English sentence? | 没问题！"Have a nice day!" 意思是"祝你有美好的一天！"你可以跟我读一遍：Have a nice day! |

命令:`SCENARIO=voice_chat NLTK_DISABLE_IMPORT_SECURITY=1 uv run python bot.py -t eval` + `PYTHONPATH=$(pwd) pipecat eval run evals/scenario_persona_voice_chat.yaml -v`
结果:`1/1 passed`(judge 全部判 yes)。

## ③ english_tutor（陪练模板）— text 模式,原样 `llm_response`

启动日志确认:`[scenario] template=english_tutor stt=assemblyai/stt-rt-v5 tts=cartesia/6eb8965c-e295-47bd-a9e4-3eeebb3abcff fast_model=gemini-3.6-flash-low dual_brain=off`(STT provider 已切到 AssemblyAI,与 voice_chat 的 Deepgram 不同,验证了 SA-04 的服务面差异也在真机装配里生效)。

| 轮次 | 用户输入 | bot `llm_response`（原样） |
|---|---|---|
| 0（问候，无用户输入） | — | 你好，我是你的英语老师。在接下来的课程里，我会重点纠正你的语法、句型和词汇表达。每次出现错误，我都需要你重新重复正确的形式。\n\n现在我们开始第一项练习。请用英文跟我打个招呼，说：Hello, teacher! |
| 1 | 你是谁？ | 我是你的英语老师。\n\n现在让我们回到练习。请试着用英文跟我打个招呼，跟我说一遍：Hello, teacher! |
| 2 | 帮我做个决定，晚饭吃火锅还是烤肉？ | 吃火锅吧。不过既然我们在上课，请试着用英文告诉我你的决定。\n\n跟我念：I choose hot pot. 或者 I choose BBQ. 请选择一句跟我重复一遍。 |
| 3 | Can you teach me one English sentence? | 没问题！你刚才这句话语法完全正确。\n\n今天我们来学这句话：I want to learn English every day.\n\n它的意思是"我每天都想学英语"。want to 后面接动词原形，表示"想要做某事"。\n\n现在，请跟我重复一遍：I want to learn English every day. |

命令:`SCENARIO=english_tutor NLTK_DISABLE_IMPORT_SECURITY=1 uv run python bot.py -t eval` + `PYTHONPATH=$(pwd) pipecat eval run evals/scenario_persona_english_tutor.yaml -v`
结果:`1/1 passed`(judge 全部判 yes)。

**人设可区分性(SA-19 判据核对)**:同一问题"你是谁？",voice_chat 答"智能语音助手"(通用助理定位),english_tutor 答"我是你的英语老师"并立刻拉回英语练习——身份段差异逐字体现在真实输出里。语言策略差异(SA-22 的行为落点):voice_chat 对"你是谁？"/"帮我做决定"两题全程中文、不引入英语教学内容(第 3 题被问到才顺带给一句英文,且仅一句、不展开);english_tutor 对同样的第 1/2 题都是"中文讲解为主 + 主动给出英文练习句并要求跟读"(如"跟我念：I choose hot pot. 或者 I choose BBQ."),体现"中文主导讲解 + 英语练习素材"的教学阶段模式,与默认模板的纯中文、无教学动作形成结构性反差。

## ④ english_tutor — 英语 audio 输入轮(AssemblyAI 中英 code-switch 真机证据,design R-12)

启动日志确认 STT 服务:`AssemblyAISTTService#0` 已连接(`Connected to AssemblyAI WebSocket`)。

场景:`scenario_persona_english_tutor_audio_en.yaml`,`user: {modality: audio, speech: {service: kokoro, voice: af_heart}}`(本地免费合成,无 API 调用成本)、`judge` 用默认 text 模态(不触发真实 TTS,`response`/`llm_response` 直接取 LLM 文本输出,零 TTS 计费)。

合成的英语输入语句:`"Can you help me practice speaking English?"`

**AssemblyAI 真实转写结果(`user_transcription` 事件,原样)**:

```
Can you help me practice speaking English?
```

——与合成输入逐字一致,证明 AssemblyAI `universal-3-5-pro` 原生 code-switch 对英语输入的转写在本次真机运行里完全正确(未被误识别成中文或产生乱码),design R-12 的"看不到英语被正确转写就判失败"判据在此通过。

紧随其后的 bot `llm_response`(原样):

```
当然可以。你刚才这句话语法完全正确，表达也很地道。

接下来我们进行简单的口语练习。请用英文回答我的问题：What is your favorite food?

你可以使用这个句型：My favorite food is... 后面加上你喜欢的食物。请试着用英文回答一遍。
```

结果:`1/1 passed`。命令:`SCENARIO=english_tutor NLTK_DISABLE_IMPORT_SECURITY=1 uv run python bot.py -t eval` + `PYTHONPATH=$(pwd) pipecat eval run evals/scenario_persona_english_tutor_audio_en.yaml -v`(本卡未加 `-a`,因为 judge 是 text 模态,harness 未产出可听的输出音频文件——见下节说明)。

## ⑤ TTS 侧主观评价(design R-14)—— 本卡未执行真实 TTS 朗读,如实说明

design R-14 要求"同轮顺带听 TTS 表现"，即让陪练模板真的朗读出英文练习素材（"Hello, teacher!" / "I choose hot pot." 等），主观评价中文引擎朗读英文的可懂度。经现场核实：

- `-a`/`--record-dir` 产出的可听录音，只在 **`judge: {modality: audio}`**（真实 TTS 朗读 + 转写）时才有意义——`judge: {modality: text}` 下 TTS 被 harness 自动跳过（已用官方文档 `Judging with judge:` 一节核对：*"Text (the default). The agent's TTS is skipped automatically"*），实测 ④ 节的运行 `--record-dir` 目录下确实没有产出任何 wav 文件，与文档描述一致。
- 要拿到"中文引擎朗读英文练习素材"的听感证据，必须把 `judge` 切到 `audio` 模态，这会让 Cartesia TTS（`server/.env` 的 `TTS_PROVIDER=cartesia`，真实计费服务）针对本轮的英文/中文混合文本真正合成语音——即一次会产生**真实费用**的调用。
- 本项目对"会产生真实费用的 TTS round-trip eval"已有明确先例：`server/evals/dual_brain_audio.yaml` 文件头部原文写明 *"Per project policy, only the user may execute a cost-incurring run, from their own real terminal"*，且该场景确认"has not been run by any agent"。遵循这一既有约定（不是本卡临时定的口径），本卡**不越权代跑**judge:audio 的真实 TTS 轮次，未获得听感证据，如实标注为**未完成**，不代为给出主观评价。
- 已备好可执行命令，供用户本人在自己终端决定是否执行（会产生 Cartesia 计费）：

```bash
cd /home/ky/git/voice-agent/server
SCENARIO=english_tutor NLTK_DISABLE_IMPORT_SECURITY=1 uv run python bot.py -t eval
# 另开终端：
set -a && source .env && set +a
PYTHONPATH=$(pwd) pipecat eval run evals/scenario_persona_english_tutor_audio_en.yaml \
  -v -a --record-dir /home/ky/git/voice-agent/pipeline/scenario-assembly/baseline
# 若要同时听 bot 朗读英文素材，需把该 yaml 的 judge 块临时改成：
#   judge:
#     modality: audio
#     transcription: {service: whisper}
#     eval: {factory: "judge_factory.judge_llm"}
# （改完记得跑完后改回来，避免污染本卡交付的 yaml 内容）
```

**结论**:R-14 的"发音质量是否可接受"这一问题本卡未能给出真机听感证据，留给用户本人执行上述命令后判断；若不可接受，按 design R-14 既定口径"另起变更"，本卡未改动任何 TTS 相关代码/配置。
