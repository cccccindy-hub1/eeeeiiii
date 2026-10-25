# GroundedReview v2 — Evidence Abstraction Ladder (EAL)
## 离线研究方案 · 构念效度审计计划 · 实施预算（draft1，待批准）

- 协议版本：`eal-v0-draft1`
- 状态：**离线设计 + 离线原型 + 离线自检已完成；零付费调用、未扩样、未修改任何 E1/CEE 冻结产物、未 git commit。**
- 冻结锚点：CEE v1.1（DS DA 0.909 / GPT 0.818，22 bundle = 7 sufficient_positive / 6 decisive_negative / 9 insufficient）；E1（pooled oracle DA DS 0.591 / GPT 0.673）。
- 本轮代码（全部新增、`eal_` 前缀、不导入时不写盘）：
  - [eal_protocol.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/eal_protocol.py)（三层 head / schema / 通道前提 / `gold_from_facts` 允许欠定）
  - [eal_render.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/eal_render.py)（从冻结 store 渲染三层）
  - [eal_audit.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/eal_audit.py)（逐层泄漏 + 机械复算 + grounding-step 审计）
  - [eal_selftest.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/eal_selftest.py)（592 项不变量自检，全绿）
- 本轮产物（新目录，隔离于冻结 store）：`stance_pilot/evidence_store_eal/`
  - `layers/<bundle_id>__<layer>.txt`（22×3=66 份渲染）、`eal_materials_manifest.json`、
    `eal_construct_audit.json`、`eal_selftest_report.json`、本文件、`eal_design_freeze.json`。

---

## 0. 研究问题与构念定位

论文核心问题：**When does an agent have enough evidence to decide?**
GroundedReview 把它拆为三个可测层（本分层是**后续研究设计**，不是对现有实验的因果分解）：

| 层 | 构念 | 现有证据 |
|---|---|---|
| L1 Evidence Acquisition | 是否主动取证/调工具/请求补证 | E1 涉及（但 E1 同时跨三层，非纯 L1） |
| L2 Evidence Grounding | 从**原始**日志/执行记录/来源中判断哪些事实可信、相关、充分 | **空白，v2 主攻** |
| L3 Decision Policy | 在已裁决事实上执行非对称 ACCEPT/REJECT/NEED 规则 | CEE v1.1 = L3 控制组 |

Task 20 的关键结论：CEE 22/22 Gold 可从模型可见的布尔字段 + Prompt 规则**机械复算**，
因此 CEE 测的是 **Policy Execution over Pre-Adjudicated Evidence**，不是从原始观测做 grounding。
EAL 的目的是在**同一 Issue / Patch / 真实执行事实**上，只改变证据的**抽象程度**，
从而把 L2 从 L3 中分离出来；它不是通过"删信息"制造差异。

---

## 1. 三个证据抽象条件（授权任务①）

三层共用同一冻结 ternary 语义段（`SEMANTICS_BASE`）、同一五字段输出 schema、同一 system/goal；
唯一变化是证据体的抽象层级与随之呈现的判断负担。

### 1.1 RAW（L2 目标条件：原始证据推理与来源判断）
逐字（仅主机路径脱敏）提供：
- ISSUE 原文、PATCH diff、AUTHOR 声明；
- **TARGET 块**：被审 target 的 `base_commit` / `patch_sha256`（供模型自行做 linkage）；
- 维护者**仓库 attestation 原文 JSON**（`expected_run_tree`、`declared_fail_to_pass`、
  `declared_p2p_scoped`、`built_at`；剔除内部真实性布尔 `_attestation_authentic`）；
- **签名 CI run record 原文 JSON**（经冻结 `neutralize_fixture(..., declared=None)`：
  去 artifact 化、去内部 scenario/tier-D 预填计数，保留实际执行 scope；模型须自行比对
  target↔record 的 base/patch、record.run_tree↔attestation.expected_run_tree、
  declared set↔已执行 per-test 集合）；
