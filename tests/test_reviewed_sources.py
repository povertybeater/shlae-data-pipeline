import unittest
from datetime import date
import reviewed_sources as r

class SourceTests(unittest.TestCase):
    def test_source_identity_and_channel(self):
        d=date(2026,10,2)
        html='<h1>Roper Electrical Corporation</h1><p>781 885 1310</p><p>office@example.com</p>'
        x=r.extract('Roper Electrical Corporation',html,'https://example.com/contact',d)
        self.assertEqual(x['contact_verification'],'contact_checked')
        self.assertFalse(x['mailbox_delivery_tested'])
        self.assertIsNone(r.extract('Different Company',html,'https://example.com',d))
        self.assertIsNone(r.extract('Roper Electrical Corporation','<h1>Roper Electrical Corporation</h1><script>fake@example.com</script>','https://example.com',d))
    def test_one_fetch_and_fail_closed(self):
        rows=[{'applicant':'Roper Electrical Corporation'}]*2
        calls=[]
        def reader(url): calls.append(url); return '<h1>Roper Electrical Corporation</h1><p>781 885 1310</p>'
        contacts,status=r.refresh(rows,date(2026,10,2),reader,lambda u:True)
        self.assertEqual(len(calls),1)
        self.assertEqual(len(contacts),1)
        self.assertEqual(r.refresh(rows,date(2026,10,2),reader,lambda u:False)[0],{})
