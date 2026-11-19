# Minimal example

> **EXAMPLE - illustrative only.** Everything below was produced by running this Skill on the fictional paper
> `mini_paper.md` in this folder (the study and its numbers do not exist). The notes in `mini_paper.notes.txt` were written by the
> developer to exercise the tool: this is **not** a platform result, not a score and not an official case. Real inputs arrive as
> `/input/case.json` plus the paper.

## 1. Prepare and look at the skeleton
```bash
python3 scripts/nc.py prepare examples/mini_paper.md --work W
python3 scripts/nc.py outline W
```
```
{"file": "mini_paper.md", "lang": "en", "units": 12, "sections": 9, "words": 445, "cue_counts": {"contribution": 1, "result": 3, "data": 2, "limitation": 5, "future": 1}}
Section skeleton to follow (6 top-level sections need a section_summary): §1 Introduction | §2 Study Area and Data | §3 Method | §4 Results | §5 Discussion | §6 Conclusion
OUTLINE of mini_paper.md (en, 10 citable units)
§front (front matter) | L0 | p- | E001..E001 | 8 words (8 with subsections) [optional]
§abs Abstract | L1 | p- | E002..E002 | 64 words (64 with subsections) [optional]  cues: con:1 res:1
§1 Introduction | L1 | p- | E003..E003 | 59 words (59 with subsections)  cues: dat:2
§2 Study Area and Data | L1 | p- | E004..E004 | 60 words (60 with subsections)  cues: lim:1
§3 Method | L1 | p- | E005..E005 | 70 words (70 with subsections)  cues: lim:1
§4 Results | L1 | p- | E006..E008 | 92 words (92 with subsections)  cues: res:2
§5 Discussion | L1 | p- | E009..E009 | 60 words (60 with subsections)  cues: lim:3
§6 Conclusion | L1 | p- | E010..E010 | 32 words (32 with subsections)  cues: fut:1
§s8 References | L1 | p- | E011..E012 | 29 words (29 with subsections) [excluded]
```

## 2. Read, find, and look at the cue sentences
```bash
python3 scripts/nc.py read W --sec 5 --sentences
```
```
## §5 Discussion (p-)
E009 [paragraph p-]
  E009.1 The gain over logistic regression suggests that non-linear interactions between slope and rainfall matter.
  E009.2 The results are limited to one corridor and to the sedimentary and metamorphic lithologies it contains, so transfer to other regions is untested.
  E009.3 Incomplete inventories before 2015 probably bias the model towards larger landslides.
  E009.4 Rainfall is interpolated from only 12 gauges, which cannot resolve convective storms.
```
```bash
python3 scripts/nc.py find W "rainfall gauges convective storms" -k 2
python3 scripts/nc.py cues W --kind limitation --top 4
```
```
E009 [p- §5] (6.7) The gain over logistic regression suggests that non-linear interactions between slope and rainfall matter. The results are limited to one corridor and to the sedimentary and metamorphic lithologies it contains, so transfer to other regions 
E004 [p- §2] (1.9) The corridor crosses sedimentary and metamorphic terrain between 800 m and 3,200 m elevation. The landslide inventory contains 1,284 mapped landslides from 2010 to 2020; inventories before 2015 were compiled from road maintenance logs and a
== limitation (5 candidate sentences; top 4)
  E009.2 [p- §5] The results are limited to one corridor and to the sedimentary and metamorphic lithologies it contains, so transfer to other regions is untested.
  E009.4 [p- §5] Rainfall is interpolated from only 12 gauges, which cannot resolve convective storms.
  E005.4 [p- §3] We assume that the relationship between rainfall and slope failure is stationary over the study period.
  E009.3 [p- §5] Incomplete inventories before 2015 probably bias the model towards larger landslides.
```

