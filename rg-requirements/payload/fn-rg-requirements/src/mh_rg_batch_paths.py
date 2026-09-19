# mh.asset.rg-batch-paths_1.0 - turn the one batch record a run selected into the plain list of paths that
# internal mh.batch-line-splitter splits into branches.
#
# This file is NOT part of any bundle. It is reached only through the git block of
# rg-requirements/functions/fn-rg-batch-paths/mh-function.yaml.
#
# roles - every Variable is named by a meta, never hard-coded:
#   records   INPUT  - the JSON array internal mh.meta-storage (action select) wrote: [{type, recKey, body}]
#   paths     OUTPUT - the record's paths, one per line, in the record's order
#
# EXACTLY ONE record. The select names one key: none selected means the key is not in the table this run
# reads (synthetic or not), more than one means the select was not keyed. Either way the run would work on
# something other than the batch it was launched for, so it fails here - before a single CC call is paid for.
#
# EVERY PATH is checked before any is written: absolute, and listed once. The splitter gives each line a
# branch of its own, so a relative path would fail one branch after the others had spent CC on theirs, and a
# path listed twice would put the same file's requirements into the project twice.

import json
import os
import sys

from mh_task_io import load_params, output_role, read_role, write_text

FUNCTION_CODE = 'mh.asset.rg-batch-paths_1.0'


def the_record(records_json):
    """The one selected record: a dict with a string body."""
    try:
        records = json.loads(records_json)
    except ValueError:
        raise ValueError('the records are not JSON - expected the array mh.meta-storage select writes') from None
    if not isinstance(records, list):
        raise ValueError('the records are not a JSON array - expected the array mh.meta-storage select writes')
    if not records:
        raise ValueError('no record was selected - the records array is empty (does the key exist in the table '
                         'this run reads, synthetic or not?)')
    if len(records) != 1:
        keys = [str(r.get('recKey')) if isinstance(r, dict) else '?' for r in records]
        raise ValueError('expected exactly one selected record, got ' + str(len(records)) + ': ' + ', '.join(keys))
    record = records[0]
    if not isinstance(record, dict) or not isinstance(record.get('body'), str):
        raise ValueError('the selected record carries no string body')
    return record


def batch_paths(body, rec_key):
    """The non-blank lines of a record's body, stripped and in order - each absolute and each listed once, or a
    failure naming every line that is not."""
    paths = [line.strip() for line in body.splitlines() if line.strip()]
    if not paths:
        raise ValueError("record '" + rec_key + "' has an empty body - there is no file to derive requirements from")
    problems = []
    seen = set()
    for path in paths:
        if not os.path.isabs(path):
            problems.append("not an absolute path: '" + path + "'")
        elif path in seen:
            problems.append("listed more than once: '" + path + "'")
        seen.add(path)
    if problems:
        raise ValueError("record '" + rec_key + "' refused before any file was processed: " + '; '.join(problems))
    return paths


def main(argv):
    print(FUNCTION_CODE)
    params = load_params(argv)
    task = params['task']
    try:
        record = the_record(read_role(task, 'records'))
        target = output_role(task, 'paths')
        rec_key = str(record.get('recKey'))
        paths = batch_paths(record['body'], rec_key)
        write_text(target, '\n'.join(paths))
        print("record '" + rec_key + "': " + str(len(paths)) + ' path(s)')
        return 0
    except (ValueError, OSError) as e:
        print('FAILED: ' + str(e))
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
