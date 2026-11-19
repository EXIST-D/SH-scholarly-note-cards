#!/usr/bin/env python3
"""Evidence-retrieval evaluation on the public QASPER validation split (allenai/qasper, CC BY 4.0; 281 NLP papers with human evidence annotations).

For every question that has a paragraph as gold evidence, the paper's paragraphs are ranked with the same BM25 (+ section titles) that `nc.py find`
uses; we report recall@k and MRR, and a random baseline. QASPER questions were written from title and abstract only, so this is a hard,
conservative proxy for "can the tool find the unit that supports a statement".

usage: python3 qasper_eval.py [N_PAPERS]      (needs pyarrow; downloads nothing - put qasper_validation.parquet next to this file)
data:  https://huggingface.co/datasets/allenai/qasper/resolve/refs%2Fconvert%2Fparquet/qasper/validation/0000.parquet
"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
for cand in (os.environ.get("NC_SCRIPTS"), os.path.join(HERE, "..", "scripts"), os.path.join(HERE, "..", "submission", "scripts")):
    if cand and os.path.isdir(cand):
        sys.path.insert(0, cand)
        break
import nlib  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402


def units_of(p):
    ft = p["full_text"]
    return [(sec, para) for sec, paras in zip(ft["section_name"], ft["paragraphs"]) for para in paras if para and para.strip()]


def evaluate(papers, variant):
    hits = {1: 0, 3: 0, 5: 0, 10: 0}
    n = 0
    mrr = 0.0
    for p in papers:
        units = units_of(p)
        texts = [((u[0] or "") + " " + u[1]) if variant == "section" else u[1] for u in units]
        sq = [nlib.squash(u[1]) for u in units]
        bm = nlib.BM25(texts)
        for q, ans in zip(p["qas"]["question"], p["qas"]["answers"]):
            gold = {nlib.squash(e) for a in ans["answer"] for e in a["evidence"] if e and not e.startswith("FLOAT SELECTED")}
            gi = {i for i, s in enumerate(sq) if s in gold}
            if not gi:
                continue
            n += 1
            sc = bm.score(q, bigram_boost=0.3 if variant != "nobigram" else 0)
            order = sorted(range(len(sc)), key=lambda i: -sc[i])
            rank = next((r for r, i in enumerate(order, 1) if i in gi), 10 ** 6)
            for k in hits:
                hits[k] += rank <= k
            mrr += 1.0 / rank if rank < 10 ** 6 else 0
    return n, {k: round(v / n, 3) for k, v in hits.items()}, round(mrr / n, 3)


if __name__ == "__main__":
    path = os.path.join(HERE, "qasper_validation.parquet")
    papers = pq.read_table(path).to_pylist()
    if len(sys.argv) > 1:
        papers = papers[: int(sys.argv[1])]
    rnd = random.Random(0)
    n_r = h5 = 0
    for p in papers:
        units = units_of(p)
        sq = [nlib.squash(u[1]) for u in units]
        for q, ans in zip(p["qas"]["question"], p["qas"]["answers"]):
            gold = {nlib.squash(e) for a in ans["answer"] for e in a["evidence"] if e and not e.startswith("FLOAT SELECTED")}
            gi = {i for i, s in enumerate(sq) if s in gold}
            if gi:
                n_r += 1
                h5 += bool(set(rnd.sample(range(len(units)), min(5, len(units)))) & gi)
    print("random@5 baseline: %.3f over %d questions" % (h5 / n_r, n_r))
    for v in ("nobigram", "bm25", "section"):
        n, hits, mrr = evaluate(papers, v)
        print("%-9s questions %d  recall@k %s  MRR %s" % (v, n, hits, mrr))
