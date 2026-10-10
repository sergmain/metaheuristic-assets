# run_test.py - Maven/surefire runs with a compact JSON result

A development tool for agents (Claude Code) and people running JUnit tests through Maven from a terminal. Not a
bundle: nothing here is delivered to a Processor.

## Why

Running `mvn test` in a terminal puts the whole console output into the agent's context, and a run longer than the
terminal tool's timeout has to be polled by hand. `run_test.py` owns the Maven process, waits up to a bound, and
prints a few lines of JSON: the exit code and the failures with `file:line` - or a handle to wait on.

## Usage

```
python run_test.py run  <pomDir> <test> [--max-seconds N] [--reports-dir DIR] [--mvn PATH] [--maven-arg ARG]... [--utf8]
python run_test.py wait <handle> [--max-seconds N] [--utf8]
```

- `<test>` is the `-Dtest` value: `pkg.Class`, `pkg.Class#method`. Maven runs as `mvn -q test -Dtest=<test>` in
  `<pomDir>`; `--maven-arg` adds arguments, one per flag.
- `--max-seconds` (default 50) bounds one call. Keep it under the terminal tool's EFFECTIVE limit, which is not
  necessarily its `timeout` parameter: the JetBrains MCP terminal returned a 55-second command but timed out a
  70-second one even with `timeout` set to 150 s (observed 2026-10-10). Past that limit the call comes back empty
  while the run itself goes on - `wait` on `<pomDir>/target/run-test/active`'s handle picks it up.
- The run continues after the call returns: `run` answers `"status": "running"` with a `handle`; pass it to `wait`.
- One run per `pomDir` at a time - two Maven runs race on `target/`. A second `run` answers `"status": "busy"` with the
  active run's handle.
- Output is ASCII JSON by default: non-ASCII text, e.g. a Cyrillic assertion message, arrives as `\u` escapes, which
  survive any console code page. `--utf8` prints raw UTF-8.

Exit status: `0` done, passed - `1` done, tests or Maven failed - `2` still running - `3` lost, busy or bad usage.

## Output

```
{
  "status": "done",
  "exit": 1,
  "seconds": 41.3,
  "test": "ai.metaheuristic.ai.mcp.ExecContextWaitUtilsTest",
  "tests": 17, "failed": 1, "errors": 0, "skipped": 0,
  "failures": [
    { "test": "ai.metaheuristic.ai.mcp.ExecContextWaitUtilsTest#test_terminal_waitsUntilTheExecContextFinishes",
      "kind": "failure", "type": "org.opentest4j.AssertionFailedError",
      "message": "expected: <3000> but was: <4000>", "at": "ExecContextWaitUtilsTest.java:156" }
  ],
  "failuresTruncated": false
}
```

`status` is one of `done`, `running`, `lost` (the supervisor died without a result - see `mavenOutput`), `busy`,
`usage`. When Maven failed before any test ran - a compilation error, no test matching `<test>` - there is no report,
and `mavenOutput` carries Maven's `[ERROR]` lines instead.

## How it works

- `run` writes `<pomDir>/target/run-test/<runId>/run.json` and starts a detached supervisor (this script,
  `_supervise`), which runs Maven with its output in `maven.log` and then writes Maven's exit code to `exit.json`.
  The handle is that run directory's path.
- The end of a run is `exit.json`, never a side effect: a run that never got to the tests still ends.
- Only reports written after the run started are read, so `target/surefire-reports` left over from an earlier run is
  never mistaken for this one's.
- `file:line` is the first stack frame inside the test class - its methods, lambdas and nested classes.
- On Windows Maven is `mvn.cmd`, started without a shell, so no PowerShell quoting is involved.

Standard library only. Tests: `python -m pytest -q tests`.
