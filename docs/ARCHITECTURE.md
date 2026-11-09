# Architecture

A short, accurate description of how the system is built and why. For the beginner version, read
[`PROJECT_GUIDE.md`](PROJECT_GUIDE.md). For the defects, read [`AUDIT.md`](AUDIT.md).

---

## 1. What the system is

Three Python files at runtime, one SQLite file, one local model server:

| File | Lines | Responsibility |
|---|---:|---|
| `app.py` | 256 | Rendering and orchestration only. No memory rules. |
| `memory_engine.py` | 1,332 | Prompts, schema, database, extraction, lifecycle, retrieval, answering. |
| `evaluate.py` | 950 | Benchmark runner. Not used by the app. |

Ollama serves two models with different jobs:

- **`qwen3.5:9b`** (chat) — reads and writes text: extract episodes, decide whether to search,
  write the answer.
- **`embeddinggemma`** (embeddings) — converts text into 768 numbers so meaning can be compared.

The chat model cannot produce reliable meaning-vectors, and the embedding model cannot write a
sentence. Both are required.

**Non-goals:** multi-user support, cloud inference, an agent framework, a vector database, Docker,
authentication. Those are deliberate omissions for a single-user research prototype, not oversights.

---

## 2. One turn, end to end

```text
user types
   │
   ▼
app.py: add_message()              → messages row
   │
   ▼
handle_turn()                      (memory_engine.py:1238)
   │
   ├─ retrieval disabled?  → answer with an explicit "archive unavailable" note
   ├─ trivial turn?        → answer directly, no model routing
   │
   ├─ decide()              chat model → {"needs_memory": bool, "search_query": str}
   │     └─ on any failure: search anyway (safe default)
   │
   ├─ retrieve()            query → 768-d vector → cosine vs every active/done episode
   │     └─ filter < 0.30, sort desc, take top 4, format evidence blocks
   │
   └─ answer()              ANSWER_SYSTEM + evidence + last 8 *user* messages + question
         └─ assistant history is stripped so deleted memories cannot leak back in
   │
   ▼
app.py: add_message() (assistant)  → messages row
app.py: save_trace()               → turn_traces row (question, answer, query, scores, evidence)
   │
   ▼
app.py: form_memories(incremental=True)
   │
   ├─ messages not yet in formed_messages
   ├─ trivial? skip the model entirely
   ├─ split long messages (> 6,000 chars), batch
   ├─ chat model + EPISODE_SCHEMA (structured JSON)
   ├─ Pydantic EpisodeCandidate validation
   ├─ source IDs must exist and include ≥ 1 user message
   ├─ lexical grounding check (≥ 35% content-word overlap)
   ├─ embed accepted episodes
   ├─ skip exact restatements (≥ 0.90, same type, same numbers)
   ├─ insert + apply lifecycle + consolidate duplicates
   └─ mark messages formed
```

Two things are worth noticing:

- **The reply is rendered before extraction starts.** The spinner says "Saving new memories…" and the
  user is never blocked on a second model call to read the answer.
- **Extraction is incremental and retryable.** `formed_messages` records what was processed. A failed
  batch is not marked, so the next turn tries again.

---

## 3. Data model

```text
conversations ──1──∞── messages
      │                    │
      │                    │  (episodes cite message IDs by value)
      └──1──∞── episodes ──┘
                    │
                    ├──∞── memory_events     (audit trail, no FK)
                    └──∞── turn_traces       (via conversation_id)

formed_messages   (independent bookkeeping)
```

| Table | One row is | Key columns |
|---|---|---|
| `conversations` | A chat session. | `conversation_id`, `status` |
| `messages` | One raw message. | `message_id`, `conversation_id`, `role`, `content` |
| `episodes` | One memory. | `episode_id`, `event_type`, `status`, `facts` (JSON), `source_message_ids` (JSON), `embedding` (JSON), `superseded_by` |
| `turn_traces` | One question/answer. | `question`, `answer`, `details` (JSON: query, scores, evidence), `latency_ms` |
| `memory_events` | One state change. | `episode_id`, `action`, `detail` |
| `formed_messages` | One processed message. | `message_id`, `formed_at` |

**Provenance chain:** `episodes.source_conversation_id` identifies the chat;
`episodes.source_message_ids` lists the exact `messages.message_id` rows that justify the memory.

**There are no enforced foreign keys on `episodes`.** Links are by value. This keeps the schema easy
to inspect with `sqlite3`, at the cost of orphan rows after a delete. See [`AUDIT.md`](AUDIT.md).

Embeddings are JSON arrays of 768 floats, stored next to `embedding_model` and `embedding_dim`.
Similarity is computed in NumPy at query time. There is no vector index.

---

## 4. Memory formation

`form_memories` (`memory_engine.py:802`) is the most important function. It applies a sequence of
gates; each gate can reject an episode without killing the batch.

| Gate | Rule | On failure |
|---|---|---|
| Trivial turn | Exact match against `TRIVIAL_PHRASES` (`hi`, `thanks`, `ok`, …) | Skip models, mark formed, store nothing. |
| Schema | `EpisodeCandidate` — allowed `event_type`, non-empty facts and sources | Skip that episode, keep the rest. |
| Source IDs | Every ID must exist in the transcript that was sent | Skip the episode. |
| User evidence | At least one cited message must be from the user | Skip the episode. Assistant replies are context, never evidence. |
| Grounding | ≥ 35% of a fact's content words must appear in its cited user messages | Skip the episode. |
| Duplicate | Same type, compatible numbers, cosine ≥ 0.90 | Do not store a second copy. |
| Lifecycle | Compare with the best older match | Update the older memory's status instead of leaving both current. |

