"""Cross-check your hand scores against the deterministic flags.
  python audit.py
Lists scored outputs that the automatic checks flagged (fabricated numbers, banned phrases,
foreign script, stray Latin words) together with the accuracy score you gave. Writes audit.csv.
Note: flags stored before a check existed (e.g. banned phrases when the box was empty) are missing.
"""
import json

import pandas as pd

from core import db

h = pd.read_csv("hand_scores.csv", encoding="utf-8-sig")
h = h[pd.to_numeric(h["human_accuracy"], errors="coerce").notna()]
runs = {r["id"]: r for r in db.list_runs()}
rows = []
for _, r in h.iterrows():
    run = runs[r["run_id"]]
    s = json.loads(run["scores"])
    flags = []
    if s.get("unsupported_numbers"):
        flags.append("fabricated numbers: " + ",".join(s["unsupported_numbers"]))
    if s.get("banned_hits"):
        flags.append("banned: " + ",".join(s["banned_hits"]))
    if s.get("foreign_script"):
        flags.append("foreign script")
    if s.get("latin_words", 0) >= 2:
        flags.append(f"{s['latin_words']} latin words")
    if flags:
        rows.append({"run_id": run["id"], "version": f"v{run['version']}",
                     "your_score": float(r["human_accuracy"]), "flags": " | ".join(flags)})
df = pd.DataFrame(rows)
print(f"Scored outputs: {len(h)}   flagged by automatic checks: {len(df)}")
if len(df):
    print(f"Of the flagged outputs, you scored {int((df.your_score >= 3).sum())} at 3 or higher")
    print(f"Mean score you gave flagged outputs: {df.your_score.mean():.2f}")
    print(df.to_string(index=False))
    df.to_csv("audit.csv", index=False, encoding="utf-8-sig")