- **4 类逐字日志**：f2p（post 验收）、p2p（post 回归）、p2p_baseline（**base 同范围回归**，
  用于判断 post 失败是否为 pre-existing / 不适用）、symptom（issue 症状探针 **pre+post**，
  真实 pytest/probe 输出，含命令、exit code、堆栈、`short test summary`）；每条日志附
  **原始（脱敏前）字节 sha256**，与 record 的 `log_digests` 互链，可审计；
- 探针**源文件**（仅当归档留存；未留存时如实标注，不伪造）。

模型在 RAW 必须自行完成 5 个 grounding 判断：
(1) linkage：record 实际 base/patch 是否 == TARGET；
(2) freshness：record.run_tree 是否 == attestation.expected_run_tree（在通道前提之内，见 §2）；
(3) coverage：declared 集合是否都被执行；
(4) applicability：post FAILED 的检查在 base 是否非 FAILED（用 p2p_baseline / f2p 语义判定适用失败）；
(5) symptom：从探针 pre/post exit code 与 result lines 读症状是否在 patch 后仍复现。

### 1.2 STRUCTURED（L2 校准条件：解析但不裁决）
对**同一批原始记录**做确定性解析并组织成 7 张表，但**绝不输出**
`linked / fresh / complete / symptom_persists` 等判决布尔，也无任何 match/verdict 列：
- T1 identity operands：target 值 vs record 值（两列并排，**不判等**）；
- T2 run-tree operands：record tree vs attestation expected tree（**不判等**）；
- T3 declared sets（attestation 声明集合）；
- T4 per-check execution join：`test_id | declared_as | present_in | f2p_post_status |
  p2p_post_status | p2p_base_status`（成员关系 + 各阶段状态，**不给"是否适用失败"结论**）；
- T5 record summary（runner 自记聚合计数，原样）；
- T6 parsed pytest 日志头（command / exit_code / pytest_summary）；
- T7 parsed probe：pre/post 各自 command / exit_code / result_lines
  （**不给 present-before / persists-after 二值**）。

RAW→STRUCTURED 是"表示方式"的抽象（原始文本 → 解析字段），保留全部**操作数**，
仅移除读者本应自行完成的比对/归类动作；这是与"单纯删标签"的本质区别（见 §4 充分性）。

### 1.3 ADJUDICATED（L3 控制条件：政策执行）
**逐字节复用冻结 CEE v1.1 bundle**（`evidence_store_cee/bundles/<bid>.txt`），
含 INTEGRITY VERDICTS 四布尔与 probe 两布尔。原型已对 22/22 验证
`adjudicated_bytes == frozen_cee_bytes`，head = `cee.CEE_HEAD`。
该臂回答："当可信事实已被裁决好，模型能否正确执行既定非对称政策？"

---

## 2. 通道前提 vs 层变量：HMAC 真实性的处理（关键设计决断）

签名/HMAC 的**真实性**无法由模型在任一层复算（无密钥）。我们不假装 RAW 读者能"验签"，
因此把它定义为**所有三层恒定的通道前提**（`_INTEGRITY_PREMISE`，明示：记录已验签、
日志哈希已核对），它不随抽象层级变化，因而**不是**层间操纵变量。

随层级变化的只有 5 个 grounding 判断（linkage / freshness / coverage / applicability /
symptom）。必须严格区分两件事（用户明确告诫）：
- **记录本身的签名真实性**（通道前提，恒定）；
- **该签名记录是否关联到"当前被审 target patch"**（linkage，RAW/STRUCTURED 须自行判断；
  签名真实 ≠ 关联到目标 patch）。

裁决→可比对操作数映射（`VERDICT_OPERANDS`）：

| 裁决 | RAW/STRUCTURED 中必须自行比对的操作数 |
|---|---|
| linked | TARGET.base/patch  vs  record.base_commit/patch_sha256 |
| fresh | record.run_tree  vs  attestation.expected_run_tree |
| complete | attestation.declared{fail_to_pass,p2p_scoped}  vs  已执行 per-test key 集合 |
| applicable failure | post FAILED 且 base 非 FAILED（`pass_to_pass_baseline` map；缺 map 时回退 summary） |
| symptom_persists | 探针 post exit_code 非 0（pre 非 0 确认症状本应触发）——**exit code 不是布尔结论** |

---

