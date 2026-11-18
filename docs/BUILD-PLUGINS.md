# 从官方 ImmortalWrt 源码构建插件版

插件版不是完整源码镜像。构建机下载官方 ImmortalWrt 25.12.2 压缩包，依次应用 r1 主线补丁和插件增量补丁，再安装 feeds。

```sh
wget https://codeload.github.com/immortalwrt/immortalwrt/tar.gz/refs/tags/v25.12.2 -O immortalwrt-v25.12.2.tar.gz
tar -xf immortalwrt-v25.12.2.tar.gz
cd immortalwrt-25.12.2
# 从本分支取得两个补丁和配置文件
patch -p1 < immortalwrt-25.12.2-t153-r1.patch
patch -p1 < immortalwrt-25.12.2-t153-plugins-r1.patch
./scripts/feeds update -a
./scripts/feeds install -a
cp t153mx-omnigate-plugins-full.config .config
export CCACHE_DIR="$PWD/.ccache"
make defconfig
make menuconfig
make -j$(nproc)
```

在 `menuconfig` 中确认：

```text
Target System  -> sunxi
Subtarget      -> Cortex-A7
Target Profile -> DshanPI T153MX OmniGate
Target Images  -> ext4, 256 MiB
```

构建结果位于 `bin/targets/sunxi/cortexa7/`：

- `immortalwrt-sunxi-cortexa7-dshanpi_t153mx-omnigate-ext4-raw.img.gz`
- `immortalwrt-sunxi-cortexa7-dshanpi_t153mx-omnigate.manifest`
- `sha256sums`

插件补丁还把 Rust 的 `llvm.download-ci-llvm` 设为 `false`，从源码构建 LLVM，避开上游 CI LLVM 临时归档失效导致的 404；因此首次构建会比基线更久。当前 pinned feeds 中需要 Go module 缓存的 FRP/GOST/rclone/cloudflared，以及需要额外外部源码下载的 collectd 统计、Mosquitto/libwebsockets 和 ARM 工具链无法稳定编译的 MiniDLNA/FFmpeg 未放入默认镜像；配置文件中的服务只表示“编译进镜像”，不会自动打开端口或启用拨号、VPN、共享服务。部署后从 LuCI 或 `/etc/config/` 按实际硬件设置。
