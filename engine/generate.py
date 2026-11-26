"""Content Engine, piece 1: institution style profiles + generate -> check -> revise loop.

    from engine.generate import generate
    result = generate("moh_palestine", {"topic": ..., "audience": ..., "facts": ...}, channel="press_release")

Every result has status "draft_for_review": nothing is ever marked approved automatically.
"""
import json
import os
import re

from core import llm, scoring

PROFILE_DIR = os.path.join(os.path.dirname(__file__), "profiles")

# Lessons from the Prompt Engineering Studio, enforced as hard checks.
GLOBAL_BANNED = ["الرياض", "السعودية", "الإمارات", "الإفراج", "بنجاح", "تم إغلاق", "يُستكمل",
                 "the best ever", "guaranteed", "أفضل على الإطلاق"]
WEEKDAYS = ["الأحد", "الإثنين", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"]
PLACEHOLDER_RE = re.compile(r"\[[^\]]*\]")

CHANNELS = {
    "press_release": {
        "min_words": 30, "max_words": 120, "headline": True, "min_lines": 3, "sections": ["العنوان", "الفقرة الأولى", "الفقرة الثانية"],
        "instructions": ("A headline that describes the news (never the institution name alone), then two short "
                         "paragraphs. The first sentence of the first paragraph names the institution."),
    },
    "public_notice": {
        "min_words": 20, "max_words": 80, "headline": True, "min_lines": 2, "sections": ["العنوان", "النص"],
        "instructions": "A one-line headline, then 2 to 3 sentences with the key facts and any action required.",
    },
    "social_post": {
        "min_words": 10, "max_words": 50, "headline": False, "min_lines": 1, "sections": [],
        "instructions": "One short post of 2 to 3 sentences with the key fact first. No hashtags, no emojis.",
    },
}
REQUIRED_PROFILE_KEYS = ["id", "name_ar", "kind", "tone", "style_notes", "preferred_phrases", "banned_phrases"]


def load_profile(profile_id):
    path = os.path.join(PROFILE_DIR, f"{profile_id}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"No profile '{profile_id}'. Available: {list_profiles()}")
    with open(path, encoding="utf-8") as f:
        profile = json.load(f)
    missing = [k for k in REQUIRED_PROFILE_KEYS if k not in profile]
    if missing:
        raise ValueError(f"Profile '{profile_id}' is missing keys: {missing}")
    return profile


def list_profiles():
    return sorted(f[:-5] for f in os.listdir(PROFILE_DIR) if f.endswith(".json"))


def parse_sections(raw, channel):
    """Split a labeled draft into {label: text}. Returns (parts, missing_labels)."""
    labels = CHANNELS[channel]["sections"]
    pat = re.compile(r"^[\s*#\-]*(" + "|".join(re.escape(l) for l in labels) + r")[ \t]*[:：][ \t]*", re.M)
    found = list(pat.finditer(raw))
    parts = {}
    for i, m in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(raw)
        parts.setdefault(m.group(1), raw[m.end():end].strip())
    return parts, [l for l in labels if not parts.get(l)]


def build_prompt(profile, brief, channel):
    ch = CHANNELS[channel]
    notes = "\n".join(f"- {n}" for n in profile["style_notes"])
    phrases = "، ".join(profile["preferred_phrases"])
    system = (
        f"You are a communications officer for {profile['name_ar']} ({profile['kind']}). "
        "Write ONLY in formal Modern Standard Arabic, in plain text with no markdown, no hashtags and no emojis. "
        "Use ONLY the facts provided. "
        f"Use the institution name exactly as given: {profile['name_ar']}. Never name any other institution. "
        "Never invent numbers, dates, weekdays, places, phone numbers, websites, procedures, promises or health claims. "
        "Do not add a dateline. Match the tense to the facts: a scheduled event is written in the present or future, "
        "never as already done, and never claim that work was completed or succeeded unless the facts say so. "
        "If a detail is missing, leave it out; never write placeholders in square brackets. "
        "Never output English words or Latin letters. "
        "Inflect names of audience groups correctly for their role in the sentence "
        "(for example, use the accusative after verbs such as ننصح and ندعو).\n"
        f"Tone: {profile['tone']}.\nStyle notes:\n{notes}\nPreferred phrasing (use where natural): {phrases}"
    )
    fmt, tail = "", "Output only the Arabic text."
    if ch["sections"]:
        fmt = ("\nFormat: write exactly these labeled sections, each label at the very start of its own line, "
               "followed by a colon and then the text:\n" + "\n".join(f"{l}: ..." for l in ch["sections"]))
        tail = "Output only the labeled sections."
    user = (
        f"Institution: {profile['name_ar']}\nChannel: {channel}. {ch['instructions']}\n"
        f"Topic: {brief['topic']}\nAudience: {brief['audience']}\n"
        f"Facts (the only allowed source): {brief['facts']}\n"
        f"Length: {ch['min_words']} to {ch['max_words']} words in total.{fmt}\n{tail}"
    )
    return system, user


def check(text, profile, brief, channel, structure=True):
    """Return a list of plain-English issues; an empty list means all checks pass."""
    ch = CHANNELS[channel]
    variables = {"institution": profile["name_ar"], **{k: str(v) for k, v in brief.items()}}
    banned = GLOBAL_BANNED + profile.get("banned_phrases", [])
    s = scoring.heuristic_scores(text, variables, "", ch["min_words"], ch["max_words"], banned)
    issues = []
    if s["unsupported_numbers"]:
        issues.append("contains numbers that are not in the facts: " + ", ".join(s["unsupported_numbers"]))
    if s["banned_hits"]:
        issues.append("contains banned or unsupported wording: " + ", ".join(s["banned_hits"]))
    if s["foreign_script"] or s.get("latin_words", 0):
        issues.append("contains non-Arabic words or script; write Arabic only")
    if s["markdown"]:
        issues.append("uses markdown formatting; write plain text")
    if not s["length_ok"]:
        issues.append(f"length must be {ch['min_words']} to {ch['max_words']} words (it has {s['words']})")
    if profile["name_ar"] not in text:
        issues.append(f"does not name the institution exactly as given: {profile['name_ar']}")
    if PLACEHOLDER_RE.search(text):
        issues.append("contains a placeholder in square brackets; leave missing details out instead")
    source = " ".join(str(v) for v in brief.values())
    for day in WEEKDAYS:
        pat = r"(?<![\u0600-\u06FF])" + day + r"(?![\u0600-\u06FF])"
        if re.search(pat, text) and not re.search(pat, source):
            issues.append(f"states a weekday that is not in the facts: {day}")
    text_wo_name = text.replace(profile["name_ar"], "")
    for term in profile.get("claim_terms", []):
        if term in text_wo_name and term not in source:
            issues.append(f"mentions something that is not in the facts: {term}")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not structure:
        return issues
    if len(lines) < ch["min_lines"]:
        issues.append(f"needs at least {ch['min_lines']} separate lines (headline and paragraphs); it has {len(lines)}")
    if ch["headline"] and lines:
        first = lines[0]
        if first.strip(" .:،") == profile["name_ar"]:
            issues.append("the headline is just the institution name; write a headline that describes the news")
        elif len(first.split()) > 12 or first.endswith("."):
            issues.append("the first line must be a short headline of at most 12 words with no full stop")
    return issues


def generate(profile_id, brief, channel="press_release", model=None, max_attempts=3, temperature=0.3):
    if channel not in CHANNELS:
        raise ValueError(f"Unknown channel '{channel}'. Options: {sorted(CHANNELS)}")
    missing = [k for k in ("topic", "audience", "facts") if not str(brief.get(k, "")).strip()]
    if missing:
        raise ValueError(f"Brief is missing: {missing}")
    profile = load_profile(profile_id)
    model = model or llm.DEFAULT_MODEL
    system, user = build_prompt(profile, brief, channel)
    history, prompt = [], user
    for attempt in range(1, max_attempts + 1):
        raw = llm.complete(system, prompt, model, temperature=temperature).strip()
        labels = CHANNELS[channel]["sections"]
        parts, missing = parse_sections(raw, channel) if labels else ({}, [])
        if missing:
            text = raw
            issues = check(text, profile, brief, channel, structure=False)
            issues.append("write the answer with these labeled sections, each label at the start of its own line "
                          "followed by a colon: " + "، ".join(labels) + " (missing: " + "، ".join(missing) + ")")
        else:
            text = "\n\n".join(parts[l] for l in labels) if labels else raw
            issues = check(text, profile, brief, channel)
        history.append({"attempt": attempt, "raw": raw, "text": text, "issues": issues})
        if not issues:
            break
        prompt = (user + "\n\nPrevious draft:\n" + raw + "\n\nProblems found:\n- " + "\n- ".join(issues)
                  + "\n\nWrite a corrected version that fixes every problem, in the same labeled format. Output only the corrected text.")
    best = min(history, key=lambda h: (len(h["issues"]), -h["attempt"]))
    return {"profile": profile_id, "channel": channel, "model": model, "text": best["text"],
            "issues": best["issues"], "passed": not best["issues"], "attempts": len(history),
            "status": "draft_for_review", "history": history}
