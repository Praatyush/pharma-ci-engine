"""Per-chunk extraction: ``Chunk`` -> grounded schema fact entities.

Calls the isolated ``gemini_client`` for structured output, then maps the
``source_ref``-free / id-free payloads onto the schema models — assigning
deterministic ids and attaching a ``SourceRef`` built from the chunk's
``line_range`` + a verbatim ``snippet`` (NOT ``section_path``, which is decorative
on this corpus — see LEARNINGS). This module does NOT import ``google.genai``.

By design (LEARNINGS): an asset spanning N chunks is extracted N times; cross-chunk
dedup / alias resolution is deferred to assembly (Phase 2+). Duplicate assets in
output are expected, not a bug.
"""

import re
from dataclasses import dataclass, field

from src.ingestion.chunker import Chunk
from src.schema import (
    Asset,
    MarketMetric,
    Program,
    RegulatoryEvent,
    SourceRef,
    Trial,
)

from .gemini_client import generate_structured
from .models import ChunkExtraction

EXTRACTION_SYSTEM_PROMPT = """\
You are a pharmaceutical competitive-intelligence extraction system. You are given \
ONE excerpt from a company report (markdown converted from a PDF: spacing/line \
breaks are irregular, and table cells may appear as `##` lines or be split across \
lines). Extract structured facts into the provided schema.

Rules:
- Extract ONLY facts explicitly supported by THIS excerpt. Do not infer, complete, \
or use outside knowledge. If a field is not stated, leave it null / omit it.
- Values may be split across adjacent lines by the PDF conversion; reassemble them \
when the meaning is unambiguous, but never invent content to complete a fragment.
- Capture every distinct asset (drug/molecule), development program, clinical \
trial, regulatory event, and market/financial metric the excerpt states.
- Reference each fact's asset by the asset name or development code exactly as \
written (`asset_ref` / `asset_refs` / `subject_ref`), so it can be linked downstream.
- For every extracted item, set `evidence` to a SHORT span copied VERBATIM from the \
excerpt that supports it. Copy exact characters; do not paraphrase.
- Closed-vocabulary fields (region, stage, phase, agency, action, status, metric, \
basis) must be one of the allowed values. If the excerpt's value does not clearly \
map to an allowed value, leave that field null — do NOT force it.
- Open-vocabulary fields are FREE TEXT; record them as written. Suggested values are \
only to steer normalization — NEVER coerce to them:
    therapeutic_area: oncology, immunology, neuroscience, gastroenterology, \
rare_disease, vaccines, cardiometabolic, ...
    therapeutic_area is the BROAD disease domain (e.g. oncology, immunology, \
neuroscience, gastroenterology, rare_disease, vaccines, cardiometabolic). \
indication is the SPECIFIC condition (e.g. 'Celiac disease', 'Hidradenitis \
suppurativa', 'Ulcerative Colitis'). Do NOT put a specific condition in \
therapeutic_area — map it to its broad domain instead.
    modality: small_molecule, mAb, ADC, bispecific, radioligand, gene_therapy, \
cell_therapy, siRNA/RNAi, peptide, plasma_derived, vaccine, ...
    primary_endpoint: PFS, OS, ORR, DFS, DOR, EFS, pCR, PASI, DLQI, HbA1c, EDSS, \
immunogenicity, ...
- Do NOT output document ids, line numbers, citations, an `id`, or a `source_ref` — \
the calling system adds those.
- If the excerpt has no extractable facts (glossary, table of contents, disclaimer, \
page header), return empty lists.
"""

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_MAX_SNIPPET_CHARS = 600


@dataclass
class ExtractionResult:
    """Schema fact entities (and assets) extracted from a document, in order."""

    assets: list[Asset] = field(default_factory=list)
    programs: list[Program] = field(default_factory=list)
    trials: list[Trial] = field(default_factory=list)
    regulatory_events: list[RegulatoryEvent] = field(default_factory=list)
    market_metrics: list[MarketMetric] = field(default_factory=list)

    def extend(self, other: "ExtractionResult") -> None:
        self.assets.extend(other.assets)
        self.programs.extend(other.programs)
        self.trials.extend(other.trials)
        self.regulatory_events.extend(other.regulatory_events)
        self.market_metrics.extend(other.market_metrics)


def _slug(name: str) -> str:
    return _SLUG_RE.sub("-", name.strip().lower()).strip("-") or "unknown"


def _snippet_for(evidence: str | None, chunk: Chunk) -> str:
    """Use the model's verbatim quote only if it really is in the chunk; else the chunk."""
    if evidence and evidence in chunk.text:
        return evidence
    return chunk.text[:_MAX_SNIPPET_CHARS]