## 3. 同源配对：同一 Issue/Patch/执行事实（授权任务②③④⑤）

- 一个 item 的三层共享同一 `instance_id / base_commit / target patch_sha256 /
  served run record / attestation`；不改变任务难度、不改写结果。
- RAW/STRUCTURED 都提供 pre/post 探针、失败堆栈、执行命令、patch/base 关联**操作数**；
  ADJUDICATED 提供对应预裁决事实。
- 自检 S2 对 22 item 验证 payload 归属同一 bundle、RAW/STRUCTURED 均含 target base/patch；
  S3 验证 ADJUDICATED 与冻结 bundle 逐字节相等。

### 冻结归档的真实粒度限制（如实披露，不补齐、不伪造）
- 22/22 有 attestation、有 f2p per-test map、有 symptom 日志；
- p2p per-test map 16/22、p2p_baseline per-test map 10/22（其余仅 runner 聚合计数）；
- 探针源文件 9/22（probe 输出 22/22 都在）。
缺 map 的 item：RAW 仍渲染该日志段并附固定披露句 `(log not retained in the archive)`；
STRUCTURED 仍渲染 T4/T5，缺失单元格为 `-`/`absent`。这是归档的历史限制，
**正式 v2 新数据必须在构建时保证四类日志与三类 per-test map 全留存**（纳入标准 §7）。

---

## 4. 逐层 Gold 充分性：不强制三层 Gold 一致（授权任务⑥）

- `gold_from_facts(...)` 允许操作数为 `None`：枚举未知通道所有组合，
  若所有组合推出**唯一**标签则该层 gold 仍 determined；若推出多个标签，
  标记 `gold_underdetermined` 并列出欠定通道，**绝不强制三层共用一个 gold**。
- 冻结原型结果：因 22/22 attestation 全留存、f2p/symptom 全在，
  **RAW/STRUCTURED 22/22 都能从可见材料确定 gold，且与冻结 oracle 一致**；
  ADJUDICATED 同为 22/22（重现 Task 20 结论）。欠定通道列表为空。
- 若未来某 issue 的 RAW 归档缺关键操作数（如无 baseline 日志无法判 applicability），
  该 item 在该层标 `gold_underdetermined`，分析时按"该层不可判"单列，
  不回填、不与他层强行配对计分。

---

## 5. 逐层独立 Label Leakage Audit + 充分性检查（授权任务⑦）

[eal_audit.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/eal_audit.py) 纯文本解析
（不信任渲染器内存中的对象），每层 4 问：

- **Q1 字面泄漏**：直接标签 token（ACCEPT/REJECT/NEED_EVIDENCE 作为答案、gold/class/scenario
  名、`decisive_failure`/`sufficient_success` 等）与复合场景词表；按"issue/patch 自然语言区"
  vs"注入证据区"分别计数。通用词（bad/valid/stale 等）只作信息项——冻结字段
  `p2p_preexisting_bad_ids` 合法含 "bad"，不计泄漏。
- **Q2 裁决缺失（仅 RAW/STRUCTURED）**：扫 linked/fresh/complete 的 yes-no、probe
  present/persists 二值、integrity verdict 标题、match 列；ADJUDICATED 豁免（本就应含）。
- **Q3 机械复算 gold**：三套**互相独立**的文本解析器
  （`parse_raw_layer_v2` 解析 JSON 块+日志 exit code；`parse_structured_layer` 解析 7 张表；
  `parse_adjudicated_layer` 复用冻结 `cee_leakage_audit_v11.parse_rendered_fields`），
  再套冻结 `oracle_gold`，与冻结 gold 比对。
- **Q4 grounding-step 计数**：量化每层要求读者完成的判断步数
  （RAW：读 JSON 块、自行 hash 比对、读多份日志；STRUCTURED：比对次数 / membership 次数 /
  per-check 归类次数；ADJUDICATED：仅 6 个已打印布尔 + 1 次规则应用），作为"接地负担"的
  操作化指标。

**原型结果（`eal_construct_audit.json`，脚本末尾硬断言）**：
`mechanical_gold 22/22 × 3 层`；RAW/STRUCTURED `verdict_free 22/22`；三层 `label_clean 22/22`。

