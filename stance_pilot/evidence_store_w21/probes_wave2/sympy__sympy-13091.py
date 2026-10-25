# issue: Basic.__eq__ returns False instead of NotImplemented when comparing
# against an unknown type, so the reflected __eq__ on the other operand is
# never consulted and equivalence becomes asymmetric. A reflected True must
# win once Basic returns NotImplemented.
import sys
from sympy import Basic


class ReflectedTrue:
    def __eq__(self, other):
        if isinstance(other, Basic):
            return True
        return NotImplemented

    def __ne__(self, other):
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result


s = Basic()
f = ReflectedTrue()
if not (s == f):
    print("FAIL: Basic == unknown did not delegate to reflected __eq__")
    sys.exit(1)
if (s != f):
    print("FAIL: Basic != unknown did not delegate to reflected __ne__")
    sys.exit(1)
print("OK: rich comparison symmetric via reflected methods")
