# mh.asset.rg-req-store-batch_1.0 - store every file's requirements of one batch in the RG project, as ONE chain.
#
# This file is NOT part of any bundle. It is reached only through the git block of
# rg-requirements/functions/fn-rg-req-store-batch/mh-function.yaml.
#
# roles - every Variable is named by a meta, never hard-coded:
#   rg-base-url    INPUT  - the RG (dispatcher) base url, e.g. http://localhost:64967
#   project-code   INPUT  - the project to store into: ready, running an RG genesis pipeline, owning no snapshot -
#                           what mh.asset.rg-temp-project_1.1 creates with variable-for-rg-pipeline-uid
#   paths          INPUT  - the batch: one path per line, exactly what internal mh.batch-line-splitter split
#   answers        INPUT  - every branch's answer as mh.asset.rg-req-check_1.0 wrote it, collected by internal
#                           mh.aggregate (type text): one line of JSON per file, blank lines between them
#   req-ids        OUTPUT - the ids RG gave the stored requirements, one per line, in storing order
#   req-sources    OUTPUT - one line per stored requirement: its id, a TAB, the file it was derived from
#
# THE CREDENTIAL is the vault entry RG_API_AUTH, handed over on the Processor's loopback secret channel exactly
# as for mh.asset.rg-req-store_1.0.
#
# ONE TASK, ONE CHAIN. requirements/manual forks a new STAGE from whichever COMMITTED snapshot it is given and
# does not refuse a parent that already has children (RgSnapshotLifecycleService.openStageFromParent checks
# only that the parent is COMMITTED). Branches writing in parallel would fork the project into one leaf per
# file. So the branches only answer, and this Task stores through mh.asset.rg-req-store_1.0's own chain
# (store_all): requirement #1 through requirements/manual/first - the project's one-shot genesis - and each
# next one onto the snapshot the previous call committed.
#
# EVERY FILE OR NOTHING, checked before RG is called. The answers must cover the batch exactly: one per path,
# none for a path outside it. internal mh.aggregate collects only the variables that exist, so a branch that
# never wrote its answer is simply absent from the collection - without this check the batch would be stored
# short, its record deleted afterwards, and nothing would say that a file's requirements never arrived.
# Requirements are stored in the batch's order, each file's in the order CC gave them.

import json
import sys

from mh_rg_req_store import (FIRST_TIMEOUT_SEC, NEXT_TIMEOUT_SEC, basic_authorization, created, excerpt,
                             first_url, next_url, parse_requirements, post_json, rg_base, store_all)
from mh_secret_client import exchange, extract_secret_fields, zero
from mh_task_io import NULL_VALUE, load_params, output_role, read_role, write_text

FUNCTION_CODE = 'mh.asset.rg-req-store-batch_1.0'

# How many paths a failure message names before it only counts the rest.
LISTED = 10


def listing(paths):
    shown = ', '.join(paths[:LISTED])
    return shown if len(paths) <= LISTED else shown + ', ... (' + str(len(paths) - LISTED) + ' more)'


def parse_answers(answers_text):
    """Each non-blank line of the collection as (sourcePath, requirements), in the collection's order - or a
    failure naming the line, or the file, that is wrong."""
    answers = []
    for number, line in enumerate((answers_text or '').split('\n'), 1):
        text = line.strip()
        if not text:
            continue
        try:
            answer = json.loads(text)
        except ValueError:
            raise ValueError('line ' + str(number) + ' of the answers is not JSON: ' + excerpt(text)) from None
        path = answer.get('sourcePath') if isinstance(answer, dict) else None
        if not isinstance(path, str) or not path.strip() or not isinstance(answer.get('requirements'), list):
            raise ValueError('line ' + str(number) + ' of the answers is not {"sourcePath": ..., '
                             '"requirements": [...]}: ' + excerpt(text))
        try:
            requirements = parse_requirements(json.dumps(answer['requirements']))
        except ValueError as e:
            raise ValueError('the answer for ' + path.strip() + ' - ' + str(e)) from None
        answers.append((path.strip(), requirements))
    return answers


