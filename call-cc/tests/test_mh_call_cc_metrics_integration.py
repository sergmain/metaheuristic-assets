# An integration test of the mh.metrics output: mh.asset.call-cc's REAL main() with the `claude` CLI replaced by a fake
# python script that answers the way CC 2.1.314 does under --output-format json (one result line on stdout, measured on
# 2026-11-06), and run_claude_api against a local Messages API.
#
#   1. the session is asked for its JSON result, and the result's final text still reaches the console as text;
#   2. a declared output of type mh.metrics receives ONE CC entry with the session's counts and its time;
#   3. a process that declares none gets no file - the run is the run it was before;
#   4. an outage the model reports INSIDE the JSON result still ends the Function with the negative exit code;
#   5. a console with no result line (an older CLI, a CLI that failed early) records the call with null counts;
#   6. two such outputs fail before CC is ever started;
#   7. on the API path, the one request is recorded with the response's usage.
#
# Same shape as test_mh_call_cc_mcp_unavailable_integration.py: no doubles, no monkeypatching of production.

import contextlib
import io
import json
import os
import stat
import sys

import mh_call_cc
from test_mh_api_call import EchoMessagesApi, ProcessorSecretChannel

FAKE_HEAD = (
    "import json, os, sys\n"
    "here = os.path.dirname(os.path.abspath(__file__))\n"
    "with open(os.path.join(here, 'cc-argv.json'), 'w', encoding='utf-8') as f:\n"
    "    json.dump(sys.argv[1:], f)\n"
    "sys.stdin.buffer.read()\n"
    "def say(text):\n"
    "    sys.stdout.buffer.write((text + '\\n').encode('utf-8'))\n"
    "def result(text):\n"
    "    say(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'result': text,\n"
    "                    'usage': {'input_tokens': 2, 'output_tokens': 193, 'cache_creation_input_tokens': 18176,\n"
    "                              'cache_read_input_tokens': 16560},\n"
    "                    'modelUsage': {'claude-haiku-5-5': {'inputTokens': 2, 'outputTokens': 193,\n"
    "                                   'cacheReadInputTokens': 16560, 'cacheCreationInputTokens': 18176}}}))\n"
)

# A healthy session: the answer stored where the MCP server stores it, then CC's one JSON line.
HEALTHY_FAKE = FAKE_HEAD + (
    "os.makedirs('cc-data', exist_ok=True)\n"
    "with open(os.path.join('cc-data', 'cc-result.out'), 'w', encoding='utf-8') as f:\n"
    "    f.write('the answer')\n"
    "result('Stored the answer with mh_cc_store_result.')\n"
    "sys.stdout.buffer.flush()\n"
    "sys.exit(0)\n"
)

# The model found the MCP server gone: its one line is the session's final text, so under --output-format json it is
# INSIDE the result line - no console line starts with the marker any more. CC itself exits 0.
UNAVAILABLE_FAKE = FAKE_HEAD + (
    "result('MCP_UNAVAILABLE: CONNECTION_CLOSED')\n"
    "sys.stdout.buffer.flush()\n"
    "sys.exit(0)\n"
)

# A console with no result line at all - an answer stored, but nothing CC-shaped printed.
TEXT_FAKE = FAKE_HEAD + (
    "os.makedirs('cc-data', exist_ok=True)\n"
    "with open(os.path.join('cc-data', 'cc-result.out'), 'w', encoding='utf-8') as f:\n"
    "    f.write('the answer')\n"
    "say('Stored the answer.')\n"
    "sys.stdout.buffer.flush()\n"
    "sys.exit(0)\n"
)

METRICS_OUTPUT = (
    "    - name: ccMetrics\n"
    "      id: 3\n"
    "      dataType: variable\n"
    "      type: mh.metrics\n"
)


