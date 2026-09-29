"""Daily Boston activity feed: 30-day source-date window and safe previews.

Full records are ephemeral unless encrypted with SHLAE_PRIVATE_FEED_KEY.
Never commit plaintext contact or project identity data to this repository.
"""
import base64
import csv
import hashlib
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from mine_multi_industry_leads import RESOURCE, RENEWABLE, first, stable_id

ROOT = Path(__file__).resolve().parent
API = "https://data.boston.gov/api/3/action/datastore_search_sql"
DATASET = "https://data.boston.gov/dataset/approved-building-permits"
ZONE = ZoneInfo("America/New_York")
PUBLIC_FIELDS = (
    "id", "sector", "name", "location", "agency", "value", "description",
    "record_date", "source_url", "source_type", "first_seen_at", "date_checked",
    "status", "expires_on", "contact_status", "purchase_ready",
)


def source_date(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return None


def current(record, today):
    issued = source_date(first(record, "issued_date", "issueddate", "record_date"))
    return issued is not None and today - timedelta(days=30) < issued <= today


def fetch_recent(today, opener=urlopen, page_size=1000, max_records=50000):
    """Sort on source date, not database ID; reject truncated result sets."""
    cutoff = today - timedelta(days=30)
    upper = today + timedelta(days=1)
    rows = []
    for offset in range(0, max_records + 1, page_size):
        sql = (
            f'SELECT * FROM "{RESOURCE}" '
            f"WHERE issued_date > '{cutoff.isoformat()} 23:59:59.999999' "
            f"AND issued_date < '{upper.isoformat()}' "
            f"ORDER BY issued_date DESC, _id DESC LIMIT {page_size} OFFSET {offset}"
        )
        with opener(API + "?" + urlencode({"sql": sql}), timeout=60) as response:
            payload = json.load(response)
        page = payload.get("result", {}).get("records")
        if payload.get("success") is not True or not isinstance(page, list):
            raise RuntimeError("Invalid Boston source response; feed not replaced")
        if offset >= max_records and page:
            raise RuntimeError("Record limit exceeded; refusing an incomplete feed")
        rows.extend(page)
        if len(page) < page_size:
            return rows
    raise RuntimeError("Incomplete source result")


def full_record(raw, today, previous):
    address = first(raw, "address", "full_address")
    source_id = first(raw, "_id")
    if not address or not source_id or not current(raw, today):
        return None
    # Closed permits are historical signals, not current outreach inventory.
    permit_status = first(raw, "status")
    if permit_status.casefold() in {"closed", "expired", "revoked", "cancelled", "canceled", "void"}:
        return None
    lead_id = stable_id("permit", f"{RESOURCE}:{source_id}")
    details = " ".join(filter(None, (
        first(raw, "workdesc", "description"), first(raw, "comments"),
    )))
    sector = "Renewable Energy" if RENEWABLE.search(details) else "Construction"
    issued = first(raw, "issued_date", "issueddate")
    applicant = first(raw, "applicant")
    return {
        "id": lead_id, "sector": sector,
        "business_name": "", "contact_name": "",
        "applicant_name": applicant, "email": "", "phone": "", "website": "",
        "street_address": address, "city": first(raw, "city") or "Boston",
        "state": first(raw, "state") or "MA", "zip": first(raw, "zip"),
        "description": details, "value": first(raw, "declared_valuation"),
        "permit_number": first(raw, "permitnumber"),
        "permit_type": first(raw, "permittypedescr"),
        "permit_status": permit_status, "record_date": issued,
        "expiration_date": first(raw, "expiration_date"),
        "occupancy_type": first(raw, "occupancytype"), "sq_feet": first(raw, "sq_feet"),
        "agency": "Boston Inspectional Services",
        "source_url": "https://data.boston.gov/api/3/action/datastore_search?" + urlencode({
            "resource_id": RESOURCE, "filters": json.dumps({"_id": raw["_id"]}),
        }),
        "contact_status": "source_applicant_only" if applicant else "contact_missing",
        "contact_checked_at": "", "contact_source_url": "",
        "first_seen_at": previous.get(lead_id, today.isoformat()),
        "date_checked": today.isoformat(),
        "expires_on": (source_date(issued) + timedelta(days=30)).isoformat(),
        "purchase_ready": False,
    }


def preview(full):
    """Allowlist with generic text: free-text comments can contain identities."""
    return {
        "id": full["id"], "sector": full["sector"],
        "name": full["sector"] + " permit activity",
        "location": "Boston, MA", "agency": full["agency"],
        "value": full["value"],
        "description": "Recently issued " + full["sector"].lower() + " permit. Full project and contact details are withheld.",
        "record_date": full["record_date"], "source_url": DATASET,
        "source_type": "building_permit", "first_seen_at": full["first_seen_at"],
        "date_checked": full["date_checked"], "status": "public_record_preview",
        "expires_on": full["expires_on"], "contact_status": full["contact_status"],
        "purchase_ready": full["purchase_ready"],
    }


def enrich_contact(item, contacts, today):
    """Accept researched contacts keyed by stable ID, with dated evidence."""
    contact = contacts.get(item["id"])
    if not contact:
        return
    checked = source_date(contact.get("checked_at"))
    source = str(contact.get("source_url", ""))
    if not checked or not today - timedelta(days=30) < checked <= today or not source.startswith("https://"):
        return
    for field in ("business_name", "contact_name", "email", "phone", "website"):
        item[field] = str(contact.get(field, "")).strip()
    item["contact_checked_at"] = checked.isoformat()
    item["contact_source_url"] = source
    item["purchase_ready"] = bool(item["business_name"] and (item["email"] or item["phone"]))
    item["contact_status"] = "reviewed_business_contact" if item["purchase_ready"] else "incomplete_business_contact"


def build(records, today, previous=None, contacts=None):
    unique = {}
    for raw in records:
        item = full_record(raw, today, previous or {})
        if item:
            enrich_contact(item, contacts or {}, today)
            unique[item["id"]] = item
    full = sorted(unique.values(), key=lambda item: (item["record_date"], item["id"]), reverse=True)
    public = [preview(item) for item in full]
    # Prune state too: old records must not be carried forward into inventory.
    state = {item["id"]: item["first_seen_at"] for item in full}
    return public, full, state


def write_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def encrypt_full(records, key):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        raw_key = base64.b64decode(key, validate=True)
    except Exception as error:
        raise ValueError("Private feed key must be base64") from error
    if len(raw_key) != 32:
        raise ValueError("Private feed key must decode to 32 bytes")
    nonce = os.urandom(12)
    ciphertext = AESGCM(raw_key).encrypt(
        nonce, json.dumps(records, ensure_ascii=False).encode("utf-8"),
        b"shlae-private-feed-v1",
    )
    return json.dumps({
        "version": 1, "algorithm": "AES-256-GCM",
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
    }) + "\n"


def main():
    today = datetime.now(ZONE).date()
    state_path = ROOT / "state" / "first_seen.json"
    previous = json.loads(state_path.read_text()) if state_path.exists() else {}
    if not isinstance(previous, dict):
        raise ValueError("Invalid first-seen state")
    records = fetch_recent(today)
    contacts = json.loads(os.environ.get("SHLAE_REVIEWED_CONTACTS_JSON") or "{}")
    if not isinstance(contacts, dict):
        raise ValueError("Reviewed contacts must be keyed by lead ID")
    public, full, state = build(records, today, previous, contacts)
    key = os.environ.get("SHLAE_PRIVATE_FEED_KEY", "")
    encrypted = encrypt_full(full, key) if key else None
    folder = ROOT / "public"
    folder.mkdir(exist_ok=True)
    # An empty successful result replaces old inventory; a source failure does not.
    write_atomic(folder / "multi_industry_leads.json", json.dumps(public, indent=2) + "\n")
    temporary = folder / "leads.csv.tmp"
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=PUBLIC_FIELDS)
        writer.writeheader()
        writer.writerows(public)
    os.replace(temporary, folder / "leads.csv")
    write_atomic(state_path, json.dumps(state, indent=2) + "\n")
    if encrypted is not None:
        write_atomic(folder / "private_leads.enc.json", encrypted)
    elif (folder / "private_leads.enc.json").exists():
        (folder / "private_leads.enc.json").unlink()
    write_atomic(folder / "feed_status.json", json.dumps({
        "updated_at": datetime.now(ZONE).isoformat(),
        "window_days": 30, "record_count": len(public),
        "private_feed_encrypted": encrypted is not None,
        "purchase_ready_count": sum(row["purchase_ready"] for row in public),
    }, indent=2) + "\n")
    print(f"Fetched {len(records)} recent source records; published {len(public)} active previews.")
    print("Private encrypted feed enabled:", encrypted is not None)
    if not key:
        print("::warning::SHLAE_PRIVATE_FEED_KEY is not configured. Full details are not retained or deployed.")


if __name__ == "__main__":
    main()
