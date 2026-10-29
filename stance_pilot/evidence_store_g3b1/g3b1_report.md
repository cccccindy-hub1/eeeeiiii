# GroundedReview — Gate 3-B.1 独立构念效度审计报告

零 API · 不新增 Issue · 不修改任何 Gate 3-B 冻结产物 · 不提交 Git

- 代码：`evidence/g3b1_audit.py`（新文件，`g3b1_` 前缀；**刻意不 import `g3b_analyze`**，用独立实现跨校验；仅离线读取冻结数据）
- 机器结果：`evidence_store_g3b1/audit/g3b1_independent_audit.json`
- Gold 敏感性 changelog：`evidence_store_g3b1/audit/g3b1_gold_sensitivity_changelog.md`
- 方法：Clopper–Pearson 用整数二项式尾部求和（`math.comb`）+ 二分，非 Beta 分位数路径；bootstrap 用私有 `random.Random`、issue 簇重采样 B=50000、seed=20261026。
- 本阶段新增模型调用：**0**；新增 Issue：0；Git commit：0（冻结基线 HEAD=2097ecd）。

术语遵循审批意见：DeepSeek 的现象统一称 **Protocol-Relative Over-Abstention（协议相关的过度弃权）**，不称普遍意义上的 reviewer over-conservative。

---

## 结论先行（TL;DR）

1. 冻结的 C1/C2/DA/错误家族/精确区间经独立实现**逐值复算一致**。
2. **最关键发现是一个构念冲突，而不是一个模型校准结论。** 充分条件（Escalate/T3A）下模型收到的 freshness 工具对 **全部 60 个 active cell 返回 `fresh=false / record_run_tree=null`**，但该 false 是**结构性假象**：canonical record 根本没有 `run_tree` 字段，端点拿 `null == 期望树hash` 恒判 False。Gold 侧经独立 restage 判定 **10/10 fresh=true、签名 authentic、树同一**。
3. 因此 DeepSeek 的 23 个充分条件弃权 cell（9 个 issue）**没有一个能在"模型实际所见材料"下被干净地归为模型校准错误**：
   - 14 个（T3A/Escalate）由**工具的虚假 fresh=false** 诱发——模型看到一个看起来真实的"不新鲜"裁决并据 prompt 的不对称规则谨慎处理（五类标签 B，可免责）；
   - 8 个（T2A）由**静态协议自相矛盾**诱发：模型收到的 prompt 要求 ACCEPT 必须 linked+fresh，而静态块头明写 "linkage not yet verified"，且无工具可验证。所谓"制度性信任授予"只存在于 gold 侧 docstring，**从未写进给模型的 prompt**。名义上落入五类标签 A（未遵循制度性信任前提），但按**实际下发的 prompt** 模型是合规的；
   - 1 个（24443/T2A）是对覆盖率采取了比冻结协议更严格的标准（标签 C，部分可归因于模型选择，现实中可辩护）。
   - 标签 D（缺少必要工具证据）= 0。
4. GPT 的 C1 错误 ACCEPT（SymPy-17318/T2A）经双向核验**确证是真实的证据利用失败**：F2P 失败白纸黑字在可见静态块中，模型却称全部通过。
5. 原报告"DeepSeek 15/50 空 reason"**不可复现**：以冻结 runner 自己的解析器口径为 **10/50**，其中 9 个其实是"prose 前缀 + 内含非空 reason 的有效内嵌 JSON"，**真正截断缺失仅 1**。需更正。
6. Gold 仍 **Provisional**：10/10 `human_adjudication=pending`、单一标注者 n=1，第二标注者仍缺。
7. **Gate 3-C 建议 NO-GO（直接扩样）**；建议先执行一个零/低 API 的 **Gate 3-B.2 证据有效性协议修复**（F 通道），并并行安排第二标注者仲裁，再议扩样。

---

## 任务 1 — 独立复算（不导入 g3b_analyze）

全部与冻结结果一致（`task1_*`）。

