# Case study: testing prompts for Arabic government communications

## Problem

A government communication tool must not invent facts. A press release with a wrong country, a made-up phone number or an unsupported health claim is worse than no release. I wanted a way to compare prompt versions with evidence, not impressions, using a local open model (Qwen 2.5 7B via Ollama) so that no text leaves the machine.

## What I built

A Streamlit tool with versioned prompts, `{{variable}}` templates, test sets, repeated runs, side-by-side Arabic output, deterministic checks and an LLM judge. I then built tooling to measure how far the judge could be trusted.

## Prompt iterations

| Version | Idea | Outcome |
|---|---|---|
| v1 | Plain instruction | Invented a country, date and phone number in most outputs; leaked Chinese and Latin text; mistranslated "press release" as a phrase meaning "release from custody" |
| v2 | Use only supplied facts, fixed structure | No fabricated numbers; still invented an institution; misused a placeholder |
| v3 | Plain text, no dateline, placeholder only inside sentences | Cleaner, but garbled tokens at default temperature |
| v4 | Required `institution` variable plus one example | Not better than v3; the model inserted the placeholder in outputs where nothing was missing |
| v5 | Removed placeholders, match tense to the facts, name the institution | Best on the automatic checks |

## Findings

**1. Deterministic checks were the reliable signal.** Across repeated runs (3 cases x 3 repeats per version), v1 averaged about 1.4 to 1.6 fabricated numbers per output and 5 to 8 stray Latin words, while v2 and v3 had zero fabricated numbers. With banned phrases enabled, v1 averaged 2.33 hits per output against 0.22 for v2 and v3.

**2. Input language mattered as much as prompt wording.** English audience and tone values in the test cases leaked English words into the Arabic ("Residents", "Taxpayers"). Rewriting the test inputs in Arabic and lowering temperature to 0.3 brought Latin-word leakage to zero for v3 and v4. The cases also changed slightly, so this is consistent with, not proof of, the cause.

**3. A prompt instruction can backfire.** My v3 and v4 prompts told the model to use a placeholder where a detail was missing. The model started inserting it everywhere, once even as a verb. In v3 and v4, 0.89 banned hits per output were the placeholder and a wrong-tense phrase ("was closed" for a scheduled closure). Removing the instruction in v5 brought this to 0.

**4. The LLM judge was noisy and wrong in a systematic way.**
- The same prompt and test set scored 3.78 accuracy in one run and 3.00 in the next.
- Against 24 outputs I scored by hand (blind to version and judge score): exact agreement 21%, within one point 62%, mean absolute error 1.29, bias -1.29 (judge harsher than me), Spearman correlation 0.36.
- It ranked v5 last on accuracy, while my scores ranked it first.
- Its written reasons showed why: it penalized *omitted* details and tone as "accuracy" problems, flagged a sentence that was in the source as an addition, and often replied in Chinese.

**5. Can the judge be fixed? Partly.** I re-judged the same 24 outputs with two alternative prompts, without regenerating anything or changing my scores.

| Judge | Exact | Within 1 | MAE | Bias | Spearman | Parse fails |
|---|---|---|---|---|---|---|
| Original | 21% | 62% | 1.29 | -1.29 | 0.36 | 0 |
| Strict (score only unsupported statements; ignore omissions and tone; English reply) | 43% | 91% | 0.65 | +0.30 | 0.28 | 1 |
| Claim-checking (list claims, mark each supported, score computed in code) | 29% | 71% | 1.08 | +0.67 | -0.35 | 0 |

The strict prompt fixed calibration: error halved and bias near zero, and by version it no longer ranked v5 last (v1 lowest, v5 tied highest, matching my ordering at the extremes). It did not improve output-level ranking (Spearman 0.28) and still rated v1, the weakest prompt, at 4.0 on average where I gave 3.3. The claim-checking judge failed: its scores (v1 at 5.0, negative correlation) are consistent with the 7B model marking almost every claim as supported. I adopted the strict judge as a secondary signal and kept the deterministic checks as the pass/fail gate. [ADD: the constant-4 baseline figure from the check above.]

## Errors the checks did not catch

- Wrong weekdays (all versions called 15 December 2026 a Wednesday or Thursday; it is a Tuesday). I added the weekday to the test facts and banned the wrong ones.
- Wrong tense for scheduled events, caught only through a banned-phrase workaround.
- Small grammar errors in Arabic, and invented details that are not numbers or names.

## Limitations

- Three cases per test set, and about 5 hand-scored samples per version. Differences between v3, v4 and v5 in human scores are not statistically meaningful.
- One annotator without domain expertise; my scores may be lenient (I gave v1 a 3.3 on average despite fabricated countries and numbers).
- A 7B local model for both generation and judging.
- The exact-match institution check is strict by design.
- Evaluating one bilingual output exposed two flaws in my own checks: the Latin-word check was skipped when text was near 50% Arabic, and the number check split times like 6:00 into separate numbers. I fixed both, but earlier runs were scored with the old checks.
- Even the final prompt (v5) occasionally invented a completion claim ("the work was carried out successfully" for a closure that had not happened yet), used the institution name as the headline, and made small Arabic grammar errors. The deterministic checks do not catch these without per-phrase banned lists.

## What I would do next

- Expand to 20+ cases across health, municipal and emergency notices, with a second annotator.
- Use a larger or different judge model and compare.
- Add checks for dates and weekdays against supplied facts.
- Feed the winning prompt into a content engine with retrieval over institution style guides.
- Add checks for completion claims and weekdays against the supplied facts, and test a v6 that asks for a content headline separate from the institution name.

## Content Engine: generate, check, revise

I built a second module that drafts Arabic communications from a brief and an institution profile, runs every draft through the Studio's deterministic checks, and feeds the problems back to the model for up to three attempts. Every result is marked `draft_for_review`.

**Evaluation:** 12 fictional briefs (several designed to tempt the model: sparse facts, a named person, a phone number, medical topics), 3 runs each, Qwen 2.5 7B.

| | First-attempt pass | After retries | Mean attempts |
|---|---|---|---|
| Run 1 | 58% | 86% | 1.58 |
| Run 2 | 72% | 97% | 1.31 |

**What I found:**
- The retry loop does most of the work: in run 2, 72% of drafts pass first time and 97% after retries.
- One brief failed all 9 attempts in run 1 with three identical drafts. The cause was my own instruction: the social-post prompt said "key fact first", which conflicted with the check requiring the institution name. I fixed the instruction, made the feedback say exactly what to do, and raised the temperature slightly on retries. Social posts went from 56% to 100% after retries.
- The checks caught the model inventing facts: praise words ("improving quality"), a medical claim ("protects against diseases") and a computed end date for a campaign that only gave a start date and a duration.
- Structure rules in plain prose were unreliable for a 7B model (headlines and paragraph counts failed after three attempts). Asking for labeled sections that my code parses and assembles fixed it.
- A check written for one phrasing missed the next: the Arabic definite article "ال" broke a term match until I switched to stems.

**Limitations:** one run per configuration, and I changed three things at once between runs, so the gain isn't attributable to one change. The briefs are fictional and written by me. A pass means the automatic checks pass: small embellishments and grammar slips still get through, which is why a human must approve every draft.

## Responsible AI notes

Outputs are drafts for human review; nothing is published automatically. The tool runs locally, which fits the data-sovereignty needs of government use. The main risk found was confident fabrication, which is why the checks target unsupported facts first.
