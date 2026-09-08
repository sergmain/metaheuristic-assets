# Verification Function for the git-delivery cycle, scenario #2.
#
# This file is NOT part of any bundle. It is reached only through the git block of
# verify-git-cycle/scenario-2/functions/fn-hello-git/mh-function.yaml, which pins this
# repo and this path. The Processor materializes the pinned commit and executes the
# script straight out of that materialized tree.
#
# No inputs. One output variable, written as artifacts/<output variable id>.

import json
import os
import sys

import yaml

# ❗ THE REVISION MARKER — bump this literal before every scenario #2 run.
#
# It is opaque payload content. This script knows NOTHING about how it was delivered, which
# commit it came from, or that git is involved at all — a Task on the Processor is never told
# its own sourcing, and that is correct behaviour, not a limitation to work around. The marker
# is simply a value that changes when this file changes.
#
# That is precisely what makes it proof. Nothing else in the repo has to move for a new run to
# emit a new value: no Function code bump, no mh-function.yaml edit, no re-import, no new
# SourceCode uid. Push this file, create a new ExecContext, and if the new value comes out then
# the new commit ran.
PAYLOAD_MARKER = 'rev-2'

cwd = os.getcwd()

print('mh-verify.hello-git_1.2')
print('Cwd: ', cwd)
print('Script: ', os.path.abspath(__file__))

# the LAST positional argument is always the absolute path to the params file
yaml_file = sys.argv[len(sys.argv) - 1]
with open(yaml_file, 'r', encoding='utf-8') as stream:
    params = (yaml.load(stream, Loader=yaml.FullLoader))['task']

# the task's own asset dir holds a copy of commits/<sha>/<git.path>
asset_path = os.path.join(cwd, 'asset')
print('Asset dir exists: ', os.path.isdir(asset_path))
if os.path.isdir(asset_path):
    print('Asset dir content: ', sorted(os.listdir(asset_path)))


def artifact(name):
    var = next(v for v in params['outputs'] if v['name'] == name)
    return os.path.join(cwd, 'artifacts', str(var['id']))


execContextId = str(params['execContextId'])
recKey = 'scenario-2-' + execContextId
body = 'hello, execContextId=' + execContextId

with open(artifact('response'), 'w', encoding='utf-8') as f:
    json.dump([{'type': 'mh-verify.git-cycle', 'recKey': recKey, 'body': body}], f)

with open(artifact('recKeys'), 'w', encoding='utf-8') as f:
    f.write(recKey + '\n')

with open(artifact('payloadRev'), 'w', encoding='utf-8') as f:
    f.write(PAYLOAD_MARKER)

print('payloadRev=' + PAYLOAD_MARKER)
print('recKey=' + recKey)
sys.exit(0)
