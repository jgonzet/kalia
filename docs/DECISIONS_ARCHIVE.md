# Decisions archive

Superseded decisions, moved here verbatim from [DECISIONS.md](DECISIONS.md).

## "Today" is `REFERENCE_DATE`, else the reference date stored with the loaded dataset, else the system date
Date: 2026-10-16
Chose: the loader saves the dataset's `reference_date` in a new table (`dataset_meta`); `Settings.resolve_today` picks `REFERENCE_DATE`, then that stored date, then the system date, and the chat does it on every question.
Rejected: the system date as the default (the deadlines of the dataset, September and October 2026, become overdue as days pass); the date in `compose.yaml` (a second copy of what `company.json` holds); a column in `catalog_meta` (a database created before would need a migration, and there are none); computing it once at startup (a server running past midnight keeps the old day).
Why: a database loaded before this has no stored date until the dataset is loaded again.
Source: issue #18, commits 8f0dc45 (storage, loader, `resolve_today`) and 94fc9e5 (read on every question).
Superseded 2026-10-17: "Today" is `REFERENCE_DATE`, else the system date; nothing is stored in the database.

