# mh.asset.dir-batcher_1.0 - turn any directory into batches of source files, ready for MH_META_STORAGE.
#
# This file is NOT part of any bundle. It is reached only through the git block of
# dir-batcher/functions/fn-dir-batcher/mh-function.yaml.
#
# REUSABLE BY CONSTRUCTION. Nothing about a particular run is written into this Function or into the
# .mhsc that calls it:
#
#   targetDir        an INPUT VARIABLE, delivered to variable/<input variable id>
#   metaStorageType  an OUTPUT - minted here from the execContextId, so two runs never share a table
#   batchRecords     an OUTPUT - JSON array of {type, recKey, body}, what mh.meta-storage upserts
#
# The core below - scan / is_selected / chunk / rec_key / type_name / to_records - is pure, and it is
# what dir-batcher/tests exercises. main() is the boundary and is not unit-tested.

import fnmatch
import json
import os
import sys

# Files per batch. A tuning constant, not a per-run parameter: changing it changes what a batch IS,
# which is a property of the capability rather than of the directory being batched.
BATCH_SIZE = 100

# Prefix of the minted type. The run's own identity is appended to it, never authored into it.
TYPE_PREFIX = 'mh.asset.dir-batch-for-requirements'

# ---------------------------------------------------------------------------------------------------
# NEGATIVE FILTER - directories that are never walked.
#
# Applied FIRST, before any mask is considered, and pruned in place so os.walk never descends into
# them at all. Order matters for more than speed: a .java under node_modules or target is generated or
# vendored, and it would pass the positive filter on its name alone. Excluding the tree is the only
# place that distinction can be made.
#
# Any directory whose name starts with a dot is pruned as well (skip_dot_dirs), which already covers
# .git and .angular; they are named here too so the list reads as the whole intent rather than half
# of it.
EXCLUDED_DIRS = frozenset({
    # version control
    '.git', '.hg', '.svn',
    # IDE and tooling state
    '.idea', '.vscode', '.settings', '.metadata', '.gradle', '.mvn', '.angular',
    # language and test caches
    '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.tox', '.eggs',
    # virtualenvs and dependency trees
    '.venv', 'venv', 'node_modules', 'bower_components', 'vendor', 'site-packages',
    # build output and staging
    'target', 'build', 'out', 'dist', 'bin', 'obj', 'coverage', '.next', '.nuxt', '.cache',
})

# ---------------------------------------------------------------------------------------------------
# POSITIVE FILTER - file masks, as one general group plus one group per language or framework.
#
# To support a new language: add a group below and list it in ALL_FILE_MASKS. Nothing else changes.
# Grouping is not decoration - it is what makes the next addition a two-line edit that a reviewer can
# see the intent of, instead of an append to an undifferentiated list.
MASKS_GENERAL = ('*.md', '*.properties', 'LICENSE.*')

MASKS_JAVA = ('*.java',)
MASKS_SQL = ('*.sql',)
MASKS_PYTHON = ('*.py',)
MASKS_TYPESCRIPT = ('*.ts',)
MASKS_JAVASCRIPT = ('*.js',)
MASKS_GOLANG = ('*.go',)

MASKS_MAVEN = ('pom.xml',)
MASKS_ANT = ('build.xml',)
MASKS_ANGULAR = ('angular.json', 'package.json', '*.html', '*.css', '*.scss', '*.sass')
MASKS_SPRING_BOOT = ('application*.yaml', 'application*.yml')

ALL_FILE_MASKS = tuple(sorted(set(
    MASKS_GENERAL
    + MASKS_JAVA + MASKS_SQL + MASKS_PYTHON + MASKS_TYPESCRIPT + MASKS_JAVASCRIPT + MASKS_GOLANG
    + MASKS_MAVEN + MASKS_ANT + MASKS_ANGULAR + MASKS_SPRING_BOOT
)))


def is_selected(name, file_masks=ALL_FILE_MASKS):
    """True when a file NAME matches at least one mask.

    fnmatchcase, not fnmatch: the latter folds case on Windows and not on Linux, so the same tree
    would batch differently depending on which Processor picked up the Task. A queue whose contents
    depend on the machine that built it cannot be resumed on another one.
    """
    return any(fnmatch.fnmatchcase(name, mask) for mask in file_masks)


