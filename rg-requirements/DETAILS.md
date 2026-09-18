# rg-requirements

SourceCode `mh-rg-requirements-from-file-1.1` · Functions `mh.asset.rg-req-prompt_1.0`, `mh.asset.rg-req-store_1.0`
· payload `rg-requirements/payload/fn-rg-requirements` · also uses `mh.asset.rg-temp-project_1.1`,
`mh.asset.call-cc` and the internal `mh.meta-storage`

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
