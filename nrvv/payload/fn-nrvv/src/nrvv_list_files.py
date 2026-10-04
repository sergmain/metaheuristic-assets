# mh.asset.nrvv-list-files_1.0 - the files under a dir that match an include glob and no exclude glob, one
# absolute path per line, sorted. The input of the per-file split of the recovery run (plan 042, decision 11).
#
# Globs are matched against the path RELATIVE to the dir, in forward slashes, case-sensitively:
#   *    any run of characters except '/'
#   ?    one character except '/'
#   **/  zero or more whole directories        (**/*.java matches A.java and a/b/A.java)
#   **   anything, '/' included
# No include glob means no file: the include list states what is wanted, and an empty one wants nothing.
# Directories named .git are never entered.

import json
import os
import re
import sys

import mh_task_io as io


def glob_to_regex(glob):
    g = glob.replace('\\', '/')
    out = []
    i = 0
    while i < len(g):
        if g.startswith('**/', i):
            out.append('(?:.*/)?')
            i += 3
        elif g.startswith('**', i):
            out.append('.*')
            i += 2
        elif g[i] == '*':
            out.append('[^/]*')
            i += 1
        elif g[i] == '?':
            out.append('[^/]')
            i += 1
        else:
            out.append(re.escape(g[i]))
            i += 1
    return re.compile('^' + ''.join(out) + '$')


def list_files(root, include_globs, exclude_globs):
    """Sorted absolute paths of the files under root matching some include glob and no exclude glob."""
    includes = [glob_to_regex(g) for g in include_globs or []]
    excludes = [glob_to_regex(g) for g in exclude_globs or []]
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != '.git']
        for name in filenames:
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace('\\', '/')
            if any(r.match(rel) for r in includes) and not any(r.match(rel) for r in excludes):
                found.append(os.path.abspath(path))
    return sorted(found)


def parse_globs(text):
    """A JSON array of glob strings; a NULLIFIED Variable (None) is an empty list."""
    if text is None or not text.strip():
        return []
    value = json.loads(text)
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError('globs must be a JSON array of strings, actual: ' + text)
    return value


def main(argv):
    task = io.load_params(argv)['task']
    root = io.read_role(task, 'dir-path').strip()
    files = list_files(root, parse_globs(io.read_role(task, 'include-globs')),
                       parse_globs(io.read_role(task, 'exclude-globs')))
    io.write_text(io.output_role(task, 'files'), '\n'.join(files))
    print('nrvv-list-files: ' + str(len(files)) + ' file(s) under ' + root)


if __name__ == '__main__':
    main(sys.argv)
