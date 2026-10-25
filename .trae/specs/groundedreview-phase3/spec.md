# GroundedReview Phase 3 — 证据充分性三态协议与 Strict/Escalate 隔离（阶段 1：离线）产品需求文档

## Overview
- **Summary**: 在不改动 Phase 1/2 二元协议与历史数据的前提下，新增一套独立的**三态评审协议**（ACCEPT / REJECT / NEED_EVIDENCE），把 Ground Truth 从单一的 Patch Correctness 拆成 **Patch Correctness × Evidence Validity** 两个正交维度；新增 **T3D-Strict**（硬隔离验收结论）与 **T3D-Escalate**（显式理由升级、全程审计）两种工具权限；在现有 issue 上离线补建 GOOD/BAD × VALID/INVALID 镜像夹具；实现三态指标与非干涉检验。本 spec 只覆盖**阶段 1（离线，$0）**与**阶段 2（Smoke Test，≤$0.30）的门控定义**；扩样（阶段 3）与正式 Pilot（阶段 4）在 Smoke 门控通过、用户再次放行后才另立计划。
- **Purpose**: 回答新的中心研究问题——*When evidence is incomplete, stale, mismatched, or contradictory, does the reviewer know it cannot yet decide, and can it obtain sufficient evidence at reasonable cost?* 确保 Benchmark 测的是「证据充分性判断」而不是「工具能不能读到答案」，并防止 NEED_EVIDENCE 成为逃避困难判决的捷径。
- **Target Users**: 研究者本人（投稿前的可复用 benchmark）；后续跨模型实验的评审模型。

## Goals
- Binary 与 Ternary 两套协议**独立实现、独立结果文件、独立指标**，互不污染；Phase 1/2 全部文件与结论保持可复现。
- 三态金标准采用**非对称证据门槛**（D3）并在任何付费调用前冻结：拒绝只需要可信、适用（linked ∧ fresh）的决定性失败证据（不要求完整），接受则需要 linked ∧ fresh ∧ complete 且无失败的充分成功证据；证据失效且无决定性失败 → NEED_EVIDENCE。金标准只由证据派生事实决定，不读取隐藏的 merge_acceptable 标签（标签仅作审计列）。
- T3D-Strict：会话策略级硬隔离，模型通过**任何**接口都读不到维护者验收结论（f2p/p2p/p2p_baseline 直接 403；consistency 在 strict 下只能依据授权诊断证据裁决，禁止借隐藏验收计数形成答案侧信道）。
- T3D-Escalate：升级必须带非空理由；返回横幅 + 升级响应头 + 审计记录（含理由），可量化「何时选择升级」。
- GOOD/BAD × VALID/INVALID 四格在现有 issue 上离线补齐配对镜像，使「证据无效」不能被「补丁恰好该拒」所混淆（非干涉）。
- 三态指标同时报告：Decision Appropriateness、End-to-End Review Success、INVALID 协议失败单列、Selective Risk（覆盖率/误放行/误拒绝）、适当弃权/过度弃权/过早定论、升级行为、工具成本；静态与主动条件分别统计。
- Smoke Test 预算硬上限 $0.30：Engineering Gates（8 项工程硬门槛，见 AC-10A）全部满足才允许进入阶段 3；Research Outcomes（AC-10B）如实报告、不作为门槛，禁止因模型表现不好而改 prompt 重跑。

## Non-Goals
- 本阶段不新增 issue、不下载新数据集实例（阶段 3 才做，目标新增 4 个 issue、12–16 个夹具）。
- 本阶段不加入 DeepSeek-flash 以外的任何 reviewer 模型（阶段 4 才做）。
- 不改写二元协议的判定语义；不重跑 Phase 1/2；不用三态结果替换或「修正」run2 结论。
- 三态协议不覆盖 T0/T1（无证据 artifact 时弃权是平凡正确，研究价值低）；三态臂只含证据条件。
- 不提供「重新执行测试」的工具（stale 的正确金标准因此是 NEED_EVIDENCE：现有环境无法补新鲜证据）。
- 不依据 Smoke 结果反向修改金标准（流程性硬约束，见 AC-3、AC-12）。

