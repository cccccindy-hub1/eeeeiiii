# GroundedReview Wave-2 — Task 10 离线扩样：条件化金标准、证据缺口分类与 4 个新 Issue 产品需求文档

## Overview
- **Summary**: 在不改动 Phase 1/2/3 任何文件（含金标准、夹具、Prompt v1、45 个 Smoke 结果）的前提下，离线完成 Task 10 的第一阶段：(1) 将三态金标准拆分为 **oracle_gold**（全部可信证据下最适当判决，双通道：验收通道 + 诊断症状通道）与 **condition_gold**（在某实验条件的可见/可获取证据下能够被支持的最适当判决），并以机械的「条件 × 证据表面」可见性矩阵推导，禁止用模型输出反推标签；(2) 审计全部 partial-but-decisive 夹具（含 Wave-1 M4）决定性失败证据在五个条件下的实际可见性；(3) 为 NEED_EVIDENCE 增加**有证据 grounding 的缺口分类**（stale / linkage_mismatch / coverage_incomplete / contradiction / unspecified），分类必须由该条件下已呈现或已裁决的证据验证，不仅凭模型自述；(4) 从 `Lego-X/SWE-Review-Bench` 新增 **4 个独立 issue**（不含现有 8 个），经验性真值标注 + 真实 pytest 构建 GOOD/BAD × VALID/INVALID 镜像（优先 VALID / STALE / INCOMPLETE / PARTIAL-BUT-DECISIVE）；(5) 冻结 Wave-2 金标准、扩展 selfcheck、出新旧对比与未来 Pilot（≤$1，暂不执行）预算报告。
- **Purpose**: 解决 Smoke Test 暴露的两个测量效度威胁——①统一 gold 跨条件比较决策适当性不公平（M4 的决定性失败证据在 T3D-Strict 下不可见，NEED 不应计为可归责的过度弃权）；②NEED_EVIDENCE 无差别计分无法区分「识别了具体缺口」与「学会保守总没错」。
- **Target Users**: 研究者本人；未来跨模型实验。
- **Scope Gate（用户 2026-10-20 批准边界）**: 本 spec **只批准离线构建与验证，禁止任何付费 LLM API 调用**；不增加新 Reviewer 模型；离线报告通过后，正式 DeepSeek Pilot（≤$1）与跨模型实验另行批准。

## Goals
- 同一夹具在五个条件下同时具有 oracle_gold 与 condition_gold；两套标签都只由可信证据事实 + 该条件的证据可见性机械推导，纯函数、确定性、可冻结；标签函数签名不得接收 patch_correct / merge_acceptable / 任何模型输出。
- 输出「证据可见性矩阵」：夹具 × 条件 × 证据事实（症状、linkage、freshness、coverage、逐测试验收结果）的可呈现/可裁决/可获取（含理由门控升级）状态，作为 condition_gold 的推导依据并接受 selfcheck 逐格审计。
- NEED_EVIDENCE 的缺口分类与 grounding 验证器：区分 `verified_gap`（模型指出的缺口在该条件下确实被已呈现/已裁决证据支持）、`claimed_but_unverified`（模型声称了该条件无法核验的缺口，如静态条件声称 stale）、`decisive_in_hand_but_abstained`（可访问证据已支持 REJECT 却弃权）、`unspecified`（无具体缺口的泛化弃权）。
- 4 个新 issue、目标 12–16 个新夹具（每 issue ≥1，镜像优先四型），全部 fix_w2_ 新命名空间；新旧 issue=12、夹具总数=21–25（最终按构建实际计数）。
- Wave-1 的 45 个 Smoke 结果**不重打分、不改动**；另出一份明确标注为「v2 语义影子重算」的派生对照表，展示若在新语义下旧结果的双重得分，仅供版本差异分析。
- 全部离线验证通过 selfcheck（3.13）与真实 pytest 构建（3.9 镜像沿用现有解释器纪律），零 LLM 费用。

