# GroundedReview Phase 3（阶段 1：离线）实施计划

说明：本计划只执行到「离线实现 + 自检 + 提交检查结果」。Smoke Test（阶段 2）任务已列出但处于 blocked，须用户在看到阶段 1 成果后明确放行；扩样（阶段 3）与正式 Pilot（阶段 4）不在本计划执行，Smoke 门控通过后另立计划。

## Task 1: 三态基础模块（schema/解析/非对称金标准纯函数）
- **Status**: `completed`
- **Completion Evidence**: `evidence/ternary.py` 已实现 TERNARY_DECISION_SCHEMA、parse_ternary_decision、gold_decision（签名仅 evidence_integrity/decisive_failure/sufficient_success，inspect 断言无 patch_correct/merge_acceptable）、derive_evidence_facts、build_gold_row(s)、render_gold、CLI。TR-1.1/1.2/1.3/1.4 由 Task7 selfcheck check_gold_asymmetry 持续验证（7 行真值表 + 冻结文件逐行重导一致 + 二次渲染确定性）。
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 新增 `evidence/ternary.py`：三态 JSON schema（decision enum = ACCEPT/REJECT/NEED_EVIDENCE，reason、evidence_mismatch 保留；NEED_EVIDENCE 时允许 `missing_evidence` 简述）；三态解析函数返回 ACCEPT/REJECT/NEED_EVIDENCE/INVALID/AMBIGUOUS（多候选冲突仍 AMBIGUOUS，不猜第一个）。
  - 同模块提供**非对称证据门槛**金标准纯函数（spec D3）：
    ```
    gold_decision(*, evidence_integrity, decisive_failure, sufficient_success):
        if decisive_failure: return REJECT
        if evidence_integrity and sufficient_success: return ACCEPT
        return NEED_EVIDENCE
    ```
    入参只能是证据派生事实（linked/fresh/complete、可信且适用的 executed_failure/success），**不得接收 merge_acceptable/patch_correct**；另提供 `derive_evidence_facts(fixture_record, normalized_outcomes)`：仅当 linked ∧ fresh 时，已执行的声明 f2p 失败或 scoped 回归才置 decisive_failure（不要求 complete，partial-but-decisive → REJECT）；sufficient_success 要求 linked∧fresh∧complete∧执行数>0∧无失败。stale/wrong_patch 上的失败不适用，不置 decisive_failure。
  - 提供冻结写出器：读取夹具清单（phase2 5 行 + phase3 镜像行）与其中证据事实生成 `evidence_store/phase3_gold.jsonl`，字段 id/scenario/patch_correct（仅审计列）/evidence_integrity/decisive_failure/sufficient_success/gold/basis；canonical 键排序、重复运行逐字节一致。
  - 不修改 `pilot.py` 的二元 parse_decision/schema（Phase1/2 路径零影响）。
- **Acceptance Criteria Addressed**: AC-3, AC-2（解析部分）
- **Test Requirements**:
  - `rule` TR-1.1: 对 5 种解析输入（三态合法/无 JSON/冲突双 JSON）分类正确；证据：离线断言输出。
  - `rule` TR-1.2: gold 纯函数对 valid/contradictory/stale/incomplete/wrong_patch、BAD×stale、GOOD×wrong_patch 及 **partial-but-decisive（complete=false 但 linked/fresh 且有已执行失败 → REJECT）** 的映射全部符合 spec D3；证据：断言表。
  - `rule` TR-1.3: 标签无关性——gold_decision 签名不含 patch_correct；derive 出的同一组证据事实，无论 gold 文件是否写 patch_correct 列，gold 取值相同；证据：单元断言。
  - `rule` TR-1.4: gold 文件二次生成哈希一致；证据：连续两次生成后哈希对比。