---

## 6. 与 CEE v1.1 的连接：可对照、不可合池（授权任务⑧）

- ADJUDICATED 臂 == CEE v1.1 冻结 bundle（字节一致），因此 v2 与 CEE 在**同一协议片段**上
  天然可对照；但 **RAW/STRUCTURED 是不同协议**（不同 head、不同接地负担、不同输入长度），
  其分数**不得与 CEE/E1 分数直接合池求平均**。
- 允许的连接方式：
  1. **层内**报告每层各自 DA / 机制指标；
  2. **层间配对**只在 EAL 内部做 RAW↔STRUCTURED↔ADJUDICATED 的同一 issue 配对转移；
  3. 与 CEE 的关系仅作**跨研究并置**（juxtaposition），明确是不同协议、不同样本，
     复用 E1↔CEE 已确立的"只并列、不合分、不过度因果"纪律；
  4. ADJUDICATED 可作为 EAL 内部的"上限/政策执行基线"，用以量化
     **abstraction-sensitivity**（接地失败相对政策执行失败的增量，见 §8）。

---

## 7. 样本选择：独立 Issue 优先，镜像不充数（授权任务⑨）

- **现有原型**：10 个真实独立 issue、22 个 fixture（同一 issue 的多个镜像 fixture 共享
  issue/probe，非独立）。仅用于管线与构念验证，**不作为 v2 功效计算的样本量**。
- **正式 v2 纳入标准（新数据）**：
  1. 以**独立 issue 为抽样单位**；优先新增此前未用过的 issue（仍可在 SymPy 起步，
     但应规划跨仓库外推）；
  2. 每 issue 在构建时**四类日志 + 三类 per-test map + 探针源 + attestation 全留存**，
     从源头消除本轮归档粒度缺口；
  3. 每 issue 可构造多个证据条件 fixture（linked/unlinked、fresh/stale、complete/incomplete、
     symptom gone/persists），但这些是**同一 issue 簇内的重复测量**，
     **统计上按 issue 聚类，绝不把镜像当独立 n**；
  4. 保持三类 gold 平衡（sufficient_positive / decisive_negative / insufficient），
     尤其保证 decisive-negative 中既有"具体适用失败"也有"症状通道独立支撑"；
  5. 新增 issue 冻结前过与本轮相同的 Q1–Q4 审计与自检。
- 目标规模（分阶段，见 §10）：试点 +20 独立 issue（每 issue 2 fixture = 40 cell/层），
  全量 +40 独立 issue（80 cell/层）。最终功效与 CI 以 issue 簇数（20/40）而非 cell 数报告。

---

## 8. 配对统计方案与预注册机制指标（授权任务⑩）

沿用冻结统计惯例：**issue-cluster bootstrap，seed=7，n_boot=10000**；
McNemar 精确双侧仅作描述性（簇内相关、n 小）。

- **主分析（EAL 内部、同一 issue 配对）**：对每模型分别估计
  `P(correct_RAW)`、`P(correct_STRUCTURED)`、`P(correct_ADJUDICATED)` 的簇 bootstrap 均值与 95% CI；
  配对差 `Δ_raw−adj`、`Δ_str−adj`、`Δ_raw−str`（按 issue 聚合后 bootstrap，单元=issue）。
- **层间转移矩阵**：3×3（或在欠定时含"undeterminable"）记录同一 issue 跨层判决迁移，
  定位错误发生在哪一次抽象跃迁。
- **预注册机制指标（每层每模型）**：
  1. Decision Appropriateness（parseable 为分母，沿用 CEE 口径）；
  2. Over-abstention rate（gold∈{ACCEPT,REJECT} 却判 NEED）；
  3. False-commit-accept / unsupported-reject 率；
  4. **Grounding-to-Policy Gap（本研究主效应）** =
     `DA_adjudicated − DA_raw`（配对），即"事实已裁决能做对、但要自己接地时出错"的增量；
     STRUCTURED 作中介定位（表示抽象 vs 裁决的各自贡献）；
  5. **Channel-specific grounding accuracy**：只在能从留存 reason/操作数读出判断时，
     对 5 个 grounding 通道分别评（见 §9 留存修复后才可用，预注册为次要指标）；
  6. INVALID/AMBIGUOUS/API_ERROR 率单列。
