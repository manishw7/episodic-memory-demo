"""Minimal episodic memory: formation, SQLite storage, embedding retrieval, grounded answers.

Everything runs against a local Ollama server. There is deliberately no cloud fallback.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Iterator, Literal, Optional, get_args

import numpy as np
import ollama
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator

load_dotenv()

EventType = Literal["event", "decision", "task", "outcome", "project_update", "preference", "goal"]

EXTRACTION_SYSTEM = """You turn a conversation into durable episodic memories.

Return JSON only, with this shape:
{"episodes": [{"title": "...", "event_type": "event|decision|task|outcome|project_update|preference|goal",
  "event_time": "ISO date/time or null", "summary": "...", "participants": ["..."],
  "facts": ["..."], "outcome": "completed result or null", "source_message_ids": ["..."]}]}

Rules:
- Extract zero or more episodes. Return {"episodes": []} when nothing is worth remembering.
- ONE EPISODE PER DISTINCT EVENT. If one message contains several separate events (for example one
  person's deadline, another person's completed work, and a blocker), emit one episode per event.
  Never merge different events into one episode, even when they share a message.
- The same applies to lists of independent facts. When a message is a profile or a list of separate
  attributes (education, device, health, goals, habits), emit one episode per topic, not one giant
  episode. Durability test: if two facts would be useful in different future conversations, they
  belong in different episodes. A device, address, or contact detail is its own episode.
- Merge only sentences that describe the same single event.
- Store: decisions and their reasons, commitments and assignments, completed outcomes, blockers and
  status changes, durable preferences, and goals.
- Do NOT store: greetings, thanks, small talk, weather, pleasantries, vague progress such as
  "things are going well", or hypotheticals such as "we might" or "maybe later".
- A rejected option, a requirement, or a reason is part of the decision or task it explains. Fold it
  into that episode's facts; never emit it as its own episode.
- Weather, mood, or how the day is going is never a preference, goal, or event, even when the user
  phrases it as an opinion. A preference must be about how the user wants to work or be answered
  (format, tone, tools, schedule).
- Ignore the assistant's suggestions unless the user explicitly accepts them.
- Never record a question the user asked as if it were a fact. Never turn a date the user asked
  about into an established date.
- Never store the assistant's recommendations, advice, warnings, or analysis as a memory. Only store
  what the user stated or what actually happened. If the assistant said "you should avoid X" but the
  user did not agree, that is not a memory.
- source_message_ids must contain only IDs from USER messages. Assistant messages are context, not
  sources. Never cite an assistant message as a source, even when it repeats a fact.
- If a statement is self-reported health information (allergies, diagnoses, symptoms), store it as
  a project_update or preference with the user's own words, and do not treat it as medically
  verified. A single self-reported health claim should be one episode, not split into several.
- event_time is the date or time of the event itself (a deadline, meeting, or completion), copied
  from the transcript. It is NOT the date of the conversation. Use null when it is not established.
- outcome is null unless the transcript establishes a result. A task/commitment that is only
  assigned or planned has outcome null. Distinguish intentions from completed actions.
- source_message_ids must contain one or more message_id values copied exactly from the transcript.
- participants contains named people or teams involved. Do not use speaker roles such as "user" or
  "assistant" when named people are present; "user" is allowed for the speaker's own preference,
  goal, or plan.
- Each fact should be a self-contained statement with the names, dates, and reasons that matter.
- Do not invent IDs, dates, outcomes, or facts. Do not add fields.
- Use "preference" only for durable likes/dislikes or working preferences. Use "project_update"
  for status, constraints, or unresolved/missing results. Use "goal" for a target the user is
  working toward, such as a presentation or deadline. Use "task" for work assigned to someone.
- A choice between alternatives is a "decision", even when phrased as "selected", "chose", or
  "went with". An "outcome" is a completed result of work, not the act of choosing.
- Keep titles short and specific. A title must never be about small talk."""

DECISION_SYSTEM = """You decide whether a new user message requires searching a persistent archive
of memories from earlier conversations.

Set needs_memory to true when the message asks about earlier conversations, prior decisions, events,
assigned tasks, outcomes, project status, or durable preferences/goals. Also set it to true when the
message mentions a named person, project, experiment, date, commitment, or completion status whose
answer could live in project history, or uses references such as "the project", "the test", or
"last time".

Apply this to implicit and possessive references too: "my presentation", "my preferred format",
"our decision", "the mentor session", "the talk". A request that depends on the user's own plans,
preferences, project, or prior work still needs the archive even if it does not say "remember" or
"previous conversation".

Default to searching. Set needs_memory to false only for clearly self-contained requests: general
knowledge, math, casual conversation, creative writing, or a task whose needed inputs are all in the
message. Current-session messages are already available to the answerer; use them to resolve
references, but do not assume the current session contains the answer.

Return JSON only:
{"needs_memory": true, "search_query": "self-contained retrieval query"}

If needs_memory is false, search_query must be "". The search_query should expand pronouns and
references into a standalone query."""

ANSWER_SYSTEM = """You are a careful local assistant. Answer the user's message clearly and concisely.

If a RETRIEVED EPISODIC MEMORY section is supplied:
- It is the only evidence about earlier conversations. Ground every historical claim in it.
- Answer the user's actual question. Use the evidence as context, not as a list to recite. Do not
  enumerate stored episodes unless the user asks for the records.
- Apply the evidence when appropriate: follow a stated preference, build on a decision, or reason
  toward next steps. Clearly label suggestions and uncertain inferences as suggestions/inferences.
- Never invent past events, decisions, dates, people, or numbers.
- Do not infer gender or other personal attributes that the evidence does not state. Use "they" when
  the evidence does not state pronouns.
- If the evidence does not establish the answer, say that the available records do not establish it.
- If the evidence says no memories matched, say that no relevant memories were found; do not guess.
- Earlier turns in this conversation are conversational context, not memory evidence. If the
  RETRIEVED EPISODIC MEMORY section does not establish a fact, do not restate it from an earlier
  assistant message; say that the available records do not establish it.
- Distinguish supported facts from uncertain inference, and label any inference as inference.
- Do not claim a search succeeded if the evidence is empty.
- Answer the question first. Do not open with a description of the archive's state ("there is
  conflicting information", "the records do not establish...") unless the answer really is
  unavailable.
