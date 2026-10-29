#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Download and flash the full Fedora system from an SM-T860 TWRP root shell."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request

TAG='v2026.10.29-gpu18'
BASE=f'https://github.com/starlight4you/t860-fedora/releases/download/{TAG}/'
HERE=Path(__file__).resolve().parent

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while data:=f.read(8*1024*1024): h.update(data)
    return h.hexdigest()

def download(name,expected=None):
    if Path(name).name!=name or not name:
        raise RuntimeError('Invalid download filename in manifest')
    target=HERE/name
    if target.exists() and (expected is None or sha(target)==expected): return target
    print(f'Downloading {name}',flush=True)
    partial=target.with_name(target.name+'.partial')
    try:
        request=urllib.request.Request(BASE+name,headers={'User-Agent':'t860-fedora-installer'})
        with urllib.request.urlopen(request,timeout=120) as source, partial.open('wb') as out:
            length=int(source.headers.get('Content-Length','0'))
            copied=0; next_report=128*1024*1024
            while data:=source.read(8*1024*1024):
                out.write(data); copied+=len(data)
                if copied>=next_report:
                    progress=f'{100*copied/length:.1f}%' if length else f'{copied//(1024*1024)} MiB'
                    print(f'  {name}: {progress}',flush=True)
                    next_report=copied+128*1024*1024
        if expected and sha(partial)!=expected: raise RuntimeError(f'Checksum mismatch: {name}')
        partial.replace(target)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return target

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--download',action='store_true',help='Download and verify this pinned release, without flashing')
    p.add_argument('--erase-android',action='store_true',help='Replace Android userdata with Fedora after confirmation')
    p.add_argument('--serial',help='ADB serial when more than one device is connected')
    p.add_argument('--check-only',action='store_true',help='Verify all downloads, recovery, stock boot patch and partition sizes; write nothing')
    args=p.parse_args()
    manifest_path=HERE/'manifest.json'
    if args.download or not manifest_path.exists(): download('manifest.json')
    manifest=json.loads(manifest_path.read_text())
    if manifest['release']!=TAG or manifest['device']!='SM-T860': raise RuntimeError('Unexpected release manifest')
    assets=manifest['assets']
    for asset in assets:
        file=HERE/asset['name']
        if args.download or not file.exists(): download(asset['name'],asset['sha256'])
        if file.stat().st_size!=asset['bytes'] or sha(file)!=asset['sha256']:
            raise RuntimeError(f"Damaged download: {asset['name']}")
        print(f"Verified {asset['name']}",flush=True)
    if not args.erase_android and not args.check_only:
        print('Download verification complete. Boot TWRP, then run: python3 flash.py --erase-android')
        return
    adb_path=shutil.which('adb')
    if adb_path is None: raise RuntimeError('Install official Android SDK Platform-Tools and add adb to PATH')
    adb=[adb_path]+(['-s',args.serial] if args.serial else [])
    def run(*cmd,capture=False):
        return subprocess.run(adb+list(cmd),check=True,text=True,stdout=subprocess.PIPE if capture else None)
    version=run('shell','getprop','ro.twrp.version',capture=True).stdout.strip()
    model=run('shell','getprop','ro.product.model',capture=True).stdout.strip()
    device=run('shell','getprop','ro.product.device',capture=True).stdout.strip()
    if not version or (model!='SM-T860' and device!='gts6lwifi') or model.startswith(('SM-T865','SM-T867')):
        raise RuntimeError('Connect an SM-T860 in TWRP, not Android or Download Mode')
    if run('shell','id','-u',capture=True).stdout.strip()!='0': raise RuntimeError('A TWRP root shell is required')
    print(f'Device: {model} / {device}; TWRP {version}')
    if args.erase_android and not args.check_only:
        print('This ERASES Android apps and data. boot/cache/vbmeta are replaced; recovery and firmware partitions are retained.')
        if input('Type SM-T860 ERASE to continue: ').strip()!='SM-T860 ERASE':
            raise RuntimeError('Cancelled before writing')
    bundle=HERE/manifest['installer_bundle']
    run('push',str(bundle),'/tmp/t860-fedora-installer.tar.gz')
    run('shell','mkdir -p /tmp/t860-fedora-installer && tar -xzf /tmp/t860-fedora-installer.tar.gz -C /tmp/t860-fedora-installer && chmod 755 /tmp/t860-fedora-installer/busybox /tmp/t860-fedora-installer/magiskboot /tmp/t860-fedora-installer/patcher /tmp/t860-fedora-installer/bootverify && mkdir -p /tmp/t860-fedora-installer/bin && /tmp/t860-fedora-installer/busybox --install -s /tmp/t860-fedora-installer/bin')
    remote=['shell','-T','/tmp/t860-fedora-installer/busybox','sh','/tmp/t860-fedora-installer/recovery-install.sh']
    run(*remote,'prepare')
    backup=HERE/'android-backup'
    if backup.exists(): backup=HERE/f'android-backup-{int(time.time())}'
    run('pull','/tmp/t860-fedora-installer/android-backup',str(backup))
    print(f'Original boot/cache/vbmeta backed up to {backup}',flush=True)
    if args.check_only:
        print('CHECK_ONLY_PASS: no tablet partitions were written.')
        return
    pieces=[HERE/name for name in manifest['rootfs_parts']]
    total=sum(x.stat().st_size for x in pieces); sent=0; next_report=0
    proc=subprocess.Popen(adb+remote+['write-root'],stdin=subprocess.PIPE)
    try:
        for piece in pieces:
            with piece.open('rb') as src:
                while data:=src.read(4*1024*1024):
                    proc.stdin.write(data); sent+=len(data)
                    if sent>=next_report:
                        print(f'Image transfer: {100*sent/total:.1f}%',flush=True)
                        next_report=sent+128*1024*1024
        proc.stdin.close()
        if proc.wait()!=0: raise RuntimeError('System image write failed. Keep TWRP open; do not reboot.')
    except BaseException:
        if proc.poll() is None: proc.terminate(); proc.wait()
        raise
    run(*remote,'finish')
    print('Installation complete. Default desktop credentials: fedora / fedora. Change the password; SSH is disabled.')
    print('First boot grows the filesystem. Android restoration backups are on this PC and in /var/lib/tabs6/android-backup.')
    run('reboot')

if __name__=='__main__':
    try: main()
    except (Exception,KeyboardInterrupt) as error:
        print(f'ERROR: {error}',file=sys.stderr)
        sys.exit(1)
