# Improvements — What to Do Next

Prioritised list of improvements, from highest value to lowest effort. Each item states
the problem, the proposed fix, the effort, and the risk.

---

## High value, small effort

### 1. Inject the current date into the answer prompt
- **Problem:** The model has no idea what "today" is. It invented "today is before 18
  November 2026" when today was 25 November 2026.
- **Fix:** Add `Today is {utc_now()[:10]}.` to the answer system prompt.
- **Effort:** small. **Risk:** low. Add a test that the prompt contains the date.

### 2. Fill `event_time` during extraction
- **Problem:** Dates like "since 18 November 2026" land only in the summary; `event_time`
  stays empty. Time-based logic cannot use a clean date.
- **Fix:** Update the extraction prompt to require `event_time` for any stated date, and
  validate that a stated date appears in `event_time` or facts.
- **Effort:** small–medium. **Risk:** low. Add tests on the fake model.

### 3. Exclusivity for "best friend" (and similar unique relations)
- **Problem:** A new "Sugam is my best friend" does not retire "Nabin is my best friend".
  Two active memories coexist and every answer lists both.
- **Fix:** Detect unique-relation attributes and supersede the older one when a new value
  arrives. Could be a small rule in `_apply_lifecycle` plus a list of unique relations.
- **Effort:** medium. **Risk:** medium (must not over-supersede).

### 4. Routing stability
- **Problem:** The same question sometimes searches and sometimes does not, producing
  "I don't have information" even when a memory exists.
- **Fix:** Always search when the archive is non-empty, or retry once on a "no" decision.
- **Effort:** small. **Risk:** low (slightly more retrieval calls).

## Medium value, medium effort

### 5. Write-before-answer ordering
- **Problem:** Memories are written after the reply, so a fact stated in the same turn
  is "unknown" until the next turn.
- **Fix:** Either run extraction before answering (slower) or surface just-written
  memories in the reply.
- **Effort:** medium. **Risk:** latency.

### 6. Force-layout map
- **Problem:** PCA projection leaves clusters uneven and the right side sparse on a
  projector.
- **Fix:** Add a small spring layout seeded by PCA, cached by episode ID, with new nodes
  placed near their nearest neighbour.
- **Effort:** medium. **Risk:** visual instability if not cached.

### 7. Reset demo button
- **Problem:** Rehearsing accumulates live memories; restoring requires stopping the app.
- **Fix:** Keep a `demo.seed.db` copy (created by `start.sh --demo`) and a sidebar
  button that copies it back and clears session state.
- **Effort:** small. **Risk:** low.

### 8. Complete deletion
- **Problem:** `turn_traces.details` keeps a copy of evidence text after deletion.
- **Fix:** Scrub evidence from traces on delete, or mark traces as "contains deleted
  memory".
- **Effort:** small–medium. **Risk:** low.

## Lower value / polish

### 9. Contradiction resolution in code
- **Problem:** Only a prompt rule handles conflicts; benchmark case `c4` fails.
- **Fix:** Detect same-attribute conflicts and pick the better-supported value.
- **Effort:** medium. **Risk:** medium.

### 10. Routing sees only 30 newest episodes
- **Problem:** Older memories cannot influence the decision to search.
- **Fix:** Summarise or page the episode list, or always search when non-empty.
- **Effort:** small. **Risk:** low.

### 11. Abstention wording
- **Problem:** The bot sometimes says "I don't have information" even when a memory
  exists but was not retrieved.
- **Fix:** Distinguish "no relevant memory found" from "retrieval turned off".
- **Effort:** small. **Risk:** low.

### 12. Dark/light theme for chart colours
- **Problem:** Label colours are a compromise; not ideal on either theme.
- **Fix:** Detect `st.get_option("theme.base")` and pick a palette.
- **Effort:** small. **Risk:** low.

### 13. Map legend tidy-up
- **Problem:** Two legend rows (State, Project) take vertical space.
- **Fix:** Merge into one row or replace the shape legend with a caption.
- **Effort:** small. **Risk:** low.

## Things to NOT change (they work)

- The evidence panel and abstention behaviour.
- The lifecycle arrows and audit trail.
- The prebuilt demo archive and `--demo` mode.
- The test suite's fake-model approach (fast, no Ollama).
- The "no new dependencies" rule.<|end|><|start|>write to=assistant<|channel|>analysis <|constrain|>xml<|message|><rfl:parameter name="content">
# Operations — Run, Demo, Restore, Troubleshoot

