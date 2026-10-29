# GroundedReview v2.1 — 离线实验设计报告（Design Gate，$0）

- 授权：用户 2026-10-25 批准 v2.1 **离线设计**；明确不批准真实模型调用、不批准 Gate 3 付费扩样、不新增 Issue、不运行 Gemini、不 commit。
- 本阶段产物：设计模块 [eal_v21_design.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/eal_v21_design.py)（**结构上无 live 代码路径、不导入任何模型客户端**）、88 个冻结候选 payload（[v21/layers](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/v21/layers)）、[设计清单](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/v21/eal_v21_design_manifest.json)、[冻结清单（含预注册+预算）](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/v21/eal_v21_freeze_manifest.json)、[离线 preflight（15 项全 PASS）](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/v21/eal_v21_preflight.json)。E1/CEE/Gate-2/G2.5 原始产物全部只读未改。
- 研究问题（用户给定）：**GPT 的错误源于没有正确比较证据操作数（Evidence Verification Failure），还是没有正确执行拒绝/弃权规则（Decision Policy Failure）？**

---

## 1. 2×2 正交消融设计（指令 1–4）

被试层固定为 **STRUCTURED**（G2.5 异常所在层），22 个冻结 fixture × 4 条件 = 88 cell/模型；A0B0 与 Gate-2 structured **逐字节相同**（preflight 22/22 校验）。

| | **B0** 冻结 Gate-2 判决头 | **B1** 头内加非对称规则提醒 |
|---|---|---|
| **A0** Gate-2 structured 原字节 | A0B0 控制（= Gate 2 观察） | A0B1 仅政策 |
| **A1** 正文加 TABLE 0 确定性计数 | A1B0 仅渲染 | A1B1 两者 |

**Factor A — Evidence Rendering（仅渲染，+1187 字节/item）。** 在正文首句后插入 `TABLE 0 — DETERMINISTIC OPERAND COUNTS`，14 行计数全部由 TABLES 1–4 已呈现操作数机械算出：身份操作数相等/相异对数、run-tree 相异对数、declared f2p/p2p 的 declared/present/absent 数、declared p2p 有 base 状态数、post-patch f2p FAILED 数。**纪律**：不出现 linked/fresh/complete/symptom_persists 任何布尔或近义词（preflight 对 88 个正文做 verdict-word 扫描，0 命中）；不做合取（不把"身份相等+树相等"合并成一个结论）；absent id 列表仍留在 TABLE 4，TABLE 0 只给数量。
- 已知且预注册的权衡：`run-tree differing=0` 与 `identity differing=0` 并列时，读者再走一步合取即可推出新鲜度——但这一步合取在 A0 也始终可做（TABLE 1/2 并排），A 只降低算术成本。这正是用户授权的"计算辅助"，作为显著性操纵**本身就是实验变量**，须按此解释，不得宣称 A 仍与 A0 信息等价；它仍是"距裁决一步之遥的计数"，不是裁决。

**Factor B — Policy Reminder（仅头，+807 字节/item）。** 5 条引用**全部逐字取自冻结头**（prompts.py TERNARY_HEAD，preflight 逐句校验存在且头增量恰好等于该块），不改 ACCEPT/REJECT/NEED_EVIDENCE 定义：①单个适用失败即足 REJECT、不必跑全；②stale/错链/不适用日志中的失败不是 REJECT 依据；③ACCEPT 需 complete/fresh/linked/failure-free；④不得仅因 stale/不全而 REJECT；⑤对决定性失败或完整成功弃权即错误。②④针对 G2.5 发现的负例 over-abstention，③针对正面幻觉。

**正交保证（preflight 机械校验）**：A 只改正文（四条件 head sha：A0B0==A1B0、A0B1==A1B1）；B 只改头（body sha：A0B0==A0B1、A1B0==A1B1）；字节增量可加。任何条件的效果不得跨因素归因。

## 2. 离线三审计与 Mock（指令 5、11）

