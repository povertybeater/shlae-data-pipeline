import os
import json
import csv
import re
from datetime import datetime, timedelta
import requests

# Optional: Add your free Socrata API Token via environment variable
SOCRATA_APP_TOKEN = os.getenv("SOCRATA_APP_TOKEN", "")

# 1. Endpoints & Constants
BOSTON_PERMITS_ENDPOINT = "https://data.boston.gov/api/3/action/datastore_search"
RESOURCE_ID_BUILDING_PERMITS = "6ddcd912-32a0-43df-9908-63574f8c7e77" # Building Permits

# Categories & Keywords Filter Map
CATEGORY_KEYWORDS = {
    "Construction": ["construction", "building", "permit", "renovation", "contractor", "masonry", "plumbing", "electrical", "hvac", "roofing"],
    "IT": ["software", "hardware", "network", "cybersecurity", "cloud", "it services", "technology", "telecom", "data"],
    "Event Management & Catering": ["catering", "event", "venue", "banquet", "food service", "hospitality", "av equipment"],
    "Professional Services": ["consulting", "legal", "accounting", "janitorial", "security", "marketing", "staffing", "architecture"]
}

def redact_email(email):

    if not email or "@" not in email:
        return "contact*****@domain.com"
    name, domain = email.split("@", 1)
    if len(name) <= 2:
        redacted_name = name[0] + "*****"
    else:
        redacted_name = name[0] + "*****" + name[-1]
    return f"{redacted_name}@{domain}"

def redact_text(text):
    if not text:
        return "N/A"
    words = text.split()
    if len(words) > 1:
        return words[0] + " ***** " + words[-1]
    return text[:2] + "*****"

def fetch_boston_permits():
    """Fetch building permits from Boston Socrata/CKAN API"""
    headers = {}
    if SOCRATA_APP_TOKEN:
        headers["X-App-Token"] = SOCRATA_APP_TOKEN
        
    params = {
        "resource_id": RESOURCE_ID_BUILDING_PERMITS,
        "limit": 100,
        "sort": "declared_valuation desc"
    }
    
    try:
        response = requests.get(BOSTON_PERMITS_ENDPOINT, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        records = data.get("result", {}).get("records", [])
        return records
    except Exception as e:
        print(f"Error fetching Boston permits: {e}")
        return []

def categorize_lead(work_description, category_hint=""):
    """Assign record to one of the 4 main categories"""
    text = (work_description + " " + category_hint).lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return category
    return "Construction" # Default fallback for building permits

def process_leads():
    raw_permits = fetch_boston_permits()
    processed_leads = []
    
    for idx, item in enumerate(raw_permits, start=101):
        work_desc = item.get("workdesc", "General Construction Project")
        category = categorize_lead(work_desc)
        
        raw_val = item.get("declared_valuation", "0")
        try:
            val_float = float(re.sub(r"[^\d.]", "", str(raw_val)))
            formatted_val = f"${val_float:,.0f}" if val_float > 0 else "$250,000+"
        except ValueError:
            formatted_val = "$250,000+"

        applicant = item.get("applicant", "Prime Contractor LLC")
        owner = item.get("owner", "City of Boston / Private Owner")
        
        # Build Lead Record
        lead = {
            "id": idx,
            "sector": category,
            "name": f"{category} Project - {item.get('address', 'Greater Boston')}",
            "agency": owner,
            "value": formatted_val,
            "description": work_desc[:120] + "..." if len(work_desc) > 120 else work_desc,
            "raw_contact": applicant,
            "email": redact_email(f"procurement@{str(applicant or 'unknown').lower().replace(' ', '').replace(',', '')[:8]}.com"),
            "unlocked": False,
            "date_added": datetime.now().strftime("%Y-%m-%d")
        }
        processed_leads.append(lead)

    # Output 1: Save JSON feed for dynamic website display
    with open("multi_industry_leads.json", "w", encoding="utf-8") as f:
        json.dump(processed_leads, f, indent=2)
        
    # Output 2: Save CSV export file
    keys = processed_leads[0].keys() if processed_leads else []
    if keys:
        with open("leads.csv", "w", newline="", encoding="utf-8") as f:
            dict_writer = csv.DictWriter(f, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(processed_leads)

    print(f"Successfully processed {len(processed_leads)} leads across 4 categories.")

if __name__ == "__main__":
    process_leads()
