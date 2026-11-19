#!/usr/bin/env python3
"""nc.py - evidence-linked structured paper notes (cards).

You read the paper and write the notes; this tool makes every note checkable: it splits the paper into addressable evidence units
(E012, sentences E012.3), shows you the paper's own section skeleton and the sentences that look like limitations / contributions /
results, VERIFIES each note the moment you submit it (verbatim quote, numbers, wording support, strength, section alignment), tells
you what is still missing (required fields, section summaries, uncovered limitation cues), and assembles a card, a searchable note
index and a human-review checklist.

  nc.py prepare INPUT --work W [--case /input/case.json] [--pages 1-8] [--lang auto]
  nc.py outline W                         section skeleton with unit ranges, sizes and cue counts
  nc.py read W --sec 3.2 | --ids E010-E040 | --page 4 | --cue limitation   [--sentences] [--max-words 1500]
  nc.py find W "query" [-k 5]             retrieve evidence units (BM25 + section titles)
  nc.py cues W [--kind limitation] [--top 15]
  nc.py ingest W [FILE|-]                 validate + store notes (block format or JSONL); errors are printed at once
  nc.py next W                            what is still missing / failing
  nc.py check W                           whole-card verification and coverage
  nc.py assemble W --out OUT [--case ...] [--answers answers.json]
  nc.py search OUT_OR_W "query" [--kind finding] [-k 8]     retrieve notes
  nc.py compare CARD.json CARD.json ... [--format md|csv]    side-by-side fields of several cards
  nc.py drop W ID [ID ...]                delete notes
  nc.py status W
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nlib  # noqa: E402

VERSION = "1.0.0"
SCHEMA = "scholarly-note-cards/1"

KINDS = {  # kind -> (label, card field, required min, description)
    "meta": ("Bibliographic data", "meta", 0, "title, authors, year, venue, DOI, field"),
    "question": ("Research question / objective", "question", 1, "what problem or question the paper addresses and why"),
    "contribution": ("Contribution", "contributions", 1, "what the authors claim to add"),
    "data": ("Data / materials", "data", 1, "datasets, samples, instruments, corpora, participants (with sizes and sources)"),
    "method": ("Method", "methods", 1, "approach, model, procedure, analysis"),
    "setting": ("Setting / parameter", "settings", 0, "hyper-parameters, protocol details, versions, thresholds"),
    "assumption": ("Assumption / premise", "assumptions", 0, "what must hold for the conclusions to be valid"),
    "finding": ("Main finding", "findings", 1, "a result, with the condition under which it holds"),
    "conclusion": ("Conclusion", "conclusions", 1, "what the authors conclude / recommend"),
    "limitation": ("Limitation", "limitations", 1, "weakness, scope limit, failure case, threat to validity"),
    "definition": ("Definition / term", "definitions", 0, "concept, variable, abbreviation with its meaning"),
    "future": ("Future work / open question", "future_work", 0, "what the authors leave open"),
    "reproducibility": ("Reproducibility / availability", "reproducibility", 0, "code, data, models, versions, links"),
    "relation": ("Relation to other work", "relations", 0, "how it builds on / differs from cited work"),
    "section_summary": ("Section summary", "section_summaries", 0, "purpose / method / result / conclusion / link of one section"),
}
REQUIRED = [k for k, v in KINDS.items() if v[2] > 0]
EXCLUDED_SECTIONS = re.compile(r"^\s*(\d+[.\s]+)?(references?|bibliography|literature cited|acknowledge?ments?|funding|conflicts? of interest|author contributions|(table of )?contents|参考文献|致谢|目录)\s*$", re.I)
OPTIONAL_SECTIONS = re.compile(r"^\s*(\d+[.\s]+)?(appendix|appendices|supplementary|supplemental|附录)", re.I)
BODY_KEYS = {"text": "text", "claim": "text", "cond": "cond", "conditions": "cond", "condition": "cond", "premise": "cond", "ev": "ev", "evidence": "ev", "anchor": "ev", "anchors": "ev",
             "quote": "quote", "quotes": "quote", "tags": "tags", "tag": "tags", "note": "note", "notes": "note", "derived": "derived", "purpose": "purpose", "method": "method",
             "result": "result", "conclusion": "conclusion", "link": "link", "searched": "searched", "status": "status", "conf": "conf", "confidence": "conf", "sec": "sec",
             "section": "sec", "id": "id", "title": "title", "authors": "authors", "year": "year", "venue": "venue", "doi": "doi", "field": "field", "term": "term"}


# ------------------------------------------------------------------------------------------------ io
def jload(p, default=None):
    if not os.path.isfile(p):
        return default
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def jsave(p, obj):
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def find_key(obj, names):
    if isinstance(obj, dict):
        for k in names:
            if k in obj:
                return obj[k]
        for v in obj.values():
            r = find_key(v, names)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_key(v, names)
            if r is not None:
                return r
    return None


# ------------------------------------------------------------------------------------------------ source loading (PDF / docx / md / txt / tex / json)
def load_source(path, work, args):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        out = os.path.join(work, "parsed")
        cmd = [sys.executable, os.path.join(HERE, "parse_pdf.py"), path, "--out", out]
        if args.ocr:
            cmd += ["--ocr", args.ocr]
        res = subprocess.run(cmd, capture_output=True, text=True)
        try:
            summary = json.loads(res.stdout.strip().splitlines()[-1])
        except Exception:
            raise SystemExit("PDF parsing failed: %s" % (res.stdout[-300:] + res.stderr[-300:]))
        if summary.get("status") == "failed":
            raise SystemExit("PDF parsing failed: %s" % json.dumps(summary, ensure_ascii=False))
        doc = jload(os.path.join(out, "parsed.json"))
        tables = {t["id"]: t for t in doc.get("tables", [])}
        blocks = []
        for b in doc["blocks"]:
            t = b["type"]
            blk = {"type": {"reference_block": "reference"}.get(t, t), "text": b.get("text", ""), "pages": b.get("pages") or [b["page"]], "page": b["page"], "bbox": b.get("bbox"),
                   "block": b["id"], "level": b.get("level"), "number": b.get("number")}
            if t == "table":
                tb = tables.get(b.get("table_id"))
                if not tb:
                    continue
                blk["text"] = tb["markdown"]
                blk["pages"] = tb["pages"]
            blocks.append(blk)
        return blocks, {"format": "pdf", "parser_status": doc["status"], "parser_warnings": doc.get("warnings", []), "unparsed": doc.get("unparsed", []), "pages": doc["source"]["pages"],
                        "file": os.path.basename(path), "pdf_metadata": doc["source"].get("metadata", {})}
    if ext == ".docx":
        return docx_blocks(path), {"format": "docx", "file": os.path.basename(path)}
    with open(path, encoding="utf-8", errors="replace") as fh:
        raw = fh.read()
    if ext == ".json":
        try:
            obj = json.loads(raw)
        except Exception:
            obj = None
        if obj is not None:
            blocks = json_blocks(obj)
            if blocks:
                return blocks, {"format": "json", "file": os.path.basename(path)}
    return text_blocks(raw, ext), {"format": ext.lstrip(".") or "txt", "file": os.path.basename(path)}


def json_blocks(obj):
    """Accept {title, abstract, sections:[{heading, paragraphs}]}, {full_text:{section_name, paragraphs}}, {paragraphs:[...]}, {text:'...'}."""
    blocks = []

    def add(typ, text, **kw):
        if text and str(text).strip():
            blocks.append({"type": typ, "text": str(text).strip(), "pages": [kw.get("page")] if kw.get("page") else [], "page": kw.get("page"), "bbox": None,
                           "block": "j%d" % len(blocks), "level": kw.get("level"), "number": None})
    if isinstance(obj, dict):
        if obj.get("title"):
            add("title", obj["title"], level=0)
        if obj.get("abstract"):
            add("abstract", obj["abstract"])
        ft = obj.get("full_text")
        if isinstance(ft, dict) and "section_name" in ft:
            for name, paras in zip(ft["section_name"], ft["paragraphs"]):
                add("heading", name, level=1)
                for p in paras:
                    add("paragraph", p)
            return blocks
        secs = obj.get("sections")
        if isinstance(secs, list):
            for s in secs:
                if isinstance(s, dict):
                    add("heading", s.get("heading") or s.get("title") or s.get("name"), level=s.get("level", 1))
                    for p in s.get("paragraphs") or ([s["text"]] if s.get("text") else []):
                        add("paragraph", p if isinstance(p, str) else p.get("text", ""))
            if blocks:
                return blocks
        paras = obj.get("paragraphs") or obj.get("segments") or obj.get("blocks")
        if isinstance(paras, list):
            for p in paras:
                if isinstance(p, str):
                    add("paragraph", p)
                elif isinstance(p, dict):
                    t = p.get("type") if p.get("type") in ("heading", "title", "caption", "paragraph", "table", "list_item", "footnote", "abstract", "reference", "formula") else "paragraph"
                    add(t, p.get("text") or p.get("content"), page=p.get("page"), level=p.get("level"))
            return blocks
        t = obj.get("text") or obj.get("body") or obj.get("content")
        if isinstance(t, str):
            return text_blocks(t, ".md")
    elif isinstance(obj, list):
        for p in obj:
            add("paragraph", p if isinstance(p, str) else (p.get("text") if isinstance(p, dict) else ""))
    return blocks


def docx_blocks(path):
    import zipfile
    from xml.etree import ElementTree as ET
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main", "m": "http://schemas.openxmlformats.org/officeDocument/2006/math"}
    W = "{%s}" % ns["w"]
    try:
        root = ET.fromstring(zipfile.ZipFile(path).read("word/document.xml"))
    except Exception as e:
        raise SystemExit("cannot read .docx: %s" % e)
    blocks = []

    def ptext(p):
        return "".join(t.text or "" for t in p.iter(W + "t")).strip()
    for el in root.find(W + "body"):
        if el.tag == W + "p":
            txt = ptext(el)
            if not txt:
                continue
            style = el.find("w:pPr/w:pStyle", ns)
            sv = (style.get(W + "val") if style is not None else "") or ""
            m = re.match(r"(?i)heading\s*(\d)", sv)
            typ, lvl = "paragraph", None
            if sv.lower() == "title":
                typ, lvl = "title", 0
            elif m:
                typ, lvl = "heading", int(m.group(1))
            elif re.match(r"^\s*(Figure|Fig\.|Table|FIG\.|TABLE)\s*[\dA-Z]+[.:]", txt) or sv.lower() == "caption":
                typ = "caption"
            elif el.find("w:pPr/w:numPr", ns) is not None:
                typ = "list_item"
            blocks.append({"type": typ, "text": txt, "pages": [], "page": None, "bbox": None, "block": "d%d" % len(blocks), "level": lvl, "number": None})
        elif el.tag == W + "tbl":
            rows = [[" ".join(ptext(p) for p in tc.iter(W + "p")).replace("|", "/") for tc in tr_.findall(W + "tc")] for tr_ in el.iter(W + "tr")]
            if rows:
                md = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * len(rows[0])] + ["| " + " | ".join(r) + " |" for r in rows[1:]]
                blocks.append({"type": "table", "text": "\n".join(md), "pages": [], "page": None, "bbox": None, "block": "d%d" % len(blocks), "level": None, "number": None})
    return blocks


def text_blocks(raw, ext):
    raw = re.sub(r"<!--.*?-->", "", raw, flags=re.S)
    blocks, para, fence = [], [], False

    def flush():
        if para:
            txt = "\n".join(para).strip()
            if txt:
                typ = "paragraph"
                if re.match(r"^\s*(\|.+\|\s*\n?)+$", txt):
                    typ = "table"
                elif re.match(r"^\s*(Figure|Fig\.|Table|FIG\.|TABLE)\s*[\dA-Z]+[.:]", txt):
                    typ = "caption"
                elif re.match(r"^\s*([-*•]|\d+[.)])\s+", txt):
                    typ = "list_item"
                blocks.append({"type": typ, "text": txt if typ == "table" else re.sub(r"\s*\n\s*", " ", txt), "pages": [], "page": None, "bbox": None, "block": "t%d" % len(blocks),
                               "level": None, "number": None})
            para.clear()
    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("```"):
            flush()
            fence = not fence
            continue
        if fence:
            continue
        if s.startswith("$$") and s.endswith("$$") and len(s) > 4:
            flush()
            blocks.append({"type": "formula", "text": s, "pages": [], "page": None, "bbox": None, "block": "t%d" % len(blocks), "level": None, "number": None})
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s) or re.match(r"^\\(section|subsection|subsubsection)\*?\{(.*)\}", s)
        if m:
            flush()
            lvl = len(m.group(1)) if m.group(1).startswith("#") else {"section": 1, "subsection": 2, "subsubsection": 3}[m.group(1)]
            is_title = lvl == 1 and not any(b["type"] in ("title", "heading") for b in blocks)
            blocks.append({"type": "title" if is_title else "heading", "text": m.group(2).strip(), "pages": [], "page": None, "bbox": None, "block": "t%d" % len(blocks),
                           "level": 0 if is_title else lvl, "number": None})
            continue
        if not s:
            flush()
            continue
        if s.startswith("%") and ext == ".tex":
            continue
        para.append(line)
    flush()
    return blocks


TERMINAL = tuple(".?!:;。？！：；”\"')]")
SKIPPABLE = ("caption", "table", "footnote", "formula", "header", "footer", "margin", "figure")


def merge_continuations(blocks):
    """Re-join a paragraph cut by a figure caption, column or page break."""
    alltext = " ".join(b.get("text", "") for b in blocks)
    hyph = set(w.lower() for w in re.findall(r"[A-Za-z]+-[A-Za-z]+", alltext))
    drop, merged = set(), 0
    for i, b in enumerate(blocks):
        if i in drop or b["type"] not in ("paragraph", "list_item"):
            continue
        txt = b.get("text", "").rstrip()
        if not txt or txt.endswith(TERMINAL) or len(txt) < 15:
            continue
        j = i + 1
        while j < len(blocks) and j <= i + 6 and (j in drop or blocks[j]["type"] in SKIPPABLE):
            j += 1
        if j >= len(blocks) or j > i + 6:
            continue
        q = blocks[j]
        qt = q.get("text", "").lstrip()
        if q["type"] not in ("paragraph", "list_item") or not qt or not (qt[0].islower() or qt[0] in "(,;"):
            continue
        if txt.endswith("-") and re.search(r"[A-Za-z]-$", txt):
            m1, m2 = re.search(r"([A-Za-z]+)-$", txt), re.match(r"([A-Za-z]+)", qt)
            keep = bool(m1 and m2 and (m1.group(1) + "-" + m2.group(1)).lower() in hyph)
            joined = txt + qt if keep else txt[:-1] + qt
        else:
            joined = txt + " " + qt
        b["text"] = joined
        b["pages"] = sorted(set((b.get("pages") or []) + (q.get("pages") or [])))
        drop.add(j)
        merged += 1
    return [b for k, b in enumerate(blocks) if k not in drop], merged


# ------------------------------------------------------------------------------------------------ units, sections
NUM_HEAD = re.compile(r"^\s*((?:\d{1,2}(?:\.\d{1,2}){0,3})|(?:[A-H](?:\.\d{1,2}){0,2})|(?:[IVX]{1,5}))[.)]?\s+(.+)$")


def build_units(blocks, args):
    blocks, merged = merge_continuations(blocks)
    units, sections = [], []
    cur = {"id": "§front", "title": "(front matter)", "level": 0, "number": None, "units": [], "excluded": False, "optional": True, "parent": None}
    sections.append(cur)
    stack = []
    seq = 0
    page_filter = None
    if args.pages:
        page_filter = set()
        for part in str(args.pages).split(","):
            m = re.fullmatch(r"(\d+)-(\d+)", part.strip())
            if m:
                page_filter.update(range(int(m.group(1)), int(m.group(2)) + 1))
            elif part.strip().isdigit():
                page_filter.add(int(part))
    in_abstract = False
    last_top_number = None
    for b in blocks:
        t, text = b["type"], (b.get("text") or "").strip()
        if not text or t in ("header", "footer", "margin"):
            continue
        pgs = b.get("pages") or ([b["page"]] if b.get("page") else [])
        if page_filter and pgs and not (set(pgs) & page_filter):
            continue
        if t == "heading" and text.endswith(":") and len(text.split()) <= 4:
            t = "paragraph"  # a run-in label such as "Decoder:" is not a section
        if t == "heading":
            m = NUM_HEAD.match(text)
            number, title = (m.group(1), m.group(2).strip()) if m else (None, text)
            lvl = b.get("level") if isinstance(b.get("level"), int) and b.get("level") else ((number.count(".") + 1) if number and re.match(r"^\d", number) else 1)
            # PRL style: "V. SEARCHES" followed by "A. Generic ..." / "B. ..." - a single letter under a ROMAN top-level section is a subsection, not an appendix
            if number and re.fullmatch(r"[A-H]", number) and last_top_number and re.fullmatch(r"[IVX]+", last_top_number):
                lvl = 2
            seq += 1
            sid = "§" + (number if number else "s%d" % seq)
            if number and sid in {x["id"] for x in sections} and lvl == 2:
                sid = "§%s.%s" % (last_top_number, number)
            if any(s["id"] == sid for s in sections):
                sid += "-%d" % seq
            if lvl <= 1:
                last_top_number = number
            is_abs = bool(re.match(r"^\s*(abstract|summary|摘要)\s*$", title, re.I))
            if is_abs:
                sid = "§abs"
            while stack and stack[-1]["level"] >= lvl:
                stack.pop()
            parent = stack[-1]["id"] if stack else None
            cur = {"id": sid, "title": title, "level": lvl, "number": number, "units": [], "excluded": bool(EXCLUDED_SECTIONS.match(text)), "parent": parent,
                   "optional": bool(OPTIONAL_SECTIONS.match(text)) or is_abs or bool(number and lvl <= 1 and re.match(r"^[A-H](\.\d+)*$", number)) or bool(re.match(r"^\s*contributions\s*$", title, re.I)), "pages": []}
            if stack and (stack[-1].get("excluded") or stack[-1].get("optional")) and lvl > stack[-1]["level"]:
                cur["excluded"] = cur["excluded"] or stack[-1].get("excluded", False)
                cur["optional"] = cur["optional"] or stack[-1].get("optional", False)
            stack.append(cur)
            sections.append(cur)
            in_abstract = is_abs
            continue
        if t in ("reference", "reference_block"):
            cur_ex = True
        else:
            cur_ex = cur["excluded"]
        typ = {"abstract": "abstract", "front_matter": "front"}.get(t, t)
        if t == "abstract":
            if not any(s["id"] == "§abs" for s in sections):
                cur = {"id": "§abs", "title": "Abstract", "level": 1, "number": None, "units": [], "excluded": False, "parent": None, "optional": True, "pages": []}
                sections.append(cur)
                stack[:] = [cur]
        uid = "E%03d" % (len(units) + 1)
        sents = nlib.split_sentences(text) if typ in ("paragraph", "abstract", "list_item", "caption", "footnote", "front") else [text]
        u = {"id": uid, "type": typ, "text": text, "sentences": sents, "pages": pgs, "page": b.get("page") or (pgs[0] if pgs else None), "bbox": b.get("bbox"),
             "block": b.get("block"), "section": cur["id"], "excluded": cur_ex, "words": nlib.wcount(text)}
        units.append(u)
        cur["units"].append(uid)
    # sections' page spans and sizes
    byid = {u["id"]: u for u in units}
    for s in sections:
        pg = sorted({p for uid in s["units"] for p in byid[uid]["pages"]})
        s["pages"] = pg
        s["n_units"] = len(s["units"])
        s["words"] = sum(byid[uid]["words"] for uid in s["units"])
        s["first"], s["last"] = (s["units"][0], s["units"][-1]) if s["units"] else (None, None)
    sections = [s for s in sections if s["units"] or s["id"] != "§front"]
    # normalise heading levels: the smallest level used in the document is the top level (Markdown "##" headings, Word styles ...)
    lv = [s["level"] for s in sections if s["id"] != "§front" and s["level"] and s["level"] >= 1]
    if lv and min(lv) > 1:
        shift = min(lv) - 1
        for s in sections:
            if s["id"] != "§front" and s["level"]:
                s["level"] -= shift
    # totals including all descendants (a "Results" heading may hold no text itself but 3 subsections)
    kids = defaultdict(list)
    for s in sections:
        if s.get("parent"):
            kids[s["parent"]].append(s["id"])
    byid_s = {s["id"]: s for s in sections}

    def total(sid):
        s = byid_s[sid]
        return s["words"] + sum(total(k) for k in kids[sid] if k in byid_s)
    for s in sections:
        s["words_total"] = total(s["id"])

    def path(sid):
        s = byid_s[sid]
        return (path(s["parent"]) + " > " if s.get("parent") in byid_s else "") + s["title"]
    for s in sections:
        s["path"] = path(s["id"])
    return units, sections, merged


def compute_cues(units, sections):
    sec = {s["id"]: s for s in sections}
    cues = []
    for u in units:
        if u["excluded"] or u["type"] in ("heading", "table", "formula", "front", "title"):
            continue
        title = sec[u["section"]].get("path") or sec[u["section"]]["title"]
        for i, s in enumerate(u["sentences"], 1):
            kinds = nlib.classify_sentence(s, title)
            if u["type"] in ("caption", "footnote"):
                kinds = [k for k in kinds if k == "result"]
            if not kinds:
                continue
            score = {}
            for k in kinds:
                sc = len(nlib.CUES[k].findall(s))
                if k == "limitation":
                    sc += 1.5 if nlib.LIMIT_SECTIONS.search(title) else 0
                    sc += 1 if re.search(r"\b(limitation|assum|future work|cannot|fail)", s, re.I) else 0
                if k == "result":
                    sc += 1 if re.search(r"\b(results?|experiments?|evaluation|performance)\b", title, re.I) else 0
                score[k] = sc
            cues.append({"unit": u["id"], "sent": i, "kinds": kinds, "score": score, "text": s})
    return cues


# ------------------------------------------------------------------------------------------------ anchors
ANCHOR_RE = re.compile(r"E(\d{3,})(?:\.(\d+)(?:-(\d+))?)?")


def parse_anchors(spec):
    """'E012, E014.2, E020-E022, E031.1-3' -> list of (unit_id, sent_from, sent_to) ; sentence None = whole unit."""
    out, bad = [], []
    spec = spec or ""
    for part in re.split(r"[,;\s]+", spec.strip()):
        if not part:
            continue
        m = re.fullmatch(r"E(\d{3,})-E?(\d{3,})", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 0 < b - a <= 60:
                out += [("E%03d" % n, None, None) for n in range(a, b + 1)]
                continue
        m = ANCHOR_RE.fullmatch(part)
        if m:
            out.append(("E%03d" % int(m.group(1)), int(m.group(2)) if m.group(2) else None, int(m.group(3)) if m.group(3) else (int(m.group(2)) if m.group(2) else None)))
        else:
            bad.append(part)
    return out, bad


def anchor_text(units_by_id, anchors):
    txt, texts = [], []
    for uid, a, b in anchors:
        u = units_by_id.get(uid)
        if not u:
            continue
        if a:
            ss = u["sentences"][a - 1:b]
            texts.append(" ".join(ss))
        else:
            texts.append(u["text"])
    return " ".join(texts), texts


def fmt_anchor(units_by_id, uid, a=None, b=None):
    u = units_by_id[uid]
    pg = ",".join(str(p) for p in u["pages"]) or "-"
    return "%s%s · p%s · %s" % (uid, ".%d%s" % (a, "-%d" % b if b and b != a else "") if a else "", pg, u["section"])


# ------------------------------------------------------------------------------------------------ state
def load_all(work):
    d = jload(os.path.join(work, "units.json"))
    if d is None:
        raise SystemExit("no units.json in %s: run `prepare` first" % work)
    notes = jload(os.path.join(work, "notes.json"), {})
    return d, notes


def sec_of(d):
    return {s["id"]: s for s in d["sections"]}


def build_index(d):
    docs = []
    secs = sec_of(d)
    for u in d["units"]:
        docs.append(secs[u["section"]]["title"] + " " + u["text"])
    return nlib.BM25(docs)


def in_section(d, sec_id, uid):
    secs = sec_of(d)
    u = next((x for x in d["units"] if x["id"] == uid), None)
    if not u:
        return False
    cur = u["section"]
    while cur:
        if cur == sec_id:
            return True
        cur = (secs.get(cur) or {}).get("parent")
    return False


# ------------------------------------------------------------------------------------------------ prepare / reading commands
def cmd_prepare(a):
    os.makedirs(a.work, exist_ok=True)
    if not os.path.isfile(a.input):
        raise SystemExit("input not found: " + a.input)
    case = jload(a.case) if a.case and os.path.isfile(a.case) else None
    blocks, meta = load_source(a.input, a.work, a)
    units, sections, merged = build_units(blocks, a)
    if not units:
        raise SystemExit("no readable text found in the input")
    body = " ".join(u["text"] for u in units if u["type"] in ("paragraph", "abstract"))
    lang = a.lang if a.lang != "auto" else nlib.detect_lang(body)
    cues = compute_cues(units, sections)
    # bibliographic hints from the front matter
    title = next((u["text"] for u in units if u["type"] == "title"), None)
    front = [u["text"] for u in units if u["type"] == "front"][:6]
    head_text = " ".join(u["text"] for u in units[:12])
    year = re.findall(r"\b(?:19|20)\d{2}\b", head_text)
    doi = re.findall(r"\b10\.\d{4,9}/[^\s)\]>,;]+", " ".join(u["text"] for u in units[:30]))
    arx = re.findall(r"arXiv:\s?(\d{4}\.\d{4,5})", " ".join(u["text"] for u in units[:30]), re.I)
    meta.update({"lang": lang, "n_units": len(units), "n_sections": len(sections), "continuations_merged": merged, "version": VERSION,
                 "hints": {"title": title, "front_matter": front, "years": sorted(set(year))[:4], "doi": doi[:1], "arxiv": arx[:1],
                           "pdf_metadata": meta.get("pdf_metadata", {})}, "task": (find_key(case, ["task", "instruction", "prompt", "question"]) if case else None)})
    jsave(os.path.join(a.work, "units.json"), {"meta": meta, "units": units, "sections": sections, "cues": cues})
    jsave(os.path.join(a.work, "state.json"), {"t0": time.time(), "budget_s": a.budget})
    if not os.path.isfile(os.path.join(a.work, "notes.json")):
        jsave(os.path.join(a.work, "notes.json"), {})
    nuse = [u for u in units if not u["excluded"]]
    ck = Counter(k for c in cues for k in c["kinds"])
    print(json.dumps({"ok": True, "work": a.work, "file": meta["file"], "format": meta["format"], "lang": lang, "pages": meta.get("pages"), "units": len(units), "citable_units": len(nuse),
                      "sections": len(sections), "words": sum(u["words"] for u in nuse), "continuations_merged": merged, "cue_counts": dict(ck), "parser_status": meta.get("parser_status")},
                     ensure_ascii=False))
    for w in meta.get("parser_warnings", [])[:3]:
        print("WARNING (parser): " + w)
    if meta.get("unparsed"):
        print("WARNING: parts of the file could not be read (%s): report them as not processed." % json.dumps(meta["unparsed"][:3]))
    need = [s for s in sections if not s["excluded"] and not s["optional"] and s["level"] <= 1 and s.get("words_total", 0) >= 25]
    print("Section skeleton to follow (%d top-level sections need a section_summary): %s" % (len(need), " | ".join("%s %s" % (s["id"], s["title"][:28]) for s in need)))
    print("Next: `outline`, then `read` the paper section by section (`read W --sec 1`), then write notes and `ingest` them.")


def words_budget_read(units, max_words):
    out, used = [], 0
    for u in units:
        if used and used + u["words"] > max_words:
            break
        out.append(u)
        used += u["words"]
    return out


def cmd_outline(a):
    d, notes = load_all(a.work)
    cues = d["cues"]
    per = defaultdict(Counter)
    byu = {u["id"]: u for u in d["units"]}
    for c in cues:
        for k in c["kinds"]:
            per[byu[c["unit"]]["section"]][k] += 1
    print("OUTLINE of %s (%s, %d citable units)" % (d["meta"]["file"], d["meta"]["lang"], sum(1 for u in d["units"] if not u["excluded"])))
    for s in d["sections"]:
        ind = "  " * max(0, (s["level"] or 1) - 1)
        flags = " [excluded]" if s["excluded"] else (" [optional]" if s["optional"] else "")
        cu = " ".join("%s:%d" % (k[:3], n) for k, n in per[s["id"]].most_common(4))
        print("%s%s %s | %s | p%s | %s..%s | %d words (%d with subsections)%s%s" % (ind, s["id"], s["title"][:50], "L%d" % s["level"], ",".join(map(str, s["pages"][:3])) or "-", s["first"], s["last"], s["words"], s.get("words_total", s["words"]), flags,
                                                           ("  cues: " + cu) if cu else ""))


def cmd_read(a):
    d, notes = load_all(a.work)
    units = [u for u in d["units"]]
    sel = []
    if a.sec:
        sid = a.sec if a.sec.startswith("§") else "§" + a.sec
        sel = [u for u in units if in_section(d, sid, u["id"])]
        if not sel:
            raise SystemExit("no such section: %s (see `outline`)" % sid)
    elif a.ids:
        anchors, bad = parse_anchors(a.ids)
        want = {x[0] for x in anchors}
        sel = [u for u in units if u["id"] in want]
    elif a.page:
        sel = [u for u in units if a.page in u["pages"]]
    elif a.cue:
        byu = {u["id"]: u for u in units}
        cs = [c for c in d["cues"] if a.cue in c["kinds"]]
        cs.sort(key=lambda c: -c["score"].get(a.cue, 0))
        for c in cs[: a.top]:
            print("%s.%d [%s p%s %s] %s" % (c["unit"], c["sent"], a.cue, ",".join(map(str, byu[c["unit"]]["pages"])) or "-", byu[c["unit"]]["section"], c["text"][:300]))
        return
    else:
        sel = units
    sel = [u for u in sel if not u["excluded"] or a.ids]
    chunk = words_budget_read(sel, a.max_words)
    secs = sec_of(d)
    last_sec = None
    for u in chunk:
        if u["section"] != last_sec:
            s = secs[u["section"]]
            print("\n## %s %s (p%s)" % (s["id"], s["title"], ",".join(map(str, s["pages"][:3])) or "-"))
            last_sec = u["section"]
        pg = ",".join(map(str, u["pages"])) or "-"
        if a.sentences and len(u["sentences"]) > 1:
            print("%s [%s p%s]" % (u["id"], u["type"], pg))
            for i, s in enumerate(u["sentences"], 1):
                print("  %s.%d %s" % (u["id"], i, s))
        else:
            print("%s [%s p%s] %s" % (u["id"], u["type"], pg, u["text"]))
    if len(chunk) < len(sel):
        print("\n... %d more unit(s): continue with --ids %s-%s" % (len(sel) - len(chunk), sel[len(chunk)]["id"], sel[-1]["id"]))


def cmd_find(a):
    d, notes = load_all(a.work)
    bm = build_index(d)
    byu = d["units"]
    for i, sc in bm.top(a.query, a.k):
        u = byu[i]
        if u["excluded"]:
            continue
        print("%s [p%s %s] (%.1f) %s" % (u["id"], ",".join(map(str, u["pages"])) or "-", u["section"], sc, u["text"][:240].replace("\n", " ")))


def cmd_cues(a):
    d, notes = load_all(a.work)
    byu = {u["id"]: u for u in d["units"]}
    kinds = [a.kind] if a.kind else ["limitation", "contribution", "future", "availability"]
    for k in kinds:
        cs = [c for c in d["cues"] if k in c["kinds"]]
        cs.sort(key=lambda c: -c["score"].get(k, 0))
        print("== %s (%d candidate sentences; top %d)" % (k, len(cs), a.top))
        for c in cs[: a.top]:
            print("  %s.%d [p%s %s] %s" % (c["unit"], c["sent"], ",".join(map(str, byu[c["unit"]]["pages"])) or "-", byu[c["unit"]]["section"], c["text"][:220]))


# ------------------------------------------------------------------------------------------------ note parsing
def clean_value(v):
    return v.strip()


def parse_note_blocks(text):
    recs, cur, key = [], None, None
    for ln in text.splitlines():
        s = ln.rstrip()
        if re.match(r"^\s*```\w*\s*$", s):
            continue
        m = re.match(r"^\s*[#=*]{2,}\s*([a-z_]+)\b(.*?)[*=#]*\s*$", s)
        if m and m.group(1) in KINDS:
            cur = {"kind": m.group(1), "attrs": {}, "fields": {}}
            for kv in re.findall(r"([a-z_]+)=((?:\"[^\"]*\")|\S+)", m.group(2)):
                cur["attrs"][BODY_KEYS.get(kv[0], kv[0])] = kv[1].strip('"')
            recs.append(cur)
            key = None
            continue
        if cur is None:
            continue
        mk = re.match(r"^\s*(?:[-*]\s*)?([A-Za-z_]+)\s*[:：]\s*(.*)$", s)
        if mk and mk.group(1).lower() in BODY_KEYS:
            key = BODY_KEYS[mk.group(1).lower()]
            cur["fields"].setdefault(key, [])
            if mk.group(2).strip():
                cur["fields"][key].append(mk.group(2).strip())
            continue
        if key and s.strip():
            cur["fields"][key].append(s.strip())
        elif key is None and s.strip():
            cur["fields"].setdefault("text", []).append(s.strip())
            key = "text"
    out = []
    for r in recs:
        f = {k: " ".join(v) if k not in ("quote",) else v for k, v in r["fields"].items()}
        f.update({k: v for k, v in r["attrs"].items() if k not in f})
        out.append({"kind": r["kind"], **f})
    return out


def parse_note_jsonl(text):
    out = []
    for ln in text.splitlines():
        ln = ln.strip()
        if ln.startswith("{"):
            try:
                o = json.loads(ln)
            except Exception:
                continue
            if o.get("kind") in KINDS:
                if isinstance(o.get("ev"), list):
                    o["ev"] = ", ".join(o["ev"])
                if isinstance(o.get("tags"), list):
                    o["tags"] = ", ".join(o["tags"])
                if isinstance(o.get("quote"), str):
                    o["quote"] = [o["quote"]]
                out.append(o)
    return out


def split_quotes(q):
    if not q:
        return []
    items = q if isinstance(q, list) else [q]
    out = []
    for it in items:
        for part in re.split(r"\s*\|\|\|\s*", it):
            part = part.strip().strip('"“”\'').strip()
            if part:
                out.append(part)
    return out


# ------------------------------------------------------------------------------------------------ validation
def best_unit_for(d, bm, text, exclude=()):
    for i, sc in bm.top(text, 4):
        u = d["units"][i]
        if u["id"] not in exclude and not u["excluded"]:
            return u, sc
    return None, 0


def validate_note(d, bm, note, others):
    """Return (issues, verification). issues: [{severity, kind, detail}]"""
    issues, ver = [], {}
    byu = {u["id"]: u for u in d["units"]}
    kind = note["kind"]
    text = (note.get("text") or "").strip()
    cond = (note.get("cond") or "").strip()
    status = note.get("status") or "reported"
    lang_note = nlib.detect_lang(text) if text else d["meta"]["lang"]
    lang_src = d["meta"]["lang"]
    allfields = " ".join(note.get(k, "") for k in ("text", "purpose", "method", "result", "conclusion", "link") if note.get(k))
    if kind == "section_summary":
        if not note.get("sec") or note["sec"] not in sec_of(d):
            issues.append({"severity": "error", "kind": "section", "detail": "section_summary needs sec=<section id from `outline`> (e.g. sec=§3)"})
        if not any(note.get(k) for k in ("purpose", "method", "result", "conclusion", "text")):
            issues.append({"severity": "error", "kind": "empty", "detail": "section_summary has no content (purpose/method/result/conclusion)"})
    elif kind != "meta" and not text and status == "reported":
        issues.append({"severity": "error", "kind": "empty", "detail": "note has no text"})
    anchors, bad = parse_anchors(note.get("ev", ""))
    if bad:
        issues.append({"severity": "error", "kind": "anchor_syntax", "detail": "bad anchors: %s (use E012, E012.2, E012-E014)" % ", ".join(bad[:4])})
    unknown = [x[0] for x in anchors if x[0] not in byu]
    if unknown:
        issues.append({"severity": "error", "kind": "anchor_unknown", "detail": "unknown evidence ids: %s (ids are E001..E%03d)" % (", ".join(sorted(set(unknown))[:5]), len(d["units"]))})
    anchors = [x for x in anchors if x[0] in byu]
    for uid, a_, b_ in anchors:
        u = byu[uid]
        if u["excluded"]:
            issues.append({"severity": "error", "kind": "anchor_excluded", "detail": "%s is in an excluded section (references/acknowledgements) and cannot be evidence" % uid})
        if a_ and (a_ > len(u["sentences"]) or (b_ and b_ > len(u["sentences"]))):
            issues.append({"severity": "error", "kind": "anchor_sentence", "detail": "%s has only %d sentences" % (uid, len(u["sentences"]))})
    anchors = [x for x in anchors if not byu[x[0]]["excluded"] and not (x[1] and x[1] > len(byu[x[0]]["sentences"]))]
    if not anchors and status == "reported" and kind != "meta":
        sug, _ = best_unit_for(d, bm, allfields or text)
        issues.append({"severity": "error", "kind": "no_evidence", "detail": "no evidence anchor (ev:). %s" % (("Closest unit: %s [%s] %s..." % (sug["id"], sug["section"], sug["text"][:80])) if sug else "Use `find` to locate it.")})
    if status in ("not_reported", "unclear") and not note.get("note") and not note.get("searched"):
        issues.append({"severity": "error", "kind": "not_reported_unexplained", "detail": "status=%s needs `searched:` or `note:` saying where you looked" % status})
    ev_full, _ = anchor_text(byu, [(x[0], None, None) for x in anchors])
    ev_exact, ev_parts = anchor_text(byu, anchors)
    # --- quotes: verbatim
    quotes = split_quotes(note.get("quote"))
    qres = []
    for q in quotes:
        sq = nlib.squash(q)
        if len(sq) < 6:
            continue
        if sq in nlib.squash(ev_full):
            qres.append("verified")
            continue
        where = [u for u in d["units"] if not u["excluded"] and sq in nlib.squash(u["text"])]
        if where:
            qres.append("elsewhere")
            issues.append({"severity": "error", "kind": "quote_other_unit", "detail": "quote is verbatim but sits in %s (%s), not in the cited evidence: cite %s" % (where[0]["id"], where[0]["section"], where[0]["id"])})
            continue
        best, bi = 0.0, None
        for u in d["units"]:
            if u["excluded"]:
                continue
            su = nlib.squash(u["text"])
            if len(su) < len(sq) or len(sq) > 600:
                continue
            sm = difflib.SequenceMatcher(None, su, sq, autojunk=False)
            m = sm.find_longest_match(0, len(su), 0, len(sq))
            ratio = m.size / len(sq)
            if ratio > best:
                best, bi = ratio, u
        if best >= 0.9:
            qres.append("approx")
            issues.append({"severity": "warn", "kind": "quote_approx", "detail": "quote differs slightly from %s (%.0f%% matches): copy it exactly" % (bi["id"], 100 * best)})
        else:
            qres.append("missing")
            issues.append({"severity": "error", "kind": "quote_missing", "detail": "quote not found in the paper (best match %.0f%%%s): possible fabrication or paraphrase - quote verbatim or drop the quote" % (
                100 * best, " in " + bi["id"] if bi and best >= 0.5 else "")})
    ver["quotes"] = qres or ["none"]
    # --- numbers
    nums = nlib.numbers(" ".join(x for x in (text, cond, note.get("purpose", ""), note.get("method", ""), note.get("result", ""), note.get("conclusion", "")) if x))
    derived = bool(note.get("derived"))
    ev_nums = Counter(nlib.numbers_ev(ev_full)) if anchors else Counter()
    ev_nums_loose = set(ev_nums)  # citation markers, "Figure 3" and years in citations are not number evidence
    miss = []
    for n in nums:
        if n in ev_nums_loose or n in ev_nums:
            continue
        if re.fullmatch(r"\d", n) and not derived:
            continue  # single digits are usually counts/enumerations ("3 datasets")
        miss.append(n)
    ver["numbers"] = "ok" if not miss else "unsupported"
    if miss and anchors:
        elsewhere = []
        for n in miss[:4]:
            hit = next((u for u in d["units"] if not u["excluded"] and n in set(nlib.numbers_ev(u["text"]))), None)
            elsewhere.append("%s%s" % (n, " (found in %s)" % hit["id"] if hit else " (not in the paper)"))
        sev = "warn" if derived else "error"
        issues.append({"severity": sev, "kind": "numbers", "detail": "numbers not in the cited evidence: %s%s" % (", ".join(elsewhere), " - marked derived" if derived else ". Cite the unit that contains them, or add `derived: how you computed it`")})
    # --- lexical support (same language only)
    if anchors and text and kind not in ("meta", "section_summary") and lang_note == lang_src:
        cw = nlib.content_words(text + " " + cond)
        ew = nlib.content_words(ev_full)
        sup = len(cw & ew) / len(cw) if cw else 1.0
        # best single sentence
        ver["support"] = round(sup, 2)
        if len(cw) >= 4:
            if sup < 0.12:
                sug, _ = best_unit_for(d, bm, text, exclude={x[0] for x in anchors})
                issues.append({"severity": "error", "kind": "support", "detail": "the cited evidence hardly shares any wording with the note (support %.2f)%s" % (sup, ". Closest unit: %s [%s] %s..." % (sug["id"], sug["section"], sug["text"][:70]) if sug else "")})
            elif sup < 0.3:
                issues.append({"severity": "warn", "kind": "support", "detail": "weak wording support from the cited evidence (%.2f): check the anchor or add the missing anchor" % sup})
    # --- strength / hedge / negation / overclaim
    if anchors and text and kind not in ("meta", "section_summary"):
        if any(x[1] for x in anchors):
            ev_for_cues = ev_exact
        else:  # unit-level anchor: judge strength against the 2 evidence sentences that best match the note, not the whole paragraph
            sents = [x for uid, _, _ in anchors for x in byu[uid]["sentences"]]
            cwn = nlib.content_words(text + " " + cond)
            sents.sort(key=lambda x: -len(cwn & nlib.content_words(x)))
            ev_for_cues = " ".join(sents[:2])
        if nlib.HEDGE.search(ev_for_cues) and not nlib.HEDGE.search(text + " " + cond) and nlib.STRONG.search(text):
            issues.append({"severity": "warn", "kind": "strength", "detail": "evidence is hedged (%s) but the note states it as established (%s)" % (nlib.HEDGE.search(ev_for_cues).group(0), nlib.STRONG.search(text).group(0))})
        oc = [m.group(0).lower() for m in nlib.OVERCLAIM.finditer(text)]
        evstems = set(nlib.tokens(ev_full))
        oc = [w for w in oc if nlib.stem(w) not in evstems and not re.search(r"\b" + re.escape(w) + r"\b", ev_full, re.I)]
        if oc:
            issues.append({"severity": "warn", "kind": "overclaim", "detail": "claim words not found in the evidence: %s" % ", ".join(sorted(set(oc))[:3])})
        if nlib.NEGATION.search(ev_for_cues) and not nlib.NEGATION.search(text + " " + cond) and kind in ("limitation", "finding"):
            issues.append({"severity": "warn", "kind": "negation", "detail": "the evidence contains a negation (%s) that the note does not reflect" % nlib.NEGATION.search(ev_for_cues).group(0)})
    # --- kind specific
    if kind == "finding" and not cond and not note.get("derived"):
        issues.append({"severity": "warn", "kind": "no_condition", "detail": "finding without `cond:` - state the dataset / setting / assumption under which it holds (or `cond: none stated in the paper`)"})
    if kind == "section_summary" and note.get("sec") in sec_of(d) and anchors:
        off = [x[0] for x in anchors if not in_section(d, note["sec"], x[0])]
        if off:
            issues.append({"severity": "error", "kind": "section_alignment", "detail": "evidence outside section %s: %s (a section summary must cite its own section)" % (note["sec"], ", ".join(sorted(set(off))[:5]))})
    if kind not in ("section_summary", "meta") and nlib.wcount(text) > 75:
        issues.append({"severity": "warn", "kind": "atomicity", "detail": "note has %d words: split it into atomic notes (one claim each)" % nlib.wcount(text)})
    if kind not in ("meta",) and note.get("tags", "") == "":
        issues.append({"severity": "warn", "kind": "tags", "detail": "no tags: add 2-4 lower-case retrieval tags"})
    # --- duplicates
    if text:
        cw = nlib.content_words(text)
        for o in others:
            if o["id"] != note.get("id") and o["kind"] == kind and o.get("text"):
                ow = nlib.content_words(o["text"])
                if cw and ow and len(cw & ow) / len(cw | ow) >= 0.8:
                    issues.append({"severity": "warn", "kind": "duplicate", "detail": "near-duplicate of %s" % o["id"]})
                    break
    # --- undefined acronyms
    if text and lang_note == lang_src:
        ac = [x for x in set(nlib.acronyms(text + " " + cond)) if x not in ev_full and not any(x in (o.get("text") or "") + (o.get("term") or "") for o in others if o["kind"] == "definition")]
        if ac:
            issues.append({"severity": "warn", "kind": "acronym", "detail": "acronym(s) not found in the cited evidence nor defined: %s" % ", ".join(sorted(ac)[:4])})
    ver["anchors"] = len(anchors)
    return issues, ver


def status_of(issues):
    if any(i["severity"] == "error" for i in issues):
        return "error"
    return "warn" if issues else "ok"


def next_id(notes, kind):
    p = {"meta": "T", "question": "Q", "contribution": "C", "data": "D", "method": "M", "setting": "P", "assumption": "A", "finding": "F", "conclusion": "K", "limitation": "L",
         "definition": "G", "future": "U", "reproducibility": "R", "relation": "X", "section_summary": "S"}[kind]
    n = 1
    while "%s%d" % (p, n) in notes:
        n += 1
    return "%s%d" % (p, n)


def cmd_ingest(a):
    d, notes = load_all(a.work)
    bm = build_index(d)
    text = sys.stdin.read() if (not a.file or a.file == "-") else open(a.file, encoding="utf-8").read()
    recs = parse_note_jsonl(text) if text.lstrip().startswith("{") else parse_note_blocks(text)
    if not recs:
        raise SystemExit("no notes found: start each note with '=== finding' (kinds: %s)" % ", ".join(KINDS))
    n = Counter()
    lines = []
    for bad in sorted({m.group(1) for m in re.finditer(r"^\s*[#=*]{2,}\s*([A-Za-z_]+)", text, re.M) if m.group(1).lower() not in KINDS}):
        lines.append("ignored a block with unknown kind '%s' (kinds: %s)" % (bad, ", ".join(KINDS)))
    touched = set()
    for r in recs:
        kind = r["kind"]
        nid = r.get("id")
        replaced = False
        if not nid and kind == "meta":
            nid = next((k2 for k2, v2 in notes.items() if v2["kind"] == "meta"), None)
            replaced = bool(nid)
        if not nid:
            # resubmission without an id: a note whose wording is nearly the same as an existing one of the same kind REPLACES it
            cw = nlib.content_words((r.get("text") or "") + " " + (r.get("purpose") or "") + (r.get("sec") or ""))
            best, bj = None, 0.0
            for k2, v2 in notes.items():
                if v2["kind"] != kind or k2 in touched:
                    continue
                if kind == "section_summary":
                    if v2.get("sec") and v2["sec"] == ("§" + r.get("sec", "").lstrip("§")):
                        best, bj = k2, 1.0
                        break
                    continue
                ow = nlib.content_words((v2.get("text") or "") + " " + (v2.get("purpose") or ""))
                if cw and ow:
                    j = len(cw & ow) / len(cw | ow)
                    if j > bj:
                        best, bj = k2, j
            if best and bj >= 0.6:
                nid, replaced = best, True
        nid = nid or next_id(notes, kind)
        if kind == "section_summary" and not r.get("id") and r.get("sec") and not replaced:
            nid = "S" + (re.sub(r"[^0-9A-Za-z.]+", "", r["sec"].replace("§", "")) or nid[1:])
        touched.add(nid)
        tags = ", ".join(sorted({t.strip().lower() for t in re.split(r"[,;]", r.get("tags", "")) if t.strip()}))
        note = {"id": nid, "kind": kind, "text": (r.get("text") or "").strip(), "cond": (r.get("cond") or "").strip(), "ev": (r.get("ev") or "").strip(), "quote": split_quotes(r.get("quote")),
                "tags": tags, "status": (r.get("status") or "reported").strip().lower(), "conf": r.get("conf", ""), "note": r.get("note", ""), "derived": r.get("derived", ""),
                "searched": r.get("searched", ""), "sec": (("§" + r["sec"].lstrip("§")) if r.get("sec") else ""), "purpose": r.get("purpose", ""), "method": r.get("method", ""),
                "result": r.get("result", ""), "conclusion": r.get("conclusion", ""), "link": r.get("link", ""), "term": r.get("term", "")}
        for k in ("title", "authors", "year", "venue", "doi", "field"):
            if r.get(k):
                note[k] = r[k]
        if kind == "meta":
            note["text"] = note["text"] or "; ".join("%s: %s" % (k, note[k]) for k in ("title", "authors", "year", "venue", "doi", "field") if note.get(k))
        others = [v for k2, v in notes.items() if k2 != nid]
        issues, ver = validate_note(d, bm, {**note, "quote": " ||| ".join(note["quote"])}, others)
        note.update({"issues": issues, "verification": ver, "status_check": status_of(issues), "tries": notes.get(nid, {}).get("tries", 0) + 1, "ts": int(time.time())})
        notes[nid] = note
        n[note["status_check"]] += 1
        if replaced:
            lines.append("%s replaced the earlier version of this note (same wording; use id=%s to be explicit)" % (nid, nid))
        for iss in issues:
            if iss["severity"] == "error" or a.verbose:
                lines.append("%s %s %s: %s" % (nid, iss["severity"].upper(), iss["kind"], iss["detail"]))
    jsave(os.path.join(a.work, "notes.json"), notes)
    kinds = Counter(v["kind"] for v in notes.values() if v["status_check"] != "error")
    print("stored %d | ok %d | warn %d | ERROR %d | accepted notes by kind: %s" % (len(recs), n["ok"], n["warn"], n["error"], ", ".join("%s %d" % kv for kv in kinds.most_common())))
    print("ids: " + " ".join("%s%s" % (k, "*" if notes[k]["status_check"] == "error" else "") for k in sorted(touched, key=lambda x: (x[0], int(re.sub(r"\D", "", x) or 0)))) + "   (* = failing; resubmit with id=<id>)")
    for ln in lines[:40]:
        print("  " + ln)
    if n["error"]:
        print("Fix the ERROR notes and resubmit them with the same id (id=...) or `nc.py next %s`." % a.work)
    sys.exit(2 if n["error"] else 0)


# ------------------------------------------------------------------------------------------------ check / next
def covered_units(notes):
    cov = defaultdict(set)
    for n in notes.values():
        if n["status_check"] == "error":
            continue
        for uid, a_, b_ in parse_anchors(n.get("ev", ""))[0]:
            cov[uid].add(n["id"])
    return cov


def run_check(work):
    d, notes = load_all(work)
    secs = sec_of(d)
    good = {k: v for k, v in notes.items() if v["status_check"] != "error"}
    errs, warns, problems = [], [], []
    kinds = Counter(v["kind"] for v in good.values() if v.get("status", "reported") == "reported")
    not_rep = {v["kind"] for v in good.values() if v.get("status") == "not_reported"}
    cues = d["cues"]
    byu = {u["id"]: u for u in d["units"]}
    cov = covered_units(notes)
    # required fields
    missing_kinds = []
    for k in REQUIRED:
        if kinds[k] < KINDS[k][2] and k not in not_rep:
            missing_kinds.append(k)
    # section summaries
    need = [s for s in d["sections"] if not s["excluded"] and not s["optional"] and s["level"] <= 1 and s.get("words_total", s["words"]) >= 25]
    have = {v.get("sec") for v in good.values() if v["kind"] == "section_summary"}
    missing_secs = [s["id"] for s in need if s["id"] not in have]
    # not-reported claims versus cues
    contradictions = []
    for k in not_rep:
        if k in ("limitation", "future", "reproducibility"):
            ck = {"limitation": "limitation", "future": "future", "reproducibility": "availability"}[k]
            strong = [c for c in cues if ck in c["kinds"] and c["score"].get(ck, 0) >= 2]
            if strong:
                contradictions.append({"kind": k, "cues": ["%s.%d" % (c["unit"], c["sent"]) for c in strong[:4]]})
    # cue coverage
    def covered(c):
        return c["unit"] in cov
    lim = [c for c in cues if "limitation" in c["kinds"] and c["score"].get("limitation", 0) >= 2.5]
    lim_unc = [c for c in lim if not covered(c)]
    res_cues = [c for c in cues if "result" in c["kinds"] and c["score"].get("result", 0) >= 2 and re.search(r"\d", c["text"]) and
                re.search(r"result|experiment|evaluation|performance|analysis|ablation", secs[byu[c["unit"]]["section"]].get("path") or secs[byu[c["unit"]]["section"]]["title"], re.I)]
    res_unc = [c for c in res_cues if not covered(c)]
    # conflicts between definitions
    defs = defaultdict(set)
    for v in good.values():
        if v["kind"] == "definition" and v.get("term"):
            defs[v["term"].lower()].add(v["text"].strip().lower())
    conflicting = [t for t, s in defs.items() if len(s) > 1]
    # verification statistics
    nq = [q for v in good.values() for q in v["verification"].get("quotes", []) if q != "none"]
    n_ok_notes = sum(1 for v in good.values() if v["status_check"] == "ok")
    cond_missing = [v["id"] for v in good.values() if v["kind"] == "finding" and not v.get("cond") and not v.get("derived")]
    summary = {"notes": len(notes), "accepted": len(good), "with_errors": sum(1 for v in notes.values() if v["status_check"] == "error"), "with_warnings": sum(1 for v in good.values() if v["status_check"] == "warn"),
               "missing_required_fields": missing_kinds, "sections_needing_summary": len(need), "sections_missing_summary": missing_secs,
               "limitation_cues": "%d/%d covered" % (len(lim) - len(lim_unc), len(lim)), "result_cues": "%d/%d covered" % (len(res_cues) - len(res_unc), len(res_cues)),
               "quotes_verified": "%d/%d" % (sum(1 for q in nq if q == "verified"), len(nq)), "findings_without_condition": len(cond_missing), "conflicting_definitions": conflicting,
               "not_reported_contradicted": contradictions}
    return {"summary": summary, "uncovered_limitation_cues": ["%s.%d %s" % (c["unit"], c["sent"], c["text"][:110]) for c in lim_unc[:8]],
            "uncovered_result_cues": ["%s.%d %s" % (c["unit"], c["sent"], c["text"][:110]) for c in res_unc[:8]], "kinds": dict(kinds), "findings_without_condition": cond_missing[:10],
            "error_notes": [k for k, v in notes.items() if v["status_check"] == "error"], "ok_notes": n_ok_notes}


def cmd_check(a):
    rep = run_check(a.work)
    jsave(os.path.join(a.work, "check_report.json"), rep)
    s = rep["summary"]
    print(json.dumps(s, ensure_ascii=False))
    for k in s["missing_required_fields"]:
        print("MISSING required field: %s (%s) - write at least one note, or `status=not_reported` with `searched:`" % (k, KINDS[k][3]))
    if s["sections_missing_summary"]:
        print("MISSING section summaries: %s" % ", ".join(s["sections_missing_summary"]))
    for c in s["not_reported_contradicted"]:
        print("CONTRADICTION: you reported '%s' as not reported but the text has candidates: %s" % (c["kind"], ", ".join(c["cues"])))
    for x in rep["uncovered_limitation_cues"][:6]:
        print("UNCOVERED limitation cue: " + x)
    for x in rep["uncovered_result_cues"][:4]:
        print("UNCOVERED result sentence: " + x)
    if rep["findings_without_condition"]:
        print("findings without conditions: %s" % ", ".join(rep["findings_without_condition"]))
    bad = bool(s["missing_required_fields"] or s["sections_missing_summary"] or s["with_errors"] or s["conflicting_definitions"] or s["not_reported_contradicted"])
    sys.exit(2 if bad else 0)


def cmd_next(a):
    d, notes = load_all(a.work)
    rep = run_check(a.work)
    s = rep["summary"]
    st = load_state(a.work)
    el = int(time.time() - st.get("t0", time.time()))
    print("NEXT STEPS | elapsed %ds of %ds budget%s" % (el, st.get("budget_s", 900), " | LOW TIME: assemble now" if st.get("budget_s", 900) - el < 150 else ""))
    todo = 0
    if rep["error_notes"]:
        todo += 1
        print("1. FIX failing notes (resubmit with the same id): %s" % ", ".join(rep["error_notes"][:12]))
        for k in rep["error_notes"][:4]:
            for iss in notes[k]["issues"]:
                if iss["severity"] == "error":
                    print("     %s %s: %s" % (k, iss["kind"], iss["detail"][:200]))
    if s["missing_required_fields"]:
        todo += 1
        print("2. WRITE required fields: " + "; ".join("%s (%s)" % (k, KINDS[k][3]) for k in s["missing_required_fields"]))
    if s["sections_missing_summary"]:
        todo += 1
        secs = sec_of(d)
        print("3. WRITE section_summary (purpose/method/result/conclusion/link + ev inside the section) for: %s" % "; ".join("%s %s" % (i, secs[i]["title"][:30]) for i in s["sections_missing_summary"]))
    if rep["uncovered_limitation_cues"]:
        todo += 1
        print("4. CHECK these sentences - limitations / assumptions the paper states (cover with notes or ignore if not limitations):")
        for x in rep["uncovered_limitation_cues"][:6]:
            print("     " + x)
    if rep["uncovered_result_cues"]:
        todo += 1
        print("5. Result sentences with numbers not yet used as evidence:")
        for x in rep["uncovered_result_cues"][:4]:
            print("     " + x)
    if rep["findings_without_condition"]:
        print("6. Add `cond:` to findings: %s" % ", ".join(rep["findings_without_condition"][:8]))
    if not todo:
        print("Nothing blocking. Run `check`, then `assemble`.")


def load_state(work):
    return jload(os.path.join(work, "state.json"), {})


# ------------------------------------------------------------------------------------------------ assemble
def anchors_render(d, ev):
    byu = {u["id"]: u for u in d["units"]}
    out = []
    for uid, a_, b_ in parse_anchors(ev)[0]:
        if uid in byu:
            out.append(fmt_anchor(byu, uid, a_, b_))
    return out


def derive_meta(d, notes):
    m = {}
    for v in notes.values():
        if v["kind"] == "meta" and v["status_check"] != "error":
            for k in ("title", "authors", "year", "venue", "doi", "field"):
                if v.get(k):
                    m[k] = v[k]
    h = d["meta"]["hints"]
    if "title" not in m and h.get("title"):
        m["title"] = h["title"]
        m["title_source"] = "auto (parsed title)"
    if "year" not in m and h.get("years"):
        m["year_hint"] = h["years"][0]
    if "doi" not in m and h.get("doi"):
        m["doi"] = h["doi"][0]
    if h.get("arxiv"):
        m["arxiv"] = h["arxiv"][0]
    m["language"] = d["meta"]["lang"]
    return m


def note_public(d, v):
    byu = {u["id"]: u for u in d["units"]}
    anchors = parse_anchors(v.get("ev", ""))[0]
    pages = sorted({p for uid, _, _ in anchors if uid in byu for p in byu[uid]["pages"]})
    secs_ = sorted({byu[uid]["section"] for uid, _, _ in anchors if uid in byu})
    out = {k: v[k] for k in ("id", "kind", "text", "cond", "ev", "quote", "tags", "status", "conf", "note", "derived", "searched", "sec", "term") if v.get(k)}
    for k in ("purpose", "method", "result", "conclusion", "link"):
        if v.get(k):
            out[k] = v[k]
    out.update({"anchors": anchors_render(d, v.get("ev", "")), "pages": pages, "sections": secs_,
                "blocks": [byu[uid]["block"] for uid, _, _ in anchors if uid in byu and byu[uid].get("block")],
                "bboxes": [{"unit": uid, "page": byu[uid]["page"], "bbox": byu[uid]["bbox"]} for uid, _, _ in anchors if uid in byu and byu[uid].get("bbox")],
                "verification": {"checks": v["verification"], "status": v["status_check"], "issues": [i["kind"] + ": " + i["detail"] for i in v["issues"]]}})
    return out


def render_md(d, card, notes, rep):
    secs = d["sections"]
    L = []
    m = card["meta"]
    L += ["# %s" % (m.get("title") or d["meta"]["file"]), "", "> Structured note card (%s) · source `%s` · status **%s**. Every note carries evidence anchors `[Exxx.s · page · §section]`; `✓q` quote verified verbatim, `✓n` numbers found in the evidence."
          % (SCHEMA, d["meta"]["file"], card["status"]), ""]
    meta_rows = [(k, m[k]) for k in ("authors", "year", "venue", "doi", "arxiv", "field", "language") if m.get(k)]
    if meta_rows:
        L += ["| field | value |", "|---|---|"] + ["| %s | %s |" % (k, str(v).replace("|", "/")) for k, v in meta_rows] + [""]

    def mark(n):
        v = n["verification"]["checks"]
        b = []
        if "verified" in v.get("quotes", []):
            b.append("✓q")
        if v.get("numbers") == "ok":
            b.append("✓n")
        return " ".join(b)

    def line(n):
        anc = "; ".join(n["anchors"][:4]) or "no anchor"
        cond = ("  \n  _conditions:_ " + n["cond"]) if n.get("cond") else ""
        q = ("  \n  > " + " / ".join(n["quote"][:2])) if n.get("quote") else ""
        nt = ("  \n  _note:_ " + n["note"]) if n.get("note") else ""
        return "- **%s** %s %s `[%s]`%s%s%s" % (n["id"], n.get("text", ""), mark(n), anc, cond, q, nt)
    L += ["## Key fields", ""]
    for k, (label, field, req, desc) in KINDS.items():
        if k in ("meta", "section_summary", "setting", "relation", "definition", "future", "reproducibility", "assumption", "contribution") and not card["fields"].get(field):
            continue
        items = card["fields"].get(field, [])
        L += ["### %s" % label, ""]
        if not items:
            nr = [n for n in notes.values() if n["kind"] == k and n.get("status") in ("not_reported", "unclear")]
            L += ["- _not reported / not found_ " + ("(%s)" % (nr[0].get("searched") or nr[0].get("note", ""))) if nr else "- _missing_"]
        for n in items:
            L.append(line(n))
        L.append("")
    L += ["## Section-by-section (the paper's own skeleton)", ""]
    sm = {n["sec"]: n for n in card["fields"].get("section_summaries", [])}
    for s in secs:
        if s["excluded"] or not (s["units"] or s.get("words_total")):
            continue
        ind = "#" * min(6, 2 + max(0, (s["level"] or 1) - 1))
        L += ["%s %s %s (p%s)" % (ind, s["id"], s["title"], ",".join(map(str, s["pages"][:3])) or "-"), ""]
        n = sm.get(s["id"])
        if n:
            for k in ("purpose", "method", "result", "conclusion", "link"):
                if n.get(k):
                    L.append("- **%s:** %s" % (k, n[k]))
            if n.get("text"):
                L.append("- " + n["text"])
            L.append("- anchors: " + "; ".join(n["anchors"][:5]))
            L.append("")
        elif s["level"] <= 1 and not s["optional"]:
            L += ["- _no summary written_", ""]
    L += ["## Verification", ""]
    sres = rep["summary"]
    L += ["| check | result |", "|---|---|", "| notes accepted / with warnings / failing | %d / %d / %d |" % (sres["accepted"], sres["with_warnings"], sres["with_errors"]),
          "| quotes verified verbatim | %s |" % sres["quotes_verified"], "| limitation cues covered | %s |" % sres["limitation_cues"], "| numeric result sentences covered | %s |" % sres["result_cues"],
          "| section summaries missing | %s |" % (", ".join(sres["sections_missing_summary"]) or "none"), ""]
    L += ["**Machine-checked:** evidence ids exist and are citable; quotes are verbatim; numbers occur in the cited evidence; section summaries cite their own section; required fields and section coverage.  ",
          "**Needs a human:** whether a note truly captures the paper's meaning (wording support is only a lexical signal), whether conditions are complete, warnings listed in `review_checklist.md`.", ""]
    return "\n".join(L)


def checklist_md(d, card, notes, rep):
    L = ["# Human review checklist", "", "Machine checks catch missing evidence, non-verbatim quotes, unsupported numbers, wrong-section anchors and missing fields. They do **not** prove a note is a faithful summary.", ""]
    s = rep["summary"]
    L += ["## 1. Failing notes (%d)" % s["with_errors"]]
    for k in rep["error_notes"]:
        L.append("- %s: %s" % (k, "; ".join(i["kind"] + ": " + i["detail"] for i in notes[k]["issues"] if i["severity"] == "error")[:300]))
    if not rep["error_notes"]:
        L.append("- none")
    L += ["", "## 2. Missing"]
    L += ["- required field: %s" % k for k in s["missing_required_fields"]] + ["- section summary: %s" % x for x in s["sections_missing_summary"]]
    if not s["missing_required_fields"] and not s["sections_missing_summary"]:
        L.append("- none")
    L += ["", "## 3. Warnings to confirm"]
    n_w = 0
    for k, v in notes.items():
        if v["status_check"] == "warn":
            n_w += 1
            L.append("- %s [%s]: %s" % (k, v["kind"], "; ".join(i["kind"] + ": " + i["detail"] for i in v["issues"])[:300]))
    if not n_w:
        L.append("- none")
    L += ["", "## 4. Sentences that look like limitations / results but are not covered by any note"]
    L += ["- " + x for x in rep["uncovered_limitation_cues"] + rep["uncovered_result_cues"]] or ["- none"]
    L += ["", "## 5. Low-confidence or flagged by the author of the notes"]
    fl = [v for v in notes.values() if v.get("conf") in ("low", "medium") or v.get("status") in ("unclear", "conflict")]
    L += ["- %s [%s]: %s" % (v["id"], v["kind"], v.get("note") or v.get("conf") or v.get("status")) for v in fl] or ["- none"]
    L += ["", "## 6. Not reported (with where it was searched)"]
    nr = [v for v in notes.values() if v.get("status") == "not_reported"]
    L += ["- %s: %s" % (v["kind"], v.get("searched") or v.get("note")) for v in nr] or ["- none"]
    return "\n".join(L) + "\n"


def contract_fields(case):
    oc = find_key(case, ["output_contract", "outputContract", "output_schema", "outputs"]) if case else None
    fields = []

    def add(x):
        if isinstance(x, str) and x not in fields:
            fields.append(x)
    if isinstance(oc, list):
        for it in oc:
            add(it if isinstance(it, str) else (it.get("name") or it.get("field") or it.get("key")) if isinstance(it, dict) else None)
    elif isinstance(oc, dict):
        inner = oc.get("fields") or oc.get("required") or oc.get("properties") or oc.get("required_fields")
        if isinstance(inner, list):
            for it in inner:
                add(it if isinstance(it, str) else (it.get("name") or it.get("field") or it.get("key")) if isinstance(it, dict) else None)
        elif isinstance(inner, dict):
            for k in inner:
                add(k)
        else:
            for k in oc:
                if k not in ("type", "description", "title", "version", "schema", "$schema", "additionalProperties"):
                    add(k)
    return fields


def derive_field(name, ctx):
    n = name.lower()
    card, rep, d = ctx["card"], ctx["rep"], ctx["d"]
    f = card["fields"]
    if n in ("status", "run_status", "state", "outcome"):
        return True, card["status"]
    if n in ("sources", "source", "input", "inputs", "input_id", "input_identification", "input_files"):
        return True, [{"file": d["meta"]["file"], "format": d["meta"]["format"], "pages": d["meta"].get("pages"), "language": d["meta"]["lang"], "tool": "scholarly-note-cards %s" % VERSION}]
    if n in ("uncertainty", "uncertainties", "limitations_of_notes", "caveats", "risks", "unresolved", "uncertain_items"):
        return True, ctx["uncertainty"]
    if n in ("change_records", "changes", "change_log", "modifications", "edits"):
        return True, ctx["changes"]
    if n in ("card", "paper_card", "note_card", "structured_card", "notes_card", "structured_notes"):
        return True, card
    if n in ("summary", "abstract", "overview", "tldr", "paper_summary", "summary_text", "总结"):
        return True, card["summary"]
    if n in ("title", "paper_title", "metadata", "meta", "bibliography", "paper_info"):
        return True, card["meta"] if n in ("metadata", "meta", "bibliography", "paper_info") else card["meta"].get("title")
    for key in ("question", "research_question", "objective", "problem"):
        if n == key:
            return True, f.get("question", [])
    if n in ("data", "datasets", "materials", "data_materials", "dataset"):
        return True, f.get("data", [])
    if n in ("methods", "method", "approach", "methodology"):
        return True, f.get("methods", []) + f.get("settings", [])
    if n in ("findings", "main_findings", "results", "key_findings", "key_results"):
        return True, f.get("findings", [])
    if n in ("conclusions", "conclusion", "takeaways"):
        return True, f.get("conclusions", [])
    if n in ("limitations", "limitation", "constraints", "limitations_and_assumptions"):
        return True, f.get("limitations", []) + (f.get("assumptions", []) if n == "limitations_and_assumptions" else [])
    if n in ("assumptions", "premises", "conditions", "preconditions", "前提条件"):
        return True, f.get("assumptions", []) + [x for x in f.get("findings", []) if x.get("cond")]
    if n in ("contributions", "contribution"):
        return True, f.get("contributions", [])
    if n in ("definitions", "glossary", "terminology", "key_terms", "concepts", "knowledge_points", "knowledge_items"):
        return True, f.get("definitions", [])
    if n in ("future_work", "open_questions", "future"):
        return True, f.get("future_work", [])
    if n in ("reproducibility", "availability", "code_data_availability"):
        return True, f.get("reproducibility", [])
    if n in ("sections", "section_summaries", "structure", "outline", "skeleton", "section_notes", "章节总结"):
        return True, card["skeleton"] if n in ("structure", "outline", "skeleton") else card["sections"]
    if n in ("notes", "atomic_notes", "note_list", "items"):
        return True, ctx["notes_pub"]
    if n in ("evidence", "evidence_links", "anchors", "source_links", "provenance", "references_to_source", "evidence_map"):
        return True, [{"note": x["id"], "kind": x["kind"], "anchors": x["anchors"], "pages": x["pages"], "quote": x.get("quote")} for x in ctx["notes_pub"]]
    if n in ("verification", "checks", "qa", "validation", "quality", "self_check"):
        return True, {"summary": rep["summary"], "uncovered_limitation_cues": rep["uncovered_limitation_cues"], "uncovered_result_cues": rep["uncovered_result_cues"]}
    if n in ("human_review", "needs_review", "review_items", "todo", "manual_review", "to_confirm"):
        return True, ctx["review_items"]
    if n in ("tags", "keywords", "index_terms"):
        return True, sorted({t for x in ctx["notes_pub"] for t in (x.get("tags", "").split(", ") if x.get("tags") else [])})
    return False, None


def cmd_assemble(a):
    d, notes = load_all(a.work)
    rep = run_check(a.work)
    s = rep["summary"]
    pub = [note_public(d, v) for v in notes.values() if v["status_check"] != "error"]
    meta = derive_meta(d, notes)
    f = defaultdict(list)
    for n in pub:
        f[KINDS[n["kind"]][1]].append(n)
    sections = []
    for sct in d["sections"]:
        if sct["excluded"] or not (sct["units"] or sct.get("words_total")):
            continue
        sm = next((n for n in f["section_summaries"] if n.get("sec") == sct["id"]), None)
        sections.append({"id": sct["id"], "title": sct["title"], "level": sct["level"], "pages": sct["pages"], "units": [sct["first"], sct["last"]], "words": sct["words"], "parent": sct["parent"],
                         "optional": sct["optional"], "summary": ({k: sm[k] for k in ("purpose", "method", "result", "conclusion", "link", "text") if sm.get(k)} | {"anchors": sm["anchors"], "note": sm["id"]}) if sm else None})
    skeleton = [{"id": x["id"], "title": x["title"], "level": x["level"], "pages": x["pages"], "has_summary": x["summary"] is not None} for x in sections]
    complete = not (s["missing_required_fields"] or s["sections_missing_summary"] or s["with_errors"] or s["conflicting_definitions"] or s["not_reported_contradicted"] or d["meta"].get("unparsed"))
    status = "success" if complete else ("partial" if pub else "failed")
    def first_text(field, n=2):
        return " ".join(x["text"] for x in f.get(field, [])[:n])
    summary = " ".join(x for x in (first_text("question", 1), first_text("contributions", 2), first_text("findings", 3), first_text("conclusions", 1), ("Limitations: " + first_text("limitations", 2)) if f.get("limitations") else "") if x)
    card = {"schema": SCHEMA, "tool_version": VERSION, "status": status, "meta": meta, "summary": summary, "skeleton": skeleton, "fields": {k: f.get(k, []) for k in [v[1] for v in KINDS.values()]},
            "sections": sections, "verification": rep["summary"]}
    unc = []
    for k in s["missing_required_fields"]:
        unc.append({"kind": "missing_field", "detail": k})
    for x in s["sections_missing_summary"]:
        unc.append({"kind": "missing_section_summary", "detail": x})
    for k in rep["error_notes"]:
        unc.append({"kind": "failed_note", "note": k, "detail": "; ".join(i["detail"] for i in notes[k]["issues"] if i["severity"] == "error")[:300]})
    for u in d["meta"].get("unparsed", []):
        unc.append({"kind": "unparsed_input", "page": u.get("page"), "detail": "%s %s" % (u.get("reason"), u.get("detail", ""))})
    for w in d["meta"].get("parser_warnings", []):
        unc.append({"kind": "parser_warning", "detail": w})
    for v in notes.values():
        if v.get("status") in ("not_reported", "unclear", "conflict") or v.get("conf") == "low":
            unc.append({"kind": v.get("status") if v.get("status") != "reported" else "low_confidence", "note": v["id"], "detail": v.get("searched") or v.get("note") or ""})
    if s["with_warnings"]:
        unc.append({"kind": "warnings", "detail": "%d note(s) carry warnings: see review_checklist.md" % s["with_warnings"]})
    for x in rep["uncovered_limitation_cues"][:5]:
        unc.append({"kind": "uncovered_limitation_cue", "detail": x})
    changes = [{"change": "paragraphs re-joined across figures/columns/pages", "count": d["meta"].get("continuations_merged", 0)},
               {"change": "notes re-submitted after failing a check", "count": sum(1 for v in notes.values() if v.get("tries", 1) > 1)},
               {"change": "notes marked derived (value computed by the note author, not quoted)", "count": sum(1 for v in notes.values() if v.get("derived"))}]
    review = [{"note": k, "why": v["status_check"], "detail": "; ".join(i["kind"] + ": " + i["detail"] for i in v["issues"])[:300]} for k, v in notes.items() if v["status_check"] in ("error", "warn")]
    out = a.out
    os.makedirs(out, exist_ok=True)
    jsave(os.path.join(out, "card.json"), card)
    with open(os.path.join(out, "card.md"), "w", encoding="utf-8") as fh:
        fh.write(render_md(d, card, {n["id"]: n for n in pub}, rep))
    with open(os.path.join(out, "notes.jsonl"), "w", encoding="utf-8") as fh:
        for n in pub:
            fh.write(json.dumps(n, ensure_ascii=False) + "\n")
    jsave(os.path.join(out, "evidence_index.json"), {"source": d["meta"]["file"], "sections": d["sections"], "units": [{k: u[k] for k in ("id", "type", "section", "pages", "page", "bbox", "block", "excluded", "text", "sentences")} for u in d["units"]]})
    with open(os.path.join(out, "review_checklist.md"), "w", encoding="utf-8") as fh:
        fh.write(checklist_md(d, card, notes, rep))
    jsave(os.path.join(out, "check_report.json"), rep)
    ctx = {"card": card, "rep": rep, "d": d, "status": status, "uncertainty": unc, "changes": changes, "notes_pub": pub, "review_items": review}
    case = jload(a.case) if a.case and os.path.isfile(a.case) else None
    fields = contract_fields(case)
    answers = jload(a.answers, {}) if a.answers else {}
    cid = (find_key(case, ["case_id", "caseId"]) or find_key(case, ["id"])) if case else None
    result = {"case_id": cid}
    unfilled = []
    for fld in fields:
        if fld == "case_id":
            continue
        if fld in answers:
            result[fld] = answers[fld]
            continue
        ok, v = derive_field(fld, ctx)
        result[fld] = v if ok else None
        if not ok:
            unfilled.append(fld)
    for nm in ("status", "sources", "uncertainty", "change_records", "card", "verification", "human_review"):
        if nm not in result:
            result[nm] = answers.get(nm, derive_field(nm, ctx)[1])
    for k, v in answers.items():
        result.setdefault(k, v)
    if case is not None and cid is None:
        unfilled.append("case_id")
    result["_meta"] = {"generator": "scholarly-note-cards/nc.py %s" % VERSION, "contract_fields": fields, "unfilled_fields": unfilled, "contract_found": bool(fields),
                       "files": ["card.json", "card.md", "notes.jsonl", "evidence_index.json", "review_checklist.md", "check_report.json"]}
    jsave(os.path.join(out, "result.json"), result)
    print(json.dumps({"written": out, "status": status, "notes": "%d accepted / %d with errors" % (s["accepted"], s["with_errors"]), "missing_required_fields": s["missing_required_fields"],
                      "sections_missing_summary": s["sections_missing_summary"], "quotes_verified": s["quotes_verified"], "limitation_cues": s["limitation_cues"],
                      "unfilled_contract_fields": unfilled, "contract_found": bool(fields)}, ensure_ascii=False))
    if unfilled:
        print("UNFILLED contract fields (put them in answers.json and re-run assemble --answers): " + ", ".join(unfilled))
    if not fields and a.case:
        print("WARNING: no output_contract found in the case file: read /input/case.json and task.md and add the fields by hand via --answers")
    sys.exit(0 if ((not unfilled and fields) or not a.case) else 2)


# ------------------------------------------------------------------------------------------------ search / compare / status
def cmd_search(a):
    p = a.target
    notes = []
    if os.path.isfile(os.path.join(p, "notes.jsonl")):
        notes = [json.loads(l) for l in open(os.path.join(p, "notes.jsonl"), encoding="utf-8") if l.strip()]
    elif os.path.isfile(os.path.join(p, "notes.json")):
        d, nn = load_all(p)
        notes = [note_public(d, v) for v in nn.values() if v["status_check"] != "error"]
    else:
        raise SystemExit("no notes.jsonl / notes.json in %s" % p)
    if a.kind:
        notes = [n for n in notes if n["kind"] == a.kind]
    docs = [" ".join([n.get("text", ""), n.get("cond", ""), n.get("tags", ""), n.get("term", ""), " ".join(n.get(k, "") for k in ("purpose", "method", "result", "conclusion"))]) for n in notes]
    bm = nlib.BM25(docs)
    for i, sc in bm.top(a.query, a.k):
        n = notes[i]
        print("%s [%s] (%.1f) %s  <%s>" % (n["id"], n["kind"], sc, (n.get("text") or n.get("result") or n.get("purpose") or "")[:200], "; ".join(n["anchors"][:2])))


def cmd_compare(a):
    cards = [(os.path.basename(os.path.dirname(os.path.abspath(p))) or p, jload(p)) for p in a.cards]
    fields = [x.strip() for x in a.fields.split(",")]
    rows = []
    for name, c in cards:
        r = {"paper": c["meta"].get("title") or name}
        for f in fields:
            r[f] = "; ".join((x.get("text") or "")[:140] for x in c["fields"].get(f, [])[:3])
        rows.append(r)
    if a.format == "csv":
        import csv
        w = csv.writer(sys.stdout)
        w.writerow(["paper"] + fields)
        for r in rows:
            w.writerow([r["paper"]] + [r[f] for f in fields])
    else:
        print("| paper | " + " | ".join(fields) + " |")
        print("|---|" + "---|" * len(fields))
        for r in rows:
            print("| %s | " % r["paper"][:60].replace("|", "/") + " | ".join(r[f].replace("|", "/") for f in fields) + " |")


def cmd_drop(a):
    d, notes = load_all(a.work)
    gone = [i for i in a.ids if notes.pop(i, None) is not None]
    jsave(os.path.join(a.work, "notes.json"), notes)
    print("dropped: %s | not found: %s" % (", ".join(gone) or "-", ", ".join(i for i in a.ids if i not in gone) or "-"))


def cmd_status(a):
    d, notes = load_all(a.work)
    c = Counter(v["status_check"] for v in notes.values())
    st = load_state(a.work)
    print(json.dumps({"units": len(d["units"]), "sections": len(d["sections"]), "notes": len(notes), "ok": c["ok"], "warn": c["warn"], "error": c["error"],
                      "elapsed_s": int(time.time() - st.get("t0", time.time())), "budget_s": st.get("budget_s")}))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("input")
    p.add_argument("--work", required=True)
    p.add_argument("--case")
    p.add_argument("--pages")
    p.add_argument("--lang", default="auto")
    p.add_argument("--budget", type=int, default=900)
    p.add_argument("--ocr", choices=["auto", "off", "force"])
    p.set_defaults(fn=cmd_prepare)
    p = sub.add_parser("outline")
    p.add_argument("work")
    p.set_defaults(fn=cmd_outline)
    p = sub.add_parser("read")
    p.add_argument("work")
    p.add_argument("--sec")
    p.add_argument("--ids")
    p.add_argument("--page", type=int)
    p.add_argument("--cue")
    p.add_argument("--top", type=int, default=12)
    p.add_argument("--sentences", action="store_true")
    p.add_argument("--max-words", type=int, default=1500)
    p.set_defaults(fn=cmd_read)
    p = sub.add_parser("find")
    p.add_argument("work")
    p.add_argument("query")
    p.add_argument("-k", type=int, default=5)
    p.set_defaults(fn=cmd_find)
    p = sub.add_parser("cues")
    p.add_argument("work")
    p.add_argument("--kind")
    p.add_argument("--top", type=int, default=12)
    p.set_defaults(fn=cmd_cues)
    p = sub.add_parser("ingest")
    p.add_argument("work")
    p.add_argument("file", nargs="?")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(fn=cmd_ingest)
    p = sub.add_parser("next")
    p.add_argument("work")
    p.set_defaults(fn=cmd_next)
    p = sub.add_parser("check")
    p.add_argument("work")
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("assemble")
    p.add_argument("work")
    p.add_argument("--out", required=True)
    p.add_argument("--case")
    p.add_argument("--answers")
    p.set_defaults(fn=cmd_assemble)
    p = sub.add_parser("search")
    p.add_argument("target")
    p.add_argument("query")
    p.add_argument("--kind")
    p.add_argument("-k", type=int, default=8)
    p.set_defaults(fn=cmd_search)
    p = sub.add_parser("compare")
    p.add_argument("cards", nargs="+")
    p.add_argument("--fields", default="question,data,methods,findings,limitations")
    p.add_argument("--format", choices=["md", "csv"], default="md")
    p.set_defaults(fn=cmd_compare)
    p = sub.add_parser("drop")
    p.add_argument("work")
    p.add_argument("ids", nargs="+")
    p.set_defaults(fn=cmd_drop)
    p = sub.add_parser("status")
    p.add_argument("work")
    p.set_defaults(fn=cmd_status)
    a, extra = ap.parse_known_args(argv)
    if extra:
        if a.cmd == "ingest" and extra == ["-v"]:
            a.verbose = True
        elif a.cmd == "ingest" and len(extra) == 1 and not a.file:
            a.file = extra[0]
        else:
            ap.error("unrecognized arguments: " + " ".join(extra))
    a.fn(a)


if __name__ == "__main__":
    main()
