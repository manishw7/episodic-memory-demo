# Demo and Visual Views — Memory Map and Time Machine

This document explains the two visual screens, the live-write flow, and the demo script.

---

## 1. Why two views

The original app only had chat. For a mentor demo we needed to **see** the memory. So two
new views were added on top of the existing Chat:

- **Memory Map** — a live constellation of every memory and how they connect.
- **Time Machine** — travel to any day and see what the bot knew then.

Nothing in the chat path was removed or changed. The chat still works exactly as before.

## 2. Memory Map

### What you see

- One dot per memory. Colour = state (green active, blue completed, amber replaced,
  red cancelled). Shape = project (circle Atlas, square Beacon, triangle Cinder,
  triangle-down your own writes).
- **Coloured arrows** = state changes (e.g. old memory replaced by new one).
- **Grey lines** = two memories are similar in meaning (cosine ≥ 0.65).
- **Purple diamonds** = a person who appears in more than one project (a bridge).
- **Cluster labels** = project name + count (e.g. "ATLAS · 18").
- Hover a dot for title, project, state, people, learned date, summary.

### How it is built (derived at render time, not stored)

1. Load all episodes with embeddings.
2. Project embeddings to 2D with PCA. The basis is computed once and cached in session
   state, so existing dots do not move when a new memory is added.
3. Build lifecycle edges (superseded → replacement).
4. Build similarity edges (top 2 neighbours per node above the floor, excluding
   lifecycle pairs).
5. Build person hubs (people spanning ≥ 2 projects) and their edges.
6. Render with Altair. Hover tooltips come from the data frame.

### Live writes (sidebar → "Try a live write")

Each button runs the **real** extractor on a fresh standalone conversation:

| Button | Sentence written | What you should see |
|---|---|---|
| Change a date | "Priya's review of the Atlas demo script is now due on 20 November 2026." | Old Priya dot turns amber, a coloured arrow appears, halo for 30 s, count 50→51. |
| Add a task | "Noah's Beacon launch retro is due on 21 November 2026." | New square in Beacon, linked to Noah. |
| Add an update | "Cinder now runs a nightly integrity check on the analytics tables." | New triangle in Cinder, linked to existing Cinder memories. |

- `incremental=False` is used because incremental extraction appends the whole known
  memory list to the prompt and the model stops extracting novel facts once the archive
  is large.
- A fresh conversation avoids polluting existing conversations.
- **Write your own memory** accepts any sentence and a project tag (just for the shape).

### Search

Type a question in "Ask the map" and click "Highlight related memories". Matching dots
get a bright blue ring and their scores appear on the right. This uses the same
embedding retrieval as the chat.

### Delete

At the bottom: "Manage: delete a memory and watch the links disappear". Pick a memory,
click Delete. The dot and all its lines vanish; counts update; a deleted event is logged.

### Live feed and metrics (right panel)

- Memories, Links, People, Projects counts.
- State line (active / completed / replaced / cancelled).
- Map matches (when searching).
- Live feed of the 6 most recent events.
- People across projects (name, projects, memory count).

## 3. Time Machine

### What you see

- A stepped area chart of memory counts over time, coloured by state.
- A dashed vertical line marking the selected date.
- A date slider and three presets.
- Four metric cards: Memories known, Active, Completed, Replaced or cancelled.
- A "What changed on …" list for the selected day.
- A "Memories the system knew" list grouped by project.

### How it works

The state on any day is **reconstructed** from `memory_events`:

1. Sort all events by time.
2. Replay them: `created` → active, `done`/`cancelled`/`superseded` → that state,
   `deleted` → removed.
3. Snapshot the state at the end of the chosen day.

So the Time Machine is not a stored snapshot — it is computed on demand from the audit
trail. This is why deleting a memory still shows it in the history before the deletion.

### Presets

- **Scope change · 12 Oct** — Atlas changed from a cloud service to a local prototype.
  Shows 24 known memories (23 active, 1 replaced).
- **Launch day · 6 Nov** — busy Beacon/Cinder day.
- **Today** — where your live writes appear.

## 4. The demo archive (`demo.db`)

- 50 memories across three interlocking projects: **Atlas (18), Beacon (17), Cinder (15)**.
- 17 sessions, 50 messages, 68 audit events.
- All four lifecycle states. Supersession chains, completed tasks, cancellations.
- Shared people (Mira, Asha, Ravi, Priya, …) link the clusters.
- Built once by the real extractor and committed, so the demo looks identical everywhere
  and starts instantly.

Rebuild or inspect:

```bash
source .venv/bin/activate
python scripts/build_demo_db.py --force   # rebuild (uses the models)
python scripts/build_demo_db.py --check   # inspect, no model calls
```

The builder refuses to write to `memory.db`.

## 5. Demo flow (suggested, ~20 minutes)

1. Start: `./start.sh --demo`. Open <http://localhost:8501>.
2. **Memory Map**: show the three clusters, hover a dot, explain colours and shapes.
3. Click **Change a date** in the sidebar. Wait for the success message. Show the amber
   dot, the arrow, the halo, the count change, and the live feed.
4. Click **Add a task**, then **Add an update**. Show new nodes and links.
5. Search "what changed with the schema?" → blue rings + scores.
6. Delete one of the just-added memories → dot and links vanish.
7. **Time Machine**: click "Scope change · 12 Oct" → 24 known, change list, grouped
   memory list. Drag the slider. Click "Today" to see your own changes.
8. **Chat**: click "Load demo conversation & extract memories", wait for the banner.
9. Ask the four questions (see `docs/OPERATIONS.md` / README §6). Open "Retrieval
   details" under each answer.
