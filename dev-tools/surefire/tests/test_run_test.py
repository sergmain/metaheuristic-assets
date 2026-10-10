import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import run_test

SCRIPT = Path(run_test.__file__).resolve()

FAILING_REPORT = textwrap.dedent('''\
    <?xml version="1.0" encoding="UTF-8"?>
    <testsuite name="com.acme.FooTest" tests="4" failures="1" errors="1" skipped="1" time="0.5">
      <testcase name="test_ok" classname="com.acme.FooTest" time="0.01"/>
      <testcase name="test_bad" classname="com.acme.FooTest" time="0.02">
        <failure message="expected: &lt;1&gt; but was: &lt;2&gt;" type="org.opentest4j.AssertionFailedError">org.opentest4j.AssertionFailedError: expected: &lt;1&gt; but was: &lt;2&gt;
    	at org.junit.jupiter.api.AssertionUtils.fail(AssertionUtils.java:42)
    	at com.acme.FooTest.test_bad(FooTest.java:57)
    </failure>
      </testcase>
      <testcase name="test_boom" classname="com.acme.FooTest" time="0.01">
        <error message="boom" type="java.lang.IllegalStateException">java.lang.IllegalStateException: boom
    	at com.acme.Prod.run(Prod.java:10)
    	at com.acme.FooTest.lambda$test_boom$0(FooTest.java:63)
    </error>
      </testcase>
      <testcase name="test_skipped" classname="com.acme.FooTest" time="0">
        <skipped/>
      </testcase>
    </testsuite>
    ''')

PASSING_REPORT = textwrap.dedent('''\
    <?xml version="1.0" encoding="UTF-8"?>
    <testsuite name="com.acme.FooTest" tests="1" failures="0" errors="0" skipped="0" time="0.1">
      <testcase name="test_ok" classname="com.acme.FooTest" time="0.01"/>
    </testsuite>
    ''')

FAKE_MVN = textwrap.dedent('''\
    import os, sys, time
    test = next(a[len('-Dtest='):] for a in sys.argv[1:] if a.startswith('-Dtest='))
    time.sleep(float(os.environ.get('FAKE_MVN_SLEEP', '0')))
    passing = (os.environ.get('FAKE_MVN_OUTCOME') == 'pass'
               or test in os.environ.get('FAKE_MVN_PASS_TESTS', '').split(';'))
    os.makedirs(os.path.join('target', 'surefire-reports'), exist_ok=True)
    with open(os.path.join('target', 'surefire-reports', 'TEST-' + test + '.xml'), 'w', encoding='utf-8') as f:
        f.write(os.environ['FAKE_MVN_PASSING' if passing else 'FAKE_MVN_FAILING'])
    sys.exit(0 if passing else 1)
    ''')


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def failing_case(i):
    return (f'<testcase name="t{i}" classname="com.acme.BarTest">'
            f'<failure message="m{i}" type="T">at com.acme.BarTest.t{i}(BarTest.java:{i})</failure></testcase>')


# ==================== parsing ====================

def test_parse_report_counts_every_kind(tmp_path):
    counts, _ = run_test.parse_report(write(tmp_path / 'TEST-com.acme.FooTest.xml', FAILING_REPORT))

    assert counts == {'tests': 4, 'failed': 1, 'errors': 1, 'skipped': 1}


def test_parse_report_failure_carries_its_assertion_line(tmp_path):
    _, failures = run_test.parse_report(write(tmp_path / 'TEST-com.acme.FooTest.xml', FAILING_REPORT))

    assert failures[0] == {
        'test': 'com.acme.FooTest#test_bad',
        'kind': 'failure',
        'type': 'org.opentest4j.AssertionFailedError',
        'message': 'expected: <1> but was: <2>',
        'at': 'FooTest.java:57',
    }


def test_parse_report_error_points_into_the_test_class_not_production(tmp_path):
    _, failures = run_test.parse_report(write(tmp_path / 'TEST-com.acme.FooTest.xml', FAILING_REPORT))

    assert failures[1]['kind'] == 'error'
    assert failures[1]['at'] == 'FooTest.java:63', 'the first frame is Prod.java; the test-class frame is the lambda'
    assert failures[1]['origin'] == 'Prod.java:10', 'where it happened, outside the test class'
    assert 'cause' not in failures[1], 'nothing chained'
    assert 'origin' not in failures[0], 'an assertion failure gets no origin - its line is the answer'


