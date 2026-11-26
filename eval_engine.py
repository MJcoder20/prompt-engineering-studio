"""Measure the Content Engine on a fixed set of briefs (engine/eval_briefs.json; all fictional).

  python eval_engine.py                       3 repeats per brief, model from core/llm.py
  python eval_engine.py --repeats 1 --limit 4 quick check on the first 4 briefs
Writes eval_results.json (full drafts and issues) and eval_runs.csv (one row per run).
"""
import argparse
import collections
import csv
import json
import os
import re
import sys

from engine.generate import generate

BRIEFS_PATH = os.path.join(os.path.dirname(__file__), "engine", "eval_briefs.json")


def load_briefs(limit=None):
    with open(BRIEFS_PATH, encoding="utf-8") as f:
        briefs = json.load(f)["briefs"]
    return briefs[:limit] if limit else briefs


def run_eval(briefs, repeats, model, attempts, progress=False):
    records = []
    for i, b in enumerate(briefs, 1):
        for rep in range(1, repeats + 1):
            r = generate(b["profile"], b["brief"], b["channel"], model, attempts)
            first = r["history"][0]["issues"]
            records.append({"id": b["id"], "profile": b["profile"], "channel": b["channel"], "tags": b["tags"],
                            "rep": rep, "passed": r["passed"], "attempts": r["attempts"], "first_pass": not first,
                            "first_issues": first, "final_issues": r["issues"], "text": r["text"], "history": r["history"]})
            if progress:
                print(f"[{i}/{len(briefs)}] {b['id']} run {rep}: passed={r['passed']} attempts={r['attempts']}", flush=True)
    return records


def _norm(issue):
    return re.sub(r"\(it has \d+\)", "", issue).strip()


def _rate(rows, key):
    return f"{sum(1 for r in rows if r[key]) / len(rows):.0%}" if rows else "-"


def summarize(records):
    out = []
    n = len(records)
    out.append(f"Runs: {n}   first-attempt pass: {_rate(records, 'first_pass')}   "
               f"pass after retries: {_rate(records, 'passed')}   mean attempts: {sum(r['attempts'] for r in records) / n:.2f}")
    for title, keyf in (("channel", lambda r: [r["channel"]]), ("profile", lambda r: [r["profile"]]), ("tag", lambda r: r["tags"])):
        groups = collections.defaultdict(list)
        for r in records:
            for k in keyf(r):
                groups[k].append(r)
        out.append(f"\nBy {title}:  (runs | first-attempt | after retries)")
        for k, rows in sorted(groups.items()):
            out.append(f"  {k:<22} {len(rows):>3} | {_rate(rows, 'first_pass'):>4} | {_rate(rows, 'passed'):>4}")
    first = collections.Counter(_norm(i) for r in records for i in r["first_issues"])
    final = collections.Counter(_norm(i) for r in records for i in r["final_issues"])
    out.append("\nMost common first-draft problems:")
    out += [f"  {c:>3}x  {i}" for i, c in first.most_common(8)] or ["  none"]
    out.append("\nProblems still present after retries:")
    out += [f"  {c:>3}x  {i}" for i, c in final.most_common(6)] or ["  none"]
    return "\n".join(out)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = argparse.ArgumentParser()
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--attempts", type=int, default=3)
    p.add_argument("--model")
    p.add_argument("--limit", type=int)
    a = p.parse_args()
    records = run_eval(load_briefs(a.limit), a.repeats, a.model, a.attempts, progress=True)
    with open("eval_results.json", "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=1)
    with open("eval_runs.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "channel", "rep", "passed", "attempts", "first_pass", "final_issues"])
        for r in records:
            w.writerow([r["id"], r["channel"], r["rep"], r["passed"], r["attempts"], r["first_pass"], " | ".join(r["final_issues"])])
    print("\n" + summarize(records))


if __name__ == "__main__":
    main()
