# Human gold return — independent verification & adjudication record v1 (2026-11-08)

All frozen inputs read-only. This record promotes no gold by itself.

## 1. Source files (sha256)
- `human_review_workbench_return_20261108.json` — 8555 bytes — `decdc50a8d3839069ae54de9287bf74640d5037d2fc271f702305040c08ef097`
- `human_review_tracking_filled_return_20261108.csv` — 1054 bytes — `ae5f68aac87e4c858ccb3be53265e2fef90e07e68d1a014d7e649081cac3c39c`
- `workbench_html` — 1528737 bytes — `3593aff3523411c9d85cec7a149c5c876432df2de491f97760bfe2ddd27d8a3f`

## 2. Blind-packet integrity
- embedded evidence files: 144
- embedded sha256 matches frozen disk file: 144
- decoded text matches frozen disk file: 144
- full byte+text identity: 144
- sealed packet->instance mapping ok: True

## 3. Reconciliation (18 packets)
| set | packet | issue | oracle (prov.) | GLM | human blind | vs oracle | vs GLM | GLM-click | arb | blind ts |
|---|---|---|---|---|---|---|---|---|---|---|
| G3-C.1 | P01 | 14248 | REJECT | REJECT | REJECT | agree | agree | yes |  | 2026-11-08 |
| G3-C.1 | P02 | 19495 | ACCEPT | ACCEPT | ACCEPT | agree | agree | yes |  | 2026-11-01 |
| G3-C.1 | P03 | 19346 | ACCEPT | REJECT | ACCEPT | agree | DISAGREE | yes | REJECT | 2026-11-08 |
| G3-C.1 | P04 | 19040 | ACCEPT | ACCEPT | ACCEPT | agree | agree | yes |  | 2026-11-08 |
| G3-C.1 | P05 | 16886 | ACCEPT | ACCEPT | ACCEPT | agree | agree | yes |  | 2026-11-08 |
| G3-C.1 | P06 | 19637 | ACCEPT | ACCEPT | ACCEPT | agree | agree | yes |  | 2026-11-08 |
| G3-C.1 | P07 | 22914 | ACCEPT | ACCEPT | ACCEPT | agree | agree | yes |  | 2026-11-08 |
| G3-C.1 | P08 | 15875 | REJECT | REJECT | ACCEPT | DISAGREE | DISAGREE | yes |  | 2026-11-08 |
| G3-A | P01 | 24443 | ACCEPT | ACCEPT | ACCEPT | agree | agree | yes |  | 2026-11-08 |
| G3-A | P02 | 13615 | ACCEPT | ACCEPT | ACCEPT | agree | agree | yes |  | 2026-11-08 |
| G3-A | P03 | 19783 | REJECT | REJECT | REJECT | agree | agree | yes |  | 2026-11-08 |
| G3-A | P04 | 20590 | ACCEPT | ACCEPT | ACCEPT | agree | agree | yes |  | 2026-11-08 |
| G3-A | P05 | 17630 | REJECT | REJECT | REJECT | agree | agree | yes |  | 2026-11-08 |
| G3-A | P06 | 21847 | ACCEPT | ACCEPT | ACCEPT | agree | agree | yes |  | 2026-11-08 |
| G3-A | P07 | 15349 | ACCEPT | ACCEPT | ACCEPT | agree | agree | yes |  | 2026-11-08 |
| G3-A | P08 | 24213 | ACCEPT | ACCEPT | ACCEPT | agree | agree | yes |  | 2026-11-08 |
| G3-A | P09 | 17318 | REJECT | REJECT | REJECT | agree | agree | yes |  | 2026-11-08 |
| G3-A | P10 | 13974 | ACCEPT | ACCEPT | ACCEPT | agree | agree | yes |  | 2026-11-08 |

- blind labels locked: **18/18**
- human blind vs PROVISIONAL oracle: **17/18** (disagreements: 15875)
- human blind vs GLM: **16/18** (disagreements: 19346, 15875)

## 4. Returned CSV diagnosis
- header fields 10, row field counts [9]; column-shift confirmed: **True**
- oracle column deleted by hand; all later columns shifted; JSON export is the authoritative source
- rows whose CSV "oracle" column differs from frozen oracle: 15875
- authoritative source = returned JSON; corrected canonical CSV written alongside this report.

