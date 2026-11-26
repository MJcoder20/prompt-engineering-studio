"""Run: python test_engine.py   (no model needed; the LLM is stubbed)"""
from core import llm
from engine import generate as g

BRIEF = {"topic": "حملة تطعيم مجانية للأطفال", "audience": "أولياء الأمور",
         "facts": "تُنفَّذ الحملة من 10 إلى 20 كانون الأول 2026. تُقام في جميع مراكز الرعاية الصحية الأولية. الخدمة مجانية. الفئة المستهدفة: الأطفال من عمر 0 إلى 5 سنوات."}
HEAD = "حملة تطعيم مجانية للأطفال"
P1 = ("أعلنت وزارة الصحة الفلسطينية عن تنفيذ حملة تطعيم مجانية للأطفال من عمر 0 إلى 5 سنوات، "
      "وذلك من 10 إلى 20 كانون الأول 2026 في جميع مراكز الرعاية الصحية الأولية.")
P2 = "وتدعو الوزارة أولياء الأمور إلى مراجعة أقرب مركز صحي خلال هذه الفترة."
GOOD = "\n\n".join([HEAD, P1, P2])
LABELED = f"العنوان: {HEAD}\nالفقرة الأولى: {P1}\nالفقرة الثانية: {P2}"
BAD = "**حملة التطعيم**\nالرياض - 8 ديسمبر. Call 191 now for more information.\n[اسم المنظمة]"

for pid in g.list_profiles():
    assert g.load_profile(pid)["name_ar"]
profile = g.load_profile("moh_palestine")

# --- content and structure checks on assembled text
assert g.check(GOOD, profile, BRIEF, "press_release") == []
bad = " | ".join(g.check(BAD, profile, BRIEF, "press_release"))
for part in ("banned", "numbers", "non-Arabic", "markdown", "placeholder", "institution"):
    assert part in bad, (part, bad)
assert any("weekday" in i for i in g.check(GOOD.replace("في جميع", "يوم الجمعة في جميع"), profile, BRIEF, "press_release"))
assert not any("weekday" in i for i in g.check(GOOD.replace("في جميع", "في الأحداث في جميع"), profile, BRIEF, "press_release"))
assert any("headline" in i for i in g.check("وزارة الصحة الفلسطينية\n\n" + GOOD, profile, BRIEF, "press_release"))
REAL1 = ("تعلن وزارة الصحة الفلسطينية حملة تطعيم مجانية للأطفال. تُنفَّذ الحملة من 10 إلى 20 كانون الأول 2026 في جميع مراكز الرعاية الصحية الأولية. "
         "تدعو الوزارة أولياء الأمور لضمان تلقي أبنائهم التطعيمات اللازمة حسب العمر. الخدمة مجانية ومتاحة للأطفال من عمر 0 إلى 5 سنوات.")
r1 = " | ".join(g.check(REAL1, profile, BRIEF, "press_release"))
assert "separate lines" in r1 and "headline" in r1, r1

# --- claim terms: only allowed when the facts contain them (institution name is excluded)
claim = " | ".join(g.check(GOOD.replace(P2, "وتوفر الحماية اللازمة للأطفال ضد الأمراض المعدية."), profile, BRIEF, "press_release"))
assert "أمراض" in claim and "حماية" in claim, claim
REAL2 = GOOD.replace(P2, "ندعو أولياء الأمور لتقديم أطفالهم للمشاركة في هذه الحملة، حيث ستكون الخدمة مجانية وستهدف إلى تطعيم الأطفال ضد أمراض معدية.")
assert any("أمراض" in i for i in g.check(REAL2, profile, BRIEF, "press_release")), "real Qwen output must be flagged"
assert "فلسطين" in " | ".join(g.check(GOOD.replace(HEAD, HEAD + " في فلسطين"), profile, BRIEF, "press_release"))
BRIEF2 = {**BRIEF, "facts": BRIEF["facts"] + " تهدف الحملة إلى حماية الأطفال من الأمراض المعدية."}
assert not any("not in the facts" in i for i in g.check(GOOD.replace(P2, "وتدعو الوزارة إلى حماية الأطفال من الأمراض المعدية."), profile, BRIEF2, "press_release"))

# --- section parsing
parts, missing = g.parse_sections(LABELED, "press_release")
assert not missing and parts["العنوان"] == HEAD and parts["الفقرة الثانية"] == P2
parts, missing = g.parse_sections(REAL1, "press_release")
assert len(missing) == 3
parts, missing = g.parse_sections("العنوان: عنوان\nالنص: فقرة\nأخرى", "public_notice")
assert not missing and parts["النص"] == "فقرة\nأخرى"

# --- generate loop (stubbed model)
replies = iter([BAD, LABELED])
llm.complete = lambda system, user, model, max_tokens=1200, temperature=None: next(replies)
r = g.generate("moh_palestine", BRIEF, model="stub")
assert r["passed"] and r["attempts"] == 2 and r["status"] == "draft_for_review" and r["text"] == GOOD, r["issues"]

llm.complete = lambda *a, **k: REAL1          # model ignores the labeled format every time
r = g.generate("moh_palestine", BRIEF, model="stub")
assert not r["passed"] and r["attempts"] == 3 and any("labeled sections" in i for i in r["issues"])

llm.complete = lambda *a, **k: BAD
r = g.generate("moh_palestine", BRIEF, model="stub")
assert not r["passed"] and r["attempts"] == 3 and r["issues"]

for bad_brief in ({"topic": "x"}, {}):
    try:
        g.generate("moh_palestine", bad_brief, model="stub"); raise SystemExit("should fail")
    except ValueError:
        pass
# retries raise the temperature a little so a retry can differ from the previous draft
temps = []
def rec(system, user, model, max_tokens=1200, temperature=None):
    temps.append(round(temperature, 2)); return BAD
llm.complete = rec
g.generate("moh_palestine", BRIEF, model="stub", temperature=0.3)
assert temps == [0.3, 0.45, 0.6], temps
assert "begin the first sentence" in " | ".join(g.check(GOOD.replace("وزارة الصحة الفلسطينية", "الوزارة"), profile, BRIEF, "press_release"))
print("All engine tests passed.")
