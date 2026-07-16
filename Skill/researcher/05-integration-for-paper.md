# Skill: Integration for paper — the MS's special skill

**Agent**: Master's student
**When**: The PhD is writing the paper and needs the MS to translate
"a pile of evidence records" into "a coherent argument".

The user's spec calls this out explicitly: "the master's
student's skill in integrating paper information needs special
design". This is the most important MS skill.
The other research skills (search, read, merge, conflicts) feed
into this one.

The MS's job in the write phase is **integration**: take the
structured evidence records (datasets, metrics, claims, key
figures) and turn them into prose the PhD can drop into the
paper. The MS does NOT decide the venue, the section order, or
the contribution list — those are the PhD's calls. The MS
turns data into argument.

## What integration looks like

Given a list of `Evidence` records (from `extract_evidence`):

```python
evs = [
    Evidence(paper=p1, datasets=("PSM", "MSL"), metrics=("F1=0.83",),
             claims=("uses contrastive SSL",), summary="..."),
    Evidence(paper=p2, datasets=("PSM",), metrics=("F1=0.78",),
             claims=("uses self-training",), summary="..."),
    ...
]
```

the MS produces a Markdown section the PhD can paste into the
paper. For the related-work section, this looks like:

```markdown
## 2. Related Work

### 2.1 Self-supervised anomaly detection on time series

[Smith et al., 2024] propose a contrastive self-supervised
pretraining step for multivariate time-series anomaly detection,
reporting 0.83 F1 on PSM (Sec. 4.2) and 0.79 F1 on MSL (Tab. 3)
under the standard 80/20 split. [Lee et al., 2023] use a
self-training scheme with confidence thresholding, reporting
0.78 F1 on PSM. The two methods agree on PSM being hard, but
disagree on the optimal pretraining signal: [Smith] favor
contrastive (Tab. 5 ablation); [Lee] favor self-training (Sec.
5.3). We are not aware of any surveyed paper that combines
the two under a unified protocol.

### 2.2 ...
```

## The integration rules (must follow)

1. **Every claim cites a real paper from the survey log**. No
   unsourced assertions. If the MS does not have evidence for a
   claim, it says "the surveyed corpus does not address X" —
   it does not invent.

2. **Numbers must be from the Evidence record, not from the
   LLM's memory.** The LLM is told: "Do not invent values; the
   surveys may not have given you a number. If a number is
   missing, leave the cell as 'not yet evaluated' or skip the
   claim."

3. **Conflicts are surfaced, not hidden.** If two papers
   disagree, the MS writes "X reports ..., Y reports ...; the
   conflict is in <protocol>". The PhD uses the conflict as a
   motivation point.

4. **Cluster by theme, not by paper**. The reader should not see
   "Paper 1 does A. Paper 2 does B. Paper 3 does C." The reader
   should see "Method family X (used by [ref], [ref]) does A;
   method family Y (used by [ref], [ref]) does B." Cite the
   cluster members; describe the family.

5. **The gap statement is one sentence.** Not a paragraph, not a
   bullet list, not "we hypothesize". One sentence: "No
   surveyed paper combines <X> with <Y> under <protocol Z>."

6. **Match the venue's reference style.** The PhD's LaTeX writer
   uses `acmart` with `ACM-Reference-Format` by default, but the
   user can override per venue. The MS's integration output
   uses the venue's `[Author, Year]` style, not a freeform
   cite.

## Style review (the MS reviews the PhD's prose)

The PhD drafts the paper section by section. After each draft
the MS does a **style review**:

- Read the draft against the spec's "avoid AI-style phrasing"
  list (no "It is worth noting", no "In recent years", no "Many
  researchers have", no first-person filler).
- Flag every violation with `!!! STYLE !!!` in the feedback.
- Do not rewrite the PhD's prose without permission; just
  flag.

This is the only place in the project where the MS critiques
the PhD's output. It is short and surgical; it does not become
a co-author.

## Output format for the PhD

The MS's output for one section is a single Markdown string
starting with the section's `##` heading and ending with a
blank line. The PhD concatenates section outputs into
`paper.md`. No meta-commentary in the output.