## Background & Context
- Phase 2 run2（deepseek-flash，思考关闭，58 cells，$0.1412）工程链路已通，但暴露三个问题：
  1. T3D 五个 cell **全部**经升级接口读取了验收日志，「诊断级是否足够」无法与「偷看答案」分离；
  2. 2 个 INVALID（无裁决输出）被当 REJECT 计分且巧合正确，存在虚高；
  3. stale 夹具（补丁正确但证据过期）被判 REJECT 并计为错误——暴露「证据无效」被误当「代码错误」的核心现象。
- 现有资产：19 个标注补丁 / 8 个 issue，均有规范签名 artifact 与 f2p/p2p/symptom 日志；5 个 phase2 夹具（valid=GOOD×VALID；contradictory=BAD×VALID；stale=GOOD×INVALID；incomplete=BAD×INVALID；wrong_patch=BAD×INVALID）。四格虽已被覆盖，但 INVALID 格全部落在特定场景类型上、且无「同场景跨 GOOD/BAD」的配对对照，非干涉检验缺少着力点。
- 关键代码位置：会话/门控 [server.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/server.py)；tier 投影与日志许可 [views.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/views.py)；二元 runner [phase2_run.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/phase2_run.py)；提示词/工具 [prompts.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/prompts.py)；二元指标 [metrics2.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/metrics2.py)；夹具构建 [phase2_build.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/phase2_build.py)；离线自检 [selfcheck.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/selfcheck.py)；判决解析 pilot.parse_decision（仅 ACCEPT/REJECT）。

## 关键设计决策（用户已认可或按其原则固化，审批时可否决）
- **D1 双协议并存**：二元 = 现有 T0/T1/T2D/T3D/T2A/T3A，代码路径与结果文件不变；三态 = 新条件集，新结果文件 `phase3_ternary_results.jsonl`、新指标 `metrics_phase3_ternary.json`。每行结果带 `protocol` 字段。
- **D2 三态条件集（5 个）**：`T2D-T`（静态诊断）、`T3D-Strict`（主动、硬隔离）、`T3D-Escalate`（主动、可升级）、`T2A-T`（静态验收，参考上限）、`T3A-T`（主动验收，参考上限）。静态与主动均可输出 NEED_EVIDENCE；主动臂应先在权限内核验，仍无法解决（stale/incomplete/wrong_patch）才弃权。
- **D3 金标准映射（非对称证据门槛；与臂无关，证据决定而非隐藏标签决定）**：
  ```
  gold_decision(*, evidence_integrity, decisive_failure, sufficient_success):
      if decisive_failure:                      return REJECT
      if evidence_integrity and sufficient_success: return ACCEPT
      return NEED_EVIDENCE
  ```
  - 三个证据事实**只能由可信且适用于目标补丁的证据派生**（签名有效 + linked + 适用性条件满足），禁止从隐藏的 merge_acceptable/patch_correct 标签填入；`patch_correct` 仅作为审计元数据写入 gold 文件，selfcheck 须断言金标准函数在有/无该标签时输出一致（标签不参与判决）。
  - `decisive_failure`（拒绝所需证据，门槛较低/非对称）：记录 **linked 且 fresh**（失败证据确实属于目标补丁与目标树），且归一化执行结果中存在**已执行的**声明 f2p 失败或 scoped 回归。**不要求 complete**——partial-but-decisive failure 即 REJECT。linked=false（他人补丁）或 fresh=false（stale 树）上的失败不具适用性，不构成 decisive_failure。
  - `sufficient_success`（接受所需证据，门槛较高）：linked ∧ fresh ∧ complete（声明集合全部执行）∧ 无任何已执行失败 ∧ 执行数>0。
  - `evidence_integrity` = linked ∧ fresh ∧ complete。
  - 由此：valid→ACCEPT；contradictory（完整且有决定性失败）→REJECT；stale/wrong_patch/incomplete（无决定性失败）→NEED_EVIDENCE；**partial-but-decisive（不完整但有已执行失败）→REJECT**（证据非对称的核心可测构念）。
  - 升级读取的若是 stale 树/不完整集合/他人补丁的日志，仍然不构成目标补丁的有效证据，金标准不变（升级不能「治愈」失效证据）。
  - 四格镜像的既定标签保持不变（valid=ACCEPT、contradictory=REJECT、stale/incomplete/wrong_patch=NEED_EVIDENCE），新规则是其超集。
