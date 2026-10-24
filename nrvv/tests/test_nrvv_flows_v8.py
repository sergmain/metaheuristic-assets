# plan 050 Phase 13 (decision 3) - the two flows of NRVV v8, read as the files that ship: the top-level definition writes no
# design, the DESIGN flow writes the design only, both take exactly definitionBaselineVariables, close and finish run last,
# and each API twin in nrvv-api/source-codes is exactly what nrvv/tools/api_twin.py writes from its base.

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))

import api_twin  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
TOP_LEVEL = os.path.join(ROOT, 'nrvv', 'source-codes', 'nrvv-definition-top-level-1.0.mhsc')
DESIGN = os.path.join(ROOT, 'nrvv', 'source-codes', 'nrvv-design-1.0.mhsc')
TWINS = {TOP_LEVEL: os.path.join(ROOT, 'nrvv-api', 'source-codes', 'nrvv-definition-top-level-api-1.0.mhsc'),
         DESIGN: os.path.join(ROOT, 'nrvv-api', 'source-codes', 'nrvv-design-api-1.0.mhsc')}

PROCESS = re.compile(r'^\s*(?P<name>[A-Za-z0-9_]+)\s*:=\s*(?:internal\s+)?(?P<code>[A-Za-z0-9_.:-]+)\s*\{')
PART = re.compile(r'meta\s+part\s*=\s*"(?P<part>[A-Z_]+)"')


def text_of(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def code_only(text):
    """The flow without its // comments - a header describing the graph must not satisfy a test about the graph."""
    return '\n'.join(line for line in text.splitlines() if not line.strip().startswith('//'))


def processes(text):
    return [(m.group('name'), m.group('code')) for m in (PROCESS.match(line) for line in code_only(text).splitlines()) if m]


def parts_of(text, code):
    """The `meta part` values of the processes of function `code`, in order."""
    out, current = [], None
    for line in code_only(text).splitlines():
        m = PROCESS.match(line)
        if m:
            current = m.group('code')
            continue
        p = PART.search(line)
        if p and current == code:
            out.append(p.group('part'))
    return out


def variables(text):
    block = re.search(r'variables\s*\{(?P<body>.*?)\}', code_only(text), re.S).group('body')
    return [v.strip() for line in block.splitlines() for v in line.replace('<-', '').split(',') if v.strip()]


def test_the_top_level_definition_writes_no_design():
    text = text_of(TOP_LEVEL)
    assert 'source "nrvv-definition-top-level-1.0"' in text
    assert parts_of(text, 'mhdg-nrvv.read-definition-input') == ['SUBJECTS', 'BOUNDARY']
    assert parts_of(text, 'mhdg-nrvv.store-definition-part') == ['TOP_LEVEL', 'BOUNDARY'], 'no DESIGN part (decision 3)'
    assert [c for _, c in processes(text)].count('mh.asset.call-cc_1.2') == 2, 'the top-level and the boundary sessions'


def test_the_design_flow_writes_the_design_only():
    text = text_of(DESIGN)
    assert 'source "nrvv-design-1.0"' in text
    assert parts_of(text, 'mhdg-nrvv.read-definition-input') == ['DESIGN']
    assert parts_of(text, 'mhdg-nrvv.store-definition-part') == ['DESIGN']
    assert [c for _, c in processes(text)].count('mh.asset.call-cc_1.2') == 1, 'one design session per branch'
    assert ('designs', 'mh.batch-line-splitter') in processes(text), 'one branch per top-level requirement'


def test_both_take_the_definition_baseline_inputs_open_first_and_close_and_finish_last():
    for path in (TOP_LEVEL, DESIGN):
        text = text_of(path)
        assert variables(text) == ['production?', 'runId', 'projectCode', 'model', 'effort?'], path
        names = processes(text)
        assert names[0] == ('open', 'mhdg-nrvv.open-stage'), path
        assert names[-2:] == [('close', 'mhdg-rg.post-processing'), ('finish', 'mhdg-nrvv.finish-run')], path
        assert code_only(text).count('tag terminal') == 2, path


def test_each_api_twin_is_what_the_generator_writes_from_its_base():
    for base, twin_path in TWINS.items():
        expected, uid, sites = api_twin.twin(text_of(base), os.path.basename(base))
        assert text_of(twin_path) == expected, twin_path + ' is generated, never edited'
        assert uid.endswith('-api-1.0') and sites, uid
