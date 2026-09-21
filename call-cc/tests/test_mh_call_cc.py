# Synthetic unit tests for mh.asset.call-cc, per MH-GIT-DELIVERY-FUNCTION-DESCRIPTION.md section 5.
#
# Every fixture is built by the test. Nothing here reads a params file, a task dir, an mh-env.yaml
# off a Processor, a dispatcher or a real CC install - which is why every expected value below could
# be written down in advance. No CC process is started and no MCP session is opened: the boundary is
# integration territory (section 5.6) and the core is what these own.
#
# Run:  pytest call-cc/tests

import io
import json

import pytest

import mh_call_cc
from mh_call_cc import (meta_value, meta_keys, require_meta, variable_name, find_variable,
                        input_path, output_path, resolve_env, timeout_sec, mcp_config, cc_command,
                        tail_lines, optional_cli_value, DEFAULT_TIMEOUT_SEC,
                        cc_settings, mcp_unavailable_line, SETTINGS_FILE, SYSTEM_PROMPT_FILE,
                        MCP_UNAVAILABLE_RULE, MCP_UNAVAILABLE_MARKER, MCP_UNAVAILABLE_PLACEHOLDER)
from mh_cc_mcp_server import store_once, log


# ----------------------------------------------------------------- metas, and why the list is scanned

def test_meta_value_scans_the_whole_list():
    metas = [{'model': 'opus'}, {'variable-for-prompt': 'ccPrompt'}]

    assert meta_value(metas, 'variable-for-prompt') == 'ccPrompt'


def test_meta_value_reads_a_key_out_of_a_multi_key_entry():
    # MH permits several keys in one entry, so a lookup that only ever reads entry[0] would miss them
    metas = [{'model': 'opus', 'timeout-sec': '600'}]

    assert meta_value(metas, 'timeout-sec') == '600'


def test_meta_value_takes_the_first_hit_when_a_key_is_declared_twice():
    metas = [{'model': 'first'}, {'model': 'second'}]

    assert meta_value(metas, 'model') == 'first'


def test_meta_value_is_none_when_the_key_is_not_declared():
    assert meta_value([{'model': 'opus'}], 'variable-for-output') is None


def test_meta_value_survives_an_absent_or_empty_metas_list():
    assert meta_value(None, 'model') is None
    assert meta_value([], 'model') is None


def test_meta_value_stringifies_what_yaml_produced():
    # 'timeout-sec: 600' unquoted parses as an int, and every caller here expects text
    assert meta_value([{'timeout-sec': 600}], 'timeout-sec') == '600'


def test_meta_keys_lists_every_declared_key_sorted():
    assert meta_keys([{'b': '1', 'a': '2'}, {'c': '3'}]) == ['a', 'b', 'c']


def test_require_meta_strips_the_value():
    assert require_meta([{'model': '  opus  '}], 'model') == 'opus'


def test_require_meta_rejects_an_absent_meta_and_names_what_was_declared():
    try:
        require_meta([{'model': 'opus'}], 'variable-for-prompt')
        assert False, 'an absent required meta must not be tolerated'
    except ValueError as e:
        assert 'variable-for-prompt' in str(e)
        assert 'model' in str(e), 'the message must show what WAS declared, or a typo hides'


def test_require_meta_rejects_a_blank_meta():
    try:
        require_meta([{'variable-for-prompt': '   '}], 'variable-for-prompt')
        assert False, 'a blank required meta names no variable and must not be tolerated'
    except ValueError:
        pass


def test_variable_name_reads_the_variable_for_key():
    metas = [{'variable-for-prompt': 'ccPrompt-1'}]

    assert variable_name(metas, 'prompt') == 'ccPrompt-1'


def test_variable_name_has_no_fallback_to_the_logical_name():
    # falling back would run against whatever variable happened to be called 'prompt', which is a
    # wrong answer rather than an error
    try:
        variable_name([{'model': 'opus'}], 'prompt')
        assert False, 'an undeclared variable binding must fail, not guess'
    except ValueError:
        pass


