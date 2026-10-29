#!/bin/bash
# Build the Fedora-matched SDDM daemon with VT and autologin reuse fixes.
set -euo pipefail
cd /workspace
src=/workspace/build/sddm-fedora-patched
rpm_sources=/workspace/build/sddm-fedora-source
if [ ! -d "$src" ]; then
    mkdir -p "$src"
    tar -xzf "$rpm_sources/sddm-0.21.0.tar.gz" --strip-components=1 -C "$src"
    for patch_name in \
        228778c2b4b7e26db1e1d69fe484ed75c5791c3a.patch \
        sddm-PR1876.patch \
        sddm-0.21.0-fix-restart-greeter-when-helper-is-in-a-wrong-state.patch \
        0001-Delay-for-logind-and-fallback-to-seat0.patch \
        sddm-0.20.0-fedora_config.patch \
        sddm-0.18.0-environment_file.patch \
        sddm-rpmostree-tmpfiles-hack.patch \
        sddm-0.21.0-qt6greeter.patch; do
        patch -d "$src" -p1 < "$rpm_sources/$patch_name"
    done
    patch -d "$src" -p1 < scripts/sddm-vt-name.patch
fi
if ! grep -q 'session.service() == QLatin1String("sddm-autologin")' "$src/src/daemon/Display.cpp"; then
    patch -d "$src" -p1 < scripts/sddm-autologin-reuse.patch
fi
cmake -S "$src" -B build/sddm-compile \
    -DCMAKE_INSTALL_PREFIX=/usr -DCMAKE_INSTALL_LIBDIR=lib64 \
    -DCMAKE_INSTALL_LIBEXECDIR=libexec -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_WITH_QT6=ON -DBUILD_MAN_PAGES=OFF -DENABLE_JOURNALD=ON \
    -DSESSION_COMMAND=/etc/X11/xinit/Xsession \
    -DWAYLAND_SESSION_COMMAND=/etc/sddm/wayland-session
cmake --build build/sddm-compile --target sddm -j8
install -m755 build/sddm-compile/src/daemon/sddm build/sddm-vt-fixed
strip build/sddm-vt-fixed
sha256sum build/sddm-vt-fixed
