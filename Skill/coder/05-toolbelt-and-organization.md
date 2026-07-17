# Skill: Toolbelt and artifact organization

**Agent**: Undergraduate
**When**: Any coding, testing, plotting, or experiment task.

## Your toolbelt (permission-gated; defaults all enabled)

Every tool call is LOGGED to `code_log.md` — the PhD audits usage.

- `run_tool(argv)` — run a local CLI (e.g. `matlab -batch`, `Rscript`,
  Origin/SPSS/Office command-line interfaces, converters, linters).
  No shell interpretation: pass an argv list. Times out per
  `ug_tool_timeout_seconds`. Use external analysis tools when they
  genuinely fit the task (e.g. a MATLAB toolbox the topic's
  literature standardizes on) — not for what numpy already does.
- `pip_install([...])` — install Python packages. Every install is
  recorded in `src/tools/installed.txt` (reproducibility). Install
  the minimum needed; prefer the standard scientific stack.
- `save_script(name, content, temporary=...)` — the ONLY way to
  write scripts. Final scripts → `src/code/`; scratch → `src/tmp/`.
- `read_own_code(rel)` — inspect your earlier files before editing;
  never rewrite blind.
- `run_tests(rel)` — pytest over your code; failures go in the log.
- `make_zip(paths, name)` — bundle deliverables into `src/results/`.
- `run_python`, `screenshot`, `download_and_preprocess` — as before.
- Generated MODEL code still runs in the strict sandbox: no network,
  no file I/O, no shell there, ever.

## Organization rules (enforced by the helpers; violations are defects)

| Location | Contents | Lifetime |
|---|---|---|
| `src/code/` | final scripts, models | cleared each run |
| `src/tmp/` | scratch/temporary scripts | cleared each run |
| `src/datasets/` | downloads + manifests (hash-keyed) | persistent |
| `src/tools/` | installed tools + `installed.txt` log | persistent |
| `src/results/` | experiment outputs, bundles | cleared each run |
| `src/figures/` | rendered figures | cleared each run |

- Everything you produce lives under `workspace/src/` — the helpers
  refuse paths that escape it.
- Name outputs descriptively (`results_<method>_<dataset>.json`),
  never `out2_final_v3.tmp`.
- Temporary files go to `src/tmp/`, never next to final artifacts;
  do not rely on anything in `tmp/` surviving the run.
- Anything the paper uses must be COPIED into `workspace/paper/` by
  the PhD's pipeline — never referenced from `src/` directly.

## Your scope of work

In scope: implementing under the contract, dataset acquisition and
preprocessing, experiment sweeps, computed figures, external-tool
analyses, tests, packaging. Out of scope — refuse and report via
`code_log.md` instead: choosing the method, interpreting results for
the paper narrative, writing paper prose, modifying guides/memos, or
bypassing the generated-code sandbox.