CHAINED_TRACE = textwrap.dedent('''\
    java.lang.IllegalStateException: wrapper
    \tat org.springframework.aop.Proxy.invoke(Proxy.java:5)
    \tat com.acme.FooTest.test_x(FooTest.java:20)
    Caused by: java.lang.RuntimeException: middle
    \tat com.acme.Service.call(Service.java:30)
    \t... 3 more
    Caused by: java.lang.NullPointerException: Cannot invoke "String.length()"
    \tat java.base/java.util.Objects.requireNonNull(Objects.java:233)
    \tat app//com.acme.FooTest$Fixture.build(FooTest.java:99)
    \tat app//com.acme.Repo.find(Repo.java:77)
    \tat com.acme.Service.call(Service.java:31)
    \t... 3 more
    ''')


def test_root_cause_is_the_deepest_caused_by():
    cause, section = run_test.root_cause(CHAINED_TRACE)

    assert cause == 'java.lang.NullPointerException: Cannot invoke "String.length()"'
    assert section.lstrip().startswith('Caused by: java.lang.NullPointerException')


def test_root_cause_without_a_chain_is_the_whole_trace():
    assert run_test.root_cause('x\n\tat a.B.c(B.java:1)') == (None, 'x\n\tat a.B.c(B.java:1)')
    assert run_test.root_cause(None) == (None, '')


def test_origin_skips_jdk_framework_and_test_class_frames_of_the_root_cause():
    # java.base/ and app// prefixes parsed; Objects is JDK, FooTest$Fixture is the test class; Repo is the code
    assert run_test.origin('com.acme.FooTest', CHAINED_TRACE) == 'Repo.java:77'


def test_origin_none_when_only_the_test_class_and_frameworks_are_in_the_trace():
    trace = '\tat org.junit.Assert.fail(Assert.java:1)\n\tat com.acme.FooTest.t(FooTest.java:5)'

    assert run_test.origin('com.acme.FooTest', trace) is None


def test_parse_report_error_carries_its_cause_and_origin(tmp_path):
    xml = ('<testsuite><testcase name="test_x" classname="com.acme.FooTest">'
           f'<error message="wrapper" type="java.lang.IllegalStateException">{CHAINED_TRACE}</error>'
           '</testcase></testsuite>')

    _, failures = run_test.parse_report(write(tmp_path / 'TEST-com.acme.FooTest.xml', xml))

    assert failures[0]['at'] == 'FooTest.java:20'
    assert failures[0]['cause'] == 'java.lang.NullPointerException: Cannot invoke "String.length()"'
    assert failures[0]['origin'] == 'Repo.java:77'


def test_parse_report_without_message_takes_the_first_trace_line(tmp_path):
    xml = ('<testsuite><testcase name="t" classname="a.B"><failure type="X">'
           'java.lang.AssertionError: no message attribute\n\tat a.B.t(B.java:3)</failure></testcase></testsuite>')

    _, failures = run_test.parse_report(write(tmp_path / 'TEST-a.B.xml', xml))

    assert failures[0]['message'] == 'java.lang.AssertionError: no message attribute'
    assert failures[0]['at'] == 'B.java:3'


def test_parse_report_reads_utf8_messages(tmp_path):
    xml = ('<?xml version="1.0" encoding="UTF-8"?><testsuite><testcase name="t" classname="a.B">'
           '<failure message="ожидалось: новый текст" type="X">at a.B.t(B.java:9)</failure></testcase></testsuite>')

    _, failures = run_test.parse_report(write(tmp_path / 'TEST-a.B.xml', xml))

    assert failures[0]['message'] == 'ожидалось: новый текст'


def test_locate_nested_class_frame():
    trace = 'x\n\tat com.acme.FooTest$Inner.test_x(FooTest.java:12)'

    assert run_test.locate('com.acme.FooTest', trace) == 'FooTest.java:12'


