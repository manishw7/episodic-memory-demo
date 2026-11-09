# Benchmark guide

This benchmark tests the **memory contract**, not whether the chatbot sounds intelligent.

It answers five questions:

1. Did it store the right memories, and only those?
2. Did it organise them correctly over time?
3. Did it retrieve the best memory among deliberately confusing alternatives?
4. Did the answer actually depend on memory, rather than on the model's general knowledge?
5. Did it stay honest and robust under stress?

The report is written to `eval_results/eval_report.md`. Every raw output is in
`eval_results/raw.json`, so any score can be traced back to a concrete case.

---

## 1. The five test sets

| File | Question | What it contains |
|---|---|---|
| `benchmark/formation.json` | Did it store the right things and reject noise? | Conversations mixing decisions, tasks, outcomes, preferences, small talk, hypotheticals, assistant suggestions, negations, and repeated facts |
| `benchmark/retrieval.json` | Did it pick the best memory among many? | Each query has one or more gold memories plus hard negatives: same person, same topic, old vs new, open vs completed, negation, distractor |
| `benchmark/lifecycle.json` | Does memory behave correctly over time? | Multi-session cases: assign → complete, cancel, change a preference, duplicate a fact, change a date, restart |
| `benchmark/answering.json` | Did it use memory faithfully? | Answerable and unanswerable questions, preference application, required evidence, forbidden claims |
| `benchmark/causal.json` | Is the answer really caused by memory? | Memory-off control, counterfactual change, evidence deletion, hard-negative injection |
| `benchmark/stress.json` | Does it survive extreme cases? | Restart, deletion, prompt injection, 40 distractors, empty archive |

The formation set uses gold **keywords** for matching, and a `must_not_store` list for statements
that should never become a separate memory.

`f13_profile_bundle_split` exists because of a real failure. One message gave a profile with three
unrelated topics (education, hardware, an allergy). The extractor produced a single 18-fact
"background summary" memory, so the laptop detail was buried inside a giant episode and a laptop
question later failed to retrieve it. The case requires three separate memories and forbids any
title containing "background summary" or "profile summary". `r13_buried_attribute` is its retrieval
counterpart: the hardware memory competes with the other profile topics and with a memory about
asking someone else for laptop details, which mentions laptops without describing the user's device.

The retrieval set seeds episodes directly. That isolates retrieval quality from extraction quality.
If extraction is wrong, the retrieval score is still meaningful because the retrieval test uses gold
memories.

Be honest about what that buys you: **seeded retrieval cases do not prove the system works end to
end**, because the model did not write those memories. They measure ranking only. A good retrieval
number plus bad extraction can still produce a memory assistant that never finds anything. The
formation set is the un-seeded half, since every memory in it is produced by the real extraction
pipeline. When someone asks "does it actually work", run a fresh database end to end — real
conversation in, LLM extraction, then the question — rather than quoting the retrieval score.

---

## 2. Metrics in plain English

### Formation

- **Precision** — of everything the model stored, how much matched a gold memory?
  Low precision means noise or hallucinated memories.
- **Recall** — of the gold memories, how many were stored?
  Low recall means it missed important information.
- **Noise rejection** — of the statements marked `must_not_store`, how many did **not** become a
  separate memory? This checks episode titles, not summaries, so a correct episode may still mention
  a rejected option in its context.
- **Metadata accuracy** — for matched memories, was the event type correct?
- **Exact-count rate** — did the number of extracted episodes equal the number of gold events?
  This is a simple atomicity check: one episode per event.
- **Duplicate rate** — duplicate pairs divided by extracted memories.
- **False-memory rate** — conversations with nothing memorable that still produced a memory.
- **Provenance valid** — every stored source message ID exists in the transcript. This must be 100%.

### Retrieval

- **Top-1 accuracy** — the single best memory is the gold memory.
- **MRR@4** — how high the first correct memory appears. 1.0 means it is always first.
- **Recall@4** — was the gold memory in the top four? This matters because the answer sees four.
- **Precision@4** — how much of the top four is relevant. Low precision means noise in the prompt.
- **Hard-negative rejection** — how often a deliberately confusing memory ranks below the gold.
- **Rank margin** — gold score minus the best hard-negative score. Positive means the gold won;
  larger means a clearer win.
- **AUROC** — probability that a relevant memory scores above an irrelevant one.
  0.5 is random, 1.0 is perfect.
- **Calibration** — for each similarity band, what fraction is actually relevant.
  This is used to choose the retrieval threshold from data instead of guessing.

### Lifecycle

- **Fact recall at checkpoints** — the expected fact exists after each session.
- **Outcome accuracy** — tasks without completion have `outcome = null`; completed work has an
  outcome.
- **Type accuracy** — the episode type matches the gold type.
- **Duplicate pairs** — the same fact stored more than once across sessions.
- **Lifecycle state changes** — after a multi-session case, did the expected number of older
  memories become `done`, `superseded`, or `cancelled`? This is the check that memory is living
  rather than append-only.

### Answering

- **Answerable accuracy** — all required facts are present and no forbidden claims appear.
- **Unanswerable abstention** — the model refuses when the archive does not establish an answer.
- **False abstention** — the model refuses a question it could answer. The detector looks for refusal
  vocabulary ("no records", "not establish", "unknown") and then requires that the answer also
  contains none of the case's required keywords. A good answer that happens to use the word
  "unknown" in a caveat sentence is therefore not counted as a refusal.
