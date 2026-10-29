# Human-written symptom probe for sympy issue 22914, derived ONLY from the
# public issue report: PythonCodePrinter (pycode) does not support Min/Max and
# emits a "Not supported in Python" comment with the bare Min(a, b) call.
# Independent of the maintainer test_patch / test_PythonCodePrinter.
import sys
from sympy import symbols, Min, Max, pycode

a, b = symbols('a b')
c_min = pycode(Min(a, b))
c_max = pycode(Max(a, b))
print('pycode(Min) =', repr(c_min))
print('pycode(Max) =', repr(c_max))
if 'Not supported' in c_min or 'Min(' in c_min:
    print('FAIL: pycode does not support Min:', c_min)
    sys.exit(1)
if 'Not supported' in c_max or 'Max(' in c_max:
    print('FAIL: pycode does not support Max:', c_max)
    sys.exit(1)
if c_min.replace(' ', '') != 'min(a,b)':
    print('FAIL: expected min(a, b), got', c_min)
    sys.exit(1)
if c_max.replace(' ', '') != 'max(a,b)':
    print('FAIL: expected max(a, b), got', c_max)
    sys.exit(1)
print('OK: pycode supports Min/Max')
