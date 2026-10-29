#!/bin/bash
set -euo pipefail
TREE="${KERNEL_TREE:-/workspace/build/linux-6.12}"
OUT="${KERNEL_OUTPUT:-/workspace/build}"
INSTALL="${KERNEL_INSTALL_DIR:-/workspace/build/kernel-install}"
cd "$TREE"
scripts/config --set-str LOCALVERSION "${KERNEL_LOCALVERSION:--t860}" --disable LOCALVERSION_AUTO \
  --disable DEBUG_INFO --disable DEBUG_INFO_BTF --disable DEBUG_INFO_DWARF_TOOLCHAIN_DEFAULT \
  --enable DEBUG_INFO_NONE --disable WERROR --disable MODULE_SIG \
  --disable MODULE_COMPRESS_ZSTD --disable MODULE_COMPRESS_XZ --enable MODULE_COMPRESS_NONE \
  --enable TOUCHSCREEN_FTS1BA90A --enable BATTERY_SM5705 \
  --enable TYPEC --enable DRM_AUX_BRIDGE --enable PHY_QCOM_QMP_COMBO \
  --enable POWER_RESET_QCOM_PON --enable POWER_RESET_MSM \
  --disable SERIAL_QCOM_GENI_CONSOLE --disable SERIAL_QCOM_CONSOLE \
  --enable FW_LOADER_COMPRESS --enable FW_LOADER_COMPRESS_XZ --enable FW_LOADER_COMPRESS_ZSTD \
  --module SND_SOC_CS35L41_I2C --module SND_SOC_CS48L32 --module SND_SOC_WM_ADSP --module CS_DSP \
  --module ZRAM --enable ZRAM_BACKEND_ZSTD
# Keep Waydroid's binderfs available with each kernel release. The original
# out-of-tree binder_linux module cannot be reused across kernel releases.
scripts/config --enable ANDROID_BINDER_IPC --enable ANDROID_BINDERFS \
  --set-str ANDROID_BINDER_DEVICES 'binder,hwbinder,vndbinder'
if [ "${KERNEL_DIAGNOSTICS:-0}" = 1 ]; then
  scripts/config --enable FTRACE --enable FUNCTION_TRACER \
    --enable FUNCTION_GRAPH_TRACER --enable DYNAMIC_FTRACE \
    --enable KPROBES --enable KPROBE_EVENTS
fi
if [ "${KERNEL_NATIVE_DTB:-0}" = 1 ]; then
  [ -f drivers/gpu/drm/panel/panel-samsung-ana38401.c ] || {
    echo 'Native DTB requires the prepared LTS panel driver' >&2
    exit 1
  }
  # Keep the board's verified SDSP pool ownership across all channel recoveries.
  scripts/config --enable DRM_PANEL_SAMSUNG_ANA38401 --enable RPMSG --enable QCOM_FASTRPC
fi
# Fedora firewalld uses nftables; the upstream port config only enables xtables.
scripts/config --module NF_TABLES --enable NF_TABLES_INET --enable NF_TABLES_NETDEV \
  --enable NF_CONNTRACK_MARK --enable NF_CONNTRACK_SECMARK \
  --module NFT_CT --module NFT_COUNTER --module NFT_LIMIT --module NFT_LOG \
  --module NFT_REJECT --module NFT_REJECT_INET --module NFT_REJECT_IPV4 \
  --module NFT_REJECT_IPV6 --module NFT_MASQ --module NFT_REDIR --module NFT_NAT \
  --module NFT_CHAIN_NAT --module NFT_FIB --module NFT_FIB_INET \
  --module NFT_FIB_IPV4 --module NFT_FIB_IPV6 --module NFT_COMPAT
make ARCH=arm64 olddefconfig
if [ "${KERNEL_NATIVE_DTB:-0}" = 1 ]; then
  [ "$(scripts/config --state QCOM_FASTRPC)" = y ] || {
    echo 'Native build requires built-in FastRPC for SDSP ownership tracking' >&2
    exit 1
  }
fi
DTBS=(qcom/sm8150-samsung-gts6lwifi.dtb)
if [ "${KERNEL_NATIVE_DTB:-0}" = 1 ]; then
  DTBS+=(qcom/sm8150-samsung-gts6lwifi-native.dtb)
fi
make ARCH=arm64 -j"${KERNEL_JOBS:-8}" Image "${DTBS[@]}" modules
mkdir -p "$INSTALL" "$OUT"
make ARCH=arm64 INSTALL_MOD_PATH="$INSTALL" INSTALL_MOD_STRIP=1 modules_install
cp arch/arm64/boot/Image "$OUT/Image"
cp arch/arm64/boot/dts/qcom/sm8150-samsung-gts6lwifi.dtb "$OUT/gts6.dtb"
if [ "${KERNEL_NATIVE_DTB:-0}" = 1 ]; then
  cp arch/arm64/boot/dts/qcom/sm8150-samsung-gts6lwifi-native.dtb "$OUT/gts6-native.dtb"
fi
cp .config "$OUT/kernel-built.config"
make -s ARCH=arm64 kernelrelease > "$OUT/kernel-release.txt"
sha256sum "$OUT/Image" "$OUT/gts6.dtb"
