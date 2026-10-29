# GroundedReview Gate 3-B 报告 — External Feasibility Pilot（100 真实 Cell）

- 报告版本：g3b-report-v1。定位：**外部可行性 Pilot（小样本、单仓库、Provisional Gold）**。
- 授权依据：用户书面**有条件批准** Gate 3-B：10 个全新独立 SymPy issue × 5 冻结条件 × 2 模型 = **100 个真实付费 Cell**；新增总预算硬上限 **$3.00**、每模型 **$1.50**。
- Gold 状态：全程 **Provisional（mechanically adjudicated, human-agreement pending；annotator2 = NOT_OBTAINED 10/10，n=1）**。本轮**不是**独立人工 Gold 验证，不报 κ，结论仅停留在行为层。
- 未触碰红线：未新增 issue/镜像，未改 prompt/gold/证据/既有冻结结果，未用 Gemini/R2/Gate 3-C，**零 git commit**。
- 执行完成后**立即停止**，等待下一次书面批准。

---

## 0. 一句话结论（先给判断，后给证据）

在 10 个**独立** issue 上，旧 Fixture 的两条方向性错误模式出现了**不对称复现**：

- **C2（DeepSeek 充分证据下过度弃权）稳健复现**：10 个 issue 中 **9 个**在任一充分条件下仍弃权（点估 0.90，issue-cluster 95% CI **[0.70, 1.00]**，下界 > 0；精确 CP **[0.555, 0.998]**）。其保守行为不太可能仅由旧镜像结构造成。
- **C1（GPT 错误接受）仅弱复现、未达确认标准**：3 个 gold-REJECT issue 中 **1 个**（17318）在充分条件下被 ACCEPT（点估 0.33，但 issue-cluster 95% CI **[0.00, 1.00]**、精确 CP **[0.008, 0.906]**，下界贴 0）。这是"值得继续研究的苗头"，**不能**外推为 33.3% 的普遍错误率。
- 两个**受限**条件下两模型均 **10/10 正确弃权、零不当承诺**；但这只衡量"会弃权"，**不**解释为受限条件下的推理/校准能力差异。

---

## 1. 付费前 5 项门（用户指令 1–5）：全部满足后才产生费用

| 门 | 结果 | 证据 |
|---|---|---|
| ① 冻结清单/10 issue/Gold/五条件/Prompt/参数/评分/代码 Hash 核验 | PASS | freeze 重建后 on-disk == canonical；父冻结 **G3-A 141 + G3-A.1 122** 文件逐一复算 0 改动 |
| ② Condition Gold ↔ Oracle Gold 对应 + 欠定/来源不可用/制度性信任披露 | PASS | T2D-T、T3D-Strict 各 10/10 NEED；Escalate/T2A/T3A 与 oracle 完全一致（7 ACCEPT/3 REJECT）；oracle↔condition 分歧 20；T2A 充分性标注为**制度性信任假设** |
| ③ annotator2=NOT_OBTAINED 保留、Gold 不自动升级 | PASS | 10/10 仍 NOT_OBTAINED；结果冻结显式标注 Provisional |
| ④ 独立 Label Leakage Audit + Evidence Sufficiency + BudgetGuard Selftest + 全量 Mock | PASS（21/21） | [g3b_preflight.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3b/preflight/g3b_preflight.json)；全量 mock 100 cell 零 error、$0 |
| ⑤ 任一失败即停、不静默改冻结材料 | 遵守 | 审计曾两次 FAIL（误报/分层），均**修正审计代码并重建 freeze**，未改任何 prompt/gold/证据 |

泄漏审计的两处关键设计：
- 结果词（`FAIL_TO_PASS/PASS_TO_PASS`）**仅在 tier D 禁止**；tier A/Escalate 呈现聚合验收结果（如 `FAIL_TO_PASS passed: 1/1`）是该条件本应提供的证据，不是泄漏。
- D 层结果屏蔽由结构性投影检查独立保证：coverage 端点只返回"执行了多少/声明了多少"，明文 *reports no pass/fail outcomes*。

## 2. 执行纪律（用户指令 6–10）

- **⑥ T3 = 真实多轮工具会话**：30 个 active cell/模型全部产生 ≥1 次真实 HTTP 工具调用（静态 T2D/T2A 全部 0 工具、单轮）。复用冻结的真实 evidence server（[server.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/server.py)），在 g3a store 的**隔离临时副本**上运行，冻结 store 零写入。
- **⑦ 一次有效判决、零重试**：100/100 行 `retries=0`；无任何因"预测不合预期"的重试。
- **⑧ 全字段保留**：decision/reason/missing_evidence/evidence_gap/tool_trace/tokens/cost/wall/served id/error 均逐 cell 落盘（见结果 jsonl）。
- **⑨ 双显式授权门 + 逐请求 BudgetGuard**：须同时给 `--allow-paid-run --i-acknowledge-g3b-approved`，否则 REFUSED（selftest 已验证裸调/缺 ACK 均被拒）；每次模型调用前 pre-call bound 检查；resume 累计既有花费。
- **⑩ 漂移即停**：served id 与期望逐一比对，**零漂移**——`deepseek-flash`×50、`gpt-4.1-mini-2025-04-14`×50。

