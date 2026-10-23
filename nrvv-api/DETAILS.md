# nrvv-api - DETAILS

NRVV's Anthropic API environment (plan 052): the API twin of every NRVV flow that calls a model, and the API code of
the implementation Function. A delivery unit of its own, so that importing it registers exactly the API environment
and nothing of `nrvv/` that is still under development.

## What is here

| path | what |
|---|---|
| `source-codes/nrvv-<name>-api-<version>.mhsc` | the API twin of `nrvv/source-codes/nrvv-<name>-<version>.mhsc` |
| `functions/fn-nrvv-implement-api` | `mh.asset.nrvv-implement-api_1.0`: the implementation script with `api.keyCode ANTHROPIC_API_KEY` |

The call-cc API code a twin calls, `mh.asset.call-cc-api_1.0`, belongs to `call-cc/` and is delivered from there.

## How a twin is made

❗ **Generated, never edited:** `python nrvv/tools/api_twin.py <base.mhsc>... --out nrvv-api/source-codes`. A twin is
its base flow with every model call site moved to the API code of its Function (`mh.asset.call-cc_<v>` ->
`mh.asset.call-cc-api_1.0`, `mh.asset.nrvv-implement_<v>` -> `mh.asset.nrvv-implement-api_1.0`) and
`llm_provider = "claude_api"` on that site's metas; its name is the base name plus `-api`, its version the base's.
NRVV starts it by that name (`nrvv-needs-cv-api`, ...) when the project's environment is `claude_api`.

- A changed base flow is a new base version, so its twin is a new file - never a rewrite of an existing twin (a twin is
  a descriptor: MH-GIT-DELIVERY-FUNCTION-DESCRIPTION.md 1.5). The tool refuses to overwrite a twin that differs.
- Both payloads are shared with the CC environment: the API path is selected inside them by `llm_provider`, so a
  payload change reaches both environments on the same push.

## Delivery

`mh_import_bundle_from_git(repo = https://github.com/sergmain/metaheuristic-assets.git, path = nrvv-api)`.
