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
| 1 | `call` — `mh.asset.call-cc` | writes `.mcp.json`, runs CC with the prompt on stdin, copies the stored answer into `ccResult` |

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
| `model` | no | CC model (`opus`, `sonnet`, a full model code). Absent means CC's own default |
| `timeout-sec` | no | seconds allowed to the CC process. Absent means 300 |

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
| `cc-data/cc-result.out` | the answer, written by the MCP server |
| `cc-data/cc-console.log` | CC's console, whole |
| `cc-data/mcp-server.log` | the MCP server's own log |
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

---

## 6. Known limits

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
