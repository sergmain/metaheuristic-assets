# mh.asset.rg-open-stage_1.0 - open ONE STAGE on a fresh, EMPTY project: the STAGE every branch of the batch stores
# into, opened before the fan-out, with no requirement singled out to start the project.
#
# This file is NOT part of any bundle. It is reached only through the git block of
# rg-requirements/functions/fn-rg-open-stage/mh-function.yaml.
#
# roles - every Variable is named by a meta, never hard-coded:
#   rg-base-url          INPUT  - the RG the project lives in, e.g. http://localhost:64967
#   project-code         INPUT  - the project: ready, bound to an RG genesis pipeline, owning no snapshot - what
#                                 mh.asset.rg-temp-project_1.1 creates
#   model, effort        OPTIONAL INPUTS - the run's pair; unbound, nullified or blank sends none (effort is null for
#                                 a model that takes none - Haiku)
#   stage-snapshot-id    OUTPUT - the id of the opened STAGE, as decimal text. Bind it to a Variable named
#                                 stageSnapshotId: internal mhdg-rg.store-req and mhdg-rg.post-processing read that name
#   genesis-snapshot-id  OUTPUT - the id of the COMMITTED genesis the STAGE was forked from, as decimal text
#
# ONE CALL: RG's MCP tool mhdg_rg_open_stage WITHOUT parentSnapshotId. On a project with no COMMITTED snapshot RG
# (RgPleAuthoringService.openStage) runs the project's own genesis pipeline with no requirement - an EMPTY genesis -,
# waits for it to commit (its own bound, 04.689.068), and forks the STAGE from that snapshot with a copy of the genesis
# ExecContext. A project that already owns a COMMITTED snapshot is refused by RG (689.064) - nothing is tip-guessed.
#
# THE CREDENTIAL is the vault entry RG_API_AUTH, handed over on the Processor's loopback secret channel, exactly as
# mh.asset.rg-genesis-snapshot_1.0 receives it; the MCP client is the payload's mh_rg_mcp_client.

import json
import sys

from mh_rg_mcp_client import call_tool
from mh_rg_req_store import basic_authorization, excerpt, rg_base
from mh_rg_req_store_batch import llm_pair, optional_role
from mh_secret_client import exchange, extract_secret_fields, zero
from mh_task_io import load_params, output_role, read_role, write_text

FUNCTION_CODE = 'mh.asset.rg-open-stage_1.0'

MCP_PATH = '/rest/v1/legal/mcp'
# The call returns only after RG's genesis run has committed and the STAGE is forked: RG bounds its own wait for the
# genesis (awaitGenesisCommitted); this read timeout sits above that bound.
OPEN_STAGE_TIMEOUT_SEC = 600


def open_stage_arguments(code, model, effort):
    """The arguments of mhdg_rg_open_stage: the project and the run's pair - and NO parentSnapshotId, which is what
    makes RG open the genesis STAGE of an empty project."""
    return dict({'infoBank': code}, **llm_pair(model, effort))


def the_stage(answer):
    """(stageSnapshotId, genesis snapshotId) from what mhdg_rg_open_stage answered - or a failure naming what was
    answered."""
    if not isinstance(answer, dict):
        raise ValueError('mhdg_rg_open_stage answered no object')
    if answer.get('errorMessage'):
        raise ValueError('mhdg_rg_open_stage: ' + str(answer.get('errorMessage')))
    stage = answer.get('stageSnapshotId')
    genesis = answer.get('parentSnapshotId')
    if not isinstance(stage, int) or isinstance(stage, bool):
        raise ValueError('mhdg_rg_open_stage answered no stageSnapshotId: ' + excerpt(json.dumps(answer)))
    if not isinstance(genesis, int) or isinstance(genesis, bool):
        raise ValueError('mhdg_rg_open_stage answered no genesis snapshot (parentSnapshotId) for STAGE ' + str(stage)
                         + ': ' + excerpt(json.dumps(answer)))
    if stage == genesis:
        raise ValueError('mhdg_rg_open_stage answered the same id for the STAGE and its genesis: ' + str(stage))
    return stage, genesis


def run(task, credential):
    base = rg_base(read_role(task, 'rg-base-url'))
    code = (read_role(task, 'project-code') or '').strip()
    # both outputs resolved BEFORE RG is called: a missing declaration found after the genesis ran would leave an
    # open STAGE whose id nobody was told
    stage_target = output_role(task, 'stage-snapshot-id')
    genesis_target = output_role(task, 'genesis-snapshot-id')
    if not code:
        raise ValueError('input project-code is empty - there is no project to open a STAGE on')
    if credential is None:
        raise ValueError('no credential was handed over: mh-function.yaml declares api keyCode RG_API_AUTH, '
                         'but the params file carries no secretPort / checkCode')
    arguments = open_stage_arguments(code, optional_role(task, 'model'), optional_role(task, 'effort'))
    answer = call_tool(base + MCP_PATH, basic_authorization(credential), 'mhdg_rg_open_stage', arguments,
                       OPEN_STAGE_TIMEOUT_SEC)
    stage, genesis = the_stage(answer)
    write_text(stage_target, str(stage))
    write_text(genesis_target, str(genesis))
    print(code + ': empty genesis committed as snapshot ' + str(genesis) + ', STAGE ' + str(stage) + ' opened from it')
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
