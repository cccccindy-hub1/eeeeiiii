# GroundedReview — Submission Finalization Readiness (v4)

Date: 2026-11-03. Manuscript: `paper_sprint/latex_g4/main_v4_submission.pdf`
(Paper Sprint v4, 24 pages: main text through p.17, references p.18,
appendix pp.19–24). This file is the submission-preparation record; it does
not change any research number or gold label.

Hard constraints honored this round: **zero new model API calls, zero new
issues, zero new experiment variants, zero git commits**; all historical
frozen artifacts were used read-only.

---

## 1. Statistical verification report (independent v2)

Script: `evidence/g4_verify_v2.py` (read-only).
Outputs: `evidence_store_g4_live/analysis_v2/g4_verification_v2.{json,md}`.
**0 verification problems.**

### 1.1 Data integrity (144 cells)
- Manifest: 144/144 slots present, serials 0–143, gold tier PROVISIONAL;
  72/72 fixed bundles; pinned bundle sha256 recomputed from raw payloads
  **144/144**; trace == raw answer **144/144**.
- Exactly one model call per cell; 0 retries, 0 errors, 0 downgrades.
- Served ids exact in all 144 cells: `gpt-4.1-mini-2025-04-14` (72),
  `deepseek-flash` (72).
- Cost independently recomputed from token usage × frozen prices:
  **US$0.807389** total (GPT 0.436376; DeepSeek 0.371013), matches run
  audit; peak ledger 0.807389 < US$2.00 hard cap; pre-call guard
  reconstructs without violation.
- Parse failures: 0/144 (independent re-parse identical).

### 1.2 Confirmatory H1 (pre-registered; per-model, never pooled)
| Model | U(A) | U(B) | b | c | exact two-sided p | paired Δ (A−B) | bootstrap 95% | CP95 for B |
|---|---|---|---|---|---|---|---|---|
| GPT-4.1-mini | 0/18 | 8/18 | 0 | 8 | **0.0078125** = 2·(1/2)^8 | −0.4444 | [−0.667, −0.222] | [0.215, 0.692] |
| DeepSeek-Flash | 0/18 | 0/18 | 0 | 0 | 1.0000000 | 0.000 | [0, 0] | [0, 0.185] |

Bootstrap B=20,000 issue-clustered, seed 20261102; CP = Clopper–Pearson.

### 1.3 Pre-registration conformance
- H1 two-sided issue-paired exact McNemar: conforms.
- Issue-cluster bootstrap: conforms (B/seed above).
- **CP per cell: v1 deviation found and closed.** v1 reported Wilson only;
  v2 reports the pre-registered Clopper–Pearson. Wilson remains in the
  frozen v1 report; nothing historical was rewritten.
- H2 (C/D) is a diagnostic gate (not confirmatory); parse-fail =
  non-ACCEPT; only H1 confirmatory; pilot/underpowered labeling — all
  conform.

### 1.4 Corrected interaction (the reported "DiD = 0.056" was wrong)
- DV must be identical across all four cells: raw binary acceptance
  Y = 1{ACCEPT}. U cannot be used because its scoring rule changes across O
  (NEED gold blocked; oracle gold visible).
- DiD_m = mean_i[(Y_B−Y_A)] − mean_i[(Y_D−Y_C)].
  GPT: (8−0)/18 − (12−13)/18 = **0.5000**.
  DeepSeek: (0−0)/18 − (12−12)/18 = **0** (C and D identical).
  Interaction DiD_GPT − DiD_DS = **0.5000**, issue bootstrap 95%
  [0.278, 0.722] (exploratory, seed 20261105).
- The v1 "0.0556" was the between-model difference of the visible-cell
  contrast mean(Y_D−Y_C) (−1/18 vs 0) — an O-visibility contrast
  mislabeled as an interaction. Correction documented in v2 and in
  §"Strata, sensitivity, and interaction" of the paper; v1 frozen.
- Between-model A/B effect difference: **0.4444**, issue-paired bootstrap
  95% **[0.222, 0.667]** (exploratory, seed 20261103). The within-GPT H1 is
  confirmatory; this contrast is not — the two must not be conflated.

### 1.5 C/D diagnostic and strata
- Unsupported ACCEPT on the 5 oracle-REJECT issues in C/D: 0/5 both models;
  CP95 [0, 0.522]. Oracle match: GPT 17/18 (C), 16/18 (D); DeepSeek 17/18
  both.
