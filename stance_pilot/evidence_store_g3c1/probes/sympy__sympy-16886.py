# Human-written symptom probe for sympy issue 16886, derived ONLY from the
# public issue report: Morse encoding of the digit "1" is wrong ("----")
# instead of the standard ".----". Independent of the maintainer test_patch /
# test_encode_morse.
import sys
from sympy.crypto.crypto import encode_morse

got = encode_morse('1')
print('encode_morse("1") =', repr(got))
if got != '.----':
    print('FAIL: Morse code for "1" is %r, expected ".----"' % got)
    sys.exit(1)
print('OK: Morse "1" -> .----')
