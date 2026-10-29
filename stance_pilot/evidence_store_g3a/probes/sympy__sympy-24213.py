# Human-written symptom probe for sympy issue 24213, derived from the public
# issue report. The reported, reproducible failure is that
# SI._collect_factor_and_dimension(a1*t1 + v1) RAISES ValueError even though
# acceleration*time is dimensionally velocity. The maintainer regression test
# (test_issue_24211) asserts exactly "should not throw ValueError here"; it
# does not require the returned dimension to be canonicalised to "velocity".
# We therefore test the reported symptom (no exception), not a stronger
# dimension-normalisation claim the report never made.
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
