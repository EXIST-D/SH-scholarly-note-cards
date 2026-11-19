"""nlib - text analysis helpers for evidence-linked paper notes (standard library only).

Normalisation, tokenisation, BM25 retrieval, sentence splitting, numbers, cue detection (limitations, contributions, results,
data, settings, definitions), hedge / strength lexicons, acronyms. Nothing here calls a model.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

CJK_RE = re.compile(r"[㐀-鿿豈-﫿]")
LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "­": ""}


def cjk_ratio(text):
    c = len(CJK_RE.findall(text))
    l = len(re.findall(r"[A-Za-z]", text))
    return c / (c + l) if c + l else 0.0


def detect_lang(text):
    return "zh" if cjk_ratio(text) > 0.3 else "en"


def norm(s):
    """Fold typography so PDF text and a model's quote compare equal."""
    s = unicodedata.normalize("NFKC", s or "")
    for k, v in LIGATURES.items():
        s = s.replace(k, v)
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-").replace("−", "-")
    s = re.sub(r"(?<=[A-Za-z])-\s*\n\s*(?=[a-z])", "", s)
    return re.sub(r"\s+", " ", s).strip()


def squash(s):
    """Letters/digits/CJK only, lower-case: robust verbatim comparison independent of spacing and punctuation."""
    return re.sub(r"[\W_]+", "", norm(s).lower())


# ------------------------------------------------------------------------------------------------ tokens / BM25
STOP = set("""a an the of in on at to for from by with without within into onto over under between among across about as is are was were be been being this that these those
it its their our we you they he she i and or but nor so yet if then than which who whom whose what when where while although because since not no can could may might will would shall
should must also such more most less least both either each other another same different new one two three first second third use used using based show shown shows paper work approach method
methods result results however thus therefore hence et al fig figure table section""".split())


