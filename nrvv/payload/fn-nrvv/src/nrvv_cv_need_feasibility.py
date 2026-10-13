# NEED check FEASIBILITY (plan 047, Phase 11): can the agreed NEEDs be implemented at all? CC answers exactly ONE verdict
# (decision 7):
#   INFEASIBLE       the minimal set of NEEDs that cannot hold together (needReqIds, at least one) and why (reason) -
#                    a hard finding: NRVV declines
#   UNDERDETERMINED  a witness design meeting every NEED (witness) and the choices the NEEDs leave open (openChoices) -
#                    a soft finding carrying the open choices
#   DETERMINED       a witness design (witness) - no finding
# A witness is a design sketch of at most 2000 characters that names every agreed NEED (its reqId) with how the sketch
# meets it. Optimality is not a criterion: it is a NEED or it is not asked. Run 3 times per gate (decision 13).
#
# The canonical answer keeps the verdict's own fields only:
#   {"verdict": "INFEASIBLE", "needReqIds": [...], "reason": "..."}
#   {"verdict": "UNDERDETERMINED", "witness": "...", "openChoices": [...]}
#   {"verdict": "DETERMINED", "witness": "..."}
# The Dispatcher's mhdg-nrvv.store-findings checks the same again (NrvvFindingUtils.parseFeasibility).
#
# Pure but for run_check().

import json
import re

import mh_task_io as io
import nrvv_assessment as na
import nrvv_cc_answer as ca
import nrvv_cv_need as cv

VERDICTS = ('INFEASIBLE', 'UNDERDETERMINED', 'DETERMINED')
FIELDS = ('verdict', 'needReqIds', 'reason', 'witness', 'openChoices')
WITNESS_MAX_CHARS = 2000

ANSWER_SHAPE = ('{"verdict": "<INFEASIBLE|UNDERDETERMINED|DETERMINED>", "needReqIds": ["<NEED reqId>"], '
                '"reason": "<why they cannot hold together>", "witness": "<the design sketch>", '
                '"openChoices": ["<a choice the NEEDs leave open>"]}')


def compose(needs):
    """The feasibility prompt over the agreed NEEDs."""
    lines = [
        'You judge whether the NEEDs a project\'s stakeholders have agreed can be implemented at all - all of them',
        'together, by one system, in the world the NEEDs describe. You answer with exactly ONE verdict.',
        '',
        '- INFEASIBLE: no design can meet all the NEEDs. Give the MINIMAL set of NEEDs that cannot hold together',
        '  (needReqIds - drop any NEED the conflict does not need) and the reason, naming the situation in which they',
        '  cannot all hold.',
        '- UNDERDETERMINED: a design meets every NEED, and the NEEDs leave real choices open - a number, a policy, a',
        '  behaviour they do not fix. Give a witness design and the open choices (openChoices), one short line each.',
        '- DETERMINED: a design meets every NEED and the NEEDs leave nothing material open. Give a witness design.',
        '',
        'A witness is a design sketch of at most ' + str(WITNESS_MAX_CHARS) + ' characters. It names EVERY agreed NEED',
        'by its reqId, saying for each how the sketch meets it. Do not fill an open choice with an invented number: list',
        'it in openChoices. Optimality is not a criterion: a better design is not asked unless a NEED asks for it.',
        'A COST_OBJECTIVE NEED is met by a design that keeps that cost low against the others; it is never a fixed bound.',
        '',
    ]
    return '\n'.join(lines + cv.KIND_HINT + [''] + cv.corpus(needs) + [
        '',
        'Answer by calling the mh_cc_store_result tool exactly once, with exactly this JSON object - only the fields of',
        'your verdict - and nothing else:',
        ANSWER_SHAPE,
        cv.ANSWER_TAIL.replace('the findings', 'the verdict'),
    ])


def _strings(value):
    return isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value)


def names(witness, req_id):
    """Whether the witness names NEED `req_id` - the reqId not continued by a digit (GAS-2 is not named by GAS-21)."""
    return re.search(re.escape(req_id) + r'(?!\d)', witness) is not None


def verdict_of(cc_result, needs):
    """CC's verdict in canonical form, or a ValueError naming the first violation."""
    text = (cc_result or '').strip()
    fenced = na.FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    data = ca.loads(text)
    if not isinstance(data, dict):
        raise ValueError('CC answered no {"verdict": ...} object: ' + na.excerpt(text))
    extra = [k for k in data.keys() if k not in FIELDS]
    if extra:
        raise ValueError('the verdict has an unknown field ' + repr(extra[0]))
    verdict = data.get('verdict')
    if verdict not in VERDICTS:
        raise ValueError('unknown verdict ' + repr(verdict))
    known = [str(n['reqId']) for n in needs]
    if verdict == 'INFEASIBLE':
        ids = data.get('needReqIds')
        if not _strings(ids) or len(ids) < 1:
            raise ValueError('an INFEASIBLE verdict names at least one NEED in needReqIds')
        ids = [x.strip() for x in ids]
        unknown = [x for x in ids if x not in known]
        if unknown:
            raise ValueError('needReqIds names ' + repr(unknown[0]) + ', which is not one of the agreed NEEDs')
        if len(set(ids)) != len(ids):
            raise ValueError('needReqIds names a NEED twice')
        reason = data.get('reason')
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError('an INFEASIBLE verdict gives its reason')
        return {'verdict': verdict, 'needReqIds': ids, 'reason': reason.strip()}
    witness = data.get('witness')
    if not isinstance(witness, str) or not witness.strip():
        raise ValueError('a ' + verdict + ' verdict gives its witness design')
    witness = witness.strip()
    if len(witness) > WITNESS_MAX_CHARS:
        raise ValueError('the witness is ' + str(len(witness)) + ' characters, at most ' + str(WITNESS_MAX_CHARS))
    missing = [x for x in known if not names(witness, x)]
    if missing:
        raise ValueError('the witness does not name NEED ' + missing[0] + ': it names every agreed NEED')
    if verdict == 'DETERMINED':
        return {'verdict': verdict, 'witness': witness}
    choices = data.get('openChoices')
    if not _strings(choices) or len(choices) < 1:
        raise ValueError('an UNDERDETERMINED verdict lists the choices the NEEDs leave open')
    return {'verdict': verdict, 'witness': witness, 'openChoices': [c.strip() for c in choices]}


def run_check(task, function_code):
    needs = cv.needs_of(io.read_role(task, 'agreed-needs'))
    result = verdict_of(io.read_role(task, 'cc-result'), needs)
    io.write_text(io.output_role(task, 'findings'), json.dumps(result, ensure_ascii=False))
    print(function_code + ': ' + result['verdict']
          + (' ' + str(result['needReqIds']) if 'needReqIds' in result else '')
          + (', ' + str(len(result['openChoices'])) + ' open choice(s)' if 'openChoices' in result else ''))
