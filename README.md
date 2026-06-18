# pharma-ci-engine

A pharmaceutical competitive-intelligence engine: it extracts structured facts from dense industry documents, then runs a research agent that answers competitive questions with cited output, escalating to live regulatory sources when the documents fall short. An offline evaluation harness measures the whole pipeline.

The use case here is pharma competitive intelligence, but the architecture is general: grounded answers from a private corpus, augmented with live external sources when the corpus falls short.

The distinguishing feature of the project is not the agent itself, but the **measurement system** around it. The eval harness is built to answer a question most agent demos can't: when the system gets an answer wrong, is the *agent* failing, or is the *measurement* failing? Telling those two apart is the whole discipline, and the project's sharpest result came from getting it right.

## What the evaluation found

The agent's first evaluation scored **0.00** on claim recall. It looked broken.

It wasn't. The scorer was. Once the measurement was fixed to distinguish what the agent actually got right from what the scorer could actually detect, recall went from **0.11 to 0.56 without a single line of agent code changing**. The improvement was in *retrieval* and in the *scorer*, not the agent. A working system had been made to look broken by a flawed way of measuring it.

Most of the engineering effort went into building a measurement trustworthy enough to earn that conclusion, because a number you can't trust is worse than no number at all. The full arc, and the four distinct scorer fixes behind that 0.11→0.56 jump, is in the [evaluation case study](docs/EVALUATION_CASE_STUDY.md).

## Why this exists

Competitive-intelligence analysts in pharma spend hours pulling the same facts out of earnings reports, pipeline tables, and regulatory filings: what phase is this drug in, did that trial read out, when was this approval granted. The work is repetitive, high-volume, and unforgiving of errors.

This project explores a narrow version of that workflow: can a structured extraction pipeline plus a retrieval-grounded research agent answer real competitive questions with cited, verifiable output, while staying measurable and debuggable. That last part is what makes it more than a demo.

## What the agent does

The agent follows a retrieve → assess → answer loop, escalating to live regulatory tools only when the corpus cannot support an answer. Two real runs show both halves.

A question the **corpus can answer** — the development stage of a drug in the pipeline — is answered directly, every claim cited back to the source document and line range:

```text
$ python -m src.agent.run "What is the development stage of fazirsiran?"
TERMINAL STATE: answered
  [1] subject:   fazirsiran
      attribute: development stage for alpha-1 antitrypsin-deficiency associated liver disease in the U.S.
      value:     P-III
      cite:      (qr2025_q4_Pipeline_table_en, (202, 301))
```

A question the **corpus cannot answer** — the FDA approval status of a drug that isn't in the documents at all — is recognized as a gap, escalated to a live regulatory source (openFDA), and answered with the external record cited by its application number:

```text
$ python -m src.agent.run "Is pitolisant approved by the FDA?"
TERMINAL STATE: answered
  [1] subject:   pitolisant
      attribute: FDA approval status
      value:     approved
      cite:      (openfda:NDA211150, None)
```

The two citations show the agent's two grounding modes. A corpus claim cites a document and the exact line range it came from; a live-tool claim cites the external record's identity — here an FDA application number — with no line range, because an API record isn't a span of text. The agent never guesses past its evidence: when the corpus is silent and no tool can fill the gap, it says so. That "I have grounds to answer this" versus "I don't" decision is enforced in code, not left to the model — which is what makes the behavior measurable.

## How it's built

```text
markdown ─▶ ingestion ─▶ extraction ─▶ ┌─ retrieval (FAISS + BM25, hybrid)
            (load,        (LLM →        └─ evals (offline scoring)
             chunk)        schema)            │
                                              ▼
                                  agent (plan · retrieve · assess · cite,
                                         escalating to live tools on a gap)
                                              ▼
                                grounded, cited competitive answers
```

- **`src/ingestion/`** — loads pharma markdown, section-aware character chunking with overlap.
- **`src/schema/`** — a Pydantic v2 domain model: documents, drugs, development programs, trials, regulatory events, market metrics, and provenance.
- **`src/extraction/`** — LLM structured-output extraction into that schema; citations are assigned by code, not by the model.
- **`src/rag/`** — embeddings, a FAISS dense index, and hybrid (dense + BM25) retrieval fused on source spans.
- **`src/agent/`** — the research agent: a code-owned loop (plan, retrieve, assess, synthesize) that makes three narrow judgment calls and leaves control flow, stopping, escalation, and citation resolution to code.
- **`src/tools/`** — live API clients for ClinicalTrials.gov and openFDA, used only when the corpus can't answer.
- **`src/evals/`** — the deterministic scorer and hand-authored golden datasets that measure extraction, retrieval, and the agent.

A defining design choice runs through all of it: the language model is given only the calls that need judgment, and everything testable — the loop, the stopping rule, the decision to escalate, the link from each claim to its evidence — is kept in code. The reasoning behind this and the other major decisions is in [engineering decisions](docs/ENGINEERING_DECISIONS.md); the full system design is in [architecture](docs/ARCHITECTURE.md).

## How do I know it works?

The honest answer has two parts.

The **measurement is committed and inspectable.** The scorer, the golden datasets, the recorded API fixtures, and the deterministic value-matching layer are all in the repo, and fully covered by the test suite. Anyone can read exactly how every number was produced: no LLM grading itself, no hidden threshold, no tunable knob doing the work.

The **agent's results are documented, not reproducible from a clean clone** — a deliberate consequence of the project's constraints, not an omission. Running the agent end to end needs the private corpus and a live model key, so the headline numbers live in the case study as findings rather than behind a one-command rerun. The question the project actually cares about — *is the measurement trustworthy* — is answerable by reading the committed scorer and goldens, without re-running the model.

## Install and run

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                                  # 144 tests
```

Running the extraction, retrieval, or agent commands additionally requires a source corpus under `data/` (gitignored) and a Gemini API key in `.env`:

```bash
cp .env.example .env                    # add your key locally; never commit .env
set -a; source .env; set +a             # load .env into the shell

python -m src.extraction.run --report takeda    # extract one report into the schema
python -m src.evals.run                          # score extraction against the golden set
python -m src.evals.retrieval_run                # score retrieval
python -m src.agent.run "Is pitolisant approved by the FDA?"   # ask the agent
```

The first agent or retrieval run downloads a pinned embedding model (~67 MB) once, then caches it. `data/` holds the corpus, the extraction artifacts, and the FAISS index; a fresh clone has none of these, so these commands need the corpus and a key. The test suite needs neither.

## Documentation

- **[Evaluation case study](docs/EVALUATION_CASE_STUDY.md)** — how the system is measured across four escalating layers, and why the headline numbers are what they are. The best single read.
- **[Engineering decisions](docs/ENGINEERING_DECISIONS.md)** — the principles behind the major design choices: build the measurement first, refuse knobs you can't justify, keep control where it can be tested, localize before you solve.
- **[Architecture](docs/ARCHITECTURE.md)** — the full system design: modules, data flow, and the domain schema.
- `docs/` also holds the internal design and working records (planning docs, decision logs, the running engineering-learnings log) for anyone who wants the development detail.

## Tech stack

Python 3.11+ · Gemini (LLM + structured extraction) · FAISS · `rank-bm25` · Pydantic v2 · httpx · pytest. Library- and CLI-first; no GUI.

## Status

Complete: a structured extraction pipeline, hybrid retrieval, a live-tool research agent, and an offline evaluation harness covering all three. Single-provider (Gemini) and corpus-scoped by design. PDF ingestion and a typed tool-failure layer are documented as deliberate deferrals rather than gaps.
