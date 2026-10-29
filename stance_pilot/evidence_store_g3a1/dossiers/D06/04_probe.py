# Symptom probe for an anonymised SymPy dimensions issue.
# NOTE: the acceptance criterion of this probe is under
# independent review; see packet P-CRITERION (opened by the
# coordinator). Judge the executed behaviour from the logs.
import sys
from sympy.physics import units
from sympy.physics.units.systems.si import SI

v1 = units.Quantity('v1')
SI.set_quantity_dimension(v1, units.velocity)
SI.set_quantity_scale_factor(v1, 2 * units.meter / units.second)

a1 = units.Quantity('a1')
SI.set_quantity_dimension(a1, units.acceleration)
SI.set_quantity_scale_factor(a1, -9.8 * units.meter / units.second ** 2)

t1 = units.Quantity('t1')
SI.set_quantity_dimension(t1, units.time)
SI.set_quantity_scale_factor(t1, 5 * units.second)

try:
    factor, dimension = SI._collect_factor_and_dimension(a1 * t1 + v1)
except Exception as e:  # noqa: BLE001 - the reported ValueError is the symptom
    print('FAIL: _collect_factor_and_dimension raised', type(e).__name__, e)
    sys.exit(1)
print('OK: no dimension error for a*t + v ->', 'factor', factor,
      'dimension', dimension)