def test_locate_none_when_no_frame_is_in_the_test_class():
    assert run_test.locate('com.acme.FooTest', '\tat com.acme.Prod.run(Prod.java:10)') is None


def test_locate_does_not_match_a_class_with_the_same_prefix():
    assert run_test.locate('com.acme.Foo', '\tat com.acme.FooTest.t(FooTest.java:1)') is None


def test_truncate_cuts_long_messages():
    assert run_test.truncate('x' * 1000) == 'x' * run_test.MAX_MESSAGE_CHARS + '...'
    assert run_test.truncate('  short  ') == 'short'


def test_summarize_caps_the_failure_list(tmp_path):
    cases = ''.join(failing_case(i) for i in range(1, 13))
    report = write(tmp_path / 'TEST-com.acme.BarTest.xml', f'<testsuite>{cases}</testsuite>')

    s = run_test.summarize([report])

    assert s['failed'] == 12
    assert len(s['failures']) == run_test.MAX_FAILURES
    assert s['failuresTruncated'] is True


def test_fresh_reports_ignores_reports_older_than_the_run(tmp_path):
    started = time.time()
    old = write(tmp_path / 'TEST-a.Old.xml', PASSING_REPORT)
    os.utime(old, (started - 60, started - 60))
    new = write(tmp_path / 'TEST-a.New.xml', PASSING_REPORT)
    os.utime(new, (started + 1, started + 1))

    assert run_test.fresh_reports(tmp_path, started) == [new]


def test_fresh_reports_of_a_missing_dir_is_empty(tmp_path):
    assert run_test.fresh_reports(tmp_path / 'nope', time.time()) == []


def test_reports_between_keeps_only_the_window(tmp_path):
    t = time.time()
    reports = []
    for name, at in (('Before', t - 10), ('Inside', t), ('After', t + 10)):
        p = write(tmp_path / f'TEST-a.{name}.xml', PASSING_REPORT)
        os.utime(p, (at, at))
        reports.append(p)

    assert run_test.reports_between(tmp_path, t - 1, t + 1) == [reports[1]]
    assert run_test.reports_between(tmp_path / 'nope', t - 1, t + 1) == []


def test_read_list_skips_blank_lines_and_comments(tmp_path):
    listed = write(tmp_path / 'sweep.txt', '# the plain group\na.B,a.C\n\n  a.D#t  \n# a.E\n')

    assert run_test.read_list(listed) == ['a.B,a.C', 'a.D#t']


def test_log_errors_keeps_error_lines_without_ansi(tmp_path):
    log = write(tmp_path / 'maven.log', '[INFO] x\n\x1b[1;31m[ERROR]\x1b[m COMPILATION ERROR\n[ERROR] A.java:[3,1] boom\n')

    assert run_test.log_errors(log) == ['[ERROR] COMPILATION ERROR', '[ERROR] A.java:[3,1] boom']


def test_log_errors_keeps_the_first_lines_where_the_cause_is(tmp_path):
    cascade = '\n'.join(f'[ERROR] B{i}.java:[1,1] cannot find symbol' for i in range(100))
    log = write(tmp_path / 'maven.log', f'[ERROR] A.java:[2004,33] the cause\n{cascade}\n')

    errors = run_test.log_errors(log)

    assert errors[0] == '[ERROR] A.java:[2004,33] the cause'
    assert len(errors) == run_test.MAX_LOG_LINES


def test_log_errors_drops_mavens_closing_advice(tmp_path):
    log = write(tmp_path / 'maven.log', '\n'.join([
        '[ERROR] the cause',
        '[ERROR] -> [Help 1]',
        '[ERROR] ',
        '[ERROR] To see the full stack trace of the errors, re-run Maven with the -e switch.',
        '[ERROR] Re-run Maven using the -X switch to enable full debug logging.',
        '[ERROR] For more information about the errors and possible solutions, please read the following articles:',
        '[ERROR] [Help 1] http://cwiki.apache.org/confluence/display/MAVEN/MojoFailureException',
    ]))

    assert run_test.log_errors(log) == ['[ERROR] the cause']