## Task 2: 服务端会话策略 strict/escalate
- **Status**: `completed`
- **Completion Evidence**: `evidence/server.py`（POLICIES、reason 门控、strict 403、consistency 仅授权诊断裁决、audit）与 `evidence/views.py`（D 级剥离 f2p/p2p/验收 digest，保留 symptom 与 pass_to_pass_baseline）。TR-2.1–2.4 由 selfcheck check_phase3_policy_http 真实 HTTP 验证通过（含 contradictory 隐藏 f2p 失败时 strict consistency=consistent 不泄漏；wrong_patch F/F→contradicted；空白 reason %20%20→400）。
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - `POST /sessions` 增加 `policy`（`strict`|`escalate`，缺省向后兼容：无 policy 时保持 Phase-2 既有行为；仅当显式传 policy 时启用新语义；非法值 400），与 evidence_tier 一起入 session 与审计。
  - `_log` 改造：D 级请求 f2p/p2p/p2p_baseline 时——strict 直接 **403** JSON 错误（不读正文、审计 `denied_strict`）；escalate 要求 query（GET 无 body）带非空 `reason`（URL-encoded），缺失/空白 → **400**（审计 `escalation_reason_missing`），带理由时维持横幅 + `X-Evidence-Tier-Escalation:1`，审计记录 reason/log 名/cell。
  - **Strict consistency 改为仅依据授权诊断证据裁决（封堵隐藏答案侧信道）**：strict+D 下只用注册 claim 与症状探针等可见诊断——症状与 claim 冲突 → contradicted；症状支持 → consistent；诊断无法裁决的验收类 claim → 新 verdict `insufficient_evidence`（定性 reason）；**不得**读取 summary 的 f2p/p2p 归一化计数。escalate+D 下允许按验收归一化裁决，但 consistency 调用同样必须带非空 reason，审计 `consistency_escalation`，响应加升级标记。无 claim 仍 409。
  - **views.py D 投影移除验收日志 log_digests（f2p/p2p/p2p_baseline 的 digest 键）**，symptom digest 保留；strict 与旧二元 D 投影的这一变更须同步检查不破坏既有 selfcheck（既有检查不断言验收 digest 存在）。
  - 其余端点按 tier 既有投影不变；新增 selfcheck 可区分 policy 的会话路径。
  - tier A 不受 policy 影响（验收基线照常）；无 policy 的 Phase-2 会话行为与现在完全一致（含旧 consistency 逻辑），保证二元零回归。
- **Acceptance Criteria Addressed**: AC-5, AC-5b, AC-6
- **Test Requirements**:
  - `rule` TR-2.1: strict 会话对三个验收日志名均返回 403 且响应体无任何 verdict 文本，审计出现 denied_strict；证据：selfcheck HTTP 用例。
  - `rule` TR-2.2: escalate 无 reason/空 reason → 400；非空 reason → 200 + 横幅 + 升级头 + 审计含 reason；reason 经 query string 传递并正确 URL-decode；证据：selfcheck 用例与 audit.jsonl 条目。
  - `rule` TR-2.3: strict 下 artifact/verify/freshness/coverage/symptom 行为不回归；D 投影不再含验收 log_digests；strict consistency 只按注册症状探针裁决——症状仍复现（wrong_patch，pre=False/post=False）正向声明 → contradicted；症状已消失（contradictory，post=True）→ consistent（隐藏 f2p 失败不得泄漏为 contradicted）；无注册症状/诊断无法裁决验收部分 → insufficient_evidence；无 policy 旧路径对 contradictory 仍按隐藏计数返回 contradicted（二元回归断言）；证据：selfcheck 回归 + 新增用例。
  - `rule` TR-2.4: escalate 下 consistency 无 reason → 400/拒绝，带 reason 才返回验收裁决且有审计与升级标记；证据：selfcheck 用例。

## Task 3: 三态提示词与策略化工具说明
- **Status**: `completed`
- **Completion Evidence**: `evidence/prompts.py`：TERNARY_CONDITIONS 五条件、ternary_condition_tier_policy、build_ternary_messages、ternary_tools。TR-3.1 由 selfcheck check_ternary_prompts 文本扫描通过（静态两条件无 tools 措辞；strict 工具枚举无 f2p 且提示 403/disabled；escalate 含 reason/400/audited）。
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 在 `prompts.py` 新增三态 builder（不改二元 builder）：系统/用户文案明确三态语义——ACCEPT=证据有效且充分支持可合并；REJECT=证据有效且含决定性失败/回归；NEED_EVIDENCE=证据无法链接/过期/不完整等导致**无法对补丁下结论**，必须指出缺口；明确「证据失效不等于补丁错误」「证据充分时不许用 NEED_EVIDENCE 逃避」。
  - T3D-Strict 工具说明移除验收日志升级入口（工具枚举中不暴露 f2p/p2p；symptom 保留），调用被服务端 403 时提示该通道在本策略不可用；T3D-Escalate 工具说明要求升级请求必填 reason 并告知被记录；T3A-T 全工具。
  - 静态三态（T2D-T/T2A-T）不出现任何工具措辞。
