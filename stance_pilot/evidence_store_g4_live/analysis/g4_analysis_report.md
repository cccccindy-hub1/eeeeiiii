# G4 Controlled Intervention — Independent Analysis Report

- Analysis: read-only, re-derived from frozen raw records (144 live cells).
- Gold: PROVISIONAL; annotator2 NOT_OBTAINED.
- Models reported SEPARATELY; no pooling.
- Primary endpoint H1: unsupported acceptance A vs B, issue-paired two-sided exact McNemar.

## Served model IDs
- GPT-4.1-mini: {'gpt-4.1-mini-2025-04-14': 72}
- DeepSeek-Flash: {'deepseek-flash': 72}
- independent re-parse mismatches vs runner: []

## GPT-4.1-mini

| Cell | ACCEPT | REJECT | NEED_EVIDENCE | INVALID | U (unsupported accept) | Wilson 95% |
|---|---|---|---|---|---|---|
| A | 0 | 0 | 18 | 0 | 0/18 (0.0%) | [0.0, 17.6] |
| B | 8 | 0 | 10 | 0 | 8/18 (44.4%) | [24.6, 66.3] |
| C | 13 | 4 | 1 | 0 | 0/18 (0.0%) | [0.0, 17.6] |
| D | 12 | 5 | 1 | 0 | 0/18 (0.0%) | [0.0, 17.6] |

**H1 exact McNemar:** b(A only)=0, c(B only)=8, discordant n=8, two-sided p=0.0078; paired diff=-0.444, issue-bootstrap 95% CI [-0.667, -0.222]. Significant(0.05, two-sided)=True.

A->B ternary transitions: NEED_EVIDENCE->ACCEPT: 8, NEED_EVIDENCE->NEED_EVIDENCE: 10

**C/D diagnostic:** ternary C={'ACCEPT': 13, 'REJECT': 4, 'NEED_EVIDENCE': 1}, D={'ACCEPT': 12, 'REJECT': 5, 'NEED_EVIDENCE': 1}; oracle match C 17/18, D 16/18; unsupported on 5 oracle-REJECT issues C=0, D=0 (paired discordants 0/0, exact p=1.0000).

Strata (13 oracle-ACCEPT / 5 oracle-REJECT; n=5 is underpowered):
- oracle_ACCEPT_n13: A 0/13, B 6/13, C 0/13, D 0/13
- oracle_REJECT_n5: A 0/5, B 2/5, C 0/5, D 0/5

Sensitivity: parse failures=0; complete-case equals primary (no parse failures). Gold-flip extremes C/D: {'U_C': 0, 'U_D': 0} / {'U_C': 13, 'U_D': 12}.

Cost (recomputed raw): $0.4364; tokens in=1052816, out=9531.

Historical G3-B.3 comparison is narrative only (different protocol/inputs/task; not pooled): {'strict_accept': '7/10'}.

## DeepSeek-Flash

| Cell | ACCEPT | REJECT | NEED_EVIDENCE | INVALID | U (unsupported accept) | Wilson 95% |
|---|---|---|---|---|---|---|
| A | 0 | 0 | 18 | 0 | 0/18 (0.0%) | [0.0, 17.6] |
| B | 0 | 0 | 18 | 0 | 0/18 (0.0%) | [0.0, 17.6] |
| C | 12 | 6 | 0 | 0 | 0/18 (0.0%) | [0.0, 17.6] |
| D | 12 | 6 | 0 | 0 | 0/18 (0.0%) | [0.0, 17.6] |

**H1 exact McNemar:** b(A only)=0, c(B only)=0, discordant n=0, two-sided p=1.0000; paired diff=+0.000, issue-bootstrap 95% CI [+0.000, +0.000]. Significant(0.05, two-sided)=False.

A->B ternary transitions: NEED_EVIDENCE->NEED_EVIDENCE: 18

**C/D diagnostic:** ternary C={'ACCEPT': 12, 'REJECT': 6, 'NEED_EVIDENCE': 0}, D={'ACCEPT': 12, 'REJECT': 6, 'NEED_EVIDENCE': 0}; oracle match C 17/18, D 17/18; unsupported on 5 oracle-REJECT issues C=0, D=0 (paired discordants 0/0, exact p=1.0000).

Strata (13 oracle-ACCEPT / 5 oracle-REJECT; n=5 is underpowered):
- oracle_ACCEPT_n13: A 0/13, B 0/13, C 0/13, D 0/13
- oracle_REJECT_n5: A 0/5, B 0/5, C 0/5, D 0/5

Sensitivity: parse failures=0; complete-case equals primary (no parse failures). Gold-flip extremes C/D: {'U_C': 0, 'U_D': 0} / {'U_C': 12, 'U_D': 12}.

Cost (recomputed raw): $0.3710; tokens in=1159086, out=19406.

Historical G3-B.3 comparison is narrative only (different protocol/inputs/task; not pooled): {'strict_accept': '9/10 then 1/10'}.

## Exploratory O x M interaction
```json
{
  "per_model": {
    "gpt-4.1-mini": {
      "delta_O_accept_visibility_rejects": 0.0,
      "delta_O_accept_visibility_all18_descriptive": -0.05555555555555555
    },
    "deepseek-flash": {
      "delta_O_accept_visibility_rejects": 0.0,
      "delta_O_accept_visibility_all18_descriptive": 0.0
    }
  },
  "difference_in_differences_all18": 0.05555555555555555,
  "caution": "Exploratory only; 18 issues (5 oracle-REJECT), no power for model interaction; no causal attribution beyond design."
}
```

## Budget audit
```json
{
  "runner_audit_total_usd": 0.807389,
  "recomputed_from_raw_total_usd": 0.807389,
  "per_model_recomputed_usd": {
    "gpt-4.1-mini": 0.436378,
    "deepseek-flash": 0.371011
  },
  "per_model_audit_usd": {
    "deepseek-flash": 0.371011,
    "gpt-4.1-mini": 0.436378
  },
  "hard_cap_usd": 2.0,
  "within_cap": true,
  "calls_per_cell": 1,
  "retries_per_cell": 0,
  "gold_status": "PROVISIONAL; annotator2 NOT_OBTAINED"
}
```
