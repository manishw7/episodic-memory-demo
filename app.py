"""Single-page Streamlit UI for the episodic-memory demo."""

from __future__ import annotations

import time
import uuid
from typing import Any

import streamlit as st

from memory_engine import MemoryEngine, Settings

st.set_page_config(page_title="Episodic Memory Demo", page_icon="🧠", layout="wide")


@st.cache_resource
def get_engine() -> MemoryEngine:
    return MemoryEngine(Settings.from_env())


def fresh_session() -> None:
    st.session_state.conversation_id = f"conv_{uuid.uuid4().hex[:12]}"
    st.session_state.messages = []
    st.session_state.ended = False
    st.session_state.saved_episode_ids = []


def notice(kind: str, text: str) -> None:
    st.session_state.notice = {"kind": kind, "text": text}


engine = get_engine()
settings = engine.settings
if "conversation_id" not in st.session_state:
    fresh_session()
if "notice" not in st.session_state:
    st.session_state.notice = None

st.title("🧠 Episodic Memory")
st.caption(
    "One archive, three ways to look at it: talk to it, see how its memories connect, or "
    "travel back to any day and see what it knew then."
)
VIEWS = ["Chat", "Memory Map", "Time Machine"]
# A link like ?view=Memory+Map opens straight to one screen, which is handy for a demo.
# It only seeds the first render; clicking the switcher afterwards is not overridden.
if "view" not in st.session_state:
    requested = st.query_params.get("view")
    st.session_state.view = requested if requested in VIEWS else "Chat"
view = st.segmented_control(
    "View",
    VIEWS,
    label_visibility="collapsed",
    key="view",
) or "Chat"


# ----------------------------- sidebar -----------------------------

