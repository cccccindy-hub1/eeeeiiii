# GroundedReview R1 — Test–Retest Reliability Report

**Gate**: `r1_live`（Gate-2 冻结协议的第 2 个时间点；Gate-2 自身 132 行 = round 0）
**授权**：2026-10-25 书面批准 R1，132 个新增真实调用，两模型**合计硬上限 $1.50**；X（2×2 消融）、R2、Gate 3 扩样、Gemini、git commit 仍未授权。
**执行结果**：132/132 成功，**新增花费 $0.4766**（DeepSeek $0.2164 + GPT $0.2602），≤ 上限；0 API_ERROR / 0 INVALID / 0 AMBIGUOUS；零重试、零工具、temperature=0、max_tokens=4096、`response_format=json_object`。

> **统计单位声明**：两轮是对同一批 22 个冻结 fixture 的配对复测，**不是**统计独立的新 Issue。所有区间均为 issue-cluster 配对 bootstrap（单位 `instance_id`，10 簇；簇内镜像/layer 先取均值、簇等权；seed=7，n=10000）。它刻画的是**跨 fixture 的变异**，两轮数据**不能**估计某后端的逐 cell 输出方差，也不构成稳定噪声标准差/置信区间。主指标"逐 cell 三态一致率"按用户要求按 66 cell 直接报告，区间仍按簇。

---

## 0. 条件等价性（先证明两轮真的相同，再谈稳定性）

| 检查 | DeepSeek-flash | GPT-4.1-mini |
|---|---|---|
| Payload sha256 两轮逐 cell 相等 | **66/66** | **66/66** |
| Prompt 指纹集合两轮相等（raw/structured/adj 3 个） | 是 | 是 |
| R1 served id | `deepseek-flash` ×66 | `gpt-4.1-mini-2025-04-14` ×66 |
| served 与期望 id 全匹配 | 是 | 是 |
| temperature / max_tokens / response_format / tools / retries | 0 / 4096 / json_object / 0 / 0 | 同左 |
| R1 输入 token | 643,744（与 Gate-2 完全相同） | 600,010（完全相同） |
| R1 输出 token | 19,394（Gate-2 20,032） | 12,609（Gate-2 12,318） |

输入逐字节相同、声明的 served id 稳定；两轮的任何判决差异因此只能来自**后端侧的非确定性（temp=0 不保证逐 cell 确定）或未公开的服务端权重变更**。我们只能确认"声明的模型 id 字符串未漂移"，**无法排除同 id 下的静默服务端版本变化**（API 不返回可核验的权重版本哈希）——这是本研究持续存在的一个外部效度限制。

独立分析（不导入 Gate-2 分析器，直接重读两轮 jsonl + 冻结 gold 重算）**复现了 Gate-2 的 round-0 DA**：GPT raw/str/adj = .409/.545/.818，DS = .773/.864/.909（四舍五入一致），交叉验证通过。

---

## A. 逐 cell 三态 Exact Agreement

| 模型 | 总体（cell） | 不一致数 | cluster 等权点估计 | cluster 95% CI | raw | structured | adjudicated |
|---|---|---|---|---|---|---|---|
| DeepSeek-flash | **62/66 = 93.9%** | 4 | 0.944 | [0.900, 0.983] | 20/22 = 90.9% | 20/22 = 90.9% | **22/22 = 100%** |
| GPT-4.1-mini | **63/66 = 95.5%** | 3 | 0.922 | [0.833, 1.000] | **22/22 = 100%** | 21/22 = 95.5% | 20/22 = 90.9% |

两模型总体一致率都 ≥ 90%（落在用户决策表的"高一致"参考带），但 CI 很宽（仅 10 簇），且**层间与错误类型高度不均匀**（见下）。特别地：**GPT raw 22/22 完全稳定，但 raw 的 DA 只有 40.9%**——高一致性不等于高正确性，模型在稳定地犯错。

## B. 判决转移矩阵与定向翻转

