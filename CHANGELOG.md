# Changelog

## 1.0.0 (2026-07-18)

First public release. Paperfessor turns a one-sentence research
direction into a survey, real experiments, and a venue-formatted PDF —
with honesty guards at every step.

### Highlights

- **Three-agent pipeline** (PhD / Master's / Undergraduate) with
  spec-conformant status APIs, checkbox task guides, timestamped work
  logs, passive review on every report, and active review after 2
  minutes of silence.
- **Real experiments only**: benchmark loaders download real public
  data (SMD, NAB) or fail loudly — synthetic stand-ins are banned;
  the LLM-implemented method must parse, pass a static safety check,
  and survive a smoke run on real data before the k = 3-seed sweep;
  results feed the paper verbatim (mean ± 95% CI, best-F1 bolded).
- **Honesty guards in the writer**: measured numbers are injected
  into abstract/intro/experiments/conclusion/limitations prompts;
  claims about unevaluated baselines or benchmarks are blocked;
  process/handoff notes, agent role names, placeholder citations, and
  internal paths are stripped or rejected.
- **Layout inspection (Article 19)**: rect-based geometry from
  pypdfium2, column-aware line gaps, image-aware density, calibrated
  thresholds; every page must pass before a run is accepted.
- **LaTeX robustness**: acmart topmatter fixed, text-mode math and
  underscore escaping, wide tables span both columns inside
  `\resizebox` (margin overflow impossible), figures placed inside
  their sections, content-derived table captions, column balancing.
- **Reliability**: MiniMax thinking-mode empty-response fix,
  retry-with-feedback loops for every agent call, fail-safe relevance
  scoring, crash-proof survey reads, DOI→arXiv PDF resolution.
- **Cross-platform**: Windows / Linux / macOS paths via platformdirs,
  POSIX TeX Live discovery, OS-keychain key storage with an
  encrypted-file fallback.
- **GUI**: paper preview tab rendering the generated PDF,
  background-threaded runs, live token dashboard.
- **Memory discipline**: shared skill defining how agents write and
  recall memory; memo auto-compaction; permanent archive with
  PDF-only zips.
- **Durable learning memory** (`doc_learn.md`): a cross-run,
  PhD-only, category-grouped store (venue requirements, paper style,
  coordination, method design, …) that is never cleared, consulted in
  planning and writing, and kept compact by near-duplicate collapsing.
- **Topic isolation**: the planner separates same-topic prior art from
  cross-topic inspiration, so changing research topic never confuses
  old memories.
- **Research goals & SOTA campaign**: `--goal`
  (sota / comparison / experiments / review / exploration) decides
  whether beating the baselines is required; `--campaign` chains
  attempts — improve a method up to a configurable number of rounds,
  switch methods, and on exhaustion replan while keeping memory but
  clearing artifacts and datasets.
- **Venue-aware writing**: the MS studies how papers for the target
  venue are organized and written; the PhD picks the theory/experiment
  balance and routes overflow theory to an appendix (or supplementary
  materials when the venue forbids appendices).
- **Configurable permissions & hard folder scope**: the Undergraduate
  can run local tools and install packages by default (toggleable via
  CLI / env / GUI); each agent may only write inside its assigned
  workspace folders, enforced in code.

### Install & CI

- `requirements.txt`, cross-platform CI, and a PyPI Trusted-Publishing
  release workflow (`.github/workflows/workflow.yml`).

### Security & privacy

- API keys live in the OS keychain only; never on disk, in logs, in
  prompts sent onward, or in the paper.
- No personal paths or project-internal names ship in the package or
  appear in generated papers.
