"""CLI: run extraction over one corpus report and persist the result.

    python -m src.extraction.run --report takeda

Loads a markdown report, chunks it, runs **paced** per-chunk Gemini extraction
(printing per-chunk progress), and writes the result to a gitignored artifact
under ``data/eval/extractions/``. That artifact is the fixed input the Phase-2
eval harness scores against — produced once so the harness never re-burns
free-tier quota (see ``docs/LEARNINGS.md``).

Requires the environment to be loaded first::

    set -a; source .env; set +a      # GEMINI_API_KEY + GEMINI_MODEL

Report metadata (company, doc_type, snapshot date) is not reliably inferable from
the file, so the two known corpus reports are registered below; ``--path`` etc.
allow an arbitrary file.
"""

import argparse
import hashlib
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from src.ingestion import ChunkConfig, chunk_document, load_report
from src.schema.enums import DocType

from .extractor import EXTRACTION_SYSTEM_PROMPT, ExtractionResult, extract_document
from .persistence import count_by_type, save_extraction

# Snapshot date the source states ("as of May 13, 2026" on Takeda; Novartis Q1
# covers the period ended 2026-03-31). Caller-supplied because the source states
# it once globally, not per row (see docs/LEARNINGS.md 2026-06-07).
_REPORTS: dict[str, dict[str, str]] = {
    "takeda": {
        "path": "data/reports/qr2025_q4_Pipeline_table_en.md",
        "source_company": "Takeda",
        "doc_type": "pipeline_table",
        "as_of_date": "2026-05-13",
        "publication_date": "2026-05-13",
        "period_covered": "FY2025 Q4",
    },
    "novartis": {
        "path": "data/reports/q1-2026-interim-financial-report-en.md",
        "source_company": "Novartis",
        "doc_type": "financial_report",
        "as_of_date": "2026-03-31",
        "publication_date": "2026-03-31",
        "period_covered": "Q1 2026",
    },
}

_DEFAULT_DELAY_SECONDS = 4.5
_DEFAULT_OUT_DIR = Path("data/eval/extractions")


def _git_sha() -> str | None:
    """Short HEAD sha for run provenance, or None outside a git checkout."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return sha or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _running_total_reporter():
    """A stateful ``on_chunk`` callback that prints per-chunk + cumulative counts."""
    totals = {k: 0 for k in ("assets", "programs", "trials", "regulatory_events", "market_metrics")}

    def report(index: int, total: int, chunk_result: ExtractionResult) -> None:
        added = count_by_type(chunk_result)
        for key, value in added.items():
            totals[key] += value
        delta = " ".join(
            f"+{added[k]}{abbr}"
            for k, abbr in (
                ("assets", "a"),
                ("programs", "p"),
                ("trials", "t"),
                ("regulatory_events", "r"),
                ("market_metrics", "m"),
            )
            if added[k]
        )
        cum = f"Σ a{totals['assets']} p{totals['programs']} t{totals['trials']} " \
              f"r{totals['regulatory_events']} m{totals['market_metrics']}"
        print(f"  [{index + 1:>3}/{total}] {delta or '(none)':<28} {cum}", flush=True)

    return report


def _resolve_report(args: argparse.Namespace) -> dict[str, str]:
    """Merge a named-report preset with any explicit overrides from the CLI."""
    spec: dict[str, str] = dict(_REPORTS[args.report]) if args.report else {}
    # spec key -> argparse dest holding an explicit override.
    for spec_key, arg_dest in (
        ("path", "path"),
        ("source_company", "company"),
        ("doc_type", "doc_type"),
        ("as_of_date", "as_of_date"),
    ):
        override = getattr(args, arg_dest, None)
        if override:
            spec[spec_key] = override
    missing = [k for k in ("path", "source_company", "doc_type", "as_of_date") if not spec.get(k)]
    if missing:
        raise SystemExit(
            f"Missing required report metadata: {', '.join(missing)}. "
            f"Use --report {{{','.join(_REPORTS)}}} or pass them explicitly."
        )
    return spec


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", choices=sorted(_REPORTS), help="Named corpus report preset.")
    parser.add_argument("--path", help="Markdown path (overrides preset).")
    parser.add_argument("--company", dest="company", help="source_company (overrides preset).")
    parser.add_argument("--doc-type", dest="doc_type", help="Document doc_type (overrides preset).")
    parser.add_argument("--as-of-date", dest="as_of_date", help="Snapshot date (overrides preset).")
    parser.add_argument("--chunk-size", type=int, default=ChunkConfig.chunk_size, help="Chunk size (chars).")
    parser.add_argument("--overlap", type=int, default=ChunkConfig.overlap, help="Chunk overlap (chars).")
    parser.add_argument("--delay", type=float, default=_DEFAULT_DELAY_SECONDS, help="Inter-call pacing (s).")
    parser.add_argument("--limit", type=int, default=None, help="Extract only the first N chunks (smoke test).")
    parser.add_argument("--out-dir", type=Path, default=_DEFAULT_OUT_DIR, help="Output directory.")
    args = parser.parse_args()

    spec = _resolve_report(args)
    config = ChunkConfig(chunk_size=args.chunk_size, overlap=args.overlap)

    loaded = load_report(
        spec["path"],
        source_company=spec["source_company"],
        doc_type=spec["doc_type"],  # type: ignore[arg-type]  # validated by Document(doc_type: DocType)
        publication_date=spec.get("publication_date"),
        period_covered=spec.get("period_covered"),
    )
    chunks = chunk_document(loaded, config)
    if args.limit is not None:
        chunks = chunks[: args.limit]

    model = os.environ.get("GEMINI_MODEL", "(GEMINI_MODEL unset)")
    out_path = args.out_dir / f"{loaded.document.id}.extraction.json"

    print(f"Report   : {loaded.document.id}  ({spec['source_company']}, {spec['doc_type']})")
    print(f"Chunks   : {len(chunks)}  (size={config.chunk_size}, overlap={config.overlap}"
          f"{', LIMITED to ' + str(args.limit) if args.limit is not None else ''})")
    print(f"Model    : {model}   pacing={args.delay}s/call   as_of={spec['as_of_date']}")
    print(f"Output   : {out_path}")
    print("Extracting (per-chunk):", flush=True)

    result = extract_document(
        chunks,
        source_company=spec["source_company"],
        as_of_date=spec["as_of_date"],
        delay_seconds=args.delay,
        on_chunk=_running_total_reporter(),
    )

    meta = {
        "document_id": loaded.document.id,
        "source_company": spec["source_company"],
        "doc_type": spec["doc_type"],
        "as_of_date": spec["as_of_date"],
        "chunk_count": len(chunks),
        "chunk_config": {"chunk_size": config.chunk_size, "overlap": config.overlap},
        "limit": args.limit,
        "extraction_model": model,
        "prompt_sha256": hashlib.sha256(EXTRACTION_SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12],
        "delay_seconds": args.delay,
        "git_sha": _git_sha(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    saved = save_extraction(out_path, result, meta=meta)

    counts = count_by_type(result)
    print("\nDone. Counts by type:")
    for key, value in counts.items():
        print(f"  {key:<18} {value}")
    print(f"Total facts (excl. assets): "
          f"{sum(v for k, v in counts.items() if k != 'assets')}")
    print(f"Saved    : {saved}")


if __name__ == "__main__":
    main()
