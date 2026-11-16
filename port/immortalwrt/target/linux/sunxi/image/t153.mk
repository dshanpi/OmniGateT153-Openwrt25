# SPDX-License-Identifier: GPL-2.0-only
# T153 uses a source-built four-core SPL/U-Boot and a fixed 32 MiB boot FAT.
# Keep its disk image separate from the generic sunxi sysupgrade layout.

define Build/t153-sdcard
	./gen_t153_sdcard_img.sh $@ \
		$(IMAGE_KERNEL) $(IMAGE_ROOTFS) \
		$(CONFIG_TARGET_ROOTFS_PARTSIZE) \
		$(STAGING_DIR_IMAGE)/$(DEVICE_NAME)-u-boot-with-spl.bin \
		t153.bootscript
endef

define Device/dshanpi_t153mx-omnigate
  $(call Device/FitImageGzip)
  DEVICE_VENDOR := DshanPI
  DEVICE_MODEL := T153MX OmniGate
  DEVICE_VARIANT := four-core Cortex-A7 (experimental)
  SOC := sun8i-t153
  SUNXI_DTS := allwinner/sun8i-t153-dshanpi-omnigate
  SUPPORTED_DEVICES := dshanpi,t153mx-omnigate
  KERNEL_LOADADDR := 0x48008000
  KERNEL_ENTRY := 0x48008000
  KERNEL_INITRAMFS := kernel-bin | gzip | fit gzip $$(DTS_DIR)/$$(SUNXI_DTS).dtb
  FILESYSTEMS := ext4
  IMAGES := raw.img.gz
  IMAGE/raw.img.gz := t153-sdcard | gzip
  # The bin-only U-Boot package is selected by its BUILD_DEVICES default.
  # It must not enter DEVICE_PACKAGES, which are installed into the rootfs.
  DEVICE_PACKAGES := luci luci-ssl-openssl ethtool ip-full \
	t153-immortal-defaults luci-theme-argon luci-app-argon-config \
	luci-i18n-base-zh-cn luci-i18n-firewall-zh-cn \
	luci-i18n-argon-config-zh-cn \
	luci-app-3ginfo-lite luci-i18n-3ginfo-lite-zh-cn \
	luci-app-sms-tool-js luci-i18n-sms-tool-js-zh-cn \
	luci-app-mwan3 luci-i18n-mwan3-zh-cn iptables-nft ip6tables-nft \
	luci-app-smartdns luci-i18n-smartdns-zh-cn \
	luci-app-ddns luci-i18n-ddns-zh-cn \
	luci-app-nlbwmon luci-i18n-nlbwmon-zh-cn \
	-automount -autocore -luci-app-cpufreq \
	kmod-usb2 kmod-usb-ohci kmod-usb-storage usbutils \
	kmod-can kmod-can-raw kmod-can-t153 \
	canutils canutils-candump canutils-cansend canutils-canfdtest \
	kmod-usb-net-qmi-wwan kmod-usb-net-cdc-mbim \
	kmod-usb-serial-option kmod-usb-serial-qualcomm \
	kmod-usb-net-cdc-ether kmod-usb-net-rndis \
	uqmi umbim luci-proto-qmi luci-proto-mbim luci-proto-3g \
	kmod-ppp ppp comgt picocom \
	kmod-cfg80211 kmod-aic8800-t153-sdio aic8800d80-firmware \
	iw wpad-basic-mbedtls kmod-bluetooth kmod-hci-uart \
	kmod-rfkill kmod-rfkill-gpio bluez-utils bluez-daemon aic8800d80-bt
endef
TARGET_DEVICES += dshanpi_t153mx-omnigate
