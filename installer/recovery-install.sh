#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Invoked by flash.py inside TWRP. Large image data is streamed from the PC.
set -eu
set -o pipefail
WORK=/tmp/t860-fedora-installer
export PATH="$WORK/bin:/sbin:/system/bin:/vendor/bin"
export ROOT="$WORK/root" WORK
fail() { echo "ERROR: $*" >&2; exit 1; }
hash() { sha256sum | cut -d ' ' -f 1; }
part() {
    for d in /dev/block/by-name /dev/block/bootdevice/by-name /dev/block/platform/soc/*/by-name; do
        if [ -b "$d/$1" ]; then readlink -f "$d/$1"; return; fi
    done
    fail "Partition missing: $1"
}
unmount_partition() {
    dev="$1"
    for point in /sdcard /data/media /data /cache; do
        if mountpoint -q "$point"; then
            source=$(awk -v p="$point" '$2==p {print $1}' /proc/mounts | head -n 1)
            if [ "$(readlink -f "$source")" = "$dev" ] || { [ "$dev" = "$USERDATA" ] && [ "$point" != /cache ]; }; then
                umount "$point" || fail "Cannot unmount $point. Disable MTP in recovery."
            fi
        fi
    done
    while read -r source point rest; do
        [ "$(readlink -f "$source")" != "$dev" ] || fail "$dev is still mounted at $point"
    done < /proc/mounts
}
cd "$WORK"
. ./manifest.env
BOOT=$(part boot) CACHE=$(part cache) USERDATA=$(part userdata) VBMETA=$(part vbmeta)
case "${1:-}" in
prepare)
    model=$(getprop ro.product.model)
    device=$(getprop ro.product.device)
    case "$model:$device" in SM-T860:*|*:gts6lwifi) ;; *) fail 'Only SM-T860 (gts6lwifi) is supported.' ;; esac
    case "$model" in SM-T865*|SM-T867*) fail 'Cellular models are not supported.' ;; esac
    [ -n "$(getprop ro.twrp.version)" ] || fail 'Boot official TWRP for gts6lwifi first.'
    [ "$(id -u)" = 0 ] || fail 'Recovery root shell required.'
    [ "$(blockdev --getsize64 "$BOOT")" = 67108864 ] || fail 'Unexpected boot partition size.'
    [ "$(blockdev --getsize64 "$CACHE")" = 419430400 ] || fail 'Unexpected cache partition size.'
    [ "$(blockdev --getsize64 "$USERDATA")" -ge "$ROOTFS_BYTES" ] || fail 'userdata is too small.'
    for name in vendor apnhlos modem persist efs; do part "$name" >/dev/null; done
    sha256sum -c SHA256SUMS
    echo 'Backing up boot, cache and vbmeta to recovery RAM...'
    mkdir -p android-backup patch
    dd if="$BOOT" of=android-backup/boot.img bs=1048576
    dd if="$CACHE" of=android-backup/cache.img bs=1048576
    dd if="$VBMETA" of=android-backup/vbmeta.img bs=1048576
    (cd android-backup; sha256sum *.img > SHA256SUMS)
    echo 'Patching the tablet’s own stock boot image...'
    ./bootverify android-backup/boot.img stock
    cd patch
    ../magiskboot unpack ../android-backup/boot.img
    ../patcher kernel ../SM8150_EFI_NOSB.fd patched_kernel ../DualBoot.Sm8150.cfg ../TabS6.bin
    mv patched_kernel kernel
    ../magiskboot repack ../android-backup/boot.img new-boot.img
    ../bootverify new-boot.img uefi
    cd ..
    [ "$(wc -c < vbmeta.img)" -le "$(blockdev --getsize64 "$VBMETA")" ] || fail 'vbmeta is too large.'
    touch prepared
    echo PREPARE_PASS_NO_PARTITIONS_WRITTEN
    ;;
write-root)
    [ -f prepared ] || fail 'Run prepare first.'
    [ ! -f root-written ] || fail 'This session already wrote userdata.'
    unmount_partition "$USERDATA"
    unmount_partition "$CACHE"
    echo 'Writing Fedora. Android userdata is being erased.'
    gunzip -c | dd of="$USERDATA" bs=1048576
    sync
    echo 'Verifying userdata read-back...'
    [ "$(head -c "$ROOTFS_BYTES" "$USERDATA" | hash)" = "$ROOTFS_RAW_SHA256" ] || fail 'userdata verification failed. Do not reboot.'
    mkdir -p "$ROOT"
    mount -t ext4 "$USERDATA" "$ROOT" || fail 'Recovery cannot mount the new ext4 filesystem.'
    mkdir -p "$ROOT/var/lib/tabs6/android-backup"
    cp -a android-backup/. "$ROOT/var/lib/tabs6/android-backup/"
    . "$ROOT/usr/local/libexec/tabs6/import-firmware.sh"
    import_device_firmware
    sync
    umount "$ROOT"
    touch root-written
    echo ROOTFS_WRITE_AND_FIRMWARE_IMPORT_PASS
    ;;
finish)
    [ -f root-written ] || fail 'System image and firmware import must finish first.'
    gunzip -c cache.img.gz | dd of="$CACHE" bs=1048576
    sync
    [ "$(head -c 419430400 "$CACHE" | hash)" = "$CACHE_RAW_SHA256" ] || fail 'cache verification failed. Do not reboot.'
    dd if=vbmeta.img of="$VBMETA" bs=4096
    dd if=patch/new-boot.img of="$BOOT" bs=1048576
    sync
    cmp patch/new-boot.img "$BOOT" || fail 'boot verification failed.'
    [ "$(head -c "$(wc -c < vbmeta.img)" "$VBMETA" | hash)" = "$(hash < vbmeta.img)" ] || fail 'vbmeta verification failed.'
    touch installed
    echo INSTALLATION_COMPLETE
    ;;
*) fail 'Expected prepare, write-root or finish.' ;;
esac
