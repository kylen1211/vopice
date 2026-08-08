# openspec/ · 已废弃流程的归档区(冻结只读)

**2026-08-08 起本目录冻结,只读不写。**

openspec 三门流程(门一需求 / 门二评审 / 门三验收)已于 2026-08-07 退役,由 dev-pipeline
状态机取代。新变更一律开在 `<项目根>/pipeline/<change-id>/`,债务一律记 `pipeline/debts.md`。

## 本目录还剩什么

- `changes/archive/2026-08-03-fast-slow-brain/` — 快慢脑变更的完整历史留痕(proposal /
  research / design / tasks / gate.yml / retro),**保留作为设计依据与决策考古用**。
  其中 `design.md` 是快慢脑契约(R1–R8、§5.2 位置即归属、§6.7 prompt 契约)的原始出处,
  `pipeline/debts.md` 的 D-004/D-005 直接引用它的条款编号。

## 已迁走的东西

| 原位置 | 现位置 |
|---|---|
| `openspec/specs/voice-assistant-p1/spec.md` | `docs/specs/voice-assistant-p1.md` |
| `openspec/specs/dual-brain/spec.md` | `docs/specs/dual-brain.md` |
| `docs/backlog.md`(B1–B5) | `pipeline/debts.md`(D-001–D-008) |
| `openspec/config.yaml` | 已删除(流程配置随流程废弃) |
| `openspec/changes/task-dispatch/` | 已删除(2026-08-02 建的空壳,零内容) |

不要再往本目录写入任何新文件。