- **分析纪律**：只报告行为层面的表述
  （如 "abstained on cases where the rendered evidence contained a decisive applicable
  failure alongside incomplete coverage"），在没有 reason 原文时**不写**确定的心理机制
  （"模型因为 coverage 不完整而拒绝"）。
- **欠定处理**：任一层 `gold_underdetermined` 的 issue 从该层主分析剔除并单列数量/原因，
  预先规定，不事后补判。

---

## 9. 完整输出与工具轨迹留存方案（授权任务⑪；修复 CEE 缺陷）

CEE runner 曾因 SDK `ChatCompletion.content` 在 HTTP 200 后、落盘前崩溃，导致 2 次 DS
调用计费但 reason 未落盘（Task 20 只能据最终标签推断错误机制）。v2 runner 规范
（**本轮只写规范、不实现、不调用**）：

1. **先落盘后解析**：收到响应的第一动作是把**完整 raw response 文本**（或原始 JSON 字节）
   append 到只增日志，并立即 fsync；解析在落盘成功之后进行。
2. **逐条记录**：请求时间、model id 字符串（+ served 版本字段，标注 DeepSeek 类 id≠权重）、
   layer、bundle_id、payload_sha256、prompt_fingerprint、temperature/max_tokens/response_format、
   HTTP status、usage（prompt/completion/total tokens）、`raw_content_sha256`。
3. **五字段结构化解析结果**与**原文并列留存**：`decision / confidence / reason /
   missing_evidence / evidence_gap` 中 `reason`、`missing_evidence`、`evidence_gap`
   的**原文逐字**必须保存（CEE 仅存了 decision，正是本轮要修的点）。
4. **工具轨迹**（未来若 EAL 加可选取证臂）：每条 tool 请求/响应、参数、返回摘要、
   HTTP 状态、时间戳，按序存档；无工具臂记 `tools_sent=0`。
5. **失败也留痕**：解析异常/客户端异常时，已收到的字节与异常栈都落盘并标
   `CLIENT_ERROR`（区分"未计费"与"计费未落盘"），resume 保证每 (issue,layer) 恰一次有效判决。
6. **密钥卫生**：API key 只从环境读取，**永不进入 prompt / 产物 / 日志 / git**；
   落盘前对任何回显做 key 模式脱敏；产物目录加入忽略规则防止误提交。
7. 留存 schema 在正式跑之前先冻结（含字段名与必填校验），与 BudgetGuard 记录联动。

---

## 10. 成本、规模与分阶段审批（授权任务⑫）

### 10.1 实测字节锚点（本轮 22 个冻结 fixture 渲染）
以 ADJUDICATED 实测 ~2246 输入 token / 中位 8119 字节 校准 bytes/token ≈ **3.62**：

| 层 | 字节 min/中位/max | 估算输入 token/单元（中位） | 22 cell 单模型 token |
|---|---|---|---|
| RAW | 24,715 / 52,758 / 245,404 | ~14,600（max ~68,000） | ~423,000 |
| STRUCTURED | 12,676 / 23,432 / 36,743 | ~6,500 | ~146,000 |
| ADJUDICATED | 6,635 / 8,119 / 14,488 | ~2,250 | ~55,000 |

> RAW 长尾极重（最大 ~245KB，主要是大堆栈/全量 pytest 输出）。正式 v2 应对 RAW 设
> **预算护栏**：保留全部与判决相关的日志（失败堆栈、探针、命令、per-test 行），
> 对与判决无关的通过用例 traceback 可做**确定性、可审计的截断**（保留头尾+哈希），
> 截断规则须在冻结前审计、且不得删掉任何 grounding 操作数。

### 10.2 API 成本（粗估，正式跑前用小样本实测单价复算）
沿用 CEE 实测单价量级（DS ≈ $0.44/百万 in、GPT-4.1-mini ≈ $0.50/百万 in；输出每单元
固定 ~150 token，占比很小）。两模型合计、三层、仅输入的量级估算：

