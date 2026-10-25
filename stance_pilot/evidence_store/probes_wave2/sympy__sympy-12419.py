# issue: total sum of the elements of an orthogonal M.T*M (an Identity) is
# wrongly 0 instead of n. Self-contained symptom from the issue report; only
# public sympy API. Evaluate at n=3 (concrete) to avoid symbolic-sum variance.
import sys
from sympy import MatrixSymbol, Sum, Symbol, symbols
from sympy import Q as Query
from sympy.assumptions import assuming, refine

n = Symbol('n', integer=True, positive=True)
i, j = symbols('i j', integer=True)
M = MatrixSymbol('M', n, n)
with assuming(Query.orthogonal(M)):
    e = refine((M.T * M).doit())
out = Sum(Sum(e[i, j], (i, 0, n - 1)), (j, 0, n - 1)).subs(n, 3).doit()
if out != 3:
    print("FAIL: total sum of identity elements:", out)
    sys.exit(1)
print("OK: total sum of identity elements =", out)
