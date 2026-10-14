# mh.asset.call-cc_1.2 (plan 047, decision 19): what the Dispatcher's execution gate identifies in a failed call-cc
# Task's console. Read from the descriptor that ships - nothing here restates its rules. The matching is MH's own,
# FunctionAnalyzerUtils.firstHit: every pattern of every analyzer, find() anywhere in the console, no implicit flags.

import glob
import os
import re

import yaml

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

# the CC CLI on a Processor whose OAuth login expired and could not be refreshed: every CC Task there fails this way
OAUTH_EXPIRED_CONSOLE = (
    'mh.asset.call-cc\n'
    'prompt: 18233 chars\n'
    'timeout: 900s\n'
    '--- CC console ---\n'
    'API Error: 401 {"type":"error","error":{"type":"authentication_error",'
    '"message":"OAuth session expired and could not be refreshed"}}\n'
    '\n'
    'exit code: 1\n'
    'FAILED: Claude Code exited with code 1\n')

SESSION_LIMIT_CONSOLE = "You've hit your session limit \ufffd resets 8:30pm (America/Los_Angeles)\n"

ORDINARY_CONSOLE = (
    'mh.asset.call-cc\n'
    '--- CC console ---\n'
    '[DEBUG] OAuth token refreshed\n'
    '[DEBUG] Rate limit headers: anthropic-ratelimit-unified-status=allowed\n'
    'exit code: 0\n'
    'stored 3845 bytes into output variable "ccResult"\n')


def descriptor_of(code):
    for path in glob.glob(os.path.join(REPO, 'call-cc', 'functions', '*', 'mh-function.yaml')):
        with open(path, encoding='utf-8') as f:
            function = yaml.safe_load(f)['function']
        if function['code'] == code:
            return function
    raise AssertionError('no call-cc descriptor declares ' + code)


def first_hit(analyzers, console):
    for analyzer in analyzers or []:
        for regex in analyzer.get('regex') or []:
            if regex and re.search(regex, console):
                return analyzer
    return None


def test_an_expired_oauth_login_withholds_the_processor_and_spends_no_try():
    hit = first_hit(descriptor_of('mh.asset.call-cc_1.2').get('analyzers'), OAUTH_EXPIRED_CONSOLE)
    assert hit is not None, 'the expired OAuth login must match an analyzer of mh.asset.call-cc_1.2'
    assert hit['scope'] == 'processor', 'the login is per Processor: the Function still runs elsewhere'
    assert hit['incrementTries'] is False
    assert re.fullmatch(r'\d+(ms|s|min|h|d)', str(hit['timeout']).strip())
    assert str(hit['timeout']).strip() == '30min'


def test_1_2_keeps_the_session_limit_analyzer_of_1_1():
    hit = first_hit(descriptor_of('mh.asset.call-cc_1.2').get('analyzers'), SESSION_LIMIT_CONSOLE)
    assert hit is not None
    assert hit['scope'] == 'function'
    assert hit['incrementTries'] is False


def test_1_1_does_not_know_the_oauth_line():
    assert first_hit(descriptor_of('mh.asset.call-cc_1.1').get('analyzers'), OAUTH_EXPIRED_CONSOLE) is None


def test_an_ordinary_console_blocks_nothing():
    assert first_hit(descriptor_of('mh.asset.call-cc_1.2').get('analyzers'), ORDINARY_CONSOLE) is None


def test_the_v5_flows_name_call_cc_1_2():
    # plan 047: every v5 development flow names mh.asset.call-cc_1.2
    for name in ('nrvv-expectation-analysis-1.0.mhsc', 'nrvv-cv-need-contradiction-1.0.mhsc',
                 'nrvv-cv-need-quality-1.0.mhsc', 'nrvv-cv-need-feasibility-1.0.mhsc',
                 # plan 047 Phase 14
                 'nrvv-definition-baseline-1.2.mhsc', 'nrvv-redefinition-1.2.mhsc',
                 'nrvv-cv-need-backtrace-1.0.mhsc',
                 # plan 047 Phase 20
                 'nrvv-criteria-1.1.mhsc', 'nrvv-suite-author-1.2.mhsc',
                 # plan 047 Phase 23
                 'nrvv-triage-1.0.mhsc'):
        with open(os.path.join(REPO, 'nrvv', 'source-codes', name), encoding='utf-8') as f:
            codes = set(re.findall(r'(mh\.asset\.call-cc[_0-9.]*) \{', f.read()))
        assert codes == {'mh.asset.call-cc_1.2'}, name + ': ' + str(codes)
