# mh.asset.nrvv-source-ref_1.0 - cite the branch's file as repository + revision + repository-relative path, and put
# that citation into the branch's checked answer, so the store writes it into every requirement's Rationale (plan 042,
# section 3: the source of a recovered requirement is repository + revision + file; correction C1 of nrvv/DETAILS.md).
#
# Inputs  (process metas variable-for-<role>):
#   location     JSON {"url", "branchOrRef", "dir"} - the source the run recovers, as the request named it
#   commit       the sha mh.asset.nrvv-checkout_1.0 resolved the location to
#   dir-path     the absolute path of `dir` inside the checkout (nrvv-checkout's dir-path)
#   source-path  the branch's file: one absolute path, the splitter's line
#   answer       the branch's answer as mh.asset.rg-req-check_1.0 wrote it: ONE line of JSON
#                {"sourcePath": <source-path>, "requirements": [...]}
# Outputs:
#   source-ref   <url>@<commit>:<dir>/<the file relative to dir-path>, forward slashes; <url>@<commit>:<file> when
#                dir is the repository root
#   ref-answer   the same answer with its sourcePath replaced by source-ref - nothing else changed
#
# WHY AFTER check, NOT INSTEAD OF ITS PATH: rg-req-check refuses a source-path that is not an absolute path
# (mh_rg_req_path_prompt.the_path), so check keeps the real file. rg-req-store-stage pairs each answer with a line of
# its `paths` input by string equality and appends 'source: <path>' to every Rationale; both of its inputs are written
# here from ONE computed string, so they pair by construction. The shared rg-requirements Functions stay unchanged.
#
# ONE LINE, ASCII: the answer is re-written with json.dumps(ensure_ascii=True), as rg-req-check writes it.
#
# Pure but for run()/main(): no git, no network - the commit is the one nrvv-checkout already resolved.

import json
import os
import re
import sys

import mh_task_io as io
import nrvv_paths
from nrvv_checkout import parse_location

# a full sha: SHA-1 (40) or SHA-256 (64) hex, lower case as git prints it
COMMIT = re.compile(r'[0-9a-f]{40}(?:[0-9a-f]{24})?')
EXCERPT = 200


def one_line(text, role):
    """The one non-blank line of an input, stripped - or a failure naming the role."""
    lines = [line.strip() for line in (text or '').splitlines() if line.strip()]
    if len(lines) != 1:
        raise ValueError('input ' + role + ' must hold exactly one non-blank line, actual: ' + str(len(lines)))
    return lines[0]


def absolute(path, role):
    """The path normalized - or a failure when it is not absolute: every path of a run is shared by its Tasks."""
    if not os.path.isabs(path):
        raise ValueError('input ' + role + " is not an absolute path: '" + path + "'")
    return os.path.normpath(path)


def the_commit(text):
    """The full commit sha the checkout resolved, stripped - never a branch name or an abbreviation."""
    value = one_line(text, 'commit')
    if not COMMIT.fullmatch(value):
        raise ValueError("input commit is not a full commit sha: '" + value + "'")
    return value


def relative_file(source_path, dir_path):
    """The file's path relative to dir-path, in forward slashes - or a failure when it is not under dir-path."""
    try:
        rel = os.path.relpath(source_path, dir_path)
    except ValueError:  # another drive
        rel = None
    parts = [p for p in (rel or '').replace('\\', '/').split('/') if p]
    if not parts or parts == [os.curdir] or parts[0] == os.pardir:
        raise ValueError("input source-path '" + source_path + "' is not a file under dir-path '" + dir_path + "'")
    return '/'.join(parts)


def source_ref(location, commit, dir_path, source_path):
    """<url>@<commit>:<dir>/<file>, the file taken relative to dir-path, dir in git's own spelling."""
    rel_dir = nrvv_paths.rel_posix(location['dir'])
    file = relative_file(os.path.normpath(source_path), os.path.normpath(dir_path))
    return location['url'].strip() + '@' + commit + ':' + (rel_dir + '/' + file if rel_dir else file)


def ref_answer(answer_text, source_path, ref):
    """The checked answer with its sourcePath replaced by ref - or a failure when it is not one checked answer about
    the branch's own file."""
    line = one_line(answer_text, 'answer')
    try:
        answer = json.loads(line)
    except ValueError:
        raise ValueError('input answer is not JSON: ' + line[:EXCERPT]) from None
    if not isinstance(answer, dict) or not isinstance(answer.get('sourcePath'), str) \
            or not isinstance(answer.get('requirements'), list):
        raise ValueError('input answer is not {"sourcePath": ..., "requirements": [...]}: ' + line[:EXCERPT])
    if os.path.normpath(answer['sourcePath'].strip()) != os.path.normpath(source_path):
        raise ValueError("input answer is about '" + answer['sourcePath'] + "', not the branch's file '"
                         + source_path + "'")
    answer['sourcePath'] = ref
    return json.dumps(answer, ensure_ascii=True)


def run(task):
    location = parse_location(io.read_role(task, 'location'))
    commit = the_commit(io.read_role(task, 'commit'))
    dir_path = absolute(one_line(io.read_role(task, 'dir-path'), 'dir-path'), 'dir-path')
    source_path = absolute(one_line(io.read_role(task, 'source-path'), 'source-path'), 'source-path')
    ref = source_ref(location, commit, dir_path, source_path)
    answer = ref_answer(io.read_role(task, 'answer'), source_path, ref)
    io.write_text(io.output_role(task, 'source-ref'), ref)
    io.write_text(io.output_role(task, 'ref-answer'), answer)
    print('nrvv-source-ref: ' + ref)


def main(argv):
    run(io.load_params(argv)['task'])


if __name__ == '__main__':
    main(sys.argv)