# ----------------------------------------------------------------- variables and where they live

def test_find_variable_returns_the_matching_declaration():
    variables = [{'name': 'a', 'id': '1'}, {'name': 'b', 'id': '2'}]

    assert find_variable(variables, 'b')['id'] == '2'


def test_find_variable_names_what_was_declared():
    try:
        find_variable([{'name': 'a', 'id': '1'}], 'missing')
        assert False, 'an undeclared variable must be reported'
    except ValueError as e:
        assert 'missing' in str(e)
        assert 'a' in str(e)


def test_find_variable_on_nothing_at_all_is_still_an_error():
    for variables in [None, []]:
        try:
            find_variable(variables, 'a')
            assert False, 'no declarations cannot satisfy a lookup'
        except ValueError:
            pass


def test_input_path_uses_the_declared_data_type():
    path = input_path('/work', {'id': '100001', 'dataType': 'variable'})

    assert path.replace('\\', '/') == '/work/variable/100001'


def test_input_path_falls_back_to_variable_when_no_data_type_was_declared():
    path = input_path('/work', {'id': '100001'})

    assert path.replace('\\', '/') == '/work/variable/100001'


def test_output_path_is_artifacts_whatever_the_data_type_says():
    path = output_path('/work', {'id': '200001', 'dataType': 'variable'})

    assert path.replace('\\', '/') == '/work/artifacts/200001'


# ----------------------------------------------------------------- mh-env.yaml, in both shapes

def test_resolve_env_reads_the_mapping_shape_the_processor_writes():
    envs = {'python-3': 'C:\\anaconda3\\python.exe', 'claude-code': 'claude'}

    assert resolve_env(envs, 'claude-code') == 'claude'


def test_resolve_env_reads_the_list_shape():
    envs = [{'code': 'python-3', 'exec': '/usr/bin/python3'}, {'code': 'claude-code', 'exec': '/usr/bin/claude'}]

    assert resolve_env(envs, 'claude-code') == '/usr/bin/claude'


def test_resolve_env_missing_code_lists_what_is_available():
    try:
        resolve_env({'python-3': 'python'}, 'claude-code')
        assert False, 'a missing env must be reported, not returned as None'
    except ValueError as e:
        assert 'claude-code' in str(e)
        assert 'python-3' in str(e)


def test_resolve_env_rejects_a_blank_exec():
    try:
        resolve_env({'claude-code': '   '}, 'claude-code')
        assert False, 'a blank exec is not an executable'
    except ValueError:
        pass


def test_resolve_env_rejects_a_shape_it_does_not_understand():
    try:
        resolve_env('claude-code: claude', 'claude-code')
        assert False, 'a string is neither of the two shapes and must not be searched'
    except ValueError:
        pass


# ----------------------------------------------------------------- the CC timeout

def test_timeout_is_the_default_when_no_meta_declares_one():
    assert timeout_sec([{'model': 'opus'}]) == DEFAULT_TIMEOUT_SEC


def test_timeout_is_the_default_when_the_meta_is_blank():
    assert timeout_sec([{'timeout-sec': '  '}]) == DEFAULT_TIMEOUT_SEC


def test_timeout_comes_from_the_meta_when_declared():
    assert timeout_sec([{'timeout-sec': '600'}]) == 600


def test_timeout_rejects_zero_and_negative():
    for value in ['0', '-1']:
        try:
            timeout_sec([{'timeout-sec': value}])
            assert False, value + ' is not a length of time to wait'
        except ValueError:
            pass


# ----------------------------------------------------------------- .mcp.json

def test_mcp_config_round_trips_as_json():
    parsed = json.loads(mcp_config('/usr/bin/python3', '/asset/src/mh_cc_mcp_server.py', '/work/cc-data/cc-result.out'))

    assert list(parsed['mcpServers']) == ['mhcc']
    assert parsed['mcpServers']['mhcc']['type'] == 'stdio'
    assert parsed['mcpServers']['mhcc']['command'] == '/usr/bin/python3'


