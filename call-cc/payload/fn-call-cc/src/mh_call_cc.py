# mh.asset.call-cc - run the Claude Code CLI against a prompt handed in as a Variable, and return
# whatever the model stored through this Function's own MCP server.
#
# This file is NOT part of any bundle. It is reached only through the git block of
# call-cc/functions/fn-call-cc/mh-function.yaml.
#
# AGNOSTIC BY CONSTRUCTION. This Function knows how to start CC and how to collect one answer. It
# knows nothing about what the prompt asks for, and nothing about what the answer means:
#
#   prompt   an INPUT VARIABLE  - named by meta 'variable-for-prompt', passed to CC on stdin verbatim
#   output   an OUTPUT VARIABLE - named by meta 'variable-for-output', receives the answer byte for byte
#
# Nothing is parsed, validated, reformatted or interpreted on the way through. A capability that needs
# a particular prompt writes that prompt into the input Variable; a capability that needs the answer
# in a particular shape asks for it in that prompt and parses it in a LATER process. Put either of
# those here and this Function stops being reusable, which is the one property it exists to have.
#
# EVERY variable is named by a meta, never hard-coded. A process at any nesting level renames its
# variables freely - project-code-1, project-code-2 - and the Function is unaffected, because it is
# told which name to look for rather than guessing.
#
# The core below - meta_value / variable_name / find_variable / resolve_env / timeout_sec /
# mcp_config / cc_command / tail_lines - is pure, and it is what call-cc/tests exercises. main() is
# the boundary and is not unit-tested, per MH-GIT-DELIVERY-FUNCTION-DESCRIPTION.md 5.5-5.6.

import json
import os
import shutil
import subprocess
import sys

# Timeout for the CC process itself, in seconds. Overridable per process with meta 'timeout-sec',
# because how long an answer takes is a property of the prompt, which this Function does not own.
DEFAULT_TIMEOUT_SEC = 300

# Env code resolved from artifacts/mh-env.yaml to find the CC executable. The Processor writes that
# file before launching; a box without the entry cannot run this Function at all.
CLAUDE_CODE_ENV_CODE = 'claude-code'

# The name the MCP server is registered under in .mcp.json. It also fixes the tool-id prefix CC
# builds, which is why --allowedTools below is derived from this constant rather than written twice.
#
# No hyphen, no dot: CC composes tool ids as mcp__<server>__<tool>, and whether it preserves a
# separator inside <server> is not something this repo can establish. A name that cannot raise the
# question is cheaper than an answer that would have to be verified on every CC release.
MCP_SERVER_NAME = 'mhcc'

# The MCP server ships in this same payload directory, so it is always the sibling of this file -
# see MH-GIT-DELIVERY-FUNCTION-DESCRIPTION.md 4.4: the Processor copies <git.path> into
# {task.home}/asset, whole, at launch time.
MCP_SERVER_SCRIPT = 'mh_cc_mcp_server.py'

MCP_CONFIG_FILE = '.mcp.json'
PROMPT_FILE = 'cc-prompt.txt'
CONSOLE_LOG_FILE = 'cc-console.log'

# Where the MCP server puts the answer, and where this Function looks for it. Under the task dir, so
# two Tasks never see each other's result.
CC_DATA_DIR = 'cc-data'
CC_RESULT_FILE = 'cc-result.out'
MCP_LOG_FILE = 'mcp-server.log'

ARTIFACTS_DIR = 'artifacts'
MH_ENV_FILE = 'mh-env.yaml'

# The tool CC must call to return its answer. Named here only so the failure message can say what was
# not called; this Function never speaks MCP itself.
STORE_RESULT_TOOL = 'mh_cc_store_result'

# Matches what MH's own launcher keeps of a console. The dispatcher's analyzers read this Function's
# stdout, so the tail is what a usage-limit or quota rule gets to match against.
MAX_OUTPUT_LINES = 2000

# The settings file for the CC session, passed by FILE NAME with --settings - the same way .mcp.json is passed
# with --mcp-config. It turns ultracode OFF, explicitly. Ultracode is a Claude Code setting (xhigh effort plus
# automatic dynamic-workflow orchestration), and a user-level "ultracode": true on the Processor box would
# otherwise start every run with it. --settings outranks every settings.json scope except managed settings.
#
# NOT in .mcp.json: --mcp-config reads MCP servers only, and a settings key placed there is never consulted.
SETTINGS_FILE = 'cc-settings.json'

