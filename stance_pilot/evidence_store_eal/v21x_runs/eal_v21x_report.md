# GroundedReview v2.1 — Experiment X（2×2 Factorial）报告

**Gate**: `v21x_live`
**授权**：2026-10-25「R1 验收通过，X 有条件批准」——22 fixture × 4 factorial 条件 × 2 模型 = **176 个新增真实调用，总硬上限 $1.50（两模型合计）**。不含 R2 / Gate 3 扩样 / Gemini / 其他模型 / 新 Issue；不提交 git。
**执行结果**：**176/176 成功，新增花费 $0.392409**（DeepSeek-flash $0.182078 + GPT-4.1-mini $0.210331），均在全局 $1.50 与各模型 $0.75 门内；**0 API_ERROR / 0 INVALID / 0 AMBIGUOUS**，零重试、零工具、temperature=0、max_tokens=4096、`response_format=json_object`，raw response 全部先落盘再解析。

> **因子定义（行为层干预）**：A = **Verification Assistance**（A0 无 / A1 有，在证据后附"计数辅助 TABLE 0"，+1187 B 输出预算内的结构化失配操作数汇总）；B = **Policy Salience**（B0 无 / B1 有，+807 B 的非对称决策规则提醒）。四条件 `a0b0 / a1b0 / a0b1 / a1b1` 均在 X 中**独立重新调用**，不借用 Gate-2 / R1 的 A0B0。所有结论仅为**行为层**解释；ΔAB ≠ 0 只表示两干预的行为效果相互依赖，不等同于任何模型内部机制的因果证明。

---

## 0. 付费前置审计（五项，全部完成后方才付费）

| # | 审计项 | 结论 | 产物 |
|---|---|---|---|
| 1 | R1 GPT pooled DA 0.591→0.591 与 Δ+0.022 口径 | **用户疑点成立：原报告把 cell 加权水平值与 issue 等权差值同栏混用。** 双口径分列（见 §1），不改任何数 | [eal_x_estimand_audit.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/x/eal_x_estimand_audit.json) |
| 2 | Gate-2 / R1 / X 的 cluster bootstrap 估计量 | Gate-2 为 **cell-weighted**（重抽 issue 簇后池化全部 cell），R1 为 **issue-equal**（簇内先均值再等权）。**两者 CI 不可跨口径直接比较**；X 统一冻结为双口径并列、**issue 等权为主** | [eal_stats.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/eal_stats.py) |
| 3 | 四条件 prompt / payload / gold / schema / 参数 / rubric / code hash 冻结 | 完整冻结；88 payload 字节 sha 断言通过；preflight 16 项全 PASS | [eal_v21x_freeze_manifest.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/v21x/eal_v21x_freeze_manifest.json) |
| 4 | 四条件独立重调 | 176 cell 全部为 X 新调用；call_order 为固定交错序（cyclic Latin shift，seed=7），模型/条件在序号上交替 | 同上 `call_order` |
| 5 | 离线 mock + 预算保护 | mock 176 端到端跑通（0 error、$0、raw 先落盘）；`--total-budget-usd 0.001` 在首次发送前硬停、new_rows=0、spend=0 | [eal_v21x_preflight.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/v21x/eal_v21x_preflight.json) |

双闸 `--allow-paid-run` + `--i-acknowledge-x-approved-2026-10-25`；逐请求 BudgetGuard（全局门 + 各模型门）；served 漂移即停（未触发）。

### §1 估计口径审计专节（回应正式指令第 1、2 条）

22 个 fixture 属于 **10 个 issue**，且每 issue 的 cell（fixture）数不等（1 个 issue 12 cell，3 个各 9，3 个各 6，3 个各 3）。因此两种估计量不同：

- **Cell-weighted DA**：`Σ(正确 cell) / Σ(cell)`，大 issue 权重大。
- **Issue-equal-weighted DA**：先在簇内取均值，再对 10 个 issue 等权平均。

重算 R1 vs Gate-2 同 payload structured 复测：

| 模型 | Cell-weighted r0→r1（Δ） | Issue-equal r0→r1（Δ，95% cluster CI） |
|---|---|---|
| GPT-4.1-mini | .5909 → .5909（**0.0000**） | .5111 → .5333（**+0.0222** [−.0333, +.1000]） |
| DeepSeek-flash | .8485 → .8182（**−.0303**） | .8500 → .8167（**−.0333** [−.0833, +.0167]） |