def stem(w):
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    for suf in ("ization", "isation", "ations", "ation", "ings", "ing", "ness", "ments", "ment", "edly", "ed", "ly", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            if suf in ("es", "s") and (w.endswith("ss") or w.endswith("us") or w.endswith("is")):
                return w
            return w[: -len(suf)]
    return w


def tokens(text, keep_stop=False):
    text = norm(text).lower()
    out = []
    for w in re.findall(r"[a-z0-9]+(?:[-'][a-z0-9]+)*|[㐀-鿿]", text):
        if CJK_RE.match(w):
            out.append(w)
            continue
        for part in re.split(r"[-']", w) if "-" in w else [w]:
            if not part or (part in STOP and not keep_stop) or (len(part) < 2 and not part.isdigit()):
                continue
            out.append(stem(part))
    return out


def content_words(text):
    return set(tokens(text))


class BM25:
    def __init__(self, docs, k1=1.2, b=0.75):
        self.k1, self.b = k1, b
        self.docs = [tokens(d) for d in docs]
        self.n = len(self.docs)
        self.avg = (sum(len(d) for d in self.docs) / self.n) if self.n else 1.0
        df = Counter()
        for d in self.docs:
            df.update(set(d))
        self.idf = {t: math.log(1 + (self.n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.tf = [Counter(d) for d in self.docs]
        self.bigrams = [Counter(zip(d, d[1:])) for d in self.docs]

    def score(self, query, bigram_boost=0.3):
        q = tokens(query)
        qb = list(zip(q, q[1:]))
        res = []
        for i, tf in enumerate(self.tf):
            ln = len(self.docs[i]) or 1
            s = 0.0
            for t in set(q):
                f = tf.get(t, 0)
                if f:
                    s += self.idf.get(t, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * ln / self.avg))
            if bigram_boost and qb:
                s += bigram_boost * sum(self.idf.get(a, 0) for a, b2 in qb if self.bigrams[i].get((a, b2)))
            res.append(s)
        return res

    def top(self, query, k=5):
        sc = self.score(query)
        order = sorted(range(len(sc)), key=lambda i: -sc[i])
        return [(i, sc[i]) for i in order[:k] if sc[i] > 0]


# ------------------------------------------------------------------------------------------------ sentences
ABBR = {"e.g", "i.e", "et al", "al", "fig", "figs", "eq", "eqs", "vs", "approx", "dr", "prof", "no", "sec", "ref", "refs", "cf", "ca", "inc", "ltd", "resp", "etc", "viz",
        "st", "mr", "mrs", "ms", "jr", "sr", "vol", "pp", "ed", "eds", "dept", "univ", "col", "ch", "tab", "est", "max", "min", "avg", "ie", "eg", "p", "sp", "var"}


def split_sentences(text):
    text = text.strip()
    if not text:
        return []
    out, start, n, i = [], 0, len(text), 0
    while i < n:
        ch = text[i]
        if ch in "。！？":
            j = i + 1
            while j < n and text[j] in "”’）」』\"')":
                j += 1
            out.append(text[start:j].strip())
            start = j
            i = j
            continue
        if ch in ".!?":
            j = i + 1
            while j < n and text[j] in "\"'”’)]":
                j += 1
            if j >= n or not text[j].isspace():
                i = j
                continue
            k = j
            while k < n and text[k].isspace():
                k += 1
            if k >= n:
                i = j
                continue
            c = text[k]
            boundary = c.isupper() or c.isdigit() or c in "\"“'‘([" or CJK_RE.match(c) is not None
            if ch == ".":
                m = re.search(r"([A-Za-z.]+)$", text[start:i])
                word = (m.group(1) if m else "").lower().rstrip(".")
                if word in ABBR:
                    boundary = False
                elif len(word) == 1 and word.isalpha() and text[i - 1].isupper():
                    boundary = False
                elif re.search(r"(^|\s)\d+$", text[start:i]) and start == 0 and not out:
                    boundary = False
                elif c.islower():
                    boundary = False
            if boundary:
                out.append(text[start:j].strip())
                start = k
            i = j
            continue
        i += 1
    if start < n and text[start:].strip():
        out.append(text[start:].strip())
    return out


# ------------------------------------------------------------------------------------------------ numbers
NUM_RE = re.compile(r"(?<![\w.])[-−–+±]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])[-−–+±]?\d+(?:\.\d+)?(?:[eE][-+−]?\d+)?")
CITE_RE = re.compile(r"\[\s*\d+(?:\s*[-–,;]\s*\d+)*\s*\]")
REF_RE = re.compile(r"\b(?:Figures?|Figs?\.?|Tables?|Tab\.?|Equations?|Eqs?\.?|Sections?|Sec\.?|§|Appendix|Algorithms?)\s*\(?[A-Z]?\d+(?:\.\d+)*[a-z]?\)?", re.I)
YEAR_RE = re.compile(r"\b(19|20)\d{2}[a-z]?\b")


def norm_num(s):
    s = s.replace("−", "-").replace("–", "-").replace(",", "").strip()
    if s.startswith("+"):
        s = s[1:]
    if re.fullmatch(r"-?\d+\.\d+", s):
        s = s.rstrip("0").rstrip(".")
    return s


def numbers(text, drop_refs=True):
    """Numbers that carry a claim: citation markers, 'Figure 3' style references and years in citations are removed first."""
    t = norm(text)
    t = re.sub(r"\b10\s*\^\s*[-+]?\s*(?=\d)|\b10[-+](?=\d)", "10 ", t)  # 10^-9, 10-9 (lost superscript) -> "10 9" on both sides
    if drop_refs:
        t = CITE_RE.sub(" ", t)
        t = REF_RE.sub(" ", t)
        t = re.sub(r"\([A-Z][A-Za-z'\-]+(?: et al\.?)?(?:,| and [A-Z][a-z]+,?)? ?\d{4}[a-z]?(?:[;,] ?[A-Z][^()]{0,60}\d{4}[a-z]?)*\)", " ", t)
        t = re.sub(r"\b[A-Z][A-Za-z'\-]+ et al\.? ?\(?\d{4}[a-z]?\)?", " ", t)
    return [norm_num(x) for x in NUM_RE.findall(t) if norm_num(x) not in ("", "-", "+")]


def numbers_ev(text):
    """Numbers present in EVIDENCE text: only bracketed citation markers are dropped (years, 'Table 2' etc. are legitimate evidence)."""
    t = norm(text)
    t = re.sub(r"\b10\s*\^\s*[-+]?\s*(?=\d)|\b10[-+](?=\d)", "10 ", t)
    t = CITE_RE.sub(" ", t)
    out = [norm_num(x) for x in NUM_RE.findall(t) if norm_num(x) not in ("", "-", "+")]
    for x in list(out):  # PDF text layers glue 10^13 into "1013": accept it as 10 and 13 as well
        m = re.fullmatch(r"10(\d{1,2})", x)
        if m:
            out += ["10", m.group(1).lstrip("0") or "0"]
    return out


# ------------------------------------------------------------------------------------------------ cues
CUES = {
    "limitation": re.compile(r"\b(limitations?|limited to|limits?|cannot|can not|could not|can't|fail(?:s|ed|ure)?(?: to)?|does not|do not|did not|doesn't|don't|unable|not able|only (?:works|applies|holds|valid|tested|evaluated|considers?)|"
                             r"assum(?:e|es|ed|ing|ption|ptions)|under the assumption|restricted|restricts?|constraints?|caveats?|future work|left (?:for|to)|beyond the scope|remains? (?:unclear|open|challenging|unknown)|"
                             r"drawbacks?|shortcomings?|weakness(?:es)?|trade-?offs?|sensitive to|depends? on|depending on|degrad(?:e|es|ation)|not (?:yet |been )?(?:tested|evaluated|considered|explored|investigated|addressed)|"
                             r"biases?|biased|threats? to validity|overfit(?:s|ting)?|lack(?:s|ing)? of|insufficient|small(?:er)? (?:sample|dataset)|unclear|uncertain(?:ty)?|may not|might not|not generali[sz]e|"
                             r"incomplete|miss(?:es|ed|ing)?|underestimat\w+|overestimat\w+|coarse|cannot resolve|untested|unverified|not validated|only (?:one|a single|two))\b", re.I),
    "contribution": re.compile(r"\b(we (?:propose|introduce|present|develop|show|demonstrate|find|observe|prove|derive|report|establish|describe|build|release|provide|study|investigate|analy[sz]e)|"
                               r"our (?:main |key |major )?contributions?|in this (?:paper|work|study|article)|this (?:paper|work|study|article) (?:proposes?|presents?|introduces?|shows?|investigates?|studies)|novel|new (?:method|approach|framework|model|dataset|benchmark))\b", re.I),
    "result": re.compile(r"\b(outperform(?:s|ed|ing)?|improv(?:e|es|ed|ement|ements|ing)|achiev(?:e|es|ed|ing)|reduc(?:e|es|ed|tion)|increas(?:e|es|ed|ing)|decreas(?:e|es|ed|ing)|higher|lower|better|worse|"
                          r"state-of-the-art|sota|accuracy|f1|bleu|rouge|error rate|precision|recall|auc|rmse|mae|speed-?up|faster|slower|significant(?:ly)?)\b", re.I),
    "data": re.compile(r"\b(data ?sets?|corpus|corpora|benchmark|samples?|participants|subjects|patients|collected|annotated|train(?:ing)? (?:set|data|split)|test (?:set|data|split)|validation (?:set|split)|"
                       r"evaluated on|trained on|we use the|sourced from|obtained from|stations?|specimens?|cohort|measurements?|observations?|survey)\b", re.I),
    "setting": re.compile(r"\b(learning rate|batch size|epochs?|optimi[sz]er|hyper-?parameters?|dropout|weight decay|warm-?up|layers?|hidden (?:size|dimension|units)|heads?|iterations?|steps?|seed|gpu|tpu|"
                          r"temperature|threshold|window|sampling (?:rate|frequency)|resolution|kernel|parameters)\b", re.I),
    "definition": re.compile(r"\b(we define|is defined as|are defined as|denote[sd]?|refers? to|stands? for|is called|are called|known as|termed)\b|\((?:[A-Z][A-Za-z0-9\-]{1,10}s?)\)", re.I),
    "future": re.compile(r"\b(future work|in the future|future research|we plan to|left for future|will explore|further (?:work|research|studies|investigation))\b", re.I),
    "availability": re.compile(r"\b(code|data|models?|implementation|checkpoints?) (?:is|are|will be|has been|have been)? ?(?:publicly )?(?:available|released|open-?sourced?)|github\.com|https?://|doi\.org|zenodo|supplementary|reproducib", re.I),
}
LIMIT_SECTIONS = re.compile(r"limitation|discussion|conclusion|future|threat|caveat|analysis|ablation|error", re.I)


def wcount(text):
    """Word count that also works for Chinese: Latin words + CJK characters / 1.6."""
    return len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", text)) + int(len(CJK_RE.findall(text)) / 1.6)


CUES_ZH = {
    "limitation": re.compile(r"局限|不足|缺点|缺陷|仅适用|仅限|只适用|只能|无法|不能|不适用|假设|假定|前提|条件下|尚未|有限|偏差|误差较大|下降|难以|未能|风险|不确定|受限|漏|不完整|不具"),
    "contribution": re.compile(r"本文提出|我们提出|本文的贡献|主要贡献|创新|首次|本文介绍|本研究|本文设计|本文构建"),
    "result": re.compile(r"准确率|精度|召回|提高|提升|优于|高于|低于|降低|达到|增加|减少|显著|误差|结果表明|实验表明"),
    "data": re.compile(r"数据集|样本|语料|采集|标注|训练集|测试集|验证集|受试者|观测|调查|测量"),
    "setting": re.compile(r"学习率|批大小|轮次|优化器|超参数|参数|层数|迭代|阈值|分辨率|采样"),
    "definition": re.compile(r"定义为|称为|是指|指的是|简称|记为|表示为"),
    "future": re.compile(r"未来|下一步|后续研究|进一步研究|今后|将继续|有待"),
    "availability": re.compile(r"开源|代码|公开|github|数据可得|补充材料"),
}


def classify_sentence(sent, section=""):
    """Cue kinds a sentence belongs to (a sentence may have several)."""
    if cjk_ratio(sent) > 0.3:
        out = []
        for k, rx in CUES_ZH.items():
            if rx.search(sent):
                if k in ("result", "setting") and not re.search(r"\d", sent):
                    continue
                if k == "limitation" and wcount(sent) < 5:
                    continue
                out.append(k)
        return out
    kinds = []
    for k, rx in CUES.items():
        if rx.search(sent):
            if k == "result" and not re.search(r"\d", sent):
                continue
            if k == "setting" and not re.search(r"\d|=", sent):
                continue
            if k == "limitation" and len(sent.split()) < 6:
                continue
            kinds.append(k)
    return kinds


HEDGE = re.compile(r"\b(may|might|could|can possibly|possibly|perhaps|probably|likely|unlikely|suggest(?:s|ed|ing)?|appear(?:s|ed|ing)? to|seem(?:s|ed|ing)?|tend(?:s|ed)? to|potentially|presumably|"
                   r"preliminary|partially|partly|somewhat|roughly|approximately|about|around|largely|mostly|generally|typically|often|sometimes|in some cases|indicat(?:e|es|ed|ing)|hypothesi[sz]e)\b", re.I)
STRONG = re.compile(r"\b(prove[sd]?|proof|demonstrat(?:e|es|ed|ing)|confirm(?:s|ed|ing)?|establish(?:es|ed)?|always|never|entirely|completely|definitely|clearly|"
                    r"conclusively|dramatically|substantially|eliminate[sd]?|solve[sd]?|guarantee[sd]?)\b", re.I)
OVERCLAIM = re.compile(r"\b(state-of-the-art|sota|first|novel|best|superior|outperform(?:s|ed)?|significantly|breakthrough|unprecedented|optimal|robust|proven|universally|every|always|never|guaranteed?)\b", re.I)
NEGATION = re.compile(r"\b(not|no|never|neither|nor|none|without|cannot|can't|isn't|aren't|don't|doesn't|didn't|won't|fail(?:s|ed)? to|unable|lack(?:s|ed|ing)?|absence|insufficient|insignificant|unlikely)\b", re.I)
ACRONYM_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,}[a-z]?\b")
ACRONYM_OK = {"AND", "OR", "THE", "FOR", "ET", "AL", "II", "III", "IV", "OK", "US", "UK", "EU", "ID", "QA"}


def acronyms(text):
    return [a for a in ACRONYM_RE.findall(text) if a not in ACRONYM_OK and not re.fullmatch(r"\d+", a)]
