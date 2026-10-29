# G3-A · 三层离线证据材料与 Derived-Summary 披露（Task 8）

每个 issue 的材料位于
[layers/&lt;issue&gt;/](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/layers)，
三层来自**相同的底层执行事实**（同一次 base+candidate+maintainer test_patch
的真实 pytest 重放），只是加工程度不同。

## 1. 三层定义

| 层 | 目录 | 内容 | 是否含派生判断 |
|---|---|---|---|
| **Raw** | `raw/` | 用户 `problem_statement.txt`、`candidate.patch`、`maintainer_test.patch`，以及四个逐字日志 `f2p.log` / `p2p.log` / `p2p_baseline.log` / `symptom.log` | **否**。逐字材料，无解析后的判决表、无标签。 |
| **Structured** | `structured/run_record.json` | HMAC 签名运行记录的确定性**解析**结果（逐测试 F2P/P2P/baseline 状态图、summary）+ 签名 git write-tree attestation（声明集合） | **是，派生**：逐测试状态由 `evidence.builder.parse_node_logs/name_outmes` 从原始 pytest `-v` 日志**机械解析**，不引入任何新的执行事实；provenance/runner 元数据逐字回显。 |
| **Adjudicated** | `adjudicated/` | 冻结的 `gold.json`（oracle/condition_gold + 事实依据）与 `sufficiency_certificate.json`（最小 forcing 通道、证据状态、人工仲裁 pending） | **是，结论层**：模型**永不可见**（leakage 已审计，raw+structured 0 命中）。 |

## 2. Derived-Summary 披露（强制）

- Structured 层的 per-test maps / summary 是对 Raw 日志的**本地确定性派生
  分类**，由构建器在本机执行后解析生成；它们**不是**外部 CI 系统的产物。
  材料中不得、也没有出现"UPSTREAM CI RUNNER"之类把本地派生伪装成上游
  权威 CI 的措辞；runner 字段如实写作
  `pytest/vendored-git py=... host=windows-local`。
- attestation 的 run_tree 是在本机对精确三元组 `git write-tree` 捕获，
  签名（HMAC）保证记录自构建后未被篡改；它证明"记录与所执行树绑定"，
  **不**声称该运行来自 GitHub Actions 或人类合并门禁。
- 数据集的 `resolved` 字段是 SWE-bench harness 真值，**不是人类合并决定**；
  它仅出现在 adjudicated/审计文件，不进入 raw/structured 模型面。

## 3. 同底事实保证

- 三层共享同一 `artifact_id`、同一组 `log_digests`。审计
  [g3a_leakage_token_audit.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/audit/g3a_leakage_token_audit.json)
  逐 issue 校验：四个 raw 日志的 sha256 与签名记录 `log_digests` **10/10
  一致**，证明三层未使用彼此矛盾的运行结果。
- 溯源（repo / base_commit / 两个 patch sha / 测试命令 / 环境 / run_tree /
  F2P / scoped-P2P 数）集中登记在
  [g3a_provenance_manifest.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/g3a_provenance_manifest.json)。

## 4. 覆盖范围口径（随证据披露）

P2P 是**作用域子集**（维护者 test_patch 文件 + 每个改动代码文件相邻
tests/ 包内可映射的测试），并非数据集声明的完整 P2P 套件。因此
structured/adjudicated 的"全绿/complete"是**作用域内完整**；oracle
ACCEPT = 作用域可接受 + 症状消除，不外推为全仓库回归通过。