即 R1 报告中的 "0.591 → 0.591 (Δ+0.022)" 是**水平用 cell 口径、差值用 issue 口径**的混栏；两个数各自正确，但不应并列在同一结果栏。本报告起**所有水平与差值都在同一口径内成对报告**。冻结实现：[eal_stats.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/eal_stats.py)（`SEED=7, N_BOOT=10000, cluster=instance_id`，点估计与 CI 严格同一统计量；cell 口径点估计完全复现 Gate-2，CI 仅因簇排序有约 0.005 的 Monte Carlo 级差异）。

---

## A. 四条件 DA（双口径，95% issue-cluster bootstrap）

**主口径 = issue-equal**（10 簇，seed=7，n=10000，同一批 22 fixture 配对）；cell 口径并列供与 Gate-2 口径衔接，**不跨口径比较 CI**。

### DeepSeek-flash

| 条件 | DA issue（主） [CI] | DA cell [CI] |
|---|---|---|
| A0B0 control | 0.8000 [0.6333, 0.9500] | 0.7727 [0.5909, 0.9500] |
| A1B0 assistance | 0.8500 [0.6833, 1.0000] | 0.8182 [0.6316, 1.0000] |
| A0B1 salience | 0.8167 [0.6333, 1.0000] | 0.7727 [0.5600, 1.0000] |
| A1B1 combined | 0.8833 [0.7667, 1.0000] | 0.8636 [0.7368, 1.0000] |

### GPT-4.1-mini

| 条件 | DA issue（主） [CI] | DA cell [CI] |
|---|---|---|
| A0B0 control | 0.4250 [0.2000, 0.6500] | 0.5000 [0.2778, 0.6538] |
| A1B0 assistance | 0.5250 [0.2917, 0.7417] | 0.5455 [0.3333, 0.7037] |
| A0B1 salience | 0.4750 [0.2583, 0.6750] | 0.5455 [0.3529, 0.6774] |
| A1B1 combined | 0.6250 [0.4000, 0.8250] | 0.6364 [0.4500, 0.7778] |

两模型四条件 DA 单调形态一致：combined 最高；GPT 的控制组基线很低（issue .425），干预的上行空间与绝对增益更大。所有 CI 均较宽（仅 10 簇），且效应 CI 下界贴 0（见 B），不支持强因果断言。

## B. 预注册因子效应（issue 主口径，配对方差，cluster bootstrap）

公式（冻结）：ΔA=[(Y10−Y00)+(Y11−Y01)]/2；ΔB=[(Y01−Y00)+(Y11−Y10)]/2；ΔAB=Y11−Y10−Y01+Y00，所有差值针对同一批 fixture 配对。

| 模型 | 效应 | Issue 点 [95% CI] | Cell 点 [95% CI] |
|---|---|---|---|
| GPT-4.1-mini | **ΔA assistance** | **+0.1250 [0.0000, 0.3250]** | +0.0682 [0.0000, 0.2059] |
| GPT-4.1-mini | **ΔB salience** | **+0.0750 [0.0000, 0.2250]** | +0.0682 [0.0000, 0.2308] |
| GPT-4.1-mini | ΔAB interaction | +0.0500 [0.0000, 0.1500] | +0.0455 [0.0000, 0.1538] |
| DeepSeek-flash | ΔA assistance | +0.0583 [0.0000, 0.1167] | +0.0682 [0.0000, 0.1304] |
| DeepSeek-flash | ΔB salience | +0.0250 [−0.0333, 0.0917] | +0.0227 [−0.0526, 0.1000] |
| DeepSeek-flash | ΔAB interaction | +0.0167 [−0.1167, 0.1333] | +0.0455 [−0.1176, 0.1818] |

**解读（行为层，谨慎）**：