The extraction prompt (`EXTRACTION_SYSTEM`, `:26`) is where most of the judgement lives. It asks for
episodes of six durable kinds — decisions, commitments, outcomes, blockers/status changes,
preferences, goals — and explicitly rejects greetings, hypotheticals, questions, and the assistant's
own unaccepted advice. It also enforces **one episode per topic**: a profile becomes separate
education, hardware, and health memories rather than one giant record whose embedding is an average
of everything.

Extraction runs at `temperature=0` with `top_k=1`. Without the `top_k` pin, the same profile produced
3 episodes on one run and 14 on the next. Reproducibility matters for both the benchmark and a live
demo.

`event_time` is free text, stored and displayed, never parsed.

---

## 5. Retrieval and answering

**Routing** (`decide`, `:1189`) is a separate model call. It sees the last few turns, the new
message, and a compact catalog of up to 30 episodes with their first facts. Facts are included
because a title like "User background summary" hides the laptop detail that should trigger a search.

**Retrieval** (`retrieve`, `:1148`) embeds the rewritten query, loads every `active` or `done`
episode with its vector, computes cosine similarity, applies `min_similarity` (default 0.30), sorts,
and keeps `top_k` (default 4). Superseded and cancelled memories are never candidates.

**Answering** (`answer`, `:1213`) sends the evidence blocks only. Each block carries the episode ID,
event time, summary, facts, outcome, sources, and score. The prompt forbids inventing dates or people,
requires abstention when the evidence does not establish an answer, and says a conflict is only a
conflict when two memories assign different values to the same attribute — a past request or an
earlier gap in knowledge is background, not a contradiction.

The prompt is a rule, not an enforcement mechanism. The code-level guarantee is narrower: deleted
episodes cannot be retrieved, and assistant history is stripped from the answer prompt.

---

## 6. Lifecycle

| Status | Meaning | Retrieved? |
|---|---|---|
| `active` | Current fact, open task, standing preference | Yes |
| `done` | Completed task/goal — history | Yes |
| `superseded` | Replaced by a newer value | No |
| `cancelled` | Explicitly called off | No |

`_apply_lifecycle` (`:992`) finds the single best older match (≥ 0.45, with participant overlap) and
applies three rules:

1. New `outcome` + old open `task`/`goal` → old becomes `done`.
2. Cancel language ("cancelled", "no longer", "won't", "dropped") + old open task → `cancelled`.
3. Both replaceable types and similarity ≥ 0.72 → old becomes `superseded`, pointing at the new row.

`consolidate_duplicates` (`:1059`) runs after every save and merges accidental duplicates, keeping the
memory with more dates and facts.

History is kept rather than overwritten because "what is true now" and "what happened then" are
different questions. Deleting the old deadline would make "when was it originally due?" unanswerable.

Known limits: only one older memory is updated per new episode; similarity is the only signal;
contradictions between two active memories are not resolved; there is no edit operation.

---

## 7. Design decisions and tradeoffs

| Decision | Why | Cost |
|---|---|---|
| Episodes, not raw messages | Retrieval works on meaning-dense records. | Extraction can lose nuance. |
| Local models only | No keys, no cloud, no data leaves the machine. | Slow on CPU; model quality is a ceiling. |
| SQLite, JSON vectors, NumPy scan | Inspectable with one command; no infrastructure. | Linear scan; no vector index. |
| Exact cosine, single score | Simple to explain and debug. | No hybrid lexical signal, no reranking. |
| Structured JSON output + Pydantic | A malformed model reply cannot corrupt the database. | Tight schema can reject unusual but valid events. |
| Lexical grounding check | Cheap backstop against invented facts. | Not semantic entailment; can miss paraphrases. |
| Keep history, mark status | Past questions remain answerable and auditable. | More rows; retrieval must filter correctly. |
| Automatic writing | No button to forget to press. | A bad extraction is stored before you see it. |
| Prompt-only contradiction handling | Keeps the prototype small. | Benchmark `c4` fails. This is the biggest gap. |

---

## 8. Where to change what

| Goal | Edit |
|---|---|
| What gets remembered | `EXTRACTION_SYSTEM` (`:26`) |
| Whether to search | `DECISION_SYSTEM` (`:80`) / `decide` (`:1189`) |
| How answers are phrased | `ANSWER_SYSTEM` (`:105`) / `answer` (`:1213`) |
| Ranking or thresholds | `retrieve` (`:1148`), `Settings` (`:186`) |
| Lifecycle rules | `_apply_lifecycle` (`:992`) |
| Duplicate handling | `_find_existing_duplicate` (`:973`), `consolidate_duplicates` (`:1059`) |
| Database schema | `_init_db` (`:636`) |
| UI behaviour | `app.py` |
| Test cases | `benchmark/*.json` |

The restart rule: after editing the engine, **restart Streamlit**. A cached module once produced
`AttributeError: 'MemoryEngine' object has no attribute 'list_traces'`.
