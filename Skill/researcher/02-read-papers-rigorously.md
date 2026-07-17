# Skill: Read papers rigorously

**Agent**: Master's student
**When**: After fetching, before writing the survey.

The PhD expects each paper you include to have been **fully read**,
not just abstract-skimmed. The user's spec (req.txt) demands:
"for every article, perform rigorous full-text detailed reading,
record the arguments and the supporting data, chart and reference
evidence — in particular the dataset the experiments use, and the
performance of the paper's method on that dataset".

For every paper:

1. **Capture the data** — what dataset(s), what split, what
   protocol, what numbers, what baseline they compare to.
2. **Capture the evidence** — which tables, which figures,
   which appendix section supports each claim.
3. **Capture the citations** — which prior work the paper
   builds on, and which prior work it disagrees with.
4. **Capture the limit** — what the paper admits it does not
   solve. The PhD uses this to scope the gap statement.
5. **Cross-check** — if a number looks too good, search the
   citation graph for replications or rebuttals.

## How to actually do this in Paperfessor

You have two real read paths.

### Path A: Offline PDF (the right path when an arXiv / OA PDF exists)

```python
from paperfessor.agents.master import MasterStudent
ms = MasterStudent(settings, router, workspace)
papers = ms.search_papers("...", max_arxiv=3, max_venue=3)  # arXiv + OpenAlex
scholar = ms.search_web("...", limit=5)                     # Scholar
# Dedup; pick the top 5 by citation count.
for p in papers[:5]:
    try:
        ft = ms.read_paper(p)              # downloads PDF, extracts text
        ev = ms.extract_evidence(ft)       # LLM call: structured extraction
        # ev.datasets, ev.metrics, ev.claims, ev.key_figures, ev.summary
    except PaperInaccessible:
        continue
```

`extract_evidence` returns an `Evidence` record with
`datasets`, `metrics`, `claims`, `key_figures`, `summary`. The
fields are anchored in the paper's real text (the LLM is given
the first ~12k chars of the body); the LLM is told to not
invent values, so the data is real.

### Path B: Online HTML (the fallback when no PDF is reachable)

```python
ft = ms.read_paper_online("https://example.com/paper.html")
# body is the rendered innerText; no figures / tables preserved.
```

Use this for paywalled or HTML-only papers. The LLM still gets
real prose, but the figure/table extraction is weaker.

## What a good log entry looks like

```
## <paper title>

- **Authors**: Last, F.M., ..., Last, Z.Y.
- **Year / Venue**: 2024 / NeurIPS 2024 [arxiv]   (or [openalex] / [scholar])
- **arXiv**: 2401.01234   (https://arxiv.org/abs/2401.01234)
- **DOI**: 10.1162/neco.2006...   (when known)
- **Citations (OpenAlex)**: 187   (for relevance ranking)
- **Datasets**: PSM, MSL, SMD   (comma-separated)
- **Headline metrics**: F1=0.83, Precision=0.91
- **Claims (from paper)**:
    - The method uses a contrastive self-supervised pretraining step.
    - Outperforms USAD by 4 F1 on PSM under the standard split.
- **Key figures/tables**:
    - Figure 1: architecture diagram.
    - Table 3: per-dataset F1.
- **Bottom line**: <2-3 sentence summary>.
```

A bad log entry is "paper X does Y." A good log entry is "paper
X reports 0.78 F1 on dataset D (table 3, row 7), trained on 4k
labeled examples (section 4.2), using the public split from
[ref]; the authors note the result depends on the random seed
(section 5.1)."

The PhD will write the related-work section from your logs.
