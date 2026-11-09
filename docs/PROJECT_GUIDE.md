# The Episodic Memory Project — A Beginner's Handbook

**For:** a new intern who has never seen this project.
**Written:** 2026-10-30
**Verified against:** the code in `episodic-memory-demo/`, not against the README alone.

---

## How to read this handbook

Read it in order the first time. Every chapter builds on the one before.

Three symbols are used throughout:

- 🧠 **Idea** — the concept, in plain words.
- 🔍 **In the code** — where it actually happens, with a file and line number.
- ⚠️ **Be careful** — something that looks one way but behaves another.

Anything I could not confirm in the code is marked **Cannot verify**.

---

# 1. The story: why this project exists

## 1.1 A chatbot with no memory

Imagine you install a chat app. On Monday you say:

> "Our team decided to use SQLite for the project database."

The chatbot replies: "Got it."

On Tuesday you talk about something else — lunch, the weather.

On Wednesday you open a brand new chat and ask:

> "Which database did we select for the project?"

The chatbot answers: "I don't have any information about your project."

Nothing is broken. That is simply how most chatbots work.

## 1.2 Why ordinary chatbots forget

A chatbot is a program that talks to a **Large Language Model** — an LLM. An LLM is a very large
pattern-matching engine trained on text. It is good at language. It is not a database.

Each time you send a message, the app sends the model a bundle of text and asks for a reply. That
bundle is called the **context window** — the model's short-term working space. When the chat ends,
the bundle is discarded. The model itself does not change.

So the model "forgets" because nothing was ever written down. It has no notebook.

## 1.3 The obvious bad fix: save everything

The first idea is: save every message forever, and paste them all back in when needed.

This fails for three reasons:

1. **Space.** The context window is limited. You cannot paste a year of chat into every question.
2. **Noise.** Most messages are greetings, jokes, and half-sentences. Pasting them makes the useful
   fact harder to find.
3. **Wrong shape.** A conversation contains decisions, tasks, opinions, and small talk mixed
   together. The model needs the *decision*, not forty messages surrounding it.

So we need two things: **decide what is worth keeping**, and **find it again later**.

## 1.4 What an AI agent is

An **agent** is a program that does more than answer once. It has a goal, it takes steps, and it
uses tools.

In this project the agent is small but real. On every message it:

1. decides whether it needs to look something up,
2. looks it up,
3. answers using what it found,
4. writes down anything new that is worth remembering.

That loop — decide, act, record — is what makes it an agent rather than a chat window.

## 1.5 What memory means for an agent

**Memory** is stored information that survives past the current moment.

Researchers usually split agent memory into a few kinds:

| Kind | Plain meaning | Example in this project |
|---|---|---|
| Working memory | What is in front of you right now | The last few messages of the current chat |
| Episodic memory | Things that happened, with time and people | "On 3 October the team chose SQLite" |
| Semantic memory | General facts and preferences | "The user prefers bullet points" |
| Procedural memory | How to do a task | **Not implemented** |

This project is mainly about **episodic memory** — memories of events.

## 1.6 What episodic memory is

**Episodic memory** is memory for specific episodes: what happened, when, who was involved, and how
it turned out.

In humans: "Last Tuesday I missed the bus and arrived late to the dentist."

In this project: an **episode** is one structured record such as:

> **Title:** Local prototype storage decision
> **Type:** decision
> **When:** 2025-10-03
> **People:** team
> **Facts:** The team chose SQLite for the local prototype because it is single-user and offline-first.
> **Outcome:** (none — a decision is not a completed task)

An episode is not a chat message. It is a *cleaned-up summary of something that happened*, with
proof of where it came from.

## 1.7 What this application should be able to do

By the end of a session with this demo, you should be able to:

1. Tell the assistant something durable on Monday.
2. Start a completely new conversation on Wednesday.
3. Ask an indirect question.
4. Get an answer that cites the Monday memory.
5. Open the evidence panel and see exactly which memory and which original message were used.
6. Delete that memory and watch the answer stop working.

That last step matters. A memory you cannot inspect and cannot delete is not really yours.

## 1.8 The one-sentence version

> This project gives a local chatbot a notebook: it writes down important events as structured
> memories, finds them again by meaning, and answers only from what it actually wrote down.

---

# 2. What the project actually is

Before the tour, here is the honest summary.

It is **one Streamlit web page** on top of **one Python engine** on top of **one SQLite file**, using
**one local model server**.

| Part | What it is |
|---|---|
| `app.py` | The web page. 256 lines. No memory logic. |
| `memory_engine.py` | The brain. 1,332 lines. Prompts, database, extraction, retrieval, answering. |
| `evaluate.py` | The measuring tool. 950 lines. Runs 51 test cases. |
| `test_memory.py` | 22 fast tests with a fake model. |
| `test_evaluate.py` | 5 tests for the scoring maths. |
| `memory.db` | The notebook. One SQLite file. |
| `benchmark/*.json` | Gold-answer test data. |

It runs entirely on your own machine. There is no cloud service, no API key, and no account.

🔍 **In the code:** the only network address anywhere in the Python source is
`http://127.0.0.1:11434` (`memory_engine.py:187`), which is your own computer talking to itself.

⚠️ **Be careful:** "local" here means "the model runs on your Mac". It does not mean "small". The
chat model is about 6.6 GB.

---

# 3. The technologies, one at a time

For each tool: what it is, why we need it, what it does here, and what breaks without it.

## 3.1 Python

**What:** the programming language everything is written in.
**Why:** it has good libraries for AI, databases, and web pages.
**Here:** all four `.py` files.
**Without it:** nothing runs.

Version: the README says Python 3.10 or newer, tested on 3.12. **Cannot verify** your exact version
from the repository alone.

## 3.2 Streamlit

**What:** a Python library that turns a script into a web page. You write `st.chat_input(...)` and a
text box appears in a browser.
**Why:** we want to *show* the memory working, not just print to a terminal.
**Here:** `app.py` uses `st.chat_input`, `st.sidebar`, `st.expander`, `st.spinner`, `st.session_state`.
**Without it:** you would have to use the engine from a Python shell. That works
(`memory_engine.integration_check()`), but you cannot see the archive or the evidence.

⚠️ **Be careful:** Streamlit re-runs the whole script top-to-bottom on every interaction. That is why
the code keeps state in `st.session_state` and caches the engine with `@st.cache_resource`
(`app.py:16`).

## 3.3 SQLite

**What:** a database that lives in a single file. No server to start. You can copy it, back it up, or
delete it.
**Why:** memories must survive restarts, and we want to inspect them with normal tools.
**Here:** `memory.db`, six tables, all access through `sqlite3` in `memory_engine.py`.
**Without it:** memories would vanish when the app closes.

## 3.4 Ollama

**What:** a program that runs large language models on your own computer and exposes them over a
simple HTTP address.
**Why:** we want local inference, no cloud, no keys.
**Here:** `memory_engine.py:270` (`OllamaClient`) wraps the `ollama` Python package and points at
`127.0.0.1:11434`.
**Without it:** every model call fails with a clear `OllamaError`. The app shows the message; it does
**not** silently switch to a cloud provider.

🔍 **In the code:** `OllamaClient.chat` (`:279`) and `OllamaClient.embed` (`:305`). Both raise an
error on failure. There is no fallback path anywhere.

## 3.5 Qwen (`qwen3.5:9b`)

**What:** a **chat model** — a large language model that reads text and writes text.
**Why:** we need something that understands language well enough to summarise a conversation, judge
whether a question is about the past, and write a clear answer.
**Here:** it does **four different jobs**, all with the same model but different prompts:
1. extraction (turn a conversation into episodes),
2. routing (does this question need the archive?),
3. answering (write the reply),
4. and nothing else — it does *not* make embeddings.
**Without it:** no memories could be created and no answers written.

## 3.6 EmbeddingGemma

**What:** an **embedding model** — a model that converts text into a list of numbers that represents
its *meaning*.
**Why:** we need to find a memory by meaning, not by exact words. "Which database did we pick?" and
"we chose SQLite" share almost no words, but they mean related things.
**Here:** `Settings.embed_model`, used in `OllamaClient.embed` (`:305`). Produces **768 numbers** per
piece of text in this environment.
**Without it:** retrieval would collapse to keyword search, and paraphrased questions would fail.

## 3.7 The difference between the two models

This is the single most important distinction in the project.

| | Chat model (Qwen) | Embedding model (EmbeddingGemma) |
|---|---|---|
| Input | text | text |
| Output | **text** (a sentence, JSON, an answer) | **768 numbers** |
| Good at | understanding, reasoning, writing | measuring meaning-similarity |
| Used for | extraction, routing, answering | finding memories |
| Analogy | a librarian who reads and explains | a librarian who files books by topic |

You cannot ask the embedding model "which database did we choose?" and get a sentence back. You
cannot ask the chat model to give you a reliable 768-number meaning vector. They do different jobs.

## 3.8 NumPy

**What:** a Python library for fast maths on lists of numbers.
**Why:** comparing 768-number vectors by hand would be slow and ugly.
**Here:** `cosine()` (`:351`) uses `np.dot` and `np.linalg.norm`; vectors are loaded as
`np.asarray(...)` in `retrieve` (`:1153–1168`).
**Without it:** you would rewrite a few lines of arithmetic. Not fatal, just slower and noisier.

⚠️ **Be careful:** NumPy is doing the *comparison*. It is not storing anything and it is not a vector
database. The vectors live in SQLite as text.

## 3.9 Pydantic

**What:** a Python library that checks data against a declared shape.
**Why:** the model returns JSON, and models sometimes return the wrong fields, wrong types, or
missing values. We must reject bad data before it reaches the database.
**Here:** `EpisodeCandidate` (`:206`) declares exactly what an episode may contain. `model_validate`
either returns a clean object or raises.
**Without it:** malformed memories would be written to the database and would break retrieval later.

## 3.10 python-dotenv

**What:** reads a `.env` file into environment variables.
**Why:** configuration (model names, database path, thresholds) should not be hard-coded.
**Here:** `load_dotenv()` at the top of `memory_engine.py`, read by `Settings.from_env()` (`:195`).
**Without it:** you would edit Python source to change a model name.

## 3.11 pytest

**What:** a test runner. You write functions starting with `test_`, and it runs them.
**Why:** to prove behaviour still works after a change.
**Here:** `test_memory.py`, `test_evaluate.py`.
**Without it:** you would test by hand, forget, and break things.

## 3.12 What is deliberately **not** used

To avoid confusion, these are **not** in the project:

- No LangChain, LangGraph, or agent framework.
- No vector database (no Pinecone, Chroma, FAISS, Qdrant).
- No graph database.
- No Docker.
- No authentication or user accounts.
- No cloud LLM provider.
- No web framework other than Streamlit.

If you read about these elsewhere, they are not part of this codebase.

---

# 4. Architecture and folder structure

## 4.1 The picture

```text
                    ┌──────────────────────────────┐
                    │            User              │
                    └──────────────┬───────────────┘
                                   │ types a message
                                   ▼
                    ┌──────────────────────────────┐
                    │   Streamlit page (app.py)    │
                    │  chat, sidebar, evidence     │
                    └──────────────┬───────────────┘
                                   │ calls
                                   ▼
        ┌──────────────────────────────────────────────────┐
        │        MemoryEngine (memory_engine.py)           │
        │                                                  │
        │  handle_turn ──► decide ──► retrieve ──► answer  │
        │       │                                          │
        │       └────────► form_memories ──► store         │
        └───────┬──────────────────┬───────────────┬───────┘
                │                  │               │
                ▼                  ▼               ▼
        ┌───────────────┐  ┌───────────────┐  ┌─────────────────┐
        │    SQLite     │  │  Ollama chat  │  │  Ollama embed   │
        │  memory.db    │  │ qwen3.5:9b    │  │ embeddinggemma  │
        │  6 tables     │  │ text → text   │  │ text → 768 nums │
        └───────────────┘  └───────────────┘  └─────────────────┘
```

## 4.2 The same picture as jobs in an office

| Component | Office analogy |
|---|---|
| Streamlit page | The reception desk. Where you talk and where you can open the filing cabinet. |
| MemoryEngine | The assistant who decides what to do. |
| Ollama | The building where the specialists sit. |
| Qwen | The writer. Reads, summarises, answers. |
| EmbeddingGemma | The filing clerk. Does not explain anything, just writes a topic code for every page. |
| SQLite | The filing cabinet. |

## 4.3 The folder structure

