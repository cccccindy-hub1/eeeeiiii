# GroundedReview Wave-2 离线阶段独立评审（Task 10）

- Spec：[spec.md](spec.md)；任务：[tasks.md](tasks.md)
- 评审范围：Task 1–10 全部离线产物（Task 11 付费 Pilot 仍 blocked，不在本次评审范围）
- 评审方式：评审动作在实现完成后进行，所有结论以**重跑/重读产物**为准，不采信代码注释自述；selfcheck 以实际退出码为准，数字以从产物重新计算为准。
- 日期：2026-10-21

## 1. TR-10.4 构念效度自评（AC-W2-12，rubric 1–5）

### 自评结论：**4 / 5（达到 ≥4 通过线）**

### 1.1 评分锚点对照

| 锚点 | 要求 | 本次实现的落点 |
|---|---|---|
| 1 | 条件 gold 仍可被隐藏标签/模型输出污染，或分歧不可解释 | 不成立。`gold_w2` 签名经 `check_signature_clean()` 断言，禁止 patch_correct/merge_acceptable/label_class/decision/parsed/answer/model/gold/scenario/response/output 等标签与模型输出令牌入签；标签无关性另有 scramble 对照断言（selfcheck w2-1） |
| 3 | 主要通道覆盖，但存在一类证据可见性靠人工判断 | 已超过。五条件 × 双通道（O 验收、P 症状）的可见/可裁决/可获取状态全部由 [visibility.py](../../stance_pilot/evidence/visibility.py) 机械投影，模拟器投影与真实 HTTP 会话逐字段交叉（selfcheck w2-3，tempfile 副本起 server，零污染源 store） |
| 5 | 全部事实可见性机械可审计、分歧逐条可解释、grounding 验证无灰色地带 | 前两项满足；grounding 真值表（w2-5）本身无灰色地带，但其**经验校准**尚未在 live v2 输出上观察（Pilot blocked），故不给满分（见 §1.3） |

### 1.2 支持 4 分的证据

1. **制度受限弃权 vs 可归责弃权被机械区分**：
   - [wave2_decisive_visibility.json](../../stance_pilot/evidence_store/wave2_decisive_visibility.json) 覆盖全部 6 个 oracle REJECT 夹具 × 5 条件；`blameworthy_abstain` 定义为「强制 REJECT 的通道在该条件下 rendered/adjudicated/obtainable 时，NEED 才可归责」。
   - 点查 M4（incomplete_decisive_bad）：T2D/Strict 下 O=`not_visible`/`hard_blocked`、P 极性 gone → NEED **不可归责**；T3A 下 O=`obtainable` 且有 executed failure → NEED 可归责；Escalate 下 O=`obtainable_with_reason` → 可归责。
   - 点查 wrong_patch（症状 persists）：即使 O 在 T2D/Strict 被 withholding，P 在静态块可观察 → T2D/Strict 的 NEED 仍可归责（20 个 blameworthy cell 含此两行）。不对称规则在双通道层面自洽，无漏归责。
   - 反例边界 stale_persists 的 T2A：condition_gold=REJECT 但 P_obs=False、O 仅 presented，审计正确地未标 blameworthy（呈现面 REJECT 可支持，但拿不到可裁决通道）。
2. **分歧逐条可解释**：22 行 gold × 5 条件共记录 22 条非空 oracle↔condition 分歧（T2D 11、Strict 11、T2A 11；Escalate/T3A 恒等 oracle，断言保证），每条带 `condition_basis` 文本与 `oracle_condition_divergences` 枚举；分布与转移在 [wave2_offline_acceptance.json](../../stance_pilot/evidence_store/wave2_offline_acceptance.json) item3 复算一致（如 T2A：NEED→ACCEPT×7、NEED→REJECT×2、REJECT→ACCEPT×1、ACCEPT→NEED×1）。
3. **泛化保守可被缺口分类识别**：[gap_w2.py](../../stance_pilot/evidence/gap_w2.py) 四类 grounding（verified_gap / claimed_but_unverified / decisive_in_hand_but_abstained / unspecified）真值表全断言（w2-5）；v2 五枚举 stale/linkage_mismatch/coverage_incomplete/contradiction/unspecified 与端点裁决的映射无自由裁量：静态条件下声明 stale/linkage/coverage 一律 claimed_but_unverified，contradiction 一律 decisive_in_hand_but_abstained。
4. **非干涉保证评分不被隐藏答案泄漏**：World A/B 真实扰动隐藏 Acceptance Evidence、保持 Diagnostic Evidence 不变，Strict 面语义一致性由 w2-8 断言；Smoke 服务端审计实际 0 次 strict 泄漏（memory 记录的「无 403 ≠ 有泄漏」结论与审计事件计数一致）。
5. **确定性/可复算**：fresh `build_gold_rows()` 与冻结 22 行逐行相等，sha256=`28cc59d…38d01`；影子表 45 live cell 双口径重算（seed=7、issue-cluster、n_boot=10000）可复现。

