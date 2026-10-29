# Human-written symptom probe for sympy issue 24443, derived ONLY from the
# public issue report (homomorphism construction on a PermutationGroup wrongly
# rejected the identity images generators -> generators). Independent of tests.
import sys
from sympy.combinatorics import DihedralGroup
from sympy.combinatorics.homomorphisms import homomorphism

D3 = DihedralGroup(3)
try:
    T = homomorphism(D3, D3, D3.generators, D3.generators)
except Exception as e:  # noqa: BLE001
    print('FAIL: identity homomorphism rejected:', type(e).__name__, e)
    sys.exit(1)
# T must map the identity to the identity (basic homomorphism property)
if T(D3.identity) != D3.identity:
    print('FAIL: homomorphism does not map identity to identity')
    sys.exit(1)
print('OK: identity homomorphism on D3 constructed:', T)