```text
episodic-memory-demo/
├── app.py                     Web page. Buttons, chat, evidence panels.
├── memory_engine.py           Everything else: prompts, DB, extraction, retrieval, answering.
├── evaluate.py                51-case benchmark runner and report writer.
├── test_memory.py             22 fast tests (fake model, no Ollama).
├── test_evaluate.py           5 tests for the scoring maths.
├── benchmark/
│   ├── formation.json         13 cases: what should be stored
│   ├── retrieval.json         13 cases: which memory should win
│   ├── lifecycle.json          6 cases: how memories change over time
│   ├── answering.json         10 cases: answering from evidence
│   ├── causal.json             4 cases: is memory really causing the answer?
│   └── stress.json             5 cases: restart, deletion, injection, flood, empty
├── memory.db                  Your live archive. Gitignored.
├── memory.db.before-block2.bak  Backup from an earlier refactor. Gitignored.
├── eval_results/
│   ├── eval_report.md         Human-readable benchmark report.
│   └── raw.json               Every case, score, ranking and answer.
├── docs/
│   ├── PROJECT_GUIDE.md       This handbook.
│   ├── ARCHITECTURE.md        Short design and data-flow reference.
│   ├── BENCHMARK_GUIDE.md     Metrics explained in plain English.
│   ├── RESULTS.md             The recorded benchmark run and its caveats.
│   └── AUDIT.md               A line-by-line technical audit.
├── .env                       Your settings. Gitignored.
├── .env.example               Safe template, committed.
├── requirements.txt           Python dependencies.
├── Makefile                   Shortcuts: make run / test / eval.
└── README.md                  Setup, demo, and repository map.
```

## 4.4 What each file is responsible for

| File | Job | Used at runtime? |
|---|---|---|
| `memory_engine.py` | All logic | Yes |
| `app.py` | Interface only | Yes |
| `evaluate.py` | Measurement | Only when you run it |
| `test_memory.py` | Correctness checks | Only under pytest |
| `test_evaluate.py` | Maths checks | Only under pytest |
| `benchmark/*.json` | Test inputs and gold answers | Only during evaluation |
| `memory.db` | The archive | Yes |

⚠️ **Be careful:** `app.py` contains no memory rules at all. If you want to change *what* is
remembered, you edit `memory_engine.py`, never `app.py`.

---

# 5. How a memory is created

This is the most important chapter. We will follow one message from keystroke to database row.

## 5.1 The example conversation

> **Monday, 09:00 — user:**
> "Project sync. We're building a local prototype for one user, offline-first. The team decided to
> use SQLite for storage because it fits that constraint."

This is the same shape as the demo data stored in `DEMO_MESSAGES` (`memory_engine.py:593`).

## 5.2 Step by step

### Step 1 — The user sends a message

They type into the chat box at the bottom of the page.

🔍 **In the code:** `app.py:222`
```python
elif prompt := st.chat_input("Message the assistant..."):
```

### Step 2 — The app stores the message first

Before any thinking happens, the raw text is written to SQLite.

🔍 **In the code:** `app.py:224` calls `engine.add_message(...)`, which inserts into the `messages`
table (`memory_engine.py:715`).

Why store it first? Because provenance depends on it. Later, an episode will point at this row by
its `message_id`. If the message were not saved, the memory would have nothing to cite.

### Step 3 — The engine answers the user

🔍 **In the code:** `app.py:229` calls `engine.handle_turn(...)`. That function is explained fully in
Chapter 8. In short: it decides whether to search, searches if needed, and writes a reply.

The reply is stored as an assistant message (`app.py:234`) and shown on screen (`app.py:248`).

⚠️ **Be careful:** the reply is rendered *before* memory saving starts, so you are not staring at a
blank screen. The spinner says "Saving new memories..." (`app.py:250`).

### Step 4 — Memory creation starts automatically

This is the key design decision: **there is no "Save to memory" button.**

🔍 **In the code:** `app.py:251`
```python
written, notes = engine.form_memories(
    st.session_state.conversation_id, incremental=True, end=False
)
```

`incremental=True` means "only look at messages I have not processed yet". `end=False` means "keep
this conversation open".

### Step 5 — Which messages are new?

The engine keeps a small table, `formed_messages`, listing every message already sent to extraction.

🔍 **In the code:** `_formed_message_ids` (`:784`) reads that table; `form_memories` (`:813–815`)
filters the conversation down to the new ones.

This is what stops the same turn being extracted twice. It also means a failed extraction can be
retried next turn (because the messages were never marked).

### Step 6 — The greeting shortcut

If the new messages are only greetings or acknowledgements, the model is never called.

🔍 **In the code:** `is_trivial_turn` (`:380`) checks each user message against a small set:
`hi, hello, hey, thanks, ok, yes, no, sure, bye, ...` (`TRIVIAL_PHRASES`, `:374`).

If everything matches, the engine marks the messages as formed and returns no memories. This saves
a model call on "thanks!".

⚠️ **Be careful:** the match is exact after lowercasing and stripping punctuation. "ok" matches.
"ok, thanks!" does not.

### Step 7 — The prompt is assembled

The engine builds a text block like this (simplified):

```text
Conversation transcript:

[NEW] [2025-10-03T09:00:00+00:00] user (message_id=demo-msg-001):
Project sync. We're building a local prototype for one user, offline-first.
The team decided to use SQLite for storage because it fits that constraint.

Extract durable episodic memories from the [NEW] messages only. ...
```

Two system-level prompts are involved:

1. `EXTRACTION_SYSTEM` (`:26`) — the rulebook, sent as the system message.
2. The transcript plus instructions — sent as the user message.

🔍 **In the code:** `form_memories` (`:865–874`).

### Step 8 — Long conversations are split

The model has a limit on how much text it can read at once (`num_ctx: 8192` tokens, set at
`:282`). If we send more, the model silently ignores the end. That would lose facts.

So messages longer than **6,000 characters** are cut into windows, and the windows are grouped into
batches that fit.

🔍 **In the code:** `MAX_EXTRACTION_CHARS = 6000` (`:445`), `split_long_messages` (`:448`),
`batch_messages` (`:461`).

The chunks keep the same `message_id`, so provenance still points at the right original message.

### Step 9 — The model is asked

🔍 **In the code:** `:870`

```python
raw = self.llm.chat(
    [{"role": "system", "content": EXTRACTION_SYSTEM},
     {"role": "user", "content": prompt}],
    json_mode=True, temperature=0.0, schema=EPISODE_SCHEMA,
)
```

Three things to notice:

- `temperature=0.0` and `top_k=1` mean "be deterministic". The same conversation should give the
  same episodes every time. (Ollama still samples at temperature 0 unless you force `top_k=1`; the
  code does this at `:283–287`.)
- `schema=EPISODE_SCHEMA` constrains the model's output to a known JSON shape. This is called
  **structured output**. It is much more reliable than asking nicely.
- The same chat model is used here as everywhere else.

### Step 10 — What the model must decide

The extraction prompt (`EXTRACTION_SYSTEM`, `:26–78`) is a list of rules. The important ones, in
plain language:

**Store these:**
- decisions and their reasons,
- commitments and assignments,
- completed outcomes,
- blockers and status changes,
- durable preferences (how you want to work or be answered),
- goals.

**Never store these:**
- greetings, thanks, small talk, weather, pleasantries,
- vague progress like "things are going well",
- hypotheticals like "we might" or "maybe later",
- questions the user asked (a question is not a fact),
- the assistant's advice, unless the user agreed to it.

**Shape rules:**
- One episode per distinct event. If one message contains three separate events, produce three
  episodes.
- A profile or a list of separate attributes becomes one episode **per topic** — education,
  hardware, health, goals. Not one giant episode.
- Rejected options and reasons are folded into the decision they explain.
- If nothing is worth remembering, return `{"episodes": []}`.

**Provenance rules:**
- `source_message_ids` may only contain IDs from **user** messages. Assistant messages are context,
  not evidence.
- `event_time` is when the *event* happened, not when the chat happened.
- `outcome` is null unless a result is actually established.

⚠️ **Be careful:** the last rule matters a lot. "Mira will finish the schema by 18 October" is a
`task` with `outcome: null`. "Mira finished the schema on 18 October" is an `outcome`.

### Step 11 — What comes back

```json
{
  "episodes": [
    {
      "title": "Local prototype storage decision",
      "event_type": "decision",
      "event_time": "2025-10-03",
      "summary": "The team chose SQLite for the local prototype because it is single-user and offline-first.",
      "participants": ["team"],
      "facts": [
        "The team chose SQLite for storage.",
        "The reason is that the prototype is single-user and offline-first."
      ],
      "outcome": null,
      "source_message_ids": ["demo-msg-001"]
    }
  ]
}
```

### Step 12 — Python checks the shape

🔍 **In the code:** `:893`

```python
candidate = EpisodeCandidate.model_validate(item)
```

If `event_type` is `"banana"`, or `facts` is a string instead of a list, or `title` is two characters
long, Pydantic raises an error and that episode is skipped with a note. The other episodes in the
same response are still processed.

### Step 13 — Python checks the sources

🔍 **In the code:** `validate_source_ids` (`:343`) and the user-source rule (`:895–899`).

Two checks:

1. Every ID in `source_message_ids` must exist in the batch we just sent. The model cannot invent
   `msg_999`.
2. At least one cited message must be a **user** message.

Why check? Because a model that cites nothing, or cites only its own previous reply, has no
evidence. We refuse those.

### Step 14 — Python checks the facts against the source

This is the **grounding check**, and it is the cleverest small guard in the project.

🔍 **In the code:** `ungrounded_fact` (`:430`), threshold `GROUNDING_MIN_OVERLAP = 0.35` (`:364`).

In plain words:

1. Take the facts the model produced.
2. Take the user messages it cited.
3. Remove common words ("the", "a", "of") and chop simple endings ("prefers" → "prefer").
4. For each fact, ask: what fraction of its content words appear in the sources?
5. If that fraction is below 35%, reject the **whole episode**.

Example:

| Fact | Source text | Overlap | Verdict |
|---|---|---|---|
| "The team chose SQLite for storage." | "...the team decided to use SQLite for storage..." | high | accept |
| "The user is allergic to bread." | "...the team decided to use SQLite..." | ~0 | **reject** |

⚠️ **Be careful:** this is a **word-overlap** check, not a truth check. It catches invented details
that the source never mentions. It cannot catch a fact built from the right words in the wrong
order. It is a backstop, not a proof.

### Step 15 — Embeddings are generated

All accepted episodes are embedded in one batch.

🔍 **In the code:** `:930`
```python
vectors = self.llm.embed([embedding_text(episode) for episode in candidates])
```

`embedding_text` (`:553`) builds a consistent template:

```text
<title>
Type: <event_type>
Summary: <summary>
Participants: <names or unknown>
Facts: <fact>; <fact>; ...
Outcome: <outcome or unknown>
```

An embedding is a list of 768 numbers. Chapter 7 explains what they mean.

### Step 16 — Duplicates are found

Two levels:

1. **Within this batch** (`:940`): if two episodes carry the same information, keep one.
2. **Against the whole archive** (`:950` → `_find_existing_duplicate`, `:973`): if this event is
   already stored, do not store it again.

Both use the same idea: same `event_type`, compatible numbers, and cosine similarity of at least
**0.90** (`DUPLICATE_SIMILARITY`, `:358`).

⚠️ **Be careful:** the number check is deliberate. "Review on 6 November" and "review on 13 November"
are very similar sentences, but different facts. If the digits differ, it is *not* a duplicate.

### Step 17 — The row is written

🔍 **In the code:** `_insert_episode` (`:1095`).

```sql
INSERT INTO episodes(
    episode_id, created_at, updated_at, event_time, title, event_type,
    summary, participants, facts, outcome, source_conversation_id,
    source_message_ids, status, embedding, embedding_model, embedding_dim
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
```

Python generates the ID (`ep_` + 12 random hex characters) and the timestamps. The model never
supplies either.

An audit row is also written:

```sql
INSERT INTO memory_events(event_id, episode_id, action, detail, created_at)
VALUES (..., 'created', '<title>', ...)
```

### Step 18 — Older memories may be updated

🔍 **In the code:** `_apply_lifecycle` (`:992`). Chapter 9 explains this fully.

### Step 19 — Cleanup and bookkeeping

🔍 **In the code:** `consolidate_duplicates()` (`:964`) runs after **every** save, then
`_mark_formed()` (`:968`) records which messages have been processed.

