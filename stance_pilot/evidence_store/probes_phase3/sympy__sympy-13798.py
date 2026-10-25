
# issue: latex(mul_symbol=...) should accept an arbitrary separator string
import sys
from sympy import symbols
from sympy.printing.latex import latex
x, y = symbols("x y")
out = latex(3*x**2*y, mul_symbol=r"\,")
if r"\," not in out:
    print("FAIL: custom mul_symbol not used:", out)
    sys.exit(1)
print("OK:", out)
