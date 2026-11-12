"""Host-only checks for the 1.2 release metadata and release artifacts."""

from __future__ import annotations

import ast
import errno
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import uuid

import pytest


pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def test_vendored_controller_imports_without_runtime_dependencies() -> None:
    # The help entry point imports the controller bootstrap without opening a
    # listening socket. Missing vendored libraries must fail in the host gate.
    environment = {
        key: value for key, value in os.environ.items()
        if not key.startswith(("COV_CORE_", "COVERAGE_"))
    }
    result = subprocess.run(
        [sys.executable, "pox.py", "--help"],
        cwd=ROOT / "OFCONTROLLERS/pox",
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_release_version_is_consistent() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package = (ROOT / "niep/__init__.py").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert 'version = "1.2.0a1"' in pyproject
    assert '__version__ = "1.2.0a1"' in package
    assert "Version: 1.2.0a1" in readme


def test_release_documentation_and_pox_baseline_are_present() -> None:
    required = (
        "CHANGELOG.md",
        "docs/migration-1.2.md",
        "docs/release-checklist.md",
        "docs/pox-provenance.md",
        "docs/adr/0001-compatibility-policy.md",
        "docs/adr/0002-vendored-pox.md",
    )
    for relative in required:
        assert (ROOT / relative).is_file(), relative

    provenance = (ROOT / "docs/pox-provenance.md").read_text(encoding="utf-8")
    assert "19802a2aaa74a8630a6dc6b0f172264d4013e8c5" in provenance
    assert "753143ddca501fb2f273bdd617bd2e557be1a114" in provenance
    assert "9014a023860e829454fffb8d7a986650fdff752c" in provenance
    assert "535355262fe9270135c16ffd63f37e63a7699657" in provenance
    assert "9d2747111abeecb5f8ec4a2e2f6eea27e9" in provenance
    assert "480b40cdf498288ae85b019026c02fe9c2c4208b800de4f134d358d01a6f3d03" in provenance
    assert "exact upstream commit or archive hash" in provenance
    assert "183 files changed" in provenance


def test_compatibility_inventory_documents_paths_surfaces_and_flag_owner() -> None:
    migration = (ROOT / "docs/migration-1.2.md").read_text(encoding="utf-8")
    paths = (
        "TOPO-MAN/Command.py",
        "TOPO-MAN/Executer.py",
        "TOPO-MAN/InfrastructureRuntime.py",
        "TOPO-MAN/Parser.py",
        "TOPO-MAN/Result.py",
        "TOPO-MAN/Service.py",
        "TOPO-MAN/SocketServer.py",
        "TOPO-MAN/Spec.py",
        "VEM/ClickOnOSv.py",
        "VEM/Container.py",
        "VEM/ContainerNetworkRuntime.py",
        "VEM/DockerRuntime.py",
        "VEM/LibvirtRuntime.py",
        "VEM/SFC.py",
        "VEM/TerminalSession.py",
        "VEM/VM.py",
        "VEM/VMImageStore.py",
        "VEM/VMNetworkRuntime.py",
        "VEM/VNF.py",
        "CLI/HTTP.py",
        "CLI/CLI.py",
        "CLI/Launcher.py",
        "tools/niepctl.py",
        "tools/niepd.py",
        "tools/niepctl",
    )
    assert all(f"`{path}`" in migration for path in paths)
    assert "LegacyExecutorAdapter" in migration
    assert "CommandDispatcher" in migration
    assert "PlanningDiagnostic.legacy_code" in migration
    assert "RuntimeFailure.type" in migration
    assert "NIEP_DISABLE_LOCAL_POX" in migration
    assert "Runtime maintainers" in migration
    assert "Release maintainers" in migration
    assert "before the first `1.3.0` release candidate" in migration


def test_setuptools_package_boundary_excludes_vendored_pox() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package_find = pyproject.split("[tool.setuptools.packages.find]", 1)[1]
    include_line = next(
        line.strip() for line in package_find.splitlines() if line.strip().startswith("include")
    )
    patterns = ast.literal_eval(include_line.split("=", 1)[1].strip())
    assert patterns
    assert all(str(pattern).startswith("niep") for pattern in patterns)
    assert (ROOT / "OFCONTROLLERS/pox/LICENSE").is_file()
    assert (ROOT / "OFCONTROLLERS/pox/NOTICE").is_file()


def test_release_checklist_installs_wheel_with_pinned_dependencies() -> None:
    checklist = (ROOT / "docs/release-checklist.md").read_text(encoding="utf-8")

    # ``--no-deps`` is valid for the build-only wheel command, but a clean
    # functional install must exercise the wheel metadata and lock runtime
    # dependencies with the release constraints.
    assert "pip wheel . --no-deps --no-build-isolation" in checklist
    assert "pip install --no-deps" not in checklist.replace("\\\n", " ")
    assert 'pip install --no-deps "$release_tmp"/wheel/*.whl' not in checklist
    assert (
        'pip install \\\n'
        '  --constraint "$release_tmp/niep-1.2.0a1/constraints/py3-linux.txt" \\\n'
        '  "$release_tmp"/wheel/*.whl'
    ) in checklist


def test_source_distribution_contains_release_material_and_pox_notices(tmp_path: Path) -> None:
    output_dir = tmp_path / "sdist"
    # Build after deliberately creating generated artifacts in recursive
    # manifest roots.  The test must protect release output even when the
    # source checkout has just run pytest or another bytecode-producing tool.
    token = uuid.uuid4().hex
    preserved = ROOT / f"tests/__pycache__/release_metadata_preserved_{token}.pyc"
    generated = (
        ROOT / f"tests/__pycache__/release_metadata_{token}.pyc",
        ROOT / f"tools/__pycache__/release_metadata_{token}.pyo",
    )
    preserved_contents = b"pre-existing bytecode"
    generated_contents = b"generated bytecode"
    created_files: list[Path] = []
    created_directories: list[Path] = []
    generated_files: list[Path] = []

    def ensure_directory(path: Path) -> None:
        missing: list[Path] = []
        cursor = path
        while not cursor.exists():
            missing.append(cursor)
            cursor = cursor.parent
        for directory in reversed(missing):
            directory.mkdir()
            created_directories.append(directory)

    try:
        output_dir.mkdir()
        created_directories.append(output_dir)
        for path in (preserved, *generated):
            ensure_directory(path.parent)
        with preserved.open("xb") as handle:
            created_files.append(preserved)
            handle.write(preserved_contents)
        for path in generated:
            with path.open("xb") as handle:
                created_files.append(path)
                generated_files.append(path)
                handle.write(generated_contents)

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import setuptools, sys; "
                        "setuptools.setup(script_args=['sdist', '--dist-dir', sys.argv[1]])"
                    ),
                    str(output_dir),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=60,
                check=False,
            )
        finally:
            for path in generated_files:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
        assert preserved.read_bytes() == preserved_contents
    finally:
        for path in created_files:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        for directory in reversed(created_directories):
            try:
                directory.rmdir()
            except OSError as error:
                if error.errno not in (errno.ENOTEMPTY, errno.EEXIST):
                    raise
    assert result.returncode == 0, result.stdout + result.stderr
    archives = tuple(output_dir.glob("niep-1.2.0a1.tar.gz"))
    assert len(archives) == 1
    with tarfile.open(archives[0], "r:gz") as archive:
        names = set(archive.getnames())

    required = {
        "CHANGELOG.md",
        "docs/migration-1.2.md",
        "docs/release-checklist.md",
        "docs/pox-provenance.md",
        "docs/adr/0001-compatibility-policy.md",
        "docs/adr/0002-vendored-pox.md",
        "LICENSE",
        "OFCONTROLLERS/pox/LICENSE",
        "OFCONTROLLERS/pox/NOTICE",
        "OFCONTROLLERS/pox/pox/lib/iter.py",
        "OFCONTROLLERS/pox/pox/lib/config_eval.py",
        "OFCONTROLLERS/pox/pox/lib/interfaceio/__init__.py",
        "OFCONTROLLERS/pox/pox/lib/ioworker/io_loop.py",
        "OFCONTROLLERS/pox/pox/lib/packet/gre.py",
        "OFCONTROLLERS/pox/pox/lib/packet/vxlan.py",
        "CLI/CLI.py",
        "CLI/HTTP.py",
        "CLI/Launcher.py",
        "tools/niepctl.py",
        "tools/niepd.py",
        "tools/niepctl",
        "TOPO-MAN/Command.py",
        "VEM/VNF.py",
        "tests/unit/test_release_metadata.py",
        "tests/unit/application/test_legacy_surfaces.py",
    }
    root = "niep-1.2.0a1/"
    assert {root + relative for relative in required} <= names
    assert not any(name.endswith(".qcow2") for name in names)
    assert not any("/__pycache__/" in f"/{name}" for name in names)
    assert not any(name.endswith((".pyc", ".pyo")) for name in names)
    assert not any(
        name in {root + "REFATORACOES.md", root + "notes.md"}
        or name.startswith((root + "plano-refatoracao/", root + "plano-finalizacao-refatoracao/"))
        for name in names
    )
