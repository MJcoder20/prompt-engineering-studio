"""Automatic checks + LLM-as-judge rubric."""
import json
import re

from . import llm

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
AR_RE = re.compile(r"[\u0600-\u06FF]")
FOREIGN_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\u0400-\u04ff]")  # CJK + Cyrillic
MARKDOWN_RE = re.compile(r"^\s*(#{1,6}\s|[-*]\s)|\*\*", re.M)
LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")
PLACEHOLDER_RE = re.compile(r"\[[^\]]*\]")


def normalize(text):
    return (text or "").translate(_DIGITS)


def arabic_ratio(text):
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for ch in letters if AR_RE.match(ch)) / len(letters)


def numbers_in(text):
        return {n for n in NUM_RE.findall(normalize(text)) if n.strip("0.,")}

def _latin_in_arabic(output):
    """Count Latin-letter words inside mostly-Arabic text (ignoring [placeholders])."""
    clean = PLACEHOLDER_RE.sub("", output)
    if arabic_ratio(clean) <= 0.2:
        return 0
    return len(LATIN_WORD_RE.findall(clean))

def heuristic_scores(output, variables, reference="", min_words=0, max_words=0, banned=None):
    """Cheap, deterministic checks. The key one: numbers in the output that
    do not appear in the supplied source facts = possible fabrication."""
    source = " ".join(str(v) for v in variables.values()) + " " + (reference or "")
    unsupported = sorted(numbers_in(output) - numbers_in(source))
    words = len(output.split())
    length_ok = (not min_words or words >= min_words) and (not max_words or words <= max_words)
    hits = [b for b in (banned or []) if b.strip() and b.lower() in output.lower()]
    return {
        "words": words,
        "arabic_ratio": round(arabic_ratio(output), 2),
        "unsupported_numbers": unsupported,
        "length_ok": length_ok,
        "banned_hits": hits,
        "foreign_script": bool(FOREIGN_RE.search(output)),
        "latin_words": _latin_in_arabic(output),
        "institution_named": int(str(variables.get("institution", "")) in output),
        "markdown": bool(MARKDOWN_RE.search(output)),
    }


JUDGE_SYSTEM = (
    "You are a strict evaluator of official government communications. "
    "Score the OUTPUT from 1 (poor) to 5 (excellent) on:\n"
    "- accuracy: score ONLY unsupported statements (invented facts, places, numbers, institutions, claims). Do NOT lower accuracy for omitted details, brevity or tone. The institution field is part of the SOURCE.\n"
    "- tone: appropriate, formal, neutral, non-promotional\n"
    "- language_quality: correct, natural, clear writing in the requested language\n"
    'Reply with JSON only: {"accuracy":int,"tone":int,"language_quality":int,"rationale":"one sentence"}'
)


def llm_judge(output, variables, reference, model):
    source = json.dumps(variables, ensure_ascii=False)
    user = f"SOURCE:\n{source}\n\nREFERENCE (optional):\n{reference or 'n/a'}\n\nOUTPUT:\n{output}"
    raw = llm.complete(JUDGE_SYSTEM, user, model, max_tokens=300, temperature=0.0)
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        data = json.loads(m.group(0))
        return {k: data[k] for k in ("accuracy", "tone", "language_quality", "rationale")}
    except Exception:
        return {"accuracy": None, "tone": None, "language_quality": None,
                "rationale": f"unparseable judge reply: {raw[:80]}"}