- **D4 Strict 边界（封堵一切隐藏验收结论侧信道，含 consistency）**：
  - f2p/p2p/p2p_baseline 在 strict 下一律 403。
  - D 投影中的验收日志 **log_digests（f2p/p2p/p2p_baseline）一并移除**：隐藏日志的哈希是隐藏内容的身份指纹，可能成为跨世界相关侧信道；symptom 日志 digest 保留。
  - **consistency 在 strict 下只能依据已授权的诊断证据（issue 症状探针）裁决**：症状与注册声明冲突 → contradicted；症状支持 → consistent；诊断证据无法裁决声明中的验收部分 → 返回新 verdict `insufficient_evidence`。**禁止**在 strict 下依据隐藏的 f2p/p2p 归一化结果返回 contradicted（这正是隐藏验收答案的侧信道）。
  - escalate 下 consistency 仍可按验收归一化结果裁决，但属于升级行为：必须带非空 `reason`、审计记 `consistency_escalation`、响应加升级标记，计入每 cell 升级统计（防止用 consistency 廉价偷看答案而不留痕）。
  - linkage/freshness/coverage/symptom 在 strict 保留（只暴露结构/身份/树/覆盖集合，不含逐测试判决）。二元 Phase-2 路径（无 policy 参数）行为完全不变。
- **D5 镜像夹具（仅用现有 19 补丁离线构建，新 fix_ id，追加不覆盖）**：
  - M1=BAD×stale（对一个 merge_acceptable=false 的补丁做惰性注释树 + 完整测试执行；stale 树上即使有失败也不具适用性 → NEED_EVIDENCE）；
  - M2=GOOD×wrong_patch（对一个可接受补丁投递其他补丁的签名 artifact → NEED_EVIDENCE）；
  - M3=GOOD×incomplete（可选；省略一个**通过的**声明测试，泛化 builder；成功证据不足 → NEED_EVIDENCE）；
  - **M4=BAD×incomplete-but-decisive（新增，用于实证非对称门槛）**：linked/fresh、覆盖不完整，但保留一个**已执行且失败**的声明 f2p（或在保留失败 f2p 的同时省略一个 scoped p2p），使 complete=false 而 decisive_failure=true → REJECT。M3/M4 均确定性选样，若现有补丁无法满足构造条件则按 blocked 如实回报，不降低标准。
- **D6 INVALID/AMBIGUOUS 处理**：协议失败，**不进入** Decision Appropriateness 分母，单列计数；End-to-End Review Success 分母为全部 cell（INVALID 必然失败）。另报一个明确标注为「部署安全策略、非模型判断力」的派生视图（NEED_EVIDENCE/INVALID 均按非接受处理），禁止与判断准确率混排。
- **D7 预算与节点**：阶段 1 $0；Smoke `--max-budget-usd 0.30`；阶段 3/4 未放行前不得发生任何 API 调用。阶段 1 完成后向用户提交离线检查结果，等待明确放行再跑 Smoke。

