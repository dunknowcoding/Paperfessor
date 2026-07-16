# Paperfessor

> A research direction, a top-innovation paper draft, and a runnable
> code project — across one unified, multilingual GUI + CLI.

Paperfessor is a 3-agent desktop app. You give it a research
direction (a sentence is enough); the three agents plan the paper,
do the literature, write the code, run the experiments, draft the
manuscript, and seal the deliverable.

- **PhD student** (`Skill/doc/`) — supervisor / paper architect
- **Master's student** (`Skill/researcher/`) — literature + survey
- **Undergraduate** (`Skill/coder/`) — code + experiments

## Installation

```bash
# 1. Create a Python 3.11+ environment (any tool you like)
python3.11 -m venv .venv
source .venv/bin/activate          # Linux / macOS
# or:  .venv\Scripts\activate      # Windows

# 2. Install Paperfessor in editable mode
pip install -e ".[gui,dev]"

# 3. (Optional) Copy the example env file and edit it
cp .env.example .env
```

If you prefer not to use `pip install -e`, you can also run the CLI
directly: `python -m src run "..."` from the project root, with
`PYTHONPATH` set to `src/`.

## First-time setup

Paperfessor stores API keys in the **OS keychain** (Windows
Credential Manager / macOS Keychain / Secret Service on Linux).
Keys never touch disk in plaintext.

```bash
# Store a key for the MiniMax provider
paperfessor key set minimax --key "sk-..."

# List the providers that have a key configured
paperfessor key list

# Test the keychain + the LLM round-trip in one shot
paperfessor key test minimax
```

If you do not have a MiniMax key, any other supported provider works
the same way:

```bash
paperfessor key set openai     --key "sk-..."
paperfessor key set anthropic  --key "sk-ant-..."
paperfessor key set google     --key "AIza..."
# Local providers don't need a key
paperfessor models list        # if Ollama is running locally
```

## Run a paper

```bash
# 3-agent run, paper draft written to workspace/paper/body/paper.md
paperfessor run "self-supervised learning for time-series anomaly detection in industrial IoT"

# Dry-run: just show the planned phases, no LLM calls
paperfessor run "..." --dry-run  # (planned; not yet implemented)

# GUI with the same flow
paperfessor-gui
```

Each run is recorded in the local SQLite memory at
`<workspace>/memory.sqlite3`. Inspect it with:

```bash
paperfessor memory stats         # aggregate counts
paperfessor memory runs          # recent runs (most-recent first)
paperfessor memory archived      # archived attempts (used to skip methods)
```

## Configuration

Two ways to configure Paperfessor: a `.env` file at the project
root, or the GUI Settings tab. Both override the defaults. The
GUI is friendlier; the CLI is faster to script.

### Environment variables

All settings can be set via env vars with the `PAPERFESSOR_` prefix.
The full list is in `.env.example`. The most useful ones:

| Variable                       | Default                | What it does                                            |
|--------------------------------|------------------------|---------------------------------------------------------|
| `PAPERFESSOR_PROVIDER`         | `minimax`              | LLM provider slug                                       |
| `PAPERFESSOR_MODEL`            | `MiniMax-M3`           | Project-wide default model                              |
| `PAPERFESSOR_PHD_MODEL`        | `MiniMax-M3`           | Model the PhD uses                                       |
| `PAPERFESSOR_MS_MODEL`         | `MiniMax-M3`           | Model the master's student uses                          |
| `PAPERFESSOR_UG_MODEL`         | `MiniMax-M3`           | Model the undergraduate uses                             |
| `PAPERFESSOR_BASE_URL`         | MiniMax direct API URL | Override the API endpoint                               |
| `PAPERFESSOR_THINKING_MODE`    | `true`                 | `true` = model uses thinking; `false` = no thinking     |
| `PAPERFESSOR_MAX_INPUT_TOKENS` | `1000000`              | Cap on the input we send to the LLM                     |
| `PAPERFESSOR_DEFAULT_MAX_TOKENS` | `32768`              | Cap on the output per call                              |
| `PAPERFESSOR_DISPLAY_STYLE`    | `default`              | `minimal` / `default` / `vibrant`                       |
| `PAPERFESSOR_DISPLAY_COLOR`    | `auto`                 | `auto` / `dark` / `light` / `monochrome`                |
| `PAPERFESSOR_LANGUAGE`         | `en`                   | Interface language: `en` / `zh-CN` / `ja`               |

### Per-agent model picker

The three agents (PhD, MS, UG) can each use a different model. This
is useful if you want, say, the strongest model on the PhD and a
cheaper model on the UG:

```bash
# Set per-agent models via the CLI
paperfessor models pick --group phd
paperfessor models pick --group ms
paperfessor models pick --group ug
```

