# rg-temp-project

SourceCode `mh-rg-temp-project-1.0` · Function `mh.asset.rg-temp-project_1.0` · payload
`rg-temp-project/payload/fn-rg-temp-project`

## 1. Purpose

Give a caller a fresh, empty RG project and tell it the project's code - a scratch project for trying a
pipeline, an import or a language without touching a real one. It is `mkdtemp` for RG: a fixed prefix, a
random suffix, created atomically, and a new draw only when the code turns out to be taken.

"Temporary" is how the code is minted and what the project says about itself - its name, and a
description naming the ExecContext that created it. RG has no temporary flag, and nothing in this
capability deletes a project.

## 2. The graph

One process, `mkproject`, calling `mh.asset.rg-temp-project_1.0`. The order that matters is inside the
Function:

1. **The secret handoff comes first.** The Processor's `accept()` waits 10 seconds, so the Function
   connects before it does anything else - in a development run too.
2. **Everything resolvable is resolved before RG is called**: the inputs, the output declaration, the url,
   the shape of the credential. A defect found after the project exists would leave a project whose code
   nobody was told.
3. **A development run stops there**, writing `mh.null-value`.
4. **A production run executes the mkdtemp loop**: draw `TMP` + 8 of `[A-Z0-9]` from a CSPRNG, `POST
   /rest/v1/rg/projects/add`; on "already exists" draw again, at most 10 times. Every other refusal is final.

## 3. Run-data contract

Launch with `mh_create_exec_context_with_variables`; `mh_create_exec_context` refuses a SourceCode with
source-level inputs (`562.120`).

| variable | direction | meaning | permitted values |
|---|---|---|---|
| `rgBaseUrl` | in | the RG (dispatcher) to create the project in | an absolute http(s) url, e.g. `http://localhost:64967` |
| `locale` | in | the project's language, fixed for its lifetime | what RG accepts: `ru en es de he ja fr ko it nl` |
| `production` | in, required | whether anything is created | `true` creates; every other value, `mh.null-value` included, is a development run |
| `projectCode` | out, ExecContext level | the code RG answered with | `TMP` + 8 of `[A-Z0-9]`; `mh.null-value` when nothing was created |

**The credential is not a variable.** It is the vault key `RG_API_KEY`, declared as `api.keyCode` in
`mh-function.yaml` and handed over by the Processor on the loopback secret channel. The vault holds the
PLAIN `login:password` of an RG account with the role `ADMIN` or `LEGAL_ADMIN` - not base64; the Function
encodes it for HTTP Basic, the only scheme RG's REST API accepts.

## 4. Durable side effects

- **Production:** one RG project, in the company of the account in `RG_API_KEY`.
  `RgProjectTxService.createProjectTx` writes the info bank, the project (`isReady=false`, no SourceCode,
  the default `maxDepth`) and its empty DERIVATION / CONTAINMENT / VERIFICATION DAG records. Name:
  `Temporary project <code>`. Description: `Temporary project created by mh.asset.rg-temp-project_1.0 in
  ExecContext #<id>`.
- **Development:** nothing.
- No meta storage is written, so there is nothing to register in `MH_META_STORAGE_REGISTRY`.

## 5. Fitness criteria

| id | criterion | hardness | type |
|---|---|---|---|
| F1 | the reported `projectCode` names a project that exists in RG - read back from RG by its code, never taken from the output alone | hard | D |
| F2 | the created project is empty and not yet runnable: 0 snapshots, `isReady=false`, no SourceCode | hard | D |
| F3 | a temporary project is recognisable as one without this file: its code starts with `TMP` and its description names the ExecContext that created it | soft | D |
| F4 | a development run leaves RG untouched: `projectCode` is `mh.null-value` | hard | D |

## 6. Corrections

None yet.
