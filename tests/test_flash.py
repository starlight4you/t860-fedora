#!/usr/bin/env python3
"""Exercise the actual host installer against a non-destructive fake ADB peer."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

PROJECT=Path(__file__).resolve().parents[1]
FAKE='''#!PYTHON
import json,os,sys
from pathlib import Path
a=sys.argv[1:]
with open(os.environ['ADB_LOG'],'a') as f: f.write(json.dumps(a)+'\\n')
if a[:2]==['shell','getprop']:
 print({'ro.twrp.version':'3.7.0-test','ro.product.model':os.environ.get('MODEL','SM-T860'),'ro.product.device':'test-device'}[a[2]])
elif a==['shell','id','-u']: print('0')
elif a[0]=='pull': Path(a[-1]).mkdir()
elif a[-1]=='write-root':
 data=sys.stdin.buffer.read()
 with open(os.environ['ADB_LOG'],'a') as f: f.write(json.dumps({'received':len(data)})+'\\n')
 sys.exit(42 if os.environ.get('FAIL_WRITE') else 0)
'''

class FlashTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name)
  shutil.copy2(PROJECT/'flash.py',self.root/'flash.py')
  self.bin=self.root/'bin'; self.bin.mkdir()
  adb=self.bin/'adb'; adb.write_text(FAKE.replace('PYTHON',sys.executable,1)); adb.chmod(0o755)
  files={'installer.tar.gz':b'installer fixture','root.part000':b'first root piece','root.part001':b'last piece'}
  for name,data in files.items(): (self.root/name).write_bytes(data)
  manifest={'release':'v2026.10.29-gpu18','device':'SM-T860','installer_bundle':'installer.tar.gz',
            'rootfs_parts':['root.part000','root.part001'],
            'assets':[{'name':n,'bytes':len(d),'sha256':hashlib.sha256(d).hexdigest()} for n,d in files.items()]}
  (self.root/'manifest.json').write_text(json.dumps(manifest))
  self.log=self.root/'adb.log'
  self.env=dict(os.environ,PATH=str(self.bin)+os.pathsep+os.environ['PATH'],ADB_LOG=str(self.log))
 def run_flash(self,*args,answer='',**env):
  return subprocess.run([sys.executable,str(self.root/'flash.py'),*args],input=answer,text=True,capture_output=True,env=dict(self.env,**env))
 def calls(self):
  return [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []
 def test_check_only_never_writes(self):
  result=self.run_flash('--check-only'); self.assertEqual(result.returncode,0,result.stderr)
  self.assertTrue(any(isinstance(c,list) and c[-1]=='prepare' for c in self.calls()))
  self.assertFalse(any(isinstance(c,list) and c[-1] in ['write-root','finish','reboot'] for c in self.calls()))
 def test_corrupt_asset_stops_before_adb(self):
  (self.root/'root.part001').write_bytes(b'corrupted')
  result=self.run_flash('--check-only'); self.assertNotEqual(result.returncode,0)
  self.assertEqual(self.calls(),[])
 def test_wrong_model_stops_before_push(self):
  result=self.run_flash('--check-only',MODEL='SM-T865'); self.assertNotEqual(result.returncode,0)
  self.assertFalse(any(c[0]=='push' for c in self.calls()))
 def test_cancel_never_pushes_or_writes(self):
  result=self.run_flash('--erase-android',answer='cancel\n'); self.assertNotEqual(result.returncode,0)
  self.assertFalse(any(c[0]=='push' for c in self.calls()))
 def test_success_streams_all_parts_then_finishes(self):
  result=self.run_flash('--erase-android',answer='SM-T860 ERASE\n'); self.assertEqual(result.returncode,0,result.stderr)
  self.assertIn({'received':26},self.calls())
  self.assertTrue(any(isinstance(c,list) and c[-1]=='finish' for c in self.calls()))
 def test_remote_failure_prevents_finish_and_reboot(self):
  result=self.run_flash('--erase-android',answer='SM-T860 ERASE\n',FAIL_WRITE='1'); self.assertNotEqual(result.returncode,0)
  self.assertFalse(any(isinstance(c,list) and c[-1] in ['finish','reboot'] for c in self.calls()))

if __name__=='__main__': unittest.main()
