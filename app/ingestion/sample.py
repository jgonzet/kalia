"""The sample company the app loads at startup, so a person who just started it has something to ask about."""

import logging
from dataclasses import dataclass, replace
from datetime import date

from app.config import ROOT, CommitmentsSource, Settings
from app.extraction import CommitmentExtractor
from app.extraction.saved import SavedExtractionInfo, SavedExtractionReader, find_saved_extraction
from app.ingestion.dataset import DatasetSource, load_dataset
from app.storage import Store

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SampleInfo:
    """What the chat page tells the person about the data: whose it is and where its commitments came from."""

    company: str
    commitments_source: CommitmentsSource
    failed_documents: int = 0  # documents whose extraction failed in this start; 0 when nothing was loaded now
    saved_extraction: SavedExtractionInfo | None = None  # which saved extraction the commitments come from; None with a live extraction


def prepare_sample(settings: Settings, store: Store, extractor: CommitmentExtractor | None) -> tuple[Settings, SampleInfo]:
    """Load `data/<SAMPLE_COMPANY>/` into the store; return the settings with its date as the default "today", and its info.

    It loads when the store has no catalog or lacks a document of the sample (an interrupted load is completed on the
    next start, since loading again replaces what was there); a store that holds the whole sample is left as it is.
    The commitments come from `COMMITMENTS_SOURCE`: the company's saved extraction (its file is read and checked on every
    start, even when nothing is loaded), or `extractor` (None, like the fake backend, leaves the documents without
    commitments). The date of the sample's `company.json` is used only when `REFERENCE_DATE` is not set. The info
    reports the current `COMMITMENTS_SOURCE`, which is not what a store loaded by an earlier run was filled with, and
    how many extractions failed in this start.
    """
    company_dir = ROOT / "data" / str(settings.sample_company)
    if not (company_dir / "company.json").is_file():
        raise ValueError(f"SAMPLE_COMPANY={settings.sample_company!r}: no dataset at {company_dir}")
    failed = 0
    dataset = DatasetSource(company_dir)
    company = dataset.company
    source_docs = list(dataset.documents())
    saved = None
    if settings.commitments_source == "saved":
        saved = SavedExtractionReader(find_saved_extraction(company_dir), company["id"], settings.owner_id)
    if store.load_catalog() is None or any(store.get_document(d.id) is None for d in source_docs):
        if saved is not None:
            source: CommitmentExtractor | None = saved
        else:
            source = extractor
            if source is None:
                logger.warning("COMMITMENTS_SOURCE=extraction but this LLM backend extracts nothing: no commitments loaded")
            else:
                llm = settings.llm_for("extractor")
                if llm.backend not in ("ollama", "fake"):
                    logger.warning(
                        "COMMITMENTS_SOURCE=extraction: %d documents will be sent to %s (%s), one call each. If that is a paid "
                        "API it charges for them, and this repeats on every start that finds no stored sample",
                        len(source_docs),
                        llm.model,
                        llm.backend,
                    )
        result = load_dataset(company_dir, store, source)
        failed = len(result.failed)
        logger.info(
            "sample %s loaded: %d documents, commitments from %s, %d extractions failed",
            settings.sample_company,
            result.documents,
            settings.commitments_source,
            failed,
        )
    if settings.reference_date is None:
        settings = replace(settings, reference_date=date.fromisoformat(company["reference_date"]))
    return settings, SampleInfo(company["name"], settings.commitments_source, failed, saved.info if saved else None)