def test_log_errors_falls_back_to_the_tail(tmp_path):
    log = write(tmp_path / 'maven.log', '\n'.join(f'line {i}' for i in range(100)))

    errors = run_test.log_errors(log)

    assert len(errors) == run_test.MAX_LOG_LINES
    assert errors[-1] == 'line 99'


# ==================== run state ====================

def new_run_dir(tmp_path, started_at):
    run_dir = tmp_path / 'run'
    run_dir.mkdir()
    run_test.write_json_atomic(run_dir / run_test.RUN_FILE, {
        'pomDir': str(tmp_path), 'test': 'com.acme.FooTest', 'reportsDir': str(tmp_path / 'reports'),
        'command': ['mvn'], 'startedAt': started_at})
    return run_dir


def finished_pid():
    p = subprocess.Popen([sys.executable, '-c', 'pass'])
    p.wait()
    return p.pid


def test_collect_done_reads_this_runs_report(tmp_path):
    started = time.time() - 5
    run_dir = new_run_dir(tmp_path, started)
    write(tmp_path / 'reports' / 'TEST-com.acme.FooTest.xml', FAILING_REPORT)
    run_test.write_json_atomic(run_dir / run_test.EXIT_FILE, {'exit': 1, 'finishedAt': started + 3})

    r = run_test.collect(run_dir)

    assert r['status'] == 'done'
    assert r['exit'] == 1
    assert r['seconds'] == 3.0
    assert r['handle'] == str(run_dir)
    assert r['tests'] == 4
    assert [f['at'] for f in r['failures']] == ['FooTest.java:57', 'FooTest.java:63']
    assert 'mavenOutput' not in r
    assert run_test.exit_code_of(r) == run_test.EXIT_FAILED


def test_collect_done_without_reports_shows_mavens_errors(tmp_path):
    started = time.time() - 5
    run_dir = new_run_dir(tmp_path, started)
    write(run_dir / run_test.LOG_FILE, '[ERROR] COMPILATION ERROR\n')
    run_test.write_json_atomic(run_dir / run_test.EXIT_FILE, {'exit': 1, 'finishedAt': started + 2})

    r = run_test.collect(run_dir)

    assert r['status'] == 'done'
    assert 'none written' in r['reports']
    assert r['mavenOutput'] == ['[ERROR] COMPILATION ERROR']
    assert run_test.exit_code_of(r) == run_test.EXIT_FAILED


def test_collect_lost_when_the_supervisor_died_without_a_result(tmp_path):
    run_dir = new_run_dir(tmp_path, time.time() - 5)
    write(run_dir / run_test.PID_FILE, str(finished_pid()))

    r = run_test.collect(run_dir)

    assert r['status'] == 'lost'
    assert run_test.exit_code_of(r) == run_test.EXIT_OTHER


def test_collect_running_while_the_pid_is_not_recorded_yet(tmp_path):
    run_dir = new_run_dir(tmp_path, time.time())

    assert run_test.collect(run_dir)['status'] == 'running'


def test_collect_lost_when_the_pid_never_got_recorded(tmp_path):
    run_dir = new_run_dir(tmp_path, time.time() - run_test.PID_GRACE_SECONDS - 1)

    assert run_test.collect(run_dir)['status'] == 'lost'


def test_pid_alive():
    assert run_test.pid_alive(os.getpid()) is True
    assert run_test.pid_alive(finished_pid()) is False
    assert run_test.pid_alive(None) is False


def test_emit_prints_one_line_unless_pretty(capsys):
    result = {'status': 'done', 'exit': 1, 'handle': 'h', 'tests': 2, 'failed': 1,
              'failures': [{'test': 'a.B#t', 'at': 'B.java:1'}]}

    run_test.emit(result, utf8=False)
    one_line = capsys.readouterr().out
    run_test.emit(result, utf8=False, pretty=True)
    pretty = capsys.readouterr().out

    assert one_line.count('\n') == 1
    assert pretty.count('\n') > 1
    assert json.loads(one_line) == json.loads(pretty)