### 工具协议实测审计（区分"门存在"与"live 是否撞门"）
| 现象 | DeepSeek-flash | GPT-4.1-mini |
|---|---|---|
| 静态 cell 出现工具调用 | 0/20 | 0/20 |
| T3D-Strict 接受日志硬墙尝试 / live 观察到 403 | **0 / 0** | **0 / 0** |
| T3D-Escalate 升级请求 / 批准 / 无 reason 拒绝 | 30 / 30 / 3 | 5 / 5 / 0 |
| T3A 下 claim_contradicted 的 issue | 17318,17630,19783 | 17318,17630,19783 |

**必须如实说明**：live 中两模型在 Strict 下**都没有去请求被墙的 acceptance-log 工具**，因此 live 的 403 计数为 0；它们改用授权诊断工具（linkage/freshness/coverage/consistency/run_log）后弃权。403 硬墙本身存在于冻结 server，并在**零成本全量 mock** 中被脚本主体实测触发（`log:missing_reason` 与 403 路径）。Escalate 的 reason 门控在 live 中被真实触发（DS 有 3 次无 reason 被 400 拒绝后，带 reason 获 200+banner 批准）。

## 3. 费用 / 预算 / 模型版本（用户指令 18）

| 模型 | Cell | 输入 tok | 输出 tok | 实际费用 | 模型调用总数 | 墙钟(s) |
|---|---|---|---|---|---|---|
| deepseek-flash | 50 | 531,239 | 26,112 | **$0.190706** | 280 | 217.1 |
| gpt-4.1-mini | 50 | 216,846 | 8,260 | **$0.099952** | 100 | 132.9 |
| **合计** | **100** | 748,085 | 34,372 | **$0.290658** | 380 | 350.0 |

- 总费用 **$0.291**，对 **$3.00** 硬顶约 **10.3×** 余量；每模型均远低于 **$1.50** 帽。无 BudgetGuard 中止（audit `stop_msg=""`、`within_total_cap=true`）。
- 参数：temperature **0**、completion_cap **8192**、max_tool_turns **8**、max_model_calls/cell **12**、prompt **p3-ternary-v2**；100 行共享单一 freeze sha 与单一 runner sha。

---

## 4. 主要结果（用户指令 11–15）

> 独立单位 n = **10 个 issue**；100 个 cell 是 issue 内的重复测量，**未**当作 100 个独立样本。主比较只在 5 个冻结条件内进行，**不与 E1 的 22 fixture 合池**。

### 4.1 C1 — GPT 在 3 个 gold-REJECT issue 上的错误 ACCEPT（确认性、方向性）
- 指标：issue 在三个充分条件（Escalate/T2A/T3A）中**任一** ACCEPT（issue 内 OR 合并不增加独立 n）。
- 结果：**k = 1/3**，唯一错误接受 = **issue 17318**，且只发生在 **T2A-T**；Escalate 0/3、T3A 0/3。
- 精确区间（Clopper-Pearson）：**[0.0084, 0.9057]**；issue-cluster bootstrap（B=10000, seed=7）：**[0.00, 1.00]**。
- 判定：点估 > 0（方向性"苗头"成立），但 bootstrap 下界 = 0，**未满足预注册的确认标准**。按用户预判措辞：即使 1/3 也值得进一步研究，但**不得**宣称 33.3% 的普遍规律。
- **机制（verbatim 摘要）**：GPT 17318/T2A 称 *"All scoped acceptance tests pass with no failures or regressions"* 并据此 ACCEPT；但同一 issue 在其 T3A/T3D-Escalate 多轮中，模型自己读到 `test_issue_12420` 失败并判 REJECT。即：在单轮制度性信任条件下，它**忽略/覆盖了已呈现的 F2P 失败信号**。

