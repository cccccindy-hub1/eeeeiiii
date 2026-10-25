
# issue: a complicated constant that is algebraically zero is not recognized:
# Poly(<const>, x) must equal Poly(0, x, domain='EX'); downstream clear_denoms then
# produces an unstripped zero DMP and division by it raises ZeroDivisionError.
import sys
from sympy import symbols, Poly, S, sqrt
x = symbols("x")
f = Poly(-117968192370600*18**(S(1)/3)/(217603955769048*(24201 +
    253*sqrt(9165))**(S(1)/3) + 2273005839412*sqrt(9165)*(24201 +
    253*sqrt(9165))**(S(1)/3)) - 15720318185*2**(S(2)/3)*3**(S(1)/3)*(24201
    + 253*sqrt(9165))**(S(2)/3)/(217603955769048*(24201 + 253*sqrt(9165))**
    (S(1)/3) + 2273005839412*sqrt(9165)*(24201 + 253*sqrt(9165))**(S(1)/3))
    + 15720318185*12**(S(1)/3)*(24201 + 253*sqrt(9165))**(S(2)/3)/(
    217603955769048*(24201 + 253*sqrt(9165))**(S(1)/3) + 2273005839412*
    sqrt(9165)*(24201 + 253*sqrt(9165))**(S(1)/3)) + 117968192370600*2**(
    S(1)/3)*3**(S(2)/3)/(217603955769048*(24201 + 253*sqrt(9165))**(S(1)/3)
    + 2273005839412*sqrt(9165)*(24201 + 253*sqrt(9165))**(S(1)/3)), x)
if f != Poly(0, x, domain='EX'):
    print("FAIL: zero constant not recognized as Poly(0)")
    sys.exit(1)
print("OK: constant recognized as zero poly")
