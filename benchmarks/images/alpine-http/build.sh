#!/usr/bin/env bash
# Build in a private mount namespace; never operate on a host disk.
set -Eeuo pipefail
if [[ ${1:-} == --help || ${1:-} == -h ]]; then
    echo "Usage: $0 [--output DIR] [--cache DIR] --authorized-keys FILE [--password-hash FILE] [--network-map FILE]"
    exit 0
fi
[[ $EUID == 0 ]] || { echo 'Build requires root for chroot, loop devices, and mounts. Run with sudo.' >&2; exit 1; }
if [[ ${NIEP_BUILD_NAMESPACE:-0} != 1 ]]; then
    command -v unshare >/dev/null || { echo 'Missing dependency: unshare' >&2; exit 1; }
    exec unshare --mount --propagation private env NIEP_BUILD_NAMESPACE=1 "$0" "$@"
fi
HERE=$(cd -- "$(dirname -- "$0")" && pwd)
OUTPUT=$HERE/output
CACHE=$HERE/cache
KEYS=
HASH=
NETWORK=
usage() { echo "Usage: $0 [--output DIR] [--cache DIR] --authorized-keys FILE [--password-hash FILE] [--network-map FILE]"; }
while (($#)); do
    case $1 in
        --output|--cache|--authorized-keys|--password-hash|--network-map)
            [[ $# -ge 2 ]] || { usage >&2; exit 1; }
            case $1 in
                --output) OUTPUT=$2;; --cache) CACHE=$2;; --authorized-keys) KEYS=$2;;
                --password-hash) HASH=$2;; --network-map) NETWORK=$2;;
            esac; shift 2;;
        -h|--help) usage; exit 0;;
        *) usage >&2; exit 1;;
    esac
done
[[ $(uname -m) == x86_64 ]] || { echo 'An x86_64 Linux build host is required.' >&2; exit 1; }
for tool in curl sha256sum tar chroot losetup sfdisk mkfs.ext4 mount umount mountpoint qemu-img install truncate blkid mknod dd realpath grep sed awk; do
    command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 1; }
