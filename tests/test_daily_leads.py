import base64
import json
import unittest
from datetime import date
from io import BytesIO
from urllib.parse import parse_qs, urlparse

import daily_leads as p


class DailyTests(unittest.TestCase):
    today = date(2026, 9, 29)

    def record(self, **changes):
        row = {"_id": 42, "address": "12 Secret St", "issued_date": "2026-09-29T12:00:00",
               "status": "Open", "applicant": "Private Name", "comments": "Solar panels for Acme: a@example.com",
               "description": "Other", "declared_valuation": "$5000"}
        return dict(row, **changes)

    def test_cutoff_future_missing_and_closed(self):
        rows = [self.record(), self.record(_id=43, issued_date="2026-08-30"),
                self.record(_id=44, issued_date="2026-09-30"),
                self.record(_id=45, issued_date=""), self.record(_id=46, status="Closed")]
        public, full, state = p.build(rows, self.today, {"expired": "2020-01-01"})
        self.assertEqual(len(public), 1)
        self.assertNotIn("expired", state)
        self.assertEqual(full[0]["sector"], "Renewable Energy")
        self.assertFalse(public[0]["purchase_ready"])

    def test_newest_first_dedup_and_empty_success(self):
        rows = [self.record(issued_date="2026-09-20"), self.record(_id=43), self.record(_id=43)]
        public, full, state = p.build(rows, self.today)
        self.assertEqual(len(public), 2)
        self.assertGreater(public[0]["record_date"], public[1]["record_date"])
        self.assertEqual(p.build([], self.today), ([], [], {}))

    def test_no_identity_in_public_even_free_text(self):
        public, full, state = p.build([self.record()], self.today)
        text = json.dumps(public)
        for value in ("12 Secret St", "Private Name", "Acme", "a@example.com"):
            self.assertNotIn(value, text)
        self.assertIn("Private Name", json.dumps(full))
        self.assertEqual(set(public[0]), set(p.PUBLIC_FIELDS))

    def test_contacts_require_fresh_evidence_and_are_redacted(self):
        item = self.record()
        lead_id = p.stable_id("permit", f"{p.RESOURCE}:42")
        contacts = {lead_id: {"business_name": "Acme", "email": "a@example.com", "contact_verification": "contact_checked",
                             "checked_at": "2026-09-29", "source_url": "https://example.com/contact"}}
        public, full, _ = p.build([item], self.today, contacts=contacts)
        self.assertTrue(public[0]["purchase_ready"])
        self.assertNotIn("Acme", json.dumps(public))
        contacts[lead_id]["checked_at"] = "2026-08-30"
        self.assertFalse(p.build([item], self.today, contacts=contacts)[0][0]["purchase_ready"])

    def test_permit_duplicates_expiration_and_quality(self):
        rows = [self.record(permitnumber="ABC"), self.record(_id=43, permitnumber="ABC"),
                self.record(_id=44, expiration_date="2026-09-28")]
        public, _, _ = p.build(rows, self.today)
        self.assertEqual(len(public), 1)
        self.assertEqual(public[0]["age_days"], 0)
        self.assertEqual(public[0]["freshness"], "new")
        self.assertEqual(public[0]["contact_quality"], "unverified")

    def test_candidate_and_business_match_not_purchase_ready(self):
        lead_id = p.stable_id("permit", f"{p.RESOURCE}:42")
        contact = {"business_name": "Acme", "email": "a@example.com",
                   "checked_at": self.today.isoformat(), "source_url": "https://example.com"}
        for status in ("", "candidate_needs_identity_review", "business_matched"):
            contact["contact_verification"] = status
            public, _, _ = p.build([self.record()], self.today, contacts={lead_id: contact})
            self.assertFalse(public[0]["purchase_ready"])
        contact["contact_verification"] = "contact_checked"
        contact["email"] = "broken"
        self.assertFalse(p.build([self.record()], self.today, contacts={lead_id: contact})[0][0]["purchase_ready"])

    def test_date_sorted_query_and_failure(self):
        seen = []
        def opener(url, timeout):
            seen.append(parse_qs(urlparse(url).query)["sql"][0])
            return BytesIO(b'{"success":true,"result":{"records":[]}}')
        self.assertEqual(p.fetch_recent(self.today, opener), [])
        self.assertIn("ORDER BY issued_date DESC", seen[0])
        self.assertIn("2026-08-30", seen[0])
        with self.assertRaises(RuntimeError):
            p.fetch_recent(self.today, lambda url, timeout: BytesIO(b'{"success":false}'))

    def test_encrypted_feed_roundtrip(self):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key = b"x" * 32
        envelope = json.loads(p.encrypt_full([{"email": "a@example.com"}], base64.b64encode(key).decode()))
        self.assertNotIn("a@example.com", json.dumps(envelope))
        clear = AESGCM(key).decrypt(base64.b64decode(envelope["nonce"]),
                                   base64.b64decode(envelope["ciphertext"]), b"shlae-private-feed-v1")
        self.assertEqual(json.loads(clear), [{"email": "a@example.com"}])


if __name__ == "__main__":
    unittest.main()

