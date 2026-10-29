#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Sourced in recovery; ROOT is the mounted new Fedora filesystem.
import_device_firmware() {
    IMPORT="$WORK/import"
    mkdir -p "$IMPORT" "$ROOT/etc"
    for name in vendor apnhlos modem persist efs; do
        mkdir -p "$IMPORT/$name"
        case "$name" in apnhlos|modem) opts=ro; type=vfat ;; *) opts=ro,noload; type=ext4 ;; esac
        mount -t "$type" -o "$opts" "$(part "$name")" "$IMPORT/$name" || fail "Cannot read $name"
    done
    FW="$ROOT/usr/lib/firmware"
    BOARD="$FW/qcom/sm8150/gts6l"
    mkdir -p "$BOARD" "$FW/qca" "$FW/ath10k/WCN3990/hw1.0" "$ROOT/var/lib/tabs6/vendor-import"
    for source in "$IMPORT/apnhlos/image" "$IMPORT/modem/image"; do
        for f in "$source"/*.mdt "$source"/*.b[0-9][0-9] "$source"/*.jsn; do
            [ ! -f "$f" ] || cp "$f" "$BOARD/"
        done
    done
    vendor_fw="$IMPORT/vendor/firmware"
    for name in a630_sqe.fw a640_gmu.bin wlanmdsp.mbn crbtfw21.tlv crnv21.bin cs35l41-dsp1-spk-prot-calib.bin cs35l41-dsp1-spk-prot.bin cs35l41-dsp1-spk-prot.wmfw cs48l32-dsp1-ctrl.bin cs48l32-dsp1-ctrl.wmfw; do
        source=$(find "$vendor_fw" -type f -name "$name" | head -n 1)
        [ -z "$source" ] || { cp "$source" "$FW/$name"; cp "$source" "$BOARD/$name"; }
    done
    for name in a630_sqe.fw a640_gmu.bin; do
        [ -f "$FW/$name" ] || fail "Required vendor firmware missing: $name"
        cp "$FW/$name" "$FW/qcom/$name"
    done
    cp "$FW/a640_gmu.bin" "$FW/qcom/sm8150/a640_gmu.bin"
    for name in crbtfw21.tlv crnv21.bin; do
        [ -f "$FW/$name" ] || fail "Bluetooth firmware missing: $name"
        cp "$FW/$name" "$FW/qca/$name"
    done
    cp "$FW/qca/crbtfw21.tlv" "$FW/qca/crbtfw01.tlv"
    cp "$FW/qca/crnv21.bin" "$FW/qca/crnv01.bin"
    bdwlan=$(find "$vendor_fw" -type f -name bdwlan.bin | head -n 1)
    [ -n "$bdwlan" ] || fail 'Samsung Wi-Fi board data missing.'
    cp "$bdwlan" "$ROOT/var/lib/tabs6/vendor-import/bdwlan.bin"
    QCOM="$ROOT/usr/share/qcom/sm8150/Samsung/gts6lwifi"
    mkdir -p "$QCOM/sensors/config" "$QCOM/sensors/registry" "$QCOM/socinfo" "$QCOM/dsp"
    [ -d "$IMPORT/vendor/etc/sensors/config" ] || fail 'Sensor config missing.'
    cp -a "$IMPORT/vendor/etc/sensors/config/." "$QCOM/sensors/config/"
    [ -d "$IMPORT/persist/sensors/registry/registry" ] || fail 'Sensor calibration missing.'
    cp -a "$IMPORT/persist/sensors/registry/registry/." "$QCOM/sensors/registry/"
    cp "$IMPORT/vendor/etc/sensors/sns_reg_config" "$QCOM/sensors/sns_reg.conf"
    [ ! -d "$IMPORT/vendor/dsp" ] || cp -a "$IMPORT/vendor/dsp/." "$QCOM/dsp/"
    [ -r "$IMPORT/efs/bluetooth/bt_addr" ] || fail 'Bluetooth address missing from EFS.'
    tr -d '\000\r\n ' < "$IMPORT/efs/bluetooth/bt_addr" > "$ROOT/etc/tabs6-bt-address"
    chmod 600 "$ROOT/etc/tabs6-bt-address"
    chmod -R a+rX "$QCOM"
    for name in a640_zap.mdt adsp.mdt slpi.mdt modem.mdt; do
        [ -f "$BOARD/$name" ] || fail "Required DSP/GPU firmware missing: $name"
    done
    for name in efs persist modem apnhlos vendor; do umount "$IMPORT/$name"; done
    touch "$ROOT/var/lib/tabs6/vendor-import/complete"
}
