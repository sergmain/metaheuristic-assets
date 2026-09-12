from mh_commons import *

(params, artifact_path) = start_execution()

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

write_result(params, artifact_path, 'result', result)

end_execution()


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


end_execution()