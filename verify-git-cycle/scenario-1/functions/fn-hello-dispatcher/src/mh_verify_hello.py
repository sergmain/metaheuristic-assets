# Verification Function for the git-delivery cycle, scenario #1.
#
# The bundle that carries this Function is DELIVERED from a git repo, but the Function
# itself is sourcing: dispatcher - its payload travels inside the bundle's zip, exactly
# as it always has. Scenario #1 exists to prove that git DELIVERY changed nothing for a
# dispatcher-sourced Function.
#
# No inputs. One output variable, written as artifacts/<output variable id>.

import json
import os
import sys

import yaml

cwd = os.getcwd()

print('mh-verify.hello-dispatcher_1.3')
print('Cwd: ', cwd)
print('Script: ', os.path.abspath(__file__))

# the LAST positional argument is always the absolute path to the params file
yaml_file = sys.argv[len(sys.argv) - 1]
with open(yaml_file, 'r', encoding='utf-8') as stream:
    params = (yaml.load(stream, Loader=yaml.FullLoader))['task']


def artifact(name):
    var = next(v for v in params['outputs'] if v['name'] == name)
    return os.path.join(cwd, 'artifacts', str(var['id']))


execContextId = str(params['execContextId'])
recKey = 'scenario-1-' + execContextId
body = 'hello, execContextId=' + execContextId

with open(artifact('response'), 'w', encoding='utf-8') as f:
    json.dump([{'type': 'mh-verify.git-cycle', 'recKey': recKey, 'body': body}], f)

with open(artifact('recKeys'), 'w', encoding='utf-8') as f:
    f.write(recKey + '\n')

print('recKey=' + recKey)
sys.exit(0)
