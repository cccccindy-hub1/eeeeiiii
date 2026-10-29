# Human-written symptom probe for sympy issue <ID_REDACTED>, derived ONLY from the
# public issue report (Quaternion.to_rotation_matrix had a wrong sign: for a
# rotation about the x-axis, one off-diagonal sin term must be negative).
# Independent of the maintainer test_quaternion_conversions.
import sys
from sympy import symbols, cos, sin, trigsimp, Matrix
from sympy.algebras.quaternion import Quaternion

x = symbols('x', real=True)
q = Quaternion(cos(x / 2), sin(x / 2), 0, 0)   # rotation about the x-axis
M = trigsimp(q.to_rotation_matrix())
# Standard x-axis rotation matrix:
# [[1,0,0],[0,cos x,-sin x],[0,sin x,cos x]]
expect = Matrix([[1, 0, 0],
                 [0, cos(x), -sin(x)],
                 [0, sin(x), cos(x)]])
if trigsimp(M - expect) != Matrix.zeros(3):
    print('FAIL: x-axis rotation matrix\n', M, '\n!=\n', expect)
    sys.exit(1)
print('OK: rotation matrix sign correct')