## 3. A sloppy first batch is rejected immediately
(wrong AUC 0.91, an unsupported "proven in every region", a limitation whose quote is real but has no anchor)
```bash
python3 scripts/nc.py ingest W <<'EOF'
=== finding
text: The random forest reaches an AUC of 0.91 versus 0.81 for logistic regression and is proven to work in every mountain region.
cond: 5-fold spatial cross-validation.
ev: E006
quote: The random forest reaches an AUC of 0.91
tags: auc
=== limitation
text: Rainfall is interpolated from only 12 gauges.
quote: which cannot resolve convective storms
tags: rainfall
EOF
```
```
stored 2 | ok 0 | warn 0 | ERROR 2 | accepted notes by kind: 
ids: F1* L1*   (* = failing; resubmit with id=<id>)
  F1 WARN quote_approx: quote differs slightly from E006 (94% matches): copy it exactly
  F1 ERROR numbers: numbers not in the cited evidence: 0.91 (not in the paper). Cite the unit that contains them, or add `derived: how you computed it`
  F1 WARN overclaim: claim words not found in the evidence: every, proven
  L1 ERROR no_evidence: no evidence anchor (ev:). Closest unit: E009 [§5] The gain over logistic regression suggests that non-linear interactions between ...
  L1 ERROR quote_other_unit: quote is verbatim but sits in E009 (§5), not in the cited evidence: cite E009
Fix the ERROR notes and resubmit them with the same id (id=...) or `nc.py next W`.
```
Resubmitting with the right anchors replaces the notes; the complete note file `mini_paper.notes.txt` is accepted like this:
```
stored 24 | ok 24 | warn 0 | ERROR 0 | accepted notes by kind: section_summary 6, finding 4, limitation 3, data 2, meta 1, question 1, contribution 1, method 1, setting 1, assumption 1, conclusion 1, future 1, reproducibility 1
ids: A1 C1 D1 D2 F1 F2 F3 F4 K1 L1 L2 L3 M1 P1 Q1 R1 S1 S2 S3 S4 S5 S6 T1 U1   (* = failing; resubmit with id=<id>)
```

## 4. What is still missing, check, assemble
```bash
python3 scripts/nc.py next W
python3 scripts/nc.py check W
python3 scripts/nc.py assemble W --out out --case examples/case.example.json
```
```
NEXT STEPS | elapsed 0s of 900s budget
Nothing blocking. Run `check`, then `assemble`.
{"notes": 24, "accepted": 24, "with_errors": 0, "with_warnings": 0, "missing_required_fields": [], "sections_needing_summary": 6, "sections_missing_summary": [], "limitation_cues": "4/4 covered", "result_cues": "2/2 covered", "quotes_verified": "16/16", "findings_without_condition": 0, "conflicting_definitions": [], "not_reported_contradicted": []}
{"written": "out", "status": "success", "notes": "24 accepted / 0 with errors", "missing_required_fields": [], "sections_missing_summary": [], "quotes_verified": "16/16", "limitation_cues": "4/4 covered", "unfilled_contract_fields": ["reviewer_name"], "contract_found": true}
UNFILLED contract fields (put them in answers.json and re-run assemble --answers): reviewer_name
```
`case.example.json` asks for a field (`reviewer_name`) that cannot be derived, so `assemble` reports it and exits with code 2
instead of inventing a value; put it into `answers.json` and run `assemble --answers answers.json`.

## 5. The card (`out/card.md`, excerpts)
```
## Key fields

### Bibliographic data

- **T1** title: A Lightweight Landslide Susceptibility Model for Mountain Roads; field: landslide susceptibility, geohazards ✓n `[no anchor]`  
  _note:_ Fictional example paper; no venue or year exists.

### Research question / objective

- **Q1** Does a compact model trained on freely available layers still rank susceptible mountain-road sections well when it is validated spatially instead of with random splits? ✓q ✓n `[E003 · p- · §1]`  
  > We therefore ask whether a compact model trained on freely available layers still ranks susceptible road sections well under spatial validation.

### Contribution

- **C1** A random forest on eight terrain and rainfall features for a 310 km mountain road corridor, evaluated with spatial cross-validation against logistic regression. ✓q ✓n `[E002 · p- · §abs]`  
  > a random forest on eight terrain and rainfall features

### Data / materials

- **D1** Landslide inventory of 1,284 mapped landslides from 2010 to 2020; inventories before 2015 were compiled from road maintenance logs. ✓q ✓n `[E004 · p- · §2]`  
  > 1,284 mapped landslides from 2010 to 2020
- **D2** Terrain features come from a 10 m digital elevation model; daily rainfall comes from 12 gauges. ✓q ✓n `[E004 · p- · §2]`  
...
## Section-by-section (the paper's own skeleton)

## §front (front matter) (p-)

## §abs Abstract (p-)

## §1 Introduction (p-)

- **purpose:** Motivates spatially validated susceptibility models for mountain roads.
- **method:** Argues that random-split validation overstates skill because nearby samples are spatially correlated.
- **result:** Poses the question of whether a compact model still ranks road sections well under spatial validation.
- **conclusion:** A spatially validated, compact model is the gap the paper addresses.
```

## 6. Searching the notes
```bash
python3 scripts/nc.py search out "what limits generalisation to other regions" -k 2
```
```
L1 [limitation] (8.9) Results are limited to one corridor and to its sedimentary and metamorphic lithologies; transfer to other regions is untested.  <E009 · p- · §5>
S5 [section_summary] (4.9) The gain suggests non-linear slope-rainfall interactions; results are limited to one corridor, inventories are incomplete before 2015 and rainfall comes from 12 gauges.  <E009 · p- · §5>
```