- **Acceptance Criteria Addressed**: AC-13, AC-2（提示部分）
- **Test Requirements**:
  - `rule` TR-3.1: 静态三态提示无工具标记；Strict 提示无 f2p/p2p 升级措辞；Escalate 提示含 reason 必填与审计告知；证据：文本扫描断言。
  - `rubric` TR-3.2: 三态语义中立性；scale 1-5；anchors 1=NEED 成万能退路且无法区分证据缺口与困难判决，3=基本清晰但有一处灰色地带，5=三态边界与四类错误完全对齐且激励中立；threshold >=4；证据：提示词文本 + 与 AC-8 评分矩阵的对照评审。

## Task 4: 三态 runner（phase3_run.py，独立结果文件）
- **Status**: `completed`
- **Completion Evidence**: `evidence/phase3_run.py`：P3Client、ScriptedModel、mock 编排（strict 7 工具含必试 f2p 验 403；escalate 8 工具含 f2p 与 consistency 的 400→200）、--fixtures 多清单、--max-budget-usd fail-fast、独立输出 phase3_ternary_results.jsonl。干净 mock 产物 45 cell（9 夹具×5 条件）/45 trace，failed_cells=0。TR-4.2/4.3 trace 抽查通过：路径 A `artifact200→verify200→freshness200→coverage200→symptom200→f2p 403→consistency200→NEED`；路径 B `f2p 400(无reason)→f2p 200(带reason)→consistency 400→consistency 200→REJECT`；9/9 strict cell 含 403，9/9 escalate cell 含 400→授权序列。
- **Priority**: high
- **Depends On**: Task 2, Task 3
- **Description**:
  - 新增 `evidence/phase3_run.py`：条件 `T2D-T,T3D-Strict,T3D-Escalate,T2A-T,T3A-T`；每 cell 独立 session（主动臂），open_session 传 policy=strict/escalate/A；Escalate 的 get_run_log 调用透传模型给出的 reason（空则由 runner 反馈 400 给模型并记录）。
  - 输出默认 `evidence_store/phase3_ternary_results.jsonl`，每行 `protocol='ternary'`、policy、parsed（三态标准化）、called/saw 各表面标志、`escalation_requested/granted/denied/reasons`、tokens/calls/wall/cost、budget/emergency 标志；错误 cell 与 INVALID 分别落盘不毁批；resume 仅跳过无 error 完成行。
  - 沿用 flash 思考关闭、json_schema→纯 JSON 回退、per-cell emergency tokens、batch `--max-budget-usd` fail-fast。
  - 支持 `--fixtures` 多清单（phase2 + phase3）；支持 `--mock` 离线模式：从文件读预制消息序列（含工具调用回合），不触达任何 LLM，但**对接真实本地 server 与真实 runner client 工具循环**，用于无费用端到端验证。
  - **Mock 必须至少编排两条完整多轮脚本并逐轮落 trace 断言（FR-12）**：
    - 路径 A（诊断内核验后弃权）：open strict 会话 → get_test_artifact → verify linkage → check_freshness → check_coverage → 终判 **NEED_EVIDENCE**；对 stale/incomplete/wrong_patch 各跑一次，断言每轮工具名/参数/响应键与终判。
    - 路径 B（升级全流程）：open escalate 会话 → 请求 acceptance log（f2p）不带 reason → 期望 **400** → 同会话补非空 reason → 期望 granted（横幅 + 升级头 + 审计）→ 读取证据 → 终判。
    - 附加：strict 会话请求 f2p → **403** → denied_strict 审计 → granted=0。
- **Acceptance Criteria Addressed**: AC-2, AC-6b, AC-11, AC-10A（运行器能力）
- **Test Requirements**:
  - `rule` TR-4.1: mock 模式跑通 5 条件 × 至少 3 类裁决 + 1 INVALID + 1 AMBIGUOUS，结果字段完整且写入独立文件；证据：mock 运行产物。
  - `rule` TR-4.2: **路径 A** 在 stale/incomplete/wrong_patch 三个场景均按 linkage→freshness→coverage 顺序真实调用并终判 NEED_EVIDENCE，逐轮 trace（工具名/参数/关键响应/终判）与脚本断言一致；证据：mock trace 文件。
  - `rule` TR-4.3: **路径 B** 缺 reason 收到 400、补 reason 后 granted 且记录理由、读完证据终判；strict 403 路径 denied 计数正确、granted=0；证据：mock trace + 审计条目。
  - `rule` TR-4.4: `--max-budget-usd 0` 时首 cell 前即停止，phase1/2 文件无写操作（mtime/哈希）；mock 全程零 API 费用；证据：试运行与文件审计。

