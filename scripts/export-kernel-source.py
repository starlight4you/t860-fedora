#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Export source-only corresponding kernel source from the verified build tree."""
import argparse
import difflib
import io
from pathlib import Path
import tarfile

p=argparse.ArgumentParser()
p.add_argument('--upstream',type=Path,required=True)
p.add_argument('--tree',type=Path,required=True)
p.add_argument('--config',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--patch',type=Path,required=True)
a=p.parse_args()
prefix='linux-6.18.59'
seen=set(); diffs=[]; changed=[]
extra=['drivers/input/touchscreen/fts1ba90a.c',
       'drivers/power/supply/sm5705_fuelgauge.c',
       'drivers/gpu/drm/panel/panel-samsung-ana38401.c',
       'arch/arm64/boot/dts/qcom/sm8150-samsung-gts6lwifi.dts',
       'arch/arm64/boot/dts/qcom/sm8150-samsung-gts6lwifi-native.dts']
with tarfile.open(a.upstream,'r|xz') as src, tarfile.open(a.output,'w:xz',preset=3) as out:
    for info in src:
        rel=Path(info.name).relative_to(prefix).as_posix()
        seen.add(rel)
        info.uid=info.gid=0; info.uname=info.gname='root'
        if not info.isfile():
            out.addfile(info); continue
        old=src.extractfile(info).read()
        path=a.tree/rel
        assert path.is_file(), f'Missing original source: {rel}'
        data=path.read_bytes()
        if data!=old:
            assert b'\0' not in old+data, f'Unexpected changed binary source: {rel}'
            diffs.extend(difflib.unified_diff(old.decode().splitlines(True),data.decode().splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
            changed.append(rel)
        info.size=len(data)
        out.addfile(info,io.BytesIO(data))
    for rel in extra:
        assert rel not in seen, f'Extra file already in upstream: {rel}'
        data=(a.tree/rel).read_bytes()
        diffs.extend(difflib.unified_diff([],data.decode().splitlines(True),fromfile='/dev/null',tofile='b/'+rel))
        changed.append(rel)
        info=tarfile.TarInfo(prefix+'/'+rel); info.mode=0o644; info.size=len(data)
        out.addfile(info,io.BytesIO(data))
    data=a.config.read_bytes()
    info=tarfile.TarInfo(prefix+'/.config'); info.mode=0o644; info.size=len(data)
    out.addfile(info,io.BytesIO(data))
a.patch.write_text(''.join(diffs))
print('SOURCE_CHANGES',len(changed))
for rel in changed: print(rel)
print('SOURCE_ARCHIVE_READY',a.output)
