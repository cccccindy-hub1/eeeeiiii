
# issue: sstr(..., sympy_integers=True) must be respected by subexpressions
import sys
from sympy import Symbol, S, Eq, Limit, sstr
x = Symbol("x")
checks = [
    (sstr(Eq(x, S(1)/2), sympy_integers=True), "Eq(x, S(1)/2)"),
    (sstr(Limit(x, x, S(1)/2), sympy_integers=True), "Limit(x, x, S(1)/2)"),
]
bad = [(got, want) for got, want in checks if want not in got]
if bad:
    for got, want in bad:
        print("FAIL: got", repr(got), "wanted substring", repr(want))
    sys.exit(1)
print("OK:", [g for g, _ in checks])