## Task 5: 镜像夹具构建（phase3_build.py）
- **Status**: `completed`
- **Completion Evidence**: `evidence/phase3_build.py` 真实构建四镜像（Python 3.9.25 + pytest 8.4.2 重放 canonical 批次）：M1 stale_bad(glm5:13798, linked=T/fresh=F/complete=T, fail=2,n=103 但 fresh 失效→NEED)、M2 wrong_patch_good(qwen-coder:14531 异源 artifact, linked=F, fail=0,n=86)、M3 incomplete_good(linked=T/fresh=T/complete=F, fail=0,n=1)、M4 incomplete_decisive_bad(linked=T/fresh=T/complete=F, fail=1,n=1, df=True→REJECT)。`phase3_fixtures.jsonl` 4 行；GOOD/BAD 配对 stale↔stale_bad、wrong_patch_good↔wrong_patch 齐备；TR-5.1/5.2 由 selfcheck check_phase3_fixtures 验证，TR-5.3 由 Task8 哈希审计验证。
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 新增 `evidence/phase3_build.py`，复用 phase2_build 的 stage/树/put_fixture 原语；产出独立清单 `evidence_store/phase3_fixtures.jsonl`（仅镜像行，不回写 phase2 清单）。
  - 确定性选样规则：M1 = 第一个满足 class∈{A,C}（merge_acceptable=false）且声明 f2p/p2p 可在本地完整执行的补丁，构造 BAD×stale（惰性注释树 + 完整执行，expected linked=true/fresh=false/complete=true）；M2 = 第一个 class B（merge_acceptable=true）且存在异源规范 artifact 的补丁，构造 GOOD×wrong_patch（投递异源签名 artifact，linked=false）。选样 id 与理由打印并写入 fixtures_meta。
  - M3（可选）= GOOD×incomplete：泛化 incomplete 构造以支持「省略一个通过的声明 f2p 测试」；仅在不破坏既有 incomplete 语义、本地执行顺利时纳入。
  - M4（可选但优先，用于实证非对称门槛）= BAD×incomplete-but-decisive：选 class A（merge_acceptable=false）补丁，构造 linked/fresh 但覆盖不完整、同时**保留一个已执行且失败的声明 f2p**（或保留失败 f2p 并省略一个 scoped p2p），expected linked=true/fresh=true/complete=false/decisive_failure=true，gold=REJECT。需泛化 incomplete builder 支持「保留失败、省略其余项」的确定性选择规则；无法满足则与 M3 一样按 blocked 回报，不降低构造条件。
  - 镜像场景名使用 `stale_bad`/`wrong_patch_good`/`incomplete_good`/`incomplete_decisive_bad`（标签不入任何提示），expected 位（含 decisive_failure/sufficient_success 的证据事实）显式写入清单；为每目标写 canonical attestation。
  - 全程 3.11 本地执行，不产生 API 费用；新 artifact 一律新 fix_ id，仅追加。
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `rule` TR-5.1: M1/M2 构建成功，签名与 log digest 校验通过，服务端核验 freshness/linkage 与 expected 完全一致；证据：selfcheck 新夹具用例。
  - `rule` TR-5.2: 合并清单后 GOOD/BAD × VALID/INVALID 四格各 ≥1，stale 与 wrong_patch 各有 GOOD/BAD 配对（M3/M4 结果如实记录；M4 若建成则服务端核验 complete=false 而 gold=REJECT）；证据：gold/清单计数输出。
  - `rule` TR-5.3: phase2_fixtures.jsonl 与既有 fix_ artifact 未被修改；证据：前后哈希对比。
  - `rule` TR-5.4（无合格样本时）: 不降低标准硬凑，任务置 blocked 并回报候选清单与失败原因；证据：选样审计输出。

