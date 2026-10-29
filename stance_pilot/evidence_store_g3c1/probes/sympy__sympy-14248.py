# Human-written symptom probe for sympy issue 14248, derived ONLY from the
# public issue report: a difference of MatrixSymbols is printed as a sum with
# explicit "(-1)"/"-1" coefficients instead of subtraction. Independent of the
# maintainer test_patch.
import sys
from sympy import MatrixSymbol, latex, pretty

A = MatrixSymbol('A', 2, 2)
B = MatrixSymbol('B', 2, 2)
e = A - A * B - B
s = str(e)
lat = latex(e)
pp = pretty(e)
print('str   :', s)
print('latex :', lat)
print('pretty:\n' + pp)
# buggy str   : "(-1)*B + (-1)*A*B + A"
# buggy latex : "-1 B + -1 A B + A"
# fixed printers expose subtraction terms, never a literal (-1)/-1 coefficient
if '(-1)' in s:
    print('FAIL: str prints explicit (-1) coefficients:', s)
    sys.exit(1)
if '-1' in lat:
    print('FAIL: latex prints literal -1 coefficients:', lat)
    sys.exit(1)
print('OK: MatrixSymbol difference prints with subtraction')
