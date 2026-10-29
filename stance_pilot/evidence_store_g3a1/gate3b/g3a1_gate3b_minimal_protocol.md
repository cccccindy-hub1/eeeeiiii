# Gate 3-B · 最小外部验证协议（A.1 冻结版，审批前不执行）

> 版本：g3a1-gate3b-minimal-protocol-v1。本协议在**零 API、零模型结果**下
> 冻结，供 Gate 3-B 书面审批。它**收窄并取代** G3-A 版预注册计划中与本批
> 实测 gold 分布相关的执行口径（旧文件保留不改，作为历史）。真实模型调用、
> 扩样、Gemini、新 Prompt 实验**均未获批准**。

## 1. 定位（必须按此措辞）

本实验是 **External Feasibility Pilot（外部可行性先导）**，不是泛化验证。
理由：独立单元只有 10 个 issue，且全证据 REJECT 仅 3 个——任一 REJECT issue
预测翻转都会使观察到的 REJECT 错误率移动约 33 个百分点。所有结论按精确
计数 + 宽置信区间报告，不做总体患病率外推。

## 2. 两条预先指定的外部效度问题（论文核心）

- **Q-A（GPT-4.1-mini 的错误接受是否在新独立 issue 复现）**：在充分证据面
  上，对全证据 gold=REJECT 的 issue，模型是否仍判 ACCEPT（unsupported
  acceptance, UA）？
- **Q-D（DeepSeek 的过度弃权是否在充分证据下仍发生）**：在证据完整、
  gold=ACCEPT/REJECT 可判的充分证据面上，模型是否仍判 NEED_EVIDENCE
  （over-abstention）？
- **未复现同样是结果**：若新独立 issue 上未观察到上述行为，须如实报告为
  "未在独立小样本上复现"，并讨论旧数据构造（镜像 fixture、多条件重复）或
  任务条件可能放大了原结论——不得在看到结果后更改假设。

## 3. 冻结的 gold 面（A.1 实测，非预期）

来自 [g3a1_condition_gold.jsonl](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_g3a/gold/g3a1_condition_gold.jsonl)：

| 制度 | 证据性质 | Provisional 分布（10 issue） | 可检验的问题 |
|---|---|---|---|
| T3D-Escalate | 充分 | 7 ACCEPT / 3 REJECT | Q-A、Q-D |
| T2A-T | 充分（制度呈现全绿记录） | 7 ACCEPT / 3 REJECT | Q-A、Q-D |
| T3A-T | 充分 | 7 ACCEPT / 3 REJECT | Q-A、Q-D |
| T2D-T | 受限（验收通道隐藏/not adjudicated） | **10/10 NEED_EVIDENCE** | 仅弃权面 |
| T3D-Strict | 受限（验收结果硬阻断） | **10/10 NEED_EVIDENCE** | 仅弃权面 |

- oracle↔condition 总分歧 = 20：每 issue 在 T2D-T、T3D-Strict 各分歧 1 次
  （7 个 ACCEPT→NEED，3 个 REJECT→NEED）。
- **NEED_EVIDENCE 可测范围明确限定于 T2D-T / T3D-Strict**；充分证据三制度
  的 condition gold 无 NEED。因此"弃权是否恰当"在受限面上以 NEED 为正确
  答案评估，而"是否过度弃权"只在充分证据面上评估（那里正确答案非 NEED）。

## 4. 主比较（confirmatory 仅 2 个方向性，其余探索性）

- **C1（对应 Q-A）**：gpt-4.1-mini 在**充分证据三制度合并**（issue 内先对
  T3D-Escalate/T2A-T/T3A-T 取 UA 指示，避免三制度被当独立样本）对 3 个
  gold=REJECT issue 的 issue 等权误受率。方向性复现判据：点估计 > 0 且
  issue-cluster bootstrap 95% CI 下界 > 0。n_reject=3，先验标注
  `underpowered`，CI 必宽，结果仅作方向性。
- **C2（对应 Q-D）**：deepseek-* 在充分证据三制度合并上，对**全部 10 个
  issue**（正确答案为 ACCEPT 或 REJECT，均非 NEED）判 NEED_EVIDENCE 的
  issue 等权过度弃权率。方向性判据同上（>0 且 CI 下界 > 0）。
- 探索性（不报确证 p）：单制度分解、两模型对比、受限面 T2D/Strict 上
  "恰当中 NEED"率（正确即 NEED）、制度间转移、7 个 ACCEPT issue 上的
  误拒/过度 NEED 校准。

## 5. 单元、样本量、三层可判定性

- 实验单元 = **独立 issue，n=10**；模型×5 制度是 issue 内重复测量，**不**
  增加独立 n。禁止镜像，每 issue 单 target patch。
- 三层证据可判定性：
  - **充分层（Esc/T2A/T3A）**：gold 可判 ACCEPT/REJECT，检验 Q-A/Q-D；
  - **受限层（T2D/Strict）**：gold 全 NEED，仅检验"在制度要求弃权时是否
    弃权"，**不能**用于估计全信息三态校准；
  - 分析须逐条件用各自 condition_gold 取 eligible 集，并显式报告每条件
    "eligible issue 数"，禁止把全证据 3-REJECT 分母跨条件沿用。
- 调用规模：10 issue × 5 条件 × 2 模型 = **100 次模型调用**（每 issue 单
  target，无镜像）。

## 6. 统计分析（冻结，详见 stats JSON）

- 主单位独立 issue；C1 分母 3、C2 分母 10。
- 对 C1 的 3 个 REJECT：报**精确计数**（如 k/3 issue）与宽 issue-cluster
  bootstrap CI，并同时给精确二项置信区间（Clopper–Pearson）作敏感性；
  明确写出单 issue 翻转 ≈ 33pp。不做总体率推断、不报 κ、不称泛化。
- 报告每 issue 的 gold 三态类别、判决、三制度合并 UA/弃权指示；cell 数仅
  作重复测量说明。
- Parse 失败：无法解析 = 非 ACCEPT（不计 UA），单列 parse-fail 率。
- Gold 层级：Gate 3-B 启动时若仲裁未完成，全部指标标注 "against
  provisional, singly-adjudicated gold"，并在 Threats 写明缺独立人工仲裁；
  若已有 v2 human-adjudicated gold，则用 v2 并重算敏感性（方案见仲裁协议）。
- 多重性：仅 C1、C2 两个方向性 confirmatory，且各自只看 CI 下界是否 >0；
  其余一律探索性。
