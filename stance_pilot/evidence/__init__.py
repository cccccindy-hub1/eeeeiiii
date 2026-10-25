"""Evidence-Grounded Verification pilot.

Experimental line: does *verifiable evidence* (and independent verification tools)
help a reviewer distinguish symptom resolution from full merge acceptability?

Conditions (information/action space differs, not just prompt wording):
  T0 text only            issue + patch
  T1 author claim         T0 + untrusted coder claim
  T2 static artifact      T0 + real test artifact (readable, not queryable)
  T3 verified artifact    T2 + callable verification service (get + linkage check)
"""
