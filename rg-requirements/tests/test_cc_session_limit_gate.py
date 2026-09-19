# Whether a CC session limit, hit inside the batch workflow's cc step, is something the Dispatcher's execution gate
# can identify.
#
# The gate never interprets a console itself. A failed Task is matched against the analyzer rules its Function's
# descriptor declares (plus any the Dispatcher's own config adds; this installation's adds none), and a hit blocks
# the scope the rule names for the rule's timeout. So the question is answered by two artifacts in this repo: which
# call-cc Function the batch workflow's cc process runs, and what that Function's mh-function.yaml declares. Both are
# read from the files that ship - nothing here restates them.
#
# The matching below is MH's own, FunctionAnalyzerUtils.firstHit: every pattern of every analyzer, find() - not
# matches() - anywhere in the console, no implicit flags. The patterns kept to here are the same in Java's and in
# Python's regex dialect.

import glob
import os
import re

import yaml

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

# Task #664 of ExecContext #26, as the Dispatcher stored it: CC's own words, with the separator after "limit" already
# mangled into U+FFFD on the way through the Processor's code page.
SESSION_LIMIT_CONSOLE = (
    'mh.asset.call-cc\n'
    'prompt: 22339 chars\n'
    "command: ['claude', '--debug', '--print', '--output-format', 'text', '--mcp-config', '.mcp.json',"
    " '--allowedTools', 'mcp__mhcc__*']\n"
    'timeout: 900s\n'
    '--- CC console ---\n'
    "You've hit your session limit \ufffd resets 8:30pm (America/Los_Angeles)\n"
    '\n'
    'exit code: 1\n'
    'FAILED: Claude Code exited with code 1\n')


def batch_mhsc():
    paths = glob.glob(os.path.join(REPO, 'rg-requirements', 'source-codes', 'mh-rg-requirements-from-batch-*.mhsc'))
    assert len(paths) == 1, 'expected exactly one batch workflow, found: ' + str(paths)
    return paths[0]


def cc_function_code():
    """The Function code the batch workflow's cc process runs, read from the .mhsc."""
    with open(batch_mhsc(), encoding='utf-8') as f:
        found = re.search(r'^\s*cc := (\S+) \{', f.read(), re.MULTILINE)
    assert found, 'the batch workflow declares no cc process'
    return found.group(1)


def descriptor_of(code):
    """The function block of the call-cc mh-function.yaml declaring this code."""
    for path in glob.glob(os.path.join(REPO, 'call-cc', 'functions', '*', 'mh-function.yaml')):
        with open(path, encoding='utf-8') as f:
            function = yaml.safe_load(f)['function']
        if function['code'] == code:
            return function
    raise AssertionError('no call-cc descriptor declares ' + code)


def first_hit(analyzers, console):
    """FunctionAnalyzerUtils.firstHit: the first analyzer any of whose patterns is found anywhere in the console."""
    for analyzer in analyzers or []:
        for regex in analyzer.get('regex') or []:
            if regex and re.search(regex, console):
                return analyzer
    return None


def test_the_batch_workflows_cc_step_identifies_a_cc_session_limit():
    function = descriptor_of(cc_function_code())

    hit = first_hit(function.get('analyzers'), SESSION_LIMIT_CONSOLE)

    assert hit is not None, 'the session limit must match an analyzer of the Function the cc step runs'
    # what MH accepts in a descriptor (FunctionAnalyzerUtils.checkScopeAllowedInDescriptor, parseTimeout)
    assert hit['scope'] in ('api', 'function', 'processor')
    assert re.fullmatch(r'\d+(ms|s|min|h|d)', str(hit['timeout']).strip())
    assert hit['incrementTries'] is False, 'a spent session is never the Task\'s fault - its retry must be free'


def test_the_limit_is_identified_whatever_separator_survives_the_trip():
    analyzers = descriptor_of(cc_function_code()).get('analyzers')

    for separator in ('\u00b7', '\u2219', '-', '\ufffd', ''):
        console = "You've hit your session limit " + separator + ' resets 8:30pm (America/Los_Angeles)\n'
        assert first_hit(analyzers, console) is not None, 'separator ' + repr(separator)


def test_a_console_that_merely_mentions_a_limit_blocks_nothing():
    # a false hit withholds call-cc for the analyzer's whole timeout, so the rule must not fire on ordinary output
    analyzers = descriptor_of(cc_function_code()).get('analyzers')
    ordinary = (
        'mh.asset.call-cc\n'
        '--- CC console ---\n'
        '[DEBUG] Rate limit headers: anthropic-ratelimit-unified-status=allowed\n'
        '[DEBUG] context window limit: 200000 tokens\n'
        'meta max-file-bytes limits the file to 300000 bytes\n'
        'exit code: 0\n'
        'stored 3845 bytes into output variable "ccResult"\n')

    assert first_hit(analyzers, ordinary) is None
