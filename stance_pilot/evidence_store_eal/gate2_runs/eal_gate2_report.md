# GroundedReview v2 — EAL Gate 2 报告：Evidence Abstraction Pilot（132-cell 真实模型实验）

- 协议条件（冻结于任何付费调用之前）：`eal-v0-draft1+gate2-derived-summary-disclosure`
- 规模：22 fixture（7 ACCEPT / 6 REJECT / 9 NEED_EVIDENCE，镜像自 **10 个独立 issue**）× 3 层（raw / structured / adjudicated）× 2 模型（DeepSeek-flash、GPT-4.1-mini）= **132 个真实付费 Cell**
- 执行：每 cell 独立单轮、不调工具、json_object、temperature 0、max_tokens 4096；200 上的 INVALID/AMBIGUOUS 为终态，不修复不重试；仅传输错误做一次 2s 技术重试
- 总费用 **$0.4769 / 硬顶 $3.00**（DS $0.2172，GPT $0.2597）；预算状态 `within_cap`；**0 INVALID / 0 AMBIGUOUS / 0 API_ERROR**
- 冻结产物：[gate2/](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/gate2)（66 payload、[materials manifest](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/gate2/eal_gate2_materials_manifest.json)、[freeze manifest](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/gate2/eal_gate2_freeze_manifest.json)、preflight 11/11）；结果 [gate2_runs/](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/gate2_runs)；指标 [eal_gate2_metrics.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/gate2_runs/eal_gate2_metrics.json)
- **定位：小样本机制 Pilot（10 独立 issue）。下列结果不主张跨项目或跨模型家族的普遍性。**

---

## 0. 执行前 6 项零-API 条件的处置（全部满足后才产生第一笔付费调用）

1. **冻结与哈希核验**：66 个 Gate-2 payload、逐层 gold、prompt（head/goal/schema/fingerprint）、runner、analyzer、预算配置、评分规则全部在付费前写入 freeze manifest（sha256）。runner 每次发送前对 payload 同时比对 materials manifest 与 freeze manifest，漂移即退出；发送后再逐行回比 freeze，132/132 一致。
2. **Derived Summary 显式标注**：raw 与 structured 的 head 与证据区插入固定披露段，正式命名 **"RAW EXECUTION EVIDENCE WITH DERIVED SUMMARIES"**，声明 `summary`/`scope` 中的 `p2p_regressed_ids`、`p2p_preexisting_bad_ids` 等是 runner 对 post-vs-base 的**派生归类**而非裸测试输出，要求模型在 reason 中区分自证事实与继承归类，并声明这些字段不构成最终裁决。44/44 raw/structured 含披露，22/22 adjudicated **不含**（adjudicated 逐字节等于冻结 CEE bundle，22/22 校验相等）。
3. **充分性证书**：22/22 fixture 在三层均 gold-determined，未发现新欠定样本；执行中无欠定 cell。
4. **复检**：Gate-1 工程自检仍 20/20；跨模型 payload 字节一致；Label Leakage Audit 对实际服务字节命中 0；预算硬门（$1.50/模型、$3.00 总，pre-call）有效。preflight 合计 **11/11 PASS**。
5. **留存与凭据**：每行先持久化 `raw_response_text`+`raw_content_sha256`（`raw_persisted_before_parse=true`）再解析；reason / missing_evidence / evidence_gap 逐字留存。凭据扫描对 66 payload 命中 0；密钥只从 env/`~/.openai_key` 读取，不入输入或产物。
6. **模型参数与输出约束**：全量前先做 6-cell（最小 fixture×3 层×2 模型）真实探针：两后端均接受 `response_format=json_object`、未触发拒绝（因此无 plain-text 回退、无硬停）；served id 分别为 `deepseek-flash` 与 `gpt-4.1-mini-2025-04-14`，均与 E1 记录的 served id 相同。参数与冻结设计兼容，无需修改协议。

措辞纠正已采纳：本报告不使用"信息缺失替代解释已排除"，而表述为——**在当前形式化判决规则下，三层均包含足以机械确定 Gold 的信息**；这不等价于 reviewer 能从 Raw 正确提取事实、probe 具充分代表性、上游 summary 未提前完成关键适用性判断，或各证据通道在真实 code review 中同样可信。

---

## 1. 两模型 × 三层 Decision Appropriateness（数量 / 比例 / issue-cluster bootstrap 95% CI）