- **C1（GPT 错误 ACCEPT，issue 级）**：k=1/3，点估 0.333，**CP95 [0.0084, 0.9057]**，issue-cluster bootstrap [0.0, 1.0]。唯一事件：SymPy-17318 仅在 **T2A-T**；Escalate/T3A 均 0/3。
- **C2（DS 协议相关过度弃权，issue 级）**：k=9/10，点估 0.90，**CP95 [0.555, 0.9975]**，bootstrap [0.70, 1.0]。Oracle ACCEPT issue 7/7、REJECT issue 2/3。分条件：Escalate 6/10、T2A 9/10、T3A 8/10。
- **CP 标准表交叉校验**：0/10=[0,.3085]、5/10=[.1871,.8129]、10/10=[.6915,1]、7/7=[.5904,1] —— 全对。
- **条件 DA（condition gold 口径，正确/10）**：
  - DS：T2D 1.0 / Strict 1.0 / Escalate 0.4 / T2A 0.1 / T3A 0.2
  - GPT：T2D 1.0 / Strict 1.0 / Escalate 0.2 / T2A 0.8 / T3A（见 json；充分条件上 GPT 主要在 T2A/T3A 承诺）
  - 充分条件 gold==oracle，故 condition DA 与 oracle-match 在这些条件相同；受限条件两口径分离（oracle 不可达，全部 NEED 正确）。
- **受限条件正确弃权**：两模型在 T2D、Strict **均 10/10 NEED_EVIDENCE**，零不当承诺——符合制度性预期。
- **配对一致率（两模型同 issue 同条件）**：T2D 1.0、Strict 1.0、Escalate 0.8、**T2A 0.1**、T3A 0.9。T2A 是两模型分歧最大的条件。
- **错误家族（充分条件 cell 计数）**：DS 过度弃权 20（仅 ACCEPT-gold）+ REJECT-gold 弃权 3 = C2 的 23 cell；GPT 过度弃权 14 + 错误 ACCEPT 1（17318/T2A）。

## 任务 2 — fresh=false 来源逐项审计

对 10 个 issue 逐项比较 base / patch hash / run tree / expected tree / 签名 / 执行时间（`task2_freshness_provenance.per_issue`）：

| 维度 | Gold 侧（冻结） | Live T3 工具端点（模型实际所见） |
|---|---|---|
| base_commit | 与冻结 gold 一致（10/10） | 读取同一 record，base 一致 |
| patch_sha256 | record 与被审补丁一致（10/10） | 一致 |
| 签名证明 | record signature 与 attestation **均 authentic（10/10）** | authentic |
| 执行树同一性 | 独立 `git write-tree` restage：restage 树 == attested `expected_run_tree`（10/10 `all_match=true`，见 g3a_freshness_recompute.json） | `rec.run_tree == att.expected_run_tree` → **恒 False** |
| `run_tree` 字段 | gold 不读 `record.run_tree` | **canonical record 结构性无此字段**（`'run_tree' in rec == False`），取到 null |
| fresh 裁决 | **fresh=true（10/10）** | **fresh=false / record_run_tree=null（60/60 active cell）** |
| 执行时间 | started 2026-10-25 18:40 / finished 18:43（历史运行，但树同一） | 未作为陈旧依据 |

端点代码：`evidence/server.py:192`（`tree_match = rec.get('run_tree') == att['expected_run_tree']`）。
Gold 代码：`evidence/g3a_gold.py:79-82`（`fresh = att_ok and linked`，树同一性由独立 restage 建立）。

## 任务 3 — 历史运行 vs 证据失效；fresh=false 是否影响 ACCEPT 充分性

必须区分的三件事，审计结论：

1. **Historical execution（运行发生在过去）**：成立（10-25 的运行）。但时间戳较早**不**等于证据失效；树同一 + 签名 authentic + base/patch 一致。
2. **Patch linkage（证据是否对应本补丁）**：成立（patch/base hash 10/10 一致、签名 authentic）。
3. **Tree freshness（执行树是否匹配冻结预期树）**：**真实答案是"匹配"**（restage 10/10 all_match=true）。工具报的"不匹配"是**缺字段导致的假阴性**，不是真失配。

