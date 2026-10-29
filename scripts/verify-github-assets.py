#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compare GitHub's server-computed release digests with local artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

p=argparse.ArgumentParser()
p.add_argument('--repo',default='starlight4you/t860-fedora')
p.add_argument('--tag',default='v2026.10.29-gpu18')
p.add_argument('--assets',type=Path,required=True)
a=p.parse_args()
releases=json.loads(subprocess.check_output(['gh','api',f'repos/{a.repo}/releases?per_page=100']))
release=next(x for x in releases if x['tag_name']==a.tag)
remote={x['name']:x for x in release['assets']}
verified=0; pending=[]
for path in sorted(a.assets.iterdir()):
    if not path.is_file(): continue
    asset=remote.get(path.name)
    if asset is None or asset['state']!='uploaded': pending.append(path.name); continue
    h=hashlib.sha256()
    with path.open('rb') as f:
        while data:=f.read(8*1024*1024): h.update(data)
    assert asset['size']==path.stat().st_size, f'Size mismatch: {path.name}'
    assert asset.get('digest')=='sha256:'+h.hexdigest(), f'Digest mismatch: {path.name}'
    verified+=1
print(f'GITHUB_DIGESTS_VERIFIED={verified}; PENDING={len(pending)}')
for name in pending: print('PENDING',name)
if pending: raise SystemExit(2)
print('ALL_RELEASE_ASSETS_VERIFIED')