1. **Verification Assistance（A）** 方向在两模型上一致为正，GPT 绝对增益更大（issue +.125）。95% CI 下界恰为 0（未跨过 0，但也未给出远离 0 的下界），在 10 簇、22 fixture 的功效下只能读作**方向性、弱证据**的行为改善，不能读作显著因果效应。
2. **Policy Salience（B）** 同样方向为正但更弱（DS 的 CI 跨 0）。
3. **A×B 交互**点估计为正但 CI 宽（DS 跨 0，GPT 下界贴 0）。"只有联合有效"的强交互形态**不成立**——A1B0 与 A0B1 各自已有可见增益；数据与"两干预各自小的正贡献、联合叠加"相容，但不能证明加性。
4. DS 已接近高基线（ceiling），增益空间小，符合其作为阴性/天花板对照的预期。

> 一个必须说明的 bootstrap 现象：GPT 三个效应与 DS-ΔA 的 issue CI 下界都恰为 0。这是配对差值在簇重抽下的真实分布形态（许多簇的配对差值为 0），不是取整或截断；它意味着"无效应"恰落在抽样分布边缘，应与点估计方向一起谨慎解读，而非报为"显著"。

## C. 三态混淆矩阵（每个金标列内三数为该列 fixture 被判为 A=ACCEPT / R=REJECT / N=NEED 的数；Gold 分布 ACCEPT 7 / REJECT 6 / NEED 9；每条件 22 cell）

**DeepSeek-flash**（错误集中在弃权/误拒，从不误受）

| 条件 | ACCEPT-gold (A/R/N) | REJECT-gold (A/R/N) | NEED-gold (A/R/N) |
|---|---|---|---|
| A0B0 | 5 / 1 / 1 | 0 / 4 / 2 | 0 / 1 / 8 |
| A1B0 | 5 / 0 / 2 | 0 / 4 / 2 | 0 / 0 / 9 |
| A0B1 | 5 / 1 / 1 | 0 / 4 / 2 | 0 / 1 / 8 |
| A1B1 | 6 / 1 / 0 | 0 / 4 / 2 | 0 / 0 / 9 |

**GPT-4.1-mini**（错误以非 ACCEPT 金标上的误受为主，随联合干预下降）

| 条件 | ACCEPT-gold (A/R/N) | REJECT-gold (A/R/N) | NEED-gold (A/R/N) |
|---|---|---|---|
| A0B0 | 7 / 0 / 0 | 1 / 4 / 1 | 8 / 1 / 0 |
| A1B0 | 7 / 0 / 0 | 0 / 5 / 1 | 9 / 0 / 0 |
| A0B1 | 7 / 0 / 0 | 1 / 5 / 0 | 8 / 1 / 0 |
| A1B1 | 7 / 0 / 0 | 0 / 6 / 0 | 7 / 1 / 1 |

注：每列三数之和等于该金标数（7/6/9），每行条件合计 22。误受数（非 ACCEPT 金标上判 ACCEPT）：DS 四条件恒为 **0**；GPT 为 9（A0B0：1 REJECT-gold + 8 NEED-gold）、9（A1B0：0+9）、9（A0B1：1+8）、**7**（A1B1：0+7），合计 34。ACCEPT-gold 7 例在 GPT 全部 4 条件均判 ACCEPT（该子集对 GPT 是天花板）；DS 在 ACCEPT-gold 上有少量弃权/误拒。

## D. 错误家族（88 parseable / 模型，跨四条件汇总）

| 家族 | DeepSeek | GPT-4.1-mini |
|---|---|---|
| Unsupported acceptance（判 ACCEPT 而 gold ∈ {REJECT, NEED}） | **0（0.0%）** | **34（38.6%）** |
| Unsupported rejection（判 REJECT 而 gold ∈ {ACCEPT, NEED}） | 5（5.7%） | 3（3.4%） |
| Over-abstention（判 NEED 而 gold ∈ {ACCEPT, REJECT}） | 12（13.6%） | 2（2.3%） |

两模型错误形态**镜像**：DS 偏保守（弃权/误拒，零误受），GPT 偏冒进（大量误受，很少弃权）。GPT 的 34 个 unsupported acceptance 即其低 DA 的直接来源；干预主要把其中一部分从 ACCEPT 移向正确的 NEED（A1B1 的 NEED-gold 误受由 8 降到 7，并有 1 例恢复 NEED）。