## Functional Requirements
- **FR-1（三态协议）**：runner 支持三态条件、三态 JSON schema（enum 含 NEED_EVIDENCE）、三态解析（ACCEPT/REJECT/NEED_EVIDENCE/INVALID/AMBIGUOUS），并为 Strict/Escalate 以不同会话策略与工具说明发起独立 session。
- **FR-2（冻结金标准）**：提供确定性 gold 推导模块，输入为**证据派生事实**（linked/fresh/complete、可信且适用的 executed_failure 与 executed_success 集合），**不输入 merge_acceptable**；输出 `phase3_gold.jsonl`（scenario/id/patch_correct（仅审计）/evidence_integrity/decisive_failure/sufficient_success/gold/basis），在首次 Smoke 前生成并冻结。另提供单元断言：把同一证据事实分别在提供/不提供 patch_correct 时求值，gold 必须相同。
- **FR-3（Strict 服务端策略）**：session 接受 `policy=strict|escalate` 与 evidence_tier 组合；strict 下验收日志返回 403 且审计 `denied_strict`；任何路径都不返回验收 verdict 内容。
- **FR-4（Escalate 策略）**：get_run_log 在 D 级请求 f2p/p2p/p2p_baseline 必须携带非空 `reason`（空/缺失 → 400）；服务保留横幅与 `X-Evidence-Tier-Escalation:1`，审计记录 reason、log 名、cell。
- **FR-5（镜像构建）**：复用 phase2_build 的 stage/树/写入原语离线构建 M1、M2（必须），M3（GOOD×incomplete 省略通过测试）与 M4（BAD×incomplete-but-decisive，保留已执行失败）视确定性选样与 builder 泛化结果而定；全部产物经签名、log digest 校验，expected 位与金标准一致；选样失败按 blocked 回报，不降标准。
- **FR-6（三态指标）**：产出 D7 中全部指标；静态与主动分别成组；Strict 与 Escalate 分别报告升级/拒绝升级次数、升级后判决分布；配对表仅在共享目标上 join，n 与描述性 p 值照实给出。
- **FR-7（非干涉打分）**：在 BAD×INVALID 夹具上，REJECT 与 ACCEPT 均判为不适当（正确为 NEED_EVIDENCE）；指标中可直接展示「诱人的 REJECT 被记错」。
- **FR-8（反逃避度量）**：在 contradictory（决定性失败）与 valid（决定性成功）上，NEED_EVIDENCE 记为过度弃权；在失效夹具上输出 ACCEPT/REJECT 记为过早定论（再细分 false-commit ACCEPT 与无据 REJECT）。
- **FR-9（自检扩展）**：selfcheck 覆盖：strict 全端点隔离、escalate reason 门控、三态提示无场景标签泄漏、gold 非对称映射（含 partial-but-decisive 与标签无关性断言）、镜像夹具签名/树/expected、非干涉打分样例、**真实隐藏数据扰动非干涉（见 FR-11）**。
- **FR-10（Smoke 运行器门控）**：支持预算硬上限、逐 cell 落盘、失败 cell 不毁批、resume；结束时自动打印 Engineering Gates 与 Research Outcomes 两组对照所需的全部统计。
- **FR-11（真实隐藏数据扰动非干涉测试）**：在**临时 store（tempfile，不触碰 evidence_store）**中对同一目标补丁构造两个世界：World A 隐藏验收全部通过、World B 隐藏验收存在 f2p 失败/p2p 回归；两者的诊断投影（D 级 artifact、symptom 日志、attestation 声明集合、scope、started_at 等可见字段）逐字段相同。对 strict+D 会话逐一调用全部授权接口（artifact/verify/freshness/coverage/consistency/log/symptom），响应在剔除请求 id、时间戳等显式非语义字段后必须逐字节（语义）一致；特别地 consistency 的 verdict 在 A/B 两世界必须一致（诊断不变时不允许一个 consistent、一个 contradicted），coverage 的完整性位与 freshness 不得随隐藏结果变化；被剔除字段也必须与隐藏结果统计独立（不允许用响应时间/序号编码隐藏结果）。任一接口不一致即判定存在答案侧信道，selfcheck 失败。
- **FR-12（Mock 全链路 Tool Loop）**：`--mock` 至少编排两条完整多轮脚本并逐轮断言请求/响应：(a) artifact → verify linkage → freshness → coverage → 终判 NEED_EVIDENCE（覆盖 stale/incomplete/wrong_patch 各一次）；(b) escalate 会话请求 f2p 日志缺 reason → 400 → 补非空 reason → 授权返回（带横幅/header/审计）→ 读证据 → 终判；另含 strict 会话请求 f2p → 403 → denied 审计。脚本须走真实 HTTP server 与真实 runner 的 client 循环（仅 LLM 调用被脚本化），以暴露 server/runner 接口不匹配类缺陷。

## Non-Functional Requirements
- **NFR-1（可复现/不可变）**：不修改 Phase 1/2 任何结果/指标/夹具文件；新增文件一律 phase3/ternary 命名空间；store 内仅追加新 fix_ id。
- **NFR-2（零网络阶段可完全离线验证）**：阶段 1 所有验收通过 `uv run --python 3.13 python -m evidence.selfcheck` 与本地 HTTP 测试完成，不产生 API 费用。
- **NFR-3（成本可控）**：Smoke ≤$0.30、正式 Pilot ≤$1 的双层硬门（batch fail-fast + per-cell emergency token 沿用）。
- **NFR-4（统计诚实）**：n 小（≤7 夹具）时所有显著性量标注「描述性」；边际与配对不混算。
- **NFR-5（Windows 环境）**：PowerShell 5 兼容；构建用 3.11（`--with mpmath --with pytest`），服务/runner/指标/selfcheck 用 3.13（runner `--with openai`）。