## Task 6: 三态指标 metrics3.py
- **Status**: `completed`
- **Completion Evidence**: `evidence/metrics3.py`：classify 十类 error_class（appropriate_accept/reject/abstain、over_abstain、false_approve、false_reject、false_commit_accept、unsupported_reject、invalid/ambiguous_protocol）；双指标分区（decision_appropriateness 分母 parseable，cluster bootstrap CI seed=7/n=10000；end_to_end_review_success 分母全部）；deployment_safe_view 独立分区；paired_ternary_table + 描述性 McNemar；compute 默认排除 mock/error 行。TR-6.1/6.2/6.3 经 45 行桩（9 场景×5 判决）手工计数断言全部通过（临时桩脚本验后已删）；工程产物 `metrics_phase3_ternary_mock.json`（--include-mock）。
- **Priority**: high
- **Depends On**: Task 1, Task 4
- **Description**:
  - 新增 `evidence/metrics3.py`，读三态结果 + `phase3_gold.jsonl` join；输出 `evidence_store/metrics_phase3_ternary.json`。
  - 指标：Decision Appropriateness（分母=parseable）；End-to-End Review Success（分母=全部 cell，INVALID/AMBIGUOUS 失败）；INVALID/AMBIGUOUS 单列计数与比例；Coverage（非 NEED 占比）；已决子集 false-approve/false-reject；适当弃权（失效格→NEED）、过度弃权（valid/contradictory→NEED）、过早定论（失效格→ACCEPT/REJECT，细分 false-commit ACCEPT 与 unsupported REJECT）；升级 requested/granted/denied、升级后判决分布；tokens/calls/wall/USD 与每适当决策成本；共享目标配对表（带 n、描述性 McNemar p）；静态组（T2D-T/T2A-T）与主动组（T3D-*/T3A-T）分列。
  - 另输出明确命名的 `deployment_safe_view`（NEED/INVALID 按非接受处理），与判断力指标分区，禁止混排。
  - 二元 metrics2.py 不改。
- **Acceptance Criteria Addressed**: AC-7, AC-8
- **Test Requirements**:
  - `rule` TR-6.1: 用含已知金标准的桩结果（每场景×每判决）手工核对全部计数一致；证据：桩数据与对照核算。
  - `rule` TR-6.2: BAD×INVALID（stale/wrong_patch/incomplete，无决定性失败）上 REJECT/ACCEPT 均判不适当、仅 NEED 适当；contradictory 与 **M4 partial-but-decisive** 上 NEED=过度弃权/REJECT 适当（complete=false 不影响）；valid 上 NEED=过度弃权/ACCEPT 适当；证据：评分矩阵断言。
  - `rule` TR-6.3: INVALID 不出现在 Decision Appropriateness 分母但出现在 E2E 分母；证据：桩数据核对。

## Task 7: selfcheck 扩展（strict/escalate/gold/镜像/非干涉/回归）
- **Status**: `completed`
- **Completion Evidence**: TR-7.1 `uv run --python 3.13 python -m evidence.selfcheck` 退出码 0，输出存档 `evidence_store/phase3_selfcheck_output.txt`；新增 6 检查全绿：check_ternary_prompts、check_gold_asymmetry（含冻结文件重导；Windows CRLF 下按文本行比对，字节稳定性另由 Task8 哈希保证）、check_phase3_policy_http（真实 fixture 真实 HTTP：400/403/审计/正面对照）、check_phase3_fixtures（四表面 + GOOD/BAD 配对 + M4 strict 403/escalate contradicted + TR-5.2 九场景）、check_metrics3_pure（7 条 classify 断言）、check_noninterference。TR-7.2 全程本地回环。TR-7.3 World A/B：3 轮独立 strict+D 会话 × {artifact,verify,freshness,coverage,consistency,symptom_log,f2p_status} 归一化 diff 全空；两世界 consistency 均 consistent 不翻转；每世界跨轮自洽无时序编码；正面对照 World B escalate+reason → consistency contradicted、f2p 200 含 FAILED + X-Evidence-Tier-Escalation:1、audit consistency_escalation:contradicted。临时 store 用后 rmtree，零污染 evidence_store。
- **Priority**: high
- **Depends On**: Task 2, Task 5, Task 6
- **Description**:
  - 在 `selfcheck.py` 增加：strict 全端点泄漏扫描与 403/审计断言；escalate reason 门控（含 consistency reason）；三态提示无场景标签；gold 非对称映射（含 partial-but-decisive、标签无关性断言）与冻结一致性；新夹具签名/digest/attestation/四表面核验；非干涉打分样例（调用 metrics3 纯函数）。
  - **新增真实隐藏数据扰动非干涉（FR-11/AC-5b）**：在 tempfile 临时 store 用 store 原语构造同一目标补丁的 World A（隐藏 f2p/p2p 全过）与 World B（隐藏含 f2p 失败/p2p 回归）两份签名 artifact，保证 D 级投影逐字段相同（含 symptom 日志、attestation 声明集合、scope、started_at/finished_at、可见 log_digests）；分别起 build_server，用 strict+D 会话（相同注册 claim）多次逐一调用 artifact/verify/freshness/coverage/consistency/log/symptom，归一化（剔除 sid/ts 等显式非语义键）后逐接口 diff，必须完全一致；重点断言 consistency verdict 不翻转（不得 A=consistent、B=contradicted）；对剔除字段做多次重复的相关性检查（不允许时序/序号编码隐藏结果）。另验证 World B 在 escalate+reason 下可观察到失败且有审计（隔离边界的正面对照）。临时 store 用后即删，绝不写入 evidence_store。
  - 保留并回归既有全部用例（可见性、tier 泄漏、truth/store、HTTP linkage、5 夹具、极性）。
