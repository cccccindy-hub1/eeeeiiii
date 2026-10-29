# G3-A · 人工 Gold 仲裁程序与当前状态（Task 7）

## 1. 程序要求（预冻结）

- 每个 issue 的 gold 须有**至少两名相互独立的标注者**独立判定，再对分歧
  仲裁；记录逐标注者标签、一致/分歧、κ（若可行）与仲裁依据。
- 独立性要求：第二名标注者不得看过第一位标注者的标签，也不得看过任何
  模型预测或自动 oracle 输出后再"独立"标注。
- **自动规则（oracle 双通道函数）的自我一致性不是人工一致性**，严禁把
  机械复算、脚本自检或同一人两轮编码报告成"两位独立审稿人一致"。
- 若当前没有第二位标注者，该 issue 的人工一致状态**只能登记为
  `pending`**，不得回填、不得用规则一致性替代。

## 2. G3-A 当前实际状态（如实登记）

| 项 | 值 |
|---|---|
| 可投入的独立人工标注者数 | **1** |
| 第二位独立标注者 | **无** |
| 10 个 issue 的人工人对人一致状态 | **全部 `pending`** |
| 机械 oracle 复算 | 已做，且 git write-tree fresh 独立复核 10/10 一致——仅作为**内部机械一致性检查**报告 |

该 pending 状态已逐 issue 写入
[g3a_gold.jsonl](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/gold/g3a_gold.jsonl)
的 `human_adjudication` 字段与每个 Sufficiency Certificate。

## 3. 当前可用的是"可复现的机械真值"，不是"人工共识真值"

G3-A 的 gold 来自确定性、可复现、可审计的执行事实（真实 pytest F2P/P2P +
baseline-fail/post-pass 的人工手写 symptom probe + 签名/attestation）。其
优点是零主观漂移、任何人可重跑核对；局限是**尚未经第二人独立人审**。
因此：

- 在取得第二位独立标注者之前，论文/报告只能称这些标签为
  **mechanically adjudicated, human-agreement pending**；
- 不得声称 inter-rater reliability、κ 或"两名审稿人一致"；
- G3-B 的模型判决可与机械 gold 比较，但讨论 gold 本身的人效时须带此限定。

## 4. 解除 pending 的前置条件（进入 G3-B/G3-C 前建议完成）

1. 招募第二位标注者，仅提供：问题报告、候选 patch、维护者 test_patch、
   四层原始日志与渲染证据（**不提供** oracle 标签/脚本结论/模型输出）。
2. 两位标注者独立给出三态（ACCEPT/REJECT/NEED_EVIDENCE）与理由。
3. 计算一致性（原始一致率 + κ），分歧由第三人或协商仲裁，全程留痕。
4. 比较人工共识标签与机械 oracle：一致则增强 gold 可信度；系统性分歧则
   修订规则/探针并重新冻结，记录修订历史。
5. 第二位标注者到位前，G3-A 保持 `pending`；G3-B 是否在 pending 下启动，
   由 Gate 3-B 书面审批明确决定。
