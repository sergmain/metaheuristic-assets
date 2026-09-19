# rg-requirements

SourceCode `mh-rg-requirements-from-file-1.1` · Functions `mh.asset.rg-req-prompt_1.0`, `mh.asset.rg-req-store_1.0`
· payload `rg-requirements/payload/fn-rg-requirements` · also uses `mh.asset.rg-temp-project_1.1`,
`mh.asset.call-cc` and the internal `mh.meta-storage`

SourceCode `mh-rg-requirements-from-batch-1.1` (section 7) - Functions `mh.asset.rg-batch-paths_1.0`,
`mh.asset.rg-req-path-prompt_1.0`, `mh.asset.rg-req-check_1.0`, `mh.asset.rg-req-store-batch_1.0` - the same payload -
also uses the internal `mh.batch-line-splitter` and `mh.aggregate`

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

## 7. mh-rg-requirements-from-batch-1.1 - every file of a batch

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
| 4.2 | `cc` | `mh.asset.call-cc_1.1` | CC's answer; `tries 2`; cached - `cache on, cacheMeta`; a CC session limit is identified by the execution gate (7.7) |
| 4.3 | `check` | `mh.asset.rg-req-check_1.0` | `reqAnswer` - the answer checked as the store checks it, written as one line of ASCII JSON `{sourcePath, requirements}` |
| 5 | `gather` | internal `mh.aggregate`, `text` | `reqAnswers` - every branch's `reqAnswer`, collected by name across the ExecContext |
| 6 | `store` | `mh.asset.rg-req-store-batch_1.0` | the requirements in the project, as one chain; `reqIds`, `reqSources` |
| 7 | `dropRecord` | internal `mh.meta-storage`, `delete` | the `batchKey` record removed from the table `synthetic` names |

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
| `projectCode` | out | the project's code | `TMP...` |
| `reqIds` | out | the stored requirements' ids, one per line, in storing order | |
| `reqSources` | out | one line per stored requirement: its id, a TAB, the file it came from | |

**Credential:** the vault entry `RG_API_AUTH`, declared by `mh.asset.rg-temp-project_1.1` and
`mh.asset.rg-req-store-batch_1.0`.

### 7.4 Durable side effects

- One RG project per run, development runs included: its description, the pipeline, `isReady`.
- Its genesis run (an RG ExecContext) and one committed snapshot per stored requirement, in one linear chain.
- The `batchKey` record is DELETED from the table `synthetic` names - after the store has succeeded, and only then.

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