# The one --effort value that switches ultracode back on for a session, whatever the settings say. Refused.
ULTRACODE_EFFORT = 'ultracode'

# The Function's own instruction for when its MCP server is gone - appended to CC's SYSTEM prompt from this
# file, so the prompt Variable still goes in on stdin verbatim. See MCP_UNAVAILABLE_RULE.
SYSTEM_PROMPT_FILE = 'cc-system-prompt.txt'

# The start of the one line the model emits, per MCP_UNAVAILABLE_RULE, when the MCP server is not usable. The
# model cannot set CC's exit code - a -p run gives it no tool that ends the process with a code of its choosing -
# so the line is its request, and main() turns it into MCP_UNAVAILABLE_EXIT_CODE.
MCP_UNAVAILABLE_MARKER = 'MCP_UNAVAILABLE:'

# The placeholder of the rule's own template line. That line is the instruction, never a report, so
# mcp_unavailable_line() skips it: a console that echoes the system prompt must not fail a healthy run.
MCP_UNAVAILABLE_PLACEHOLDER = '<the error you saw>'

# Exit code of the Function when CC reported the MCP server unavailable. Negative on purpose: every other
# failure returns 1. Literal only where exit codes are 32-bit (Windows); POSIX keeps 8 bits, so there it reads
# as 255.
MCP_UNAVAILABLE_EXIT_CODE = -1

# What CC must do when this Function's result channel is gone. The Function owns this much and no more: it is
# the contract of its own MCP server, not a word about the task - which is why it rides on the system prompt.
# Keep the template line the only line here that starts with MCP_UNAVAILABLE_MARKER.
MCP_UNAVAILABLE_RULE = '''MCP AVAILABILITY - READ THIS FIRST:
Your answer can be returned only by calling the {tool} tool of the "{server}" MCP server. If that
server is not connected, or a call to it fails with a connection error (CONNECTION_CLOSED, failed to
reconnect, server unavailable, or any transport-level failure), STOP IMMEDIATELY.
- Do NOT wait for it to come back, and do NOT poll or retry it.
- Do NOT ask to be told when it reconnects. Nobody is reading your output interactively.
- Do NOT do the work anyway and hold the answer: unsent work is lost work.
- Do NOT print the answer instead of storing it. The console is not a fallback.
Emit exactly one line, then end your turn:
{marker} {placeholder}
That line is how this run exits IMMEDIATELY with a NEGATIVE exit code, as it must. You cannot set
the exit code yourself, so do not try - no shell command, no other tool: the Function that launched
you reads the line and exits negative. Without the line the run is reported as an ordinary failure
instead.
'''.format(tool=STORE_RESULT_TOOL, server=MCP_SERVER_NAME, marker=MCP_UNAVAILABLE_MARKER,
           placeholder=MCP_UNAVAILABLE_PLACEHOLDER)


# ---------------------------------------------------------------------------------------------------
# METAS - the indirection that makes one Function serve every process that calls it.
#
# task.metas is a LIST of maps, and a single map may carry several keys. First hit wins, scanning the
# list in order. That is the lookup MH itself performs, and reproducing it here rather than assuming
# 'one key per entry' is what keeps a hand-written .mhsc and a generated one behaving the same.

def meta_value(metas, key):
    """The first value for key across the metas list, or None."""
    for meta in metas or []:
        if not isinstance(meta, dict):
            continue
        value = meta.get(key)
        if value is not None:
            # a value coming out of YAML may already be a bool or an int - 'timeout-sec: 600'
            return str(value)
    return None


def meta_keys(metas):
    """Every key declared across the metas list, sorted. For error messages, so a typo names itself."""
    return sorted({key for meta in metas or [] if isinstance(meta, dict) for key in meta})


def require_meta(metas, key):
    """A meta that has no default: absent or blank is a defect in the SourceCode, not a runtime state.

    Failing here rather than falling back to a guessed name is deliberate. A fallback turns a missing
    declaration into a variable-not-found further down, or - worse - into a run against the wrong
    variable that happens to exist and happens to parse.
    """
    value = meta_value(metas, key)
    if value is None or not value.strip():
        raise ValueError("meta '" + key + "' is required and was not declared. Declared metas: "
                         + str(meta_keys(metas)))
    return value.strip()


