#!/usr/bin/env python3
"""
run_test.py - run a Maven/surefire test and report a compact JSON result.

Why: an agent running `mvn test` in a terminal reads the whole console output into its context, and for a run longer
than the terminal tool's timeout it has to poll by hand. This script owns the Maven process, waits up to a bound, and
prints a few lines of JSON - the exit code and the failures with file:line - or a handle to wait on.

Usage:
  python run_test.py run   <pomDir> <test> [--max-seconds N] [--reports-dir DIR] [--mvn PATH] [--maven-arg ARG]...
                           [--utf8] [--pretty]
  python run_test.py sweep <pomDir> <listFile> [the same options as run]
  python run_test.py wait  <handle> [--max-seconds N] [--utf8] [--pretty]

<test> is the -Dtest value, e.g. ai.metaheuristic.ai.mcp.ExecContextWaitUtilsTest or pkg.Class#method.
<listFile> holds one -Dtest value per line (blank lines and # comments skipped); `sweep` runs them one Maven run after
another and reports the totals and only the runs that did not pass.

Output is one line of JSON (--pretty indents it): a passed run carries no handle, and empty lists and zero counts are
left out. A test that ended in an exception also carries `cause` (the deepest "Caused by:") and `origin` (the first
frame of the root cause outside the test class and outside JDK / framework code), when they say more than `at`.

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
# a sweep shows Maven's output for each run that failed without a report - fewer lines each, there may be several
MAX_SWEEP_LOG_LINES = 10

EXIT_PASSED = 0
EXIT_FAILED = 1
EXIT_RUNNING = 2
EXIT_OTHER = 3

RUN_FILE = 'run.json'
PID_FILE = 'supervisor.pid'
EXIT_FILE = 'exit.json'
LOG_FILE = 'maven.log'
ACTIVE_FILE = 'active'
# a sweep's supervisor records the runs it finished here, and the one it is in
PROGRESS_FILE = 'progress.json'
# `run` records the supervisor's pid right after starting it; a run still without one after this long never got going
PID_GRACE_SECONDS = 30

_ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
# Maven's closing advice after a failure - the same lines every time, and never the cause
_MAVEN_FOOTER = re.compile(r'^\[ERROR\]\s*(?:$|-> \[Help|To see the full stack trace|Re-run Maven|'
                           r'For more information about the errors|\[Help \d+\])')
# a stack frame: optional class loader / module prefixes (`app//`, `java.base/`), the class, the method, file:line
_FRAME = re.compile(r'^\s*at\s+(?:[\w.$@-]*/)*([\w$.]+)\.[\w$<>]+\(([\w$]+\.java):(\d+)\)', re.M)
_CAUSED_BY = re.compile(r'^\s*Caused by:\s*(.*)$', re.M)
# the JDK, the test framework and the libraries around the code under test: never the first place to look
FRAMEWORK_PREFIXES = ('java.', 'javax.', 'jakarta.', 'jdk.', 'sun.', 'com.sun.', 'org.junit.', 'org.opentest4j.',
                      'org.apiguardian.', 'org.springframework.', 'org.hibernate.', 'org.apache.', 'net.bytebuddy.',
                      'com.zaxxer.', 'org.postgresql.', 'org.h2.', 'com.fasterxml.', 'tools.jackson.', 'org.awaitility.')


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


def root_cause(trace):
    """(the deepest "Caused by:" text, its part of the trace) - or (None, the whole trace) when nothing is chained."""
    trace = trace or ''
    found = list(_CAUSED_BY.finditer(trace))
    if not found:
        return None, trace
    last = found[-1]
    return last.group(1).strip(), trace[last.start():]


def origin(classname, trace):
    """
    file:line of the first frame of the root cause outside the test class and outside FRAMEWORK_PREFIXES, or None.

    For an exception the test's own line says only where the test was when it happened; this is where it happened.
    """
    _, section = root_cause(trace)
    for m in _FRAME.finditer(section):
        cls = m.group(1)
        if cls == classname or cls.startswith(classname + '$') or cls.startswith(FRAMEWORK_PREFIXES):
            continue
        return f'{m.group(2)}:{m.group(3)}'
    return None


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
                entry = {
                    'test': f"{classname}#{case.get('name', '')}",
                    'kind': kind,
                    'type': el.get('type', ''),
                    'message': truncate(message),
                    'at': locate(classname, trace),
                }
                if kind == 'error':
                    # an assertion failure's line is the answer; an exception's cause and origin usually are
                    cause, _ = root_cause(trace)
                    if cause:
                        entry['cause'] = truncate(cause)
                    where = origin(classname, trace)
                    if where and where != entry['at']:
                        entry['origin'] = where
                failures.append(entry)
    return counts, failures


def fresh_reports(reports_dir, started_at):
    """The TEST-*.xml files written by this run: a report older than the run's start belongs to an earlier one."""
    if not reports_dir.is_dir():
        return []
    return sorted(p for p in reports_dir.glob('TEST-*.xml') if p.stat().st_mtime >= started_at)


