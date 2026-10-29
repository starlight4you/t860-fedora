# Fedora 44 KDE for Samsung Galaxy Tab S6 Wi-Fi

适用于 **SM-T860 / gts6lwifi / Snapdragon 855** 的完整原生 Linux 系统镜像。可从原厂 Android 开始安装，不需要预先安装 Fedora，也不需要自行编译内核。

**当前版本：2026.10.29 GPU18，预发布。** 内核和驱动已在实机验证；这套新制作的全新安装器尚未完成从原厂 Android 到桌面的整机刷写验收。请保留匹配型号的原厂恢复固件。

## 下载和安装

下载入口：[Releases](https://github.com/starlight4you/t860-fedora/releases)。完整系统压缩后约 5 GB，分块用于满足 GitHub 单附件限制；`flash.py` 会自动下载并校验所有必需文件。

1. 确认型号是 **SM-T860**。SM-T865、SM-T867 和其他型号不支持。
2. 备份 Android 个人数据，解锁 bootloader。安装官方 [gts6lwifi TWRP](https://twrp.me/samsung/samsunggalaxytabs6qcomwifi.html)，按该页说明使用 Odin 刷入对应 recovery。首次刷 recovery 后直接进入 TWRP，避免被 Android 恢复覆盖。
3. 电脑安装 Python 3.9+ 和 Google 官方 [SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools)，将 `adb` 加入 PATH。平板停留在 **TWRP 主界面**，关闭 MTP；不用进入 ADB Sideload 模式。
4. 从本版本 Release 下载 `flash.py`，在其所在目录执行：

   ```sh
   python3 flash.py --download
   python3 flash.py --check-only
   python3 flash.py --erase-android
   ```

   Windows 可将 `python3` 替换为 `py -3`。最后一条命令要求输入 `SM-T860 ERASE`，随后执行安装并自动重启。也可使用同一 Release 的 Windows/macOS 启动脚本。

**安装会清空 Android 的 userdata，包括应用和内部存储文件。** boot、cache、vbmeta 会被替换。不会重分区，不写 recovery、BL、XBL、ABL、TZ、modem、vendor、persist 或 EFS。安装器在任何写入之前备份 boot/cache/vbmeta 到电脑的 `android-backup` 目录；这不包含 Android 用户数据。

首次启动扩展根文件系统。默认桌面账户为 **`fedora`，密码 `fedora`**，root 锁定，SSH 默认关闭。进入桌面后先运行 `passwd` 设置自己的密码。需要 SSH 时先安装自己的公钥，再启用 sshd。

## 包含的系统和驱动

| 项目 | 当前实现 |
|---|---|
| 系统 | Fedora 44 aarch64、KDE Plasma、Wayland、Maliit 触摸键盘 |
| 内核 | `6.18.59-t860-gpu18`，匹配的完整模块集 |
| 图形 | Adreno 640、MSM/Freedreno/Turnip，原生 DPU＋双 DSI 2560×1600 输出 |
| 显示同步 | 硬件 TE/vblank/page flip；原 simpledrm 整屏 CPU 拷贝路径已移除 |
| 面板 | ANA38401/AMSA05RB06，读取本机 MTP 校准 gamma，首帧后点亮，修复唤醒白闪/花屏 |
| 输入 | FTS1BA90A 多点触控，电源和音量键，触摸键盘 |
| 无线与音频 | WCN3990 Wi-Fi/蓝牙，扬声器和麦克风；固件从目标平板导入 |
| 传感器 | SLPI、FastRPC、libssc、iio-sensor-proxy、自动旋转 |
| 电源 | SM5705 电池/充电，s2idle，PMIC PS_HOLD 关机/重启 |

这不是 Android 容器或 chroot。桌面与应用直接运行在 Linux 上。镜像不包含开发设备的账号、Wi-Fi 密码、SSH 密钥、浏览器数据、游戏数据或 Android 容器数据。

## 固件与设备身份

公共系统镜像不携带开发设备的 Samsung 专属固件、蓝牙地址和传感器校准。安装时，从**目标平板原有的** apnhlos/modem/vendor/persist/efs 分区只读导入所需文件。UEFI handoff 由目标平板自己的 stock boot 镜像现场生成，保留 Samsung 启动容器；不会给所有设备刷同一个 Samsung stock boot。

因此安装前必须保留完整、匹配本机的 Android 固件分区。若这些分区已被擦除或来自其他型号，安装器会拒绝继续。

## 验证与已知限制

- 已验证的 GPU18 原生路径渲染约 60 FPS；用户确认拖动流畅、未见撕裂。此结果不是所有应用或游戏的性能保证。
- 两次真实 s2idle 恢复通过；修复 DSP 恢复后的共享内存重复赋权，SCM/FastRPC `-22` 循环为零，完整关机由实机用户确认不再大量报错。
- 启动早期仍可能短暂花屏，进入原生桌面后恢复；本版本未解决这一问题。
- 完整的面板硬件亮度插值尚未完成；仍依赖桌面软件调暗。S Pen、耳机接口和 USB SuperSpeed 未在本版本验收。
- 传感器固件在休眠恢复时仍可能重启，现有恢复链会重新建立服务；本版修复的是恢复失败和错误循环。
- 新制作的电脑端安装流程已经过离线校验、启动镜像一致性测试、固件导入测试和文件系统检查，**未执行清空当前开发平板的全新刷机测试**。详细范围见 [验证记录](docs/VALIDATION.md)。

## 源码、构建与鸣谢

基于 [Bentlybro/gts6l-mainline-linux](https://github.com/Bentlybro/gts6l-mainline-linux)，基线提交 `41fa9b85bfb55f9ee671a1dcb8161a5d90a2d542`。本项目保留原项目的设备移植工作，并加入原生显示、面板校准/唤醒及 FastRPC 恢复改动。

内核完整对应源码在 Release 的 `linux-6.18.59-t860-gpu18-source.tar.xz`；驱动、设备树、补丁和配置也保存在此仓库。额外用户态组件源码见 `t860-custom-userspace-source.tar.xz`。[构建及源码说明](docs/SOURCES.md)列出版本、许可证和来源。项目代码采用 GPL-2.0-only，第三方组件遵循各自许可证。

感谢 Project Aloha、DualBootKernelPatcher、Magisk、BusyBox、linux-msm、libssc、iio-sensor-proxy、Fedora、KDE 和 Linux 社区。