def test_mcp_config_passes_the_script_then_the_result_file():
    parsed = json.loads(mcp_config('python', '/asset/src/mh_cc_mcp_server.py', '/work/cc-data/cc-result.out'))

    assert parsed['mcpServers']['mhcc']['args'] == ['/asset/src/mh_cc_mcp_server.py', '/work/cc-data/cc-result.out']


def test_mcp_config_keeps_a_windows_path_intact_through_json():
    # the assertion this file exists for: a hand-built JSON string loses backslashes, and the failure
    # shows up minutes later as 'no result' rather than as a broken config
    command = 'C:\\anaconda3\\envs\\python_3-13\\python.exe'
    result = 'C:\\task\\work\\cc-data\\cc-result.out'

    parsed = json.loads(mcp_config(command, 'C:\\asset\\src\\mh_cc_mcp_server.py', result))

    assert parsed['mcpServers']['mhcc']['command'] == command
    assert parsed['mcpServers']['mhcc']['args'][1] == result


def test_mcp_config_registers_under_the_name_it_was_given():
    parsed = json.loads(mcp_config('python', '/s.py', '/r.out', 'other'))

    assert list(parsed['mcpServers']) == ['other']


# ----------------------------------------------------------------- the CC command line

def test_cc_command_allow_list_is_derived_from_the_server_name():
    # the two cannot drift: rename the server and the allow-list follows it
    command = cc_command('claude', '.mcp.json', 'other')

    assert 'mcp__other__*' in command


def test_cc_command_passes_the_config_by_bare_name():
    command = cc_command('claude', '.mcp.json')

    assert command[command.index('--mcp-config') + 1] == '.mcp.json'


def test_cc_command_starts_with_the_executable():
    assert cc_command('/usr/bin/claude', '.mcp.json')[0] == '/usr/bin/claude'


def test_cc_command_omits_the_model_when_none_was_asked_for():
    for model in [None, '', '   ']:
        assert '--model' not in cc_command('claude', '.mcp.json', 'mhcc', model), repr(model)


def test_cc_command_appends_the_model_when_one_was_asked_for():
    command = cc_command('claude', '.mcp.json', 'mhcc', '  opus  ')

    assert command[command.index('--model') + 1] == 'opus'


def test_cc_command_omits_the_effort_when_none_was_asked_for():
    for effort in [None, '', '   ']:
        assert '--effort' not in cc_command('claude', '.mcp.json', 'mhcc', 'opus', effort), repr(effort)


def test_cc_command_appends_the_effort_when_one_was_asked_for():
    command = cc_command('claude', '.mcp.json', 'mhcc', 'opus', '  medium  ')

    assert command[command.index('--effort') + 1] == 'medium'


def test_cc_command_carries_both_the_model_and_the_effort():
    command = cc_command('claude', '.mcp.json', 'mhcc', 'opus', 'medium')

    assert command[command.index('--model') + 1] == 'opus'
    assert command[command.index('--effort') + 1] == 'medium'


def test_cc_command_never_carries_the_prompt():
    # a prompt is tens of lines; it goes in on stdin, and an argv element would fail differently on
    # every platform
    command = cc_command('claude', '.mcp.json')

    for part in command:
        assert '\n' not in part, 'no element of a command line may contain a newline'


def test_cc_command_passes_the_settings_by_bare_name():
    command = cc_command('claude', '.mcp.json')

    assert command[command.index('--settings') + 1] == SETTINGS_FILE


def test_cc_command_appends_the_system_prompt_from_a_file_by_bare_name():
    command = cc_command('claude', '.mcp.json')

    assert command[command.index('--append-system-prompt-file') + 1] == SYSTEM_PROMPT_FILE


