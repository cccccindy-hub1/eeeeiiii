"""G3-A.1 tasks 1/2/4/5 — build BLINDED Gold Dossiers for the second
independent annotator. Zero API.

For each of the 10 G3-A issues emit a self-contained, anonymised dossier under
evidence_store_g3a1/dossiers/<CODE>/ containing ONLY primary materials:
  issue report, candidate patch, maintainer test patch, symptom probe, the four
  raw pytest/probe logs (f2p, p2p, p2p_baseline, symptom), a neutral provenance
  manifest, and a BLANK adjudication form.

Deliberately EXCLUDED (blinding):
  - any model prediction / reason (no models were run, but the guard stands);
  - annotator-1 / mechanical oracle & condition labels;
  - dataset `resolved`, builder label_class, issue_addressed, merge_acceptable;
  - the SymPy issue NUMBER / instance id (replaced by random code D01..D10),
    with a SEALED code->issue map kept outside the dossiers; explicit upstream
    issue URLs/refs in the prose are redacted. Code identifiers such as
    test_issue_24211 are kept (needed to read the test) — residual weak
    blinding against a deliberate web lookup is disclosed, not hidden.

Mechanical integrity (HMAC signature, log digests, restaged run tree) is stated
as a fixed PREMISE so the human spends effort on the parts a rule cannot do:
semantic F2P applicability, environment false-failure screening, and whether
the probe matches the reported symptom.

For 24213 the executed probe's editorial header (which states the chosen
criterion) is replaced by a neutral pointer; a separate packet P-24213 presents
BOTH candidate criteria without indicating the chosen one.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path

from evidence.schemas import make_artifact_id
from evidence.store import ArtifactStore
from evidence.ternary import read_jsonl

HERE = Path(__file__).resolve().parent.parent
G3A = HERE / 'evidence_store_g3a'
G3A1 = HERE / 'evidence_store_g3a1'
DOS = G3A1 / 'dossiers'
SEALED = G3A1 / 'adjudication' / 'sealed'
LOGS = ('f2p', 'p2p', 'p2p_baseline', 'symptom')
SHUFFLE_SEED = 20261026  # blinded packet order; independent of selection seed

# Decision / provenance tokens that must NOT appear in EVIDENCE files.
# (Allowed in the manual and the blank form, which define the answer task.)
EVIDENCE_LEAK = [
    r'\boracle_gold\b', r'\bcondition_gold\b', r'\bmerge_acceptable\b',
    r'\bissue_addressed\b', r'\blabel_class\b', r'\bresolved_in_dataset\b',
    r'\bresolved\b', r'\bACCEPT\b', r'\bREJECT\b', r'\bNEED_EVIDENCE\b',
]
# pytest own verdicts are legitimate evidence, not the answer.
_ISSUE_URL = re.compile(r'(?:https?://)?(?:www\.)?github\.com/sympy/sympy/(?:issues|pull)/\d+', re.I)
_ISSUE_REF = re.compile(r'(?<![A-Za-z0-9_])(?:sympy/sympy)?#\d{4,5}(?![0-9])')
_PLAIN_ISSUE = re.compile(r'(?<![A-Za-z0-9_.])(?:issue\s*[#_]?\s*)(\d{4,5})(?![0-9])', re.I)


def redact(text):
    text = _ISSUE_URL.sub('<UPSTREAM_ISSUE_REDACTED>', text)
    text = _ISSUE_REF.sub('<ISSUE_REF_REDACTED>', text)
    text = _PLAIN_ISSUE.sub(lambda m: 'issue <ID_REDACTED>', text)
    return text


FORM = """# Dossier {code} · 独立判定表（Annotator 2）

> 请先阅读编码手册 ANNOTATOR2_CODING_MANUAL.md，再填本表。所有结论须你
> 独立做出；不要查询上游仓库/PR，不要与他人讨论。

## Q1 Oracle Acceptability（三选一，圈选一个）