## 5.3 What happens in the awkward cases

| Situation | What the code does |
|---|---|
| **Only greetings** | `is_trivial_turn` short-circuits. No model call. Messages marked formed. Nothing stored. |
| **Model returns no memories** | `{"episodes": []}` is valid. Nothing stored, messages marked formed. |
| **Model returns invalid JSON** | `parse_json_object` raises `ExtractionError`. The batch fails, **nothing** from that batch is stored, messages stay unformed so the next turn retries. |
| **Model invents a fact** | Grounding check rejects that episode with a note: "fact not supported by its source messages". |
| **Model cites an assistant message only** | Rejected: "source_message_ids must include at least one user message". |
| **Embedding request fails** | `:931–932` returns an error. **Nothing is stored.** Messages stay unformed, so the next turn tries again. |
| **All candidates rejected** | Messages are marked formed anyway (`:923–927`). ⚠️ This is a real limitation: a borderline message that trips the grounding check is never retried. |

## 5.4 Why one episode per topic matters

This is worth a whole section because it was a real bug.

Suppose you paste a profile:

> "I study BSc CSIT. I use a MacBook Pro with an M1 Pro chip and 16 GB of memory. I'm allergic to
> avocado."

**The old behaviour:** one episode called "User background summary" with 18 facts inside it.

**Why that failed:** retrieval works on the episode as a whole. One embedding for a giant mixed
episode is an average of education, hardware, health, and goals. Ask "what laptop do I have?" and
that average is not very close to "laptop".

**The current behaviour:** three episodes — education, hardware, health.

**The test that guards it:** benchmark case `f13_profile_bundle_split` in
`benchmark/formation.json`. It requires three separate memories and forbids any title containing
"background summary" or "profile summary".

---

# 6. The SQLite database, table by table

## 6.1 The six tables at a glance

```text
conversations ──1───∞── messages
      │                    │
      │                    │ (episodes cite message IDs)
      │                    │
      └──1───∞── episodes ─┘
                    │
                    ├──∞── memory_events
                    └──∞── turn_traces (via conversation_id)

formed_messages  (independent bookkeeping: which messages were extracted)
```

There are **no enforced foreign keys** on `episodes`. The link from an episode to its conversation
and messages is by *value* (text IDs), not by a database constraint. That is a deliberate
small-system choice, and it has a consequence we will meet in Chapter 14.

## 6.2 `conversations`

One row per chat session.

| Column | Type | Meaning |
|---|---|---|
| `conversation_id` | TEXT, **primary key** | e.g. `conv_6de95da36f4d` |
| `created_at` | TEXT | UTC timestamp |
| `ended_at` | TEXT | set when the session is closed |
| `status` | TEXT | `active` or `ended` |

**Example row:**

| conversation_id | created_at | ended_at | status |
|---|---|---|---|
| `conv_6de95da36f4d` | 2026-10-28T06:41:19+00:00 | 2026-10-28T06:45:02+00:00 | ended |

🔍 **In the code:** created by `add_message` (`:721`); closed by `end_conversation` (`:740`).

⚠️ **Be careful:** `status` and `ended_at` are written but **never read** by any code path. They are
bookkeeping for humans. Nothing in retrieval depends on them.

## 6.3 `messages`

Every chat message, in order, exactly as typed or generated.

| Column | Type | Meaning |
|---|---|---|
| `message_id` | TEXT, **primary key** | e.g. `msg_63459cc61eef`, or `demo-msg-001` for demo data |
| `conversation_id` | TEXT, foreign key → `conversations` | which chat |
| `role` | TEXT | `user` or `assistant` |
| `content` | TEXT | the full text |
| `created_at` | TEXT | UTC timestamp |

**Example rows:**

| message_id | conversation_id | role | content (shortened) |
|---|---|---|---|
| `demo-msg-001` | `conv-demo-sync-2025-10` | user | Project sync notes from October 3, 2025... |
| `demo-msg-002` | `conv-demo-sync-2025-10` | assistant | Recorded: the team chose SQLite... |

🔍 **In the code:** written by `add_message` (`:715`), read by `get_messages` (`:731`).

⚠️ **Be careful:** there is **no index** on `messages(conversation_id)`. Every `get_messages` scans
the table. Harmless at 98 rows; noticeable at 100,000.

## 6.4 `episodes` — the important one

One row per memory.

| Column | Type | Meaning |
|---|---|---|
| `episode_id` | TEXT, **primary key** | `ep_` + 12 hex |
| `created_at` | TEXT | when the memory was written |
| `updated_at` | TEXT | last state change |
| `event_time` | TEXT | when the event happened (free text, not validated) |
| `title` | TEXT | short label |
| `event_type` | TEXT | one of seven types (below) |
| `summary` | TEXT | one or two sentences |
| `participants` | TEXT | **JSON array** stored as text |
| `facts` | TEXT | **JSON array** stored as text |
| `outcome` | TEXT | result, or NULL |
| `source_conversation_id` | TEXT | which chat it came from |
| `source_message_ids` | TEXT | **JSON array** of message IDs |
| `status` | TEXT | `active`, `done`, `superseded`, `cancelled` |
| `embedding` | TEXT | **JSON array** of 768 floats |
| `embedding_model` | TEXT | e.g. `embeddinggemma` |
| `embedding_dim` | INTEGER | e.g. 768 |
| `superseded_by` | TEXT | episode ID of the replacement |
| `change_reason` | TEXT | why the state changed |

The seven event types (`memory_engine.py:24`):

`event`, `decision`, `task`, `outcome`, `project_update`, `preference`, `goal`.

**Example row (facts and participants shortened):**

| episode_id | title | event_type | status | source_message_ids |
|---|---|---|---|---|
| `ep_b80bb760c8db` | Local prototype storage decision | decision | active | `["demo-msg-001"]` |
| `ep_49868f3d4779` | Prototype Presentation Commitment | goal | superseded | `["msg_..."]` |

## 6.5 `turn_traces`

A log of every question-and-answer, kept so you can inspect a past turn after a restart.

| Column | Type | Meaning |
|---|---|---|
| `trace_id` | TEXT, **primary key** | `tr_` + 12 hex |
| `conversation_id` | TEXT | which chat |
| `user_message_id` | TEXT | the question's message row |
| `assistant_message_id` | TEXT | the answer's message row |
| `question` | TEXT | the question |
| `answer` | TEXT | the answer |
| `details` | TEXT | **JSON**: whether it searched, the query, scores, **and the full evidence text** |
| `latency_ms` | INTEGER | how long the turn took |
| `created_at` | TEXT | when |

🔍 **In the code:** written by `save_trace` (`:749`) from `app.py:235`; read by `list_traces`
(`:765`).

⚠️ **Be careful — this matters.** The `details` column stores the **complete evidence text** sent to
the model. Deleting a memory does not remove its text from these traces. Chapter 14 explains why
that is a real problem.

## 6.6 `memory_events`

The audit trail. Every state change gets a row.

| Column | Type | Meaning |
|---|---|---|
| `event_id` | TEXT, **primary key** | `ev_` + 12 hex |
| `episode_id` | TEXT | which memory |
| `action` | TEXT | `created`, `done`, `cancelled`, `superseded`, `duplicate_seen`, `deleted` |
| `detail` | TEXT | human-readable reason |
| `created_at` | TEXT | when |

🔍 **In the code:** `log_event` (`:1036`), read by `list_events` (`:1044`).

**Example:**

| episode_id | action | detail |
|---|---|---|
| `ep_49868f3d4779` | created | Prototype Presentation Commitment |
| `ep_49868f3d4779` | superseded | replaced by ep_7ff53acb0c3a (similarity 0.82) |

⚠️ **Be careful:** there is no foreign key. Rows survive after the episode is deleted. That is useful
for auditing and confusing for counting.

## 6.7 `formed_messages`

Bookkeeping: which messages have already been through extraction.

| Column | Type | Meaning |
|---|---|---|
| `message_id` | TEXT, **primary key** | the message |
| `conversation_id` | TEXT | which chat |
| `formed_at` | TEXT | when it was processed |

🔍 **In the code:** `_formed_message_ids` (`:784`), `_mark_formed` (`:792`).

Without this table, every turn would re-extract the whole conversation and produce duplicates.

## 6.8 The vocabulary of databases

| Word | Plain meaning |
|---|---|
| **Table** | A grid of data, like a spreadsheet sheet. |
| **Row** | One record. One episode, one message. |
| **Column** | One field, the same for every row. `title`, `status`. |
| **Primary key** | The column that uniquely identifies a row. No two rows share it. |
| **Foreign key** | A column that points at a primary key in another table. `messages.conversation_id` → `conversations.conversation_id`. |
| **JSON in a database** | A list or object stored as text, e.g. `["Mira","Asha"]`. SQLite does not understand it; Python parses it with `json.loads`. |
| **SQL query** | A sentence that asks the database for something: `SELECT title FROM episodes WHERE status = 'active'`. |
| **Transaction** | A group of changes that either all happen or none do. |

⚠️ **On transactions:** this project commits after each function returns, but it opens a **new
connection for each operation** (`_db`, `:626`). So inserting an episode and updating an old one are
**two separate transactions**. A crash in between leaves a half-finished state.

## 6.9 What happens when the app closes and restarts

Nothing is lost. Everything is in `memory.db` on disk.

On startup, `_init_db` (`:636`) runs:

1. `CREATE TABLE IF NOT EXISTS ...` for all six tables — safe to run every time.
2. An **additive migration**: if `episodes` lacks `superseded_by`, `updated_at`, or
   `change_reason`, it adds them with `ALTER TABLE`.

Then the sidebar lists the archive, and retrieval works immediately.

The only thing that resets is the `st.session_state` chat history — the visible messages of the
current session. Your memories are untouched.

## 6.10 The intern's test question

> *"Where exactly is an episode stored, how do I identify its original conversation, and which
> messages created it?"*

Answer:

1. **Where:** one row in the `episodes` table of `memory.db`.
2. **Which conversation:** `episodes.source_conversation_id`.
3. **Which messages:** `episodes.source_message_ids`, a JSON array of `messages.message_id` values.

To see it yourself:

```bash
sqlite3 memory.db "SELECT episode_id, title, source_conversation_id, source_message_ids FROM episodes LIMIT 5;"
```

To see the original words:

```bash
sqlite3 memory.db "SELECT message_id, role, substr(content,1,100) FROM messages WHERE message_id = 'demo-msg-001';"
```

---

# 7. Embeddings and similarity search

## 7.1 The library analogy

Imagine a library where books are **not** sorted alphabetically. Instead, they are sorted by what
they are about. Cookbooks sit near each other. Books about mountains sit near books about hiking.

Now you walk in and say "I want something about climbing". The librarian does not look for the word
"climbing" on a spine. They walk to the mountain shelf.

That is what embeddings do for text.

## 7.2 What a text embedding is

An **embedding** is a list of numbers that represents the *meaning* of a piece of text.

For this project it is **768 numbers** per piece of text.

```text
"The team chose SQLite for storage."
   -> [ 0.013, -0.441, 0.902, ... ]   (768 numbers)
```

Those numbers are not readable by a human. They are coordinates in a 768-dimensional space.

## 7.3 Why numbers?

Because computers compare numbers easily, and meaning-similar things end up with similar numbers.

Two sentences that mean similar things produce number lists that point in similar directions. Two
unrelated sentences point in different directions.

## 7.4 What a vector is

A **vector** is just an ordered list of numbers. `[0.1, 0.9, -0.3]` is a 3-dimensional vector.
`[0.013, -0.441, 0.902, ...]` with 768 entries is a 768-dimensional vector.

"768 dimensions" sounds exotic. It just means "768 numbers in the list". You cannot picture it, and
you do not need to.

## 7.5 A tiny worked example

Real embeddings have 768 numbers. Here is a fake 2-number version so you can see the maths.

| Text | Vector |
|---|---|
| "We chose SQLite for the database" | `[0.90, 0.10]` |
| "Which database did we pick?" | `[0.85, 0.20]` |
| "The weather is nice today" | `[0.05, 0.95]` |

**Cosine similarity** measures the angle between two vectors, ignoring their length. The result is
between -1 and 1:

- **1.0** — same direction, same meaning.
- **0.0** — unrelated.
- **-1.0** — opposite.

For the pairs above:

| Pair | Cosine | Reading |
|---|---:|---|
| SQLite statement vs database question | ~0.99 | very similar |
| SQLite statement vs weather | ~0.03 | unrelated |

