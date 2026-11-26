# Handoff Document — Episodic Memory (for new interns)

This is the master handoff. It records **what exists, what was done, what changed, how to run
it, how to continue, and what to improve**. Read `docs/OVERVIEW.md` first for the big picture,
then come back here.

---

## 1. Project identity

- **Name:** Episodic Memory Demo (`episodic-memory-demo`)
- **Repo:** `https://github.com/manishw7/episodic-memory-demo.git`
- **Latest commit:** `52738f5` — "feat: Memory Map and Time Machine views with live writes"
- **Previous commit:** `2d81009` — "feat: three-project demo archive with denser cross-links"
- **Stack:** Python 3.12, Streamlit, SQLite, Ollama (`qwen3.5:9b` + `embeddinggemma`)
- **No cloud, no API keys, no agent framework, no vector DB.** Local only.
- **Tests:** 29 fast tests (`pytest -q`), no Ollama needed. Benchmark: 51 cases.

## 2. What the system does (one paragraph)

A chatbot with a notebook. It reads conversations, extracts durable facts as structured
"episodes", stores them in SQLite, and retrieves the right ones by meaning in later chats.
It can update, complete, cancel, supersede, or delete memories, and it can abstain when it
does not know. On top of that it has two visual screens: a live **Memory Map** and a
**Time Machine**. Everything runs locally.

## 3. What is finished (status)

| Area | Status | Notes |
|---|---|---|
| Core engine (`memory_engine.py`) | ✅ Done | Extraction, retrieval, answering, lifecycle, dedup, deletion, traces. |
| Single-page Streamlit UI (`app.py`) | ✅ Done | Chat, sidebar, evidence panels, view switcher. |
| Prebuilt demo archive (`demo.db`) | ✅ Done | 50 memories, 3 projects, all lifecycle states. |
| `start.sh` / `stop.sh` | ✅ Done | One-command start/stop, `--demo` mode, `--no-browser`, `--status`. |
| Engine fixes (speaker roles, title-merge overlap) | ✅ Done | With regression tests. 29 tests pass. |
| Memory Map view | ✅ Done | Nodes, edges, hubs, search, live writes, delete, live feed. |
| Time Machine view | ✅ Done | History chart, slider, presets, counts, change list, known memories. |
| Live writes | ✅ Done | Sidebar buttons + custom text; halo + live feed. |
| Documentation | ✅ Done | README updated; `docs/` expanded (see section 9). |
| README | ✅ Done | New views, live demo flow, restore procedure documented. |

## 4. What changed in this phase (the UI work)

- `app.py` rewritten: three-way view switcher on `st.segmented_control` (so `st.chat_input`
  only renders in Chat). Chat behaviour preserved. Deep links via `?view=...`.
- New file `demo_views.py`: Memory Map + Time Machine implementation, live-write controls,
  delete control, `_write_memory`, `_node_frame`, `_positions`, `_lifecycle_edges`,
  `_similarity_edges`, `_people_hubs`.
- Map improvements after visual review: state legend restored, theme-safe label colours,
  amber halo + blue match rings, sidebar write controls (so the map stays in view),
  removed auto-refresh to keep the projector view still.
- `README.md`: demo archive now described as 3 projects / 50 memories; new "5.3 visual
  demo" section; repository layout and test count updated.

## 5. How to run (quick)

```bash
cd /Users/manishwagle/Desktop/ChatBot/episodic-memory-demo
./start.sh --demo            # demo mode: uses demo.db, never memory.db
# or
./start.sh                   # real mode: uses memory.db
./stop.sh                    # stop everything
```

Open <http://localhost:8501>. First model load can take 20–60 seconds.

See `docs/OPERATIONS.md` for flags, environment variables, and troubleshooting.

## 6. How to test

```bash
source .venv/bin/activate
pytest -q                    # 29 passed, < 1 second, no Ollama needed
python -m py_compile app.py demo_views.py memory_engine.py
python scripts/build_demo_db.py --check   # inspect demo.db, no model calls
```

Full benchmark (real models, several minutes): `python evaluate.py`.

## 7. How to continue (next steps)

Priority order, from the audit and demo prep:

1. **Fix the date hallucination** (high value, small): the answer prompt has no current
   date, so the model invents one. Inject `utc_now()` into the answer system prompt.
