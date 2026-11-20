"""xPost dashboard: read-only view of drafts, posts, engagement, replies and voice edits.

Run from the repo root:  .venv/bin/streamlit run dashboard/app.py
Approvals and posting stay in Telegram + xurl; nothing here writes or posts.
"""
import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data  # noqa: E402
from x_schedule import DEFAULT_WINDOWS, plan  # noqa: E402

st.set_page_config(page_title="xPost dashboard", layout="wide")


@st.cache_data(ttl=60, show_spinner="Loading data...")
def load(handle, max_age_days):
    return data.load(handle, max_age_days)


with st.sidebar:
    st.header("xPost")
    data.x_db._load_env()
    handle = st.text_input("X handle", os.environ.get("X_HANDLE", "")).lstrip("@")
    max_age = st.slider("Pending replies: max age (days)", 1, 14, 3)
    if st.button("Refresh data"):
        load.clear()
    st.caption(f"Source: {data.source()}")
    st.caption("Read-only. Approve and post from Telegram.")

d = load(handle, max_age)
eng, posts, pending, edits = d["engagement"], d["posts"], d["pending"], d["edits"]
o = data.overview(eng, posts)
pct = {"rate": st.column_config.NumberColumn("eng. rate", format="percent")}

tab_overview, tab_posts, tab_perf, tab_replies, tab_edits, tab_sched = st.tabs(
    ["Overview", "Posts", "Performance", "Replies", "Voice edits", "Schedule"])

with tab_overview:
    c = st.columns(5)
    c[0].metric("Published by agent", o["published"])
    c[1].metric("Drafts waiting", o["drafts"])
    c[2].metric("Posts scraped", o["scraped"])
    c[3].metric("Total views", f"{o['views']:,}")
    c[4].metric("Avg engagement rate", f"{o['avg_rate']:.2%}")
    st.caption("Engagement rate = (likes + 2×RTs + 3×replies + 3×quotes + bookmarks) / views")
    if eng.empty:
        st.info("No engagement data yet. Run `tools/x_engagement.py --fetch --handle <handle>`.")
    else:
        seen = eng[eng["views"] > 0].sort_values("date")
        left, right = st.columns(2)
        left.subheader("Engagement rate over time")
        left.line_chart(seen.set_index("date")["rate"])
        right.subheader("Views per post")
        right.bar_chart(seen.set_index("date")["views"])
    if len(pending):
        st.warning(f"{len(pending)} replies waiting for an answer. See the Replies tab.")

with tab_posts:
    status = st.segmented_control("Status", ["all", "draft", "published"], default="all")
    view = posts if status in (None, "all") else posts[posts["status"] == status]
    if view.empty:
        st.info("No posts saved by the agent yet.")
    else:
        st.dataframe(
            view[["updated_at", "status", "kind", "text", "views", "rate", "style", "why", "id"]],
            hide_index=True, width="stretch",
            column_config={**pct, "text": st.column_config.TextColumn(width="large"),
                           "style": st.column_config.TextColumn("style check")})

with tab_perf:
    if eng.empty:
        st.info("No engagement data yet.")
    else:
        cols = st.columns(3)
        for col, key, title in zip(cols, ("format", "length", "hour_utc"),
                                   ("By format", "By length", "By hour (UTC)")):
            b = data.breakdown_df(eng, key)
            col.subheader(title)
            col.bar_chart(b.set_index(key)["avg_rate"])
            col.dataframe(b, hide_index=True, width="stretch",
                          column_config={"avg_rate": st.column_config.NumberColumn(
                              "avg rate", format="percent")})
        st.subheader("All scraped posts")
        st.dataframe(
            eng[["date", "text", "views", "likes", "retweets", "replies", "quotes",
                 "bookmarks", "rate", "format"]],
            hide_index=True, width="stretch",
            column_config={**pct, "text": st.column_config.TextColumn(width="large")})

with tab_replies:
    if not handle:
        st.info("Enter your X handle in the sidebar to find unanswered replies.")
    elif pending.empty:
        st.success("No unanswered replies on your recent posts.")
    else:
        st.caption("Draft answers with the x-reply skill; they still go through Telegram approval.")
        st.dataframe(pending, hide_index=True, width="stretch")

with tab_edits:
    st.caption("Your rewrites of agent drafts. The agent uses these as voice examples.")
    if edits.empty:
        st.info("No edits stored yet.")
    for _, e in edits.iterrows():
        with st.container(border=True):
            a, b = st.columns(2)
            a.markdown("**Agent draft**")
            a.write(e["original"])
            b.markdown("**Your version**")
            b.write(e["final"])
            if e["note"]:
                st.caption(f"Note: {e['note']}")

with tab_sched:
    st.caption("Preview of the jittered times `tools/x_schedule.py` would pick. Nothing is saved.")
    a, b, c = st.columns(3)
    n = a.number_input("Posts per day", 1, 6, 2)
    gap = b.number_input("Min gap (minutes)", 15, 600, 90)
    windows = c.text_input("Active windows (local time)", DEFAULT_WINDOWS)
    if st.button("Roll a sample day"):
        try:
            p = plan(int(n), windows, int(gap), skip_chance=0.1)
            st.write("Skip today" if p["skip"] else "Post at: " + ", ".join(p["times"]))
        except ValueError as err:
            st.error(f"Bad windows: {err}")