**判定：fresh=false 不代表证据失效，也不是单纯记录较早；它是 gold 规则与 live 工具在 F 通道上的相互矛盾裁决。** 在冻结协议（V1）下，证据对 ACCEPT 是充分的（fresh 由独立 restage 保证）；但模型在 T3 条件下被工具明确告知 fresh=false。因此"充分证据下过度弃权"这一标签在 T3 条件上**混入了仪器噪声**：模型是在对一个它无法识破的、看起来权威的 false 信号作合理反应。这直接影响 Escalate/T3A 的 condition_gold 解释——审批人对 freshness 的怀疑成立，且比预想更尖锐（不是边界语义争议，而是一端结构性恒假）。

## 任务 4 — Gold Sensitivity Version（不改原 Gold）

冻结 V1 **磁盘未改**。另建两套纯分析假设版本，仅重投影 Escalate/T3A（T2A 与两受限条件各版本相同）；完整推导与计数见
[g3b1_gold_sensitivity_changelog.md](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3b1/audit/g3b1_gold_sensitivity_changelog.md) 与 json `task4_gold_sensitivity`：

- **V2（工具字面 fresh=false 喂入冻结规则）**：非新鲜运行既不支持 ACCEPT 成功也不支持 REJECT 失败；10 个 issue symptom 均 gone，故 **Esc/T3A 各 10/10 全塌成 NEED_EVIDENCE**。此版本下 DS/GPT 的 Esc/T3A 弃权全部 gold-correct，"充分证据下过度弃权"在这两个条件**按构造消失**，C2 成为纯 T2A 现象。
- **V3（linked 的决定性失败即使 stale 仍可 REJECT）**：3 个 REJECT issue 保持 REJECT、7 个 ACCEPT issue 变 NEED。此版本下 DS 在 **17630/T3A**（已获 `contradicted` 并读到失败 f2p 却据 stale-run 规则弃权）会重新成为一个真实错误（漏掉决定性拒绝）；但 7 个 ACCEPT issue 的弃权主体仍由仪器解释。
- 三版本在 Esc/T3A 都不产生新的错误 ACCEPT；唯一 C1 事件在 T2A，各版本对 T2A 不动，故 C1 对 F 通道语义**稳健**。

## 任务 5 — DeepSeek 9 个 Protocol-Relative Over-Abstention 逐案归类

机器标签 + 人工归并见 json `task5_DS9_machine_tags` 与 `task5_DS9_human_adjudication`（每案含 600 字 verbatim reason、answer_form、tool_calls、gap、是否见 fresh=false）。

按审批人五类标签对 **23 个弃权 cell（9 issue）** 计数：**A=8，B=14，C=1，D=0，E=0**。

- **A 未遵循制度性信任前提 = 8（全部为 T2A）**：T2A 按 gold 意图是制度性呈现、不裁决 L/F/C，模型却援引 linkage/freshness/coverage 弃权。**但关键归责裁决**：实际下发的 prompt 里**没有**信任授予——`TERNARY_HEAD`（prompts.py:169-198）对所有条件统一要求 ACCEPT 必须 fresh+linked+complete，静态块头（views.py:229）明写 "ACCEPTANCE tier; … linkage not yet verified"，且 T2A 无工具可验证。故模型是**遵循了它实际收到的规则**；"noncompliance"针对的是一条从未发送给它的规则。根因：静态协议矛盾；可归责性：**按实际 prompt 可免责**。
- **B 实际来源/出处疑虑 = 14（T3A 8 + Escalate 6）**：每个 cell 的 verbatim 理由都含 freshness/run_tree/stale/current tree，工具确实返回了 fresh=false。根因：**F 通道结构性假阴性**；可归责性：**仪器诱发，可免责**。其中 Escalate 有 6 个 ACCEPT-gold cell（13974/15349/20590/21847/24213/24443 的多数）**已成功升级并读到通过的 f2p/p2p**，仍被虚假 fresh=false 否决。
- **C 覆盖充分性疑虑 = 1（24443/T2A）**：静态块已呈现 1/1 F2P + 1/1 P2P（冻结 complete=true），模型认为相对整个模块"太薄"。属比协议更严格的覆盖标准，现实中可辩护，但与冻结充分性相悖；部分可归因于模型选择。
- **D 缺少必要工具证据 = 0**。受限条件下的弃权不计入 C2（其 gold 本就是 NEED）。
- **17630/T3A 特别案**：模型 `consistency=contradicted`、已读失败的 f2p，却引用 prompt 原文"stale run 中的失败不能作为 reject 依据"而弃权。这是"看到决定性证据却未据以拒绝"，但其依据正是被虚假 fresh=false 触发的 prompt 规则；在 V1 下是过度弃权，在 V3 下仍是错误——这是全部样本中**最接近真实模型侧错误**的一个 T3 cell，建议在论文中单列为机制标本。

