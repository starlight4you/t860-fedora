#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Assemble a full system release; run in the isolated Linux builder."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import tarfile

p=argparse.ArgumentParser()
p.add_argument('--project',type=Path,required=True)
p.add_argument('--stage',type=Path,default=Path('/var/tmp/t860-release'))
a=p.parse_args(); stage=a.stage; project=a.project
tag='v2026.10.29-gpu18'
out=stage/'assets'; out.mkdir(exist_ok=True)
bundle=stage/'installer-bundle'; bundle.mkdir(exist_ok=True)
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while data:=f.read(8*1024*1024): h.update(data)
    return h.hexdigest()
assert sha(Path('/workspace/build/gpu18-lts/Image'))=='98e0c5498deee45b31a58ba121bc77b4f19a3fc5af316179e749828f4fbe7640'
assert sha(stage/'SM8150_EFI_NOSB.fd')=='119d01594436f83658bb6200c0295f9532b872e20d4130d9069a6c4c936bc394'
files={
    'busybox':stage/'source/busybox-1.37.0/busybox',
    'patcher':stage/'patcher', 'bootverify':stage/'bootverify',
    'magiskboot':Path('/workspace/build/magiskboot'),
    'SM8150_EFI_NOSB.fd':stage/'SM8150_EFI_NOSB.fd',
    'TabS6.bin':Path('/workspace/build/TabS6.bin'),
    'DualBoot.Sm8150.cfg':project/'third_party/DualBootKernelPatcher/Config/DualBoot.Sm8150.cfg',
    'recovery-install.sh':project/'installer/recovery-install.sh',
    'cache.img.gz':stage/'payload/cache.img.gz',
}
for name,path in files.items(): shutil.copy2(path,bundle/name)
shutil.copytree(project/'licenses',bundle/'licenses',dirs_exist_ok=True)
# Unsigned standalone AVB vbmeta header: algorithm NONE, verification/hashtree disabled.
vbmeta=bytearray(4096)
vbmeta[:4]=b'AVB0'
struct.pack_into('>II',vbmeta,4,1,0)
struct.pack_into('>I',vbmeta,120,3)
vbmeta[128:128+len(b'avbtool 1.3.0')]=b'avbtool 1.3.0'
(bundle/'vbmeta.img').write_bytes(vbmeta)
raw_sha=sha(stage/'fedora.img'); cache_sha=sha(stage/'cache.img')
(bundle/'manifest.env').write_text(f'ROOTFS_BYTES={ (stage/"fedora.img").stat().st_size }\nROOTFS_RAW_SHA256={raw_sha}\nCACHE_RAW_SHA256={cache_sha}\n')
(bundle/'SHA256SUMS').write_text(''.join(f'{sha(x)}  {x.relative_to(bundle).as_posix()}\n' for x in sorted(bundle.rglob('*')) if x.is_file() and x.name!='SHA256SUMS'))
bundle_name='T860-Fedora44-GPU18-installer.tar.gz'
with tarfile.open(out/bundle_name,'w:gz',compresslevel=1) as tar:
    for path in sorted(bundle.iterdir()): tar.add(path,arcname=path.name)
parts=[]
with (stage/'payload/rootfs.img.gz').open('rb') as src:
    index=0
    while True:
        chunk=src.read(8*1024*1024)
        if not chunk: break
        name=f'T860-Fedora44-GPU18-rootfs.img.gz.part{index:03d}'
        with (out/name).open('wb') as dst:
            size=0
            while chunk:
                dst.write(chunk); size+=len(chunk)
                remaining=1_800_000_000-size
                if remaining<=0: break
                chunk=src.read(min(8*1024*1024,remaining))
        parts.append(name); index+=1
assets=[{'name':x.name,'bytes':x.stat().st_size,'sha256':sha(x)} for x in [out/bundle_name]+[out/n for n in parts]]
manifest={'format':'t860-recovery-stream-v1','release':tag,'device':'SM-T860','kernel':'6.18.59-t860-gpu18',
          'prerelease':True,'rootfs_bytes':(stage/'fedora.img').stat().st_size,'rootfs_raw_sha256':raw_sha,
          'rootfs_gzip_sha256':sha(stage/'payload/rootfs.img.gz'),'installer_bundle':bundle_name,
          'rootfs_parts':parts,'assets':assets}
(out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
for name in ['flash.py','flash-macos.command','flash-windows.cmd','README.md']:
    shutil.copy2(project/name,out/name)
for path in [stage/'source/linux-6.18.59-t860-gpu18-source.tar.xz',stage/'source/busybox-1.37.0.tar.bz2',stage/'source/t860-custom-userspace-source.tar.xz']:
    shutil.copy2(path,out/path.name)
shutil.copy2(stage/'packages.tsv',out/'packages.tsv')
(out/'SHA256SUMS').write_text(''.join(f'{sha(x)}  {x.name}\n' for x in sorted(out.iterdir()) if x.is_file() and x.name!='SHA256SUMS'))
print(json.dumps(manifest,indent=2))
print('RELEASE_ASSETS_READY',out)