### 1.3 不给 5 分的理由（诚实局限）

- **L1（构念约定，未经验校准）**：Escalate 按「可获取（潜在）」计入 condition_gold（spec Open Question Q1），是机械执行的制度假设，但「升级必被授予且必带来有用证据」尚未经 live v2 行为验证；Smoke 的 v1 观察是 Escalate 减少 NEED 但引入 unsupported REJECT，提示潜在语义与实际行为可能系统性偏离。
- **L2（经验覆盖缺口）**：gap 四类 grounding 只在脚本真值表与 65 个 wave2 mock cell 上验证；真实模型 v2 输出的类别分布、unspecified 占比要到 Task 11 才能观测，真值表「无灰色地带」不等于实测无灰色地带。
- **L3（外部效度，非构念缺陷）**：夹具实际覆盖 10 个 issue（新增仅 4 个），issue-cluster CI 在 n=4 新 issue 上必然很宽；本评审只确认构念一致性，不主张结果可推广。
- **L4（边界规则的可争辩性）**：「active 条件下可观察的 persists 症状本身即 decisive-in-hand，与 consistency verdict 无关」是一条研究设计选择而非逻辑必然；已在 w2-5 负例（polarity=gone + consistent 才得 claimed）中固定语义，但替代定义（要求端点确认）在未来论文中需作为敏感性分析披露。

以上四项均不构成评分污染或不可解释分歧，故 4 分；待 Pilot 后 L1/L2 可重评。

## 2. 验收条件核对

| AC | 类型 | 结论 | 主要证据 |
|---|---|---|---|
| AC-W2-1 | rule | PASS | [wave2_freeze_audit.json](../../stance_pilot/evidence_store/wave2_freeze_audit.json)：10 个冻结文件字节全等；baseline 213 条仅 audit.jsonl/fixtures_meta.json 漂移且证明 benign；快照窗 350→425，349 unchanged、0 removed、新增全部 wave2_/fix_w2_ 命名空间 |
| AC-W2-4 | rule | PASS | visibility 五条件矩阵入每行 gold；HTTP 交叉 w2-3 零分歧；Escalate/T3A 恒等 oracle 断言；22 条分歧均有 basis |
| AC-W2-5 | rule | PASS | 6 个 decisive 夹具 × 5 条件审计齐全，M4/wrong_patch/stale_persists 点查与矩阵一致 |
| AC-W2-6 | rule | PASS | w2-5 gap 真值表全绿（含静态无工具、active 取得裁决、矛盾负例） |
| AC-W2-10 | rule | PASS | Python 3.13 全量 selfcheck exit 0：既有 11 check + 11 个 wave2 check 全绿；65 个 wave2 mock cell failed=0、cost=$0；零 LLM key 读取 |
| AC-W2-11 | rule | PASS | [wave2_offline_acceptance.json](../../stance_pilot/evidence_store/wave2_offline_acceptance.json) 七项齐备，9 项 cross_checks 全 true |
| AC-W2-12 | rubric | PASS（4/5） | 本文件 §1 |
| AC-W2-2/3/7/8/9 | rule/mixed | PASS（随 Task 2–9 冻结，selfcheck w2-1/2/4/6/7/8/9 回归覆盖） | selfcheck 输出、wave2_shadow_wave1_scores.json |

## 3. AC-W2-11 七项数字独立复核要点

