# Gate 3-A 完成报告 · 首批 10 个全新独立 Issue 离线构建与审计

**Gate**：G3-A（独立 Issue 数据构建与离线审计）｜ **API 预算**：$0，实际付费模型调用 0｜
**依据**：用户 2026-10-26《Research Consolidation 验收与 Gate 3 决策》书面授权。

> 本阶段只做离线数据构建与审计。**未执行 G3-B/G3-C、未调用任何付费模型/Gemini/R2、
> 未用新样本优化 prompt、未修改 E1/CEE/EAL/R1/X/Consolidation 任何冻结结果、
> 未 git commit。** 全部新产物隔离于 [evidence_store_g3a/](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a)，
> 代码 `g3a_` 前缀；冻结快照 `evidence_store_w21/` 全程只读。

---

## 1. 10 个全新独立 Issue（任务 1、2）

入选清单（与旧 12 个 issue 零重叠，确定性种子 `20261026A`，61 合格/14 排除）：

| issue | 数据集状态 | target 生成器 | oracle_gold | class | 症状 | 维护者 F2P |
|---|---|---|---|---|---|---|
| 13615 | resolved | GLM-5-FP8 | ACCEPT | B | gone | 1/1 |
| 13974 | resolved | GLM-5-FP8 | ACCEPT | B | gone | 1/1 |
| 15349 | resolved | GLM-5-FP8 | ACCEPT | B | gone | 1/1 |
| 17318 | **unresolved** | GLM-5-FP8 | **REJECT** | A | gone（验收仍败） | 0/1 |
| 17630 | **unresolved** | GLM-5-FP8 | **REJECT** | A | gone（验收仍败） | 1/2 |
| 19783 | **unresolved** | GLM-5-FP8 | **REJECT** | A | gone（验收仍败） | 1/2 |
| 20590 | resolved | GLM-5-FP8 | ACCEPT | B | gone | 1/1 |
| 21847 | resolved | GLM-5-FP8 | ACCEPT | B | gone | 1/1 |
| 24213 | resolved | GLM-5-FP8 | ACCEPT | B | gone | 1/1 |
| 24443 | resolved | GLM-5-FP8 | ACCEPT | B | gone | 1/1 |

- 纳入/排除标准在选样前**预冻结**（门 G1–G5：新颖性、base 离线可取、维护者 test_patch
  干净且 F2P 名可映射、≥1 干净 target patch、blob 完整），**不依据任何模型历史错误挑样**。
- 每 issue **仅一个 target patch**，**无镜像 fixture**；7 resolved / 3 unresolved 是自然分布。
- 产物：[g3a_selection.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/selection/g3a_selection.json)、
  [g3a_selection_protocol.md](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/selection/g3a_selection_protocol.md)、
  [g3a_target_rows.jsonl](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/raw/g3a_target_rows.jsonl)、
  [g3a_provenance_manifest.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/g3a_provenance_manifest.json)。

## 2. 真实 pytest 重放与手写 symptom probes（任务 3）

- 10 个 probe 全部**人工手写**，从 issue 报告派生、仅用公开 sympy API，独立于维护者 test_patch；
  在 vendored `repro/sympy_src` 上用 **Python 3.9.25 + pytest 8.4.2 + mpmath 1.4.1（uv --offline）**
  真实执行（非付费服务）。
- 每 issue：checkout base → baseline probe（须失败）→ apply 候选 → post probe → apply 维护者
  test_patch → F2P + 作用域 P2P + baseline P2P 三文件一批跑 pytest → content-addressed 产物 + HMAC
  签名 + `git write-tree` attestation。
- **4 个 probe 首轮构念错误均已修正并 --force 重建、全程留痕**（见
  [g3a_probe_construct_validity.md](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/audit/g3a_probe_construct_validity.md)）：
  13615（接受语义对齐 `Complement(FiniteSet(x,y),I)`）、17318（锁仍崩的复数表达式）、
  17630（旧版矩阵无 `.items()`，直接比 BlockMatrix）、24213（最终放宽为"不抛 ValueError"，
  忠于维护者 test_issue_24211 仅断言"should not throw"；披露候选未做维度等价归一化）。
