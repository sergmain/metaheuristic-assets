#!/usr/bin/env python3
"""
run_test.py - run a Maven/surefire test and report a compact JSON result.

Why: an agent running `mvn test` in a terminal reads the whole console output into its context, and for a run longer
than the terminal tool's timeout it has to poll by hand. This script owns the Maven process, waits up to a bound, and
prints a few lines of JSON - the exit code and the failures with file:line - or a handle to wait on.

Usage:
  python run_test.py run  <pomDir> <test> [--max-seconds N] [--reports-dir DIR] [--mvn PATH] [--maven-arg ARG]... [--utf8]
  python run_test.py wait <handle> [--max-seconds N] [--utf8]

<test> is the -Dtest value, e.g. ai.metaheuristic.ai.mcp.ExecContextWaitUtilsTest or pkg.Class#method.

Exit status: 0 done, tests passed - 1 done, tests or Maven failed - 2 still running, the output carries the handle -
3 lost (the supervisor died without a result), busy (another run is active in that pomDir) or bad usage.

How it works: `run` starts a detached supervisor process (this script, `_supervise`) that runs Maven and writes Maven's
exit code to exit.json; `run` and `wait` then poll for that file up to --max-seconds. Run state lives in
<pomDir>/target/run-test/<runId>/, and the handle is that directory's path.

Standard library only - nothing to install.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

DEFAULT_MAX_SECONDS = 50
POLL_SECONDS = 1.0
MAX_FAILURES = 10
MAX_MESSAGE_CHARS = 400
MAX_LOG_LINES = 30

EXIT_PASSED = 0
EXIT_FAILED = 1
EXIT_RUNNING = 2
EXIT_OTHER = 3

RUN_FILE = 'run.json'
PID_FILE = 'supervisor.pid'
EXIT_FILE = 'exit.json'
LOG_FILE = 'maven.log'
ACTIVE_FILE = 'active'
# `run` records the supervisor's pid right after starting it; a run still without one after this long never got going
PID_GRACE_SECONDS = 30

_ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
# Maven's closing advice after a failure - the same lines every time, and never the cause
_MAVEN_FOOTER = re.compile(r'^\[ERROR\]\s*(?:$|-> \[Help|To see the full stack trace|Re-run Maven|'
                           r'For more information about the errors|\[Help \d+\])')


# ==================== pure functions over files ====================

def write_json_atomic(path, data):
    """Readers never see a half-written file: the content lands under a temp name and is renamed into place."""
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(data, indent=2), encoding='utf-8')
    os.replace(tmp, path)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def truncate(text, limit=MAX_MESSAGE_CHARS):
    text = (text or '').strip()
    return text if len(text) <= limit else text[:limit] + '...'


def locate(classname, trace):
    """file:line of the first stack frame inside the test class - its methods, lambdas and nested classes - or None."""
    if not classname or not trace:
        return None
    pattern = r'at\s+' + re.escape(classname) + r'(?:\$[\w$]+)?\.[\w$<>]+\(([\w$]+\.java):(\d+)\)'
    m = re.search(pattern, trace)
    return f'{m.group(1)}:{m.group(2)}' if m else None


def parse_report(path):
    """One surefire TEST-*.xml: (counts, failures). A failure is a <failure> or an <error> of a <testcase>."""
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == 'testsuite' else root.findall('testsuite')
    counts = {'tests': 0, 'failed': 0, 'errors': 0, 'skipped': 0}
    failures = []
    for suite in suites:
        for case in suite.iter('testcase'):
            counts['tests'] += 1
            if case.find('skipped') is not None:
                counts['skipped'] += 1
            classname = case.get('classname', '')
            for kind, counter in (('failure', 'failed'), ('error', 'errors')):
                el = case.find(kind)
                if el is None:
                    continue
                counts[counter] += 1
                trace = el.text or ''
                message = el.get('message') or (trace.splitlines()[0] if trace else '')
                failures.append({
                    'test': f"{classname}#{case.get('name', '')}",
                    'kind': kind,
                    'type': el.get('type', ''),
                    'message': truncate(message),
                    'at': locate(classname, trace),
                })
    return counts, failures


def fresh_reports(reports_dir, started_at):
    """The TEST-*.xml files written by this run: a report older than the run's start belongs to an earlier one."""
    if not reports_dir.is_dir():
        return []
    return sorted(p for p in reports_dir.glob('TEST-*.xml') if p.stat().st_mtime >= started_at)


def summarize(report_paths):
    total = {'tests': 0, 'failed': 0, 'errors': 0, 'skipped': 0}
    failures = []
    for path in report_paths:
        counts, fs = parse_report(path)
        for k, v in counts.items():
            total[k] += v
        failures.extend(fs)
    return {**total, 'failures': failures[:MAX_FAILURES], 'failuresTruncated': len(failures) > MAX_FAILURES}


