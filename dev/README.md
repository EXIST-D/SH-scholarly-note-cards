# dev tools and fixtures (not part of the Skill runtime)

- `seeded_notes_eval.py WORK_DIR` - injects one defect at a time into a finished correct card and measures how often `ingest`'s verifier
  catches it (set `NC_SCRIPTS=../scripts` if needed).
- `qasper_eval.py` - evidence-retrieval recall on the public QASPER validation split; put `qasper_validation.parquet` next to it
  (download: `https://huggingface.co/datasets/allenai/qasper/resolve/refs%2Fconvert%2Fparquet/qasper/validation/0000.parquet`, CC BY 4.0) and `pip install pyarrow`.
- `attention_notes.txt`, `ligo_notes.txt` - notes written by the developer through the tool for two public papers
  (arXiv:1706.03762, arXiv:1602.03837; short verbatim quotes for verification only). Reproduce a card:
  `python3 ../scripts/nc.py prepare <paper.pdf> --work W && python3 ../scripts/nc.py ingest W attention_notes.txt && python3 seeded_notes_eval.py W`
  (PDFs are not included; download them from arXiv. Unit ids depend on the parse, so notes assume the PyMuPDF backend of this Skill.)
- `zh_paper.md` - a tiny Chinese test paper used to check Chinese handling.