- [ ] ACCEPT
- [ ] REJECT
- [ ] NEED_EVIDENCE

## 证据可信三前提（机械完整性已作为前提提供；此处判断语义疑点）

| 前提 | 是 | 否 | 存疑 | 备注 |
|---|---|---|---|---|
| linked（记录确属被审补丁+指定基线） |  |  |  |  |
| fresh（无语义层面的代码状态疑点） |  |  |  |  |
| complete（声明用例均已执行） |  |  |  |  |

## 假失败 / 不适用排查（逐项：未命中 / 命中 / 无法判断）

| 排查项 | 结论 | 说明（涉及哪个测试/日志行） |
|---|---|---|
| 环境/依赖/flaky/平台假失败 |  |  |
| F2P 对候选补丁不适用或超出 issue 范围 |  |  |
| 测试本身错误/过时 |  |  |
| 基线即坏（preexisting-bad） |  |  |
| 症状探针断言与用户报告症状错位（过强/过弱） |  |  |

## 双通道核对

- 验收通道：补丁后是否存在适用的 F2P 失败 / 非基线坏 P2P 回归？______
  （列出具体测试节点名；若无写“无”）
- 诊断通道：基线是否复现症状 ____；补丁后症状：消失 / 仍持续 / 无法判断。

## 理由（必填，至少 2–3 句；说明你如何权衡两条通道）

_______________________________________________________________

_______________________________________________________________

## 信息充分性

- [ ] 材料足以判定
- [ ] 材料不足，需要（说明需要什么）：__________________________
"""

# Per-F2P-node applicability worksheet (task 4). Generated for EVERY dossier
# so its mere presence never flags which cases are the symptom-resolved-but-
# failing ones. Post status comes straight from the f2p log (already visible
# evidence); the blank columns are the human-only judgements.
F2P_SHEET_HEAD = """# Dossier {code} · 维护者 F2P 逐节点适用性工作表

> 对**声明的每一个 FAIL_TO_PASS 节点**独立作答。post 状态直接抄自
> 05_log_f2p.txt（你可见的一手证据）；右侧四列才是需要你人工判断的。
> 基线（未打补丁）预期该节点失败；可用 03_maintainer_test.patch 阅读其
> 断言，用 07 日志确认作用域内是否本就坏，用 01 判断该语义是否属于
> issue 的合理完成标准。

| F2P 节点 | post 实际状态(抄日志) | ① 关联性：确为被审补丁+指定基线的记录? | ② 真实性：失败是真实逻辑失败，还是环境/依赖/flaky/平台? | ③ 基线是否本就坏? | ④ 适用性：该断言是否为 issue 的合理完成标准（而非过强/替代设计/测试过时）? | 该节点是否构成可接受性失败? |
|---|---|---|---|---|---|---|
"""
F2P_SHEET_ROW = "| {node} | {status} |  |  |  |  | 是 / 否 / 无法判断 |\n"
F2P_SHEET_TAIL = """
综合：若存在“是可接受性失败”的节点，请在主判定表 Q1 相应体现；若你判定
所有 post 失败节点均不适用或为假失败，请在主表理由中明确说明依据。
"""

# Task 5: criterion-review packet. Both candidate criteria presented WITHOUT
# saying which one the builder finally executed.
CRITERION_PACKET = """# Dossier {code} · P-CRITERION 探针判据专题表

本案症状探针在构建期曾在两种判据间取舍。请你**独立**判断哪一种更忠实于
issue 报告症状，材料不告诉你构建期最终执行了哪一种。

## 背景（来自一手材料，你可自行核对）
- issue 报告的可观察症状：一段关于“等价量纲/维度”的计算在某输入下抛出
  异常（详见 01_issue.txt 的实际复现代码）。
- 候选补丁确实改动了相关量纲处理路径（详见 02_candidate.patch）。
- 维护者为本系列回归添加的测试只断言该计算“不应抛出异常”（见
  03_maintainer_test.patch；注意测试函数名沿用历史编号，与本案编号无关）。
