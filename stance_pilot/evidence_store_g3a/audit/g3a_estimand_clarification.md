# G3-A · 统计口径说明：34/88、0.567、0.662 的分母与估计量

- 目的：回应验收意见，明确 Consolidation 报告中三个 unsupported-
  acceptance（UA）比例**不是同一分母**，避免论文歧义。
- 数据：冻结 Experiment X，gpt-4.1-mini，88 个 parseable cell
  （22 fixture × 4 条件）。Gold 分布 ACCEPT 28 / REJECT 24 /
  NEED_EVIDENCE 36；其中 UA 在定义上只可能发生在 gold∈{REJECT,
  NEED_EVIDENCE} 的单元（**acceptance-eligible**，共 60 个）。
- 本说明由 [g3a_estimand_clarify.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/g3a_estimand_clarify.py)
  从冻结 jsonl 独立重算（$0，只读冻结），结果落
  [g3a_ua_denominators.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/audit/g3a_ua_denominators.json)。

## 1. 三个比例各自的统计总体

| 量 | 数值 | 分子（UA 事件） | **分母（统计总体）** | 估计量含义 |
|---|---|---|---|---|
| **34/88** | **0.3864** | 34 | **全部 88 个 parseable cell**（含 28 个 ACCEPT-gold 单元——UA 在这些单元不可能发生） | X 的**错误家族事件率/每 cell**：把误受当作三类错误家族之一，在全部判决中报告。分母混入了不可能误受的单元，**不是条件化的误受风险**。 |
| **0.567** | **0.5667** | 34 | **60 个 acceptance-eligible cell**（gold=REJECT 24 + gold=NEED 36），cell 加权 | 在"本不该 ACCEPT"的单元上，模型仍判 ACCEPT 的**条件化误受率（cell 加权）**。同一 issue 的镜像 fixture × 4 条件在分母里重复计数。 |
| **0.662** | **0.6625** | — | **9 个至少含 1 个 eligible 单元的独立 issue**；先在每 issue 内算 UA/eligible（镜像 fixture 与四条件在 issue 内等权），再对 9 个 issue 取算术平均 | **issue 等权的条件化误受率**：每个独立 issue 一票，消除大簇/镜像的重复权重。 |
| （附带）0.4375 | 0.4375 | — | **全部 10 个 issue**；每 issue 内 UA/全部 cell，再对 10 issue 平均 | issue 等权的"每 cell 错误家族率"，与 34/88 同概念但 issue 等权；含纯 ACCEPT issue（sympy-16450，UA 率 0）。 |

## 2. 逐 issue 分解（解释 0.567 与 0.662 的差异来源）

| issue（尾号） | UA / eligible | issue 内 eligible 率 | UA / 全部 cell |
|---|---|---|---|
| 12419 | 4/4 | 1.000 | 4/12 = .333 |
| 12481 | 4/4 | 1.000 | 4/16 = .250 |
| 12489 | 1/12 | .083 | 1/12 = .083 |
| 13091 | 4/8 | .500 | 4/12 = .333 |
| 13798 | 3/8 | .375 | 3/8 = .375 |
| 14531 | 8/8 | 1.000 | 8/8 = 1.000 |
| 17139 | 4/4 | 1.000 | 4/4 = 1.000 |
| 18199 | 2/4 | .500 | 2/4 = .500 |
| 18211 | 4/8 | .500 | 4/8 = .500 |
| 16450（纯 ACCEPT） | 0/0 | 不适用（无 eligible 单元） | 0/4 = 0 |

- cell 加权 0.567 把每个镜像 fixture×条件当一次观测；issue 等权 0.662
  让 sympy-12481（16 cell，其中仅 4 eligible）等大 issue 与 sympy-17139
 （4 eligible）各持一票。后者 ≥ 前者，说明 UA **不是被大簇稀释/放大的
  假象**——多数独立 issue 的条件化误受率本来就高。
- 两口径差异是**加权方案**差异，不是样本或事件不同；二者分子事件集
  完全相同（同为那 34 次），区别只在分母是否条件化于 eligible、以及
  cell 加权还是 issue 等权。

## 3. 独立性限定（论文必须随数字报告）

- **0.662 仍不等于"9 个独立失败案例"**：34 次 UA 仅来自 9 个不同
  fixture，且 24/34 落在镜像对的负向 fixture 内；issue 内四条件高度
  相关。建议论文表述（采用验收意见原文）：
  > "Unsupported acceptance was observed across nine of ten issue clusters,
  > although the failures arose from a small set of related fixtures
  > evaluated under multiple conditions."
- 0.662 的单位是 issue 簇，但 n=9（eligible 口径）/10（全 cell 口径），
  不得外推为总体现患率；它是发现队列（discovery cohort）的描述量。

## 4. G3-B 主分析将统一的口径（预先冻结，见 G3-B 分析计划）

- 主指标 **P1** 报告两个并列数字，且都以**独立 issue 为簇**：
  1. issue 等权条件化误受率（每 issue 内 UA/eligible，再跨 issue 平均，
     issue-cluster bootstrap CI）；
  2. 每 cell 错误家族率（UA/全部判决）作为可比较的辅助量。
- G3-A 主队列**禁止镜像 fixture、每 issue 仅一个 target patch**，因此
  G3-B 中 issue 等权与 cell 加权在 issue 内天然一致（每 issue 一个目标
  patch，条件重复仅来自因子设计），从设计上消除本轮的加权歧义。
- 类别不平衡报告：按 gold 三类（ACCEPT/REJECT/NEED）分别给出每类的
  判决分布与每类条件化错误率，不仅报总 DA；并报告 issue 数与每 issue
  的 gold 类别，不把 cell 数当样本量。
