"""Build PUBLIC Boston opportunity previews from official source records.

Permits are activity signals, not open bids. Contacts and paid files are never
generated or included in this feed.

IT Services and Professional Services records enter only through
reviewed_opportunities.csv with an official Boston source URL.

Each source record receives a deterministic stable ID so repeated runs do not
create duplicate lead records.
"""

import csv
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen


# ---------------------------------------------------------------------------
# Paths and source configuration
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
STATE = ROOT / "state" / "first_seen.json"
REVIEWED = ROOT / "reviewed_opportunities.csv"

API = "https://data.boston.gov/api/3/action/datastore_search"
RESOURCE = "6ddcd912-32a0-43df-9908-63574f8c7e77"

DEFAULT_PERMIT_LIMIT = 1000
MAX_PERMIT_LIMIT = 5000
PAGE_SIZE = 100


# ---------------------------------------------------------------------------
# Lead categories
# ---------------------------------------------------------------------------

SECTORS = {
    "Construction",
    "IT Services",
    "Professional Services",
    "Renewable Energy",
}

RENEWABLE = re.compile(
    r"\b("
    r"solar|"
    r"photovoltaic|"
    r"pv array|"
    r"solar array|"
    r"solar panel|"
    r"battery storage|"
    r"battery energy storage|"
    r"energy storage|"
    r"energy efficiency|"
    r"energy retrofit|"
    r"heat pump|"
    r"geothermal|"
    r"wind turbine"
    r")\b",
    re.I,
)


# ---------------------------------------------------------------------------
# Public output schema
# ---------------------------------------------------------------------------