The CLI lists the live model catalog for the active provider, then
picks the "latest" cloud model (by version number) or a random
local model (for Ollama / llamacpp).

### Working directory

Paperfessor reads & writes:

- **Runtime workspace**: `<project>/workspace/`
  - `doc_memo.md` (PhD's private memory)
  - `article_memo.md` (PhD's paper-writing memory)
  - `shared/{research_guide, code_guide, research_log, code_log}.md`
  - `paper/` (the drafted paper, including `body/paper.md`)
  - `src/` (the UG's coding folder: code, datasets, tools)
  - `archived/` (history of every prior attempt)
- **Settings**: `<project>/.env` (or `PAPERFESSOR_*` env vars)
- **API keys**: OS keychain (never on disk)
- **Long-term memory**: `<project>/data/memory.sqlite3`
- **Logs**: `<project>/logs/` (when present)

The workspace is recreated from `src/workspace.py` on every run.
The `shared/`, `paper/`, `src/`, and `archived/` subdirs are the four
required subdirs; the `doc_memo.md` and `article_memo.md` files are
the two required top-level memos. `gitignore` excludes
`workspace/` and `data/`.

## Workflow (typical first session)

```bash
# 1. Install + activate
pip install -e ".[gui,dev]"
# 2. Configure a key
paperfessor key set minimax --key "sk-..."
# 3. Verify the keychain round-trip
paperfessor key test minimax
# 4. Inspect what models are available
paperfessor models list
# 5. Run a direction
paperfessor run "few-shot time-series classification on industrial sensor streams"
# 6. Read what the agents produced
cat workspace/paper/body/paper.md
cat workspace/doc_memo.md
cat workspace/article_memo.md
# 7. Inspect the long-term memory
paperfessor memory stats
paperfessor memory runs
# 8. (Optional) launch the GUI
paperfessor-gui
```

## CLI reference

```bash
paperfessor --help
paperfessor run [DIRECTION] [OPTIONS]      # start a 3-agent run
paperfessor doctor                          # env + dep diagnostics
paperfessor config show                     # effective config
paperfessor key {set,list,delete,test}     # API key management
paperfessor display {show,set}              # CLI display style
paperfessor models {list,pick}              # model auto-discovery
paperfessor soul show                       # show the SOUL governance file
paperfessor memory {stats,runs,archived}    # long-term memory
```

`paperfessor run` flags:

```bash
--depth {shallow,normal,deep}        # research depth
--venue VENUE                       # target venue (neurips, icml, acl, ...)
--language {en,zh-CN,ja}            # output language
--provider PROVIDER                 # LLM provider slug
--model MODEL                       # project-wide default model
--phd-model MODEL                   # override the PhD's model
--ms-model MODEL                    # override the MS's model
--ug-model MODEL                    # override the UG's model
--thinking / --no-thinking          # toggle extended-reasoning prefill
--max-input-tokens N                # cap on input tokens (context window)
--max-output-tokens N               # cap on output tokens
--display-style {minimal,default,vibrant}
--display-color {auto,dark,light,monochrome}
--verbose / -V                      # verbose logging
```

## Project layout

```
Paperfessor/
├── pyproject.toml
├── SOUL.md                  # governance (formerly "Constitution")
├── LICENSE
├── README.md
├── .env.example
├── .gitignore
├── src/                     # the Python package
│   ├── __init__.py          # version + public API
│   ├── __main__.py          # `python -m src` (or `python -m paperfessor` after install)
│   ├── _meta.py             # SOUL_PATH, soul_sha256()
│   ├── config.py            # pydantic Settings
│   ├── paths.py             # filesystem locations
│   ├── memory.py            # SQLite-backed run + archive history
│   ├── workspace.py         # bootstrap + archive helpers
│   ├── monitor.py           # passive + active supervisor (2-min heartbeat)
│   ├── agents/              # 3-agent model (PhD, MS, UG)
│   ├── llm/                 # LLM subsystem
│   ├── runner/              # the 3-agent run loop
│   ├── cli/                 # Typer app
│   ├── gui/                 # PyQt6 app
│   └── i18n/                # multilingual strings
├── workspace/               # runtime: 3-agent active workspace
│   ├── doc_memo.md
│   ├── article_memo.md
│   ├── shared/{research_guide,code_guide,research_log,code_log}.md
│   ├── paper/README.md
│   ├── src/README.md
│   └── archived/README.md
└── Skill/                   # per-agent skill specs (markdown)
    ├── doc/                 # PhD's skills
    ├── researcher/          # MS's skills
    └── coder/               # UG's skills
```

## Multilingual README

- [English](README.md)
- [简体中文](docs/zh-CN/README.md)
- [日本語](docs/ja/README.md)

## License

MIT.
