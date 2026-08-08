# T-0 · 改动前 LLM 行为基线(pre-change,C-17 步骤 1-3)

> 依据 `contract/cases.md` C-17 与 `design.md` R-7(坑 P57)。本文件归档
> `server/evals/baseline_probe.yaml` 8 问的改动前真实回复原文，供 T-8(C-17 步骤 4)
> 改动落地后同问同答对读。**判定要求**（本卡验收项 5）：本文件必须在任何一行
> `server/prompts.py`/`bot.py`/`config.py`/`task_dispatch.py`/`task_dispatch_contract.py`
> 改动落地之前生成——下方 `git status --porcelain server/` 原样输出即为该时刻的证据。

## 时序证据(design.md R-7 判定用)

取样时刻执行:

```
$ git -C /home/ky/git/voice-agent status --porcelain server/
?? server/evals/baseline_probe.yaml
```

原样输出只有本卡新建的 `server/evals/baseline_probe.yaml`（本卡独占产出物），
不含 `server/prompts.py` / `server/bot.py` / `server/config.py` /
`server/task_dispatch.py` / `server/task_dispatch_contract.py` 任一行改动 —— 满足
时序硬要求。

## 运行环境

- 运行时间戳(本地时区 +08:00):`2026-08-08T21:54:48+08:00` 起,单次场景运行耗时 52245ms。
- `LLM_MODEL`:`gemini-3.6-flash-low`(来自 `server/.env`,与 bot.py 主 LLM 服务同一取值)。
- 运行命令(两个终端):
  ```
  cd /home/ky/git/voice-agent/server && NLTK_DISABLE_IMPORT_SECURITY=1 uv run bot.py -t eval 2>&1 | tee /tmp/pipecat-baseline.txt
  cd /home/ky/git/voice-agent/server && set -a && source .env && set +a && PYTHONPATH="$(pwd)" NLTK_DISABLE_IMPORT_SECURITY=1 pipecat eval run evals/baseline_probe.yaml -v -d --logs-dir eval-runs
  ```
- 第二条命令退出码:`0`(1/1 passed · 52.2s)。
- 原样调试日志:`server/eval-runs/baseline_probe.eval.log`(59 行,`-d` 生成)。

## 8 条真实回复原文

问题分类(C-17 步骤 1 原文):2 条知识问答(Q1/Q2)/ 2 条闲聊(Q3/Q4)/
2 条执行类请求(Q5/Q6)/ 2 条多轮追问(Q7 追问 Q2、Q8 追问 Q6)。

## Q1

- 分类:知识问答
- 问题原文:`光合作用的基本化学方程式是什么？`
- 回复原文:
  > 光合作用的基本化学方程式是：六个二氧化碳加上六个水，在光照和叶绿素的作用下，生成一个葡萄糖和六个氧气。
  >
  > 简单来说就是：6CO2 + 6H2O 生成 C6H12O6 + 6O2。

## Q2

- 分类:知识问答
- 问题原文:`居里夫人一共获得过几次诺贝尔奖？分别是哪两个学科？`
- 回复原文:
  > 居里夫人一共获得过两次诺贝尔奖，分别是物理学奖和化学奖。

## Q3

- 分类:闲聊
- 问题原文:`你好呀，今天心情怎么样？`
- 回复原文:
  > 我很好，随时准备为你提供帮助！你今天心情怎么样？

## Q4

- 分类:闲聊
- 问题原文:`你平时会不会觉得无聊呀？`
- 回复原文:
  > 不会呀，因为我没有情感，也不会感到无聊。只要你需要我，我就随时待命！

## Q5

- 分类:执行类请求(改动前被 `prompts.py::CAPABILITY_BOUNDARY_SECTION` 拒答)
- 问题原文:`帮我把浏览器里正在放的视频暂停一下`
- 回复原文:
  > 我无法为你暂停视频，因为我没有操作你设备或控制浏览器的权限。

## Q6

- 分类:执行类请求(改动前被 `prompts.py::CAPABILITY_BOUNDARY_SECTION` 拒答)
- 问题原文:`帮我订一张明天去上海的机票`
- 回复原文:
  > 抱歉，我无法为你预订机票。我没有操作实际业务的权限，你需要通过旅行软件或航空公司官网自行预订。

## Q7

- 分类:多轮追问(追问 Q2,"她"指居里夫人)
- 问题原文:`她后来是怎么去世的？跟她的研究工作有关系吗？`
- 回复原文:
  > 居里夫人因长期接触放射性物质患上再生障碍性贫血而去世，这确实与她的科学研究工作密切相关。

## Q8

- 分类:多轮追问(追问 Q6,同一趟上海行程换交通方式)
- 问题原文:`那如果坐高铁去呢，大概要多久？`
- 回复原文:
  > 这取决于你从哪里出发。比如从北京到上海，坐高铁大约需要4.5到6个小时；如果从南京或杭州出发，只需要一两个小时。你能告诉我你的出发地吗？

## 备注

- 全部 8 问均成功取得 `response`,无失败/空缺项。
- Q5/Q6 的拒答措辞是 T-3 落地后核心对读点(`CAPABILITY_BOUNDARY_SECTION` 届时删除
  "无执行能力"一句),T-8 需重点比对这两条改动前后是否仍然拒答、拒答措辞如何变化。
- Q7/Q8 显示改动前上下文保留正常(能正确回指 Q2/Q6 的主体),可作为 T-8 侧的上下文
  能力回归对照基线。