def variable_name(metas, logical_name):
    """The actual Variable name bound to a logical role, via meta 'variable-for-<logical_name>'."""
    return require_meta(metas, 'variable-for-' + logical_name)


def optional_cli_value(metas, logical_name, read_variable):
    """The value for an optional CLI flag (--model, --effort), or None to omit it.

    The flag is driven by an OPTIONAL input Variable, named by meta 'variable-for-<logical_name>', not by a
    literal meta: the model and effort a run uses are a property of the RUN, so they arrive as ExecContext-level
    inputs, the same way `synthetic` does, and stay out of the SourceCode. All four "no value" states collapse to
    omission, so the CLI's own default applies and the run still works:

      - the meta is absent            -> the process did not wire this flag at all
      - the named Variable is absent  -> wired but not bound (an optional input never seeded and not materialised)
      - the value is blank
      - the Variable is nullified     -> MH marks it 'empty' and downloads no file; the reader returns None

    read_variable(name) -> the Variable's text, or None if it is not bound. Passed in rather than reached for, so
    the resolution is testable without a task dir (production hands it the real reader; a test hands it a dict).
    ❗ Omission is deliberate here and NOT the require_meta path: a missing optional flag is a runtime state, not a
    SourceCode defect. The DAHF guide (0.5) is what obliges an authored workflow to declare model and effort; the
    Function stays permissive so an ad-hoc call runs with CC's defaults.
    """
    var_name = meta_value(metas, 'variable-for-' + logical_name)
    if var_name is None or not var_name.strip():
        return None
    value = read_variable(var_name.strip())
    if value is None or not value.strip():
        return None
    return value.strip()


# ---------------------------------------------------------------------------------------------------
# VARIABLES

def find_variable(variables, name):
    """The declared variable with this name, or a failure that lists what WAS declared."""
    for var in variables or []:
        if isinstance(var, dict) and var.get('name') == name:
            return var
    declared = [v.get('name') for v in variables or [] if isinstance(v, dict)]
    raise ValueError("variable '" + name + "' is not declared in the task params. Declared: " + str(declared))


def input_path(working_path, var):
    """Where the Processor put an input variable: {workingPath}/{dataType}/{id}."""
    return os.path.join(working_path, str(var.get('dataType') or 'variable'), str(var['id']))


def output_path(working_path, var):
    """Where an output variable is expected: always {workingPath}/artifacts/{id}, whatever its dataType."""
    return os.path.join(working_path, ARTIFACTS_DIR, str(var['id']))


# ---------------------------------------------------------------------------------------------------
# ENVIRONMENT

def resolve_env(envs, code):
    """The executable an env code names, accepting either shape mh-env.yaml is written in.

    The Processor writes the short layout - envs as a mapping of code -> exec - which MH reads as its
    oldest env version and upgrades. From a later version on, the same field is a list of
    {code, exec}. Both are read here so this Function never has to know which version wrote the file
    it was handed.
    """
    if isinstance(envs, dict):
        found = envs.get(code)
        available = sorted(envs)
    elif isinstance(envs, list):
        found = next((e.get('exec') for e in envs
                      if isinstance(e, dict) and e.get('code') == code), None)
        available = sorted(str(e.get('code')) for e in envs if isinstance(e, dict))
    else:
        raise ValueError('envs in ' + MH_ENV_FILE + ' is neither a mapping nor a list, got '
                         + type(envs).__name__)

    if found is None or not str(found).strip():
        raise ValueError("env code '" + code + "' not found in " + MH_ENV_FILE
                         + '. Available: ' + str(available))
    return str(found).strip()


def timeout_sec(metas, default=DEFAULT_TIMEOUT_SEC):
    """Seconds to wait for CC, from meta 'timeout-sec'. Absent means the default."""
    value = meta_value(metas, 'timeout-sec')
    if value is None or not value.strip():
        return default
    seconds = int(value.strip())
    if seconds < 1:
        raise ValueError('timeout-sec must be greater than 0, got ' + str(seconds))
    return seconds


# ---------------------------------------------------------------------------------------------------
# THE CC INVOCATION

