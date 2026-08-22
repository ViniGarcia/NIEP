"""Host-only checks for the NIEP environment doctor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import pytest

from tools import niep_doctor


pytestmark = [pytest.mark.unit, pytest.mark.contract]

ALPINE_TAG = "alpine:3.20"
ALPINE_DIGEST = "sha256:" + "c64c687cbea9300178b30c95835354e34c4e4febc4badfe27102879de0483b5e"
ALPINE_REFERENCE = f"{ALPINE_TAG}@{ALPINE_DIGEST}"
DOCKERFILES = (
    Path("tests/fixtures/containers/iperf3/Dockerfile"),
    Path("tutorial/examples/containers/iperf3/Dockerfile"),
)
CONTAINER_DESCRIPTORS = (
    Path("tests/fixtures/alpine-container.json"),
    Path("tests/fixtures/alpine-router-container.json"),
    Path("tutorial/examples/alpine-container.json"),
    Path("tutorial/examples/alpine-router-container.json"),
)


def _fake_repo(root: Path, *, dockerfile_reference: str = ALPINE_REFERENCE) -> None:
    """Create only the files needed by Docker lock checks in a temp repo."""
    (root / "Vagrantfile").write_text("# test repository\n", encoding="utf-8")
    installation = root / "INSTALLATION"
    installation.mkdir()
    (installation / "image-locks.env").write_text(
        "\n".join(
            (
                f"NIEP_ALPINE_IMAGE={ALPINE_TAG}",
                f"NIEP_ALPINE_DIGEST={ALPINE_DIGEST}",
                f"NIEP_ALPINE_REFERENCE={ALPINE_REFERENCE}",
                "NIEP_TEST_IMAGE=niep/iperf3-test:local",
                "NIEP_TUTORIAL_IMAGE=niep/iperf3:local",
                "",
            )
        ),
        encoding="utf-8",
    )
    for relative in DOCKERFILES:
        dockerfile = root / relative
        dockerfile.parent.mkdir(parents=True, exist_ok=True)
        dockerfile.write_text(f"FROM {dockerfile_reference}\n", encoding="utf-8")
    for relative in CONTAINER_DESCRIPTORS:
        descriptor = root / relative
        descriptor.parent.mkdir(parents=True, exist_ok=True)
        descriptor.write_text(
            json.dumps({"ID": "locked-fixture", "IMAGE": ALPINE_REFERENCE}),
            encoding="utf-8",
        )


def _checks_by_name(doctor: niep_doctor.Doctor) -> dict[str, dict[str, object]]:
    return {check["name"]: check for check in doctor.checks}


def test_dockerfiles_must_match_exact_locked_tag_and_digest(tmp_path: Path) -> None:
    """A mutable tag or a different digest must be rejected for every fixture."""
    _fake_repo(tmp_path)

    matching = niep_doctor.Doctor(tmp_path)
    matching._check_dockerfile_locks()
    checks = _checks_by_name(matching)
    assert checks["dockerfile:tests/fixtures/containers/iperf3/Dockerfile"]["status"] == "PASS"
    assert checks["dockerfile:tutorial/examples/containers/iperf3/Dockerfile"]["status"] == "PASS"

    (tmp_path / DOCKERFILES[0]).write_text(f"FROM {ALPINE_TAG}\n", encoding="utf-8")
    mismatching = niep_doctor.Doctor(tmp_path)
    mismatching._check_dockerfile_locks()
    checks = _checks_by_name(mismatching)
    assert checks["dockerfile:tests/fixtures/containers/iperf3/Dockerfile"]["status"] == "FAIL"
    assert checks["dockerfile:tutorial/examples/containers/iperf3/Dockerfile"]["status"] == "PASS"

    (tmp_path / CONTAINER_DESCRIPTORS[0]).write_text(
        json.dumps({"ID": "mutable-fixture", "IMAGE": ALPINE_TAG}),
        encoding="utf-8",
    )
    mutable_descriptor = niep_doctor.Doctor(tmp_path)
    mutable_descriptor._check_dockerfile_locks()
    checks = _checks_by_name(mutable_descriptor)
    assert checks["container-image:tests/fixtures/alpine-container.json"]["status"] == "FAIL"


def test_check_images_requires_qemu_img(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The image-only mode cannot pass without qemu-img format validation."""
    _fake_repo(tmp_path)
    doctor = niep_doctor.Doctor(tmp_path)
    monkeypatch.setattr(niep_doctor, "EXPECTED_QCOW2", ())
    monkeypatch.setattr(niep_doctor.shutil, "which", lambda _name: None)
    monkeypatch.setattr(niep_doctor, "_run", lambda *_args, **_kwargs: (0, ""))
    monkeypatch.setattr(doctor, "check_docker", lambda **_kwargs: None)

    result = doctor.run(images_only=True)

    assert result == 1
    assert _checks_by_name(doctor)["qemu-img"]["status"] == "FAIL"


def _fake_docker_run(command: list[str], **_kwargs: object) -> tuple[int, str]:
    """Answer only the Docker calls made by ``Doctor.check_docker``."""
    if command[1:3] == ["info", "--format"]:
        return 0, "29.5.0"
    if command[1:4] == ["image", "inspect", "--format"] and command[-1] == ALPINE_REFERENCE:
        return 0, json.dumps([f"alpine@{ALPINE_DIGEST}"])
    if command[1:3] == ["image", "inspect"]:
        return 1, "image not found"
    raise AssertionError(f"unexpected command: {command}")


def _stub_non_docker_checks(doctor: niep_doctor.Doctor, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the local-image option test independent from host prerequisites."""
    no_op: Callable[..., None] = lambda *_args, **_kwargs: None
    for name in (
        "check_python",
        "check_venv",
        "check_libvirt",
        "check_mininet",
        "check_ovs",
        "check_bridges",
        "check_lfs_and_qcow2",
    ):
        monkeypatch.setattr(doctor, name, no_op)


def test_check_local_images_is_explicit_and_required_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Explicit local-image checking fails for absent build products."""
    _fake_repo(tmp_path)
    monkeypatch.setattr(niep_doctor.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    monkeypatch.setattr(niep_doctor, "_run", _fake_docker_run)

    explicit = niep_doctor.Doctor(tmp_path)
    _stub_non_docker_checks(explicit, monkeypatch)
    assert explicit.run(check_local_images=True) == 1
    explicit_checks = _checks_by_name(explicit)
    assert explicit_checks["docker-image-niep_test_image"]["status"] == "FAIL"
    assert explicit_checks["docker-image-niep_tutorial_image"]["status"] == "FAIL"

    normal = niep_doctor.Doctor(tmp_path)
    _stub_non_docker_checks(normal, monkeypatch)
    assert normal.run() == 0
    normal_checks = _checks_by_name(normal)
    assert "docker-image-niep_test_image" not in normal_checks
    assert "docker-image-niep_tutorial_image" not in normal_checks
