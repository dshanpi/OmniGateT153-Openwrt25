# ImmortalWrt 25.12.2 · T153 插件扩展版

目标版本：`v25.12.2-t153-plugins-r1`  
适配板：OmniGate T153，4× Cortex-A7、1 GiB DDR4、eMMC。完整镜像和独立 FES 在 GitHub Release 附件中，源码、配置和补丁位于分支 [`immortalwrt-25.12-t153-plugins`](https://github.com/dshanpi/OmniGateT153-Openwrt25/tree/immortalwrt-25.12-t153-plugins)。

## 本版内容

- 网络与安全：adblock-fast、banIP、PBR、SQM、UPnP、WOL、DoH DNS、ACME、Tinyproxy。
- 运维：ttyd、Watchcat、自动重启、Chrony、Commands、IRQ balance、LLDP、vnStat、tcpdump、htop、iperf3。
- VPN：OpenVPN（LuCI）、WireGuard、ZeroTier。
- 工业接口：T153 CAN-FD、ser2net、SNMP、mbusd、GPIO/I2C/SPI 工具。
- 4G/USB：EC20/ML302 的 QMI、MBIM、PPP、USB 网卡和串口驱动，3ginfo-lite、短信管理。
- 存储：Ksmbd、NFS、Diskman、Filemanager、USB 打印、Aria2。
- 无线：AIC8800D80 Wi-Fi/蓝牙驱动与固件随设备包保留。

服务默认保持关闭；插件“编译进镜像”不等于已经打开端口、完成拨号或通过每一项硬件验收。eth0/LAN 的默认管理地址仍为 `192.168.153.1`，eth1/WAN 默认不开放 LuCI。

## 构建和烧录

从 ImmortalWrt `v25.12.2` 源码解压后，依次应用 r1 板级补丁和本分支的插件补丁，执行 `./scripts/feeds update -a`、`./scripts/feeds install -a`、复制 `configs/t153mx-omnigate-plugins-full.config`、`make defconfig`、`make menuconfig`、`make`。dufs 需要 Rust/LLVM 构建缓存，未放入快速可复现的默认镜像。

烧录时解压 Release 的 `.img.gz`，选择完整 raw `.img` 和独立 `t153-fes-ddr933-ram-loader.img`，使用 `command / raw` 写入 eMMC 用户区，开启校验和重启；不要启用额外 Boot0 写入。详细参数见 [`docs/FLASH-PLUGINS.md`](docs/FLASH-PLUGINS.md)。

## 边界和未验收项

插件版使用 256 MiB rootfs 分区，Linux 当前可用内存窗口为 384 MiB。Docker/容器、数据库、Netdata、ClamAV、BT 下载器、大型代理套件、依赖 Go module 缓存的 FRP/GOST/rclone/cloudflared、依赖 Rust/LLVM 构建缓存的 dufs、collectd、Mosquitto 和 MiniDLNA/FFmpeg 未放入默认镜像。AIC8800D80 在既有启动记录中仍有上电失败；蓝牙、4G 数据拨号、mwan3 切换、WAN 长期稳定性和插件逐项实机操作需要单独验收。
