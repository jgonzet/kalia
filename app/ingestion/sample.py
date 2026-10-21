"""The sample company the app loads at startup, so a person who just started it has something to ask about."""

import logging
from dataclasses import dataclass, replace
from datetime import date

from app.config import ROOT, CommitmentsSource, Settings
from app.extraction import CommitmentExtractor
from app.extraction.expected import ExpectedCommitmentsReader
from app.ingestion.dataset import DatasetSource, load_dataset
from app.storage import Store

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SampleInfo:
    """What the chat page tells the person about the data: whose it is and where its commitments came from."""

    company: str
    commitments_source: CommitmentsSource


def prepare_sample(settings: Settings, store: Store, extractor: CommitmentExtractor | None) -> tuple[Settings, SampleInfo]:
    """Load `data/<SAMPLE_COMPANY>/` into an empty store; return the settings with its date as the default "today", and its info.

    A store that already has a catalog is left as it is. The commitments come from `COMMITMENTS_SOURCE`: the `expected`
    files, or `extractor` (None, like the fake backend, leaves the documents without commitments). The date of the
    sample's `company.json` is used only when `REFERENCE_DATE` is not set. The info reports the current
    `COMMITMENTS_SOURCE`, which is not what a store loaded by an earlier run was filled with.
    """
    company_dir = ROOT / "data" / str(settings.sample_company)
    if not (company_dir / "company.json").is_file():
        raise ValueError(f"SAMPLE_COMPANY={settings.sample_company!r}: no dataset at {company_dir}")
    if store.load_catalog() is None:
        if settings.commitments_source == "expected":
            source: CommitmentExtractor | None = ExpectedCommitmentsReader(company_dir, settings.owner_id)
        else:
            source = extractor
            if source is None:
                logger.warning("COMMITMENTS_SOURCE=extraction but this LLM backend extracts nothing: no commitments loaded")
        count = load_dataset(company_dir, store, source)
        logger.info("sample %s loaded: %d documents, commitments from %s", settings.sample_company, count, settings.commitments_source)
    company = DatasetSource(company_dir).company
    if settings.reference_date is None:
        settings = replace(settings, reference_date=date.fromisoformat(company["reference_date"]))
    return settings, SampleInfo(company["name"], settings.commitments_source)