## E. 证据操作数与 reason 矛盾的断言比例（冻结 G2.5 标注标准，pass-2 人工裁定）

Pass-1 词表自动计数偏高（DS 14/88、GPT 34/88），因为它把"描述失败证据时出现的 fresh/linked 等词"以及"判 REJECT/NEED 正确但描述性提及属性"也算入。按冻结 rubric 本就要求的 **pass-2 人工确认 affirmative 断言**（否定/含糊/对冲、明确承认 f2p 失败、仅争论相关性等一律移除），独立裁定脚本逐条阅读全部 48 个候选：

| 模型 | Pass-1 auto | **Pass-2 confirmed（字面矛盾断言率）** | 其中作用于 ACCEPT（**operative 充分性幻觉，G2.5 构念**） |
|---|---|---|---|
| DeepSeek | 14 | **6 / 88 = 6.8%** | **0 / 88 = 0.0%** |
| GPT-4.1-mini | 34 | **24 / 88 = 27.3%** | **20 / 88 = 22.7%** |

GPT 各条件 confirmed / operative-on-ACCEPT：

| 条件 | confirmed | operative(ACCEPT) |
|---|---|---|
| A0B0 | 5 | 5 |
| A1B0 | 6 | 6 |
| A0B1 | 6 | 5 |
| A1B1 | 7 | **4** |

关键观察：**combined 条件下 GPT"作用于 ACCEPT 的充分性幻觉"从控制组的 5 降到 4，且是唯一出现该下降的条件**；但字面矛盾断言总数未降（A1B1 反而 7），说明干预主要改变了部分案例的**最终判决**（使模型在承认证据不足时落到 NEED 而非 ACCEPT），并未消除其在 reason 中做出与操作数矛盾的属性断言的倾向。这与 DA 增益集中在判决层一致。DS 的 operative-on-ACCEPT 在所有条件恒为 0。裁定逐行理由（含移除规则：af83be49 / a242cd7a / f0c49f82 / f51defe8 / 403163cb / faae0894 / c637f604 的具体依据）见 [eal_v21x_live_reason_adjudication.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/v21x_runs/eal_v21x_live_reason_adjudication.json)。

## F. 预注册 8 历史案诊断（G2.5 NEED→ACCEPT；诊断子集，**不替代全 22 主分析**）

8 案（`62dfb1c6 / 2c11095a / e4e8b26c / c637f604 / ec813709 / a25d0cf5 / 403163cb / c59a8ceb`，覆盖 freshness / coverage(p4) / linkage）：

| 模型·条件 | 仍判 ACCEPT | 恢复 NEED | 其他（REJECT） |
|---|---|---|---|
| DS A0B0 | 0 | 7 | 1 |
| DS A1B0 / A0B1 / A1B1 | 0 | 8 | 0 |
| GPT A0B0 / A1B0 / A0B1 | **8** | 0 | 0 |
| GPT A1B1 | **7** | **1**（`c637f604`） | 0 |

- **DS** 在 X 全部四条件对这 8 案零误受（A0B0 的 1 例 REJECT 也是非 ACCEPT），与其零 unsupported acceptance 一致。
- **GPT** 在单独 A1 或单独 B1 下 **8 案全部仍判 ACCEPT**——两个干预单独都不能纠正这类历史稳定错误；**唯一恢复发生在 A1B1 联合条件，且仅 `c637f604` 1 例**（该例 pass-2 reason 中也明确承认了其 f2p 失败）。这是"联合干预对最顽固错误有边际作用、但远未消除"的直接证据：8 案中 7 案（87.5%）即使在 combined 下仍稳定误受。

## G. R1 稳定性 × X 的敏感性（不把单次翻转解释为干预效应）

1. **控制组必须重跑——实证成立**。把 X 的 A0B0（全新批次、同冻结 payload）与 Gate-2、R1 三个时间点对齐：两模型各有 **20/22 fixture 三次判决完全相同、各 2 个发生漂移**：
   - DS：`c564f50f`（gold ACCEPT）A→N→R；`c637f604`（gold NEED）N→R→R。
   - GPT：`faae0894`（REJECT→REJECT→NEED）；`a242cd7a`（ACCEPT→NEED→ACCEPT）。
   这证实了即使 temp=0、payload 逐字节相同，跨批次仍存在约每模型 2/22 的判决漂移；因此 X 的配对设计（同批四条件、同 fixture 配对）与"不借用历史控制组"是必要的，**跨批次的单次翻转不能归因于干预**。
