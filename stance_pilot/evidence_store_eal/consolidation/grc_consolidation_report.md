# GroundedReview — Research Consolidation Gate 报告（零 API · 离线收束）

- 授权：用户 2026-10-26 书面验收 Experiment X，仅批准本轮 **$0 离线
  Research Consolidation**；不批准新付费实验、Gate 3 扩样、R2、Gemini、
  新 Issue、git commit。
- 纪律：全部新分析写入独立目录 [consolidation/](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/consolidation)；
  新代码前缀 `grc_`（[evidence/](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence)）；
  E1/CEE/EAL/R1/X 冻结产物全程只读。**零模型调用、零新增 Issue、零样本构建。**
- 本报告对应授权任务 1–9。所有数值由独立 `grc_*` 代码从冻结产物重算。

---

## 0. 交付清单

| 任务 | 代码（只读新增） | 产物 |
|---|---|---|
| 1 冻结确认 | — | 未改动任何既有产物；本轮仅在 consolidation/ 与 evidence/grc_* 新增 |
| 2 独立统计重算 | [grc_recompute.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/grc_recompute.py) | [grc_x_recompute.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/consolidation/grc_x_recompute.json) |
| 3 盲法复核 | [grc_blind_packet.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/grc_blind_packet.py)、[grc_blind_unblind.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/grc_blind_unblind.py) | [grc_blind_packet.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/consolidation/grc_blind_packet.json)、[grc_blind_key_SEALED.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/consolidation/grc_blind_key_SEALED.json)、[grc_blind_coding.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/consolidation/grc_blind_coding.json)、[grc_blind_unblind.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/consolidation/grc_blind_unblind.json) |
| 4 逐 Issue 分布 | [grc_issue_distribution.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/grc_issue_distribution.py) | [grc_issue_distribution.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/consolidation/grc_issue_distribution.json) |
| 5 八案串联 | [grc_chronic8_linkage.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/grc_chronic8_linkage.py) | [grc_chronic8_linkage.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/consolidation/grc_chronic8_linkage.json) |
| 6 论文草稿 | — | [grc_paper_draft.md](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/consolidation/grc_paper_draft.md) |
| 8 Gate 3 设计 | [grc_gate3_power.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/grc_gate3_power.py) | [grc_gate3_power.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/consolidation/grc_gate3_power.json)、[grc_gate3_design.md](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/consolidation/grc_gate3_design.md) |

---

## 1. 独立统计重算（任务 2）——逐值一致

`grc_recompute.py` **不导入** X 分析器/统计模块，独立重写整簇 bootstrap
（10 个 issue 簇、seed=7、10,000 次、2.5/97.5 百分位），与冻结
[eal_v21x_live_analysis.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/v21x_runs/eal_v21x_live_analysis.json)
交叉校验：**`exact_match_all=true`，0 处不一致**。

复现的四条件 DA（issue 主口径 [bootstrap CI]）：

| 条件 | deepseek-flash | gpt-4.1-mini |
|---|---|---|
| a0b0 | .800 [.633,.950] | .425 [.200,.650] |
| a1b0 | .850 | .525 |
| a0b1 | .817 | .475 |
| a1b1 | .883 | .625 [.400,.825] |

因子效应（issue 等权）：GPT ΔA **+0.125 [0,.325]**、ΔB **+0.075 [0,.225]**、
ΔAB **+0.050 [0,.150]**；DS ΔA +.058[0,.117]、ΔB +.025[−.033,.092]、
ΔAB +.017[−.117,.133]。

**统计口径澄清（重要）**：GPT 三个区间**下界恰为 0**，不是统计显著——
"无效应"落在重采样分布边缘，仅构成方向性弱证据；DS 的 ΔB/ΔAB 跨 0。
错误家族(/88) 复现一致：GPT unsupported_accept **34 (38.6%)** / reject 3 /
over_abstain 2；DS accept **0** / reject 5 / over_abstain **12**。
执行事实复核：176/176 成功、$0.392409（<$1.50 上限）、0 错误；四条件均
重新调用、served 模型 88/88 一致。

## 2. 盲法复核（任务 3）——方法学疑问的直接回应

严格按授权要求：盲包 48 条（与 shipped pass-1 候选集逐一同构断言通过，
14 DS + 34 GPT），每条**只含**机械操作数事实、完整理由、被命中属性；
**不含**模型名/条件/gold/判决/旧 pass-2（shuffle seed 20261026，映射表
[grc_blind_key_SEALED.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/consolidation/grc_blind_key_SEALED.json)
在编码完成后才打开）。证据操作数完整保留。

揭盲结果（[grc_blind_unblind.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/consolidation/grc_blind_unblind.json)）：

- 总体原始一致率 **0.854**，Cohen's κ **0.71**。
- **GPT（34 单元）：一致 0.971，κ 0.93**；盲判 confirmed 25 vs pass-2 24。
  **促成误受（operative-on-accept）数两轮完全相同 = 20/34**，分条件
  5/6/5/4（a0b0/a1b0/a0b1/a1b1）。核心结论"约 3/5 的误受携带与证据矛盾
  的肯定断言"对盲法稳健。
- **DS（14 单元）：一致 0.571，κ 0.00**；盲判 confirmed **0** vs pass-2 6。
  6 个分歧**全部是 NEED_EVIDENCE 弃权单元**：理由都**显式、正确地**报告了
  tree/sha 失配或执行内失败测试并弃权；pass-1 词表命中的是文中别处的肯定
  词（如 "cannot confirm complete, fresh…"），宽口径 pass-2 计入，严格字面
  规则下应为"正确承认"而非矛盾断言。**两轮 operative-on-accept 均为 0**——
  DS 从未把矛盾断言与误受结合。
