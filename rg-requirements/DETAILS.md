# rg-requirements

SourceCode `mh-rg-requirements-from-file-1.1` · Functions `mh.asset.rg-req-prompt_1.0`, `mh.asset.rg-req-store_1.0`
· payload `rg-requirements/payload/fn-rg-requirements` · also uses `mh.asset.rg-temp-project_1.1`,
`mh.asset.call-cc` and the internal `mh.meta-storage`

SourceCode `mh-rg-requirements-from-batch-1.4` (section 7) - Functions `mh.asset.rg-batch-paths_1.0`,
`mh.asset.rg-req-path-prompt_1.0`, `mh.asset.rg-req-check_1.0`, `mh.asset.rg-req-store-batch_1.0` - the same payload -
also uses the internal `mh.batch-line-splitter` and `mh.aggregate`

SourceCode `mh-rg-requirements-from-batch-internal-1.0` (section 8) - the batch graph with its store run inside RG as
the internal Function `mhdg-rg.req-store-batch` - Functions `mh.asset.rg-batch-paths_1.0`,
`mh.asset.rg-req-path-prompt_1.0`, `mh.asset.rg-req-check_1.0`, `mh.asset.rg-temp-project_1.1`, `mh.asset.call-cc_1.1`

SourceCode `mh-rg-requirements-from-batch-stage-first-1.0` (section 12) - ONE STAGE opened on the still-empty project,
every file's requirements stored into it from the file's own branch - Functions `mh.asset.rg-open-stage_1.0`,
`mh.asset.rg-req-lines_1.0`, and internal-1.0's except the store

SourceCode `mh-rg-requirements-from-batch-stage-store-1.0` (section 12, E3) - the same STAGE, internal-1.0's `store`
moved into every file's branch after `check`, one Task per file - Functions `mh.asset.rg-open-stage_1.0`,
`mh.asset.rg-req-store-stage_1.0`, and internal-1.0's except the store

## 1. Purpose

Turn one source file into requirements held in RG. A fresh RG project is created for the purpose; the file is
named by a record of a meta table (the output of a dir-batcher run); CC reads the file together with the
project's description and writes the requirements; they are stored in the project.

## 2. The graph

Declaration order is execution order.

| # | process | Function | contributes |
|---|---|---|---|
| 1 | `mkproject` | `mh.asset.rg-temp-project_1.1` | the project: the given description, the given RG genesis pipeline, ready - created in development runs too |
| 2 | `select` | internal `mh.meta-storage`, `select` | `batchRecords` - the `batchKey` record of `metaTable`, from the table `synthetic` names |
| 3 | `prompt` | `mh.asset.rg-req-prompt_1.0` | the path on the first line of the record, the file (up to 300000 bytes), and the prompt: description, document, answer contract |
| 4 | `cc` | `mh.asset.call-cc` | CC's answer: a JSON array of `{name, content, rationale}`, 1 to 5 of them |
| 5 | `store` | `mh.asset.rg-req-store_1.0` | the requirements in the project; `reqIds` |

The store step checks the whole answer first - JSON, non-empty, at least 3 words of content, a rationale - and
only then writes. Requirement #1 goes through `requirements/manual/first`, which runs the project's one-shot
genesis and answers with the snapshot it committed; every next one goes through `requirements/manual` onto the
snapshot the previous call committed.

## 3. Run-data contract

Launch with `mh_create_exec_context_with_variables`.

| variable | direction | meaning | example |
|---|---|---|---|
| `rgBaseUrl` | in | the RG to work in | `http://localhost:64967` |
| `locale` | in | the project's language | `en` |
| `projectDescription` | in | what the requirements are for - the project's description and part of the prompt | `Requirements for java-based database Derby` |
| `rgPipelineUid` | in | the RG genesis pipeline the project runs | `mhdg-rg-cc-1.0.76` |
| `metaTable` | in | the meta-storage type holding the batch records | `mh.asset.dir-batch-for-requirements.2` |
| `batchKey` | in | the record to read | `batch-0001` |
| `synthetic` | in | `true` reads the synthetic meta store, `false` the production one | `true` |
| `production` | in, required | declared by convention; it gates nothing in this graph | `false` |
| `projectCode` | out | the project's code | `TMP…` |
| `sourcePath` | out | the file the requirements came from | |
| `reqIds` | out | the stored requirements' ids, one per line | |

**Credential:** the vault entry `RG_API_AUTH` (plain `login:password`), declared by `mh.asset.rg-temp-project_1.1`
and `mh.asset.rg-req-store_1.0` and handed to each over the Processor's loopback secret channel.

## 4. Durable side effects

- One RG project, created in every run, development runs included: its description, the pipeline, `isReady`.
- Its genesis run (an RG ExecContext) and one committed snapshot per stored requirement.
- Nothing is written to meta storage; the batch record is only read.

## 5. Fitness criteria

| id | criterion | hardness | type |
|---|---|---|---|
| F1 | the reported `projectCode` names a project RG lists, with the given description | hard | D |
| F2 | every id in `reqIds` is a requirement of that project in RG, and there are as many as CC answered | hard | D |
| F3 | `sourcePath` is the first line of the selected record | hard | D |
| F4 | every stored requirement is about the source file - its content can be traced to the document | soft | S |

## 6. Corrections

