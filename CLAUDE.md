# voice-agent · 项目总纲

> 每个会话开工前先读本节锚定方向;细节按指针跳转,不要凭记忆推断。
> 注意:旧项目会话记忆存在 voice-translate-v2 的项目路径下,本仓库新会话**不会**自动加载——本文件就是唯一入口锚点。

## 最终目标(2026-08-02 用户拍板,唯一版本)

**桌面客户端**承载的个人 AI 语音助手:
G1 实时语音对话 / G2 慢脑质量升级(快脑先答→慢脑深析→回流补充续接)/ G3 派活(派发任务**不中断对话**;未确认完成绝不报办好了)/ G4 按需监控本机页面内容实时交互。
**派活≠慢脑,两个独立功能。陪练=配置态(换 prompt/换 LLM),不是功能;真功能只有同声翻译+面试辅助,放最后。**

## 开发流程

- 开发或行为变更:用户显式点名 `/dev-pipeline` 才起流程,不自行代为发起。
- 变更产物落 `pipeline/<change-id>/`,债务落 `pipeline/debts.md`。
- openspec 已停用;`.claude/commands/opsx/`、`.claude/skills/openspec-*/` 保留待观察,不使用。

## 事实源指针(按需读,索引优先不整读)

- 2 期路线图与能力现状:`docs/capability-ledger.md`
- 项目债务簿:`pipeline/debts.md`
- 历史需求留痕:`docs/specs/`(已与代码脱节,仅考古用)
- 外部方案参考:`docs/external-design-references.md`
- 旧项目能力查询清单:`docs/legacy-capability-index.md`(旧库 `~/git/voice-translate-v2` 只读)
- pipecat 官方资料地图:`docs/official-resources-map.md`
- 旧流程归档区:`openspec/`(冻结只读,见 `openspec/README.md`)

## 项目纪律

- **官方脚手架结构不动**:新功能落既有目录(server/、client/、evals/、tests/、scripts/),要动结构须在 dev-pipeline 设计段(S2a)显式批准;
- 开发/测试/示例一律按 pipecat 官方标准,先查资料地图找官方对应件,不自研官方已有的能力;
- 索引优先、按需取数,不整读大文档;
- 引用外部依赖源码的行号前,先 `diff` 本地副本与本项目实装的那份,不一致以实装为准;
- 启动 bot.py/pytest 须带 `NLTK_DISABLE_IMPORT_SECURITY=1`;`pipecat` CLI 是全局工具(非项目 venv),factory judge 需 `PYTHONPATH=$(pwd)` + 手动 source .env。

@AGENTS.md
