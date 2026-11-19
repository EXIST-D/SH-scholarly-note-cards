# Checks: what is verified, at which severity, what cannot be verified

`ingest` runs the note checks on every submitted note; `check` runs the card-level checks. **ERROR** = not accepted, fix and
resubmit. **WARN** = accepted, a human should look; listed in `review_checklist.md`. Everything is rule-based and
deterministic; no model is called. The verification protocol is explicit on purpose: "supported by the cited evidence" means
exactly what is listed here and nothing more.

## Note checks
| Check | Rule | Severity |
|---|---|---|
| evidence anchor | `ev` required when `status=reported`; ids must exist (`E001..`), sentence numbers must exist, units in references/acknowledgements are not citable | ERROR (the error names the closest unit) |
| quote verbatim | each quote must occur in the cited units (case, spacing, punctuation, ligatures, hyphenation tolerant) | ERROR if absent; ERROR naming the right unit if it occurs elsewhere; WARN if >= 90 % matches |
| numbers | every number in `text`, `cond` and section-summary fields must occur in the cited evidence (decimals, %, sizes, years; `10^-9` equals `10-9`; `10^13` equals the PDF form `1013`); single digits are ignored; citation markers `[21]`, `Table 2`, years inside citations are not numbers | ERROR (names the unit that contains the number, or says it is not in the paper); WARN if the note says `derived:` |
| wording support | content-word overlap between note and cited evidence (same language only): < 0.12 almost no shared wording, < 0.30 weak | ERROR / WARN, with the closest unit as suggestion |
| strength | evidence sentence (best matching one) is hedged but the note states it as established; claim words (state-of-the-art, first, novel, significantly, outperform ...) absent from the evidence; evidence negation not reflected | WARN |
| section alignment | a `section_summary` must cite units inside its own section (subsections count) | ERROR |
| conditions | a `finding` without `cond:` or `derived:` | WARN |
| atomicity | a non-summary note over 75 words | WARN |
| tags | no tags | WARN |
| duplicates | near-identical wording within the same kind | WARN |
| acronyms | acronym not in the cited evidence and not defined by a `definition` note | WARN |
| not reported | `status=not_reported` / `unclear` needs `searched:` or `note:` | ERROR |

## Card checks (`check`, `next`)
| Check | Rule |
|---|---|
| required fields | question, contribution, data, method, finding, conclusion, limitation: each at least one reported note, or `status=not_reported` |
| section coverage | every non-excluded, non-optional top-level section with >= 25 words (including its subsections) needs a section summary; appendices (letter-numbered), abstract, front matter, contributions/acknowledgements/contents are optional or excluded |
| "not reported" versus the text | a field marked not reported while the cue search finds strong candidates (limitation / future work / availability statements) is a contradiction and is listed |
| cue coverage | strong limitation/assumption sentences and numeric result sentences in results sections that no note uses as evidence are listed (hints, not errors) |
| definitions | the same term defined twice with different wording is flagged as conflicting |
| statistics | accepted / warned / failing notes, quotes verified `x/y`, findings without conditions |

## What is machine-checked and what is not
Machine-checked: evidence ids and citability, verbatim quotes, numbers in evidence, section alignment, required fields,
section coverage, contradictions between "not reported" and the cues. **Needs a human**: whether a note truly captures
the meaning (wording support is only a lexical signal), whether the conditions are complete, whether a warned note is acceptable.
`review_checklist.md` lists every item of the second kind.

## Measured detection (development test, not a platform score)
Defects were injected one at a time into the notes of two finished, correct cards on real public papers (Attention Is All
You Need, 51 notes; GW150914 LIGO paper, 30 notes) and checked with the same `validate_note()` that `ingest` uses
(`dev/seeded_notes_eval.py`). Fictional and real-paper fixtures are in `dev/` and `examples/`.

| injected defect | cases | caught (any) | caught as ERROR |
|---|---|---|---|
| fabricated quote (two words changed) | 38 / 21 | 100 % / 100 % | 100 % / 100 % |
| paraphrase passed off as a quote | 41 / 21 | 100 % / 100 % | 100 % / 100 % |
| anchor points to another section (with quote) | 43 / 21 | 100 % / 100 % | 100 % / 100 % |
| anchor points to another section (no quote) | 43 / 21 | 95 % / 100 % | 79 % / 81 % |
| a number changed | 16 / 12 | 94 % / 100 % | 94 % / 83 % |
| evidence anchor deleted | 50 / 29 | 100 % / 100 % | 100 % / 100 % |
| overclaim added ("proving it is superior ...") | 15 / 9 | 100 % / 100 % | 0 % (WARN by design) |
| hedge replaced by "clearly demonstrates" | 7 / 5 | 43 % / 60 % | 0 % (WARN by design) |
| section summary cites another section | 7 / 8 | 100 % / 100 % | 100 % / 100 % |
| text replaced by an unrelated sentence | 43 / 21 | 86 % / 71 % | 56 % / 52 % |
| negation deleted | 6 / 3 | 33 % / 33 % | 0 % (WARN by design) |
| one section summary removed / all limitation notes removed / "limitation: not reported" although cues exist | - | caught / caught / caught | - |

On the correct notes: 0 error-level false alarms in both cards; 2 and 3 warnings (an acronym not in the cited unit, a hedge
word in another sentence of the unit).

Evidence retrieval (`find`, also used for the "closest unit" suggestions) on the public QASPER validation split (281 NLP
papers, 888 questions with a human-marked evidence paragraph; questions were written from title and abstract only, so this
is a conservative proxy, `dev/qasper_eval.py`): BM25 over paragraphs with section titles gives recall@1 0.23, @3 0.50,
@5 0.64, @10 0.80, MRR 0.41; random choice of 5 paragraphs gives 0.21.

## Blind spots (stated in results when relevant)
- A note that reuses the paper's words but changes the meaning (swapped subject, wrong comparison direction) passes the
  lexical checks; hedge/negation detection depends on word lists (43 % and 33 % above).
- A correct number cited from a unit that happens to contain the same number for another quantity.
- Quality of the summary prose, completeness of conditions beyond the cue search, and which findings are "main".
- Figures as images and formulas as pictures are not in the text layer; numbers there cannot be verified.
