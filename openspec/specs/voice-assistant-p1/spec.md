# voice-assistant-p1 Specification

## Purpose
TBD - created by archiving change pipecat-native-p1. Update Purpose after archive.
## Requirements
### Requirement: R1 轮次结束即回应
当用户一轮说话结束时,系统必须(SHALL)开始生成并输出回应。

#### Scenario: R1-S1 基本问答
- **GIVEN** 网页端会话已建立
- **WHEN** 用户说完一句问话且轮次判定结束
- **THEN** 助手开始输出回答

### Requirement: R2 播报可被打断
在播报期间,当用户开始说话时,系统必须(SHALL)停止播报并转入聆听。

#### Scenario: R2-S1 打断
- **GIVEN** 助手正在播报
- **WHEN** 用户开口说话
- **THEN** 播报停止,用户新话被听取

### Requirement: R3 双通道输出
系统必须(SHALL)以语音+屏幕文字双通道输出回应。

#### Scenario: R3-S1 字幕同步
- **GIVEN** 助手输出一段回答
- **THEN** 页面同步显示对应文字

### Requirement: R4 执行动作类请求如实告知不支持
如果用户发出执行动作类请求(改文件/发消息/操作程序等),则系统必须(SHALL)如实告知本期不支持执行,且不得假称已执行。

#### Scenario: R4-S1 拒绝执行不谎报
- **GIVEN** 会话进行中
- **WHEN** 用户说"帮我改个文件"
- **THEN** 回复明确说明本期不支持执行任务,且不出现"已完成"类表述

#### Scenario: R4-S2 知识问答不冒充实时
- **GIVEN** 会话进行中
- **WHEN** 用户问一般知识问题
- **THEN** 正常回答,且不声称信息为"实时查询所得"

### Requirement: R5 配置缺失快速失败
如果启动时必需配置缺失,则系统必须(SHALL)报出具体缺失项并拒绝启动。

#### Scenario: R5-S1 缺 key 启动失败
- **GIVEN** 必需 API key 未配置
- **WHEN** 启动服务
- **THEN** 启动失败,输出列明缺失项名称

### Requirement: R6 旧仓库冻结保护
系统必须继续(SHALL CONTINUE TO)保持旧项目 voice-translate-v2 的产品代码与测试不受本变更修改(整库只读参考;旧库内仅允许改动本变更自身的 openspec 文档)。

#### Scenario: R6-S1 旧库零改动
- **GIVEN** 1 期实施完成
- **WHEN** 对比旧仓库工作区与本变更起点
- **THEN** 除 openspec/ 下本变更文档外无任何改动

### Requirement: R7 会话干净结束服务保持可连
当用户结束会话后,系统必须(SHALL)干净结束该会话且服务保持可连。

#### Scenario: R7-S1 立即重连
- **GIVEN** 上一会话已结束
- **WHEN** 用户立即重新连接
- **THEN** 新会话建立成功

> **原 R8「失联会话自动回收」已于 2026-08-01 由用户裁决移出 1 期范围**(见 proposal §7 排除清单),故本增量不含该 Requirement。僵尸会话的处置手段为重启服务进程。

