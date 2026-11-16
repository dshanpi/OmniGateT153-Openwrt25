# 从官方源码构建 T153 ImmortalWrt r1

本仓库的 `immortalwrt-25.12-t153` 分支保存板级适配，不是完整上游源码树。构建方式是 **下载 ImmortalWrt v25.12.2 官方源码归档 → 应用完整 T153 补丁 → 正常 feeds / menuconfig / make**。

`port/immortalwrt/` 将适配文件按上游路径展开，便于阅读；`manifest.json` 记录清单与摘要，`upstream-changes.patch` 便于审阅已有上游文件的改动。它们不替代完整补丁，不能直接整目录覆盖上游源码。持久 SPL/U-Boot 与内核均由本次源码构建，不依赖本机 Tina SDK 或预编译启动区。

## 1. 准备 Linux 构建环境

Ubuntu 24.04 示例，使用普通用户在独立目录构建：

```sh
sudo apt-get update
sudo apt-get install build-essential clang flex bison gawk gcc-multilib \
  g++-multilib gettext git libncurses-dev libssl-dev libelf-dev \
  python3 python3-dev python3-setuptools python3-pyelftools \
  rsync swig unzip zlib1g-dev file wget curl ca-certificates patch \
  xz-utils bzip2 zstd time pkg-config
```

可复用上游下载缓存；不要将其它版本的 `build_dir` / `staging_dir` 作为输入。不要把解压的源码嵌套在无关 Git 仓库里，以免版本脚本误取父仓库信息。

## 2. 下载官方源码、补丁和配置

```sh
mkdir -p ~/immortalwrt25-t153-r1
cd ~/immortalwrt25-t153-r1

curl --fail --location --output immortalwrt-25.12.2.tar.gz \
  https://codeload.github.com/immortalwrt/immortalwrt/tar.gz/refs/tags/v25.12.2

release_url='https://github.com/dshanpi/OmniGateT153-Openwrt25/releases/download/v25.12.2-t153-immortalwrt-r1'
curl --fail --location --output immortalwrt-25.12.2-t153-r1.patch \
  "$release_url/immortalwrt-25.12.2-t153-r1.patch"
curl --fail --location --output t153mx-omnigate-immortalwrt-v25.12.2.config \
  "$release_url/t153mx-omnigate-immortalwrt-v25.12.2.config"
curl --fail --location --output SHA256SUMS "$release_url/SHA256SUMS"

printf '%s  %s\n' \
  1126f61d9d300d165221419f54fef847dda955c9cb80a817f4b71b7c2fa187eb \
  immortalwrt-25.12.2.tar.gz | sha256sum -c -
sha256sum -c SHA256SUMS --ignore-missing
printf '%s  %s\n' \
  ea3aa43db99dcc2c6f947441a74b0711f5a6609220da43af1dd3f05344b60817 \
  immortalwrt-25.12.2-t153-r1.patch | sha256sum -c -

tar -xzf immortalwrt-25.12.2.tar.gz
cd immortalwrt-25.12.2
patch -p1 < ../immortalwrt-25.12.2-t153-r1.patch
```

应无 `.rej` 或补丁冲突。r1 补丁与 preview.2 完整补丁内容相同；直接应用到官方干净源码，不能在已打 preview 补丁的树上重复应用，也不能叠加旧 OpenWrt 25.12.6 补丁。

## 3. 常规 feeds 与菜单配置

```sh
./scripts/feeds update -a
./scripts/feeds install -a
cp ../t153mx-omnigate-immortalwrt-v25.12.2.config .config
make defconfig
make menuconfig
```

也可不导入配置，直接在 `make menuconfig` 选择：

```text
Target System  → Allwinner ARM SoCs
Subtarget      → Allwinner A20/A3x/H3/R40（cortexa7）
Target Profile → DshanPI T153MX OmniGate four-core Cortex-A7 (experimental)
```

