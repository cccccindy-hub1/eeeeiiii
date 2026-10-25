# issue: Permutation cannot be subclassed: operations that build the result
# through the internal _af_new helper always return a bare Permutation, even
# when both operands are a subclass. A transposition composed with itself is
# the identity permutation, and it must keep the subclass type.
import sys
from sympy.combinatorics import Permutation


class MyPermutation(Permutation):
    pass


p = MyPermutation([1, 0, 2])
r = p * p                       # transposition squared -> identity
if list(r) != [0, 1, 2]:
    print("FAIL: p*p is not identity:", list(r))
    sys.exit(1)
if type(r) is not MyPermutation:
    print("FAIL: subclass type lost in multiplication, got", type(r).__name__)
    sys.exit(1)
print("OK: p*p keeps subclass type ->", type(r).__name__, list(r))