FIELDS = (
    "id",
    "sector",
    "name",
    "location",
    "agency",
    "value",
    "description",
    "record_date",
    "source_url",
    "source_type",
    "first_seen_at",
    "date_checked",
    "status",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def first(record, *names):
    """Return the first non-empty value from the requested fields."""

    return next(
        (
            str(record[name]).strip()
            for name in names
            if record.get(name) is not None
            and str(record[name]).strip()
        ),
        "",
    )


def stable_id(kind, source_id):
    """Create a deterministic SHLAE lead ID from the source identity."""

    digest = hashlib.sha256(
        f"{kind}:{source_id}".encode("utf-8")
    ).hexdigest()[:16].upper()

    return "BOS-" + digest


# ---------------------------------------------------------------------------
# Boston building permit transformation
# ---------------------------------------------------------------------------

def transform(record):
    """Convert one Boston permit record into one public preview."""

    source_id = first(record, "_id")
    address = first(record, "address", "full_address")

    # A record without a stable source ID or location cannot safely
    # become a lead preview.
    if not source_id or not address:
        return None

    description = first(
        record,
        "workdesc",
        "description",
    )

    source_url = API + "?" + urlencode(
        {
            "resource_id": RESOURCE,
            "filters": json.dumps(
                {"_id": record["_id"]}
            ),
        }
    )

    sector = (
        "Renewable Energy"
        if RENEWABLE.search(description)
        else "Construction"
    )

    return {
        "id": stable_id(
            "permit",
            f"{RESOURCE}:{source_id}",
        ),
        "sector": sector,
        "name": f"Boston permit activity — {address}",
        "location": f"{address}, Boston, MA",
        "agency": "Boston Inspectional Services",
        "value": first(
            record,
            "declared_valuation",
        ),
        "description": description[:500],
        "record_date": first(
            record,
            "issued_date",
            "issueddate",
            "apply_date",
        ),
        "source_url": source_url,
        "source_type": "building_permit",
        "status": "public_record_preview",
    }


# ---------------------------------------------------------------------------
# Boston permit retrieval
# ---------------------------------------------------------------------------

def fetch_permits(opener=urlopen, limit=DEFAULT_PERMIT_LIMIT):
    """Retrieve the newest Boston permit records in 100-record pages."""

    if not 1 <= limit <= MAX_PERMIT_LIMIT:
        raise ValueError(
            f"BOSTON_PERMIT_LIMIT must be 1–{MAX_PERMIT_LIMIT}"
        )

    records = []

    for offset in range(0, limit, PAGE_SIZE):

        page_limit = min(
            PAGE_SIZE,
            limit - offset,
        )

        url = API + "?" + urlencode(
            {
                "resource_id": RESOURCE,
                "limit": page_limit,
                "offset": offset,
                "sort": "_id desc",
            }
        )

        with opener(url, timeout=30) as response:
            payload = json.load(response)

        result = payload.get("result", {})
        page_records = result.get("records")

        if (
            payload.get("success") is not True
            or not isinstance(page_records, list)
        ):
            raise RuntimeError(
                "Invalid Boston permit response; "
                "existing feed preserved"
            )

        records.extend(page_records)

        # If Boston returns fewer records than requested,
        # we have reached the available end of the result set.
        if len(page_records) < page_limit:
            break

    if not records:
        raise RuntimeError(
            "No Boston permits returned; existing feed preserved"
        )

    return records


# ---------------------------------------------------------------------------
# Manually reviewed official opportunities
# ---------------------------------------------------------------------------

def reviewed_previews(path=REVIEWED):
    """Load reviewed Boston opportunities from the repository CSV."""

    if not path.exists():
        return []

    required = {
        "source_id",
        "source_url",
        "sector",
        "name",
        "location",
        "agency",
        "description",
        "record_date",
        "value",
    }

    with path.open(
        newline="",
        encoding="utf-8-sig",
    ) as stream:

        reader = csv.DictReader(stream)

        if (
            not reader.fieldnames
            or not required.issubset(reader.fieldnames)
        ):
            raise ValueError(
                "reviewed_opportunities.csv "
                "is missing required columns"
            )

        result = []

        for line, row in enumerate(reader, 2):

            if not any(
                (value or "").strip()
                for value in row.values()
                if isinstance(value, str)
            ):
                continue

            source_id = first(row, "source_id")
            source_url = first(row, "source_url")
            sector = first(row, "sector")

            host = urlparse(source_url)

            if (
                sector not in SECTORS
                or not source_id
                or not first(row, "name")
                or not re.search(
                    r"\bBoston\b",
                    first(row, "location"),
                    re.I,
                )
                or host.scheme != "https"
                or host.hostname
                not in {
                    "boston.gov",
                    "www.boston.gov",
                    "data.boston.gov",
                    "procurement.boston.gov",
                }
            ):
                raise ValueError(
                    f"Invalid reviewed Boston source at line {line}"
                )

            result.append(
                {
                    "id": stable_id(
                        "reviewed",
                        source_id,
                    ),
                    "sector": sector,
                    "name": first(row, "name"),
                    "location": first(row, "location"),
                    "agency": first(row, "agency"),
                    "value": first(row, "value"),
                    "description": first(
                        row,
                        "description",
                    )[:500],
                    "record_date": first(
                        row,
                        "record_date",
                    ),
                    "source_url": source_url,
                    "source_type": "reviewed_official_record",
                    "status": "public_record_preview",
                }
            )

    return result


# ---------------------------------------------------------------------------
# Build and deduplicate feed
# ---------------------------------------------------------------------------

def build(
    records,
    reviewed=(),
    previous=None,
    now=None,
):
    """Build one deduplicated public feed from all candidate records."""

    now = now or datetime.now(timezone.utc)

    state = dict(previous or {})

    # Dictionary is intentionally keyed by stable lead ID.
    # If the same source record appears more than once, only
    # one copy survives.
    output = {}

    for raw in records:

        preview = transform(raw)

        if preview:
            output[preview["id"]] = preview

    for preview in reviewed:
        output[preview["id"]] = preview

    if not output:
        raise RuntimeError(
            "No valid records; existing feed preserved"
        )

    for preview in output.values():

        lead_id = preview["id"]

        # Preserve the date on which SHLAE first encountered
        # this stable source record.
        state.setdefault(
            lead_id,
            now.isoformat(timespec="seconds"),
        )

        preview["first_seen_at"] = state[lead_id]
        preview["date_checked"] = now.date().isoformat()

    return (
        sorted(
            output.values(),
            key=lambda preview: (
                preview["sector"],
                preview["id"],
            ),
        ),
        state,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():

    limit = int(
        os.getenv(
            "BOSTON_PERMIT_LIMIT",
            str(DEFAULT_PERMIT_LIMIT),
        )
    )

    if not 1 <= limit <= MAX_PERMIT_LIMIT:
        raise ValueError(
            f"BOSTON_PERMIT_LIMIT must be 1–{MAX_PERMIT_LIMIT}"
        )

    if STATE.exists():
        previous = json.loads(
            STATE.read_text(encoding="utf-8")
        )
    else:
        previous = {}

    if (
        not isinstance(previous, dict)
        or any(
            not isinstance(key, str)
            or not isinstance(value, str)
            for key, value in previous.items()
        )
    ):
        raise ValueError(
            "Invalid first-seen state; refusing to reset dates"
        )

    raw_permits = fetch_permits(
        limit=limit
    )

    reviewed = reviewed_previews()

    previews, state = build(
        raw_permits,
        reviewed,
        previous,
    )

    PUBLIC.mkdir(
        parents=True,
        exist_ok=True,
    )

    STATE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_temp = (
        PUBLIC / "multi_industry_leads.json.tmp"
    )

    csv_temp = (
        PUBLIC / "leads.csv.tmp"
    )

    state_temp = STATE.with_suffix(
        ".json.tmp"
    )

    json_temp.write_text(
        json.dumps(
            previews,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    state_temp.write_text(
        json.dumps(
            state,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    with csv_temp.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as stream:

        writer = csv.DictWriter(
            stream,
            fieldnames=FIELDS,
        )

        writer.writeheader()
        writer.writerows(previews)

    # Replace the live files only after the complete build succeeds.
    os.replace(
        json_temp,
        PUBLIC / "multi_industry_leads.json",
    )

    os.replace(
        csv_temp,
        PUBLIC / "leads.csv",
    )

    os.replace(
        state_temp,
        STATE,
    )

    counts = {
        sector: sum(
            preview["sector"] == sector
            for preview in previews
        )
        for sector in sorted(SECTORS)
    }

    print(
        f"Boston permit records examined: "
        f"{len(raw_permits)}"
    )

    print(
        f"Unique public previews generated: "
        f"{len(previews)}"
    )

    print(
        "Public preview counts:",
        counts,
    )

    print(
        "No verified contact details or paid files were generated; "
        "these records are not for sale."
    )


if __name__ == "__main__":
    main()