CI 为按 `instance_id` 重采样的 issue-cluster bootstrap（seed=7，n=10000，10 簇）；镜像 fixture 仅作簇内重复，不充独立 n。本轮无 INVALID/AMBIGUOUS/API_ERROR，故 parseable 与 all-requests 两个分母数值相同（列两个口径以备复核）。

| 模型 | 层 | n 正确 | DA（parseable=all） | 95% CI |
|---|---|---:|---:|---|
| DeepSeek-flash | raw | 17/22 | 0.773 | [0.563, 0.950] |
| DeepSeek-flash | structured | 19/22 | 0.864 | [0.737, 1.000] |
| DeepSeek-flash | adjudicated | 20/22 | **0.909** | [0.783, 1.000] |
| GPT-4.1-mini | raw | 9/22 | 0.409 | [0.176, 0.577] |
| GPT-4.1-mini | structured | 12/22 | 0.545 | [0.353, 0.677] |
| GPT-4.1-mini | adjudicated | 18/22 | **0.818** | [0.636, 0.957] |

**跨协议锚点复现**：两模型的 adjudicated DA 分别为 0.909 与 0.818，与冻结 CEE v1.1 的 DS 0.909 / GPT 0.818 **逐点相同**（同模型、同冻结 bundle、同 wire controls）。这支持 EAL 管线与 CEE 的可比性，但两者**只并列、不合池**。

要点：两个模型都呈 raw < structured < adjudicated 的**单调**点估计，但 CI 宽（n=10 独立 issue），不能据此外推；且抽象收益在两模型间大小悬殊（见 §2）。

## 2. 三个预注册配对差值（均可为负；不预设单调）

同模型内同 fixture 配对，单位=bundle，簇=instance_id，seed=7/n=10000；McNemar 精确双侧仅作描述。

| 模型 | 对比（高−低抽象） | 平均配对差 | 95% CI | 高对/低错 | 低对/高错 | McNemar p（描述） |
|---|---|---:|---|---:|---:|---:|
| DeepSeek | Adjudicated − Raw | **+0.136** | [−0.077, 0.381] | 5 | 2 | 0.453 |
| DeepSeek | Structured − Raw | +0.091 | [−0.143, 0.364] | 5 | 3 | 0.727 |
| DeepSeek | Adjudicated − Structured | +0.045 | [0.000, 0.143] | 1 | 0 | 1.000 |
| GPT-4.1-mini | Adjudicated − Raw | **+0.409** | **[0.250, 0.600]** | 10 | 1 | 0.012 |
| GPT-4.1-mini | Structured − Raw | +0.136 | [−0.048, 0.350] | 5 | 2 | 0.453 |
| GPT-4.1-mini | Adjudicated − Structured | **+0.273** | **[0.105, 0.476]** | 9 | 3 | 0.146 |

解读（对应用户最关注的两种可能，**两种都出现了，但分属不同模型**）：
- **DeepSeek ≈ 用户设想的第一种**：Structured 明显追上 Adjudicated（差仅 +0.045，CI 下沿 0），整体差距主要在 Raw→Structured（+0.091）。对该模型，主要困难偏向**从原始日志抽取/组织证据**，拿到整理好的执行事实后，有效性与政策推断已接近上限。
- **GPT-4.1-mini = 用户设想的第二种**：Structured 仍显著落后 Adjudicated（+0.273，CI 不含 0），且 Structured−Raw 仅 +0.136（CI 跨 0）。对该模型，即使给出结构化执行事实，仍难以正确判断**来源、关联性与证据充分性**；预裁决的 adjudicated 层带来最大且最集中的增益（Adj−Raw +0.409，CI [0.25,0.60]）。

三个差值本轮点估计均非负，但 DS 的两个跨 raw 差值 CI 跨 0；"抽象越高越准"在本 Pilot 中未被反例推翻，也未被强保证。

## 3. 每层混淆矩阵、Always-NEED baseline 与三个错误家族

行=模型判决，列=Gold（ACCEPT/REJECT/NEED）。**Always-NEED baseline = 9/22 = 0.409**。

DeepSeek-flash：
- raw：ACCEPT [6,0,0]；REJECT [1,6,4]；NEED [0,0,5]
- structured：ACCEPT [6,0,0]；REJECT [0,4,0]；NEED [1,2,9]
- adjudicated：ACCEPT [7,0,0]；REJECT [0,4,0]；NEED [0,2,9]

