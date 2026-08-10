---
change_id: scenario-assembly
grade: L3
contract_tier: cases
stage: s2b
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
    hash: 29320b221abd3aabba307e88facfdcbb848f87ff2946adb63fd40d2d4132a98f
  contract:
    hash: 3597903221a54651fbba6bf49137c6413bdbff2cd23b35634c3e493f10177046
    based_on: 29320b221abd3aabba307e88facfdcbb848f87ff2946adb63fd40d2d4132a98f
  tasks:
    hash: be39bb690c5963fcb1d4429d6ca98766d52b8a415ec310213717792491a2621a
    based_on: 3597903221a54651fbba6bf49137c6413bdbff2cd23b35634c3e493f10177046
approvals:
- point: prd
  at: 2026-08-10T08:40Z
  hash: b72a1c1d3087b231d3e9357cb5cd4194c61007167e5b522a870eb25cdd6647b2
- point: prd-refreeze
  at: 2026-08-10T09:30Z
  hash: a97aabb957d58bc97d2d4ccd1cd3d59974c8e4f566a8e094daf3596f2d127d32
  reason: FR-4护栏句事实纠错(用户随设计批准授权)
- point: contract
  at: 2026-08-10T09:30Z
  hash: 630277ca11c256df600752cf2d49bbb1eb36fbe2c845fe9044a22acd94cd60d9
- point: prd-refreeze2
  at: 2026-08-10T11:05Z
  hash: 29320b221abd3aabba307e88facfdcbb848f87ff2946adb63fd40d2d4132a98f
  reason: 语言段可覆盖+FR-5白名单assemblyai+FR-7终版文案
  均经用户逐项拍板: null
