# A requirement as the TEST_AUTHOR prompts show it (plan 042, Phase 10). Pure: no IO.
#
# mhdg-rg.read-req hands a requirement over as RG stores its document: a {{METADATA...}}...{{/METADATA}} block, then
# the title and the numbered items (1. Requirement content, 2. Rationale, 3. Constraints, 4. Acceptance), every
# paragraph prefixed with a {{M=<n>}} marker. A prompt gets the readable text: the block and the markers removed,
# nothing reworded.
#
# The Rationale of a recovered requirement ends with `source: <citation>` (nrvv/DETAILS.md, Recovery R5): a repository
# citation `<url>@<commit>:<dir>/<File>.java`, or - before correction C1 - an absolute file path. The file it names
# decides the Python module the tests import: every requirement recovered from one file is verified against one
# module, so suites written in parallel agree on the API the implementer must provide.

import re

METADATA = re.compile(r'\{\{METADATA[^}]*\}\}.*?\{\{/METADATA\}\}', re.DOTALL)
MARKER = re.compile(r'\{\{M=\d+\}\}')
SOURCE = re.compile(r'^\s*(?:\d+(?:\.\d+)*\)\s*)?source:\s*(\S.*?)\s*$', re.MULTILINE)
BLANK_RUN = re.compile(r'\n{3,}')
# a repository citation <url>@<commit>:<repository-relative path>; the path is what follows the commit
REPO_CITATION = re.compile(r'@[0-9a-fA-F]{7,64}:(.*)$')

# the module every test imports when the requirement names no source file (a requirement authored by hand)
DEFAULT_MODULE = 'app'


def plain_text(content):
    """The requirement's readable text: RG's metadata block and paragraph markers removed, trailing spaces dropped,
    at most one blank line in a row. Nothing else changes."""
    text = METADATA.sub('', content or '')
    text = MARKER.sub('', text)
    lines = [line.rstrip() for line in text.replace('\r\n', '\n').split('\n')]
    return BLANK_RUN.sub('\n\n', '\n'.join(lines)).strip()


def source_citation(content):
    """The value of the requirement's LAST `source:` line, or None when it has none."""
    found = SOURCE.findall(plain_text(content))
    return found[-1] if found else None


def source_file_name(citation):
    """The file a citation names: the last '/'- or '\\'-separated part of its path - for a repository citation the
    path after '@<commit>:', since the url before it has slashes of its own. None for a blank citation."""
    if not citation or not citation.strip():
        return None
    text = citation.strip()
    repo = REPO_CITATION.search(text)
    path = repo.group(1) if repo else text
    name = re.split(r'[/\\]', path)[-1]
    return name or None


def snake_case(stem):
    """NrvvSample -> nrvv_sample, HTTPServer -> http_server, Main -> main; anything but [a-z0-9] becomes '_'."""
    s = re.sub(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', '_', stem)
    return re.sub(r'[^A-Za-z0-9]+', '_', s).strip('_').lower()


def module_name(content):
    """The Python module the tests of this requirement import: the snake_case stem of its source file, prefixed with
    'm_' when it would start with a digit; DEFAULT_MODULE when the requirement names no source file."""
    file_name = source_file_name(source_citation(content))
    if not file_name:
        return DEFAULT_MODULE
    stem = file_name.rsplit('.', 1)[0] if '.' in file_name else file_name
    name = snake_case(stem)
    if not name:
        return DEFAULT_MODULE
    return 'm_' + name if name[0].isdigit() else name
