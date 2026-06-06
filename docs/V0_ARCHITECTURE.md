# V0_ARCHITECTURE.md — Legacy Prototype (Deprecated)

> **Read this for context only.** This documents the v0 prototype that the
> current project replaces. Do **not** replicate its patterns, framing, or
> output format — it is here so you understand the starting point of the
> migration, not as a template.
> Original repo (read-only reference): https://github.com/Praatyush/financial_report_analyzer

## What v0 was

A batch **financial-report summarizer** packaged as a double-click desktop app
for non-technical users. The user pasted a list of PDF URLs into a text file;
the app downloaded each PDF, summarized it, and wrote one `.txt` summary per
company. There was **no retrieval, no structured data, no evaluation, and no
live data** — it compressed whole documents into fixed prose buckets.

## Data flow

```
urls.txt → download PDF → extract text (pdfplumber) → clean →
chunk (~2500 words) → summarize each chunk (LLM, "map") →
combine chunk summaries (LLM, "reduce") → write <company>_analysis.txt
```

A classic **map-reduce summarization** pipeline. Every run reads the *entire*
document; nothing is indexed or retrieved.

## Stack

- Python 3.7+
- OpenAI SDK — `gpt-4o-mini`
- `pdfplumber` (extraction), `requests` (download), `python-dotenv`
- `tkinter` (GUI popups), PyInstaller (packaged `.app` / executable)
- **No** vector store, embeddings, retrieval, agents, tools, or evals

## Output buckets (the wrong domain)

v0 summarized into six **financial** categories: Executive Summary, Financial
Performance, Strategic Initiatives, Risk Factors, Future Outlook, Regional
Performance (NA / Europe). This generic-financial framing is the version that
*missed the real objective*. The target system pivots to product-level
**oncology clinical intelligence** — see `ARCHITECTURE.md`.

## Why it's being rewritten (limitations)

1. **Summarizes, can't answer.** No Q&A or fact retrieval over a corpus.
2. **Brute-force, doesn't scale.** Re-reads every document in full; no index.
   Useless across dozens of competitor reports.
3. **Unstructured output.** Freeform `.txt`; nothing typed or queryable.
4. **Wrong domain.** Financial buckets, not clinical-lifecycle intelligence.
5. **Ungrounded.** No faithfulness/quality measurement; hallucinations invisible.
6. **Static only.** Knows nothing beyond the uploaded PDFs.

## Salvage vs. discard

| Component | Verdict | Notes |
|---|---|---|
| PDF download helper (`requests` + UA header) | **Salvage** | Reuse; harden error handling. |
| `pdfplumber` text extraction | **Salvage, upgrade** | Keep, but improve table handling for clinical/financial tables. |
| Word-based chunker | **Reference only** | Concept reusable; RAG needs **token-based** chunking with overlap — rewrite. |
| `tkinter` GUI | **Discard** | New system is CLI / library-first. |
| PyInstaller packaging | **Discard** | Not a desktop-app deliverable. |
| Financial-bucket prompts + 6 categories | **Discard** | Replaced by the domain schema + extraction. |
| Freeform `.txt` output | **Discard** | Replaced by structured records + grounded, cited answers. |
