# Human-written symptom probe for sympy issue 17318, derived from the public
# issue report. The report's headline expression was already non-crashing at
# this base_commit (returns I), but the closely related complex expression from
# the maintainer regression test still raises IndexError ("tuple index out of
# range") at baseline; an expression that cannot be denested must be returned
# unchanged rather than crash. Independent of the maintainer test file.
import sys
from sympy import sqrt, S
from sympy.simplify.sqrtdenest import sqrtdenest

I = S.ImaginaryUnit
e = 3 - sqrt(2) * sqrt(4 + I) + 3 * I
try:
    out = sqrtdenest(e)
except Exception as ex:  # noqa: BLE001 - IndexError reproduces the symptom
    print('FAIL: sqrtdenest raised', type(ex).__name__, ex)
    sys.exit(1)
# no denesting exists -> must come back equal to the input (returned unchanged)
if out != e and (out - e).simplify() != 0:
    print('FAIL: sqrtdenest changed the value:', out)
    sys.exit(1)
print('OK: sqrtdenest no crash ->', out)
