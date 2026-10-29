BLIND PACKET P04 — GroundedReview independent patch review
============================================================
You are an independent adjudicator. Judge ONLY from the files in
this folder. Do not search the web or the issue tracker. Folder
ids are blinded; if the verbatim patch/problem text happens to
quote an upstream issue number, ignore it and do not look it up.

Files:
  01 problem statement
  02 candidate patch (the patch under review)
  03 maintainer test_patch (declared acceptance tests)
  04 declared test id sets
  05 CI FAIL_TO_PASS log (after patch)
  06 CI scoped PASS_TO_PASS log (after patch)
  07 CI PASS_TO_PASS at BASE commit (pre-patch reference)
  08 issue-symptom probe (derived from the issue text, not a
     maintainer acceptance test; a pass means the symptom is
     gone)

SCOPE NOTE: this local pilot executed only the scoped P2P subset
(06), not the entire dataset P2P list in 04; judge scoped
acceptability and say so in your reason if it matters.

Apply the rubric in 00_annotator_protocol.md and enter your label
in annotator2_labels.csv (one row per packet).
