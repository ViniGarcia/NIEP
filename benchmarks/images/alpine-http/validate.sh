#!/usr/bin/env bash
# Boot disposable overlays, verify HTTP over both NICs, then power off via SSH.
set -Eeuo pipefail
if (($# != 2)); then echo "Usage: $0 BASE.qcow2 SSH_PRIVATE_KEY" >&2; exit 1; fi
BASE=$(realpath "$1")
KEY=$(realpath "$2")
for tool in qemu-system-x86_64 qemu-img curl ssh python3 cmp; do
    command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 1; }
done
[[ -f $BASE && -f $KEY ]] || { echo 'Base image and private SSH key must exist.' >&2; exit 1; }
WORK=$(mktemp -d)
PID=
# Invoked by the EXIT trap.
# shellcheck disable=SC2317
cleanup() {
    local status=$?
    trap - EXIT
    if [[ -n $PID ]] && kill -0 "$PID" 2>/dev/null; then
        kill "$PID" 2>/dev/null || true
        wait "$PID" 2>/dev/null || true
    fi
    if ((status)); then
        echo "Validation failed; serial log retained in $WORK/serial.log" >&2
        rm -f "$WORK/instance.qcow2"
    else rm -rf "$WORK"; fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
qemu-img create -q -f qcow2 -F qcow2 -b "$BASE" "$WORK/instance.qcow2"
# QEMU rejects a port collision; never connect to another listener after a failed launch.
read -r HTTP_PORT SSH_PORT DATA_PORT < <(python3 - <<'PY'
import socket
sockets = [socket.socket() for _ in range(3)]
for sock in sockets:
    sock.bind(('127.0.0.1', 0))
print(*(sock.getsockname()[1] for sock in sockets))
PY
)
ACCEL=tcg
[[ -r /dev/kvm && -w /dev/kvm ]] && ACCEL=kvm
qemu-system-x86_64 -machine "pc,accel=$ACCEL" -m 256 -smp 1 \
    -drive "file=$WORK/instance.qcow2,format=qcow2,if=virtio" \
    -netdev "user,id=management,hostfwd=tcp:127.0.0.1:$HTTP_PORT-:8080,hostfwd=tcp:127.0.0.1:$SSH_PORT-:22" \
    -device virtio-net-pci,netdev=management,addr=0x03 \
    -netdev "user,id=data,net=10.20.0.0/24,host=10.20.0.254,hostfwd=tcp:127.0.0.1:$DATA_PORT-10.20.0.2:8080" \
    -device virtio-net-pci,netdev=data,mac=52:54:02:20:10:01,addr=0x0a \
    -display none -serial "file:$WORK/serial.log" -monitor none -no-reboot > "$WORK/qemu.log" 2>&1 &
PID=$!
SSH=(ssh -i "$KEY" -p "$SSH_PORT" -o BatchMode=yes -o ConnectTimeout=2 -o StrictHostKeyChecking=accept-new -o "UserKnownHostsFile=$WORK/known_hosts" root@127.0.0.1)
ready=0
for ((attempt=0; attempt<120; attempt++)); do
    kill -0 "$PID" 2>/dev/null || { cat "$WORK/qemu.log" >&2; exit 1; }
    if [[ $(curl --noproxy '*' -sS --max-time 1 -o "$WORK/health" -w '%{http_code}' "http://127.0.0.1:$HTTP_PORT/health" 2>/dev/null) == 200 ]] && cmp -s "$WORK/health" <(printf ok); then ready=1; break; fi
    sleep 1
done
((ready)) || { echo 'Timed out waiting for HTTP 200 /health.' >&2; exit 1; }
# Static MAC mapping is optional in the base. Configure it over management SSH if absent.
ssh_ready=0
for ((attempt=0; attempt<30; attempt++)); do
    if "${SSH[@]}" true 2>/dev/null; then ssh_ready=1; break; fi
    sleep 1
done
((ssh_ready)) || { echo 'SSH authentication failed.' >&2; exit 1; }
if curl --noproxy '*' --fail --silent --max-time 2 "http://127.0.0.1:$DATA_PORT/health" -o "$WORK/boot-data" && cmp -s "$WORK/boot-data" <(printf ok); then
    echo 'PASS: data NIC was configured automatically at boot.'
else
    echo 'Configuring the data NIC via SSH for a generic base.'
    # Expand interface variables in the remote guest shell.
    # shellcheck disable=SC2016
    "${SSH[@]}" 'for dev in /sys/class/net/*; do if [ "$(cat "$dev/address")" = 52:54:02:20:10:01 ]; then iface=${dev##*/}; ip addr replace 10.20.0.2/24 dev "$iface"; ip link set "$iface" up; fi; done'
fi
[[ $(curl --noproxy '*' --fail --silent --max-time 5 -o "$WORK/data-health" -w '%{http_code}' "http://127.0.0.1:$DATA_PORT/health") == 200 ]]
cmp -s "$WORK/data-health" <(printf ok)
"${SSH[@]}" 'rc-service niep-httpd status; ip -4 addr; cat /etc/alpine-release; ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub; /bin/busybox-extras --list | grep -x httpd; poweroff'
for ((attempt=0; attempt<30; attempt++)); do
    if ! kill -0 "$PID" 2>/dev/null; then
        wait "$PID"; PID=
        echo "PASS: HTTP 200 ok on management and data NICs, SSH, clean poweroff ($ACCEL, 256 MiB, 1 vCPU)."
        exit 0
    fi
    sleep 1
done
echo 'Guest did not power off cleanly.' >&2
exit 1
