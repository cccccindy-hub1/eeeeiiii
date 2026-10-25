
# issue: posify must preserve the is_finite assumption
import sys
from sympy import Symbol, posify
x = Symbol("x", finite=True)
xp, _ = posify(x)
if not xp.is_finite:
    print("FAIL: posified symbol lost finite assumption:", xp._assumptions)
    sys.exit(1)
print("OK: xp.is_finite =", xp.is_finite)
