#!/usr/bin/env python3
"""Build the synthetic demo archive used by the Memory Map and Time Machine screens.

It writes a separate SQLite file (default: demo.db) by running the *real* extraction
pipeline over scripts/story.py, one conversation session at a time. Each project is built into
its own temporary archive and the rows are merged afterwards: in a single shared history the
extractor treats a second project's "definition"/"team" memories as already known. It never
opens memory.db.

After extraction the episodes and their audit events are stamped with the dates of the
messages that produced them. Extraction itself has no notion of "now" for a transcript that
spans weeks, so this is what makes the timeline meaningful; the memory content is still
entirely the extractor's.

    python scripts/build_demo_db.py            # build demo.db (refuses to overwrite)
    python scripts/build_demo_db.py --force    # rebuild from scratch
    python scripts/build_demo_db.py --check    # inspect an existing demo.db (no model calls)
    python scripts/build_demo_db.py --project Atlas   # only one project (debugging)
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from memory_engine import MemoryEngine, Settings  # noqa: E402
import story  # noqa: E402


def remove_sqlite_files(path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix)
        if candidate.exists():
            candidate.unlink()


def project_names() -> list[str]:
    """Story project names, in the order they first appear."""
    names: list[str] = []
    for session in story.SESSIONS:
        if session["project"] not in names:
            names.append(str(session["project"]))
    return names


def build_sessions(engine: MemoryEngine, sessions: list[dict[str, object]]) -> int:
    """Run the real extractor over each session and return how many memories it stored."""
    total_stored = 0
    for session in sessions:
        conversation_id = session["conversation_id"]
        messages = session["messages"]
        print(f"== [{session['project']}] {conversation_id} ({messages[0][1][:10]}) ==")

        for message_id, created_at, content in messages:
            engine.add_message(conversation_id, "user", content, created_at, message_id)

        stored, notes = engine.form_memories(conversation_id, incremental=True, end=True)
        total_stored += len(stored)
        print(f"  stored {len(stored)}; rejected {len(notes)}")
        for note in notes:
            print(f"    ! {note}")
    return total_stored


def merge_databases(target: Path, sources: list[Path]) -> None:
    """Combine archives built independently, preserving episode and event ids."""
    remove_sqlite_files(target)
    # Let the engine create the schema, then copy the rows.
    MemoryEngine(replace(Settings.from_env(), database_path=str(target)))
    conn = sqlite3.connect(target)
    try:
        for index, source in enumerate(sources):
            conn.execute(f"ATTACH DATABASE ? AS part{index}", (str(source),))
        for index in range(len(sources)):
            conn.execute(f"INSERT INTO episodes SELECT * FROM part{index}.episodes")
            conn.execute(f"INSERT INTO memory_events SELECT * FROM part{index}.memory_events")
        conn.commit()
    finally:
        conn.close()


def build(db_path: Path, only: str | None = None) -> int:
    settings = replace(Settings.from_env(), database_path=str(db_path))

    print(f"Database: {db_path}")
    print(f"Models:   {settings.chat_model} + {settings.embed_model}")
    print(f"Sessions: {len(story.SESSIONS)}  "
          f"Messages: {len(story.all_messages())}\n")

    if only:
        engine = MemoryEngine(settings)
        total_stored = build_sessions(
            engine, [s for s in story.SESSIONS if s["project"] == only]
        )
    else:
        # Build each project into its own archive, then merge. When every project shares one
        # extraction history the model sees another project's "definition" and "team" memories
        # in its known list and quietly skips the new project's equivalents.
        temporary: list[Path] = []
        total_stored = 0
        for project in project_names():
            temp = db_path.with_name(f"{db_path.name}.{project.lower()}.tmp")
            remove_sqlite_files(temp)
            engine = MemoryEngine(replace(Settings.from_env(), database_path=str(temp)))
            total_stored += build_sessions(
                engine, [s for s in story.SESSIONS if s["project"] == project]
            )
            temporary.append(temp)

        print("\nMerging per-project archives...")
        merge_databases(db_path, temporary)
        for temp in temporary:
            remove_sqlite_files(temp)

    print(f"\nStored {total_stored} episode(s) in total.")

    stamped = stamp_story_dates(db_path)
    print(f"Stamped {stamped} episode(s) and their audit events with the story dates.\n")

    report(db_path)
    return 0


def stamp_story_dates(db_path: Path) -> int:
    """Rewrite created_at on episodes and memory_events using the source message dates."""
    message_dates = {message_id: created_at
                     for message_id, created_at, _ in story.all_messages()}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT rowid, episode_id, source_message_ids FROM episodes ORDER BY rowid"
        ).fetchall()

        base: dict[str, datetime] = {}
        for row in rows:
            ids = json.loads(row["source_message_ids"] or "[]")
            dates = [message_dates[i] for i in ids if i in message_dates]
            if dates:
                base[row["episode_id"]] = min(datetime.fromisoformat(d) for d in dates)

        # Keep insertion order stable inside one day: first episode at :00, next at :01, ...
        per_day: dict[str, int] = {}
        stamped: dict[str, str] = {}
        for row in rows:
            episode_id = row["episode_id"]
            if episode_id not in base:
                continue
            when = base[episode_id]
            day = when.date().isoformat()
            offset = per_day.get(day, 0)
            per_day[day] = offset + 1
            stamp = (when + timedelta(seconds=offset)).isoformat(timespec="seconds")
            stamped[episode_id] = stamp
            conn.execute(
                "UPDATE episodes SET created_at = ?, updated_at = ? WHERE episode_id = ?",
                (stamp, stamp, episode_id),
            )

        events = conn.execute(
            "SELECT event_id, episode_id, detail FROM memory_events ORDER BY rowid"
        ).fetchall()
        for event in events:
            when = stamped.get(event["episode_id"])
            for caused_by in re.findall(r"ep_[0-9a-f]+", event["detail"] or ""):
                if caused_by in stamped:
                    candidate = stamped[caused_by]
                    when = candidate if when is None else max(when, candidate)
            if when is not None:
                conn.execute("UPDATE memory_events SET created_at = ? WHERE event_id = ?",
                             (when, event["event_id"]))

        conn.commit()
        return len(stamped)
    finally:
        conn.close()


SUBJECT_STOPWORDS = {
    "task", "deadline", "assignment", "cancellation", "cancel", "update", "initial",
    "completion", "completed", "due", "date", "the", "a", "an", "and", "of", "for",
    "to", "in", "on", "at", "by", "with", "user", "team",
}


def subject_words(title: str) -> set[str]:
    """The subject of a task title, ignoring lifecycle words."""
    return {word for word in re.findall(r"[a-z0-9]{3,}", title.lower())
            if word not in SUBJECT_STOPWORDS}


def report(db_path: Path) -> None:
    settings = replace(Settings.from_env(), database_path=str(db_path))
    engine = MemoryEngine(settings)
    episodes = engine.list_episodes(include_embeddings=False, include_inactive=True)
    events = engine.list_events(limit=1000)

    counts: dict[str, int] = {}
    for episode in episodes:
        counts[episode["status"]] = counts.get(episode["status"], 0) + 1

    actions: dict[str, int] = {}
    for event in events:
        actions[event["action"]] = actions.get(event["action"], 0) + 1

    print("Status totals:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "empty")
    print("Events:", ", ".join(f"{k}={v}" for k, v in sorted(actions.items())) or "none")

    by_id = {episode["episode_id"]: episode for episode in episodes}
    ordered = sorted(episodes, key=lambda e: (e["created_at"], e["title"]))

    def project_of(episode: dict[str, Any]) -> str:
        return story.project_of_conversation(episode["source_conversation_id"])

    grouped: dict[str, list[dict[str, Any]]] = {}
    for episode in ordered:
        grouped.setdefault(project_of(episode), []).append(episode)

    print("\nBy project:")
    for name in sorted(grouped):
        subset = grouped[name]
        sub_counts: dict[str, int] = {}
        for episode in subset:
            sub_counts[episode["status"]] = sub_counts.get(episode["status"], 0) + 1
        detail = ", ".join(f"{k}={v}" for k, v in sorted(sub_counts.items()))
        print(f"  {name:<8} {len(subset):>2} memories   {detail}")

    print("\nTimeline (date the system learned it):")
    for episode in ordered:
        when = episode["created_at"][:10]
        link = f"  -> {episode['superseded_by']}" if episode.get("superseded_by") else ""
        print(f"  {when}  {project_of(episode):<8} {episode['status']:<10} "
              f"{episode['event_type']:<14} {episode['title'][:48]}{link}")

    chains = [ep for ep in ordered if ep.get("superseded_by")]
    if chains:
        print("\nLifecycle chains:")
        for old in chains:
            new = by_id.get(old["superseded_by"], {})
            print(f"  [{project_of(old)}] [{old['status']}] {old['title'][:42]}")
            print(f"      -> [{project_of(new) if new else '?'}] "
                  f"{new.get('title', old['superseded_by'])[:50]} "
                  f"({new.get('status', '?')})")

    print()
    expected = {"active", "superseded", "done", "cancelled"}
    missing = expected - set(counts)
    problems: list[str] = []
    if missing:
        problems.append(f"no {', '.join(sorted(missing))} memories")

    dangling = [ep["superseded_by"] for ep in episodes
                if ep.get("superseded_by") and ep["superseded_by"] not in by_id]
    if dangling:
        problems.append(f"dangling superseded_by: {', '.join(dangling)}")

    for old in chains:
        new = by_id.get(old["superseded_by"])
        if new is None:
            continue
        if project_of(old) != project_of(new):
            problems.append(
                f"cross-project link: [{project_of(old)}] {old['title']} -> "
                f"[{project_of(new)}] {new['title']}"
            )
        if new["created_at"][:10] < old["created_at"][:10]:
            problems.append(
                f"time runs backwards: {new['title']} ({new['created_at'][:10]}) "
                f"replaces {old['title']} ({old['created_at'][:10]})"
            )
        if not (subject_words(old["title"]) & subject_words(new["title"])):
            problems.append(f"unrelated supersession: {old['title']} -> {new['title']}")

    # A cancelled or completed task should not still have an active task/goal twin. The
    # cancellation record itself ("... cancelled") is expected to stay active, so it is skipped.
    for closed in ordered:
        if closed["status"] not in ("cancelled", "done"):
            continue
        subject = subject_words(closed["title"])
        if not subject:
            continue
        for other in ordered:
            if (other is closed or other["status"] != "active"
                    or other["event_type"] not in ("task", "goal")):
                continue
            if "cancel" in other["title"].lower():
                continue  # the closure record, which is meant to stay active
            if subject <= subject_words(other["title"]):
                problems.append(
                    f"active {other['event_type']} duplicates a {closed['status']} one: "
                    f"{other['title']}"
                )

    if problems:
        print("Checks: NEEDS WORK")
        for problem in problems:
            print(f"  - {problem}")
    else:
        print("Checks: PASS - all four states, no dangling or cross-project links, "
              "no active duplicates.")


def check(db_path: Path) -> int:
    if not db_path.exists():
        print(f"{db_path} does not exist. Run the builder first.", file=sys.stderr)
        return 1
    report(db_path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(ROOT / "demo.db"))
    parser.add_argument("--force", action="store_true", help="rebuild even if the file exists")
    parser.add_argument("--check", action="store_true", help="only inspect an existing archive")
    parser.add_argument("--project", default=None,
                        help="build only one story project (Atlas, Beacon, Cinder)")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if db_path.name == "memory.db":
        print("Refusing to write to memory.db. Use a separate demo database.", file=sys.stderr)
        return 2

    if args.check:
        return check(db_path)

    if db_path.exists():
        if not args.force:
            print(f"{db_path} already exists. Use --force to rebuild.", file=sys.stderr)
            return 1
        remove_sqlite_files(db_path)

    return build(db_path, only=args.project)


if __name__ == "__main__":
    raise SystemExit(main())
