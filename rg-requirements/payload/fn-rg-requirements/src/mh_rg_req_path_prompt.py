# mh.asset.rg-req-path-prompt_1.0 - build the CC prompt for ONE source file, named by its path.
#
# This file is NOT part of any bundle. It is reached only through the git block of
# rg-requirements/functions/fn-rg-req-path-prompt/mh-function.yaml.
#
# roles - every Variable is named by a meta, never hard-coded:
#   source-path   INPUT  - the file's absolute path: the one line internal mh.batch-line-splitter handed this branch
#   description   INPUT  - what the requirements are for: the RG project's description
#   prompt        OUTPUT - the complete prompt for mh.asset.call-cc
#
# The cap, the reading and the prompt are mh.asset.rg-req-prompt_1.0's own - read_capped, compose_prompt,
# parse_max_file_bytes - so a file becomes the same prompt whichever of the two workflows asks. The only
# difference is where the path comes from. A file over meta max-file-bytes (default 300000) fails the Task
# rather than being cut, for the reason given there.

import os
import sys

from mh_rg_req_prompt import compose_prompt, parse_max_file_bytes, read_capped
from mh_task_io import NULL_VALUE, load_params, meta_value, output_role, read_role, write_text

FUNCTION_CODE = 'mh.asset.rg-req-path-prompt_1.0'


def the_path(text):
    """The one absolute path a branch was handed, stripped."""
    lines = [line.strip() for line in (text or '').splitlines() if line.strip()]
    if not lines:
        raise ValueError('input source-path is empty - this branch was handed no file')
    if len(lines) != 1:
        raise ValueError('input source-path holds ' + str(len(lines)) + ' lines, expected exactly one path '
                         '(meta number-of-lines-per-task of the splitter must be 1)')
    path = lines[0]
    if not os.path.isabs(path):
        raise ValueError("input source-path is not an absolute path: '" + path + "'")
    return path


def prompt_for(path, description, max_bytes):
    """(prompt, characters of the file): the file read under the cap and put into the prompt whole."""
    if not description or not description.strip() or description.strip() == NULL_VALUE:
        raise ValueError('input description is empty - the prompt has to say what the requirements are for')
    content = read_capped(path, max_bytes)
    return compose_prompt(description.strip(), path, content), len(content)


def main(argv):
    print(FUNCTION_CODE)
    params = load_params(argv)
    task = params['task']
    try:
        path = the_path(read_role(task, 'source-path'))
        description = read_role(task, 'description')
        target = output_role(task, 'prompt')
        max_bytes = parse_max_file_bytes(meta_value(task.get('metas') or [], 'max-file-bytes'))
        prompt, characters = prompt_for(path, description, max_bytes)
        write_text(target, prompt)
        print('source: ' + path + ' (' + str(characters) + ' characters), prompt: ' + str(len(prompt))
              + ' characters')
        return 0
    except (ValueError, OSError) as e:
        print('FAILED: ' + str(e))
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
