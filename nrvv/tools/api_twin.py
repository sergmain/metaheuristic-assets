# The Anthropic API twin of an NRVV flow (plan 052, Phase 4): the same graph, every model call site moved to the API
# code of its Function and told to take the claude_api path. Twins are generated, never written by hand, so a base flow
# and its twin cannot drift.
#
#   python nrvv/tools/api_twin.py <base.mhsc>... [--out <dir>]
#
# NRVV's twins live in nrvv-api/source-codes (--out nrvv-api/source-codes): the API environment's own delivery unit,
# so importing it registers the twins and nothing of nrvv/ that is still under development (nrvv-api/DETAILS.md).
#
# Per base flow `source "<name>-<version>"` the twin is `source "<name>-api-<version>"`, written as
# <out>/<name>-api-<version>.mhsc (default: beside the base). Per call site of a model Function:
#
#   <process> := mh.asset.call-cc_<v> {          ->  <process> := mh.asset.call-cc-api_1.0 {
#   <process> := mh.asset.nrvv-implement_<v> {   ->  <process> := mh.asset.nrvv-implement-api_1.0 {
#   the first `meta` line of that process        ->  meta llm_provider = "claude_api",
#                                                         <the original first meta, re-indented>
#
# The API code is the one that declares api.keyCode ANTHROPIC_API_KEY; the meta is what selects the API path inside the
# shared payload. Refused, with the reason: a flow with no model call site, a call site without `variable-for-model`
# (the API has no default model), a call site that already carries llm_provider, a model code anywhere outside a call
# site (an unknown shape is not rewritten by guesswork), and an existing twin file that differs - a twin is a
# descriptor, so a changed twin needs a new base version (MH-GIT-DELIVERY-FUNCTION-DESCRIPTION.md 1.5).
#
# Not shipped: only nrvv/payload/fn-nrvv reaches a Processor.

import os
import re
import sys

API_CODES = (
    (re.compile(r'mh\.asset\.call-cc_\d+(?:\.\d+)*'), 'mh.asset.call-cc-api_1.0'),
    (re.compile(r'mh\.asset\.nrvv-implement_\d+(?:\.\d+)*'), 'mh.asset.nrvv-implement-api_1.0'),
)
MODEL_CODE = re.compile(r'mh\.asset\.(?:call-cc|nrvv-implement)_\d+(?:\.\d+)*')
CALL_SITE = re.compile(r'^(?P<head>\s*[A-Za-z0-9_.-]+\s*:=\s*)(?P<code>' + MODEL_CODE.pattern + r')(?P<tail>\s*\{\s*)$')
SOURCE = re.compile(r'^(?P<head>\s*source\s+")(?P<name>[A-Za-z0-9_.-]+?)-(?P<version>\d+(?:\.\d+)+)(?P<tail>".*)$')
META = re.compile(r'^(?P<indent>\s*)meta\s+(?P<rest>.*)$')
PROCESS_START = re.compile(r':=')
PROVIDER_META = 'llm_provider = "claude_api",'
TWIN_SUFFIX = '-api'


class TwinError(ValueError):
    pass


def api_code(code):
    for pattern, replacement in API_CODES:
        if pattern.fullmatch(code):
            return replacement
    raise TwinError('no API code for ' + code)


def _is_comment(line):
    return line.lstrip().startswith('//')


