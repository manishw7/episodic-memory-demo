# Working Mechanism — Start to Finish

This document walks through the complete life of a message, from the moment you type it to
the moment a memory is stored and later retrieved. Plain language, no jargon without an
explanation.

---

## 1. The big picture in one diagram

```
            ┌──────────────────────────────┐
            │  Streamlit page (app.py)     │  ← what you see
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

Two models, one database, one app. The app only renders and orchestrates; all rules live
in `memory_engine.py`.

## 2. One turn, step by step

### Step 1 — You type a message

You press Enter in the Chat box. The text is your question or statement.

### Step 2 — The message is stored first

Before anything else, the raw message is written to the `messages` table with an ID and
a timestamp. This is **provenance**: every later memory can point back to the exact
sentence that produced it.

### Step 3 — The engine answers you

`handle_turn(question, history, retrieval_enabled=...)` runs:

1. **Route (decide).** The chat model is asked: "Does this question need the archive?"
   It returns `{"needs_memory": true/false, "search_query": "..."}`. If the model fails,
   the app falls back to searching.
2. **Retrieve.** If needed, your question is embedded into a 768-dimension vector. That
   vector is compared (cosine similarity) with every stored episode that is active or
   completed. Matches above a floor (0.30) are kept, top 4.
3. **Answer.** The chat model is given your question plus the retrieved evidence only.
   It must answer from that evidence, or abstain ("the records do not establish that").
   Earlier assistant turns are stripped out so a deleted memory cannot leak back in.

You see the answer immediately. Under it you can open **Retrieval details** to see the
decision, the rewritten query, the episode IDs and scores, the source message IDs, and
the exact evidence text.

### Step 4 — Memory creation (automatic, in the background)

After the answer is shown, `form_memories` runs on the new messages:

1. **Which messages are new?** Only messages not yet in `formed_messages`. This makes the
   writer idempotent — it never processes the same message twice.
2. **Greeting shortcut.** If the turn is just "hi" or "thanks", it is skipped.
3. **Prompt assembly.** The chat model is given the new messages plus a compact list of
   the memories already known, and asked to extract episodes as JSON.
4. **Validation.** Each candidate is checked against a schema (title, type, summary,
   facts, people, dates, outcome, source IDs). Bad ones are rejected.
5. **Source check.** Every fact must cite message IDs that exist.
6. **Grounding check.** A fact's content words must actually appear in its sources
   (lexical overlap ≥ 0.35). This blocks invented details.
7. **Embedding.** Each accepted episode is turned into a vector.
8. **Deduplication.** If the new episode is very similar (≥ 0.90) to an existing one,
   it is treated as a restatement, not new information.
9. **Lifecycle.** A later outcome closes a task; a cancelled task is cancelled; a changed
   value supersedes the old memory. (See section 6.)
10. **Store.** The episode and an audit event are written to SQLite. `formed_messages`
    is updated.

### Step 5 — You see the result

The sidebar shows "Memory writer: stored N new episode(s)" or "nothing new to store".
In the Memory Map, the new memory appears with a halo for 30 seconds.

## 3. Memory formation in detail

### What is an episode?

A memory is not a message. It is a structured record:

- `title` — short name, e.g. "Ravi's retrieval experiment deadline"
- `event_type` — one of: preference, decision, project_update, task, outcome, goal
- `event_time` — when the event happened (not when it was written)
- `summary` — one sentence
- `facts` — list of self-contained statements
- `participants` — people involved (never speaker roles like "user" unless it is the
  user's own preference)
- `outcome` — result, if known
- `source_message_ids` — the original messages that prove it
- `status` — active / done / superseded / cancelled
- `superseded_by`, `change_reason` — link to the newer memory that replaced it
- `embedding` — the meaning vector

### Deduplication (`consolidate_duplicates`)

Runs automatically after every write. Two memories merge if:

- same event type,
- participants overlap,
- same numbers,
- **and** either the embeddings are very close (≥ 0.90) **or** the titles match (≥ 0.45)
  **and** the content overlaps (≥ 0.35).

The richer memory is kept; the other is removed with an audit event.

Two important fixes were added:

- Speaker roles (`user`, `assistant`, `system`) are **ignored** when matching participants.
  Otherwise every memory looked like it shared the "user" participant.
- Title-based merging now **requires content overlap**, so generic titles like
  "Project X definition" do not merge across projects.

### Lifecycle (`_apply_lifecycle`)

When a new memory arrives, the system links it to an existing one if the same people and
event are involved and the similarity is high enough:

- A task that later gets an outcome → the task becomes **done** and points to the outcome.
- A task that is cancelled → becomes **cancelled**.
- A value that changes → the old one becomes **superseded** and points to the new one.

Old versions are never silently deleted. They stay in the table with `status` and
`superseded_by`, and appear in the audit trail.

## 4. Retrieval and answering

- `decide`: the model returns `{"needs_memory": bool, "search_query": str}`. Failures
  fall back to searching.
- `retrieve`: embeds the query, compares with active + done episodes, floor 0.30, top 4.
  Superseded and cancelled memories are excluded from retrieval.
- `answer`: uses only the retrieved evidence. The assistant's own earlier messages are
  stripped from the history so a deleted memory cannot leak back. If nothing matches, it
  abstains.

## 5. The Memory Map (live picture)

The map is **not** a stored diagram. It is derived at render time from:

- memory nodes (one per episode),
- lifecycle edges (superseded → replacement, coloured by state),
- similarity edges (cosine ≥ 0.65, max 2 per node, grey),
- person bridge hubs (people appearing in more than one project, purple diamonds),
- project centroids (labels with counts).

Positions come from a PCA projection of the embedding vectors. The basis is computed
once and stored in session state, so existing dots **do not move** when a new memory is
added. New dots land near their neighbours.

Hovering a dot shows its title, project, state, people, learned date, and summary.
Searching lights up matching dots with a blue ring and shows scores on the right.
A write adds a halo that lasts 30 seconds and a live-feed entry.

## 6. The Time Machine (history)

The archive's history is rebuilt from `memory_events`. For any chosen date:

1. Sort all events by time.
2. Replay them in order: `created` → active, `done` / `cancelled` / `superseded` → that
   state, `deleted` → removed.
3. Snapshot the state at the end of that day.

The result is: counts, a change list for that day, and the full list of memories that
existed on that day, grouped by project. The stepped area chart shows the whole history.

## 7. Live writes (demo mode)

In demo mode, the sidebar buttons run the **real** extractor on a fresh standalone
conversation:

- `incremental=False` is used because incremental extraction appends the whole known
  memory list to the prompt, and with a large archive the model stops extracting novel
  facts.
- A fresh conversation avoids polluting the existing archive's conversations.
- The PCA basis is cached, so existing dots stay put.

Each write updates the map, the counts, and the live feed immediately.

## 8. Data flow summary

```
you type → message stored → decide → retrieve → answer shown
                                        ↓
                              form_memories (new messages only)
                                        ↓
                              validate → ground → embed → dedupe → lifecycle
                                        ↓
                              SQLite (episodes + memory_events)
                                        ↓
                              Map / Time Machine re-derive the view
```

## 9. Key constants (all in `memory_engine.py`)

| Constant | Value | Purpose |
|---|---:|---|
| `DUPLICATE_SIMILARITY` | 0.90 | Treat a new episode as a restatement. |
| `SUPERSEDE_SIMILARITY` | 0.72 | Replace an old value with a newer similar one. |
| `LINK_SIMILARITY` | 0.45 | Link an outcome/cancellation to the open task. |
| `GROUNDING_MIN_OVERLAP` | 0.35 | Reject facts whose words barely appear in sources. |
| `SIMILARITY_FLOOR` (map) | 0.65 | Minimum similarity for a grey "related" line. |
| `MEMORY_MIN_SIMILARITY` | 0.30 | Minimum score for retrieval evidence. |

## 10. Where to change what

| If you want to change… | Edit |
|---|---|
| What is remembered | `memory_engine.py` (prompts, schema, rules) |
| How it looks | `app.py`, `demo_views.py` |
| The demo story | `scripts/story.py`, then rebuild `demo.db` |
| Models or DB path | `.env` |
| Thresholds | constants in `memory_engine.py` |