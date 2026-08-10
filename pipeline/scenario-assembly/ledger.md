---
change_id: scenario-assembly
grade: L2
contract_tier: cases
stage: s1b
stage_status: done
pending: null
base_commit: 8d11dd25f624f38fec935411108a33396804f8b1
loop_counts:
  implement: 0
  integrate: 0
  review: 0
rollback_count: 0
frozen:
  prd:
    hash: b72a1c1d3087b231d3e9357cb5cd4194c61007167e5b522a870eb25cdd6647b2
  contract:
    hash: null
    based_on: null
  tasks:
    hash: null
    based_on: null
approvals:
- point: prd
  at: 2026-08-10T08:40Z
  hash: b72a1c1d3087b231d3e9357cb5cd4194c61007167e5b522a870eb25cdd6647b2
worktrees: []
generated: []
uncovered: []
parked: []
budget:
  limit_tokens: null
  spent_note: null
---
2026-08-10T15:22:36 init change_id=scenario-assembly
2026-08-10T15:23:20 set base_commit=8d11dd25f624f38fec935411108a33396804f8b1
2026-08-10T15:23:34 set grade=L2
2026-08-10T15:23:34 set contract_tier=cases
2026-08-10T15:23:34 set stage_status=done
2026-08-10T15:23:34 set stage=s1a
2026-08-10T15:23:34 set stage_status=running
2026-08-10T15:23:47 s0 judged grade=L2 hit=新增功能+改公共装配路径+同域未清债D-008; tier预判=cases(无新HTTP端点,RTVI消息契约留s2a终定); debts NOTICE 呈现不阻断,D-008/D-003 与本变更相关
2026-08-10T15:28:53 s1a 用户追加调研项:双脑架构成熟方案外部检索(现方案不够优雅,寻参考;关联 D-004/D-005),落点 research/dual-brain-alternatives.md
2026-08-10T15:41:19 用户拍板(s1a):模板切换时机=会话间切换(重建装配重开会话);本次不引入 ServiceSwitcher,运行时热切(轻量/跨厂商)均出范围;ServiceSwitcher 调研纪要留档备后续档位升级
2026-08-10T15:46:32 stage=s1a research done files=codebase-survey.md,external-research.md,dual-brain-alternatives.md,facts.md;三路回执 DONE_WITH_CONCERNS/DONE/DONE_WITH_CONCERNS;结论呈用户确认中
2026-08-10T15:46:32 set stage_status=waiting_human
2026-08-10T15:46:32 set pending=s1a 调研结论待确认;附拍板项:①主干测试基线修法 ②双脑加固是否另开变更
2026-08-10T15:48:58 呈批结果:双脑加固入队排后(act_msmxk0qo);s1a 结论用户要求先自行审阅,保持 waiting_human;基线破损用户要求说明前因后果后再定修法
2026-08-10T16:03:26 基线修复完成(用户拍板恢复法):从726ba43恢复baseline/两个json,pytest全套 70 passed(此前collection中断只能跑53);实测确认测试仅引用这两文件,恢复范围未扩大;工作区改动留待下次stage commit收编
2026-08-10T16:07:11 用户确认 s1a 调研结论(2026-08-10);范围锚定:场景模板定义+会话间切换装配,不含 ServiceSwitcher/双脑
2026-08-10T16:07:11 set pending=
2026-08-10T16:07:11 set stage_status=done
2026-08-10T16:07:11 set stage=s1b
2026-08-10T16:07:11 set stage_status=running
2026-08-10T16:17:08 set stage_status=waiting_human
2026-08-10T16:17:08 set pending=PRD 待批(硬批准点①)
2026-08-10T16:25:01 PRD呈批用户意见[E]三条:①FR-4本次保持强制不可覆盖,但s2a须预留低成本升级路径(用户预告后期必做语气可调);②开放问题①性质已向用户澄清(仅影响FR-3实现方式非决策);③FR-7陪练模板钉为英语陪练/英语教师人设,旧库实测无现成文案,已派外部检索tutor-persona参考(落research/)。PM修订中
2026-08-10T16:27:28 set pending=PRD 呈批暂缓:等 tutor-persona 外部检索回来核对是否触及 PRD 范围,并批后做最后一轮修订再呈(用户要求攒批一次改)
2026-08-10T16:35:38 用户拍板:新增范围——慢脑默认停用(配置开关控制装配是否挂双脑分支,代码与测试保留,dual_brain eval 改为开关开启时适用);并入本变更与人设检索发现攒同一轮 PRD 修订。依据:现无开关(SLOW_LLM_MODEL必需+无条件装配,codegraph实测);派活不受影响(独立worker用快脑模型)
2026-08-10T16:38:59 用户拍板:陪练模板角色定位=严格定义的英语教师(业界回避严格教师系商业留存考量,个人使用无此顾虑);FR-7 文案呈批待确认项收敛为仅中英配比一项
2026-08-10T16:40:56 用户拍板:发音纠错定性=可做但属后期高级功能(专用发音评测工具链提取音素指标),本期出范围入非目标;本期人设文案仍不得承诺纠发音
2026-08-10T16:42:11 set pending=PRD 终版待批(硬批准点①,攒批修订已全部落盘)
2026-08-10T16:43:09 set frozen.prd.hash=b72a1c1d3087b231d3e9357cb5cd4194c61007167e5b522a870eb25cdd6647b2
2026-08-10T16:43:09 set approvals[+]={point: prd, at: 2026-08-10T08:40Z, hash: b72a1c1d3087b231d3e9357cb5cd4194c61007167e5b522a870eb25cdd6647b2}
2026-08-10T16:43:09 set pending=
2026-08-10T16:43:09 PRD 批准冻结(硬批准点①,用户[A]);12条FR终版;无UI需求跳过ui-designer
2026-08-10T16:43:09 set stage_status=done