def _source_ref(chunk: Chunk, evidence: str | None, as_of_date: str | None) -> SourceRef:
    return SourceRef(
        document_id=chunk.document_id,
        section=chunk.section_label,        # decorative only — not load-bearing
        line_range=chunk.line_range,        # load-bearing provenance
        snippet=_snippet_for(evidence, chunk),
        as_of_date=as_of_date,
    )


def _primary_identifier(asset) -> str | None:
    for candidate in (
        asset.generic_name,
        asset.development_codes[0] if asset.development_codes else None,
        asset.brand_names[0] if asset.brand_names else None,
        asset.aliases[0] if asset.aliases else None,
    ):
        if candidate and candidate.strip():
            return candidate
    return None


def _map_payload(
    payload: ChunkExtraction, chunk: Chunk, *, source_company: str, as_of_date: str
) -> ExtractionResult:
    """Map a chunk's extraction payload onto grounded schema objects."""
    result = ExtractionResult()

    for a in payload.assets:
        primary = _primary_identifier(a)
        if primary is None:
            continue  # an Asset needs at least one identifier (schema validator)
        result.assets.append(
            Asset(
                id=_slug(primary),
                generic_name=a.generic_name,
                development_codes=a.development_codes,
                brand_names=a.brand_names,
                aliases=a.aliases,
                company=a.company or source_company,
                originator_company=a.originator_company,
                target=a.target,
                mechanism_of_action=a.mechanism_of_action,
                modality=a.modality,
                route=a.route,
            )
        )

    base = f"{chunk.document_id}:{chunk.chunk_index}"

    for i, p in enumerate(payload.programs):
        result.programs.append(
            Program(
                id=f"{base}:program:{i}",
                asset_id=_slug(p.asset_ref),
                therapeutic_area=p.therapeutic_area,
                indication=p.indication,
                line_of_therapy=p.line_of_therapy,
                region=p.region,
                stage=p.stage,
                status_reason=p.status_reason,
                formulation=p.formulation,
                as_of_date=p.as_of_date or as_of_date,
                source_ref=_source_ref(chunk, p.evidence, as_of_date),
            )
        )

    for i, t in enumerate(payload.trials):
        result.trials.append(
            Trial(
                id=f"{base}:trial:{i}",
                trial_name=t.trial_name,
                nct_id=t.nct_id,
                asset_ids=[_slug(r) for r in t.asset_refs],
                indication=t.indication,
                phase=t.phase,
                comparator=t.comparator,
                primary_endpoint=t.primary_endpoint,
                met_primary_endpoint=t.met_primary_endpoint,
                statistical_significance=t.statistical_significance,
                endpoint_result=t.endpoint_result,
                readout_date=t.readout_date,
                region=t.region,
                source_ref=_source_ref(chunk, t.evidence, as_of_date),
            )
        )

    for r in payload.regulatory_events:
        result.regulatory_events.append(
            RegulatoryEvent(
                asset_id=_slug(r.asset_ref),
                agency=r.agency,
                region=r.region,
                action=r.action,
                status=r.status,
                date=r.date,
                indication=r.indication,
                source_ref=_source_ref(chunk, r.evidence, as_of_date),
            )
        )

    for m in payload.market_metrics:
        result.market_metrics.append(
            MarketMetric(
                subject=m.subject_ref,  # asset name or company, as written (union-as-string)
                metric=m.metric,
                value=m.value,
                unit=m.unit,
                currency=m.currency,
                basis=m.basis,
                period=m.period,
                geography=m.geography,
                source_ref=_source_ref(chunk, m.evidence, as_of_date),
            )
        )

    return result


def extract_chunk(
    chunk: Chunk, *, source_company: str, as_of_date: str
) -> ExtractionResult:
    """Extract one chunk via Gemini structured output, mapped to grounded schema objects."""
    payload = generate_structured(
        chunk.text,
        ChunkExtraction,
        system_instruction=EXTRACTION_SYSTEM_PROMPT,
        temperature=0.0,
    )
    return _map_payload(payload, chunk, source_company=source_company, as_of_date=as_of_date)


def extract_document(
    chunks: list[Chunk], *, source_company: str, as_of_date: str
) -> ExtractionResult:
    """Extract every chunk of a document and concatenate the results (no dedup)."""
    result = ExtractionResult()
    for chunk in chunks:
        result.extend(
            extract_chunk(chunk, source_company=source_company, as_of_date=as_of_date)
        )
    return result