2. **Fill `event_time` during extraction** (medium): dates like "since 18 November 2026"
   land only in the summary. Make the extractor populate `event_time`.
3. **Exclusivity for "best friend"** (medium): a new "X is my best friend" should
   supersede an older "Y is my best friend". Needs a rule, not just similarity.
4. **Routing stability** (medium): identical questions sometimes search and sometimes
   do not. Consider always searching when the archive is non-empty, or a retry.
5. **Write-before-answer ordering** (low/UX): writing after the reply causes "no info
   about X" on the same turn. Could surface the just-written memory in the reply.
6. **Force-layout map** (low): spread clusters more evenly for projector use.
7. **Reset demo button** (low): restore `demo.db` from a seed copy on stage.
8. **Update tests** for any of the above, keeping the 29 passing.

See `docs/IMPROVEMENTS.md` for the full prioritised list with effort estimates.

## 8. Known issues (from the audit)

- Deletion is incomplete: `turn_traces.details` keeps a copy of evidence text.
- Contradictions are not resolved in code (prompt rule only). Benchmark case `c4` fails.
- Retrieval quality is modest (top-1 69%) and measured with the floor disabled.
- Routing only sees 30 newest episodes.
- Extraction is prompt-dependent; grounding is lexical, not a truth check.
- Single user, no auth. Do not expose the server publicly.
- `event_time` often empty (see improvement 2 above).

## 9. Documentation map

| File | Purpose |
|---|---|
| `docs/OVERVIEW.md` | Top-to-bottom simple explanation. Read first. |
| `docs/WORKING_MECHANISM.md` | Complete mechanism, step by step. |
| `docs/HANDOFF.md` | This file. Master handoff. |
| `docs/DEMO_AND_VIEWS.md` | Memory Map, Time Machine, live writes, demo flow. |
| `docs/DEVELOPMENT_HISTORY.md` | What was done and when. |
| `docs/IMPROVEMENTS.md` | Future work, prioritised. |
| `docs/OPERATIONS.md` | Run, demo, restore, troubleshoot. |
| `docs/ARCHITECTURE.md` | Concise design and data flow. |
| `docs/PROJECT_GUIDE.md` | Beginner handbook (19 chapters). |
| `docs/BENCHMARK_GUIDE.md` | Every metric explained. |
| `docs/RESULTS.md` | Recorded benchmark numbers. |
| `docs/AUDIT.md` | Technical audit and defects. |

## 10. File map (quick)

```
episodic-memory-demo/
├── app.py                  Screen + view switcher + chat + sidebar
├── demo_views.py           Memory Map + Time Machine + live writes
├── memory_engine.py        All logic: prompts, schema, SQLite, extraction, retrieval
├── demo.db                 Committed 50-memory demo archive (demo mode only)
├── memory.db               Real notebook (never opened in demo mode)
├── scripts/
│   ├── story.py            Atlas / Beacon / Cinder transcripts
│   └── build_demo_db.py    Rebuilds demo.db through the real extractor
├── start.sh / stop.sh      One-command start (--demo) / stop
├── test_memory.py          29 fast tests (fake model, no Ollama)
├── test_evaluate.py        Scoring tests
├── evaluate.py             51-case benchmark
├── benchmark/              Six gold-annotated case files
├── docs/                   All documentation
└── README.md               User-facing guide
```

## 11. Important notes for interns

- **Never delete or overwrite `memory.db`** unless you are starting fresh on purpose.
- **Demo mode never opens `memory.db`.** Use `./start.sh --demo` for demos and testing.
- **Do not commit `memory.db`.** It is git-ignored. `demo.db` is committed and must stay
  pristine; restore with `git checkout -- demo.db` after rehearsing.
- **All inference is local.** Do not expose Streamlit publicly (single user, no auth).
- **The first model load is slow** (20–60 s). Be patient; do not double-click.
- **Tests do not need Ollama.** They use a fake model. Run them often.
- **Read `docs/AUDIT.md`** before changing anything in `memory_engine.py`. It lists every
  defect and where it lives.

## 12. Contacts / ownership

- Repository owner: `manishw7` (GitHub).
- This handoff was prepared on 26 November 2026.
- For questions about the engine: start with `memory_engine.py` and `docs/AUDIT.md`.
- For questions about the UI: start with `app.py` and `demo_views.py`.