- 唯一反向：GPT faae0894/a1b0（先论证 REJECT 后反转，明确断言 "coverage
  complete/fully executed"，而 102/102 p2p 缺席）盲判 P3 confirmed，但该单元
  最终判决 NEED，不构成 operative。

**局限如实标注**：pass-3 是**同一编码者、部分盲**的敏感性检查，不是独立
标注者信度——存在残留回忆，且 assisted 单元文本可能提及所给计数表从而
泄露条件。因此结论应表述为：盲法**加固了 GPT operative 矛盾计数（20 稳定）**，
同时表明 **DS 的非 operative 计数（6）处在编码约定边界、对口径敏感**，不应
当作无标注误差的客观测量。Gate 3 设计已要求至少一名独立于发现团队的编码者。

## 3. 逐 Issue 错误分布（任务 4）

34 次 GPT unsupported acceptance 的分布（[grc_issue_distribution.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/consolidation/grc_issue_distribution.json)）：

- 横跨 **10 个独立 issue 中的 9 个**；**issue 等权率（在可误受单元上）
  0.662，高于 cell 加权率 0.567**——错误并非由最大簇放大。最大单一 issue
  sympy-14531 占 8/34（0.235）。
- 但 **fixture 粒度上 34 次仅来自 9 个不同 fixture**（7 个在四条件全部误受、
  2 个仅部分条件），且 **24/34 次落在镜像对的负向 fixture 内**（与某 valid
  fixture 共享 artifact base 的 stale/wrong 变体）。独立错误*实例*更接近
  9 fixture / 9 issue，而非 34 cell。这直接支持"Gate 3 主攻新独立 issue、
  禁止主队列镜像配对"。

## 4. 八历史案串联（任务 5）

G2.5(structured) / R1(structured) / X 四条件逐案（[grc_chronic8_linkage.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/consolidation/grc_chronic8_linkage.json)）：

- **GPT：7/8 稳定误受**（所有时间点×所有条件均 ACCEPT）；唯一受干预影响的
  c637f604 仅在 **a1b1（两因子联合）** 恢复 NEED，此前 G2.5/R1/a0b0/a1b0/
  a0b1 全部误受。
- **DS：7/8 稳定正确弃权**；c637f604 在 R1 摆到 REJECT、其余时间点 NEED，
  属边界慢性振荡而非干预响应。
- 全 22 fixture 的三时间点（Gate2/R1/X-a0b0）各模型 20/22 判决一致，各 2
  漂移（DS: c564f50f、c637f604；GPT: faae0894、a242cd7a）。

## 5. 论文草稿与 Threats（任务 6、7）

[grc_paper_draft.md](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/consolidation/grc_paper_draft.md)
将 Results 分为 **Evidence Acquisition (E1) / Decision Policy over
pre-adjudicated evidence (CEE) / Evidence Verification (EAL/G2.5) /
Factorial corrections (X) / Error families / 盲法理由编码 / Issue 集中度 /
跨时稳定性 / Reliability**，Discussion 收束为用户拟定的三观察主线，全部
用行为层措辞（Verification Assistance / Policy Salience；ΔAB≠0 仅表相互
依赖）。Threats to Validity 覆盖要求的全部九项：仅 10 issue、单仓库、镜像
fixture、预裁决事实、Derived Summary、模型版本、temp0 非确定性、主观理由
编码、实验条件与证据长度混杂。

## 6. Gate 3 设计（任务 8，仅设计不执行）

[grc_gate3_design.md](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/consolidation/grc_gate3_design.md)
+ 离线功效模拟 [grc_gate3_power.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/consolidation/grc_gate3_power.json)。
要点：新独立 issue 抽样规则（**主队列禁止镜像配对**、机械资格筛选、分层
但不手挑类别）、六项证据质量门（linkage/freshness/coverage/原始日志保留/
探针溯源/无标签泄漏）、机械 oracle + 盲于模型输出的独立人工 gold 仲裁、
含独立编码者的盲法理由编码、k=3 temp0 重复以直接测重测信度、长度匹配
对照以分离 A 因子的长度混杂。

功效（基于冻结 X 的 issue 级配对差值经验离散度，20,000 次模拟）：错误模式
**复现/现患率目标（P1/P2）约 30 个新 issue 足够**；但要确认 GPT ΔA 在
≈0.125 的因子效应需约 **60 个独立 issue**（该效应 issue 间异质性大，
SD 0.317，n=30 功效仅 .55、n=60 达 .85）。预算按 X 实际单价 $0.00223/调用
估算：两模型×四条件，30 issue k=3 ≈ **$1.61**，60 issue k=3 ≈ **$3.20**
（仅规划数字，非授权）。

## 7. 研究判断与停止点

本轮离线证据支持收束后的核心主张：
1. 两类 Reviewer 的错误校准方向相反——GPT 倾向**过早、与证据矛盾的接受**，
   DS 倾向**过度弃权**且不产生 operative 矛盾断言。
2. 该 GPT 模式跨 9/10 issue、7/8 历史案与全部时间点稳定，**两种提示干预
   均未被证明能可靠消除它**（CI 贴 0、样本仅 10 簇、噪声同量级）。
3. 盲法复核把"24/6"修正为更诚实的表述：**operative（误受相关）矛盾计数
   GPT 20 稳健、DS 0 稳健**；非 operative 的宽口径计数对编码约定敏感。

**建议维持用户决定**：不扩样、不跑 R2/Gemini、不在 22 旧 fixture 上继续
调 prompt；下一笔真正有预算的工作留给 Gate 3 的独立 issue 外部验证（30
issue 复现队列优先，因子确认另行扩至 60）。

本轮到此**停止**，等待下一次书面批准：零 API 调用、零新 Issue、零 Gate 3
样本构建、E1/CEE/EAL/R1/X 冻结数据未改、未 git commit。