- **Acceptance Criteria Addressed**: AC-5, AC-5b, AC-6, AC-9
- **Test Requirements**:
  - `rule` TR-7.1: `uv run --python 3.13 python -m evidence.selfcheck` 退出码 0，新旧用例全绿；证据：完整输出。
  - `rule` TR-7.2: 自检全程仅本地回环 HTTP、无外部 API 调用；证据：命令环境与网络面说明（无 key 使用、无外网请求代码路径）。
  - `rule` TR-7.3: World A/B 逐接口归一化 diff 为空、consistency verdict 两世界一致、非语义字段无相关；escalate 正面对照可观察差异且有审计；证据：selfcheck 扰动 diff 报告（空）与审计片段。

## Task 8: 阶段 1 离线验收与付费前检查点
- **Status**: `completed`（交付物已提交；随后停止等待阶段 2 明确批准，Task 9 保持 blocked）
- **Completion Evidence**: 汇总审计文件 `evidence_store/phase3_task8_audit.json`：
  1. Selfcheck 输出 `phase3_selfcheck_output.txt`（exit 0，新旧用例全绿，见 Task7）。
  2. Mock Trace：`phase3_mock_traces/` 45 份；路径 A/B 与 403 抽查通过（见 Task4）；结果 `phase3_mock_results.jsonl` 45 行、failed_cells=0、189 次真实本地工具调用。
  3. Noninterference：见 Task7（3 轮 × 7 表面 diff 空 + 正面对照）。
  4. Fixture Matrix：审计文件 fixture_matrix 9 行（valid ACCEPT L/F/C fail0/n39；contradictory REJECT df1 fail1/n114；incomplete NEED；stale NEED；wrong_patch NEED；stale_bad NEED L/~F/C fail2/n103；wrong_patch_good NEED ~L fail0/n86；incomplete_good NEED fail0/n1；incomplete_decisive_bad REJECT L/F/~C df1 fail1/n1）；四格 GOOD/BAD × VALID/INVALID 与 stale/wrong_patch 配对齐备。
  5. Gold Hash：`phase3_gold.jsonl` sha256=`dbebcfc311a2402528ceb745c33fc03613e0f433dfda82a779886591f40e45d7`（9 行）；确定性重导（CLI 写临时文件）字节哈希相同、逐行内容相同。
  6. 历史 Hash Diff：213 个基线文件中 211 个逐字节未变、无缺失；实验结果/夹具/artifact 修改数为 0；仅两个运行时产物变化——audit.jsonl（server `'a'` 追加日志，含 denied_strict=15、escalation_reason_missing=12、consistency_escalation=7 追加记录）与 fixtures_meta.json（实验员侧 provenance map，put_fixture 时整体重写，9 键全部 fix_ 命名空间且 phase3 仅新增 4 键），二者均非 Phase1/2 实验结果。新增 34 个白名单 phase3 artifact/log/signature/attestation/probe 文件 + 45 mock trace + 清单/gold/选样/指标/selfcheck 输出，无未分类新增。
  7. 零费用：45 mock cell 全部 mock=true、cost_usd 合计 $0.0；ScriptedModel 进程内出判决，mock 路径不构造外部 HTTP client（环境中虽有 DEEPSEEK_API_KEY，mock 模式从不读取）。新增源码：ternary.py、metrics3.py、phase3_run.py、phase3_build.py 四个新文件，server.py/views.py/prompts.py/selfcheck.py 增量修改；metrics2.py 与 Phase1/2 文件未改。
  8. Smoke 预算：9 夹具 × 5 条件 = 45 cell（T2D-T/T3D-Strict/T3D-Escalate/T2A-T/T3A-T 各 9）；Phase2 实测 deepseek-flash 58 cell $0.1412（$0.00243/cell），45 cell 线性外推 ≈$0.1096，硬顶 $0.30（fail-fast `--max-budget-usd 0.30`，约 2.7× 余量）。门控拆分已写入审计 smoke_plan.gating_split：Engineering Gates 六项硬门槛（权限隔离/gold 冻结/无泄漏/INVALID 计分/结果独立存储/预算）；Research Outcomes（stale/wrong_patch 误 REJECT、contradictory 过度弃权、工具滥用、三态准确性）如实报告、不作为门控、禁止改 prompt 重跑凑结果。
