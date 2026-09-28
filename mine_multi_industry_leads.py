"""Build PUBLIC Boston opportunity previews from official source records.

Permits are activity signals, not open bids. Contacts and paid files are never
generated or included in this feed. IT and professional-service records enter
only through reviewed_opportunities.csv with an official source URL.
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

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
STATE = ROOT / "state" / "first_seen.json"
REVIEWED = ROOT / "reviewed_opportunities.csv"
API = "https://data.boston.gov/api/3/action/datastore_search"
RESOURCE = "6ddcd912-32a0-43df-9908-63574f8c7e77"
SECTORS = {"Construction", "IT Services", "Professional Services", "Renewable Energy"}
RENEWABLE = re.compile(r"\b(solar|photovoltaic|pv array|battery storage|energy storage|heat pump|geothermal|wind turbine)\b", re.I)
FIELDS = ("id", "sector", "name", "location", "agency", "value", "description", "record_date", "source_url", "source_type", "first_seen_at", "date_checked", "status")


def first(record, *names):
    return next((str(record[n]).strip() for n in names if record.get(n) is not None and str(record[n]).strip()), "")


def stable_id(kind, source_id):
    return "BOS-" + hashlib.sha256(f"{kind}:{source_id}".encode()).hexdigest()[:16].upper()


def transform(record):
    source_id = first(record, "_id")
    address = first(record, "address", "full_address")
    if not source_id or not address:
        return None
    description = first(record, "workdesc", "description")
    source_url = API + "?" + urlencode({"resource_id": RESOURCE, "filters": json.dumps({"_id": record["_id"]})})
    return {
        "id": stable_id("permit", f"{RESOURCE}:{source_id}"),
        "sector": "Renewable Energy" if RENEWABLE.search(description) else "Construction",
        "name": "Boston permit activity — " + address,
        "location": address + ", Boston, MA", "agency": "Boston Inspectional Services",
        "value": first(record, "declared_valuation"),
        "description": description[:500],
        "record_date": first(record, "issued_date", "issueddate", "apply_date"),
        "source_url": source_url, "source_type": "building_permit", "status": "public_record_preview",
    }


def fetch_permits(opener=urlopen, limit=100):
    records = []
    for offset in range(0, limit, 100):
        url = API + "?" + urlencode({"resource_id": RESOURCE, "limit": min(100, limit - offset), "offset": offset, "sort": "_id desc"})
        with opener(url, timeout=30) as response:
            payload = json.load(response)
        if payload.get("success") is not True or not isinstance(payload.get("result", {}).get("records"), list):
            raise RuntimeError("Invalid Boston permit response; existing feed preserved")
        records.extend(payload["result"]["records"])
    if not records:
        raise RuntimeError("No Boston permits returned; existing feed preserved")
    return records


def reviewed_previews(path=REVIEWED):
    if not path.exists():
        return []
    required = {"source_id", "source_url", "sector", "name", "location", "agency", "description", "record_date", "value"}
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("reviewed_opportunities.csv is missing required columns")
        result = []
        for line, row in enumerate(reader, 2):
            if not any((v or "").strip() for v in row.values() if isinstance(v, str)):
                continue
            source_id, source_url, sector = (first(row, key) for key in ("source_id", "source_url", "sector"))
            host = urlparse(source_url)
            if (sector not in SECTORS or not source_id or not first(row, "name") or
                not re.search(r"\bBoston\b", first(row, "location"), re.I) or
                host.scheme != "https" or host.hostname not in {"boston.gov", "www.boston.gov", "data.boston.gov", "procurement.boston.gov"}):
                raise ValueError(f"Invalid reviewed Boston source at line {line}")
            result.append({
                "id": stable_id("reviewed", source_id), "sector": sector,
                "name": first(row, "name"), "location": first(row, "location"),
                "agency": first(row, "agency"), "value": first(row, "value"),
                "description": first(row, "description")[:500], "record_date": first(row, "record_date"),
                "source_url": source_url, "source_type": "reviewed_official_record", "status": "public_record_preview",
            })
        return result


def build(records, reviewed=(), previous=None, now=None):
    now = now or datetime.now(timezone.utc)
    state = dict(previous or {})
    output = {}
    for raw in records:
        preview = transform(raw)
        if preview:
            output[preview["id"]] = preview
    for preview in reviewed:
        output[preview["id"]] = preview
    if not output:
        raise RuntimeError("No valid records; existing feed preserved")
    for preview in output.values():
        lead_id = preview["id"]
        state.setdefault(lead_id, now.isoformat(timespec="seconds"))
        preview["first_seen_at"] = state[lead_id]
        preview["date_checked"] = now.date().isoformat()
    return sorted(output.values(), key=lambda p: (p["sector"], p["id"])), state


def main():
    limit = int(os.getenv("BOSTON_PERMIT_LIMIT", "100"))
    if not 1 <= limit <= 1000:
        raise ValueError("BOSTON_PERMIT_LIMIT must be 1–1000")
    previous = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    if not isinstance(previous, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in previous.items()):
        raise ValueError("Invalid first-seen state; refusing to reset dates")
    previews, state = build(fetch_permits(limit=limit), reviewed_previews(), previous)
    PUBLIC.mkdir(exist_ok=True)
    STATE.parent.mkdir(exist_ok=True)
    json_temp, csv_temp, state_temp = (PUBLIC / "multi_industry_leads.json.tmp", PUBLIC / "leads.csv.tmp", STATE.with_suffix(".json.tmp"))
    json_temp.write_text(json.dumps(previews, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    state_temp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with csv_temp.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(previews)
    os.replace(json_temp, PUBLIC / "multi_industry_leads.json")
    os.replace(csv_temp, PUBLIC / "leads.csv")
    os.replace(state_temp, STATE)
    print("Public preview counts:", {s: sum(p["sector"] == s for p in previews) for s in sorted(SECTORS)})
    print("No verified contact details or paid files were generated; these records are not for sale.")


if __name__ == "__main__":
    main()
