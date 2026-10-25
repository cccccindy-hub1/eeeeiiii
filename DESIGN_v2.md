# BlindVerify / StanceBench — 实验设计 v2（定稿）

## 定位
- 测量贡献：stance attribution（within-patch, randomized, independent sessions）
- 方法贡献：Evidence-Bound Handoff Contract（区分主张 / 可核验事实）
- 辅助：judgment revision（顺序翻转）

## 实验 1：Stance Attribution（主）
- 独立会话，随机条件，固定 patch/issue/工具
- 条件：Neutral / Positive / Negative
- 配对比较，估计接受率差
- 指标：FPR(bad->accept)、GPR(good retained)、ΔMCC

## 实验 2：Evidence x Stance 冲突
- 四格：stance in {Pos, Neu} x CI in {pass, fail}
- 再加证据来源三档：自述 < 未认证引用 < 独立执行器签发
- 关注：证据真实但立场相反时，reviewer 信谁

## 实验 3：Handoff Protocol（方法贡献）
- P1 自由文本 / P2 无解释 / P3 结构化事实 / P4 证据绑定
- Controlled Evaluation：固定信息集与工具权限
- Deployment Evaluation：固定预算，允许协议自由使用 token
- 两者分开报告

## 实验 4：Judgment Revision（辅助）
- d0 -> 随机声明 -> d1
- 指标：flip rate；区分 bad->accept / good->reject
- 明确承认 self-consistency bias 与自我纠正混杂

## 样本
- 起点：SWE-Review-Bench 候选 PR (1,384)
- Pilot：30 配对 patch（15 good / 15 bad）
- 缺陷分层：类型（逻辑/边界/跨模块/并发）+ 可见性（现有测试可检/需新测试/需复杂环境）

## 统计
- McNemar / 配对 bootstrap
- 难度用跨模型平均 blind 正确率定义，并在回归中控制

## 必须报告的威胁
- BPAR @ prevalence 重加权
- 证据伪造/过期条件
- 交互项功效分析
