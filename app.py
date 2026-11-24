import html
import json
import os
import time

import pandas as pd
import streamlit as st

from core import db, llm, scoring

db.init()
st.set_page_config(page_title="Prompt Engineering Studio", layout="wide")
st.title("Prompt Engineering Studio")

# ---------------- sidebar ----------------
st.sidebar.header("Settings")
model = st.sidebar.text_input("Model", llm.DEFAULT_MODEL, help="mock / ollama:<model> / Claude model name")
use_judge = st.sidebar.checkbox("Use LLM judge", True)
judge_model = st.sidebar.text_input("Judge model", model)
min_words = st.sidebar.number_input("Min words (0 = off)", 0, 2000, 0)
max_words = st.sidebar.number_input("Max words (0 = off)", 0, 2000, 0)
temperature = st.sidebar.slider("Generation temperature (Ollama)", 0.0, 1.0, 0.3, 0.1)
repeats = st.sidebar.number_input("Repeats per case", 1, 5, 1)
banned = st.sidebar.text_area("Banned phrases (one per line)", "the best ever\nguaranteed\nأفضل على الإطلاق").splitlines()
st.sidebar.caption("Models: `mock` (offline test), `ollama:qwen2.5:7b` (free, local), or a Claude model name (needs API key).")
if not model.startswith(("mock", "ollama:")) and not os.environ.get("ANTHROPIC_API_KEY"):
    st.sidebar.warning("ANTHROPIC_API_KEY not set. Use 'mock' or 'ollama:<model>'.")


def show_text(text):
    rtl = scoring.arabic_ratio(text) > 0.5
    body = html.escape(text).replace("\n", "<br>")
    d, a = ("rtl", "right") if rtl else ("ltr", "left")
    st.markdown(f'<div dir="{d}" style="text-align:{a};line-height:1.8">{body}</div>', unsafe_allow_html=True)


tab1, tab2, tab3, tab4 = st.tabs(["1. Prompts", "2. Test sets", "3. Run & compare", "4. History"])

# ---------------- tab 1: prompts ----------------
with tab1:
    prompts = db.list_prompts()
    c1, c2 = st.columns([1, 2])
    with c1:
        new_name = st.text_input("New prompt name")
        if st.button("Create prompt") and new_name:
            db.create_prompt(new_name)
            st.rerun()
        names = {p["name"]: p["id"] for p in prompts}
        chosen = st.selectbox("Select prompt", list(names)) if names else None
    if chosen:
        pid = names[chosen]
        versions = db.list_versions(pid)
        with c2:
            base = versions[0] if versions else {"system": "", "template": "", "version": 0}
            st.caption(f"Editing from v{base['version']} - saving creates v{base['version'] + 1}")
            system = st.text_area("System prompt", base["system"] or "", height=130)
            template = st.text_area("Template (use {{variable}})", base["template"], height=200)
            st.write("Detected variables:", db.extract_vars(template) or "none")
            notes = st.text_input("Version notes")
            if st.button("Save as new version") and template.strip():
                db.add_version(pid, system, template, notes)
                st.rerun()
        st.subheader("Version history")
        for v in versions:
            with st.expander(f"v{v['version']} - {v['created_at']} - {v['notes'] or ''}"):
                st.code(f"SYSTEM:\n{v['system']}\n\nTEMPLATE:\n{v['template']}", language="text")

# ---------------- tab 2: test sets ----------------
with tab2:
    ts_name = st.text_input("New test set name")
    if st.button("Create test set") and ts_name:
        db.create_testset(ts_name)
        st.rerun()
    sets = {t["name"]: t["id"] for t in db.list_testsets()}
    if sets:
        sel = st.selectbox("Test set", list(sets), key="ts_sel")
        tsid = sets[sel]
        vars_json = st.text_area(
            "Add case: variables as JSON",
            '{"topic": "", "audience": "", "tone": "", "facts": ""}', height=140)
        ref = st.text_area("Reference answer (optional)", "")
        if st.button("Add case"):
            try:
                db.add_case(tsid, json.loads(vars_json), ref)
                st.rerun()
            except json.JSONDecodeError as e:
                st.error(f"Invalid JSON: {e}")
        cases = db.list_cases(tsid)
        st.write(f"{len(cases)} cases")
        for c in cases:
            st.json(c["variables"], expanded=False)