done
[[ -s $KEYS ]] || { echo '--authorized-keys must name a nonempty public authorized_keys file.' >&2; exit 1; }
if grep -q 'PRIVATE KEY' "$KEYS"; then echo 'Refusing a private key; supply public keys only.' >&2; exit 1; fi
mkdir -p "$OUTPUT" "$CACHE"
OUTPUT=$(realpath "$OUTPUT"); CACHE=$(realpath "$CACHE")
[[ ! -e $OUTPUT/alpine-http-base.qcow2 ]] || { echo 'Output already exists; choose a new output directory.' >&2; exit 1; }
WORK=$(mktemp -d "$OUTPUT/.build.XXXXXX")
ROOT=$WORK/root
LOOP=
PARTITION_NODE=
cleanup() {
    local status=$?
    trap - EXIT
    if mountpoint -q "$ROOT" && ! umount -R "$ROOT"; then
        echo "Could not unmount $ROOT; retained build directory and loop device $LOOP for recovery." >&2
        exit 1
    fi
    [[ -z $LOOP ]] || losetup -d "$LOOP"
    [[ -z $PARTITION_NODE ]] || rm -f "$PARTITION_NODE"
    rm -rf "$WORK"
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'echo "Build failed at line $LINENO" >&2' ERR
ROOTFS=alpine-minirootfs-3.20.10-x86_64.tar.gz
ROOTFS_SHA=0d44a414245f043ae56872a23762e6c9bee585da2cbe4aa81cbd0331eaf53223
if [[ ! -f $CACHE/$ROOTFS ]]; then
    curl --fail --location --retry 3 "https://dl-cdn.alpinelinux.org/alpine/v3.20/releases/x86_64/$ROOTFS" -o "$CACHE/$ROOTFS.part"
    mv "$CACHE/$ROOTFS.part" "$CACHE/$ROOTFS"
fi
printf '%s  %s\n' "$ROOTFS_SHA" "$CACHE/$ROOTFS" | sha256sum -c -
mkdir -p "$ROOT"
truncate -s 2G "$WORK/disk.raw"
printf 'label: dos\nstart=2048, type=83, bootable\n' | sfdisk "$WORK/disk.raw"
LOOP=$(losetup --find --show --partscan "$WORK/disk.raw")
# Minimal build environments may have no udev to create partition nodes.
if [[ ! -b ${LOOP}p1 ]]; then
    IFS=: read -r major minor < "/sys/class/block/${LOOP##*/}p1/dev"
    PARTITION_NODE=${LOOP}p1
    mknod "$PARTITION_NODE" b "$major" "$minor"
fi
# Disable ext4 features unsupported by the Syslinux BIOS loader.
mkfs.ext4 -q -O ^64bit,^metadata_csum -L niep-root "${LOOP}p1"
mount "${LOOP}p1" "$ROOT"
tar -xzf "$CACHE/$ROOTFS" -C "$ROOT"
cp /etc/resolv.conf "$ROOT/etc/resolv.conf"
mount --rbind /dev "$ROOT/dev"
mount --make-rslave "$ROOT/dev"
mount -t proc proc "$ROOT/proc"
mount -t sysfs sysfs "$ROOT/sys"
printf '%s\n' 'https://dl-cdn.alpinelinux.org/alpine/v3.20/main' > "$ROOT/etc/apk/repositories"
mkdir -p "$CACHE/apks" "$ROOT/tmp/apks"
# Locked APK closure: never silently resolve newer packages during a rebuild.
while read -r checksum package; do
    package=${package#./}
    if [[ ! -f $CACHE/apks/$package ]]; then
        curl --fail --location --retry 3 "https://dl-cdn.alpinelinux.org/alpine/v3.20/main/x86_64/$package" -o "$CACHE/apks/$package.part"
        mv "$CACHE/apks/$package.part" "$CACHE/apks/$package"
    fi
    printf '%s  %s\n' "$checksum" "$CACHE/apks/$package" | sha256sum -c -
    cp "$CACHE/apks/$package" "$ROOT/tmp/apks/"
done < "$HERE/packages.sha256"
chroot "$ROOT" /bin/sh -c 'apk add --no-network /tmp/apks/*.apk'
cp "$HERE/guest/httpd" "$ROOT/etc/init.d/niep-httpd"
cp "$HERE/guest/network" "$ROOT/etc/init.d/niep-network"
chmod 755 "$ROOT/etc/init.d/niep-httpd" "$ROOT/etc/init.d/niep-network"
: > "$ROOT/etc/niep-network.conf"
[[ -z $NETWORK ]] || cp "$NETWORK" "$ROOT/etc/niep-network.conf"
mkdir -p "$ROOT/var/www" "$ROOT/root/.ssh"
printf ok > "$ROOT/var/www/health"
install -m 600 "$KEYS" "$ROOT/root/.ssh/authorized_keys"
chmod 700 "$ROOT/root/.ssh"
# '*' disables password login but allows public key authentication.
sed -i 's|^root:[^:]*:|root:*:|' "$ROOT/etc/shadow"
cat > "$ROOT/etc/ssh/sshd_config" <<'SSH'
PermitRootLogin prohibit-password
PasswordAuthentication no
KbdInteractiveAuthentication no
AuthorizedKeysFile .ssh/authorized_keys
Subsystem sftp internal-sftp
SSH
if [[ -n $HASH ]]; then
    # Read a caller-generated crypt hash; never place plaintext passwords in the image.
    password_hash=$(cat "$HASH")
    [[ $password_hash == \$6\$* ]] || { echo 'Expected a SHA-512 crypt password hash.' >&2; exit 1; }
    # The variable is expanded inside the guest shell.
    # shellcheck disable=SC2016
    HASH_VALUE=$password_hash chroot "$ROOT" /bin/sh -c 'printf "root:%s\n" "$HASH_VALUE" | chpasswd -e'
    sed -i 's/PermitRootLogin prohibit-password/PermitRootLogin yes/; s/PasswordAuthentication no/PasswordAuthentication yes/' "$ROOT/etc/ssh/sshd_config"
fi
cat > "$ROOT/etc/mkinitfs/mkinitfs.conf" <<'INIT'
features="base virtio scsi ext4"
INIT
cat > "$ROOT/etc/fstab" <<'FSTAB'
LABEL=niep-root / ext4 defaults 0 0
FSTAB
printf 'niep-alpine\n' > "$ROOT/etc/hostname"
printf '127.0.0.1 localhost niep-alpine\n::1 localhost\n' > "$ROOT/etc/hosts"
printf '\nttyS0::respawn:/sbin/getty -L 115200 ttyS0 vt100\n' >> "$ROOT/etc/inittab"
printf 'ttyS0\n' >> "$ROOT/etc/securetty"
chroot "$ROOT" /bin/sh -eu <<'GUEST'
# Verify the actual binary and record its provider; Alpine splits this applet out.
/bin/busybox-extras --list | grep -qx httpd
/bin/busybox-extras httpd --help 2>&1 | grep -q 'Listen for incoming HTTP requests'
for service in devfs dmesg mdev; do rc-update add "$service" sysinit; done
for service in hwdrivers modules sysctl hostname bootmisc networking niep-network; do rc-update add "$service" boot; done
for service in sshd niep-httpd; do rc-update add "$service" default; done
for service in mount-ro killprocs savecache; do rc-update add "$service" shutdown; done
kernel=$(ls /lib/modules)
mkinitfs "$kernel"
mkdir -p /boot/syslinux
cp /usr/share/syslinux/ldlinux.c32 /boot/syslinux/
extlinux --install /boot/syslinux
apk info -v | sort > /etc/niep-packages.txt
GUEST
cat > "$ROOT/boot/syslinux/extlinux.conf" <<'BOOT'
SERIAL 0 115200
DEFAULT alpine
PROMPT 0
TIMEOUT 0
LABEL alpine
  LINUX /boot/vmlinuz-virt
  INITRD /boot/initramfs-virt
  APPEND root=LABEL=niep-root rootfstype=ext4 modules=virtio_pci,virtio_blk,ext4 console=tty0 console=ttyS0,115200n8
BOOT
dd if="$ROOT/usr/share/syslinux/mbr.bin" of="$WORK/disk.raw" bs=440 count=1 conv=notrunc status=none
cp "$ROOT/etc/niep-packages.txt" "$WORK/packages.txt"
rm -f "$ROOT"/etc/ssh/ssh_host_* "$ROOT/etc/machine-id" "$ROOT/var/lib/dbus/machine-id" "$ROOT/etc/resolv.conf" "$ROOT/etc/random-seed" "$ROOT/var/lib/seedrng/seed"
rm -rf "$ROOT/tmp/apks" "$ROOT/var/cache/apk/"* "$ROOT/var/lib/dhcpcd/"*
for target in dev sys proc ''; do umount -R "$ROOT${target:+/$target}"; done
losetup -d "$LOOP"; LOOP=
[[ -z $PARTITION_NODE ]] || rm -f "$PARTITION_NODE"
PARTITION_NODE=
qemu-img convert -f raw -O qcow2 "$WORK/disk.raw" "$WORK/alpine-http-base.qcow2"
qemu-img check "$WORK/alpine-http-base.qcow2"
install -m 444 "$WORK/alpine-http-base.qcow2" "$OUTPUT/alpine-http-base.qcow2"
cp "$WORK/packages.txt" "$OUTPUT/packages.txt"
cp "$HERE/packages.sha256" "$OUTPUT/packages.sha256"
(cd "$OUTPUT" && sha256sum alpine-http-base.qcow2 > image.sha256)
echo "Built $OUTPUT/alpine-http-base.qcow2"