- Only call something a conflict when two memories give different values for the same attribute of
  the same thing, such as two different laptop models or two different dates for one review.
- A memory that records a request, a plan, a question, or a moment when the user did not yet know
  something is background, not a contradiction. Not knowing a detail in the past does not contradict
  a detail stated later, and asking someone else for information says nothing about the user's own
  hardware.
- If two memories genuinely conflict on the same attribute, state the better-supported value (the
  more specific memory, or the one with the higher match score) and mention the other in one short
  sentence. Do not present both as equally likely.

If no evidence section is supplied, answer normally, but never imply that you remember earlier
conversations."""

# Ollama structured outputs: the grammar prevents malformed or duplicate-key JSON.
EPISODE_SCHEMA = {
    "type": "object",
    "properties": {"episodes": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "event_type": {"type": "string", "enum": list(get_args(EventType))},
            "event_time": {"type": ["string", "null"]},
            "summary": {"type": "string"},
            "participants": {"type": "array", "items": {"type": "string"}},
            "facts": {"type": "array", "items": {"type": "string"}},
            "outcome": {"type": ["string", "null"]},
            "source_message_ids": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "event_type", "event_time", "summary", "participants",
                     "facts", "outcome", "source_message_ids"],
        "additionalProperties": False,
    }}},
    "required": ["episodes"],
    "additionalProperties": False,
}
DECISION_SCHEMA = {
    "type": "object",
    "properties": {"needs_memory": {"type": "boolean"}, "search_query": {"type": "string"}},
    "required": ["needs_memory", "search_query"],
    "additionalProperties": False,
}


class MemoryEngineError(Exception):
    """Base error for explicit, user-visible failures."""


class OllamaError(MemoryEngineError):
    pass


class EmbeddingMismatch(MemoryEngineError):
    pass


class ExtractionError(MemoryEngineError):
    pass


@dataclass(frozen=True)
class Settings:
    ollama_base_url: str = "http://127.0.0.1:11434"
    chat_model: str = "qwen3.5:9b"
    embed_model: str = "embeddinggemma"
    database_path: str = "./memory.db"
    top_k: int = 4
    min_similarity: float = 0.30

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", cls.ollama_base_url).rstrip("/"),
            chat_model=os.getenv("OLLAMA_CHAT_MODEL", cls.chat_model),
            embed_model=os.getenv("OLLAMA_EMBED_MODEL", cls.embed_model),
            database_path=os.getenv("DATABASE_PATH", cls.database_path),
            top_k=int(os.getenv("MEMORY_TOP_K", "4")),
            min_similarity=float(os.getenv("MEMORY_MIN_SIMILARITY", "0.30")),
        )


class EpisodeCandidate(BaseModel):
    """What the LLM is allowed to produce. Python adds all IDs and timestamps."""

    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=3, max_length=200)
    event_type: EventType
    event_time: Optional[str] = None
    summary: str = Field(min_length=3)
    participants: list[str] = Field(default_factory=list)
    facts: list[str]
    outcome: Optional[str] = None
    source_message_ids: list[str]

    @field_validator("title", "summary", "event_time", "outcome", mode="before")
    @classmethod
    def _clean_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("participants", "facts", "source_message_ids", mode="before")
    @classmethod
    def _clean_list(cls, value: Any) -> Any:
        if not isinstance(value, list):
            raise ValueError("must be a list")
        return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))

    @field_validator("participants")
    @classmethod
    def _participants_allowed_empty(cls, value: list[str]) -> list[str]:
        return value

    @field_validator("facts", "source_message_ids")
    @classmethod
    def _list_not_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("must contain at least one item")
        return value


class Episode(EpisodeCandidate):
    episode_id: str
    created_at: str
    source_conversation_id: str


class MemoryDecision(BaseModel):
    needs_memory: bool
    search_query: str = ""


@dataclass
class RetrievalResult:
    query: str
    matches: list[dict[str, Any]]
    evidence: str
    embedding_model: str
    query_dim: int
    candidates: int


@dataclass
class OllamaClient:
    """Thin local client. Errors are raised, never redirected to a cloud service."""

    settings: Settings
    _client: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = ollama.Client(host=self.settings.ollama_base_url, timeout=600)

    def chat(self, messages: list[dict[str, str]], *, json_mode: bool = False,
             temperature: float = 0.2, schema: Optional[dict] = None) -> str:
        try:
            options: dict[str, Any] = {"temperature": temperature, "num_ctx": 8192}
            if temperature <= 0.0:
                # Ollama still samples at temperature 0. With top_k=1 the extraction is greedy and
                # reproducible: the same conversation yields the same episodes on every run, which a
                # benchmark and a demo both need.
                options["top_k"] = 1
            response = self._client.chat(
                model=self.settings.chat_model,
                messages=messages,
                format=schema or ("json" if json_mode else None),
                think=False,
                options=options,
            )
        except Exception as exc:  # connection refused, missing model, timeout
            raise OllamaError(
                f"Ollama chat failed ({self.settings.ollama_base_url}, model "
                f"{self.settings.chat_model}). Is Ollama running and the model pulled? {exc}"
            ) from exc
        content = response.message.content or ""
        if not content.strip():
            raise OllamaError("Ollama returned an empty chat response.")
        return content

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = self._client.embed(
                model=self.settings.embed_model, input=texts, truncate=True
            )
        except Exception as exc:
            raise OllamaError(
                f"Ollama embedding failed (model {self.settings.embed_model}). "
                f"Is Ollama running and the model pulled? {exc}"
            ) from exc
        vectors = [list(map(float, vector)) for vector in response.embeddings]
        if len(vectors) != len(texts) or not all(vectors):
            raise OllamaError("Ollama returned an unexpected embedding response.")
        return vectors


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse JSON, tolerating an occasional markdown fence around it."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        cleaned = cleaned[4:] if cleaned.lstrip().startswith("json") else cleaned
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ExtractionError(f"Model did not return a JSON object: {text[:200]}")
    try:
        value = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"Invalid JSON from model: {exc}") from exc
    if not isinstance(value, dict):
        raise ExtractionError("Model JSON must be an object.")
    return value


def validate_source_ids(source_ids: list[str], allowed_ids: set[str]) -> None:
    unknown = sorted(set(source_ids) - allowed_ids)
    if unknown:
        raise ExtractionError(f"source_message_ids not in transcript: {unknown}")
    if not source_ids:
        raise ExtractionError("source_message_ids must not be empty")


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denominator) if denominator else 0.0


# Lifecycle tuning. These are deliberately conservative: memory should be merged or replaced
# only when the two episodes clearly describe the same thing.
DUPLICATE_SIMILARITY = 0.90
SUPERSEDE_SIMILARITY = 0.72

# A fact must share at least this share of its content words with the messages it cites. This is a
# cheap lexical backstop against invented memories: an extracted fact that the source never
# mentions (for example a health detail the assistant guessed) is rejected.
GROUNDING_MIN_OVERLAP = 0.35
LINK_SIMILARITY = 0.45

CANCEL_MARKERS = ("cancel", "call off", "called off", "no longer", "will not", "won't",
                  "dropped", "abandoned", "scrapped")

# Types that can be replaced by a newer statement about the same subject. `outcome` is excluded:
# an outcome completes or closes work, it does not replace a value.
REPLACEABLE_TYPES = {"event", "decision", "task", "project_update", "preference", "goal"}

TRIVIAL_PHRASES = {
    "hi", "hello", "hey", "thanks", "thank you", "ok", "okay", "yes", "no",
    "sure", "bye", "goodbye", "cool", "great", "nice", "got it", "understood",
}


def is_trivial_turn(messages: list[dict[str, str]]) -> bool:
    """A fast path: greetings and acknowledgements never need memory and never produce it."""
    user_texts = [m["content"].strip().lower().rstrip("!.?") for m in messages if m["role"] == "user"]
    if not user_texts:
        return False
    return all(text in TRIVIAL_PHRASES for text in user_texts)


TITLE_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "at", "by", "with",
    "update", "note", "user", "team",
}

# Deterministic backstop for the extraction prompt. A memory whose title is small talk is not a
# memory, however the model labelled it.
SMALL_TALK_TITLES = (
    "weather", "greeting", "small talk", "pleasantr", "how's it going", "how is it going",
    "nice day", "good morning", "good evening", "thanks for", "thank you", "feeling",
    "chit chat", "chit-chat", "mood",
)


def is_small_talk(episode: "Episode") -> bool:
    title = episode.title.lower()
    return any(marker in title for marker in SMALL_TALK_TITLES)


def tokens(text: str) -> set[str]:
    return {word for word in "".join(c if c.isalnum() else " " for c in text.lower()).split()
            if word not in TITLE_STOPWORDS}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def grounding_words(text: str) -> set[str]:
    """Content words with a very light stem, so 'prefers' and 'prefer' count as the same word."""
    words = set()
    for word in tokens(text):
        for suffix in ("ing", "ed", "s"):
            if len(word) > 4 and word.endswith(suffix):
                word = word[:-len(suffix)]
                break
        words.add(word)
    return words


def ungrounded_fact(facts: list[str], source_text: str) -> Optional[str]:
    """Return the first fact whose content words barely appear in its cited source messages."""
    source_words = grounding_words(source_text)
    for fact in facts:
        words = grounding_words(fact)
        if not words:
            continue
        overlap = len(words & source_words) / len(words)
        if overlap < GROUNDING_MIN_OVERLAP:
            return fact
    return None


# Extraction context limit. Ollama truncates prompts above the model context, which silently loses
# facts from long messages. Messages are split and batched below this size instead.
MAX_EXTRACTION_CHARS = 6000


def split_long_messages(messages: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    """Split an oversized message into windows that keep the same message_id for provenance."""
    pieces: list[dict[str, str]] = []
    for message in messages:
        content = message["content"]
        if len(content) <= limit:
            pieces.append(message)
            continue
        for start in range(0, len(content), limit):
            pieces.append({**message, "content": content[start:start + limit]})
    return pieces


def batch_messages(messages: list[dict[str, str]], limit: int) -> list[list[dict[str, str]]]:
    """Group message pieces into batches that each fit the extraction prompt."""
    batches: list[list[dict[str, str]]] = []
    current: list[dict[str, str]] = []
    size = 0
    for message in messages:
        length = len(message["content"]) + 120
        if current and size + length > limit:
            batches.append(current)
            current, size = [], 0
        current.append(message)
        size += length
    if current:
        batches.append(current)
    return batches


def format_batch(batch: list[dict[str, str]], part: int, total: int,
                 new_ids: set[str], incremental: bool) -> str:
    lines = []
    for message in batch:
        marker = "[NEW] " if incremental and message["message_id"] in new_ids else ""
        lines.append(
            f"{marker}[{message['created_at']}] {message['role']} "
            f"(message_id={message['message_id']}):\n{message['content']}"
        )
    header = f"This is part {part} of {total} of the conversation.\n\n" if total > 1 else ""
    return header + "\n\n".join(lines)


def numbers_in(text: str) -> set[str]:
    """Digit tokens, used to tell 'November 6' from 'November 13'."""
    return set("".join(c if c.isdigit() else " " for c in text).split())


def episode_text(episode: Episode) -> str:
    return " ".join([episode.title, episode.summary, *episode.facts, episode.outcome or ""])


def is_same_memory(a: Episode, a_vector: list[float],
                   b: Episode, b_vector: list[float]) -> bool:
    """True when two episodes carry the same information (not merely a related topic)."""
    if a.event_type != b.event_type:
        return False
    text_a, text_b = episode_text(a), episode_text(b)
    # A changed date or number is new information, not a duplicate.
    if numbers_in(text_a) != numbers_in(text_b):
        return False
    if cosine(np.asarray(a_vector), np.asarray(b_vector)) >= DUPLICATE_SIMILARITY:
        return True
    return jaccard(tokens(a.title), tokens(b.title)) >= 0.5 and set(a.facts) == set(b.facts)


def is_redundant(a: Episode, a_vector: list[float], b: Episode, b_vector: list[float]) -> bool:
    """Within one extraction batch: one memory per event is enough."""
    return is_same_memory(a, a_vector, b, b_vector)


def information_score(episode: Episode | dict[str, Any]) -> tuple[int, int, int]:
    """Prefer the version that carries more dates and facts when two memories are merged."""
    if isinstance(episode, dict):
        text = " ".join([episode.get("title", ""), episode.get("summary", ""),
                         *episode.get("facts", []), episode.get("outcome") or ""])
        facts = episode.get("facts", [])
    else:
        text, facts = episode_text(episode), episode.facts
    return (len(numbers_in(text)), len(facts), len(text))


def participants_overlap(left: list[str], right: list[str]) -> bool:
    """Both empty or unknown participants are allowed; otherwise one name must match."""
    if not left or not right:
        return True
    return bool({name.lower() for name in left} & {name.lower() for name in right})


def _row_text(row: dict[str, Any]) -> str:
    return " ".join([row["title"], row["summary"], *row["facts"], row["outcome"] or ""])


def same_numbers(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """A memory that omits a date is a weaker version of one that states it."""
    return numbers_compatible(_row_text(left), _row_text(right))


def numbers_compatible(left_text: str, right_text: str) -> bool:
    left_numbers, right_numbers = numbers_in(left_text), numbers_in(right_text)
    if not left_numbers or not right_numbers:
        return True
    return left_numbers == right_numbers


def embedding_text(episode: Episode) -> str:
    parts = [
        episode.title,
        f"Type: {episode.event_type}",
        f"Summary: {episode.summary}",
        f"Participants: {', '.join(episode.participants) or 'unknown'}",
        f"Facts: {'; '.join(episode.facts)}",
        f"Outcome: {episode.outcome or 'unknown'}",
    ]
    return "\n".join(parts)[:6000]


def format_history(history: list[dict[str, str]], limit: int = 6) -> str:
    recent = history[-limit:]
    return "\n".join(f"{m['role']}: {m['content']}" for m in recent) or "(no current-session messages)"


def _format_evidence(matches: list[dict[str, Any]]) -> str:
    if not matches:
        return "No episodic memories matched this query. The result set is empty."
    blocks = []
    for match in matches:
        ep = match["episode"]
        blocks.append(
            f"[EPISODE {ep['episode_id']}]\n"
            f"Title: {ep['title']}\n"
            f"Event type: {ep['event_type']}\n"
            f"Event time: {ep['event_time'] or 'unknown'}\n"
            f"Participants: {', '.join(ep['participants']) or 'unknown'}\n"
            f"Summary: {ep['summary']}\n"
            f"Facts: {'; '.join(ep['facts'])}\n"
            f"Outcome: {ep['outcome'] or 'unknown'}\n"
            f"Source conversation: {ep['source_conversation_id']}\n"
            f"Source message IDs: {', '.join(ep['source_message_ids'])}\n"
            f"Similarity: {match['score']:.4f}"
        )
    return "\n\n".join(blocks)


DEMO_CONVERSATION_ID = "conv-demo-sync-2025-10"
DEMO_MESSAGES: list[tuple[str, str, str, str]] = [
    ("demo-msg-001", "2025-10-03T09:00:00+00:00", "user",
     "Project sync notes from October 3, 2025. We're building a local prototype for a single user, "
     "offline-first. The team decided to use SQLite for storage because it fits that constraint."),
    ("demo-msg-002", "2025-10-03T09:01:00+00:00", "assistant",
     "Recorded: the team chose SQLite for the local prototype because it is single-user and offline-first."),
    ("demo-msg-003", "2025-10-03T09:05:00+00:00", "user",
     "Mira was assigned to finish the episode schema by October 18, 2025. It is a commitment and is not done yet."),
    ("demo-msg-004", "2025-10-03T09:06:00+00:00", "assistant",
     "Understood. Mira owns the episode schema, with a target date of October 18, 2025."),
    ("demo-msg-005", "2025-10-07T14:00:00+00:00", "user",
     "Status on October 7, 2025: Asha completed the deletion tests today."),
    ("demo-msg-006", "2025-10-07T14:01:00+00:00", "assistant",
     "Asha completed deletion testing on October 7, 2025."),
    ("demo-msg-007", "2025-10-07T14:05:00+00:00", "user",
     "Ravi's retrieval experiment is still incomplete as of October 7, 2025. The test incorrectly used "
     "the chat model for embeddings instead of embeddinggemma, so the run is blocked."),
    ("demo-msg-008", "2025-10-07T14:06:00+00:00", "assistant",
     "Noted: Ravi's retrieval experiment is incomplete because the test used the chat model for "
     "embeddings rather than embeddinggemma."),
    ("demo-msg-009", "2025-10-07T14:10:00+00:00", "user",
     "We have not established a numerical retrieval-accuracy result yet. Do not record any accuracy number."),
    ("demo-msg-010", "2025-10-07T14:11:00+00:00", "assistant",
     "Understood. No numerical retrieval-accuracy result has been established."),
]


class MemoryEngine:
    def __init__(self, settings: Optional[Settings] = None, llm: Any = None) -> None:
        self.settings = settings or Settings.from_env()
        self.llm = llm or OllamaClient(self.settings)
        self._init_db()

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.settings.database_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._db() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    ended_at TEXT,
                    status TEXT NOT NULL DEFAULT 'active'
                );
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS episodes (
                    episode_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    event_time TEXT,
                    title TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    participants TEXT NOT NULL,
                    facts TEXT NOT NULL,
                    outcome TEXT,
                    source_conversation_id TEXT NOT NULL,
                    source_message_ids TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    embedding TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    embedding_dim INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_episodes_conversation
                    ON episodes(source_conversation_id);
                CREATE TABLE IF NOT EXISTS turn_traces (
                    trace_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    user_message_id TEXT,
                    assistant_message_id TEXT,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    details TEXT NOT NULL,
                    latency_ms INTEGER,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_turn_traces_conversation
                    ON turn_traces(conversation_id, created_at);
                CREATE TABLE IF NOT EXISTS memory_events (
                    event_id TEXT PRIMARY KEY,
                    episode_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    detail TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_events_episode
                    ON memory_events(episode_id, created_at);
                CREATE TABLE IF NOT EXISTS formed_messages (
                    message_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    formed_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_formed_messages_conversation
                    ON formed_messages(conversation_id);
                """
            )
            # Additive migration so an existing memory.db keeps working.
            existing = {row["name"] for row in conn.execute("PRAGMA table_info(episodes)")}
            for column, ddl in (
                ("superseded_by", "TEXT"),
                ("updated_at", "TEXT"),
                ("change_reason", "TEXT"),
            ):
                if column not in existing:
                    conn.execute(f"ALTER TABLE episodes ADD COLUMN {column} {ddl}")

    # ---------- conversations and messages ----------

    def add_message(self, conversation_id: str, role: str, content: str,
                    created_at: Optional[str] = None, message_id: Optional[str] = None) -> dict[str, str]:
        message_id = message_id or f"msg_{uuid.uuid4().hex[:12]}"
        created_at = created_at or utc_now()
        with self._db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO conversations(conversation_id, created_at, status) VALUES (?, ?, 'active')",
                (conversation_id, created_at),
            )
            conn.execute(
                "INSERT INTO messages(message_id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (message_id, conversation_id, role, content, created_at),
            )
        return {"message_id": message_id, "conversation_id": conversation_id,
                "role": role, "content": content, "created_at": created_at}

    def get_messages(self, conversation_id: str) -> list[dict[str, str]]:
        with self._db() as conn:
            rows = conn.execute(
                "SELECT message_id, conversation_id, role, content, created_at FROM messages "
                "WHERE conversation_id = ? ORDER BY created_at, rowid",
                (conversation_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def end_conversation(self, conversation_id: str) -> None:
        with self._db() as conn:
            conn.execute(
                "UPDATE conversations SET ended_at = ?, status = 'ended' WHERE conversation_id = ?",
                (utc_now(), conversation_id),
            )

    # ---------- turn traces ----------

    def save_trace(self, conversation_id: str, question: str, answer: str,
                   details: dict[str, Any], *, user_message_id: Optional[str] = None,
                   assistant_message_id: Optional[str] = None,
                   latency_ms: Optional[int] = None) -> str:
        """Persist one turn's retrieval/writer details so they survive a restart."""
        trace_id = f"tr_{uuid.uuid4().hex[:12]}"
        with self._db() as conn:
            conn.execute(
                "INSERT INTO turn_traces(trace_id, conversation_id, user_message_id, "
                "assistant_message_id, question, answer, details, latency_ms, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (trace_id, conversation_id, user_message_id, assistant_message_id, question,
                 answer, json.dumps(details), latency_ms, utc_now()),
            )
        return trace_id

    def list_traces(self, conversation_id: Optional[str] = None, limit: int = 10) -> list[dict[str, Any]]:
        query = "SELECT * FROM turn_traces"
        params: list[Any] = []
        if conversation_id is not None:
            query += " WHERE conversation_id = ?"
            params.append(conversation_id)
        query += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
        params.append(limit)
        with self._db() as conn:
            rows = conn.execute(query, params).fetchall()
        traces = []
        for row in rows:
            trace = dict(row)
            trace["details"] = json.loads(trace["details"])
            traces.append(trace)
        return traces

    # ---------- episode formation ----------

    def _formed_message_ids(self, conversation_id: str) -> set[str]:
        with self._db() as conn:
            rows = conn.execute(
                "SELECT message_id FROM formed_messages WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchall()
        return {row["message_id"] for row in rows}

    def _mark_formed(self, conversation_id: str, message_ids: list[str]) -> None:
        """Remember which messages were already sent to extraction, so each turn is processed once."""
        now = utc_now()
        with self._db() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO formed_messages(message_id, conversation_id, formed_at) "
                "VALUES (?, ?, ?)",
                [(message_id, conversation_id, now) for message_id in message_ids],
            )

    def form_memories(self, conversation_id: str, *, incremental: bool = False,
                      end: bool = True) -> tuple[list[dict[str, Any]], list[str]]:
        """Ask the LLM for episodes, validate them, embed, and store them automatically.

        `incremental=True` extracts only messages written since the last save, which is how the app
        writes memory after every reply. `end=False` keeps the conversation open for the next turn.
        """
        messages = self.get_messages(conversation_id)
        if not messages:
            return [], ["The conversation has no messages."]

        if incremental:
            already_formed = self._formed_message_ids(conversation_id)
            new_messages = [m for m in messages if m["message_id"] not in already_formed]
            if not new_messages:
                if end:
                    self.end_conversation(conversation_id)
                return [], []
        else:
            new_messages = messages

        new_ids = {m["message_id"] for m in new_messages}
        if incremental and is_trivial_turn(new_messages):
            self._mark_formed(conversation_id, list(new_ids))
            if end:
                self.end_conversation(conversation_id)
            return [], []

        context: list[dict[str, str]] = []
        if incremental:
            older = [m for m in messages if m["message_id"] not in new_ids]
            context = older[-2:]

        instructions = (
            "Extract durable episodic memories from the [NEW] messages only. Use the [CONTEXT] "
            "and unmarked messages only to resolve names, dates, and references. Every "
            "source_message_ids value must come from a [NEW] message. Only user messages can be "
            "sources; assistant messages are context only."
            if incremental else
            "Extract the durable episodic memories now."
        )
        known_block = ""
        if incremental:
            known = self.list_episodes()
            if known:
                known_block = (
                    "Memories already saved (do not extract them again unless a [NEW] message "
                    "changes them):\n"
                    + "\n".join(f"- {row['title']} ({row['event_type']})" for row in known)
                    + "\n\n"
                )

        pieces = split_long_messages(new_messages, MAX_EXTRACTION_CHARS)
        batches = batch_messages(pieces, MAX_EXTRACTION_CHARS)
        items: list[Any] = []
        for part, batch in enumerate(batches, start=1):
            transcript = format_batch(batch, part, len(batches), new_ids, incremental)
            if context:
                context_text = "\n\n".join(
                    f"[{m['created_at']}] {m['role']} (message_id={m['message_id']}):\n{m['content']}"
                    for m in context
                )
                transcript = f"[CONTEXT]\n{context_text}\n\n[TRANSCRIPT]\n{transcript}"
            prompt = (
                f"Conversation transcript:\n\n{transcript}\n\n{known_block}{instructions} "
                "Return JSON only."
            )
            try:
                raw = self.llm.chat(
                    [{"role": "system", "content": EXTRACTION_SYSTEM},
                     {"role": "user", "content": prompt}],
                    json_mode=True, temperature=0.0, schema=EPISODE_SCHEMA,
                )
                payload = parse_json_object(raw)
                batch_items = payload.get("episodes")
                if not isinstance(batch_items, list):
                    raise ExtractionError('Missing "episodes" list in extraction output.')
                items.extend(batch_items)
            except MemoryEngineError as exc:
                return [], [f"Memory extraction failed (part {part}): {exc}"]
            except Exception as exc:
                return [], [f"Memory extraction failed (part {part}): {exc}"]

        allowed_ids = new_ids
        candidates: list[Episode] = []
        errors: list[str] = []
        now = utc_now()
        user_ids = {m["message_id"] for m in new_messages if m["role"] == "user"}

        for index, item in enumerate(items, start=1):
            try:
                candidate = EpisodeCandidate.model_validate(item)
                validate_source_ids(candidate.source_message_ids, allowed_ids)
                if user_ids and not (set(candidate.source_message_ids) & user_ids):
                    raise ValueError(
                        "source_message_ids must include at least one user message; "
                        "assistant messages are not sources."
                    )
            except Exception as exc:
                errors.append(f"Episode {index} rejected: {exc}")
                continue
            episode = Episode(
                **candidate.model_dump(),
                episode_id=f"ep_{uuid.uuid4().hex[:12]}",
                created_at=now,
                source_conversation_id=conversation_id,
            )
            if is_small_talk(episode):
                errors.append(f"Episode {episode.episode_id} rejected: small talk ({episode.title}).")
                continue
            cited = {m["message_id"]: m["content"] for m in new_messages
                     if m["message_id"] in episode.source_message_ids and m["role"] == "user"}
            bad_fact = ungrounded_fact(episode.facts, " ".join(cited.values()))
            if bad_fact:
                errors.append(
                    f"Episode {episode.episode_id} rejected: fact not supported by its source "
                    f"messages ({bad_fact[:90]})."
                )
                continue
            candidates.append(episode)

        if not candidates:
            self._mark_formed(conversation_id, list(new_ids))
            if end:
                self.end_conversation(conversation_id)
            return [], errors

        try:
            vectors = self.llm.embed([embedding_text(episode) for episode in candidates])
        except Exception as exc:
            return [], errors + [f"Embedding failed; nothing stored: {exc}"]

        stored: list[dict[str, Any]] = []
        accepted: list[tuple[Episode, list[float]]] = []
        for episode, vector in zip(candidates, vectors):
            if len(vector) != len(vectors[0]):
                errors.append(f"Episode {episode.episode_id} rejected: inconsistent embedding dimensions.")
                continue
            duplicate = next(
                (previous for previous, previous_vector in accepted
                 if is_redundant(episode, vector, previous, previous_vector)),
                None,
            )
            if duplicate:
                errors.append(
                    f"Episode {episode.episode_id} merged into {duplicate.episode_id}: same event."
                )
                continue
            existing = self._find_existing_duplicate(episode, vector)
            if existing:
                errors.append(
                    f"Episode {episode.episode_id} not stored: already remembered as "
                    f"{existing['episode_id']}."
                )
                self.log_event(existing["episode_id"], "duplicate_seen", episode.title)
                continue
            accepted.append((episode, vector))
            self._insert_episode(episode, vector)
            change = self._apply_lifecycle(episode, vector)
            stored.append({**episode.model_dump(), "status": "active", "change": change})

        # Merging is part of the write path, not a button the user has to remember.
        merged = self.consolidate_duplicates()
        if merged:
            errors.append("Cleanup: merged " + ", ".join(item["merged"] for item in merged)
                          + " into an existing memory.")
        self._mark_formed(conversation_id, list(new_ids))
        if end:
            self.end_conversation(conversation_id)
        return stored, errors

    def _find_existing_duplicate(self, episode: Episode,
                                 vector: list[float]) -> Optional[dict[str, Any]]:
        """Same event already in the archive? Do not store it twice."""
        text = episode_text(episode)
        for row in self.list_episodes(include_embeddings=True):
            if row["event_type"] != episode.event_type:
                continue
            row_text = " ".join([row["title"], row["summary"], *row["facts"],
                                 row["outcome"] or ""])
            if not numbers_compatible(text, row_text):
                continue
            if information_score(episode) > information_score(row):
                # The new version carries more information; keep it and let lifecycle replace the old one.
                continue
            score = cosine(np.asarray(vector), np.asarray(row["embedding"]))
            if score >= DUPLICATE_SIMILARITY:
                return row
        return None

    def _apply_lifecycle(self, episode: Episode, vector: list[float]) -> Optional[dict[str, Any]]:
        """Update older memories: completed, cancelled, or replaced by newer information."""
        text = episode_text(episode).lower()
        cancelled = any(marker in text for marker in CANCEL_MARKERS)
        best: Optional[tuple[float, dict[str, Any]]] = None
        for row in self.list_episodes(include_embeddings=True):
            if row["episode_id"] == episode.episode_id or row["status"] != "active":
                continue
            if not participants_overlap(episode.participants, row["participants"]):
                continue
            score = cosine(np.asarray(vector), np.asarray(row["embedding"]))
            if score >= LINK_SIMILARITY and (best is None or score > best[0]):
                best = (score, row)
        if best is None:
            return None

        score, old = best
        if episode.event_type == "outcome" and old["event_type"] in ("task", "goal"):
            self._change_state(old["episode_id"], "done", episode.episode_id,
                               f"completed by {episode.episode_id} (similarity {score:.2f})")
            return {"action": "completed", "episode_id": old["episode_id"]}
        if cancelled and old["event_type"] in ("task", "goal"):
            self._change_state(old["episode_id"], "cancelled", episode.episode_id,
                               f"cancelled by {episode.episode_id} (similarity {score:.2f})")
            return {"action": "cancelled", "episode_id": old["episode_id"]}
        if (old["event_type"] in REPLACEABLE_TYPES and episode.event_type in REPLACEABLE_TYPES
                and score >= SUPERSEDE_SIMILARITY):
            self._change_state(old["episode_id"], "superseded", episode.episode_id,
                               f"replaced by {episode.episode_id} (similarity {score:.2f})")
            return {"action": "superseded", "episode_id": old["episode_id"]}
        return None

    def _change_state(self, episode_id: str, status: str, superseded_by: Optional[str] = None,
                      reason: Optional[str] = None) -> None:
        with self._db() as conn:
            conn.execute(
                "UPDATE episodes SET status = ?, superseded_by = ?, change_reason = ?, updated_at = ? "
                "WHERE episode_id = ?",
                (status, superseded_by, reason, utc_now(), episode_id),
            )
        self.log_event(episode_id, status, reason)

    # ---------- audit trail ----------

    def log_event(self, episode_id: str, action: str, detail: Optional[str] = None) -> None:
        with self._db() as conn:
            conn.execute(
                "INSERT INTO memory_events(event_id, episode_id, action, detail, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (f"ev_{uuid.uuid4().hex[:12]}", episode_id, action, detail, utc_now()),
            )

    def list_events(self, episode_id: Optional[str] = None,
                    limit: int = 100) -> list[dict[str, Any]]:
        query = "SELECT * FROM memory_events"
        params: list[Any] = []
        if episode_id is not None:
            query += " WHERE episode_id = ?"
            params.append(episode_id)
        query += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
        params.append(limit)
        with self._db() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    # ---------- consolidation ----------

    def consolidate_duplicates(self) -> list[dict[str, Any]]:
        """Merge memories that describe the same event. Keeps the richer one."""
        rows = self.list_episodes(include_embeddings=True)
        merged: list[dict[str, Any]] = []
        removed: set[str] = set()
        for index, first in enumerate(rows):
            if first["episode_id"] in removed:
                continue
            for second in rows[index + 1:]:
                if second["episode_id"] in removed:
                    continue
                if first["event_type"] != second["event_type"]:
                    continue
                if not participants_overlap(first["participants"], second["participants"]):
                    continue
                if not same_numbers(first, second):
                    continue
                score = cosine(np.asarray(first["embedding"]), np.asarray(second["embedding"]))
                titles = jaccard(tokens(first["title"]), tokens(second["title"]))
                if score >= DUPLICATE_SIMILARITY or titles >= 0.45:
                    keep, drop = ((first, second) if information_score(first) >= information_score(second)
                                  else (second, first))
                    combined = list(dict.fromkeys([*keep["facts"], *drop["facts"]]))
                    with self._db() as conn:
                        conn.execute(
                            "UPDATE episodes SET facts = ?, updated_at = ? WHERE episode_id = ?",
                            (json.dumps(combined), utc_now(), keep["episode_id"]),
                        )
                    self._change_state(drop["episode_id"], "superseded", keep["episode_id"],
                                       f"merged duplicate of {keep['episode_id']}")
                    removed.add(drop["episode_id"])
                    merged.append({"kept": keep["episode_id"], "merged": drop["episode_id"],
                                   "title": keep["title"]})
                    break
        return merged

    def _insert_episode(self, episode: Episode, vector: list[float]) -> None:
        with self._db() as conn:
            conn.execute(
                "INSERT INTO episodes(episode_id, created_at, updated_at, event_time, title, event_type, "
                "summary, participants, facts, outcome, source_conversation_id, source_message_ids, "
                "status, embedding, embedding_model, embedding_dim) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    episode.episode_id, episode.created_at, episode.created_at, episode.event_time,
                    episode.title, episode.event_type, episode.summary,
                    json.dumps(episode.participants), json.dumps(episode.facts), episode.outcome,
                    episode.source_conversation_id, json.dumps(episode.source_message_ids),
                    "active", json.dumps(vector), self.settings.embed_model, len(vector),
                ),
            )
        self.log_event(episode.episode_id, "created", episode.title)

    # ---------- archive ----------

    def list_episodes(self, include_embeddings: bool = False,
                      include_inactive: bool = False) -> list[dict[str, Any]]:
        columns = ("episode_id, created_at, updated_at, event_time, title, event_type, summary, "
                   "participants, facts, outcome, source_conversation_id, source_message_ids, status, "
                   "superseded_by, change_reason, embedding_model, embedding_dim")
        if include_embeddings:
            columns += ", embedding"
        where = "" if include_inactive else " WHERE status IN ('active', 'done')"
        with self._db() as conn:
            rows = conn.execute(
                f"SELECT {columns} FROM episodes{where} ORDER BY created_at DESC, rowid DESC"
            ).fetchall()
        episodes = []
        for row in rows:
            episode = dict(row)
            episode["participants"] = json.loads(episode["participants"])
            episode["facts"] = json.loads(episode["facts"])
            episode["source_message_ids"] = json.loads(episode["source_message_ids"])
            if include_embeddings:
                episode["embedding"] = json.loads(episode["embedding"])
            episodes.append(episode)
        return episodes

    def delete_episode(self, episode_id: str) -> bool:
        with self._db() as conn:
            row = conn.execute("SELECT title FROM episodes WHERE episode_id = ?",
                               (episode_id,)).fetchone()
            cursor = conn.execute("DELETE FROM episodes WHERE episode_id = ?", (episode_id,))
        if row is not None:
            self.log_event(episode_id, "deleted", row["title"])
        return cursor.rowcount > 0

    # ---------- retrieval ----------

    def retrieve(self, query: str, top_k: Optional[int] = None,
                 min_similarity: Optional[float] = None) -> RetrievalResult:
        query = query.strip()
        if not query:
            raise MemoryEngineError("A retrieval query is required.")
        query_vector = np.asarray(self.llm.embed([query])[0], dtype=np.float64)
        rows = self.list_episodes(include_embeddings=True)
        candidates = []
        for row in rows:
            if row["embedding_model"] != self.settings.embed_model:
                raise EmbeddingMismatch(
                    f"Stored episode {row['episode_id']} uses embedding model "
                    f"'{row['embedding_model']}', but queries use '{self.settings.embed_model}'."
                )
            stored = np.asarray(row["embedding"], dtype=np.float64)
            if stored.shape != query_vector.shape:
                raise EmbeddingMismatch(
                    f"Stored episode {row['episode_id']} has dimension {stored.size}; "
                    f"query dimension is {query_vector.size}."
                )
            score = cosine(stored, query_vector)
            candidates.append((score, row))
        threshold = self.settings.min_similarity if min_similarity is None else min_similarity
        limit = self.settings.top_k if top_k is None else top_k
        candidates.sort(key=lambda pair: pair[0], reverse=True)
        matches = [
            {
                "episode": {key: value for key, value in row.items() if key != "embedding"},
                "score": score,
            }
            for score, row in candidates
            if score >= threshold
        ][:limit]
        return RetrievalResult(
            query=query, matches=matches, evidence=_format_evidence(matches),
            embedding_model=self.settings.embed_model, query_dim=int(query_vector.size),
            candidates=len(rows),
        )

    # ---------- decision, answering, one turn ----------

    def decide(self, question: str, history: list[dict[str, str]]) -> MemoryDecision:
        catalog_lines = []
        for episode in self.list_episodes()[:30]:
            facts = " | ".join(episode["facts"][:3])
            catalog_lines.append(f"- {episode['title']} ({episode['event_type']}): {facts}")
        catalog = "\n".join(catalog_lines) or "(archive is empty)"
        prompt = (
            f"Archive contents (titles and key facts, for relevance context):\n{catalog}\n\n"
            f"Current-session history:\n{format_history(history)}\n\n"
            f"New user message:\n{question}\n\nReturn the JSON decision only."
        )
        try:
            raw = self.llm.chat(
                [{"role": "system", "content": DECISION_SYSTEM}, {"role": "user", "content": prompt}],
                json_mode=True, temperature=0.0, schema=DECISION_SCHEMA,
            )
            decision = MemoryDecision.model_validate(parse_json_object(raw))
        except Exception:
            # Searching is the safe fallback; retrieval itself still has a similarity threshold.
            return MemoryDecision(needs_memory=True, search_query=question)
        if decision.needs_memory and not decision.search_query.strip():
            decision.search_query = question
        return decision

    def answer(self, question: str, history: list[dict[str, str]],
               retrieval: Optional[RetrievalResult] = None, memory_disabled: bool = False) -> str:
        messages: list[dict[str, str]] = [{"role": "system", "content": ANSWER_SYSTEM}]
        # Conversation context, not evidence: earlier assistant replies may restate a memory the
        # user has since deleted, so they are never sent to the answer model. Only user messages
        # (what actually happened in this conversation) plus retrieved episodes are allowed.
        history = [message for message in history if message["role"] != "assistant"]
        if memory_disabled:
            messages.append({
                "role": "system",
                "content": "Memory retrieval is disabled for this turn; the archive is unavailable. "
                           "Do not claim to have searched it, and do not claim that no memories exist. "
                           "If the question depends on earlier conversations, say you cannot check the "
                           "memory archive because retrieval is turned off.",
            })
        if retrieval is not None:
            messages.append({
                "role": "system",
                "content": "RETRIEVED EPISODIC MEMORY (the only evidence about earlier conversations):\n\n"
                           + retrieval.evidence,
            })
        messages.extend(history[-8:])
        messages.append({"role": "user", "content": question})
        return self.llm.chat(messages, temperature=0.2)

    def handle_turn(self, question: str, history: list[dict[str, str]],
                    retrieval_enabled: bool = True) -> dict[str, Any]:
        details: dict[str, Any] = {
            "memory_enabled": retrieval_enabled,
            "searched": False,
            "needs_memory": None,
            "search_query": None,
            "results": [],
            "evidence": None,
            "reason": "",
        }
        if not retrieval_enabled:
            details["reason"] = "Memory retrieval was disabled. No memories were supplied."
            return {"answer": self.answer(question, history, memory_disabled=True), "details": details}

        if is_trivial_turn([{"role": "user", "content": question}]):
            details["reason"] = "Trivial turn; no memory needed or produced."
            return {"answer": self.answer(question, history), "details": details}

        decision = self.decide(question, history)
        details["needs_memory"] = decision.needs_memory
        details["search_query"] = decision.search_query or None
        if not decision.needs_memory:
            details["reason"] = "The model judged that earlier-conversation memory was not needed."
            return {"answer": self.answer(question, history), "details": details}

        result = self.retrieve(decision.search_query)
        details.update({
            "searched": True,
            "reason": "Memory was searched; relevant episodes were supplied."
            if result.matches else "Memory was searched but returned an explicit empty result.",
            "results": [
                {
                    "episode_id": match["episode"]["episode_id"],
                    "title": match["episode"]["title"],
                    "score": round(match["score"], 4),
                    "source_message_ids": match["episode"]["source_message_ids"],
                }
                for match in result.matches
            ],
            "evidence": result.evidence,
            "embedding_model": result.embedding_model,
            "query_dim": result.query_dim,
            "candidates": result.candidates,
        })
        return {"answer": self.answer(question, history, result), "details": details}

    # ---------- demo ----------

    def reset_demo(self) -> None:
        with self._db() as conn:
            conn.execute("DELETE FROM episodes WHERE source_conversation_id = ?", (DEMO_CONVERSATION_ID,))
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (DEMO_CONVERSATION_ID,))
            conn.execute("DELETE FROM formed_messages WHERE conversation_id = ?", (DEMO_CONVERSATION_ID,))
            conn.execute("DELETE FROM conversations WHERE conversation_id = ?", (DEMO_CONVERSATION_ID,))

    def load_demo(self) -> tuple[list[dict[str, Any]], list[str]]:
        """Seed source messages, then use the normal extraction pipeline (never direct inserts)."""
        self.reset_demo()
        for message_id, created_at, role, content in DEMO_MESSAGES:
            self.add_message(DEMO_CONVERSATION_ID, role, content, created_at, message_id)
        return self.form_memories(DEMO_CONVERSATION_ID)


def integration_check() -> None:
    """Manual integration test against real local Ollama models. Uses a throwaway database."""
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        settings = replace(Settings.from_env(), database_path=os.path.join(directory, "integration.db"))
        engine = MemoryEngine(settings)
        print(f"Chat model: {settings.chat_model} | Embedding model: {settings.embed_model}")
        episodes, errors = engine.load_demo()
        print(f"\nExtracted {len(episodes)} episodes; {len(errors)} rejected.")
        for episode in episodes:
            print(f"- {episode['episode_id']} [{episode['event_type']}] {episode['title']}")
        for error in errors:
            print(f"  ! {error}")

        questions = [
            "Why was the retrieval experiment blocked?",
            "Who completed deletion testing, and when?",
            "What was Mira responsible for?",
            "What retrieval accuracy did the team achieve?",
        ]
        for question in questions:
            turn = engine.handle_turn(question, [], retrieval_enabled=True)
            ids = [item["episode_id"] for item in turn["details"]["results"]]
            scores = [item["score"] for item in turn["details"]["results"]]
            print(f"\nQ: {question}\nRetrieved: {list(zip(ids, scores)) or 'EMPTY'}")
            print(f"A: {turn['answer']}")


if __name__ == "__main__":
    integration_check()
