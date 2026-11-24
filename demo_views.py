"""Visual screens for the demo: the Memory Map and the Time Machine."""

from __future__ import annotations

import hashlib
import time
import uuid
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

STATUS_ORDER = ["active", "done", "superseded", "cancelled"]
STATUS_LABELS = {
    "active": "Active",
    "done": "Completed",
    "superseded": "Replaced",
    "cancelled": "Cancelled",
}
STATUS_COLORS = {
    "Active": "#22c55e",
    "Completed": "#3b82f6",
    "Replaced": "#f59e0b",
    "Cancelled": "#ef4444",
}
STATUS_ICONS = {
    "active": "🟢",
    "done": "✅",
    "superseded": "🔁",
    "cancelled": "🚫",
}
ACTION_ICONS = {
    "created": "✨",
    "done": "✅",
    "cancelled": "🚫",
    "superseded": "🔁",
    "deleted": "🗑️",
}
PROJECT_ORDER = ["Atlas", "Beacon", "Cinder", "Live"]
PROJECT_SHAPES = {
    "Atlas": "circle",
    "Beacon": "square",
    "Cinder": "triangle-up",
    "Live": "triangle-down",
}
SPEAKER_ROLES = {"user", "assistant", "system"}
SIMILARITY_FLOOR = 0.65
GLOW_SECONDS = 30.0


# --------------------------------------------------------------------------- helpers


def _project_of(conversation_id: str) -> str:
    text = (conversation_id or "").lower()
    if "atlas" in text:
        return "Atlas"
    if "beacon" in text:
        return "Beacon"
    if "cinder" in text:
        return "Cinder"
    return "Live"


def _short(text: str, limit: int = 170) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _hash_jitter(seed: str) -> tuple[float, float]:
    digest = hashlib.md5(seed.encode()).digest()
    return ((digest[0] / 255) - 0.5) * 0.045, ((digest[1] / 255) - 0.5) * 0.045


def _positions(embeddings: np.ndarray) -> np.ndarray:
    """Project embeddings onto a stable two-dimensional basis.

    The basis is computed once and kept in session state. New live memories are projected
    onto the same basis, so existing dots do not jump around when one is added.
    """
    basis = st.session_state.get("map_basis")
    if basis is not None and basis["mean"].shape[0] != embeddings.shape[1]:
        basis = None
    if basis is None:
        mean = embeddings.mean(axis=0)
        centered = embeddings - mean
        if len(embeddings) >= 2:
            _, _, vt = np.linalg.svd(centered, full_matrices=False)
            components = vt[:2]
        else:
            components = np.zeros((2, embeddings.shape[1]))
            components[0, 0] = 1.0
            if embeddings.shape[1] > 1:
                components[1, 1] = 1.0
        for axis in range(components.shape[0]):
            loading = components[axis]
            if loading[np.argmax(np.abs(loading))] < 0:
                components[axis] = -loading
        projected = centered @ components.T
        span = float(np.abs(projected).max()) or 1.0
        basis = {
            "mean": mean.astype(np.float64),
            "components": components.astype(np.float64),
            "span": span,
        }
        st.session_state.map_basis = basis
    return (embeddings - basis["mean"]) @ basis["components"].T / basis["span"]


def _ping(kind: str, text: str) -> None:
    st.session_state.map_message = {"kind": kind, "text": text}


# --------------------------------------------------------------------------- frames


def _node_frame(engine) -> pd.DataFrame | None:
    episodes = engine.list_episodes(include_embeddings=True, include_inactive=True)
    if not episodes:
        return None
    rows = []
    for episode in episodes:
        people = [person for person in episode["participants"]
                  if person.lower() not in SPEAKER_ROLES]
        rows.append(
            {
                "id": episode["episode_id"],
                "title": episode["title"],
                "status": episode["status"],
                "status_label": STATUS_LABELS.get(episode["status"], episode["status"].title()),
                "type": episode["event_type"],
                "project": _project_of(episode["source_conversation_id"]),
                "people_list": people,
                "people": ", ".join(people) or "—",
                "summary": _short(episode["summary"]),
                "created": episode["created_at"][:10],
                "updated": episode["updated_at"] or episode["created_at"],
                "superseded_by": episode["superseded_by"],
                "embedding": episode["embedding"],
            }
        )
    frame = pd.DataFrame(rows)
    embeddings = np.asarray(frame["embedding"].tolist(), dtype=np.float64)
    coordinates = _positions(embeddings)
    frame["x"] = coordinates[:, 0]
    frame["y"] = coordinates[:, 1]
    jitter = np.asarray([_hash_jitter(episode_id) for episode_id in frame["id"]])
    frame["x"] = frame["x"] + jitter[:, 0]
    frame["y"] = frame["y"] + jitter[:, 1]
    frame["summary"] = frame["summary"].map(_short)
    return frame


