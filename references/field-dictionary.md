# Field dictionary, anchors and outputs

## Evidence units and anchors
`prepare` turns the paper into **units** with stable ids `E001, E002, ...` in reading order: paragraph, list_item, caption,
footnote, table (as a pipe table), formula, title, abstract, front matter. Each unit stores `section`, `page(s)`,
`bbox` and (PDF) the parser block id. Sentences inside a unit are addressable as `E012.3` (1-based), ranges as `E012.2-4`
or `E010-E014` (units). References / acknowledgements / contents are marked `excluded` and cannot be cited.
Sections have ids from the paper's numbering (`§3`, `§3.2`, `§V`, `§A`) or `§s<n>`; `§abs` is the abstract and `§front` the
front matter. A paragraph cut by a figure, column or page is re-joined (its pages list contains both pages).

## Note kinds (card fields)
| kind | card field | required | meaning |
|---|---|---|---|
| meta | meta | no | title, authors, year, venue, doi, field (never invented; hints are auto-extracted: parsed title, years, DOI, arXiv id) |
| question | question | yes | what the paper asks or sets out to do, and why |
| contribution | contributions | yes | what the authors claim to add (keep "to the best of our knowledge" hedges) |
| data | data | yes | datasets, samples, instruments, sizes, sources, time spans |
| method | methods | yes | approach, model, procedure, analysis |
| setting | settings | no | hyper-parameters, protocol details, versions, thresholds |
| assumption | assumptions | no | premises that must hold for conclusions to hold |
| finding | findings | yes | result + `cond:` (the conditions) |
| conclusion | conclusions | yes | what the authors conclude or recommend |
| limitation | limitations | yes | weakness, scope limit, failure case, threat to validity |
| definition | definitions | no | concept / variable / abbreviation (`term:`) |
| future | future_work | no | what is left open |
| reproducibility | reproducibility | no | code, data, models, links |
| relation | relations | no | how it builds on or differs from cited work |
| section_summary | section_summaries | per section | `sec=§N`; `purpose`, `method`, `result`, `conclusion`, `link` |

Common keys: `text`, `cond`, `ev`, `quote`, `tags`, `note`, `status` (`reported` default, `not_reported`, `unclear`,
`conflict`), `conf` (`high|medium|low`), `derived`, `searched`, `id`, `term`. IDs are assigned automatically per kind
(`F1`, `L2`, `S3` ...) and printed by `ingest`.

## Output files (`assemble --out`)
| file | content |
|---|---|
| `card.md` | readable card: metadata, key fields with anchors `[E031.2 · p5 · §4.2]`, marks ✓q (quote verified) ✓n (numbers found), quotes, conditions; section-by-section in the paper's own order with purpose/method/result/conclusion/link; verification table; what is machine-checked vs needs a human |
| `card.json` | schema `scholarly-note-cards/1`: `meta`, `summary`, `skeleton` (paper order, has_summary), `fields` (all kinds), `sections` (outline + summary), `verification` |
| `notes.jsonl` | one atomic note per line: text, cond, kind, tags, anchors (rendered), pages, sections, source block ids, bboxes, quotes, verification status and issues - ready for retrieval and reuse |
| `evidence_index.json` | every unit with id, type, section, pages, bbox, block, text, sentences (the source of every anchor) |
| `review_checklist.md` | failing notes, missing items, warnings to confirm, uncovered limitation/result sentences, low-confidence/flagged notes, not-reported items with where they were searched |
| `check_report.json` | statistics and coverage |
| `result.json` | `case_id`, every field of the case's `output_contract`, plus `status`, `sources`, `uncertainty`, `change_records`, `card`, `verification`, `human_review`, and `_meta` (contract fields, **unfilled fields**, files) |

`status` is `success` only when required fields and all required section summaries exist, no note fails, no "not reported"
claim is contradicted, and the input was read completely; else `partial` (something accepted) or `failed`.

## How `result.json` fields are derived
Matched case-insensitively: `summary`/`abstract`/`overview`/`tldr`; `title`/`metadata`/`meta`; `question`/`research_question`/
`objective`; `data`/`datasets`/`materials`; `methods`/`approach`; `findings`/`results`/`key_findings`; `conclusions`;
`limitations`; `assumptions`/`premises`/`conditions`; `contributions`; `definitions`/`glossary`/`knowledge_points`/`key_terms`;
`future_work`; `reproducibility`; `sections`/`section_summaries`; `structure`/`outline`/`skeleton`; `notes`/`atomic_notes`;
`evidence`/`anchors`/`provenance`; `verification`/`checks`/`qa`; `human_review`/`review_items`; `tags`/`keywords`;
`status`; `sources`; `uncertainty`; `change_records`; `card`. Anything else is `null` and listed in `_meta.unfilled_fields`
and on stdout (exit code 2); `answers.json` values always win. Nothing is invented.

## Searching and comparing
`search OUT "query" [--kind finding] [-k 8]` ranks notes (BM25 over text, conditions, tags, terms and section-summary
fields). `compare card1.json card2.json [--fields question,data,methods,findings,limitations] [--format md|csv]` prints one
row per paper - the card fields are the same for every paper, so cards are comparable side by side.
