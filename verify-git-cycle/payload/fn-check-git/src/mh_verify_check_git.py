# Verification Function #2 for the git-delivery cycle, scenario #2.
#
# This file is NOT part of any bundle. It is reached only through the git block of
# verify-git-cycle/scenario-2/functions/fn-check-git/mh-function.yaml.
#
# Consumes output#2 - the records mh.meta-storage selected back out of MH_META_STORAGE -
# and ASSERTS on them. A non-zero exit code marks the Task ERROR, and that is the only
# mechanism by which an empty or wrong round trip can fail the run: a select that matches
# nothing writes [] and succeeds on its own terms.
#
# One input, delivered to variable/<variable id> - NOT artifacts/.
# One output, written as artifacts/<output variable id>.

import json
import os
import sys

import yaml

cwd = os.getcwd()

print('mh-verify.check-git_1.3')
print('Cwd: ', cwd)
print('Script: ', os.path.abspath(__file__))

# the LAST positional argument is always the absolute path to the params file
yaml_file = sys.argv[len(sys.argv) - 1]
with open(yaml_file, 'r', encoding='utf-8') as stream:
    params = (yaml.load(stream, Loader=yaml.FullLoader))['task']

inp = next(v for v in params['inputs'] if v['name'] == 'output2')
with open(os.path.join(cwd, 'variable', str(inp['id'])), 'r', encoding='utf-8') as f:
    records = json.load(f)

expected = 'hello, execContextId=' + str(params['execContextId'])

if len(records) != 1:
    print('FAILED: expected exactly 1 record, got ' + str(len(records)))
    sys.exit(1)
if records[0]['body'] != expected:
    print('FAILED: body=[' + records[0]['body'] + '], expected=[' + expected + ']')
    sys.exit(1)

var = next(v for v in params['outputs'] if v['name'] == 'verdict')
with open(os.path.join(cwd, 'artifacts', str(var['id'])), 'w', encoding='utf-8') as f:
    f.write('OK recKey=' + records[0]['recKey'])
print('OK recKey=' + records[0]['recKey'])
sys.exit(0)
