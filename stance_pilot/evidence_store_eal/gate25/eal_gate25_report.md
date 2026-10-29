# GroundedReview v2 — G2.5 零-API 错误审计与构念复核报告

- 授权：用户 2026-10-25 Gate 2 验收通过，批准 G2.5 离线审计，**$0 API**；不新增 Issue、不改 E1/CEE/EAL 冻结文件、不 commit。
- 范围：授权指令第 1–10 项。全部结论来自冻结产物的离线分析；新增只读代码 [eal_gate25_audit.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/eal_gate25_audit.py)，结构化证据写入新目录 [gate25/](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/gate25)（[eal_gate25_audit.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/gate25/eal_gate25_audit.json)），**未触碰任何 Gate-2 及以前的冻结文件**。
- 口径先行澄清（第 8 项）：GPT structured 层两个"9"是**不同集合**——① Gold=NEED 的 9 个错误 = 8 个误 ACCEPT + 1 个误 REJECT；② 9 个 unsupported acceptance = 上述 8 个 + 1 个 REJECT-gold 误 ACCEPT（`a242cd7a`）。Gate 2 混淆矩阵本身正确，本报告给出逐案集合以免混淆。

---

## 1. GPT-4.1-mini Structured 层 8 个 NEED→ACCEPT 逐案审计（指令 1–3）

8 个唯一 bundle 来自 **7 个独立 issue**（sympy-14531 有 2 个镜像 fixture：`c59a8ceb`、`403163cb`）。每案均同时取得：模型完整 `reason`/`missing_evidence`/`evidence_gap`（8 案的 gap 与 missing **全部为空**——模型在错误 ACCEPT 时不报告任何缺口）、Structured 表格操作数、对应 Raw 同源证据，以及从同一批主材料用冻结 oracle 独立恢复的六通道事实。

| # | bundle | issue | oracle 事实（linked/fresh/complete） | 模型 reason 的关键断言 | 归因（主） | DS 同案 |
|---|---|---|---|---|---|---|
| 1 | 62dfb1c6 | sympy-12481 | T/F/T | "evidence is fresh, linked, complete" | **Freshness** | NEED（gap=stale） |
| 2 | ec813709 | sympy-17139 | T/T/F | "coverage … adequate … fresh, linked, complete" | **Coverage** | NEED（coverage_incomplete） |
| 3 | a25d0cf5 | sympy-13091 | T/T/F | "fresh, linked run record … no failures reported" | **Coverage** | NEED（coverage_incomplete） |
| 4 | c637f604 | sympy-13798 | T/F/T | "passes fully post-patch with no regressions" | **Freshness**（+coverage） | NEED（stale） |
| 5 | 2c11095a | sympy-12419 | T/F/T | "linked to the current commit tree" | **Freshness** | NEED（stale） |
| 6 | c59a8ceb | sympy-14531 | **F**/F/T | "identity operands match … fully executed" | **Linkage**（+freshness） | NEED（linkage_mismatch） |
| 7 | e4e8b26c | sympy-18211 | T/F/T | "run is fresh and linked to the exact patch" | **Freshness** | NEED（stale） |
| 8 | 403163cb | sympy-14531 | T/T/F | "fresh and linked … no acceptance failures" | **Coverage** | NEED（coverage_incomplete） |

**归因计数（主因）：忽略 Freshness 4、忽略 Coverage 3、忽略 Linkage 1；无单纯"误读 Symptom"或单纯"误用 Derived Summary"案。** 六类标签允许并存：#4 freshness+coverage，#6 linkage+freshness。

**全部 8/8 案都满足"充分性幻觉"操作定义**：模型在 reason 中**显式断言**了一个 Structured 表格直接矛盾的属性。矛盾值在 Structured 中均可见：
- 树失配（fresh=false）在 **TABLE 2** 逐字并排：如 #1 `def06202…` ≠ `0ffe704f…`、#5 `8dee…` ≠ `4b19…`、#7 `3aa3…` ≠ `37e0…`；#4 `6caa…` ≠ `de83…`。
- Linkage 失败在 **TABLE 1**：#6 record patch `235a157f…` ≠ TARGET `172ae3cc…`。
- Coverage 失败由 **TABLE 3（declared）vs TABLE 4（executed）** 的集合差直接给出：#2 声明 2 f2p+67 p2p，仅 1 f2p 执行（67 p2p 行 `present_in=absent`）；#3 声明 89 p2p 全 absent；#8 声明 84 p2p、p2p 汇总 `0/0`。
- #4 还有执行内失败：f2p `test_latex_basic` FAILED（0/1 f2p、101/102 p2p），模型却写 "all passing"。

Raw 对应证据：同一 signed record JSON 含相同的 run_tree/patch 哈希与 per-test map；8 案中 5 案还缺 `p2p_baseline_map`、4 案缺探针源（见 §5 局限）。

## 2. DeepSeek 同 8 案配对对照（指令 4）——错误为模型特有

