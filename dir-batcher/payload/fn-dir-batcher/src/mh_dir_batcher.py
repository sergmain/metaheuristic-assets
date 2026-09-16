# mh.asset.dir-batcher_1.0 - turn any directory into batches of files, ready for MH_META_STORAGE.
#
# This file is NOT part of any bundle. It is reached only through the git block of
# dir-batcher/functions/fn-dir-batcher/mh-function.yaml.
#
# REUSABLE BY CONSTRUCTION. Nothing about a particular run is written into this Function or into
# the .mhsc that calls it:
#
#   targetDir        an INPUT VARIABLE, delivered to variable/<input variable id>. The subject of
#                    the run arrives at run time, so one registered SourceCode batches any
#                    directory and pointing it somewhere else costs nothing.
#   metaStorageType  an OUTPUT. The type is minted here from the execContextId, so two runs never
#                    share a table, and the run reports where it put the data instead of a human
#                    reading it off the source.
#   batchRecords     an OUTPUT. JSON array of {type, recKey, body} - the wire format
#                    mh.meta-storage upserts.
#
# Both outputs are written as artifacts/<output variable id>.
#
# The core below - scan / chunk / rec_key / type_name / to_records - is pure, and it is what
# dir-batcher/tests exercises. main() is the boundary and is not unit-tested.

import json
import os
import sys

# Files per batch. A tuning constant, not a per-run parameter: changing it changes what a batch IS,
# which is a property of the capability rather than of the directory being batched.
BATCH_SIZE = 100

# Prefix of the minted type. The run's own identity is appended to it, never authored into it.
TYPE_PREFIX = 'mh.asset.dir-batch'


def scan(root, skip_dot_dirs=True):
    """Every regular file under root, as absolute paths, sorted.

    Sorted because a re-run must produce the same batches: os.walk makes no promise about order,
    and a queue that renumbers itself between runs cannot be resumed.

    Dot directories are pruned by default - .git alone would swamp a source tree with thousands
    of object files nobody asked to have batched.
    """
    paths = []
    for current, dirs, files in os.walk(root):
        if skip_dot_dirs:
            dirs[:] = [d for d in dirs if not d.startswith('.')]
        for name in files:
            full = os.path.join(current, name)
            if os.path.isfile(full):
                paths.append(os.path.abspath(full))
    paths.sort()
    return paths


def chunk(paths, batch_size):
    """Cut into batches of at most batch_size, order preserved. The last batch is the short one."""
    if batch_size < 1:
        raise ValueError('batch_size must be greater than 0, got ' + str(batch_size))
    return [paths[i:i + batch_size] for i in range(0, len(paths), batch_size)]


def rec_key(index, batch_count):
    """batch-0001, 1-based.

    The padding width is the wider of 4 and the batch count's own width, so the keys of one run
    always sort numerically - a 12,000-batch run pads to 5 rather than letting batch-10000 sort
    before batch-9999.
    """
    width = max(4, len(str(max(batch_count, 1))))
    return 'batch-' + str(index).zfill(width)


def type_name(exec_context_id, prefix=TYPE_PREFIX):
    """The table this run writes to. Per run by construction: nothing else can collide with it."""
    return prefix + '.' + str(exec_context_id)


def to_records(rec_type, paths, batch_size):
    """The records one run stores: body is the batch's paths, one per line."""
    chunks = chunk(paths, batch_size)
    return [
        {'type': rec_type, 'recKey': rec_key(i + 1, len(chunks)), 'body': '\n'.join(c)}
        for i, c in enumerate(chunks)
    ]


def read_input(cwd, params, name):
    var = next(v for v in params['inputs'] if v['name'] == name)
    with open(os.path.join(cwd, 'variable', str(var['id'])), 'r', encoding='utf-8') as f:
        return f.read()


def write_output(cwd, params, name, content):
    var = next(v for v in params['outputs'] if v['name'] == name)
    with open(os.path.join(cwd, 'artifacts', str(var['id'])), 'w', encoding='utf-8') as f:
        f.write(content)


def main(argv):
    # imported here rather than at module scope: the core above must stay importable by a test
    # that has no PyYAML installed, because nothing in the core needs it
    import yaml

    cwd = os.getcwd()
    print('mh.asset.dir-batcher_1.0')
    print('Cwd: ', cwd)
    print('Script: ', os.path.abspath(__file__))

    # the LAST positional argument is always the absolute path to the params file
    yaml_file = argv[len(argv) - 1]
    with open(yaml_file, 'r', encoding='utf-8') as stream:
        params = (yaml.load(stream, Loader=yaml.FullLoader))['task']

    target_dir = read_input(cwd, params, 'targetDir').strip()
    if not target_dir:
        print('FAILED: input variable targetDir is empty')
        return 1
    if not os.path.isdir(target_dir):
        print('FAILED: not a dir: ' + target_dir)
        return 1

    rec_type = type_name(params['execContextId'])
    paths = scan(target_dir)
    records = to_records(rec_type, paths, BATCH_SIZE)

    # the records first and the type second: a consumer reading the type variable must never find
    # the address of a queue that has not been filled yet
    write_output(cwd, params, 'batchRecords', json.dumps(records, ensure_ascii=False))
    write_output(cwd, params, 'metaStorageType', rec_type)

    print('dir=' + target_dir + ', files=' + str(len(paths)) + ', batchSize=' + str(BATCH_SIZE)
          + ', batches=' + str(len(records)) + ', type=' + rec_type)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))