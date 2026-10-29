#!/usr/bin/env python3
"""Prepare a clean Linux 6.18.59 tree without changing the 6.12 fallback.

This first prepares the existing simpledrm display path on the newer kernel.
Native DPU/panel enablement is a separate device-tree target and test entry.
Run once on a freshly extracted tree; unexpected source changes are errors.
"""
from pathlib import Path
import argparse
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--tree', type=Path, default=ROOT / 'build/linux-6.18.59')
parser.add_argument('--config', type=Path,
                    default=ROOT / 'kernel/config/gts6lwifi_defconfig-full')
args = parser.parse_args()
tree = args.tree.resolve()
if (tree / '.tabs6-prepared').exists():
    parser.error('tree already prepared; use a fresh upstream extraction')
if 'VERSION = 6\nPATCHLEVEL = 18\n' not in (tree / 'Makefile').read_text():
    parser.error('expected an upstream Linux 6.18 tree')

patches = []
for name in ['dwc3-allow-userspace-role-control',
             'mfd-qcom-spmi-pmic-tolerate-denied-revid',
             'msm-poweroff-release-ps-hold-early',
             'qcom-pon-ps-hold-shutdown-and-smpl',
             'cs48l32-accept-cs48l33',
             'sm8250-sndcard-sm8150-secondary-tdm',
             'simpledrm-gts6lwifi-native-argb',
             'msm-gts6lwifi-render-only',
             'dsi-ana38401-defer-hs-clock',
             'msm-gts6lwifi-boot-framebuffer-map',
             'fastrpc-gts6lwifi-sdsp-shared-state']:
    patch = ROOT / f'kernel/patches/linux-6.18/{name}.patch'
    if not patch.exists():
        patch = ROOT / f'kernel/patches/{name}.patch'
    data = patch.read_text()
    if name.startswith('mfd-'):
        data = re.sub(r'^--- drivers/.*$', '--- a/drivers/mfd/qcom-spmi-pmic.c', data, flags=re.M)
        data = re.sub(r'^\+\+\+ drivers/.*$', '+++ b/drivers/mfd/qcom-spmi-pmic.c', data, flags=re.M)
    subprocess.run(['patch', '-p1', '--dry-run', '--batch', '--forward'],
                   input=data, text=True, cwd=tree, check=True)
    patches.append(data)

for data in patches:
    subprocess.run(['patch', '-p1', '--batch', '--forward'], input=data,
                   text=True, cwd=tree, check=True)

for name, dest, config in [
    ('fts1ba90a', 'drivers/input/touchscreen', 'TOUCHSCREEN_FTS1BA90A'),
    ('sm5705_fuelgauge', 'drivers/power/supply', 'BATTERY_SM5705'),
]:
    shutil.copy2(ROOT / f'kernel/drivers/{name}.c', tree / dest)
    with (tree / dest / 'Makefile').open('a') as f:
        f.write(f'\nobj-$(CONFIG_{config}) += {name}.o\n')
    with (tree / dest / 'Kconfig').open('a') as f:
        f.write(f'\nconfig {config}\n\ttristate "Tab S6 {name}"\n\tdepends on I2C\n')

shutil.copy2(ROOT / 'kernel/dts/sm8150-samsung-gts6lwifi.dts',
             tree / 'arch/arm64/boot/dts/qcom/')
with (tree / 'arch/arm64/boot/dts/qcom/Makefile').open('a') as f:
    f.write('\ndtb-$(CONFIG_ARCH_QCOM) += sm8150-samsung-gts6lwifi.dtb\n')
shutil.copy2(ROOT / 'kernel/dts/sm8150-samsung-gts6lwifi-native.dts',
             tree / 'arch/arm64/boot/dts/qcom/')
with (tree / 'arch/arm64/boot/dts/qcom/Makefile').open('a') as f:
    f.write('dtb-$(CONFIG_ARCH_QCOM) += sm8150-samsung-gts6lwifi-native.dtb\n')
shutil.copy2(ROOT / 'kernel/drivers/panel-samsung-ana38401.c',
             tree / 'drivers/gpu/drm/panel/')
with (tree / 'drivers/gpu/drm/panel/Makefile').open('a') as f:
    f.write('\nobj-$(CONFIG_DRM_PANEL_SAMSUNG_ANA38401) += panel-samsung-ana38401.o\n')
with (tree / 'drivers/gpu/drm/panel/Kconfig').open('a') as f:
    f.write('\nconfig DRM_PANEL_SAMSUNG_ANA38401\n'
            '\ttristate "Experimental Samsung ANA38401 AMSA05RB06 panel"\n'
            '\tdepends on OF && DRM_BRIDGE && DRM_MIPI_DSI\n'
            '\thelp\n\t  Experimental bonded command-mode Tab S6 panel.\n'
            '\t  Requires the native DT and the deferred HS clock patch.\n')

# Samsung's firmware leaves these UFS/USB halt status bits unreliable.
p = tree / 'drivers/clk/qcom/gcc-sm8150.c'
text = p.read_text()
for clock in ['ufs_phy_axi', 'ufs_phy_ahb', 'ufs_phy_unipro_core',
              'ufs_phy_ice_core', 'ufs_phy_phy_aux', 'aggre_ufs_phy_axi',
              'usb30_prim_master', 'usb30_prim_mock_utmi', 'usb3_prim_phy_aux',
              'usb3_prim_phy_com_aux', 'usb3_prim_phy_pipe',
              'aggre_usb3_prim_axi', 'cfg_noc_usb3_prim_axi']:
    pattern = r'(static struct clk_branch gcc_' + clock + r'_clk = \{)(.*?)(\n\};)'
    def fix(m):
        body = m[2]
        if '.halt_check' in body:
            body = re.sub(r'\.halt_check = \w+,', '.halt_check = BRANCH_HALT_SKIP,', body)
        else:
            body = '\n\t.halt_check = BRANCH_HALT_SKIP,' + body
        return m[1] + body + m[3]
    text, count = re.subn(pattern, fix, text, flags=re.S)
    if count != 1:
        raise RuntimeError(f'expected one clock {clock}, found {count}')
p.write_text(text)

# Do not replace the upstream MMU test or add dummy platform devices. The
# newer MSM driver has a managed GPU-only probe path for the fallback DT.
shutil.copy2(args.config, tree / '.config')
# Samsung's verified SDSP ownership record must live for the entire boot.
subprocess.run(['scripts/config', '--enable', 'RPMSG', '--enable', 'QCOM_FASTRPC'],
               cwd=tree, check=True)
(tree / '.tabs6-prepared').write_text('6.18 fallback display preparation\n')
print('Prepared; use a distinct LOCALVERSION and matching module directory.')
