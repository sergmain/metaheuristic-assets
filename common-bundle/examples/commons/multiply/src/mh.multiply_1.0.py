from mh_commons import *

(params, artifact_path) = start_execution()

left_var = get_var_as_int('inputValue')
right_var = get_var_as_int('index')

result = left_var * right_var

write_result(params, artifact_path, 'result', result)

end_execution()