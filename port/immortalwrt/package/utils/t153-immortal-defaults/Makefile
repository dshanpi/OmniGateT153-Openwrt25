# SPDX-License-Identifier: GPL-2.0-only
include $(TOPDIR)/rules.mk

PKG_NAME:=t153-immortal-defaults
PKG_VERSION:=1
PKG_RELEASE:=1
PKG_LICENSE:=GPL-2.0-only
PKGARCH:=all

include $(INCLUDE_DIR)/package.mk

define Package/t153-immortal-defaults
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=OmniGate T153 ImmortalWrt UI and service defaults
  DEPENDS:=@TARGET_sunxi +luci-theme-argon +luci-app-argon-config
endef

define Build/Compile
endef

define Package/t153-immortal-defaults/install
	$(INSTALL_DIR) $(1)/etc/uci-defaults
	$(INSTALL_BIN) ./files/99-t153-immortal $(1)/etc/uci-defaults/
endef

$(eval $(call BuildPackage,t153-immortal-defaults))