### 4.2 C2 — DeepSeek 在 10 个充分证据 issue 上的错误弃权（确认性、方向性）
- 指标：issue 在三个充分条件中**任一**判 NEED_EVIDENCE。
- 结果：**k = 9/10**（唯一未在任一充分条件弃权的是 gold-REJECT 的 17318，它在三条件都正确 REJECT）。
- 精确 CP：**[0.5550, 0.9975]**；issue-cluster bootstrap：**[0.70, 1.00]**（下界 > 0）→ **方向性稳健复现**。
- 按 oracle gold 分层：**ACCEPT issue 7/7 全部过度弃权（1.00）**；REJECT issue 2/3 过度弃权（0.67）。
- 按条件（探索性，分母 10）：Escalate 6/10、**T2A 9/10**、T3A 8/10。
- **机制（verbatim 摘要）**：在 **T2A 已制度性假定 linkage 可信、声明集即全集**的条件下，DS 仍以 *"linkage … cannot be confirmed … not trustworthy for THIS patch"*（13615，gap=`linkage_mismatch`）和 *"1/1 … far too thin … does not verify linkage"*（24443，gap=`coverage_incomplete`）弃权——即对证据施加了**高于该条件所提供的信任/覆盖门槛**。

### 4.3 两个受限条件：正确弃权单列（指令 13）
| 条件 | GPT 正确 NEED | DS 正确 NEED | 不当承诺 |
|---|---|---|---|
| T2D-T | 10/10 | 10/10 | 0 |
| T3D-Strict | 10/10 | 10/10 | 0 |

两模型在受限条件下弃权完全正确，但**只**说明它们在证据被扣减时会 abstain；不与充分条件的 DA 一起解释为推理能力差异。

### 4.4 Oracle DA 与 Condition DA 分列（指令 11）
充分条件下 condition gold == oracle gold，故二者数值相同；受限条件下 condition gold=NEED 而 oracle 为 7 ACCEPT/3 REJECT，二者**刻意分离**：

| 条件（gold 分布） | GPT condDA | GPT oracleDA | DS condDA | DS oracleDA |
|---|---|---|---|---|
| T2D-T（10 NEED） | 1.00 | 0.00 | 1.00 | 0.00 |
| T3D-Strict（10 NEED） | 1.00 | 0.00 | 1.00 | 0.00 |
| T3D-Escalate（7A/3R） | 0.20 | 0.20 | 0.40 | 0.40 |
| T2A-T（7A/3R） | **0.80** | 0.80 | **0.10** | 0.10 |
| T3A-T（7A/3R） | 0.30 | 0.30 | 0.20 | 0.20 |

读法：DS 在**单轮 T2A** 反而比需要主动取证的 T3A 更常弃权（0.10 vs 0.20），说明其保守不是"不会用工具"，而是**对制度性可信证据也拒绝采信**；GPT 则在 T2A 最敢承诺（0.80，含唯一一次错误接受）。

### 4.5 配对分析（指令 14–15）
- 两模型逐条件判决一致率：T2D **1.00**、Strict **1.00**、Escalate 0.80、**T2A 0.10**、T3A 0.90。最大分歧出现在 T2A——GPT 接受处 DS 多弃权。
- issue 内"充分条件承诺率 − 受限条件承诺率"（cluster bootstrap 95%）：GPT **+0.467 [0.333, 0.667]**；DS **+0.233 [0.033, 0.467]**。两者都会在证据变多后更多承诺，但 GPT 的响应幅度约为 DS 的两倍。
- C1/C2 预注册方向：C2 **复现**；C1 仅点估计方向出现、区间未排除 0（**未复现到确认强度，非反向**）。

## 5. 按 Issue 原始判决 / 错误家族 / 来源验证（指令 16）

判决缩写 A=ACCEPT R=REJECT N=NEED_EVIDENCE；og=oracle gold；两个受限条件两模型均为 N/N（未列入）。

| issue | og | GPT Esc | GPT T2A | GPT T3A | DS Esc | DS T2A | DS T3A |
|---|---|---|---|---|---|---|---|
| 13615 | A | N | **A** | N | A | N | N |
| 13974 | A | N | **A** | N | N | N | N |
| 15349 | A | N | **A** | N | N | N | N |
| 17318 | **R** | R | **A ←C1 错误接受** | R | R | R | R |
| 17630 | **R** | N | N | R | R | N | N |
| 19783 | **R** | R | R | R | R | N | R |
| 20590 | A | N | **A** | N | N | N | N |
| 21847 | A | N | **A** | N | N | N | N |
| 24213 | A | N | **A** | N | N | N | N |
| 24443 | A | N | **A** | N | N | N | N |

- 错误家族（充分条件、按 condition/oracle gold 计；解析失败单列）：
  - GPT：**过度弃权 16**、**错误接受 1**、错误拒绝 0、解析/传输失败 **0/50**。
  - DS：**过度弃权 23**、错误接受 **0**、错误拒绝 0、解析/传输失败 **0/50**。
- 来源验证：**每个 active cell（30/模型）都带 `fresh_false`**——这是**结构性、非区分性**信号（attestation 记录的是 2026-10-25 的历史执行树，freshness 端点对历史记录返回 fresh=false）。真正区分 REJECT 的是 **T3A 下仅 17318/17630/19783 三个 REJECT issue 出现 `claim_contradicted`**，7 个 ACCEPT issue 无一出现。
- 数据质量观察：**DS 15/50 行返回空 `reason`**（decision JSON 有效、可解析，但理由串为空；GPT 0/50）。这不改变判决计数，但削弱部分 DS 结论的可解释性，已在结果冻结记录。

