#!/bin/sh
# Read-only acceptance snapshot; does not dial, reconfigure, reboot or flash.
set -eu
[ "$(cat /tmp/sysinfo/board_name)" = dshanpi,t153mx-omnigate ] || {
    echo 'This check requires the OmniGate T153 board.' >&2
    exit 1
}
. /etc/openwrt_release
[ "$DISTRIB_ID" = ImmortalWrt ] && [ "$DISTRIB_RELEASE" = 25.12.2 ] || {
    echo 'This check targets ImmortalWrt 25.12.2.' >&2
    exit 1
}
printf 'System: %s %s %s\n' "$DISTRIB_ID" "$DISTRIB_RELEASE" "$DISTRIB_REVISION"
uname -a
printf 'Online CPUs: '; cat /sys/devices/system/cpu/online
printf 'Memory: '; sed -n '/^MemTotal:/p' /proc/meminfo
for option in luci.main.lang luci.main.mediaurlbase system.t153_immortal.applied; do
    printf '%s=' "$option"; uci -q get "$option" || true
done
for service in mwan3 smartdns ddns nlbwmon; do
    printf '%s enabled=' "$service"
    if /etc/init.d/"$service" enabled; then echo yes; else echo no; fi
    /etc/init.d/"$service" status || true
done
apk info -e luci-theme-argon luci-app-argon-config luci-app-3ginfo-lite \
    luci-app-sms-tool-js luci-app-mwan3 luci-app-smartdns luci-app-ddns \
    luci-app-nlbwmon kmod-aic8800-t153-sdio || true
fw4 check
iptables -V
ip6tables -V
ip -br address
ip route
lsusb -t
for device in eth0 eth1; do ethtool "$device" || true; done
mwan3 status || true
printf '\nThis is a read-only snapshot, not a traffic, Wi-Fi, Bluetooth or 4G test.\n'
