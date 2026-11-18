# Human gold adjudication record v2 (2026-11-08)

Versioned record; v1 verification and all frozen evidence remain untouched.

## 1. Identity and attestation
- Annotator: independent third party (coordinator verbal confirmation, in-session 2026-11-08)
- Signed attestation: **NOT YET OBTAINED**
- Pre-submission action: collect signed statement with name, role/competence, independence and date; until then HUMAN_CONFIRMED labels are not upgraded in the manuscript
- 19495 note: blind lock timestamp 2026-11-01 (author quick-look session, research_excluded); retained by explicit coordinator decision; label equals provisional oracle so no statistic changes

## 2. Focused reviews (human decisions)
- **FR1** -> `instrument_fix` (GLM: instrument_fix, agree=True); rubric amendment=no — the test_subs_CondSet assertion change repaired the test instrument only; the acceptability oracle was not redefined; 19495 ACCEPT label stands
- **FR2** -> `same_standard` (GLM: same_standard, agree=True); rubric amendment=no — both REJECTs apply one disjunctive standard (decisive P2P regression on inputs the base handled); no split pre-registration required

## 3. Per-issue final labels
| issue | prov. oracle | GLM | human blind | human arbiter | final label | basis | state |
|---|---|---|---|---|---|---|---|
| 14248 | REJECT | REJECT | REJECT | — | **REJECT** | human blind agrees with provisional oracle | HUMAN_CONFIRMED_PENDING_SIGNATURE |
| 19495 | ACCEPT | ACCEPT | ACCEPT | — | **ACCEPT** | provisional label confirmed by human blind (2026-11-01 lock retained by coordinator decision); FR1 instrument-fix decision | HUMAN_CONFIRMED_PENDING_SIGNATURE |
| 19346 | ACCEPT | REJECT | ACCEPT | REJECT | **REJECT** | HUMAN_ARBITER_OVERRIDE (returned JSON P03 arb; dedicated 19346 card left blank) | CANDIDATE_PENDING_SIGNED_ATTESTATION |
| 19040 | ACCEPT | ACCEPT | ACCEPT | — | **ACCEPT** | human blind agrees with provisional oracle | HUMAN_CONFIRMED_PENDING_SIGNATURE |
| 16886 | ACCEPT | ACCEPT | ACCEPT | — | **ACCEPT** | human blind agrees with provisional oracle | HUMAN_CONFIRMED_PENDING_SIGNATURE |
| 19637 | ACCEPT | ACCEPT | ACCEPT | — | **ACCEPT** | human blind agrees with provisional oracle | HUMAN_CONFIRMED_PENDING_SIGNATURE |
| 22914 | ACCEPT | ACCEPT | ACCEPT | — | **ACCEPT** | human blind agrees with provisional oracle | HUMAN_CONFIRMED_PENDING_SIGNATURE |
| 15875 | REJECT | REJECT | ACCEPT | — | **REJECT** | FROZEN_PROVISIONAL_KEPT; human blind ACCEPT disagreement unresolved (no arbiter); FR2 same-standard decision supports the REJECT | DISPUTED_PROVISIONAL |
| 24443 | ACCEPT | ACCEPT | ACCEPT | — | **ACCEPT** | human blind agrees with provisional oracle | HUMAN_CONFIRMED_PENDING_SIGNATURE |
| 13615 | ACCEPT | ACCEPT | ACCEPT | — | **ACCEPT** | human blind agrees with provisional oracle | HUMAN_CONFIRMED_PENDING_SIGNATURE |
| 19783 | REJECT | REJECT | REJECT | — | **REJECT** | human blind agrees with provisional oracle | HUMAN_CONFIRMED_PENDING_SIGNATURE |
| 20590 | ACCEPT | ACCEPT | ACCEPT | — | **ACCEPT** | human blind agrees with provisional oracle | HUMAN_CONFIRMED_PENDING_SIGNATURE |
| 17630 | REJECT | REJECT | REJECT | — | **REJECT** | human blind agrees with provisional oracle | HUMAN_CONFIRMED_PENDING_SIGNATURE |
| 21847 | ACCEPT | ACCEPT | ACCEPT | — | **ACCEPT** | human blind agrees with provisional oracle | HUMAN_CONFIRMED_PENDING_SIGNATURE |
| 15349 | ACCEPT | ACCEPT | ACCEPT | — | **ACCEPT** | human blind agrees with provisional oracle | HUMAN_CONFIRMED_PENDING_SIGNATURE |
| 24213 | ACCEPT | ACCEPT | ACCEPT | — | **ACCEPT** | human blind agrees with provisional oracle | HUMAN_CONFIRMED_PENDING_SIGNATURE |
| 17318 | REJECT | REJECT | REJECT | — | **REJECT** | human blind agrees with provisional oracle | HUMAN_CONFIRMED_PENDING_SIGNATURE |
| 13974 | ACCEPT | ACCEPT | ACCEPT | — | **ACCEPT** | human blind agrees with provisional oracle | HUMAN_CONFIRMED_PENDING_SIGNATURE |

Agreement: {"blind_labels_locked": "18/18", "human_blind_vs_provisional_oracle": "17/18", "human_blind_vs_glm": "16/18", "disagreements_vs_oracle": ["15875"], "disagreements_vs_glm": ["19346", "15875"]}

## 4. Open protocol items
- signed annotator/arbiter attestation missing
- 15875 human-vs-oracle disagreement has no arbiter verdict
- 19346 dedicated arbitration card blank (packet-level arb used)
- per-packet time and confidence fields empty (18/18)
- two contradictory GLM "agree" clicks on P03/P08 (verbal labels in JSON remain authoritative)

## 5. G4 figures under both label scenarios
### S0 frozen provisional vs S1 human-reviewed (ARB-1)
| model | cell | S0 unsupported (x/n) | S0 match | S1 unsupported (x/n) | S1 match |
|---|---|---|---|---|---|
| gpt-4.1-mini | A | 0/5 | 0/18 | 0/6 | 0/18 |
| gpt-4.1-mini | B | 2/5 | 6/18 | 2/6 | 6/18 |
| gpt-4.1-mini | C | 0/5 | 17/18 | 1/6 | 16/18 |
| gpt-4.1-mini | D | 0/5 | 16/18 | 0/6 | 17/18 |
| deepseek-flash | A | 0/5 | 0/18 | 0/6 | 0/18 |
| deepseek-flash | B | 0/5 | 0/18 | 0/6 | 0/18 |
| deepseek-flash | C | 0/5 | 17/18 | 0/6 | 18/18 |
| deepseek-flash | D | 0/5 | 17/18 | 0/6 | 18/18 |

- H1 and exploratory contrasts are identical under S0 and S1 (gold-independent); see record JSON for full CP intervals.
