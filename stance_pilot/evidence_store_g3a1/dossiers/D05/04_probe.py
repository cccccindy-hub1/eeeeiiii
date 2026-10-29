# Human-written symptom probe for sympy issue <ID_REDACTED>, derived ONLY from the
# public issue report (Dagger(A) * IdentityOperator() was not simplified to
# Dagger(A), unlike A * Identity). Independent of maintainer tests.
import sys
from sympy.physics.quantum import Operator, IdentityOperator, Dagger

A = Operator('A')
ident = IdentityOperator()
B = Dagger(A)
out = B * ident
if out != B:
    print('FAIL: Dagger(A)*Identity =', out, '!= Dagger(A)')
    sys.exit(1)
# control: the already-working direction must still hold
if A * ident != A:
    print('FAIL: A*Identity =', A * ident)
    sys.exit(1)
print('OK: Dagger(A)*Identity =', out)
