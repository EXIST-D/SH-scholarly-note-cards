# scholarly-note-cards · 论文结构化笔记卡 Skill

面向「阅读10｜文献总结与结构化笔记」：把一篇论文变成**可核验、可检索、可比较的笔记卡**——研究问题、数据、方法及其条件、
主要发现及其成立的前提、局限与假设、术语定义，以及**按论文自身章节顺序**写成的章节摘要。笔记由模型阅读后撰写；凡是「必须确定、
可以复核」的事情都交给脚本：证据单元化（`E012`、句级 `E012.3`、页码、bbox）、笔记提交即核验（引文是否逐字出自原文、数字是否出现在所引证据里、
章节是否对得上）、缺项与漏项提示、检索与对比、人工复核清单。

> 文中的数字都来自我的开发自测（2 张真实论文卡片 + 1 张虚构示例卡片 + QASPER 公开数据集检索），**不是平台成绩**；卡片由开发者本人通过本工具撰写，
> 没有与「不加载 Skill 的模型」做过对照，因此不宣称相对基线的提升。

## 对应题面的四个问题
| 题面问题 | 做法 | 自查手段 |
|---|---|---|
| 对得上 | `outline` 给出论文自己的标题树（`3.2` / `V.` / `A.` 等编号、Markdown 与 Word 层级归一）；每个顶层章节必须有一条 `section_summary`（purpose / method / result / conclusion / link 到相邻章节），并按论文顺序输出；摘要必须引用**本章节内**的证据 | `check`：缺失章节、章节对齐错误 |
| 留得住 | 必备字段（问题、贡献、数据、方法、发现、结论、局限）；发现必须写 `cond:`（成立条件）；`assumption`/`limitation` 单独成类；线索检测列出「像局限/假设/贡献/结果」的句子防止遗漏；论文内部自相矛盾用 `status=conflict` 记录 | 「声称未报告但原文有线索」会被拒绝；未覆盖线索清单 |
| 找得回 | 每条笔记必须有证据锚点；引文逐字验证；数字必须出现在所引单元；`evidence_index.json` 连到页码/bbox/解析块 | `ingest` 当场报错并指出数字或引文真正所在的单元 |
| 用得上 | 所有论文同一套 schema；`notes.jsonl` 原子笔记带标签与锚点；`search` 检索笔记；`compare` 并排比较多篇；`card.md` 给人看、`card.json` 给程序用；清单标明哪些必须人工确认 | 复核清单 `review_checklist.md` |

## 目录
```
SKILL.md                         Agent 入口：何时用、步骤、笔记块格式、写作规则、异常处理
README.md                        本文件
scripts/nc.py                    命令行：prepare / outline / read / find / cues / ingest / next / check / assemble / search / compare / drop / status
scripts/nlib.py                  归一化、BM25、句子切分、数字、线索词（纯标准库）
scripts/parse_pdf.py             PDF 解析（来自 scholarly-pdf-parser v1.0.0，含 OCR 接入与一处重复片段修复）
references/field-dictionary.md   字段字典、锚点格式、输出文件、result.json 推导规则
references/checks.md             每项检查的规则、严重度、实测检出率与盲区
references/failure-modes.md      故障现象 → 处置
references/method-notes.md       设计依据、预算、已知限制
examples/                        虚构示例论文、示例笔记、最小调用示例（真实运行输出）、虚构契约
GITHUB_URL.txt                   作品的 GitHub 公开链接
dev/ （仅仓库）                  评测脚本与夹具：植入缺陷评测、QASPER 检索评测、真实论文笔记
```

## 依赖与安装
- Python 3.8+，笔记流程只用标准库。
- PDF 输入用自带 `scripts/parse_pdf.py`，需要 `pymupdf`（可回退 `pdfplumber` / `pypdf`）；扫描件需要 OCR：`pip install rapidocr`（模型已打包，运行时不联网，中英文）或 `tesseract`。
- Markdown / 文本 / LaTeX / `.docx`（段落、标题、表格）/ `.json` 无需额外依赖。中文论文可用（线索词、字数统计、引文与数字核验均支持）。
- 版本与来源：PyPI 官方包；开发环境 Python 3.11、pymupdf 2.1、rapidocr 3.10。

