import os
import gc
import sys
from datetime import datetime

import yaml


class Logger(object):
    def __init__(self, artifact_path):
        self.terminal = sys.stdout
        self.log = open(os.path.join(artifact_path, "logfile-factorial.log"), "w", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        # this flush method is needed for python 3 compatibility.
        # this handles the flush command by doing nothing.
        # you might want to specify some extra behavior here.
        pass


def get_variable_by_id(variables, code):
    for v in variables:
        if v['name']==code:
            return v

    raise Exception('Not found variable ' + code)


def get_variable_by_type(variables, type):
    for v in variables:
        if v['type']==type:
            return v

    raise Exception('A variable with type ' + type + " wasn't found" )


def get_disk_from_envs(envs, disk_code):
    for v in envs['disk']:
        if v['code']==disk_code:
            return v['path']

    raise Exception('A Disk mapping with code ' + disk_code + " wasn't found" )


def get_var_as_int(var_name):
    var_input = get_variable_by_id(params['inputs'], var_name)
    input_filename = os.path.join(var_input['dataType'], str(var_input['id']))

    with open(input_filename, 'r', encoding='utf-8') as file:
        data = file.read()

    return int(data)


cwd = os.getcwd()
artifact_path = os.path.join(cwd, 'artifacts')
sys.stdout = Logger(artifact_path)

print('Start time: ', str(datetime.now()))
print('Args: ', sys.argv)

# path to params.yaml will be absolute
yaml_file = sys.argv[len(sys.argv)-1]
with open(yaml_file, 'r', encoding="utf-8") as stream:
    params = (yaml.load(stream, Loader=yaml.FullLoader))['task']

cur_factorial = get_var_as_int('inputValue')
index = get_var_as_int('index')

f = cur_factorial * index

var_result = get_variable_by_id(params['outputs'], 'result')
result_filename = os.path.join(artifact_path, str(var_result['id']))
if os.path.exists(result_filename):
    os.remove(result_filename)

text_file = open(result_filename, "w", encoding="utf-8")
text_file.write(str(f))
text_file.close()

print('End time: ', str(datetime.now()))

gc.collect()
sys.exit(0)