1. **Issue 口径**：truth.jsonl 历史全集 8 issue；本次选择池 206 行/75 instance，七道静态 gate 后确定性选中 4 个新 issue（#12419/#12481/#12489/#13091）；**夹具实际服务口径** wave1 6 issue + 新增 4 = 10 issue。spec 文字「8→12」为历史全集口径，汇总 JSON 已显式注明两套口径，未用 12 冒充夹具数。
2. **计数**：patches/ 33 个模型补丁文件覆盖 12 issue、12 个 maintainer test_patch；probes_wave2/ 实测 4 个探针；wave2 构建夹具 13 个（w2_valid×6、w2_stale×2、w2_decisive_bad×2、w2_stale_bad×1、w2_stale_persists×1、w2_incomplete_good×1），blocked 为空；served gold 22 行、22 个 artifact、16 个 distinct patch_sha256。
3. **condition_gold 分布**：T2D 与 Strict 同为 NEED 20/REJECT 2（agree 11/22），Escalate/T3A 同为 ACCEPT 7/NEED 9/REJECT 6（agree 22/22），T2A 为 ACCEPT 14/REJECT 7/NEED 1（agree 11/22）——与 handoff 勘察数逐一相等。
4. **Pilot 规模**：22×5 = **110 cell**，聚合 condition_gold：ACCEPT 28 / NEED 59 / REJECT 23。
5. **预算**：Smoke 实测 45 cell、行级求和 $0.203015（审计累计 $0.203016，差 $1e-6 为行级舍入，已双列）、单价 $0.00451144/cell；110 cell 线性外推 **$0.4963 < $1 硬门**；pre-call BudgetGuard + fail-stop + `--max-tool-turns 12` 沿用。估算假设（wave2 active 单元占比更高、v2 schema 更长）已在文件中标注。
6. **v1↔v2 差异**：schema（三判决 + evidence_gap 五枚举 + 三类派生 grounding）、prompt（p3-ternary-v1/v2）、gold（单 gold → oracle/condition 双通道 + 非对称规则）、metrics（冻结 v1 官方分；wave2 双口径 + issue-cluster bootstrap seed=7/10000；影子表 official=false）四层差异均登记。
7. **一致性**：所有数字由脚本从产物实时计算，9 项交叉断言全过。

## 4. 评审发现

### 4.1 已闭合问题（实现期发现并修复，复核确认）

- F1（已修复）：静态 Diagnostic Tier 症状极性反转 bug（Phase 2 run1），wave2 w2-5 增加极性守卫，反转 run 单独归档排除。
- F2（已修复）：gold 冻结哈希重算误用裸 `derive_rows`，正确路径为 `wave2_gold.build_gold_rows()`（含 visibility/decisive 三列）；w2-1 已固定。
- F3（已修复并解释）：既有 HTTP selfcheck 对真实 store 起 server 会 append audit.jsonl，导致 baseline manifest 漂移；w2-9 已将 audit.jsonl/fixtures_meta.json 列为 known_benign 并有窗口内 pre==post 证据，wave2 交叉检查改用 tempfile 副本。
- F4（已修复）：矛盾真值表语义曾错误依赖 consistency verdict；现行规则与负例固定在 w2-5。

### 4.2 残留风险（不阻塞离线验收，转入 Task 11 守门）

- R1：$0.496 为线性外推，wave2 主动取证单元可能抬高 tool-turn 成本；硬门已设 $1 且 pre-call 保守上界守卫，预计可 fail-stop。
- R2：Phase 2 历史上出现过两次协议非合规 INVALID 输出碰巧命中真值；Task 11 必须继续把 INVALID 单列、禁止按巧合命中计正确。
- R3：边界 stale 夹具曾出现「遵循证据信号但偏离预注册 ground truth」；condition_gold 已缓解制度面错配，但若 Pilot 再现，按异常原始记录、单独报告，不得中途改设计（硬约束）。

## 5. 评审结论

- 离线阶段（Task 1–10）**通过独立评审**：selfcheck exit 0、冻结集零改动、双通道 gold 构念效度 4/5、AC-W2-11 七项数字与产物一致、预算估算在硬门内。
- **Task 11（正式 DeepSeek Pilot，≤$1）维持 blocked**，须用户再次书面批准后方可执行；开跑前置条件：$1 硬门与 pre-call guard 复核、110 cell 独立 session、版本身份四元组（Gold SHA / Fixture Manifest Hash / Prompt Version / served model id）逐行落盘、Strict/Escalate 服务端审计沿用。
