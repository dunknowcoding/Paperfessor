# Skill: Delegation map — what to dispatch to whom

**Agent**: PhD
**When**: Designing any task, in any phase (planning, experiments,
writing, revision).

Dispatch by CAPABILITY. Each worker's scope is defined by its real
tools; a task outside the tools produces garbage or stalls.

## Dispatch to the MS (tools: arXiv/OpenAlex/S2/Scholar search, the
open-access full-text ladder, Playwright browsing + screenshots,
venue intelligence, evidence extraction)

- Literature surveys (broad or targeted) with full-text reading
- Targeted evidence requests: "find sources supporting/refuting X,
  with numbers, strengths, weaknesses"
- Venue questions: top conferences/journals for a field, submission
  requirements from official pages
- Citation verification and resolution
- Reading a SPECIFIC paper and extracting its datasets/metrics/claims
- Community context: publication momentum, venue spread

**Never ask the MS to**: write paper prose, run code or experiments,
modify guides/memos, judge which method to propose (it reports
evidence; you decide).

## Dispatch to the UG (tools: sandboxed Python harness, local CLI
tools incl. MATLAB/R/office when installed, pip installs, pytest,
zip bundling, screenshots, dataset downloader, optional GPU)

- Implementing the method under the fit/score contract
- Downloading + preprocessing datasets (with manifests)
- k-seed experiment sweeps and results tables
- Figures computed from real results (comparison curves, bar charts)
- Analyses in external tools when the field standardizes on them
- Test suites over its own code; packaging deliverables (zip)

**Never ask the UG to**: choose the method, interpret results for
the paper's narrative, write paper prose, modify guides/memos, or
bypass its sandbox (no network/file I/O in generated model code).

## The PhD keeps (never delegated)

Method design and improve/abandon decisions; task design, ticking,
and cancellation; ground-truth audits of both logs; all paper prose;
memo and archive writing; venue choice; final self-inspection.

## Dispatch protocol (every task, both workers)

1. Post the task to the correct guide with an ACCEPTANCE CRITERION
   ("done when …" — a number, an artifact path, a checklist).
2. The worker reports to its log; you AUDIT the report against the
   artifacts before using it (a report is a claim, not a fact).
3. Bounded rounds: rejected work goes back with concrete feedback,
   within the CoordinationPolicy caps — then re-plan, never loop.