- 08_log_symptom.txt 给出探针在基线与补丁后的真实执行结果。

## 两种候选判据
- **判据 A（窄，异常消除）**：补丁后该复现路径不再抛出异常，即判症状解决。
  理由（主张方）：与维护者回归测试“should not throw”一致；异常即报告的
  直接可观察症状。
- **判据 B（宽，语义修正）**：除不抛异常外，还要求结果满足
  acceleration*time == length/time 的维度等价（即返回被正确归一化为
  velocity），否则症状仅“止住崩溃”而未真正修正量纲。
  理由（主张方）：issue 标题是“未检测到等价维度”，用户关心的是量纲等价
  被正确处理，而非仅仅不崩。

## 请回答（不要预设构建期采用了哪个）
1. issue 报告**正文的实际复现代码**直接展示的症状，是“抛异常”还是
   “返回了量纲不等价的值”？（引用原文）
2. 判据 A 是否足以代表该症状被解决？  足以 / 不足以免崩溃但语义未修 /
   无法判断。
3. 若你倾向判据 B：仅做到 A 的候选，在 Q1 可接受性上应判 ACCEPT、REJECT
   还是 NEED_EVIDENCE？为什么（注意区分诊断通道与验收通道）？
4. 若你倾向判据 A：把要求提高到 B，是否会让探针**超出**维护者测试与
   issue 原文，从而对该候选**过强**？
5. 你最终建议本案诊断通道采用：判据 A / 判据 B / 需要补充信息（说明）。
"""


MANIFEST_TMPL = """Dossier {code} — 材料清单与完整性前提（中性，不含任何答案）

仓库（已匿名）：SymPy（本地 vendored 仓库，真实执行）
base_commit：{base}
候选补丁 sha256：{patch}
维护者 test_patch sha256：{tp}
执行环境：{runner}
测试命令：python -m pytest <作用域文件> -v --tb=short -p no:cacheprovider
         （3 文件一批；含全部 F2P + 作用域 P2P + 基线 P2P）
探针执行：CPython 3.9.25 + pytest 8.4.2 + mpmath 1.4.1（uv，离线）

声明的 FAIL_TO_PASS 节点（维护者回归测试）：
{f2p}

声明的作用域 PASS_TO_PASS 节点数：{p2p_n}（相邻 tests/ 包内可映射子集，
非数据集完整 P2P 套件；完整 P2P 未在本地执行——“通过”仅指作用域内）。

机械完整性前提（已由构建期 HMAC/sha256/git write-tree 核验，你无需重算）：
- 四个日志与签名记录 log_digests 一致；
- 执行树 = base + 候选补丁 + 维护者 test_patch 的确定性重放树；
- 记录签名可信。
你仍应独立判断：这些测试在**语义上**是否适用于该候选、失败是否为环境
假失败、探针是否忠实于 issue 报告症状。

匿名化说明（重要）：issue 编号与上游 URL 在 01–04 文件中已统一替换为
<ID_REDACTED>/<UPSTREAM_ISSUE_REDACTED>（含补丁/测试注释中引用该 issue
的位置）。替换只针对引用标记，不改任何代码行与断言语义；故 02/03 的
显示字节与上面 sha256 绑定的权威字节仅在这些注释标记处不同。代码内部
因测试命名惯例而保留的形如 test_issue_<数字> 的函数名未改（读懂测试所
需）；它们不构成本案编号的可靠标识，残留的弱可识别性已在审计中披露。