[preflight](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/v21/eal_v21_preflight.json) **15/15 PASS**：
- **Label Leakage**：88 正文 0 verdict/metadata 泄露（沿用 Gate-2 冻结正则）+ TABLE 0 额外 verdict-word 扫描 0 命中；全 payload 无凭据。
- **Evidence Sufficiency**：计数内部自洽（present+absent=declared、相等+相异=比较数）；A1 正文**删除 TABLE 0 后与 A0 逐字节相等**（无操作数增删）；22/22 gold 仍可从可见材料确定，分布 7/6/9。
- **Hash 冻结**：88 payload sha、四条件 prompt 指纹、system/goal/schema sha、相关代码 sha 全部写入冻结清单。
- **Rubric 锚定**：预计算的 p1–p4 操作数矛盾标志在 G2.5 八案上**逐案复现归因**（freshness 案树相异=1；coverage 缺席案 absent>0；c59a8ceb 身份相异字段=patch_sha256；c637f604 的 "+coverage" 对应 p4 已执行 f2p FAILED，非缺席，校验中已显式区分）。
- **Mock**：确定性 oracle 响应器（不触网）跑完 176 个 mock 行，四条件两模型 DA=1.00，仅验证摄取/评分/2×2 估计管线，**不构成任何效果证据**。Gate-1 冻结自检仍 20/20。

## 3. 预注册指标与统计（指令 6、7）

- **主样本 = 全部 22 fixture**；8 个 G2.5 案例仅为**预注册诊断子集**，不用于筛选主样本。独立单位 = **10 个 issue 簇（instance_id）**，镜像 fixture 在簇内取均值后再进入对比；bootstrap seed=7/10000，配对百分位法重抽 10 簇。
- 主要终点 **DA**；次要：**NEED→ACCEPT 率**（9 个 NEED-gold，Verification Failure 行为标记）、**与可见操作数矛盾的验证断言比例**（见下 rubric）、**Over-Abstention**（总体 + 单列 REJECT-gold 子集，Policy Failure 标记）。
- 估计量：A 主效应（B 边际平均）、B 主效应（A 边际平均）、**AB 交互**。**判读措辞（按 2026-10-25 R1 审批意见收紧）**：因素效应是**行为层面**的，不能唯一等同于模型内部失败机制——A 的效应支持 **Verification Assistance** 解释（计数既可能减少比较/计算错误，也可能仅提升操作数显著性，二者在本设计不可分离）；B 的效应支持 **Policy Salience** 解释（重新注意非对称规则，或仅因提示更长更显著，不可分离）；非零交互说明两干预相互依赖。预注册的**行为判读**：A-only 改善 NEED→ACCEPT/矛盾断言 → 与 Verification Assistance 相容；B-only 改善 REJECT-gold 弃权 → 与 Policy Salience 相容；DS 在 structured 对 8/8 案本就正确（接近天花板），作为**阴性对照**。
- **矛盾断言编码 rubric**（需 reason 中有显式断言，仅凭最终 ACCEPT 不算——那归入 NEED→ACCEPT 终点）：P1 声称身份/目标匹配而 p1 标志真；P2 声称 fresh/current tree/run 匹配而 p2 标志真；P3 声称覆盖完整/充分/全跑而 p3 标志真；P4 声称全部通过/无失败而存在已执行 f2p FAILED。冻结清单已逐 cell 预算四标志；运行后对逐字 reason 双盲两轮编码、报告编码一致性。
- **功效诚实声明**：n=10 簇，CI 预期较宽；本实验定位为**机制定位 Pilot**，不做确认性功效宣称。

## 4. 统计口径纠正（指令 10）

G2.5 报告中"GPT 调用噪声约 ±9 pp"的表述**收回**，正式口径为：
> 在 **22 个相同输入、两轮调用**上观察到 2 个逐 cell 判决翻转（零和，故总准确率同为 18/22），证明 **temperature=0 不保证逐 cell 可复现**。但两轮、22 个样本**不足以估计输出方差，也不构成稳定噪声标准差或置信区间**；该翻转幅度也不能作为 Adjudicated−Raw（+40.9 pp）层间提升的不确定性估计。

判决稳定性改由下节**独立 Reliability Check** 量化。本纠正只写入 v2.1 报告，G2.5 原始报告作为当时产物保留不动。

## 5. 独立 Reliability Check 设计（指令 8、9，独立预算）

