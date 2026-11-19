---
name: scholarly-note-cards
description: Turn a research paper (PDF, Word, Markdown/text, LaTeX, JSON) into a structured, evidence-linked note card - research question, data, method with conditions, findings with their premises, limitations and assumptions, definitions, and a summary of every section that follows the paper's own skeleton. Every note points to an addressable evidence unit (E012, sentence E012.3, page, bbox), quotes are verified verbatim by script, numbers must occur in the cited evidence, missing fields and unreported items are stated, and the output is searchable and comparable. Use whenever a task asks to summarise, take notes on, extract fields from, or build a reusable card for a paper and the result must be checkable against the source.
---

# scholarly-note-cards

You read the paper and write the notes. The tool makes them **checkable**: it cuts the paper into addressable evidence
units (`E012`, sentences `E012.3`), shows the paper's own section skeleton and the sentences that look like limitations /
contributions / results, **verifies every note the moment you submit it** (verbatim quote, numbers, wording support,
strength, section alignment), tells you what is still missing, and assembles a card (`card.md` / `card.json`), a searchable
note index and a human-review checklist. Nothing is accepted without an evidence anchor, so nothing is un-sourced.

## When to use
A paper (or a section range) must become notes / a card / section summaries / key-point list / extracted fields, and the
claims must be traceable to the source. Works for English and Chinese papers. Not for free-form "tell me about this paper"
chat answers that need no evidence.

## Quick start (`SK` = directory of this file, installed as `/skills/weekly-skill`; `W=/app/work/nc`)
```bash
python3 $SK/scripts/nc.py prepare /input/<file> --work $W --case /input/case.json   # parse, units, outline, cues
python3 $SK/scripts/nc.py outline $W                      # the paper's own skeleton (section ids, sizes, cue counts)
python3 $SK/scripts/nc.py read $W --sec 3                 # read a section (units with ids); --ids E010-E040 / --page 4 / --sentences
python3 $SK/scripts/nc.py ingest $W <<'EOF'              # submit notes (block format below): verified immediately
=== finding
text: ...
EOF
python3 $SK/scripts/nc.py next $W                         # what is missing / failing, with concrete next steps
python3 $SK/scripts/nc.py check $W                        # whole-card verification and coverage
python3 $SK/scripts/nc.py assemble $W --out /app/output --case /input/case.json   # run early and again at the end
```
Extra: `find $W "query"` (retrieve evidence units), `cues $W --kind limitation`, `search /app/output "query"` (retrieve your
notes), `compare card1.json card2.json` (side-by-side fields), `drop $W ID`. `prepare` options: `--pages 3-9`, `--lang
zh|en`, `--budget 900`, `--ocr auto|off|force` (scanned PDFs).

## Procedure (about 12-16 requests for a 10-page paper)
1. **Read the task** (`/input/case.json`, `task.md`): which paper, which fields, language of the notes, exact
   `output_contract`. Find the input under `/input`; never assume file names. `prepare` prints units, sections, cue counts,
   warnings (unreadable pages, OCR) and the list of top-level sections that each need a section summary.
2. **See the skeleton** with `outline`. Your notes must follow *this* structure and the paper's argument order - not a generic
   abstract template. Sections are listed with ids (`§3`, `§3.2`), pages and unit ranges.
3. **Read** section by section with `read` (use `--sentences` when you need sentence anchors). `cues` / `read --cue limitation`
   list sentences that look like limitations, assumptions, contributions, results: they are hints, not truth.
4. **Write notes** in the block format below, 15-25 notes per batch, and `ingest` them. Errors come back immediately with the
   exact reason and, where possible, the unit that really contains the number or quote. Fix **only the failing notes**
   (resubmit with `id=`). Warnings are things to look at; do not delete them to look clean.
5. **Cover the card**: required fields (question, contribution, data, method, finding, conclusion, limitation: each at least
   one note, or `status=not_reported` with `searched:` saying where you looked) and one `section_summary` per listed
   top-level section (purpose / method / result / conclusion / link to the neighbouring sections).
6. `next` lists what is still missing, uncovered limitation / result sentences and findings without conditions. `check` is
   the final gate (exit code 2 if something blocking remains).
7. **Assemble**. `assemble` writes `card.md`, `card.json`, `notes.jsonl`, `evidence_index.json`, `review_checklist.md`,
   `check_report.json` and `result.json` (every contract field it can derive, plus `case_id`, `status`, `sources`,
   `uncertainty`, `change_records`). Fields it cannot derive are listed: put your values in `/app/work/answers.json` and
   re-run with `--answers`. Run `assemble` once after your first accepted batch (an honest partial result exists early) and
   again at the end.
8. **Report honestly**: status `success` only if required fields and all section summaries exist and no note fails;
   otherwise `partial` with what is missing and why.