def test_cc_command_refuses_the_ultracode_effort():
    # --effort ultracode switches ultracode on for the session whatever the settings say, so passing it on
    # would undo the explicit disable
    for effort in ['ultracode', '  ultracode  ', 'Ultracode']:
        try:
            cc_command('claude', '.mcp.json', 'mhcc', 'opus', effort)
            assert False, repr(effort) + ' would switch ultracode back on and must be refused'
        except ValueError as e:
            assert 'ultracode' in str(e)


def test_cc_command_still_passes_every_real_effort_level():
    for effort in ['low', 'medium', 'high', 'xhigh', 'max']:
        command = cc_command('claude', '.mcp.json', 'mhcc', 'opus', effort)

        assert command[command.index('--effort') + 1] == effort


# ----------------------------------------------------------------- ultracode off

def test_cc_settings_turns_ultracode_off_and_nothing_else():
    # parsed, not string-compared: the file must be JSON that CC reads as ultracode=false
    assert json.loads(cc_settings()) == {'ultracode': False}


# ----------------------------------------------------------------- the MCP_UNAVAILABLE report

# A console of a healthy run: --debug lines and the model's final text, no report.
HEALTHY_CONSOLE = ('[DEBUG] MCP server "mhcc": Connection established\n'
                   '[DEBUG] Calling MCP tool: mh_cc_store_result\n'
                   'Stored.\n')


def test_mcp_unavailable_line_finds_the_models_report():
    console = HEALTHY_CONSOLE + 'MCP_UNAVAILABLE: CONNECTION_CLOSED\n[DEBUG] Cleaning up MCP servers\n'

    assert mcp_unavailable_line(console) == 'MCP_UNAVAILABLE: CONNECTION_CLOSED'


def test_mcp_unavailable_line_strips_an_indented_report_with_windows_line_ends():
    console = '[DEBUG] start\r\n   MCP_UNAVAILABLE: failed to reconnect   \r\n'

    assert mcp_unavailable_line(console) == 'MCP_UNAVAILABLE: failed to reconnect'


def test_mcp_unavailable_line_is_none_for_a_healthy_console():
    assert mcp_unavailable_line(HEALTHY_CONSOLE) is None


def test_mcp_unavailable_line_is_none_when_there_is_no_console():
    for console in [None, '', ' \n \n']:
        assert mcp_unavailable_line(console) is None, repr(console)


def test_mcp_unavailable_line_skips_the_template_line():
    # the rule's instruction line, as a console that echoed the system prompt would carry it
    assert mcp_unavailable_line(HEALTHY_CONSOLE + 'MCP_UNAVAILABLE: <the error you saw>\n') is None


def test_mcp_unavailable_line_ignores_the_marker_inside_a_line():
    # a report is a whole line; the marker quoted inside a debug line is not the model reporting anything
    assert mcp_unavailable_line('[DEBUG] system prompt: MCP_UNAVAILABLE: CONNECTION_CLOSED\n') is None


def test_mcp_unavailable_line_never_fires_on_the_rule_itself():
    # both halves are needed: without the first, the second would pass on a rule that lost its template line
    template = MCP_UNAVAILABLE_MARKER + ' ' + MCP_UNAVAILABLE_PLACEHOLDER
    assert template in [line.strip() for line in MCP_UNAVAILABLE_RULE.splitlines()], \
        'the rule must still carry its template line: ' + template

    assert mcp_unavailable_line(MCP_UNAVAILABLE_RULE) is None, \
        'a console that echoes the system prompt must never be read as the model reporting the server gone'


def test_mcp_unavailable_rule_names_this_functions_own_server_and_tool():
    assert '"mhcc" MCP server' in MCP_UNAVAILABLE_RULE
    assert 'mh_cc_store_result' in MCP_UNAVAILABLE_RULE


# ----------------------------------------------------------------- model / effort as optional inputs
#
# optional_cli_value reads the OPTIONAL input variable named by 'variable-for-<flag>' and reduces every "no
# value" state to None (omit the flag). The variable reader is a function parameter, so each test hands in a
# plain dict lookup - the real value production computed, never a programmed double.