## Non-Goals
- 不执行正式 Pilot（未来 ≤$1，另行批准）；不发生任何 DeepSeek/其他 LLM 调用。
- 不新增 Reviewer 模型；不改 Phase 1/2 二元协议、metrics2、Phase-3 v1 提示词与 `phase3_gold.jsonl`。
- 不用新金标准追溯改写 Wave-1 官方结果；影子重算表是独立派生分析，不进任何官方指标文件。
- 不提供「重新执行测试」工具；stale 的正确判决仍是无法补新鲜证据（按可见层级各表）。
- 不依据模型未来表现反向修改任何 gold（沿用 AC-12 精神）。
- 不追求每 issue 四型镜像齐全：确定性选样/构建失败时按 blocked 如实回报候选筛选过程，不降低构造标准。

## Background & Context
- Smoke（9 fixtures × 5，45 cells）关键现象：T3D-Strict 9/9 全弃权（其 66.7% 适当率全部来自 NEED）；M4 除 T3A-T 外全 NEED；T2A-T 持验收级静态证据也 9/9 弃权；Escalate 解锁 contradictory 的正确 REJECT，却对 incomplete/incomplete_good 无据 REJECT。这些现象跨条件比较的前提是 gold 公平——而 M4 的已执行 f2p 失败在 Strict 下被策略硬隔离（403）、在 T2D 下从不可见，统一要求 REJECT 不公平。
- 现有代码事实（2026-10-20 勘察确认）：
  - 真值经验来源：`truth.jsonl` 19 补丁 / 8 issue，标签来自本地执行——手写 symptom probe（[probes.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/probes.py)，issue 文本派生）+ canonical pytest 批次（3.9），`merge_acceptable`/`issue_addressed`/`regression_free_scoped` 均本地派生并落 `label_provenance`，无模型参与。
  - 数据来源：[cache_raw.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/cache_raw.py) 从 HF `Lego-X/SWE-Review-Bench` 拉取 sympy 行；现有 raw_rows 21 行 / 8 issue；新 issue 走同一缓存管线（数据下载，非 LLM）。
  - 条件表面：症状探针五条件可见（T2D/T2A 静态文本块，T3D symptom 日志 + strict consistency 诊断裁决）；verify/freshness/coverage 三个裁决端点仅主动臂存在（[server.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/server.py) L158-245）；逐测试验收结果仅 tier A 呈现/可裁决，D+strict 硬隔离 403，D+escalate 理由门控后可获取（L247-303, L372+）；D 投影以 attestation 声明值替换执行计数，使 incomplete 在静态 D 完全不可察觉（[views.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/views.py) L58-120）。
  - 现 gold（[ternary.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/ternary.py)）只建模验收通道（fail_to_pass/pass_to_pass_scoped 已执行结果）；症状极性（wrong_patch 夹具 post=false）从未进入 gold_decision。
  - 构建原语：[phase3_build.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/phase3_build.py) 已具备 stale 树、异源 artifact、canonical 批次诚实重放（M3/M4）原语与确定性选样审计；新 wave 可复用。
- 关键既有冻结值：`phase3_gold.jsonl` sha256=`dbebcfc311a2402528ceb745c33fc03613e0f433dfda82a779886591f40e45d7`；prompt v1 版本串 `p3-ternary-v1`（5 个 per-condition fingerprint 已随 Smoke 结果落盘）。

## 关键设计决策（DW2，审批时可否决）