## 5. Protocol gaps (must be closed before gold promotion)
- SIGN_NULL: no annotator name/role/attestation recorded
- FR1_PENDING: focused review on 19495 not answered
- FR2_PENDING: focused review on 14248/15875 not answered
- C19346_CARD_NULL: dedicated 19346 arbitration card not filled (a packet-level arb verdict exists instead)
- MINS_EMPTY: time not recorded on 18/18 packets (protocol requires per-packet time)
- CONF_EMPTY: confidence not recorded on 18/18 packets
- OLD_TIMESTAMP G3-C.1::P02 issue 19495: blind locked 2026-11-01T07:56:40.843Z (from the 2026-11-01 author quick-look session, then tagged research_excluded; needs a fresh independent lock)
- CONTRADICTORY_GLM_CLICK G3-C.1::P03 issue 19346: blind ACCEPT != GLM REJECT but review marked "agree"
- CONTRADICTORY_GLM_CLICK G3-C.1::P08 issue 15875: blind ACCEPT != GLM REJECT but review marked "agree"
- UNRESOLVED_DISAGREEMENT issue 15875: human ACCEPT vs oracle REJECT (GLM REJECT); no arbiter verdict

## 6. G4 recomputation — ARB-1 candidate (19346 ACCEPT->REJECT only)
reject stratum becomes 6 issues: 14248, 15875, 17318, 17630, 19346, 19783

| model | cell | raw ACCEPT | unsupported on rejects (x/n) | CP95 | oracle match | CP95 |
|---|---|---|---|---|---|---|
| gpt-4.1-mini | A | 0 | 0/6 | [0.000,0.459] | 0/18 | [0.000,0.185] |
| gpt-4.1-mini | B | 8 | 2/6 | [0.043,0.777] | 6/18 | [0.133,0.590] |
| gpt-4.1-mini | C | 13 | 1/6 | [0.004,0.641] | 16/18 | [0.653,0.986] |
| gpt-4.1-mini | D | 12 | 0/6 | [0.000,0.459] | 17/18 | [0.727,0.999] |
| deepseek-flash | A | 0 | 0/6 | [0.000,0.459] | 0/18 | [0.000,0.185] |
| deepseek-flash | B | 0 | 0/6 | [0.000,0.459] | 0/18 | [0.000,0.185] |
| deepseek-flash | C | 12 | 0/6 | [0.000,0.459] | 18/18 | [0.815,1.000] |
| deepseek-flash | D | 12 | 0/6 | [0.000,0.459] | 18/18 | [0.815,1.000] |

B-cell strata under ARB-1:
- gpt-4.1-mini: rejects 2/6 ['14248', '15875'] CP95 [0.043,0.777]; accept-stratum 6/12 CP95 [0.211,0.789]
- deepseek-flash: rejects 0/6 [] CP95 [0.000,0.459]; accept-stratum 0/12 CP95 [0.000,0.265]

- H1 A/B (McNemar p=0.0078125, paired delta, bootstrap CI) and the exploratory DiD/between-model CIs are **unchanged** (gold-independent).

### Hypothetical ARB-2 (NOT adopted; 15875 also flipped to ACCEPT)
reject stratum 5: 14248, 17318, 17630, 19346, 19783
- gpt-4.1-mini B: unsupported 1/5, oracle match 7/18
- gpt-4.1-mini C: unsupported 1/5, oracle match 15/18
- gpt-4.1-mini D: unsupported 0/5, oracle match 16/18
- deepseek-flash B: unsupported 0/5, oracle match 0/18
- deepseek-flash C: unsupported 0/5, oracle match 17/18
- deepseek-flash D: unsupported 0/5, oracle match 17/18

## 7. Promotion decision
**NOT_PROMOTED** — gold stays PROVISIONAL: identity/signature missing, arbiter independence unverifiable, FR1/FR2 unanswered, 15875 disagreement unresolved, one stale 2026-11-01 lock
Pending confirmation, candidate change: 19346 ACCEPT->REJECT
