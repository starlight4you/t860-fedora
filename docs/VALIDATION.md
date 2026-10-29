# 2026.10.29 GPU18 验证范围

## 已在 SM-T860 实机完成

- `6.18.59-t860-gpu18` 默认启动及关机后重新启动。
- 原生 DPU＋双 DSI、颜色和明暗正常；桌面拖动流畅，用户未见撕裂。
- 电源键熄屏再点亮，无此前的白闪/花屏，显示与触摸正常。
- 两次 RTC 触发的真实 s2idle；每次 SDSP 恢复复用已成功验证的共享内存状态，传感器重新可用。
- SCM assign / FastRPC probe / rpmsg probe 的 `-22` 循环计数均为 0。
- 完整 poweroff 后，用户确认关机不再大量出现 `-22`；重新开机仍是 GPU18，传感器正常。
- 安装器的固件导入逻辑对保留的 Android 分区做只读测试，所有必需 GPU/DSP/无线/传感器文件检查通过。测试输出只写入隔离临时目录。

## 已离线完成

- 同样的 stock boot、FD、shellcode 和静态 patcher 重建 UEFI handoff；结果逐字节等于已在设备使用的镜像。
- Samsung boot header、UNCOMPRESSED_IMG、SEANDROIDENFORCE、AVB footer/vbmeta、UEFI FV 结构检查。
- 模块版本与 Image/设备树配套；不包含 GPU19/GPU20 的 SMMU 诊断或实验修改。
- 公开文件系统去除机器身份、用户数据和凭据后复制到全新 ext4，防止删除文件残留在空闲块。
- ext4 检查与 FAT ESP 检查；移除旧 recovery 内核不认识的 orphan_file / metadata_csum_seed 特性。
- 对发布资产生成 SHA-256；电脑端先验证所有下载，远端验证工具，写入后回读 userdata/cache/boot/vbmeta。
- 在只读系统镜像上叠加一次性测试层，以合成 Wi-Fi 校准输入运行首次和再次启动初始化，均通过；不会把测试身份或密钥写回公共镜像。systemd 初始化单元检查通过。
- 电脑端安装器通过六项模拟 ADB 测试：校验损坏、错误型号、取消、只检查、完整传输以及远端写入失败后阻止后续写入/重启。
- 只读镜像加一次性测试层执行 Fedora `dnf --cacheonly check`，依赖检查通过。

## 仍未完成

没有把当前开发平板恢复为原厂 Android 再执行这一新版完整安装流程，因此 Release 标为预发布。离线测试和现有系统上的驱动验收不能替代这一整机验收。

启动阶段短暂花屏、完整硬件亮度调节、S Pen、耳机接口、USB SuperSpeed 不在已完成范围。FastRPC 修复没有消除 Samsung 传感器固件自身的恢复时重启。