- GPT B strata: 6/13 oracle-ACCEPT unsupported (CP95 [0.192, 0.749]);
  2/5 oracle-REJECT unsupported (CP95 [0.053, 0.853]). DeepSeek 0 in both
  strata (REJECT-stratum CP95 [0, 0.522]).
- Gold-flip sensitivity: H1 endpoint condition gold is NEED by design and
  is invariant to oracle flips; C/D diagnostic agreement is label-dependent
  (flipping all 13 provisional ACCEPT labels would render C/D accepts
  unsupported: GPT 13/12, DS 12/12).

### 1.6 Items that cannot be independently verified (6, disclosed)
1. No external network capture (exclusivity rests on the runner ledger).
2. No provider billing-dashboard cross-check (USD from tokens × frozen max
   prices).
3. Served identity beyond the provider-returned id string (weights/routing).
4. Provider-internal caching across contexts (fresh inputs guaranteed by
   construction; server behavior not observable).
5. The signed identity attestation for the returned human labels (verbal
   confirmation of an independent third party only; signature not yet filed).
6. Wall-clock/timestamps from the runner only (no independent clock).

---

## 2. Issue/numbering reconciliation (19346 vs FR1/19495 vs FR2)

Verified directly against 144 raw answers:
- **19495 (FR1, oracle-ACCEPT, provisional):** GPT verdicts N/A/A/A
  (A/B/C/D), DeepSeek N/N/A/A. Both models ACCEPT in C and D, consistent
  with the provisional label. FR1 has now been ruled by the independent
  human as an **instrument-only fix** (no oracle redefinition, no rubric
  amendment).
- **19346 (separate packet; GLM said REJECT vs provisional oracle ACCEPT):**
  GPT N/N/A/R, DeepSeek N/N/R/R. It is the only oracle-ACCEPT issue any
  model rejects under C/D (DS both; GPT under D only). It has its own
  arbitration worksheet (G3-C.1 P03) and is **not** FR1. The human arbiter
  records **REJECT** (packet-level field; dedicated card blank); adopted
  only in the human-reviewed S1 scenario, not mass-promoted.
- **FR2** = whether the two oracle-REJECT issues 14248 and 15875 share one
  disjunctive REJECT standard; the independent human rules **same
  standard**, no rubric amendment. Both are ACCEPTed by GPT only in
  cell B; both models REJECT them in C and D.
- Paper corrections made: §Threats FR1 bullet (had falsely said both models
  REJECT 19495 under C/D); §G4 C/D paragraph rewritten; a frozen-v1 internal
  "DiD 0.056" sentence corrected; full 18-issue grid added as Appendix
  Table 16. No historical evidence file was modified.

## 3. Human gold status (2026-11-08 return; gold stays PROVISIONAL pending signature)
- Independent third-party return received and archived under
  `paper_sprint/human/returns/` (workbench JSON sha256
  `decd50a8…f097`; CSV `ae5f68aa…c39c`). Read-only verification: 144/144
  embedded evidence files byte-identical to frozen packets; 18/18 blind
  labels locked; blind vs provisional oracle **17/18**, vs GLM 16/18.
- FR1 = **instrument_fix**, FR2 = **same_standard** (human; both agree
  with GLM; no rubric amendments). 19346 human arbiter = **REJECT**
  (recorded in S1 scenario only). 15875 human blind ACCEPT vs oracle/GLM
  REJECT has **no arbiter verdict**: frozen REJECT retained, disagreement
  disclosed. 19495 blind lock retains its 2026-11-01 timestamp by
  coordinator decision (label identical to oracle; no number changes).
- The hand-edited returned CSV had its oracle column deleted; the workbench
  JSON is authoritative and a corrected canonical CSV was regenerated.
- Records: `evidence_store_human_gold/adjudication_v1/` (integrity) and
  `adjudication_v2/` (final per-issue labels; S0/S1 recomputation). Under
  S1 (6 rejects): GPT C unsupported 1/6 (19346), match 16/18; GPT D match
  17/18; DeepSeek C/D match **18/18**. H1 (p=0.0078125), paired delta and
  all exploratory CIs are numerically invariant (gold-independent).
- No gold was fabricated or mass-promoted. **Pre-submission action:**
  collect the signed annotator/arbiter attestation (name, role,
  independence, date) and, if desired, an arbiter verdict for 15875;
  then issue a versioned gold promotion. The v5 manuscript reports S0 as
  primary and S1 separately (`main_v5_human_gold.pdf`).

---

## 4. Final submission checklist

