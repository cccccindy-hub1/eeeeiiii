# G3-A · Symptom Probe 构念效度与修正审计

每个 G3-A issue 都配一个**人工手写**的 symptom probe：只使用公开 sympy
API、从用户问题报告派生、独立于维护者 `test_patch`；要求 baseline 失败、
候选补丁后通过（或对"应返回不变"的情形不崩溃）。probe 是诊断通道
（diagnostic channel），与维护者 F2P/P2P 验收通道相互独立。

首轮真实重放后，4/10 的 probe 暴露了**探针自身**的构念问题（不是候选
patch 的结论被改），均经 base/post 现场诊断后修正并 **--force 重跑**。
修正全过程留痕于此，严禁静默改判。

| issue | 首轮现象 | 诊断（base/post 实测） | 修正 |
|---|---|---|---|
| 13615 | post probe 仍失败，与维护者 F2P 通过矛盾 | 维护者 `test_Complement` 的接受语义是 `Complement({x,y,2},I) == Complement({x,y},I)`：数字 2 被移除，自由符号因归属未知而保留为对区间的补集，**并非** `== {x,y}`。baseline 错给 `{x,y}`。 | 期望值改为维护者接受的 `Complement(FiniteSet(x,y),I)`；baseline 仍失败、post 通过。 |
| 24213（第一次修正） | post probe 抛 AttributeError | 该旧版 `DimensionSystem` 无 `get_dimension`（探针 API 用错）；补丁后原 ValueError 已消除。 | 维度改为与独立计算的 `meter/second` 维度比较，不依赖版本相关访问器。 |
| 24213（最终决断） | 上述"维度须归一化为 velocity"断言 post 仍失败（返回 `Dimension(acceleration*time)`），得 class=D/addressed=False | 该断言**超出了报告症状**：issue 报告的可复现症状就是 `SI._collect_factor_and_dimension(a1*t1+v1)` 抛 ValueError；维护者回归测试 `test_issue_24211` 只断言"should not throw ValueError here"，**并未**要求返回维度被规范为 velocity。候选确实消除了崩溃（F2P 1/1），但未识别 `acceleration*time == length/time` 的等价归一化。 | 按"probe 须忠实用户报告症状、且以维护者 ACCEPTED test 语义为准"原则，probe **放宽为仅断言不抛异常**。重建后 class=B / addressed=True / acceptable=True（F2P 1/1）。**披露**：该候选仅消除崩溃、未做维度等价归一化；若研究问题关心"等价维度识别"，这是候选的真实局限，但不属于本 issue 报告的症状，不得由探针自行加码。 |
| 17318 | baseline probe 通过（无区分力） | 报告标题表达式在该 base_commit **已不崩溃**（返回 I）；但维护者回归测试中的相关复数表达式 `sqrtdenest(3-sqrt(2)sqrt(4+I)+3I)` 仍抛 IndexError。post 不再崩且返回不变（==e），但维护者 F2P 仍 0/1（`_sqrt_match(4+I)` 应为 `[]`，候选给 `[4+I,0,1]`）。 | probe 锁定仍在 baseline 崩溃的 `e` 表达式（不崩溃且等值返回）；issue_addressed 与 merge_acceptable 因此可分离。 |
| 17630 | post probe 遍历 `blocks.items()` 抛 AttributeError | 该版 `BlockMatrix.blocks` 是 ImmutableDenseMatrix，无 `.items()`；实测 post 下 `block_collapse(b*b*b)==BlockMatrix([[a**3,z],[z,z]])` 为 True，baseline 抛 ValueError。 | 直接与期望 BlockMatrix 比较，并加 b*b 对照；不再遍历内部矩阵。 |

## 区分力复核（全部 10 个，修正后重跑确认）

- 修正后四个 issue 的 probe 均满足 baseline 失败 / post 行为正确；
- 其余 6 个（13974、15349、20590、21847、24443、19783）首轮即
  baseline exit=1 / post exit=0，无需修改。

## 与 gold 的关系（重要）

- probe 只决定**诊断通道**（issue_addressed / symptom_persists）。
- 验收通道（F2P/P2P）独立来自维护者 test_patch 的真实 pytest。二者可
  合法背离：例如 17630 症状被消除但一个维护者测试仍失败
  （merge_acceptable=False）；17318 崩溃被消除但 `_sqrt_match` 语义不符、
  F2P 失败。这类背离正是 oracle 双通道规则要区分的情形，不是噪声。
- 探针修正发生在任何模型预测之前，属于离线数据构建期的 gold 确立过程；
  不依据任何模型输出。