- **2026-09-18, 1.0 → 1.1.** 1.0 created the project with `maxDepth 1`. RG refuses a `maxDepth` outside `[2, 6]`
  (`RgConsts`, `03.877.010`), so no project was created (ExecContext #11). The requirement had been inferred
  from an error message in `RgFirstManualRequirementService`; the code that runs the genesis
  (`RgExecTxService`, `827.145`) already runs a MANUAL genesis at depth 1 whatever the project holds. 1.1 sends
  no depth.

---

## 7. mh-rg-requirements-from-batch-1.4 - every file of a batch

### 7.1 Purpose

Turn every file of one batch record into requirements held in one fresh RG project, then take the record off the
queue. CC works on the files in parallel, one branch per file; the requirements are stored as one chain of
snapshots; the record is deleted only after every file's requirements are stored.

### 7.2 The graph

Declaration order is execution order; everything after `split` waits for all of its branches.

| # | process | Function | contributes |
|---|---|---|---|
| 1 | `mkproject` | `mh.asset.rg-temp-project_1.1` | the project, as in section 2 |
| 2 | `select` | internal `mh.meta-storage`, `select` | `batchRecords` - the `batchKey` record of `metaTable` |
| 3 | `paths` | `mh.asset.rg-batch-paths_1.0` | `batchPaths` - the record's paths, one per line; refuses a record that is missing or not unique, and a relative or repeated path |
| 4 | `split` | internal `mh.batch-line-splitter` | one branch per path, the path in `sourcePath` |
| 4.1 | `prompt` | `mh.asset.rg-req-path-prompt_1.0` | the file (up to 300000 bytes) and the prompt - the same prompt `mh.asset.rg-req-prompt_1.0` builds |
| 4.2 | `cc` | `mh.asset.call-cc_1.1` | CC's answer; model and effort from the optional `model`/`effort` inputs (DAHF 0.5); `tries 2`; cached - `cache on, cacheMeta`; a CC session limit is identified by the execution gate (7.7) |
| 4.3 | `check` | `mh.asset.rg-req-check_1.0` | `reqAnswer` - the answer checked as the store checks it, written as one line of ASCII JSON `{sourcePath, requirements}` |
| 5 | `gather` | internal `mh.aggregate`, `text` | `reqAnswers` - every branch's `reqAnswer`, collected by name across the ExecContext |
| 6 | `store` | `mh.asset.rg-req-store-batch_1.0` | the requirements in the project as TWO committed snapshots - the genesis (#1) and one sealed STAGE with all the rest (7.7); every rationale ends with `source: <file>`; `reqIds`, `reqSources` |
| 7 | `dropRecord` | internal `mh.meta-storage`, `delete` | **disabled in 1.2** (commented out, 7.7) - the `batchKey` record would be removed from the table `synthetic` names |

**Why the store is not in the branches.** `requirements/manual` forks a new STAGE from whichever COMMITTED snapshot
it is given, and `RgSnapshotLifecycleService.openStageFromParent` checks only that the parent is COMMITTED - never
whether it already has children. Branches storing in parallel would fork the project into one leaf per file, each
holding a different subset; and `requirements/manual/first` is one-shot, so only one branch could have started the
chain at all.

**Every file or nothing.** Before RG is called, the store requires the answers to cover the batch exactly: one per
path, none outside it. `mh.aggregate` collects only the variables that exist, so a branch that never wrote its
answer would otherwise simply be missing. A failed branch therefore holds the whole batch back: nothing is stored
and the record stays in the queue. Resetting the failed Task re-runs that file alone; the other files' answers are
kept.

### 7.3 Run-data contract

Launch with `mh_create_exec_context_with_variables`.

| variable | direction | meaning | example |
|---|---|---|---|
| `rgBaseUrl`, `locale`, `projectDescription`, `rgPipelineUid`, `metaTable`, `production` | in | as in section 3 | |
| `batchKey` | in | the record to process, then delete | `batch-0004` |
| `synthetic` | in | the table the record is read from AND deleted from: exactly `true` (synthetic) or `false` (production) - the delete refuses any other value | `true` |
| `model` | in, optional | the model CC uses (`--model`). Unseeded or `mh.null-value` -> the flag is omitted and CC's default applies | `claude-opus-4-8` |
| `effort` | in, optional | the effort CC uses (`--effort`: `low`/`medium`/`high`/`xhigh`/`max`). Unseeded or `mh.null-value` -> omitted | `medium` |
| `projectCode` | out | the project's code | `TMP...` |
| `reqIds` | out | the stored requirements' ids, one per line, in storing order | |
| `reqSources` | out | one line per stored requirement: its id, a TAB, the file it came from | |

**Credential:** the vault entry `RG_API_AUTH`, declared by `mh.asset.rg-temp-project_1.1` and
`mh.asset.rg-req-store-batch_1.0`.

### 7.4 Durable side effects

- One RG project per run, development runs included: its description, the pipeline, `isReady`.
- Its genesis run (an RG ExecContext) and one committed snapshot per stored requirement, in one linear chain.
- The `batchKey` record is DELETED from the table `synthetic` names - after the store has succeeded, and only then.
  ⚠️ Not in 1.2: `dropRecord` is commented out, so the record stays in the table and the batch can be run again.

### 7.5 Fitness criteria

| id | criterion | hardness | type |
|---|---|---|---|
| F1 | the reported `projectCode` names a project RG lists, with the given description | hard | D |
| F2 | every id in `reqIds` is a requirement of that project, as many as the answers held | hard | D |
| F3 | the project's snapshots form one linear chain - no fork | hard | D |
| F4 | every path of the record appears in `reqSources`, and no other path does | hard | D |
| F5 | the `batchKey` record is gone from the table, and every other record of it is still there | hard | D |
| F6 | a stored requirement is about its source file - its content can be traced to the document | soft | S |

### 7.6 Limits

- A failure inside the store's chain is not resumable by a reset: the genesis is spent, and
  `requirements/manual/first` refuses a project that already owns a snapshot. The record is still in the queue, so
  a new run of the same batch writes a new project.
- A failure after the genesis leaves the STAGE open and uncommitted: the project's committed state is the genesis
  (requirement #1) alone, and the store's failure names the STAGE and the ids written into it.

### 7.7 Corrections

- **2026-09-18, 1.0 -> 1.1.** `cc` is cached: `cache on, cacheMeta`. MH keys an entry on the Function code, the
  SHA-256 and length of every input - here the prompt, which carries the description, the path and the whole file -
  and, with `cacheMeta`, on every meta of the process; the Function's git revision is not part of the key
  (`CacheUtils.getKey`). A re-run of a batch therefore pays CC only for files whose prompt changed or whose answer
  was never stored. An entry is written only when a Task of a cached process finishes OK
  (`TaskFinishingTxService.finishAsOk`), so a 1.0 run left nothing to reuse, and a failed `cc` Task leaves none.
- With the cache, a reset of `cc` answers from it (`CHECK_CACHE`, `ExecContextTaskResettingService`): an answer the
  `check` step refused comes back unchanged on a plain reset. Drop the entry first with the Task's reset-cache
  (`POST /exec-context/task-reset-cache`). A `cc` Task that failed left no entry, so a plain reset asks CC again.
- **2026-09-18, 1.0 -> 1.1.** `cc` runs `mh.asset.call-cc_1.1`: the same payload, plus an `analyzers` rule matching
  CC's session-limit message (`hit your ... limit`). On a hit the execution gate withholds call-cc for 30 minutes
  (scope `function`) and the Task's retry is free, so a spent CC session no longer uses up a branch's tries - in 1.0
  it failed the branch (Task #664, ExecContext #26). A new code rather than an edit of `mh.asset.call-cc`: the
  Dispatcher skips a Function code it already has without reading its descriptor again (`FunctionService`,
  `295.240`). Import the `call-cc` bundle before this one.
- **2026-09-19.** `cc` declares `model = "claude-opus-4-8"` and `effort = "medium"` - the DAHF development pairing
  (`DAHF-IMPLEMENTATION-AND-CONTINUOUS-IMPROVEMENT.md` 0.5), no longer left to the Processor host's CLI default.
  `mh.asset.call-cc` passes `--effort` when the process declares an `effort` meta (as it already did for `--model`).
  Both metas enter the cache key under `cacheMeta`.
- **2026-09-19 (revised).** model and effort are now OPTIONAL ExecContext-level input variables (`model?`,
  `effort?`), not literal metas - a property of the run, like `synthetic`. The `cc` process binds them with
  `variable-for-model`/`variable-for-effort`, and `mh.asset.call-cc` reads each optional input: unseeded or
  `mh.null-value` omits the flag (CC's default), any other value passes it. As inputs their content is hashed
  into the cache key. Seeding the DAHF 0.5 development pairing (opus 4.8 / medium) is done at launch, via
  `mh_create_exec_context_with_variables`, not in the SourceCode.
- **2026-09-19, 1.1 -> 1.2.** `dropRecord` is commented out: for now the batch record stays in the meta table after
  a run, so the same batch can be run again (1.0's ExecContext #26 finished without storing, leaving `batch-0004`
  in place). The graph ends at `store`. To consume the queue again, restore the process and bump the uid.
- **2026-09-19, store in one STAGE.** `mh.asset.rg-req-store-batch_1.0` no longer commits one snapshot per requirement:
  every such commit cloned the parent's ExecContext, so ExecContext #27 managed ~250 commits in 19 minutes, each
  slower than the last. Now #1 goes through `requirements/manual/first` (the genesis), ONE STAGE is opened from that
  snapshot, every other requirement is written into it over the same REST endpoint (a STAGE write commits nothing and
  answers a null `snapshotId`), and the STAGE is sealed once: two committed snapshots per batch. Opening and sealing
  exist only as RG MCP tools (`mhdg_rg_open_stage`, `mhdg_rg_seal_snapshot`), called through the payload's
  `mh_rg_mcp_client` over Streamable HTTP at `/rest/v1/legal/mcp`, with the same `RG_API_AUTH` Basic credential.
  Every stored rationale now ends with an empty line and `source: <the file>`, so the provenance travels with the
  requirement instead of living only in the run's `reqSources` output. Payload-only change: same Function code, same
  SourceCode (1.2); a new ExecContext picks it up by resolving `HEAD`.

---

## 8. mh-rg-requirements-from-batch-internal-1.0 - every file of a batch, stored inside RG

### 8.1 Purpose

Turn every file of one batch record into requirements held in one fresh RG project - the purpose of section 7 - with
the store done INSIDE RG: the internal Function `mhdg-rg.req-store-batch` (RG's `RgReqStoreBatch`) writes the whole
batch in one loop in the dispatcher, where `mh.asset.rg-req-store-batch_1.0` makes one HTTP request per requirement
with the `RG_API_AUTH` credential. It stands beside `mh-rg-requirements-from-batch-1.5`, which keeps working; neither
replaces the other, so this is a new uid rather than a version of 1.5.

### 8.2 The graph

Declaration order is execution order; everything after `split` waits for all of its branches. Processes 1-5 are 1.5's,
unchanged except that `model` and `effort` are required inputs (8.3).

| # | process | Function | contributes |
|---|---|---|---|
| 1 | `mkproject` | `mh.asset.rg-temp-project_1.1` | the project, as in section 2, with the run's model and effort recorded on it |
| 2 | `select` | internal `mh.meta-storage`, `select` | `batchRecords` - the `batchKey` record of `metaTable`; cached |
| 3 | `paths` | `mh.asset.rg-batch-paths_1.0` | `batchPaths`, as in 7.2; cached |
| 4 | `split` | internal `mh.batch-line-splitter` | one branch per path, the path in `sourcePath` |
| 4.1 | `prompt` | `mh.asset.rg-req-path-prompt_1.0` | the file and the prompt, as in 7.2 |
| 4.2 | `cc` | `mh.asset.call-cc_1.1` | CC's answer, at the run's `model` / `effort`; `tries 2`; `cache on, cacheMeta` |
| 4.3 | `check` | `mh.asset.rg-req-check_1.0` | `reqAnswer` - one line of ASCII JSON `{sourcePath, requirements}` |
| 5 | `gather` | internal `mh.aggregate`, `text` | `reqAnswers` - every branch's `reqAnswer`, joined with a blank line (`AggregateFunction`, `"\n\n"`); a nullified one is skipped |
| 6 | `store` | internal `mhdg-rg.req-store-batch` | the requirements as TWO committed snapshots: #1 through the project's genesis (`RgFirstManualRequirementService`, which waits for the genesis ExecContext to commit), every other one written into ONE STAGE forked from that snapshot (`RgPleAuthoringService.openStage`, `RgRequirementExtendedService.addManualDerivedRequirement`), the STAGE sealed once (`sealSnapshot`); every rationale ends with an empty line and `source: <file>`; `reqIds`, `reqSources` |

There is no `dropRecord`: the record stays in the table, as in 1.5.

**Why the store is not in the branches** and **every file or nothing** hold unchanged - see 7.2. The coverage check
(one answer per path, none outside the batch, each requirement with at least 3 words of content - RG's own count - and
a rationale) runs inside the internal Function before RG is called, and both outputs are resolved before it too, so a
refused batch touches nothing.

### 8.3 Run-data contract

Launch with `mh_create_exec_context_with_variables`. Every input below must be passed; a nullable one takes JSON `null`.

| variable | direction | meaning | example |
|---|---|---|---|
| `rgBaseUrl` | in | the RG the project is created in - `mkproject` only; the store runs inside RG and uses no URL | `http://localhost:64967` |
| `locale`, `projectDescription`, `rgPipelineUid`, `metaTable` | in | as in section 3 | |
| `batchKey` | in | the record to process; it is only read | `batch-0005` |
| `synthetic` | in | the table the record is read from: `true` synthetic, `false` production | `true` |
| `production` | in, nullable (`production?`) | gates nothing here - the project is created in every run (`create-in-development`). Only an exact `true` is production; `null` or anything else is a development run | `null` |
| `model` | in, REQUIRED | the model CC uses, recorded on the project, the genesis snapshot and the STAGE. DAHF 0.5: `claude-opus-4-8` unless the run pins another | `claude-opus-4-8` |
| `effort` | in, REQUIRED | the effort CC uses (`low`/`medium`/`high`/`extra`/`max`), recorded as `model` is | `medium` |
| `projectCode` | out | the project's code | `TMP...` |
| `reqIds` | out | the stored requirements' ids, one per line, in storing order | |
| `reqSources` | out | one line per stored requirement: its id, a TAB, the file it came from | |

**Credential:** the vault entry `RG_API_AUTH`, declared by `mh.asset.rg-temp-project_1.1` only. The store has none.

❗ **Company.** `mkproject` creates the project as the `RG_API_AUTH` account, so the project belongs to that account's
company. The internal store writes as the company of the ExecContext (`RgSystemUserContext`) and RG looks the project up
within it. Launch the SourceCode in the company `RG_API_AUTH` belongs to; otherwise the store fails before writing
anything - `04.984.010`, carrying RG's `04.876.010` (project not found).

### 8.4 Durable side effects

- One RG project per run, development runs included: its description, the pipeline, `isReady`, the run's model/effort.
- Its genesis run (an RG ExecContext) and TWO committed snapshots: the genesis (requirement #1) and the sealed STAGE
  holding every other requirement - ONE snapshot when the batch held a single requirement.
- Nothing is written to meta storage; the batch record is only read.

### 8.5 Fitness criteria

| id | criterion | hardness | type |
|---|---|---|---|
| F1 | the reported `projectCode` names a project RG lists, with the given description | hard | D |
| F2 | every id in `reqIds` is a requirement of that project, as many as the answers held | hard | D |
| F3 | the project owns exactly two COMMITTED snapshots (one for a single-requirement batch), the second a child of the first - no fork | hard | D |
| F4 | every path of the record appears in `reqSources`, and no other path does | hard | D |
| F5 | a stored requirement's text carries its CC content and ends its rationale with `source: <file>`, the file `reqSources` pairs with its id | hard | D |
| F6 | a stored requirement is about its source file - its content can be traced to the document | soft | S |

### 8.6 Limits

- A failure inside the store after the genesis is not resumable by a reset, as in 7.6: the genesis is spent, and the
  genesis call refuses a project that already owns a snapshot. The store's failure says what is committed and names
  the STAGE and the ids written into it; a new run of the same batch writes a new project.
- A failed store Task goes to `ERROR_WITH_RECOVERY` and, having no `tries`, is finished `ERROR` by the dispatcher's
  recovery pass - a refused batch is refused the same way again.
- The genesis wait is RG's own bound (`RgPleAuthoringService.awaitGenesisCommitted`) - the same one the HTTP route
  of 1.5 reaches through `requirements/manual/first`.

### 8.7 Corrections

- **2026-09-24, created** beside 1.5 rather than as its next version, so both stay live. Three differences from 1.5:
  `store` is the internal `mhdg-rg.req-store-batch` (same metas minus `variable-for-rg-base-url`, `rgBaseUrl` no
  longer one of its inputs); `production` is nullable (`production?`), which `mh.asset.rg-temp-project_1.1` reads as a
  development run; `model` and `effort` are REQUIRED - the optional form 1.5 uses is retired for these two inputs
  (`DAHF-IMPLEMENTATION-AND-CONTINUOUS-IMPROVEMENT.md` 0.5). The store was verified against a real `rg-req-check`
  answer (a Derby `ContextImpl.java` answer of five requirements) in RG's `RgReqStoreBatchTest`, commit `e185ce7a`.
- **2026-09-24, first development run - ExecContext #313, FINISHED, 13 of 13 Tasks OK, no retries (~2.3 min).**
  Synthetic input only: the record `batch-synthetic-0001` of `mh.asset.rg-req-batch-synthetic` in
  `MH_META_STORAGE_SYNTHETIC` (registered first, registry id 3), listing the two files of `synthetic/corpus/`;
  `production` null, `synthetic` true, `claude-opus-4-8` / `medium`, `rgPipelineUid` `mhdg-rg-cc-1.0.80`. Observed:
  project `TMP7K82YBKM`, which RG lists (project 24, ready) with exactly the launched description (F1); `reqIds`
  `-1..-10`; `reqSources` `-1..-5` -> `SyntheticRateLimiter.java`, `-6..-10` ->
  `SyntheticRetryPolicy.java` (F4); RG lists the same ten ids (F2); two COMMITTED snapshots, #288 the genesis by
  `pipeline-run`, #289 the sealed STAGE by `system-rg`, parent #288, both recording opus 4.8 / medium (F3); `-8` read
  in full at #289 - CC's content, rationale ending `source: ...SyntheticRetryPolicy.java` (F5), traceable to
  `delayBefore` (F6). The company rule of 8.3 held: the store found the project `mkproject` created, both company 2.
  The one difference from 1.5 visible in RG: the STAGE is signed `system-rg` instead of the `RG_API_AUTH` account.
- **2026-09-24, first production run - ExecContext #316, FINISHED in 989 s, store Task OK.** Inputs as ExecContext #310
  (a 1.5 run of the same batch) except `production` = `true`, `claude-sonnet-4-6` / `medium`, `locale` `en`:
  `batch-0005` of `mh.asset.dir-batch-for-requirements.2`, read with `synthetic` = `true` (where the record lives -
  `synthetic` is an input of its own here, not derived from `production`), 100 Derby files, `rgPipelineUid`
  `mhdg-rg-cc-1.0.80`. Observed: project `TMP2TH95BNR` (project 25, ready, the launched description - F1); `reqIds`
  `-1..-491` contiguous, and RG lists exactly those 491 (F2); two COMMITTED snapshots, #290 the genesis and #291 the
  sealed STAGE with parent #290, both `claude-sonnet-4-6` / `medium` (F3); `reqSources` pairs id and file in batch
  order, starting at `ClassMember.java` (F4, spot-checked); `-250` read in full at #291 - CC's content, rationale
  ending with the `source:` line of `FormatableProperties.java` (F5). F6 not checked: the Derby sources lie outside
  the directory the executor may read. Timing: the store Task took 394.6 s, the STAGE was open 368.1 s - #310's HTTP
  store kept its STAGE open 1437 s for the same batch (x3.9). Profiling events show the per-requirement RG work is
  nearly equal on both paths (~0.73 s vs ~0.76 s); the gain is the ~2.1 s per requirement #310 spent between
  creations, outside RG's add.

## 9. mh-rg-requirements-from-batch-parallel-1.0 - each file stored in its own branch

### 9.1 Purpose

The purpose of section 8, with the store moved into the fan-out: each branch stores ITS file's requirements right
after `check`, so storing runs in parallel with the other branches instead of waiting for all of them. A changed flow,
so a new uid beside internal-1.0, which is left as it is and keeps working.

### 9.2 The graph

internal-1.0's graph (8.2) with two changes, and nothing else - proven by comparing the two files line by line,
comments and blank lines aside:

- `gather` (internal `mh.aggregate`) and the top-level `store` are removed.
- `store` (internal `mhdg-rg.req-store-batch`, the same metas) runs inside `split`'s sequential block after `check`,
  bound to the branch's own Variables: `variable-for-paths = "sourcePath"` (the branch's one path) and
  `variable-for-answers = "reqAnswer"` (the branch's one answer). The Function's coverage check then covers that one
  file.

### 9.3 Run-data contract

The inputs of 8.3, unchanged. Outputs:

| variable | direction | meaning |
|---|---|---|
| `projectCode` | out, ExecContext | the project's code |
| `reqIds` | out, per branch | the ids of that branch's file's requirements, one per line |
| `reqSources` | out, per branch | one line per requirement of that file: its id, a TAB, the file |

With no `gather` there is no ExecContext-level `reqIds` / `reqSources`.

### 9.4 Durable side effects

As 8.4: one RG project per run and what the stores commit into it; nothing is written to meta storage.

### 9.5 Fitness criteria

| id | criterion | hardness | type |
|---|---|---|---|
| P1 | the reported `projectCode` names a project RG lists, with the given description | hard | D |
| P2 | every branch's `store` Task is OK, and every path of the record is some branch's `reqSources` file | hard | D |
| P3 | every id in the branches' `reqIds` is a requirement of that project, as many as the answers held | hard | D |
| P4 | the project's COMMITTED snapshots form one chain - no fork | hard | D |
| P5 | a stored requirement's text carries its CC content and ends its rationale with `source: <file>` | hard | D |

### 9.6 Corrections

- 2026-09-30, ExecContext #8 (SourceCode #18, `batch-0004` of `mh.asset.dir-batch-for-requirements.2`, synthetic,
  claude-sonnet-4-6 / medium, project `TMPP6XH6FH1`): FAILED, stopped. The first branch's `store` ran the project's
  genesis; every later branch's `store` was refused by RG with `04.876.020 ERROR: Project TMPP6XH6FH1 already owns 1
  snapshot(s), so it is not a just-created project` (surfaced as `04.985.050` / `04.984.010`, e.g. Task #4679):
  `mhdg-rg.req-store-batch` spends the project's one-shot genesis on requirement #1 of EVERY call, so it can run once per
  project, not once per branch. 13 branch `store` Tasks had failed by 09:53:11 when the ExecContext was stopped.
- 2026-09-30, repair (DAHF 0.17 -> 4.3-4.5). SourceCode #18 archived (DAHF 0.3). Criterion added, and promoted into the
  graph of section 10: **a store step that runs once per branch writes into a STAGE that is already open, and never
  spends the genesis - the genesis STAGE is opened ONCE, before the fan-out**. RG's own refusal named the shape: open a
  STAGE, write into it. Its in-graph form is RG's own cascade - `mhdg-rg.open-stage`, `mhdg-rg.store-req`,
  `mhdg-rg.post-processing` - which section 10 uses.

## 10. mh-rg-requirements-from-batch-cascade-1.0 - every requirement stored in its own branch, RG's cascade

### 10.1 Purpose

The purpose of section 8, with every requirement stored in parallel: each file's branch turns its checked answer into
one line per requirement, and each requirement is stored in a branch of its own, into ONE STAGE opened once before the
fan-out and committed once after it. It is the repair of section 9 (9.6) and a changed flow, so a new uid beside
internal-1.0.

### 10.2 The graph

Processes 1-3 (`mkproject`, `select`, `paths`) and the branch's `prompt`, `cc`, `check` are internal-1.0's (8.2),
unchanged. `gather` and `store` are gone. New:

| # | process | Function | contributes |
|---|---|---|---|
| 4 | `genesis` | internal `mh.evaluation` | `parentSnapshotId` = the TEXT `null` (SpEL `'null'`) - the explicit genesis fork point `open-stage` requires (a bare `null` would nullify the Variable, refused `844.022`) |
| 5 | `open` | internal `mhdg-rg.open-stage` | the project's genesis STAGE, recorded with THIS ExecContext, and a `PIPELINE_RUN` event; stamps the STAGE with `model` / `effort`; `stageSnapshotId`, `triggerEventId` |
| 6.4 | `lines` | `mh.asset.rg-req-lines_1.0` | `reqLines` - the branch's answer as one `{name, content, rationale}` JSON line per requirement, the fields `RequirementLine` reads |
| 6.5 | `reqs` | internal `mh.batch-line-splitter` | one branch per requirement, the line in `reqJson` |
| 6.5.1 | `store` | internal `mhdg-rg.store-req` | the requirement written into the STAGE (`createRequirement`, then its revision prepared and activated); `requirementId` |
| 7 | `commit` | internal `mhdg-rg.post-processing`, `tag terminal` | the STAGE committed and the event completed - or, if any Task of the ExecContext ended in `ERROR`, the STAGE marked FAILED (fail-closed) |

`open-stage`, `store-req` and `post-processing` read `projectCode`, `parentSnapshotId`, `stageSnapshotId` and
`triggerEventId` by those exact names.

### 10.3 Run-data contract

The inputs of 8.3, unchanged. Outputs: `projectCode` at ExecContext level; `requirementId` per requirement branch.
There is no ExecContext-level `reqIds` / `reqSources`.

### 10.4 Durable side effects

- One RG project per run, as in 8.4.
- ONE committed snapshot: the genesis STAGE, holding every requirement - opened and committed by THIS ExecContext,
  which RG records as the project's pipeline run, with its `PIPELINE_RUN` event. The project's bound genesis pipeline
  (`rgPipelineUid`) is not run.
- Nothing is written to meta storage.

### 10.5 Fitness criteria

| id | criterion | hardness | type |
|---|---|---|---|
| C1 | the reported `projectCode` names a project RG lists, with the given description | hard | D |
| C2 | every `store` Task is OK, and every path of the record had a branch whose `store` Tasks ran | hard | D |
| C3 | the project owns exactly ONE COMMITTED snapshot, holding as many requirements as the answers held | hard | D |
| C4 | a stored requirement carries its CC content | hard | D |
| C5 | a stored requirement is about its source file | soft | S |

### 10.6 Limits

- The requirement text carries no `source: <file>` line: `store-req` composes its four items with one line each and
  numbers them by counting, so an extra line would be numbered as the next item. The file of a requirement is the
  `sourcePath` of the branch whose `store` Task wrote its `requirementId`.
- The project's pipeline run is this batch ExecContext. What a later RG operation that clones the pipeline run (an
  objection) does with it is not established.

### 10.7 Corrections

- 2026-09-30, ExecContext #11 (SourceCode #19, `batch-0004` of `mh.asset.dir-batch-for-requirements.2`, synthetic,
  claude-sonnet-4-6 / medium, project `TMPVG956AFJ`): stopped. The repair of 9.6 held - `open-stage` opened genesis
  STAGE 7 41.5 s after the start, stamped with the run's pair, and no branch touched the genesis. Then `store-req`
  failed: 22 Tasks by 10:17:22, in bursts, each with `977.060 ... Could not open JPA EntityManager for transaction`
  after 30.1 s (Task #5640: 1790788507269 -> 1790788537380) - a DB-connection acquisition timeout. Up to 20
  `store-req` run at once (`internalFunctionMaxConcurrency` 20); the repo's dispatcher config sets no pool size, i.e.
  HikariCP's default of 10 connections and 30 s. 46 requirements were visible 231 s after the STAGE opened, the
  numbering with gaps (-1, -17, -27, -44, -50, -51), so a `tries` retry could write a requirement twice - none was
  added. Stopped as a hot-spin (DAHF 0.17 -> pause); nothing in the graph sets the dispatcher's concurrency or pool.
  Criterion added: **C6 (hard, D) - no `store-req` Task fails on a DB-connection timeout; a run that shows one is not
  a valid result and not a benchmark.** Limit added: the parallel store needs a dispatcher whose DB pool covers its
  internal-function concurrency.
## 11. mh-rg-requirements-from-batch-staged-1.3 - requirement #1 as the genesis, the others in parallel into one STAGE

### 11.1 Purpose

The purpose of section 8, with the store split in two: requirement #1 of the batch's first file through the project's
genesis (`mhdg-rg.req-store-batch`, handed one file and one requirement), and every other requirement written in
parallel, one branch each, into ONE STAGE forked from the genesis and committed once. An experiment beside
cascade-1.0 (section 10), which opens a genesis STAGE instead; a changed flow, so a new uid.

### 11.2 The graph

internal-1.0's processes 1-5 (8.2), `gather` included, unchanged. Then:

| # | process | Function | contributes |
|---|---|---|---|
| 6 | `first` | `mh.asset.rg-req-first_1.0` | the batch store's own `plan` over the collected answers (every file or nothing), split into `firstPath` + `firstAnswer` (requirement #1 alone, one answer line), `otherReqs` (every other requirement, one `{name, content, rationale}` line each, batch order) and `hasFirstReq` |
| 7 | `insert` | internal `mh.nop`, `when hasFirstReq ? true : false` (the bare Variable - 11.6) | holds 7.1-7.5 in order |
| 7.1 | `genesis` | internal `mhdg-rg.req-store-batch` | requirement #1 as the project's genesis - one committed snapshot, no STAGE; `firstReqIds`, `firstReqSources` |
| 7.2 | `parent` | `mh.asset.rg-genesis-snapshot_1.0` | `parentSnapshotId` - the id of the project's one COMMITTED parentless snapshot, read over MCP `mhdg_rg_list_snapshots`; anything else refused |
| 7.3 | `open` | internal `mhdg-rg.open-stage` | ONE STAGE forked from the genesis; `stageSnapshotId`, `triggerEventId` |
| 7.4 | `reqs` / `store` | internal `mh.batch-line-splitter` / `mhdg-rg.store-req` | every other requirement written into the STAGE, one branch each |
| 7.5 | `close` | internal `mhdg-rg.post-processing`, `tag terminal` | the STAGE committed - or marked FAILED if any Task of the ExecContext ended in `ERROR` |

### 11.3 Run-data contract

The inputs of 8.3, except that `effort` is NULLABLE (`effort?`, since 1.2): null for a model that takes no effort -
`claude-haiku-4-5-20251001` (`RgLlmModel.takesEffort` false) - with which cc passes no `--effort` and RG records the
model with a null effort. `model` stays required. Output: `projectCode`. **Credential:** `RG_API_AUTH`, declared by
`mh.asset.rg-temp-project_1.1` and `mh.asset.rg-genesis-snapshot_1.0`.

### 11.4 Durable side effects

One RG project per run; TWO committed snapshots - the genesis (requirement #1) and the STAGE holding every other
requirement, opened and committed by this ExecContext. Nothing written to meta storage.

### 11.5 Fitness criteria

| id | criterion | hardness | type |
|---|---|---|---|
| S1 | the reported `projectCode` names a project RG lists, with the given description | hard | D |
| S2 | every `store` Task is OK, and none failed on a DB-connection timeout (C6) | hard | D |
| S3 | the project owns exactly TWO COMMITTED snapshots, the second a child of the first, holding as many requirements as the answers held | hard | D |
| S4 | a stored requirement carries its CC content | hard | D |

### 11.6 Corrections

- 2026-09-30, ExecContext #12 (staged-1.0, SourceCode #20, `batch-0004`, synthetic, claude-sonnet-4-6 / medium,
  project `TMPY1RO4KWF`): the fan-out, `gather` and `first` ran OK - `first` split 495 requirements into #1 (from
  `...\authentication\UserAuthenticator.java`) and 494 others. The `insert` gate (Task #5727) then failed in 1 s with
  `509.300 not supported type: class java.lang.String`: `when hasFirstReq == "true"` compares a Variable holding true
  with a STRING, and MH's comparator (`EvaluateExpressionLanguage.getTypeComparator`) treats such a Variable as a
  boolean and refuses the string operand (`getValueBoolean`). Nothing was stored. `== true` is no repair: the grammar
  refuses a boolean literal as a comparison operand (import `564.200`, line 183:28). Repaired in 1.1 with the bare
  Variable, `when hasFirstReq ? true : false` - the form RG's own pipeline gates with; 1.0 archived (MH-GIT-DELIVERY 1.6). Promoted (DAHF 4.4): the test
  `tests/test_mhsc_when_clauses.py` refuses any `.mhsc` of this capability whose `when` compares with `"true"` /
  `"false"`.
- 2026-09-30, 1.2: `effort` made nullable on the ExecContext and on `mkproject`, `cc` and `genesis`, for a run on Haiku
  with a null effort - which MH refuses for an input not declared nullable (`01.562.124`, `ExecContextCreatorService`).
  The flow is unchanged. 1.1 (SourceCode #21) archived (MH-GIT-DELIVERY 1.6); it stopped nothing - ExecContext #13, 1.1's
  `batch-0004` run, was no longer on the Dispatcher (not found).
- 2026-09-30, ExecContext #14 (staged-1.2, SourceCode #32, SYNTHETIC record `synthetic-0001` of
  `mh.asset.dir-batch-for-requirements.synthetic` - the two files of `synthetic/corpus` - model
  `claude-haiku-4-5-20251001`, effort null, `rgPipelineUid` `mhdg-rg-cc-1.0.80`, project `TMPXIK2WWW6`): FINISHED in 196.2 s,
  STAGE FAILED. Haiku with a null effort ran through `mkproject`, `cc` and the genesis, and both snapshots record the
  model with a null effort. The genesis (snapshot 8) committed in 23.4 s; `parent` and `open-stage` forked STAGE 10 from
  it. Of the ~8 `store-req` Tasks, 2 (#6428, #6440) failed after 31.2 s with `977.060 ... Could not open JPA
  EntityManager for transaction`, and `post-processing` marked STAGE 10 FAILED (`822.055 Pipeline run had 2 errored
  task(s)`). S2 / C6 violated. NOT a run alone: ExecContext #15 - the same SourceCode on a second record, launched with it and
  stopped later - wrote at the same moment (its store-req Tasks #6429-#6443 interleave with #14's #6428-#6442) and ended
  with 5 store-req Tasks in ERROR, not examined. So ~16 parallel writes, not hundreds (10.7), already starve the
  dispatcher's DB pool; the parallel store needs a pool sized for it.
- 2026-09-30, ExecContext #18 (staged-1.2, `synthetic-0001` ALONE, Haiku / null effort, `mhdg-rg-cc-1.0.80`, project
  `TMPB3XCT19I`): every Task OK. Genesis snapshot 12 committed in 22.1 s; STAGE 13 forked from it and COMMITTED 3.0 s
  after it opened, with the ~8 `store-req` Tasks of the batch in parallel. S1-S3 hold. The same flow on the same record
  failed in #14 only while #15 wrote beside it: the dispatcher's log of that window shows `HikariPool-1 - Connection is
  not available, request timed out after 30012ms (total=10, active=10, idle=0, waiting=9)` - a pool of 10 against ~18
  parallel `store-req` (and up to 20 internal-function permits) - and in the same 30 s the Processor's `srv-v2` and
  `keep-alive` requests timed out too; those are retried, `store-req` is not.
- 2026-09-30, ExecContexts #20 and #21 (staged-1.2, `synthetic-0001` and `synthetic-0002` launched together, Haiku /
  null effort, `mhdg-rg-cc-1.0.80`) after the dispatcher's `spring.datasource.hikari.maximum-pool-size` was raised from
  10 to 100: both FINISHED, every Task OK, their `store-req` Tasks interleaved (#6589-#6605). Projects `TMPTO3MNA4F`
  and `TMPZPXFHAYD`: genesis snapshots 14 / 15 committed in 23.3 s / 23.4 s; STAGEs 16 / 17 opened 8 ms apart and
  COMMITTED 4.08 s after opening, each. The scenario #14 + #15 failed on (10.7, 11.6) passes with the pool of 100 -
  S1-S3 hold for both.
- 2026-09-30, ExecContext #24 - the benchmark (staged-1.2, `batch-0004` of `mh.asset.dir-batch-for-requirements.2`,
  synthetic, `claude-haiku-4-5-20251001` / null effort, `mhdg-rg-cc-1.0.80`, DB pool 100, project `TMPSROT3N5I`):
  FINISHED in 723.4 s, every Task OK. 464 requirements (Haiku; Sonnet made 495 from the same batch). Fan-out of 100
  files with UNCACHED CC to the end of `gather`: 630.0 s. `first` 9.9 s. Genesis snapshot 18 committed in 22.3 s; its
  commit to STAGE 19 open (`req-store-batch` returning, `parent` over MCP, `open-stage`): 23.2 s. STAGE 19, 463
  requirements written by parallel `store-req`, opened -> COMMITTED in **31.07 s = 0.067 s per requirement (~14.9/s)**.
  Store phase, genesis opened -> STAGE committed: 76.6 s. Against internal-1.0 on the same build (ExecContext #5, 8.7:
  STAGE 54.9 s for 495 = 0.111 s per requirement, store phase 78.5 s): the STAGE writes are 1.66x faster per
  requirement, the whole store phase is level - the parallel writes win back what the second top-level round trip
  (`parent` + `open-stage`, 23.2 s) costs.
  The 23.2 s from the genesis commit to the STAGE opening, split: 2.6 s until `parent` (Task #6915) was assigned,
  20.5 s for `parent` itself (1790805254980 -> 1790805275484; `first`, an external Task without a network call, took 9.9 s),
  90 ms for `open-stage`. `parent` exists only because `mhdg-rg.req-store-batch` does not output the genesis snapshot id.
- 2026-09-30, DEFECT - wrong requirement type; staged-1.2 (SourceCode #32) and cascade-1.0 (SourceCode #19, section 10)
  archived (DAHF 0.3). `mhdg-rg.store-req` is RG's decomposition write: it creates DECOMPOSED requirements
  (`RgEnums` `DECOMPOSED(0)`; the dispatcher log of #14/#15 reads `075.240 Requirement created: TMPXIK2WWW6-2
  type=DECOMPOSED`). This capability stores MANUAL requirements, DERIVED (`DERIVED(1)`) - what `req-store-batch`
  writes. Checked on #24's project `TMPSROT3N5I`: `-1` (the genesis, through `req-store-batch`) reqType 1 = DERIVED,
  `-2` (through `store-req`) reqType 0 = DECOMPOSED - so #24 stored 1 DERIVED and 463 DECOMPOSED requirements. #24's
  benchmark therefore compares two different write paths: the 0.067 s vs 0.111 s per requirement is DECOMPOSED writes
  in parallel against DERIVED writes in one Task, and is NOT a measure of what parallelism buys the manual store.
  Criterion added for every variant of this capability: **every stored requirement is DERIVED (reqType 1), the type
  internal-1.0 stores.**
- 2026-09-30, CORRECTION of the entry above and REPAIR - staged-1.3. `store-req` writes the type its line names: its
  `RequirementLine.type` reads ABSENT as DECOMPOSED, and RG's own manual path sets it to DERIVED
  (`RgStoreReq.authoredRequirementLine`). The DECOMPOSED requirements were a defect of this capability's own Function:
  `mh.asset.rg-req-first_1.0` wrote its other-reqs lines without `type`. Fixed in its payload - every line now carries
  `"type": "DERIVED"`, pinned by `tests/test_mh_rg_req_first.py` - and the graph relaunched as staged-1.3 (1.2 was
  archived; the graph is unchanged). The claim above that only `req-store-batch` writes DERIVED requirements was
  wrong and is withdrawn. cascade-1.0 stays archived: its genesis is `open-stage`'s empty genesis STAGE, not a manual one.
- 2026-09-30, ExecContext #27 - staged-1.3 (SourceCode #33) on `batch-0004`, Haiku / null effort, DB pool 100, project
  `TMPSCXVYV3U`: FINISHED in 337.7 s, both snapshots COMMITTED. 458 requirements, ALL DERIVED - checked `-2` (the first
  written into the STAGE) and `-458` (the last): reqType 1. Fan-out to the end of `gather` 252.3 s (CC from the cache);
  `first` 11.4 s; genesis snapshot 20 in 22.3 s; genesis commit -> STAGE 21 open 17.25 s (`parent`); STAGE 21, 457
  DERIVED requirements by parallel `store-req`, open -> COMMITTED **27.87 s = 0.061 s per requirement (~16.4/s)**; store
  phase (genesis open -> STAGE commit) 67.4 s. Against internal-1.0 (ExecContext #5, 8.7 - DERIVED too, one Task, 495
  requirements): STAGE 54.9 s = 0.111 s per requirement, store phase 78.5 s. Same requirement type now: the parallel
  STAGE writes are 1.82x faster per requirement and the store phase 14% shorter; `parent` (17.25 s) is what keeps the
  gap from being wider (follow-up: `req-store-batch` does not output the genesis snapshot id).

## 12. mh-rg-requirements-from-batch-stage-first-1.0 - ONE STAGE opened on the empty project, stored from every branch

### 12.1 Purpose - the business frame

- **Objective.** A batch's requirements go into a fresh RG project with NO requirement singled out as the first: the
  STAGE is opened while the project is still empty, each file's requirements are stored from that file's own branch
  right after its answer is checked, and the STAGE is committed once. staged-1.3 (section 11) needed requirement #1
  as the project's genesis before any STAGE could be forked; RG now commits an EMPTY genesis, which removes that split.
  A changed flow, so a new uid beside internal-1.0 and staged-1.3, both left as they are.
- **Success criteria.** A FINISHED run on `batch-0004` of `mh.asset.dir-batch-for-requirements.2` (synthetic store)
  that meets 12.5 G1-G5. Measured beside it, under the same model / effort as the baseline: the whole run, and the
  store's tail - from the last `check` Task OK to the STAGE COMMITTED - beside staged-1.3's ExecContext #27 (Haiku /
  null effort: `gather` end -> STAGE commit = `first` 11.4 s + store phase 67.4 s) and internal-1.0's #5 (store phase
  78.5 s).
- **Invariants.** internal-1.0 and staged-1.3 live and unchanged; the same inputs; one project per run; every file of
  the batch stored; every stored requirement DERIVED; nothing written to meta storage.
- **Done.** The run's observed values beside the baseline's, recorded in 12.6 and reported.

### 12.2 The graph

internal-1.0's graph (8.2) with these changes and nothing else - proven by comparing the two files line by line,
comments and blank lines aside: `gather` and the top-level `store` are gone, so are the ExecContext-level outputs
`reqIds` / `reqSources`; `effort` is nullable (`effort?`, as in 11.3); and:

| # | process | Function | contributes |
|---|---|---|---|
| 2 | `open` | `mh.asset.rg-open-stage_1.0` | RG's MCP `mhdg_rg_open_stage` WITHOUT `parentSnapshotId`: RG (`RgPleAuthoringService.openStage`) runs the project's own genesis pipeline with no requirement, waits for it to commit (its own bound, `04.689.068`), and forks ONE STAGE from it with a copy of the genesis ExecContext; `stageSnapshotId`, `genesisSnapshotId` |
| 5.4 | `lines` | `mh.asset.rg-req-lines_1.0` | `reqLines` - the file's checked answer as one `{name, content, rationale, type: DERIVED}` line per requirement |
| 5.5 | `reqs` | internal `mh.batch-line-splitter` | one branch per requirement, the line in `reqJson` |
| 5.5.1 | `store` | internal `mhdg-rg.store-req` | the requirement written into the STAGE, which it reads by the name `stageSnapshotId`; `requirementId` |
| 6 | `close` | internal `mhdg-rg.post-processing`, `tag terminal` | the STAGE committed - or marked FAILED if any Task of the ExecContext ended in `ERROR` (fail-closed: every file or nothing). Its `triggerEventId` is optional and absent here |

**Why `open` comes second.** It is the step the whole flow depends on and the only one that can fail on the deployed
RG itself (an RG that cannot commit an empty genesis gives up after its own bound). Placed before `select`, it stops a
run before any CC call is made.

**Why the store is in the branches now.** 7.2's reason - parallel writes would fork the project, and only one branch
could run the one-shot genesis - no longer applies: the genesis is spent once, by `open`, before the fan-out, and every
branch writes into the one STAGE it opened; no branch commits anything.

**E3's graph (`mh-rg-requirements-from-batch-stage-store-1.0`).** The table above with 5.4-5.5.1 replaced by ONE
process - internal-1.0's `store` moved into the branch after `check`:

| # | process | Function | contributes |
|---|---|---|---|
| 5.4 | `store` | `mh.asset.rg-req-store-stage_1.0` | the branch's file (`sourcePath`) and answer (`reqAnswer`) checked for coverage, then every requirement of the file written into the STAGE named by `stageSnapshotId` through RG's `requirements/manual` (`addManualDerivedRequirement`, STAGE mode - DERIVED, commits nothing); every rationale ends with `source: <file>`; `reqIds`, `reqSources` per branch |

### 12.3 Run-data contract

The inputs of 8.3, except that `effort` is NULLABLE (`effort?`, as in 11.3) - null only for a model that takes none.
Output: `projectCode` at ExecContext level; `requirementId` per requirement branch; `stageSnapshotId` and
`genesisSnapshotId` at the top level of the ExecContext. There is no ExecContext-level `reqIds` / `reqSources`: the file
of a requirement is the `sourcePath` of the branch whose `store` Task wrote its `requirementId`.

**Credential:** `RG_API_AUTH`, declared by `mh.asset.rg-temp-project_1.1` and `mh.asset.rg-open-stage_1.0`. Launch in
the company of the `RG_API_AUTH` account (8.3).

### 12.4 Durable side effects

- One RG project per run, development runs included, as in 8.4.
- Its genesis run - RG's own pipeline ExecContext, with no requirement - and TWO committed snapshots: the empty
  genesis, and the STAGE forked from it holding every requirement.
- If the run fails after `open`, the empty genesis stays COMMITTED and the STAGE is marked FAILED by `close`; the
  project holds no requirement.
- Nothing is written to meta storage; the batch record is only read.

### 12.5 Fitness criteria

| id | criterion | hardness | type |
|---|---|---|---|
| G1 | the reported `projectCode` names a project RG lists, with the given description | hard | D |
| G2 | every `store` Task is OK, none failed on a DB-connection timeout (C6), and every path of the record had a branch whose `store` Tasks ran | hard | D |
| G3 | the project owns exactly TWO COMMITTED snapshots: the parentless genesis holding NO requirement, and the STAGE, its child, holding every requirement - as many as the branches' `reqLines` held | hard | D |
| G4 | every stored requirement is DERIVED (reqType 1), the type internal-1.0 stores (11.6) | hard | D |
| G5 | a stored requirement carries its CC content | hard | D |
| G6 | a stored requirement is about its source file - its content can be traced to the document | soft | S |

### 12.6 Corrections

- **2026-10-01, created.** `mh.asset.rg-req-lines_1.0` (written for cascade-1.0, section 10) wrote its lines WITHOUT
  `type`, so `store-req` would have stored them DECOMPOSED - the defect 11.6 found in `rg-req-first_1.0`. Fixed in its
  payload the same way: every line now carries `"type": "DERIVED"` (the value `rg-req-first_1.0` defines), pinned by
  `tests/test_mh_rg_req_lines.py` (Characterization Test: the old key set pinned green, flipped red, payload fixed,
  all 172 tests of the capability green). cascade-1.0 is archived and is not relaunched by this change.
- **2026-10-01, ExecContext #29 - a wrong run input, not a flow defect.** Launched with `rgPipelineUid`
  `mhdg-rg-cc-1.0.80`, the pipeline of ExecContext #27. `mkproject` created `TMP2A51G0CU` and then refused to bind
  the pipeline: RG offers a project only the LATEST version per pipeline name (`RgExecService.getAvailableSourceCodes`),
  and `mhdg-rg-cc-1.0.81` is registered now. The project stays not ready, nothing else ran. Rule for every launch of
  this capability: `rgPipelineUid` is the latest `mhdg-rg-cc-*` the dispatcher lists. The pipeline runs only inside
  `open` (the empty genesis), so it does not touch what the store comparison measures.
- **2026-10-01, E3 measured - ExecContext #39** (`batch-0004`, Haiku / null effort, `mhdg-rg-cc-1.0.81`, CC uncached
  - every push changes the cache key -, DB pool 100, no other ExecContext running; project `TMPTZZ8MMVC`):

  | measure | E3 stage-store-1.0, #39 | staged-1.2, #24 (uncached) | staged-1.3, #27 (CC cached) |
  |---|---|---|---|
  | whole run | 917.7 s | 723.4 s | 337.7 s |
  | `open`: empty genesis committed + STAGE forked | 29.0 s (genesis 28 committed 10.2 s after creation) | - | - |
  | first store starts | 179.7 s after the run starts, while CC still runs for other files | after `gather` (630 s fan-out) | after `gather` |
  | after the last store starts (store + `close` + finish) | 29.9 s | `first` + STAGE store | `first` 11.4 s + store phase 67.4 s |
  | one store Task (3 sampled: first, middle, last branch) | 24.8 s / 23.4 s / 26.3 s for 5 requirements each, ~5 s per write | - | - |
  | requirements | 469, ids -1..-469 with no gap, all in STAGE 29 | - | 458 |
  | governed (`resetTaskId` set) | yes - 8 of 8 read in #36 | no (`store-req`) | no (`store-req`) |

  ⚠️ The whole run is 194.3 s LONGER than staged-1.2's #24 under the same conditions, while the part after the
  fan-out is ~2.6x shorter. ❓ Not established why: the 100 store Tasks hold Processor slots for about 2,500 s inside
  the fan-out (stores were seen on cores 1, 4 and 8), which may delay `cc` Tasks - deciding that needs the `cc` Tasks'
  queueing in #39 beside #24. The ~5 s per HTTP write against ~0.11 s for the same write inside RG (internal-1.0, #5)
  is recorded as a follow-up; the in-RG store into a named STAGE (follow-up on `req-store-batch`) would remove both.

### 12.7 Experiments

| id | hypothesis | answers | SourceCode | riskiest assumption | verdict |
|---|---|---|---|---|---|
| E1 | the STAGE opened on the EMPTY project by RG's own genesis (MCP `mhdg_rg_open_stage`, no parent), each file's requirements stored from its branch after `check` by internal `store-req`, one Task per requirement, the STAGE committed once by `post-processing` | the request of 2026-10-01; staged-1.3's split into requirement #1 and the others (11.2) | `mh-rg-requirements-from-batch-stage-first-1.0` (SourceCode #44, archived) | the deployed RG commits an EMPTY genesis - held (ExecContext #30) | REJECTED - by the human: the store is internal-1.0's `store`, ONE Task per file, not one per requirement. Evidence: ExecContext #30 (`synthetic-0001`, Haiku / null effort, `mhdg-rg-cc-1.0.81`, project `TMPPOR98994`) FINISHED in 136.1 s, 26 of 26 Tasks OK; `open` 32.0 s; genesis 22 parentless, no requirement, its own ExecContext #31; STAGE 23 child of 22, COMMITTED, 9 requirements all reqType 1, every `resetTaskId` null |
| E2 | the human's shape (2026-10-01): internal-1.0's `store` (internal `mhdg-rg.req-store-batch`) MOVED into every file's branch right after `check` - one store Task per file -, the STAGE opened before the fan-out on the empty project by `open`, committed once by `close` | E1's rejection - one Task per requirement is not the shape | `mh-rg-requirements-from-batch-stage-branch-1.0` (SourceCode #45, archived) | `req-store-batch` writes the branch's requirements into the open STAGE. Read in RG's code on every ref: it takes no STAGE and starts with the project's genesis (`addFirstManualDerivedRequirement`), which RG refuses once the project owns a snapshot (`04.876.020`, as parallel-1.0's ExecContext #8) | REJECTED - ExecContext #33 (`synthetic-0001`, Haiku / null effort, `mhdg-rg-cc-1.0.81`, project `TMPW8YIOATR`): `open` OK, both branch `store` Tasks (#8607, #8611) refused in 5 s - `04.985.050` / `04.984.010` / `04.876.020 Project TMPW8YIOATR already owns 2 snapshot(s) ... Open a STAGE with mhdg_rg_open_stage and use mhdg_rg_add_manual_derived_req against it`. The internal Function cannot be told the STAGE - a change inside RG, recorded as a follow-up |
| E3 | E2's shape with the one thing it lacked: the branch's `store` - still ONE Task per file, right after `check` - writes into the STAGE named by `stageSnapshotId`, through the write RG's refusal names (`addManualDerivedRequirement`, REST `requirements/manual` in STAGE mode), by `mh.asset.rg-req-store-stage_1.0` | E2, ExecContext #33: the store must be told the STAGE, and RG named the write that takes it | `mh-rg-requirements-from-batch-stage-store-1.0` (SourceCode #46) | parallel writes from many branches into ONE STAGE through REST land without a DB-connection timeout (C6) and number without collision - held: 100 concurrent-capable stores, ids contiguous | ACCEPTED - meets G1-G5 (G6 read on 2). ExecContext #36 (`synthetic-0001`, project `TMPU5MXIIU4`): FINISHED 159.7 s, 15 of 15 OK; genesis 26 empty, STAGE 27 its child with 8 DERIVED requirements, the two stores' ids interleaved, every `resetTaskId` set. ExecContext #39 (`batch-0004`, project `TMPTZZ8MMVC`): FINISHED 917.7 s, 407 of 407 OK, 100 store Tasks; genesis 28 empty, STAGE 29 its child holding 469 requirements; -235 and -469 read in full - DERIVED, CC's content, `source:` naming the file. Timing beside the baselines in 12.6 |
