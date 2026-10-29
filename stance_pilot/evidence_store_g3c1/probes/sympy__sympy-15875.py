# Human-written symptom probe for sympy issue 15875, derived ONLY from the
# public issue report: Add.is_zero wrongly returns False for a complex integer
# that is provably zero. is_zero must never give the wrong answer (False for
# an expression that simplifies to 0). Independent of the maintainer
# test_patch / test_Add_is_zero.
import sys
from sympy import I, simplify

e = -2 * I + (1 + I) ** 2
print('expr         :', e)
print('simplify     :', simplify(e))
print('e.is_zero    :', e.is_zero)
print('simplified 0 :', simplify(e).is_zero)
# (1+I)**2 == 2*I, so the expression is exactly 0; is_zero must not say False
if e.is_zero is False:
    print('FAIL: is_zero wrongly False for provably-zero complex Add')
    sys.exit(1)
if simplify(e) != 0:
    print('FAIL: expression does not simplify to 0')
    sys.exit(1)
print('OK: is_zero is not wrongly False for the zero complex Add')
