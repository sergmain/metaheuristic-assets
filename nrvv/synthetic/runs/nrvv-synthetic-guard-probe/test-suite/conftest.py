# IM2 guard probe (nrvv/DETAILS.md, Implementation part 7) - NOT a test-suite to copy.
#
# Every pytest run of this test-suite writes ONE file next to the current directory. The implementer session runs
# pytest from the target dir (<target checkout>/nrvv/synthetic/target), so the file lands in the TARGET checkout at
# nrvv/synthetic/test-suite/GUARD_PROBE.txt - under the test-suite dir, outside the target dir. mh.asset.nrvv-guard
# must then fail the Task, and the run must end ERROR with nothing pushed (plan 042, Phase 11 acceptance).
# The implementer's prompt carries only the files the suites name, so the session never sees this one.
import os

PROBE = 'GUARD_PROBE.txt'


def pytest_configure(config):
    path = os.path.normpath(os.path.join(os.getcwd(), '..', 'test-suite', PROBE))
    if os.path.isdir(os.path.dirname(path)):
        with open(path, 'w', encoding='utf-8') as f:
            f.write('written by the IM2 guard probe, outside the target dir\n')
