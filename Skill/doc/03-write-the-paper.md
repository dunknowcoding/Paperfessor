# Skill: Write a top-venue paper

**Agent**: PhD
**When**: All experiments are done, you're writing the paper.

A top-venue paper is not a long paper — it is a **dense** paper.
Every sentence must be evidence-anchored; every claim cites a
real paper from the survey.

## 1. Pick the venue template first

Use `phd.detect_and_fetch_venue(direction)`. The PhD's LLM picks
the single best target venue for the direction (KDD for data
mining / time series; CVPR for vision; ACL for NLP; NeurIPS for
general ML; etc.). The PhD then downloads the venue's official
template and falls back to `acmart [sigconf]` if the download
fails. **The user override in the direction string wins** —
if the user writes "submit to NeurIPS", the PhD uses NeurIPS.

If LaTeX is not installed at all, fall back to `pandoc paper.md
-o paper.docx` (Office) or just keep the `.md` and say so in
`article_memo.md`'s `Template check` field.

## 2. Page budget (CRITICAL)

- **Main body must be ≤ venue's page limit** (NeurIPS / ICML / ICLR
  / KDD = 9; ACL / EMNLP / CVPR / ICCV / ICRA / IROS = 8; AAAI /
  IJCAI = 7). acmart does not enforce this; the PhD must count
  the rendered PDF pages and split.
- **Anything that pushes over the page limit** goes to
  `paper_appendix.md` and renders as `\appendix` in the .tex.
  This includes:
  - Extended proofs / theory derivations
  - Extra experiments / ablations
  - Hyperparameter tables
  - Per-dataset detail
  - Dataset statistics
- **The appendix must not contain**:
  - `src/` file names (e.g. `workspace/src/code/train.py` is FORBIDDEN)
  - Local PC paths (e.g. `G:\Arduino\...`, `/Users/...`, `C:\...`)
  - Project-internal names (skill files, doc_memo references, etc.)
  - Anything not in the public paper domain

The PhD's `paper_appendix.md` writer MUST redactor-check the
content before it lands in the .tex.

## 3. Figure budget

- At least **4 figures** in the main body, each cited via
  `\ref{fig:...}`. The Reviewer will reject a paper with 0
  figures.
- Larger block diagrams: use `\begin{figure*}` (2-column width).
  Smaller figures: `\begin{figure}` (1-column).
- Side-by-side: two `\subfloat` blocks. Stacked: one
  `\subfloat` with multiple subfigures.
- Every figure needs a caption (`\caption{...}`), a label
  (`\label{fig:...}`), and a source. No floating screenshots.
- The MS's `screenshot_figure` or UG's `screenshot` produces the
  PNG; the PhD copies it into `paper/figures/`.

## 4. Table budget

- At least one **main-results table** (Table 1) with k-seed
  error bars. No single-seed numbers in the main body.
- Table 1 should compare the proposed method against every
  baseline on every target dataset, with a "Source" column
  marking `reproduced` vs `cited`.
- Per-dataset detail tables go in the **Appendix** (page budget).

## 5. AI-style phrasing — kill it

Forbidden:
- "It is worth noting that…"
- "In recent years…"
- "Many researchers have…"
- "This is an exciting area…"
- "In this work, we propose…" (first person, filler)
- "Extensive experiments demonstrate…" (vague hand-wave)
- "The rest of the paper is organized as follows." (boilerplate)

Required:
- Active voice, declarative
- Every claim cites a paper from the survey (real bib key)
- "We show X (Sec. N) achieves Y on Z (Table 1) at P % 95-CI."

If the LLM produces AI-style filler, **revise at the source** —
do not paper over with a regex. The MS has a `style review` skill
that calls this out.

## 6. Preview every page

After every section draft:
1. Compile the .tex → .pdf.
2. Render the new pages with `pypdfium2` (use the
   `screenshot_pdf_page` helper in `src/research/web.py`).
3. Run the Article 19 layout checks (font size, line spacing,
   paragraph spacing, no overlap, density, no margin crossing).
4. Append a `visual_inspect` row to `article_memo.md` with
   pass/fail for each check.
5. If any check fails, **revise the section** and re-preview.
   Do not move to the next section until this one is clean.

## 7. Datasets & experimental environment

If the paper has experiments, the Experimental Setup section
must describe, in this order:
- **Hardware** (CPU/GPU, RAM)
- **Software** (Python, PyTorch / TensorFlow, key libraries + versions)
- **Datasets** (name, source URL, license, sample count, feature count,
  train/val/test split ratio)
- **Protocol** (k seeds, batch size, optimizer, lr, schedule,
  early-stopping rule, evaluation metric)
- **Baselines** (with citations)

This is the spec; do not skip hardware or software.

## 8. Style / honesty / no project-internal info

- No local paths in the paper (e.g. `G:\Arduino\driver\Paperfessor\...`).
- No `Skill/` content quoted in the paper.
- No `doc_memo.md` / `article_memo.md` references in the paper.
- No fake authors. The author block is "Paperfessor Agent Group"
  unless the user has supplied real authors.
- No fake datasets. Datasets in the paper are the ones the UG
  actually ran on.
- No fake numbers. If the UG has not run an experiment, the
  cell is "TBD (UG to run)".

The PhD runs the redactor pass before compile. The check is
literal: a `\G:` or `\Users` or `workspace/` in the .tex fails
the build.
