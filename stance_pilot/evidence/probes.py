"""Executable symptom probes, one per pilot instance.

Each probe is a small script derived directly from the user-reported symptom in the
issue (NOT from the maintainer test_patch). Executed both before and after the
candidate patch. issue_addressed := the post-patch probe exits 0 AND the pre-patch
probe did not (the latter guards against probes that pass vacuously at baseline).

A probe must be self-contained, use only public sympy API, and exit 0 on expected
behavior / non-zero on wrong behavior or exception.
"""

PROBES = {
'sympy__sympy-13798': r'''
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
''',

'sympy__sympy-14531': r'''
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
''',

'sympy__sympy-16450': r'''
# issue: posify must preserve the is_finite assumption
import sys
from sympy import Symbol, posify
x = Symbol("x", finite=True)
xp, _ = posify(x)
if not xp.is_finite:
    print("FAIL: posified symbol lost finite assumption:", xp._assumptions)
    sys.exit(1)
print("OK: xp.is_finite =", xp.is_finite)
''',

'sympy__sympy-16597': r'''
# issue: an even symbol must be inferred finite
import sys
from sympy import Symbol
m = Symbol("m", even=True)
if m.is_finite is not True:
    print("FAIL: m.is_finite =", m.is_finite)
    sys.exit(1)
print("OK: m.is_finite =", m.is_finite)
''',

'sympy__sympy-17139': r'''
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
''',

'sympy__sympy-18199': r'''
# issue: nthroot_mod must return root x=0 when a % p == 0. At baseline the literal
# zero case raised ValueError("Log does not exist"); the 17*17 case happened to work.
import sys
from sympy.ntheory.residue_ntheory import nthroot_mod
try:
    r_list = nthroot_mod(0, 4, 17, all_roots=True)
    r_scalar = nthroot_mod(0, 4, 17)
except Exception as e:
    print("FAIL: zero root path raised:", type(e).__name__, e)
    sys.exit(1)
if r_list != [0] or r_scalar != 0:
    print("FAIL: expected [0]/0, got", r_list, r_scalar)
    sys.exit(1)
print("OK: zero root returned:", r_list, r_scalar)
''',

'sympy__sympy-18211': r'''
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
''',

'sympy__sympy-20428': r'''
# issue: a complicated constant that is algebraically zero is not recognized:
# Poly(<const>, x) must equal Poly(0, x, domain='EX'); downstream clear_denoms then
# produces an unstripped zero DMP and division by it raises ZeroDivisionError.
import sys
from sympy import symbols, Poly, S, sqrt
x = symbols("x")
f = Poly(-117968192370600*18**(S(1)/3)/(217603955769048*(24201 +
    253*sqrt(9165))**(S(1)/3) + 2273005839412*sqrt(9165)*(24201 +
    253*sqrt(9165))**(S(1)/3)) - 15720318185*2**(S(2)/3)*3**(S(1)/3)*(24201
    + 253*sqrt(9165))**(S(2)/3)/(217603955769048*(24201 + 253*sqrt(9165))**
    (S(1)/3) + 2273005839412*sqrt(9165)*(24201 + 253*sqrt(9165))**(S(1)/3))
    + 15720318185*12**(S(1)/3)*(24201 + 253*sqrt(9165))**(S(2)/3)/(
    217603955769048*(24201 + 253*sqrt(9165))**(S(1)/3) + 2273005839412*
    sqrt(9165)*(24201 + 253*sqrt(9165))**(S(1)/3)) + 117968192370600*2**(
    S(1)/3)*3**(S(2)/3)/(217603955769048*(24201 + 253*sqrt(9165))**(S(1)/3)
    + 2273005839412*sqrt(9165)*(24201 + 253*sqrt(9165))**(S(1)/3)), x)
if f != Poly(0, x, domain='EX'):
    print("FAIL: zero constant not recognized as Poly(0)")
    sys.exit(1)
print("OK: constant recognized as zero poly")
''',
}

def probe_source(instance_id: str) -> str:
    return PROBES[instance_id]
