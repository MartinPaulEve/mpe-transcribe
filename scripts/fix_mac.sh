#!/usr/bin/env bash
# Restore the Parallels shared-networking route on the Mac.
#
# Symptom: network clients can START a recording but the host's
# replies never arrive — no ACK/STATE/TEXT reaches the VM, stop
# presses do nothing, the host log fills with "Rejected START" and
# "Giving up on unACKed datagram", and the Mac cannot ping the VM
# while the VM can still ping the Mac.
#
# Cause: macOS occasionally drops the connected-subnet route for
# the Parallels bridge (after sleep/wake, Wi-Fi changes, or VPN
# flaps). Mac->VM packets then follow the default route out the
# physical interface and vanish. Re-adding the route fixes it
# instantly.
#
# Usage: ./fix_mac.sh [vm-ip]     (default vm-ip: 10.211.55.4)
set -euo pipefail

VM_IP="${1:-10.211.55.4}"

# Find the Parallels bridge: the first bridge interface with an
# IPv4 address (bridge100 for shared networking).
IFACE=""
ADDR=""
for candidate in $(ifconfig -l); do
    case "$candidate" in
        bridge*) ;;
        *) continue ;;
    esac
    addr=$(ifconfig "$candidate" 2>/dev/null | awk '/inet /{print $2; exit}')
    if [ -n "$addr" ]; then
        IFACE="$candidate"
        ADDR="$addr"
        break
    fi
done
if [ -z "$IFACE" ]; then
    echo "Error: no bridge interface with an IPv4 address found." >&2
    echo "Is Parallels running with shared networking?" >&2
    exit 1
fi

# Parallels shared networking uses a /24 (netmask 0xffffff00).
SUBNET="${ADDR%.*}.0/24"
echo "==> Bridge: $IFACE ($ADDR), subnet $SUBNET"

echo "==> Route to $VM_IP before:"
route -n get "$VM_IP" 2>/dev/null | grep -E 'interface|gateway' || true

sudo route -n delete -net "$SUBNET" >/dev/null 2>&1 || true
sudo route -n add -net "$SUBNET" -interface "$IFACE" >/dev/null

echo "==> Route to $VM_IP after:"
route -n get "$VM_IP" 2>/dev/null | grep -E 'interface|gateway' || true

if ping -c 2 -t 3 "$VM_IP" >/dev/null 2>&1; then
    echo "==> OK: $VM_IP is reachable."
else
    echo "==> Warning: route restored but $VM_IP is still unreachable." >&2
    echo "    Check the VM is running, or restart Parallels networking" >&2
    echo "    (or reboot the Mac)." >&2
    exit 1
fi
