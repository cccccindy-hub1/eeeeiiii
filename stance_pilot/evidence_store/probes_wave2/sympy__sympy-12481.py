# issue: Permutation constructor rejects non-disjoint cycles with ValueError;
# cycles should be applied left-to-right and the resulting permutation returned.
# [[0,1],[0,1]] applies the same transposition twice -> identity.
import sys
from sympy.combinatorics import Permutation

try:
    p = Permutation([[0, 1], [0, 1]])
except Exception as exc:
    print("FAIL: non-disjoint cycles raised:", type(exc).__name__, exc)
    sys.exit(1)
if list(p) != [0, 1]:
    print("FAIL: expected identity [0, 1], got", list(p))
    sys.exit(1)
print("OK: non-disjoint cycles ->", list(p))
