# 插件版烧录

适用：T153 OmniGate、1 GiB DDR4、eMMC。

## 文件

- `immortalwrt-...-ext4-raw.img`：完整 raw 镜像，写入 eMMC 用户区。
- `t153-fes-ddr933-ram-loader.img`：独立 FES，只在 RAM 中初始化 DDR 并提供烧录通道。
- `SHA256SUMS`：校验文件。

Release 提供 `.img.gz` 时，先解压成 `.img`。不要把 FES 拼进 raw，也不要把 FES 单独写入 eMMC。

## LYNX / FEL

1. 让 T153 进入 FEL，USB 数据线连接电脑，确认工具识别的是 T153。
2. 固件选择完整 `.img`；loader 选择独立 `t153-fes-ddr933-ram-loader.img`。
3. 使用 `command / raw`，目标为 eMMC 用户区；启用写入校验和烧录后重启。
4. 不勾选 Boot0 / `--emmc-boot0-from-image` 扩展；本项目验证的是 raw 用户区流程。
5. 等待写入、校验、重启均成功。插件版 raw 文件预期大小约 306,184,192 字节。

```json
{
  "firmwarePath": "<absolute-path>/immortalwrt-sunxi-cortexa7-dshanpi_t153mx-omnigate-ext4-raw.img",
  "confirmDestructive": true,
  "options": {
    "mode": "command",
    "verify": true,
    "postFlashAction": "reboot",
    "vendorOptions": {
      "raw": true,
      "loaderPath": "<absolute-path>/t153-fes-ddr933-ram-loader.img"
    }
  }
}
```

启动后 eth0/LAN 默认地址为 `192.168.153.1`；eth1/WAN 默认不开放 LuCI。串口为 3.3 V TTL、115200、8N1。首次进入后设置 root 密码，再按需启用插件服务。