with st.sidebar:
    st.header("Memory controls")
    if view == "Memory Map":
        from demo_views import render_map_sidebar

        render_map_sidebar(engine)
        st.divider()

    retrieval_enabled = True
    if view == "Chat":
        st.session_state.setdefault("retrieval_enabled", True)
        retrieval_enabled = st.toggle(
            "Use memory retrieval", key="retrieval_enabled",
            help="When on, every message gets a model decision about whether to search the "
                 "archive; a search happens only if the decision is yes. When off, no decision "
                 "and no search occur.",
        )

        if st.button("Start fresh session", width="stretch"):
            fresh_session()
            st.rerun()

        if st.button(
            "End session",
            width="stretch",
            disabled=not st.session_state.messages or st.session_state.ended,
            help="Memories are already saved after every reply. This saves anything still "
                 "pending and closes the working context.",
        ):
            with st.spinner("Saving any remaining messages..."):
                episodes, errors = engine.form_memories(
                    st.session_state.conversation_id, incremental=True, end=True
                )
            st.session_state.saved_episode_ids.extend(
                episode["episode_id"] for episode in episodes
            )
            st.session_state.ended = True
            if errors:
                notice("warning",
                       f"Stored {len(episodes)} new memories. Notes: " + " | ".join(errors))
            else:
                notice("success", f"Session ended. {len(episodes)} new memories stored.")
            st.rerun()

        if st.button("Load demo conversation & extract memories", width="stretch",
                     help="Seeds dated fictional messages, then runs the normal LLM extraction "
                          "pipeline."):
            with st.spinner("Processing the demo conversation through Qwen..."):
                episodes, errors = engine.load_demo()
            fresh_session()
            if errors and not episodes:
                notice("error", "Demo extraction failed: " + " | ".join(errors))
            else:
                notice(
                    "success",
                    f"Demo processed: {len(episodes)} memories created through the normal "
                    "pipeline. A fresh conversation is ready — ask the four demo questions.",
                )
            st.rerun()

    st.caption(
        f"Chat: `{settings.chat_model}`\n\nEmbeddings: `{settings.embed_model}`\n\n"
        f"DB: `{settings.database_path}`"
    )

    st.divider()
    show_inactive = st.checkbox("Show superseded / cancelled memories", value=False)
    if st.button("Merge duplicate memories", width="stretch",
                 help="Backstop for archives created before automatic merging. New memories "
                      "are merged during saving."):
        merged = engine.consolidate_duplicates()
        if merged:
            notice("success", f"Merged {len(merged)} duplicate memories.")
        else:
            notice("info", "No duplicates found.")
        st.rerun()

    if st.toggle("Browse saved memories", key="browse_archive"):
        archive = engine.list_episodes(include_inactive=show_inactive)
        st.subheader(f"Saved memories ({len(archive)})")
        if not archive:
            st.caption("No episodes yet. Say something memorable, or load the demo.")
        for episode in archive:
            state = episode["status"]
            icon = {"active": "🟢", "done": "✅",
                    "superseded": "🔁", "cancelled": "🚫"}.get(state, "⚪")
            with st.expander(f"{icon} {episode['title']}"):
                st.write(episode["summary"])
                st.caption(
                    f"State: {state} · Type: {episode['event_type']} · "
                    f"Event date: {episode['event_time'] or 'unknown'}"
                )
                if episode["superseded_by"]:
                    st.caption(
                        f"Replaced by `{episode['superseded_by']}` — "
                        f"{episode['change_reason'] or ''}"
                    )
                st.caption(f"Episode ID: `{episode['episode_id']}`")
                st.caption(f"Source conversation: `{episode['source_conversation_id']}`")
                st.caption("Source messages: " + ", ".join(
                    f"`{mid}`" for mid in episode["source_message_ids"]
                ))
                if episode["facts"]:
                    st.markdown("**Facts**\n" + "\n".join(
                        f"- {fact}" for fact in episode["facts"]
                    ))
                if episode["outcome"]:
                    st.markdown(f"**Outcome:** {episode['outcome']}")
                st.caption(
                    f"Embedding: {episode['embedding_model']} ({episode['embedding_dim']} dims)"
                )
                history = engine.list_events(episode["episode_id"], limit=10)
                if history:
                    st.caption("History: " + " · ".join(
                        f"{event['action']} ({event['created_at'][:10]})"
                        for event in history
                    ))
                if st.button("Delete memory", key=f"del_{episode['episode_id']}"):
                    engine.delete_episode(episode["episode_id"])
                    notice("success", f"Deleted episode {episode['episode_id']}.")
                    st.rerun()

    if view == "Chat":
        traces = engine.list_traces(limit=5)
        if traces:
            with st.expander(f"Recent persisted turns ({len(traces)})"):
                st.caption("These survive a restart. They are useful when testing the "
                           "benchmark cases.")
                for trace in traces:
                    st.markdown(f"**Q:** {trace['question']}")
                    st.caption(
                        f"{trace['created_at']} · {trace['latency_ms'] or 0} ms · "
                        f"searched: {trace['details'].get('searched')} · "
                        f"query: {trace['details'].get('search_query') or 'none'}"
                    )
                    st.write(trace["answer"][:400]
                             + ("..." if len(trace["answer"]) > 400 else ""))
                    st.divider()


if st.session_state.notice:
    kind, text = st.session_state.notice["kind"], st.session_state.notice["text"]
    {"success": st.success, "warning": st.warning,
     "error": st.error, "info": st.info}[kind](text)
    st.session_state.notice = None


# ----------------------------- chat -----------------------------