GPT-4.1-mini：
- raw：ACCEPT [5,1,6]；REJECT [0,2,1]；NEED [2,3,2]
- structured：ACCEPT [7,1,8]；REJECT [0,5,1]；NEED [0,0,0]
- adjudicated：ACCEPT [7,0,1]；REJECT [0,3,0]；NEED [0,3,8]

错误家族（parseable 为分母；rate 分母见指标文件）：

| 模型 | 层 | Over-Abstention | Unsupported Acceptance（false commit） | Unsupported Rejection |
|---|---|---:|---:|---:|
| DeepSeek | raw | 0 | 0 | **5** |
| DeepSeek | structured | 3 | 0 | 0 |
| DeepSeek | adjudicated | 2 | 0 | 0 |
| GPT | raw | 5 | 7 | 1 |
| GPT | structured | 0 | **9** | 1 |
| GPT | adjudicated | 3 | 1 | 0 |

对照 baseline 的关键观察：
- **GPT raw DA 0.409 恰等于 Always-NEED**：它在 raw 层的输出整体是混乱的高熵混合（5 个无依据 ACCEPT、5 个过度 abstain 兼有），并未形成稳定的"一律 NEED"策略，但准确度退到了机械弃权基线。
- **GPT structured 的 0 个 NEED 判决**：整理过事实后它转向**过度承诺**——9 个 unsupported acceptance 中有 8 个落在 NEED gold（insufficient 0/9，见 §5）。结构化消除了"找不到证据"的保守，却没有补上"判断证据是否充分"的能力。
- **DeepSeek raw 的 5 个 unsupported rejection 全部落在 NEED gold**：它在原始日志上倾向于把"症状消失 + 测试通过"直接读成决定性失败已被排除而 REJECT，越过了充分性门槛；结构化后该错误家族清零，转为更保守的 over-abstention。

## 4. 同一 Fixture 三层判决转移矩阵

行=起点层判决，列=终点层判决（ACCEPT/REJECT/NEED），22 fixture；本轮全部 parseable，无跳过。

**raw → structured**
- DeepSeek：ACCEPT [5,0,1]；REJECT [1,4,6]；NEED [0,0,5]
- GPT：ACCEPT [11,1,0]；REJECT [0,3,0]；NEED [5,2,0]

**structured → adjudicated**
- DeepSeek：ACCEPT [6,0,0]；REJECT [0,4,0]；NEED [1,0,11]（几乎稳定，仅 1 个 NEED→ACCEPT 被纠正）
- GPT：ACCEPT [8,1,7]；REJECT [0,2,4]；NEED [0,0,0]（**15/22 发生转移**，主要是 structured 的 ACCEPT 被 adjudicated 改判）

**raw → adjudicated**
- DeepSeek：ACCEPT [6,0,0]；REJECT [1,4,6]；NEED [0,0,5]
- GPT：ACCEPT [6,0,6]；REJECT [0,1,2]；NEED [2,2,3]

要点：DeepSeek 在 structured→adjudicated 已基本饱和（诊断信息在 raw→structured 段已大部分释放）；GPT 的判决在 structured→adjudicated 仍大规模重排，说明**结构化事实与"可据以裁决"之间对该模型还隔着一次实质性的有效性/政策判断**。

## 5. 按 evidence_class 分层（正确数/总数，DA）

| 模型 | 层 | sufficient_positive (7) | decisive_negative (6) | insufficient (9) |
|---|---|---:|---:|---:|
| DeepSeek | raw | 6/7 .857 | **6/6 1.000** | 5/9 .556 |
| DeepSeek | structured | 6/7 .857 | 4/6 .667 | **9/9 1.000** |
| DeepSeek | adjudicated | 7/7 1.000 | 4/6 .667 | 9/9 1.000 |
| GPT | raw | 5/7 .714 | 2/6 .333 | 2/9 .222 |
| GPT | structured | 7/7 1.000 | 5/6 .833 | **0/9 .000** |
| GPT | adjudicated | 7/7 1.000 | 3/6 .500 | 8/9 .889 |

- 两模型在 adjudicated 上都把 sufficient_positive 做到 7/7。
- **insufficient（NEED gold）是区分两层抽象能力的关键类**：GPT 从 raw 2/9 → structured 0/9（过度承诺）→ adjudicated 8/9；DeepSeek 从 raw 5/9 → structured/adj 9/9。证据充分性判断，而非单纯的正/负信号识别，承载了主要的层间效应。
- decisive_negative 上两模型在 adjudicated 都只有 4/6 与 3/6，**错误方向都是把 REJECT 判成 NEED_EVIDENCE**（对 decisive-negative 的过度保守，见 §6 逐字证据），这与 Gate-1 标记的 2 个 symptom-alone forcing REJECT（wrong_patch/stale_persists，grounding 要求最高）一致，是各层共同残留的难点。

