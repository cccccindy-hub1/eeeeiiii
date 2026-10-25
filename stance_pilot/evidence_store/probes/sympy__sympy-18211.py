
# issue: Eq(n*cos(n)-3*sin(n),0).as_set() should be a ConditionSet, not raise
import sys
from sympy import Symbol, Eq, cos, sin, ConditionSet
n = Symbol("n", real=True)
try:
    out = Eq(n*cos(n) - 3*sin(n), 0).as_set()
except Exception as e:
    print("FAIL: as_set raised:", type(e).__name__, e)
    sys.exit(1)
if not isinstance(out, ConditionSet):
    print("FAIL: expected ConditionSet, got", type(out).__name__, out)
    sys.exit(1)
print("OK:", out)
