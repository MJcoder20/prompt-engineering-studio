"""Human-approval storage. Drafts start 'pending'; only a named reviewer can approve or reject.
Decisions are final: a decided draft is never changed. Rules are enforced here, not only in the UI."""
import json
import os
import sqlite3
from datetime import datetime


def _conn():
    c = sqlite3.connect(os.environ.get("REVIEW_DB", "reviews.db"))
    c.row_factory = sqlite3.Row
    return c


def init():
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS drafts(
            id INTEGER PRIMARY KEY, created_at TEXT, profile TEXT, channel TEXT, model TEXT,
            brief TEXT, text TEXT, auto_passed INTEGER, issues TEXT, attempts INTEGER, history TEXT,
            status TEXT DEFAULT 'pending', reviewer TEXT, decided_at TEXT,
            final_text TEXT, final_issues TEXT, note TEXT)""")


def add_draft(result, brief):
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO drafts(created_at, profile, channel, model, brief, text, auto_passed, issues, attempts, history) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), result["profile"], result["channel"], result["model"],
             json.dumps(brief, ensure_ascii=False), result["text"], int(result["passed"]),
             json.dumps(result["issues"], ensure_ascii=False), result["attempts"],
             json.dumps(result["history"], ensure_ascii=False)))
        return cur.lastrowid


def _row(r):
    d = dict(r)
    for k in ("brief", "issues", "history", "final_issues"):
        d[k] = json.loads(d[k]) if d.get(k) else None
    return d


def list_drafts(status=None):
    with _conn() as c:
        q = "SELECT * FROM drafts" + (" WHERE status=?" if status else "") + " ORDER BY id DESC"
        return [_row(r) for r in c.execute(q, (status,) if status else ())]


def get(draft_id):
    with _conn() as c:
        r = c.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
    return _row(r) if r else None


def decide(draft_id, status, reviewer, final_text, final_issues, note=""):
    if status not in ("approved", "rejected"):
        raise ValueError("status must be 'approved' or 'rejected'")
    if not (reviewer or "").strip():
        raise ValueError("a reviewer name is required")
    if status == "rejected" and not (note or "").strip():
        raise ValueError("a reason is required to reject a draft")
    if status == "approved" and final_issues and not (note or "").strip():
        raise ValueError("approving a draft with open check issues needs an override note")
    with _conn() as c:
        cur = c.execute(
            "UPDATE drafts SET status=?, reviewer=?, decided_at=?, final_text=?, final_issues=?, note=? "
            "WHERE id=? AND status='pending'",
            (status, reviewer.strip(), datetime.now().isoformat(timespec="seconds"), final_text,
             json.dumps(final_issues, ensure_ascii=False), (note or "").strip(), draft_id))
        if cur.rowcount != 1:
            raise ValueError("draft not found or already decided (decisions are final)")