def scan(root, excluded_dirs=EXCLUDED_DIRS, file_masks=ALL_FILE_MASKS, skip_dot_dirs=True):
    """Every selected file under root, as absolute paths, sorted.

    Negative filter first, positive filter second. Sorted because a re-run must produce the same
    batches: os.walk makes no promise about order, and a queue that renumbers itself between runs
    cannot be resumed.
    """
    paths = []
    for current, dirs, files in os.walk(root):
        # in place, so os.walk does not descend - this is the negative filter, and it runs first
        dirs[:] = [d for d in dirs
                   if d not in excluded_dirs and not (skip_dot_dirs and d.startswith('.'))]
        for name in files:
            if not is_selected(name, file_masks):
                continue
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

    The padding width is the wider of 4 and the batch count's own width, so the keys of one run always
    sort numerically - a 12,000-batch run pads to 5 rather than letting batch-10000 sort before
    batch-9999.
    """
    width = max(4, len(str(max(batch_count, 1))))
    return 'batch-' + str(index).zfill(width)


# What the registry is told about the table this run creates. The Function is the only thing that
# knows these: the recKey shape and the body encoding are properties of how IT writes, and the
# description needs the directory that was actually scanned. Asking the .mhsc to carry them would be
# asking a second place to stay in step with this one.
REC_KEY_FORMAT = 'batch-NNNN, 1-based, zero-padded to the width of the batch count'
BODY_FORMAT = 'one absolute file path per line'
CONSUMER = 'list the keys, take one, read its paths, do the work, delete that record'


def describe(target_dir, file_count, batch_size=BATCH_SIZE):
    """One sentence for a reader who was not here, naming the tree that was actually scanned."""
    return ('Source-file paths found under ' + str(target_dir) + ' - ' + str(file_count)
            + ' files, ' + str(batch_size) + ' paths per record')


def is_synthetic(production):
    """Whether this run writes to the synthetic meta storage table.

    Production mode is the literal 'true' and nothing else. Every other value means development:
    'mh.null-value', an empty string, 'True', a typo. That asymmetry is deliberate - a row written to
    the production store cannot be un-written by re-running, while a run that lands in the synthetic
    store costs one re-run. So the expensive mistake is the one requiring a deliberate act.
    """
    return production is None or production.strip() != 'true'


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
    # imported here rather than at module scope: the core above must stay importable by a test that
    # has no PyYAML installed, because nothing in the core needs it
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

    # REQUIRED, never optional: a caller with no value still has to pass something, so an optional
    # declaration would only hide the question of which string means absent. 'mh.null-value' is that
    # string by convention, and like every non-'true' value it selects development.
    production = read_input(cwd, params, 'production')
    synthetic = is_synthetic(production)

    rec_type = type_name(params['execContextId'])
    paths = scan(target_dir)
    records = to_records(rec_type, paths, BATCH_SIZE)

    # the records first and the type second: a consumer reading the type variable must never find the
    # address of a queue that has not been filled yet
    write_output(cwd, params, 'batchRecords', json.dumps(records, ensure_ascii=False))
    write_output(cwd, params, 'metaStorageType', rec_type)
    write_output(cwd, params, 'syntheticFlag', 'true' if synthetic else 'false')

    # for mh.meta-storage-registry, which runs BEFORE mh.meta-storage writes a single record
    write_output(cwd, params, 'tableDesc', describe(target_dir, len(paths)))
    write_output(cwd, params, 'tableRecKeyFormat', REC_KEY_FORMAT)
    write_output(cwd, params, 'tableBodyFormat', BODY_FORMAT)
    write_output(cwd, params, 'tableConsumer', CONSUMER)

    print('dir=' + target_dir + ', files=' + str(len(paths)) + ', batchSize=' + str(BATCH_SIZE)
          + ', batches=' + str(len(records)) + ', type=' + rec_type
          + ', production=' + repr(production) + ', synthetic=' + str(synthetic))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))