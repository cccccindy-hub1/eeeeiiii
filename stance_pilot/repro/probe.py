import sys, subprocess, json
from sympy import Symbol, S

print("sympy", S.__class__.__module__, __import__("sympy").__version__)
print("commit:", subprocess.run(["git","rev-parse","HEAD"],capture_output=True,text=True).stdout.strip())

# does the historical rule table already contain even == integer & !odd ?
from sympy.core.assumptions import _assume_rules
rules = str(_assume_rules)
print("rule even==integer present:", "even" in rules and "integer" in rules)

m = Symbol("m", even=True)
print("Symbol(even=True):", dict(even=m.is_even, integer=m.is_integer, finite=m.is_finite, rational=m.is_rational))

# the exact issue reproduction
print("ISSUE REPRO m.is_finite =", m.is_finite)

# what the test_patch asserts (subset)
cases = [
    ("rational=True", Symbol("x", rational=True).is_finite),
    ("irrational=True", Symbol("x", irrational=True).is_finite),
    ("integer=True", Symbol("x", integer=True).is_finite),
    ("complex=True", Symbol("x", complex=True).is_finite),
]
for name, v in cases: print(f"  {name:16s} is_finite = {v}")
