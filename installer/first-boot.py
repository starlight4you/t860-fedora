#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
"""Generate per-install state and Wi-Fi board container without shipping identity."""
import os
import json
from pathlib import Path
import secrets
import shutil
import subprocess

state = Path('/var/lib/tabs6')
state.mkdir(parents=True, exist_ok=True)
assert Path('/var/lib/tabs6/vendor-import/complete').exists(), 'Recovery firmware import did not finish'
if not (state / 'release-initialized').exists():
    mapping=state/'vendor-import/board-map.json'
    mapping.write_text(json.dumps([{'names':['bus=snoc,qmi-board-id=ff,qmi-chip-id=30224',
                                           'bus=snoc,qmi-board-id=ff'],
                                   'data':'/var/lib/tabs6/vendor-import/bdwlan.bin'}]))
    subprocess.run(['/usr/local/libexec/tabs6/ath10k-bdencoder',
                    '-o', '/usr/lib/firmware/ath10k/WCN3990/hw1.0/board-2.bin',
                    '-c', str(mapping)], check=True)
    def mac():
        return ':'.join(f'{b:02x}' for b in bytes([2]) + secrets.token_bytes(5))
    p=Path('/etc/tabs6-usb.conf')
    p.write_text(f'DEV_MAC={mac()}\nHOST_MAC={mac()}\n')
    p.chmod(0o600)
    subprocess.run(['ssh-keygen', '-A'], check=True)
    (state / 'release-initialized').touch()
soc=Path('/usr/share/qcom/sm8150/Samsung/gts6lwifi/socinfo')
soc.mkdir(parents=True, exist_ok=True)
for p in Path('/sys/devices/soc0').glob('*'):
    if p.is_file():
        try:
            (soc/p.name).write_bytes(p.read_bytes())
            (soc/p.name).chmod(0o644)
        except OSError:
            pass
