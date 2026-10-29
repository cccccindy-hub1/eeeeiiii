# Gate 3-A.1 审计报告 — Gold 独立仲裁准备 + G3-B 付费前置审计

- 版本：g3a1-report-v1（零 API；未发起任何模型调用、未扩样、未用 Gemini、
  未做新 Prompt 实验）。
- 授权范围：用户对 Gate 3-A 工程与数据构建初步验收通过，正式批准
  **Gate 3-A.1 零 API 工作**；Gate 3-B 真实调用**继续等待书面批准**。
- 冻结校验：G3-A 全部 **141** 个冻结文件 sha256 逐一复算，**0 改动、0 缺失**
  （见 [g3a1_freeze_manifest.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a1/g3a1_freeze_manifest.json)）；E1/CEE/EAL/R1/X/Consolidation 未触碰。
- 本报告完成后**停止**，不提交 Git，等待 Gate 3-B 下一次书面批准。

---

## 1. 12 项任务逐项交代

| # | 任务 | 交付与结论 |
|---|---|---|
| 1 | 10 issue 的 Gold Dossier | 每 issue 一份自足盲包（issue 原文、候选补丁、维护者测试、症状探针、4 份真实日志），共 10 份，置于 [dossiers/](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a1/dossiers) |
| 2 | Dossier 不含模型预测/reason，不预告标注者1结论 | 盲包以随机码 D01–D10 匿名（seed 20261026），issue 号/URL 全部脱敏；证据文件泄漏扫描 **0 命中**（见 [g3a1_dossier_leakage_audit.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a1/audit/g3a1_dossier_leakage_audit.json)）；编码手册 [ANNOTATOR2_CODING_MANUAL.md](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a1/dossiers/ANNOTATOR2_CODING_MANUAL.md) |
| 3 | 安排第二标注者，否则保持 10/10 pending | 已备齐可直接交付的盲包+手册+空白表；现实中**第二人尚未取得**，台账 10/10 `NOT_OBTAINED`；明确禁止模型自评/机械复算冒充（见 [仲裁协议](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a1/adjudication/g3a1_adjudication_protocol.md)） |
| 4 | 三个 REJECT 重点审 F2P 关联性/真实性/适用性 | 每份盲包都附**逐 F2P 节点空白工作表**（10_f2p_worksheet_blank.md，关联性/真实性/基线即坏/适用性四问）；为不破坏盲法，不预告哪几份是重点案，由标注者自行从日志识别 |
| 5 | 24213 probe 判据修正独立审核 | 对应盲包附 **P-CRITERION 专题表**（11_P_CRITERION_blank.md），并列"仅不抛异常(判据A)"与"还须维度归一化(判据B)"，**不披露构建期采用了哪一个** |
| 6 | 分别冻结 oracle_gold 与 condition_gold，记录分歧 | oracle 沿用冻结 G3-A；condition 五制度投影落 [g3a1_condition_gold.jsonl](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/gold/g3a1_condition_gold.jsonl)（新 sidecar，version w2-gold-v1+g3a-v1+g3a1-condition-v1）；oracle↔condition 总分歧 **20** |
| 7 | 重申自然分布 7/3/0，禁平衡 | 自然分布 **7 ACCEPT / 3 REJECT / 0 NEED_EVIDENCE**；0 镜像、每 issue 单 target、未改任何标签；台账与冻结清单均固化此声明 |
| 8 | G3-B 最小外部验证协议 | [g3a1_gate3b_minimal_protocol.md](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a1/gate3b/g3a1_gate3b_minimal_protocol.md)：两条主比较、n=10、三层可判定性、NEED 可测范围 |
| 9 | 三种仲裁结果处理 | 仲裁协议 §4：全一致→升 human-adjudicated v2；部分争议→第三人/协商+changelog+敏感性；无第二人→永久 Provisional 并在 Threats 披露 |
| 10 | 冻结统计方案 | [g3a1_gate3b_stats_plan.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a1/gate3b/g3a1_gate3b_stats_plan.json)：单位=独立 issue；C1 分母 3、C2 分母 10；issue-cluster bootstrap CI + k/3 精确 CP 区间；单 REJECT 翻转 33.3pp |
| 11 | 费用/最坏包络/BudgetGuard | [g3a1_gate3b_budget.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a1/gate3b/g3a1_gate3b_budget.json)：100 调用，点估 **$0.223**、观察有界最坏 **$0.86**、规划最坏 **$1.13**；建议每模型硬顶 **$2.50**、全局 **$5.00**（复用现成 BudgetGuard，pre-call 硬门） |
| 12 | 审计报告/材料/状态表/G3-B 建议 | 本报告 + 冻结清单 + 仲裁台账 + 本目录全部材料 |