def _lifecycle_edges(frame: pd.DataFrame) -> tuple[pd.DataFrame, set[tuple[str, str]]]:
    index = {episode_id: position for position, episode_id in enumerate(frame["id"])}
    rows: list[dict[str, Any]] = []
    pairs: set[tuple[str, str]] = set()
    for row in frame.itertuples(index=False):
        target = row.superseded_by
        if not target or target not in index:
            continue
        destination = index[target]
        rows.append(
            {
                "a": row.id,
                "b": target,
                "x": row.x,
                "y": row.y,
                "x2": frame.iloc[destination]["x"],
                "y2": frame.iloc[destination]["y"],
                "status_label": STATUS_LABELS.get(row.status, row.status.title()),
                "kind": "changed",
                "label": f"{row.title} → {frame.iloc[destination]['title']}",
            }
        )
        pairs.add(tuple(sorted((row.id, target))))
    return pd.DataFrame(rows, columns=["a", "b", "x", "y", "x2", "y2",
                                       "status_label", "kind", "label"]), pairs


def _similarity_edges(frame: pd.DataFrame,
                      lifecycle: set[tuple[str, str]]) -> pd.DataFrame:
    embeddings = np.asarray(frame["embedding"].tolist(), dtype=np.float64)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / np.maximum(norms, 1e-9)
    similarity = embeddings @ embeddings.T
    ids = list(frame["id"])
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for i, episode_id in enumerate(ids):
        picked = 0
        for j in np.argsort(-similarity[i]):
            j = int(j)
            if j == i:
                continue
            score = float(similarity[i, j])
            if score < SIMILARITY_FLOOR:
                break
            pair = tuple(sorted((episode_id, ids[j])))
            if pair in lifecycle or pair in seen:
                continue
            seen.add(pair)
            rows.append(
                {
                    "a": episode_id,
                    "b": ids[j],
                    "x": frame.iloc[i]["x"],
                    "y": frame.iloc[i]["y"],
                    "x2": frame.iloc[j]["x"],
                    "y2": frame.iloc[j]["y"],
                    "kind": "related",
                    "label": f"{frame.iloc[i]['title']} ~ {frame.iloc[j]['title']} "
                             f"({score:.2f})",
                }
            )
            picked += 1
            if picked >= 2:
                break
    return pd.DataFrame(rows, columns=["a", "b", "x", "y", "x2", "y2", "kind", "label"])


def _people_hubs(frame: pd.DataFrame):
    by_person: dict[str, list[str]] = defaultdict(list)
    display: dict[str, str] = {}
    for row in frame.itertuples(index=False):
        for person in dict.fromkeys(row.people_list):
            key = person.lower()
            display.setdefault(key, person)
            by_person[key].append(row.id)

    project_of = dict(zip(frame["id"], frame["project"]))
    coordinates = {row.id: (row.x, row.y) for row in frame.itertuples(index=False)}
    hub_rows: list[dict[str, Any]] = []
    edge_rows: list[dict[str, Any]] = []
    for key, members in by_person.items():
        projects = sorted({project_of[member] for member in members})
        if len(projects) < 2:
            continue
        name = display[key]
        subset = frame[frame["id"].isin(members)]
        hub_x = float(subset["x"].mean())
        hub_y = float(subset["y"].mean())
        hub_rows.append(
            {
                "x": hub_x,
                "y": hub_y,
                "person": name,
                "label": f"{name} · {', '.join(projects)}",
                "count": len(members),
                "projects": ", ".join(projects),
            }
        )
        for member in members:
            member_x, member_y = coordinates[member]
            edge_rows.append(
                {
                    "member": member,
                    "x": hub_x,
                    "y": hub_y,
                    "x2": member_x,
                    "y2": member_y,
                    "kind": "person",
                    "label": f"{name} appears in this memory",
                }
            )
    return (
        pd.DataFrame(hub_rows, columns=["x", "y", "person", "label", "count", "projects"]),
        pd.DataFrame(edge_rows, columns=["member", "x", "y", "x2", "y2", "kind", "label"]),
    )


