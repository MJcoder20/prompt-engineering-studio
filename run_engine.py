"""Try the Content Engine.

  python run_engine.py --demo                       three sample briefs (health, road closure, fee deadline)
  python run_engine.py --profile nablus_municipality --channel public_notice \
      --topic "..." --audience "..." --facts "..."   (write the brief in Arabic)
Add --json to print the full result, --model mock to test offline.
"""
import argparse
import json
import sys

from engine.generate import CHANNELS, generate, list_profiles

SAMPLES = [
    ("moh_palestine", "press_release", {
        "topic": "حملة تطعيم مجانية للأطفال", "audience": "أولياء الأمور",
        "facts": "تُنفَّذ الحملة من 10 إلى 20 كانون الأول 2026. تُقام في جميع مراكز الرعاية الصحية الأولية. الخدمة مجانية. الفئة المستهدفة: الأطفال من عمر 0 إلى 5 سنوات."}),
    ("nablus_municipality", "public_notice", {
        "topic": "إغلاق شارع لصيانة شبكة المياه", "audience": "السكان وسائقي المركبات",
        "facts": "يُغلق الشارع الرئيسي من الساعة 6 صباحًا حتى الساعة 2 ظهرًا يوم الثلاثاء 15 كانون الأول 2026. الطريق البديل عبر شارع القدس. تنفّذ البلدية الأعمال."}),
    ("nablus_municipality", "social_post", {
        "topic": "تمديد مهلة تسديد الرسوم البلدية", "audience": "دافعو الرسوم",
        "facts": "تم تمديد المهلة حتى 31 كانون الثاني 2027. يمكن الدفع إلكترونيًا عبر بوابة البلدية."}),
]


def show(r, as_json):
    if as_json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return
    print(f"[{r['profile']} / {r['channel']}]  passed={r['passed']}  attempts={r['attempts']}  status={r['status']}")
    print(r["text"])
    for i in r["issues"]:
        print("  ! " + i)
    print("-" * 60)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    p = argparse.ArgumentParser()
    p.add_argument("--demo", action="store_true")
    p.add_argument("--profile", choices=list_profiles())
    p.add_argument("--channel", default="press_release", choices=sorted(CHANNELS))
    p.add_argument("--topic"); p.add_argument("--audience"); p.add_argument("--facts")
    p.add_argument("--model"); p.add_argument("--attempts", type=int, default=3)
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    if a.demo:
        for prof, ch, brief in SAMPLES:
            show(generate(prof, brief, ch, a.model, a.attempts), a.json)
    elif a.profile and a.topic and a.audience and a.facts:
        show(generate(a.profile, {"topic": a.topic, "audience": a.audience, "facts": a.facts},
                      a.channel, a.model, a.attempts), a.json)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
