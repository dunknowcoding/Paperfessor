# Skill: Debug without burning the budget

**Agent**: Undergraduate
**When**: Something breaks during a run.

Default budget per task: 30 minutes of debugging. Past that, the
PhD will void the task and reassign. The PhD does not want you
spending 3 hours on a flaky third-party import.

While you debug:

1. **Reproduce minimally** — strip the broken call down to the
   smallest input that still fails. A 200-line test that crashes
   tells you less than a 5-line test that crashes.
2. **Read the traceback bottom-up** — the last frame is the
   symptom; the first frame is the cause. Most beginners read
   top-down and waste time on the surface.
3. **Check the obvious first** — wrong working directory,
   missing dependency, wrong dataset path, wrong Python
   version. These are the **most common** failures. Don't
   skip them.
4. **Log the diagnosis** to `code_log.md` *before* you fix it.
   The PhD will want to know what went wrong and why you
   tried what you tried. Format:

   ```
   ### 2026-07-14 18:30 | debug train.py | task: t1
   - error: ImportError: No module named 'torch_scatter'
   - tried: pip install torch_scatter -> build failed (MSVC missing)
   - tried: conda install pytorch-scatter -> conflict with torch==2.0
   - root cause: torch_scatter wheel not available for our torch
   - next: pin torch==1.13 + torch_scatter==2.1.2 (verified wheel)
   ```

5. **If the bug is in someone else's code** (a library, a
   paper's reference implementation) — stop, log it, ask
   the PhD. Don't fight a third-party bug for an hour. The
   PhD may decide to swap the library or the method.

## When to give up

- After 30 minutes of debugging the **same** symptom, the
  PhD will void the task. Don't fight the void. Log what you
  tried, and ask the PhD for a different task.
- If the failure is "I don't have GPU", that's not a debug
  task; it's an environment task. Log it and let the PhD
  re-spec the run for CPU-only.

## Anti-patterns to avoid

- "Let me just try one more thing..." (you've been on this for
  an hour)
- "I'll just comment this out and see" (you now have a different
  code base than the PhD reviewed)
- "The error is fine, the model still trains" (it doesn't)
- "I'll fix it later" (you won't)
