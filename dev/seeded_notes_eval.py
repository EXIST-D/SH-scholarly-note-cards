#!/usr/bin/env python3
"""Seeded-defect evaluation of the note verifier (development tool, not part of the Skill runtime).

Takes a finished, correct work directory (units.json + notes.json), injects ONE typical defect at a time into otherwise correct notes, runs
the same validate_note() used by `ingest`, and reports how often the defect is caught (any issue / error level). The three global checks
(missing section summary, missing required field, "not reported although cues exist") are tested on copies of the notes.

usage: seeded_notes_eval.py WORK_DIR        (set NC_SCRIPTS=/path/to/scripts if nc.py is elsewhere)
Reproduce with the bundled fixture:
  python3 ../scripts/nc.py prepare <paper.pdf-or-md> --work W && python3 ../scripts/nc.py ingest W attention_notes.txt && python3 seeded_notes_eval.py W
"""
import copy
import json
import os
import random
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
for cand in (os.environ.get("NC_SCRIPTS"), os.path.join(HERE, "..", "scripts"), os.path.join(HERE, "..", "submission", "scripts"), os.path.join(HERE, "scripts")):
    if cand and os.path.isdir(cand):
        sys.path.insert(0, cand)
        break
import nc  # noqa: E402
import nlib  # noqa: E402


