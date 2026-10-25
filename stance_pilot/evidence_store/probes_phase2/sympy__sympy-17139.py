
# issue: simplify(cos(x)**I) raised "Invalid comparison of complex I"
import sys
from sympy import cos, simplify, Symbol, I
x = Symbol("x")
try:
    out = simplify(cos(x)**I)
except Exception as e:
    print("FAIL: simplify raised:", type(e).__name__, e)
    sys.exit(1)
print("OK: simplify ->", out)
