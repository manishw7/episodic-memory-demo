"""The synthetic multi-project story behind the visual demo.

Design notes (deliberate, not accidental):

* One event per message. The extractor splits messages that contain several events, which
  creates near-duplicate task pairs, so every sentence here states exactly one thing.
* A superseding pair uses near-identical wording ("...is due on 26 October 2026" ->
  "...is now due on 9 November 2026"). The lifecycle linker only replaces a memory when the
  two embeddings are at least 0.72 similar, so the wording is the tuning lever.
* Every task has a different owner. The linker matches on shared participant names, so a
  cancellation or completion cannot close somebody else's work.
* Preference changes and scope changes carry different numbers and titles, so they become
  supersessions instead of being merged as duplicates.
* Each message carries an explicit date. The builder stamps the archive with these dates, so
  the timeline is complete even when the extractor leaves event_time empty.
* Three projects share people (Mira, Ravi) but not task ownership. That produces visible
  cross-project connections in the graph without cross-project lifecycle links.

The builder runs these through the real extraction pipeline; nothing is hand-written into
the database.
"""

# Each session is one conversation, extracted in order. The builder adds the messages, runs
# real extraction, then stamps the result with these dates.
SESSIONS: list[dict[str, object]] = [
    # =====================================================================
    # Project Atlas - the main four-week narrative (Oct 5 - Nov 9)
    # =====================================================================
    {
        "project": "Atlas",
        "conversation_id": "conv_atlas_01_kickoff",
        "messages": [
            ("story-001", "2026-10-05T09:00:00+00:00",
             "Project Atlas is a multi-user cloud service for shared project notes."),
            ("story-002", "2026-10-05T09:04:00+00:00",
             "We chose SQLite for Project Atlas storage because it runs locally without a server."),
            ("story-003", "2026-10-05T09:08:00+00:00",
             "Mira, Asha, Ravi, and Dev are the four engineers building Atlas."),
            ("story-004", "2026-10-05T09:12:00+00:00",
             "I prefer bullet-point summaries when you report progress, with at most 5 bullets."),
        ],
    },
    {
        "project": "Atlas",
        "conversation_id": "conv_atlas_02_scope_change",
        "messages": [
            ("story-005", "2026-10-12T10:00:00+00:00",
             "Project Atlas is a single-user local prototype, not a multi-user cloud service for "
             "shared project notes, as of 12 October 2026."),
            ("story-006", "2026-10-12T10:05:00+00:00",
             "Ravi's retrieval experiment is due on 2 November 2026."),
            ("story-007", "2026-10-12T10:10:00+00:00",
             "Dev's usage dashboard is due on 30 October 2026."),
        ],
    },
    {
        "project": "Atlas",
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
        "project": "Atlas",
        "conversation_id": "conv_atlas_04_changes",
        "messages": [
            ("story-012", "2026-11-02T11:00:00+00:00",
             "Mira's episode schema is now due on 9 November 2026 instead of 26 October 2026."),
            ("story-013", "2026-11-02T11:05:00+00:00",
             "As of 2 November 2026, Dev's usage dashboard is cancelled and will not be built."),
        ],
    },
    {
        "project": "Atlas",
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

    # =====================================================================
    # Project Beacon - a charity launch site (Sep 14 - Nov 6)
    # =====================================================================
    {
        "project": "Beacon",
        "conversation_id": "conv_beacon_01_setup",
        "messages": [
            ("beacon-001", "2026-09-14T09:00:00+00:00",
             "Project Beacon is a public launch site for the river cleanup charity."),
            ("beacon-002", "2026-09-14T09:04:00+00:00",
             "Astro is the framework for the Beacon site; it ships almost no JavaScript."),
            ("beacon-003", "2026-09-14T09:08:00+00:00",
             "Noah, Priya, Sam, Elena, and Maya are the five people running the Beacon launch."),
        ],
    },
    {
        "project": "Beacon",
        "conversation_id": "conv_beacon_02_dates",
        "messages": [
            ("beacon-004", "2026-09-21T10:00:00+00:00",
             "Elena's goal is to launch Beacon on 30 October 2026."),
            ("beacon-005", "2026-09-21T10:05:00+00:00",
             "Priya owns the Beacon copy; it is due on 16 October 2026."),
            ("beacon-006", "2026-09-21T10:10:00+00:00",
             "Noah owns the Beacon landing page; it is due on 23 October 2026."),
            ("beacon-007", "2026-09-21T10:15:00+00:00",
             "Sam owns the Beacon traffic report; it is due on 23 October 2026."),
            ("beacon-008", "2026-09-21T10:20:00+00:00",
             "Maya owns the printed postcards for Beacon; they are due on 20 October 2026."),
        ],
    },
    {
        "project": "Beacon",
        "conversation_id": "conv_beacon_03_design",
        "messages": [
            ("beacon-009", "2026-10-05T11:00:00+00:00",
             "The Beacon brand uses the river cleanup colours, green and sand."),
            ("beacon-010", "2026-10-05T11:05:00+00:00",
             "Plausible is the Beacon metrics tool."),
        ],
    },
    {
        "project": "Beacon",
        "conversation_id": "conv_beacon_04_changes",
        "messages": [
            ("beacon-011", "2026-10-16T14:00:00+00:00",
             "Priya completed the Beacon copy on 16 October 2026."),
            ("beacon-012", "2026-10-16T14:05:00+00:00",
             "Elena's goal is to launch Beacon on 6 November 2026 instead of 30 October 2026."),
            ("beacon-013", "2026-10-16T14:10:00+00:00",
             "As of 16 October 2026, Maya's printed postcards for Beacon are cancelled and will "
             "not be printed."),
        ],
    },
    {
        "project": "Beacon",
        "conversation_id": "conv_beacon_05_launch",
        "messages": [
            ("beacon-014", "2026-11-06T15:00:00+00:00",
             "Noah completed the Beacon landing page on 6 November 2026."),
            ("beacon-015", "2026-11-06T15:04:00+00:00",
             "Sam completed the Beacon traffic report on 6 November 2026."),
            ("beacon-016", "2026-11-06T15:08:00+00:00",
             "Elena launched the Beacon site on 6 November 2026."),
        ],
    },
    {
        # A single-message session keeps this a separate memory. Mira also owns an Atlas task,
        # which is what connects the Beacon cluster to the Atlas cluster in the graph.
        "project": "Beacon",
        "conversation_id": "conv_beacon_06_bridge",
        "messages": [
            ("beacon-017", "2026-11-03T10:00:00+00:00",
             "Mira proofread the Beacon charity story on 3 November 2026."),
        ],
    },

    # =====================================================================
    # Project Cinder - an internal data pipeline (Sep 28 - Nov 6)
    # =====================================================================
    {
        "project": "Cinder",
        "conversation_id": "conv_cinder_01_setup",
        "messages": [
            ("cinder-001", "2026-09-28T09:00:00+00:00",
             "Project Cinder is an internal data pipeline that rebuilds the weekly analytics "
             "tables."),
            ("cinder-002", "2026-09-28T09:04:00+00:00",
             "DuckDB is the analytics store for Cinder; it runs in-process without a server."),
        ],
    },
    {
        "project": "Cinder",
        "conversation_id": "conv_cinder_02_plan",
        "messages": [
            ("cinder-004", "2026-10-02T10:00:00+00:00",
             "Ravi reviewed the Cinder schema on 2 October 2026."),
            ("cinder-005", "2026-10-02T10:05:00+00:00",
             "Omar's Cinder schema is due on 16 October 2026."),
            ("cinder-006", "2026-10-02T10:10:00+00:00",
             "Lena's Cinder pipeline is due on 23 October 2026."),
            ("cinder-007", "2026-10-02T10:15:00+00:00",
             "Tessa's Cinder backfill tests are due on 6 November 2026."),
            ("cinder-008", "2026-10-02T10:20:00+00:00",
             "Nadia's Cinder CSV export is due on 30 October 2026."),
        ],
    },
    {
        "project": "Cinder",
        "conversation_id": "conv_cinder_03_changes",
        "messages": [
            ("cinder-009", "2026-10-16T11:00:00+00:00",
             "Omar completed the Cinder schema on 16 October 2026."),
            ("cinder-010", "2026-10-16T11:05:00+00:00",
             "Lena's Cinder pipeline is now due on 6 November 2026 instead of 23 October 2026."),
            ("cinder-011", "2026-10-16T11:10:00+00:00",
             "As of 16 October 2026, Nadia's Cinder CSV export is cancelled and will not be "
             "built."),
        ],
    },
    {
        "project": "Cinder",
        "conversation_id": "conv_cinder_04_finish",
        "messages": [
            ("cinder-012", "2026-11-06T14:00:00+00:00",
             "Lena completed the Cinder pipeline on 6 November 2026."),
            ("cinder-013", "2026-11-06T14:05:00+00:00",
             "Tessa completed the Cinder backfill tests on 6 November 2026."),
            ("cinder-014", "2026-11-06T14:10:00+00:00",
             "The Cinder weekly refresh finished in 4 minutes on 6 November 2026."),
            ("cinder-015", "2026-11-06T14:15:00+00:00",
             "Prefect schedules the Cinder jobs and retries failed runs."),
        ],
    },
    {
        # Asha also owns the Atlas deletion tests, linking Cinder to the Atlas cluster.
        "project": "Cinder",
        "conversation_id": "conv_cinder_05_bridge",
        "messages": [
            ("cinder-016", "2026-11-04T10:00:00+00:00",
             "Asha audited Cinder's storage costs on 4 November 2026."),
        ],
    },
    {
        # Priya also owns the Beacon copy, linking Atlas back to the Beacon cluster.
        "project": "Atlas",
        "conversation_id": "conv_atlas_06_bridge",
        "messages": [
            ("story-018", "2026-11-10T10:00:00+00:00",
             "Priya's review of the Atlas demo script is due on 12 November 2026."),
        ],
    },
]


def all_messages() -> list[tuple[str, str, str]]:
    """Flat (message_id, created_at, content) list, in story order."""
    return [message for session in SESSIONS for message in session["messages"]]


def project_of_conversation(conversation_id: str) -> str:
    """Map a demo conversation id to its project name."""
    for session in SESSIONS:
        if session["conversation_id"] == conversation_id:
            return str(session["project"])
    return "Live"