文件：
  01_issue.txt              用户问题报告（issue 号已匿名）
  02_candidate.patch        被审候选补丁（唯一 target，无镜像）
  03_maintainer_test.patch  维护者回归测试补丁
  04_probe.py               从 issue 报告派生的症状探针
  05_log_f2p.txt            补丁后 F2P 的真实 pytest 日志
  06_log_p2p.txt            补丁后作用域 P2P 的真实 pytest 日志
  07_log_p2p_baseline.txt   基线（未打补丁）作用域 P2P 日志（用于识别 preexisting）
  08_log_symptom.txt        症状探针 基线/补丁后 执行结果
  09_form_blank.md          你的空白判定表
  10_f2p_worksheet_blank.md 逐 F2P 节点的关联性/真实性/基线/适用性空白工作表
{criterion_note}"""


def sha(t):
    return hashlib.sha256(t.encode('utf-8')).hexdigest()


def main():
    DOS.mkdir(parents=True, exist_ok=True)
    SEALED.mkdir(parents=True, exist_ok=True)
    store = ArtifactStore(str(G3A / 'store'),
                          fixtures_meta_name='g3a_fixtures_meta.json')
    raws = {r['instance_id']: r
            for r in read_jsonl(str(G3A / 'raw' / 'g3a_target_rows.jsonl'))}
    golds = {g['instance_id']: g
             for g in read_jsonl(str(G3A / 'gold' / 'g3a_gold.jsonl'))}
    iids = sorted(raws)
    order = iids[:]
    random.Random(SHUFFLE_SEED).shuffle(order)

    sealed, leak_audit = [], []
    for k, iid in enumerate(order, 1):
        code = f'D{k:02d}'
        raw, g = raws[iid], golds[iid]
        patch = g['patch_sha256']
        aid = make_artifact_id(iid, patch)
        rec, authentic = store.get(aid)
        d = DOS / code
        d.mkdir(parents=True, exist_ok=True)

        issue = redact(raw['problem_statement'])
        # Patches/tests are authoritative code, but their COMMENTS often quote
        # the upstream issue number/URL, which would break anonymisation. Redact
        # only those tokens; this is disclosed in the manifest (display bytes
        # differ from the sha256-bound original only at redacted comment tokens).
        cand = redact(raw['model_patch'])
        tp = redact(raw['test_patch'])
        (d / '01_issue.txt').write_text(issue, encoding='utf-8', newline='')
        (d / '02_candidate.patch').write_text(cand, encoding='utf-8', newline='')
        (d / '03_maintainer_test.patch').write_text(tp, encoding='utf-8',
                                                    newline='')

        # Probe: anonymise header comments. For the criterion-reviewed case
        # (24213), replace editorial header with a neutral pointer.
        probe = (G3A / 'probes' / f'{iid}.py').read_text(encoding='utf-8')
        if iid.endswith('24213'):
            probe = ('# Symptom probe for an anonymised SymPy dimensions issue.\n'
                     '# NOTE: the acceptance criterion of this probe is under\n'
                     '# independent review; see packet P-CRITERION (opened by the\n'
                     '# coordinator). Judge the executed behaviour from the logs.\n'
                     + re.sub(r'\A.*?(?=\n(?:import|from) )', '', probe,
                              count=1, flags=re.S).lstrip('\n'))
        probe = redact(probe)
        (d / '04_probe.py').write_text(probe, encoding='utf-8', newline='')

        logs = {}
        for j, nm in enumerate(LOGS, 5):
            txt = (G3A / 'store' / 'logs' / f'{aid}.{nm}.log').read_text(
                encoding='utf-8')
            logs[nm] = txt
            (d / f'{j:02d}_log_{nm}.txt').write_text(txt, encoding='utf-8',
                                                     newline='')
        (d / '09_form_blank.md').write_text(FORM.format(code=code),
                                            encoding='utf-8', newline='')

        # 10: per-F2P applicability worksheet (every dossier; task 4).
        sheet = F2P_SHEET_HEAD.format(code=code)
        for node, status in rec['fail_to_pass'].items():
            sheet += F2P_SHEET_ROW.format(node=node, status=status)
        sheet += F2P_SHEET_TAIL
        (d / '10_f2p_worksheet_blank.md').write_text(
            sheet, encoding='utf-8', newline='')

        # 11: criterion-review packet ONLY for the criterion-adjusted case;
        # filename carries no issue id (blinded). Flagged in its manifest.
        is_criterion_case = iid.endswith('24213')
        if is_criterion_case:
            (d / '11_P_CRITERION_blank.md').write_text(
                CRITERION_PACKET.format(code=code),
                encoding='utf-8', newline='')

        manifest = MANIFEST_TMPL.format(
            code=code, base=raw['base_commit'], patch=patch,
            tp=rec['test_patch_sha256'], runner=rec['runner'],
            f2p='\n'.join(f'  - {n}' for n in raw['FAIL_TO_PASS']),
            p2p_n=g['facts']['declared_scoped_count'],
            criterion_note=('\n  11_P_CRITERION_blank.md   探针判据专题表（本案构建期做过判据取舍）\n'
                            if is_criterion_case else ''))
        (d / '00_manifest.txt').write_text(manifest, encoding='utf-8',
                                           newline='')

        sealed.append({'code': code, 'instance_id': iid,
                       'patch_sha256': patch,
                       'oracle_gold_sealed': g['oracle_gold'],
                       'human_status': g['human_adjudication']['status']})

        # Leakage scan on EVIDENCE files only (form/manual define the task and
        # legitimately contain the answer vocabulary).
        hits = []
        for fn in ('01_issue.txt', '02_candidate.patch',
                   '03_maintainer_test.patch', '04_probe.py') \
                  + tuple(f'{j:02d}_log_{n}.txt'
                          for j, n in enumerate(LOGS, 5)):
            body = (d / fn).read_text(encoding='utf-8', errors='replace')
            for pat in EVIDENCE_LEAK:
                for m in re.finditer(pat, body):
                    hits.append({'file': fn, 'pattern': pat,
                                 'context': body[max(0, m.start()-20):
                                                m.end()+20]})
            # bare target issue number must not survive anonymisation, except
            # inside a test_issue_<n> function name (disclosed weak residual).
            tnum = iid.split('-')[-1]
            for m in re.finditer(r'(?<![A-Za-z0-9_])' + tnum + r'(?![0-9])',
                                 body):
                pre = body[max(0, m.start()-12):m.start()]
                if pre.endswith('test_issue_'):
                    continue
                hits.append({'file': fn, 'pattern': 'BARE_TARGET_ID',
                             'context': body[max(0, m.start()-30):
                                             m.end()+10]})
        leak_audit.append({'code': code, 'instance_id': iid,
                           'leak_hits': hits,
                           'leak_clean': not hits,
                           'residual_weak_blinding':
                               'test_issue_<n> function names retained '
                               '(needed to read the test)'})

    # Sealed map (coordinator only; NOT handed to annotator).
    sealed_doc = {
        '_sealed': 'BLIND CODE -> ISSUE MAP. Keep from Annotator 2 until all '
                   'forms are submitted. Opening it early breaks blinding.',
        'shuffle_seed': SHUFFLE_SEED,
        'mapping': sealed,
    }
    (SEALED / 'g3a1_blind_code_map.json').write_text(
        json.dumps(sealed_doc, ensure_ascii=False, indent=2, sort_keys=True)
        + '\n', encoding='utf-8')
    (G3A1 / 'adjudication').mkdir(parents=True, exist_ok=True)
    (G3A1 / 'audit').mkdir(parents=True, exist_ok=True)
    (G3A1 / 'audit' / 'g3a1_dossier_leakage_audit.json').write_text(
        json.dumps(leak_audit, ensure_ascii=False, indent=2, sort_keys=True)
        + '\n', encoding='utf-8')

    n = sum(len(a['leak_hits']) for a in leak_audit)
    print('dossiers:', len(sealed), '->', DOS)
    print('blind codes:', [s['code'] + ':' + s['instance_id'].split('-')[-1]
                           for s in sealed])
    print('evidence leak hits:', n)
    for a in leak_audit:
        for h in a['leak_hits']:
            print('  LEAK', a['code'], h)
    print('sealed map ->', SEALED / 'g3a1_blind_code_map.json')


if __name__ == '__main__':
    main()
