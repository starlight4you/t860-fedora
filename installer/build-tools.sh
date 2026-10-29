#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
# Native aarch64 Linux; install musl-gcc, kernel headers, make and a C compiler.
set -euo pipefail
BUSYBOX_SOURCE="${1:?path to extracted busybox-1.37.0}"
OUT="${2:?new output directory}"
PROJECT=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$OUT/headers"
OUT=$(cd "$OUT" && pwd)
for name in linux asm asm-generic mtd scsi sound video; do
    [ ! -e "/usr/include/$name" ] || ln -sfn "/usr/include/$name" "$OUT/headers/$name"
done
cp "$PROJECT/installer/busybox.config" "$BUSYBOX_SOURCE/.config"
make -C "$BUSYBOX_SOURCE" CC=musl-gcc EXTRA_CFLAGS="-I$OUT/headers" -j8
cp "$BUSYBOX_SOURCE/busybox" "$OUT/busybox"
musl-gcc -static -O2 "$PROJECT/third_party/DualBootKernelPatcher/patcher.c" \
    "$PROJECT/third_party/DualBootKernelPatcher/utils.c" -o "$OUT/patcher"
musl-gcc -static -Os -Wall -Wextra "$PROJECT/installer/bootverify.c" -o "$OUT/bootverify"
sha256sum "$OUT/busybox" "$OUT/patcher" "$OUT/bootverify"