## 2. Gold 层级（当前唯一允许的表述）

10 个 oracle 标签与其五制度 condition 投影当前均为 **Provisional Gold
（mechanically adjudicated, human-agreement pending）**，独立标注人数 n=1。
第二人完成前不得称 human-adjudicated、不得报告 κ/ inter-rater agreement。

## 3. condition gold 实测（任务 6 的关键发现）

- oracle：7 ACCEPT / 3 REJECT。
- **T2D-T：10/10 NEED_EVIDENCE；T3D-Strict：10/10 NEED_EVIDENCE**（10 个
  issue 症状全 gone，验收通道在这两个受限制度被隐藏 / not adjudicated）。
- T3D-Escalate / T2A-T / T3A-T：均 7 ACCEPT / 3 REJECT，与 oracle 一致。
- 总分歧 20 = 每 issue 在 T2D、Strict 各分歧 1 次。

这精确支持用户的研究判断：**NEED_EVIDENCE 是受限证据下的 condition-level
decision，而不是这批补丁的 oracle label**；充分证据制度下无 NEED。

## 4. 盲法与独立性保障（任务 1/2/4/5）

- 随机匿名 D01–D10，真实映射密封于
  [g3a1_blind_code_map.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a1/adjudication/sealed/g3a1_blind_code_map.json)（协调者保管，表单收齐前不得开启）。
- 证据文件对 ACCEPT/REJECT/NEED_EVIDENCE、oracle/condition_gold、
  resolved、label_class、merge_acceptable 等做正则扫描，**0 命中**。
- issue 号/URL（含补丁与测试注释中的引用）统一脱敏；代码内
  `test_issue_<数字>` 函数名为读懂测试保留——跨 10 包共现 120 个此类名称，
  目标 issue 号本身零出现，残留弱可识别性已在 manifest/audit 显式披露，
  而非隐藏。
- 机械完整性（HMAC、日志摘要、restaged run tree）作为**前提**陈述，把
  人工精力集中到规则做不到的部分：F2P 语义适用性、环境假失败、探针与
  报告症状的契合度。

## 5. G3-B 付费前置审计结论（任务 8/10/11）

- 定位：**External Feasibility Pilot**，非泛化验证。
- 两条预先指定的外部效度问题：
  - **C1**：gpt-4.1-mini 在充分证据面上是否仍对 gold=REJECT issue 错误接受
    （分母仅 3 个独立 issue，underpowered）；
  - **C2**：deepseek-* 在充分证据面（正确答案永非 NEED）上是否仍过度弃权
    （分母 10）。
  - 未复现也是可报告结果，假设在零结果前冻结，不在看到数据后更改。
- NEED 可测范围严格限于 T2D-T / T3D-Strict（那里 10/10 正确答案即 NEED）。
- 预算：点估远低于硬顶；最坏规划包络 $1.13 仍 < 全局 $5；BudgetGuard 在
  每次发送前按"实际输入+满额输出"上界预检，served model id 漂移与价格
  漂移（>1.5×）均硬停。**这些硬顶是建议值，须 Gate 3-B 书面批准后才设定。**

## 6. 未决与建议

- 唯一实质性未决项：**第二名独立标注者尚未取得**，Gold 维持 Provisional。
- 建议：先依仲裁协议取得/安排 Annotator 2；在其完成揭盲前，不建议启动
  Gate 3-B 的确认性解读。若届时仍无法取得第二人，G3-B 即便获批也只能在
  Provisional gold 上作 pilot 信号，并在 Threats 明示缺独立人工仲裁。
- 本阶段不请求新的 API 授权；Gate 3-B 是否执行、以何硬顶执行，留待用户
  下一次书面批准。

## 7. 产物索引

- 盲包与手册：`evidence_store_g3a1/dossiers/`（含每案空白主判定表、逐 F2P
  工作表；一案含 P-CRITERION 专题表）。
- 仲裁：`evidence_store_g3a1/adjudication/`（协议、台账 jsonl、摘要、
  密封映射）。
- 泄漏审计：`evidence_store_g3a1/audit/g3a1_dossier_leakage_audit.json`。
- G3-B：`evidence_store_g3a1/gate3b/`（最小协议、统计冻结、预算）。
- condition gold sidecar：`evidence_store_g3a/gold/g3a1_condition_gold.jsonl`。
- 冻结清单：`evidence_store_g3a1/g3a1_freeze_manifest.json`（含 changelog、
  121 个新文件 sha256、G3-A 141 文件零改动证明）。
- 新代码：`evidence/g3a1_conditions.py`、`g3a1_dossiers.py`、
  `g3a1_adjudication.py`、`g3a1_stats_plan.py`、`g3a1_budget.py`、
  `g3a1_freeze.py`。