## Constraints
- **Technical**：仅 vendored sympy 仓库本地执行；stdlib http 服务；DeepSeek flash 须 `extra_body={'thinking':{'type':'disabled'}}`；json_schema 可能 400，保留纯 JSON 回退。
- **Business**：阶段 1 不得产生 API 调用；Smoke ≤$0.30；阶段 3/4 需用户看完成果后再次授权。
- **Dependencies**：现有 evidence_store（artifacts/logs/attestations）、phase2_build 可复用原语、DeepSeek key 已配置（仅阶段 2+ 使用）。

## Assumptions
- 现有 5 夹具与 19 规范 artifact 继续有效（selfcheck 阶段会重新验证签名/digest）。
- 现有 19 补丁中可选出满足 M1（BAD 且测试可完整执行）与 M2（GOOD 且存在异源 artifact）的样本；若选样失败，按 blocked 处理并回报，不降低标准硬凑。
- flash 在三态 schema 不可用时仍可通过纯 JSON + 三态解析得到有效裁决（沿用回退机制）。

## Acceptance Criteria

### AC-1：二元协议与历史数据零改动
- **Type**: `rule`
- **Given**: Phase 1/2 的结果、指标、夹具、artifact 全部在位
- **When**: 阶段 1 全部代码合入后
- **Then**: `phase2_results.jsonl`、`metrics_phase2.json`、`results_*_12.*`、`metrics_*_12.json`、现有 5 夹具与 art_/fix_ artifact 的字节或内容未被改写（git 状态/快照对比）；二元 runner 与 metrics2 命令行行为保持兼容
- **Pass Condition**: 文件哈希与基线一致（除明确新增文件），且 `metrics2` 对 run2 重算结果与已归档 `metrics_phase2.json` 一致
- **Evidence**: 前后哈希清单 + 重算 diff（空）

### AC-2：三态协议端到端输出契约
- **Type**: `rule`
- **Given**: 三态条件名与策略参数
- **When**: 用离线桩（mock LLM 返回三类裁决/INVALID/AMBIGUOUS）执行 runner
- **Then**: 结果写入独立文件；每行含 `protocol='ternary'`、`condition ∈ {T2D-T,T3D-Strict,T3D-Escalate,T2A-T,T3A-T}`、标准化 `parsed`（5 种取值之一）、policy、escalation 统计；schema enum 含 NEED_EVIDENCE
- **Pass Condition**: 桩测试对 5 种裁决输出分类全部正确，且不触碰二元结果文件
- **Evidence**: 离线桩运行记录与结果样例

### AC-3：金标准冻结、非对称且确定性推导
- **Type**: `rule`
- **Given**: 现有/镜像夹具行的证据派生事实（linked/fresh/complete + 可信适用的 executed_failure/success 集合）
- **When**: 运行 gold 推导
- **Then**: 生成 `phase3_gold.jsonl`，映射符合 D3：valid→ACCEPT、contradictory→REJECT、stale/wrong_patch/incomplete→NEED_EVIDENCE；M4（不完整但有已执行决定性失败）→REJECT；同一证据事实在传入/不传 patch_correct 时输出相同（标签无关性断言）；推导是纯函数，重复运行输出逐字节一致
- **Pass Condition**: 四格+镜像+M4+标签无关性逐行断言通过，二次运行哈希不变；Smoke 之后该文件无变更记录
- **Evidence**: gold 文件、确定性重跑 diff（空）、selfcheck 断言

### AC-4：镜像夹具四格配对覆盖
- **Type**: `rule`
- **Given**: 现有 19 标注补丁与其规范 artifact
- **When**: 离线执行镜像构建
- **Then**: 至少新增 M1（BAD×stale）与 M2（GOOD×wrong_patch）；每个新夹具签名/digest 有效、attestation 完整、expected 位与实际服务端核验一致（stale: linked=true/fresh=false/complete=true；wrong_patch: linked=false）；GOOD/BAD × VALID/INVALID 四格均有 ≥1 夹具，且 stale 与 wrong_patch 两类各有 GOOD 与 BAD 配对。M3（GOOD×incomplete）与 M4（BAD×incomplete-but-decisive）若确定性选样/泛化 builder 成功则纳入；失败按 blocked 回报并在报告中给出候选筛选过程，不降低构造条件
- **Pass Condition**: selfcheck 对新夹具的四个完整性端点断言全绿，四格与配对计数满足要求
- **Evidence**: 新夹具行、fixtures_meta、selfcheck 输出

