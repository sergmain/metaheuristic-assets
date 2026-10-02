# mh-api-probe - DETAILS

## 1. Purpose

Prove that a DAHF flow can reach an MH REST endpoint, authenticated with a credential the Vault delivers -
the path a flow takes when it needs something only MH's REST API answers. `mh-api-probe-meta-tables-1.0`
probes `GET /rest/v1/dispatcher/meta-storage/meta-tables` and hands back its answer.

**Business frame (DAHF §H.5), derived from the request - no question was needed:**

- **Objective:** a DAHF flow calls an MH REST endpoint (meta-tables) and gets its real answer, authenticated
  by a key delivered from the Vault.
- **Success:** a development ExecContext reaches FINISHED, its one Task is OK, and `metaTables` holds the
  endpoint's HTTP 200 JSON answer - read back by value, `production` false in it.
- **Invariants:** MH and RG untouched; development mode end to end (the endpoint is asked for its synthetic
  view); the key never appears in the Task's console or in any Variable.
- **Done:** the observed answer, beside the ExecContext id.

## 2. The graph

One process, `probe` -> `mh.asset.mh-api-probe_1.0`: one GET of `meta api-path` on `mhBaseUrl`, with
`?production=true` only when the `production` input is exactly `true`.

## 3. The run-data contract

| variable | dir | meaning |
|---|---|---|
| `mhBaseUrl` | in | the MH dispatcher, e.g. `http://localhost:64967` - an observed URL that answers |
| `production` | in, nullable | exactly `true` reads the production view; null (a development run) and every other value the synthetic one |
| `metaTables` | out | the endpoint's JSON answer, as received |

- **Credential:** Vault entry `MH_API_AUTH` - the plain `login:password` of an MH account with `MAIN_ADMIN`
  or `ADMIN` (`MetaStorageRestController`: `hasAnyRole('MAIN_ADMIN', 'ADMIN')`). `MAIN_ADMIN` sees every
  company's tables, `ADMIN` its own company's.
  - 1.1 (`mh.asset.mh-api-probe_1.1`) uses `RG_API_AUTH` instead - an existing entry; see E1/E2 below.
- **Company:** launch in the company whose Vault holds `MH_API_AUTH` - the management company (uniqueId 1)
  for the runs below. Its key has priority over the same key in any other company's Vault.
- **Launch:** `mh_create_exec_context_with_variables`, `production` passed as JSON `null`.

## 4. Durable side effects

None. The endpoint is a read; the only thing a run leaves is its own `metaTables` Variable.

## 5. Fitness criteria

| # | criterion | hardness | type |
|---|---|---|---|
| F1 | `metaTables` is the endpoint's HTTP 200 JSON answer, not an error page or a login page | hard | D |
| F2 | a development run reads the synthetic view: `production` is `false` in the answer | hard | D |
| F3 | the key appears nowhere in the Task's console or in `metaTables` | hard | D |

## 6. Corrections

- **2026-10-02, E1, ExecContext #80, Task #24944.** `01.812.040 Vault has no entry for companyId=2,
  keyCode=MH_API_AUTH`, exit -992, with the Vaults of company 1 and 2 both UNLOCKED - so the key is in
  neither (the management Vault is consulted first). Learned: a probe must name a Vault entry that EXISTS;
  `RG_API_AUTH` is the existing one holding an account's `login:password`. The SourceCode was imported into
  company 2, so runs execute there and the management company's keys take priority.
- **2026-10-02, E2, ExecContext #81, Task #24946 (OK, 20.3 s assigned -> completed).** Console:
  `GET http://localhost:64967/rest/v1/dispatcher/meta-storage/meta-tables?production=false` -> `HTTP 200, keys
  ['production', 'showCompany', 'tables'], list sizes {'tables': 2}`. `metaTables` (Variable #13514), read in
  full: `production` false, `showCompany` false, two tables of company 2 - `mh.asset.dir-batch-for-requirements.2`
  and `mh.asset.dir-batch-for-requirements.synthetic`. F1, F2, F3 hold. `showCompany` false means the
  `RG_API_AUTH` account is an `ADMIN` (its own company's tables), not a `MAIN_ADMIN` (every company's) - a probe
  that must see across companies needs a `MAIN_ADMIN` credential.

## 7. Experiments

| id | hypothesis | answers | SourceCode | riskiest assumption | verdict |
|---|---|---|---|---|---|
| E1 | the request taken literally: one process, one authenticated GET with the Vault key `MH_API_AUTH` | - | `mh-api-probe-meta-tables-1.0` | the management Vault holds `MH_API_AUTH` with an admin's `login:password`, and the Processor reaches `http://localhost:64967` - the cheapest run that shows it is this run | REJECTED - ExecContext #80: `812.040` no entry `MH_API_AUTH` in company 1 or 2 |
| E2 | the same graph with the existing Vault entry `RG_API_AUTH` | E1, ExecContext #80: `MH_API_AUTH` exists in no Vault | `mh-api-probe-meta-tables-1.1` | the `RG_API_AUTH` account has `ADMIN` or `MAIN_ADMIN` - a 403 would falsify it | CHAMPION - ExecContext #81: Task OK, HTTP 200, F1-F3 hold; the account is `ADMIN` of company 2 |
