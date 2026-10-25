
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