def test_trim_of_a_passed_run_keeps_what_the_reader_acts_on():
    result = {'status': 'done', 'exit': 0, 'seconds': 4.2, 'test': 'a.B', 'handle': 'h', 'tests': 3, 'failed': 0,
              'errors': 0, 'skipped': 0, 'failures': [], 'failuresTruncated': False}

    assert run_test.trim(result) == {'status': 'done', 'exit': 0, 'seconds': 4.2, 'test': 'a.B', 'tests': 3}
    assert result['handle'] == 'h', 'trim copies; the result itself is left as it was'


def test_trim_of_a_failed_run_keeps_the_handle_and_the_failures():
    result = {'status': 'done', 'exit': 1, 'handle': 'h', 'tests': 3, 'failed': 1, 'errors': 0,
              'failures': [{'test': 'a.B#t'}], 'failuresTruncated': False}

    assert run_test.trim(result) == {'status': 'done', 'exit': 1, 'handle': 'h', 'tests': 3, 'failed': 1,
                                     'failures': [{'test': 'a.B#t'}]}


def test_trim_keeps_the_handle_of_a_running_run_and_trims_sweep_items():
    assert run_test.trim({'status': 'running', 'handle': 'h', 'elapsedSeconds': 1.0})['handle'] == 'h'
    swept = run_test.trim({'status': 'done', 'exit': 1, 'handle': 'h', 'runs': 2, 'passedRuns': 1, 'tests': 5,
                           'failed': 1, 'errors': 0, 'skipped': 0,
                           'items': [{'test': 'a.B', 'exit': 1, 'failed': 1, 'errors': 0, 'skipped': 0,
                                      'failures': [{'test': 'a.B#t'}], 'failuresTruncated': False}]})

    assert swept['items'] == [{'test': 'a.B', 'exit': 1, 'failed': 1, 'failures': [{'test': 'a.B#t'}]}]
    assert run_test.exit_code_of(swept) == run_test.EXIT_FAILED


def test_emit_is_ascii_by_default(capsys):
    run_test.emit({'status': 'done', 'exit': 0, 'message': 'текст'}, utf8=False)

    out = capsys.readouterr().out
    assert out.isascii()
    assert json.loads(out)['message'] == 'текст'


# ==================== end to end, with a stand-in for Maven ====================

def fake_maven(tmp_path):
    """Maven's place in the command is an executable; this one writes a surefire report the way Maven would."""
    script = write(tmp_path / 'fake_mvn.py', FAKE_MVN)
    if os.name == 'nt':
        return write(tmp_path / 'fake-mvn.cmd',
                     f'@"{sys.executable}" "{script}" %*\r\n@exit /b %ERRORLEVEL%\r\n')
    launcher = write(tmp_path / 'fake-mvn', f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
    launcher.chmod(0o755)
    return launcher


def cli(*args, **env):
    full_env = {**os.environ, 'FAKE_MVN_FAILING': FAILING_REPORT, 'FAKE_MVN_PASSING': PASSING_REPORT, **env}
    p = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=full_env, timeout=120)
    return p.returncode, json.loads(p.stdout)


def pom_dir(tmp_path):
    pom = tmp_path / 'module'
    write(pom / 'pom.xml', '<project/>')
    return pom


def test_run_reports_failures_with_their_lines(tmp_path):
    code, r = cli('run', str(pom_dir(tmp_path)), 'com.acme.FooTest', '--mvn', str(fake_maven(tmp_path)),
                  '--max-seconds', '60')

    assert code == run_test.EXIT_FAILED, r
    assert r['status'] == 'done'
    assert r['exit'] == 1
    assert r['test'] == 'com.acme.FooTest'
    assert [f['test'] for f in r['failures']] == ['com.acme.FooTest#test_bad', 'com.acme.FooTest#test_boom']


def test_run_returns_a_handle_and_wait_finishes_it(tmp_path):
    mvn = str(fake_maven(tmp_path))

    code, started = cli('run', str(pom_dir(tmp_path)), 'com.acme.FooTest', '--mvn', mvn, '--max-seconds', '0.5',
                        FAKE_MVN_SLEEP='3', FAKE_MVN_OUTCOME='pass')
    assert code == run_test.EXIT_RUNNING, started
    assert started['status'] == 'running'

    code, done = cli('wait', started['handle'], '--max-seconds', '60')
    assert code == run_test.EXIT_PASSED, done
    assert done['status'] == 'done'
    assert done['exit'] == 0
    assert done['tests'] == 1
    assert 'failures' not in done, 'trimmed: a passed run has none to show'
    assert 'handle' not in done, 'trimmed: a passed run needs no handle'


