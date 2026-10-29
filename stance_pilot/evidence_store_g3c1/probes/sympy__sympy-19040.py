# Human-written symptom probe for sympy issue 19040, derived ONLY from the
# public issue report: factoring with extension=True drops the factor (y - 1),
# yielding x - 1 which is no longer equal to the input polynomial. Independent
# of the maintainer test_patch / test_issue_5786.
import sys
from sympy import symbols, expand, factor, simplify

x, y = symbols('x y')
z = expand((x - 1) * (y - 1))
plain = factor(z)
ext = factor(z, extension=[__import__('sympy').I])
print('input      :', z)
print('factor     :', plain)
print('factor ext :', ext)
# extension factoring must preserve the value (retain the y-1 factor)
if simplify(expand(ext) - z) != 0:
    print('FAIL: factor(extension=[I]) dropped a factor; expansion =',
          expand(ext))
    sys.exit(1)
print('OK: factor with extension preserves the polynomial')
