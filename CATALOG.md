| workflow | bundle dir | description |
|---|---|---|
| mh-call-cc-1.0 | call-cc | Runs the Claude Code CLI on a prompt taken from a Variable and returns CC's answer verbatim in a Variable. Builds no prompt and parses no answer - the model step inside a larger workflow. |
| mh-dir-batcher-1.3 | dir-batcher | Scans a source-code directory, cuts the list of files worth deriving requirements from into fixed-size batches, and stores each batch as a meta-storage record - a work queue for a requirements pass. |
| mh-rg-temp-project-1.1 | rg-temp-project | Creates a fresh, empty RG project with a random TMP code through the RG REST API (vault key RG_API_AUTH) and reports the code. Optionally sets its description, an RG genesis pipeline and readiness. |
| mh-rg-requirements-from-file-1.1 | rg-requirements | Reads the file named by a meta-storage batch record (the output of dir-batcher), has CC derive requirements from it for a given description, and stores them in a fresh RG project. Uses rg-temp-project and call-cc. |
| mh-rg-requirements-from-batch-1.1 | rg-requirements | Reads every file named by one meta-storage batch record, has CC derive requirements from each file in parallel (one mh.batch-line-splitter branch per file, CC answers cached), stores them all in a fresh RG project as one chain of snapshots, then deletes the record. Uses rg-temp-project and call-cc. |
| mh-verify-git-cycle-1-1.2 | verify-git-cycle/scenario-1 | Test fixture for Function delivery: a dispatcher-sourced hello Function's response is upserted into meta storage (mh-verify.git-cycle). No DETAILS.md. |
| mh-verify-git-cycle-2-1.2 | verify-git-cycle/scenario-2 | Test fixture for Function delivery: the same with a git-sourced hello Function, also reporting the payload revision. No DETAILS.md. |
| mh-factorial-main-1.8 | common-bundle | Legacy YAML example (factorial): the entry graph, built on mh.exec-source-code. No DETAILS.md. |
| mh-factorial-recursion-1.17 | common-bundle | Legacy YAML example (factorial): the recursive graph, built on mh.evaluation and mh.nop. No DETAILS.md. |
| source-code-for-simple-rnn-v1.1 | common-bundle | Legacy YAML example: permutes variables and inlines (mh.permute-variables-and-inlines) and runs the simple-rnn:1.3 Function. No DETAILS.md. |
