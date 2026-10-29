#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Sanitize a private staging COPY; never point this at a running rootfs."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess

p=argparse.ArgumentParser()
p.add_argument('--root', type=Path, required=True)
p.add_argument('--project', type=Path, required=True)
p.add_argument('--original-project', type=Path, required=True)
a=p.parse_args()
r=a.root.resolve(); project=a.project.resolve(); original=a.original_project.resolve()
assert str(r).startswith('/var/tmp/t860-release/'), 'Only the isolated release staging tree is allowed'
assert (r/'etc/fedora-release').exists()

def remove(rel):
    path=r/rel.lstrip('/')
    if path.is_symlink() or path.is_file(): path.unlink()
    elif path.is_dir(): shutil.rmtree(path)

def write(rel,text,mode=0o644):
    path=r/rel.lstrip('/')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text); path.chmod(mode)

def copy(src,rel,mode=None):
    target=r/rel.lstrip('/')
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,target)
    if mode is not None: target.chmod(mode)

def chroot(*cmd,**kw):
    return subprocess.run(['chroot',str(r),*cmd],check=True,**kw)

# Remove identities, credentials, all home directories and persistent runtime data.
for rel in ['root','home','boot','tmp','var/tmp','var/log','var/cache',
            'var/lib/NetworkManager','var/lib/bluetooth','var/lib/AccountsService',
            'var/lib/tabs6','var/lib/sss','var/lib/sddm','var/lib/systemd',
            'var/lib/tqftpserv','var/lib/dnf','var/lib/private','var/lib/waydroid','var/lib/tailscale',
            'etc/NetworkManager/system-connections','etc/tabs6-bt-address',
            'etc/machine-info','etc/adjtime','etc/ssh/sshd_config.d/20-t860.conf']:
    remove(rel)
for pattern in ['etc/ssh/ssh_host_*','etc/*shadow-','etc/gshadow-',
                'etc/pki/tls/private/*','etc/ssl/private/*','var/lib/chrony/*',
                'var/spool/mail/*','var/spool/cron/*']:
    for path in r.glob(pattern): remove(str(path.relative_to(r)))
for rel in ['root','home/fedora','boot','tmp','var/tmp','var/log','var/cache','var/lib/tabs6',
            'var/lib/sddm','var/lib/tqftpserv','etc/NetworkManager/system-connections']:
    (r/rel).mkdir(parents=True,exist_ok=True)
(r/'tmp').chmod(0o1777); (r/'var/tmp').chmod(0o1777); (r/'root').chmod(0o700)
write('/etc/machine-id','')
dbus=r/'var/lib/dbus/machine-id'
if dbus.exists() or dbus.is_symlink(): dbus.unlink()
dbus.parent.mkdir(parents=True,exist_ok=True); dbus.symlink_to('/etc/machine-id')
write('/etc/hostname','t860-fedora\n')
write('/etc/fstab','/dev/sda30 / ext4 defaults,noatime 0 1\n')
write('/etc/crypttab','')
write('/etc/tabs6-usb.conf','DEV_MAC=02:86:00:00:00:01\nHOST_MAC=02:86:00:00:00:02\n',0o600)
write('/etc/NetworkManager/system-connections/tabs6-usb.nmconnection',
      '[connection]\nid=tabs6-usb\ntype=ethernet\ninterface-name=usb0\nautoconnect=true\n'
      '[ethernet]\n[ipv4]\nmethod=manual\naddress1=169.254.86.2/16\nnever-default=true\n'
      '[ipv6]\nmethod=link-local\n',0o600)
write('/etc/ssh/sshd_config.d/20-t860.conf','PermitRootLogin no\nPasswordAuthentication no\nPubkeyAuthentication yes\n')
write('/etc/systemd/system/serial-getty@ttyGS0.service.d/override.conf',
      '[Service]\nExecStart=\nExecStart=-/sbin/agetty --noclear %I 115200 vt100\n')
chroot('usermod','--password','!','root')
chroot('chpasswd',input='fedora:fedora\n',text=True)
write('/home/fedora/.config/kwinrc','[Wayland]\nInputMethod=/usr/share/applications/com.github.maliit.keyboard.desktop\nVirtualKeyboardEnabled=true\n')
write('/home/fedora/.config/kscreenlockerrc','[Daemon]\nAutolock=false\nLockOnResume=false\n')
for desktop in ['org.kde.plasma-welcome.desktop','imsettings-start.desktop','sealertauto.desktop']:
    write('/home/fedora/.config/autostart/'+desktop,'[Desktop Entry]\nHidden=true\n')
chroot('chown','-R','fedora:fedora','/home/fedora')

# The old image carried private Samsung files. Delete every file that was imported,
# not just firmware directory names, then construct a NEW filesystem later.
fw=r/'usr/lib/firmware'
for path in (original/'private/firmware/vendor').iterdir():
    if path.is_file(): remove('/usr/lib/firmware/'+path.name)
