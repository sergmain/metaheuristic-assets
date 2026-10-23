# call-cc — DETAILS

Everything true of THIS capability and of nothing else.

---

## 1. Purpose

Run the Claude Code CLI against a prompt handed in as a Variable, and return whatever the model sent
back through this capability's own MCP server — verbatim, as a Variable.

The Function is agnostic on both ends, and that is the whole design:

- it does not build the prompt — a caller writes the prompt into the input Variable
- it does not read the answer — the answer is copied byte for byte into the output Variable

Put a prompt or a parser inside it and it stops being reusable, which is the one property it exists
to have. A caller that needs a particular answer shape asks for it in the prompt and parses it in a
LATER process.

❗ **Where this sits.** A workflow that takes a file and stores it in a meta table is deterministic.
A workflow that takes a file, ANALYSES it, and stores the result is semi-deterministic — and this
Function is the analysing step inside one: the single slot where a deterministic pipeline hands a
judgement to a model and gets an answer back. ⚠️ It is NOT the layer that decides which workflow to
run, or whether a job needs a model at all. That decision is made above it and arrives here already
made, as a prompt in a Variable.

---

## 2. The graph

`mh-call-cc-1.0.mhsc` — the prompt arrives as a source-level input, so one registered graph serves
every caller that has something to ask.

| # | process | what it contributes |
|---|---|---|
| 1 | `call` — `mh.asset.call-cc` | writes `.mcp.json`, `cc-settings.json` and `cc-system-prompt.txt`, runs CC with the prompt on stdin, copies the stored answer into `ccResult` |

❗ `ccResult` is declared with `->` in the source-level `variables` block. That is what makes it an
ExecContext-level output global rather than a variable visible only inside the graph.

❗ **Launch it with `mh_create_exec_context_with_variables`.** It initializes source-level inputs and
then produces Tasks. `mh_create_exec_context` refuses a SourceCode that declares any (562.120),
because it has no way to supply the values — that is a routing rule, never a reason to write the
run's prompt into the `.mhsc`.

---

## 3. The run-data contract

Every Variable is named by a meta — never hard-coded — so a process at any nesting level may rename
its variables freely.

**Metas** on the `call` process:

| meta | required | meaning |
|---|---|---|
| `variable-for-prompt` | yes | name of the INPUT Variable holding the complete prompt |
| `variable-for-output` | yes | name of the OUTPUT Variable receiving the answer |
| `variable-for-model` | no (yes on `claude_api`) | name of an optional INPUT Variable holding the model id (`opus`, `sonnet`, a full model code). Absent means CC's own default; the API has no default (§8) |
| `variable-for-effort` | no | name of an optional INPUT Variable holding the CC effort; ignored on `claude_api` |
| `llm_provider` | no | `cc` (absent means this) or `claude_api` (§8). Any other value fails the Task |
| `max-tokens` | no | `claude_api` only: the output budget of the one call. Absent means 8192 |
| `timeout-sec` | no | seconds allowed to the CC process - or to the HTTP call on `claude_api`. Absent means 300 |

⚠️ `variable-for-prompt` and `variable-for-output` have **no fallback**. An absent meta fails the
Task rather than guessing a name, because a guess that happens to hit an existing variable is a wrong
answer instead of an error.

⚠️ The process `timeout` must be LARGER than `timeout-sec`. The inner one lets the Function report
what went wrong; the outer one kills the Task without a word.

**Env**, resolved from `artifacts/mh-env.yaml`:

| env code | what for |
|---|---|
| `claude-code` | the CC executable |

The MCP server is launched with `sys.executable` — by construction the interpreter the Processor
already resolved to run this Function — so `python-3` is never looked up a second time.

---

## 4. Durable side effects

Inside the task dir only. Nothing is written outside it, and nothing survives the Task.

| where | what |
|---|---|
| `cc-prompt.txt` | the prompt, as fed to CC on stdin |
| `.mcp.json` | the generated MCP config |
| `cc-settings.json` | the CC session settings — `{"ultracode": false}`, passed with `--settings` (§6) |
| `cc-system-prompt.txt` | the MCP-availability rule, appended to CC's system prompt with `--append-system-prompt-file` (§5) |
| `cc-data/cc-result.out` | the answer, written by the MCP server |
| `cc-data/cc-console.log` | CC's console, whole |
| `cc-data/mcp-server.log` | the MCP server's own log |
| `cc-data/api-response.json` | `claude_api` only: the raw API response (never the key - it goes out in a header) |
| `artifacts/<output id>` | the answer, copied verbatim |

---

## 5. The result channel

One MCP tool, `mh_cc_store_result(result)`, and it stores exactly once.

❗ **The console is not a fallback.** It is Processor-owned diagnostics — stderr is merged into it and
the tail is truncated — so an answer recovered from it may already have been cut in half, silently. A
run that stored nothing through the tool produced nothing, and fails.

❗ **A second call is refused**, and the first answer is left unchanged. A Task runs this Function in
its own task dir exactly once, so a second store is not a second answer — it is one run contradicting
itself, and silently overwriting would keep whichever call happened to be last.

⚠️ **An empty store is refused without spending the single store.** Otherwise the file would exist,
the guard would be spent, and the Function would still report "no result" — the model having been
told `stored: true` for a run that fails.

