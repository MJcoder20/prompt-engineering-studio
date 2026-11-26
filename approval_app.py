"""Human-approval page for the Content Engine.   Run:  streamlit run approval_app.py"""
import html

import pandas as pd
import streamlit as st

from core import llm
from engine import generate as g
from engine import review_store as store

store.init()
st.set_page_config(page_title="Draft review", layout="wide")
st.title("Content Engine: draft review")
st.caption("Every draft is a proposal. Nothing is approved automatically; a named reviewer decides, and decisions are final.")

with st.sidebar:
    st.header("Settings")
    model = st.text_input("Model", llm.DEFAULT_MODEL, key="model")
    temperature = st.slider("Temperature", 0.0, 1.0, 0.3, 0.1, key="temperature")
    attempts = st.number_input("Max attempts", 1, 5, 3, key="attempts")


def show_rtl(text):
    body = html.escape(text).replace("\n", "<br>")
    st.markdown(f'<div dir="rtl" style="text-align:right;line-height:2;font-size:1.1rem">{body}</div>',
                unsafe_allow_html=True)


tab_new, tab_queue, tab_log = st.tabs(["1. New draft", "2. Review queue", "3. Decisions log"])

# ---------------- new draft ----------------
with tab_new:
    c1, c2 = st.columns(2)
    profile_id = c1.selectbox("Institution profile", g.list_profiles(), key="profile")
    channel = c2.selectbox("Channel", sorted(g.CHANNELS), key="channel")
    topic = st.text_input("Topic (Arabic)", key="topic")
    audience = st.text_input("Audience (Arabic, in the accusative/genitive form)", key="audience")
    facts = st.text_area("Facts - the only allowed source (Arabic)", key="facts", height=120)
    if st.button("Generate draft", type="primary", key="gen"):
        if not (topic.strip() and audience.strip() and facts.strip()):
            st.error("Topic, audience and facts are all required.")
        else:
            brief = {"topic": topic.strip(), "audience": audience.strip(), "facts": facts.strip()}
            try:
                with st.spinner("Generating and checking..."):
                    result = g.generate(profile_id, brief, channel, model, int(attempts), temperature)
                draft_id = store.add_draft(result, brief)
                st.success(f"Draft #{draft_id} saved to the review queue (automatic checks passed: {result['passed']}, "
                           f"attempts: {result['attempts']}). Open the Review queue tab to decide.")
                show_rtl(result["text"])
                for i in result["issues"]:
                    st.warning(i)
            except Exception as e:
                st.error(f"Generation failed: {e}")

# ---------------- review queue ----------------
with tab_queue:
    pending = store.list_drafts("pending")
    if not pending:
        st.info("No drafts are waiting for review.")
    else:
        labels = {f"#{d['id']} - {d['profile']} / {d['channel']} - {d['created_at']}": d["id"] for d in pending}
        pick = st.selectbox("Pending drafts", list(labels), key="draft_pick")
        d = store.get(labels[pick])
        profile, brief = g.load_profile(d["profile"]), d["brief"]
        left, right = st.columns([3, 2])
        with left:
            st.subheader("Draft (editable)")
            final = st.text_area("Final text", d["text"], key=f"final_{d['id']}", height=230)
            st.caption("Right-to-left preview of the text above:")
            show_rtl(final)
        with right:
            st.subheader("Automatic checks")
            st.write(f"Engine result: {'passed' if d['auto_passed'] else 'FAILED'} after {d['attempts']} attempt(s) "
                     f"({d['model']})")
            live = g.check(final, profile, brief, d["channel"])
            if live:
                st.error("Open issues in the text as it stands now:")
                for i in live:
                    st.write("- " + i)
            else:
                st.success("The text as it stands passes all automatic checks.")
            with st.expander("Brief"):
                st.json(brief)
            with st.expander("Attempt history"):
                for h in d["history"]:
                    st.markdown(f"**Attempt {h['attempt']}** - {len(h['issues'])} issue(s)")
                    show_rtl(h["text"])
        st.divider()
        reviewer = st.text_input("Your name (required)", key="reviewer")
        note = st.text_input("Note (required to reject, or to approve with open issues)", key=f"note_{d['id']}")
        a, r = st.columns(2)
        decision = None
        if a.button("Approve", type="primary", key=f"approve_{d['id']}"):
            decision = "approved"
        if r.button("Reject", key=f"reject_{d['id']}"):
            decision = "rejected"
        if decision:
            try:
                store.decide(d["id"], decision, reviewer, final, live, note)
                st.success(f"Draft #{d['id']} {decision} by {reviewer.strip()}.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))

# ---------------- decisions log ----------------
with tab_log:
    allrows = store.list_drafts()
    decided = [x for x in allrows if x["status"] != "pending"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Pending", len(allrows) - len(decided))
    m2.metric("Approved", sum(x["status"] == "approved" for x in decided))
    m3.metric("Rejected", sum(x["status"] == "rejected" for x in decided))
    m4.metric("Edited by reviewer", sum((x["final_text"] or "").strip() != x["text"].strip() for x in decided))
    if decided:
        df = pd.DataFrame([{
            "draft": x["id"], "decided_at": x["decided_at"], "status": x["status"], "reviewer": x["reviewer"],
            "profile": x["profile"], "channel": x["channel"], "engine_passed": bool(x["auto_passed"]),
            "edited": (x["final_text"] or "").strip() != x["text"].strip(),
            "open_issues_at_decision": len(x["final_issues"] or []), "note": x["note"]} for x in decided])
        st.dataframe(df)
        st.download_button("Download log (CSV)", df.to_csv(index=False).encode("utf-8-sig"), "decisions.csv",
                           key="download")