**DeepSeek（4 次翻转，零和分散）**
- raw：`403163cb`（gold NEED）NEED→REJECT；`a25d0cf5`（gold NEED）REJECT→NEED（两案在 REJECT↔NEED 间反向摆动）
- structured：`c564f50f`（gold ACCEPT）ACCEPT→NEED（由对变错）；`c637f604`（gold NEED）NEED→REJECT
- adjudicated：无翻转

**GPT（3 次翻转，全部不在 raw）**
- adjudicated：`59e46a77`（gold REJECT）REJECT→NEED（由对变错，新增一次 REJECT-gold 上的过度弃权）；`ec813709`（gold NEED）ACCEPT→NEED（**由错变对**）
- structured：`a242cd7a`（gold REJECT）ACCEPT→NEED（两轮都错，但错误家族从 unsupported acceptance 迁出）
- raw：**无翻转**

关键观察：GPT 本轮的 2 个 adjudicated 翻转（`59e46a77`、`ec813709`）**正是 G2.5 早先两轮对照中已记录翻转的同两例**。加入 R1 后，这两例在 3 个时间点上持续振荡（`ec813709`：CEE NEED 对 → EAL adj ACCEPT 错 → R1 NEED 对；`59e46a77`：CEE NEED 错 → EAL adj REJECT 对 → R1 NEED 错）。它们是**慢性不稳定 cell**，而非一次性抖动。

## C. DA 轮次差（配对，cluster bootstrap）

| 模型 | DA round0 | DA round1 | 总体 Δ [95% CI] | raw Δ | structured Δ | adjudicated Δ |
|---|---|---|---|---|---|---|
| DeepSeek | 0.849 | 0.818 | **−0.033 [−0.083, +0.017]** | 0.000 | −0.083 [−0.20, 0.00] | 0.000 |
| GPT-4.1-mini | 0.591 | 0.591 | **+0.022 [−0.033, +0.100]** | 0.000 | 0.000 | +0.067（点） |

- GPT 三层 DA 数值上均无净变化（structured 的 `a242cd7a` 与 adjudicated 的两翻转都是"错↔错"或"一对一错抵消"，净 0）。
- DS 的小幅下降集中在 structured（`c564f50f` 由对变错），区间跨 0。
- **没有任何一层的 DA 变化可与 0 区分**（CI 均跨 0）；这与"高逐 cell 一致率"一致。

## D. 区间与独立性

如前：所有 CI 以 10 个 issue 簇为单位、配对 bootstrap；重复 cell 未被当作独立 Issue，两轮也未用于估计每个 cell 的输出方差。

## E. GPT structured 的 8 个 G2.5 NEED→ACCEPT 复测（诊断；主样本仍为全 22）

| 指标 | 结果 |
|---|---|
| gate2 八案是否全为 ACCEPT | 是（8/8） |
| **R1 仍判 ACCEPT** | **8/8（100%）** |
| R1 恢复 NEED_EVIDENCE | 0/8 |
| R1 其他（REJECT） | 0/8 |

8 案（`62dfb1c6`/`2c11095a`/`e4e8b26c`/`c637f604`/`ec813709`/`a25d0cf5`/`403163cb`/`c59a8ceb`，覆盖 freshness / coverage / linkage）在 structured 层**逐案复现**，全部稳定地给出与可见证据操作数矛盾的 ACCEPT。

**这是本轮最重要的结论**：G2.5 标记的"在完整证据操作数已呈现时仍做出矛盾验证结论"**不是一次性调用噪声**——它在独立的第二次真实调用中 8/8 重现。相反，GPT 的 3 次随机翻转发生在 adjudicated（2 例）与另一个 REJECT-gold structured 案（`a242cd7a`），**没有一次发生在这 8 个过度接受案上**。这把该现象从"可能的调用抖动"进一步收紧为"structured 呈现下系统性、可复现的行为模式"。

