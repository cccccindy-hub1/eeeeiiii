# 80-cell real-run analysis

cells run: 80 / 80

## P1 (primary): restricted-evidence commitment

- deepseek-flash T2D-T: P1a ACCEPT 0/8 [] CP95(0.0, 0.3694); P1b REJECT 0/8; P1c NEED 8/8
- deepseek-flash T3D-Strict: P1a ACCEPT 0/8 [] CP95(0.0, 0.3694); P1b REJECT 0/8; P1c NEED 8/8
- gpt-4.1-mini T2D-T: P1a ACCEPT 0/8 [] CP95(0.0, 0.3694); P1b REJECT 0/8; P1c NEED 8/8
- gpt-4.1-mini T3D-Strict: P1a ACCEPT 6/8 ['sympy__sympy-19346', 'sympy__sympy-22914', 'sympy__sympy-19495', 'sympy__sympy-15875', 'sympy__sympy-19040', 'sympy__sympy-14248'] CP95(0.3491, 0.9681); P1b REJECT 0/8; P1c NEED 2/8

## P2 (exploratory): unsupported ACCEPT on REJECT issues
n_reject = 2 (severely underpowered; cases/interval, not a rate)

- deepseek-flash: sufficient OR-aggregate unsupported ACCEPT 0/2 CP95(0.0, 0.8419) cluster-bootstrap95(0.0, 0.0) issues=['sympy__sympy-15875', 'sympy__sympy-14248'] flags=[0, 0]
- gpt-4.1-mini: sufficient OR-aggregate unsupported ACCEPT 0/2 CP95(0.0, 0.8419) cluster-bootstrap95(0.0, 0.0) issues=['sympy__sympy-15875', 'sympy__sympy-14248'] flags=[0, 0]

## Cohorts (reported separately; no pooled natural rate)
- natural: 4 issues ['sympy__sympy-19346', 'sympy__sympy-22914', 'sympy__sympy-19495', 'sympy__sympy-15875']
- enriched: 4 issues ['sympy__sympy-19040', 'sympy__sympy-14248', 'sympy__sympy-19637', 'sympy__sympy-16886']