# --------------------------------------------------------------------------- write path


def _write_memory(engine, text: str, project: str) -> None:
    text = " ".join((text or "").split())
    if len(text) < 10:
        st.warning("Write at least a short sentence so the extractor has something to work with.")
        return
    slug = project.lower() if project in {"Atlas", "Beacon", "Cinder"} else "live"
    conversation_id = f"conv_live_{slug}_{uuid.uuid4().hex[:8]}"
    with st.spinner("Running the real extractor…"):
        try:
            engine.add_message(
                conversation_id, "user", text,
                message_id=f"live_{uuid.uuid4().hex[:10]}",
            )
            # A fresh standalone conversation is processed in full. Incremental extraction
            # appends the whole known-memory list to the prompt, and with a large archive the
            # model then declines to extract genuinely new facts.
            stored, notes = engine.form_memories(conversation_id, incremental=False, end=True)
        except Exception as exc:  # noqa: BLE001 - shown in the UI on stage
            st.error(f"The extractor failed: {exc}")
            return

    if not stored:
        detail = " ".join(notes) if notes else "the model returned no durable memory"
        st.warning(f"Nothing was stored: {detail}. Try a more specific sentence.")
        return

    titles = ", ".join(episode["title"] for episode in stored)
    st.session_state.map_glow = {
        "ids": [episode["episode_id"] for episode in stored],
        "until": time.time() + GLOW_SECONDS,
    }
    changes = [episode["change"]["action"] for episode in stored if episode.get("change")]
    suffix = f" ({', '.join(sorted(set(changes)))})" if changes else ""
    _ping("success", f"Stored {len(stored)} memory: {titles}{suffix}")
    st.rerun()


# --------------------------------------------------------------------------- memory map

# One-click writes used in the live demo. Each one either changes an existing memory's
# date or adds a new link to a person and project already on the map.
EXAMPLES = [
    ("Change a date", "Atlas",
     "Priya's review of the Atlas demo script is now due on 20 November 2026."),
    ("Add a task", "Beacon",
     "Noah's Beacon launch retro is due on 21 November 2026."),
    ("Add an update", "Cinder",
     "Cinder now runs a nightly integrity check on the analytics tables."),
]


def render_map_sidebar(engine) -> None:
    """Demo controls live in the sidebar so a click never scrolls the map out of view."""
    st.markdown("**Try a live write**")
    st.caption("Each button runs the real extractor. Watch the map change in place.")
    for label, project, sentence in EXAMPLES:
        if st.button(label, key=f"example_{project}", width="stretch"):
            _write_memory(engine, sentence, project)

    with st.expander("Write your own memory"):
        with st.form("add_memory", clear_on_submit=True, border=False):
            text = st.text_area(
                "What happened?",
                height=92,
                placeholder="e.g. Priya's review of the Atlas demo script is now due on "
                            "20 November 2026.",
            )
            project = st.selectbox("Project", ["Atlas", "Beacon", "Cinder", "Live"], index=3)
            submitted = st.form_submit_button("Save memory", type="primary")
        if submitted:
            _write_memory(engine, text, project)


