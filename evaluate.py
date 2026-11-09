"""Benchmark the episodic-memory engine with gold cases.

This measures the memory contract, not "did the chatbot sound smart":
formation quality, ranking among hard negatives, lifecycle behaviour,
grounded answering, causal dependence on memory, and robustness.

Usage:
    python evaluate.py
    python evaluate.py --sections formation,retrieval
    python evaluate.py --out eval_results
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from memory_engine import Episode, MemoryEngine, Settings, embedding_text, utc_now

ROOT = Path(__file__).resolve().parent
BENCHMARK = ROOT / "benchmark"
DEFAULT_OUT = ROOT / "eval_results"

REFUSAL_PHRASES = (
    "do not have", "don't have", "no records", "not establish", "no relevant memories",
    "cannot check", "unable to", "not available", "not specified", "not provided",
    "unknown", "not enough information",
)

TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "for", "is", "are", "was", "were",
    "in", "on", "at", "by", "with", "that", "this", "it", "as", "be", "has", "have",
    "had", "will", "would", "can", "could", "should", "from", "not", "no", "but",
    "we", "i", "you", "they", "he", "she", "user", "users",
}


# --------------------------------------------------------------------------- helpers

def load_cases(name: str) -> list[dict[str, Any]]:
    path = BENCHMARK / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def fresh_engine(tmp: str, settings: Settings) -> tuple[MemoryEngine, Path]:
    db_path = Path(tmp) / "eval.db"
    return MemoryEngine(replace(settings, database_path=str(db_path))), db_path


def add_messages(engine: MemoryEngine, conversation_id: str,
                 messages: list[dict[str, str]]) -> list[str]:
    ids = []
    for index, message in enumerate(messages, start=1):
        message_id = f"{conversation_id}-m{index}"
        engine.add_message(conversation_id, message["role"], message["content"],
                           message.get("created_at"), message_id)
        ids.append(message_id)
    return ids


def text_of(episode: dict[str, Any]) -> str:
    parts = [
        episode.get("title", ""),
        episode.get("summary", ""),
        " ".join(episode.get("facts", [])),
        " ".join(episode.get("participants", [])),
        episode.get("outcome") or "",
    ]
    return " ".join(parts).lower()


def keyword_match(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return all(keyword.lower() in lowered for keyword in keywords)


def spec_matches(spec: dict[str, Any], episode: dict[str, Any]) -> bool:
    return keyword_match(text_of(episode), spec.get("keywords", []))


def token_set(text: str) -> set[str]:
    return {token for token in TOKEN_RE.findall(text.lower()) if token not in STOPWORDS}


def is_duplicate(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if a.get("event_type") != b.get("event_type"):
        return False
    left, right = token_set(text_of(a)), token_set(text_of(b))
    if not left or not right:
        return False
    return len(left & right) / len(left | right) >= 0.75


def duplicate_pairs(episodes: list[dict[str, Any]]) -> int:
    total = 0
    for i in range(len(episodes)):
        for j in range(i + 1, len(episodes)):
            if is_duplicate(episodes[i], episodes[j]):
                total += 1
    return total


def auroc(scores: list[float], labels: list[int]) -> float | None:
    """Probability a relevant item scores above an irrelevant one (tie-aware)."""
    positives = sum(labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return None
    order = sorted(range(len(scores)), key=lambda index: scores[index])
    ranks = [0.0] * len(scores)
    index = 0
    while index < len(order):
        end = index
        while end + 1 < len(order) and scores[order[end + 1]] == scores[order[index]]:
            end += 1
        average_rank = (index + end) / 2.0 + 1.0
        for position in range(index, end + 1):
            ranks[order[position]] = average_rank
        index = end + 1
    positive_ranks = [ranks[i] for i, label in enumerate(labels) if label == 1]
    return (sum(positive_ranks) - positives * (positives + 1) / 2.0) / (positives * negatives)


def calibration_table(pairs: list[tuple[float, int]]) -> list[dict[str, Any]]:
    bins = [(-1.0, 0.0, "< 0.00"), (0.0, 0.2, "0.00-0.20"), (0.2, 0.4, "0.20-0.40"),
            (0.4, 0.6, "0.40-0.60"), (0.6, 0.8, "0.60-0.80"), (0.8, 1.01, "0.80-1.00")]
    rows = []
    for low, high, label in bins:
        selected = [label_value for score, label_value in pairs if low <= score < high]
        relevant = sum(selected)
        rows.append({
            "band": label,
            "n": len(selected),
            "relevant": relevant,
            "precision": (relevant / len(selected)) if selected else None,
        })
    return rows


def answer_abstains(answer: str) -> bool:
    lowered = answer.lower()
    return any(phrase in lowered for phrase in REFUSAL_PHRASES)


def format_matches(answer: str, expected: str) -> bool:
    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    if expected == "bullets":
        return sum(1 for line in lines if line.startswith(("-", "*", "•"))) >= 2
    if expected == "table":
        return sum(1 for line in lines if line.count("|") >= 2) >= 2
    return False


def seed_episode(engine: MemoryEngine, spec: dict[str, Any], episode_id: str) -> str:
    # Evaluation seeds gold episodes directly so retrieval is measured independently of extraction.
    episode = Episode(
        episode_id=episode_id,
        created_at=utc_now(),
        source_conversation_id="benchmark",
        title=spec["title"],
        event_type=spec["event_type"],
        event_time=spec.get("event_time"),
        summary=spec["summary"],
        participants=spec.get("participants", []),
        facts=spec["facts"],
        outcome=spec.get("outcome"),
        source_message_ids=spec.get("source_message_ids", ["benchmark-msg"]),
    )
    vector = engine.llm.embed([embedding_text(episode)])[0]
    engine._insert_episode(episode, vector)
    return episode.episode_id


def run_answer(engine: MemoryEngine, question: str) -> tuple[str, dict[str, Any], int]:
    started = time.perf_counter()
    turn = engine.handle_turn(question, [], retrieval_enabled=True)
    return turn["answer"], turn["details"], int((time.perf_counter() - started) * 1000)


# --------------------------------------------------------------------------- formation

def run_formation(settings: Settings) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    cases = load_cases("formation")
    for case in cases:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = fresh_engine(tmp, settings)
            conversation = f"bench-{case['id']}"
            message_ids = add_messages(engine, conversation, case["messages"])
            episodes, errors = engine.form_memories(conversation)

            used: set[int] = set()
            matched_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
            for gold in case.get("gold_memories", []):
                for index, episode in enumerate(episodes):
                    if index not in used and spec_matches(gold, episode):
                        used.add(index)
                        matched_pairs.append((gold, episode))
                        break

            matched = len(matched_pairs)
            extracted = len(episodes)
            gold_count = len(case.get("gold_memories", []))
            duplicates = duplicate_pairs(episodes)
            noise_violations = [
                phrase for phrase in case.get("must_not_store", [])
                if any(phrase.lower() in episode["title"].lower() for episode in episodes)
            ]
            source_ids = {mid for episode in episodes for mid in episode["source_message_ids"]}
            provenance_ok = source_ids <= set(message_ids)
            metadata_correct = sum(
                1 for gold, episode in matched_pairs
                if gold.get("event_type") == episode["event_type"]
            )
            rows.append({
                "id": case["id"],
                "extracted": extracted,
                "gold": gold_count,
                "matched": matched,
                "precision": (matched / extracted) if extracted else (1.0 if gold_count == 0 else 0.0),
                "recall": (matched / gold_count) if gold_count else None,
                "duplicates": duplicates,
                "noise_violations": noise_violations,
                "provenance_ok": provenance_ok,
                "metadata_correct": metadata_correct,
                "titles": [episode["title"] for episode in episodes],
                "errors": errors,
            })

    case_count = len(rows)
    extracted_total = sum(row["extracted"] for row in rows)
    gold_total = sum(row["gold"] for row in rows)
    matched_total = sum(row["matched"] for row in rows)
    noise_total = sum(len(case.get("must_not_store", [])) for case in cases)
    noise_bad = sum(len(row["noise_violations"]) for row in rows)
    with_gold = sum(1 for row in rows if row["gold"] > 0)
    without_gold = case_count - with_gold
    false_memory_cases = sum(1 for row in rows if row["gold"] == 0 and row["extracted"] > 0)
    exact_count_cases = sum(1 for row in rows if row["extracted"] == row["gold"])
    metadata_total = sum(row["matched"] for row in rows)
    metadata_ok = sum(row["metadata_correct"] for row in rows)
    return {
        "rows": rows,
        "summary": {
            "cases": case_count,
            "extracted": extracted_total,
            "gold": gold_total,
            "matched": matched_total,
            "precision": (matched_total / extracted_total) if extracted_total else None,
            "recall": (matched_total / gold_total) if gold_total else None,
            "noise_checks": noise_total,
            "noise_violations": noise_bad,
            "noise_rejection": (1 - noise_bad / noise_total) if noise_total else None,
            "metadata_accuracy": (metadata_ok / metadata_total) if metadata_total else None,
            "exact_count_rate": (exact_count_cases / case_count) if case_count else None,
            "duplicate_pairs": sum(row["duplicates"] for row in rows),
            "duplicate_rate": (sum(row["duplicates"] for row in rows) / extracted_total) if extracted_total else 0.0,
            "false_memory_rate": (false_memory_cases / without_gold) if without_gold else None,
            "provenance_ok": all(row["provenance_ok"] for row in rows),
        },
    }


# --------------------------------------------------------------------------- retrieval

def run_retrieval(settings: Settings) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    calibration_pairs: list[tuple[float, int]] = []
    all_scores: list[float] = []
    all_labels: list[int] = []

    for case in load_cases("retrieval"):
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = fresh_engine(tmp, settings)
            specs = case["gold"] + case["hard_negatives"]
            ids = [seed_episode(engine, spec, f"ep_bench_{case['id']}_{i}")
                   for i, spec in enumerate(specs)]
            gold_ids = set(ids[:len(case["gold"])])
            negative_ids = set(ids[len(case["gold"]):])
            result = engine.retrieve(case["query"], top_k=len(specs), min_similarity=-1.0)
            ranked = [(match["episode"]["episode_id"], match["score"], match["episode"]["title"])
                      for match in result.matches]
            top4 = ranked[:4]
            first_gold_rank = next(
                (rank for rank, (episode_id, _, _) in enumerate(ranked, start=1)
                 if episode_id in gold_ids), None
            )
            top1 = bool(ranked and ranked[0][0] in gold_ids)
            mrr = (1.0 / first_gold_rank) if first_gold_rank else 0.0
            recall4 = (sum(1 for episode_id, _, _ in top4 if episode_id in gold_ids)
                       / len(gold_ids)) if gold_ids else 0.0
            precision4 = (sum(1 for episode_id, _, _ in top4 if episode_id in gold_ids)
                          / min(4, len(ranked))) if ranked else 0.0
            if first_gold_rank is None:
                negatives_above = len(negative_ids)
            else:
                negatives_above = sum(
                    1 for episode_id, _, _ in ranked[:first_gold_rank - 1]
                    if episode_id in negative_ids
                )
            hard_negative_rejection = (
                1 - negatives_above / len(negative_ids)
            ) if negative_ids else None
            gold_scores = [score for episode_id, score, _ in ranked if episode_id in gold_ids]
            negative_scores = [score for episode_id, score, _ in ranked if episode_id in negative_ids]
            rank_margin = (max(gold_scores) - max(negative_scores)) if gold_scores and negative_scores else None
            labels = [1 if episode_id in gold_ids else 0 for episode_id, _, _ in ranked]
            all_scores.extend(score for _, score, _ in ranked)
            all_labels.extend(labels)
            calibration_pairs.extend((score, label) for (_, score, _), label in zip(ranked, labels))
            rows.append({
                "id": case["id"],
                "query": case["query"],
                "top1": top1,
                "mrr": mrr,
                "recall4": recall4,
                "precision4": precision4,
                "hard_negative_rejection": hard_negative_rejection,
                "rank_margin": rank_margin,
                "first_gold_rank": first_gold_rank,
                "ranked_titles": [title for _, _, title in ranked],
            })

    def average(key: str) -> float | None:
        values = [row[key] for row in rows if row[key] is not None]
        return (sum(values) / len(values)) if values else None

    return {
        "rows": rows,
        "summary": {
            "cases": len(rows),
            "top1": average("top1"),
            "mrr": average("mrr"),
            "recall4": average("recall4"),
            "precision4": average("precision4"),
            "hard_negative_rejection": average("hard_negative_rejection"),
            "rank_margin": average("rank_margin"),
            "auroc": auroc(all_scores, all_labels),
            "calibration": calibration_table(calibration_pairs),
        },
    }


# --------------------------------------------------------------------------- lifecycle

def run_lifecycle(settings: Settings) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    fact_checks = fact_passes = 0
    outcome_checks = outcome_passes = 0
    type_checks = type_passes = 0
    state_checks = state_passes = 0
    persistence_checks = persistence_passes = 0

    for case in load_cases("lifecycle"):
        with tempfile.TemporaryDirectory() as tmp:
            engine, db_path = fresh_engine(tmp, settings)
            session_rows = []
            for session_index, session in enumerate(case["sessions"], start=1):
                conversation = f"life-{case['id']}-s{session_index}"
                add_messages(engine, conversation, session["messages"])
                engine.form_memories(conversation)
                archive = engine.list_episodes()
                for expect in session.get("expect", []):
                    candidates = [ep for ep in archive
                                  if keyword_match(text_of(ep), expect["keywords"])]
                    fact_ok = bool(candidates)
                    outcome_ok = None
                    if "expected_outcome" in expect:
                        expected = expect["expected_outcome"]
                        if expected is None:
                            outcome_ok = any(ep["outcome"] is None for ep in candidates)
                        else:
                            outcome_ok = any(
                                ep["outcome"] and expected.lower() in ep["outcome"].lower()
                                for ep in candidates
                            )
                    type_ok = None
                    if expect.get("event_type"):
                        type_ok = any(ep["event_type"] == expect["event_type"] for ep in candidates)
                    session_rows.append({
                        "session": session_index,
                        "keywords": expect["keywords"],
                        "fact_ok": fact_ok,
                        "outcome_ok": outcome_ok,
                        "type_ok": type_ok,
                    })
                    fact_checks += 1
                    fact_passes += int(fact_ok)
                    if outcome_ok is not None:
                        outcome_checks += 1
                        outcome_passes += int(outcome_ok)
                    if type_ok is not None:
                        type_checks += 1
                        type_passes += int(type_ok)

            archive = engine.list_episodes(include_inactive=True)
            active = engine.list_episodes()
            state_changes = sum(1 for episode in archive if episode["status"] != "active")
            expected_changes = case.get("expect_state_changes")
            state_ok = None if expected_changes is None else state_changes == expected_changes
            persistence_ok = None
            if case.get("restart_query"):
                reopened = MemoryEngine(replace(settings, database_path=str(db_path)))
                result = reopened.retrieve(case["restart_query"], top_k=4, min_similarity=0.0)
                persistence_ok = any(
                    keyword_match(text_of(match["episode"]), case.get("restart_keywords", []))
                    for match in result.matches
                )
                persistence_checks += 1
                persistence_passes += int(persistence_ok)

            rows.append({
                "id": case["id"],
                "session_checks": session_rows,
                "episodes": len(active),
                "all_episodes": len(archive),
                "state_changes": state_changes,
                "expected_state_changes": expected_changes,
                "state_ok": state_ok,
                "duplicate_pairs": duplicate_pairs(active),
                "persistence_ok": persistence_ok,
            })
            if state_ok is not None:
                state_checks += 1
                state_passes += int(state_ok)

    return {
        "rows": rows,
        "summary": {
            "cases": len(rows),
            "fact_checks": fact_checks,
            "fact_passes": fact_passes,
            "fact_recall": (fact_passes / fact_checks) if fact_checks else None,
            "outcome_checks": outcome_checks,
            "outcome_passes": outcome_passes,
            "outcome_accuracy": (outcome_passes / outcome_checks) if outcome_checks else None,
            "type_checks": type_checks,
            "type_passes": type_passes,
            "type_accuracy": (type_passes / type_checks) if type_checks else None,
            "duplicate_pairs": sum(row["duplicate_pairs"] for row in rows),
            "state_checks": state_checks,
            "state_passes": state_passes,
            "state_accuracy": (state_passes / state_checks) if state_checks else None,
            "persistence_checks": persistence_checks,
            "persistence_passes": persistence_passes,
        },
    }


# --------------------------------------------------------------------------- answering

def run_answering(settings: Settings) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    answerable_total = answerable_passes = 0
    unanswerable_total = unanswerable_passes = 0
    false_abstentions = 0
    format_checks = format_passes = 0
    evidence_checks = evidence_passes = 0
    searched = 0
    latencies: list[int] = []

    for case in load_cases("answering"):
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = fresh_engine(tmp, settings)
            for index, spec in enumerate(case.get("memories", [])):
                seed_episode(engine, spec, f"ep_answer_{case['id']}_{index}")
            answer, details, latency = run_answer(engine, case["question"])
            lowered = answer.lower()
            required_ok = all(keyword.lower() in lowered
                              for keyword in case.get("required_keywords", []))
            forbidden_hit = any(keyword.lower() in lowered
                                for keyword in case.get("forbidden_keywords", []))
            abstained = answer_abstains(answer)
            if case.get("answerable", True):
                passed = required_ok and not forbidden_hit
                answerable_total += 1
                answerable_passes += int(passed)
                # Only a refusal with no answer in it is a false abstention. Scanning the whole
                # answer for refusal vocabulary misfires on a good answer that happens to contain a
                # word like "unknown" or "not establish" in a caveat sentence.
                if abstained and not required_ok:
                    false_abstentions += 1
            else:
                passed = abstained and not forbidden_hit
                unanswerable_total += 1
                unanswerable_passes += int(passed)

            format_ok = None
            if case.get("expected_format"):
                format_ok = format_matches(answer, case["expected_format"])
                format_checks += 1
                format_passes += int(format_ok)

            evidence_ok = None
            expected_evidence = case.get("expected_evidence", [])
            if expected_evidence:
                evidence_ok = any(
                    any(keyword.lower() in result["title"].lower() for keyword in expected_evidence)
                    for result in details.get("results", [])
                )
                evidence_checks += 1
                evidence_passes += int(evidence_ok)

            searched += int(details.get("searched", False))
            latencies.append(latency)
            rows.append({
                "id": case["id"],
                "question": case["question"],
                "answer": answer,
                "passed": passed,
                "required_ok": required_ok,
                "forbidden_hit": forbidden_hit,
                "abstained": abstained,
                "format_ok": format_ok,
                "evidence_ok": evidence_ok,
                "searched": details.get("searched", False),
                "latency_ms": latency,
            })

    return {
        "rows": rows,
        "summary": {
            "cases": len(rows),
            "answerable_accuracy": (answerable_passes / answerable_total) if answerable_total else None,
            "unanswerable_abstention": (unanswerable_passes / unanswerable_total) if unanswerable_total else None,
            "false_abstentions": false_abstentions,
            "format_accuracy": (format_passes / format_checks) if format_checks else None,
            "evidence_accuracy": (evidence_passes / evidence_checks) if evidence_checks else None,
            "searched": searched,
            "avg_latency_ms": (sum(latencies) / len(latencies)) if latencies else None,
        },
    }


# --------------------------------------------------------------------------- causal

def run_causal(settings: Settings) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in load_cases("causal"):
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = fresh_engine(tmp, settings)
            kind = case["kind"]
            passed = False
            detail = ""

            if kind == "memory_off":
                seed_episode(engine, case["memory"], f"ep_causal_{case['id']}")
                on_answer, _, _ = run_answer(engine, case["question"])
                off_turn = engine.handle_turn(case["question"], [], retrieval_enabled=False)
                on_ok = case["required_keyword"].lower() in on_answer.lower()
                off_fails = case["required_keyword"].lower() not in off_turn["answer"].lower()
                passed = on_ok and off_fails
                detail = f"memory_on={on_ok} memory_off_fails={off_fails}"

            elif kind == "counterfactual":
                old_id = seed_episode(engine, case["old_memory"], f"ep_causal_{case['id']}_old")
                run_answer(engine, case["question"])
                engine.delete_episode(old_id)
                seed_episode(engine, case["new_memory"], f"ep_causal_{case['id']}_new")
                answer, _, _ = run_answer(engine, case["question"])
                follows_new = case["new_keyword"].lower() in answer.lower()
                old_absent = case["old_keyword"].lower() not in answer.lower()
                passed = follows_new and old_absent
                detail = f"follows_new={follows_new} old_absent={old_absent}"

            elif kind == "deletion":
                episode_id = seed_episode(engine, case["memory"], f"ep_causal_{case['id']}")
                first_answer, _, _ = run_answer(engine, case["question"])
                engine.delete_episode(episode_id)
                second_answer, _, _ = run_answer(engine, case["question"])
                first_ok = case["required_keyword"].lower() in first_answer.lower()
                second_abstains = answer_abstains(second_answer)
                passed = first_ok and second_abstains
                detail = f"first_ok={first_ok} second_abstains={second_abstains}"

            elif kind == "hard_negative":
                seed_episode(engine, case["gold"], f"ep_causal_{case['id']}_gold")
                seed_episode(engine, case["negative"], f"ep_causal_{case['id']}_neg")
                answer, _, _ = run_answer(engine, case["question"])
                gold_ok = case["gold_keyword"].lower() in answer.lower()
                negative_absent = case["negative_keyword"].lower() not in answer.lower()
                passed = gold_ok and negative_absent
                detail = f"gold_ok={gold_ok} negative_absent={negative_absent}"

            rows.append({"id": case["id"], "kind": kind, "passed": passed, "detail": detail})

    return {
        "rows": rows,
        "summary": {
            "cases": len(rows),
            "passes": sum(1 for row in rows if row["passed"]),
            "pass_rate": (sum(1 for row in rows if row["passed"]) / len(rows)) if rows else None,
        },
    }


# --------------------------------------------------------------------------- stress

DISTRACTOR_TOPICS = [
    "budget review", "office move", "hiring plan", "laptop order", "conference travel",
    "onboarding checklist", "security audit", "design review", "customer call", "release notes",
]


def make_distractors(count: int) -> list[dict[str, Any]]:
    distractors = []
    for index in range(count):
        topic = DISTRACTOR_TOPICS[index % len(DISTRACTOR_TOPICS)]
        distractors.append({
            "title": f"Unrelated note {index}: {topic}",
            "event_type": "event",
            "event_time": "2026-01-01",
            "summary": f"An unrelated note about {topic}.",
            "participants": ["team"],
            "facts": [f"An unrelated note about {topic}."],
            "outcome": None,
        })
    return distractors


def run_stress(settings: Settings) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in load_cases("stress"):
        with tempfile.TemporaryDirectory() as tmp:
            engine, db_path = fresh_engine(tmp, settings)
            kind = case["kind"]
            passed = False
            detail = ""

            if kind == "restart":
                seed_episode(engine, case["memory"], f"ep_stress_{case['id']}")
                reopened = MemoryEngine(replace(settings, database_path=str(db_path)))
                result = reopened.retrieve(case["query"], top_k=4, min_similarity=0.0)
                passed = any(case["required_keyword"].lower() in text_of(match["episode"])
                             for match in result.matches)
                detail = f"matches_after_restart={len(result.matches)}"

            elif kind == "deletion":
                episode_id = seed_episode(engine, case["memory"], f"ep_stress_{case['id']}")
                engine.delete_episode(episode_id)
                result = engine.retrieve(case["query"], top_k=4, min_similarity=0.0)
                passed = not result.matches
                detail = f"matches_after_delete={len(result.matches)}"

            elif kind == "injection":
                seed_episode(engine, case["normal_memory"], f"ep_stress_{case['id']}_normal")
                seed_episode(engine, case["malicious_memory"], f"ep_stress_{case['id']}_bad")
                answer, _, _ = run_answer(engine, case["question"])
                required_ok = case["required_keyword"].lower() in answer.lower()
                forbidden_absent = case["forbidden_keyword"].lower() not in answer.lower()
                passed = required_ok and forbidden_absent
                detail = f"required_ok={required_ok} injection_blocked={forbidden_absent}"

            elif kind == "flood":
                seed_episode(engine, case["gold"], f"ep_stress_{case['id']}_gold")
                for index, spec in enumerate(make_distractors(case["distractor_count"])):
                    seed_episode(engine, spec, f"ep_stress_{case['id']}_d{index}")
                result = engine.retrieve(case["query"], top_k=4, min_similarity=0.0)
                top1 = result.matches[0]["episode"] if result.matches else None
                passed = bool(top1 and case["required_keyword"].lower() in text_of(top1))
                detail = f"top1={top1['title'] if top1 else 'none'}"

            elif kind == "empty":
                answer, _, _ = run_answer(engine, case["question"])
                passed = answer_abstains(answer)
                detail = f"abstained={passed}"

            rows.append({"id": case["id"], "kind": kind, "passed": passed, "detail": detail})

    return {
        "rows": rows,
        "summary": {
            "cases": len(rows),
            "passes": sum(1 for row in rows if row["passed"]),
            "pass_rate": (sum(1 for row in rows if row["passed"]) / len(rows)) if rows else None,
        },
    }


# --------------------------------------------------------------------------- report

def percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def number(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def write_report(results: dict[str, Any], settings: Settings, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Episodic Memory Benchmark",
        "",
        f"- Chat model: `{settings.chat_model}`",
        f"- Embedding model: `{settings.embed_model}`",
        "- Cases are synthetic and gold-annotated. Raw outputs are in `raw.json`.",
        "",
        "The goal is not to compare versions. It is to test the memory contract:",
        "formation selectivity, ranking among hard negatives, lifecycle behaviour,",
        "grounded answering, causal dependence on memory, and robustness.",
        "",
    ]

    if "formation" in results:
        s = results["formation"]["summary"]
        lines += [
            "## Formation and selectivity",
            "",
            "| Metric | Result |",
            "|---|---|",
            f"| Cases | {s['cases']} |",
            f"| Gold memories | {s['gold']} |",
            f"| Extracted memories | {s['extracted']} |",
            f"| Matched | {s['matched']} |",
            f"| Precision | {percent(s['precision'])} |",
            f"| Recall | {percent(s['recall'])} |",
            f"| Noise rejection | {percent(s['noise_rejection'])} |",
            f"| Metadata accuracy | {percent(s['metadata_accuracy'])} |",
            f"| Exact-count cases | {percent(s['exact_count_rate'])} |",
            f"| Duplicate rate | {number(s['duplicate_rate'])} |",
            f"| False-memory rate | {percent(s['false_memory_rate'])} |",
            f"| Provenance valid | {s['provenance_ok']} |",
            "",
        ]
        notes = [
            row for row in results["formation"]["rows"]
            if row["matched"] < row["gold"] or row["noise_violations"] or row["duplicates"]
            or (row["matched"] and row["metadata_correct"] < row["matched"])
        ]
        if notes:
            lines += ["### Formation cases needing attention", ""]
            for row in notes:
                lines.append(
                    f"- `{row['id']}`: matched {row['matched']}/{row['gold']}, "
                    f"extracted {row['extracted']}, noise {row['noise_violations'] or 'none'}, "
                    f"duplicates {row['duplicates']}. "
                    f"Extracted: {', '.join(row['titles']) or 'none'}."
                    + (f" Errors: {'; '.join(row['errors'])}." if row["errors"] else "")
                )
            lines.append("")

    if "retrieval" in results:
        s = results["retrieval"]["summary"]
        lines += [
            "## Retrieval and ranking",
            "",
            "| Metric | Result |",
            "|---|---|",
            f"| Cases | {s['cases']} |",
            f"| Top-1 accuracy | {percent(s['top1'])} |",
            f"| MRR@4 | {number(s['mrr'])} |",
            f"| Recall@4 | {percent(s['recall4'])} |",
            f"| Precision@4 | {percent(s['precision4'])} |",
            f"| Hard-negative rejection | {percent(s['hard_negative_rejection'])} |",
            f"| Mean rank margin | {number(s['rank_margin'])} |",
            f"| AUROC | {number(s['auroc'])} |",
            "",
            "### Calibration",
            "",
            "| Similarity band | Memories | Relevant | Precision |",
            "|---|---:|---:|---:|",
        ]
        for row in s["calibration"]:
            lines.append(
                f"| {row['band']} | {row['n']} | {row['relevant']} | {percent(row['precision'])} |"
            )
        lines.append("")
        misses = [row for row in results["retrieval"]["rows"] if not row["top1"]]
        if misses:
            lines += ["### Top-1 misses", ""]
            for row in misses:
                lines.append(
                    f"- `{row['id']}`: {row['query']} — ranked: "
                    f"{', '.join(row['ranked_titles'][:4])}."
                )
            lines.append("")

    if "lifecycle" in results:
        s = results["lifecycle"]["summary"]
        lines += [
            "## Lifecycle and organization",
            "",
            "| Metric | Result |",
            "|---|---|",
            f"| Cases | {s['cases']} |",
            f"| Fact recall at checkpoints | {percent(s['fact_recall'])} |",
            f"| Outcome accuracy | {percent(s['outcome_accuracy'])} |",
            f"| Type accuracy | {percent(s['type_accuracy'])} |",
            f"| Duplicate pairs | {s['duplicate_pairs']} |",
            f"| Lifecycle state changes | {s['state_passes']}/{s['state_checks']} |",
            f"| Persistence | {s['persistence_passes']}/{s['persistence_checks']} |",
            "",
        ]
        if s["state_accuracy"] is not None and s["state_accuracy"] < 1:
            failures = [row["id"] for row in results["lifecycle"]["rows"]
                        if row["state_ok"] is False]
            lines.append("Lifecycle state failures: " + ", ".join(f"`{case}`" for case in failures) + ".")
            lines.append("")
        duplicate_cases = [row["id"] for row in results["lifecycle"]["rows"] if row["duplicate_pairs"]]
        if duplicate_cases:
            lines.append(f"Cases with cross-session duplicates: {', '.join(f'`{case}`' for case in duplicate_cases)}.")
            lines.append("")
        checkpoint_failures = []
        for row in results["lifecycle"]["rows"]:
            for check in row["session_checks"]:
                if check["outcome_ok"] is False or check["type_ok"] is False:
                    checkpoint_failures.append(
                        f"`{row['id']}` session {check['session']} "
                        f"(outcome={check['outcome_ok']}, type={check['type_ok']})"
                    )
        if checkpoint_failures:
            lines.append("Lifecycle checkpoint failures: " + "; ".join(checkpoint_failures) + ".")
            lines.append("")

    if "answering" in results:
        s = results["answering"]["summary"]
        lines += [
            "## Grounded answering",
            "",
            "| Metric | Result |",
            "|---|---|",
            f"| Cases | {s['cases']} |",
            f"| Answerable accuracy | {percent(s['answerable_accuracy'])} |",
            f"| Unanswerable abstention | {percent(s['unanswerable_abstention'])} |",
            f"| False abstentions | {s['false_abstentions']} |",
            f"| Format application | {percent(s['format_accuracy'])} |",
            f"| Expected evidence retrieved | {percent(s['evidence_accuracy'])} |",
            f"| Turns that searched | {s['searched']} |",
            f"| Average latency | {s['avg_latency_ms']} ms |",
            "",
        ]
        failures = [row for row in results["answering"]["rows"] if not row["passed"]]
        if failures:
            lines += ["### Answering failures", ""]
            for row in failures:
                lines.append(f"- `{row['id']}`: {row['question']} — answer: {row['answer'][:300]}")
            lines.append("")

    if "causal" in results:
        s = results["causal"]["summary"]
        lines += [
            "## Causal controls",
            "",
            "| Metric | Result |",
            "|---|---|",
            f"| Cases | {s['cases']} |",
            f"| Passed | {s['passes']} |",
            f"| Pass rate | {percent(s['pass_rate'])} |",
            "",
            "Details:",
            "",
        ]
        for row in results["causal"]["rows"]:
            lines.append(f"- `{row['id']}`: {'PASS' if row['passed'] else 'FAIL'} — {row['detail']}")
        lines.append("")

    if "stress" in results:
        s = results["stress"]["summary"]
        lines += [
            "## Robustness",
            "",
            "| Metric | Result |",
            "|---|---|",
            f"| Cases | {s['cases']} |",
            f"| Passed | {s['passes']} |",
            f"| Pass rate | {percent(s['pass_rate'])} |",
            "",
        ]
        for row in results["stress"]["rows"]:
            lines.append(f"- `{row['id']}`: {'PASS' if row['passed'] else 'FAIL'} — {row['detail']}")
        lines.append("")

    lines += [
        "## How to read this",
        "",
        "- Formation precision/recall is at the memory level, using the gold keywords in each case.",
        "- Noise rejection checks that statements marked `must_not_store` did not become memories.",
        "- Hard-negative rejection checks how often a deliberately confusing memory outranks the gold.",
        "- Rank margin is gold score minus the best hard-negative score; larger is better.",
        "- AUROC is the probability a relevant memory scores above an irrelevant one.",
        "- Causal controls require the answer to change when memory is turned off, changed, or deleted.",
        "- Small n means these are engineering measurements, not statistical proof.",
        "",
    ]

    report_path = out_dir / "eval_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    (out_dir / "raw.json").write_text(
        json.dumps({"settings": settings.__dict__, "results": results}, indent=2, default=str),
        encoding="utf-8",
    )
    return report_path


# --------------------------------------------------------------------------- main

def main() -> None:
    parser = argparse.ArgumentParser(description="Run the episodic-memory benchmark.")
    parser.add_argument("--sections", default="formation,retrieval,lifecycle,answering,causal,stress")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--chat-model")
    parser.add_argument("--embed-model")
    args = parser.parse_args()

    settings = Settings.from_env()
    if args.chat_model:
        settings = replace(settings, chat_model=args.chat_model)
    if args.embed_model:
        settings = replace(settings, embed_model=args.embed_model)

    sections = [section.strip() for section in args.sections.split(",") if section.strip()]
    runners = {
        "formation": run_formation,
        "retrieval": run_retrieval,
        "lifecycle": run_lifecycle,
        "answering": run_answering,
        "causal": run_causal,
        "stress": run_stress,
    }

    results: dict[str, Any] = {}
    print(f"Chat model: {settings.chat_model} | Embeddings: {settings.embed_model}")
    for section in sections:
        if section not in runners:
            raise SystemExit(f"Unknown section: {section}")
        print(f"Running {section}...", flush=True)
        results[section] = runners[section](settings)

    report_path = write_report(results, settings, Path(args.out))
    print(f"\nReport written to {report_path}")

    for section, data in results.items():
        summary = data["summary"]
        print(f"\n{section.upper()}")
        for key, value in summary.items():
            if key == "calibration":
                continue
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
