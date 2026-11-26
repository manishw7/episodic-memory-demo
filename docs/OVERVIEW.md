# Episodic Memory — Overview (Top to Bottom)

This document explains the whole project in plain language, from the idea to the files,
to the screen, to the data. If you are new, read this first.

---

## 1. What this project is

**A chatbot with a notebook.**

A normal chatbot forgets everything when the chat closes. This one writes important
facts into a small database (a "notebook") and can look them up later — even in a brand
new conversation — or say plainly "the records do not establish that" when it does not
know.

Everything runs on your own computer through Ollama. No cloud, no API keys, no agent
framework, no vector database.

One-sentence version:

> *Read a conversation, decide what is worth remembering, store it as structured
> "episodes" in SQLite, and retrieve the right memory later — by meaning, not by keyword.*

## 2. What it can do

- Remember facts across separate chats (e.g. "We chose SQLite" on Monday, "Which DB?"
  on Wednesday).
- Answer using only the retrieved facts and show the evidence (episode ID, score, source
  message IDs, exact text).
- **Abstain** instead of guessing when the notebook has no answer.
- Update facts over time: a task can be completed, cancelled, or replaced by a newer
  value. Old versions are kept for inspection.
- Delete a memory and stop using it.
- Show a live, interactive **Memory Map** (constellation of connected memories).
- Travel through time with the **Time Machine** (reconstruct what it knew on any day).

## 3. The three rooms (views)

At the top of the page there is one switcher with three buttons:

| View | What it is |
|---|---|
| **Chat** | Talk to the bot. Every reply shows a "Retrieval details" expander with the evidence. |
| **Memory Map** | A live picture of every memory and how they connect. Add or delete memories and watch it change. |
| **Time Machine** | A timeline of the archive. Pick any date and see exactly what the bot knew then. |

## 4. The notebook (the data)

The notebook is a SQLite file. Two files exist:

- `memory.db` — your **real** notebook. Created when you use the app normally.
- `demo.db` — a **pretend** notebook with 50 ready-made memories. Used only with
  `./start.sh --demo`. `memory.db` is never opened in demo mode.

The notebook has a small number of tables. The important ones:

| Table | What it holds |
|---|---|
| `episodes` | The saved memories. Each has a title, type, summary, facts, people, dates, status, and the IDs of the original messages. |
| `messages` | Every user/assistant message, with IDs and timestamps (provenance). |
| `memory_events` | The audit trail. Every memory created, completed, cancelled, replaced, or deleted. |
| `conversations` | One row per chat. |
| `turn_traces` | One row per turn: question, answer, decision, query, retrieved episodes, score, latency. |
| `formed_messages` | Which messages have already been processed into memories (so nothing is extracted twice). |

## 5. The brain (`memory_engine.py`)

One file contains all the logic. Its main jobs:

- `add_message` — store a raw message.
- `form_memories` — read new messages, ask the chat model to extract episodes, validate
  them, embed them, deduplicate, apply lifecycle, store them.
- `decide` — ask the model whether a question needs the archive at all.
- `retrieve` — embed the question, compare with stored episodes by cosine similarity,
  keep the best ones above a floor.
- `answer` — answer using only the retrieved evidence, or abstain.
- `delete_episode`, `consolidate_duplicates`, `list_events`, `list_episodes` — helpers.

The app (`app.py`) only renders and orchestrates. It contains no memory rules.

## 6. The models (both local, via Ollama)

| Model | Role |
|---|---|
| `qwen3.5:9b` | The chat model: extraction, routing, answering. |
| `embeddinggemma` | The embedding model: turns text into 768-dimension vectors for similarity. |

## 7. How one turn works (short version)

1. You type a message. It is stored first.
2. The bot decides whether it needs the archive.
3. If yes, it embeds your question and searches the notebook.
4. It answers using only the retrieved evidence (or abstains).
5. In the background, new messages are extracted into memories and saved automatically.

No "save" button exists. See `docs/WORKING_MECHANISM.md` for the full version.

## 8. The prebuilt demo archive (`demo.db`)

A synthetic eight-week story: **50 memories across three projects** — Atlas (18), Beacon
(17), Cinder (15) — with shared people linking the clusters. Every lifecycle state
appears. It is produced once by the **real** extraction pipeline and committed, so the
demo looks identical everywhere and starts instantly. See `docs/DEMO_AND_VIEWS.md`.

## 9. Numbers at a glance

- 50 demo memories, 17 sessions, 50 messages, 68 audit events
- 13 people, 3 projects, 69 links on the map
- 29 fast tests (no Ollama needed)
- 51-case benchmark, 17/17 formation matched, 100% abstention on unanswerable
- 8 documentation files in `docs/`

## 10. Where to look first

| If you want to… | Read |
|---|---|
| Understand the whole system simply | `docs/OVERVIEW.md` (this file) |
| See the complete mechanism step by step | `docs/WORKING_MECHANISM.md` |
| Hand off the project to someone | `docs/HANDOFF.md` |
| Run the app or the demo | `docs/OPERATIONS.md` |
| Understand the Memory Map / Time Machine | `docs/DEMO_AND_VIEWS.md` |
| See what was changed recently | `docs/DEVELOPMENT_HISTORY.md` |
| See what to improve next | `docs/IMPROVEMENTS.md` |
| Understand every metric | `docs/BENCHMARK_GUIDE.md` |
| Read the recorded numbers | `docs/RESULTS.md` |
| Find known defects | `docs/AUDIT.md` |

## 11. Simple glossary

- **Episode / memory:** one saved fact with details.
- **State:** active / completed / replaced / cancelled.
- **Superseded:** replaced by a newer memory; old one kept for history.
- **Embedding:** meaning fingerprint.
- **Retrieval:** searching by meaning.
- **Evidence:** the saved text shown under an answer.
- **Abstain:** saying "the records do not establish that".
- **Provenance:** which original messages produced a memory.
- **Lifecycle:** how a memory changes state over time.
- **Fragment:** a Streamlit block that refreshes on its own (we removed the auto-refresh
  from the map to keep the projector view still).
- **Demo mode:** `./start.sh --demo` — uses `demo.db`, never `memory.db`.