**对审批人二选一问题的回答**：现阶段证据**不支持**把 C2 解释为单纯 Policy Noncompliance（模型校准问题）。主体（B 类 14 个 + A 类按实际 prompt 可免责的 8 个）是**证据制度自身缺陷（F 通道假阴性 + 静态协议矛盾）诱发的合理/合规谨慎**，即 Evidence Skepticism 与协议构造问题；仅 24443/T2A（C）与可能的 17630/T3A（V3 口径）带模型侧成分。命名维持 **Protocol-Relative Over-Abstention** 是恰当的。

## 任务 6 — GPT SymPy-17318 / T2A 错误 ACCEPT 双向核验

确证。渲染 17318 的 T2A 静态块，可见材料中白纸黑字含：

- `FAIL_TO_PASS passed: 0/1`
- `failing acceptance test ids: test_issue_12420`

GPT 却在 reason 中称 "All scoped acceptance tests pass with no failures … evidence is fresh" 并判 **ACCEPT**。失败确在模型可见材料内 → **看到证据却错误使用（真实的 evidence-verification failure）**，不是没看到。配对反证成立：同一补丁同一模型在 **T3A** 自读/获得失败信号（`consistency=contradicted`）后判 **REJECT**。这是"证据获取方式改变了模型对同一失败信号的利用"的干净配对案例。但 n=3 个 REJECT issue、CP [0.008,0.906]，不可声称稳定群体发生率。

## 任务 7 — T2A / Escalate / T3A 证据权限 × 实际获取 × 判决矩阵

完整矩阵见 json `task7_evidence_access_matrix`，汇总 `task7_access_summary`（obtained=已实际拿到验收结果信号）。

- **T2A（静态，0 工具，结果直接呈现）**：DS 拿到结果后弃权 9 / 承诺 1；GPT 弃权 1 / 承诺 9。→ 证据**人人可见**，分歧纯在"如何对待未验证 linkage 的呈现"，是纯解读差异，与获取无关。
- **Escalate（需非空 reason 升级拉日志）**：
  - DS：成功升级读到验收日志后弃权 5、承诺 4；未升级即弃权 1。
  - GPT：升级读到后弃权 3、承诺 2；未升级弃权 5。
  - 即 DS 多为"**看到结果却被 fresh=false 拦下**"，GPT 更常"**没去拿结果**"。
