#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ] || [ "$#" -ne 1 ]; then
    printf 'Usage: sudo sh scripts/setup-uinput.sh USER\n' >&2
    exit 1
fi
id "$1" >/dev/null
getent group rm-wacom2 >/dev/null || groupadd --system rm-wacom2
usermod -aG rm-wacom2 "$1"
install -d /etc/udev/rules.d /etc/modules-load.d
printf '%s\n' 'SUBSYSTEM=="misc", KERNEL=="uinput", GROUP="rm-wacom2", MODE="0660"' > /etc/udev/rules.d/99-rm-wacom2-uinput.rules
printf '%s\n' uinput > /etc/modules-load.d/rm-wacom2.conf
modprobe uinput
udevadm control --reload-rules
udevadm trigger --action=change --subsystem-match=misc --sysname-match=uinput
udevadm settle
printf 'Setup complete. Log out and back in before running the demos.\n'