## 6. reason / missing_evidence / evidence_gap 机制审计（逐字、数据驱动）

66 行/模型全部逐字留存三个自由文本字段。下列为基于文本与 gold/decision 的规则化归类，不调用模型、不推断无文本支撑的心理状态。

`evidence_gap` 枚举分布（非空数）：
- DeepSeek：stale 15、coverage_incomplete 7、linkage_mismatch 5、contradiction 3、空 36
- GPT：coverage_incomplete 10、stale 7、空 49（从不使用 linkage_mismatch/contradiction）

关键词在 reason/missing 中的提及行数：
- DeepSeek：symptom/probe 64、linkage 58、stale/fresh 54、coverage/incomplete 19
- GPT：linkage 62、stale/fresh 60、symptom/probe 57、coverage/incomplete 13

**stale / unlinked(linkage) / incomplete 的误用核查（命中 7 条，逐字可溯）**：
- *REJECT-gold 却以 coverage/incomplete 为由弃权*（把决定性失败说成"没跑全"）：DS structured `af83be49`；GPT raw `a242cd7a`、`59e46a77`；GPT adjudicated `f51defe8`。这是 decisive_negative 上 4 个 REJECT→NEED 错误的直接文本机制——模型承认 symptom/linkage，却用"覆盖不全"拒绝下 REJECT。
- *ACCEPT-gold 却援引 stale/fresh 顾虑*：两模型在 raw 的 `cd502546`、DS structured `f0851759`（该 cell 最终判决仍多数正确，属理由与结论张力，单列不过度解读）。
- 未发现把明确 unlinked/stale 证据当作 fresh/linked 接受的**反向**硬误用；GPT 从不显式使用 linkage_mismatch 标签，与其在 raw 上 linkage 类失败一致（它"不判 linkage"，而非"判错 linkage"）。

代表性逐字证据（节选，全文在 jsonl）：
- GPT structured 对 insufficient 的 false commit（`ec813709`）：*"…The issue symptom probe shows that the error is resolved post-patch (exit code 0 vs 1 pre-patch). The declared fail_to_pass tests…"* —— 仅凭 symptom 解除 + 声明的 f2p 即 ACCEPT，未独立核验覆盖与关联性。
- DS raw 对 insufficient 的 unsupported reject（`ec813709`）：*"Linkage and freshness are intact… The symptom probe is decisive and applicable…"*，gap 填 `contradiction` —— 同一 fixture 在 raw 被反向过判 REJECT，说明 Raw 日志下两模型对同一组事实的**充分性阈值不稳定**。
- GPT raw 对 decisive-negative 弃权（`faae0894`）：*"…the symptom probe confirms the patch fixes the symptom… However, the acceptance test run … shows 6 test failures in scope"* —— 抓到了决定性失败信号却停在 NEED，体现 raw 上"信号在、政策不落地"。

## 7. 敏感性与局限性（长度 / 证据位置 / Derived Summary / Probe Source）

