# Episodic Memory Benchmark

- Chat model: `qwen3.5:9b`
- Embedding model: `embeddinggemma`
- Cases are synthetic and gold-annotated. Raw outputs are in `raw.json`.

The goal is not to compare versions. It is to test the memory contract:
formation selectivity, ranking among hard negatives, lifecycle behaviour,
grounded answering, causal dependence on memory, and robustness.

## Formation and selectivity

| Metric | Result |
|---|---|
| Cases | 13 |
| Gold memories | 17 |
| Extracted memories | 17 |
| Matched | 17 |
| Precision | 100% |
| Recall | 100% |
| Noise rejection | 100% |
| Metadata accuracy | 100% |
| Exact-count cases | 100% |
| Duplicate rate | 0.000 |
| False-memory rate | 0% |
| Provenance valid | True |

## Retrieval and ranking

| Metric | Result |
|---|---|
| Cases | 13 |
| Top-1 accuracy | 69% |
| MRR@4 | 0.846 |
| Recall@4 | 100% |
| Precision@4 | 34% |
| Hard-negative rejection | 85% |
| Mean rank margin | 0.085 |
| AUROC | 0.759 |

### Calibration

| Similarity band | Memories | Relevant | Precision |
|---|---:|---:|---:|
| < 0.00 | 0 | 0 | n/a |
| 0.00-0.20 | 0 | 0 | n/a |
| 0.20-0.40 | 11 | 1 | 9% |
| 0.40-0.60 | 21 | 7 | 33% |
| 0.60-0.80 | 8 | 5 | 62% |
| 0.80-1.00 | 1 | 1 | 100% |

### Top-1 misses

- `r6_near_duplicate`: What did Asha finish? — ranked: Asha completed onboarding, Asha completed deletion tests, Asha started deletion tests.
- `r8_project_scope`: What is the current project scope? — ranked: Project scope: multi-user cloud service, Project scope: local single-user prototype, Project update: demo scheduled.
- `r10_negation`: What did we decide about Postgres? — ranked: Decision: Postgres chosen for the prototype, Decision: SQLite chosen, Postgres rejected, Task: evaluate Postgres for storage.
- `r11_multi_hop`: What should Ravi fix before rerunning the retrieval experiment? — ranked: Ravi's retrieval experiment completed, Ravi's retrieval experiment blocked by chat-model embeddings, Decision: use embeddinggemma for embeddings, Decision: use chat model for embeddings.

## Lifecycle and organization

| Metric | Result |
|---|---|
| Cases | 6 |
| Fact recall at checkpoints | 100% |
| Outcome accuracy | 100% |
| Type accuracy | 90% |
| Duplicate pairs | 0 |
| Lifecycle state changes | 6/6 |
| Persistence | 1/1 |

Lifecycle checkpoint failures: `l5_date_change` session 2 (outcome=None, type=False).

## Grounded answering

| Metric | Result |
|---|---|
| Cases | 10 |
| Answerable accuracy | 100% |
| Unanswerable abstention | 100% |
| False abstentions | 0 |
| Format application | 100% |
| Expected evidence retrieved | 100% |
| Turns that searched | 9 |
| Average latency | 6143.4 ms |

## Causal controls

| Metric | Result |
|---|---|
| Cases | 4 |
| Passed | 3 |
| Pass rate | 75% |

Details:

- `c1_memory_off_control`: PASS — memory_on=True memory_off_fails=True
- `c2_counterfactual`: PASS — follows_new=True old_absent=True
- `c3_evidence_deletion`: PASS — first_ok=True second_abstains=True
- `c4_hard_negative_injection`: FAIL — gold_ok=True negative_absent=False

## Robustness

| Metric | Result |
|---|---|
| Cases | 5 |
| Passed | 5 |
| Pass rate | 100% |

- `s1_restart_persistence`: PASS — matches_after_restart=1
- `s2_deletion`: PASS — matches_after_delete=0
- `s3_prompt_injection`: PASS — required_ok=True injection_blocked=True
- `s4_distractor_flood`: PASS — top1=Project Atlas deadline
- `s5_empty_archive`: PASS — abstained=True

## How to read this

- Formation precision/recall is at the memory level, using the gold keywords in each case.
- Noise rejection checks that statements marked `must_not_store` did not become memories.
- Hard-negative rejection checks how often a deliberately confusing memory outranks the gold.
- Rank margin is gold score minus the best hard-negative score; larger is better.
- AUROC is the probability a relevant memory scores above an irrelevant one.
- Causal controls require the answer to change when memory is turned off, changed, or deleted.
- Small n means these are engineering measurements, not statistical proof.