def reports_between(reports_dir, started_at, finished_at):
    """The TEST-*.xml files written while one run of a sweep ran: its runs are sequential, so their windows don't meet."""
    if not reports_dir.is_dir():
        return []
    return sorted(p for p in reports_dir.glob('TEST-*.xml') if started_at <= p.stat().st_mtime <= finished_at)


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


def read_list(path):
    """The -Dtest values of a sweep: one per line; blank lines and # comments skipped."""
    tests = []
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            tests.append(line)
    return tests


def item_log(index):
    return f'maven-{index:03d}.log'


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


def maven_command(mvn, test, maven_args):
    return [mvn, '-q', 'test', f'-Dtest={test}', *maven_args]


def run_maven(command, cwd, log_path):
    """One Maven run, its output into log_path; its exit code (127 when it cannot start)."""
    env = dict(os.environ)
    # Maven's own JVM; the forked test JVM writes its results as XML, which carries its encoding
    env['MAVEN_OPTS'] = (env.get('MAVEN_OPTS', '') + ' -Dstdout.encoding=UTF-8 -Dstderr.encoding=UTF-8').strip()
    # the supervisor has no console, so a console program it starts would open a window of its own
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with open(log_path, 'wb') as log:
        try:
            proc = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
            return proc.wait()
        except OSError as e:
            log.write(f'[ERROR] run_test: cannot start Maven: {e}\n'.encode('utf-8'))
            return 127


def supervise(run_dir):
    """
    The detached half: runs Maven - once, or once per line of a sweep, in order - then records the exit code.
    exit.json is the only signal that the run ended; a sweep's progress.json says how far it got before that.
    """
    meta = read_json(run_dir / RUN_FILE)
    if 'items' not in meta:
        code = run_maven(meta['command'], meta['pomDir'], run_dir / LOG_FILE)
        write_json_atomic(run_dir / EXIT_FILE, {'exit': code, 'finishedAt': time.time()})
        return
    done = []
    for index, item in enumerate(meta['items']):
        started = time.time()
        write_json_atomic(run_dir / PROGRESS_FILE, {'done': done, 'current': item['test'], 'currentStartedAt': started})
        code = run_maven(item['command'], meta['pomDir'], run_dir / item_log(index))
        done.append({'test': item['test'], 'exit': code, 'startedAt': started, 'finishedAt': time.time()})
        write_json_atomic(run_dir / PROGRESS_FILE, {'done': done})
    write_json_atomic(run_dir / EXIT_FILE, {'exit': 0 if all(d['exit'] == 0 for d in done) else 1,
                                            'finishedAt': time.time()})


# ==================== results ====================

def sweep_progress(run_dir, meta):
    """How far a sweep got: runs finished of all, the one in progress, and the runs that failed so far."""
    progress_path = run_dir / PROGRESS_FILE
    progress = read_json(progress_path) if progress_path.is_file() else {'done': []}
    result = {'done': len(progress['done']), 'of': len(meta['items'])}
    if progress.get('current'):
        result['current'] = progress['current']
    failed = [d['test'] for d in progress['done'] if d['exit'] != 0]
    if failed:
        result['failedSoFar'] = failed
    return result


def last_item_log(run_dir):
    logs = sorted(run_dir.glob('maven-*.log'))
    return logs[-1] if logs else run_dir / LOG_FILE


