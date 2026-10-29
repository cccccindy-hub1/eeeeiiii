# Human-written symptom probe for sympy issue 19495, derived ONLY from the
# public issue report: substituting a concrete value into a ConditionSet whose
# base set is an ImageSet in the SAME substituted symbol over-substitutes the
# ConditionSet's OWN bound variable x. The issue report shows the plain
#   cs.subs(y, Rational(1, 3))
# result as the malformed
#   {1/3 | 1/3 in {2*pi*n + asin(1/3) | n in Z}  and  1/3 in {...}}
# i.e. ConditionSet(1/3, ...) -- the dummy x was replaced by 1/3. The same
# report demonstrates the CORRECT reference result via xreplace / simultaneous
# subs, which already worked and collapses the (now-true) condition to the base
# ImageSet:
#   {2*pi*n + asin(1/3) | n in Z}.
# Independent of the maintainer test_patch / test_subs_CondSet.
import sys
from sympy import (symbols, Rational, pi, asin, Interval, ConditionSet,
                   Contains, imageset, Lambda, S, Symbol)

x, y, n = symbols('x y n')
cs = ConditionSet(x, Contains(y, Interval(-1, 1)),
                  imageset(Lambda(n, 2 * n * pi + asin(y)), S.Integers))

out = cs.subs(y, Rational(1, 3))
# The report itself shows these already give the correct answer at baseline.
ref_xreplace = cs.xreplace({y: Rational(1, 3)})
ref_simul = cs.subs({y: Rational(1, 3)}, simultaneous=True)
print('before          :', cs)
print('plain subs      :', out)
print('xreplace ref    :', ref_xreplace)
print('simultaneous ref:', ref_simul)

# (1) The bound dummy variable of a surviving ConditionSet must stay a Symbol.
#     The bug over-substitutes x -> 1/3, yielding ConditionSet(1/3, ...).
if isinstance(out, ConditionSet) and not isinstance(out.args[0], Symbol):
    print('FAIL: ConditionSet bound variable was over-substituted to',
          out.args[0])
    sys.exit(1)

# (2) Plain subs must agree with the report's own correct reference results.
if out != ref_xreplace or out != ref_simul:
    print('FAIL: plain .subs disagrees with the xreplace/simultaneous '
          'reference shown in the issue report')
    sys.exit(1)

# (3) The substituted symbol must be gone and the condition must have resolved
#     away from y entirely (no free y anywhere).
if y in out.free_symbols:
    print('FAIL: free symbol y still present after subs:', out.free_symbols)
    sys.exit(1)

print('OK: ConditionSet.subs no longer over-substitutes the bound variable')