def twin(text, base_name='<base>'):
    """(twin text, twin uid, [(process line no, base code, api code)]). Line endings are kept as they are."""
    eol = '\r\n' if '\r\n' in text else '\n'
    lines = text.split(eol)
    uid = None
    sites = []
    inserted = 0   # lines added so far: a site is reported at its line in the BASE text
    i = 0
    while i < len(lines):
        line = lines[i]
        if _is_comment(line):
            i += 1
            continue
        source = SOURCE.match(line)
        if source:
            if uid is not None:
                raise TwinError(base_name + ': more than one source declaration')
            if source.group('name').endswith(TWIN_SUFFIX):
                raise TwinError(base_name + ': ' + source.group('name') + ' is already a twin')
            uid = source.group('name') + TWIN_SUFFIX + '-' + source.group('version')
            lines[i] = source.group('head') + uid + source.group('tail')
            i += 1
            continue
        site = CALL_SITE.match(line)
        if site:
            code = site.group('code')
            replacement = api_code(code)
            lines[i] = site.group('head') + replacement + site.group('tail')
            meta_at = _first_meta(lines, i + 1)
            if meta_at is None:
                raise TwinError(base_name + ': line ' + str(i + 1) + ', ' + code + ' - the call site has no meta')
            block = _meta_block(lines, meta_at)
            if 'variable-for-model' not in block:
                raise TwinError(base_name + ': line ' + str(i + 1) + ', ' + code + " - no 'variable-for-model': the "
                                'API path has no default model')
            if 'llm_provider' in block:
                raise TwinError(base_name + ': line ' + str(i + 1) + ', ' + code + ' - already carries llm_provider')
            meta = META.match(lines[meta_at])
            lines[meta_at:meta_at + 1] = [meta.group('indent') + 'meta ' + PROVIDER_META,
                                         meta.group('indent') + '     ' + meta.group('rest')]
            sites.append((i + 1 - inserted, code, replacement))
            inserted += 1
            i = meta_at + 2
            continue
        if MODEL_CODE.search(line):
            raise TwinError(base_name + ': line ' + str(i + 1) + ' names a model code outside a call site: '
                            + line.strip())
        i += 1
    if uid is None:
        raise TwinError(base_name + ': no source declaration')
    if not sites:
        raise TwinError(base_name + ': no model call site - a flow that calls no model needs no twin')
    header = ['// API TWIN of ' + base_name + ' - generated by nrvv/tools/api_twin.py (plan 052): every model call site',
              '// on the API code of its Function, with llm_provider = "claude_api". Do not edit: regenerate from the base.',
              '']
    return eol.join(header + lines), uid, sites


def _first_meta(lines, start):
    """The index of the first `meta` line of the process that starts before `start`, or None at the next process."""
    for j in range(start, len(lines)):
        if _is_comment(lines[j]):
            continue
        if PROCESS_START.search(lines[j]) or lines[j].strip() == '}':
            return None
        if META.match(lines[j]):
            return j
    return None


def _meta_block(lines, start):
    """The text of a meta statement: its first line and every continuation line after a trailing comma."""
    block = [lines[start]]
    j = start
    while lines[j].rstrip().endswith(',') and j + 1 < len(lines):
        j += 1
        block.append(lines[j])
    return '\n'.join(block)


def write_twin(base_path, out_dir=None):
    """Writes the twin of base_path; returns (twin path, 'written' | 'unchanged', sites)."""
    with open(base_path, encoding='utf-8', newline='') as f:
        text = f.read()
    twin_text, uid, sites = twin(text, os.path.basename(base_path))
    path = os.path.join(out_dir or os.path.dirname(os.path.abspath(base_path)), uid + '.mhsc')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        with open(path, encoding='utf-8', newline='') as f:
            if f.read() == twin_text:
                return path, 'unchanged', sites
        raise TwinError(path + ' exists with other content - a twin is a descriptor: bump the base version instead')
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(twin_text)
    return path, 'written', sites


def main(argv):
    args = argv[1:]
    out_dir = None
    if '--out' in args:
        at = args.index('--out')
        out_dir = args[at + 1]
        del args[at:at + 2]
    if not args:
        print('usage: python api_twin.py <base.mhsc>... [--out <dir>]')
        return 2
    failed = 0
    for base in args:
        try:
            path, state, sites = write_twin(base, out_dir)
            print(state + ' ' + path + ' - ' + ', '.join(c + ' -> ' + a + ' (line ' + str(n) + ')' for n, c, a in sites))
        except TwinError as e:
            failed += 1
            print('REFUSED ' + str(e))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
