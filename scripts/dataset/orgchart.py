"""Generate an org chart table from a company's people.jsonl."""

import json
import sys
from pathlib import Path


def build_table(people_path: Path, user_id: str) -> str:
    """Return a Markdown table of the people and their reporting lines, marking the user."""
    people = [json.loads(line) for line in people_path.read_text().splitlines() if line]
    names = {p["id"]: p["name"] for p in people}
    rows = ["| id | Name | Role | Area | Level | Reports to |", "|---|---|---|---|---|---|"]
    for p in people:
        name = f"**{p['name']} (user)**" if p["id"] == user_id else p["name"]
        boss = names[p["reports_to"]] if p["reports_to"] else "—"
        rows.append(f"| {p['id']} | {name} | {p['role']} | {p['area']} | {p['level']} | {boss} |")
    return "\n".join(rows)


def main() -> None:
    """Write ORGCHART.md for the company folder given as argument (default: lamanija)."""
    company_dir = Path("data") / (sys.argv[1] if len(sys.argv) > 1 else "lamanija")
    company = json.loads((company_dir / "company.json").read_text())
    table = build_table(company_dir / "people.jsonl", company["user_id"])
    out = company_dir / "ORGCHART.md"
    out.write_text(
        f"# {company['name']} — org chart\n\n"
        "Generated from `people.jsonl` by `scripts/dataset/orgchart.py`; do not edit by hand.\n\n"
        f"{table}\n"
    )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