## 7.6 The real formula

🔍 **In the code:** `cosine` (`:351`)

```python
def cosine(a, b):
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denominator) if denominator else 0.0
```

In words: multiply matching numbers, add them up (the dot product), then divide by the lengths.
That gives the angle's cosine. NumPy does the arithmetic fast.

## 7.7 How an episode gets an embedding

🔍 **In the code:** `embedding_text` (`:553`) builds a fixed template, then `llm.embed` converts it.

```text
Local prototype storage decision
Type: decision
Summary: The team chose SQLite for the local prototype...
Participants: team
Facts: The team chose SQLite for storage.; The reason is single-user and offline-first.
Outcome: unknown
```

Two things to notice:

- The **whole episode** is embedded, not each fact separately.
- The template is **the same every time**, so episodes are comparable to each other.

⚠️ **Be careful:** because the whole episode is embedded, a giant episode with 18 unrelated facts
gets an "average" embedding. That is exactly the bug described in Chapter 5.4.

## 7.8 How a question gets an embedding

🔍 **In the code:** `retrieve` (`:1153`)

```python
query_vector = np.asarray(self.llm.embed([query])[0], dtype=np.float64)
```

The query is the **rewritten** question from the router, not always your exact words. Chapter 8
explains why.

⚠️ **Be careful:** documents are embedded with a labelled template; queries are embedded as plain
text. This mismatch means scores tend to be lower than they would be with matched formatting. It is
a known, acceptable imperfection here.

## 7.9 How the comparison happens

🔍 **In the code:** `retrieve` (`:1154–1169`)

```python
rows = self.list_episodes(include_embeddings=True)
for row in rows:
    stored = np.asarray(row["embedding"], dtype=np.float64)
    score = cosine(stored, query_vector)
```

In plain words: load every active memory, compare the question to each, keep the score.

There is **no index**. This is a full scan. At 16 memories it is instant; at 100,000 it would be far
too slow.

## 7.10 What the scores mean in practice

From the last recorded benchmark (2026-10-28), grouping all retrieved memories by score:

| Score band | Memories examined | Actually relevant | Precision |
|---|---:|---:|---:|
| 0.20 – 0.40 | 11 | 1 | 9% |
| 0.40 – 0.60 | 21 | 7 | 33% |
| 0.60 – 0.80 | 8 | 5 | 62% |
| 0.80 – 1.00 | 1 | 1 | 100% |

Read that carefully. **A score around 0.30 is almost always noise.** A score above 0.80 is almost
always right.

The production setting only accepts scores of **0.30 or higher**
(`MEMORY_MIN_SIMILARITY=0.30`). So it is accepting a band that is mostly noise. Chapter 14 returns
to this.

## 7.11 Top-k retrieval and the threshold

Two settings control what comes back:

| Setting | Value | Meaning |
|---|---:|---|
| `MIN_SIMILARITY` | 0.30 | Ignore anything below this score |
| `TOP_K` | 4 | Return at most four memories |

Why not return everything? Because the answer model has limited space, and extra wrong memories
cause wrong answers. Why not return only one? Because sometimes two memories together answer the
question.

## 7.12 Semantic similarity is not factual accuracy

This is the most important warning in this chapter.

Two memories can **look** similar to a question without either being the right answer.

Example. Question: *"What laptop do I use?"*

| Memory | Why it scores high | Is it an answer? |
|---|---|---|
| "User hardware setup: MacBook Pro M1 Pro, 16 GB" | talks about a laptop | **Yes** |
| "User asked for an email about laptop details for Nabin" | also talks about laptops | **No** — it is a task, not a device fact |

Both are "about laptops". Only one describes the user's computer.

Cosine similarity measures **topic closeness**, not **question answering**. This is why the project
needs:

1. the grounding check at write time (does the fact come from the source?),
2. the answer prompt's rules (don't treat a request as a contradiction),
3. and, in future, better ranking.

A high similarity score means "this is about a related subject". It does not mean "this is true" or
"this answers you".

---

# 8. How a memory is retrieved

Back to the Monday-to-Wednesday story.

> **Wednesday, user:** "Which database did we select for the project?"

## 8.1 The full journey

### Step 1 — The message reaches the engine

🔍 **In the code:** `app.py:229` → `handle_turn` (`memory_engine.py:1238`).

### Step 2 — Is retrieval even allowed?

If the sidebar toggle is off, the engine skips everything and answers with an explicit note that the
archive is unavailable.

🔍 **In the code:** `:1249–1251`.

### Step 3 — Is this a trivial message?

"hi" or "thanks" gets answered immediately, with no decision call and no search.

🔍 **In the code:** `:1253–1255`.

### Step 4 — Should we search at all?

This is **memory routing**. A separate model call decides.

🔍 **In the code:** `decide` (`:1189`).

The model receives:

1. **A catalog of the archive**: up to 30 episodes, each as
   `- Title (event_type): fact1 | fact2 | fact3`.
2. The last 6 messages of the current chat.
3. Your new message.

It returns:

```json
{"needs_memory": true, "search_query": "project database selection SQLite decision"}
```

Why show the model the catalog? Because a title alone often does not reveal what is inside. A memory
titled "User background summary" gives no hint that a laptop fact is buried in it. Including a few
facts fixes that.

⚠️ **Be careful:** the catalog is capped at 30 episodes, newest first (`:1191`). Once you have more
than 30 memories, older ones can never influence the routing decision. This is a real limitation.

### Step 5 — The search query

Notice the router rewrote "Which database did we select for the project?" into something more
standalone. This is called **query expansion**. It helps because pronouns like "we" and "it" carry no
meaning for an embedding.

If the model returns `needs_memory: false`, the search query must be empty, and no search happens.

### Step 6 — The query becomes numbers

🔍 **In the code:** `retrieve` (`:1153`). One embedding call.

### Step 7 — SQLite hands over the candidates

🔍 **In the code:** `list_episodes(include_embeddings=True)` (`:1114`).

The SQL that matters:

```sql
SELECT episode_id, title, ..., status, embedding, ...
FROM episodes
WHERE status IN ('active', 'done')
ORDER BY created_at DESC, rowid DESC
```

Only **active** and **done** memories. Superseded and cancelled ones are excluded here — that is how
old decisions stop influencing answers.

### Step 8 — Cosine similarity is calculated

One comparison per active memory. 16 memories means 16 comparisons.

### Step 9 — Results are ranked

Highest score first.

### Step 10 — The top memories are selected

Drop anything under 0.30. Keep at most 4.

### Step 11 — Evidence is formatted

🔍 **In the code:** `_format_evidence` (`:570`).

Each match becomes a text block:

```text
[EPISODE ep_b80bb760c8db]
Title: Local prototype storage decision
Event type: decision
Event time: 2025-10-03
Participants: team
Summary: The team chose SQLite for the local prototype...
Facts: The team chose SQLite for storage.; The reason is single-user and offline-first.
Outcome: unknown
Source conversation: conv-demo-sync-2025-10
Source message IDs: demo-msg-001
Similarity: 0.7412
```

Every block carries the ID, the date, the sources, and the score. That is what makes the system
auditable.

### Step 12 — The answer model is called

🔍 **In the code:** `answer` (`:1213`).

The message list it builds:

1. `ANSWER_SYSTEM` — the rulebook for answering.
2. `"RETRIEVED EPISODIC MEMORY..."` — the evidence blocks.
3. The last 8 **user** messages from this chat.
4. Your question.

⚠️ **Be careful — this is deliberate:** assistant messages are **removed** before this call
(`:1219`). Reason: an earlier assistant reply might repeat a memory you have since deleted. If it
were sent, the model could "remember" something that no longer exists. Only user messages (what
actually happened in this chat) plus retrieved evidence are allowed.

### Step 13 — The trace is saved

🔍 **In the code:** `app.py:235` → `save_trace` (`:749`).

The row records the question, the answer, whether it searched, the query, the scores, and the full
evidence text. This is why the sidebar can show past turns after a restart.

### Step 14 — The UI shows the evidence

🔍 **In the code:** `app.py:168–189`.

Under each reply there is an expander. It shows:

- whether retrieval was enabled,
- whether the model requested memory,
- the search query,
- the reason string,
- each retrieved episode with its ID, title, and similarity,
- the source message IDs,
- and the exact evidence text in a code block.

## 8.2 Five different things, easily confused

These are separate steps. Mixing them up is the most common source of confusion.

| Term | What it means | Where it happens |
|---|---|---|
| **Memory routing** | Deciding *whether* to search at all | `decide` (`:1189`) |
| **Memory retrieval** | Fetching candidate memories from the database | `retrieve` (`:1148`) |
| **Similarity ranking** | Ordering candidates by score | inside `retrieve` |
| **Evidence selection** | Which memories actually go into the prompt | threshold + top-k + `_format_evidence` |
| **Answer generation** | Writing the final reply | `answer` (`:1213`) |

A failure at any one of these looks the same to the user: a bad answer. That is why the evidence
panel exists.

## 8.3 What happens in each awkward case

| Situation | What the user sees |
|---|---|
| **Router says no memory needed** | An answer with no evidence. The panel says "memory not searched" and gives the reason. |
| **Retrieval finds nothing** | The evidence string is literally `"No episodic memories matched this query. The result set is empty."` and the model is told to say it found no relevant memories. |
| **Retrieval finds the wrong memory** | The model may answer confidently from a bad memory. The evidence panel is how you catch this. |
| **Several memories are relevant** | All of them (up to 4) go into the prompt. The model is told to use them as context, not to list them. |
| **Two memories contradict** | The model is instructed to prefer the better-supported value. ⚠️ Nothing enforces this. Chapter 14. |
| **Retrieval is turned off** | A system note says the archive is unavailable. The model must not claim that no memories exist, only that it cannot check them. |

---

# 9. How memories change over time

Memories are not frozen. The project keeps a **lifecycle**.

## 9.1 The story

```text
2 October:
  The team plans to finish the schema by 10 October.
    -> task, outcome = null, status = active

7 October:
  The deadline changes to 15 October.
    -> a new task for the same subject

16 October:
  Mira reports the schema is finished.
    -> outcome, status = active
```

What *should* the system know at each stage?

| Date | Should know | Should still be able to answer |
|---|---|---|
| 2 Oct | task open, due 10 Oct | "What is due on 10 October?" |
| 7 Oct | task open, due 15 Oct | "When was it originally due?" → 10 Oct |
| 16 Oct | completed | "When did Mira finish?" → 16 Oct; "What was the original deadline?" → 10 Oct |

Notice the last column. **Keeping history is the point.** If we overwrote the old deadline, we could
never answer "when was it originally due?"

## 9.2 The four states

| Status | Meaning | Retrievable? |
|---|---|---|
| `active` | current, true | **Yes** |
| `done` | completed | **Yes** (you can still ask what happened) |
| `superseded` | replaced by a newer memory | **No** |
| `cancelled` | called off | **No** |

🔍 **In the code:** the filter is `WHERE status IN ('active', 'done')` (`:1121`).

## 9.3 How transitions happen

🔍 **In the code:** `_apply_lifecycle` (`:992`).

After a new episode is stored, the engine looks for the **single best matching older memory**:

1. Skip itself and anything not active.
2. Skip memories with no participant overlap.
3. Compute cosine similarity.
4. Keep the highest match at or above `LINK_SIMILARITY = 0.45`.

Then:

| Condition | New state of the older memory |
|---|---|
| New episode is `outcome`, old is `task` or `goal` | old → `done` |
| New text contains a cancel word ("cancel", "call off", "no longer", "won't", "dropped", "abandoned", "scrapped") and old is `task`/`goal` | old → `cancelled` |
| Both are replaceable types and similarity ≥ `SUPERSEDE_SIMILARITY = 0.72` | old → `superseded` |

`REPLACEABLE_TYPES` = `event, decision, task, project_update, preference, goal`. `outcome` is
excluded, because an outcome closes work rather than replacing a value.

Every change writes a `memory_events` row with the reason, including the similarity score.

## 9.4 Duplicate consolidation

Two memories may describe the same event after several saves. A cleanup pass runs **after every
save**.

🔍 **In the code:** `consolidate_duplicates` (`:1059`).

It compares every pair of active episodes and merges when:

- same `event_type`, **and**
- participants overlap (or one side is empty), **and**
- numbers are compatible, **and**
- either cosine ≥ 0.90 **or** title word-overlap ≥ 0.45.

The richer memory is kept (`information_score` prefers more dates, then more facts, then more text).
Facts are unioned. The loser becomes `superseded` with reason "merged duplicate of ...".