- **P0 离线原型（本轮）**：22×3 渲染 + 审计 + 自检。**$0（已完成，零付费）。**
- **P1 现有 22 fixture × 3 层 × 2 模型（若未来批准）**：约
  (423k+146k+55k)=624k 输入 token/模型 → 两模型 **≈ $0.6–0.7**（不含重跑/长尾）。
  建议硬顶 **$3**（含 RAW 长尾与 10% 故障重试）。
- **P2 +20 独立 issue × 2 fixture = 40 cell/层 × 2 模型**：
  RAW ~1.23M / STR ~0.55M / ADJ ~0.18M（两模型合计），**约 $1.5–2**；
  建议硬顶 **$8**。
- **P3 +40 独立 issue（全量，80 cell/层 × 2 模型）**：约为 P2 两倍，**约 $3–4**；
  建议硬顶 **$16**。
- 全程 BudgetGuard **逐请求 pre-call 拦截**（复用 CEE v1.1 机制），默认 dry-run，
  必须显式 `--allow-paid-run` 且设置本阶段硬顶才放行；跨硬顶调用在发出前被拒。

### 10.3 数据构建成本（离线/算力/人工）
- 每新 issue：checkout + 应用 patch + 跑 f2p/p2p/baseline + 编写并运行 issue 症状探针
  （pre/post 各一次），主要是 CI 算力（SymPy 全/范围测试，分钟级～十几分钟/issue）；
- 人工：issue 选取与 gold 裁决、attestation 撰写、探针与 issue 症状对齐核查、
  冻结前 Q1–Q4 审计。粗估每独立 issue 15–30 分钟人工（探针对齐是主要工时）；
- 探针正确性需双人/规则复核（探针必须真正对应 issue 所述症状），
  避免把 `symptom_persists=true` 当作"原始日志"——它是对**探针退出码语义**的解释，
  RAW 给的是退出码和输出，不是那个布尔。

### 10.4 分阶段审批门（每门须书面批准才进入下一阶段）
- **Gate 0（本轮，已完成并停在此处）**：离线设计 + 原型 + 审计 + 自检 + 预算。**等待批准。**
- **Gate 1**：批准后才可实现 v2 runner（仍默认 dry-run，零付费）+ 留存 schema，
  用 mock 跑通全链路与 BudgetGuard 越顶拦截；**不扩真实数据**。
- **Gate 2**：批准后才可在**现有 22 fixture** 做付费 P1（硬顶 $3），验证三层 live 可解析、
  reason 全留存、abstraction-sensitivity 可观测；
- **Gate 3**：批准后才可构建 +20 独立 issue（含全留存纳入标准）并跑 P2（硬顶 $8）；
- **Gate 4**：依据 P2 的 CI 宽度/簇数做功效复核，再决定是否批 P3 全量（硬顶 $16）。

---

## 11. 本轮自检结论（592 项全绿，零网络）

[eal_selftest_report.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/eal_selftest_report.json)：
- S1 两次渲染字节/行/manifest 完全确定；
- S2 三层同源（payload 归属同 bundle；RAW/STRUCTURED 含 target base/patch）；
- S3 ADJUDICATED 22/22 与冻结 CEE bundle **逐字节相等**、head=`CEE_HEAD`；
- S4 RAW/STRUCTURED 信息等价（per-check join、run-tree、pre/post 退出码、日志 sha 互链；
  归档缺口如实披露），STRUCTURED 不是单纯删信息；
- S5 RAW/STRUCTURED 22/22 **零预裁决布尔**；
- S6 六操作数均可恢复、三层 gold 22/22 determined 且 == oracle、症状极性与日志一致；
- S7 主机路径/用户名脱敏干净；7 ACCEPT / 6 REJECT / 9 NEED、10 独立 issue 分布不变。

## 12. 边界与下一步（等待批准）
本轮**只做设计、离线原型与自检**：未运行任何付费模型、未扩大真实数据集、
未修改 E1/CEE 的 Gold/Prompt/Bundle/结果/指标、未 git commit。
请审批：(a) 本方案与构念效度审计计划；(b) 是否进入 Gate 1（仅 runner 离线实现，仍零付费）。
