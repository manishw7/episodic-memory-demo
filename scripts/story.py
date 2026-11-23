"""The synthetic four-week story behind the visual demo.

Design notes (deliberate, not accidental):

* One event per message. The extractor splits messages that contain several events, which
  creates near-duplicate task pairs, so every sentence here states exactly one thing.
* A superseding pair uses near-identical wording ("...is due on 26 October 2026" ->
  "...is now due on 9 November 2026"). The lifecycle linker only replaces a memory when the
  two embeddings are at least 0.72 similar, so the wording is the tuning lever.
* Every task has a different owner. The linker matches on shared participant names, so
  giving Ravi, Mira, Asha and Dev one task each prevents a cancellation or completion from
  closing somebody else's work.
* The preference change is deliberately worded to stay a separate memory (a different
  number and a different title), so it becomes a supersession instead of being merged.
* Each message carries an explicit date. The builder stamps the archive with these dates, so
  the timeline is complete even when the extractor leaves event_time empty.

The builder runs these through the real extraction pipeline; nothing is hand-written into
the database.
"""

# Each session is one conversation, extracted in order. The builder adds the messages, runs
# real extraction, then stamps the result with these dates.
SESSIONS: list[dict[str, object]] = [
    {
        "conversation_id": "conv_atlas_01_kickoff",
        "messages": [
            ("story-001", "2026-10-05T09:00:00+00:00",
             "Project Atlas is a multi-user cloud service for shared project notes."),
            ("story-002", "2026-10-05T09:04:00+00:00",
             "We chose SQLite for Project Atlas storage because it runs locally without a server."),
            ("story-003", "2026-10-05T09:08:00+00:00",
             "The Project Atlas team is Mira, Asha, Ravi, and Dev."),
            ("story-004", "2026-10-05T09:12:00+00:00",
             "I prefer bullet-point summaries when you report progress, with at most 5 bullets."),
        ],
    },
    {
        "conversation_id": "conv_atlas_02_scope_change",
        "messages": [
            ("story-005", "2026-10-12T10:00:00+00:00",
             "As of 12 October 2026, Project Atlas is a single-user local prototype, not a "
             "multi-user cloud service."),
            ("story-006", "2026-10-12T10:05:00+00:00",
             "Ravi's retrieval experiment is due on 2 November 2026."),
            ("story-007", "2026-10-12T10:10:00+00:00",
             "Dev's usage dashboard is due on 30 October 2026."),
        ],
    },
    {
        "conversation_id": "conv_atlas_03_planning",
        "messages": [
            ("story-008", "2026-10-19T14:00:00+00:00",
             "Mira's episode schema is due on 26 October 2026."),
            ("story-009", "2026-10-19T14:05:00+00:00",
             "Asha's deletion tests are due on 2 November 2026."),
            ("story-010", "2026-10-19T14:10:00+00:00",
             "We chose Streamlit for the Project Atlas interface because it runs locally in a "
             "browser."),
            ("story-011", "2026-10-19T14:15:00+00:00",
             "For progress reports, I now prefer a table with 3 columns instead of bullet-point "
             "summaries."),
        ],
    },
    {
        "conversation_id": "conv_atlas_04_changes",
        "messages": [
            ("story-012", "2026-11-02T11:00:00+00:00",
             "Mira's episode schema is now due on 9 November 2026 instead of 26 October 2026."),
            ("story-013", "2026-11-02T11:05:00+00:00",
             "As of 2 November 2026, Dev's usage dashboard is cancelled and will not be built."),
        ],
    },
    {
        "conversation_id": "conv_atlas_05_completion",
        "messages": [
            ("story-014", "2026-11-09T16:00:00+00:00",
             "Mira completed the episode schema on 9 November 2026."),
            ("story-015", "2026-11-09T16:04:00+00:00",
             "Asha completed the deletion tests on 9 November 2026."),
            ("story-016", "2026-11-09T16:08:00+00:00",
             "Ravi completed the retrieval experiment on 9 November 2026 after switching from "
             "chat-model embeddings to embeddinggemma."),
            ("story-017", "2026-11-09T16:12:00+00:00",
             "Goal: present the Project Atlas prototype to mentors on 20 November 2026."),
        ],
    },
]


def all_messages() -> list[tuple[str, str, str]]:
    """Flat (message_id, created_at, content) list, in story order."""
    return [message for session in SESSIONS for message in session["messages"]]