## 使用步骤
```bash
python3 scripts/nc.py prepare paper.pdf --work W [--case /input/case.json]   # 解析成证据单元，列出章节骨架与线索
python3 scripts/nc.py outline W                                              # 论文自己的章节结构
python3 scripts/nc.py read W --sec 3 [--sentences]                           # 阅读（带单元编号）
python3 scripts/nc.py ingest W < notes.txt                                   # 提交笔记，立即核验（也可 heredoc）
python3 scripts/nc.py next W                                                 # 还缺什么、哪些要修
python3 scripts/nc.py check W                                                # 全卡核验与覆盖
python3 scripts/nc.py assemble W --out out --case /input/case.json           # 卡片、索引、清单、result.json
python3 scripts/nc.py search out "关键词" --kind finding                     # 检索笔记
```
笔记块格式（无需 JSON 转义）：
```
=== finding
text: 一条原子化的发现。
cond: 成立条件（数据集/设置/假设）。
ev: E104, E101.2
quote: "从证据中逐字复制的片段"
tags: bleu, translation
```
完整示例（真实运行输出）见 `examples/minimal-example.md`。

## 输出
`card.md` · `card.json` · `notes.jsonl`（原子笔记）· `evidence_index.json`（锚点来源）· `review_checklist.md` · `check_report.json` ·
`result.json`（契约字段 + `case_id` + `status` + `sources` + `uncertainty` + `change_records`；推导不出的字段置 `null` 并列出，不编造）。

## 实测（开发自测，非平台成绩）
对**两张已完成的真实论文卡片**（Attention Is All You Need，51 条笔记；LIGO GW150914，30 条笔记）逐个植入缺陷，用 `ingest` 同一套核验检测（`dev/seeded_notes_eval.py`）：

| 植入的缺陷 | 检出（任一提示） | 错误级检出 |
|---|---|---|
| 伪造引文（改两个词） | 100 % / 100 % | 100 % / 100 % |
| 释义冒充引文 | 100 % / 100 % | 100 % / 100 % |
| 锚点指到别的章节（带引文） | 100 % / 100 % | 100 % / 100 % |
| 锚点指到别的章节（无引文） | 95 % / 100 % | 79 % / 81 % |
| 数字被改 | 94 % / 100 % | 94 % / 83 % |
| 删掉证据锚点 | 100 % / 100 % | 100 % / 100 % |
| 夸大（"proving it is superior…"） | 100 % / 100 % | 0 %（设计为警告） |
| 弱化词被换成 "clearly demonstrates" | 43 % / 60 % | 0 %（设计为警告） |
| 章节摘要引了别的章节 | 100 % / 100 % | 100 % / 100 % |
| 正文被换成无关句子 | 86 % / 71 % | 56 % / 52 % |
| 删掉否定词 | 33 % / 33 % | 0 %（设计为警告） |
| 删掉一条章节摘要 / 删光局限 / 「局限=未报告」但原文有线索 | 均检出 | — |

对正确笔记：错误级误报 0；各有 2、3 条合理警告。
证据检索（`find`）在公开数据集 QASPER 验证集（281 篇 NLP 论文，888 个带人工证据段落的问题）上：召回@1 0.23、@3 0.50、@5 0.64、@10 0.80，MRR 0.41；随机选 5 段为 0.21
（QASPER 的问题只依据标题和摘要撰写，是偏保守的代理）。

## 已知限制
- 检查是规则式的：笔记换了意思但沿用原文词汇（主语互换、比较方向反）能通过词汇检查；弱化/否定检测依赖词表（上表 43 % / 33 %）；「哪些发现算主要发现」由撰写者判断。
- 线索检测是词表式（英文 + 基础中文），其他语言没有线索。
- PDF 质量决定上限：扫描件依赖 OCR；图片形式的图表/公式不在文本层；复杂表格为启发式重建。
- 没有标题的文档（信件、部分短报告）会被当成一个大章节。
- 未在评测模型（DeepSeek）和真实预算下实跑；未测英中之外的语言、超过 30 页论文的完整写作流程、含图片/文本框的 Word。
- 请求数估计（约 12–16 次/10 页论文）是按流程推算，不是实测。

## 版本与维护
`nc.py` 1.0.0 · schema `scholarly-note-cards/1` · 问题与改进请在 GitHub 仓库提 issue。