- truth：[g3a_truth.jsonl](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/g3a_truth.jsonl)。

## 3. oracle_gold 先于任何预测冻结（任务 4）

- 复用纯函数 `gold_w2.oracle_gold`（避免规则漂移），从签名 record + attestation **机械复算**
  linked/fresh/complete/failure/symptom_persists；在任何模型预测之前冻结。
- [g3a_gold.jsonl](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/gold/g3a_gold.jsonl)：
  **oracle 自然分布 7 ACCEPT / 3 REJECT / 0 NEED_EVIDENCE**。
- **双通道关键构念**：17318/17630/19783 的候选都**消除了报告症状**（诊断通道 addressed=True），
  但维护者 F2P 仍有失败（验收通道 acceptable=False）→ 全证据 oracle=REJECT。这正是诊断与验收
  可合法分离的情形。
- **全证据层无 NEED 是发现而非缺陷**：证据完整、症状与验收明确时三态中的 NEED 不自然出现；
  NEED 是证据受限的 condition 投影，预期在 G3-B 受限制度（T2D/Strict）下产生。
- 区分 `oracle_gold`（补丁实际可接受性）与 `condition_gold`（当前可见证据支持的判决）；主队列
  只冻结全证据面，per-regime 标签在 G3-B 渲染时由 `condition_gold` 机械投影、不重新仲裁。
- **作用域口径如实披露**：P2P 是 test_patch 文件 + 改动代码相邻 tests 的**作用域子集**，
  oracle ACCEPT = 作用域可接受，不外推全仓库回归。

## 4. 证据充分性证书 + fresh 独立复核（任务 5、9）

- [g3a_sufficiency_certificates.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/audit/g3a_sufficiency_certificates.json)：
  每 issue 给出最小 forcing 通道（ACCEPT=linked+fresh+complete+success；REJECT=linked+fresh+
  acceptance_failure；症状持续则 symptom 单独 forcing）、证据状态、gold 是否欠定。
  **10/10 gold_underdetermined=False**；source_applicable 与 source_trustworthy 均真。
- [g3a_freshness_recompute.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/audit/g3a_freshness_recompute.json)：
  独立脚本从零重新 restage（base+候选+test_patch）跑 `git write-tree`，与 attestation
  expected_run_tree **10/10 一致、签名 10/10 可信**（不跑 pytest，纯 git 二次推导）。
- **Label leakage 审计**：raw+structured 模型面层扫描答案词表（ACCEPT/REJECT/NEED_EVIDENCE、
  oracle/merge_acceptable/issue_addressed/label_class/resolved 等）**0 命中**；pytest PASSED/FAILED
  是合法验收证据，已白名单。
- **Token / 截断**：三层字符三口径估算（chars//4、chars/3.62、whitespace+punct）；最大 raw 层
  约 35,118B ≈ **9.7k token（chars/3.62）**，远小于两模型上下文，**G3-A 无截断风险**。
- **来源关联**：四个 raw 日志 sha256 与签名记录 log_digests **10/10 一致**，证明三层共用同一
  底层执行事实。产物 [g3a_leakage_token_audit.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/audit/g3a_leakage_token_audit.json)。

## 5. 人工 Gold 仲裁：全部 pending（任务 7）

- 当前只有 **1 名标注者，无第二人** → 10 个 issue 的人工人对人一致状态**全部登记 `pending`**，
  逐 issue 写入 gold 行 `human_adjudication` 与每张证书。
- 机械 oracle 复算 + git-tree fresh 一致仅作为**内部机械一致性检查**单独报告，
  **严禁、也未被伪装成两位独立审稿人一致性**。
- 程序与解除 pending 的前置条件见
  [g3a_human_adjudication_protocol.md](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/gold/g3a_human_adjudication_protocol.md)：
  在取得第二位独立标注者之前，标签只能称 **mechanically adjudicated, human-agreement pending**，
  不得声称 κ/inter-rater reliability。