Target venue is **not yet chosen**, so venue-specific values below are
action items, not assumptions. No deadlines or requirements are invented.

### 4.1 Format and scope
- [ ] Select target venue/track and replace the generic preamble
      (`article`, 11pt, 1in margins) with that venue's exact template and
      bibliography style (currently `natbib` + `plainnat`, `references.bib`).
- [ ] Enforce that venue's page limit for main text; current main text is
      ~17 pages in the generic format (references p.18; appendix 19–24).
- [ ] Confirm reproducibility-figure policy (native TikZ is editable; keep
      source, rasterize only if required).
- [ ] Set non-anonymous title block only for a camera-ready; current
      `\author{Anonymous submission}` is double-blind ready.
- [ ] Remove the working `\date{... Paper Sprint v4 ...}` line before
      submission; verify headers/footers carry no author metadata in PDF
      properties (Author/Creator fields).
- [ ] Balance section lengths after template conversion; re-float all
      tables/figures; regenerate the List of Tables if the venue wants one.

### 4.2 Anonymization
- [ ] No file paths with user names in the PDF (checked: none in .tex/.bib);
      re-grep after any edit (`guoci`, home dirs, host names).
- [ ] References: self-citations must use third person per venue policy.
- [ ] Data/code release: scrub git remotes, commit metadata, and any
      account/key strings from the released archive; served model ids are
      provider-public and safe; keep cost ledgers (no personal data).
- [ ] AI-use disclosure: the GLM-4.6 auxiliary pre-annotation was
      research-excluded (not an annotator, not human gold); declare model
      assistance in writing/analysis truthfully per venue policy.

### 4.3 Content claims (locked to v2 verification)
- [ ] Abstract, §G4, Table 11, and conclusion all state 0/18→8/18,
      p=0.0078, CI [−0.667,−0.222], DeepSeek 0/18 (p=1.0) — verified.
- [ ] CP intervals present; Wilson-vs-CP deviation disclosed; exploratory
      model contrasts explicitly labeled (Table 12 evidence-grade table).
- [ ] No sentence implies DeepSeek's null is evidence of absence.
- [ ] PROVISIONAL gold appears wherever C/D agreement or oracle strata are
      interpreted; human review status stated (FR1/FR2 closed; 19346 arbiter
      REJECT in S1 only; 15875 open; signed attestation pending).
- [ ] G4 vs G3-B.3 compared narratively only; no pooled tests.
- [ ] Six unverifiable items remain disclosed (Appendix E).

### 4.4 Data availability and reproducibility
- [ ] Choose release scope: (a) code `evidence/*.py`, build/run/verify
      scripts; (b) frozen inputs `evidence_store_g4_sufficiency/` (bundles,
      manifest, payload hashes, gate, preregistration + addendum);
      (c) outputs `evidence_store_g4_live/` (144 raw-first records,
      traces, runs/audit, analysis v1, analysis_v2, freeze manifests);
      (d) human packets, returned workbench JSON/CSV (archived with
      sha256), adjudication v1/v2 records and corrected canonical CSV).
- [ ] Verify SymPy upstream license/attribution for redistributed issue
      snippets/patches; provide upstream URLs and commit ids.
- [ ] Reproduce-from-freeze command documented (offline, $0): table/figure
      builders plus `uv run --offline -m evidence.g4_verify_v2`; state
      live calls cannot be re-run identically without budget
      authorization, and that results are keyed to served ids and the
      frozen price sheet.
- [ ] Add a top-level REPRODUCE/README in the release bundle mapping every
      paper number to the producing script and frozen store.
- [ ] SHA-256 manifest of the release (pattern:
      `evidence_store_g4_live/freeze/g4live_freeze_manifest_v2.json`,
      477 files; 468 shared with v1; the only hash changes are the four
      intentionally edited manuscript files).

### 4.5 PDF, references, author statements
- [ ] Clean compile in the venue toolchain (tectonic currently: 0 errors,
      no undefined citations; only minor overfull/underfull hbox warnings).
- [ ] Font embedding check in the final toolchain; hyperlinks render;
      table 12/16 margin-fit verified visually.
- [ ] Every bib entry exists and is cited; no "??" refs; URLs/DOIs alive;
      no fabricated venue facts in the manuscript.
- [ ] Statements prepared if required: funding (none to declare),
      conflicts, ethics (paid API use disclosed; no human-subjects data;
      independent human annotation obtained, signed attestation pending),
      reproducibility/artifacts, AI-use.
