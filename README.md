# SHLAE Boston project activity and researched lead data

## Current daily workflow

`.github/workflows/daily_lead_scraper.yml` tests the pipeline and runs `daily_leads.py` daily at 10:14 UTC. It retrieves Boston Inspectional Services building permits issued within the rolling 30-day window, excludes closed/expired/revoked/canceled/void permits, deduplicates source-derived IDs, and sorts newest records first. A source failure preserves existing outputs; a successful empty result replaces expired inventory.

`mine_multi_industry_leads.py` supplies shared helpers and a separate legacy preview builder. Its reviewed IT/professional opportunity CSV is **not consumed by the active daily_leads.py workflow**. Do not describe those sectors as populated by the daily permit feed.

## What the data contains

Public previews contain SHLAE ID, sector, generic activity description, Boston location, agency, declared valuation when present, record date, dataset link, check date, expiry date, contact status and purchase readiness. Business/contact identities, street addresses, email and phone are withheld.

Private project records contain address/city/state/ZIP where supplied, description, permit number/type/status/issue date, applicant name, reported valuation, expiration date, occupancy type, square footage and an individual source-record link. Missing source fields remain blank. A permit applicant is not automatically a property owner or decision maker; valuation is not a confirmed remaining budget.

Separately researched contacts may add business name, company role, contact name/role, email and/or phone, website, contact evidence source, review date and verification status. `SHLAE_REVIEWED_CONTACTS_JSON` must be keyed by stable lead ID. Current enrichment requires evidence dated within the last 30 days and an HTTPS source. The basic `purchase_ready` flag requires a company name and at least one email or phone; it does not by itself prove that checkout or a buyer download is ready.

Contract status is independent of permit status. Reviewed `SHLAE_REVIEWED_CONTRACTS_JSON` can add open solicitation, awarded, work underway, completed or canceled status, appointed contractor, award date, source and check date. Without accepted evidence, contract status remains unknown. Never infer an open bid, buying intent or remaining work from an issued permit.

## Premium energy packages

`energy_packages.py` groups explicit permit descriptions into solar, battery-storage, heat-pumps, ev-charging and efficiency packages. Eligibility additionally requires company/contact roles and `contact_verification=reviewed`; completed/canceled projects are excluded. Incomplete records go to contact review. One project may appear in several categories, so counts overlap. CSV exports include activity categories, project and contact fields, evidence dates/links, contract status, and new/changed/unchanged markers.

## Public and private delivery

`public/feed_status.json` reports freshness, record count, encryption availability and contact-ready count. `public/energy_package_status.json` reports package eligibility. Check current counts before advertising available inventory. Encryption availability does not mean verified contacts or paid delivery exist.

With `SHLAE_PRIVATE_FEED_KEY` (base64 32-byte key), full records are retained as AES-256-GCM encrypted data. Energy package bundles are retained in a private GitHub Actions artifact for seven days. Never commit plaintext contacts or buyer exports, and never place plaintext exports under `public/`. Decryption/export uses the key from the environment, not command-line arguments:

```bash
python energy_packages.py private/energy_packages.enc.json --output private/exports
```

The FTP action uploads `public/` only when `SHLAE_PUBLIC_FEED_ENABLED=true`, using configured FTP secrets on port 21. It currently uses FTP, not FTPS. Keep deployment rooted to the intended SHLAE leads directory; do not expose decrypted files there.

## Customer-facing offer

Explain the exact available fields, reviewed record count, price, file format and delivery before taking payment. The website's single-lead price is $15 when a reviewed record and delivery are confirmed; premium packages are scoped separately. Public previews are not automatically saleable. A selected-lead checkout, buyer limits, sale window and protected download must be verified independently; the pipeline does not implement them. Monthly alerts are separately invoiced each month.

## Validation

```bash
python -m unittest discover -s tests -v
```

Tests do not require network access. Live source retrieval and site delivery must be checked separately.