- **DW2-1 双通道 oracle_gold（v2）**。可信证据有两个相互独立的判决通道：
  - 验收通道：签名 artifact 的已执行 f2p/p2p 结果，适用性要求 linked ∧ fresh；充分成功额外要求 complete ∧ 执行数>0 ∧ 零失败（沿用 D3）。
  - 诊断通道：issue 派生 symptom probe 的 pre/post 极性。补丁后症状仍复现（post_patch_passed=false，且 pre=false 排除真空探针）对目标补丁构成**适用的决定性失败**（症状探针直接针对被审 issue，不依赖 artifact linkage；注册正向声明下 consistency=contradicted）；症状消失只构成 issue 级支持，绝不构成验收通过。
  - 规则（纯函数）：
    ```
    oracle_gold(*, linked, fresh, complete,
                acceptance_failure, acceptance_success, symptom_persists):
        if (linked and fresh and acceptance_failure) or symptom_persists:
            return REJECT
        if linked and fresh and complete and acceptance_success and not symptom_persists:
            return ACCEPT
        return NEED_EVIDENCE
    ```
  - 后果（已知并接受）：Wave-1 wrong_patch（post=false）在 v2 双通道 oracle 下为 REJECT（v1 为 NEED）。`phase3_gold.jsonl` 与 Smoke 官方结果**保持冻结不变**；差异只在独立影子表中披露。
- **DW2-2 condition_gold = 可见性投影后再求 gold**。对每条件先做「证据表面投影」（模拟该条件服务端/静态块实际呈现或可经授权工具获取的事实），再套用与 oracle 相同的 gold 规则；输入仍只有证据事实，无模型输出。可见性约定（逐字段由 selfcheck 对照真实服务端响应审计）：

  | 事实 | T2D-T | T3D-Strict | T3D-Escalate | T2A-T | T3A-T |
  |---|---|---|---|---|---|
  | 症状极性 P（呈现/可裁决） | 呈现 | 可裁决（consistency 诊断）+日志 | 同 Strict | 呈现 | 可裁决+日志 |
  | linkage 裁决 L | 否（仅身份字段，非裁决） | verify 可裁决 | verify 可裁决 | 否 | verify 可裁决 |
  | freshness 裁决 F | 否 | freshness 可裁决 | freshness 可裁决 | 否（run_tree 不在静态块） | freshness 可裁决 |
  | coverage 裁决 C | 否（D 投影以声明值替换，缺口不可察觉） | coverage 可裁决 | coverage 可裁决 | 否（无声明集合基线） | coverage 可裁决 |
  | 验收逐测试结果 O | 不可见 | 硬隔离（403，不可获取） | **理由门控后可获取**（可获取即视为可支持，获取行为另计量） | 完整呈现 | 可获取（tier A 无限制） |

  - 约定要点：①身份字符串（patch_sha256/base_commit/run_tree 的原始值）在静态块出现但**不构成裁决**（块标题明示 linkage not yet verified；模型无 SHA-256 计算能力），condition_gold 只采信官方裁决或直接呈现的判决内容；②Escalate 的 O 按**可获取**计入（condition_gold 描述该证据制度下「能够被支持」的判决，这正是跨条件比较公平性所需；实际是否升级、升级成本与升级后判决在行为层另行报告）；故 condition_gold(T3D-Escalate)=oracle_gold、condition_gold(T3A-T)=oracle_gold 恒等，selfcheck 须断言；③T2A-T 按「记录所呈现内容」求 gold（stale_bad 的陈旧记录内含 2 个真实失败 → condition 可 REJECT 而 oracle=NEED；stale(GOOD) 陈旧记录全过 → condition 可 ACCEPT 而 oracle=NEED），这类 oracle/condition 分歧正是要测量的制度偏差；④T2D-T 下症状消失且无验收通道 → valid 的 condition_gold=NEED（制度上无法支持 ACCEPT），Smoke 中 T2D 对 valid 的 NEED 在 v2 下从过度弃权改为适当弃权。
  - 只对 oracle_gold == condition_gold 的夹具集直接报告跨条件 Decision Appropriateness 主对比；分歧集单列「制度受限弃权/制度受限决定」分析（用户要求：只有两者一致时才可直接比较）。
