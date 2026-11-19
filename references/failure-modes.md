# Failure modes and handling

| Symptom | Cause | Action |
|---|---|---|
| `prepare`: "PDF parsing failed" | encrypted / corrupt / unreadable PDF | report the message; ask for the password or a copy; never guess content |
| `prepare` warns about unreadable pages | scanned pages without OCR engine, image-only pages | report them as not processed; `pip install rapidocr` if allowed and re-run |
| "no readable text found" | empty file, wrong format, `--pages` outside the document | check input and `--pages` |
| outline looks flat or odd (a section missing, a label like "Decoder:" as heading) | PDF typography, run-in headings | trust `read --page` for the real text; section summaries only need to cover what `outline` lists as top level; mention the oddity in `uncertainty` |
| a paragraph appears cut in two units | a break the parser could not join | cite both units |
| `ingest`: no evidence anchor | `ev:` missing | use `find "<claim words>"` and cite the unit; the error already names the closest unit |
| ERROR quote not found | paraphrase or typo | copy the sentence from `read` output exactly, or drop `quote:` |
| ERROR quote is in another unit | anchor and quote disagree | cite the unit named in the error |
| ERROR numbers not in the cited evidence | wrong anchor, a computed value, or a typo | cite the unit named in the error; add `derived:` for computed values; do not "round" quietly |
| ERROR section_alignment | a section summary cites another section | cite units inside that section (subsections count) |
| ERROR not_reported_unexplained | `status=not_reported` without `searched:` | say where you looked (sections, `cues` kinds) |
| check: "reported as not reported but the text has candidates" | the cue search found limitation / future-work / availability sentences | read them; write the notes or explain why they are not that |
| check: sections missing summary | a listed top-level section has none | write `=== section_summary sec=§N` with `ev` inside it |
| WARN weak support / strength / acronym | wording mismatch, inflation, undefined acronym | verify against the evidence; fix when real; leave when acceptable (the human checklist keeps it) |
| two notes with the same wording | resubmission without `id` | the later one replaces the earlier (same kind, similar wording); use `drop` to delete a note |
| paper language differs from note language | detection by character ratio | quotes stay in the paper's language; lexical and acronym checks are skipped, quote/number/anchor checks stay |
| `assemble` exit code 2 | contract fields it cannot derive | fill them in `answers.json`, run `assemble --answers` again |
| `LOW TIME` in `next` | budget almost used | `assemble` now; report uncovered sections as not covered |

Reporting template for a partial run: `status`, notes accepted/failing, missing required fields and sections with reason,
items needing a human, what was tried.
