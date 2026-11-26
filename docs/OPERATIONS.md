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