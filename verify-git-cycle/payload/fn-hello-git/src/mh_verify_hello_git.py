# Verification Function for the git-delivery cycle, scenario #2.
#
# This file is NOT part of any bundle. It is reached only through the git block of
# verify-git-cycle/scenario-2/functions/fn-hello-git/mh-function.yaml, which pins this
# repo and this path. The Processor materializes the pinned commit and executes the
# script straight out of that materialized tree.
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

print('mh-verify.hello-git_1.2')
print('Start time: ', str(datetime.now()))
print('Args: ', sys.argv)
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

var_result = find_variable_by_name(params['outputs'], 'greeting')
result_filename = os.path.join(artifact_path, str(var_result['id']))
if os.path.exists(result_filename):
    os.remove(result_filename)

with open(result_filename, 'w', encoding='utf-8') as text_file:
    text_file.write('hello from a git-sourced Function, execContextId=' + str(params['execContextId']))

print('Result was written to ', result_filename)
print('End time: ', str(datetime.now()))
sys.exit(0)