完整 22 fixture 的 structured 两轮逐项结果见 [eal_r1_analysis.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/r1_runs/eal_r1_analysis.json) 的 `structured_all22`，未按历史错误筛主样本。

## F. 两轮错误家族比较

**GPT**
- raw：完全不变（unsupported_acceptance 7、over_abstention 5、unsupported_rejection 1，两轮一致）。
- structured：unsupported_acceptance **9→8**，over_abstention **0→1**——唯一迁移是 `a242cd7a` 从错误 ACCEPT 变为弃权；**8 个 NEED-gold 过度接受全部保留**。
- adjudicated：unsupported_acceptance 1→0（`ec813709` 修正）、over_abstention 3→4（`59e46a77` 新增一次对 REJECT-gold 的弃权）。
- REJECT-gold 上的过度弃权（政策非对称规则相关）：raw 3/6 两轮不变；structured 0→1/6；adjudicated 3→4/6。

**DeepSeek**
- raw / adjudicated 错误家族完全不变；structured over_abstention 3→4、新增 unsupported_rejection 1（`c637f604`）。
- REJECT-gold 弃权：raw 0/6、structured 2/6、adj 2/6，两轮一致（DS 本就基本正确执行非对称规则）。

## G. 服务端/配置/费用审计

- served id、payload sha、prompt 指纹、采样参数、response_format、tools、retries：两模型全部与 Gate-2 兼容且本轮内部零漂移（见 §0）。
- **能确认**：声明模型 id 未变、输入字节完全相同。**不能确认**：同 id 背后的服务端权重版本（无版本哈希）——两次时间点的差异须在"后端非确定性或静默版本变化"这一不可拆分的前提下解读。
- 费用：DeepSeek in 643,744 / out 19,394 = $0.2164；GPT in 600,010 / out 12,609 = $0.2602；**合计 $0.4766 ≤ $1.50 硬上限**，BudgetGuard 在每次调用前预检、全局共享门生效。
- 全部原始响应在解析前落盘，reason / missing_evidence / evidence_gap / token / latency / served 逐行保留；支持续跑（本轮一次跑完，未触发）。

---

## 结论与对 X 的建议

1. 两模型总体逐 cell 一致率 94–96%，处于用户"高一致（≥90%）"参考带；但**该结论必须分层、分错误类型解读**，总体均值会掩盖结构。
2. **GPT raw 100% 稳定却只有 41% DA**：稳定性与正确性是两回事；且 GPT 全部 3 次翻转都发生在信息最丰富的 structured/adjudicated 层。
3. **目标现象高度可复现**：GPT structured 的 8 个"矛盾验证结论"案 8/8 重现、0 次受翻转影响；这强化了 v2.1 的检验价值——X 若改变这 8 案的判决，将很难再归因于重测随机。
4. 慢性振荡只集中在 2 个 adjudicated cell（`59e46a77`、`ec813709`，跨 3 个时间点），分析 X 时应把这两例标记为高重测方差、单独报告。
5. DS 接近天花板且基本稳定，继续作为机制检验的阴性对照。

**建议（供决策，不自行执行）**：依据用户决策表，总体一致率 ≥90% 支持**可以考虑批准 X**，且 8/8 复现使 X 的主要终点（structured NEED→ACCEPT 与矛盾断言比例）处在低重测噪声区；但 X 的分析必须：① 以 issue 簇为单位、把模型随机性纳入；② 对 2 个慢性振荡 adjudicated cell 做敏感性标注；③ 维持 Verification Assistance / Policy Salience 的行为层措辞，不断言唯一内部机制。

**R2 暂不建议自动追加**：8/8 复现 + 总体高一致意味着 r=1 已足够回答"同输入是否同判"；除非 X 结果落在临界区，否则第三时间点边际价值有限。

已停止：未运行 X / R2 / Gemini / Gate 3，未新增 Issue，未修改 Gate-2 / G2.5 / CEE / E1 / v2.1 冻结数据，未提交 git。等待是否执行 X 的下一次书面批准。
