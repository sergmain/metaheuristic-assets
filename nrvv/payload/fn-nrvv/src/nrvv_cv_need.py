# The NEED checks of NRVV v5 (plan 047, Phase 10): what every nrvv-cv-need-<workflow> flow shares - the agreed NEEDs
# as the prompt lists them (with their clause kinds), the answer instruction, the check of CC's findings, and the two
# Task runners each workflow's prompt and check script call.
#
# The answer is ONE JSON object {"findings": [{"kind", "subject", "counterpart"?, "text"}]}:
#   kind         one of the workflow's kinds
#   subject      the reqId of the agreed NEED the finding is about - one of the NEEDs the run was given
#   counterpart  a pair kind (CONTRADICTION, REDUNDANCY): another agreed NEED (required); any other kind: another
#                agreed NEED, or nothing
#   text         what the finding is
# A finding whose conflict key an earlier one has is dropped: KIND|min(subject,counterpart)|max(...) for a pair kind -
# so a mirrored pair is one finding - and KIND|subject otherwise. The Dispatcher's mhdg-nrvv.store-findings checks the
# same rules again (NrvvFindingUtils.parseNeedsCvFindings with the workflow's kinds, dedupByConflictKey).
#
# Pure but for run_prompt() / run_check().

import json

import mh_task_io as io
import nrvv_assessment as na
import nrvv_cc_answer as ca

FIELDS = ('kind', 'subject', 'counterpart', 'text')

# How the prompts explain a NEED's clause kind (decision 2 of plan 047).
KIND_HINT = [
    'Each NEED carries its clause kind: OBLIGATION - something the stakeholder needs to hold; COST_OBJECTIVE - a cost',
    'the stakeholder wants kept low, an objective to weigh and never a fixed bound; ENVIRONMENT_FACT - how the world',
    'around the system behaves, not something the system does; SCOPE_LIMITER - what matters or does not matter, what is',
    'out of scope. A NEED without a kind is an OBLIGATION.',
]

ANSWER_SHAPE = ('{"findings": [{"kind": "<kind>", "subject": "<NEED reqId>", "counterpart": "<NEED reqId or null>", '
                '"text": "<the finding>"}]}')
ANSWER_TAIL = 'Print nothing - neither the findings nor any explanation: only what the tool stores reaches the pipeline.'


def needs_of(raw):
    """The agreed NEEDs the run was given (mhdg-nrvv.read-agreed-needs), or a ValueError."""
    return na.agreed_needs_of(raw)


def corpus(needs):
    """The agreed NEEDs as the prompt lists them, each with its clause kind."""
    if not needs:
        return ['The project has no agreed NEED.']
    lines = ['The agreed NEEDs:']
    for n in needs:
        kind = n.get('kind')
        lines.append('')
        lines.append('NEED ' + str(n.get('reqId')) + (' (' + str(kind) + ')' if kind else '') + ': '
                     + str(n.get('title') or '').strip())
        for text_line in str(n.get('statement') or '').strip().splitlines():
            lines.append('  ' + text_line)
    return lines


def answer():
    """The LAST part of every NEED-check prompt: how the answer is stored. CC reads it last, so it acts on it."""
    return [
        '',
        'Answer by calling the mh_cc_store_result tool exactly once, with exactly this JSON object, and nothing else:',
        ANSWER_SHAPE,
        ANSWER_TAIL,
    ]


def conflict_key(kind, subject, counterpart, pair_kinds):
    if kind in pair_kinds and counterpart is not None:
        a, b = sorted((subject, counterpart))
        return kind + '|' + a + '|' + b
    return kind + '|' + subject


def findings_of(cc_result, needs, kinds, pair_kinds):
    """CC's findings as the canonical answer {"findings": [...]}, a mirrored or repeated conflict once, or a ValueError
    naming the first violation."""
    text = (cc_result or '').strip()
    fenced = na.FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    data = ca.loads(text)
    if not isinstance(data, dict) or set(data.keys()) != {'findings'} or not isinstance(data['findings'], list):
        raise ValueError('CC answered no {"findings": [...]} object: ' + na.excerpt(text))
    known = {str(n['reqId']) for n in needs}
    seen = set()
    out = []
    for i, f in enumerate(data['findings']):
        where = 'finding #' + str(i)
        if not isinstance(f, dict):
            raise ValueError(where + ' is not an object')
        extra = [k for k in f.keys() if k not in FIELDS]
        if extra:
            raise ValueError(where + ' has an unknown field ' + repr(extra[0]))
        kind = f.get('kind')
        if kind not in kinds:
            raise ValueError(where + ' has a kind this check does not report: ' + repr(kind))
        finding_text = f.get('text')
        if not isinstance(finding_text, str) or not finding_text.strip():
            raise ValueError(where + ' has no text')
        subject = str(f.get('subject') or '').strip()
        if subject not in known:
            raise ValueError(where + ' names subject ' + repr(subject) + ', which is not one of the agreed NEEDs')
        counterpart = f.get('counterpart')
        counterpart = None if counterpart is None else str(counterpart).strip() or None
        other_need = counterpart is not None and counterpart != subject and counterpart in known
        if kind in pair_kinds and not other_need:
            raise ValueError(where + ' is a ' + kind + ' and names no other agreed NEED as counterpart')
        if counterpart is not None and not other_need:
            raise ValueError(where + ' names counterpart ' + repr(counterpart) + ', which is not another agreed NEED')
        key = conflict_key(kind, subject, counterpart, pair_kinds)
        if key in seen:
            continue
        seen.add(key)
        item = {'kind': kind, 'subject': subject, 'text': finding_text.strip()}
        if counterpart is not None:
            item['counterpart'] = counterpart
        out.append(item)
    return {'findings': out}


def run_prompt(task, function_code, compose):
    needs = needs_of(io.read_role(task, 'agreed-needs'))
    prompt = compose(needs)
    io.write_text(io.output_role(task, 'prompt'), prompt)
    print(function_code + ': ' + str(len(needs)) + ' agreed NEED(s), ' + str(len(prompt)) + ' chars')


def run_check(task, function_code, kinds, pair_kinds):
    needs = needs_of(io.read_role(task, 'agreed-needs'))
    result = findings_of(io.read_role(task, 'cc-result'), needs, kinds, pair_kinds)
    io.write_text(io.output_role(task, 'findings'), json.dumps(result, ensure_ascii=False))
    print(function_code + ': ' + str(len(result['findings'])) + ' finding(s): '
          + ', '.join(f['kind'] + '/' + f['subject'] + ('/' + f['counterpart'] if 'counterpart' in f else '')
                      for f in result['findings']))
