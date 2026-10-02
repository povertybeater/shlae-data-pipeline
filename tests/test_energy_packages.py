import base64,json,tempfile,unittest
from pathlib import Path
from energy_packages import classify,packages,decrypt,export
from daily_leads import encrypt_full
class PackageTests(unittest.TestCase):
 def row(self,**kw):
  return dict(dict(id='one',description='Solar and battery energy storage',business_name='Company',company_role='installer',contact_role='sales',email='a@example.com',contact_verification='reviewed',purchase_ready=True),**kw)
 def test_categories(self):
  self.assertEqual(classify('replace smoke alarm battery'),[])
  self.assertEqual(classify('solar and battery energy storage'),['battery-storage','solar'])
 def test_readiness_and_changes(self):
  g,r,s=packages([self.row()]);self.assertEqual(g['solar'][0]['change_type'],'new')
  self.assertEqual(packages([self.row()],s)[0]['solar'][0]['change_type'],'unchanged')
  self.assertEqual(packages([self.row(email='b@example.com')],s)[0]['solar'][0]['change_type'],'changed')
  g,r,s=packages([self.row(company_role='')]);self.assertFalse(g['solar']);self.assertEqual(len(r),1)
  self.assertEqual(packages([])[2],{})
 def test_encrypted_export(self):
  key=base64.b64encode(b'x'*32).decode();bundle=[dict(package='solar',records=[self.row(business_name='=BAD()')])]
  with tempfile.TemporaryDirectory() as f:
   p=Path(f)/'enc.json';p.write_text(encrypt_full(bundle,key));self.assertNotIn('a@example.com',p.read_text())
   self.assertEqual(decrypt(p,key),bundle);export(bundle,Path(f)/'csv')
   self.assertIn("'=BAD()",(Path(f)/'csv/solar.csv').read_text(encoding='utf-8-sig'))
   with self.assertRaises(Exception):decrypt(p,base64.b64encode(b'y'*32).decode())
