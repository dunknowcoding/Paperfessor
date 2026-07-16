# Skill: Write clean, runnable code

**Agent**: Undergraduate
**When**: Every coding task.

The code you write ends up in the paper. It must:

1. **Be self-contained** — every Python file the PhD/Architect
   mentions must exist, import cleanly, and have at least a
   smoke test.
2. **Have no leaked secrets** — API keys, paths to your local
   machine, internal project structure. Run the redactor
   (in the future: `paperfessor key redact <file>`) before
   declaring done.
3. **Be reproducible** — every dataset download, preprocessing
   step, and model checkpoint path must be deterministic. Hash
   inputs where the dataset is versioned.
4. **Match the PhD's spec** — no extra modules, no quietly-
   removed requirements, no disabled tests.
5. **Be runnable in the declared environment** — check that the
   target Python version, GPU/CPU choice, and pinned dependency
   versions all line up with what the paper says.
6. **Have a smoke test** — a `python train.py --epochs 1` style
   entry point that prints a real (not "PLACEHOLDER") metric
   line. The PhD will not tick your task without this.

## Style

- Functions < 50 lines where possible.
- One top-level `main()`; `if __name__ == "__main__": main()`.
- Type hints on every public function.
- No print-debug. Use `logging`.
- Errors must be raised, not swallowed.
- For numerical code: pin a random seed; report the seed.

## Reporting numbers (do not skip this)

When done, log the actual numbers you got (loss, accuracy,
runtime, GPU memory peak) to `code_log.md`. The PhD uses those
numbers when drafting the paper. Format:

```
### 2026-07-14 18:00 | ran train.py | task: t1
- seed: 42
- epochs: 3
- final loss: 0.213
- val acc: 0.871
- runtime: 412s on RTX 4090
- peak gpu mem: 9.4 GB
- file: workspace/src/code/train.py
```

A "PLACEHOLDER" metric line in the code or the log is a code
review failure. The PhD will void the task.