def plan(paths_text, answers):
    """[(path, requirement)] in the batch's order, each file's requirements in their answer's order - or a
    failure naming every path that is unanswered, answered twice, or not part of the batch."""
    batch = [line.strip() for line in (paths_text or '').split('\n') if line.strip()]
    if not batch:
        raise ValueError('input paths is empty - there is no batch to store')
    if len(set(batch)) != len(batch):
        raise ValueError('input paths lists a file more than once - its requirements would be stored twice')
    by_path = {}
    repeated = []
    for path, requirements in answers:
        if path in by_path:
            repeated.append(path)
        else:
            by_path[path] = requirements
    in_batch = set(batch)
    missing = [path for path in batch if path not in by_path]
    foreign = [path for path in by_path if path not in in_batch]
    problems = []
    if missing:
        problems.append(str(len(missing)) + ' of the ' + str(len(batch)) + ' files have no answer: '
                        + listing(missing))
    if repeated:
        problems.append('answered more than once: ' + listing(repeated))
    if foreign:
        problems.append('answered but not in the batch: ' + listing(foreign))
    if problems:
        raise ValueError('the answers do not cover the batch, nothing was stored: ' + '; '.join(problems))
    return [(path, requirement) for path in batch for requirement in by_path[path]]


def sources_text(ids, pairs):
    """One line per stored requirement: its id, a TAB, its file."""
    return '\n'.join(req_id + '\t' + path for req_id, (path, _) in zip(ids, pairs))


def run(task, credential):
    base = rg_base(read_role(task, 'rg-base-url'))
    code = read_role(task, 'project-code').strip()
    pairs = plan(read_role(task, 'paths'), parse_answers(read_role(task, 'answers')))
    # both resolved BEFORE RG is called: a missing output declaration found after the genesis would leave
    # stored requirements whose ids nobody was told
    ids_target = output_role(task, 'req-ids')
    sources_target = output_role(task, 'req-sources')
    if not code or code == NULL_VALUE:
        raise ValueError('input project-code is empty - there is no project to store into')
    if credential is None:
        raise ValueError('no credential was handed over: mh-function.yaml declares api keyCode RG_API_AUTH, '
                         'but the params file carries no secretPort / checkCode')
    authorization = basic_authorization(credential)
    files = len({path for path, _ in pairs})
    print('storing ' + str(len(pairs)) + ' requirement(s) from ' + str(files) + ' file(s) into ' + code)

    def post_first(body):
        status, text = post_json(first_url(base, code), body, authorization, FIRST_TIMEOUT_SEC)
        print('POST requirements/manual/first -> HTTP ' + str(status))
        return created(status, text)

    def post_next(body):
        status, text = post_json(next_url(base, code), body, authorization, NEXT_TIMEOUT_SEC)
        print('POST requirements/manual onto snapshot ' + str(body['snapshotId']) + ' -> HTTP ' + str(status))
        return created(status, text)

    ids = store_all([requirement for _, requirement in pairs], post_first, post_next)
    write_text(ids_target, '\n'.join(ids))
    write_text(sources_target, sources_text(ids, pairs))
    print('stored ' + str(len(ids)) + ' requirement(s): ' + ids[0] + ' .. ' + ids[-1])
    return 0


def main(argv):
    print(FUNCTION_CODE)
    params = load_params(argv)
    # FIRST, before anything that can take time: the Processor's accept() waits 10 seconds for this connection
    port, check_code = extract_secret_fields(params)
    try:
        credential = exchange(port, check_code) if port is not None else None
    except OSError as e:
        print('FAILED: the secret handoff did not complete: ' + str(e))
        return 1
    try:
        return run(params['task'], credential)
    except (ValueError, RuntimeError, OSError) as e:
        print('FAILED: ' + str(e))
        return 1
    finally:
        if credential is not None:
            zero(credential)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