def mcp_config(python_exec, server_script, result_file, server_name=MCP_SERVER_NAME):
    """The .mcp.json text telling CC to spawn this payload's MCP server over stdio.

    The result file is passed as an ARGUMENT rather than agreed as a constant on both sides. The
    Function owns where the answer lands and the server is told; there is one source of truth, and a
    server started by hand for debugging states on its own command line where it will write.

    json.dumps does the escaping. Building this text by concatenation is how a Windows path loses its
    backslashes, and a .mcp.json that parses into the wrong command fails as 'CC produced no result'
    several minutes later rather than as a broken config.
    """
    return json.dumps({
        'mcpServers': {
            server_name: {
                'type': 'stdio',
                'command': python_exec,
                'args': [server_script, result_file],
            }
        }
    }, indent=2)


def cc_command(claude_code_exec, mcp_config_name, server_name=MCP_SERVER_NAME, model=None, effort=None,
               settings_name=SETTINGS_FILE, system_prompt_name=SYSTEM_PROMPT_FILE):
    """The CC command line. The prompt is deliberately NOT in it.

    A prompt is tens of lines with newlines and quotes in it; passing it as an argv element does not
    work on any platform and fails differently on each. It goes in on stdin - see main().

    --allowedTools is derived from server_name so the two cannot drift: rename the server and the
    allow-list follows, instead of silently permitting nothing.

    model and effort are each appended only when the process asked for one. An absent meta leaves the
    flag off and the CLI's own default applies - which the DAHF guide (0.5) forbids for an authored
    workflow, so both are declared there; the Function stays permissive so an ad-hoc call still runs.

    --settings and --append-system-prompt-file name files by bare name, like --mcp-config: the settings switch
    ultracode OFF (SETTINGS_FILE), the system prompt carries MCP_UNAVAILABLE_RULE. An effort of 'ultracode' is
    refused, not passed on: --effort ultracode turns ultracode on for the session whatever the settings say.
    """
    command = [
        claude_code_exec,
        '--debug',
        '--print',
        '--output-format', 'text',
        '--mcp-config', mcp_config_name,
        '--settings', settings_name,
        '--append-system-prompt-file', system_prompt_name,
        '--allowedTools', 'mcp__' + server_name + '__*',
    ]
    if model is not None and model.strip():
        command += ['--model', model.strip()]
    if effort is not None and effort.strip():
        if effort.strip().lower() == ULTRACODE_EFFORT:
            raise ValueError("effort '" + effort.strip() + "' is refused: ultracode is explicitly off for this "
                             + 'Function, and --effort ultracode would switch it back on for the session')
        command += ['--effort', effort.strip()]
    return command


def tail_lines(text, max_lines=MAX_OUTPUT_LINES):
    """The last max_lines lines, which is the half of a console worth keeping when it is too long."""
    if max_lines < 1:
        raise ValueError('max_lines must be greater than 0, got ' + str(max_lines))
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return '\n'.join(lines[-max_lines:])


def cc_settings():
    """The --settings JSON for the CC session: ultracode explicitly off, and nothing else.

    json.dumps writes it for the same reason it writes .mcp.json: text built by hand is how a config ends up
    parsed as something other than what was meant.
    """
    return json.dumps({'ultracode': False}, indent=2)


def mcp_unavailable_line(console):
    """The model's MCP_UNAVAILABLE report in the CC console, stripped, or None when there is none.

    A report is a whole line starting with MCP_UNAVAILABLE_MARKER, as the rule demands - the marker mid-line is
    not one. The rule's own template line is skipped by its placeholder, so a console that echoes the system
    prompt never fails a healthy run.
    """
    for line in (console or '').splitlines():
        line = line.strip()
        if (line.startswith(MCP_UNAVAILABLE_MARKER)
                and line[len(MCP_UNAVAILABLE_MARKER):].strip() != MCP_UNAVAILABLE_PLACEHOLDER):
            return line
    return None


# ---------------------------------------------------------------------------------------------------
# THE CONSOLE

def utf8_console(stream):
    """stream, re-encoded as UTF-8 so that writing to it can no longer fail - or left alone when it cannot be.

    On a Windows Processor this Function's stdout is a pipe, and Python encodes a stdout that is not a
    console with the ANSI code page - cp1252 - and strict errors. CC's --debug console is not cp1252: the
    first character outside it (U+2192 RIGHTWARDS ARROW, observed) raised UnicodeEncodeError out of the
    print of that console. That print runs on EVERY call and before the result is collected, so a run whose
    answer was already stored in cc-result.out failed its Task. UTF-8 encodes every character, and
    backslashreplace covers the one thing it cannot - a lone surrogate. main() hands stdout and stderr to
    this before anything is printed.
    """
    reconfigure = getattr(stream, 'reconfigure', None)
    if reconfigure is not None:
        reconfigure(encoding='utf-8', errors='backslashreplace')
    return stream