⚠️ **Be careful:** the `title overlap ≥ 0.45` branch alone can merge two genuinely different
memories that share a formulaic title such as "Project scope: ...". This is a known risk.

## 9.5 Deletion

🔍 **In the code:** `delete_episode` (`:1137`).

```sql
DELETE FROM episodes WHERE episode_id = ?
```

This is a **hard delete**. The row is gone. An audit row (`action='deleted'`) is written first.

⚠️ **Be careful — the important limitation:** deletion removes the episode but **not** the copies of
its text inside `turn_traces.details`. Chapter 14 explains the consequence.

## 9.6 Why not just overwrite?

Because "what is true now" and "what happened then" are different questions.

If you replace the old deadline with the new one, you can answer "when is it due?" but not "did the
deadline change?". Keeping both, with states, lets you answer both — and it lets a human audit why
the system believes what it believes.

That is why the project keeps `superseded` and `cancelled` rows instead of deleting them.

## 9.7 Lifecycle limitations found in the code

1. **Only one older memory is updated per new episode.** `_apply_lifecycle` keeps a single `best`
   match (`:996–1006`). If three old memories should close, two stay active.
2. **Similarity is the only signal.** Two unrelated memories that happen to embed close together at
   0.72 can be linked.
3. **Contradictions between two active memories are not resolved.** Nothing changes state because
   two truths disagree.
4. **No editing.** You can delete, but you cannot correct a memory's text.
5. **`event_time` is never used for ranking**, only displayed.

---

# 10. The Python files and functions

This chapter is a map. For each important function: what it solves, who calls it, what goes in, what
comes out, and what happens on failure.

## 10.1 `memory_engine.py` — the engine

### `Settings` (`:186`)

- **Solves:** where does configuration live?
- **Called by:** `MemoryEngine.__init__`, `app.py:18`, `evaluate.py`.
- **In:** environment variables.
- **Out:** a frozen dataclass with model names, database path, `top_k`, `min_similarity`.
- **Talks to:** nothing.
- **Fails:** `int()`/`float()` on a bad env value raises at startup — loud and early, which is good.

### `OllamaClient` (`:270`)

- **Solves:** one place that talks to Ollama.
- **Called by:** the engine for every model call.
- **In:** chat messages + options, or a list of texts.
- **Out:** a string, or a list of vectors.
- **Talks to:** Ollama over HTTP.
- **Fails:** raises `OllamaError` with a message naming the model and address. **It never falls back
  to another provider.**

```python
def chat(self, messages, *, json_mode=False, temperature=0.2, schema=None):
    options = {"temperature": temperature, "num_ctx": 8192}
    if temperature <= 0.0:
        options["top_k"] = 1        # greedy decoding
    ...
```

### `MemoryEngine.__init__` (`:621`)

- **Solves:** wiring.
- **Does:** stores settings, creates the LLM client, calls `_init_db()`.

### `_db` (`:626`)

- **Solves:** safe connection handling.
- **Does:** opens a connection, sets `row_factory` so rows behave like dictionaries, commits on
  success, closes in `finally`.
- **Note:** one connection per call. Not one long-lived connection.

### `_init_db` (`:636`)

- **Solves:** make sure the schema exists.
- **Does:** `CREATE TABLE IF NOT EXISTS` for six tables, creates indexes, then an additive migration
  for three `episodes` columns.
- **Fails:** a locked or corrupt database raises a `sqlite3` error at startup.

### `add_message` (`:715`)

- **Solves:** persist one message.
- **Called by:** `app.py:224`, `app.py:234`, `evaluate.add_messages`, `load_demo`.
- **In:** conversation ID, role, content, optional timestamp, optional message ID.
- **Out:** a dict of the message.
- **Does:** creates the conversation if missing (`INSERT OR IGNORE`), inserts the message.
- **Fails:** a duplicate `message_id` raises (the `messages` insert is not `OR IGNORE`).

### `get_messages` (`:731`)

- **Solves:** read a conversation in order.
- **Out:** list of dicts, ordered by `created_at` then `rowid`.
- **Fails:** returns an empty list for an unknown conversation.

### `form_memories` (`:802`) — **the most important function**

- **Solves:** turn new messages into stored episodes.
- **Called by:** `app.py:251` (after every reply), `app.py:66` (End session), `load_demo`, tests,
  `evaluate.run_formation`, `evaluate.run_lifecycle`.
- **In:** `conversation_id`, `incremental` flag, `end` flag.
- **Out:** `(stored_episodes, notes)` where notes are human-readable rejection messages.
- **Inside:** the 19 steps of Chapter 5.
- **Talks to:** SQLite, chat model, embedding model.
- **Fails:**
  - no messages → returns `([], ["The conversation has no messages."])`
  - model error → returns `([], [error])`, stores nothing, does not mark formed
  - embedding error → same
  - individual bad episode → skipped, others continue

### `_find_existing_duplicate` (`:973`)

- **Solves:** is this event already remembered?
- **In:** an episode and its vector.
- **Out:** the existing row, or `None`.
- **Logic:** same type, compatible numbers, and either the new one is less informative than the old
  (then it is a duplicate) with cosine ≥ 0.90.

### `_apply_lifecycle` (`:992`)

- **Solves:** keep older memories honest.
- **In:** the new episode and its vector.
- **Out:** `{action, episode_id}` or `None`.
- **Fails:** silently does nothing when no match reaches 0.45.

### `consolidate_duplicates` (`:1059`)

- **Solves:** merge accidental duplicates.
- **Out:** a list of merges performed.
- **Cost:** compares every pair — O(n²). Fine at 16 memories, slow at thousands.

### `list_episodes` (`:1114`)

- **Solves:** read the archive.
- **In:** `include_embeddings`, `include_inactive`.
- **Out:** list of dicts with JSON columns already parsed.
- **Note:** by default excludes `superseded` and `cancelled`.

### `delete_episode` (`:1137`)

- **Solves:** remove a memory.
- **Does:** logs `deleted`, then `DELETE FROM episodes`.
- **Out:** `True` if a row was removed.

### `retrieve` (`:1148`)

- **Solves:** find memories for a query.
- **In:** query text, optional `top_k` and `min_similarity` overrides.
- **Out:** a `RetrievalResult` with matches, formatted evidence, model name, dimension, candidate
  count.
- **Fails:** raises `EmbeddingMismatch` if any stored episode used a different model or dimension.

### `decide` (`:1189`)

- **Solves:** routing.
- **Out:** a `MemoryDecision(needs_memory, search_query)`.
- **Fails:** any exception → returns `needs_memory=True` with the raw question as the query. Searching
  is treated as the safe default.

### `answer` (`:1213`)

- **Solves:** produce the reply.
- **In:** question, history, optional retrieval, `memory_disabled` flag.
- **Out:** a string.
- **Important:** strips assistant turns from history before the call.

### `handle_turn` (`:1238`)

- **Solves:** orchestrate one message.
- **Out:** `{"answer": str, "details": dict}`.
- **The `details` dict is what the UI renders** — searched, needs_memory, search_query, results,
  evidence, reason.

### `load_demo` (`:1294`) and `reset_demo` (`:1287`)

- **Solves:** the reproducible demo.
- **Does:** deletes prior demo rows, inserts ten dated fictional messages, then runs **the real
  extraction pipeline**. It does not insert episodes directly.

### `integration_check` (`:1302`)

- **Solves:** a manual smoke test against real models.
- **Run with:** `python -m memory_engine`.
- **Not** collected by pytest.

## 10.2 `app.py` — the interface

| Function / block | Line | Job |
|---|---:|---|
| `get_engine` | 16 | Cached engine so the DB connection setup is not repeated |
| `fresh_session` | 21 | New conversation ID, clears visible chat |
| `notice` | 28 | Queue a success/warning/error banner |
| Sidebar | 42 | Toggle, buttons, archive, traces |
| Chat loop | 222 | The main per-message flow |

⚠️ **Be careful:** `fresh_session` does **not** delete memories. It only clears the chat window. That
is the whole point — it is how you test cross-session recall.

## 10.3 `evaluate.py` — measurement

| Function | Line | Job |
|---|---:|---|
| `load_cases` | 47 | Read a `benchmark/*.json` file |
| `fresh_engine` | 52 | Engine on a temporary database |
| `seed_episode` | 161 | **Insert an episode directly, bypassing extraction** |
| `run_answer` | 181 | Call `handle_turn` and time it |
| `run_formation` | 189 | Real extraction, scored against gold keywords |
| `run_retrieval` | 273 | Ranking over seeded episodes |
| `run_lifecycle` | 353 | Multi-session state changes |
| `run_answering` | 459 | Answers over seeded episodes |
| `run_causal` | 544 | Off / counterfactual / deletion / hard negative |
| `run_stress` | 628 | Restart, deletion, injection, flood, empty |
| `write_report` | 697 | Build `eval_report.md` and `raw.json` |
| `main` | 905 | CLI entry point |

⚠️ **Be careful:** `seed_episode` (`:161`) constructs an `Episode` in Python and calls the private
`_insert_episode`. It skips validation, grounding, duplicate detection, and lifecycle. So those four
benchmark sections do **not** test extraction. Chapter 12 explains what that means for the numbers.

## 10.4 How the functions connect

```text
app.py:222  chat_input
   └─> add_message                     (SQLite: messages)
   └─> handle_turn
         ├─> is_trivial_turn           (no model)
         ├─> decide                    (Ollama chat)
         ├─> retrieve                  (Ollama embed + SQLite: episodes)
         │     └─> _format_evidence
         └─> answer                    (Ollama chat)
   └─> add_message                     (SQLite: messages)
   └─> save_trace                      (SQLite: turn_traces)
   └─> form_memories
         ├─> _formed_message_ids       (SQLite: formed_messages)
         ├─> split/batch
         ├─> llm.chat                  (Ollama chat)
         ├─> EpisodeCandidate          (Pydantic)
         ├─> validate_source_ids
         ├─> ungrounded_fact           (grounding)
         ├─> llm.embed                 (Ollama embed)
         ├─> _find_existing_duplicate  (SQLite + cosine)
         ├─> _insert_episode           (SQLite: episodes)
         ├─> _apply_lifecycle          (SQLite: episodes + memory_events)
         ├─> consolidate_duplicates    (SQLite + cosine)
         └─> _mark_formed              (SQLite: formed_messages)
```

That is the whole system in one picture. Every feature you read about lives on one of those lines.

---

# 11. The Streamlit application

Everything a user can actually do, and what happens behind it.

## 11.1 Starting a conversation

There is no "new chat" page. When you open the app, `fresh_session()` (`app.py:21`) gives you a
random conversation ID such as `conv_6de95da36f4d`. That ID is used for every message you send until
you start a new session.

## 11.2 Sending a message

Type in the box at the bottom and press Enter.

Behind it: store user message → `handle_turn` → store assistant message → save trace → render →
`form_memories` → rerun the page.

## 11.3 **Start fresh session** (`:54`)

Creates a new conversation ID and empties the visible chat.

**It does not touch the archive.** This is the button that makes cross-session recall testable.

## 11.4 **End session** (`:58`)

Runs `form_memories(..., incremental=True, end=True)` to flush anything not yet processed, then
marks the conversation ended and shows the memories saved during this session.

⚠️ **Be careful:** memories are already saved after every reply. This button is a safety net, not the
main path. Skipping it loses nothing.

## 11.5 Creating memories

Automatic. There is no "save" button. After each reply you will see either:

- "Memory writer: stored N new episode(s) from this turn.", or
- "Memory writer: nothing new to store from this turn."

If something was rejected, an expander called **Memory writer notes** lists the reasons.

## 11.6 Inspecting stored memories

The sidebar lists every retrievable memory with a state icon:

| Icon | State |
|---|---|
| 🟢 | active |
| ✅ | done |
| 🔁 | superseded |
| 🚫 | cancelled |

Expand one to see: summary, state, type, event date, episode ID, source conversation, source message
IDs, facts, outcome, embedding model and dimension, and its event history.

## 11.7 **Use memory retrieval** toggle (`:44`)

| Toggle | Effect |
|---|---|
| On | Every non-trivial message triggers a routing call, and a search if the router says yes |
| Off | No routing call, no search, and the model is told the archive is unavailable |

This is the switch that lets you demonstrate that memory is really doing the work.

## 11.8 Viewing retrieved evidence

Under every assistant reply there is an expander titled either "Retrieval details (memory searched)"
or "(memory not searched)". Inside:

- whether retrieval was enabled,
- whether the model asked for memory,
- the search query,
- the reason,
- each retrieved episode with ID, title, similarity,
- source message IDs,
- the complete evidence text given to the model.

This is the single most useful debugging tool in the project.

## 11.9 Deleting a memory

Inside an episode's expander there is a **Delete memory** button. It calls `delete_episode` and
reruns the page.

⚠️ **Be careful:** deleting removes the episode row. The text may still exist in `turn_traces`.

## 11.10 **Show superseded / cancelled memories** (`:93`)

A checkbox that includes inactive episodes in the sidebar list. Useful for showing that history is
kept rather than overwritten.

## 11.11 **Load demo conversation & extract memories** (`:77`)

Seeds ten dated fictional messages and runs the real extraction pipeline, then starts a fresh
conversation. Produces the four-question demo described in Chapter 17.

## 11.12 **Merge duplicate memories** (`:94`)

Calls `consolidate_duplicates()` manually.

⚠️ **Be careful:** new memories are already merged during saving. This button is a backstop for
archives created by older code.

## 11.13 **Recent persisted turns** (`:137`)

Shows the last 5 `turn_traces` rows: question, timestamp, latency, whether it searched, the query,
and the first 400 characters of the answer. These survive a restart.

## 11.14 What the UI does **not** have

- No memory editing.
- No approval workflow.
- No archive search box.
- No conversation switcher.
- No multi-user login.
- No pagination (it renders every episode).

---

# 12. Tests and benchmark results

## 12.1 Why testing an AI memory system is hard

Normal software is predictable: give it the same input, get the same output.

A language model is not. Ask twice, get two phrasings. So you cannot test "the answer equals this
exact string". You test **properties**:

- Did it store the right memory?
- Did it *not* store the wrong one?
- Did retrieval put the right memory on top?
- Did the answer contain the required fact and avoid the forbidden one?
- Did the answer change when memory was removed?

That is what this project does.

## 12.2 The four kinds of test — a critical distinction

| Kind | Uses real Ollama? | Starts from a conversation? | What it proves |
|---|---|---|---|
| **Mocked unit test** (`test_memory.py`) | No — `FakeLLM` | Sometimes | The Python plumbing is correct |
| **Metric unit test** (`test_evaluate.py`) | No | No | The maths in the scoring code is correct |
| **Seeded benchmark** (retrieval, answering, causal, stress) | Yes, for embeddings and answers | **No** — episodes inserted directly | Ranking and answering behaviour |
| **End-to-end benchmark** (formation, lifecycle) | Yes | **Yes** | The whole pipeline, extraction included |

⚠️ **Be careful:** only the fourth kind can prove "a conversation becomes a usable memory". The
third kind starts with memories the model never wrote. Do not quote a seeded score as proof that
extraction works.

## 12.3 The unit tests: 27 passing

```bash
pytest -q
# 27 passed
```

**22 engine tests** in `test_memory.py` use a `FakeLLM` (`:14`) that returns canned JSON, plus
`fake_embed` (`:33`) which maps keywords to 4-dimensional vectors.

What they check:

| Behaviour | Test |
|---|---|
| Extraction output is schema-validated | `test_episode_extraction_is_schema_validated` |
| Unknown source IDs rejected | `test_source_message_ids_must_come_from_transcript` |
| Episode survives restart | `test_stored_episode_survives_app_restart` |
| Paraphrased query retrieves | `test_paraphrased_query_retrieves_relevant_episode` |
| Deleted memory is not retrieved | `test_deleted_episode_is_not_retrieved` |
| Answer uses retrieved evidence | `test_historical_question_uses_retrieved_evidence` |
| Deleted memory cannot be answered from chat history | `test_deleted_memory_cannot_be_answered_from_chat_history` |
| Invented fact rejected | `test_fact_not_supported_by_source_messages_is_rejected` |
| Router sees facts, not just titles | `test_decision_prompt_includes_facts_not_just_titles` |
| Assistant turns never used as evidence | `test_assistant_history_is_never_evidence_even_without_a_search` |
| Conflict rules present in prompt | `test_answer_prompt_separates_real_conflicts_from_background` |
| Trace persists | `test_turn_trace_is_persisted` |
| Changed preference supersedes old | `test_changed_preference_supersedes_the_old_one` |
| Small talk rejected | `test_small_talk_episode_is_rejected_by_python` |
| Repeated preference not duplicated | `test_repeated_preference_is_not_stored_twice` |
| Completed task → done | `test_completed_task_is_marked_done_not_deleted` |
| Cancelled task → cancelled | `test_cancelled_task_is_marked_cancelled` |
| Consolidation keeps richer memory | `test_consolidate_duplicates_keeps_the_richer_memory` |
| Incremental writer processes once | `test_incremental_writer_processes_each_turn_once` |
| Failed extraction is retried | `test_incremental_writer_retries_a_failed_extraction` |
| Auto-merge on save | `test_saving_merges_duplicates_automatically` |
| Empty archive abstains | `test_no_supporting_memory_returns_empty_evidence_without_fabrication` |

**5 metric tests** in `test_evaluate.py`: keyword matching, duplicate detection, AUROC, calibration
buckets, format detection.

⚠️ **Be careful:** the fake embeddings have **4 dimensions**, not 768. These tests prove the plumbing
works. They say nothing about whether the real model finds the right memory.

## 12.4 The benchmark: 51 cases

| Section | Cases | Uses real extraction? | Measures |
|---|---:|:---:|---|
| Formation | 13 | **Yes** | What gets stored, what gets rejected |
| Retrieval | 13 | No (seeded) | Ranking against hard negatives |
| Lifecycle | 6 | **Yes** | Behaviour across sessions |
| Answering | 10 | No (seeded) | Grounded answers and abstention |
| Causal | 4 | No (seeded) | Does memory cause the answer? |
| Stress | 5 | No (seeded) | Restart, deletion, injection, flood, empty |

⚠️ **Cases are not the same as expected memories.** The 13 formation cases contain **17 expected
memories** in total, because some cases ask for several at once (for example, `f13_profile_bundle_split`
requires three separate topic memories). That is why the results table below says "17 gold", not "13".
Section totals (51) count *cases*; formation results count *memories*.

## 12.5 The metrics, with tiny examples

### Precision and recall

Suppose there are 3 real memories in a conversation, and the system stores 4.

- **Precision** = how many of what it stored were correct. 3 correct / 4 stored = **75%**.
  Low precision means noise.
- **Recall** = how many of the real ones it found. 3 found / 3 real = **100%**.
  Low recall means it missed things.

High precision with low recall = it only remembers a little, but that little is right.
Low precision with high recall = it remembers everything, including junk.

### Precision@K and Recall@K

"@K" means "in the top K results".

If the top 4 retrieved memories are `[gold, noise, noise, gold]`:

- **Precision@4** = 2 gold / 4 returned = **50%**.
- **Recall@4** = 2 gold found / however many gold exist.

### Top-1 accuracy

Did the single best-ranked memory belong to the gold set?

If yes → 1. If no → 0. Average across cases.

This is strict. A system can be genuinely useful with 69% top-1 if the correct memory is usually
still in the top 4.

### Mean Reciprocal Rank (MRR)

Where did the first correct answer appear?

- Rank 1 → 1/1 = 1.0
- Rank 2 → 1/2 = 0.5
- Rank 3 → 1/3 = 0.33
- Not found → 0

Average those. **MRR 0.846** means the first correct memory is usually rank 1, occasionally rank 2.

### AUROC

**Area Under the Receiver Operating Characteristic curve.** A single number for "how well does the
score separate relevant from irrelevant?"

- **1.0** = perfect separation: every relevant memory scores above every irrelevant one.
- **0.5** = random guessing.
- **0.759** means: pick a random relevant memory and a random irrelevant one; there is a 75.9%
  chance the relevant one scored higher.

### Calibration

Are the scores honest? This table groups memories by score band and asks how many were actually
relevant. It is the most practical diagnostic in the whole suite.

### Abstention accuracy

When the archive does not contain the answer, does the model say so? Measured on cases marked
unanswerable.

### False abstention

The opposite failure: it refuses a question it could answer.

⚠️ **Implementation note:** the detector looks for refusal words ("no records", "not establish",
"unknown") **and** checks that the answer lacks the case's required keywords. An earlier version
scanned the whole answer and mislabelled good answers that used the word "unknown" in a caveat.

### Unsupported-claim rate

How often a stored fact is not supported by its source. In this benchmark it is reported as
**false-memory rate**.

### Latency

Wall-clock time per turn, in milliseconds. The last run averaged about **6.1 seconds**, dominated by
three chat calls and two embedding calls.

### Hard-negative rejection

A **hard negative** is a deliberately confusing wrong memory: same person, same topic, opposite
status. If the wrong one ranks above the right one, that is a failure.

**85%** means 85% of hard negatives were correctly ranked below the gold memory.

## 12.6 The recorded results

**These are from the artifact dated 2026-10-28. They were not re-run for this handbook.**

| Section | Result |
|---|---|
| **Formation** | 17 gold / 17 extracted / 17 matched; precision 100%; recall 100%; noise rejection 100%; metadata accuracy 100%; exact-count 100%; duplicate rate 0; false-memory 0%; provenance valid |
| **Retrieval** | top-1 69%; MRR@4 0.846; recall@4 100%; precision@4 34%; hard-negative rejection 85%; mean rank margin 0.085; AUROC 0.759 |
| **Lifecycle** | fact recall 100% (11/11); outcome accuracy 100% (4/4); type accuracy 90% (9/10); state changes 6/6; duplicates 0; persistence 1/1 |
| **Answering** | answerable 100%; unanswerable abstention 100%; false abstentions 0; format 100%; evidence 100%; 9 of 10 turns searched; 6,143 ms average |
| **Causal** | 3 of 4 passed — `c4_hard_negative_injection` failed |
| **Stress** | 5 of 5 passed |

## 12.7 What these numbers prove

- Extraction is selective: 17/17 matched with zero duplicates and zero invented memories in the
  gold set.
- Lifecycle states behave correctly across the six designed scenarios.
- The answering prompt uses evidence, applies a stored format preference, and abstains on the
  unanswerable case.
- The system survives a restart, a deletion, a prompt-injection attempt, 40 distractors, and an
  empty archive.

## 12.8 What these numbers do **not** prove

1. **Retrieval does not test the production threshold.** `run_retrieval` calls
   `retrieve(..., min_similarity=-1.0)` (`evaluate.py:288`). The 0.30 gate that actually runs in the
   app is disabled for the measurement. So top-1 69% is "ranking quality with no floor", not what a
   user experiences.
2. **Four sections bypass extraction.** Retrieval, answering, causal and stress insert episodes with
   `seed_episode`, skipping validation, grounding, dedupe and lifecycle.
3. **Contradictions are unresolved.** `c4` fails: two active memories give different dates for the
   same review, and the answer includes the wrong one.
4. **Small samples.** 13 retrieval cases is an engineering measurement, not statistical proof.
5. **Synthetic data.** The cases are written by hand, not collected from real users.
6. **The router's 30-episode cap is never exercised**, because every test archive is small.

## 12.9 The failed and weak cases, honestly

| Case | What happened | Why it matters |
|---|---|---|
| `c4_hard_negative_injection` | Wrong date in the answer | Contradictory active memories are not resolved in code |
| `l5_date_change` session 2 | Event typed `task`, gold expected `goal` | Labelling disagreement, not a wrong memory |
| `r6`, `r8`, `r10`, `r11` | Gold not ranked first | Near-duplicates, stale vs current scope, negation, multi-hop |
| Calibration 0.20–0.40 | 9% precision | The production threshold admits mostly noise |

---

# 13. Research background

**Important:** none of these papers are cited anywhere in this repository. A search of all `.md`,
`.py` and `.json` files finds **no mention** of CoALA, MemGPT, Reflexion, or Generative Agents.

So this chapter is **background reading**, not a description of what was implemented. It explains
where the ideas in this project come from, and — more usefully — where the project stops short of
them.

## 13.1 CoALA — memory categories

**Paper:** Sumers et al., *Cognitive Architectures for Language Agents*.

**Main idea:** language agents should be organised like cognitive systems, with explicit memory
types:

| Memory | Meaning |
|---|---|
| Working | The current context window |
| Episodic | Specific past events |
| Semantic | General facts and knowledge |
| Procedural | How to perform actions |