- point: contract-refreeze
  at: 2026-08-10T11:05Z
  hash: 3597903221a54651fbba6bf49137c6413bdbff2cd23b35634c3e493f10177046
  reason: R1语言段+R2 assemblyai修订
  dry-run 19机检+4manual: null
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
2026-08-10T16:43:09 set stage=s2a
2026-08-10T16:43:09 set stage_status=running
2026-08-10T17:04:36 set stage_status=waiting_human
2026-08-10T17:04:36 set pending=设计与契约待批(硬批准点②);随批决策:FR-4 PRD事实纠错回改授权、人设文案并行起草
2026-08-10T17:07:59 设计批准([A],硬批准点②):拓扑=单进程多会话+会话级重读配置;scenarios.py注册表+六段prompt;DUAL_BRAIN_ENABLED默认关;D-003最小触碰;cases档17用例。随批授权:FR-4护栏句纠错回改PRD(PM执行中,改毕重冻结)、测试白名单3处、D-019登记(已入debts.md)。人设文案并行起草中
2026-08-10T17:08:24 set frozen.prd.hash=a97aabb957d58bc97d2d4ccd1cd3d59974c8e4f566a8e094daf3596f2d127d32
2026-08-10T17:08:24 set approvals[+]={point: prd-refreeze, at: 2026-08-10T09:30Z, hash: a97aabb957d58bc97d2d4ccd1cd3d59974c8e4f566a8e094daf3596f2d127d32, reason: FR-4护栏句事实纠错(用户随设计批准授权)}
2026-08-10T17:08:24 set frozen.contract.hash=630277ca11c256df600752cf2d49bbb1eb36fbe2c845fe9044a22acd94cd60d9
2026-08-10T17:08:24 set frozen.contract.based_on=a97aabb957d58bc97d2d4ccd1cd3d59974c8e4f566a8e094daf3596f2d127d32
2026-08-10T17:08:24 set approvals[+]={point: contract, at: 2026-08-10T09:30Z, hash: 630277ca11c256df600752cf2d49bbb1eb36fbe2c845fe9044a22acd94cd60d9}
2026-08-10T17:08:24 set pending=
2026-08-10T17:08:24 s2a 冻结完成:PRD 重冻结(FR-4纠错)+design/contract 冻结,based_on 链闭合
2026-08-10T17:08:24 set stage_status=done
2026-08-10T17:08:24 set stage=s2b
2026-08-10T17:08:24 set stage_status=running
2026-08-10T17:16:19 用户拍板三项:①人设文案=版本A标准严格;②中英配比=候选全不适配,用户自述初级学习者尚无法英语交流,定向为教学阶段模式(中文主导讲解+英语练习素材,渐进提升英语占比),具体策略文本PM起草待终确认;③语言段冲突=本次改为模板可覆盖(走FR-4预留升级路径,默认模板仍中文,护栏句独立段不变),需回改PRD/design/contract并重冻结
2026-08-10T17:17:26 s2b首轮拆卡完成(4卡/12FR零空洞/21用例全落,占位符与互斥自检过);拆卡独立发现同一语言段冲突按纪律停下,用户拍板已递达恢复轮纳入。追加并入s2a修订批:INV-2依赖方向落点(自检归config.py)、design引用错位(SA-15→SA-18/补§测试策略)、用例口径21非17。T-4手工前置待办:用户须手工在server/evals/fault.env加DUAL_BRAIN_ENABLED=true(s5前)
2026-08-10T17:23:58 set grade=L3
2026-08-10T17:23:58 用户拍板:STT语言风险解法=引入AssemblyAI STT(用户亲测中英文识别均可,官方pipecat配置文档 https://www.assemblyai.com/docs/voice-agents/pipecat-universal-3-5-pro);陪练模板用assemblyai,默认模板不动。定级升L3(命中'引入新外部依赖服务'触发器,升级自主):s5变异抽样上限5→8。待办链:架构核实pipecat本地版本AssemblyAI服务并修design/contract→PM改FR-5白名单+出合成文案预览→卡增补→重冻结链+闸门
2026-08-10T17:31:27 架构R2落盘:AssemblyAI实测核verified(1.6.0有服务/零新包/无语言锁/原生code-switch),契约+SA-23,dry-run 19机检+4manual过;新限制R-14(TTS仍中文,英语句朗读质量SA-19实测)/R-15(无模板级换AssemblyAI模型旋钮)。派单方拍板:pyproject声明assemblyai extra=是;既有测试授权白名单3处=确认。用户手工待办+1:ASSEMBLYAI_API_KEY入secrets与server/.env(s5前)。串行进PM轮(FR-5白名单+合成文案预览)
2026-08-10T17:33:15 用户提供ASSEMBLYAI_API_KEY,已写入secrets唯一事实源+server/.env(均不入库),REST只读实测200有效;手工待办清单剩:fault.env加DUAL_BRAIN_ENABLED=true(s5前)
2026-08-10T17:39:20 用户最终确认陪练模板终版合成文案(research/tutor-persona-final.md ①节,2026-08-10):FR-7判据二收口,IDENTITY_ENGLISH_TUTOR_SECTION与LANGUAGE覆盖值以该文档逐字为准,G0外部门解除;文案侧零待定项
2026-08-10T17:41:59 set stage_status=gate_failed
2026-08-10T17:41:59 s2b排干闸门:gc=10(partial过) pc=8红——T-1/T-2/T-3命中占位符「同上」lint;next_action=修复(回派拆卡agent就地展开,只传BLOCK清单)
2026-08-10T17:43:17 set frozen.prd.hash=29320b221abd3aabba307e88facfdcbb848f87ff2946adb63fd40d2d4132a98f
2026-08-10T17:43:17 set approvals[+]={point: prd-refreeze2, at: 2026-08-10T11:05Z, hash: 29320b221abd3aabba307e88facfdcbb848f87ff2946adb63fd40d2d4132a98f, reason: 语言段可覆盖+FR-5白名单assemblyai+FR-7终版文案,均经用户逐项拍板}
2026-08-10T17:43:18 set frozen.contract.hash=3597903221a54651fbba6bf49137c6413bdbff2cd23b35634c3e493f10177046
2026-08-10T17:43:18 set frozen.contract.based_on=29320b221abd3aabba307e88facfdcbb848f87ff2946adb63fd40d2d4132a98f
2026-08-10T17:43:18 set approvals[+]={point: contract-refreeze, at: 2026-08-10T11:05Z, hash: 3597903221a54651fbba6bf49137c6413bdbff2cd23b35634c3e493f10177046, reason: R1语言段+R2 assemblyai修订,dry-run 19机检+4manual}
2026-08-10T17:43:18 set frozen.tasks.hash=be39bb690c5963fcb1d4429d6ca98766d52b8a415ec310213717792491a2621a
2026-08-10T17:43:18 set frozen.tasks.based_on=3597903221a54651fbba6bf49137c6413bdbff2cd23b35634c3e493f10177046
2026-08-10T17:43:18 s2b闸门绿(gc=10 partial过/pc=0):任务卡冻结(4卡/FR零空洞/SA-01..23全落/15独占路径0重叠);T-2→T-3已知红态口径=派单方确认连续落地不设放行闸;冻结链prd→contract→tasks闭合
2026-08-10T17:43:18 set stage_status=done