def render_chat() -> None:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            details: dict[str, Any] | None = message.get("details")
            if details:
                title = ("Retrieval details (memory searched)" if details["searched"]
                         else "Retrieval details (memory not searched)")
                with st.expander(title):
                    st.write(f"Memory retrieval enabled: {details['memory_enabled']}")
                    st.write(f"Model requested memory: {details['needs_memory']}")
                    if details["search_query"]:
                        st.write(f"Search query: {details['search_query']}")
                    st.write(details["reason"])
                    if details["results"]:
                        st.markdown("**Retrieved episodes**")
                        for result in details["results"]:
                            st.write(
                                f"- `{result['episode_id']}` — {result['title']} — "
                                f"similarity {result['score']:.4f}"
                            )
                            st.caption("Source messages: " + ", ".join(
                                f"`{mid}`" for mid in result["source_message_ids"]
                            ))
                    if details["evidence"]:
                        st.markdown("**Evidence supplied to the model**")
                        st.code(details["evidence"], language="text")
                    else:
                        st.caption("No evidence was supplied to the model.")
            writer = message.get("writer")
            if writer:
                if writer["saved"]:
                    st.caption(
                        f"Memory writer: stored {writer['saved']} new episode(s) from this turn."
                    )
                else:
                    st.caption("Memory writer: nothing new to store from this turn.")
                if writer["notes"]:
                    with st.expander("Memory writer notes"):
                        for note in writer["notes"]:
                            st.caption(note)

    if st.session_state.ended:
        st.subheader("Memories saved from this session")
        saved = [
            episode for episode in engine.list_episodes()
            if episode["episode_id"] in st.session_state.saved_episode_ids
        ]
        if saved:
            for episode in saved:
                with st.expander(f"{episode['title']} · `{episode['episode_id']}`"):
                    st.write(episode["summary"])
                    st.caption(
                        f"Status: {episode['status']} · Source conversation: "
                        f"`{episode['source_conversation_id']}`"
                    )
                    if st.button("Delete this memory",
                                 key=f"saved_del_{episode['episode_id']}"):
                        engine.delete_episode(episode["episode_id"])
                        notice("success", f"Deleted episode {episode['episode_id']}.")
                        st.rerun()
        else:
            st.info("The model found nothing worth remembering in this session "
                    "(or everything was deleted).")
        st.info("This working context is finished. Click **Start fresh session** to ask a "
                "new question.")
    elif prompt := st.chat_input("Message the assistant..."):
        history = [
            {"role": message["role"], "content": message["content"]}
            for message in st.session_state.messages
        ]
        user_message = engine.add_message(
            st.session_state.conversation_id, "user", prompt
        )
        st.session_state.messages.append({"role": "user", "content": prompt})
        started = time.perf_counter()
        try:
            with st.spinner("Thinking..."):
                result = engine.handle_turn(
                    prompt, history, retrieval_enabled=retrieval_enabled
                )
        except Exception as exc:  # noqa: BLE001 - shown in the UI on stage
            notice("error", str(exc))
            st.rerun()
        latency_ms = int((time.perf_counter() - started) * 1000)
        assistant_message = engine.add_message(
            st.session_state.conversation_id, "assistant", result["answer"]
        )
        engine.save_trace(
            st.session_state.conversation_id,
            prompt,
            result["answer"],
            result["details"],
            user_message_id=user_message["message_id"],
            assistant_message_id=assistant_message["message_id"],
            latency_ms=latency_ms,
        )
        st.session_state.messages.append(
            {"role": "assistant", "content": result["answer"], "details": result["details"]}
        )
        # Show the reply now, so the user is not staring at a blank screen while memories save.
        with st.chat_message("assistant"):
            st.markdown(result["answer"])
        with st.spinner("Saving new memories..."):
            written, notes = engine.form_memories(
                st.session_state.conversation_id, incremental=True, end=False
            )
        st.session_state.messages[-1]["writer"] = {
            "saved": len(written), "notes": notes
        }
        st.session_state.saved_episode_ids.extend(
            episode["episode_id"] for episode in written
        )
        st.rerun()


# ----------------------------- views -----------------------------

if view == "Memory Map":
    from demo_views import render_memory_map

    render_memory_map(engine)
elif view == "Time Machine":
    from demo_views import render_time_machine

    render_time_machine(engine)
else:
    render_chat()