- **Priority**: high
- **Depends On**: Task 4, Task 5, Task 6, Task 7
- **Description**:
  - 3.11 构建镜像 → 生成冻结 gold → 3.13 跑 mock 端到端（含路径 A/B）+ selfcheck（含 World A/B 扰动）+ metrics3 桩核对。
  - 汇总并向用户提交以下检查结果（缺一不可）：
    1. **Selfcheck** 完整输出（退出码 0，新旧用例全绿）；
    2. **Mock Trace**（路径 A 三场景逐轮 + 路径 B 400→reason→granted + strict 403）；
    3. **Noninterference Test** 报告（World A/B 各接口归一化 diff 为空、consistency 不翻转、剔除字段无相关、escalate 正面对照）；
    4. **Fixture Matrix**（现有 5 + 新建 M1/M2（/M3/M4）的 GOOD/BAD × VALID/INVALID 四格覆盖与配对计数、expected 证据事实）；
    5. **Gold Hash**（phase3_gold.jsonl 的 sha256 与确定性重跑 diff 为空的证据）；
    6. **历史文件 Hash Diff**（phase1/2 全部结果/指标/夹具/artifact 前后哈希清单，差异为空）；
    7. 新增/修改文件清单、strict/escalate 行为证据、零费用证明；
    8. **Smoke API 预算**（条件/夹具/cell 数/单次预估花费/≤$0.30 总池与 fail-fast 设置）。
  - 向用户提交检查结果并**停止**，等待明确放行后才进入 Task 9。
- **Acceptance Criteria Addressed**: AC-1, AC-3, AC-4, AC-5b, AC-6b, AC-9, AC-11, AC-12
- **Test Requirements**:
  - `rule` TR-8.1: 全部离线命令成功且上述 8 项证据齐备；哈希审计显示 phase1/2 文件零改动；证据：检查结果汇总。
  - `rule` TR-8.2: 在未获用户放行前不执行任何付费命令；证据：执行记录无 API 调用。

## Task 9: Smoke Test（阶段 2，已完成；停止等待 Task 10 再次批准）
- **Status**: `completed`
- **Priority**: high
- **Depends On**: Task 8
- **Unblock Condition**: 用户明确批准付费 Smoke（总池 ≤$0.30）— 已获批准并执行
- **Description**:
  - 用户放行后：启动证据服务；`uv run --python 3.13 --with openai python -m evidence.phase3_run --fixtures evidence_store/phase2_fixtures.jsonl,evidence_store/phase3_fixtures.jsonl --conditions T2D-T,T3D-Strict,T3D-Escalate,T2A-T,T3A-T --model deepseek-flash --max-budget-usd 0.30 --output evidence_store/phase3_ternary_results.jsonl`；随后 metrics3 出报告，按 AC-10 **分开核对 Engineering Gates（A 组 8 项硬门槛）与 Research Outcomes（B 组如实报告）**。
  - A 组任一门控失败：回报，仅允许修工程代码/协议后重跑（共用 $0.30 池，超支须重新授权）；**禁止改 gold/夹具真值提分**（AC-12）。
  - B 组模型表现（stale 上误 REJECT、contradictory 上过度弃权、过度调用工具、三态准确性等）无论好坏一律留档报告，**不作为 Smoke 失败条件，禁止据此改 prompt 反复重跑**；每次重跑的 B 组结果全部保留，不挑选好看的一次。
- **Acceptance Criteria Addressed**: AC-10, AC-12, AC-13（实测复核）
- **Test Requirements**:
  - `rule` TR-9.1: A 组 Engineering Gates 8 项全部满足且累计 ≤$0.30；B 组 Research Outcomes 完整成表（不设通过线）；证据：Smoke 结果、门控对照表、研究结果分布表、花费汇总。
  - `rule` TR-9.2: gold 文件 Smoke 后哈希与冻结值一致；证据：哈希对比。
