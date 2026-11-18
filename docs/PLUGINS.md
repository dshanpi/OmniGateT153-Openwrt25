# T153 OmniGate 插件扩展版

本分支在 `immortalwrt-25.12-t153` 的 T153 板级补丁上，加入一套面向工业网关的可用插件集合。插件会编译进镜像，但服务保持关闭，首次启动后按实际用途启用。

- 分支：`immortalwrt-25.12-t153-plugins`
- 基线：ImmortalWrt 25.12.2（Linux 6.12.103）
- 目标：`sunxi/cortexa7 / dshanpi_t153mx-omnigate`
- rootfs 分区：256 MiB；插件版 rootfs 构建占用约 47 MiB
- 镜像：完整 raw eMMC 镜像，和 r1 使用相同的独立 DDR933 FES

## 包含的能力

| 类别 | 预装内容 |
| --- | --- |
| 网络与安全 | adblock-fast、banIP、PBR、SQM、UPnP、WOL、DoH DNS、ACME、Tinyproxy |
| 运维监控 | ttyd、Watchcat、自动重启、Chrony、Commands、IRQ balance、LLDP、vnStat、tcpdump、htop、iperf3 |
| VPN 与组网 | OpenVPN、WireGuard、ZeroTier、Cloudflared |
| 工业与串口 | ser2net、SNMP、mbusd、NATMap、GPIO/I2C/SPI 工具 |
| 存储与 USB | Ksmbd、NFS、Diskman、Filemanager、dufs、MiniDLNA、USB 打印、Aria2 |

T153 原有的 CAN-FD、EC20/ML302 4G（QMI/MBIM/PPP）、AIC8800D80 驱动和蓝牙组件也保留在设备包中。

## 资源边界

“所有能用的”按适配性实现为实用插件集合，不是把所有 feeds 包字面全选。Docker/容器、数据库、Netdata、ClamAV、qBittorrent/Transmission、大型代理套件以及依赖 Go module 缓存的 FRP/GOST/rclone/cloudflared、需要额外外部源码下载的 collectd 统计没有预装，避免在 1 GiB DDR4、Linux 当前 384 MiB 内存窗口和 256 MiB rootfs 上造成不可控资源占用。这些包可在有完整 Go module 缓存的构建环境中作为可选包加入；Wi-Fi 驱动虽保留，但 AIC8800D80 在现有实机启动记录中仍有上电失败，插件预装不代表该硬件已验收。

## 文件

- `configs/t153mx-omnigate-plugins-full.config`：完整插件配置（包名使用 OpenWrt 的连字符 Kconfig 符号）。
- `configs/t153-plugin-bundle-plan.json`：插件分组、排除项和资源策略。
- `patches/immortalwrt-25.12.2-t153-plugins-r1.patch`：在 r1 板级补丁后追加插件设备包的增量补丁。
- `docs/BUILD-PLUGINS.md`：从官方源码重建插件版。
- `docs/FLASH-PLUGINS.md`：raw + FES 烧录步骤和校验要求。

镜像与 FES 放在对应 GitHub Release，不把大二进制塞进源码分支。