- **Format application** — a stored bullet/table preference is actually applied in the answer.
- **Evidence accuracy** — the expected episode was retrieved.
- **Latency** — wall-clock time per turn.

### Causal controls

These are the tests that separate memory from general language ability:

- **Memory-off control** — the same question with retrieval off. If it still answers correctly, the
  question is contaminated by pretraining or is too easy. This uses the app's normal
  disabled-memory instruction, so the counterfactual and deletion tests are the stronger causal
  checks.
- **Counterfactual** — store a fact, ask, change the fact, ask again. The answer must follow the new
  value.
- **Evidence deletion** — ask, delete the supporting memory, ask again. The answer must become
  "unknown".
- **Hard-negative injection** — add a plausible wrong memory. The answer must still use the gold.

### Robustness

- **Restart** — memories survive a new engine instance.
- **Deletion** — deleted memories cannot be retrieved.
- **Prompt injection** — instructions stored inside a memory do not execute.
- **Distractor flood** — the gold memory still ranks first with 40 irrelevant memories.
- **Empty archive** — the model refuses instead of inventing.

---

## 3. How to run it

```bash
source .venv/bin/activate
python evaluate.py
```

Run only some sections while iterating:

```bash
python evaluate.py --sections formation,retrieval
python evaluate.py --sections causal,stress
```

Outputs:

```text
eval_results/eval_report.md   # readable report
eval_results/raw.json         # every case, answer, ranking, and error
```

The evaluator always uses a temporary SQLite database. It never touches `memory.db`.

---

## 4. How to read the report

Read it in this order:

1. **Formation precision and recall.** If precision is low, the archive is noisy. If recall is low,
   important memories are missing.
2. **Noise rejection and duplicate rate.** These show whether the model is selective.
3. **Retrieval top-1, MRR, and hard-negative rejection.** These show whether it chooses the best
   memory among confusing alternatives.
4. **Calibration.** This tells you which threshold is defensible.
5. **Answerable accuracy and abstention.** These show whether it uses memory honestly.
6. **Causal controls.** These show that the answer depends on memory.
7. **Robustness.** These show the failure boundary.

Always look at `n`. A result from 12 cases is an engineering measurement, not statistical proof.

---

## 5. Adding a case

Each JSON file is a list of cases. To add a formation case:

```json
{
  "id": "f13_my_case",
  "messages": [
    {"role": "user", "content": "...", "created_at": "2026-10-01T09:00:00+00:00"}
  ],
  "gold_memories": [
    {"keywords": ["sqlite", "prototype"], "event_type": "decision"}
  ],
  "must_not_store": ["might use postgres"]
}
```

To add a retrieval case, provide `gold` and `hard_negatives` with full episode fields. To add a
causal or stress case, follow the `kind` field in the existing files.

Keep the gold labels written **before** you look at the system output. Otherwise the benchmark
quietly becomes a test of what the system already does.

---

## 6. What this does and does not prove

It proves:

- the engine stores facts that are supported by source messages,
- it can reject small talk, hypotheticals, and unaccepted suggestions,
- retrieval can rank the gold memory above deliberately confusing alternatives,
- the answer changes when memory is turned off, changed, or deleted,
- the system survives restart, deletion, injection, and a distractor flood,
- its failures are visible and categorised.

It does not prove:

- that it is better than every other memory system,
- that the results generalise to every domain,
- that a 9B local model is as reliable as a larger model,
- that the benchmark itself has no annotation mistakes.

The honest claim is: **the memory contract is specified, measured, and falsifiable.** That is what
makes the design portable to another project.

---

## 7. Manual checks after Block 2

Normal checks:

1. `pytest -q` passes (27 tests).
2. `python evaluate.py --sections formation,lifecycle` finishes; lifecycle now reports
   `Lifecycle state changes` and `Duplicate pairs = 0`.
3. Say "I prefer bullet points" and **do not click anything**. Under the reply, the caption must say
   **Memory writer: stored 1 new episode(s)** and the sidebar must show the memory immediately.
   Then **Start fresh session**; the memory is still there.
4. Save "I prefer bullet points", start a new session, save "I now prefer tables". The sidebar
   shows 🟢 tables and, with **Show superseded / cancelled memories** checked, 🔁 the old bullet
   memory pointing at the new one.
5. Delete a memory, then start a **fresh session** and ask about it. The answer must say the
   records do not establish it. (In the same session the fact is still in the visible chat
   history, which is not memory.)

Extreme checks:

1. Save the same fact in two separate sessions. The second must not create a second memory; the
   writer notes "already remembered".
2. Save a task, then cancel it in a new session. The task becomes 🚫 cancelled and disappears from
   retrieval; asking "what is still open?" must not list it.
3. Save a date, then change the date. Only the new date is retrievable; the old one is 🔁
   superseded.
4. Send several turns in a row, then click **End session**. It must report 0 new memories because
   the writer already processed every turn; nothing is lost either way.
5. `python evaluate.py --sections stress` still passes 5/5 (restart, deletion, injection, 40
   distractors, empty archive).
