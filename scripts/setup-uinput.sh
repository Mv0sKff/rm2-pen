#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ] || [ "$#" -ne 1 ]; then
    printf 'Usage: sudo sh scripts/setup-uinput.sh USER\n' >&2
    exit 1
fi
id "$1" >/dev/null
getent group rm2-pen >/dev/null || groupadd --system rm2-pen
usermod -aG rm2-pen "$1"
install -d /etc/udev/rules.d /etc/modules-load.d
printf '%s\n' 'SUBSYSTEM=="misc", KERNEL=="uinput", GROUP="rm2-pen", MODE="0660"' > /etc/udev/rules.d/99-rm2-pen-uinput.rules
printf '%s\n' uinput > /etc/modules-load.d/rm2-pen.conf
modprobe uinput
udevadm control --reload-rules
udevadm trigger --action=change --subsystem-match=misc --sysname-match=uinput
udevadm settle
printf 'Setup complete. Log out and back in before running the demos.\n'
