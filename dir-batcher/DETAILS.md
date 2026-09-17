# dir-batcher — DETAILS

Per `DAHF-EXECUTION-ARCHITECTURE.md` — everything true of THIS capability and of nothing else.

---

## 1. Purpose

Turn any directory of source code into a work queue that a requirements pass can consume: the tree is
scanned for files worth deriving requirements from, the result is cut into fixed-size batches, and each
batch is stored as one record in meta storage under a name minted for that run. A consumer takes one
batch at a time and deletes it when done, so the queue is also the progress marker — what is left is
what remains to do, and a consumer that dies loses at most one batch.

---

## 2. The graph

Declaration order fixes execution order, so the sequence below is a correctness property, not a style.

| # | process | what it contributes |
|---|---|---|
| 1 | `batch` — `mh.asset.dir-batcher_1.0` | scans `targetDir`, applies both filters, cuts into batches of 100, mints the meta table name, derives the synthetic flag, emits the descriptor fields |
| 2 | `register` — `mh.meta-storage-registry` | records what the table is for, in `MH_META_STORAGE_REGISTRY` |
| 3 | `store` — `mh.meta-storage` | upserts the batches into the table |

❗ **`register` sits between `batch` and `store` and must.** It needs the table name, which only
`batch` can mint; and it must precede `store`, because a run that dies half-way should leave a
described empty table rather than an undescribed full one. The first explains itself; the second is an
unidentifiable heap nobody can safely delete.

---

## 3. The run-data contract

**Inputs** (source-level, both required):

| name | meaning | permitted values |
|---|---|---|
| `targetDir` | the tree to scan | any absolute path readable by the Processor |
| `production` | which meta store to write | the literal `true` selects MH_META_STORAGE; EVERY other value, `mh.null-value` included, selects MH_META_STORAGE_SYNTHETIC |

**Outputs:** `batchRecords` (JSON array of `{type, recKey, body}`), `metaStorageType` (the table name),
`syntheticFlag`, and the descriptor fields `tableDesc`, `tableRecKeyFormat`, `tableBodyFormat`,
`tableConsumer`.

⚠️ `production` is required and has no default. A caller with no value passes `mh.null-value`, which
selects the synthetic store — the failure a re-run repairs, rather than the one that cannot be undone.

---

## 4. Durable side effects

| where | what |
|---|---|
| `MH_META_STORAGE` or `MH_META_STORAGE_SYNTHETIC` | one record per batch, type `mh.asset.dir-batch-for-requirements.<execContextId>`, recKey `batch-NNNN`, body = one absolute path per line |
| `MH_META_STORAGE_REGISTRY` | one descriptor row for that table |

Both are per-run by construction: the type carries the ExecContext id, so two runs never collide and
neither needs to know about the other.

---

## 5. Fitness criteria

Corpus-specific verification criteria. Hardness: **hard** blocks release. Type: **D** is checkable by
code, **P** needs judgment.

| id | criterion | hard/soft | D/P |
|---|---|---|---|
| F1 | No selected path lies under a build-output or dependency directory — `target`, `build`, `out`, `dist`, `bin`, `obj`, `coverage`, `node_modules`, `vendor`, **`classes`** | hard | D |
| F2 | No selected path is a localized restatement of another file — a message bundle with a locale suffix such as `_ru`, `_zh_TW`, `_ja_JP` | hard | D |
| F3 | No selected path lies under a dot directory | hard | D |
| F4 | A sample of the produced queue, drawn away from the first batch, contains files a requirements pass can derive from | hard | P |
| F5 | The file-type mix is plausible for the corpus — a language's own sources dominate, and no single auxiliary extension approaches them in count | soft | P |
| F6 | No file OUTSIDE an excluded directory is dropped — exclusion removes build output, never source | hard | D |

❗ F4 and F5 exist because F1—F3 can all pass while the queue is still useless: they assert that the
rules were applied, not that the rules were the right rules. That gap is the whole reason
`DAHF-IMPLEMENTATION-AND-CONTINUOUS-IMPROVEMENT.md` exists, and F5 in particular is the check that would have caught
the correction below from a number alone.

---

## 6. Corrections

### 2026-09-16 — build output and localized bundles were being batched

**Found:** reading recKey `batch-0001` out of `mh.asset.dir-batch-for-requirements.1` after a run that
reported FINISHED with every test green.

**Evidence:** of 100 paths in the first batch, the large majority were under
`C:\sandbox\github\derby\classes\...` — generated message bundles such as
`clientmessages_ru.properties`, `messages_zh_TW.properties`, `m0_en.properties`. The corpus-wide count
said 4,990 files of which 1,450 were `.properties`, a ratio that carried the same evidence two runs
earlier and was reported without being read as evidence.

**Cause:** Derby keeps build output in `classes/`, which `EXCLUDED_DIRS` did not name; and
`MASKS_GENERAL` contained `*.properties`, which selects every translation of every message catalogue.
Neither is an implementation defect — the filter did exactly what it was specified to do, and the
specification did not match what a requirements pass needs.

**Criteria added:** F1 extended with `classes`; F2 added; F5 added, so the ratio is a check rather
than a remark.

---

### 2026-09-16 - the exclusion set was checked for over-reach, and F6 added

**Found:** while reconciling why `.sql` fell from 560 to 285 between two runs.

**Evidence:** an independent walk of the corpus - deliberately not using the Function's own code, since
verifying a filter with the filter is circular - found 835 `.sql` in total: 275 under `classes`, 275
under `target`, 285 selected. The two excluded trees hold the same number of files, which is why a
single-cause explanation looked self-confirming and was half wrong: the `.sql` and `.html` reductions
came from `target`, which the filter already excluded, and not from the `classes` correction.

**What it changed:** nothing about the filter, which behaved correctly. It exposed a missing criterion.
F1-F3 all assert that exclusion WORKS; none asserted that over-exclusion does NOT happen, so a filter
silently dropping real source would have passed every check in this file.

**Criteria added:** F6.

---
## 7. Known limits

- ⚠️ Batch size is a constant in the Function, not a per-run input. Changing it changes what a batch
  IS, which is a property of the capability rather than of the corpus being scanned.
- ⚠️ `F1` is a fixed list of directory names. A corpus that puts build output somewhere unusual needs
  the list extended — which is what the correction above was.
- ❌ Nothing verifies the queue after it is written. F4 and F5 are criteria a launcher applies; no
  process in the graph enforces them.