**Relation to this project:** the split is visible in the design — working memory is the chat
history, episodic memory is the `episodes` table, semantic memory is approximated by `preference`
episodes, and procedural memory **does not exist**.

**Implemented?** Only the distinction, not the architecture. There is no separate semantic store and
no procedural store.

## 13.2 Generative Agents — reflection

**Paper:** Park et al., *Generative Agents: Interactive Simulacra of Human Behavior*.

**Main idea:** agents keep a stream of observations, periodically **reflect** on them to form
higher-level conclusions, and retrieve memories by a blend of recency, importance, and relevance.

**Relation to this project:** there is a write-time consolidation step (`consolidate_duplicates`)
and a lifecycle, which are cousins of reflection. But this project has **no scheduled reflection
pass** that summarises a long thread into a higher-level belief.

**Implemented?** No. What exists is duplicate merging and state transition, not reflection.

## 13.3 Reflexion — learning from feedback

**Paper:** Shinn et al., *Reflexion: Language Agents with Verbal Reinforcement Learning*.

**Main idea:** after a failure, the agent writes a short verbal lesson and stores it, then uses that
lesson next time. It improves without changing model weights.

**Relation to this project:** the `memory_events` audit trail records *what happened to a memory*,
which is the raw material for this idea. But nothing converts repeated failures into a stored lesson.

**Implemented?** No. This is a plausible future direction, not a current feature.

## 13.4 MemGPT — memory management as an operating system

**Paper:** Packer et al., *MemGPT: Towards LLMs as Operating Systems*.

**Main idea:** treat the context window like RAM and external storage like disk. The agent
explicitly pages information in and out, decides what to keep, and summarises when space runs out.

**Relation to this project:** the closest match conceptually. This project also has a small working
set (chat history) and a large external store (SQLite), and it explicitly chooses what to load. But
MemGPT's core mechanism — the agent managing its own memory budget through tool calls — is **not
implemented here**. This project uses a fixed pipeline: one routing decision, then a top-4 retrieval.

**Implemented?** The *shape* (small context, big archive), not the *mechanism*.

## 13.5 What to say if someone asks "is this a CoALA implementation?"

No. It is a small episodic-memory system whose design is *consistent with* ideas from that
literature. It implements episodic storage with provenance, semantic retrieval, and a lifecycle. It
does not implement reflection, procedural memory, self-managed paging, or verbal reinforcement.

Being precise about this is more impressive than overclaiming.

---

# 14. Current problems

Ordered by how much they matter. Each one: what is wrong, why, an example, the user impact, and a
possible fix.

These are from a read-only audit of the current code. **Bugs and unfinished features are separated.**

## 14.1 Deletion does not really delete (bug)

**What:** `delete_episode` removes the row from `episodes`. But `turn_traces.details` stores the
**complete evidence text** that was shown to the model. That copy survives.

**Why:** `save_trace` (`:749`) serialises the whole `details` dict, which includes `evidence`.

**Example:** delete the MIT license memory, then open **Recent persisted turns**. The evidence block
still contains the memory's text.

**Verified:** in the live database, 16 traces contain episode evidence, and 3 of them reference
episodes that no longer exist.

**Impact:** a user who deletes a memory reasonably expects it gone. It is not.

**Fix:** on delete, redact the evidence text in related traces (or never store raw evidence, only
episode IDs and scores). Add a test that greps the whole database for the deleted text.

## 14.2 Contradictory active memories are not resolved (bug)

**What:** two memories can both be `active` while disagreeing. The answer prompt is told to prefer
the better-supported value, but nothing enforces it.

**Why:** `_apply_lifecycle` only handles completion, cancellation, and replacement. It has no concept
of "two truths about the same attribute".

**Example:** benchmark `c4`. Two memories say the Zephyr review is on 3 March and 17 March. The
answer includes the wrong date.

**Impact:** confident wrong answers on the most dangerous kind of question.

**Fix:** detect attribute-level conflict (same entity + same attribute + different value), then
either prefer the higher-scoring memory and suppress the other, or abstain and say the records
disagree.

## 14.3 The retrieval benchmark does not test the production gate (measurement bug)

**What:** `run_retrieval` passes `min_similarity=-1.0`, disabling the 0.30 filter.

**Why:** it was written to measure pure ranking.

**Example:** the reported top-1 of 69% describes ranking with no threshold. The app always applies
one.

**Impact:** the headline number overstates real-world behaviour.

**Fix:** report both — "ranking (open floor)" and "gated at 0.30". The second is the honest
user-facing number.

## 14.4 Four benchmark sections bypass extraction (measurement gap)

**What:** retrieval, answering, causal and stress use `seed_episode`, which calls the private
`_insert_episode` directly.

**Why:** it isolates ranking from extraction quality — a legitimate reason.

**Impact:** those scores cannot detect extraction failures, and the seeded rows carry fake
provenance (`source_conversation_id="benchmark"`).

**Fix:** add an end-to-end section: conversation in, extraction, retrieval, answer out.

## 14.5 The router goes blind after 30 memories (design limit)

**What:** `decide` (`:1191`) uses `list_episodes()[:30]`, newest first.

**Why:** to keep the routing prompt small.

**Impact:** once you pass 30 memories, an old memory can never influence the decision to search. The
system silently stops finding old things.

**Fix:** retrieve a candidate catalog by embedding similarity instead of recency, or raise the cap,
or let the router run a cheap search first.

## 14.6 The similarity threshold admits mostly noise (tuning bug)

**What:** `MIN_SIMILARITY = 0.30`, but the 0.20–0.40 band is 9% precise.

**Impact:** irrelevant memories enter the answer prompt, which is how false "conflicts" and hedged
answers happen.

**Fix:** raise the floor, or add a relative margin (drop anything more than Δ below the top score),
and measure both.

## 14.7 Extraction prompt grows with the archive (scaling issue)

**What:** in incremental mode, `known_block` (`:843`) lists **every** existing episode title on every
save.

**Impact:** harmless at 16 memories; at 300 it consumes context and cost on every turn, competing
with the transcript inside `num_ctx: 8192`.

**Fix:** cap it, or replace titles with a short summary of the last N.

## 14.8 No vector index (scaling issue)

**What:** every query JSON-decodes and scores every active episode.

**Impact:** fine now; dominates latency later.

**Fix:** an index (FAISS, sqlite-vec) once the archive passes a few hundred rows. Not now.

## 14.9 One embedding mismatch breaks all retrieval (fragility)

**What:** `EmbeddingMismatch` aborts the whole retrieval if any row has a different model or
dimension.

**Why:** comparing vectors from different models is meaningless, and failing loudly beats silent
garbage.

**Impact:** changing `OLLAMA_EMBED_MODEL` makes the archive unusable with no migration path.

**Fix:** skip-and-warn, plus a re-embed command.

## 14.10 Writes are not atomic (robustness)

**What:** inserting an episode and updating an older one use separate connections.

**Impact:** a crash between them leaves a new memory stored and the old one still active.

**Fix:** one transaction covering insert + lifecycle + consolidation.

## 14.11 Lifecycle updates only one older memory (correctness limit)

**What:** `_apply_lifecycle` keeps a single best match.

**Impact:** if three old tasks should close, two stay active and retrievable.

**Fix:** close all matches above the threshold, not just the best.

## 14.12 Consolidation can merge on title alone (correctness risk)

**What:** title word-overlap ≥ 0.45 is enough to merge.

**Impact:** two different memories with formulaic titles can be merged, discarding one summary.

**Fix:** require the embedding similarity as well, or raise the title threshold.

## 14.13 No temporal reasoning (missing feature)

**What:** `event_time` is stored and displayed, never used in ranking.

**Impact:** "what is the **current** scope?" is decided by cosine alone. Case `r8` fails for this
reason.

**Fix:** tie-break or boost by recency among similar scores.

## 14.14 Prompt-injection defence is prompt-only (security limit)

**What:** nothing sanitises stored content.

**Impact:** a memory containing instructions is defended only by the answer model ignoring them.
`stress/s3` currently passes, but that is one case.

**Fix:** strip or neutralise instruction-like content at write time.

## 14.15 Rejected-everything turns are never retried (data-loss bug)

**What:** if extraction returns candidates but all are rejected, messages are still marked formed.

**Impact:** a message that trips the grounding check is silently never remembered.

**Fix:** only mark formed when at least one episode is stored, or when the batch was genuinely
empty.

## 14.16 Deletion leaves orphan audit rows (bookkeeping)

**What:** `memory_events` has no foreign key; rows survive after deletion.

**Impact:** counting queries overstate the archive. Arguably correct for an audit log, but
undocumented.

**Fix:** document it, or add a foreign key with `ON DELETE SET NULL`.

## 14.17 Small engineering issues

- No index on `messages(conversation_id)`.
- No index on `episodes(status)`.
- `conversations.status` and `ended_at` are written and never read.
- `is_trivial_turn` is exact-match ("ok, thanks!" slips through).
- `handle_turn` does not save traces; only `app.py` does, so benchmark turns are untraced.
- Three representations of a memory (`Episode` model, dict rows, JSON columns).
- Two dedupe paths with different predicates.
- `event_time` is a free-form string, never parsed.
- The sidebar renders the whole archive with no pagination.

## 14.18 Limitations of a single-user prototype

Not bugs — design boundaries you should state plainly:

- **No user concept at all.** No `user_id` column anywhere. Two people cannot share an instance
  safely.
- **No authentication.**
- **No concurrency control.** One Streamlit session is assumed.
- **No backup or migration tooling.**
- **No approval step.** Every accepted memory is immediately active.
- **No editing.** Delete and re-add is the only correction.

Saying these out loud is better than pretending the demo is a product.

---

# 15. What should happen next

Proposals, not current features. Ordered by what actually improves the research claim.

## 15.1 Fix deletion propagation — **do this now**

**Why:** deletion is part of the memory contract. Right now it is false.
**Addresses:** 14.1.
**How to test:** delete a memory, then query every table for its text; assert zero hits.
**Effort:** small.
**Verdict:** highest priority. It is a correctness bug, not a feature gap.

## 15.2 Resolve contradictory memories in code — **do this now**

**Why:** a memory system that confidently reports the wrong date is worse than one that says "the
records disagree".
**Addresses:** 14.2.
**How to test:** make `c4` pass for a stated reason, and add cases for "two values, one newer" and
"two values, genuinely ambiguous".
**Effort:** medium.
**Verdict:** do it before adding features.

## 15.3 Make the measurement honest — **do this now**

**Why:** everything else is guesswork if the numbers describe a different system than the one users
run.
**Addresses:** 14.3, 14.4.
**How:** report retrieval with and without the gate; add one end-to-end section (conversation →
extraction → retrieval → answer, no seeding).
**Effort:** medium.
**Verdict:** do it alongside 15.1 and 15.2, because it tells you whether those fixes worked.

## 15.4 Remove the 30-episode routing limit — **soon**

**Why:** this is a silent failure that only appears with real use.
**Addresses:** 14.5.
**How:** select the catalog by similarity to the question instead of recency.
**How to test:** a 40-memory case where the relevant memory is the oldest.
**Effort:** medium.
**Verdict:** soon. It is cheap and it removes a cliff.

## 15.5 Calibrate the threshold — **soon**

**Why:** the 0.20–0.40 band is 9% precise.
**Addresses:** 14.6.
**How:** raise the floor, or add a relative margin. Measure precision and recall at each setting
instead of guessing.
**Effort:** small, but needs the honest measurement from 15.3 first.
**Verdict:** soon.

## 15.6 Temporal retrieval — **later**

**Why:** "what is current?" is a real user question and cosine cannot answer it.
**Addresses:** 14.13.
**How:** use `event_time` as a tiebreaker among close scores; test with `r8`.
**Effort:** medium.
**Verdict:** after the correctness work.

## 15.7 Hybrid search — **later**

**Why:** dense-only retrieval is why the low band is noisy. Exact words still matter.
**Addresses:** 14.6 indirectly.
**How:** combine cosine with BM25 or simple keyword overlap, then measure. Do not add it before
having an honest baseline.
**Effort:** medium.
**Verdict:** only after 15.3 and 15.5, or you will not know whether it helped.

## 15.8 Engineering hardening — **later**

Atomic writes, an index on `messages(conversation_id)`, skip-and-warn on embedding mismatch,
re-embed tooling, retry-on-all-rejected. Individually small; collectively they make the system
trustworthy.
**Addresses:** 14.8–14.10, 14.15, 14.17.

## 15.9 Hierarchical memory and consolidation — **much later**