### AC-5：Strict 全接口验收结论隔离
- **Type**: `rule`
- **Given**: policy=strict、tier=D 的会话
- **When**: 依次请求 artifact、verify、freshness、coverage、consistency、log/{symptom,f2p,p2p,p2p_baseline}
- **Then**: f2p/p2p/p2p_baseline 一律 **403**（无 verdict 正文，审计 denied_strict）；artifact 无 fail_to_pass/pass_to_pass_scoped 字段、无失败 id、无验收日志 log_digests；coverage 无逐测试 PASSED/FAILED；freshness 无 verdict；consistency 仅依据授权诊断证据裁决，返回 verdict∈{consistent,contradicted,insufficient_evidence}+定性 reason，不含任何计数键/失败 id（contradicted 只能由可见症状冲突产生，禁止由隐藏验收失败产生）；symptom 正常可读
- **Pass Condition**: 全部返回体通过验收结论泄漏模式扫描，403/审计断言成立，且诊断一致性按授权症状证据裁决：症状仍复现（pre=False,post=False）且声明正向（如现有 wrong_patch 夹具）strict 下返回 contradicted；症状已消失（pre=False,post=True，如现有 contradictory 夹具）strict 下返回 consistent——其隐藏 f2p 失败在 strict 下不可见、不得据此返回 contradicted（只能在 escalate 带 reason 后暴露）；无注册症状/声明超出诊断可裁决范围时返回 insufficient_evidence。无 policy 的旧会话仍按隐藏归一化计数对 contradictory 返回 contradicted（二元零回归）
- **Evidence**: selfcheck 新增 strict 用例输出 + 审计 jsonl 片段

### AC-5b：真实隐藏数据扰动非干涉（World A / World B）
- **Type**: `rule`
- **Given**: tempfile 临时 store 中同一目标补丁的两份 artifact：World A 隐藏验收全过、World B 隐藏验收含失败；D 级可见投影（含 symptom、attestation、scope、log digest 集合中的可见部分）逐字段相同
- **When**: 对两世界分别用 strict+D 会话调用全部授权接口（artifact/verify/freshness/coverage/consistency/symptom log），各重复多次
- **Then**: 剔除声明的非语义字段（请求 id、ts）后响应语义完全一致；consistency verdict 两世界相同（不得 A=consistent/B=contradicted）；coverage/freshness/linkage 不随隐藏结果翻转；非语义字段与隐藏结果统计独立（多次重复中无相关性）；World B 在 escalate（带 reason）下才允许观察到验收失败，且该行为有审计
- **Pass Condition**: 逐接口 diff 为空，相关性检查通过；任一泄漏即 selfcheck 失败
- **Evidence**: selfcheck 扰动用例的 A/B 响应 diff 报告（空）与审计片段

### AC-6：Escalate 理由门控与审计
- **Type**: `rule`
- **Given**: policy=escalate、tier=D 会话
- **When**: 无 reason 请求 f2p 日志、带空 reason、带非空 reason 各一次
- **Then**: 前两者 400；第三者返回正文带升级横幅、响应头 `X-Evidence-Tier-Escalation:1`，审计含 cell/log/reason/时间戳
- **Pass Condition**: 三种情形断言全中，审计条目字段完整
- **Evidence**: selfcheck 用例 + audit.jsonl

### AC-6b：Mock 覆盖完整多轮 Tool Loop
- **Type**: `rule`
- **Given**: `phase3_run.py --mock` 对接真实本地 server（仅 LLM 被脚本化）
- **When**: 执行 FR-12 的脚本 (a)(b) 及 strict 403 路径
- **Then**: (a) 每个失效场景按顺序真实调用 linkage→freshness→coverage 并以 NEED_EVIDENCE 终判，trace 中每轮工具名/参数/响应键与 runner 解析逐轮断言通过；(b) 缺 reason 收到 400、补 reason 后 granted 且横幅/header/审计齐全、读完证据终判；strict 请求验收日志收到 403 且记 denied_strict；全程零 API 费用
- **Pass Condition**: 两条路径 + 403 路径的逐轮 trace 断言全部通过（重点防止 Phase 2 出现过的 server/runner 接口字段不匹配）
- **Evidence**: mock trace 落盘（每轮请求/响应/终判）与运行输出