- **DW2-3 缺口分类与 grounding 验证（不凭自述）**。
  - 输出 schema（prompt v2，仅 Wave-2）在 NEED_EVIDENCE 时新增结构化字段 `evidence_gap ∈ {stale, linkage_mismatch, coverage_incomplete, contradiction, unspecified}`，保留自由文本 `missing_evidence`。
  - 验证器纯函数 `classify_abstention(condition, gap, presented_facts, tool_verdicts)`：
    - `stale` 已验证 ⇔ 该 cell 终判前 freshness 端点已返回 fresh=false（静态条件**永远无法验证** → claimed_but_unverified）；
    - `linkage_mismatch` ⇔ verify 返回 linked=false（静态无法验证）；
    - `coverage_incomplete` ⇔ coverage 返回 complete=false（静态无法验证）；
    - `contradiction` ⇔ 可访问证据存在冲突（consistency=contradicted 或症状 post=false 且正向声明）；此情形本身支持 REJECT，若模型仍 NEED → 记 `decisive_in_hand_but_abstained`（识别了决定性证据却弃权，独立错误类）；
    - 其余/空/无对应已裁决证据 → `unspecified`（泛化弃权）。
  - 行为指标主表：`grounded_abstain_rate`（verified_gap 占 NEED 比）、`unverified_claim_rate`、`blanket_abstain_rate`（unspecified 占 NEED 比）、`decisive_in_hand_abstain` 计数。
- **DW2-4 新 issue 选取与经验真值**。4 个新 instance_id 必须不在现有 8 个内；确定性选取规则（HF 候选按 instance_id 排序后依次筛）：sympy/sympy、有 ≥2 个不同 generator 候选补丁、test_patch 可干净应用、canonical 批次可在 3.9 + pytest 8.4.2 本地执行。每 issue 手写 probe（issue 文本派生，pre 必须失败、post 行为用于标注），沿用经验标签管线产出 patch_correct（审计列）。镜像优先序：VALID（GOOD, L/F/C, 全过）、STALE（GOOD×stale 与/或 BAD×stale）、INCOMPLETE（GOOD/BAD × complete=false 无失败）、PARTIAL-BUT-DECISIVE（BAD × complete=false 保留真实已执行失败）。每型至少 1 个、总量 12–16 为目标；选样/构建失败按 blocked 回报，不硬凑。
- **DW2-5 独立命名空间与冻结**：新原始行 `wave2_raw_rows.jsonl`；新探针写入 `evidence_store/probes_wave2/`；新夹具 `wave2_fixtures.jsonl`（id 前缀 `fix_w2_`）；新金标准 `wave2_gold.jsonl`（含 oracle + 五条件 condition gold + 可见性矩阵字段 + 缺口期望）；新 meta `wave2_fixtures_meta.json` 与新审计 `wave2_audit.jsonl`（不触碰 phase3 的 fixtures_meta/audit）；新代码模块 `evidence/gold_w2.py`、`evidence/wave2_build.py`、`evidence/metrics_w2.py`、`evidence/visibility.py`（可见性投影模拟器）；selfcheck 增量；ternary.py/phase3_run.py/prompts.py 仅允许**追加** v2 能力且 v1 行为/指纹不变（如追加风险大则 v2 提示词放新模块，优先新模块）。
- **DW2-6 未来 Pilot 只做定义不执行**：正式 Pilot 预算硬门 ≤$1（fail-fast + 前置 BudgetGuard 沿用 Task 9 实现），按 **issue cluster bootstrap**（重采样单位=issue，非夹具；seed 固定、n=10000）报 CI；本 spec 只交付预算估算与门控定义，不发起调用。