**Why:** eventually you want summaries of summaries — "the project's history" instead of forty
episodes.
**Addresses:** the scaling direction behind 14.7 and 14.8.
**How:** periodic summarisation of a topic cluster into a higher-level episode, with links down to
the originals.
**Verdict:** do not start this yet. Building hierarchy over noisy retrieval adds complexity without
improving the claim.

## 15.10 What **not** to do

- Do not rewrite the engine.
- Do not adopt a vector database for 16 memories.
- Do not add LangChain-style orchestration.
- Do not add multi-user support unless the research question needs it.

Every problem above is local. The architecture is proportionate.

---

# 16. Beginner FAQ

**Where are my memories stored?**
In `memory.db`, in the `episodes` table. One row per memory.

**Does the AI remember messages automatically?**
Yes. After every reply, `app.py:251` runs extraction. There is no save button.

**Does every message become a memory?**
No. Greetings are skipped. Small talk, hypotheticals, and the assistant's own advice are rejected by
the prompt. Invented facts are rejected by the grounding check. In a typical chat, most messages
produce nothing.

**What is the difference between a message and an episode?**
A **message** is raw text, exactly as typed. An **episode** is a cleaned, structured memory with a
title, type, date, facts, and source IDs. Many messages can produce one episode; one message can
produce several.

**What is an embedding?**
A list of 768 numbers representing the meaning of a piece of text.

**Why do we need two models?**
One writes language; one measures meaning. Qwen cannot produce reliable meaning-vectors, and
EmbeddingGemma cannot write an answer.

**How does the application find an old memory?**
It converts your question into numbers, compares it to every stored memory by cosine similarity,
keeps the closest ones above 0.30, and passes the top 4 to the answer model.

**Can it remember something after restarting?**
Yes. Everything is in SQLite. The visible chat resets; the archive does not.

**What happens when the user corrects an old fact?**
A new episode is stored. `_apply_lifecycle` marks the old one `superseded` if similarity ≥ 0.72, and
superseded memories stop being retrieved. You can still see the old one with "Show superseded".

**What happens when there are no matching memories?**
The evidence becomes the literal string "No episodic memories matched this query." and the model is
instructed to say it found nothing rather than guess.

**How can I see which memory supported an answer?**
Expand **Retrieval details** under the reply. It shows episode IDs, titles, scores, source message
IDs, and the exact evidence text.

**How can I run the application?**
```bash
cd episodic-memory-demo
source .venv/bin/activate
streamlit run app.py
```

**How do I run the tests?**
```bash
source .venv/bin/activate
pytest -q
```
Expect `27 passed`.

**How can I add a new benchmark case?**
Open the relevant `benchmark/*.json` file and append an object in the same shape as its neighbours.
[`BENCHMARK_GUIDE.md`](BENCHMARK_GUIDE.md) documents each section's required fields. Then run
`python evaluate.py --sections formation` (or whichever section) to check just that part.

**Which file should I inspect first when something breaks?**
`memory_engine.py`. If the problem is in what gets stored, read `form_memories` (`:802`). If it is a
wrong answer, read `retrieve` (`:1148`) and `answer` (`:1213`). If it is a missing search, read
`decide` (`:1189`). If a button misbehaves, read `app.py`.

---

# 17. Intern onboarding, step by step

Verified against `README.md` and the code.

## 17.1 Set up the environment

```bash
git clone <this-repo-url> episodic-memory-demo
cd episodic-memory-demo
python3 -m venv .venv
source .venv/bin/activate
```

Any Python 3.10+ should work; 3.12 is what the README records.

## 17.2 Install dependencies

```bash
pip install -r requirements.txt
```

That installs: `streamlit`, `ollama`, `pydantic`, `numpy`, `python-dotenv`, `pytest`. The file uses
`>=` ranges, so exact versions may differ from the original machine.

## 17.3 Start Ollama

```bash
ollama serve
```

Or start the Ollama desktop app. It listens on `127.0.0.1:11434` by default.

## 17.4 Download the models

```bash
ollama pull qwen3.5:9b
ollama pull embeddinggemma
ollama list
```

You should see both names. The chat model is about 6.6 GB; the embedding model about 621 MB.

## 17.5 Configure environment variables

```bash
cp .env.example .env
```

Defaults:

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_CHAT_MODEL=qwen3.5:9b
OLLAMA_EMBED_MODEL=embeddinggemma
DATABASE_PATH=./memory.db
MEMORY_TOP_K=4
MEMORY_MIN_SIMILARITY=0.30
```

⚠️ **If you change `OLLAMA_EMBED_MODEL`,** old episodes will not match the new model, and retrieval
raises `EmbeddingMismatch`. Delete or recreate the database if you switch intentionally.

## 17.6 Start the app

```bash
streamlit run app.py
```

Open the URL it prints, normally <http://localhost:8501>.

## 17.7 Run the example conversation

In the sidebar, click **Load demo conversation & extract memories**.

This inserts ten dated fictional messages and runs the real extraction pipeline. Wait for the
success banner. You should see new memories in the sidebar.

## 17.8 End the conversation and inspect episodes

Ask the four demo questions, one at a time:

1. Why was the retrieval experiment blocked?
2. Who completed deletion testing, and when?
3. What was Mira responsible for?
4. What retrieval accuracy did the team achieve?

Expected: the first three cite stored evidence. The fourth says the records do not establish a
numerical retrieval-accuracy result.

Now expand the sidebar episodes. Look at the facts, the source message IDs, and the event history.
Then click **End session** to see the memories saved during this session.

## 17.9 Start a fresh conversation

Click **Start fresh session**. The chat is empty. The sidebar archive is unchanged.

## 17.10 Ask a question that needs old information

Ask: "Why did we choose SQLite?"

You should get an answer citing the storage decision, retrieved from a conversation that is no longer
on screen.

## 17.11 Inspect the retrieval trace

Expand **Retrieval details** under the answer. Check:

- `Memory retrieval enabled: True`
- `Model requested memory: True`
- the search query it generated,
- the episode ID and similarity score,
- the evidence text.

Then open the sidebar's **Recent persisted turns** and find the same turn. That is the same
information, read back from SQLite after the fact.

## 17.12 Turn retrieval off and compare

Toggle **Use memory retrieval** off. Click **Start fresh session**. Ask "Why did we choose SQLite?"
again.

You should get a refusal: the model cannot check the archive because retrieval is off. It must not
claim that no memories exist.

Turn the toggle back on.

## 17.13 Run the tests

```bash
pytest -q
```

Expect `27 passed`. These do not call Ollama, so they run in under a second.

## 17.14 Run the benchmark

```bash
python evaluate.py
```

This uses **temporary databases only** — it never touches `memory.db`. It takes several minutes
because it calls the real models.

Outputs:

```text
eval_results/eval_report.md
eval_results/raw.json
```

To run one section while iterating:

```bash
python evaluate.py --sections formation
python evaluate.py --sections retrieval,lifecycle
```

To run the manual real-model smoke test without the full benchmark:

```bash
python -m memory_engine
```

---

# 18. Glossary

| Word | Plain meaning |
|---|---|
| **Agent** | A program that pursues a goal over several steps, using tools, instead of answering once. |
| **LLM** | Large Language Model. A model trained on huge amounts of text to predict and produce language. |
| **Chat model** | An LLM used to read and write text: summarise, decide, answer. |
| **Embedding model** | A model that converts text into a list of numbers representing meaning. |
| **Context window** | How much text a model can consider at once. Here, `num_ctx: 8192` tokens. |
| **Token** | A chunk of text, roughly a word piece. Models count in tokens, not characters. |
| **Episodic memory** | Memory for specific events: what happened, when, who, and how it turned out. |
| **Semantic memory** | Memory for general facts and stable preferences, not tied to one event. |
| **Working memory** | The information currently in front of the model — the active context. |
| **Procedural memory** | Memory for how to perform skills. **Not implemented here.** |
| **Episode** | One structured memory record in this project: title, type, time, summary, facts, sources. |
| **Embedding** | The numeric representation of a piece of text. |
| **Vector** | An ordered list of numbers. An embedding is a vector. |
| **Dimension** | How many numbers are in a vector. Here, 768. |
| **Cosine similarity** | A number from -1 to 1 measuring the angle between two vectors. 1 means same direction. |
| **Retrieval** | Finding stored information relevant to a query. |
| **RAG** | Retrieval-Augmented Generation. Supplying retrieved text to a model so it can answer from evidence. |
| **Prompt** | The text sent to a model, including instructions and data. |
| **System prompt** | The instruction part of a prompt that sets the model's role and rules. |
| **Structured output** | Constraining a model to emit JSON in a known schema instead of free text. |
| **Pydantic** | A Python library that validates data against a declared shape. |
| **JSON** | A text format for lists and key-value objects. |
| **SQLite** | A database that lives in a single file, with no server. |
| **Primary key** | The column that uniquely identifies a row. |
| **Foreign key** | A column pointing at a primary key in another table. |
| **SQL query** | A sentence asking the database for data, like `SELECT ... WHERE ...`. |
| **Transaction** | A group of database changes that all succeed or all fail. |
| **Provenance** | Proof of origin: which conversation and which messages a memory came from. |
| **Supersession** | Marking an old memory as replaced by a newer one, without deleting it. |
| **Consolidation** | Merging near-duplicate memories into one. |
| **Lifecycle** | The states a memory passes through: active → done / superseded / cancelled. |
| **Grounding** | Checking that a claim is supported by its source text. |
| **Abstention** | Saying "I don't know" instead of guessing. |
| **Top-k** | Returning the k best results. Here, k = 4. |
| **Threshold** | The minimum score a result needs to be accepted. Here, 0.30. |
| **Hard negative** | A deliberately confusing wrong item that a good system should rank below the right one. |
| **Precision** | Of the things stored or returned, how many were correct. |
| **Recall** | Of the things that should have been found, how many were. |
| **Precision@K / Recall@K** | The same, calculated within the top K results. |
| **MRR** | Mean Reciprocal Rank. Average of 1/rank of the first correct result. |
| **Top-1 accuracy** | How often the single best result is correct. |
| **AUROC** | A single number for how well scores separate relevant from irrelevant. 0.5 = random, 1.0 = perfect. |
| **Calibration** | Whether a score means what it claims. A 0.4 score should be relevant about 40% of the time. |
| **Latency** | How long a turn takes. |
| **Benchmark** | A fixed set of test cases with known correct answers. |
| **Mock** | A fake stand-in for a real component, used to test code without calling a model. |
| **Deterministic** | Same input, same output, every time. |
| **Temperature** | A sampling setting. 0 means as deterministic as the model allows. |
| **Top-k sampling** | How many candidate tokens the model chooses among. `top_k=1` means always pick the best. |
| **Hallucination** | A model stating something that is not supported by its inputs. |

---

# 19. Quick reference card

Keep this page open while exploring.

| Thing | Value |
|---|---|
| Chat model | `qwen3.5:9b` |
| Embedding model | `embeddinggemma`, 768 dimensions |
| Ollama address | `http://127.0.0.1:11434` |
| Database | `./memory.db` |
| Tables | `conversations`, `messages`, `episodes`, `turn_traces`, `memory_events`, `formed_messages` |
| Retrievable statuses | `active`, `done` |
| Min similarity | 0.30 |
| Top-k | 4 |
| Duplicate similarity | 0.90 |
| Supersede similarity | 0.72 |
| Lifecycle link similarity | 0.45 |
| Grounding overlap | 0.35 |
| Max extraction chars | 6,000 |
| Context window | 8,192 tokens |
| Router catalog cap | 30 episodes |
| Unit tests | 27 |
| Benchmark cases | 51 |
| LLM calls per turn | 3 chat + 2 embedding |
| App entry point | `app.py` |
| Engine entry point | `MemoryEngine` in `memory_engine.py` |
| Benchmark entry point | `python evaluate.py` |

---

## Final note to the intern

The code is small enough to read in an afternoon. Read `EXTRACTION_SYSTEM` first — that prompt is
where most of the system's judgement lives. Then read `form_memories` top to bottom. Then read
`retrieve` and `answer`.

Everything else is plumbing around those four things.

And when you present this: be precise about what is proven. The system genuinely forms episodic
memories from conversation, genuinely retrieves them across sessions, and genuinely abstains when it
has nothing. Those are real. What is not yet solved is deletion completeness, contradiction
resolution, and honest retrieval measurement. Knowing the difference between those two lists is the
most useful thing you can bring.
