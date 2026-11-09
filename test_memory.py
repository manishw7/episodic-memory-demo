"""Fast unit tests with mocked model responses. No Ollama required."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from memory_engine import (
    Episode,
    EpisodeCandidate,
    MemoryEngine,
    Settings,
)


class FakeLLM:
    def __init__(self, chat_responses: list[str] | None = None, embed_fn=None):
        self.chat_responses = list(chat_responses or [])
        self.embed_fn = embed_fn or fake_embed
        self.chat_calls: list[list[dict[str, str]]] = []

    def chat(self, messages, *, json_mode=False, temperature=0.2, schema=None):
        self.chat_calls.append(messages)
        if not self.chat_responses:
            raise AssertionError("FakeLLM has no queued chat response")
        return self.chat_responses.pop(0)

    def embed(self, texts):
        return [self.embed_fn(text) for text in texts]


def fake_embed(text: str) -> list[float]:
    """Tiny deterministic concept vectors; enough to test cosine retrieval plumbing."""
    lowered = text.lower()
    if any(word in lowered for word in ("deletion", "removal", "asha")):
        return [1.0, 0.0, 0.0, 0.05]
    if any(word in lowered for word in ("schema", "mira")):
        return [0.0, 1.0, 0.0, 0.05]
    if any(word in lowered for word in ("retrieval", "ravi", "embeddinggemma", "blocked")):
        return [0.0, 0.0, 1.0, 0.05]
    return [0.0, 0.0, 0.0, 1.0]


def make_engine(tmp_path, llm: FakeLLM) -> MemoryEngine:
    settings = Settings(database_path=str(tmp_path / "memory.db"), min_similarity=0.10, top_k=4)
    return MemoryEngine(settings, llm=llm)


def transcript_payload(ids: list[str]) -> str:
    return json.dumps({
        "episodes": [
            {
                "title": "Asha completed deletion tests",
                "event_type": "outcome",
                "event_time": "2025-10-07",
                "summary": "Asha completed the deletion tests on October 7, 2025.",
                "participants": ["Asha"],
                "facts": ["Asha completed the deletion tests."],
                "outcome": "Deletion tests completed.",
                "source_message_ids": [ids[0]],
            },
            {
                "title": "Mira owns the episode schema",
                "event_type": "task",
                "event_time": "2025-10-18",
                "summary": "Mira was assigned to finish the episode schema.",
                "participants": ["Mira"],
                "facts": ["Mira was assigned to finish the episode schema by October 18, 2025."],
                "outcome": None,
                "source_message_ids": [ids[1]],
            },
            {
                "title": "Ravi's retrieval experiment is blocked",
                "event_type": "project_update",
                "event_time": "2025-10-07",
                "summary": "The retrieval experiment is incomplete.",
                "participants": ["Ravi"],
                "facts": ["The test used the chat model instead of embeddinggemma for embeddings."],
                "outcome": None,
                "source_message_ids": [ids[2]],
            },
        ]
    })


def seed_three(tmp_path):
    llm = FakeLLM([transcript_payload(["m1", "m2", "m3"])])
    engine = make_engine(tmp_path, llm)
    engine.add_message("c1", "user", "Asha completed deletion tests on October 7, 2025.", "2025-10-07T10:00:00+00:00", "m1")
    engine.add_message("c1", "user", "Mira must finish the episode schema by October 18, 2025.", "2025-10-07T10:01:00+00:00", "m2")
    engine.add_message("c1", "user", "Ravi's retrieval experiment is blocked: the test used the chat model for embeddings instead of embeddinggemma.", "2025-10-07T10:02:00+00:00", "m3")
    episodes, errors = engine.form_memories("c1")
    assert not errors
    return engine, llm, episodes


def test_episode_extraction_is_schema_validated():
    valid = {
        "title": "Team chose SQLite",
        "event_type": "decision",
        "event_time": "2025-10-03",
        "summary": "The team selected SQLite for the offline prototype.",
        "participants": ["team"],
        "facts": ["SQLite was selected for a single-user, offline-first prototype."],
        "outcome": None,
        "source_message_ids": ["m1"],
    }
    assert EpisodeCandidate.model_validate(valid).title == "Team chose SQLite"

    with pytest.raises(ValidationError):
        EpisodeCandidate.model_validate({**valid, "event_type": "hearsay"})
    with pytest.raises(ValidationError):
        EpisodeCandidate.model_validate({**valid, "facts": []})
    with pytest.raises(ValidationError):
        EpisodeCandidate.model_validate({**valid, "title": ""})
    with pytest.raises(ValidationError):
        EpisodeCandidate.model_validate({k: v for k, v in valid.items() if k != "source_message_ids"})


def test_source_message_ids_must_come_from_transcript(tmp_path):
    bad = json.dumps({"episodes": [{
        "title": "Invented source",
        "event_type": "event",
        "event_time": None,
        "summary": "This references a message that does not exist.",
        "participants": [],
        "facts": ["A claim."],
        "outcome": None,
        "source_message_ids": ["fake-message-999"],
    }]})
    engine = make_engine(tmp_path, FakeLLM([bad]))
    engine.add_message("c1", "user", "A real message.", "2025-10-07T10:00:00+00:00", "m1")
    episodes, errors = engine.form_memories("c1")

    assert episodes == []
    assert any("not in transcript" in error for error in errors)
    assert engine.list_episodes() == []


def test_stored_episode_survives_app_restart(tmp_path):
    engine, _, episodes = seed_three(tmp_path)
    assert len(episodes) == 3
    assert all(Episode.model_validate(episode) for episode in episodes)

    restarted = make_engine(tmp_path, FakeLLM())
    loaded = restarted.list_episodes()
    assert len(loaded) == 3
    assert {episode["episode_id"] for episode in loaded} == {episode["episode_id"] for episode in episodes}
    assert all(episode["status"] == "active" for episode in loaded)


def test_paraphrased_query_retrieves_relevant_episode(tmp_path):
    engine, _, _ = seed_three(tmp_path)
    result = engine.retrieve("Who handled the removal checks?")

    assert result.matches
    assert result.matches[0]["episode"]["title"] == "Asha completed deletion tests"
    assert result.matches[0]["score"] > 0.9
    assert result.matches[0]["episode"]["source_message_ids"] == ["m1"]
    assert "EPISODE ep_" in result.evidence


def test_deleted_episode_is_not_retrieved(tmp_path):
    engine, _, episodes = seed_three(tmp_path)
    target = episodes[0]["episode_id"]
    assert engine.delete_episode(target) is True

    everything = engine.retrieve("deletion removal Asha", top_k=10, min_similarity=0.0)
    assert all(match["episode"]["episode_id"] != target for match in everything.matches)
    assert engine.delete_episode(target) is False


def test_historical_question_uses_retrieved_evidence(tmp_path):
    engine, llm, episodes = seed_three(tmp_path)
    target_id = next(e["episode_id"] for e in episodes if e["title"].startswith("Ravi"))
    llm.chat_responses = [
        json.dumps({"needs_memory": True, "search_query": "Why is Ravi's retrieval experiment blocked?"}),
        "Ravi's experiment was blocked because the test used the chat model instead of embeddinggemma.",
    ]
    turn = engine.handle_turn("Why did Ravi's experiment stall?", [], retrieval_enabled=True)

    assert turn["details"]["searched"] is True
    assert turn["details"]["results"][0]["episode_id"] == target_id
    answer_prompt = llm.chat_calls[-1]
    evidence_message = next(m["content"] for m in answer_prompt if m["content"].startswith("RETRIEVED"))
    assert target_id in evidence_message
    assert "m3" in evidence_message
    assert "embeddinggemma" in evidence_message


def test_deleted_memory_cannot_be_answered_from_chat_history(tmp_path):
    engine, llm, episodes = seed_three(tmp_path)
    target = next(episode for episode in episodes if episode["title"].startswith("Asha"))
    engine.delete_episode(target["episode_id"])
    llm.chat_responses = [
        json.dumps({"needs_memory": True, "search_query": "When did Asha finish deletion tests?"}),
        "The available records do not establish that.",
    ]
    history = [
        {"role": "user", "content": "Asha completed the deletion tests on October 7, 2025."},
        {"role": "assistant", "content": "Asha completed the deletion tests on October 7, 2025."},
    ]
    turn = engine.handle_turn("When did Asha finish?", history, retrieval_enabled=True)

    assert turn["details"]["results"] == []
    answer_prompt = llm.chat_calls[-1]
    assert not any(message["role"] == "assistant" and "October 7" in message["content"]
                   for message in answer_prompt)
    assert "do not establish" in turn["answer"]


def test_fact_not_supported_by_source_messages_is_rejected(tmp_path):
    hallucinated = episode_item(
        "User health concern regarding bread", "preference",
        "The user believes bread caused previous health problems.",
        ["The user believes bread consumption may have caused previous health problems."],
        source_ids=("m1",),
    )
    engine, _ = lifecycle_engine(tmp_path, [payload(hallucinated)])
    engine.add_message("c1", "user", "I use a MacBook Pro with an M1 Pro chip.",
                       "2026-10-28T09:00:00+00:00", "m1")

    stored, errors = engine.form_memories("c1")

    assert stored == []
    assert any("not supported by its source" in error for error in errors)
    assert engine.list_episodes() == []


def test_decision_prompt_includes_facts_not_just_titles(tmp_path):
    engine, llm, _ = seed_three(tmp_path)
    llm.chat_responses = [
        json.dumps({"needs_memory": True, "search_query": "deletion tests"}),
        "Asha completed the deletion tests on October 7, 2025.",
    ]

    engine.handle_turn("Who completed the deletion tests?", [], retrieval_enabled=True)

    decision_prompt = llm.chat_calls[-2][-1]["content"]
    assert "Asha completed deletion tests" in decision_prompt
    assert "Asha completed the deletion tests." in decision_prompt


def test_assistant_history_is_never_evidence_even_without_a_search(tmp_path):
    engine = make_engine(tmp_path, FakeLLM())
    llm = engine.llm
    llm.chat_responses = [
        json.dumps({"needs_memory": False, "search_query": ""}),
        "The available records do not establish that.",
    ]
    history = [
        {"role": "user", "content": "When is my mentor presentation?"},
        {"role": "assistant", "content": "Your mentor presentation is on November 6, 2026."},
    ]

    turn = engine.handle_turn("When is my mentor presentation?", history, retrieval_enabled=True)

    assert turn["details"]["searched"] is False
    answer_prompt = llm.chat_calls[-1]
    assert not any(message["role"] == "assistant" for message in answer_prompt)
    assert not any("November 6" in message["content"] for message in answer_prompt)


def test_answer_prompt_separates_real_conflicts_from_background(tmp_path):
    """A request or a past gap in knowledge must not be offered as a contradiction."""
    engine = make_engine(tmp_path, FakeLLM())
    engine.llm.chat_responses = [
        json.dumps({"needs_memory": False, "search_query": ""}),
        "You use a MacBook Pro with an M1 Pro chip.",
    ]

    engine.handle_turn("What laptop do I have?", [], retrieval_enabled=True)

    system_prompt = engine.llm.chat_calls[-1][0]["content"]
    assert "different values for the same attribute" in system_prompt
    assert "not a contradiction" in system_prompt


def test_turn_trace_is_persisted(tmp_path):
    engine = make_engine(tmp_path, FakeLLM())
    engine.add_message("c1", "user", "hello", "2026-01-01T00:00:00+00:00", "m1")
    engine.add_message("c1", "assistant", "hi", "2026-01-01T00:00:01+00:00", "m2")

    trace_id = engine.save_trace(
        "c1", "hello", "hi",
        {"searched": False, "search_query": None, "results": []},
        user_message_id="m1", assistant_message_id="m2", latency_ms=42,
    )

    traces = engine.list_traces(conversation_id="c1")
    assert len(traces) == 1
    assert traces[0]["trace_id"] == trace_id
    assert traces[0]["question"] == "hello"
    assert traces[0]["details"]["searched"] is False
    assert traces[0]["latency_ms"] == 42


def lifecycle_embed(text: str) -> list[float]:
    """Small hand-made vectors so related memories land at a realistic similarity."""
    lowered = text.lower()
    if "tables" in lowered:
        return [0.8, 0.6, 0.0, 0.0]      # same topic, new value: replaces the old one
    if "bullet" in lowered:
        return [1.0, 0.0, 0.0, 0.0]
    if "schema" in lowered:
        return [0.0, 0.0, 1.0, 0.0]      # task and its completion
    if "retrieval" in lowered:
        return [0.0, 0.0, 0.0, 1.0]      # task and its cancellation
    return [0.0, 0.0, 0.0, 0.0]


def payload(*episodes) -> str:
    return json.dumps({"episodes": list(episodes)})


def episode_item(title, event_type, summary, facts, participants=("user",),
                 event_time=None, outcome=None, source_ids=("m1",)):
    return {
        "title": title, "event_type": event_type, "event_time": event_time,
        "summary": summary, "participants": list(participants), "facts": list(facts),
        "outcome": outcome, "source_message_ids": list(source_ids),
    }


def lifecycle_engine(tmp_path, responses):
    llm = FakeLLM(responses, embed_fn=lifecycle_embed)
    return make_engine(tmp_path, llm), llm


def test_changed_preference_supersedes_the_old_one(tmp_path):
    engine, llm = lifecycle_engine(tmp_path, [
        payload(episode_item("Preference: bullet points", "preference",
                             "The user prefers concise bullet points.",
                             ["The user prefers concise bullet points."])),
        payload(episode_item("Preference: tables", "preference",
                             "The user now prefers tables for summaries.",
                             ["The user now prefers tables for summaries."], source_ids=("m2",))),
    ])
    engine.add_message("c1", "user", "I prefer concise bullet points.", "2026-10-01T09:00:00+00:00", "m1")
    engine.form_memories("c1")
    engine.add_message("c2", "user", "I now prefer tables.", "2026-10-20T09:00:00+00:00", "m2")
    engine.form_memories("c2")

    active = engine.list_episodes()
    assert [episode["title"] for episode in active] == ["Preference: tables"]
    everything = engine.list_episodes(include_inactive=True)
    assert len(everything) == 2
    superseded = next(episode for episode in everything if episode["status"] == "superseded")
    assert superseded["title"] == "Preference: bullet points"
    assert superseded["superseded_by"] == active[0]["episode_id"]

    result = engine.retrieve("How do I like summaries formatted?", min_similarity=0.0)
    assert result.matches[0]["episode"]["title"] == "Preference: tables"


def test_small_talk_episode_is_rejected_by_python(tmp_path):
    weather = episode_item("User preference regarding weather", "preference",
                           "The user said the weather is nice today.",
                           ["The user likes nice weather."])
    engine, _ = lifecycle_engine(tmp_path, [payload(weather)])
    engine.add_message("c1", "user", "The weather is nice today.", "2026-10-05T10:00:00+00:00", "m1")
    stored, errors = engine.form_memories("c1")

    assert stored == []
    assert any("small talk" in error for error in errors)
    assert engine.list_episodes() == []


def test_repeated_preference_is_not_stored_twice(tmp_path):
    item = episode_item("Preference: bullet points", "preference",
                        "The user prefers concise bullet points.",
                        ["The user prefers concise bullet points."])
    repeat = {**item, "source_message_ids": ["m2"]}
    engine, _ = lifecycle_engine(tmp_path, [payload(item), payload(repeat)])
    engine.add_message("c1", "user", "I prefer concise bullet points.", "2026-10-01T09:00:00+00:00", "m1")
    engine.form_memories("c1")
    engine.add_message("c2", "user", "Remember I prefer concise bullet points.", "2026-10-02T09:00:00+00:00", "m2")
    stored, errors = engine.form_memories("c2")

    assert stored == []
    assert any("already remembered" in error for error in errors)
    assert len(engine.list_episodes()) == 1


def test_completed_task_is_marked_done_not_deleted(tmp_path):
    engine, _ = lifecycle_engine(tmp_path, [
        payload(episode_item("Mira episode schema task", "task",
                             "Mira will finish the episode schema by October 18, 2025.",
                             ["Mira will finish the episode schema by October 18, 2025."],
                             participants=("Mira",))),
        payload(episode_item("Mira completed episode schema", "outcome",
                             "Mira completed the episode schema on October 18, 2025.",
                             ["Mira completed the episode schema."],
                             participants=("Mira",), outcome="Episode schema completed.",
                             source_ids=("m2",))),
    ])
    engine.add_message("c1", "user", "Mira will finish the episode schema by October 18, 2025.",
                       "2025-10-03T09:00:00+00:00", "m1")
    engine.form_memories("c1")
    engine.add_message("c2", "user", "Mira completed the episode schema on October 18, 2025.",
                       "2025-10-18T09:00:00+00:00", "m2")
    engine.form_memories("c2")

    listed = {episode["title"]: episode["status"] for episode in engine.list_episodes()}
    assert listed == {"Mira episode schema task": "done", "Mira completed episode schema": "active"}


def test_cancelled_task_is_marked_cancelled(tmp_path):
    engine, _ = lifecycle_engine(tmp_path, [
        payload(episode_item("Ravi retrieval task", "task",
                             "Ravi will run the retrieval experiment.",
                             ["Ravi will run the retrieval experiment."], participants=("Ravi",))),
        payload(episode_item("Retrieval experiment cancelled", "decision",
                             "The team cancelled the retrieval experiment.",
                             ["The retrieval experiment was cancelled."], participants=("Ravi",),
                             source_ids=("m2",))),
    ])
    engine.add_message("c1", "user", "Ravi will run the retrieval experiment.", "2025-10-03T10:00:00+00:00", "m1")
    engine.form_memories("c1")
    engine.add_message("c2", "user", "We cancelled the retrieval experiment.", "2025-10-05T10:00:00+00:00", "m2")
    engine.form_memories("c2")

    assert [episode["title"] for episode in engine.list_episodes()] == ["Retrieval experiment cancelled"]
    cancelled = next(episode for episode in engine.list_episodes(include_inactive=True)
                     if episode["status"] == "cancelled")
    assert cancelled["title"] == "Ravi retrieval task"


def test_consolidate_duplicates_keeps_the_richer_memory(tmp_path):
    engine, _ = lifecycle_engine(tmp_path, [])
    engine.add_message("c1", "user", "placeholder", "2026-10-01T09:00:00+00:00", "m1")
    rich = Episode(
        **episode_item("Prototype presentation date", "goal",
                       "The user presents the prototype to the mentor on November 6, 2026.",
                       ["The presentation is on November 6, 2026."],
                       participants=("user", "mentor"), event_time="2026-11-06"),
        episode_id="ep_rich", created_at="2026-10-01T09:00:00+00:00", source_conversation_id="c1",
    )
    vague = Episode(
        **episode_item("Prototype presentation schedule", "goal",
                       "The user scheduled a presentation with the mentor.",
                       ["A presentation was scheduled."],
                       participants=("user", "mentor")),
        episode_id="ep_vague", created_at="2026-10-02T09:00:00+00:00", source_conversation_id="c1",
    )
    engine._insert_episode(rich, lifecycle_embed("preference bullet table schema completed cancel retrieval " + rich.title))
    engine._insert_episode(vague, lifecycle_embed("preference bullet table schema completed cancel retrieval " + vague.title))

    merged = engine.consolidate_duplicates()

    assert merged == [{"kept": "ep_rich", "merged": "ep_vague",
                       "title": "Prototype presentation date"}]
    active = engine.list_episodes()
    assert [episode["episode_id"] for episode in active] == ["ep_rich"]
    assert len(active[0]["facts"]) == 2


def test_incremental_writer_processes_each_turn_once(tmp_path):
    engine, llm = lifecycle_engine(tmp_path, [
        payload(episode_item("Preference: bullet points", "preference",
                             "The user prefers concise bullet points.",
                             ["The user prefers concise bullet points."], source_ids=("m1",))),
        payload(episode_item("Preference: tables", "preference",
                             "The user now prefers tables.",
                             ["The user now prefers tables."], source_ids=("m3",))),
    ])
    engine.add_message("c1", "user", "I prefer bullet points.", "2026-10-01T09:00:00+00:00", "m1")
    engine.add_message("c1", "assistant", "Noted.", "2026-10-01T09:00:05+00:00", "m2")

    stored, errors = engine.form_memories("c1", incremental=True, end=False)
    assert [episode["title"] for episode in stored] == ["Preference: bullet points"]
    assert not errors
    with engine._db() as conn:
        status = conn.execute(
            "SELECT status FROM conversations WHERE conversation_id = 'c1'"
        ).fetchone()["status"]
    assert status == "active"

    engine.add_message("c1", "user", "Actually, I prefer tables.", "2026-10-02T09:00:00+00:00", "m3")
    stored, _ = engine.form_memories("c1", incremental=True, end=False)

    assert [episode["title"] for episode in stored] == ["Preference: tables"]
    second_prompt = llm.chat_calls[-1][-1]["content"]
    assert "[NEW] [2026-10-02T09:00:00+00:00] user (message_id=m3)" in second_prompt
    assert "[NEW] [2026-10-01T09:00:00+00:00] user (message_id=m1)" not in second_prompt
    assert "(message_id=m1)" in second_prompt  # older turns stay as context

    # Nothing new was written, so the writer does not call the model again.
    assert engine.form_memories("c1", incremental=True, end=False) == ([], [])
    assert len(llm.chat_calls) == 2


def test_incremental_writer_retries_a_failed_extraction(tmp_path):
    engine = make_engine(tmp_path, FakeLLM([], embed_fn=lifecycle_embed))
    llm = engine.llm
    engine.add_message("c1", "user", "I prefer bullet points.", "2026-10-01T09:00:00+00:00", "m1")

    stored, errors = engine.form_memories("c1", incremental=True, end=False)
    assert stored == []
    assert any("extraction failed" in error for error in errors)

    llm.chat_responses.append(payload(episode_item(
        "Preference: bullet points", "preference",
        "The user prefers concise bullet points.",
        ["The user prefers concise bullet points."], source_ids=("m1",),
    )))
    stored, _ = engine.form_memories("c1", incremental=True, end=False)

    assert [episode["title"] for episode in stored] == ["Preference: bullet points"]
    assert "[NEW] [2026-10-01T09:00:00+00:00] user (message_id=m1)" in llm.chat_calls[-1][-1]["content"]


def test_saving_merges_duplicates_automatically(tmp_path, monkeypatch):
    engine, _ = lifecycle_engine(tmp_path, [
        payload(episode_item("Prototype presentation date", "goal",
                             "The user presents on November 6, 2026.",
                             ["The presentation is on November 6, 2026."],
                             event_time="2026-11-06", source_ids=("m1",))),
    ])
    calls: list[str] = []
    monkeypatch.setattr(engine, "consolidate_duplicates",
                        lambda: calls.append("merged") or [])
    engine.add_message("c1", "user", "I present on November 6, 2026.", "2026-10-01T09:00:00+00:00", "m1")

    stored, _ = engine.form_memories("c1", incremental=True, end=False)

    assert len(stored) == 1
    assert calls == ["merged"]


def test_no_supporting_memory_returns_empty_evidence_without_fabrication(tmp_path):
    engine = make_engine(tmp_path, FakeLLM())
    llm = engine.llm
    llm.chat_responses = [
        json.dumps({"needs_memory": True, "search_query": "What retrieval accuracy did the team achieve?"}),
        "The available records do not establish a numerical retrieval-accuracy result.",
    ]
    turn = engine.handle_turn("What retrieval accuracy did the team achieve?", [], retrieval_enabled=True)

    assert turn["details"]["searched"] is True
    assert turn["details"]["results"] == []
    assert "empty" in turn["details"]["evidence"].lower()
    answer_prompt = llm.chat_calls[-1]
    evidence_message = next(m["content"] for m in answer_prompt if m["content"].startswith("RETRIEVED"))
    assert "No episodic memories matched" in evidence_message
    assert "not establish" in turn["answer"]