def _write(path, text):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def _fake_claude(scripts_dir, script):
    fake = scripts_dir / 'fake_cc.py'
    _write(fake, script)
    if os.name == 'nt':
        shim = scripts_dir / 'claude.cmd'
        _write(shim, '@"{}" "{}" %*\n'.format(sys.executable, fake))
    else:
        shim = scripts_dir / 'claude'
        _write(shim, '#!/bin/sh\nexec "{}" "{}" "$@"\n'.format(sys.executable, fake))
        os.chmod(shim, os.stat(shim).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return shim


def _task(tmp_path, script, extra_outputs=METRICS_OUTPUT):
    work = tmp_path / 'task'
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    (work / 'variable').mkdir(parents=True)
    _write(work / 'variable' / '1', 'derive requirements from this file')
    (work / 'artifacts').mkdir(parents=True)
    _write(work / 'artifacts' / 'mh-env.yaml', "envs:\n  claude-code: '{}'\n".format(_fake_claude(scripts, script)))
    params = (
        "task:\n"
        "  workingPath: '{}'\n"
        "  metas:\n"
        "    - variable-for-prompt: prompt\n"
        "    - variable-for-output: result\n"
        "    - timeout-sec: '30'\n"
        "  inputs:\n"
        "    - name: prompt\n"
        "      id: 1\n"
        "      dataType: variable\n"
        "  outputs:\n"
        "    - name: result\n"
        "      id: 2\n"
        "      dataType: variable\n"
    ).format(work) + extra_outputs
    params_path = work / 'params.yaml'
    _write(params_path, params)
    return work, scripts, params_path


def _run(params_path):
    out = io.TextIOWrapper(io.BytesIO(), encoding='utf-8', newline='')
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        rc = mh_call_cc.main([str(params_path)])
    out.flush()
    return rc, out.buffer.getvalue().decode('utf-8')


def _metrics(work):
    return json.loads((work / 'artifacts' / '3').read_text(encoding='utf-8'))


def test_the_session_is_asked_for_its_json_result(tmp_path):
    work, scripts, params_path = _task(tmp_path, HEALTHY_FAKE)

    _run(params_path)

    argv = json.loads((scripts / 'cc-argv.json').read_text(encoding='utf-8'))
    assert argv[argv.index('--output-format') + 1] == 'json'


def test_a_declared_metrics_output_receives_one_cc_entry_with_the_sessions_counts(tmp_path):
    work, scripts, params_path = _task(tmp_path, HEALTHY_FAKE)

    rc, stdout = _run(params_path)

    assert rc == 0, stdout
    assert (work / 'artifacts' / '2').read_text(encoding='utf-8') == 'the answer'
    metrics = _metrics(work)
    assert len(metrics) == 1, metrics
    entry = metrics[0]
    assert entry['type'] == 'CC'
    assert isinstance(entry['executionMs'], int) and entry['executionMs'] >= 0
    assert {k: entry[k] for k in ('inputTokens', 'outputTokens', 'cacheCreationInputTokens', 'cacheReadInputTokens')} \
        == {'inputTokens': 2, 'outputTokens': 193, 'cacheCreationInputTokens': 18176, 'cacheReadInputTokens': 16560}


def test_the_sessions_final_text_reaches_the_console_as_text(tmp_path):
    # the dispatcher's analyzers read this Function's stdout; under --output-format json CC's words sit inside a JSON
    # string, so they are printed once more as plain text
    work, scripts, params_path = _task(tmp_path, HEALTHY_FAKE)

    rc, stdout = _run(params_path)

    assert '--- CC result ---\nStored the answer with mh_cc_store_result.' in stdout


def test_without_a_metrics_output_nothing_more_is_written(tmp_path):
    work, scripts, params_path = _task(tmp_path, HEALTHY_FAKE, extra_outputs='')

    rc, stdout = _run(params_path)

    assert rc == 0, stdout
    assert sorted(os.listdir(work / 'artifacts')) == ['2', 'mh-env.yaml']


def test_an_outage_reported_inside_the_json_result_still_exits_negative(tmp_path):
    work, scripts, params_path = _task(tmp_path, UNAVAILABLE_FAKE)

    rc, stdout = _run(params_path)

    assert rc == mh_call_cc.MCP_UNAVAILABLE_EXIT_CODE, stdout
    assert 'FAILED: Claude Code reported the MCP server unavailable - MCP_UNAVAILABLE: CONNECTION_CLOSED' in stdout
    assert not (work / 'artifacts' / '2').exists(), 'an outage must leave no output behind'


def test_a_console_without_a_result_line_records_the_call_with_null_counts(tmp_path):
    work, scripts, params_path = _task(tmp_path, TEXT_FAKE)

    rc, stdout = _run(params_path)

    assert rc == 0, stdout
    metrics = _metrics(work)
    assert [m['type'] for m in metrics] == ['CC']
    assert [metrics[0][k] for k in ('inputTokens', 'outputTokens', 'cacheCreationInputTokens',
                                    'cacheReadInputTokens')] == [None, None, None, None]


def test_two_metrics_outputs_fail_before_cc_is_started(tmp_path):
    second = METRICS_OUTPUT.replace('ccMetrics', 'otherMetrics').replace('id: 3', 'id: 4')
    work, scripts, params_path = _task(tmp_path, HEALTHY_FAKE, extra_outputs=METRICS_OUTPUT + second)

    try:
        rc, stdout = _run(params_path)
        failed = rc != 0
    except ValueError as e:
        failed = 'ccMetrics' in str(e) and 'otherMetrics' in str(e)

    assert failed
    assert not (scripts / 'cc-argv.json').exists(), 'CC must not be started for a SourceCode defect'


def test_the_api_path_records_its_one_request_with_the_responses_usage(tmp_path):
    api = EchoMessagesApi('sk-test')
    channel = ProcessorSecretChannel('cc-m', b'sk-test')
    metrics_var = {'id': '3', 'name': 'ccMetrics', 'type': 'mh.metrics'}
    params = {'workingPath': str(tmp_path), 'secretPort': channel.port, 'checkCode': 'cc-m',
              'outputs': [{'id': '9', 'name': 'ccResult'}, metrics_var]}
    try:
        code = mh_call_cc.run_claude_api(params, [{'timeout-sec': '30'}], str(tmp_path), 'p', params['outputs'][0],
                                         'claude-haiku-5-5', None, api_url=api.url, metrics_var=metrics_var)
    finally:
        api.close()

    assert code == 0
    metrics = json.loads((tmp_path / 'artifacts' / '3').read_text(encoding='utf-8'))
    assert len(metrics) == 1, metrics
    assert metrics[0]['type'] == 'API'
    assert isinstance(metrics[0]['executionMs'], int)
    # EchoMessagesApi answers usage {'input_tokens': 10, 'output_tokens': 5} and no cache counts
    assert [metrics[0][k] for k in ('inputTokens', 'outputTokens', 'cacheCreationInputTokens',
                                    'cacheReadInputTokens')] == [10, 5, None, None]
