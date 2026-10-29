# G3-A · 预冻结的 Issue 纳入 / 排除标准（Selection Protocol）

- 状态：**FROZEN 2026-10-26**，在任何 G3-A 模型预测之前冻结。
- 执行代码：[g3a_select.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/g3a_select.py)
  （纯机械、确定性）；输出
  [g3a_selection.json](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/selection/g3a_selection.json)。
- 数据总体：本地全量离线缓存的 HuggingFace `Lego-X/SWE-Review-Bench`
  SymPy 分片（206 行 / 75 个不同 issue），构建/测试证据来自本机 vendored
  sympy 仓库的**真实 pytest 重放**，无任何外部付费服务。

## 1. 与选样相关的禁止事项（先于标准声明）

1. **不依据任何模型的历史评审错误选样。** 既不参考 E1/CEE/EAL/R1/X 的
   判决、矛盾断言或 per-issue 错误率，也不在看到新 issue 的模型输出后回调
   样本。是否入选只由下列可机械验证的仓库/测试规格事实决定。
2. **不与旧 10 个冻结 issue 重复**，也不与已有 canonical 执行的
   16597、20428 重复；**不用镜像 fixture 充数**。主队列每个 issue 只取
   **一个** target patch，不共享 base/patch/artifact。
3. **不强制三态标签平衡**，不通过人为制造证据缺陷来凑 ACCEPT/REJECT/
   NEED_EVIDENCE。最终标签分布是选样与真实执行的自然结果，如实报告。
4. 选样种子 `G3A_SELECT_SEED = 20261026A` 在看结果前固定；合格 id 排序后
   一次洗牌取前 10，杜绝逐 issue 人工挑拣。

## 2. 纳入门（全部为 AND，全部可离线机械判定）

| 门 | 判定（在 base_commit 与缓存数据上） |
|---|---|
| G1 新颖性 | instance_id 不属于 12 个历史 issue（10 个 v21 issue + 16597 + 20428）。 |
| G2 base 可取 | `base_commit` 对象存在于 vendored 离线 git 仓库（`GIT_NO_LAZY_FETCH=1` 下可 checkout）。 |
| G3 维护者测试规格可用 | 维护者 `test_patch` 在 base 干净 apply；每个声明的 FAIL_TO_PASS 测试名都定义在某个 test_patch 文件中；声明的 F2P 与 P2P 集合均非空。 |
| G4 ≥1 个可评审 target | 至少 1 个生成器 `model_patch` 在 base 干净 apply。target 生成器按**确定性**次序选定：先 `resolved==True`，再固定生成器优先级（GLM-5-FP8 → Qwen3-Coder-30B → Qwen3-30B-2507），再按最小 row id。选 target 不看评审内容。 |
| G5 全离线可建 | 排除已知 base tree blob 不全、需联网才能 checkout 的 sympy-11618；离线 checkout 在构建时再次复核（若失败则该 issue 记为构建期排除并按洗牌顺序递补）。 |

G3 复用冻结的 `wave2_selection_audit.json` 中已测量的静态门结果（该审计在
任何 G3-A 工作之前生成），不重新主观判断。

## 3. 排除去向（可复核）

- 12 个历史 issue → `previously_used`；sympy-11618 →
  `offline_blob_incomplete`；静态测试规格门不过 →
  `static_test_spec_gate_failed`；无干净 target patch →
  `no_clean_target_patch`。逐条 reason 写入 g3a_selection.json 的
  `excluded`，合格总体 61 个（门控后），全部 id 留档以便审计选样空间。

## 4. 选定结果（种子洗牌后前 10，按 id 排序）

sympy-13615、13974、15349、17318、17630、19783、20590、21847、24213、
24443。数据集 harness `resolved` 自然分布为 7 resolved / 3 unresolved
（17318、17630、19783），**未做任何平衡**。注意：`resolved` 是 SWE-bench
harness 真值，不是人类合并决定，也不等于本研究的 oracle_gold。

## 5. 金标签与选样的时序隔离

- Gold（oracle_gold / condition_gold）只在 target patch 真实执行完成后、
  由 [g3a_gold.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/g3a_gold.py)
  从签名记录与 attestation **机械复算**，且在任何模型预测之前冻结。
- 人工仲裁：当前无第二位独立标注者，所有 issue 的人对人一致性状态登记为
  `pending`；机械 oracle 的内部一致性单独报告，**不冒充独立人工一致性**。
