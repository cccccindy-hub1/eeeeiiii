# Human-written symptom probe for sympy issue 20590, derived ONLY from the
# public issue report (a Symbol instance regained an instance __dict__ in 1.7;
# given __slots__ it must not carry a per-instance __dict__). Independent of
# the maintainer test_patch / test_immutable.
import sys
import sympy

s = sympy.Symbol('s')
has_dict = '__dict__' in dir(s) or getattr(type(s), '__dict__', None) is not None
# The class-level __dict__ always exists on every class; the bug is an
# *instance* __dict__. Detect it directly on the instance.
try:
    instance_dict = object.__getattribute__(s, '__dict__')
    bug = True
except AttributeError:
    bug = False
    instance_dict = None
if bug:
    print('FAIL: Symbol instance carries an instance __dict__:', instance_dict)
    sys.exit(1)
print('OK: Symbol has no instance __dict__ (slots only)')