- **Completion Evidence（2025 运行，deepseek-flash 思考关闭，9 fixtures × 5 = 45 cell，独立会话）**:
  - 产物：`evidence_store/phase3_ternary_results.jsonl`（45 行，全新文件）、`evidence_store/metrics_phase3_ternary.json`、`evidence_store/phase3_run_audit_summary.json`、运行日志 `evidence_store/phase3_live_run.log`；mock 回归 `phase3_mock_results.jsonl`（45/45，$0）+ `metrics_phase3_ternary_mock.json`。
  - 付费前三项加固（用户要求）：(1) `BudgetGuard` 每次模型调用**前**按「当前 transcript 保守 prompt token 上界 + max_tokens=8192 完成上界」检查，剩余预算不足即 `BudgetGuardStop`（该次调用不发出，绝不事后超额），并设单 cell ≤12 次模型调用；(2) 每行记录 `version`（`prompt_version=p3-ternary-v1`、`gold_sha256`、per-file + combined `fixture_manifest`、per-cond `prompt_fingerprint`）与实际 `model_served`；(3) 运行级服务端审计切片汇总 `phase3_run_audit_summary.json`。
  - **Engineering Gates A 组 8/8 通过**：①四格全覆盖（GOOD-VALID 1 / GOOD-INVALID 3 / BAD-VALID 1 / BAD-INVALID 4）；②T3D-Strict reveal=0（acceptance_log_reveal=0，模型只读到 symptom 日志，9/9 cell 客户端 `strict_denied_403=False` 是因真实模型未在 strict 下请求 f2p/p2p；服务端无泄漏）；③INVALID/AMBIGUOUS=0，指标分子分母不混入；④静态/主动分表（arm=static/active）；⑤工具隔离真实 run 保持（escalate 34 请求/30 granted/7 denied=3 reason-missing+403 路径，reason 门控生效，无侧信道）；⑥gold 前后 sha256 均 `dbebcfc3…`；⑦仅写 phase3 新文件 + 运行时 audit.jsonl/fixtures_meta.json（213 基线中 211 真值/结果文件零改动，meta 仍仅 9 个 fix_ 命名空间）；⑧实销 **$0.203016 ≤ $0.30**，0 error / 0 budget-stop / 121 次守卫前置检查。
  - **Research Outcomes B 组（如实留档，非门槛）**：Decision Appropriateness T3A-T 1.0 / T3D-Strict .667 / T3D-Escalate .667 / T2A-T .667 / T2D-T .556；NEED 率 Strict=1.0（对 contradictory 与 M4 均过度弃权）；Escalate coverage .444 但出现 2 次 unsupported REJECT（incomplete、incomplete_good）；M4 仅 T3A-T 正确 REJECT，其余四条件均误 NEED_EVIDENCE（T2D-T/T3D-Strict/T3D-Escalate/T2A-T）；valid 仅 Escalate/T3A-T ACCEPT，静态与 Strict 全部弃权；部署视角 unsafe_accept=0。总成本 582,560 in / 23,540 out tok，189 工具调用，196.6s。详见 metrics JSON 与用户报告。
  - 未改 gold/夹具/prompt 提分，未中途调整设计；B 组失败模式（M4 误弃权、Escalate 无据拒绝、静态全弃权）按要求原样保留。**Task 9 后停止，Task 10 扩样需再次批准。**


## Task 10: 扩样 4 issue 与正式 Pilot（离线部分已另立 wave2 spec；正式 Pilot 仍 blocked）
- **Status**: `blocked`（离线子任务已拆至 [groundedreview-w2-offline](file:///c:/Users/guoci/work/eeeeiiii/.trae/specs/groundedreview-w2-offline/spec.md)；用户 2026-10-20 仅批准离线构建，正式付费 Pilot ≤$1 待离线报告后再次批准）
- **Priority**: `low`
- **Depends On**: Task 9
- **Blocked By**: 离线扩样（oracle/condition gold、缺口分类、4 新 issue）尚未完成与验收
- **Unblock Condition**: wave2 离线报告通过 + 用户书面批准正式 Pilot（≤$1）
- **Description**:
  - 离线部分（已批准，另立计划执行）：新增 4 个独立 issue、12–16 个夹具（本地构建），区分 oracle_gold/condition_gold、M4 类可见性审计、NEED 缺口 grounding 分类，见 groundedreview-w2-offline spec/tasks。
  - 离线通过且再次授权后：正式双协议 Pilot API ≤$1（issue cluster bootstrap CI）；再之后才考虑跨模型。
- **Acceptance Criteria Addressed**: 无（阶段 3/4 尚未定义 AC，届时另立 spec）
- **Test Requirements**:
  - `rule` TR-10.1: 在前置授权链完成前不得开始；证据：无执行记录。