- [ ] Final number pass: a diff of every numeric token in the PDF against
      `g4_verification_v2.json` (0.807389, 144, 0/18, 8/18, 0.0078125,
      −0.444, [−0.667,−0.222], [0.215,0.692], [0,0.185], 0.500,
      [0.278,0.722], 0.444, [0.222,0.667], 17/18, 16/18, 0/5, 13, 5).

---

## 5. Three trim plans (no target fixed; limits are plan inputs, not venue facts)

### 5.1 Short paper (plan target: ~4–6 pages main + optional appendix)
Keep, in order: (1) three-way decision + dual gold definition
(Oracle/Condition); (2) G4 design identification paragraph + 2×2 cell
table; (3) H1 table + the two GPT/DeepSeek result paragraphs; (4) evidence
grade table restricted to 4 rows; (5) limitations (PROVISIONAL, n=18, one
repo, yoked, narrow construct).
Cut to one-paragraph mentions: G3 ten-issue associational results and the
9/10→1/10 corrective replication (keep as motivation); all ablations;
case studies; C/D detail (single sentence + 0/5); strata table; execution
engineering; G3-C.1. Move per-issue grids, provenance, run logs, budgets,
and the six unverifiable items to a supplement/URL.
Figures: keep Figure 5 (GPT paired transitions); drop Figure 6.

### 5.2 Workshop (plan target: ~6–9 pages + appendix)
Everything in 5.1, plus: condensed related work; a short results section
covering the corrective replication and 7/10 restricted-cell finding with
one summary table; G3-C.1 8-issue replication as one paragraph; full C/D
diagnostic subsection; strata/sensitivity subsection. Keep Figures 5–6.
Workshop framing can emphasize the framework + audit methodology
(pre-registration, caps, raw-first persistence, read-only v2
re-verification) as a contribution. Appendix allowed: keep Tables 2/16
grids and Appendix E provenance.

### 5.3 Full paper (plan target: ~10–14 pages two-column main + appendix)
Current content already covers this scope; in a two-column venue template
the ~17 one-column pages compress toward the target without cuts, and then:
keep benchmark/conditions/setup intact; retain all G3 results and case
studies but tighten engineering-readiness prose into a table; keep all five
G4 tables and Figures 5–6; preserve the full limitations list and
evidence-grade table; Appendix A–E carry grids, readiness, provenance, v2
verification, and the human handoff. If a venue counts appendix pages,
move Table 16 and v2 detail to an artifact repository.

Common to all three: H1 wording stays confirmatory/per-model; model
contrast stays exploratory; PROVISIONAL stays everywhere; no target-deadline
language is to be added until a venue is chosen.

---

## 6. Readiness summary

**Ready now:** statistical record (independently recomputed; one
pre-registration deviation found and corrected in a versioned v2 with v1
frozen); the mislabelled interaction corrected; case/numbering confusion
(19346 vs 19495/FR1 vs FR2) resolved in the manuscript; complete claim
audit (C1–C8) with exact intervals; 144-cell integrity verification;
anonymous, clean-compiling v5 PDF (25 pages) with the independent human
review section, S0/S1 table, evidence-grade table and full appendix grids;
v2 freeze manifest plus human-gold v3 manifest with zero evidence-hash drift.

**Blocking before actual submission:** (1) choose venue/track → apply
template and page budget via one of §5; (2) file the signed independent
annotator/arbiter attestation (and optionally an arbiter verdict for 15875)
before any gold promotion — the v5 manuscript already reports the human
review under PROVISIONAL framing with S0 primary and S1 separate, so
submission can proceed without promotion; (3) assemble and hash
the public release bundle and write the release README; (4) final
anonymization/metadata sweep and author statements.

**Versioned artifacts:**
- Paper: `paper_sprint/latex_g4/main_v5_human_gold.pdf` (25 pages; v4
  submission PDF, v3 and v1 G3-B.3 frozen PDFs all untouched).
- Statistics: `evidence_store_g4_live/analysis_v2/g4_verification_v2.json`
  / `.md` (v1 `analysis/` untouched).
- Freeze: `evidence_store_g4_live/freeze/g4live_freeze_manifest_v2.json`
  (v1 manifest untouched; shared files hash-identical except the four
  deliberately edited manuscript source files), extended by
  `evidence_store_human_gold/freeze/human_gold_freeze_manifest_v3.json`
  (37 files; 24 shared with v2, 15 unchanged, 9 deliberate v4→v5 manuscript
  and readiness edits, **zero illegal evidence drift**; frozen v1/v3/v4 PDFs
  hash-identical).
