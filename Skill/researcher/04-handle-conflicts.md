# Skill: Handle conflicts honestly

**Agent**: Master's student
**When**: Two papers disagree, or you cannot verify a claim.

Do not paper over conflicts. The PhD would rather know now than
find out at the camera-ready stage.

1. **State the conflict plainly** in `research_log.md` — "Paper
   A reports X, paper B reports Y, both claim SOTA on the same
   dataset, the conflict is unexplained in either paper."
2. **Hypothesize the cause** — different splits, different
   metrics, different preprocessing. Don't speculate wildly; if
   you can't pinpoint, say so.
3. **Recommend what to do** — re-run, pick one and cite the
   other as future work, or contact the authors. The PhD
   decides.
4. **Do not cherry-pick** to make a paper look better than it
   is. The PhD's review pass will catch this.

A survey that hides conflicts is worse than no survey.

## Conflict log format

In `research_log.md`, mark a conflict with `!!! CONFLICT !!!` so
the PhD can grep for it:

```
!!! CONFLICT !!! Paper A (NeurIPS '23) reports 0.83 F1 on PSM;
Paper B (KDD '24) reports 0.71 on the same dataset. Different
splits: A uses the random 80/20, B uses the temporal split. B
acknowledges the gap in section 5.2.
```

Do not resolve the conflict in the log. The PhD resolves; you
document.
