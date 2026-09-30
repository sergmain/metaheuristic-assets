# mh.asset.rg-req-lines_1.0 - turn ONE file's checked answer into one requirement per line: the form internal
# mh.batch-line-splitter hands, line by line, to internal mhdg-rg.store-req as its reqJson.
#
# This file is NOT part of any bundle. It is reached only through the git block of
# rg-requirements/functions/fn-rg-req-lines/mh-function.yaml.
#
# roles - every Variable is named by a meta, never hard-coded:
#   answer   INPUT  - ONE line of JSON as mh.asset.rg-req-check_1.0 wrote it: {"sourcePath": ..., "requirements": [...]}
#   lines    OUTPUT - one JSON object per line, in CC's order: {"name": ..., "content": ..., "rationale": ...}
#
# ONLY the fields store-req's RequirementLine reads are written - name, content, rationale - and name / rationale
# only when present: a key it does not declare is a key its parser is not asked to accept. Each line is json.dumps
# with ensure_ascii, so a newline or a U+2028 inside a requirement stays escaped and every requirement is exactly one
# line whatever it says.
#
# The answer was already checked by rg-req-check (parse_requirements): content, rationale and name are what that
# check accepted. Only the shape is re-checked here, so a malformed line fails THIS branch, before store-req runs.

import json
import sys

from mh_task_io import load_params, output_role, read_role, write_text

FUNCTION_CODE = 'mh.asset.rg-req-lines_1.0'


def requirement_lines(answer_text):
    """(sourcePath, [one JSON line per requirement]) - or the failure naming what is wrong with the answer."""
    lines = [line.strip() for line in (answer_text or '').splitlines() if line.strip()]
    if len(lines) != 1:
        raise ValueError('expected exactly one answer line - one file\'s - got ' + str(len(lines)))
    try:
        answer = json.loads(lines[0])
    except ValueError:
        raise ValueError('the answer is not JSON') from None
    requirements = answer.get('requirements') if isinstance(answer, dict) else None
    if not isinstance(requirements, list) or not requirements:
        raise ValueError('the answer is not {"sourcePath": ..., "requirements": [...]} with at least one requirement')
    out = []
    for i, requirement in enumerate(requirements):
        label = '#' + str(i + 1)
        if not isinstance(requirement, dict):
            raise ValueError('requirement ' + label + ' is not an object')
        content = requirement.get('content')
        if not isinstance(content, str) or not content.strip():
            raise ValueError('requirement ' + label + ' has no content')
        item = {}
        name = requirement.get('name')
        if isinstance(name, str) and name.strip():
            item['name'] = name.strip()
        item['content'] = content.strip()
        rationale = requirement.get('rationale')
        if isinstance(rationale, str) and rationale.strip():
            item['rationale'] = rationale.strip()
        out.append(json.dumps(item, ensure_ascii=True))
    return answer.get('sourcePath'), out


def main(argv):
    print(FUNCTION_CODE)
    params = load_params(argv)
    task = params['task']
    try:
        source_path, lines = requirement_lines(read_role(task, 'answer'))
        write_text(output_role(task, 'lines'), '\n'.join(lines))
        print(str(source_path) + ': ' + str(len(lines)) + ' requirement line(s)')
        return 0
    except (ValueError, OSError) as e:
        print('FAILED: ' + str(e))
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