- **T3A（日志不设墙）**：以"实际获得验收结果信号"口径（读到原始 f2p/p2p **或** 收到 tier-A `check_claim_consistency` 的 consistent/contradicted 裁决，后者在 tier A 内部已按 acceptance outcomes 判定），**两模型均 10/10 获得了结果信号**：
  - DS：获得信号后弃权 8 / 承诺 2（承诺的 2 个是 REJECT issue 17318、19783；读到原始 f2p 的仅 4 个 cell，其余经 consistency 裁决）。
  - GPT：**从不读原始 f2p/p2p（0 次）**，只用 4 个完整性工具 + consistency 裁决；获得信号后弃权 7 / 承诺 3。3 个 REJECT issue 返回 **contradicted**，GPT 全部正确 REJECT（正确穿透虚假 fresh=false）；7 个 ACCEPT issue 返回 consistent 但 freshness=false，GPT 全部弃权。
  - 关键含义：T3A 上**不存在"没看到证据"**；分歧全在"如何使用已看到的信号"。两模型在 7 个 ACCEPT issue 上的弃权都由虚假 fresh=false 驱动；GPT 能在 REJECT issue 上"穿透"fresh=false 去用决定性矛盾信号，但两模型都不愿在仅有成功信号时穿透它去 ACCEPT。这是不对称规则与假阴性叠加的直接后果。

"没看到 vs 看到误用"小结：GPT 的 C1（17318/T2A）= **看到却误用**；DS 的 B 类弃权 = **看到（且工具明示 fresh=false）后合规谨慎**；T3A 两模型 = **均看到结果信号**（无获取缺口，差异在用不用）；GPT Escalate 的 5 例 = **没看到（未升级拿日志）**；T2A 全分歧 = **看到但对协议信任解读不同**。

## 任务 8 — DeepSeek "15/50 空 reason" 复核与机制归因影响

