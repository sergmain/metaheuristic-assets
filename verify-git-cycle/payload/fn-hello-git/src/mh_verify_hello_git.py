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

cwd = os.getcwd()

print('mh-verify.hello-git_1.3')
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

print('recKey=' + recKey)
sys.exit(0)