Everything you need to start, stop, demo, and recover.

---

## 1. Prerequisites

- macOS or Linux.
- Python 3.10+ (verified on 3.12).
- Ollama running locally (`http://127.0.0.1:11434`).
- Models: `qwen3.5:9b` (chat) and `embeddinggemma` (embeddings).
- ~8 GB free RAM.

## 2. First-time setup

```bash
git clone https://github.com/manishw7/episodic-memory-demo.git
cd episodic-memory-demo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Pull the models (once):

```bash
ollama pull qwen3.5:9b
ollama pull embeddinggemma
```

## 3. Run (real mode — uses `memory.db`)

```bash
./start.sh            # starts Ollama + models + app, opens browser
# or
source .venv/bin/activate
streamlit run app.py
```

Open <http://localhost:8501>. The first AI action can take 20–60 seconds (model load).

Stop:

```bash
./stop.sh             # stops app, unloads models, frees port
./stop.sh --keep-ollama   # leave Ollama running
./stop.sh --clean         # also delete logs and saved state
```

## 4. Run (demo mode — uses `demo.db`, never `memory.db`)

```bash
./start.sh --demo
./start.sh --demo --no-browser   # do not open a tab
```

Use this for demos and testing. `memory.db` is never opened.

## 5. Environment variables (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Where Ollama listens. |
| `OLLAMA_CHAT_MODEL` | `qwen3.5:9b` | Chat model. |
| `OLLAMA_EMBED_MODEL` | `embeddinggemma` | Embedding model. |
| `DATABASE_PATH` | `./memory.db` | SQLite file. |
| `MEMORY_TOP_K` | `4` | Max memories passed to the answer model. |
| `MEMORY_MIN_SIMILARITY` | `0.30` | Minimum cosine score for evidence. |

## 6. Rebuild the demo archive

After changing `scripts/story.py`:

```bash
source .venv/bin/activate
python scripts/build_demo_db.py --force   # rebuild (uses models, ~minutes)
python scripts/build_demo_db.py --check   # inspect, no model calls
```

The builder refuses to write to `memory.db`.

## 7. Restore a pristine demo archive after rehearsing

```bash
./stop.sh
git checkout -- demo.db
./start.sh --demo
```

## 8. Tests and benchmark

```bash
source .venv/bin/activate
pytest -q                      # 29 passed, < 1 s, no Ollama
python -m py_compile app.py demo_views.py memory_engine.py
python evaluate.py             # full benchmark, several minutes, real models
python evaluate.py --sections formation,retrieval   # one section
python -m memory_engine        # real-model smoke test
```

The benchmark never touches `memory.db`; it uses a temporary database.

## 9. Troubleshooting

| Problem | What to do |
|---|---|
| First AI action is slow (20–60 s) | Normal — the model is loading. Wait; do not click twice. |
| Map does not change after a write | Wait a few seconds, then refresh the page. Check the "Memories" number. |
| Sidebar buttons missing | Expand the sidebar (arrow top-left). They appear on the Memory Map view. |
| Halo disappeared | It lasts 30 seconds by design. The live feed keeps the event. |
| Red error under an answer | Check Ollama: `./start.sh --status`. Restart with `./start.sh --demo`. |
| Port 8501 in use | `STREAMLIT_PORT=8502 ./start.sh` |
| Want a clean slate | Stop, delete `memory.db`, start again. |
| Tests fail | Make sure you are in the venv and did not edit `memory_engine.py` carelessly. Run `git diff`. |
| `demo.db` missing | `start.sh --demo` rebuilds it automatically. |

## 10. Useful flags

```bash
./start.sh --demo              # use the synthetic demo archive
./start.sh --no-browser        # do not open a tab
./start.sh --status            # show what is running
./stop.sh --keep-ollama        # leave Ollama running
./stop.sh --clean              # delete logs and saved state
STREAMLIT_PORT=8502 ./start.sh # different port
```

## 11. Safety notes

- Single user, no auth. Do not expose the Streamlit server publicly.
- `memory.db` is git-ignored. Do not commit it.
- `demo.db` is committed and must stay pristine; restore with `git checkout -- demo.db`.
- All inference is local. No API keys anywhere in the project.