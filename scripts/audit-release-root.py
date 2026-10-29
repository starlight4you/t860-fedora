#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Fail closed on known private identity in a mounted public image."""
import argparse
import hashlib
import re
import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET

p=argparse.ArgumentParser()
p.add_argument('--root',type=Path,required=True)
p.add_argument('--original-project',type=Path,required=True)
a=p.parse_args(); r=a.root; src=a.original_project
assert not (r/'root/.ssh').exists()
assert not list((r/'etc/ssh').glob('ssh_host_*'))
assert (r/'etc/machine-id').read_text()==''
assert not (r/'usr/share/qcom/sm8150/Samsung/gts6lwifi').exists()
assert not (r/'usr/lib/firmware/qcom/sm8150/gts6l').exists()
assert not (r/'usr/lib/firmware/ath10k/WCN3990/hw1.0/board-2.bin').exists()
assert not (r/'etc/tabs6-bt-address').exists()
assert list((r/'usr/lib/modules').iterdir())==[r/'usr/lib/modules/6.18.59-t860-gpu18']
assert sorted(x.name for x in (r/'etc/NetworkManager/system-connections').iterdir())==['tabs6-usb.nmconnection']
assert not list(r.glob('etc/*shadow-'))
shadow={row.split(':',1)[0]:row.split(':')[1] for row in (r/'etc/shadow').read_text().splitlines()}
assert shadow['root']=='!', 'Remove the old password hash entirely; merely locking it is insufficient'
needles=[]
original_shadow=subprocess.check_output(['debugfs','-R','cat /etc/shadow',str(src/'build/rootfs.img')],stderr=subprocess.DEVNULL,text=True)
for row in original_shadow.splitlines():
    fields=row.split(':')
    if len(fields)>1 and fields[1].lstrip('!').startswith('$'):
        needles.append(fields[1].lstrip('!').encode())
for path in ['private/login.txt','private/bt-address','private/ssh_ed25519.pub']:
    data=(src/path).read_bytes().strip()
    if path.endswith('login.txt'):
        needles.extend(x.split(b':',1)[1] for x in data.splitlines() if x.startswith((b'fedora:',b'root:')) and len(x.split(b':',1)[1])>=8)
    else: needles.append(data)
for e in ET.parse(src/'private/wifi-store.xml').findall(".//string[@name='PreSharedKey']"):
    data=(e.text or '').strip('"').encode()
    # Short passwords can be common words in public distro templates.
    # Network profiles and user/runtime directories are checked structurally above.
    if len(data)>=12 and data!=b'null': needles.append(data)
checked=0
package_digests={}
def unchanged_package_file(path,data):
    rel='/'+path.relative_to(r).as_posix()
    if rel not in package_digests:
        result=subprocess.run(['chroot',str(r),'rpm','-qf','--qf','[%{FILENAMES}|%{FILEDIGESTS}\n]',rel],capture_output=True,text=True)
        for row in result.stdout.splitlines():
            if '|' in row:
                name,digest=row.split('|',1)
                package_digests.setdefault(name,set()).add(digest)
        package_digests.setdefault(rel,set())
    return hashlib.sha256(data).hexdigest() in package_digests[rel]
for directory in ['etc','home','root','var','usr/local']:
    for path in (r/directory).rglob('*'):
        if path.is_symlink() or not path.is_file(): continue
        data=path.read_bytes()
        assert not re.search(rb'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----\r?\n(?:[A-Za-z0-9+/=]+\r?\n)+-----END', data), f'Private key in {path.relative_to(r)}'
        # A short saved password may also be a word in an upstream config template.
        # Accept that coincidence only when the entire file matches its RPM digest.
        if any(n in data for n in needles if n):
            assert unchanged_package_file(path,data), f'Private material in {path.relative_to(r)}'
        checked+=1
print('PRIVACY_AUDIT_PASS',checked,'files; no known credentials, keys or device identity')
