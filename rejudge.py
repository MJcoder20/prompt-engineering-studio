"""Re-judge your hand-scored outputs with two stricter judges and compare agreement with YOUR scores.

  python rejudge.py [model]        default model: ollama:qwen2.5:7b
Needs hand_scores.csv (scored) and studio.db. Takes ~3-5 minutes for 24 outputs (48 judge calls).
Writes rejudge_results.csv. No outputs are regenerated and none of your scores change.
"""
import json
import re
import sys

import pandas as pd

from core import db, llm

FILE = "hand_scores.csv"

STRICT_SYSTEM = (
    "You check a government press release against its SOURCE facts. Reply in English only, JSON only.\n"
    "Score ONLY factual support of the OUTPUT: 5 = every statement is supported by the SOURCE; "
    "4 = one trivial extra phrase; 3 = one clearly unsupported detail; "
    "2 = two or three unsupported details; 1 = invented places, numbers, institutions or claims.\n"
    "Do NOT penalize: brevity, omitted details, tone, style or formality. Rewording of source facts counts as supported. "
    "The institution field is part of the SOURCE.\n"
    'Format: {"score": int, "unsupported": ["short quote of each unsupported statement"]}'
)

CLAIM_SYSTEM = (
    "Reply in English only, JSON only. List every factual statement in the OUTPUT "
    "(dates, numbers, places, institutions, services, promises, health claims). "
    "For each, say whether the SOURCE supports it. Rewording is fine; the institution field is part of the SOURCE.\n"
    'Format: {"claims": [{"claim": "short text", "supported": true}]}'
)


def _json(raw):
    m = re.search(r"\{.*\}", raw or "", re.S)
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _facts(case_id):
    with db.conn() as c:
        row = c.execute("SELECT variables FROM cases WHERE id=?", (case_id,)).fetchone()
    return row["variables"] if row else "{}"


def strict_judge(facts, output, model):
    d = _json(llm.complete(STRICT_SYSTEM, f"SOURCE:\n{facts}\n\nOUTPUT:\n{output}", model, 400, temperature=0.0))
    try:
        return max(1, min(5, int(d["score"])))
    except Exception:
        return None


def claim_judge(facts, output, model):
    d = _json(llm.complete(CLAIM_SYSTEM, f"SOURCE:\n{facts}\n\nOUTPUT:\n{output}", model, 700, temperature=0.0))
    try:
        bad = sum(1 for c in d["claims"] if c.get("supported") is False)
        return max(1, 5 - bad)
    except Exception:
        return None


def stats(df, col):
    d = df[col] - df["human"]
    s = df[col].rank().corr(df["human"].rank()) if df[col].nunique() > 1 else float("nan")
    return {"n": len(df), "exact": f"{(d == 0).mean():.0%}", "within1": f"{(d.abs() <= 1).mean():.0%}",
            "MAE": round(d.abs().mean(), 2), "bias": round(d.mean(), 2), "spearman": round(s, 2)}


def main(model="ollama:qwen2.5:7b"):
    h = pd.read_csv(FILE, encoding="utf-8-sig")
    h = h[pd.to_numeric(h["human_accuracy"], errors="coerce").notna()]
    runs = {r["id"]: r for r in db.list_runs()}
    rows = []
    for k, (_, r) in enumerate(h.iterrows(), 1):
        run = runs[r["run_id"]]
        facts = _facts(run["case_id"])
        print(f"[{k}/{len(h)}] run {run['id']} (v{run['version']})", flush=True)
        rows.append({
            "run_id": run["id"], "version": f"v{run['version']}", "human": float(r["human_accuracy"]),
            "old_judge": json.loads(run["scores"]).get("accuracy"),
            "strict": strict_judge(facts, run["output"], model),
            "claims": claim_judge(facts, run["output"], model),
        })
    df = pd.DataFrame(rows)
    df.to_csv("rejudge_results.csv", index=False)
    print("\n=== Agreement with your scores ===")
    out = {}
    for col in ("old_judge", "strict", "claims"):
        ok = df.dropna(subset=[col])
        out[col] = stats(ok, col) | {"parse_fail": len(df) - len(ok)}
    print(pd.DataFrame(out).T.to_string())
    print("\n=== Mean score by version ===")
    print(df.groupby("version")[["human", "old_judge", "strict", "claims"]].mean().round(2).to_string())


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ollama:qwen2.5:7b")