## Functional Requirements
- **FR-1（可见性投影模拟器）**：`evidence/visibility.py` 给定（fixture 行、store 签名 record、attestation、symptom、condition）→ 返回该条件的 `presented_facts`（P/L/F/C/O 的可呈现/可裁决/可获取布尔与取值），逻辑与 server/views 的真实投影/策略**同源或逐字段对齐**；selfcheck 对每夹具×每条件用真实 HTTP 会话响应与模拟器结果交叉核对（含 strict 403、escalate「可获取但未获取」的状态语义）。
- **FR-2（双通道 gold 纯函数）**：`evidence/gold_w2.py` 实现 DW2-1 规则；oracle 与 condition 两个推导入口；inspect 签名断言无 patch_correct/merge_acceptable/model 字段；同一事实组传/不传标签输出一致；canonical 序列化、重复生成逐字节一致。
- **FR-3（M4 类可见性审计）**：对所有 decisive_failure=true 夹具（Wave-1 M4 + Wave-2 新件）输出表：决定性失败证据类型（验收 O / 诊断 P）× 五条件的可见/可裁决/可获取状态，并给出每条件的 condition_gold；明确「该条件下 NEED 是否可归责」。
- **FR-4（缺口分类验证器）**：DW2-3 纯函数 + 单测真值表（每条件 × 每 gap 类，含静态 unverifiable、contradiction→decisive_in_hand、unspecified）。
- **FR-5（新 issue 数据与标注管线）**：扩展缓存脚本支持显式 id 列表与输出路径；确定性选样并落 `wave2_selection_audit.json`（候选清单、纳入/排除理由）；每 issue 手写 probe 入 `probes_wave2/`，probe 审查（pre 失败约束、只用公开 API）。
- **FR-6（真实构建与镜像）**：3.9 真实 pytest canonical 批次 + 复用 stale/wrong_patch/batch-replay 原语产出四型镜像；每产物签名/log digest/attestation 完整，服务端四表面核验与 expected 一致；构建失败 blocked 回报。
- **FR-7（Wave-2 gold 冻结）**：`wave2_gold.jsonl` 每行含 fixture 标识、patch_correct（仅审计）、双通道事实、oracle_gold、condition_gold×5、可见性矩阵 hash、basis；生成确定性，首版生成即冻结并记录 sha256。
- **FR-8（Prompt v2 追加）**：v2 三态提示在 NEED 时要求结构化 `evidence_gap`；版本串 `p3-ternary-v2`；v1 builder 与 5 个 v1 fingerprint 字节不变（selfcheck 回归断言）。
- **FR-9（Wave-2 指标，离线）**：`evidence/metrics_w2.py` 对桩结果输出：oracle 与 condition 双口径 Decision Appropriateness（分母 parseable）、E2E、INVALID/AMBIGUOUS 单列、oracle==condition 可比集与分歧集分区、缺口分类四率、升级行为与成本字段（运行时填）、静态/主动分列、**issue cluster bootstrap CI（以 issue 为重采样单位）**；对 Wave-1 45 行生成独立 `wave2_shadow_wave1_scores.json`（v2 双通道语义影子表，文件内显式标注 non-official，不改写官方文件）。
- **FR-10（runner 离线就绪，不付费）**：phase3_run（或 wave2 runner）支持 --gold/--prompt-version/--gap 字段捕获的追加能力；`--mock` 对新夹具全链路（含 v2 schema 五类 NEED 输出）零费用跑通；BudgetGuard 与版本身份字段沿用。
- **FR-11（selfcheck 扩展）**：可见性矩阵与真实 HTTP 交叉核对、双通道 gold 真值表+标签无关+确定性、M4 类审计表、缺口验证器真值表、新夹具完整性四表面、v1 指纹冻结、非干涉 World A/B 回归、历史哈希（phase1/2/3 冻结集零改动）、零网络 LLM 断言。
- **FR-12（扩样报告）**：新旧 issue 数、新旧补丁/探针/夹具数、各条件 condition_gold 分布（含与 oracle 一致/分歧计数）、预期 Pilot cell 数与每条件分布、≤$1 预算估算（以 Smoke 实际 $/cell 与 token/cell 为基线）、v1↔v2 版本差异报告（schema/提示词/gold 语义/指标差异清单）。