# ---------------- tab 3: run & compare ----------------
with tab3:
    prompts = db.list_prompts()
    sets = {t["name"]: t["id"] for t in db.list_testsets()}
    if not prompts or not sets:
        st.info("Create a prompt and a test set first (or run `python seed.py`).")
    else:
        pname = st.selectbox("Prompt", [p["name"] for p in prompts], key="run_prompt")
        pid = {p["name"]: p["id"] for p in prompts}[pname]
        versions = db.list_versions(pid)
        labels = {f"v{v['version']}": v for v in versions}
        picked = st.multiselect("Versions to compare", list(labels), default=list(labels)[:2])
        tsname = st.selectbox("Test set", list(sets), key="run_ts")
        cases = db.list_cases(sets[tsname])

        if st.button("Run", type="primary") and picked and cases:
            results, rows = {}, []
            bar = st.progress(0.0)
            total, done = len(picked) * len(cases) * int(repeats), 0
            for label in picked:
                v = labels[label]
                for case, rep in [(c, r) for c in cases for r in range(int(repeats))]:
                    try:
                        prompt = db.render(v["template"], case["variables"])
                        t0 = time.time()
                        out = llm.complete(v["system"], prompt, model, temperature=temperature)
                        latency = round(time.time() - t0, 2)
                    except Exception as e:
                        out, latency = f"ERROR: {e}", 0.0
                    sc = scoring.heuristic_scores(out, case["variables"], case["reference"],
                                                  min_words, max_words, banned)
                    if use_judge and not out.startswith("ERROR"):
                        sc.update(scoring.llm_judge(out, case["variables"], case["reference"], judge_model))
                    db.save_run(v["id"], case["id"], model, out, latency, sc)
                    results.setdefault((label, case["id"]), out)
                    rows.append({
                        "version": label, "case": case["id"], "rep": rep + 1,
                        "accuracy": sc.get("accuracy"), "tone": sc.get("tone"),
                        "language": sc.get("language_quality"),
                        "fabricated_numbers": len(sc["unsupported_numbers"]),
                        "banned_hits": len(sc["banned_hits"]),
                        "foreign_script": int(sc["foreign_script"]),
                        "latin_words": sc["latin_words"],
                        "markdown": int(sc["markdown"]),
                        "institution_named": int(sc.get("institution_named", 0)),
                        "length_ok": sc["length_ok"], "words": sc["words"], "latency_s": latency,
                    })
                    done += 1
                    bar.progress(done / total)

            df = pd.DataFrame(rows)
            st.subheader("Summary (mean per version)")
            st.dataframe(df.drop(columns=["case", "rep"], errors="ignore").groupby("version").mean(numeric_only=True).round(2),
                         use_container_width=True)
            st.subheader("Side-by-side outputs")
            for case in cases:
                st.markdown(f"**Case {case['id']}** - {case['variables'].get('topic', '')}")
                cols = st.columns(len(picked))
                for col, label in zip(cols, picked):
                    with col:
                        st.caption(label)
                        show_text(results[(label, case["id"])])
                st.divider()

# ---------------- tab 4: history ----------------
with tab4:
    runs = db.list_runs()
    if not runs:
        st.info("No runs yet.")
    else:
        flat = []
        for r in runs:
            s = json.loads(r["scores"])
            flat.append({"run": r["id"], "prompt": r["prompt"], "version": r["version"], "case": r["case_id"],
                         "model": r["model"], "accuracy": s.get("accuracy"), "tone": s.get("tone"),
                         "language": s.get("language_quality"),
                         "fabricated_numbers": len(s.get("unsupported_numbers", [])),
                         "time": r["created_at"]})
        st.dataframe(pd.DataFrame(flat), use_container_width=True)
