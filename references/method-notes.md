# Method notes

## Why this design
Fixed-budget comparison (64 requests, 900 s, 16 384 tokens per response) against the same agent without a Skill. A plain
summary agent reads the paper once, writes a compressed prose summary, cites nothing or only "section 3", and cannot say what it
left out. Four problems in the task statement, and what addresses each:

| problem | what the Skill does |
|---|---|
| 对得上 - skeleton follows the paper | `outline` gives the paper's own heading tree (numbering styles: `3.2`, `V.`, `A.`; Markdown/Word levels normalised; PRL-style `A.` under a Roman section is a subsection); one required `section_summary` per top-level section in paper order, with `link:` to neighbours; summaries must cite their own section |
| 留得住 - question, data, method conditions, findings, limitations, premises | required fields; `cond:` on findings; `assumption` and `limitation` kinds; cue detection lists sentences that state limits, assumptions, contributions, results, data, settings so they are not forgotten; a "not reported" claim is checked against the cues; conflicts inside the paper are first-class (`status=conflict`) |
| 找得回 - anchors down to the sentence, page, bbox | stable unit and sentence ids; quotes verified verbatim; numbers must occur in the cited units; `evidence_index.json` links ids to page/bbox/parser block |
| 用得上 - searchable, comparable, reusable | same schema for every paper; `notes.jsonl` atomic notes with tags and anchors; `search`; `compare`; `card.md` for people, `card.json` for programs; checklist says what a human must confirm |

## Evidence units
PDF text is parsed with reading-order recovery (bundled `parse_pdf.py`, also used by the other Skills of this series).
Figure captions, tables (as pipe tables) and formulas are units; paragraphs cut by figures/columns/pages are re-joined with
a soft-hyphen rule that keeps real compounds. Sentence splitting handles abbreviations, initials, decimals and `et al.`.

## Verification protocol
Following the literature on citation faithfulness (the same outputs get very different unsupported-citation rates under
different verifier strictness; partial support is the hardest case), the protocol is stated and deterministic: existence of
the anchor, verbatim containment of quotes, containment of numbers, a lexical-support score, and a few strength/negation cues
against the best-matching evidence sentences. Whatever cannot be decided by rules goes to the human checklist instead of
being guessed.

## Retrieval
BM25 (k1 1.2, b 0.75) with light stemming, a bigram bonus and section titles prepended to each unit. Used by `find`, by the
"closest unit" suggestions in error messages, and (over notes) by `search`. Measured on QASPER, see `checks.md`.

## Budget
A 10-page paper: `prepare` (1), `outline` (1), `read` x2-4, `ingest` x3-5, fixes x1-3, `next`/`check` (1-2), `assemble`
(1): about 12-16 requests. Reading is chunked (`read --max-words`), writing is in batches, and errors come back immediately so
repairs touch only the failing notes. `assemble` can run after the first batch, so a partial but honest result always exists.

## Known limits
- Rule-based verification: see the blind spots in `checks.md` (meaning reversal with the same words, hedge/negation
  detection by word list, "main finding" selection).
- Cue detection is lexical (English and basic Chinese lists); other languages get no cues.
- PDF quality limits everything: scanned pages need OCR; formulas and plots as images are not in the text layer; tables are
  reconstructed heuristically.
- Section detection relies on headings; papers without headings (letters, some short reports) become one big section.
- Not tested: a run by the evaluation model (DeepSeek) under its real budget; languages other than English and Chinese; papers
  over 30 pages beyond parsing and `prepare`; `.docx` with images or text boxes.
- Development evidence: three real papers (Attention Is All You Need, LIGO GW150914, plus parsing/outline of BERT, ResNet,
  GPT-3), one fictional example, a Chinese test paper, QASPER retrieval. Cards on the two real papers were written by the
  developer through the tool. No comparison against a model without the Skill was run, so no gain over a baseline is claimed.
