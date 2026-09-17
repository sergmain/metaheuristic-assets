# The internal MCP server for mh.asset.call-cc - the one channel a CC run has for returning its answer.
#
# Launched by CC, not by MH: mh_call_cc.py writes a .mcp.json naming this script and the absolute path
# of the file the answer goes into, and CC spawns it over stdio. stdout carries the MCP protocol and
# nothing else; every diagnostic goes to stderr and to mcp-server.log beside the result.
#
# ONE TOOL, and it stores ONCE.
#
#   mh_cc_store_result(result) -> the payload is written verbatim, exactly one time
#
# Content-agnostic on purpose: JSON, JSONL, YAML, prose - the server never looks inside. Whatever
# shape the answer should have was asked for in the prompt and is parsed by a later process, so
# there is nothing here to keep in step with a prompt this server never sees.
#
# WHY A TOOL RATHER THAN THE CONSOLE. An answer read off stdout is an answer that has been merged with
# stderr and tail-truncated by the launcher, and a truncated answer still looks like an answer. A tool
# call is the model stating that THIS is the result, delivered whole and out of band.
#
# WHY ONCE. A Task runs this Function in its own task dir exactly one time, so a second store is not
# a second answer - it is the same run contradicting itself, and silently overwriting would leave
# whichever call happened to be last. The second call is refused and says so, which puts the conflict
# in front of the model while it can still act on it.
#
# store_once is stdlib-only and is what call-cc/tests exercises; main() imports FastMCP and is the
# boundary, per MH-GIT-DELIVERY-FUNCTION-DESCRIPTION.md 5.5-5.6.

import json
import os
import sys
from datetime import datetime, timezone

SERVER_NAME = 'mh-call-cc'
MCP_LOG_FILE = 'mcp-server.log'


def log(message, log_file=None):
    """To stderr always, and to log_file when one was given.

    stderr is where CC keeps a spawned server's output, which makes it the right default. The file
    copy exists because the Function reports 'no result' long after the server has gone, and without
    it the only evidence of why would be inside CC's own debug stream.
    """
    line = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S') + ' ' + message
    sys.stderr.write(line + '\n')
    sys.stderr.flush()
    if log_file:
        try:
            # the directory is made here rather than assumed. The first lines this server writes are
            # the ones explaining a start that went wrong, and at that point nothing else has had a
            # reason to create anything - so a log that waited for someone else to go first would be
            # empty in precisely the case it exists for.
            parent = os.path.dirname(log_file)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except OSError as e:
            # a server that cannot write its log still has an answer to deliver
            sys.stderr.write('WARNING: could not write ' + str(log_file) + ': ' + str(e) + '\n')


def store_once(result_file, payload):
    """Write payload to result_file if and only if nothing is there yet.

    Existence of the file IS the record that a result was stored, which is what makes the guard
    survive a server restart within the same task dir. An in-memory flag would not: a second server
    process would start believing nothing had been written and would overwrite a delivered answer.

    Returns the dict the tool answers with - stored true/false, and on refusal the reason, so the
    model reads a sentence rather than inferring one from a missing field.
    """
    if os.path.exists(result_file):
        return {
            'stored': False,
            'message': 'ERROR: a result is already stored for this task. '
                       'This tool may be called only once, and the stored result is unchanged.',
        }

    # An empty store is worse than no store: the file exists, so the once-only guard is spent, and
    # the Function then reports 'no result' anyway because a zero-byte answer is not an answer. The
    # model would have been told 'stored: true' for a run that fails. Refusing leaves the single
    # store unspent and says why, so the call can be made again with the answer in it.
    if not payload.strip():
        return {
            'stored': False,
            'message': 'ERROR: the result is empty. Nothing was stored and this tool may still be '
                       'called once - call it again with your complete answer as the "result" argument.',
        }

    parent = os.path.dirname(result_file)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(result_file, 'w', encoding='utf-8') as f:
        f.write(payload)
    return {'stored': True, 'bytes': len(payload.encode('utf-8'))}


def main(argv):
    # imported here rather than at module scope: store_once above must stay importable by a test that
    # has no mcp package installed, because nothing in it needs one
    from mcp.server.fastmcp import FastMCP

    if len(argv) < 2:
        sys.stderr.write('FAILED: argv[1] must be the absolute path of the result file\n')
        return 1

    # absolute, and never derived from cwd: CC decides what the working directory of a server it
    # spawned is, and an answer written relative to a guess lands somewhere nobody reads
    result_file = os.path.abspath(argv[1])
    log_file = os.path.join(os.path.dirname(result_file), MCP_LOG_FILE)

    log('starting ' + SERVER_NAME + ', result file=' + result_file, log_file)

    mcp = FastMCP(SERVER_NAME)

    @mcp.tool()
    def mh_cc_store_result(result: str) -> str:
        """Return the final result of this task by storing it.

        Call this EXACTLY ONCE, with your complete answer as the "result" argument, verbatim and
        whole. This is the only way a result is returned: anything printed to the console is
        discarded. A second call is refused and leaves the first result unchanged.

        Args:
            result: The complete result payload to return, verbatim.
        """
        log('TOOL CALL: mh_cc_store_result(bytes=' + str(len(result.encode('utf-8'))) + ')', log_file)
        answer = store_once(result_file, result)
        answer_str = json.dumps(answer, indent=2, sort_keys=True)
        log('TOOL RESULT: mh_cc_store_result -> ' + answer_str, log_file)
        return answer_str

    log('ready, running stdio transport', log_file)
    try:
        mcp.run(transport='stdio')
    except Exception as e:
        log('server error: ' + str(e), log_file)
        return 1
    log('stopped', log_file)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