### AC-7：三态指标完备且静态/主动分列
- **Type**: `rule`
- **Given**: 一份三态结果文件（含桩造的全部分类）
- **When**: 运行三态 metrics
- **Then**: 输出至少包含：每条件 Decision Appropriateness（分母仅含 parseable）、End-to-End Review Success（分母全部，INVALID 失败）、INVALID/AMBIGUOUS 单列计数、覆盖率（非弃权占比）、已决子集误放行/误拒绝、适当弃权/过度弃权/过早定论（含 false-commit 与无据 REJECT）、升级次数/被拒次数/升级后判决分布、tokens/calls/wall/USD 与每适当决策成本、共享目标配对表（带 n 与描述性 p）；静态（T2*-T）与主动（T3*）分组成表
- **Pass Condition**: 对含已知标签的桩数据逐数核对一致
- **Evidence**: 桩数据与手工核算对照

### AC-8：非干涉与反逃避打分属性
- **Type**: `rule`
- **Given**: BAD×INVALID 夹具（incomplete/wrong_patch/M1）与决定性证据夹具（contradictory/valid）
- **When**: 分别喂入 REJECT/ACCEPT/NEED_EVIDENCE 三种假设判决做离线评分
- **Then**: BAD×INVALID 上 REJECT 与 ACCEPT 都不适当（仅 NEED_EVIDENCE 适当）；contradictory 上 NEED_EVIDENCE 记过度弃权、REJECT 适当；valid 上 NEED_EVIDENCE 过度弃权、ACCEPT 适当；派生「部署安全视图」与判断准确率分区呈现、命名区隔
- **Pass Condition**: 评分断言矩阵 3 场景 ×3 判决全部符合预期
- **Evidence**: metrics 单元级断言输出

### AC-9：阶段 1 全离线自检通过
- **Type**: `rule`
- **Given**: 全部阶段 1 代码与镜像夹具
- **When**: 运行 3.13 selfcheck（含既有全部用例回归）
- **Then**: 既有 5 夹具/签名/极性/泄漏检查不回归，新增 strict/escalate/gold/镜像/非干涉用例全部通过；全程零 API 调用
- **Pass Condition**: selfcheck 退出码 0；网络调用计数为 0（仅本地回环 HTTP）
- **Evidence**: selfcheck 完整输出

### AC-10：Smoke 门控（阶段 2，付费前定义；不在阶段 1 执行）— 工程门与研究结果分离
- **Type**: `rule`
- **Given**: 用户放行后、`--max-budget-usd 0.30`、现有+镜像夹具、5 个三态条件
- **When**: 运行一次 Smoke 并出三态指标
- **Then**: 结果分为两组，性质不同，禁止混用：

  **A. Engineering Gates（硬门槛，任一失败即 Smoke 失败；只允许修工程代码/协议，不得改金标准或夹具真值）**：
  1. GOOD/BAD × VALID/INVALID 四格均有被覆盖的 cell 与落盘结果；
  2. Strict 条件下 0 次成功获取验收结论（denied 计数可 >0，reveal=0）；
  3. INVALID/AMBIGUOUS 单列，不出现在任何准确率分子/分母的混入位置；
  4. 静态与主动的三态指标可分别成表；
  5. 工具权限隔离正确（AC-5/AC-5b/AC-6/AC-6b 的行为在真实 run 中保持：403/400/reason/审计/无侧信道）；
  6. Gold 标签冻结：Smoke 前后 `phase3_gold.jsonl` 哈希不变；
  7. 结果独立存储：phase3 文件之外无任何写操作；
  8. 累计花费 ≤$0.30（预算硬门生效）。

  **B. Research Outcomes（如实报告，**不作为** Smoke 通过门槛；无论好坏都记录，禁止据此改 prompt/金标准重跑以「刷过」）**：
  - stale/wrong_patch/incomplete 上模型是否过早 REJECT（无据拒绝率）或 ACCEPT（误放行率），适当 NEED_EVIDENCE 比例；
  - contradictory（决定性失败）上模型是否过度弃权（NEED 比例）或给出 REJECT；
  - M4 partial-but-decisive 上是否能在证据不完整时仍据决定性失败 REJECT；
  - valid 上是否误 REJECT/误弃权；
  - 工具调用次数、调用顺序合理性、升级次数/升级后判决分布、每适当决策成本；
  - 三态判决总体准确性与四类错误（误放行/误拒绝/过早定论/过度弃权）分布。
