# Skill: Merge into a coherent survey

**Agent**: Master's student
**When**: The PhD asks for a related-work section.

The PhD reads the survey to find the **gap** the paper fills. So:

1. **Cluster by theme / method / claim**, not by chronology.
   "We have four papers that use self-training; three of them
   report a 2-3pt lift on small data, one does not. The
   disagreement is in the noise schedule — see Figure 3 in [ref]
   vs. Figure 1 in [other ref]."
2. **Surface the gap explicitly.** "No surveyed paper combines
   X with Y under protocol Z" is the sentence the PhD is
   looking for.
3. **Cite every claim.** No uncited assertions. Use the exact
   `[Author, Year]` style the venue requires; the PhD will
   pass the references through a format checker.
4. **No AI-style filler** — no "this is an exciting area," no
   "many researchers have studied," no "it is worth noting
   that." Every sentence must move the gap-finding forward.

When you're done, the survey should be a tight 2-3 page
document that the PhD can lift wholesale into the related-work
section.

## How to merge (the algorithm)

1. **Group by venue or by method family**. Don't mix
   "NeurIPS 2024" with "arXiv 2024" in the same cluster
   unless they are doing the same thing.
2. **For each cluster**, write 2-4 sentences that summarize
   what the cluster does, what the headline number is, and
   what the cluster disagrees on internally. Cite each
   contribution.
3. **At the end of the related-work**, write the gap
   statement: "To the best of our knowledge, no surveyed
   work combines <X> with <Y> under <protocol Z>." This is
   the sentence the PhD will re-quote in the paper's
   Introduction.
4. **If the cluster has more than 5 papers**, pick the 2-3
   most-cited and group the rest as "and references therein".
   A 15-paper cluster in 5 paragraphs is unreadable.

## What the PhD will check

- The cluster headings match the venue's section structure
  (most CS conferences use 2-3 related-work subsections, not
  10).
- Every cited paper is in the survey log (the PhD verifies).
- The gap statement is one sentence, not a paragraph. The
  Introduction builds on it.
- The citations are formatted per venue (acmart uses
  `\bibliographystyle{ACM-Reference-Format}`, NeurIPS uses
  a `.bst`, ACL uses `acl_natbib`).
