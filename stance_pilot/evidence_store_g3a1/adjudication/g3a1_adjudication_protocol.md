# Gate 3-A.1 · Gold 独立仲裁协议与状态（Annotator 2 安排 + 三结果处理）

版本：g3a1-adjudication-v1（零 API；不改动任何冻结原始数据）
状态：**10/10 Provisional Gold，等待第二名独立标注者**。

本文件是**协调者侧**文档（含真实 issue 号与 Provisional 标签），**不得**
与发给 Annotator 2 的盲包放在一起。盲包在
`evidence_store_g3a1/dossiers/`，匿名映射密封在
`adjudication/sealed/g3a1_blind_code_map.json`（提交全部表单前不得开启）。

---

## 1. 当前 Gold 层级（务必如此表述）

- 现有 10 个 oracle 标签是 **Provisional Gold（mechanically adjudicated,
  human-agreement pending）**：由冻结规则 `gold_w2.oracle_gold` 对已签名、
  新鲜、完整的真实执行记录机械判定，n_annotators = 1（构建方即第一判断者）。
- 在第二名独立标注者完成前，**不得**称 human-adjudicated gold、不得报告
  κ / inter-rater agreement，也**不得**用模型自评或机械复算冒充人工仲裁。
- 各证据条件的 condition_gold 同属 Provisional：它是冻结事实在制度规则下
  的投影，其人工有效性依赖底层 oracle 的仲裁结果。

## 2. 第二名标注者（Annotator 2）安排

- **资格**：具备 Python/SymPy 与代码评审经验，未参与本批选样、构建与规则
  制定；与候选补丁生成模型及数据集构建无利益关联。
- **材料**：编码手册 `dossiers/ANNOTATOR2_CODING_MANUAL.md` + 10 个盲包
  D01–D10（每包含 issue 报告、候选补丁、维护者测试、探针、4 份真实日志、
  主判定表、逐 F2P 工作表；其中 1 包另含 P-CRITERION 探针判据专题表）。
- **盲法**：issue 编号/URL 已匿名，包序随机（seed 20261026）。材料中
  **无**任何模型预测/理由、无 Annotator 1/机械规则结论、无数据集 resolved。
  Annotator 2 被要求不查询上游仓库/PR、不与他人讨论，独立完成全部 10 案。
- **产出**：每案一个 Q1 三态标签 + 三前提核对 + 假失败逐项排查 + 逐 F2P
  节点四问 + 理由 + 置信度；P-CRITERION 案另交判据 A/B 建议。
- **现实约束**：若在 Gate 3-B 书面批准前无法获得 Annotator 2，则维持
  10/10 pending，**不**以任何自动方式替代；按 §4 方案 C 处理。

## 3. 揭盲与比对流程（收到全部表单后）

1. 完整性检查：10 案 Q1 标签与必填理由齐全；缺项退回补齐，不揭盲。
2. 开启 `sealed/g3a1_blind_code_map.json`，把 D## 映射回真实 instance_id。
3. 对每案比较 **Annotator 2 标签 vs Provisional oracle（机械/Annotator1）**，
   记录一致/分歧；计算原始一致率与三态 Cohen's κ（描述性，n=10）。
4. 区分两类分歧：(a) 人 vs 机械规则（规则效度问题）；(b) 若将来有更多人，
   人 vs 人（可靠性问题）。本阶段只有 1 名独立第二人，(b) 无法充分估计，
   κ 仅作描述，不作"金标准已确立"的证据。
5. 分歧案进入 §4 相应处置；任何标签修订都**新建版本**并写 changelog，
   **绝不覆盖**冻结的 G3-A g3a_gold.jsonl。

## 4. 三种仲裁结果的预设处理方案

### 方案 A：全部一致（10/10 一致）
- 将 oracle 升级为 **Human-Adjudicated Gold v2**，记录一致率=100%、κ=1
  （仍注明 n=10、单一第二标注者，外推谨慎）。
- condition_gold 随底层 oracle 一同确认；以新 sidecar
  `g3a1_gold_human_v2.jsonl` 落盘，冻结 G3-A 文件保持不动。
- P-CRITERION 案：若标注者采纳判据 A（与执行判据一致），诊断通道维持；
  若采纳判据 B，则记为"探针效度异议"，在论文 Threats 与方案中报告，并
  评估是否需以新版本重跑该探针（属新工作，需另行批准，不在 $0 范围）。

### 方案 B：部分争议（≥1 案不一致）
- 逐案召开**共识/第三标注者**仲裁：由第三名合格标注者在不见前两方结论下
  独立判同一盲包，再三方协商；终裁标签与理由全部记录。
- 每个修订以新版本保存并写 changelog（原值→新值、理由、谁裁定、日期）。
- 报告**逐案**结果与一致率/κ，并把"规则判 REJECT 但人判可接受"等系统
  模式单独列出——这直接关系规则的构建效度。
- 对只有 3 个 REJECT 的现实：任一 REJECT 案被翻转为 ACCEPT，都须在统计
  方案中按敏感性分析重算（单 issue 翻转≈33pp），结论降级表述。
- Gate 3-B 的启动建议：争议未全部终裁前，受影响 issue 在相关条件上标
  contested，不进入主要比较的确认性结论（可作为探索性结果）。

### 方案 C：无法获得第二名标注者
- 全部 10 案**永久标注 Provisional Gold**，台账保留 n_annotators=1、
  annotator2_status=NOT_OBTAINED。
- 若 Gate 3-B 仍获书面批准在 Provisional Gold 上运行，则：
  - 所有对 gold 的指标一律标注 "against provisional, singly-adjudicated
    gold"；
  - 论文 External Validity / Threats 明确写出缺少独立人工仲裁这一局限；
  - 不报告 κ，不暗示人工一致；
  - 结果定位进一步降为 **feasibility / pilot signal**，不作为泛化验证。
- 一旦日后取得 Annotator 2，回到 §3 揭盲流程，按方案 A/B 补发 v2。

## 5. 当前仲裁状态（机械台账摘要）

- 台账：`g3a1_adjudication_status.jsonl`；摘要：
  `g3a1_adjudication_status_summary.json`。
- oracle Provisional 分布：**7 ACCEPT / 3 REJECT / 0 NEED_EVIDENCE**（自然
  分布，禁镜像、禁改标签平衡类别——见任务 7 声明）。
- condition Provisional 分布：T2D-T 与 T3D-Strict 各 10/10 NEED_EVIDENCE；
  T3D-Escalate / T2A-T / T3A-T 各 7 ACCEPT / 3 REJECT；oracle↔condition
  总分歧 20（每 issue 在两个受限制度各 1 次）。
- 待人工重点问题：全部案的 F2P 适用性/假失败；其中症状消失但 F2P 失败的
  候选由标注者自行识别（盲法不预告）；24213 案另做判据 A/B 专题。