## 6. Gold 敏感性（指令 17，三口径；不事后改 Gold）

| 口径 | n | C1（GPT 错受） | C2（DS 过弃） |
|---|---|---|---|
| 当前 Provisional（全部） | 10 | 1/3，CP [0.008,0.906] | 9/10，CP [0.555,0.998] |
| 剔除 3 个 REJECT issue | 7 | **不可估计**（无 REJECT） | **7/7，CP [0.590,1.000]** |
| 剔除已记录实质争议 issue | 10 | 同口径一（**记录争议数=0**） | 9/10 |

说明：因第二标注者从未取得，仲裁台账中**没有**已记录的实质争议条目，故口径三与口径一数值相同；这不等于 Gold 无不确定性，仅表示争议尚未被观测。在纯 7 个 ACCEPT issue 上，DS 过度弃权 7/7 的下界仍 > 0.5，结论对"是否纳入 REJECT issue"稳健；而 C1 完全由 3 个 REJECT issue 决定，剔除即不可估计，凸显其证据脆弱性。

---

## 7. 采集后分析器修订的诚实披露（不掩盖）

数据采集**完成之后**，离线分析器 [g3b_analyze.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/g3b_analyze.py) 的精确区间函数被修正：初版网格尾概率搜索在端点返回退化的 0.0/1.0；已替换为精确 Beta 分位数 Clopper-Pearson，并用标准 CP 表（k=0/10、1/3、9/10、5/10 等）逐一校验通过。
- 影响范围：**仅打印的精确区间数值**；不涉及任何模型调用、判决、DA 计数、bootstrap 点估/区间或方向性结论。
- **freeze manifest、runner、prompt、gold、证据、100 行结果全部未改**；记录于每行的 freeze sha（`728a0731…`）与 runner sha（`c9a7651e…`）仍与磁盘一致。为保留该锚定，**刻意未重建数据采集 freeze**；修订在 [g3b_result_freeze.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3b/freeze/g3b_result_freeze.json) 的 `post_collection_analyzer_change_disclosure` 中留痕（采集时哈希 913e8319 → 当前 3cdcaf1c）。

## 8. 威胁与边界

1. **Provisional Gold / n=1 标注**：所有"正确/错误"均相对单人机械裁决 Gold；3 个 REJECT 的 F2P 关联性未经第二人确认。结论可能随未来人工仲裁翻转（单个 REJECT 翻转即约 33.3pp）。
2. **n=10（C1 分母仅 3）**：区间极宽，尤其 C1 不能做总体率外推；这是可行性 Pilot，不是效果量的确认测量。
3. **单仓库（SymPy）、两模型、单一冻结协议快照**：跨仓库/模型族/时间的泛化未知。
4. **T2A"充分"是制度性信任假设**：DS 对该假设的拒绝（linkage/coverage 质疑）既可能是健康的怀疑，也可能是对任务设定的不遵从；本轮无法区分，已在解读中保留。
5. **fresh_false 恒真**：多轮中最常见的信号无区分度；真正有判别力的是 claim_contradicted（仅 3 REJECT）。
6. live 未在 Strict 实际撞击 403（模型绕行）；硬墙有效性仅由零成本 mock 直接验证、由冻结 server 代码保证。

## 9. 交付物与冻结索引

- 数据采集 freeze：[g3b_freeze_manifest.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3b/freeze/g3b_freeze_manifest.json)（sha `728a0731…`）
- 结果冻结（附录）：[g3b_result_freeze.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3b/freeze/g3b_result_freeze.json)
- 付费前审计：[g3b_preflight.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3b/preflight/g3b_preflight.json)（21/21 PASS）
- 逐 cell 结果：[deepseek](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3b/runs/g3b_live_deepseek_flash_results.jsonl) / [gpt](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3b/runs/g3b_live_gpt_41_mini_results.jsonl)；[run audit](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3b/runs/g3b_live_run_audit.json)
- 全量零成本 mock：[deepseek](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3b/runs/g3b_mock_deepseek_flash_results.jsonl) / [gpt](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3b/runs/g3b_mock_gpt_41_mini_results.jsonl)
- 分析结果：[g3b_live_analysis.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3b/analysis/g3b_live_analysis.json)

## 10. 停止声明

Gate 3-B 已按授权范围全部完成：100 个真实 cell、总费用 **$0.291**（≤ $3.00）、零 error/零重试/零漂移、Gold 保持 Provisional、零 git commit。**现停止，不发起 Gate 3-C、不扩样、不新增模型；等待下一次书面批准。**
