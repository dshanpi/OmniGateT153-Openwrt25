# ImmortalWrt 25.12.2 · T153 r1 发布说明

发布日期：**2026-11-16**（Asia/Shanghai）  
版本：`v25.12.2-t153-immortalwrt-r1`  
分支：`immortalwrt-25.12-t153`

[下载本版](https://github.com/dshanpi/OmniGateT153-Openwrt25/releases/tag/v25.12.2-t153-immortalwrt-r1) · [烧录步骤](docs/FLASH.md) · [源码构建](docs/BUILD.md)

本版将已完成实机基础验证的 preview.2 镜像整理为正式 r1 发布，补齐专用分支、构建入口、烧录操作和硬件记录。**固件字节未变**，不以重新命名代替测试，也不宣称已通过全部外设或长期稳定性验收。

## 本次交付

- ImmortalWrt v25.12.2 / Linux 6.12.103，T153 四核 A7。
- 源码 DDR4、SPL/U-Boot，完整 FAT + ext4 eMMC raw 镜像。
- Argon 中文、4G 管理、mwan3、SmartDNS、DDNS、nlbwmon 软件套件。
- 未压缩 `.img` 与 `.img.gz`、独立 FES、SHA256、板级补丁和最小配置。
- 构建锁定信息、软件验证报告，以及本版实际烧录和启动记录。

## 实测结论

2026-11-16，通过 LYNX / OpenixCLI 将本版完整 raw 写入 T153 的 **eMMC 用户区**。写入量 306,184,192 字节；FES 校验、烧录后重启均成功。随后观察到源码 DDR4 初始化通过、持久 U-Boot 加载 Linux 6.12.103、ImmortalWrt 25.12.2 shell，CPU `0-3` 在线。

独立读回磁盘前 4 MiB，SHA256 与发布镜像一致。eth0 协商至 1 Gbps / 全双工，电脑从 LAN DHCP 取得 `192.168.153.169`，并从 `192.168.153.1` 获取 Argon 中文登录页面。未登录访问 LuCI 时返回 `403` 并携带 `x-luci-login-required: yes` 和登录 HTML，这是此次获取到的登录响应，不是已证明管理页面不可达。

| 文件 | 字节数 | SHA256 |
|---|---:|---|
| 完整 raw.img | 306184192 | `2a0baa4305fda37071734b81a86ef468915f56b0cd828d3ab44bb18c961da853` |
| raw.img.gz | 20514207 | `9aae8312e6859c96126154b54fdb153854e3736acf5fef8985b5481602f56867` |
| 独立 FES | 1154048 | `0d32d52139bc969f7f90665d32203ff07366ed0a31139bda607d89edbcd12873` |

## 烧录失败记录的结论

此前用户界面报告“校验主线 SPL 失败”，该阶段属于额外的 eMMC Boot0/SPL 预检，尚未写入分区。本次采用 **完整 raw + 独立 DDR933 FES，写 eMMC 用户区，不启用额外 Boot0 写入**，烧录及启动成功。

因此，本次实测不支持“该镜像分区无法启动”的判断；但此前预检的具体失败原因仍未确定，不能写成已证实的烧录工具缺陷或已修复的 SPL 算法错误。烧录时按 [FLASH.md](docs/FLASH.md) 使用已验证参数。

## 必须保留的限制

- **AIC8800D80 Wi-Fi 本次启动上电失败**，日志为 `fail to set AIC_WIFI power state to 1`。驱动和固件编入不代表 Wi-Fi 可用。
- Linux / U-Boot 当前仅使用 384 MiB 内存窗口，尚未开放整颗 1 GiB DDR4。
- WAN 千兆重复协商问题尚未确认解决；本次 LAN 千兆协商不能替代 WAN 稳定性或持续吞吐验收。
- 蓝牙、EC20 / ML302 数据拨号、多 WAN 故障切换及插件完整操作尚未在本版验收。
- 没有完成物理断电冷启动、多次重启、CPU / DDR / 存储长时压力测试。
- 不支持 `sysupgrade` / LuCI 固件升级；CPU_OFF、hotplug、suspend、多核 kexec 不在已实现接口范围。
- 临时 FES 与 AIC 设备固件含二进制组件；持久 DDR4/SPL/U-Boot 由源码构建。

正式发布表示本次交付已固定并有基础实测记录，不表示上述限制已经消失。