## Non-Functional Requirements
- **NFR-1（不可变）**：Phase 1/2/3 的结果、指标、夹具、artifact、gold、v1 prompt 一律不改；store 内仅追加 fix_w2_/新 probe/新日志；新 meta/audit 文件独立。
- **NFR-2（全离线）**：除 HF 数据集下载与 git 取新 base commit 的**数据面网络**外无外部调用；零 LLM key 使用；全部验收本地完成（3.13 selfcheck；3.9 pytest 构建）。
- **NFR-3（确定性）**：选样、probe→标签、gold、影子重算均可复现；固定排序与 bootstrap seed。
- **NFR-4（Windows/PowerShell 5）**：兼容现有执行纪律（uv、`.cmd`、不用 `&&`）。
- **NFR-5（诚实统计）**：n 以 issue 计（新 issue=4，属描述性 Pilot）；bootstrap CI 标注重采样单位与小样本限制。

## Constraints
- **Technical**：仅 vendored/本地 git sympy 仓库执行；stdlib http；构建 3.9 + mpmath + pytest==8.4.2，服务/指标/selfcheck 3.13；新 base commit 的 git 可用性需在 Task 1 验证（不可用按 blocked 回报）。
- **Business（硬）**：本阶段任何 LLM API 调用一律禁止；未来 Pilot ≤$1 且另行书面批准；不新增模型。
- **Dependencies**：现有 evidence_store、phase2/3 build 原语、probes、server/views 策略、BudgetGuard、HF 数据集可达。

## Assumptions
- HF `Lego-X/SWE-Review-Bench` 可访问且含 ≥4 个满足 DW2-4 规则的新 sympy issue；候选补丁中可经验性选出 GOOD/BAD 镜像素材。
- 新 issue 的 base_commit 可由本地 sympy git 仓库获取（remote fetch 属数据面网络）；若 fetch 失败，按 blocked 处理并回报，不换用非经验标签。
- v2 双通道语义对旧 9 夹具的重算结果可全部由现有签名记录 + symptom 字段机械得到（无需重新执行）。

## Acceptance Criteria

### AC-W2-1：Phase 1/2/3 资产零改动
- **Type**: `rule`
- **Given**: Wave-2 离线工作全部完成
- **When**: 对冻结集（phase1/2 全部结果/指标/夹具 + `phase3_gold.jsonl` + 9 夹具清单 + 45 Smoke 结果 + v1 metrics + v1 prompt 代码路径与 fixtures_meta.json/audit.jsonl）做哈希审计
- **Then**: 全部字节不变；store 内新增对象仅 fix_w2_/新 probe/新日志命名空间；新 meta/audit 使用独立文件
- **Pass Condition**: 冻结集哈希前后一致，新增文件清单全部属 Wave-2 白名单
- **Evidence**: 前后哈希清单 + 新增文件分类表

### AC-W2-2：4 个新 issue 的经验性真值管线
- **Type**: `rule`
- **Given**: HF 候选集
- **When**: 确定性选样 + probe 编写 + 3.9 真实 pytest 执行
- **Then**: 4 个新 issue（与旧 8 不重叠）各有手写 probe（issue 文本派生、pre 失败、仅公开 API）、≥1 个经验标注补丁与完整 provenance；标签全部由 probe/pytest 本地结果派生，无模型输出参与（代码扫描 + provenance 字段断言）
- **Pass Condition**: 4 issue 全部建成并有 provenance；不足 4 时 blocked 回报候选筛选全表，不以弱候选充数
- **Evidence**: wave2_selection_audit.json、probes_wave2/、构建日志、truth_w2 行

