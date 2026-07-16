# Paperfessor

> A research direction, a top-innovation paper draft, and a runnable
> code project — across one unified, multilingual GUI + CLI.

Paperfessor is a 3-agent desktop app. You give it a research
direction (a sentence is enough); the three agents plan the paper,
do the literature, write the code, run the experiments, draft the
manuscript, and seal the deliverable.

- **PhD student** — supervisor / paper architect
- **Master's student** — literature + survey
- **Undergraduate** — code + experiments

## Quick start

```bash
# 1. Install
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[gui,dev]"

# 2. Set an API key (MiniMax default; any supported provider works)
paperfessor key set minimax --key "sk-..."

# 3. Run a direction
paperfessor run "self-supervised learning for time-series anomaly detection in industrial IoT"

# 4. Inspect what the agents produced
cat workspace/paper/body/paper.md
cat workspace/doc_memo.md

# 5. (Optional) launch the GUI
paperfessor-gui
```

See the [main README](../../README.md) for the full configuration
guide, CLI reference, and project layout.
