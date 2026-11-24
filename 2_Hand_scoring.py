"""Fast blind hand-scoring page. Reads/writes hand_scores.csv (created by: python hand_score.py export 24)."""
import html
import json

import pandas as pd
import streamlit as st

FILE = "hand_scores.csv"
st.set_page_config(page_title="Hand scoring", layout="centered")
st.title("Hand scoring (blind)")

try:
    df = pd.read_csv(FILE, encoding="utf-8-sig")
except FileNotFoundError:
    st.error("hand_scores.csv not found. Run:  python hand_score.py export 24")
    st.stop()

scored = pd.to_numeric(df["human_accuracy"], errors="coerce").notna()
st.progress(float(scored.mean()), text=f"{int(scored.sum())} / {len(df)} scored")
todo = df[~scored]
if todo.empty:
    st.success("All scored. Now run:  python hand_score.py report")
    st.stop()

i = todo.index[0]
row = df.loc[i]
st.caption("5 = every claim is in the facts | 3 = one small invented detail | "
           "1 = invented facts, health claims, wrong institution, or fake numbers")

st.subheader("Source facts")
try:
    st.json(json.loads(row["source_facts"]))
except Exception:
    st.write(row["source_facts"])

st.subheader("Output")
body = html.escape(str(row["output"])).replace("\n", "<br>")
st.markdown(f'<div dir="rtl" style="text-align:right;line-height:2;font-size:1.1rem">{body}</div>',
            unsafe_allow_html=True)

st.subheader("Accuracy score")
cols = st.columns(5)
for n in range(1, 6):
    if cols[n - 1].button(str(n), key=f"s{n}_{i}", use_container_width=True):
        df["human_accuracy"] = pd.to_numeric(df["human_accuracy"], errors="coerce")
        df.loc[i, "human_accuracy"] = n
        df.to_csv(FILE, index=False, encoding="utf-8-sig")
        st.rerun()