**DeepSeek 在同 8 个 Structured cell 上 8/8 正确输出 NEED_EVIDENCE，且其 `evidence_gap` 标签与 oracle 失配逐案精确对应**（4 stale、3 coverage_incomplete、1 linkage_mismatch）。即：同样的表格、同样的并排操作数，一个模型逐案读出失配并弃权，另一个逐案断言相反属性并接受。**"结构化→幻觉充分性"是 GPT-4.1-mini 特有的失败模式，不是该条件的普遍效应。**

进一步限定机制（重要）：GPT 在 **Raw 层对同 8 案已误接受 6/8**（仅 #3、#8 在 Raw 弃权、Structured 转为误接受）。因此 Structured **没有凭空制造** provenance 盲——GPT 在任何层都未独立核验来源/新鲜度/覆盖；结构化把弥散的不确定转成了自信断言（+2 个新误接受），而 Adjudicated 纠正其中 7/8（#2 在三层全部 ACCEPT，见 §4）。假设应精炼为：

> *GPT-4.1-mini does not adjudicate provenance or coverage at any abstraction level; structured presentation converts that unperformed check into explicit claims of freshness/linkage/completeness.*

## 3. Structured 字段名/标题/说明可信度暗示审计（指令 5，只审不改）

逐字检查 [eal_render.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/eal_render.py#L277-L412) 与 [eal_protocol.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/eal_protocol.py#L162-L174)：

- **未发现** `verified_results`/`trusted_tests`/`validated_summary` 之类暗示"内容已验证"的字段名。实际字段为中性操作数：`field / TARGET under review / value inside SIGNED RUN RECORD`、`present_in`、`f2p_post_status`、`p2p_base_status`、`exit_code`。
- 头部**主动否认**预裁决："every table shows **operands, not verdicts**"、"**No integrity or applicability verdict is supplied**: there is no linked/fresh/complete indicator"；Gate-2 披露段（[eal_gate2_freeze.py L70-100](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/eal_gate2_freeze.py#L70-L100)）在 head 与 TABLE 5 两处标注派生归类，要求模型区分自证与继承。
- 残留高权威词：`SIGNED CI RUN RECORD`、`ATTESTATION`、`expected canonical tree declared in the attestation`、`PARSER RESULT`。但签名/绑定可信度来自三层**完全相同**的 `CHANNEL INTEGRITY` 恒定前提（raw 同样出现），**无法解释 structured 特有**的错误；且 DS 在同一措辞下 8/8 正确。
- 反证：TABLE 2/4 的并排设计对 DS 足以让失配显形。**审计结论：没有识别出会系统性抬高 Structured 可信度的提示设计因素；错误根因在模型的证据评估行为，而非字段命名。** 唯一可在后续协议中试验的是"失配/缺失显著性"（见 §7 建议），但那属于新协议变量，不得回改 Gate 2。

## 4. EAL Adjudicated vs CEE v1.1 逐 Cell 对照（指令 6）

逐项核对两模型 22 cell：system prompt 相同（`cee.SYSTEM_MESSAGE is eal.SYSTEM_MESSAGE`）、**22/22 user bundle 字节逐字节相同**（gate2 adjudicated payload == CEE bundle 文件，且逐行 bundle_sha 相等）、served id 相同、temperature 0、max_tokens 4096、json_object、tools=0、无 plain-text 回退。

- **DeepSeek：0 翻转，22/22 逐 cell 复现**（类别 7/6 类 4/6、不足 9/9 全一致）。
- **GPT：2 个翻转、相互抵消，故总数仍 18/22 但不是逐 cell 复现**：

| bundle | 类别 | gold | CEE 判决 | EAL adj 判决 | 正确性变化 |
|---|---|---|---|---|---|
| ec813709 (sympy-17139) | insufficient | NEED | NEED_EVIDENCE（对） | ACCEPT（错） | 对→错（不足 9/9→8/9） |
| 59e46a77 (sympy-13091) | decisive_negative | REJECT | NEED_EVIDENCE（错） | REJECT（对） | 错→对（负类 2/6→3/6） |

wire 全同，唯一剩余解释是 **temperature=0 下 API 非确定性（后端权重不钉、无种子）**。佐证：`ec813709` 在 EAL 三层 GPT 全部判 ACCEPT，而 CEE 判 NEED——典型边界样本随机摆动；`59e46a77` 同理在弃权/否决间摆动。**测量含义：GPT 的单次调用噪声量级约 ±2 cell/22（≈±9 pp），与本 Pilot 多个层间差值同量级。** 因此：① Gate 2 报告不得称"逐 cell 复现"，应称"总体率复现、GPT 存在 2 个零和翻转"；② 任何未来 GPT 的层间对比必须包含重复调用以分离该噪声（§7）。

## 5. 6 个 Decisive-negative 独立审计（指令 7）

6 fixture 来自 5 个独立 issue（sympy-12489 有 2 镜像：`af83be49`、`f51defe8`）。over-abstention 有**两种不同机制**：

**机制 A——以 coverage incomplete 为由否决一个已 linked&fresh 的 acceptance failure（政策错误）。** oracle 规则下决定性失败只需 `linked & fresh & acceptance_failure`，**不需要 complete**。
- `f51defe8`：linked T/fresh T/acc_fail T/complete F → gold REJECT；GPT adj 弃权且 gap=`coverage_incomplete`；59e46a77 同类（GPT raw coverage_incomplete）；`faae0894` 同类（GPT raw+adj 弃权）。模型把"没跑全声明集"当成阻止下 REJECT 的理由，混淆了正例（需覆盖充分）与负例（一个适用的决定性失败即足）的非对称标准。
- DeepSeek 在这三案全部正确 REJECT，未犯机制 A。

**机制 B——拒绝 symptom-alone forcing（oracle 对 2 个 wrong-patch/stale-persist 样本允许 symptom 单独决定 REJECT）。**
- `af83be49`：linked T/fresh F/symptom_persists T → gold REJECT；DS structured+adjudicated 弃权（gap=stale），GPT 三层正确。
- `f0c49f82`：linked F/fresh F/symptom_persists T → gold REJECT；DS structured+adjudicated 弃权（gap=linkage_mismatch），GPT raw 反而 false-accept、structured 正确 REJECT、adj 又弃权（stale）。
- 机制 B 主要是 **DS 的过度严格**：它要求 freshness/linkage 齐备才肯接受 symptom 持续的决定性，未采用"症状持续即补丁未解决该问题"的单列规则。

`a242cd7a`（linked/fresh/complete/acc_fail 全 T 的硬负例）：DS 三层、GPT raw/structured 之外的层均正确；**GPT structured 误 ACCEPT**（reason 称 "113/113 pass"，与记录中的失败矛盾），adjudicated 纠正为 REJECT——这是 §1 之外第 9 个 unsupported acceptance。

## 6. 口径与置信区间独立复核（指令 8）

不使用分析器，从 132 行 jsonl + 冻结 gold 独立重算：两模型三层 DA（DS .773/.864/.909；GPT .409/.545/.818）、6 个混淆矩阵、类别计数、Always-NEED=9/22 全部与 Gate 2 报告一致；用独立实现的 issue-cluster bootstrap（seed=7/n=10000）抽验 GPT adjudicated 得 [0.636, 0.957]，与报告一致。错误家族分母口径已在报告 JSON 中显式记录。**唯一需修正的表述**是 GPT structured"9 个 NEED 全错 + 9 次 unsupported acceptance"易被读成同一集合（实际两个不同的 9，见文首澄清）；数值无误。

## 7. Gate 3 决策建议（指令 9）与依据

**建议：不直接用现协议付费扩样；先用零-API/少量重复调用建立 v2.1 协议候选与可靠性基线，再扩独立 issue。** 依据：

1. **异常机制已在 7 个独立 issue 上呈现一致模式**（8/8 幻觉断言、DS 8/8 正确），构念有效，值得追；但 ② GPT temp=0 单次噪声 ±≈9pp 已被 CEE 对照实测，而 Gate 2 最关键的 GPT 层间差值（+13.6/+27.3 pp）与噪声同量级——**不先测量重测信度，扩样后的层间差无法与调用噪声分离**。
2. 错误**不是**字段暗示所致（§3），因此"改字段名"无的放矢；真正可检验的协议变量是 **provenance/coverage 失配的显著性**与**非对称政策的显式化**，二者都必须在**独立 v2.1** 中操作（保留 Gate 2 全部原始结果不覆盖）。
3. 建议的 v2.1 候选（仅设计，待批准后实现；不泄漏 gold）：(a) 在 TABLE 2/4 顶部增加**纯计数的失配/缺失摘要**（声明数、执行数、缺失数——只聚合操作数，不给 linked/fresh/complete 布尔，避免滑向 adjudicated）；(b) 对称地在三层头部重述负例"一个适用的决定性失败即足，覆盖不全不阻止 REJECT"；(c) 对现有 22 fixture 做 **k=2 重复调用**以直接估计 GPT/DS 的重测摆动，再决定新 issue 样本量。
4. Gate 3（付费）建议规模待 v2.1 离线冻结后另行报批；G4 再议第三模型。

## 8. 交付与停止点

- 结构化证据：[eal_gate25_audit.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/gate25/eal_gate25_audit.json)（8 案逐字 reason+oracle 事实+分类、CEE 翻转表含逐项 wire 核对、6 负例全判决、独立重算）；脚本 [eal_gate25_audit.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/eal_gate25_audit.py) 可复跑，$0。
- **G2.5 到此停止**：零模型调用、零新 Issue、E1/CEE/EAL 冻结 Prompt/Gold/Payload/结果/指标均未修改、未 commit。等待 Gate 3（或 v2.1 离线修订）的下一次书面批准。
