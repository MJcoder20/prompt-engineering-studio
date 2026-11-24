"""SQLite storage: prompts, versions, test sets, test cases, runs."""
import json
import os
import re
import sqlite3
from datetime import datetime

DB_PATH = os.environ.get("STUDIO_DB", "studio.db")
VAR_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init():
    with conn() as c:
        c.executescript(
            """
        CREATE TABLE IF NOT EXISTS prompts(
            id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS versions(
            id INTEGER PRIMARY KEY, prompt_id INTEGER NOT NULL, version INTEGER NOT NULL,
            system TEXT, template TEXT NOT NULL, notes TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS testsets(
            id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS cases(
            id INTEGER PRIMARY KEY, testset_id INTEGER NOT NULL,
            variables TEXT NOT NULL, reference TEXT);
        CREATE TABLE IF NOT EXISTS runs(
            id INTEGER PRIMARY KEY, version_id INTEGER, case_id INTEGER, model TEXT,
            output TEXT, latency REAL, scores TEXT, created_at TEXT);
        """
        )


# ---------- prompts / versions ----------
def create_prompt(name):
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO prompts(name) VALUES(?)", (name,))
        return c.execute("SELECT id FROM prompts WHERE name=?", (name,)).fetchone()["id"]


def list_prompts():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM prompts ORDER BY name")]


def add_version(prompt_id, system, template, notes=""):
    with conn() as c:
        n = c.execute(
            "SELECT COALESCE(MAX(version),0)+1 AS n FROM versions WHERE prompt_id=?",
            (prompt_id,),
        ).fetchone()["n"]
        cur = c.execute(
            "INSERT INTO versions(prompt_id,version,system,template,notes,created_at) VALUES(?,?,?,?,?,?)",
            (prompt_id, n, system, template, notes, datetime.now().isoformat(timespec="seconds")),
        )
        return cur.lastrowid


def list_versions(prompt_id):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM versions WHERE prompt_id=? ORDER BY version DESC", (prompt_id,))]


def extract_vars(template):
    return sorted(set(VAR_RE.findall(template or "")))


def render(template, variables):
    missing = [v for v in extract_vars(template) if v not in variables]
    if missing:
        raise KeyError(f"Missing variables: {missing}")
    return VAR_RE.sub(lambda m: str(variables[m.group(1)]), template)


# ---------- test sets ----------
def create_testset(name):
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO testsets(name) VALUES(?)", (name,))
        return c.execute("SELECT id FROM testsets WHERE name=?", (name,)).fetchone()["id"]


def list_testsets():
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM testsets ORDER BY name")]


def add_case(testset_id, variables, reference=""):
    with conn() as c:
        c.execute("INSERT INTO cases(testset_id,variables,reference) VALUES(?,?,?)",
                  (testset_id, json.dumps(variables, ensure_ascii=False), reference))


def list_cases(testset_id):
    with conn() as c:
        rows = c.execute("SELECT * FROM cases WHERE testset_id=? ORDER BY id", (testset_id,)).fetchall()
    return [{**dict(r), "variables": json.loads(r["variables"])} for r in rows]


# ---------- runs ----------
def save_run(version_id, case_id, model, output, latency, scores):
    with conn() as c:
        c.execute(
            "INSERT INTO runs(version_id,case_id,model,output,latency,scores,created_at) VALUES(?,?,?,?,?,?,?)",
            (version_id, case_id, model, output, latency, json.dumps(scores, ensure_ascii=False),
             datetime.now().isoformat(timespec="seconds")),
        )


def list_runs():
    with conn() as c:
        rows = c.execute(
            """SELECT r.id, p.name AS prompt, v.version, r.case_id, r.model, r.latency,
                      r.scores, r.created_at, r.output
               FROM runs r JOIN versions v ON v.id=r.version_id
               JOIN prompts p ON p.id=v.prompt_id ORDER BY r.id DESC"""
        ).fetchall()
    return [dict(r) for r in rows]
