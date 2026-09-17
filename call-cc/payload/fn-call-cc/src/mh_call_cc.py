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


def cc_command(claude_code_exec, mcp_config_name, server_name=MCP_SERVER_NAME, model=None):
    """The CC command line. The prompt is deliberately NOT in it.

    A prompt is tens of lines with newlines and quotes in it; passing it as an argv element does not
    work on any platform and fails differently on each. It goes in on stdin - see main().

    --allowedTools is derived from server_name so the two cannot drift: rename the server and the
    allow-list follows, instead of silently permitting nothing.
    """
    command = [
        claude_code_exec,
        '--debug',
        '--print',
        '--output-format', 'text',
        '--mcp-config', mcp_config_name,
        '--allowedTools', 'mcp__' + server_name + '__*',
    ]
    if model is not None and model.strip():
        command += ['--model', model.strip()]
    return command


def tail_lines(text, max_lines=MAX_OUTPUT_LINES):
    """The last max_lines lines, which is the half of a console worth keeping when it is too long."""
    if max_lines < 1:
        raise ValueError('max_lines must be greater than 0, got ' + str(max_lines))
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return '\n'.join(lines[-max_lines:])


# ---------------------------------------------------------------------------------------------------
# THE BOUNDARY

def read_text(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def write_text(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def main(argv):
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

    # the config is passed by FILE NAME, not by path: cwd is the task dir, and a bare name is the one
    # spelling that cannot be mangled by quoting on the way into CC
    command = cc_command(claude_code, MCP_CONFIG_FILE, MCP_SERVER_NAME, meta_value(metas, 'model'))
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

    if completed.returncode != 0:
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
