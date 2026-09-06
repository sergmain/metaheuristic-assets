# Verification Function for the git-delivery cycle, scenario #1.
#
# The bundle that carries this Function is DELIVERED from a git repo, but the Function
# itself is sourcing: dispatcher - its payload travels inside the bundle's zip, exactly
# as it always has. Scenario #1 exists to prove that git DELIVERY changed nothing for a
# dispatcher-sourced Function.
#
# No inputs. One output variable, written as artifacts/<output variable id>.

import os
import sys
from datetime import datetime

import yaml


def find_variable_by_name(variables, name):
    for v in variables:
        if v['name'] == name:
            return v
    raise Exception("Variable '" + name + "' wasn't found, available: " + str([v['name'] for v in variables]))


cwd = os.getcwd()
artifact_path = os.path.join(cwd, 'artifacts')

print('mh-verify.hello-dispatcher_1.2')
print('Start time: ', str(datetime.now()))
print('Args: ', sys.argv)
print('Cwd: ', cwd)

# the LAST positional argument is always the absolute path to the params file
yaml_file = sys.argv[len(sys.argv) - 1]
with open(yaml_file, 'r', encoding='utf-8') as stream:
    params = (yaml.load(stream, Loader=yaml.FullLoader))['task']

var_result = find_variable_by_name(params['outputs'], 'greeting')
result_filename = os.path.join(artifact_path, str(var_result['id']))
if os.path.exists(result_filename):
    os.remove(result_filename)

with open(result_filename, 'w', encoding='utf-8') as text_file:
    text_file.write('hello from a dispatcher-sourced Function delivered via git, execContextId='
                    + str(params['execContextId']))

print('Result was written to ', result_filename)
print('End time: ', str(datetime.now()))
sys.exit(0)
