# Task-params plumbing shared by the Functions of this payload.
#
# Every Variable a Function reads or writes is named by a process meta - variable-for-<role> - never
# hard-coded; the same lookup call-cc and rg-temp-project perform. task.metas is a LIST of maps and the first
# hit wins. Inputs sit at {workingPath}/{dataType}/{id}, outputs are written to {workingPath}/artifacts/{id}.

import os

NULL_VALUE = 'mh.null-value'
ARTIFACTS_DIR = 'artifacts'


def meta_value(metas, key):
    """The first value for key across the metas list, or None."""
    for meta in metas or []:
        if not isinstance(meta, dict):
            continue
        value = meta.get(key)
        if value is not None:
            return str(value)
    return None


def meta_keys(metas):
    """Every key declared across the metas list, sorted - for error messages, so a typo names itself."""
    return sorted({key for meta in metas or [] if isinstance(meta, dict) for key in meta})


def require_meta(metas, key):
    """A meta with no default: absent or blank is a defect in the SourceCode, never a runtime state."""
    value = meta_value(metas, key)
    if value is None or not value.strip():
        raise ValueError("meta '" + key + "' is required and was not declared. Declared metas: "
                         + str(meta_keys(metas)))
    return value.strip()


def variable_name(metas, role):
    """The actual Variable name bound to a role, via meta 'variable-for-<role>'."""
    return require_meta(metas, 'variable-for-' + role)


def find_variable(variables, name):
    """The declared variable with this name, or a failure that lists what WAS declared."""
    for var in variables or []:
        if isinstance(var, dict) and var.get('name') == name:
            return var
    declared = [v.get('name') for v in variables or [] if isinstance(v, dict)]
    raise ValueError("variable '" + name + "' is not declared in the task params. Declared: " + str(declared))


def input_path(working_path, var):
    return os.path.join(working_path, str(var.get('dataType') or 'variable'), str(var['id']))


def output_path(working_path, var):
    return os.path.join(working_path, ARTIFACTS_DIR, str(var['id']))


def read_text(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def write_text(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def read_role(task, role):
    """The text of the INPUT Variable bound to role."""
    metas = task.get('metas') or []
    return read_text(input_path(task['workingPath'], find_variable(task.get('inputs'), variable_name(metas, role))))


def output_role(task, role):
    """Where the OUTPUT Variable bound to role is to be written."""
    metas = task.get('metas') or []
    return output_path(task['workingPath'], find_variable(task.get('outputs'), variable_name(metas, role)))


def load_params(argv):
    """The params document; its path is always the LAST argument. PyYAML is imported here, not at module scope,
    so the modules of this payload stay importable by a test on a box without it."""
    import yaml
    with open(argv[len(argv) - 1], 'r', encoding='utf-8') as stream:
        return yaml.load(stream, Loader=yaml.FullLoader)