def collect_sweep(run_dir, meta, ended):
    """A finished sweep: the totals, and one entry per run that did not pass - with its failures or Maven's output."""
    progress_path = run_dir / PROGRESS_FILE
    done = read_json(progress_path)['done'] if progress_path.is_file() else []
    reports_dir = Path(meta['reportsDir'])
    total = {'tests': 0, 'failed': 0, 'errors': 0, 'skipped': 0}
    items = []
    passed = 0
    for index, d in enumerate(done):
        item = {'test': d['test'], 'exit': d['exit'], 'seconds': round(d['finishedAt'] - d['startedAt'], 1)}
        reports = reports_between(reports_dir, d['startedAt'], d['finishedAt'])
        if reports:
            summary = summarize(reports)
            item.update(summary)
            for k in total:
                total[k] += summary[k]
        else:
            item['reports'] = 'none written by this run - see mavenOutput'
        if d['exit'] != 0 and not item.get('failures'):
            item['mavenOutput'] = log_errors(run_dir / item_log(index))[:MAX_SWEEP_LOG_LINES]
        if d['exit'] == 0 and not item.get('failures'):
            passed += 1
        else:
            items.append(item)
    return {'status': 'done', 'exit': ended['exit'], 'seconds': round(ended['finishedAt'] - meta['startedAt'], 1),
            'test': meta['test'], 'handle': str(run_dir), 'runs': len(meta['items']), 'passedRuns': passed,
            **total, 'items': items}


def collect(run_dir):
    meta = read_json(run_dir / RUN_FILE)
    exit_path = run_dir / EXIT_FILE
    sweep = 'items' in meta
    if not exit_path.is_file():
        pid_path = run_dir / PID_FILE
        pid = int(pid_path.read_text(encoding='utf-8').strip()) if pid_path.is_file() else None
        elapsed = time.time() - meta['startedAt']
        starting = pid is None and elapsed < PID_GRACE_SECONDS
        if starting or pid_alive(pid):
            running = {'status': 'running', 'handle': str(run_dir), 'elapsedSeconds': round(elapsed, 1)}
            if sweep:
                running.update(sweep_progress(run_dir, meta))
            return running
        # checked again: the supervisor may have written it and exited between the first check and the pid probe
        if not exit_path.is_file():
            lost = {'status': 'lost', 'handle': str(run_dir),
                    'mavenOutput': log_errors(last_item_log(run_dir) if sweep else run_dir / LOG_FILE)}
            if sweep:
                lost.update(sweep_progress(run_dir, meta))
            return lost
    ended = read_json(exit_path)
    if sweep:
        return collect_sweep(run_dir, meta, ended)
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
    passed = result['exit'] == 0 and not result.get('failures') and not result.get('items')
    return EXIT_PASSED if passed else EXIT_FAILED


def trim(result):
    """
    What the reader acts on, and nothing else: a passed run needs no handle; empty lists, a false failuresTruncated and
    zero failed / errors / skipped carry nothing. The runs of a sweep are trimmed the same way.
    """
    out = dict(result)
    if out.get('status') == 'done' and exit_code_of(out) == EXIT_PASSED:
        out.pop('handle', None)
    for key in ('failed', 'errors', 'skipped'):
        if out.get(key) == 0:
            out.pop(key)
    for key in ('failures', 'failuresTruncated', 'items'):
        if key in out and not out[key]:
            out.pop(key)
    if 'items' in out:
        out['items'] = [trim(item) for item in out['items']]
    return out


def emit(result, utf8, pretty=False):
    """
    One line of JSON, --pretty indents it. ASCII by default: \\u escapes survive any console code page, raw UTF-8
    doesn't. The exit code is decided on the result before trim.
    """
    if pretty:
        text = json.dumps(trim(result), indent=2, ensure_ascii=not utf8)
    else:
        text = json.dumps(trim(result), separators=(',', ':'), ensure_ascii=not utf8)
    if utf8:
        sys.stdout.reconfigure(encoding='utf-8')
    print(text)
    return exit_code_of(result)


# ==================== commands ====================