- **长度纪律**：长度由实验条件本身决定，与层高度相关，因此本 Pilot **只记录、分层报告并讨论混杂，不把 token 数作为事后回归控制项**。Gate-2 实际服务字节 min/med/max：raw 26,568 / 57,442 / 247,257；structured 13,975 / 26,081 / 38,042；adjudicated 6,635 / 8,121 / 14,488。全部 fits DS 128k 与 GPT 1M，未触发截断；最大 raw（247KB）仍在窗内。因此"raw 最差"不能用截断解释，但长度/格式/grounding 步数在 raw↔structured 对比中仍**不可分离**（Gate-1 已记）。
- **证据位置**：Gate-2 服务字节上，决定性 symptom 证据位置 fraction 中位 raw 0.970（min .880）、structured 0.930（min .883）；adjudicated 字节未变，沿用 Gate-1 的 0.967。三层证据仍同在尾部，head 插入的固定披露段未改变"顺序跨层平衡"，层间差不宜归因于差异化排序。
- **Derived Summary（半裁决泄漏）**：22/22 的 summary/scope 是 runner 对 post-vs-base 的派生归类（`p2p_regressed_ids` 等）。raw 与 structured **同等可见**这些字段，故该泄漏不偏 raw↔structured 对比，但会整体减少两层的 grounding 步数，并可能轻微抬高二者相对"纯裸日志"的表现；Raw 全称必须写作 **Raw Execution Evidence with Derived Summaries**。这限制了"从原始日志提取"这一解释的纯度。
- **Probe Source 缺失**：13/22 fixture 缺探针源（post-patch p2p per-test map 缺 6、baseline per-test map 缺 12）。这些缺口在 forcing 分析中均非决定性（操作数是探针 pre/post 输出与 exit code，22/22 在），但探针↔issue 保真无法从源复核，模型只能依赖签名记录；baseline 缺 map 的 12 fixture 上，acceptance 通道的适用性判断部分继承了上游 summary。
- **统计与外推**：n=10 独立 issue，CI 宽且镜像簇内相关；temperature 0 非强确定、served id 相同不等于后端权重被钉死；McNemar 仅描述。**不主张跨项目/跨模型家族普适**——事实上 DS 与 GPT 呈现两种不同机制，本身就是"勿跨家族外推"的证据。
- 充分性措辞：结论限于"形式化判决规则下三层均含足以机械确定 Gold 的信息"，不主张 reviewer 必然提取成功或通道现实等可信。

## 8. 完整工程审计

| 项 | DeepSeek-flash | GPT-4.1-mini |
|---|---|---|
| requested model | deepseek-flash | gpt-4.1-mini |
| served model（逐行） | `deepseek-flash` | `gpt-4.1-mini-2025-04-14` |
| served == E1 记录 id（全部行） | true | true |
| response_format | json_object（66/66） | json_object（66/66） |
| 服务端 schema 强制 | false（靠本地五键校验） | false |
| plain-text 回退 | 未使用 | 未使用 |
| tools / turns | 0 / 1 | 0 / 1 |
| temperature / max_tokens | 0 / 4096 | 0 / 4096 |
| 输入 token（usage 合计） | 643,744 | 600,010 |
| 输出 token（usage 合计） | 20,032 | 12,318 |
| 费用 | $0.21716 | $0.25971 |
| 墙钟合计 | 163.08 s | 133.93 s |
| API_ERROR / INVALID / AMBIGUOUS | 0 / 0 / 0 | 0 / 0 / 0 |
| raw 先于解析持久化 | 66/66 | 66/66 |
| payload sha 与 freeze 一致 | 66/66 | 66/66 |

- 总费用 **$0.476875 ≤ $3.00 硬顶**；每模型 ≤ $1.50；预算状态 `within_cap`，无预算停止；跨模型 payload 字节一致=true。
- freeze manifest sha256（运行记录）：`6faffc8261e7b03b…`（完整值见 [eal_gate2_run_audit.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/gate2_runs/eal_gate2_run_audit.json)）；代码哈希（runner/analyzer/freeze/protocol/render/cee v1.1）在 freeze manifest 中逐文件留存。
- 无重试计费：全部 132 cell 均一次有效判决；续跑幂等（6-cell 探针 + 126 续跑，无重复、无遗漏）。
- DS 同名 served id 不等于后端权重可审计（id 相同、权重不钉），已在 §7 披露。

---

## 结论（供 Gate 3 决策，不作超出 Pilot 的主张）

1. 三层实验**确实提供了不同的诊断信息**：raw 主要暴露证据提取问题，structured 暴露"组织事实 ≠ 判断充分性"，adjudicated 是政策执行上限。
2. 两模型呈现用户预设的两种不同机制（DS 偏第一种、GPT 偏第二种），说明"主要瓶颈在哪一层"是**模型相关**的。
3. 最稳定、可跨模型复现的残留难点是 **decisive-negative 的过度保守**（symptom-alone forcing REJECT 被判 NEED）与 **insufficient 类的充分性校准**（GPT structured 0/9）。
4. adjudicated 逐点复现 CEE v1.1 锚点（0.909 / 0.818），管线与既有冻结结果自洽。

**Gate 2 到此停止**：未运行 Gemini、未新增 issue、未修改 E1/CEE/EAL 任何冻结数据与指标、未 git commit。是否进入 Gate 3（优先扩充独立 issue，还是先修正证据抽象协议，尤其是 insufficient 类的充分性判据与 decisive-negative 的保守偏差）需另行书面批准。