def log_errors(log_path):
    """
    The first [ERROR] lines of Maven's output, without its closing advice - or, when there are none, its last lines.

    The first ones: javac and Maven report the cause first, and what follows is often its cascade - one malformed
    file stops annotation processing and every Lombok-generated symbol of the module is reported missing after it.
    """
    if not log_path.is_file():
        return []
    lines = [_ANSI.sub('', line).rstrip() for line in log_path.read_text(encoding='utf-8', errors='replace').splitlines()]
    errors = [line for line in lines if line.startswith('[ERROR]') and not _MAVEN_FOOTER.match(line)]
    if errors:
        return errors[:MAX_LOG_LINES]
    return [line for line in lines if line.strip()][-MAX_LOG_LINES:]


# ==================== processes ====================

def pid_alive(pid):
    if not pid:
        return False
    if os.name == 'nt':
        # os.kill(pid, 0) is not a probe on Windows - it terminates the process. Ask the kernel instead.
        import ctypes
        from ctypes import wintypes
        process_query_limited_information = 0x1000
        still_active = 259
        error_access_denied = 5
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        k32.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = k32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return ctypes.get_last_error() == error_access_denied
        try:
            code = wintypes.DWORD()
            return bool(k32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == still_active
        finally:
            k32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def spawn_detached(args):
    """Starts a process that outlives this one and holds none of its console handles."""
    kwargs = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    if os.name != 'nt':
        return subprocess.Popen(args, start_new_session=True, **kwargs).pid
    base = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        # leave the caller's job object, so a terminal that kills its job on exit doesn't take the run with it
        return subprocess.Popen(args, creationflags=base | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kwargs).pid
    except OSError:
        # the job forbids breakaway
        return subprocess.Popen(args, creationflags=base, **kwargs).pid


def find_mvn(explicit):
    if explicit:
        return explicit
    for name in (('mvn.cmd', 'mvn') if os.name == 'nt' else ('mvn',)):
        found = shutil.which(name)
        if found:
            return found
    return None


def supervise(run_dir):
    """The detached half: runs Maven, then records its exit code. exit.json is the only signal that the run ended."""
    meta = read_json(run_dir / RUN_FILE)
    env = dict(os.environ)
    # Maven's own JVM; the forked test JVM writes its results as XML, which carries its encoding
    env['MAVEN_OPTS'] = (env.get('MAVEN_OPTS', '') + ' -Dstdout.encoding=UTF-8 -Dstderr.encoding=UTF-8').strip()
    # the supervisor has no console, so a console program it starts would open a window of its own
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with open(run_dir / LOG_FILE, 'wb') as log:
        try:
            proc = subprocess.Popen(meta['command'], cwd=meta['pomDir'], env=env, stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
            code = proc.wait()
        except OSError as e:
            log.write(f'[ERROR] run_test: cannot start Maven: {e}\n'.encode('utf-8'))
            code = 127
    write_json_atomic(run_dir / EXIT_FILE, {'exit': code, 'finishedAt': time.time()})


# ==================== results ====================

def collect(run_dir):
    meta = read_json(run_dir / RUN_FILE)
    exit_path = run_dir / EXIT_FILE
    if not exit_path.is_file():
        pid_path = run_dir / PID_FILE
        pid = int(pid_path.read_text(encoding='utf-8').strip()) if pid_path.is_file() else None
        elapsed = time.time() - meta['startedAt']
        starting = pid is None and elapsed < PID_GRACE_SECONDS
        if starting or pid_alive(pid):
            return {'status': 'running', 'handle': str(run_dir), 'elapsedSeconds': round(elapsed, 1)}
        # checked again: the supervisor may have written it and exited between the first check and the pid probe
        if not exit_path.is_file():
            return {'status': 'lost', 'handle': str(run_dir), 'mavenOutput': log_errors(run_dir / LOG_FILE)}
    ended = read_json(exit_path)
    # the handle stays useful after the end: maven.log is in that directory
    result = {'status': 'done', 'exit': ended['exit'], 'seconds': round(ended['finishedAt'] - meta['startedAt'], 1),
              'test': meta['test'], 'handle': str(run_dir)}
    reports = fresh_reports(Path(meta['reportsDir']), meta['startedAt'])
    if reports:
        result.update(summarize(reports))
    else:
        result['reports'] = 'none written by this run - see mavenOutput'
    if ended['exit'] != 0 and not result.get('failures'):
        result['mavenOutput'] = log_errors(run_dir / LOG_FILE)
    return result


def wait_for(run_dir, max_seconds, poll=POLL_SECONDS):
    deadline = time.monotonic() + max_seconds
    while True:
        result = collect(run_dir)
        remaining = deadline - time.monotonic()
        if result['status'] != 'running' or remaining <= 0:
            return result
        time.sleep(min(poll, remaining))


def exit_code_of(result):
    if result['status'] == 'running':
        return EXIT_RUNNING
    if result['status'] != 'done':
        return EXIT_OTHER
    return EXIT_PASSED if result['exit'] == 0 and not result.get('failures') else EXIT_FAILED


def emit(result, utf8):
    """ASCII by default: \\u escapes survive any console code page, raw UTF-8 doesn't."""
    text = json.dumps(result, indent=2, ensure_ascii=not utf8)
    if utf8:
        sys.stdout.reconfigure(encoding='utf-8')
    print(text)
    return exit_code_of(result)


# ==================== commands ====================

def cmd_run(a):
    pom_dir = Path(a.pomDir).resolve()
    if not (pom_dir / 'pom.xml').is_file():
        return emit({'status': 'usage', 'message': f'no pom.xml in {pom_dir}'}, a.utf8)
    mvn = find_mvn(a.mvn)
    if mvn is None:
        return emit({'status': 'usage', 'message': 'mvn not found on PATH; pass --mvn'}, a.utf8)

    state_root = pom_dir / 'target' / 'run-test'
    state_root.mkdir(parents=True, exist_ok=True)
    active = state_root / ACTIVE_FILE
    if active.is_file():
        previous = Path(active.read_text(encoding='utf-8').strip())
        if previous.is_dir() and collect(previous)['status'] == 'running':
            # two Maven runs in one module race on target/
            return emit({'status': 'busy', 'handle': str(previous),
                         'message': 'a run is already active in this pomDir - wait on its handle'}, a.utf8)

    run_dir = state_root / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
    run_dir.mkdir()
    reports_dir = Path(a.reports_dir).resolve() if a.reports_dir else pom_dir / 'target' / 'surefire-reports'
    write_json_atomic(run_dir / RUN_FILE, {
        'pomDir': str(pom_dir),
        'test': a.test,
        'reportsDir': str(reports_dir),
        'command': [mvn, '-q', 'test', f'-Dtest={a.test}', *a.maven_arg],
        'startedAt': time.time(),
    })
    pid = spawn_detached([sys.executable, str(Path(__file__).resolve()), '_supervise', str(run_dir)])
    (run_dir / PID_FILE).write_text(str(pid), encoding='utf-8')
    active.write_text(str(run_dir), encoding='utf-8')
    return emit(wait_for(run_dir, a.max_seconds), a.utf8)


def cmd_wait(a):
    run_dir = Path(a.handle)
    if not (run_dir / RUN_FILE).is_file():
        return emit({'status': 'usage', 'message': f'not a run handle: {run_dir}'}, a.utf8)
    return emit(wait_for(run_dir, a.max_seconds), a.utf8)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run a Maven/surefire test and report a compact JSON result.')
    sub = parser.add_subparsers(dest='command', required=True)

    run = sub.add_parser('run', help='start a test run and wait for it up to --max-seconds')
    run.add_argument('pomDir')
    run.add_argument('test', help='the -Dtest value, e.g. pkg.Class or pkg.Class#method')
    run.add_argument('--max-seconds', type=float, default=DEFAULT_MAX_SECONDS)
    run.add_argument('--reports-dir', help='default: <pomDir>/target/surefire-reports')
    run.add_argument('--mvn', help='Maven executable; default: mvn.cmd / mvn on PATH')
    run.add_argument('--maven-arg', action='append', default=[], help='extra Maven argument, repeatable')
    run.add_argument('--utf8', action='store_true', help='print raw UTF-8 instead of \\u escapes')

    wait = sub.add_parser('wait', help='wait on a running test up to --max-seconds')
    wait.add_argument('handle')
    wait.add_argument('--max-seconds', type=float, default=DEFAULT_MAX_SECONDS)
    wait.add_argument('--utf8', action='store_true', help='print raw UTF-8 instead of \\u escapes')

    supervise_cmd = sub.add_parser('_supervise', help=argparse.SUPPRESS)
    supervise_cmd.add_argument('runDir')

    a = parser.parse_args(argv)
    if a.command == '_supervise':
        supervise(Path(a.runDir))
        return 0
    if a.max_seconds < 0:
        parser.error('--max-seconds must be >= 0')
    return cmd_run(a) if a.command == 'run' else cmd_wait(a)


if __name__ == '__main__':
    sys.exit(main())
