# G4 Identifiability Gate - GO / NO-GO report

- Version: `g4-sufficiency-iv-v1.1`
- Generated (UTC): 2026-11-02T08:46:48Z
- API calls: **0**, spend: **$0**, frozen artifacts modified: False
- Factors: **O** decisive outcomes (blocked/presented); **M** `fc_attestation` freshness/coverage attestation (withheld/adjudicated); **linkage constant**.
- Issues: 18 (13 ACCEPT / 5 REJECT); all linked/fresh/complete, symptom gone.

## Decision

# **GO**

eligible to request a SEPARATE written authorization for the 144-cell paid pilot (<=$2)

## G1 - G1 schema parity: PASS

identical recursive key set and byte length within +/-10% for withheld vs adjudicated F/C payloads

No failures across the 18 issues / applicable cells.

## G2 - G2 F/C non-reconstructability: PASS

withheld cells expose no run-tree hash, attestation time, declared/executed set, missing list, or negative wording that recomputes freshness/coverage

No failures across the 18 issues / applicable cells.

## G3 - G3 outcome blocking / noninterference: PASS

A/B expose no acceptance verdict, failing/regressed id, failure count, or gold; acceptance logs return the frozen strict 403

No failures across the 18 issues / applicable cells.

## G4 - G4 linkage constancy: PASS

/verify payload and symptom surface byte-identical across A/B/C/D; linkage framing never toggled

No failures across the 18 issues / applicable cells.

## G5 - G5 only-registered-factors change: PASS

F/C payloads constant within M level across rows; logs/consistency constant within row; C/D decisive outcomes identical apart from timestamp + marker; only O and fc_attestation vary

No failures across the 18 issues / applicable cells.

## G6 - G6 interaction parity: PASS

G6.1 identical tool inventory/order; G6.2 row-wise identical fixed response status/content-type sequence (A==B, C==D; steps 0-5 constant all four; steps 6-8 differ across rows ONLY by the registered O factor: frozen strict 403/json vs 200/text); G6.3 within-row system+user char delta within +/-8% (toggled tool payloads excluded)

No failures across the 18 issues / applicable cells.

Residual interaction confounds:
- A/B vs C/D differ in static-block size and log bodies; that IS the registered O factor, not an interaction confound.
- Responses are pre-rendered/fixed, so tool call COUNT cannot diverge in this first round; an interactive round where the model chooses calls would need a fresh parity audit.
- The unified tool enum lists acceptance log names even in A/B; they return the frozen strict 403, so information content is blocked but the schema is homogeneous by design.
- Equal presentation does not guarantee equal attention; fixed presentation isolates content, not the model’s allocation of attention.
- Claim scope: `fixed_presentation_only`

## Frozen statistics / execution plan

- H1: two-sided U(A) != U(B) unsupported-ACCEPT rate; sign not pre-committed
- H2: diagnostic specificity control: |U(C)-U(D)| on the 5 reject issues + oracle-match on C and D; a comparable C/D effect weakens the construct (reported, not auto-fail)
- Primary: issue-paired exact McNemar on A vs B unsupported ACCEPT indicators (discordant b/c)
- CI: issue-clustered bootstrap 95% CI of U(A)-U(B); Clopper-Pearson per cell
- Order: balanced Latin; 8 model x cell slots shuffled and cyclically shifted one slot per issue (seed 20261102)
- Budget hard cap: $2.0; 144 cells; parse: unparseable final message = non-ACCEPT; parse-fail rate reported separately

## Identified-estimand boundary (mandatory in paper)

when freshness/coverage genuinely hold (all 18 fresh=complete=true), does attestation availability change unsupported acceptance; no claim about fresh=false/coverage=false
