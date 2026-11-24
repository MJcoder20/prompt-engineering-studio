"""Smoke tests: run with `python test_core.py` (uses a temp DB and the mock model)."""
import os, tempfile
os.environ["STUDIO_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
from core import db, scoring, llm

db.init()
assert db.extract_vars("Hi {{a}} and {{ b }}") == ["a", "b"]
assert db.render("Hi {{a}}", {"a": "x"}) == "Hi x"
try:
    db.render("{{a}}{{z}}", {"a": 1}); raise SystemExit("should fail")
except KeyError:
    pass
pid = db.create_prompt("p")
v1 = db.add_version(pid, "", "T {{x}}"); v2 = db.add_version(pid, "", "T2 {{x}}")
assert [v["version"] for v in db.list_versions(pid)] == [2, 1]
s = scoring.heuristic_scores("سيُقام الحدث في 10 ديسمبر وسيحضر 500 شخص", {"facts": "Event on 10 December"})
assert s["unsupported_numbers"] == ["500"], s
assert scoring.arabic_ratio("مرحبا") == 1.0
j = scoring.llm_judge("x", {"a": 1}, "", "mock")
assert j["accuracy"] is None  # mock reply is not JSON -> graceful fallback
assert llm.complete("", "hello", "mock").startswith("[MOCK")
print("All tests passed.")