### AC-W2-3：双通道 oracle gold 确定性冻结
- **Type**: `rule`
- **Given**: 全部新旧夹具的签名记录与 symptom
- **When**: 运行 gold_w2 生成
- **Then**: `wave2_gold.jsonl` 每行 oracle_gold 符合 DW2-1 真值表（含 wrong_patch 类症状持续→REJECT、M4→REJECT、valid→ACCEPT、stale/incomplete→NEED）；纯函数重复生成逐字节一致；标签无关性断言通过；sha256 落档
- **Pass Condition**: 真值表断言全绿、二次生成哈希相同
- **Evidence**: gold 文件、断言输出、哈希记录

### AC-W2-4：condition_gold 与可见性矩阵机械推导
- **Type**: `rule`
- **Given**: 每夹具 × 五条件
- **When**: visibility 投影 + gold_w2 推导
- **Then**: 每行含五条件 condition_gold 与可见性矩阵；模拟器结果与真实 HTTP 会话（strict/escalate/A 各一）的逐字段事实一致；Escalate/T3A 的 condition_gold 恒等于 oracle；T2D/Strict/T2A 的 oracle↔condition 分歧夹具被枚举并给 basis
- **Pass Condition**: selfcheck 逐格交叉核对零分歧（模拟器 vs 真实服务端）；恒等断言成立；分歧集非空且逐条有 basis
- **Evidence**: 矩阵产物 + selfcheck HTTP 交叉报告

### AC-W2-5：partial-but-decisive 可见性审计
- **Type**: `rule`
- **Given**: 所有 decisive_failure=true 夹具（含 Wave-1 M4）
- **When**: 运行审计
- **Then**: 输出每夹具决定性证据类型（O/P）在五条件下的可见/可裁决/可获取状态与 condition_gold，并标注该条件下 NEED 是否可归责（M4：T2D/Strict 下 O 不可见且症状消失 → NEED 不可归责；T3A 下可见 → 可归责；Escalate 可获取 → 可归责）
- **Pass Condition**: 审计表覆盖全部 decisive 夹具，结论与可见性矩阵一致
- **Evidence**: wave2_decisive_visibility 审计产物

### AC-W2-6：缺口分类 grounding 验证
- **Type**: `rule`
- **Given**: 构造的 NEED 输出真值表（五条件 × 五 gap 类 + 无工具情形）
- **When**: 调用分类验证器
- **Then**: stale/linkage/coverage 在静态条件一律 claimed_but_unverified；contradiction 映射 decisive_in_hand_but_abstained；无对应已裁决证据 → unspecified；主动条件终判前取得对应裁决才判 verified_gap
- **Pass Condition**: 真值表全部断言通过
- **Evidence**: selfcheck 用例输出

### AC-W2-7：镜像矩阵覆盖
- **Type**: `rule`
- **Given**: 4 新 issue 的经验标注补丁
- **When**: 真实 pytest 构建
- **Then**: VALID / STALE / INCOMPLETE / PARTIAL-BUT-DECISIVE 四型各 ≥1 夹具且 GOOD/BAD 镜像在可行处配对；新夹具总数目标 12–16；每件签名/digest/attestation 有效、服务端 verify/freshness/coverage 与 expected 完全一致
- **Pass Condition**: 四型齐全（不足者 blocked 记录候选筛选过程，不构成静默降标——但最终若某型为 0 且无 blocked 充分理由，本 AC 失败）
- **Evidence**: wave2_fixtures.jsonl、构建日志、selfcheck 四表面断言

### AC-W2-8：Prompt v2 追加且 v1 冻结
- **Type**: `rule`
- **Given**: v2 schema/提示词落地
- **When**: 文本/fingerprint 比对
- **Then**: v2 版本串 `p3-ternary-v2`，NEED schema 含 evidence_gap 五枚举；v1 builder 文本与 Smoke 落盘的 5 个 fingerprint 全部可复现不变；v1/v2 提示词不得互相污染
- **Pass Condition**: fingerprint 复算与 Smoke version 字段逐一相同
- **Evidence**: selfcheck 断言 + 新旧提示词 diff 报告

