"""Judge-vs-human agreement.

  python hand_score.py export [N]   -> writes hand_scores.csv (default N=24, random sample)
  python hand_score.py report       -> compares your scores with the LLM judge

Fill the human_accuracy column (1-5) in hand_scores.csv, then run report.
The sheet hides the version and the judge's score so your scoring stays blind.
Rubric: 5 = every claim is in the facts; 3 = one small invented detail;
        1 = invented facts, health claims, wrong institution, or fake numbers.
"""
import csv
import json
import random
import sys

import pandas as pd

from core import db

FILE = "hand_scores.csv"


def _facts(case_id):
    with db.conn() as c:
        row = c.execute("SELECT variables FROM cases WHERE id=?", (case_id,)).fetchone()
    return row["variables"] if row else ""


def export(n=24):
    pool = []
    for r in db.list_runs():
        s = json.loads(r["scores"])
        if r["output"].startswith("ERROR") or s.get("accuracy") is None:
            continue
        pool.append(r)
    random.Random(42).shuffle(pool)
    pool = pool[:n]
    with open(FILE, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["run_id", "source_facts", "output", "human_accuracy"])
        for r in pool:
            w.writerow([r["id"], _facts(r["case_id"]), r["output"], ""])
    print(f"Wrote {len(pool)} rows to {FILE}. Fill human_accuracy (1-5), save, then run: python hand_score.py report")


def report():
    human = pd.read_csv(FILE, encoding="utf-8-sig")
    human = human[pd.to_numeric(human["human_accuracy"], errors="coerce").notna()].copy()
    human["human_accuracy"] = human["human_accuracy"].astype(float)
    if human.empty:
        sys.exit("No human scores found. Fill the human_accuracy column first.")
    runs = {r["id"]: r for r in db.list_runs()}
    human["judge"] = human["run_id"].map(lambda i: json.loads(runs[i]["scores"]).get("accuracy"))
    human["version"] = human["run_id"].map(lambda i: f"v{runs[i]['version']}")
    human = human.dropna(subset=["judge"])
    d = (human["judge"] - human["human_accuracy"])
    print(f"Scored outputs compared:   {len(human)}")
    print(f"Exact agreement:           {(d == 0).mean():.0%}")
    print(f"Within +/-1 point:         {(d.abs() <= 1).mean():.0%}")
    print(f"Mean absolute error:       {d.abs().mean():.2f}")
    print(f"Judge bias (judge - you):  {d.mean():+.2f}   (positive = judge is more lenient)")
    if len(human) >= 5 and human["judge"].nunique() > 1 and human["human_accuracy"].nunique() > 1:
        print(f"Spearman correlation:      {human['judge'].rank().corr(human['human_accuracy'].rank()):.2f}")
    print("\nMean accuracy by version:")
    print(human.groupby("version")[["human_accuracy", "judge"]].mean().round(2).to_string())


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "export":
        export(int(sys.argv[2]) if len(sys.argv) > 2 else 24)
    elif cmd == "report":
        report()
    else:
        print(__doc__)