# ---------------------------------------------------------------------------------------------------
# THE BOUNDARY

def read_text(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def cc_version(claude_code_exec):
    """`claude --version`, one line, or a short note why it could not be read.

    Printed only when the CC call has ALREADY failed, so it costs a subprocess only on the failure path. Its job
    is diagnosis: the flags this Function passes are version-gated - `--effort` exists from a certain CLI on - so a
    host whose `claude` is too old rejects the argument and the call fails with nothing in the console naming the
    CLI as the cause. The version turns that into a one-glance answer. Never raises: a diagnostic must not become a
    second failure on top of the one it explains.
    """
    try:
        completed = subprocess.run([claude_code_exec, '--version'],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
        return completed.stdout.decode('utf-8', errors='replace').strip() or '(no output)'
    except (OSError, subprocess.SubprocessError) as e:
        return '(could not read: ' + str(e) + ')'


def write_text(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def main(argv):
    # FIRST, before anything is printed: on a Processor stdout and stderr are pipes - see utf8_console
    utf8_console(sys.stdout)
    utf8_console(sys.stderr)

    # imported here rather than at module scope: the core above must stay importable by a test that
    # has no PyYAML installed, because nothing in the core needs it
    import yaml

    print('mh.asset.call-cc')
    print('Cwd: ', os.getcwd())
    print('Script: ', os.path.abspath(__file__))

    # the LAST positional argument is always the absolute path to the params file
    yaml_file = argv[len(argv) - 1]
    with open(yaml_file, 'r', encoding='utf-8') as stream:
        params = (yaml.load(stream, Loader=yaml.FullLoader))['task']

    metas = params.get('metas') or []
    work_dir = params['workingPath']
    print('workingPath: ' + work_dir)
    print('metas: ' + str(metas))

    prompt_var = find_variable(params.get('inputs'), variable_name(metas, 'prompt'))
    prompt = read_text(input_path(work_dir, prompt_var))
    if not prompt.strip():
        print('FAILED: the prompt variable is empty. There is nothing to ask.')
        return 1
    print('prompt: ' + str(len(prompt)) + ' chars')

    # resolved BEFORE CC is launched. A missing output declaration is a SourceCode defect, and
    # finding it after a paid model call costs the call as well as the run.
    output_var = find_variable(params.get('outputs'), variable_name(metas, 'output'))

    # model and effort are OPTIONAL ExecContext-level inputs (see optional_cli_value). The reader returns the
    # text of an input variable by name, or None when it is not bound - so an optional input that was never
    # seeded omits its flag rather than failing the Task. Also None when it is NULLIFIED: MH marks such an input
    # 'empty' and downloads no file for it.
    def read_input_variable(name):
        for var in params.get('inputs') or []:
            if isinstance(var, dict) and var.get('name') == name:
                if var.get('empty'):
                    return None
                return read_text(input_path(work_dir, var))
        return None

    model = optional_cli_value(metas, 'model', read_input_variable)
    effort = optional_cli_value(metas, 'effort', read_input_variable)
    print('model: ' + (model or '(CC default)') + ', effort: ' + (effort or '(CC default)'))

    env_params = yaml.load(read_text(os.path.join(work_dir, ARTIFACTS_DIR, MH_ENV_FILE)),
                           Loader=yaml.FullLoader)
    claude_code = resolve_env(env_params.get('envs'), CLAUDE_CODE_ENV_CODE)
    print('claude-code: ' + claude_code)

    # sys.executable, not the python-3 env entry: it is by construction the interpreter the Processor
    # resolved to run THIS script, so the MCP server is guaranteed to start in the same environment
    # that already proved it can import what this payload needs.
    python_exec = sys.executable

    server_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), MCP_SERVER_SCRIPT)
    if not os.path.isfile(server_script):
        print('FAILED: MCP server script not found beside this Function at ' + server_script)
        return 1

    data_dir = os.path.join(work_dir, CC_DATA_DIR)
    os.makedirs(data_dir, exist_ok=True)
    result_file = os.path.join(data_dir, CC_RESULT_FILE)

    prompt_file = os.path.join(work_dir, PROMPT_FILE)
    write_text(prompt_file, prompt)

    config_file = os.path.join(work_dir, MCP_CONFIG_FILE)
    write_text(config_file, mcp_config(python_exec, server_script, result_file))
    print('.mcp.json:\n' + read_text(config_file))

    # ultracode explicitly off for this session - see SETTINGS_FILE
    settings_file = os.path.join(work_dir, SETTINGS_FILE)
    write_text(settings_file, cc_settings())
    print(SETTINGS_FILE + ':\n' + read_text(settings_file))

    # the Function's own rule for when its MCP server is gone, on CC's SYSTEM prompt - the prompt Variable still
    # goes in on stdin verbatim
    system_prompt_file = os.path.join(work_dir, SYSTEM_PROMPT_FILE)
    write_text(system_prompt_file, MCP_UNAVAILABLE_RULE)
    print(SYSTEM_PROMPT_FILE + ': ' + str(len(MCP_UNAVAILABLE_RULE)) + ' chars')

    # the config is passed by FILE NAME, not by path: cwd is the task dir, and a bare name is the one
    # spelling that cannot be mangled by quoting on the way into CC
    command = cc_command(claude_code, MCP_CONFIG_FILE, MCP_SERVER_NAME, model, effort)
    seconds = timeout_sec(metas)
    print('command: ' + str(command))
    print('timeout: ' + str(seconds) + 's')

    try:
        with open(prompt_file, 'r', encoding='utf-8') as stdin_file:
            completed = subprocess.run(
                command, cwd=work_dir, stdin=stdin_file,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=seconds)
    except subprocess.TimeoutExpired:
        print('FAILED: Claude Code did not finish within ' + str(seconds) + 's')
        return 1

    console = completed.stdout.decode('utf-8', errors='replace') if completed.stdout else ''
    write_text(os.path.join(data_dir, CONSOLE_LOG_FILE), console)
    # printed so the dispatcher's analyzers see the CLI's own words - a usage limit or a rejected
    # credential is stated by CC, and this stdout is the only place a rule can read it
    print('--- CC console ---\n' + tail_lines(console))
    print('exit code: ' + str(completed.returncode))

    mcp_log = os.path.join(data_dir, MCP_LOG_FILE)
    if os.path.isfile(mcp_log):
        print('--- MCP server log ---\n' + read_text(mcp_log))
    else:
        print('WARNING: no MCP server log at ' + mcp_log + ' - the server may never have started')

    # the MCP server was unavailable. The model cannot set CC's exit code, so MCP_UNAVAILABLE_RULE has it emit one
    # line and end its turn, and this is where that line becomes the NEGATIVE exit code. Checked first: a run that
    # reported the server gone produced nothing usable, whatever CC's own exit code was.
    unavailable = mcp_unavailable_line(console)
    if unavailable is not None:
        print('FAILED: Claude Code reported the MCP server unavailable - ' + unavailable)
        return MCP_UNAVAILABLE_EXIT_CODE

    if completed.returncode != 0:
        # the flags this Function passes are version-gated (--effort in particular); on a failure, name the CLI so
        # a too-old build is not mistaken for a bad prompt or a spent session
        print('claude --version: ' + cc_version(claude_code))
        print('FAILED: Claude Code exited with code ' + str(completed.returncode))
        return 1

    if not os.path.isfile(result_file) or os.path.getsize(result_file) == 0:
        # The console is NOT a fallback, deliberately. It is Processor-owned diagnostics - stderr is
        # merged into it and the tail is truncated - so an answer recovered from it is an answer that
        # may already have been cut in half, silently. A run that produced nothing through the tool
        # produced nothing.
        print('FAILED: no result at ' + result_file + '. The answer must be returned by calling the '
              + STORE_RESULT_TOOL + ' MCP tool, never by printing it to the console.')
        return 1

    os.makedirs(os.path.join(work_dir, ARTIFACTS_DIR), exist_ok=True)
    target = output_path(work_dir, output_var)
    shutil.copyfile(result_file, target)
    print('stored ' + str(os.path.getsize(target)) + ' bytes into output variable "'
          + str(output_var.get('name')) + '" at ' + target)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