def run(work):
    d, notes = nc.load_all(work)
    bm = nc.build_index(d)
    rnd = random.Random(1)
    units = [u for u in d["units"] if not u["excluded"] and u["type"] in ("paragraph", "list_item") and len(u["text"].split()) > 25]

    def val(n, mod):
        m = dict(n)
        m.update(mod)
        m["quote"] = " ||| ".join(m["quote"]) if isinstance(m.get("quote"), list) else m.get("quote", "")
        others = [v for k, v in notes.items() if k != n["id"]]
        return nc.validate_note(d, bm, m, others)[0]

    base_err = base_warn = 0
    for n in notes.values():
        iss = val(n, {})
        base_err += any(i["severity"] == "error" for i in iss)
        base_warn += bool(iss)
    rows = []

    def tally(name, fn):
        cases = hit = err = 0
        for n in notes.values():
            mod = fn(n)
            if mod is None:
                continue
            iss = val(n, mod)
            cases += 1
            hit += bool(iss)
            err += any(i["severity"] == "error" for i in iss)
        rows.append((name, cases, hit, err))

    def other_unit(n):
        cur = {a[0] for a in nc.parse_anchors(n.get("ev", ""))[0]}
        cur_secs = {u["section"] for u in d["units"] if u["id"] in cur}
        pool = [u for u in units if u["id"] not in cur and u["section"] not in cur_secs]
        return rnd.choice(pool) if pool else None

    def fab_quote(n):
        if not n.get("quote"):
            return None
        q = n["quote"][0].split()
        if len(q) < 5:
            return None
        q[len(q) // 2] = "remarkably"
        q[-1] = "universally"
        return {"quote": [" ".join(q)]}

    def paraphrase_quote(n):
        return {"quote": ["the model was clearly shown to perform better than every competing approach in all settings"]} if n.get("quote") else None

    def wrong_anchor(n):
        if n["kind"] in ("meta", "section_summary") or not n.get("ev"):
            return None
        u = other_unit(n)
        return {"ev": u["id"]} if u else None

    def wrong_anchor_noquote(n):
        m = wrong_anchor(n)
        return dict(m, quote=[]) if m else None

    def wrong_number(n):
        m = re.search(r"(?<![\w.])\d+(?:\.\d+)?", n.get("text", "") + " " + n.get("result", ""))
        if not m or len(m.group(0)) < 2:
            return None
        old = m.group(0)
        new = old[:-1] + str((int(old[-1]) + 3) % 10)
        if n.get("text") and old in n["text"]:
            return {"text": n["text"].replace(old, new, 1)}
        if n.get("result") and old in n["result"]:
            return {"result": n["result"].replace(old, new, 1)}
        return None

    def drop_ev(n):
        return {"ev": ""} if n["kind"] != "meta" else None

    def overclaim(n):
        if n["kind"] not in ("finding", "conclusion", "contribution") or not n.get("text"):
            return None
        return {"text": n["text"].rstrip(".") + ", proving it is superior to every other approach and a breakthrough."}

    def inflate(n):
        t = n.get("text", "")
        return {"text": nlib.HEDGE.sub("clearly demonstrates", t, count=1)} if nlib.HEDGE.search(t) else None

    def other_section_summary(n):
        if n["kind"] != "section_summary":
            return None
        u = other_unit(n)
        return {"ev": u["id"]} if u else None

    def unrelated(n):
        if n["kind"] in ("meta", "section_summary") or not n.get("text"):
            return None
        u = other_unit(n)
        return {"text": u["sentences"][0]} if u and u["sentences"] else None

    def drop_negation(n):
        t = n.get("text", "")
        if re.search(r"\b(not|no|without|cannot)\b", t, re.I):
            return {"text": re.sub(r"\b(does not|do not|not|without|cannot)\b ?", "", t, count=1, flags=re.I)}
        return None

    tally("fabricated quote (2 words changed)", fab_quote)
    tally("paraphrase passed off as quote", paraphrase_quote)
    tally("anchor points to another section (with quote)", wrong_anchor)
    tally("anchor points to another section (no quote)", wrong_anchor_noquote)
    tally("number changed", wrong_number)
    tally("evidence anchor deleted", drop_ev)
    tally("overclaim added", overclaim)
    tally("hedge replaced by 'clearly demonstrates'", inflate)
    tally("section summary cites another section", other_section_summary)
    tally("text replaced by an unrelated sentence", unrelated)
    tally("negation deleted", drop_negation)

    tmp = tempfile.mkdtemp()
    for f in ("units.json", "state.json"):
        if os.path.isfile(os.path.join(work, f)):
            shutil.copy(os.path.join(work, f), tmp)

    def glob(mut):
        nn = copy.deepcopy(notes)
        mut(nn)
        nc.jsave(os.path.join(tmp, "notes.json"), nn)
        return nc.run_check(tmp)["summary"]

    s1 = glob(lambda nn: [nn.pop(k) for k in [k for k, v in nn.items() if v["kind"] == "section_summary"][:1]])
    s2 = glob(lambda nn: [nn.pop(k) for k in [k for k, v in nn.items() if v["kind"] == "limitation"]])

    def nr(nn):
        for k in [k for k, v in nn.items() if v["kind"] == "limitation"]:
            nn.pop(k)
        nn["L9"] = {"id": "L9", "kind": "limitation", "text": "", "status": "not_reported", "note": "none", "ev": "", "status_check": "ok", "issues": [], "verification": {"quotes": ["none"]}}
    s3 = glob(nr)
    print("baseline on the correct notes: %d notes | error-level false alarms %d | any warning %d" % (len(notes), base_err, base_warn))
    print("%-48s %6s %9s %11s" % ("injected defect", "cases", "caught", "caught(err)"))
    for name, c, h, e in rows:
        print("%-48s %6d %8.0f%% %10.0f%%" % (name, c, 100.0 * h / c if c else 0, 100.0 * e / c if c else 0))
    print("%-48s %s" % ("one section summary removed", "caught" if s1["sections_missing_summary"] else "MISSED"))
    print("%-48s %s" % ("all limitation notes removed", "caught" if "limitation" in s2["missing_required_fields"] else "MISSED"))
    print("%-48s %s" % ("'limitation: not reported' although cues exist", "caught" if s3["not_reported_contradicted"] else "MISSED (no strong cue in this paper)"))
    shutil.rmtree(tmp, ignore_errors=True)
    return rows


if __name__ == "__main__":
    run(sys.argv[1])
