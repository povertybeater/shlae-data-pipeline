"""Energy prospect packages. No inferred buying intent or guessed contacts."""
import argparse
import base64
import csv
import hashlib
import json
import re
from pathlib import Path

RULES = {
    'battery-storage': r'\b(battery (?:energy )?storage|energy storage system|BESS)\b',
    'solar': r'\b(solar|photovoltaic|pv array)\b',
    'heat-pumps': r'\b(heat[ -]?pumps?|mini[ -]?splits?)\b',
    'ev-charging': r'\b(EV charging|electric vehicle charg\w*|EVSE)\b',
    'efficiency': r'\b(energy efficiency|weatherization|energy retrofit)\b',
}
CSV_FIELDS = ['id','activity_types','business_name','company_role','contact_name','contact_role','applicant_name',
              'email','phone','website','street_address','city','state','zip','description',
              'value','permit_number','permit_type','permit_status','record_date',
              'source_url','contact_source_url','contact_checked_at','contact_verification',
              'change_type','prospect_basis','purchase_ready','contract_status','appointed_contractor',
              'award_date','contract_status_source_url','contract_status_checked_at']


def classify(text):
    return [name for name, pattern in RULES.items() if re.search(pattern, text, re.I)]


def fingerprint(row):
    fields = ['description','value','permit_status','business_name','company_role',
              'contact_name','contact_role','applicant_name','email','phone','contact_source_url',
              'contact_verification','contact_checked_at','contract_status','appointed_contractor',
              'award_date','contract_status_source_url','contract_status_checked_at']
    return hashlib.sha256(json.dumps({k: row.get(k,'') for k in fields},sort_keys=True).encode()).hexdigest()


def packages(records, previous=None):
    previous = previous or {}
    output = {name: [] for name in RULES}
    review = []
    state = {}
    for original in records:
        row = dict(original)
        types = classify(row.get('description',''))
        if not types:
            continue
        row['activity_types'] = '; '.join(types)
        row['prospect_basis'] = 'Issued permit activity; buying intent and remaining work are not confirmed.'
        digest = fingerprint(row)
        row['change_type'] = ('new' if row['id'] not in previous else
                              'changed' if previous[row['id']] != digest else 'unchanged')
        state[row['id']] = digest
        ready = bool(row.get('contract_status', 'unknown') not in {'completed','canceled'} and row.get('purchase_ready') and row.get('company_role') and
                     row.get('contact_role') and row.get('contact_verification') == 'reviewed')
        row['purchase_ready'] = ready
        if ready:
            for name in types:
                output[name].append(row)
        else:
            row['review_reason'] = 'Needs current contact evidence, company/contact roles and reviewed verification; completed/canceled projects are excluded.'
            review.append(row)
    # A permit can appear in multiple category packages; each category has unique IDs.
    return output, review, state


def decrypt(path, key):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    envelope = json.loads(Path(path).read_text())
    if envelope.get('version') != 1 or envelope.get('algorithm') != 'AES-256-GCM':
        raise ValueError('Unsupported encrypted envelope')
    return json.loads(AESGCM(base64.b64decode(key,validate=True)).decrypt(
        base64.b64decode(envelope['nonce']),base64.b64decode(envelope['ciphertext']),
        b'shlae-private-feed-v1'))


def safe_cell(value):
    value = str(value if value is not None else '')
    return "'" + value if value.lstrip().startswith(('=','+','-','@')) else value


def export(bundle, destination):
    target = Path(destination)
    target.mkdir(parents=True,exist_ok=True)
    for package in bundle:
        name = package['package']
        if name not in RULES and name != 'contact-review':
            raise ValueError('Unknown package')
        fields = CSV_FIELDS + (['review_reason'] if name == 'contact-review' else [])
        with (target / (name + '.csv')).open('w',newline='',encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f,fieldnames=fields,extrasaction='ignore')
            writer.writeheader()
            writer.writerows({k:safe_cell(r.get(k,'')) for k in fields} for r in package['records'])


if __name__ == '__main__':
    import os
    parser = argparse.ArgumentParser(description='Decrypt package bundle to local private CSVs. Never put these in public/.')
    parser.add_argument('bundle')
    parser.add_argument('--output',default='private/exports')
    args = parser.parse_args()
    dest = Path(args.output).resolve()
    root = Path(__file__).resolve().parent
    if root / 'public' == dest or root / 'public' in dest.parents:
        parser.error('Plaintext exports cannot be written under public/')
    export(decrypt(args.bundle,os.environ['SHLAE_PRIVATE_FEED_KEY']),dest)