for rel in ['usr/lib/firmware/qcom/sm8150/gts6l','usr/share/qcom/sm8150/Samsung/gts6lwifi',
            'usr/lib/firmware/qcom/sm8150/a640_gmu.bin','usr/lib/firmware/qcom/a640_gmu.bin',
            'usr/lib/firmware/qcom/a630_sqe.fw']:
    remove(rel)
for pattern in ['usr/lib/firmware/ath10k/WCN3990/hw1.0/board-2.bin*',
                'usr/lib/firmware/qca/crbtfw0*.tlv','usr/lib/firmware/qca/crbtfw2*.tlv',
                'usr/lib/firmware/qca/crnv0*.bin','usr/lib/firmware/qca/crnv2*.bin']:
    for path in r.glob(pattern): remove(str(path.relative_to(r)))

# Only the verified release's modules are shipped.
remove('usr/lib/modules')
(r/'usr/lib/modules').mkdir(parents=True)
subprocess.run(['tar','-xzf',str(original/'build/gpu18-lts/modules.tar.gz'),'-C',str(r)],check=True)
chroot('depmod','-a','6.18.59-t860-gpu18')
for name in ['tabs6-charge.sh','tabs6-powerkeyd.py','tabs6-idled.py','tabs6-desktop-patches.py',
             'tabs6-bt-addr.sh','tabs6-screenshot','tabs6-screenshot-tray.py','usb-role','tabs6-kernel']:
    src=original/'tools'/name
    if src.exists(): copy(src,'/usr/local/bin/'+name,0o755)
for path in (project/'rootfs/maliit').iterdir():
    dest=('/usr/share/glib-2.0/schemas/' if path.suffix=='.override' else '/usr/local/share/tabs6/maliit/')+path.name
    copy(path,dest)
copy(project/'rootfs/systemd/sddm-vt-fix.conf','/etc/systemd/system/sddm.service.d/vt-fix.conf')
for name in ['tabs6-autorotate','tabs6-rotate-tray.py']:
    copy(project/'userspace/sensors'/name,'/usr/local/bin/'+name,0o755)
for name,dest in [
    ('iio-sensor-proxy-override.conf','/etc/systemd/system/iio-sensor-proxy.service.d/override.conf'),
    ('hexagonrpcd-sdsp-override.conf','/etc/systemd/system/hexagonrpcd-sdsp.service.d/override.conf'),
    ('tabs6-sensors-recover.service','/etc/systemd/system/tabs6-sensors-recover.service'),
    ('tabs6-autorotate-map.conf','/etc/systemd/user/tabs6-autorotate.service.d/map.conf')]:
    copy(project/'userspace/sensors'/name,dest)
for name in ['first-boot.py','import-firmware.sh']:
    copy(project/'installer'/name,'/usr/local/libexec/tabs6/'+name,0o755)
copy(project/'tools/ath10k-bdencoder','/usr/local/libexec/tabs6/ath10k-bdencoder',0o755)
write('/etc/systemd/system/tabs6-first-boot.service',
      '[Unit]\nDescription=Initialize Tab S6 device-local state\nAfter=local-fs.target\n'
      'Before=tabs6-usb-gadget.service tabs6-wifi.service hexagonrpcd-sdsp.service iio-sensor-proxy.service sddm.service\n'
      '[Service]\nType=oneshot\nExecStart=/usr/local/libexec/tabs6/first-boot.py\nRemainAfterExit=yes\n'
      '[Install]\nWantedBy=multi-user.target\n')
for name in ['tabs6-usb-gadget','tabs6-wifi','hexagonrpcd-sdsp','iio-sensor-proxy','sddm']:
    write(f'/etc/systemd/system/{name}.service.d/release-init.conf',
          '[Unit]\nRequires=tabs6-first-boot.service\nAfter=tabs6-first-boot.service\n')
subprocess.run(['systemctl','--root',str(r),'enable','tabs6-first-boot.service'],check=True)
subprocess.run(['systemctl','--root',str(r),'disable','sshd.service'],check=True)
chroot('glib-compile-schemas','/usr/share/glib-2.0/schemas')
chroot('ldconfig')
assert hashlib.sha256((r/'usr/local/lib64/libssc.so.2').read_bytes()).hexdigest()=='3e1cb146db36e633d223b2b8cae01d91c94bf5e10fd050f53af41d1962a087b0'
write('/etc/t860-release','Fedora 44 KDE / SM-T860 / GPU18 / 2026-10-29\n')
manifest=subprocess.check_output(['chroot',str(r),'rpm','-qa','--qf','%{NAME}\t%{EPOCHNUM}:%{VERSION}-%{RELEASE}\t%{ARCH}\t%{SOURCERPM}\n'],text=True)
write('/usr/share/t860-release/packages.tsv',''.join(sorted(manifest.splitlines(True))))
for path in r.glob('etc/*shadow-'): remove(str(path.relative_to(r)))
for path in r.glob('usr/lib/sysimage/libdnf5/*history*'): remove(str(path.relative_to(r)))
print('SANITIZED_STAGING_ROOT_READY; export to a new filesystem before distribution')