### AC-W2-9：双口径指标与影子重算
- **Type**: `rule`
- **Given**: 含已知标签的桩结果 + Wave-1 45 行
- **When**: 运行 metrics_w2
- **Then**: oracle/condition 双口径指标、可比集/分歧集、缺口四率、issue-cluster bootstrap（桩数据手算可核）全部正确；影子表对旧 45 行按 v2 重算（如 M4 在 T2D/Strict 下 condition 口径由过度弃权改适当弃权），文件显式标注非官方且不覆盖任何既有文件
- **Pass Condition**: 桩数据手算一致；影子表 45 行齐全且官方文件哈希不变
- **Evidence**: 桩对照核算 + wave2_shadow_wave1_scores.json

### AC-W2-10：全离线 selfcheck 与零 LLM 调用
- **Type**: `rule`
- **Given**: 全部 Wave-2 代码与夹具
- **When**: `uv run --python 3.13 python -m evidence.selfcheck`（扩展后）+ mock 全链路
- **When**: 3.9 构建产物通过新用例；新旧用例全绿；mock 对新夹具（含 v2 五类 NEED）零费用跑通；全程无 LLM API 调用（无 key 读取、无外网 LLM 端点代码路径；HF/git 数据面除外并在报告列明）
- **Pass Condition**: selfcheck 退出码 0；mock failed_cells=0、cost=0
- **Evidence**: selfcheck 完整输出、mock 产物、网络面说明

### AC-W2-11：扩样与预算报告
- **Type**: `rule`
- **When**: 离线工作结束
- **Then**: 报告含：新旧 issue 数（8→12）、补丁/probe/夹具计数、五条件 condition_gold 分布与 oracle 一致/分歧计数、预期 Pilot cell 总数与分布、基于 Smoke 实际单价的 ≤$1 预算估算与硬门设置说明、v1↔v2 版本差异（schema/提示/gold/指标）
- **Pass Condition**: 七项内容齐备且数字与产物一致
- **Evidence**: 离线验收报告（汇总 JSON + 对用户报告）

### AC-W2-12：条件化金标准的构念效度
- **Type**: `rubric`
- **Dimension**: oracle/condition 双层 gold 与可见性矩阵对「证据充分性判断公平性」的构念一致性（制度受限弃权与可归责弃权是否被清晰区分；缺口分类能否识别泛化保守；双通道（症状/验收）划分是否有过度归责或漏归责）
- **Scale**: 1-5
- **Anchors**: 1=条件 gold 仍可被隐藏标签/模型输出污染或分歧不可解释；3=主要通道覆盖但存在一类证据可见性靠人工判断；5=全部事实可见性机械可审计、分歧逐条可解释、 grounding 验证无灰色地带
- **Pass Threshold**: >= 4
- **Evidence**: 可见性矩阵、basis 文本、AC-W2-4/5/6 证据、影子表分歧复盘点查

## Open Questions（审批点，默认按 DW2 执行，可否决）
- [ ] Q1：Escalate 的验收结果按「可获取（潜在）」计入 condition_gold，实际升级行为/成本仅在行为层报告——确认这是「能够被支持的最适当判决」的 intended 语义（DW2-2②）。
- [ ] Q2：双通道 oracle 使 Wave-1 wrong_patch（症状持续）的 oracle 标签由 NEED 变 REJECT；旧文件冻结、只出影子表——确认接受该版本差异而不回改（DW2-1）。
- [ ] Q3：离线阶段允许 HF 数据集下载与 git fetch 新 base commit（数据面网络，非 LLM、零 LLM 费用）；若环境不允许则 4 issue 扩样转为 blocked。
- [ ] Q4：新夹具总量目标 12–16（四型各 ≥1，余下按确定性选样填充 GOOD/BAD 配对）；若构建实际落在区间外但四型齐全，按实际计数报告。
- [ ] Q5：未来正式 Pilot 的重采样单位确认为 **issue**（cluster bootstrap，新 issue n=4，CI 明确标注小样本描述性）。
