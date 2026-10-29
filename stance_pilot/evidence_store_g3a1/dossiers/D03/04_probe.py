# Human-written symptom probe for sympy issue <ID_REDACTED>, derived ONLY from the
# public issue report (block_collapse of a BlockMatrix containing ZeroMatrix
# blocks raised on the SECOND multiplication b*b*b). The fixed result must be
# the BlockMatrix with a**3 in the top-left and zero blocks elsewhere.
import sys
from sympy import MatrixSymbol
from sympy.matrices.expressions import ZeroMatrix
from sympy.matrices.expressions.blockmatrix import BlockMatrix, block_collapse

a = MatrixSymbol('a', 2, 2)
z = ZeroMatrix(2, 2)
b = BlockMatrix([[a, z], [z, z]])
expect = BlockMatrix([[a ** 3, z], [z, z]])
try:
    out = block_collapse(b * b * b)
except Exception as e:  # noqa: BLE001
    print('FAIL: block_collapse(b*b*b) raised', type(e).__name__, e)
    sys.exit(1)
if out != expect:
    print('FAIL: block_collapse(b*b*b) =', out, '!=', expect)
    sys.exit(1)
# control: the first multiplication must also remain correct
if block_collapse(b * b) != BlockMatrix([[a ** 2, z], [z, z]]):
    print('FAIL: block_collapse(b*b) regressed')
    sys.exit(1)
print('OK: block_collapse b*b*b =', out)