def reader(store):
    """A variable reader over a fixed dict: a name maps to its text, or to None when it is not bound."""
    return lambda name: store.get(name)


def var_for(flag, name):
    return [{'variable-for-' + flag: name}]


def test_optional_cli_value_is_the_variables_text_when_it_is_set():
    value = optional_cli_value(var_for('model', 'modelVar'), 'model', reader({'modelVar': '  claude-opus-4-8 '}))

    assert value == 'claude-opus-4-8'


def test_optional_cli_value_is_none_when_the_meta_is_absent():
    # the process did not wire the flag at all
    assert optional_cli_value([{'variable-for-prompt': 'p'}], 'model', reader({'modelVar': 'opus'})) is None


def test_optional_cli_value_is_none_when_the_variable_is_nullified():
    # a nullified input has no file; the production reader returns None for it
    metas = var_for('effort', 'effortVar')

    assert optional_cli_value(metas, 'effort', reader({'effortVar': None})) is None


def test_optional_cli_value_is_none_when_the_variable_is_blank():
    assert optional_cli_value(var_for('model', 'm'), 'model', reader({'m': '   \n'})) is None


def test_optional_cli_value_is_none_when_the_named_variable_is_not_bound():
    # meta present but the optional input was never materialised - permissive, not a failure
    assert optional_cli_value(var_for('model', 'missingVar'), 'model', reader({})) is None


def test_optional_cli_value_feeds_cc_command_so_a_set_input_becomes_a_flag_and_null_omits_it():
    metas = [{'variable-for-model': 'm'}, {'variable-for-effort': 'e'}]
    store = {'m': 'opus', 'e': None}

    model = optional_cli_value(metas, 'model', reader(store))
    effort = optional_cli_value(metas, 'effort', reader(store))
    command = cc_command('claude', '.mcp.json', 'mhcc', model, effort)

    assert command[command.index('--model') + 1] == 'opus'
    assert '--effort' not in command, 'a null effort input must leave the flag off'


# ----------------------------------------------------------------- console truncation

def test_tail_lines_leaves_a_short_console_alone():
    assert tail_lines('a\nb\nc', 10) == 'a\nb\nc'


def test_tail_lines_keeps_the_end_because_that_is_where_the_failure_is():
    text = '\n'.join(str(i) for i in range(100))

    assert tail_lines(text, 3) == '97\n98\n99'


def test_tail_lines_rejects_a_limit_below_one():
    try:
        tail_lines('a\nb', 0)
        assert False, 'keeping zero lines is not a truncation, it is a deletion'
    except ValueError:
        pass


# ----------------------------------------------------------------- the console, on a Windows Processor

# One line of a real CC --debug console, carrying the character that failed a Task: U+2192 is not in cp1252.
CONSOLE = '[DEBUG] MCP server "mhcc": Connection established \u2192 1 tool'


def processor_stdout():
    """(buffer, stdout) - a stdout configured the way a Windows Processor's pipe is: Python encodes a stdout that
    is not a console with the ANSI code page, cp1252, and strict errors. A real stream, not a stand-in: what is
    written lands in a buffer the test reads. newline='\\n' only so the expected bytes do not depend on the OS."""
    buffer = io.BytesIO()
    return buffer, io.TextIOWrapper(buffer, encoding='cp1252', errors='strict', newline='\n')


def test_the_cc_console_is_printed_whole_to_a_processor_stdout():
    buffer, stdout = processor_stdout()
    # main() hands its stdout to utf8_console first. Written as a characterization test before utf8_console
    # existed: the fallback is exactly what main() did then - nothing
    getattr(mh_call_cc, 'utf8_console', lambda stream: stream)(stdout)

    print('--- CC console ---\n' + tail_lines(CONSOLE), file=stdout)
    stdout.flush()

    assert buffer.getvalue() == ('--- CC console ---\n' + CONSOLE + '\n').encode('utf-8')


