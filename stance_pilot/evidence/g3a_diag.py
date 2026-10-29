"""G3-A construct diagnostic (temp): checkout candidate 17318 / 17630 states and
print exact behaviours. No artifacts written; repo restored afterwards.
Usage: python -m evidence.g3a_diag ISSUE baseline|post
"""
import json, subprocess, sys, os
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
REPO = HERE / 'repro' / 'sympy_src'
ROWS = {r['instance_id']: r for r in
        (json.loads(l) for l in
         (HERE/'evidence_store_g3a/raw/g3a_target_rows.jsonl').read_text(
             encoding='utf-8').splitlines() if l.strip())}


def git(*a):
    p = subprocess.run(['git', *a], cwd=REPO, capture_output=True, text=True)
    if p.returncode:
        print('git err', p.stderr[:400])
    return p


def write_patch(name, text):
    p = HERE/'evidence_store_g3a'/('_diag_'+name)
    with open(p, 'w', encoding='utf-8', newline='') as fh:
        fh.write(text)
    return p


def main():
    iid, phase = sys.argv[1], sys.argv[2]
    raw = ROWS[iid]
    os.environ['GIT_NO_LAZY_FETCH'] = '1'
    git('checkout', '-f', raw['base_commit']); git('clean', '-fdq')
    if phase == 'post':
        cp = write_patch('cand.patch', raw['model_patch'])
        git('apply', '--whitespace=nowarn', str(cp.resolve()))
        tp = write_patch('test.patch', raw['test_patch'])
        tfs = [l[6:] for l in raw['test_patch'].splitlines()
               if l.startswith('+++ b/')]
        if tfs:
            git('checkout', raw['base_commit'], '--', *tfs)
        git('apply', '--whitespace=nowarn', str(tp.resolve()))
    env = dict(os.environ); env['PYTHONPATH'] = str(REPO)
    if iid.endswith('17318'):
        code = (
            "from sympy import sqrt, S\n"
            "from sympy.simplify.sqrtdenest import sqrtdenest,_sqrt_match\n"
            "I=S.ImaginaryUnit\n"
            "import traceback\n"
            "try:\n"
            " print('sqrt_match(4+I)=',_sqrt_match(4+I))\nexcept Exception:\n"
            " traceback.print_exc()\n"
            "try:\n"
            " print('sqrtdenest(3I expr)=',sqrtdenest((3-sqrt(2)*sqrt(4+3*I)+3*I)/2))\n"
            "except Exception:\n traceback.print_exc()\n"
            "try:\n"
            " e=3-sqrt(2)*sqrt(4+I)+3*I; print('sqrtdenest(e)==e:',sqrtdenest(e)==e, sqrtdenest(e))\n"
            "except Exception:\n traceback.print_exc()\n")
    else:
        code = (
            "from sympy import MatrixSymbol\n"
            "from sympy.matrices.expressions import ZeroMatrix\n"
            "from sympy.matrices.expressions.blockmatrix import BlockMatrix,block_collapse\n"
            "a=MatrixSymbol('a',2,2);z=ZeroMatrix(2,2);b=BlockMatrix([[a,z],[z,z]])\n"
            "import traceback\n"
            "for k,e in (('b2',b*b),('b3',b*b*b)):\n"
            " try:\n"
            "  r=block_collapse(e);print(k,'=',r); print('  type',type(r).__name__)\n"
            "  print('  == BlockMatrix a**3:',r==BlockMatrix([[a**3,z],[z,z]]))\n"
            " except Exception:\n  traceback.print_exc()\n")
    p = subprocess.run([sys.executable, '-c', code], cwd=REPO, env=env,
                       capture_output=True, text=True)
    print('--- stdout ---'); print(p.stdout[-3000:])
    print('--- stderr ---'); print(p.stderr[-1500:])
    git('checkout', '-f', raw['base_commit']); git('clean', '-fdq')


if __name__ == '__main__':
    main()
