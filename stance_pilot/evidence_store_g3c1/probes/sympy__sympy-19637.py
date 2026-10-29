# Human-written symptom probe for sympy issue 19637, derived ONLY from the
# public issue report: kernS raises "UnboundLocalError: local variable 'kern'
# referenced before assignment" on ordinary input. Independent of the
# maintainer test_patch / test_kernS.
import sys
from sympy.core.sympify import kernS
from sympy import Symbol, simplify

text = "(2*x)/(x-1)"
try:
    expr = kernS(text)
except Exception as ex:  # noqa: BLE001 - UnboundLocalError reproduces symptom
    print('FAIL: kernS raised', type(ex).__name__, ex)
    sys.exit(1)
x = Symbol('x')
if simplify(expr - 2 * x / (x - 1)) != 0:
    print('FAIL: kernS returned wrong expression:', expr)
    sys.exit(1)
print('OK: kernS no crash ->', expr)
