# A `when` gate that compares a flag Variable with the STRING "true" / "false" fails at runtime: MH's expression
# comparator (EvaluateExpressionLanguage.getTypeComparator) treats a Variable holding true/false as a boolean, then
# refuses the string operand beside it - 509.300 "not supported type: class java.lang.String" (ExecContext #12, the
# 'insert' gate of mh-rg-requirements-from-batch-staged-1.0). A boolean literal cannot stand there either - the grammar
# allows a Variable, an INT or a STRING as a comparison operand (MhSourceCode.g4, compareExpr). What works is the flag
# alone, as RG's own pipeline gates: `when flag ? true : false`.
#
# Checked here over every .mhsc this capability ships, so the class is refused before a push instead of discovered
# in a run (DAHF-IMPLEMENTATION 4.4).

import glob
import os
import re

SOURCE_CODES = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'source-codes')

# `when <anything> ==|!= "true"|"false"` - a quoted boolean on either side of the comparison
STRING_BOOLEAN = re.compile(r'^\s*when\b.*(?:(?:==|!=)\s*"(?:true|false)"|"(?:true|false)"\s*(?:==|!=))')


def offending_lines(text):
    return [(number, line.strip()) for number, line in enumerate(text.splitlines(), 1)
            if not line.strip().startswith('//') and STRING_BOOLEAN.search(line)]


def test_no_when_gate_compares_with_a_string_boolean():
    offending = []
    for path in sorted(glob.glob(os.path.join(SOURCE_CODES, '*.mhsc'))):
        with open(path, encoding='utf-8') as f:
            offending += [os.path.basename(path) + ':' + str(n) + ': ' + line for n, line in offending_lines(f.read())]
    assert offending == [], 'compare with the boolean literal (== true), not the string ("true"): ' + '; '.join(offending)


def test_the_rule_sees_the_shape_that_failed_and_passes_the_ones_that_work():
    assert offending_lines('        when hasFirstReq == "true" ? true : false')
    assert offending_lines('        when "false" != flag ? true : false')
    assert not offending_lines('        when hasFirstReq ? true : false')
    assert not offending_lines('        when genesisModeVar != "MANUAL" ? true : false')
    assert not offending_lines('        // when hasFirstReq == "true" - a comment is not a gate')
