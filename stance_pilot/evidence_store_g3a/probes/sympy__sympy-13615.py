# Human-written symptom probe for sympy issue 13615, derived from the public
# issue report and aligned to the maintainer-accepted resolution (maintainer
# test_Complement): the number 2 inside the interval must be removed while the
# free symbols remain as a Complement against the interval (their membership is
# unknown), rather than wrongly collapsing to FiniteSet(x, y).
#   buggy baseline : Complement(FiniteSet(x,y,2), I) == FiniteSet(x, y)
#   fixed          : == Complement(FiniteSet(x, y), I)
import sys
from sympy import FiniteSet, Interval, Complement, symbols

x, y = symbols('x y')
I = Interval(-10, 10)
got = Complement(FiniteSet(x, y, 2), I)
expect = Complement(FiniteSet(x, y), I)
if got != expect:
    print('FAIL: Complement mixed symbols/numbers:', got, '!=', expect)
    sys.exit(1)
print('OK: Complement =', got)
