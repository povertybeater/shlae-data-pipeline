# Daily Boston feed

Runs at 10:14 UTC every day (6:14 a.m. Boston during daylight saving time,
5:14 a.m. in winter), on manual dispatch, and when pipeline code is pushed.

The source-date window is the 30 Boston calendar dates ending today. An issued
record expires at the beginning of the date 30 days after its source date.
Each successful run replaces the inventory, including an empty inventory.
Newest issued date comes first. Closed/expired/revoked/cancelled permits are
excluded. Permits are activity signals, not open bids or proof of buying intent.
Source failures preserve the last feed and fail the job; the website must also
filter expires_on against today's Boston date so failed runs cannot show expired
inventory.

## Public previews

Only generic sector summaries, Boston city-level location, valuation, record
dates and status appear publicly. Free-text project descriptions, business and
applicant names, street addresses, emails, phone numbers and direct source-record
links are withheld. The source link points to the dataset.

## Full records and contacts

Boston's source supplies applicant names, addresses, permit numbers, comments,
status, valuation and other project details. It has no email, phone, business
name or website fields. Applicants are NOT assumed to be business owners.
No contact is invented, no applicant-only record is marked ready for purchase.

Optional researched contacts may be supplied in the GitHub Actions secret
SHLAE_REVIEWED_CONTACTS_JSON, keyed by the stable BOS lead ID. Each entry has
business_name, contact_name, email, phone, website, source_url (HTTPS evidence)
and checked_at (YYYY-MM-DD). This is dated human research, not automated
verification. Entries older than 30 days are ignored. A business name and email
or phone are required before a record is purchase_ready. The operator must
refresh/remove contact configuration; the daily run does not manage this secret.

## Private delivery

Set SHLAE_PRIVATE_FEED_KEY to a base64-encoded random 32-byte key through GitHub's
secure Secrets UI, and configure the same key securely on the paid-download
server. Do not put it in chat, source code or public WordPress settings.
With a key, each run encrypts the current full inventory using AES-256-GCM in
public/private_leads.enc.json. Only encrypted bytes are deployed via the existing
FTP upload; plaintext is not committed, uploaded or saved as an Actions artifact.
The private file is ignored by git. Without a key the public run still succeeds,
but full records are ephemeral and no private file is retained or deployed.

The workflow retains existing FTP settings and its SHLAE_PUBLIC_FEED_ENABLED
gate. It uploads ./public/ to the FTP account root, which must remain the SHLAE
uploads/leads folder.

This pipeline does NOT implement payment authorization or website decryption.
The WooCommerce integration must verify payment and record entitlement before
decrypting and returning an individual lead. Never link the full decrypted
inventory as a downloadable product. Purchase buttons must remain disabled for
records without reviewed contacts or without configured private delivery.

## Checks

Run `python -m unittest discover -s tests -v` after installing
`cryptography==46.0.5`. Live build: `python daily_leads.py`.
The status file reports last update, inventory count, private delivery state,
and purchase-ready count. Daily expiry removes active inventory, not historical
git versions, backups or already-purchased customer copies.
