# Skill: Datasets are not scripts

**Agent**: Undergraduate
**When**: Before downloading or processing a dataset.

The PhD's `code_guide.md` will tell you which dataset(s) to use.
The mechanics of getting and processing them are yours. The
user's spec (req.txt) is explicit: "the undergraduate must
preprocess datasets after downloading them". You do not hand the
dataset to the LLM and ask it to figure out the splits;
**you** preprocess, **you** write the manifest, **you** log the
steps.

## 1. Pick the canonical source

- UCI, HuggingFace, the original paper's repo, or the dataset
  maintainer's official page. Do not pull from random mirrors
  or Kaggle dumps.
- If the canonical source is a URL with a version (e.g.
  `dataset-v3.zip`), pin the version. Do not download
  "the latest".

## 2. Pin a version (this is non-negotiable)

- Record the SHA-256 of the raw file in a `MANIFEST.txt` next
  to the data.
- Format:
  ```
  name: PSM
  version: 2022-04-12
  source: https://github.com/NetManAIOps/OmniAnomaly
  files:
    - PSM_train.npy  sha256=8a2f...  size=2.1MB
    - PSM_test.npy   sha256=1b9c...  size=540KB
  license: CC-BY-4.0
  ```
- The paper must be reproducible years from now. If a reviewer
  asks "how did you get the data?", `MANIFEST.txt` is the
  answer.

## 3. Preprocess deterministically

- Fixed random seeds (`np.random.seed(42)` at the top of every
  preprocessing script).
- No wall-clock-based shuffling.
- Explicit train/val/test splits, with the split IDs saved to
  `workspace/src/datasets/<name>@<hash>/splits.npy` (or
  `.json`).
- Standardize / normalize parameters saved alongside the data
  (`scaler_mean.npy`, `scaler_std.npy`), so the test set
  evaluation uses the training-set statistics.

## 4. Log the steps

In `code_log.md`, paste the exact command(s) you ran to fetch
and prepare the data, plus the resulting sizes and shapes:

```
### 2026-07-14 18:00 | preprocessed PSM | task: t1
- command: python workspace/src/code/preprocess_psm.py --out workspace/src/datasets/PSM@a1b2c3
- train: (132481, 25) float32
- test:  (87841, 25) float32
- val:   (10%, split 0)
- anomaly ratio (test): 0.275
- sha256(PSM_train.npy) = 8a2f...
- time: 47s
```

## 5. Save to the right place

- `workspace/src/datasets/<name>@<hash>/...` — not `~/data`.
  The whole point of the workspace layout is that the paper
  is reproducible from `workspace/` alone.
- The MS's `paper/` references these paths by **name** (e.g.
  "PSM"), never by absolute path. The UG's preprocessing
  writes the manifest; the MS's paper writes the citation.

## 6. The MS will write a `dataset cards` entry

After you preprocess, the MS records a dataset card in
`workspace/src/datasets/<name>@<hash>/card.md` with: name,
source URL, license, n_samples, n_features, anomaly ratio. The
PhD's paper uses this card for the "Dataset" subsection of
the Experimental Setup.

## Failure modes the PhD will catch

- "I downloaded from a Kaggle mirror" → void. Use the canonical
  source.
- "The split is random" → void. Save the split IDs.
- "I forgot the SHA-256" → void. The paper is not reproducible.
- "I reshuffled between runs" → void. The numbers are not
  comparable.

The PhD will not tick the dataset task until the manifest is
complete.