2. **两个慢性振荡 adjudicated cell**（`59e46a77`、`ec813709`，Gate-2/R1 间已记录）在 R1 上下文再次标注：GPT 这两例在 Gate-2/R1 分别为 REJECT/NEED 与 ACCEPT/NEED，属高重测方差；X 效应不因这两例单独成立（A1B1 恢复的 `c637f604` 不在慢性振荡名单内）。
3. 8 历史案在 Gate-2、R1 两次均 8/8 复现，X 控制组第三次仍 8/8 GPT 误受；故 A1B1 对 `c637f604` 的 1 例恢复虽只有 1 例，但发生在一个此前三次都稳定误受的案例上，其作为"联合干预行为信号"的可信度高于普通随机翻转——但仍只是 1 例，不作总体推断。

## H. 工程与冻结审计

| 项 | DeepSeek-flash | GPT-4.1-mini |
|---|---|---|
| 成功 / parseable | 88 / 88 | 88 / 88 |
| INVALID / AMBIGUOUS / API_ERROR / retries | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| served model id | `deepseek-flash` ×88 | `gpt-4.1-mini-2025-04-14` ×88 |
| served 与期望一致 / 零漂移 | 是 | 是 |
| 输入 / 输出 token | 478,112 / 32,204 | 454,332 / 17,874 |
| 费用 | $0.182078 | $0.210331 |
| 墙钟（总 / 均） | 246.6 s / 2.80 s | 186.3 s / 2.12 s |
| temp0 / max4096 / json_object / 无工具 | 全是 | 全是 |
| raw 先于解析落盘 | 88/88 | 88/88 |

**合计 $0.392409 ≤ $1.50 硬上限**（用 26%），BudgetGuard 每请求前预检、全局 $1.50 + 各 $0.75 双门生效。冻结 hash：prompt/payload/gold/schema/采样参数/rubric/code 全部在 [freeze manifest](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/v21x/eal_v21x_freeze_manifest.json)；付费运行只校验 canonical 一致、不重写 freeze。运行审计 [eal_v21x_live_run_audit.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/v21x_runs/eal_v21x_live_run_audit.json)，独立分析 [eal_v21x_live_analysis.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/v21x_runs/eal_v21x_live_analysis.json)。

**外部效度限制（沿用）**：API 不返回可核验的权重版本哈希，只能确认声明 id 字符串未漂移，无法排除同 id 下静默服务端版本变化；10 个 issue 簇导致 CI 宽、功效有限；观测均为行为输出。

---

## 结论

1. **X 在预算与纪律内完成**：176/176、$0.3924、零错误、四条件全新独立调用、全部冻结 hash 一致。
2. **干预的行为效果方向一致但证据偏弱**：Verification Assistance（A）在两模型上方向为正（GPT issue +.125），Policy Salience（B）更正但更弱（DS 跨 0），A×B 为正但宽 CI。所有关键 CI 下界贴 0 或跨 0，**不支持"统计显著的因果效应"声明**，只支持"在本 22 fixture 上方向性的行为改善"。
3. **作用机制的行为线索**：combined 是唯一降低 GPT"作用于 ACCEPT 的充分性幻觉"（5→4）并唯一恢复一例历史顽固误受（`c637f604`）的条件；但字面矛盾断言倾向未消除，8 历史案 7 例在最强干预下仍误受。这更像"改变最终决策落点"而非"纠正证据推理"。
4. **控制组三时间点 2/22 漂移**实证支持了配对设计与禁用历史控制组的决定；效应解读已把该重测噪声纳入，未把单次翻转当干预效应。
5. 两模型错误形态镜像（DS 保守零误受 / GPT 冒进 38.6% 误受），干预主要影响 GPT 的误受家族。

**已停止**：未运行 R2 / Gate 3 扩样 / Gemini / 其他模型，未新增 Issue，未修改 E1 / CEE / Gate-2 / G2.5 / R1 / v2.1 冻结数据，**未提交 git**。等待下一次书面批准。
