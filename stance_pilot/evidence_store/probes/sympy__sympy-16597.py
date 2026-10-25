
# issue: an even symbol must be inferred finite
import sys
from sympy import Symbol
m = Symbol("m", even=True)
if m.is_finite is not True:
    print("FAIL: m.is_finite =", m.is_finite)
    sys.exit(1)
print("OK: m.is_finite =", m.is_finite)