原报告 15 **不可复现**，须更正（`task8_DS_empty_reasons`）。以**冻结 runner 自己的解析器** `phase3_run._parse_answer_json`（剥开头 ```围栏后对整段 `json.loads`）口径：

- runner 口径空 reason = **10/50**（Escalate 7、T3A 3；按判决 ACCEPT 1 / REJECT 3 / NEED 6）。
- 答案形态（健壮解析）：纯 JSON 40、prose 前缀+有效内嵌 JSON 9、JSON 截断 1。
- **10 个 runner 空里有 9 个是"prose 前缀 + 内含非空 reason 的有效内嵌 JSON"**——实质理由保留在 raw answer / 工具 trace；**真正因截断缺失理由仅 1**（13615/Escalate，json_truncated）。
- 其他定义对账：evidence_gap unspecified=13、gap_classification unspecified=7。**15 在任何严格定义下都复现不出**。
- 机制归因影响：结论稳健。几乎每个弃权 cell（含 runner 解析为空者）都能在 raw answer/trace 找到明确的 freshness/linkage/coverage 理由，故任务 5 的机制归因不依赖结构化 reason 字段。**建议报告改为：以冻结解析器口径空 reason 10/50，其中实质缺失仅 1；机制分析应读 raw answer/trace 而非空 reason 字段。**

## 任务 9 — Clopper–Pearson 修正变更记录审核 + 独立验证

冻结披露（`g3b_result_freeze.json.post_collection_analyzer_change_disclosure`）：`g3b_analyze.py` 哈希 913e8319 → 3cdcaf1c，性质为"离线分析数值修复：初版网格尾部搜索给出退化 0.0/1.0 端点，替换为精确 Beta 分位数 CP（已对标准表校验）"，范围仅限分析产物，**不触碰模型调用/判决/DA/bootstrap/方向结论，freeze manifest 刻意未重建**。

独立验证：用**不同实现**（整数二项式 + 二分，非 Beta 路径）复算，C1 1/3=[0.0084,0.9057]、C2 9/10=[0.555,0.9975] 及 0/10、5/10、10/10、7/7 标准表**全部与修正后打印值一致**。结论：修正值可信，仅影响打印区间，记录在案，无需追溯改动任何冻结数据。

## 任务 10 — Provisional Gold 仲裁状态

- `g3a_gold.jsonl`：10/10 `human_adjudication.status = pending`，`n_independent_annotators = 1`（全量，非抽样）。
- `g3a1_condition_gold.jsonl`：10/10 `human_adjudication_status = pending`，oracle 来源标注 "frozen G3-A g3a_gold.jsonl (not recomputed)"。
- **限制明确保留：仍无第二名独立标注者，n=1。所有 Gold 必须表述为 Provisional，不得称 human-adjudicated，不得声称 inter-rater agreement；机械重算 oracle 不是人工共识。**

## 任务 11 — Gate 3-C go/no-go 建议

**建议：对"直接扩充 30–60 个独立 Issue"给出 NO-GO；先做 Gate 3-B.2（零/极低 API 的证据有效性协议修复），再议扩样。**

理由排序：

1. **F 通道构念冲突会污染任何扩样。** fresh=false 是一端结构性恒假（record 缺 run_tree），它系统性地把 T3 充分条件下的弃权往"合理谨慎"方向推。在修复前扩样，C2 在 Escalate/T3A 上的发生率基本测的是仪器缺陷的普及率，无法干净估计模型的校准属性。V2/V3 已显示在合理的替代语义下 C2 的 Esc/T3A 部分可从 13 cell 塌到 0——测量对该构念选择高度敏感。
2. **静态 T2A 协议自相矛盾须先修。** 要么把"制度性信任授予"真正写进 T2A 的 user-facing prompt（明确告知 linkage/freshness 由协议担保、无需验证），要么承认 T2A 本就在要求模型自行验证一个它无法验证的属性并据此重设 T2A gold。二者必须一致，否则 T2A 上 9:1 的分歧没有可解释的构念。
3. **第二标注者仲裁仍缺（n=1）。** 建议在扩样前并行安排独立第二标注 + 一致性度量，至少覆盖现有 10 个 Provisional Gold。
4. **C1 值得保留但需更大 REJECT 样本。** 17318 配对案例干净、F 通道语义对 C1 稳健（事件在 T2A），但 n=3 负例、CI 极宽，扩样时应**提高 REJECT/oracle-failure issue 的占成**，而非均匀加样。

建议的 Gate 3-B.2 范围（另行书面批准后执行，本阶段不做）：(a) 让 canonical record 携带真实 `run_tree`，或让 freshness 端点采用与 gold 一致的 restage 树，使两侧 F 裁决同一；(b) 修订 T2A prompt/gold 使信任前提显式且两端一致；(c) 用修复后的仪器对**同一 10 个 issue 离线重放 gold 投影**验证一致性（可先不调用模型）；(d) 引入第二标注者。修复并复校后，Gate 3-C 再以独立 issue 扩样，重点纳入 REJECT issue。

## 任务 12 — 产物隔离与冻结

- 全部新增产物仅在 `evidence_store_g3b1/`（本报告、audit json、sensitivity changelog）与新代码 `evidence/g3b1_audit.py`。
- 未修改 Gate 3-B 的 prompt / gold / runner / 100 条原始响应 / 历史分析；未改磁盘 V1 gold（V2/V3 仅存在于独立 json）。
- 新增 API 花费 **$0.00**；未新增 Issue；未提交 Git（冻结基线 HEAD=2097ecd，下文复核零 staged）。
- Gold 状态保持 Provisional（n=1）。

---

### 对论文两条发现的更新措辞

- **发现 A（Evidence Verification Failure）**：GPT 在部分条件下会忽略已呈现的失败证据而 ACCEPT。17318/T2A 双向核验确证、T3A 配对反证成立，是干净的"看到却误用"标本；但独立 REJECT 负例仅 3，CI 极宽，且对 F 通道语义稳健，可作为机制案例保留，发生率主张待扩样。
- **发现 B（Protocol-Relative Decision Calibration）**：DeepSeek 在协议认定充分的证据下频繁 NEED_EVIDENCE（9/10 issue，CP [0.555,0.9975]），但审计表明其弃权主体由**证据制度两处缺陷**（F 通道结构性 fresh=false 假阴性、T2A 信任前提未写入 prompt）诱发或免责。在修复协议、使"模型该信任什么"在 prompt/gold/工具三端一致之前，不应把该现象表述为模型本身系统性过度保守。

**审计到此停止，等待下一次书面批准；不自行启动 Gate 3-B.2 或 Gate 3-C。**