def render_memory_map(engine) -> None:
    st.markdown("### The memory map")
    st.caption(
        "Every dot is a memory the system wrote. Colour is its state now: green is active, "
        "blue is completed, amber was replaced, red was cancelled. Coloured lines are changes "
        "of state, grey lines are similar memories, purple diamonds are people who appear in "
        "more than one project."
    )

    message = st.session_state.pop("map_message", None)
    if message:
        {"success": st.success, "warning": st.warning,
         "error": st.error, "info": st.info}[message["kind"]](message["text"])

    # --- query ---------------------------------------------------------------
    query_column, hint_column = st.columns([2.2, 3.0])
    with query_column:
        with st.form("map_query", border=False):
            query = st.text_input(
                "Ask the map",
                placeholder="e.g. what happened to the schema?",
                label_visibility="collapsed",
            )
            search = st.form_submit_button("Highlight related memories")
        if search:
            if not query.strip():
                st.warning("Type a question first.")
            else:
                try:
                    with st.spinner("Embedding the question…"):
                        result = engine.retrieve(query.strip(), top_k=4)
                except Exception as exc:  # noqa: BLE001 - surfaced on stage
                    st.error(f"Search failed: {exc}")
                else:
                    matches = result.matches
                    st.session_state.map_match = {
                        "query": query.strip(),
                        "ids": [m["episode"]["episode_id"] for m in matches],
                        "scores": {m["episode"]["episode_id"]: m["score"] for m in matches},
                    }
    with hint_column:
        st.caption(
            "Search uses the same embedding retrieval as the chat. Matches get a bright blue "
            "ring; the score is shown in the side panel."
        )

    # No timer-driven fragment: the map re-renders on every app run, including right after
    # a write from the sidebar. That keeps the projector view still between interactions.
    def live_map() -> None:
        frame = _node_frame(engine)
        if frame is None:
            st.info("The archive is empty. Write a memory below, or load the demo conversation.")
            return

        lifecycle, lifecycle_pairs = _lifecycle_edges(frame)
        similarity = _similarity_edges(frame, lifecycle_pairs)
        hubs, hub_edges = _people_hubs(frame)

        match = st.session_state.get("map_match") or {}
        matched_ids = set(match.get("ids", []))
        matched = frame[frame["id"].isin(matched_ids)]

        glow = st.session_state.get("map_glow") or {}
        glow_ids = set(glow.get("ids", [])) if time.time() < glow.get("until", 0) else set()
        glowing = frame[frame["id"].isin(glow_ids)]

        degree: Counter[str] = Counter()
        for edges in (lifecycle, similarity):
            for row in edges.itertuples(index=False):
                degree[row.a] += 1
                degree[row.b] += 1
        for row in hub_edges.itertuples(index=False):
            degree[row.member] += 1
        frame = frame.copy()
        frame["degree"] = frame["id"].map(lambda episode_id: degree.get(episode_id, 0))

        color_scale = alt.Scale(
            domain=[STATUS_LABELS[status] for status in STATUS_ORDER],
            range=[STATUS_COLORS[STATUS_LABELS[status]] for status in STATUS_ORDER],
        )
        shape_scale = alt.Scale(
            domain=PROJECT_ORDER,
            range=[PROJECT_SHAPES[project] for project in PROJECT_ORDER],
        )

        similarity_layer = (
            alt.Chart(similarity)
            .mark_rule(color="#cbd5e1", strokeWidth=1, opacity=0.45)
            .encode(
                x=alt.X("x:Q", axis=None),
                y=alt.Y("y:Q", axis=None),
                x2="x2:Q",
                y2="y2:Q",
                tooltip=[alt.Tooltip("label:N", title="Similar memories")],
            )
        )
        hub_edge_layer = (
            alt.Chart(hub_edges)
            .mark_rule(color="#c4b5fd", strokeWidth=1.2, opacity=0.55)
            .encode(
                x=alt.X("x:Q", axis=None),
                y=alt.Y("y:Q", axis=None),
                x2="x2:Q",
                y2="y2:Q",
                tooltip=[alt.Tooltip("label:N", title="Person link")],
            )
        )
        lifecycle_layer = (
            alt.Chart(lifecycle)
            .mark_rule(strokeWidth=2.2, opacity=0.85)
            .encode(
                x=alt.X("x:Q", axis=None),
                y=alt.Y("y:Q", axis=None),
                x2="x2:Q",
                y2="y2:Q",
                color=alt.Color("status_label:N", scale=color_scale),
                tooltip=[alt.Tooltip("label:N", title="Change")],
            )
        )
        node_layer = (
            alt.Chart(frame)
            .mark_point(filled=True, stroke="white", strokeWidth=1.1)
            .encode(
                x=alt.X("x:Q", axis=None),
                y=alt.Y("y:Q", axis=None),
                size=alt.Size(
                    "degree:Q",
                    scale=alt.Scale(type="sqrt", range=[110, 720]),
                    legend=None,
                ),
                color=alt.Color(
                    "status_label:N", scale=color_scale,
                    legend=alt.Legend(title="State", orient="top", direction="horizontal"),
                ),
                shape=alt.Shape(
                    "project:N", scale=shape_scale,
                    legend=alt.Legend(title="Project", orient="top", direction="horizontal"),
                ),
                tooltip=[
                    alt.Tooltip("title:N", title="Memory"),
                    alt.Tooltip("project:N", title="Project"),
                    alt.Tooltip("status_label:N", title="State"),
                    alt.Tooltip("type:N", title="Type"),
                    alt.Tooltip("created:N", title="Learned"),
                    alt.Tooltip("people:N", title="People"),
                    alt.Tooltip("summary:N", title="Summary"),
                ],
            )
        )
        hub_layer = (
            alt.Chart(hubs)
            .mark_point(shape="diamond", size=520, filled=True,
                        color="#8b5cf6", stroke="white", strokeWidth=1.4)
            .encode(
                x=alt.X("x:Q", axis=None),
                y=alt.Y("y:Q", axis=None),
                tooltip=[
                    alt.Tooltip("person:N", title="Person"),
                    alt.Tooltip("projects:N", title="Projects"),
                    alt.Tooltip("count:Q", title="Memories"),
                ],
            )
        )
        hub_label_layer = (
            alt.Chart(hubs)
            .mark_text(dx=12, dy=-10, fontSize=11, fontWeight=600, color="#8b5cf6")
            .encode(x=alt.X("x:Q", axis=None), y=alt.Y("y:Q", axis=None), text="person:N")
        )
        project_labels = (
            frame.groupby("project", as_index=False)
            .agg(x=("x", "mean"), y=("y", "mean"), count=("id", "count"))
        )
        project_labels["label"] = (
            project_labels["project"].str.upper() + " · " + project_labels["count"].astype(str)
        )
        project_label_layer = (
            alt.Chart(project_labels)
            .mark_text(fontSize=15, fontWeight="bold", color="#7c8798", opacity=0.95, dy=-14)
            .encode(
                x=alt.X("x:Q", axis=None),
                y=alt.Y("y:Q", axis=None),
                text="label:N",
            )
        )

        layers: list[alt.Chart] = [similarity_layer, hub_edge_layer, lifecycle_layer]
        if not glowing.empty:
            # A translucent halo sits behind the nodes; the ring and caption go on top.
            layers.append(
                alt.Chart(glowing)
                .mark_point(size=2200, filled=True, color="#f59e0b", opacity=0.18)
                .encode(x=alt.X("x:Q", axis=None), y=alt.Y("y:Q", axis=None))
            )
        layers += [node_layer, hub_layer, hub_label_layer, project_label_layer]
        if not matched.empty:
            layers.append(
                alt.Chart(matched)
                .mark_point(size=1500, filled=False, stroke="#0ea5e9", strokeWidth=2.4)
                .encode(x=alt.X("x:Q", axis=None), y=alt.Y("y:Q", axis=None))
            )
            layers.append(
                alt.Chart(matched)
                .mark_text(dx=12, dy=-12, fontSize=11, fontWeight=600, color="#0ea5e9")
                .encode(x=alt.X("x:Q", axis=None), y=alt.Y("y:Q", axis=None), text="title:N")
            )
        if not glowing.empty:
            layers.append(
                alt.Chart(glowing)
                .mark_point(size=1500, filled=False, stroke="#f59e0b", strokeWidth=2.4)
                .encode(x=alt.X("x:Q", axis=None), y=alt.Y("y:Q", axis=None))
            )
            layers.append(
                alt.Chart(glowing)
                .mark_text(dx=15, dy=15, fontSize=11, fontWeight="bold", color="#f59e0b")
                .encode(x=alt.X("x:Q", axis=None), y=alt.Y("y:Q", axis=None),
                        text=alt.value("just written"))
            )

        chart = (
            alt.layer(*layers)
            .properties(height=600)
            .configure_view(stroke=None)
            .configure_legend(labelFontSize=11, titleFontSize=11, symbolSize=90)
        )

        counts = frame["status"].value_counts().to_dict()
        people = {person for values in frame["people_list"] for person in values}
        links = len(lifecycle) + len(similarity) + len(hub_edges)

        left, right = st.columns([3.25, 1.0], gap="large")
        with left:
            st.altair_chart(chart, width="stretch")
        with right:
            st.markdown("**Archive now**")
            metric_columns = st.columns(2)
            metric_columns[0].metric("Memories", len(frame))
            metric_columns[1].metric("Links", links)
            metric_columns[0].metric("People", len(people))
            metric_columns[1].metric("Projects", frame["project"].nunique())
            state_line = " · ".join(
                f"{STATUS_ICONS[status]} {STATUS_LABELS[status]} {counts.get(status, 0)}"
                for status in STATUS_ORDER
            )
            st.caption(state_line)

            if match:
                st.markdown("**Map matches**")
                titles = dict(zip(frame["id"], frame["title"]))
                scores = match.get("scores", {})
                found = False
                for episode_id in match.get("ids", []):
                    if episode_id in titles:
                        found = True
                        st.markdown(
                            f"- {titles[episode_id]}  \n"
                            f"  `{scores.get(episode_id, 0):.2f}`"
                        )
                if not found:
                    st.caption("No matches are currently visible.")

            st.markdown("**Live feed**")
            events = engine.list_events(limit=8)
            titles = dict(zip(frame["id"], frame["title"]))
            if not events:
                st.caption("No events yet.")
            for event in events[:6]:
                title = titles.get(event["episode_id"], "a deleted memory")
                icon = ACTION_ICONS.get(event["action"], "•")
                when = event["created_at"].replace("T", " ")[:16]
                st.markdown(f"{icon} **{event['action'].title()}** · {title}")
                st.caption(when)

            if not hubs.empty:
                st.markdown("**People across projects**")
                for row in hubs.itertuples(index=False):
                    st.markdown(f"- **{row.person}** · {row.projects} · {row.count}")

    live_map()

    # --- manage --------------------------------------------------------------
    st.divider()
    with st.expander("🗂 Manage: delete a memory and watch the links disappear", expanded=False):
        archive = engine.list_episodes(include_inactive=True)
        options = {
            f"{STATUS_ICONS.get(episode['status'], '•')} {episode['title']} "
            f"· {_project_of(episode['source_conversation_id'])} "
            f"· {episode['episode_id']}": episode["episode_id"]
            for episode in sorted(archive, key=lambda item: item["title"].lower())
        }
        if options:
            choice = st.selectbox("Choose a memory", list(options), key="map_delete_choice")
            if st.button("Delete selected memory", key="map_delete_button"):
                deleted = engine.delete_episode(options[choice])
                if deleted:
                    st.session_state.map_glow = {"ids": [], "until": 0}
                    _ping("success", f"Deleted {options[choice]}.")
                    st.rerun()
                else:
                    st.warning("That memory was already gone.")
        else:
            st.caption("The archive is empty.")


