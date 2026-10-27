include $(TOPDIR)/rules.mk

PKG_NAME:=r4-openclash-offline
PKG_VERSION:=1
PKG_RELEASE:=3
PKG_LICENSE:=MIT

include $(INCLUDE_DIR)/package.mk

define Package/r4-openclash-offline
  SECTION:=net
  CATEGORY:=Network
  TITLE:=ARM64 Mihomo path for OpenClash
  DEPENDS:=+luci-app-openclash +mihomo-meta +v2ray-geoip +ca-bundle +kmod-tun +kmod-nft-tproxy +kmod-nft-socket
endef

define Package/r4-openclash-offline/description
  Links the pinned mihomo-meta binary to /etc/openclash/core/clash_meta.
  Does not ship GeoSite.dat. luci-app-openclash owns that file.
endef

define Build/Prepare
	mkdir -p $(PKG_BUILD_DIR)
endef

define Build/Compile
endef

define Package/r4-openclash-offline/install
	$(INSTALL_DIR) $(1)/etc/openclash/core $(1)/usr/share/r4-openclash-offline
	$(LN) /usr/libexec/mihomo $(1)/etc/openclash/core/clash_meta
	$(LN) /usr/share/v2ray/geoip.dat $(1)/etc/openclash/GeoIP.dat
	$(INSTALL_DATA) ./provenance.json $(1)/usr/share/r4-openclash-offline/provenance.json
endef

$(eval $(call BuildPackage,r4-openclash-offline))
