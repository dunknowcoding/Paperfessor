# Changelog

## 1.3.0 (2026-07-19)

More cloud providers and clearer model selection.

### Added

- **Cloud providers**: DeepSeek, Moonshot (Kimi), Qwen (Alibaba
  DashScope), Doubao (ByteDance Volcengine), Zhipu (GLM), and xAI
  (Grok), alongside MiniMax / OpenAI / Anthropic / Google and the local
  Ollama / llama.cpp options. Each is an OpenAI-compatible endpoint the
  router reaches at that provider's own base URL, with its API key in
  the OS keychain. Per-agent providers still apply, so the PhD, MS, and
  UG can each run on a different provider.
- **Model selection in CLI and GUI**: choosing a provider defaults every
  model field to that provider's latest catalogue model, which you can
  then edit. The GUI provider list is populated from the catalogue (all
  providers appear) and updates the model fields on change; the CLI
  `run --provider <name>` does the same and lists valid providers on a
  typo.

## 1.2.0 (2026-07-18)

Smarter cognition, article-type flexibility, and cross-discipline
robustness, validated across multiple rounds of real end-to-end
generation (experimental CS papers, reviews in economics / social
science / medicine / law, technical reports, and creative fiction).

### Added

- **Article types** (`paper_goal`): alongside `sota` / `comparison` /
  `experiments` / `review` / `exploration`, two new types with
  structure and scaffolding suited to the work:
  - `technical_report` — Executive Summary, Background, System Design,
    Implementation, Evaluation/Validation, Conclusion; planned from a
    concrete engineering approach, not a research method.
  - `creative` — chaptered narrative prose with NO abstract, references,
    venue label, survey, or experiments; planned from a narrative
    framing (genre / voice / device).
- **More creative, self-critical PhD**: the innovation step reasons from
  first principles, names the strongest objection to its own idea, and
  writes in a natural human voice.
- **Durable, token-bounded memory**: recalled short/long memory is
  capped to a fixed prompt budget so accumulated learnings never inflate
  input length; a run-end reflection distills each attempt into the
  learning memory.
- **Theory-derived limitations**: the Limitations section is grounded in
  the specific assumption the proposed method bakes in, not a template.

### Fixed

- LaTeX robustness across disciplines: breakable body and reference URLs
  (`\url{}` + xurl), shrink-to-fit long display equations, title-page
  paragraph-gap calibration.
- The METHOD parser accepts markdown/bullet/dash-wrapped labels, so
  strong creative proposals are used instead of weak keyword fallbacks.
- Goal-aware readiness + defect scan: creative writing is judged on the
  prose rendering, not academic gates it does not have.

## 1.1.0 (2026-07-18)

Cross-discipline reliability, flexible models, and richer coordination.
Validated end-to-end on review-goal papers in economics, social
science, and medicine (all layout-clean, zero honesty defects) plus the
CS experimental path.

### Added

- **Goal modes** (`paper_goal`): `sota` (default; iterate to beat the
  baselines), `comparison`, `experiments`, `review`, `exploration`.
  Only `sota` makes competitiveness a hard gate.
- **Review structure**: literature-review papers get a survey layout
  (Background, Thematic Synthesis, Discussion, Open Problems) with no
  Method/Experiments; the code phase is skipped.
- **Per-agent providers/models**: the PhD, Master's, and Undergraduate
  can each use a different cloud or local provider and base URL, not
  just a different model. Optional image-generation model config.
- **Durable learning memory** (`doc_learn`, PhD-only): distilled,
  categorized lessons that persist across runs and inform every phase,
  including an `agent-capabilities` category and a team roster so the
  PhD dispatches to each model's strengths.
- **Coordination policy**: bounded method-improvement rounds, UG code
  rounds, section redrafts, inspection rounds, and a per-run LLM budget
  — all user-configurable; a campaign orchestrator with replan-keeps-
  memory on exhaustion.
- **Datasets**: private datasets (opt-in) with a must-use priority
  list; gated public datasets record an actionable NEEDS_ACTION note
  instead of failing.
- **Cross-disciplinary sourcing**: Crossref added alongside
  arXiv/OpenAlex/Scholar; MS skill documents venue-tier judgement and
  discipline/region sources.
- **No-capability-refusal guard**: a provider-neutral constraint plus
  refusal detection so local models cannot decline tool-shaped tasks
  (the program, not the model, performs search/download/file/code).

### Fixed

- LaTeX rendering across disciplines: currency `$` amounts, statistical
  `<`/`>`, and unicode inequalities before numbers (`≥ 25 … $25`) no
  longer garble the text or overflow the margin.
- Every surveyed paper becomes a reference (journal papers without an
  arXiv id/URL were dropped); references ordered by prestige.
- No CS-experiment scaffolding or anomaly-detection citations leak into
  non-CS papers; venue label shown only when confidently applicable.
- OpenMP duplicate-runtime abort (OMP Error #15) guarded at import.
- Topic isolation: same-topic vs cross-topic archive partition.

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
