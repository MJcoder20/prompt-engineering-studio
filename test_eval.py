"""Run: python test_eval.py   (no model needed; the LLM is stubbed)"""
import re
from core import llm
import eval_engine as ev

FILLER = "ندعو المواطنين الكرام إلى متابعة التفاصيل عبر القنوات الرسمية والتعاون مع الجهات المختصة خلال الفترة القادمة"


def good(user):
    name = re.search(r"Institution: (.+)", user).group(1).strip()
    ch = re.search(r"Channel: (\w+)", user).group(1)
    if ch == "press_release":
        return f"العنوان: خبر جديد من الجهة\nالفقرة الأولى: تعلن {name} عن خبر جديد للمواطنين. {FILLER}\nالفقرة الثانية: {FILLER}"
    if ch == "public_notice":
        return f"العنوان: إعلان مهم للمواطنين\nالنص: تعلن {name} إعلانا جديدا. {FILLER}"
    return f"تعلن {name} خبرا جديدا. {FILLER}"


briefs = ev.load_briefs()
assert len(briefs) == 12 and len({b["id"] for b in briefs}) == 12
assert {b["channel"] for b in briefs} == {"press_release", "public_notice", "social_post"}

llm.complete = lambda system, user, model, max_tokens=1200, temperature=None: good(user)
recs = ev.run_eval(briefs, 1, "stub", 3)
assert len(recs) == 12 and all(r["first_pass"] and r["passed"] and r["attempts"] == 1 for r in recs), \
    [r["final_issues"] for r in recs if not r["passed"]]

def flaky(system, user, model, max_tokens=1200, temperature=None):
    return good(user) if "Previous draft:" in user else "**سيئ** الرياض [x]"
llm.complete = flaky
recs = ev.run_eval(briefs[:4], 2, "stub", 3)
assert all((not r["first_pass"]) and r["passed"] and r["attempts"] == 2 for r in recs)
text = ev.summarize(recs)
assert "first-attempt pass: 0%" in text and "pass after retries: 100%" in text and "mean attempts: 2.00" in text, text
print("All eval tests passed.")
