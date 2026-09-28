# SHLAE Boston public lead previews

This repository produces public, source-backed **previews**, not paid leads. It never invents an email, phone, value, owner, or opportunity. Building permits indicate activity; they are not necessarily open bids. Do not sell a preview until its contact information and buyer file have been separately verified.

## Files to replace in GitHub

Replace `mine_multi_industry_leads.py`, `.github/workflows/daily_lead_scraper.yml`, and `README.md`. Add `reviewed_opportunities.csv` and `tests/test_pipeline.py`. Remove the old root `leads.csv` and `multi_industry_leads.json`, which contain synthetic email domains and unstable IDs. The new script writes safe output under `public/`.

## Four sectors

- **Construction:** Boston building permits from the official Analyze Boston CKAN resource.
- **Renewable Energy:** permit descriptions with explicit solar, photovoltaic, storage, heat pump, geothermal, or wind terms; still permit activity, not an open bid.
- **IT Services and Professional Services:** add only after reviewing an individual official Boston bid or public record. Enter the source ID, source URL, exact title, Boston location, agency, description, date, and value (leave unavailable values blank) in `reviewed_opportunities.csv`. The template contains no examples so it cannot publish fictitious entries.

An official Boston bid listing is at <https://www.boston.gov/bid-listings>. Check its due date and status before describing it as open. The script accepts Boston.gov and Analyze Boston HTTPS links but cannot itself prove an individual reviewed row's accuracy. The reviewer is responsible for that check.

## Run and inspect

```bash
python -m unittest discover -s tests -v
python mine_multi_industry_leads.py
```

The script requires a successful Boston API response. It will not overwrite outputs after a source failure or an invalid reviewed CSV. The public JSON and CSV are generated under `public/`. Stable source-derived IDs and `state/first_seen.json` survive daily runs. `first_seen_at` is **not** the 30-day paid sale start; that begins when a reviewed lead is first offered for sale and is stored separately in the private manifest.

## GitHub Actions and aaPanel FTP

The scheduled workflow runs at **10:14 UTC**, which changes local Boston clock time with daylight saving. It tests and builds every day. Upload is **off** until the repository variable `SHLAE_PUBLIC_FEED_ENABLED` is set to `true` after a manual run and review.

Set repository secrets `FTPS_HOST`, `FTPS_USERNAME`, and `FTPS_PASSWORD` for an FTPS account rooted at `/www/wwwroot/shlae.com/wp-content/uploads/leads/`. The action uses `server-dir: ./` and uploads only the `public/` directory contents. Verify the server permits explicit FTPS on port 21 and that the files appear at `https://shlae.com/wp-content/uploads/leads/multi_industry_leads.json` before enabling daily upload. Never place purchased contact files in that public directory or in this repository.

The current SHLAE Curated Leads page is a preparation notice and does not read this JSON yet. The $15 product is a draft. The purchase selection, five-buyer limit, 30-day sale window, and private delivery require their separate WordPress checkout integration and reviewed buyer files. Do not republish that product just because this public feed runs.