❗ **A channel that is gone ends the run at once, with a NEGATIVE exit code.** The Function owns one
instruction, about its own channel and nothing else: `cc-system-prompt.txt`, appended to CC's system
prompt, tells the model that when the `mhcc` server is not connected — or a call to it fails at
transport level — it must stop immediately, emit exactly one line `MCP_UNAVAILABLE: <the error>`, and
end its turn. The prompt Variable is untouched: the rule rides on the system prompt, not on stdin.

⚠️ **The model cannot set CC's exit code** — a `-p` run gives it no tool that ends the process with a
code of its choosing — so the line is its request. `main()` finds it in CC's console and returns `-1`
(`MCP_UNAVAILABLE_EXIT_CODE`); every other failure returns `1`. The line is checked before CC's own exit
code: a run that reported the server gone produced nothing usable, whatever CC exited with.

⚠️ **The rule's own template line is not a report.** `MCP_UNAVAILABLE: <the error you saw>` is skipped
by its placeholder, so a console that echoes the system prompt never fails a healthy run. Keep it the
only line of the rule that starts with the marker.

---

## 6. Ultracode is off

Ultracode is a Claude Code **setting** — `xhigh` effort plus automatic dynamic-workflow orchestration.
A user-level `"ultracode": true` on the Processor box would otherwise start every run with it.

- `cc-settings.json` (`{"ultracode": false}`) is passed with `--settings`, by bare name, the same way
  `.mcp.json` goes in with `--mcp-config`. `--settings` outranks every `settings.json` scope except
  managed settings.
- ❌ **Not `.mcp.json`.** `--mcp-config` reads MCP servers only; a settings key placed there is never
  consulted.
- ❗ **An `effort` of `ultracode` is refused** before CC is started. `--effort ultracode` turns
  ultracode on for the session whatever the settings say, so passing it on would undo the disable.

---

## 7. Known limits

- ⚠️ **Timeout kills the CC process, not its children.** CC spawns the MCP server; on timeout the
  Python launcher terminates the direct child only. MH's own Java launcher walks the process tree.
  A timed-out run may leave an MCP server process behind.
- ⚠️ **The `claude-code` env value is used as a single argv element.** An entry carrying arguments
  (`/usr/bin/claude --foo`) would be treated as one executable path. This matches what the Java
  Function does, and no caller has needed otherwise.
- ⚠️ **A prompt in an `.mhsc` inline literal is one line.** The STRING lexer does not accept a raw
  newline. A multi-line prompt comes from a Variable some other process wrote.
- ❓ **The MCP server name carries no hyphen or dot** (`mhcc`). CC composes tool ids as
  `mcp__<server>__<tool>`, and whether a separator inside `<server>` survives that is not established
  here — so the name avoids the question rather than answering it.
- ❌ **Nothing verifies the answer.** The Function checks that a non-empty result was stored and
  nothing else. Whether the answer is correct, or even on topic, is the caller's to judge.
- ⚠️ **A negative exit code is literal only on Windows.** Exit codes there are 32-bit; POSIX keeps 8
  bits, so `-1` from a Linux Processor reads as `255`.
- ⚠️ **The outage report depends on the model obeying the rule.** A model that holds the work or
  retries instead leaves no line; the run then fails as an ordinary "no result" (exit `1`) or at the
  timeout. A wedged MCP client can also hold the CC process open whatever the model decides.

---

## 8. The `claude_api` path

Process meta `llm_provider = "claude_api"` replaces the CC CLI with ONE Anthropic Messages API call
(`mh_api_call.py`, beside the entry in the same payload). Everything above the model is unchanged: the prompt Variable
in, the answer Variable out, every name through a meta.

❗ **The same result channel, as a forced tool.** The request offers the tool `mh_cc_store_result` (one string
parameter `result`) and forces it with `tool_choice`. The answer is that one call's `result`, copied verbatim - never
the model's free text. A prompt written for the CC path ("store your answer with `mh_cc_store_result`") therefore
works unchanged on this path.

❗ **Its own Function code.** The key arrives only for a code whose `mh-function.yaml` declares `api.keyCode`:
`mh.asset.call-cc-api_1.0` (`functions/fn-call-cc-api`), the same payload with `api.keyCode: ANTHROPIC_API_KEY`. The
CC codes never declare it - MH launches no Task whose sealed key is unavailable, so a Vault without the key would
withhold every CC run. A SourceCode on the API path names the API code AND sets `llm_provider = "claude_api"`:
`source-codes/mh-call-cc-api-1.0.mhsc` is the one-call check.

| failure | exit | what the console says |
|---|---|---|
| no model Variable | 1 | `no model for llm_provider=claude_api` - the API has no default model |
| no key handed over | 1 | `no API key was handed over` - the code declares no `api.keyCode`, or no Vault holds it |
| non-2xx response | 1 | `Anthropic API call failed with status <code>; body=...` - the analyzers match this line |
| `stop_reason` `max_tokens` | 1 | `hit max_tokens` - the answer was cut off; raise meta `max-tokens` |
| not exactly one store call, or an empty `result` | 1 | `expected exactly one mh_cc_store_result call` / `empty result` |

- ⚠️ **The key is zeroed after the call** (`mh_api_call.zero`), and is never printed, logged or written.
- ⚠️ **The model id goes to the API as given.** CC aliases (`opus`, `sonnet`) are CLI conventions; on this path a run
  passes a full model id (`claude-haiku-5-5`), and an unknown one comes back as a non-2xx response.
- ⚠️ **One call, no agent loop.** The model has no tools but the store tool, so a prompt that needs to read files or
  run commands is a CC-path prompt.