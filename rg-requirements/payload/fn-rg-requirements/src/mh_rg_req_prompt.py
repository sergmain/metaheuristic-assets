# mh.asset.rg-req-prompt_1.0 - turn one meta-storage batch record into the prompt that asks CC for requirements.
#
# This file is NOT part of any bundle. It is reached only through the git block of
# rg-requirements/functions/fn-rg-req-prompt/mh-function.yaml.
#
# roles - every Variable is named by a meta, never hard-coded:
#   records       INPUT  - the JSON array internal mh.meta-storage (action select) wrote: [{type, recKey, body}]
#   description   INPUT  - what the requirements are for: the RG project's description
#   prompt        OUTPUT - the complete prompt for mh.asset.call-cc
#   source-path   OUTPUT - the file the prompt was built from
#
# THE FILE is the first non-blank line of the body of the first record, records ordered by recKey - so
# batch-0001 before batch-0002 when a selection returns several. It must be an absolute path. Its content goes
# into the prompt whole, up to meta max-file-bytes (default 300000). A larger file fails the Task rather than
# being cut: requirements derived from half a document would be presented as if they came from all of it.
#
# THE ANSWER CONTRACT is written into the prompt, because mh.asset.call-cc adds nothing of its own: a JSON array
# of {name, content, rationale}, delivered through its MCP tool mh_cc_store_result. mh.asset.rg-req-store
# parses exactly that.

import json
import os
import sys

from mh_task_io import NULL_VALUE, load_params, meta_value, output_role, read_role, write_text

FUNCTION_CODE = 'mh.asset.rg-req-prompt_1.0'
DEFAULT_MAX_FILE_BYTES = 300_000

# Each requirement after the first costs RG a committed snapshot, so the count is bounded.
MAX_REQUIREMENTS = 5

# mh.asset.call-cc's result channel: server mhcc, one tool.
STORE_SERVER = 'mhcc'
STORE_TOOL = 'mh_cc_store_result'


def first_path(records_json):
    """The absolute path on the first line of the first record's body."""
    try:
        records = json.loads(records_json)
    except ValueError:
        raise ValueError('the records are not JSON - expected the array mh.meta-storage select writes') from None
    if not isinstance(records, list) or not records:
        raise ValueError('no record was selected - the records array is empty (does the key exist in the table '
                         'this run reads, synthetic or not?)')
    usable = [r for r in records if isinstance(r, dict) and isinstance(r.get('body'), str)]
    if not usable:
        raise ValueError('no selected record carries a string body')
    record = sorted(usable, key=lambda r: str(r.get('recKey') or ''))[0]
    for line in record['body'].splitlines():
        path = line.strip()
        if path:
            if not os.path.isabs(path):
                raise ValueError("the first line of record '" + str(record.get('recKey'))
                                 + "' is not an absolute path: '" + path + "'")
            return path
    raise ValueError("record '" + str(record.get('recKey')) + "' has an empty body")


def parse_max_file_bytes(value):
    """meta max-file-bytes as a positive whole number, the default when the process does not declare it."""
    if value is None or not str(value).strip():
        return DEFAULT_MAX_FILE_BYTES
    try:
        limit = int(str(value).strip())
    except ValueError:
        raise ValueError("meta max-file-bytes must be a whole number, got '" + str(value) + "'") from None
    if limit < 1:
        raise ValueError('meta max-file-bytes must be positive, got ' + str(limit))
    return limit


def read_capped(path, max_bytes):
    """The file's text, decoded as UTF-8 - or a failure when it is over the cap. A missing file raises OSError."""
    size = os.path.getsize(path)
    if size > max_bytes:
        raise ValueError(path + ' is ' + str(size) + ' bytes, over the ' + str(max_bytes)
                         + '-byte cap (meta max-file-bytes)')
    with open(path, 'rb') as f:
        return f.read().decode('utf-8', errors='replace')


def compose_prompt(description, path, content):
    """The whole prompt: what the requirements are for, the document, and the answer contract."""
    return (
        'You are a requirements engineer.\n'
        'Project: ' + description.strip() + '\n'
        '\n'
        'Read the source document below and derive the requirements it states or implies for this project.\n'
        '\n'
        'Source document: ' + path + '\n'
        '<<<DOCUMENT\n'
        + content + ('' if content.endswith('\n') else '\n')
        + 'DOCUMENT>>>\n'
        '\n'
        'Answer contract - follow it exactly:\n'
        '1. Produce between 1 and ' + str(MAX_REQUIREMENTS) + ' requirements.\n'
        '2. The answer is ONE JSON array and nothing else. Each element is an object with exactly these keys:\n'
        '   "name"      - a short title, at most 80 characters\n'
        '   "content"   - the requirement itself, as one or more complete sentences of at least 3 words\n'
        '   "rationale" - why the document leads to this requirement\n'
        '3. Deliver the array by calling the MCP tool ' + STORE_TOOL + ' (server ' + STORE_SERVER + ') exactly once,'
        ' with the JSON array as its result argument. Do not deliver it any other way.\n'
    )


def main(argv):
    print(FUNCTION_CODE)
    params = load_params(argv)
    task = params['task']
    try:
        records = read_role(task, 'records')
        description = read_role(task, 'description').strip()
        prompt_target = output_role(task, 'prompt')
        path_target = output_role(task, 'source-path')
        if not description or description == NULL_VALUE:
            raise ValueError('input description is empty - the prompt has to say what the requirements are for')
        max_bytes = parse_max_file_bytes(meta_value(task.get('metas') or [], 'max-file-bytes'))
        path = first_path(records)
        content = read_capped(path, max_bytes)
        prompt = compose_prompt(description, path, content)
        write_text(prompt_target, prompt)
        write_text(path_target, path)
        print('source: ' + path + ' (' + str(len(content)) + ' characters), prompt: ' + str(len(prompt))
              + ' characters')
        return 0
    except (ValueError, OSError) as e:
        print('FAILED: ' + str(e))
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