# --------------------------------------------------------------------------- time machine


def _snapshots(events: list[dict[str, Any]], days: list[date]) -> dict[date, dict[str, str]]:
    ordered = sorted(events, key=lambda event: (event["created_at"], event["event_id"]))
    state: dict[str, str] = {}
    snapshots: dict[date, dict[str, str]] = {}
    position = 0
    for day in days:
        limit = day.isoformat()
        while position < len(ordered) and ordered[position]["created_at"][:10] <= limit:
            event = ordered[position]
            action = event["action"]
            if action == "created":
                state[event["episode_id"]] = "active"
            elif action in {"done", "cancelled", "superseded"}:
                state[event["episode_id"]] = action
            elif action == "deleted":
                state.pop(event["episode_id"], None)
            position += 1
        snapshots[day] = dict(state)
    return snapshots


def render_time_machine(engine) -> None:
    st.markdown("### Time machine")
    st.caption(
        "The archive is not a list, it is a history. Scrub the date to see exactly what the "
        "system knew on that day, and what changed."
    )

    episodes = engine.list_episodes(include_inactive=True)
    events = engine.list_events(limit=5000)
    if not episodes or not events:
        st.info("No memories yet. Add one on the Memory Map first.")
        return

    titled = {episode["episode_id"]: episode for episode in episodes}
    project = {episode["episode_id"]: _project_of(episode["source_conversation_id"])
               for episode in episodes}

    first = date.fromisoformat(min(event["created_at"][:10] for event in events))
    last = max(date.fromisoformat(max(event["created_at"][:10] for event in events)),
               date.today())
    days = [first + timedelta(days=offset) for offset in range((last - first).days + 1)]

    if "tm_day" not in st.session_state or not (first <= st.session_state.tm_day <= last):
        st.session_state.tm_day = last

    def jump(target: date) -> None:
        st.session_state.tm_day = target

    preset_columns = st.columns([1.2, 1.2, 1.2, 3.0])
    preset_columns[0].button("Scope change · 12 Oct",
                             on_click=jump, args=(date(2026, 10, 12),),
                             width="stretch")
    preset_columns[1].button("Launch day · 6 Nov",
                             on_click=jump, args=(date(2026, 11, 6),),
                             width="stretch")
    preset_columns[2].button("Today",
                             on_click=jump, args=(last,),
                             width="stretch")

    selected = st.slider(
        "Date",
        min_value=first,
        max_value=last,
        step=timedelta(days=1),
        format="MMM D, YYYY",
        key="tm_day",
    )

    snapshots = _snapshots(events, days)
    records = []
    for day in days:
        counts = Counter(snapshots[day].values())
        for order, status in enumerate(STATUS_ORDER):
            records.append(
                {
                    "date": day,
                    "status_label": STATUS_LABELS[status],
                    "count": counts.get(status, 0),
                    "order": order,
                }
            )
    history = pd.DataFrame(records)
    color_scale = alt.Scale(
        domain=[STATUS_LABELS[status] for status in STATUS_ORDER],
        range=[STATUS_COLORS[STATUS_LABELS[status]] for status in STATUS_ORDER],
    )
    area = (
        alt.Chart(history)
        .mark_area(interpolate="step-after", opacity=0.9)
        .encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("count:Q", stack="zero", title="Memories"),
            color=alt.Color(
                "status_label:N", scale=color_scale,
                legend=alt.Legend(title=None, orient="top", direction="horizontal"),
            ),
            order=alt.Order("order:Q"),
            tooltip=[
                alt.Tooltip("date:T", title="Date", format="%b %d, %Y"),
                alt.Tooltip("status_label:N", title="State"),
                alt.Tooltip("count:Q", title="Memories"),
            ],
        )
    )
    marker = (
        alt.Chart(pd.DataFrame({"date": [selected]}))
        .mark_rule(color="#0f172a", strokeWidth=2, strokeDash=[5, 4])
        .encode(x="date:T")
    )
    st.altair_chart(
        alt.layer(area, marker).properties(height=300)
        .configure_view(stroke=None)
        .configure_legend(labelFontSize=11, titleFontSize=11, symbolSize=90),
        width="stretch",
    )

    current = snapshots[selected]
    counts = Counter(current.values())
    known = sum(counts.values())
    metric_columns = st.columns(4)
    metric_columns[0].metric("Memories known", known)
    metric_columns[1].metric("Active", counts.get("active", 0))
    metric_columns[2].metric("Completed", counts.get("done", 0))
    metric_columns[3].metric("Replaced or cancelled",
                             counts.get("superseded", 0) + counts.get("cancelled", 0))
    st.caption(
        f"On {selected.strftime('%B %d, %Y')} the system knew {known} memories: "
        f"{counts.get('active', 0)} active, {counts.get('done', 0)} completed, "
        f"{counts.get('superseded', 0)} replaced, {counts.get('cancelled', 0)} cancelled."
    )

    left, right = st.columns([1.0, 1.0], gap="large")
    with left:
        st.markdown(f"**What changed on {selected.strftime('%b %d')}**")
        day_events = [
            event for event in events if event["created_at"][:10] == selected.isoformat()
        ]
        if not day_events:
            st.caption("Nothing changed on this day.")
        else:
            with st.container(height=340):
                for event in sorted(day_events, key=lambda item: item["created_at"],
                                    reverse=True):
                    title = titled.get(event["episode_id"], {}).get("title", "a deleted memory")
                    icon = ACTION_ICONS.get(event["action"], "•")
                    st.markdown(f"{icon} **{event['action'].title()}** · {title}")
                    detail = event.get("detail") or ""
                    st.caption(detail[:160] if detail else event["created_at"][:16])

    with right:
        st.markdown("**Memories the system knew**")
        with st.container(height=340):
            for project_name in PROJECT_ORDER:
                entries = [
                    (episode_id, status)
                    for episode_id, status in current.items()
                    if project.get(episode_id) == project_name
                ]
                if not entries:
                    continue
                st.markdown(f"**{project_name}** · {len(entries)}")
                for episode_id, status in sorted(
                    entries, key=lambda item: titled.get(item[0], {}).get("title", "")
                ):
                    title = titled.get(episode_id, {}).get("title", "a deleted memory")
                    st.markdown(f"{STATUS_ICONS.get(status, '•')} {title}")
