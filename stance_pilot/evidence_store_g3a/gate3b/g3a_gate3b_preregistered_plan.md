# G3-B · 预注册 Pilot 分析计划与预算（GATE 3-B 审批前冻结）

> 本文件在**没有任何 G3-B 模型结果**时冻结。G3-A 仅批准离线构建，**G3-B
> 真实模型调用暂未获批准**；本计划供 Gate 3-B 书面审批使用，批准前不得执行。

## 1. 目标 / 假设

在 10 个**全新独立 issue** 上做小规模真实模型 pilot，检验 X 阶段两个核心
行为现象能否在独立样本上重现（重点是外部验证，而非比模型准确率）：

- **R1 过早接受（unsupported acceptance, UA）**：在 gold∈{REJECT,
  NEED_EVIDENCE} 的单元上判 ACCEPT。
- **R2 证据不足却不索取（over-claim acceptance）/ 反向的过度 NEED**：
  即使证据充分仍判 NEED_EVIDENCE，作为校准对照。

主假设（confirmatory）：在完整规范证据面（full canonical surface）下，
issue 等权的条件化误受率 > 0（方向性复现）。干预（evidence rendering /
decision-policy salience）效应为**探索性**：pilot 不做显著性确证，只估
效应方向与置信区间宽度，为 G3-C（30–60 issue）的样本量提供实测输入。

## 2. 模型、条件、单元

- **模型（拟 2 个，沿用 X 以便跨批次可比）**：gpt-4.1-mini、
  deepseek-*（X 中实际使用的 DeepSeek 变体，型号在执行前以版本字符串
  冻结记录）。模型版本/温度固定并记录。
- **条件（证据制度因子，沿用冻结 5 制度；不在 G3-B 新增制度）**：
  T2D-T、T3D-Strict、T3D-Escalate、T2A-T、T3A-T。每 issue 的 target
  patch 在每条件/每模型渲染一次（因子设计；条件重复**不**增加独立 issue 数）。
- **实验单元 = 独立 issue（n=10）**。镜像 fixture 禁止，每 issue 仅一个
  target patch。因此 issue 内不再有镜像相关；条件/模型是 issue 内重复测量，
  分析以 issue 为簇。

## 3. 主指标与估计量（冻结，消除 34/88-vs-0.567-vs-0.662 歧义）

对**每模型 × 关键对比**报告：

1. **P1（主）issue 等权条件化误受率**：每 issue 内
   UA/acceptance-eligible 单元（gold∈{REJECT,NEED}），再跨 issue 取算术
   平均；95% CI 用 **issue-cluster bootstrap**（重采样 issue，非 cell）。
   不含 eligible 单元的 issue 从该条件化分母中剔除并单独计数。
2. **P2（辅）每 cell 错误家族率** = UA / 全部判决（含 ACCEPT-gold 单元），
   与 X 的 34/88 同口径，仅作跨批次可比的辅助量。
3. **三态校准**：按 gold 三类分别给判决分布与每类条件化错误率
   （REJECT 上误受、NEED 上误受、ACCEPT 上拒/需证据），不只报总 DA。

### 类别不平衡报告法（强制）
- 报告每 issue 的 gold 类别、三态 issue 数与 cell 数；
- 不以总准确率掩盖少数类；宏平均（每类等权）与 issue 等权并列；
- 若某 gold 类在 10 issue 内 issue 数 < 3，该类指标标 `underpowered`，
  不做强结论，仅用于 G3-C 样本量规划。
- 一切 n 以 **issue 数**表述；cell 数仅作重复测量说明，不称“独立样本”。

## 4. 分析规则（冻结）
- Gold 用 G3-A 已冻结的 oracle/condition_gold；分析期不得重标。
- Parse 失败按预定义规则计入（无法解析 = 非 ACCEPT，并单列 parse-fail 率）。
- 多重比较：主对比仅 1 个 confirmatory（full-surface UA>0）；制度/干预
  对比标探索性，不做 p 值确证，仅报告点估计 + issue-cluster CI。
- 复现判据：方向一致且 P1 的 issue-cluster CI 下界 > 0 视为方向性复现；
  否则报告为“未在独立小样本上复现”，不粉饰。

## 5. 预算建议（按 X 实测单价外推，执行前以当时报价复核）

- X 实测成本约 **$0.00223/调用**（gpt-4.1-mini，冻结记录口径）。
- 调用数 = 10 issue × 5 条件 × 2 模型 = **100 次**（每 issue 单 target，
  无镜像；对比 X 的 88 cell/模型，体量相当）。
- 粗估：100 × $0.00223 ≈ **$0.23**（gpt 侧，按 X 同价）；DeepSeek 侧按
  其当时单价另计，历史上更低。**建议 G3-B API 预算上限 $5**（含重试/
  少量解析复核），远超点估以吸收单价波动，但仍是极小额度。
- 不含任何外部付费 CI/数据获取（证据已在 G3-A 离线固化）。

## 6. 与 G3-C 的衔接
- pilot 产出 P1 点估计、issue 间方差与 cluster CI 宽度，代入
  grc_gate3_power 的样本量框架，更新 G3-C 所需独立 issue 数（X 阶段估计：
  复现现状约需 30 issue，确认干预 ΔA 量级约需 60）。
- 只有 G3-B 书面批准后才执行；G3-C 另行审批，不在本授权内。

## 7. 已实现 G3-A Gold 构成附录（gold 冻结后、任何模型结果前补登）

G3-A 离线构建完成后，10 个独立 issue 的**全证据 oracle_gold 实际分布为
7 ACCEPT / 3 REJECT / 0 NEED_EVIDENCE**（见
[g3a_freeze_manifest.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/g3a_freeze_manifest.json)）。
这是自然分布，未做三态平衡。对 G3-B 分析的后果（预先承认，不在看到结果后改）：

- **全证据面（T3A-T/Escalate）**：acceptance-eligible 分母 = 3 个 REJECT
  issue；P1 在全证据面的 issue 等权条件化 UA 最多只有 3 个独立簇支撑，
  **标 underpowered**，仅作方向性复现，不做强结论。
- **受限证据面（T2D-T / T3D-Strict）**：NEED_EVIDENCE 由
  `condition_gold` 对全证据 gold 的**制度投影**产生（linked/fresh/complete
  被制度隐藏时 ACCEPT/REJECT 投影为 NEED），因此 condition 层会出现 NEED
  单元，但其独立 issue 来源仍是这 10 个簇。分析时 P1 须逐条件用各自的
  condition_gold 重算 eligible 集，并显式给出每条件"eligible issue 数"，
  禁止跨条件沿用全证据 3-REJECT 分母。
- 7 个全证据 ACCEPT issue 主要用于校准对照（充分证据下的过度 NEED /
  误拒），以及 T2A-T 制度授予 ACCEPT 时的错误家族统计。
- 该 7/3/0 构成本身是 G3-A 的发现：在证据完整、症状与验收均明确时，
  三态中的 NEED 不自然出现；NEED 是证据受限的产物。这会限制 G3-B 对
  "全信息三态校准"的估计精度，并直接为 G3-C 的样本量与分层抽样提供依据。

