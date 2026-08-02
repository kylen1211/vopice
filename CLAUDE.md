# voice-agent · 项目总纲

> 每个会话开工前先读本节锚定方向;细节按指针跳转,不要凭记忆推断。
> 注意:旧项目会话记忆存在 voice-translate-v2 的项目路径下,本仓库新会话**不会**自动加载——本文件就是唯一入口锚点。

## 最终目标(2026-08-02 用户拍板,唯一版本)

**桌面客户端**承载的个人 AI 语音助手:
G1 实时语音对话 / G2 慢脑质量升级(快脑先答→慢脑深析→回流补充续接)/ G3 派活(派发任务**不中断对话**;未确认完成绝不报办好了)/ G4 按需监控本机页面内容实时交互。
**派活≠慢脑,两个独立功能。陪练=配置态(换 prompt/换 LLM),不是功能;真功能只有同声翻译+面试辅助,放最后。**

## 当前阶段

**2 期需求澄清进行中,门一未起,先不开发**。能力账单草稿待用户核 → 迭代方案 → 正式门一(三门流程按全局总纲,变更开在本仓库 `openspec/`)。

## 事实源指针(按需读,索引优先不整读)

- **能力账单对照表(2 期主工作底稿)**:`docs/capability-ledger.md`(含官方件核对记录 + 核心能力/优化方案二分)
- **外部方案参考(已核实自含版)**:`docs/external-design-references.md`(qwen Work 派活底稿 / 快慢脑三参照 / kit 对比佐证;原始 `~/research/` 调研目录可清理)
- 旧项目历史能力查询清单:`docs/legacy-capability-index.md`(旧库 `~/git/voice-translate-v2` 整库冻结只读,按此清单定点取材)
- pipecat 官方资料地图:`docs/official-resources-map.md`
- 已知限制:`docs/backlog.md`;需求事实源:`openspec/specs/`(1 期基线 voice-assistant-p1 已迁入)

## 项目纪律

- **官方脚手架结构不动**:新功能落既有目录(server/、client/、evals/、tests/、scripts/),要动结构须门二显式批准;
- 开发/测试/示例一律按 pipecat 官方标准,先查资料地图找官方对应件,不自研官方已有的能力;
- 索引优先、按需取数,不整读大文档;
- 启动 bot.py/pytest 须带 `NLTK_DISABLE_IMPORT_SECURITY=1`;`pipecat` CLI 是全局工具(非项目 venv),factory judge 需 `PYTHONPATH=$(pwd)` + 手动 source .env。

@AGENTS.md