10. Turn retrieval off and ask again to prove memory does the work.
11. Restore the archive: `./stop.sh`, `git checkout -- demo.db`, `./start.sh --demo`.

## 6. Restore after rehearsing

```bash
./stop.sh
git checkout -- demo.db
./start.sh --demo
```

`memory.db` is never opened in demo mode, so your real notebook is untouched.<|end|><|start|>write to=assistant<|channel|>analysis <|constrain|>xml<|message|><rfl:parameter name="content">
# Development History — What Was Done

A chronological record of the work, so a new intern can see how the project got to its
current state. Commits are listed oldest to newest.

---

## Phase 0 — Foundation (commits `cc72d19` … `447c815`)

- Project scaffolding: Python, requirements, `.env.example`.
- `memory_engine.py`: the full engine — prompts, schema, SQLite, extraction, retrieval,
  answering, lifecycle, dedup, deletion, traces.
- Single-page Streamlit UI (`app.py`): chat, sidebar archive, evidence panels.
- 27 unit tests with a fake model (no Ollama needed).
- 51-case memory-contract benchmark.

## Phase 1 — Benchmark and docs (commits `1f79d49`, `9cad247`, `8ba375d`)

- Recorded benchmark run dated 2026-10-28 (formation 17/17, abstention 100%, etc.).
- Mentor-facing README and project documentation.
- Real clone URL in setup steps.

## Phase 2 — One-command run (commit `df56616`)

- `start.sh` and `stop.sh`: check Python, install deps, start Ollama, check models,
  start Streamlit, open browser. Safe to run twice. `--demo`, `--no-browser`,
  `--status`, `--keep-ollama`, `--clean`.

## Phase 3 — Prebuilt demo archive (commit `8417072`)

- `demo.db`: a synthetic four-week story ("Project Atlas"), 17 memories, every lifecycle
  state, three supersession chains.
- `--demo` mode: uses `demo.db`, never `memory.db`.
- Builder refuses to write to `memory.db`.

## Phase 4 — Three-project archive + engine fixes (commit `2d81009`)

- Expanded the story to three projects: **Atlas, Beacon, Cinder** (50 memories, 17
  sessions, 50 messages).
- Each project is built in its own archive, then merged, so later projects are not
  suppressed by the extractor's known-memory list.
- Engine fix: speaker roles (`user`, `assistant`, `system`) are ignored when matching
  participants. "user" no longer makes two different owners look like the same assignment.
- Engine fix: title-based merging now requires content overlap (0.35), so generic titles
  like "Project X definition" do not merge across projects.
- Regression tests for both fixes. Test count: 22 → 29 passing.
- `scripts/story.py` and `scripts/build_demo_db.py` updated.

## Phase 5 — Visual views (commit `52738f5`)

- `app.py` rewritten with a three-way view switcher (Chat / Memory Map / Time Machine)
  on `st.segmented_control`, so `st.chat_input` only renders in Chat.
- New `demo_views.py`: Memory Map and Time Machine implementation.
- Memory Map: nodes, lifecycle/similarity/person-hub edges, project centroids, metrics,
  live feed, hover details, search highlighting, halo, write box, one-click examples,
  delete control.
- Time Machine: status-as-of-date reconstruction from `memory_events`, stacked area
  history, selected-day rule, presets, counts, change list, full known-memory list.
- Live writes: sidebar buttons + custom text, running the real extractor on a fresh
  standalone conversation.
- Visual fixes after review: state legend restored, theme-safe label colours, amber halo,
  blue match rings, sidebar write controls, auto-refresh removed.
- README: new views, live demo flow, restore procedure, deep links, updated counts.
- Deep links: `?view=Memory+Map`, `?view=Time+Machine`.

## Key decisions (why things are the way they are)

- **`st.segmented_control` instead of `st.tabs`**: all tabs render at once, so
  `st.chat_input` would appear on every view.
- **Graph derived at render time**: no stored diagram. Every write changes it immediately.
- **PCA basis cached in session state**: existing dots do not move when a new memory is
  added.
- **Live writes use `form_memories(..., incremental=False)`** on a fresh conversation:
  incremental extraction appends the whole known-memory list and the model stops
  extracting novel facts once the archive is large.
- **Build each project in its own archive, then merge**: a shared known-memory list
  suppressed later projects' setup facts.
- **No new dependencies**: Altair + pandas already ship with Streamlit.
- **Local-only Ollama, single-page Streamlit, no vector/graph DB, no agent framework.**
- **`memory.db` never touched by demo features.**
- **`demo.db` is prebuilt and committed** for identical visuals and instant startup.

## Bugs found and fixed during this work

- Speaker roles included in participant matching → fixed.
- Title-only merges merged unrelated memories across projects → fixed.
- Per-project facts suppressed in a shared archive → fixed by per-project builds.
- Cinder team memory merged into the project definition → fixed by separating the
  session and rewording.
- Priya's bridge memory accidentally "completed" the Atlas presentation goal → fixed
  by making it a task with a due date.
- Map state legend missing (merged with a `legend=None` layer) → fixed.
- Project labels invisible on dark theme → fixed.
- Write controls below the map scrolled the map out of view → moved to sidebar.

## Test count over time

- 27 tests (initial).
- 29 tests (after speaker-role and title-merge regressions).

## Known open issues

See `docs/IMPROVEMENTS.md` and `docs/AUDIT.md`. Highlights: date hallucination (no
current date in prompt), `event_time` often empty, routing inconsistency, two
"best friends" coexist, contradictions not resolved in code, deletion leaves traces.