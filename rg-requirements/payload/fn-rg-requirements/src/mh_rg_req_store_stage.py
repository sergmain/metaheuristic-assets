# mh.asset.rg-req-store-stage_1.0 - store ONE file's requirements into a STAGE that is already open: the store of a
# file's branch, right after its answer is checked, one Task per file.
#
# This file is NOT part of any bundle. It is reached only through the git block of
# rg-requirements/functions/fn-rg-req-store-stage/mh-function.yaml.
#
# roles - every Variable is named by a meta, never hard-coded:
#   rg-base-url        INPUT  - the RG the project lives in, e.g. http://localhost:64967
#   project-code       INPUT  - the project
#   stage-snapshot-id  INPUT  - the open STAGE to write into, as decimal text - what mh.asset.rg-open-stage_1.0 writes
#   paths              INPUT  - the branch's file: one path per line, normally the branch's one sourcePath
#   answers            INPUT  - the branch's answer as mh.asset.rg-req-check_1.0 wrote it
#   req-ids            OUTPUT - the ids RG gave the stored requirements, one per line, in storing order
#   req-sources        OUTPUT - one line per stored requirement: its id, a TAB, its file
#
# THE WRITE is RG's requirements/manual with the STAGE's id as snapshotId - RgRequirementExtendedService
# .addManualDerivedRequirement in STAGE mode, the write internal mhdg-rg.req-store-batch makes for every requirement
# after #1, and the one RG names when it refuses a genesis on a project that owns snapshots (04.876.020: "Open a STAGE
# with mhdg_rg_open_stage and use mhdg_rg_add_manual_derived_req against it"). A write into a STAGE commits nothing:
# RG answers a null snapshotId. The writes carry no model / effort - the STAGE keeps the pair recorded on it.
#
# WHY NOT internal mhdg-rg.req-store-batch: it has no input naming a STAGE and starts every call with the project's
# genesis, which RG refuses once the project owns a snapshot (ExecContext #33, DETAILS 12.7 E2).
#
# EVERY FILE OR NOTHING within the Task: the answers must cover the paths exactly (the batch store's own plan), checked
# before RG is called. Every rationale ends with an empty line and 'source: <the file>', as the batch store writes it.
#
# THE CREDENTIAL is the vault entry RG_API_AUTH, handed over on the Processor's loopback secret channel.

import sys

from mh_rg_req_store import NEXT_TIMEOUT_SEC, basic_authorization, next_body, next_url, post_json, rg_base
from mh_rg_req_store_batch import parse_answers, plan, requirements_to_store, sources_text, written_into_stage
from mh_secret_client import exchange, extract_secret_fields, zero
from mh_task_io import load_params, output_role, read_role, write_text

FUNCTION_CODE = 'mh.asset.rg-req-store-stage_1.0'


def stage_id(text):
    """The STAGE id from its Variable's text - a positive whole number - or a failure naming what was found."""
    value = (text or '').strip()
    if not value:
        raise ValueError('input stage-snapshot-id is empty - there is no STAGE to store into')
    try:
        stage = int(value)
    except ValueError:
        raise ValueError("input stage-snapshot-id is not a snapshot id: '" + value + "'") from None
    if stage < 1:
        raise ValueError('input stage-snapshot-id is not a snapshot id: ' + value)
    return stage


def store_into_stage(requirements, stage, post_into_stage):
    """Every requirement written into the STAGE, in order: post_into_stage(body) -> reqId. Returns the ids. A failure
    names the STAGE and the ids already written into it - none of them committed."""
    if not requirements:
        raise ValueError('nothing to store')
    ids = []
    for requirement in requirements:
        try:
            ids.append(post_into_stage(next_body(requirement, stage)))
        except RuntimeError as e:
            raise RuntimeError(str(e) + ' - written into STAGE ' + str(stage) + ' before the failure, NOT committed: '
                               + (', '.join(ids) or 'none')) from None
    return ids


def run(task, credential):
    base = rg_base(read_role(task, 'rg-base-url'))
    code = (read_role(task, 'project-code') or '').strip()
    stage = stage_id(read_role(task, 'stage-snapshot-id'))
    pairs = plan(read_role(task, 'paths'), parse_answers(read_role(task, 'answers')))
    # both resolved BEFORE RG is called: a missing output declaration found after the writes would leave stored
    # requirements whose ids nobody was told
    ids_target = output_role(task, 'req-ids')
    sources_target = output_role(task, 'req-sources')
    if not code:
        raise ValueError('input project-code is empty - there is no project to store into')
    if credential is None:
        raise ValueError('no credential was handed over: mh-function.yaml declares api keyCode RG_API_AUTH, '
                         'but the params file carries no secretPort / checkCode')
    authorization = basic_authorization(credential)
    url = next_url(base, code)

    def post_into_stage(body):
        status, text = post_json(url, body, authorization, NEXT_TIMEOUT_SEC)
        return written_into_stage(status, text)

    files = len({path for path, _ in pairs})
    print('storing ' + str(len(pairs)) + ' requirement(s) from ' + str(files) + ' file(s) into STAGE ' + str(stage)
          + ' of ' + code)
    ids = store_into_stage(requirements_to_store(pairs), stage, post_into_stage)
    write_text(ids_target, '\n'.join(ids))
    write_text(sources_target, sources_text(ids, pairs))
    print('stored ' + str(len(ids)) + ' requirement(s) into STAGE ' + str(stage) + ': ' + ids[0] + ' .. ' + ids[-1])
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