**与消融臂完全分离**：不改任何 Prompt/Payload/参数/Gold，对 Gate-2 冻结 66 cell/模型原样重跑。
- 建议 **r=1 先行（Stage R1）**：Gate-2 原始轮 + 1 新轮 = 每 cell 2 个时间点，计算逐 cell 一致率、判决翻转集、配对 McNemar 描述、DA 轮次波动（min/median/max）。一致率是可解释的描述量；明确**重复调用不统计独立**（同输入、同后端、可能的时序权重漂移），不得当作 n 增大。
- 若 R1 检出实质不一致，再追加 **r=2（Stage R2，共 3 轮）** 以报 Fleiss κ 与每 cell 稳定模式。
- 产出直接决定 2×2 单轮结果是否可解释：若 GPT 轮间摆动与预期处理效应同量级，则 2×2 必须按重复测量设计执行/解读。

## 6. 分臂预算（按 Gate-2 实测 token × 峰值守卫单价；两臂不自动合并）

| 臂 | 内容 | 新调用 | 估算 |
|---|---|---|---|
| **R1 可靠性** | 66 冻结 cell × 2 模型 × 1 新轮 | 132 | **≈ $0.477**（DS .217 / GPT .260） |
| R2 可选追加 | 再 1 新轮 | 132 | ≈ $0.477（两轮合计 **≈ $0.954**） |
| **X 消融（推荐全新跑）** | 88 cell × 2 模型，四条件同批随机序 | 176 | **≈ $0.399**（DS .187 / GPT .212） |
| X 经济版（不推荐首选） | 仅跑 A1B0/A0B1/A1B1，复用 Gate-2 A0B0 | 132 | ≈ $0.30，但跨时间复用，有时序混杂，只能作次要锚点 |

三臂合计上限（R1+R2+全新 X）≈ $1.35，任一臂均需单独书面批准；Economics 细节见 [冻结清单 budget_envelopes](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence_store_eal/v21/eal_v21_freeze_manifest.json)。

## 7. 风险登记

1. **计数的裁决邻近性**：TABLE 0 降低了合取成本，理论上可被视为"半个 fresh 结论"。已用"只计数不合取、不命名词、不合并行"约束，并作为预注册的显著性变量解释；若评审认为越界，可在付费前仅保留 coverage 缺席计数（去掉身份/树相等行）做更保守变体——但这属另一次离线修订，需再批。
2. **n=10 低功效**：CI 宽，只做机制定位；Gate 3 是否扩新 issue 取决于方向性 + 可靠性结果，不取决于单次显著性。
3. **DS 天花板**：其 8 案 8/8 正确，A 对 DS 几乎无空间，属预期阴性对照而非失败。
4. **temp=0 非确定性与处理效应混杂**：以先做 R1 缓解；X 臂建议四条件同批、cell 内随机序，单模型内配对。
5. **rubric 编码主观性**：逐字断言门控 + 双盲两轮 + 报告一致性，分歧件仲裁留痕。
6. **跨时间复用 A0B0**：经济版的固有混杂，推荐全新跑。

## 8. 分阶段执行建议（全部待书面批准）

1. **先批 R1（≈$0.48，零协议改动）**——确定 GPT 逐 cell 稳定性基线。
2. **再批 X（≈$0.40，全新 88×2）**——2×2 定位 Verification vs Policy。
3. **决策门**：A1 使 GPT 矛盾断言/NEED→ACCEPT 下降且在重复中稳定 → 支持"证据显著性"机制，Gate 3 值得投新独立 issue；仅 B1 有效 → 政策执行问题；噪声主导 → 先加重复次数再谈扩样；皆无效 → 重新审视构念。
4. G4（第三模型、更大规模）在 Gate 3 独立 issue 结果之后另行报批。

## 9. 停止点

v2.1 **离线设计阶段到此停止**：$0 支出、零模型调用、零新 Issue、E1/CEE/Gate-2/G2.5 全部冻结产物未修改、未 commit（本阶段新增文件仅位于 `evidence/eal_v21_design.py` 与 `evidence_store_eal/v21*`）。等待 R1 与 X 的下一次书面批准。