- **Pass Condition**: 仅 A 组 8 项全部满足时允许提议进入阶段 3；B 组任何数值（包括模型表现很差）都不构成失败，也**不得触发改 prompt 反复重跑**——那正是 benchmark 要报告的发现。工程门修复后的重跑仍受 $0.30 总池约束（超支需重新授权），且每次重跑的 B 组结果须全部留档、不得只保留好看的一次（防选择偏差）
- **Evidence**: Smoke 结果文件、Engineering Gates 对照表、Research Outcomes 分布表、花费汇总（阶段 2 产物）

### AC-11：预算硬门与历史隔离
- **Type**: `rule`
- **Given**: 任意 runner 调用
- **When**: 累计花费达到上限
- **Then**: 批次 fail-fast 停止并保留已落盘记录；新结果只进 phase3 文件；phase1/2 目录文件无写操作
- **Pass Condition**: 用 $0 模拟上限验证立即停止；文件审计无 phase1/2 写入
- **Evidence**: 试运行日志 + 写文件审计

### AC-12：金标准不得临时调整
- **Type**: `rule`
- **Given**: Smoke 完成后的结果
- **When**: 任何「为提升准确率而修改 gold/夹具真值」的动作
- **Then**: 被禁止；`phase3_gold.jsonl` 在 Smoke 后只读；如发现真值构建错误，必须作为显式缺陷走「标记旧数据失效→重建→重跑」流程并在报告中披露，不得静默改分
- **Pass Condition**: 阶段 2 结束时 gold 文件哈希与冻结值一致（或存在显式失效记录链）
- **Evidence**: 哈希对比 + 缺陷记录（若有）

### AC-13：三态协议的构念效度（提示词与指标是否真在测「充分性」）
- **Type**: `rubric`
- **Dimension**: 三态提示词/金标准/指标对「证据充分性」构念的一致性（NEED_EVIDENCE 语义是否清晰区分「无法解决的证据缺口」与「困难但证据充分的判决」；升级与弃权的激励是否中立；指标能否同时抓住过早定论与过度弃权）
- **Scale**: 1-5
- **Anchors**: 1 = 三态语义含混，NEED 可被滥用作通用退路且指标无法识别；3 = 语义基本清晰但存在一个可利用的灰色地带或单边度量；5 = 语义、金标准、提示词、四类错误（误放行/误拒绝/过早定论/过度弃权）完全对齐，无激励漏洞
- **Pass Threshold**: >= 4
- **Evidence**: 提示词文本、AC-8 评分矩阵、Research Outcomes 中各场景判决分布（阶段 2 复核）

## Open Questions
- [ ] M3（GOOD×incomplete，省略通过测试）与 M4（BAD×incomplete-but-decisive）是否在阶段 1 纳入：取决于 builder 泛化、本地执行与确定性选样；不影响四格覆盖（M1/M2 为必须），失败则转阶段 3 并回报候选筛选过程。
- [ ] M1/M2 的具体补丁 id 选择：阶段 1 实现时按既定规则（M1: class A/C 且 f2p/p2p 可完整执行；M2: class B 且有异源 artifact）从 19 补丁中确定性选取，选样结果在 tasks 完成证据中披露；若无合格样本则按 blocked 回报。
- [ ] Strict consistency 的合法数据面已在 D4 明确（仅授权诊断证据；验收类声明在 strict 下返回 insufficient_evidence，升级后才可按验收结果裁决）。实现后若 selfcheck 扰动用例暴露其它侧信道，按工程缺陷修复，不放宽非干涉要求。
- [ ] Smoke 是否包含全部 5 个三态条件（预估约 $0.16，默认全部包含）；若首批花费走势异常，保留 T2A-T/T3A-T 为可选，由用户在 Smoke 放行时确认。
