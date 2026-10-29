#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
STAGE=/var/tmp/t860-release
PROJECT="$STAGE/project"
[ -f "$STAGE/root/etc/t860-release" ]
python3 "$PROJECT/scripts/audit-release-root.py" --root "$STAGE/root" --original-project /workspace
test ! -e "$STAGE/fedora.img"
truncate -s 18G "$STAGE/fedora.img"
# Recovery uses an older Android kernel: do not require recent ext4 features.
mkfs.ext4 -F -L t860-fedora -m 1 -O ^orphan_file,^metadata_csum_seed "$STAGE/fedora.img"
mkdir -p "$STAGE/fresh"
mount -o loop "$STAGE/fedora.img" "$STAGE/fresh"
rsync -aHAX --numeric-ids "$STAGE/root/" "$STAGE/fresh/"
python3 "$PROJECT/scripts/audit-release-root.py" --root "$STAGE/fresh" --original-project /workspace
cp "$STAGE/fresh/usr/share/t860-release/packages.tsv" "$STAGE/packages.tsv"
sync
umount "$STAGE/fresh"
e2fsck -pf "$STAGE/fedora.img"
# Only discard the temporary staging COPY after the clean export is verified.
umount "$STAGE/root"
rm "$STAGE/rootfs.img"

rm -rf "$STAGE/esp"
mkdir -p "$STAGE/esp/EFI/BOOT" "$STAGE/esp/loader/entries"
cp /workspace/build/BOOTAA64.EFI "$STAGE/esp/EFI/BOOT/BOOTAA64.EFI"
cp /workspace/build/gpu18-lts/Image "$STAGE/esp/Image"
cp /workspace/build/gpu18-lts/gts6-native.dtb "$STAGE/esp/gts6.dtb"
cp /workspace/build/gpu18-lts/gts6.dtb "$STAGE/esp/gts6-safe.dtb"
cat > "$STAGE/esp/loader/loader.conf" <<'EOF'
default fedora.conf
timeout 5
console-mode keep
editor no
reboot-on-error yes
EOF
cat > "$STAGE/esp/loader/entries/fedora.conf" <<'EOF'
title Fedora 44 KDE - SM-T860 GPU18 native display
linux /Image
devicetree /gts6.dtb
options acpi=off efi=novamap fw_devlink=permissive clk_ignore_unused pd_ignore_unused console=tty0 loglevel=6 root=/dev/sda30 rootfstype=ext4 rw rootwait selinux=0
EOF
sed -e 's/GPU18 native display/GPU18 simpledrm fallback/' -e 's/gts6.dtb/gts6-safe.dtb/' \
    "$STAGE/esp/loader/entries/fedora.conf" > "$STAGE/esp/loader/entries/fedora-safe.conf"
truncate -s 419430400 "$STAGE/cache.img"
mkfs.vfat -F 32 -n T860FEDORA "$STAGE/cache.img"
mcopy -i "$STAGE/cache.img" -s "$STAGE/esp/EFI" "$STAGE/esp/loader" ::/
for name in Image gts6.dtb gts6-safe.dtb; do
    mcopy -i "$STAGE/cache.img" "$STAGE/esp/$name" ::/
done
mdir -i "$STAGE/cache.img" ::/
fsck.vfat -n "$STAGE/cache.img"
echo CLEAN_FILESYSTEM_IMAGES_READY
