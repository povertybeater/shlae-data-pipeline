import csv
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mine_multi_industry_leads as pipeline


class PublicPreviewTests(unittest.TestCase):
    def setUp(self):
        self.record = {"_id": 42, "address": "12 Example St", "workdesc": "Install rooftop solar array", "declared_valuation": "10000"}

    def test_stable_id_and_no_invented_contacts(self):
        first = pipeline.transform(self.record)
        second = pipeline.transform(dict(self.record, applicant="Jane Doe"))
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["sector"], "Renewable Energy")
        self.assertEqual(first["source_type"], "building_permit")
        self.assertFalse({"email", "phone", "raw_contact"} & first.keys())

    def test_missing_identity_is_skipped(self):
        self.assertIsNone(pipeline.transform({"address": "12 Example St"}))

    def test_first_seen_is_preserved(self):
        now = datetime(2026, 9, 28, tzinfo=timezone.utc)
        rows, state = pipeline.build([self.record], now=now)
        later, again = pipeline.build([self.record], previous=state, now=datetime(2026, 9, 29, tzinfo=timezone.utc))
        self.assertEqual(rows[0]["first_seen_at"], later[0]["first_seen_at"])
        self.assertEqual(state, again)

    def test_bad_source_response_fails_closed(self):
        def opener(url, timeout):
            return BytesIO(b'{"success": false, "result": {"records": []}}')
        with self.assertRaises(RuntimeError):
            pipeline.fetch_permits(opener=opener)

    def test_reviewed_record_requires_official_boston_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reviewed.csv"
            with path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["source_id", "source_url", "sector", "name", "location", "agency", "description", "record_date", "value"])
                writer.writeheader()
                writer.writerow({"source_id": "EV123", "source_url": "https://unverified.example/EV123", "sector": "IT Services", "name": "IT bid", "location": "Boston, MA"})
            with self.assertRaises(ValueError):
                pipeline.reviewed_previews(path)


if __name__ == "__main__":
    unittest.main()
