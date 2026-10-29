# Human-written symptom probe for sympy issue <ID_REDACTED>, derived ONLY from the
# public issue report (powers of TensorProduct do not simplify). Independent
# of the maintainer test_patch / test_tensor_product_simp.
import sys
from sympy import Symbol
from sympy.physics.quantum import TensorProduct, tensor_product_simp
from sympy.physics.paulialgebra import Pauli

# t1 = (1 x 1) * (1 x 1) should collapse to 1 x 1 (no lingering **2).
t1 = TensorProduct(1, 1) * TensorProduct(1, 1)
r1 = tensor_product_simp(t1)
if r1 != TensorProduct(1, 1):
    print('FAIL: t1 tensor_product_simp =', r1)
    sys.exit(1)

# t2 = (1 x sigma3) * (1 x sigma3) should collapse to 1 x 1.
t2 = TensorProduct(1, Pauli(3)) * TensorProduct(1, Pauli(3))
r2 = tensor_product_simp(t2)
if r2 != TensorProduct(1, 1):
    print('FAIL: t2 tensor_product_simp =', r2)
    sys.exit(1)
print('OK: tensor product powers simplify:', r1, r2)
