# Episodic Memory Agent

A small, local, inspectable **memory layer for an LLM**. It reads a conversation, decides what is
worth remembering, stores it as structured *episodes* in SQLite, and retrieves the right memory in a
**later, separate conversation** — or says plainly that the archive does not establish an answer.

Everything runs on your own machine through [Ollama](https://ollama.com). There is no cloud service,
no API key, no agent framework, and no vector database.

> **Monday:** "We're building the prototype on SQLite."
> **Wednesday, brand-new chat:** "Which database did we pick?"
> → *"SQLite. The team chose it on 3 October because the prototype is single-user and offline-first."*
> Under the reply you can open the evidence panel and see the episode ID, the similarity score, and
> the original message that produced it.

---

## 1. The problem

A normal chatbot forgets because it has no notebook. Each request is a fresh bundle of text, and
when the chat closes, that bundle is thrown away.

The obvious fix — save every message and replay it later — fails three ways:

| Problem | What happens |
|---|---|
| **Space** | A year of chat does not fit in the model's context window. |
| **Noise** | Greetings and half-sentences bury the one sentence that matters. |
| **Shape** | A conversation mixes decisions, tasks, opinions and small talk. You want the decision, not the 40 messages around it. |

So the real job is two-sided: **decide what is worth keeping**, and **find it again by meaning**.

## 2. What this project does

On every turn it runs a small agent loop:

1. **Store** the raw message (provenance comes from this row).
2. **Route** — ask the chat model whether this message needs the archive at all.
3. **Retrieve** — embed the question, compare it with stored episodes by cosine similarity, keep
   the best matches above a floor.
4. **Answer** using only the retrieved evidence, or abstain when the evidence is absent.
5. **Form memories** — extract durable episodes from the new messages, validate them, and store
   them automatically. There is no "save" button.

Memories are **episodes**, not messages: a title, an event type, a date, a summary, people, facts,
an outcome, and the IDs of the user messages that prove it. They also have a **lifecycle** — a fact
can be completed, cancelled, superseded, or deleted, and the old version is kept for inspection
rather than silently overwritten.

## 3. Does it work?

A 51-case, gold-annotated benchmark runs against the real local models. Headline results from the
recorded run of **2026-10-28** (full tables and caveats in [`docs/RESULTS.md`](docs/RESULTS.md)):

| Area | Result |
|---|---|
| Memory formation (13 cases, 17 expected memories) | 17/17 matched, precision 100%, recall 100%, 0 duplicates, 0 invented memories |
| Retrieval (13 cases) | top-1 69%, MRR 0.846, recall@4 100%, hard-negative rejection 85%, AUROC 0.759 |
| Lifecycle (6 cases) | fact recall 100%, 6/6 state changes, 0 duplicates |
| Grounded answering (10 cases) | answerable 100%, abstention 100%, 0 false abstentions |
| Causal controls (4 cases) | 3/4 — the contradiction case fails |
| Robustness (5 cases) | 5/5 — restart, deletion, prompt injection, distractor flood, empty archive |

**Read that honestly.** Retrieval is measured with the similarity floor disabled, and four of the
six benchmark sections seed memories directly instead of extracting them. Those scores describe
ranking, not the full user experience. [`docs/RESULTS.md`](docs/RESULTS.md) states exactly what the
numbers do and do not prove.

## 4. Requirements

| Requirement | Notes |
|---|---|
| macOS or Linux | Commands below are POSIX. |
| Python 3.10+ | Verified on 3.12. |
| [Ollama](https://ollama.com) running locally | Default address `http://127.0.0.1:11434`. |
| `qwen3.5:9b` | Chat model for extraction, routing, answering. ~6.6 GB. |
| `embeddinggemma` | Embedding model, 768 dimensions. ~621 MB. |
| ~8 GB free RAM | The 9B chat model is the main constraint. CPU-only works, but extraction is slow. |

## 5. Quickstart

```bash
# 1. Ollama (skip if the desktop app is already installed and running)
brew install ollama          # macOS; on Linux use https://ollama.com/download
ollama serve                 # in a second terminal (or start the Ollama app)

# 2. Models
ollama pull qwen3.5:9b
ollama pull embeddinggemma
ollama list                  # both names should appear

# 3. Project
git clone https://github.com/manishw7/episodic-memory-demo.git
cd episodic-memory-demo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# 4. Run
streamlit run app.py
```

Open <http://localhost:8501>.

Configuration lives in `.env` (all values have defaults):

| Variable | Default | Meaning |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Where Ollama listens. |
| `OLLAMA_CHAT_MODEL` | `qwen3.5:9b` | Model for extraction, routing, answering. |
| `OLLAMA_EMBED_MODEL` | `embeddinggemma` | Model for episode and query vectors. |
| `DATABASE_PATH` | `./memory.db` | The SQLite file. Created on first start. |
| `MEMORY_TOP_K` | `4` | Maximum memories passed to the answer model. |
| `MEMORY_MIN_SIMILARITY` | `0.30` | Minimum cosine score to count as evidence. |

`memory.db` is created automatically and is git-ignored. To start over, stop the app and delete it.

## 6. The five-minute demo

This is the sequence to walk a reviewer through.

1. **Seed real memories.** In the sidebar click **Load demo conversation & extract memories**.
   It inserts ten dated fictional messages and runs the *same* extraction pipeline as live chat — it
   does not insert episodes directly.
2. **Ask the four questions**, one at a time:
   - Why was the retrieval experiment blocked?
   - Who completed deletion testing, and when?
   - What was Mira responsible for?
   - What retrieval accuracy did the team achieve?
3. **Open "Retrieval details"** under each answer. You see the decision, the rewritten search query,
   the episode IDs and scores, the source message IDs, and the exact evidence text sent to the model.
   The first three answers cite evidence. The fourth abstains: the records do not establish a number.
4. **Prove memory is doing the work.** Start a fresh session, turn **Use memory retrieval** off, and
   ask the same questions. The answers lose the archive and say they cannot check it.
5. **Prove deletion.** Turn retrieval back on, delete one memory in the sidebar, and ask again. The
   episode is gone from retrieval.

**The ordinary path:** tell it *"I'm presenting this on 6 November and I prefer bullet points"*,
start a fresh session, then ask *"when is my presentation and how do I like information formatted?"*
Both facts come back from one episode written in the previous session.

## 7. How it works

```text
           ┌──────────────────────────────┐
           │  Streamlit page (app.py)     │
           └──────────────┬───────────────┘
                          │ handle_turn()
                          ▼
        ┌────────────────────────────────────────────┐
        │  MemoryEngine (memory_engine.py)           │
        │                                            │
        │  decide → retrieve → answer                │
        │     │        │          │                  │
        │     │        │          └─ chat model      │
        │     │        └─ embedding model + SQLite   │
        │     └─ chat model                          │
        │                                            │
        │  form_memories → validate → embed → store  │
        └───────┬───────────────┬──────────────┬─────┘
                ▼               ▼              ▼
          SQLite file      Ollama chat     Ollama embed
          (6 tables)       qwen3.5:9b      embeddinggemma
```

| Stage | Where | What happens |
|---|---|---|
| Conversation storage | `add_message` | Every user/assistant message is written with an ID and timestamp. |
| Memory formation | `form_memories` | New messages only → chat model → Pydantic validation → source-ID check → grounding check → embedding → dedupe → lifecycle → SQLite. |
| Lifecycle | `_apply_lifecycle` | A later outcome closes a task; a cancelled task is cancelled; a changed value supersedes the old memory. |
| Routing | `decide` | Chat model returns `{"needs_memory": bool, "search_query": str}`. Failures fall back to searching. |
| Retrieval | `retrieve` | Cosine similarity over `active` + `done` episodes, floor 0.30, top 4. |
| Answering | `answer` | Evidence only; assistant history is stripped so a deleted memory cannot leak back in. |
| Audit | `turn_traces`, `memory_events` | Every turn and every memory state change is persisted and visible in the UI. |

Key constants, all in `memory_engine.py`:

| Constant | Value | Purpose |
|---|---:|---|
| `DUPLICATE_SIMILARITY` | 0.90 | Treat a new episode as a restatement, not new information. |
| `SUPERSEDE_SIMILARITY` | 0.72 | Replace an old value with a newer, similar one. |
| `LINK_SIMILARITY` | 0.45 | Link an outcome/cancellation to the open task it closes. |
| `GROUNDING_MIN_OVERLAP` | 0.35 | Reject a fact whose content words barely appear in its sources. |
| `MAX_EXTRACTION_CHARS` | 6000 | Split very long messages before extraction. |

## 8. Repository layout

```text
episodic-memory-demo/
├── app.py                  Streamlit UI: chat, sidebar archive, evidence panels
├── memory_engine.py        All logic: prompts, schema, SQLite, extraction, retrieval, answering
├── evaluate.py             51-case benchmark runner and report writer
├── test_memory.py          22 fast tests with a fake model (no Ollama needed)
├── test_evaluate.py        5 tests for the scoring maths
├── benchmark/              Six gold-annotated case files (formation, retrieval, lifecycle,
│                           answering, causal, stress)
├── docs/
│   ├── PROJECT_GUIDE.md    Beginner handbook — start here if you are new to the project
│   ├── ARCHITECTURE.md     Concise design and data-flow reference
│   ├── BENCHMARK_GUIDE.md  Every metric explained in plain English
│   ├── RESULTS.md          The recorded benchmark run, with honest caveats
│   └── AUDIT.md            Line-by-line technical audit, including known defects
├── eval_results/           Recorded report and raw per-case output
├── requirements.txt
├── .env.example
└── Makefile                Shortcuts: make run / test / eval
```

`app.py` contains no memory rules — it only renders and orchestrates. If you want to change *what*
is remembered, edit `memory_engine.py`.

## 9. Tests and benchmark

```bash
# Fast tests: no Ollama, no network, under a second
pytest -q                      # 27 passed

# Full benchmark: real models, temporary database, several minutes
python evaluate.py

# One section while iterating
python evaluate.py --sections formation,retrieval

# Real-model smoke test: extract the demo and ask the four questions
python -m memory_engine
```

The benchmark never touches your `memory.db`; it uses a temporary database. Output goes to
`eval_results/eval_report.md` and `eval_results/raw.json`.

`make test`, `make eval`, and `make smoke` wrap the same commands.

## 10. Known limitations

These are stated up front because they matter more than the successes:

- **Deletion is incomplete.** Deleting an episode removes the row, but `turn_traces.details` keeps a
  copy of the evidence text that was sent to the model. A user who deletes a memory can still find
  its text in a saved turn trace.
- **Contradictions are not resolved in code.** If two active memories disagree, only a prompt rule
  asks the model to prefer the better-supported value. Benchmark case `c4` fails for this reason.
- **Retrieval quality is modest and measured generously.** Top-1 is 69%, and the benchmark disables
  the production similarity floor, so the real user-facing number is lower.
- **Routing only sees 30 memories.** The decision prompt lists the 30 newest episodes, so older
  memories cannot influence the decision to search.
- **Extraction is prompt-dependent.** Borderline splits and event types can be wrong; the grounding
  check is lexical, not a truth check.
- **Single user, no auth.** Do not expose the Streamlit server publicly.

[`docs/AUDIT.md`](docs/AUDIT.md) lists every defect found, with file and line references. Being precise
about these is part of the project.

## 11. Documentation

| Document | Read it when |
|---|---|
| [`docs/PROJECT_GUIDE.md`](docs/PROJECT_GUIDE.md) | You are new and want the full beginner walkthrough (19 chapters). |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | You want the design, data flow, and tradeoffs in one sitting. |
| [`docs/BENCHMARK_GUIDE.md`](docs/BENCHMARK_GUIDE.md) | You want to understand or extend the metrics. |
| [`docs/RESULTS.md`](docs/RESULTS.md) | You want the recorded numbers and what they do and do not prove. |
| [`docs/AUDIT.md`](docs/AUDIT.md) | You want the technical defects and where they live. |

## 12. Data and privacy

All inference is local. The database, `.env`, and virtual environment are git-ignored, so cloning the
repository gives you no conversations and no credentials. The demo data is fictional and lives in
`DEMO_MESSAGES` in `memory_engine.py`. There are no API keys anywhere in the project.
