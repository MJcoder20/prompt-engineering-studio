"""Loads a sample prompt (2 versions) and an Arabic test set so the app has data on first run."""
from core import db

db.init()
pid = db.create_prompt("Press release (MSA)")
if not db.list_versions(pid):
    db.add_version(
        pid, "",
        "Write a press release in Modern Standard Arabic about: {{topic}}.\n"
        "Audience: {{audience}}. Tone: {{tone}}.\nFacts: {{facts}}",
        "v1: naive baseline")
    db.add_version(
        pid,
        "You are a communications officer for a Palestinian public institution. Write in formal "
        "Modern Standard Arabic. Use ONLY the facts provided. Never invent numbers, dates, names or "
        "quotes. Avoid promotional language. If a needed detail is missing, write [يُستكمل].",
        "Write a press release about: {{topic}}.\nAudience: {{audience}}. Tone: {{tone}}.\n"
        "Facts (the only allowed source): {{facts}}\n\n"
        "Structure: headline, one-paragraph lead, 2 short body paragraphs, closing line. 120-180 words.",
        "v2: strict grounding + structure")

tid = db.create_testset("Gov briefs (sample)")
if not db.list_cases(tid):
    cases = [
        {"topic": "Free vaccination campaign for children", "audience": "Parents", "tone": "reassuring",
         "facts": "Campaign runs 10-20 December 2026. Held at all primary health clinics. Free of charge. Ages 0-5."},
        {"topic": "Road closure for water network maintenance", "audience": "Residents and drivers", "tone": "clear and apologetic",
         "facts": "Main Street closed 6am-2pm on 15 December 2026. Alternative route via Al-Quds Road. Work carried out by the municipality."},
        {"topic": "Extension of municipal fee payment deadline", "audience": "Taxpayers", "tone": "neutral",
         "facts": "Deadline extended to 31 January 2027. Online payment available on the municipality portal."},
    ]
    for c in cases:
        db.add_case(tid, c)
print("Seeded.")