def test_second_run_in_the_same_module_is_refused_while_the_first_runs(tmp_path):
    mvn = str(fake_maven(tmp_path))
    pom = str(pom_dir(tmp_path))
    _, first = cli('run', pom, 'com.acme.FooTest', '--mvn', mvn, '--max-seconds', '0', FAKE_MVN_SLEEP='3')

    code, second = cli('run', pom, 'com.acme.FooTest', '--mvn', mvn, '--max-seconds', '0')

    assert code == run_test.EXIT_OTHER, second
    assert second['status'] == 'busy'
    assert second['handle'] == first['handle']
    cli('wait', first['handle'], '--max-seconds', '60')


def test_run_without_a_pom_is_a_usage_error(tmp_path):
    code, r = cli('run', str(tmp_path), 'com.acme.FooTest', '--mvn', 'mvn')

    assert code == run_test.EXIT_OTHER
    assert r['status'] == 'usage'


# ==================== sweep, end to end ====================

def sweep_list(tmp_path, *tests):
    return str(write(tmp_path / 'sweep.txt', '# a sweep\n' + '\n'.join(tests) + '\n'))


def test_sweep_reports_the_totals_and_only_the_runs_that_did_not_pass(tmp_path):
    listed = sweep_list(tmp_path, 'com.acme.AOkTest', 'com.acme.BBadTest', 'com.acme.COkTest')

    code, r = cli('sweep', str(pom_dir(tmp_path)), listed, '--mvn', str(fake_maven(tmp_path)), '--max-seconds', '90',
                  FAKE_MVN_PASS_TESTS='com.acme.AOkTest;com.acme.COkTest')

    assert code == run_test.EXIT_FAILED, r
    assert r['status'] == 'done'
    assert r['exit'] == 1
    assert r['runs'] == 3
    assert r['passedRuns'] == 2
    assert r['tests'] == 1 + 4 + 1, 'each run read from its own reports'
    assert [i['test'] for i in r['items']] == ['com.acme.BBadTest']
    assert [f['at'] for f in r['items'][0]['failures']] == ['FooTest.java:57', 'FooTest.java:63']
    assert 'handle' in r


def test_sweep_all_passing_is_one_short_line(tmp_path):
    listed = sweep_list(tmp_path, 'com.acme.AOkTest', 'com.acme.COkTest')

    code, r = cli('sweep', str(pom_dir(tmp_path)), listed, '--mvn', str(fake_maven(tmp_path)), '--max-seconds', '90',
                  FAKE_MVN_OUTCOME='pass')

    assert code == run_test.EXIT_PASSED, r
    assert r == {'status': 'done', 'exit': 0, 'seconds': r['seconds'], 'test': 'sweep sweep.txt', 'runs': 2,
                 'passedRuns': 2, 'tests': 2}


def test_sweep_reports_its_progress_while_running(tmp_path):
    listed = sweep_list(tmp_path, 'com.acme.AOkTest', 'com.acme.BBadTest', 'com.acme.COkTest')

    code, started = cli('sweep', str(pom_dir(tmp_path)), listed, '--mvn', str(fake_maven(tmp_path)),
                        '--max-seconds', '0.5', FAKE_MVN_SLEEP='1', FAKE_MVN_PASS_TESTS='com.acme.AOkTest')
    assert code == run_test.EXIT_RUNNING, started
    assert started['of'] == 3
    assert started['done'] < 3

    code, done = cli('wait', started['handle'], '--max-seconds', '90')
    assert code == run_test.EXIT_FAILED, done
    assert [i['test'] for i in done['items']] == ['com.acme.BBadTest', 'com.acme.COkTest']


def test_sweep_of_an_empty_list_is_a_usage_error(tmp_path):
    code, r = cli('sweep', str(pom_dir(tmp_path)), sweep_list(tmp_path, '# nothing'), '--mvn', 'mvn')

    assert code == run_test.EXIT_OTHER
    assert r['status'] == 'usage'
