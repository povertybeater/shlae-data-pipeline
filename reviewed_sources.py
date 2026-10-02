"""Refresh publicly listed contacts from manually matched official sources.

Only source URLs and applicant hashes are committed. Contact values stay in
memory and the encrypted private feed. Published does not mean call-tested.
"""
import hashlib
import re
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.robotparser import RobotFileParser
from urllib.parse import urlsplit

APPROVED = {'6a703688553a89be497fa3218d01ff87f5f3f2e49274ac49006d3efb94228725':
            'https://roperelectricalcorp.com/contact/'}


def normalize(value):
    return re.sub(r'[^a-z0-9]', '', str(value).lower())


class Text(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'): self.hidden += 1
    def handle_endtag(self, tag):
        if tag in ('script', 'style'): self.hidden = max(0, self.hidden - 1)
    def handle_data(self, data):
        if not self.hidden: self.parts.append(data)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Source redirect requires renewed review')


def fetch(url):
    opener = build_opener(NoRedirect)
    with opener.open(Request(url, headers={'User-Agent': 'SHLAE-SourceCheck/1.0'}), timeout=12) as response:
        data = response.read(1000001)
        if len(data) > 1000000: raise ValueError('Oversized source')
        return data.decode('utf-8', errors='replace')


def permitted(url):
    origin = urlsplit(url)
    robots = RobotFileParser()
    try: robots.parse(fetch(f'{origin.scheme}://{origin.netloc}/robots.txt').splitlines())
    except HTTPError as error:
        if error.code == 404: return True
        return False
    except (OSError, ValueError): return False
    return robots.can_fetch('SHLAE-SourceCheck', url)


def extract(applicant, html, source, today):
    parser = Text(); parser.feed(html)
    text = ' '.join(parser.parts)
    if normalize(applicant) not in normalize(text): return None
    emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', text)
    phones = re.findall(r'(?<!\d)(?:\+1[\s.-]*)?\(?\d{3}\)?[\s.-]+\d{3}[\s.-]+\d{4}(?!\d)', text)
    if not (emails or phones): return None
    return dict(business_name=applicant, contact_name='', email=emails[0] if emails else '',
                phone=phones[0] if phones else '', website=f'https://{urlsplit(source).netloc}/',
                company_role='Permit applicant / electrical contractor', contact_role='Business office',
                contact_verification='contact_checked', verification_method='published_official_source',
                mailbox_delivery_tested=False, phone_call_tested=False,
                source_url=source, checked_at=today.isoformat())


def refresh(records, today, reader=fetch, policy=permitted):
    matches = {}
    for row in records:
        name = str(row.get('applicant') or '').strip()
        fingerprint = hashlib.sha256(normalize(name).encode()).hexdigest()
        source = APPROVED.get(fingerprint)
        if source: matches[name] = source
    contacts = {}; failed = 0
    for name, source in matches.items():
        try:
            if not policy(source): failed += 1; continue
            contact = extract(name, reader(source), source, today)
            if contact: contacts[name] = contact
            else: failed += 1
        except (OSError, ValueError): failed += 1
    return contacts, {'approved_businesses': len(matches), 'published_contacts_checked': len(contacts),
                      'source_checks_failed': failed, 'mailbox_delivery_tests': 0, 'phone_call_tests': 0}