菜单仍保留 `experimental` 名称，r1 发布未修改该上游 profile 文案。保留 ext4 根文件系统。选择板卡后会自动带入 LuCI / Argon 中文、4G 管理、mwan3、SmartDNS、DDNS、nlbwmon 及板级驱动；SPL/U-Boot 由板卡依赖构建。无需额外插件安装或外层镜像打包脚本。

不要将固定 feeds 改为浮动分支后仍称为本版配置。关键版本如下，完整信息见 `configs/immortalwrt-v25.12.2-source-lock.json`：

| 来源 | 固定提交 |
|---|---|
| ImmortalWrt | `4fc16f2985a358bd43bb522e43f05395fcbd6ed5` |
| packages | `84bd86384928955b568988ca0e09e2c78c75173d` |
| luci | `d6167ea0645cbd1327708d85f94824f42d0eb872` |
| routing | `e49d76035aafb85ddc993b59271d8c7ba56b5362` |
| telephony | `2618106d5846a4a542fdf5809f0d3ed228ce439b` |
| video | `094bf58da6682f895255a35a84349a79dab4bf95` |

## 4. 构建和输出

```sh
make defconfig
make download -j6
make -j6
```

按主机资源调整并行数。出现错误后使用 `make -j1 V=s` 查看完整失败信息。

完整盘自动输出到：

```text
bin/targets/sunxi/cortexa7/immortalwrt-sunxi-cortexa7-dshanpi_t153mx-omnigate-ext4-raw.img.gz
```

解压取得烧录文件：

```sh
gzip -dc bin/targets/sunxi/cortexa7/immortalwrt-sunxi-cortexa7-dshanpi_t153mx-omnigate-ext4-raw.img.gz \
  > immortalwrt-sunxi-cortexa7-dshanpi_t153mx-omnigate-ext4-raw.img
```

默认布局为 32 MiB FAT 启动分区、256 MiB ext4 根分区，总盘 292 MiB。更改 `CONFIG_TARGET_ROOTFS_PARTSIZE` 后镜像大小会随之改变；烧录时以实际字节数为准。

构建输出保留 `config.buildinfo`、`feeds.buildinfo`、`version.buildinfo`、manifest 和 `sha256sums`。发布摘要用于核对发布文件；自行构建可能因 APK 签名密钥、配置选择等不同而产生不同镜像摘要，不能只按摘要不同就判定构建错误。不要发布签名私钥。

本项目的软件检查器可在构建后核对 SPL/U-Boot、分区、FIT/DTB、内核、根文件系统、67 个必选包和模块固件：

```sh
mkdir -p ../artifacts
python3 /path/to/OmniGateT153-Openwrt25/tests/immortalwrt/verify-image.py \
  --source "$PWD" \
  --output ../artifacts/image-validation.json \
  --raw-output ../artifacts/immortalwrt-t153-r1-raw.img
```

`required-packages.json` 应与检查器保留在同一目录。检查器只验证软件输入和镜像结构，不访问板卡，也不能替代硬件验收。

## 启动链与 FES

U-Boot 包固定自身元数据 `LOCALVERSION=-OpenWrt-r33311-981c978eff`、`SOURCE_DATE_EPOCH=1792282260`，保留既有 T153 引导基线；ImmortalWrt 根文件系统的版本和上游时间戳不变。启动串口出现 `OpenWrt` U-Boot 版本字符串不代表刷成旧 OpenWrt 系统，应以 `/etc/openwrt_release` 确认系统。

持久 DDR4 / SPL / U-Boot 全部由源码构建。独立 FES 在 RAM 中提供临时烧录通道，与持久启动链分开；FES 和无线设备固件仍包含二进制组件。烧录使用 [FLASH.md](FLASH.md) 的 raw eMMC 用户区流程。

**本版已验证基础启动和有线管理，AIC Wi-Fi 本次启动上电失败，WAN / 4G / 蓝牙 / 多 WAN / 长期稳定性仍有未完成项目。** 正式发布的边界见 [RELEASE-NOTES.md](../RELEASE-NOTES.md)。
