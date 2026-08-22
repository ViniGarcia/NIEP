#!/usr/bin/env python3
"""Diagnose the host prerequisites needed by NIEP.

The doctor intentionally uses only the Python standard library.  It can run
before the project virtualenv exists and is therefore also useful from an
installer or a CI preflight job.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
from typing import Any, Iterable


SUPPORTED_PYTHON = {(3, 10), (3, 11), (3, 12)}
BOX_VERSION = "4.3.12"
EXPECTED_QCOW2 = ("VEM/IMAGES/tinycore12.qcow2", "VEM/IMAGES/click-on-osv.qcow2")
IMAGE_REFERENCE_RE = re.compile(r"^[^@\s:]+:[^@\s]+@sha256:[0-9a-f]{64}$")


def _short(value: str, limit: int = 320) -> str:
    value = " ".join(value.strip().split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _run(command: Iterable[str], cwd: Path | None = None, output_limit: int = 320) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return completed.returncode, _short(completed.stdout, output_limit)


class Doctor:
    def __init__(self, root: Path, strict: bool = False) -> None:
        self.root = root
        self.strict = strict
        self.checks: list[dict[str, Any]] = []
        self.lock_values = self._read_lock_values()

    def _read_lock_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        path = self.root / "INSTALLATION" / "image-locks.env"
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return values
        for line in lines:
            match = re.match(r"^([A-Z][A-Z0-9_]*)=(.+)$", line.strip())
            if match:
                values[match.group(1)] = match.group(2).strip()
        return values

    def good(self, name: str, detail: str) -> None:
        self.checks.append({"name": name, "status": "PASS", "detail": detail})

    def bad(
        self,
        name: str,
        detail: str,
        remediation: str,
        *,
        required: bool = True,
        strict_capable: bool = True,
    ) -> None:
        is_failure = required or (self.strict and strict_capable)
        self.checks.append(
            {
                "name": name,
                "status": "FAIL" if is_failure else "WARN",
                "detail": detail,
                "remediation": remediation,
            }
        )

    def check_python(self) -> None:
        version = sys.version_info[:3]
        if version[:2] not in SUPPORTED_PYTHON:
            supported = ", ".join(f"{major}.{minor}" for major, minor in sorted(SUPPORTED_PYTHON))
            self.bad(
                "python",
                f"{platform.python_implementation()} {platform.python_version()} ({sys.executable}) is outside {supported}",
                f"Install Python {supported} and rerun INSTALLATION/setup-py3-dev.sh.",
            )
            return
        self.good("python", f"{platform.python_implementation()} {platform.python_version()} ({sys.executable})")

    def check_venv(self) -> None:
        python = self.root / ".venv" / "bin" / "python"
        if not python.is_file() or not os.access(python, os.X_OK):
            self.bad(
                "venv",
                f"virtualenv interpreter not found at {python}",
                "Run ./INSTALLATION/setup-py3-dev.sh (or make environment).",
            )
            return
        rc, output = _run([str(python), "--version"])
        if rc:
            self.bad("venv", f"could not execute {python}: {output}", "Recreate it with the setup script.")
            return
        match = re.search(r"Python (\d+)\.(\d+)", output)
        if not match or (int(match.group(1)), int(match.group(2))) not in SUPPORTED_PYTHON:
            self.bad("venv", f"unsupported interpreter: {output}", "Recreate .venv with a supported Python.")
            return
        check_rc, check_output = _run([str(python), "-m", "pip", "check"])
        if check_rc:
            self.bad("venv", f"pip check failed: {check_output}", "Run the setup script to reconcile locked dependencies.")
            return
        self.good("venv", f"{output}; pip check passed")

    def _check_dockerfile_locks(self) -> tuple[str, str]:
        image = self.lock_values.get("NIEP_ALPINE_IMAGE", "")
        digest = self.lock_values.get("NIEP_ALPINE_DIGEST", "")
        reference = self.lock_values.get("NIEP_ALPINE_REFERENCE", "")
        expected_reference = f"{image}@{digest}" if image and digest else ""
        if (
            not image
            or not digest
            or not reference
            or reference != expected_reference
            or not IMAGE_REFERENCE_RE.fullmatch(reference)
        ):
            self.bad(
                "docker-image-lock",
                "Alpine lock must define one exact tag@sha256 digest reference",
                "Set NIEP_ALPINE_IMAGE, NIEP_ALPINE_DIGEST and the matching NIEP_ALPINE_REFERENCE in INSTALLATION/image-locks.env.",
            )

        for relative in (
            "tests/fixtures/containers/iperf3/Dockerfile",
            "tutorial/examples/containers/iperf3/Dockerfile",
        ):
            dockerfile = self.root / relative
            if not dockerfile.is_file():
                self.bad(
                    "dockerfile:" + relative,
                    "fixture Dockerfile is missing",
                    "Restore the checked-in Docker fixture before running integration tests.",
                )
                continue
            from_images = re.findall(r"^FROM\s+([^\s]+)", dockerfile.read_text(encoding="utf-8"), flags=re.MULTILINE)
            if expected_reference and any(candidate == expected_reference for candidate in from_images):
                self.good("dockerfile:" + relative, f"base image uses locked reference {expected_reference}")
            else:
                self.bad(
                    "dockerfile:" + relative,
                    f"base image is not the exact locked reference: {', '.join(from_images) or 'none'}",
                    f"Use FROM {expected_reference or 'alpine:3.20@sha256:<64-hex-digest>'} and update IMAGE-LOCKS.md if deliberately changing it.",
                )

        for relative in (
            "tests/fixtures/alpine-container.json",
            "tests/fixtures/alpine-router-container.json",
            "tutorial/examples/alpine-container.json",
            "tutorial/examples/alpine-router-container.json",
        ):
            descriptor = self.root / relative
            try:
                payload = json.loads(descriptor.read_text(encoding="utf-8"))
                configured_image = payload.get("IMAGE") if isinstance(payload, dict) else None
            except (OSError, ValueError, TypeError) as exc:
                self.bad(
                    "container-image:" + relative,
                    f"cannot read fixture descriptor: {exc}",
                    "Restore valid JSON for the checked-in container fixture.",
                )
                continue
            if expected_reference and configured_image == expected_reference:
                self.good(
                    "container-image:" + relative,
                    f"runtime image uses locked reference {expected_reference}",
                )
            else:
                self.bad(
                    "container-image:" + relative,
                    f"runtime image is not the exact locked reference: {configured_image!r}",
                    f"Set IMAGE to {expected_reference or 'alpine:3.20@sha256:<64-hex-digest>'}.",
                )

        return image, digest

    def _check_local_docker_images(self, docker: str) -> None:
        """Optionally check local fixture build products after an explicit request."""
        for key in ("NIEP_TEST_IMAGE", "NIEP_TUTORIAL_IMAGE"):
            local_image = self.lock_values.get(key)
            if not local_image:
                self.bad(
                    f"docker-image-{key.lower()}",
                    f"{key} is not defined in INSTALLATION/image-locks.env",
                    "Define the local image name or omit --check-local-images.",
                )
                continue
            image_rc, image_output = _run([docker, "image", "inspect", local_image])
            if image_rc:
                self.bad(
                    f"docker-image-{key.lower()}",
                    f"local build {local_image} is not present",
                    "Build it with make vm-build-test-iperf3-image or make vm-build-iperf3-image.",
                )
            else:
                self.good(f"docker-image-{key.lower()}", f"local build {local_image} is available")

    def check_docker(
        self,
        check_local_images: bool = False,
        require_locked_image: bool = False,
    ) -> None:
        image, expected = self._check_dockerfile_locks()
        locked_reference = f"{image}@{expected}" if image and expected else image
        docker = shutil.which("docker")
        if not docker:
            self.bad("docker", "docker executable is not installed", "Install docker.io and enable the Docker service.")
            return
        info_rc, info = _run([docker, "info", "--format", "{{.ServerVersion}}"])
        if info_rc:
            self.bad(
                "docker",
                f"Docker daemon is unavailable: {info}",
                "Start docker.service and add the user to the docker group, then log in again.",
            )
            return
        self.good("docker", f"client {docker}; daemon {info}")

        # Inspect the immutable reference used by the Dockerfiles. A mutable
        # local ``alpine:3.20`` tag may legitimately point at an older cached
        # image and must neither satisfy nor block this check.
        inspect_rc, inspect_output = _run(
            [docker, "image", "inspect", "--format", "{{json .RepoDigests}}", locked_reference]
        )
        if inspect_rc:
            self.bad(
                "docker-image-alpine",
                f"locked image {locked_reference} is not cached locally: {inspect_output}",
                f"Pull it with: docker pull {locked_reference}",
                required=require_locked_image,
                strict_capable=False,
            )
        else:
            try:
                digests = json.loads(inspect_output)
                if not isinstance(digests, list):
                    digests = []
            except (ValueError, TypeError):
                digests = []
            if expected and any(str(digest).endswith("@" + expected) for digest in digests):
                self.good("docker-image-alpine", f"{image} matches locked digest {expected}")
            elif expected:
                self.bad(
                    "docker-image-alpine",
                    f"{locked_reference} reports unexpected RepoDigests (local: {', '.join(digests) or 'unreported'}, expected: {expected})",
                    f"Remove the corrupt cache entry and pull: docker pull {locked_reference}",
                )
            else:
                self.bad("docker-image-alpine", "image lock has no Alpine digest", "Set a verified digest in INSTALLATION/image-locks.env.")

        if check_local_images:
            self._check_local_docker_images(docker)

    def check_libvirt(self) -> None:
        kvm = Path("/dev/kvm")
        if not kvm.exists():
            self.bad("kvm", "/dev/kvm is absent", "Enable hardware virtualization and load the KVM kernel module.")
        elif not os.access(kvm, os.R_OK | os.W_OK):
            self.bad("kvm", "/dev/kvm exists but is not accessible", "Join the kvm group or run the integration job with the required privileges.")
        else:
            self.good("kvm", f"{kvm} is accessible")

        virsh = shutil.which("virsh")
        if not virsh:
            self.bad("libvirt", "virsh executable is not installed", "Install libvirt-clients and libvirt-daemon-system.")
            return
        rc, output = _run([virsh, "--connect", "qemu:///system", "list", "--all"])
        if rc:
            self.bad("libvirt", f"system libvirt is unavailable: {output}", "Enable libvirtd and grant the user libvirt access.")
            return
        self.good("libvirt", "qemu:///system is reachable")

    def check_mininet(self) -> None:
        mn = shutil.which("mn")
        if not mn:
            self.bad("mininet", "mn executable is not installed", "Install the distro mininet package.")
            return
        rc, output = _run([mn, "--version"])
        if rc:
            rc, output = _run([mn, "--help"])
        if rc:
            self.bad("mininet", f"mn cannot run: {output}", "Install Mininet and its Open vSwitch dependencies.")
            return
        self.good("mininet", f"{mn}: {output}")

    def check_ovs(self) -> None:
        ovs_vsctl = shutil.which("ovs-vsctl")
        if not ovs_vsctl:
            self.bad(
                "openvswitch",
                "ovs-vsctl executable is not installed",
                "Install openvswitch-switch and enable openvswitch-switch.service.",
            )
            return
        version_rc, version = _run([ovs_vsctl, "--version"])
        if version_rc:
            self.bad(
                "openvswitch",
                f"ovs-vsctl cannot run: {version}",
                "Reinstall openvswitch-switch and rerun the doctor.",
            )
            return

        systemctl = shutil.which("systemctl")
        if systemctl:
            service_rc, service = _run([systemctl, "is-active", "openvswitch-switch"])
            if service_rc or service != "active":
                self.bad(
                    "openvswitch",
                    f"openvswitch-switch.service is not active: {service}",
                    "Enable and start openvswitch-switch.service, then rerun the doctor.",
                )
                return

        show_rc, show = _run([ovs_vsctl, "show"])
        if show_rc and "permission denied" not in show.lower():
            self.bad(
                "openvswitch",
                f"Open vSwitch database is unavailable: {show}",
                "Start openvswitch-switch.service and inspect its database socket.",
            )
            return
        detail = f"{_short(version)}; service active"
        if show_rc:
            detail += "; database socket requires elevated runtime permissions"
        else:
            detail += "; database is reachable"
        self.good("openvswitch", detail)

    def check_bridges(self) -> None:
        ip = shutil.which("ip")
        if not ip:
            self.bad("bridges", "iproute2 (ip) is not installed", "Install iproute2.")
            return
        bridge_tool = shutil.which("bridge") or shutil.which("brctl")
        if not bridge_tool:
            self.bad("bridges", "neither bridge (iproute2) nor brctl (bridge-utils) is installed", "Install iproute2 and bridge-utils.")
            return
        rc, output = _run([ip, "-o", "link", "show"])
        if rc:
            self.bad("bridges", f"cannot inspect links: {output}", "Install iproute2 and check host permissions.")
            return
        if re.search(r"(?:^|\s)vbrNIEP(?:@|:)", output):
            self.good("bridges", "vbrNIEP is present")
        else:
            self.bad(
                "bridges",
                "vbrNIEP is not currently present (it is created by a topology run)",
                "This is expected before the first topology; rerun the doctor after setup or inspect `ip link`.",
                required=False,
                strict_capable=False,
            )

    def check_lfs_and_qcow2(self, require_qemu_img: bool = False) -> None:
        lfs = shutil.which("git-lfs") or shutil.which("git")
        if not lfs:
            self.bad("git-lfs", "git is not installed", "Install git and git-lfs.")
        else:
            rc, output = _run([lfs, "lfs", "version"] if Path(lfs).name == "git" else [lfs, "version"])
            if rc:
                self.bad("git-lfs", f"Git LFS is unavailable: {output}", "Install git-lfs and run git lfs install.")
            else:
                self.good("git-lfs", output)

        qemu_img = shutil.which("qemu-img")
        if not qemu_img:
            self.bad(
                "qemu-img",
                "qemu-img executable is not installed",
                "Install qemu-utils; --check-images requires qemu-img to validate qcow2 images.",
                required=require_qemu_img,
            )
        for relative in EXPECTED_QCOW2:
            path = self.root / relative
            if not path.is_file():
                self.bad("image:" + relative, "file is missing", "Run git lfs install && git lfs pull --include='VEM/IMAGES/*.qcow2'.")
                continue
            try:
                with path.open("rb") as image_file:
                    head = image_file.read(160)
            except OSError as exc:
                self.bad("image:" + relative, f"cannot read file: {exc}", "Fix repository permissions and fetch the LFS object.")
                continue
            if b"git-lfs.github.com/spec" in head:
                self.bad("image:" + relative, "file is a Git LFS pointer, not a qcow2 image", "Run git lfs install && git lfs pull --include='VEM/IMAGES/*.qcow2'.")
                continue
            if not qemu_img:
                self.bad(
                    "image:" + relative,
                    f"present ({path.stat().st_size} bytes), qemu-img is unavailable for format validation",
                    "Install qemu-utils before running VM integration tests.",
                    required=require_qemu_img,
                )
                continue
            rc, output = _run([qemu_img, "info", "--output=json", str(path)], output_limit=10000)
            try:
                qemu_info = json.loads(output)
                # qemu-img reports a qcow2 as the format of the nested file
                # node when the image has a child block driver.
                image_format = qemu_info.get("format")
                if image_format != "qcow2":
                    children = qemu_info.get("children", [])
                    if children and isinstance(children[0], dict):
                        image_format = children[0].get("info", {}).get("format")
            except (ValueError, AttributeError, TypeError):
                image_format = None
            if rc or image_format != "qcow2":
                self.bad("image:" + relative, f"qemu-img rejected the image: {output}", "Fetch the complete Git LFS object and rerun make check-images.")
            else:
                self.good("image:" + relative, f"qcow2 image present ({path.stat().st_size} bytes)")

    def run(self, images_only: bool = False, check_local_images: bool = False) -> int:
        if images_only:
            self.check_lfs_and_qcow2(require_qemu_img=True)
            self.check_docker(
                check_local_images=check_local_images,
                require_locked_image=True,
            )
        else:
            self.check_python()
            self.check_venv()
            self.check_docker(check_local_images=check_local_images)
            self.check_libvirt()
            self.check_mininet()
            self.check_ovs()
            self.check_bridges()
            self.check_lfs_and_qcow2()

        failed = any(check["status"] == "FAIL" for check in self.checks)
        return 1 if failed else 0

    def render(self, as_json: bool = False) -> None:
        if as_json:
            print(json.dumps({"root": str(self.root), "strict": self.strict, "checks": self.checks}, indent=2, sort_keys=True))
            return
        print(f"NIEP doctor: {self.root}")
        for check in self.checks:
            status = check["status"]
            print(f"[{status:4}] {check['name']}: {check['detail']}")
            if status != "PASS" and check.get("remediation"):
                print(f"       -> {check['remediation']}")
        failures = sum(check["status"] == "FAIL" for check in self.checks)
        warnings = sum(check["status"] == "WARN" for check in self.checks)
        print(f"Summary: {failures} failure(s), {warnings} warning(s)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1], help="repository root")
    parser.add_argument("--strict", action="store_true", help="treat optional host prerequisites as failures")
    parser.add_argument("--check-images", action="store_true", help="only check LFS qcow2 and Docker fixture images")
    parser.add_argument(
        "--check-local-images",
        action="store_true",
        help="require both locally built iperf3 images (not checked by the normal doctor)",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)
    root = args.repo.resolve()
    if not (root / "Vagrantfile").exists():
        parser.error(f"not a NIEP repository: {root}")
    doctor = Doctor(root, strict=args.strict)
    result = doctor.run(images_only=args.check_images, check_local_images=args.check_local_images)
    doctor.render(as_json=args.json)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
