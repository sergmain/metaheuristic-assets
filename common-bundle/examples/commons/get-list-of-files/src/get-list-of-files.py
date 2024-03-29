import os
import gc
import sys
from datetime import datetime

import yaml


class Logger(object):
    def __init__(self, log_file):
        self.terminal = sys.stdout
        self.log = open(log_file, "w", encoding="utf-8")

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


cwd = os.getcwd()

artifact_path = os.path.join(cwd, 'artifacts')

# path to params.yaml will be absolute
yaml_file = sys.argv[len(sys.argv)-1]
with open(yaml_file, 'r', encoding="utf-8") as stream:
    params = (yaml.load(stream, Loader=yaml.FullLoader))['task']

env_file = os.path.join(artifact_path, 'mh-env.yaml')
with open(env_file, 'r', encoding="utf-8") as stream_envs:
    envs = (yaml.load(stream_envs, Loader=yaml.FullLoader))


var_list_of_files = get_variable_by_id(params['outputs'], 'var-list-of-files')
list_of_files_filename = os.path.join(artifact_path, str(var_list_of_files['id']))
if os.path.exists(list_of_files_filename):
    os.remove(list_of_files_filename)


var_logger_list_of_files = get_variable_by_id(params['outputs'], 'var-logger-list-of-files')
logger_filename = os.path.join(artifact_path, str(var_logger_list_of_files['id']))
if os.path.exists(logger_filename):
    os.remove(logger_filename)

sys.stdout = Logger(logger_filename)

print('Start time: ', str(datetime.now()))
print('Args: ', sys.argv)


# Getting the current work directory (cwd)
dir_code = params['inline']['list-files']['dir-code']
thisdir = get_disk_from_envs(envs, dir_code)

text_file = open(list_of_files_filename, "w", encoding="utf-8")

# r=root, d=directories, f = files
for r, d, f in os.walk(thisdir):
    for file in f:
        p = os.path.join(r, file)
        text_file.write(p)
        text_file.write('\n')

text_file.close()

gc.collect()

sys.exit(0)