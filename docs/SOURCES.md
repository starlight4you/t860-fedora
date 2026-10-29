# Sources and reproducibility

The release contains source-only archives and a package manifest. Private Samsung images, partitions, calibration and device credentials are never uploaded.

- Port base: Bentlybro/gts6l-mainline-linux at `41fa9b85bfb55f9ee671a1dcb8161a5d90a2d542`, GPL-2.0-only.
- Kernel: Linux 6.18.59 plus this port's complete source overlay and `kernel/config/gpu18.config`. `linux-6.18.59-t860-gpu18-source.tar.xz` exports the actual build sources, including local driver additions, without objects or generated build output. `kernel/patches/full-gpu18.patch` records all source differences from the upstream tarball. The baseline build volume was case insensitive; the full overlay records its upper/lower-case netfilter source/header aliases as well, rather than silently claiming a different source tree produced the published binary.
- Project Aloha SM8150 UEFI: release 2412.74, gts6lwifi firmware (public release FD verified byte-for-byte against the deployed FD), [source](https://github.com/Project-Aloha/mu_aloha_platforms). BSD-2-Clause and embedded component licenses. The FD SHA-256 is recorded in release metadata. No developer stock boot is shipped: installation patches the recipient's own boot image.
- DualBootKernelPatcher: commit `36edd373e8d0ff2fd620832f0fc5108f7bcbc84f`, MIT; source and the unconditional TabS6 shellcode are in `third_party/DualBootKernelPatcher`.
- Magisk / magiskboot: v31.1, commit `0972f67d97f9b6302b67c5171283330c74114b4a`, GPL-3.0; [source with submodules](https://github.com/topjohnwu/Magisk/tree/v31.1). magiskboot is extracted unmodified from that release's arm64 APK library.
- BusyBox: 1.37.0, GPL-2.0; corresponding upstream source archive, exact build config and build instructions are supplied in the Release. Built statically with musl; hardware SHA accelerators and the unused tc applet are disabled for this toolchain.
- musl: 1.2.5, MIT; [source](https://musl.libc.org/releases/musl-1.2.5.tar.gz). Its copyright notice accompanies installer tools.
- libssc: commit `0cf77b93b55752da34dca2dcecc06fca8665184b` with `userspace/sensors/libssc-error-lifetime.patch`; source included in custom userspace archive.
- hexagonrpc: commit `da7a3742ab8d5273a281b70ee11f16fb2cb6a690`; tqftpserv: `0bf5b98c24229b0042554d99bb1509d813219f36`; iio-sensor-proxy: `0085ddf8ecb173a1c5fcf2344aa40e561125354f`. Source and individual licenses accompany the custom userspace archive.
- SDDM: Fedora 0.21.0 sources and Fedora patches, with this project's VT/autologin fixes. Corresponding patched source and build script are supplied.
- ath10k-bdencoder: qca-swiss-army-knife, ISC-style license retained at the top of `tools/ath10k-bdencoder`.
- Unmodified Fedora packages retain their licenses under `/usr/share/licenses` and `/usr/share/doc`. `packages.tsv` lists source RPM names; matching source packages are available from [Fedora Koji](https://koji.fedoraproject.org/koji/). The release does not relicense Fedora or any proprietary device firmware.

To build the kernel source archive on a case-sensitive Linux filesystem:

```sh
tar -xf linux-6.18.59-t860-gpu18-source.tar.xz
cd linux-6.18.59
make ARCH=arm64 olddefconfig
make ARCH=arm64 -j8 Image qcom/sm8150-samsung-gts6lwifi-native.dtb qcom/sm8150-samsung-gts6lwifi.dtb modules
make ARCH=arm64 INSTALL_MOD_PATH="$PWD/install" INSTALL_MOD_STRIP=1 modules_install
```

Use a native aarch64 toolchain or set the appropriate `CROSS_COMPILE`. Do not extract Linux sources onto a case-insensitive filesystem. Rebuilding does not guarantee an identical hash because kernel build timestamp, compiler and build host metadata affect the binary.

Installer scripts in this repository are sufficient to reconstruct the boot menu, sanitized root filesystem and recovery installer, provided the matching Fedora userspace packages and listed source artifacts are available. `prepare-release-root.py` operates only on an isolated staging copy; its private-data removal inputs are audit references and are never part of the public payload.