## 6. Raw / Structured / Adjudicated 三层材料（任务 8）

- 每 issue 三层落 [layers/&lt;issue&gt;/](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/layers)，
  来自同一次执行事实、共享 artifact_id 与 log_digests：
  - **Raw**：问题报告、候选/维护者 patch、四类逐字 pytest/probe 日志（无判决表、无标签）。
  - **Structured**：签名运行记录的**确定性解析**（逐测试状态图/summary）+ write-tree attestation。
  - **Adjudicated**：oracle/condition gold + Sufficiency Certificate（模型永不可见）。
- **Derived-Summary 严格披露**：structured 是本地构建器对 raw 日志的确定性派生分类，
  **不是**外部/上游 CI；runner 字段如实写 `host=windows-local`，无 "UPSTREAM CI RUNNER" 措辞；
  数据集 `resolved` 是 SWE-bench harness 真值、非人类合并决定，仅入 adjudicated。
  详见 [g3a_layers_disclosure.md](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/layers/g3a_layers_disclosure.md)。

## 7. 不强制三态、不镜像平衡（任务 6）

- 未要求每 issue 具备三态标签，未用镜像 fixture 人为平衡。自然结果 7/3/0 已在选样协议、冻结清单
  与 G3-B 计划中声明；类别不平衡的后果（全证据面仅 3 个 REJECT 簇支撑 UA 主指标 → underpowered）
  已在 [G3-B 预注册计划 §7](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/gate3b/g3a_gate3b_preregistered_plan.md)
  预先承认，并作为 G3-C 分层抽样与样本量依据。

## 8. 统计口径独立说明（任务 11）

[g3a_estimand_clarification.md](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/audit/g3a_estimand_clarification.md)
从冻结 X 独立重算，三个比例分母互不相同、已逐一钉死：

- **34/88 = 0.3864**：全部 parseable cell（含 28 个不可能误受的 ACCEPT-gold 单元）；
- **34/60 = 0.5667**：60 个 acceptance-eligible cell（gold∈{REJECT,NEED}，cell 加权）；
- **0.662**：9 个含 eligible 单元的 issue 各自 UA/eligible 率的**等权平均**（纯 ACCEPT 的
  issue 16450 被排除）；另附 issue-equal all-cell=0.4375（10 issue）。

## 9. G3-B 预注册计划与预算建议（任务 10）

[g3a_gate3b_preregistered_plan.md](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/gate3b/g3a_gate3b_preregistered_plan.md)
在**任何 G3-B 结果之前**冻结：模型 gpt-4.1-mini + DeepSeek；5 个冻结条件；**实验单元=独立 issue
n=10**；主指标 P1=issue 等权条件化 UA + issue-cluster bootstrap CI，P2=每 cell 错误家族率（与
34/88 同口径仅作跨批可比），三态校准与类别不平衡强制报告；100 次调用点估 ≈ **$0.23**，建议预算
上限 **$5**。§7 已按实际 7/3/0 gold 构成标注全证据面 underpowered。

## 10. 冻结清单（任务 12）

[g3a_freeze_manifest.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/g3a_freeze_manifest.json)
（freeze_id `groundedreview-gate3a-offline-frozen-2026-10-26`）逐文件 sha256 登记全部 G3-A 产物，
记录 api_budget_used=$0、paid_model_calls=0、oracle 7/3/0、human pending 10、mirror=0、
targets_per_issue=1、label_balancing=none。

---

## 结论与停止点

G3-A 的 12 项任务全部完成：10 个全新独立、零镜像的 SymPy issue 已离线构建，双通道 gold 先于预测
冻结（7 ACCEPT/3 REJECT，人工 pending），fresh 独立复核 10/10、leakage 0、日志摘要 10/10、无截断
风险，三层材料与 Derived-Summary 披露齐备，统计口径已钉死，G3-B 计划与预算已预冻结。

**现停止，等待 Gate 3-B 的书面审批。** G3-B（新 issue 真实模型 pilot）与 G3-C（扩 30–60 issue）
均**未获批准、未执行**；未 commit。