def launch(a, describe):
    """
    run and sweep: checks pomDir and Maven, refuses while another run is active there, records the run and starts its
    supervisor; then waits up to --max-seconds. describe(mvn) gives the run's test label and its command(s).
    """
    pom_dir = Path(a.pomDir).resolve()
    if not (pom_dir / 'pom.xml').is_file():
        return emit({'status': 'usage', 'message': f'no pom.xml in {pom_dir}'}, a.utf8, a.pretty)
    mvn = find_mvn(a.mvn)
    if mvn is None:
        return emit({'status': 'usage', 'message': 'mvn not found on PATH; pass --mvn'}, a.utf8, a.pretty)

    state_root = pom_dir / 'target' / 'run-test'
    state_root.mkdir(parents=True, exist_ok=True)
    active = state_root / ACTIVE_FILE
    if active.is_file():
        previous = Path(active.read_text(encoding='utf-8').strip())
        if previous.is_dir() and collect(previous)['status'] == 'running':
            # two Maven runs in one module race on target/
            return emit({'status': 'busy', 'handle': str(previous),
                         'message': 'a run is already active in this pomDir - wait on its handle'}, a.utf8, a.pretty)

    run_dir = state_root / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
    run_dir.mkdir()
    reports_dir = Path(a.reports_dir).resolve() if a.reports_dir else pom_dir / 'target' / 'surefire-reports'
    write_json_atomic(run_dir / RUN_FILE, {
        'pomDir': str(pom_dir),
        'reportsDir': str(reports_dir),
        'startedAt': time.time(),
        **describe(mvn),
    })
    pid = spawn_detached([sys.executable, str(Path(__file__).resolve()), '_supervise', str(run_dir)])
    (run_dir / PID_FILE).write_text(str(pid), encoding='utf-8')
    active.write_text(str(run_dir), encoding='utf-8')
    return emit(wait_for(run_dir, a.max_seconds), a.utf8, a.pretty)


def cmd_run(a):
    return launch(a, lambda mvn: {'test': a.test, 'command': maven_command(mvn, a.test, a.maven_arg)})


def cmd_sweep(a):
    try:
        tests = read_list(a.listFile)
    except OSError as e:
        return emit({'status': 'usage', 'message': f'cannot read {a.listFile}: {e}'}, a.utf8, a.pretty)
    if not tests:
        return emit({'status': 'usage', 'message': f'no test in {a.listFile}'}, a.utf8, a.pretty)
    return launch(a, lambda mvn: {
        'test': f'sweep {Path(a.listFile).name}',
        'items': [{'test': t, 'command': maven_command(mvn, t, a.maven_arg)} for t in tests],
    })


def cmd_wait(a):
    run_dir = Path(a.handle)
    if not (run_dir / RUN_FILE).is_file():
        return emit({'status': 'usage', 'message': f'not a run handle: {run_dir}'}, a.utf8, a.pretty)
    return emit(wait_for(run_dir, a.max_seconds), a.utf8, a.pretty)


def add_run_options(p):
    p.add_argument('--max-seconds', type=float, default=DEFAULT_MAX_SECONDS)
    p.add_argument('--reports-dir', help='default: <pomDir>/target/surefire-reports')
    p.add_argument('--mvn', help='Maven executable; default: mvn.cmd / mvn on PATH')
    p.add_argument('--maven-arg', action='append', default=[], help='extra Maven argument, repeatable')
    p.add_argument('--utf8', action='store_true', help='print raw UTF-8 instead of \\u escapes')
    p.add_argument('--pretty', action='store_true', help='indent the JSON instead of one line')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run a Maven/surefire test and report a compact JSON result.')
    sub = parser.add_subparsers(dest='command', required=True)

    run = sub.add_parser('run', help='start a test run and wait for it up to --max-seconds')
    run.add_argument('pomDir')
    run.add_argument('test', help='the -Dtest value, e.g. pkg.Class or pkg.Class#method')
    add_run_options(run)

    sweep = sub.add_parser('sweep', help='run each line of a list file as its own Maven run, one after another')
    sweep.add_argument('pomDir')
    sweep.add_argument('listFile', help='one -Dtest value per line; blank lines and # comments skipped')
    add_run_options(sweep)

    wait = sub.add_parser('wait', help='wait on a running test up to --max-seconds')
    wait.add_argument('handle')
    wait.add_argument('--max-seconds', type=float, default=DEFAULT_MAX_SECONDS)
    wait.add_argument('--utf8', action='store_true', help='print raw UTF-8 instead of \\u escapes')
    wait.add_argument('--pretty', action='store_true', help='indent the JSON instead of one line')

    supervise_cmd = sub.add_parser('_supervise', help=argparse.SUPPRESS)
    supervise_cmd.add_argument('runDir')

    a = parser.parse_args(argv)
    if a.command == '_supervise':
        supervise(Path(a.runDir))
        return 0
    if a.max_seconds < 0:
        parser.error('--max-seconds must be >= 0')
    return {'run': cmd_run, 'sweep': cmd_sweep, 'wait': cmd_wait}[a.command](a)


if __name__ == '__main__':
    sys.exit(main())
