"""Run: python test_review.py   (no model needed)"""
import os
import tempfile

os.environ["REVIEW_DB"] = os.path.join(tempfile.mkdtemp(), "r.db")
from core import llm
from engine import review_store as store

store.init()
RES = {"profile": "moh_palestine", "channel": "press_release", "model": "stub", "text": "نص", "passed": False,
       "issues": ["x"], "attempts": 3, "history": [{"attempt": 1, "text": "نص", "issues": ["x"]}]}
BRIEF = {"topic": "t", "audience": "a", "facts": "f"}

i = store.add_draft(RES, BRIEF)
assert [d["id"] for d in store.list_drafts("pending")] == [i] and store.get(i)["status"] == "pending"

def fails(**kw):
    try:
        store.decide(i, **kw); return False
    except ValueError:
        return True

assert fails(status="approved", reviewer="  ", final_text="t", final_issues=[], note="")          # no reviewer
assert fails(status="rejected", reviewer="Dr A", final_text="t", final_issues=[], note="")        # reject needs reason
assert fails(status="approved", reviewer="Dr A", final_text="t", final_issues=["open"], note="")  # override needs note
assert fails(status="maybe", reviewer="Dr A", final_text="t", final_issues=[], note="")
assert store.get(i)["status"] == "pending"
store.decide(i, "approved", "Dr A", "نص معدّل", ["open"], "reviewed manually")
d = store.get(i)
assert d["status"] == "approved" and d["reviewer"] == "Dr A" and d["final_text"] == "نص معدّل" and d["decided_at"] and d["final_issues"] == ["open"]
assert fails(status="rejected", reviewer="Dr B", final_text="t", final_issues=[], note="late")    # decisions are final
assert store.get(i)["reviewer"] == "Dr A" and not store.list_drafts("pending")

# --- the Streamlit page, end to end with a stubbed model
from streamlit.testing.v1 import AppTest
GOOD = ("العنوان: حملة تطعيم مجانية للأطفال\nالفقرة الأولى: أعلنت وزارة الصحة الفلسطينية عن تنفيذ حملة تطعيم مجانية للأطفال من عمر 0 إلى 5 سنوات، "
        "وذلك من 10 إلى 20 كانون الأول 2026 في جميع مراكز الرعاية الصحية الأولية.\nالفقرة الثانية: وتدعو الوزارة أولياء الأمور إلى مراجعة أقرب مركز صحي خلال هذه الفترة.")
llm.complete = lambda system, user, model, max_tokens=1200, temperature=None: GOOD
at = AppTest.from_file("approval_app.py", default_timeout=60).run()
assert not at.exception, [e.value for e in at.exception]
at.text_input(key="topic").set_value("حملة تطعيم مجانية للأطفال")
at.text_input(key="audience").set_value("أولياء الأمور")
at.text_area(key="facts").set_value("تُنفَّذ الحملة من 10 إلى 20 كانون الأول 2026. تُقام في جميع مراكز الرعاية الصحية الأولية. الخدمة مجانية. الفئة المستهدفة: الأطفال من عمر 0 إلى 5 سنوات.")
at.button(key="gen").click().run()
assert not at.exception, [e.value for e in at.exception]
pend = store.list_drafts("pending")
assert len(pend) == 1 and pend[0]["auto_passed"] == 1 and pend[0]["status"] == "pending"
did = pend[0]["id"]
at.button(key=f"approve_{did}").click().run()                     # no reviewer name yet
assert store.get(did)["status"] == "pending" and any("reviewer" in e.value for e in at.error)
at.text_input(key="reviewer").set_value("Dr Test").run()
at.button(key=f"approve_{did}").click().run()
assert store.get(did)["status"] == "approved" and store.get(did)["reviewer"] == "Dr Test"
print("All review tests passed.")
