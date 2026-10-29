# Human-written symptom probe for sympy issue 19346, derived ONLY from the
# public issue report: srepr does not recurse into dict/set elements (prints
# "{x, y}" / "{x: y}" instead of wrapping each element in Symbol(...)). The
# list/tuple behaviour already recurses. Independent of the maintainer
# test_patch / test_dict.
import sys
from sympy import srepr
from sympy.abc import x, y

s_set = srepr({x, y})
s_dict = srepr({x: y})
print('srepr(set)  =', s_set)
print('srepr(dict) =', s_dict)
if 'Symbol(' not in s_set:
    print('FAIL: srepr did not recurse into set elements:', s_set)
    sys.exit(1)
if 'Symbol(' not in s_dict:
    print('FAIL: srepr did not recurse into dict keys/values:', s_dict)
    sys.exit(1)
print('OK: srepr recurses into set and dict')
