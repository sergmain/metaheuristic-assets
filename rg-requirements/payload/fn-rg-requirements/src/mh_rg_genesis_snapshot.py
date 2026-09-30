# mh.asset.rg-genesis-snapshot_1.0 - the id of a fresh project's genesis snapshot: the fork point internal
# mhdg-rg.open-stage requires by name (parentSnapshotId) and that internal mhdg-rg.req-store-batch does not output.
#
# This file is NOT part of any bundle. It is reached only through the git block of
# rg-requirements/functions/fn-rg-genesis-snapshot/mh-function.yaml.
#
# roles - every Variable is named by a meta, never hard-coded:
#   rg-base-url   INPUT  - the RG the project lives in, e.g. http://localhost:64967
#   project-code  INPUT  - the project
#   snapshot-id   OUTPUT - the id of its genesis snapshot, as decimal text
#
# EXACTLY ONE snapshot. There is no HEAD (SNAPSHOT-TREE-DESCRIPTION 2.5), so this Function never picks "the latest":
# it answers only for a project whose whole tree is ONE COMMITTED snapshot without a parent - what the genesis of a
# project mkproject just created leaves - and refuses anything else, naming what it found.
#
# THE CREDENTIAL is the vault entry RG_API_AUTH, handed over on the Processor's loopback secret channel, exactly as
# mh.asset.rg-req-store-batch_1.0 receives it; the MCP call is the one that Function already makes.

import json
import sys

from mh_rg_mcp_client import call_tool
from mh_rg_req_store import basic_authorization, excerpt, rg_base
from mh_secret_client import exchange, extract_secret_fields, zero
from mh_task_io import load_params, output_role, read_role, write_text

FUNCTION_CODE = 'mh.asset.rg-genesis-snapshot_1.0'

MCP_PATH = '/rest/v1/legal/mcp'
LIST_TIMEOUT_SEC = 120


def the_genesis(listing):
    """The genesis snapshot's id from what mhdg_rg_list_snapshots answered - or a failure naming what was found."""
    if not isinstance(listing, dict):
        raise ValueError('mhdg_rg_list_snapshots answered no object')
    if listing.get('errorMessage'):
        raise ValueError('mhdg_rg_list_snapshots: ' + str(listing.get('errorMessage')))
    snapshots = listing.get('snapshots')
    if not isinstance(snapshots, list):
        raise ValueError('mhdg_rg_list_snapshots answered no snapshot list: ' + excerpt(json.dumps(listing)))
    found = ', '.join(str(s.get('snapshotId')) + ' ' + str(s.get('statusName')) for s in snapshots if isinstance(s, dict))
    if len(snapshots) != 1:
        raise ValueError('expected exactly one snapshot - the genesis of a fresh project - found ' + str(len(snapshots))
                         + (': ' + found if found else ''))
    snapshot = snapshots[0]
    if not isinstance(snapshot, dict) or snapshot.get('statusName') != 'COMMITTED' \
            or snapshot.get('parentSnapshotId') is not None or not isinstance(snapshot.get('snapshotId'), int):
        raise ValueError('the one snapshot is not a COMMITTED genesis without a parent: ' + excerpt(json.dumps(snapshot)))
    return snapshot['snapshotId']


def run(task, credential):
    base = rg_base(read_role(task, 'rg-base-url'))
    code = (read_role(task, 'project-code') or '').strip()
    target = output_role(task, 'snapshot-id')
    if not code:
        raise ValueError('input project-code is empty - there is no project to read')
    if credential is None:
        raise ValueError('no credential was handed over: mh-function.yaml declares api keyCode RG_API_AUTH, '
                         'but the params file carries no secretPort / checkCode')
    listing = call_tool(base + MCP_PATH, basic_authorization(credential), 'mhdg_rg_list_snapshots',
                        {'infoBank': code}, LIST_TIMEOUT_SEC)
    snapshot_id = the_genesis(listing)
    write_text(target, str(snapshot_id))
    print(code + ': genesis snapshot ' + str(snapshot_id))
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
