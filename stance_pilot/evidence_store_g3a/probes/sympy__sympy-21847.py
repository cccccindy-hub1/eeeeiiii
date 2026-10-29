# Human-written symptom probe for sympy issue 21847, derived ONLY from the
# public issue report (itermonomials with min_degrees=max_degrees=3 dropped
# mixed monomials of total degree 3). Independent of maintainer test.
import sys
import sympy as sp

x1, x2, x3 = sp.symbols('x1 x2 x3')
states = [x1, x2, x3]
got = set(sp.itermonomials(states, 3, min_degrees=3))
expect = {x1 ** 3, x2 ** 3, x3 ** 3,
          x1 ** 2 * x2, x1 ** 2 * x3, x2 ** 2 * x1, x2 ** 2 * x3,
          x3 ** 2 * x1, x3 ** 2 * x2, x1 * x2 * x3}
missing = expect - got
if missing:
    print('FAIL: missing total-degree-3 monomials:', sorted(map(str, missing)))
    sys.exit(1)
# every returned monomial must really have total degree exactly 3
for m in got:
    if sum(m.as_poly(x1, x2, x3).degree_list()) != 3:
        print('FAIL: monomial outside [3,3]:', m)
        sys.exit(1)
print('OK: itermonomials min=max=3 returns', len(got), 'monomials')