## Note block format (no JSON escaping)
```
=== finding id=F3 sec=§4 status=reported conf=high      <- kind; id/sec/status/conf optional (id lets you replace a note)
text: One atomic claim in your own words (one claim per note).
cond: The conditions that make it hold: dataset, setting, assumption, version ("none stated in the paper" if truly none).
ev: E104, E101.2, E110-E112                              <- evidence anchors: unit, sentence, or range; REQUIRED when status=reported
quote: "verbatim snippet copied from the evidence"       <- verified by script; copy exactly; several quotes separated by |||
tags: translation, bleu                                  <- 2-4 lower-case retrieval tags
note: why this is uncertain / how you resolved a conflict
derived: how you computed a value that is not quoted     <- only for computed numbers
```
Kinds: `meta` (title, authors, year, venue, doi, field), `question`, `contribution`, `data`, `method`, `setting`,
`assumption`, `finding`, `conclusion`, `limitation`, `definition` (add `term:`), `future`, `reproducibility`, `relation`,
`section_summary` (needs `sec=§N`; keys `purpose:`, `method:`, `result:`, `conclusion:`, `link:`; `ev` inside that section).
Alternative: JSONL `{"kind":"finding","text":"...","ev":"E104","quote":["..."],"tags":["a"]}` or `ingest $W file.txt`.
Resubmitting the same wording replaces the earlier note (or give `id=`).

## Rules for notes the checker enforces or expects
- **Atomic and anchored**: one claim per note; every reported note needs `ev`; anchor granularity should match the claim
  (a sentence for a number, a unit for a description). Use `find` if you do not know where something is.
- **Quote verbatim** from the evidence (spacing/punctuation tolerant). A quote that is not in the paper is an ERROR; a
  paraphrase is not a quote. A quote found in another unit is an ERROR that names the right unit.
- **Numbers must be in the cited evidence** (decimals, percentages, sizes). Computed values need `derived:`.
- **Findings need conditions** (`cond:`): the dataset, setting, assumption, or version that makes them true - this is what
  keeps conclusions from floating free. Put hypotheses, hedges and "we suspect" in the note as hypotheses.
- **Do not strengthen**: keep hedges (may, suggest), negation, scope ("only", "in this corridor"); the checker warns on
  inflation words not present in the evidence.
- **Conflicts and gaps are content**: if the paper contradicts itself, write a note with `status=conflict` and cite both
  places; if something is absent, `status=not_reported` + `searched:`; if the text is unclear, `status=unclear`.
- **Section summaries cite their own section** (descendants count). Mention how the section connects to its neighbours.
- **Language**: notes may be in any language; quotes stay in the paper's language. If your notes are in a different
  language than the paper, wording-support and acronym checks are skipped; quote, number and anchor checks still apply.
- Do not invent bibliographic data: if title/authors/year are not in the text, say so.

## Exceptions
| Situation | Behaviour | You do |
|---|---|---|
| scanned / image-only PDF | OCR (rapidocr or tesseract) if installed; low confidence flagged; unreadable pages listed | say OCR was used, treat low-confidence text as uncertain; no OCR engine -> report pages as not processed |
| encrypted / corrupt / not a PDF | `prepare` stops with the parser's message | report `refused`/`failed`; do not guess content |
| two-column order, figures, tables as text | reading order recovered; captions and tables are units | table numbers are citable; numbers inside figure images are not - do not read them from memory |
| very long paper | `outline` + `--pages`/`--sec` reading; `next` shows time | summarise sections in priority order (abstract/intro/results/conclusion first), `assemble`, report the rest as not covered |
| no limitation / data statement in the paper | cue search finds nothing | `status=not_reported` + `searched:`; if cues exist the checker rejects the claim and lists them |
| references / acknowledgements | excluded from evidence | do not cite them as evidence |
| no PDF library installed | `prepare` fails to parse | `pip install pymupdf`, or `pdftotext -layout` to a `.txt` and `prepare` that (no page/bbox evidence) |

## Dependencies
Python 3.8+, standard library only for the note workflow. PDF input uses the bundled `scripts/parse_pdf.py` (needs
`pymupdf`, falls back to `pdfplumber`/`pypdf`); OCR needs `rapidocr` (`pip install rapidocr`) or `tesseract`. Markdown,
text, LaTeX, `.docx` (paragraphs, headings, tables) and JSON need nothing extra. No network access is needed at run time.

## Honesty rules (hard)
Never invent text, numbers, pages, citations or bibliographic data; never report `success` with missing fields or failing
notes; say what the checks cannot prove (the review checklist lists the items a human must confirm); never claim scores or
benchmark numbers - the platform records those.

More: `README.md` (human guide and measured checker results), `references/field-dictionary.md` (fields, anchors, outputs),
`references/checks.md` (every check, severity, blind spots), `references/failure-modes.md`, `references/method-notes.md`,
`examples/minimal-example.md`.