def test_utf8_console_never_fails_on_the_one_thing_utf8_cannot_encode():
    buffer, stdout = processor_stdout()
    mh_call_cc.utf8_console(stdout)

    print('lone \ud800 surrogate', file=stdout)
    stdout.flush()

    assert buffer.getvalue() == b'lone \\ud800 surrogate\n'


def test_utf8_console_leaves_a_stream_it_cannot_reconfigure_alone():
    stream = io.StringIO()

    assert mh_call_cc.utf8_console(stream) is stream
    print(CONSOLE, file=stream)
    assert stream.getvalue() == CONSOLE + '\n'


# ----------------------------------------------------------------- store once, and only once

def test_store_once_writes_the_payload_verbatim(tmp_path):
    target = str(tmp_path / 'cc-data' / 'cc-result.out')

    answer = store_once(target, '{"finding": "x"}\n{"finding": "y"}')

    assert answer['stored'] is True
    assert (tmp_path / 'cc-data' / 'cc-result.out').read_text(encoding='utf-8') == '{"finding": "x"}\n{"finding": "y"}'


def test_store_once_creates_the_directory_it_needs(tmp_path):
    target = str(tmp_path / 'not' / 'there' / 'yet' / 'cc-result.out')

    assert store_once(target, 'answer')['stored'] is True


def test_store_once_reports_the_utf8_byte_count_not_the_character_count(tmp_path):
    target = str(tmp_path / 'cc-result.out')

    # two characters, four bytes - the number is about what was written, not about what was typed
    assert store_once(target, 'да')['bytes'] == 4


def test_store_once_refuses_the_second_call(tmp_path):
    target = str(tmp_path / 'cc-result.out')
    store_once(target, 'first')

    answer = store_once(target, 'second')

    assert answer['stored'] is False
    assert 'already stored' in answer['message']


def test_store_once_leaves_the_first_result_untouched_by_a_second_call(tmp_path):
    target = str(tmp_path / 'cc-result.out')
    store_once(target, 'first')

    store_once(target, 'second')

    assert (tmp_path / 'cc-result.out').read_text(encoding='utf-8') == 'first', \
        'a refused call that still overwrote would be worse than one that accepted'


def test_store_once_refuses_an_empty_payload_without_spending_the_single_store(tmp_path):
    target = str(tmp_path / 'cc-result.out')

    answer = store_once(target, '')

    assert answer['stored'] is False
    assert not (tmp_path / 'cc-result.out').exists(), 'an empty store must leave nothing behind'
    assert store_once(target, 'the real answer')['stored'] is True, 'the store must still be available'


def test_store_once_treats_whitespace_as_empty(tmp_path):
    target = str(tmp_path / 'cc-result.out')

    assert store_once(target, '  \n\t ')['stored'] is False
    assert not (tmp_path / 'cc-result.out').exists()


# ----------------------------------------------------------------- the log, in the window it is for

def test_log_writes_before_anything_else_has_made_the_directory(tmp_path):
    # the log's whole job is explaining a run that produced no result, and the loudest version of
    # that is a server that died before it ever stored anything - i.e. before any other code had a
    # reason to create the directory. A log that needs someone else to go first is silent exactly
    # when it is needed.
    log_file = str(tmp_path / 'cc-data' / 'mcp-server.log')

    log('starting', log_file)

    assert (tmp_path / 'cc-data' / 'mcp-server.log').read_text(encoding='utf-8').endswith('starting\n')


def test_log_appends_rather_than_replacing(tmp_path):
    log_file = str(tmp_path / 'mcp-server.log')

    log('first', log_file)
    log('second', log_file)

    written = (tmp_path / 'mcp-server.log').read_text(encoding='utf-8')
    assert 'first' in written and 'second' in written


def test_log_without_a_file_is_stderr_only_and_does_not_fail():
    log('no file given')
