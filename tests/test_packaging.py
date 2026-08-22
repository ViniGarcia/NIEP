"""Acceptance tests for the package/import boundary introduced by task 03.

These tests deliberately execute the package in a child interpreter.  An
in-process import can accidentally pass because pytest has already put the
repository root (or one of the legacy source directories) on ``sys.path``.
"""

from __future__ import annotations

import ast
import importlib
import importlib.metadata
import importlib.util
import os
from pathlib import Path
import shutil
import site
import subprocess
import sys
import textwrap
import zipfile

import pytest


pytestmark = [pytest.mark.unit, pytest.mark.contract]

ROOT = Path(__file__).resolve().parents[1]
LEGACY_RESULT = ROOT / "TOPO-MAN" / "Result.py"
LEGACY_SPEC = ROOT / "TOPO-MAN" / "Spec.py"
LEGACY_RUNTIME = ROOT / "VEM" / "TerminalSession.py"

# Result and Spec are the first neutral modules migrated by task 03.  Keeping
# this list explicit makes a missing public module an actionable failure,
# instead of silently testing only ``import niep``.
PUBLIC_MODULES = (
    "niep",
    "niep.domain",
    "niep.domain.result",
    "niep.domain.spec",
    "niep.application",
    "niep.application.parser",
    "niep.interfaces",
    "niep.runtime",
)


def _subprocess_environment() -> dict[str, str]:
    """Run children as installed consumers, without checkout bootstrap state."""

    environment = os.environ.copy()
    old_pythonpath = environment.get("PYTHONPATH", "")
    paths = []
    for value in old_pythonpath.split(os.pathsep):
        if not value:
            continue
        try:
            candidate = Path(value).resolve()
        except OSError:
            candidate = Path(value)
        if candidate == ROOT or ROOT in candidate.parents:
            continue
        paths.append(value)
    if paths:
        environment["PYTHONPATH"] = os.pathsep.join(paths)
    else:
        environment.pop("PYTHONPATH", None)
    for name in tuple(environment):
        if name.startswith(("COVERAGE_", "COV_CORE_")) or name in {
            "PYTEST_CURRENT_TEST",
            "PYTEST_ADDOPTS",
        }:
            environment.pop(name, None)
    return environment


def _run_python(code: str, cwd: Path, *, timeout: float = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=cwd,
        env=_subprocess_environment(),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _failure_details(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(
        part
        for part in (
            f"returncode={result.returncode}",
            result.stdout,
            result.stderr,
        )
        if part
    )


def _current_site_packages() -> Path:
    """Return the active test interpreter's site-packages directory.

    The isolated wheel interpreter may borrow installed runtime dependencies,
    but it must not borrow the editable source-tree package.  Adding this
    directory to ``PYTHONPATH`` exposes its importable dependencies while
    deliberately not processing its ``.pth`` files (including the editable
    ``niep`` link).
    """

    candidates = [Path(value) for value in site.getsitepackages()]
    user_site = Path(site.getusersitepackages())
    if user_site not in candidates:
        candidates.append(user_site)
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise AssertionError(f"could not locate site-packages for {sys.executable}")


def test_public_modules_import_from_a_cwd_outside_the_checkout(tmp_path: Path) -> None:
    """The installed/editable package must not resolve modules relative to cwd."""

    result = _run_python(
        """
        import importlib

        for module_name in (
            "niep",
            "niep.domain",
            "niep.domain.result",
            "niep.domain.spec",
            "niep.application",
            "niep.application.parser",
            "niep.interfaces",
            "niep.runtime",
        ):
            importlib.import_module(module_name)
        """,
        tmp_path,
    )
    assert result.returncode == 0, _failure_details(result)


def test_neutral_public_import_does_not_load_host_runtimes(tmp_path: Path) -> None:
    """Importing the package/domain layer is safe on a host without runtimes."""

    result = _run_python(
        """
        import importlib
        import sys

        heavy_roots = {"docker", "libvirt", "mininet"}

        class BlockHeavyImports:
            def find_spec(self, fullname, path=None, target=None):
                root = fullname.split(".", 1)[0]
                if root in heavy_roots:
                    raise AssertionError(
                        f"neutral package import attempted to load {fullname}"
                    )
                return None

        sys.meta_path.append(BlockHeavyImports())
        for module_name in ("niep", "niep.domain", "niep.domain.result", "niep.domain.spec"):
            importlib.import_module(module_name)

        loaded_heavy = sorted(
            name
            for name in sys.modules
            if name.split(".", 1)[0] in heavy_roots
        )
        assert not loaded_heavy, loaded_heavy
        """,
        tmp_path,
    )
    assert result.returncode == 0, _failure_details(result)


def _console_scripts() -> dict[str, importlib.metadata.EntryPoint]:
    entries = importlib.metadata.entry_points()
    if hasattr(entries, "select"):
        entries = entries.select(group="console_scripts")
    else:  # pragma: no cover - compatibility with pre-3.10 importlib.metadata
        entries = entries.get("console_scripts", ())
    return {entry.name: entry for entry in entries}


@pytest.mark.parametrize("entrypoint_name", ("niepd", "niepctl"))
def test_console_entrypoint_help_works_from_another_cwd(
    tmp_path: Path, entrypoint_name: str
) -> None:
    """The installed console entry points must start before touching a daemon."""

    entrypoint = _console_scripts().get(entrypoint_name)
    assert entrypoint is not None, f"missing console_scripts entry point: {entrypoint_name}"

    executable = shutil.which(entrypoint_name)
    if executable is None:
        # ``pytest`` is often invoked as ``.venv/bin/python -m pytest``
        # without activating the environment, so its script directory may
        # not be present in PATH even though the entry point is installed.
        sibling = Path(sys.executable).with_name(entrypoint_name)
        if sibling.is_file():
            executable = str(sibling)
    assert executable, (
        f"{entrypoint_name!r} is declared but no executable is installed; "
        "install the project in editable mode before running packaging tests"
    )
    result = subprocess.run(
        [executable, "--help"],
        cwd=tmp_path,
        env=_subprocess_environment(),
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, _failure_details(result)
    help_output = (result.stdout + result.stderr).lower()
    assert any(token in help_output for token in ("usage", "options", "commands", "help"))


def test_legacy_niepctl_shim_help_works_from_another_cwd(tmp_path: Path) -> None:
    """The documented shell shim remains usable while callers migrate."""

    shim = ROOT / "tools" / "niepctl"
    assert shim.is_file()
    result = subprocess.run(
        [str(shim), "--help"],
        cwd=tmp_path,
        env=_subprocess_environment(),
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, _failure_details(result)
    help_output = (result.stdout + result.stderr).lower()
    assert any(token in help_output for token in ("usage", "options", "commands", "help"))


def test_distribution_does_not_bundle_vendored_pox(tmp_path: Path) -> None:
    """The package configuration and (when available) wheel exclude POX."""

    # The include rule is the source-of-truth for setuptools package
    # discovery.  This assertion keeps the test useful even in a minimal
    # test environment that has pytest but not the build backend installed.
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package_find = pyproject.split("[tool.setuptools.packages.find]", 1)[1]
    include_line = next(
        line.strip() for line in package_find.splitlines() if line.strip().startswith("include")
    )
    include_patterns = ast.literal_eval(include_line.split("=", 1)[1].strip())
    assert include_patterns
    assert all(str(pattern).startswith("niep") for pattern in include_patterns)
    assert not any(
        part.lower() in {"pox", "ofcontrollers"}
        for path in (ROOT / "niep").rglob("*")
        for part in path.relative_to(ROOT).parts
    )

    wheel_dir = tmp_path / "wheel"
    wheel_dir.mkdir()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            str(ROOT),
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_dir),
        ],
        cwd=tmp_path,
        env=_subprocess_environment(),
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, _failure_details(result)

    wheels = sorted(wheel_dir.glob("*.whl"))
    assert len(wheels) == 1, f"expected one built wheel, found {wheels!r}"
    with zipfile.ZipFile(wheels[0]) as archive:
        members = archive.namelist()

    assert any(member.startswith("niep/") for member in members)
    assert not any(
        part.lower() in {"pox", "ofcontrollers"}
        for member in members
        for part in Path(member).parts
    ), "vendored POX must remain outside the main distribution"

    # Install the wheel into an isolated interpreter and import it without a
    # checkout path.  Inspecting the archive alone would miss accidental
    # reliance on the editable source tree.
    venv_dir = tmp_path / "wheel-venv"
    create_venv = subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        cwd=tmp_path,
        env=_subprocess_environment(),
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert create_venv.returncode == 0, _failure_details(create_venv)
    venv_python = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    install = subprocess.run(
        [str(venv_python), "-m", "pip", "install", "--no-deps", str(wheels[0])],
        cwd=tmp_path,
        env=_subprocess_environment(),
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert install.returncode == 0, _failure_details(install)
    imported_environment = _subprocess_environment()
    # The temporary venv intentionally has only the project wheel.  Make the
    # runtime dependencies from this test venv visible without installing
    # anything from the network.  A site-packages directory supplied through
    # PYTHONPATH does not process its .pth files, so the editable checkout
    # link cannot make the source tree win module resolution.
    imported_environment["PYTHONPATH"] = str(_current_site_packages())
    imported_environment["NIEP_ROOT"] = str(ROOT)
    imported_environment["NIEP_EXPECTED_VERSION"] = importlib.metadata.version("niep")
    imported = subprocess.run(
        [
            str(venv_python),
            "-c",
            textwrap.dedent(
                """
                import importlib.metadata
                import os
                from pathlib import Path
                import subprocess
                import sys

                import niep
                assert importlib.metadata.version("niep") == os.environ["NIEP_EXPECTED_VERSION"]
                niep_file = Path(niep.__file__).resolve()
                assert Path(sys.prefix).resolve() in niep_file.parents, niep_file
                assert Path(os.environ["NIEP_ROOT"]).resolve() not in niep_file.parents, niep_file
                assert "OFCONTROLLERS" not in str(niep_file)
                import niep.application.parser

                for command in ("niepctl", "niepd"):
                    executable = Path(sys.executable).with_name(
                        command + (".exe" if os.name == "nt" else "")
                    )
                    help_result = subprocess.run(
                        [str(executable), "--help"],
                        text=True,
                        capture_output=True,
                        timeout=10,
                    )
                    assert help_result.returncode == 0, (
                        command,
                        help_result.stdout,
                        help_result.stderr,
                    )
                    assert any(
                        token in (help_result.stdout + help_result.stderr).lower()
                        for token in ("usage", "options", "help")
                    ), command
                """
            ),
        ],
        cwd=tmp_path,
        env=imported_environment,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert imported.returncode == 0, _failure_details(imported)


def _load_legacy_module(name: str, path: Path):
    module_spec = importlib.util.spec_from_file_location(name, path)
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    # The current legacy files replace their module entry with the new module
    # object (a compatibility-shim pattern), so return the registered object
    # when that happened instead of the temporary loader object.
    return sys.modules.get(name, module)


def _import_first_available(*names: str):
    for name in names:
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as exc:
            # A missing candidate is fine; a dependency failure inside a
            # candidate is not and should be reported by the test.
            if exc.name not in {name, name.rsplit(".", 1)[0]}:
                raise
    raise AssertionError(f"none of the public module paths exists: {names!r}")


def test_legacy_shims_warn_and_preserve_module_identity() -> None:
    cases = (
        ("niep_warning_result", LEGACY_RESULT, "niep.domain.result", "niep.domain.result"),
        ("niep_warning_spec", LEGACY_SPEC, "niep.domain.spec", "niep.domain.spec"),
        (
            "niep_warning_runtime",
            LEGACY_RUNTIME,
            "niep.runtime.terminal_session",
            "niep.runtime.terminal_session",
        ),
    )
    for name, path, modern_name, alternative in cases:
        with pytest.warns(DeprecationWarning, match="use " + alternative):
            legacy = _load_legacy_module(name, path)
        assert legacy is importlib.import_module(modern_name)


def test_result_and_spec_keep_legacy_wire_shapes() -> None:
    """New neutral paths preserve the old Result/Spec data contracts."""

    with pytest.warns(DeprecationWarning, match="use niep.domain.result"):
        legacy_result = _load_legacy_module("niep_legacy_result", LEGACY_RESULT)
    modern_result = _import_first_available("niep.domain.result", "niep.result")
    assert legacy_result is modern_result
    result_type = getattr(modern_result, "ServiceResult", None)
    if result_type is None:
        result_type = getattr(modern_result, "Result", None)
    assert result_type is not None, "the new Result module must expose a result type"

    legacy_value = legacy_result.ServiceResult.success(
        legacy_result.ResultCode.STATUS,
        message="ready",
        data={"items": ["a", 2]},
        status=0,
    )
    if hasattr(result_type, "success"):
        modern_value = result_type.success(
            "status", message="ready", data={"items": ["a", 2]}, status=0
        )
    else:
        modern_value = result_type(
            ok=True,
            code="status",
            message="ready",
            data={"items": ["a", 2]},
            status=0,
        )
    assert modern_value.to_dict() == legacy_value.to_dict()

    with pytest.warns(DeprecationWarning, match="use niep.domain.spec"):
        legacy_spec = _load_legacy_module("niep_legacy_spec", LEGACY_SPEC)
    modern_spec = _import_first_available("niep.domain.spec", "niep.spec")
    assert legacy_spec is modern_spec
    spec_type = getattr(modern_spec, "InterfaceSpec", None)
    assert spec_type is not None, "the new Spec module must expose InterfaceSpec"
    interface_data = {
        "ID": "eth0",
        "MAC": "02:00:00:00:00:01",
        "IP": "192.0.2.10/24",
        "LINK_MAC": "02:00:00:00:00:02",
    }
    assert spec_type.from_dict(interface_data).to_dict() == (
        legacy_spec.InterfaceSpec.from_dict(interface_data).to_dict()
    )


def _maintained_python_files() -> list[Path]:
    """Return maintained application and test code, excluding vendored code."""

    roots = ("niep", "CLI", "TOPO-MAN", "VEM", "tools", "tests")
    files: list[Path] = []
    for root_name in roots:
        root = ROOT / root_name
        if root.is_dir():
            files.extend(path for path in root.rglob("*.py") if path.is_file())
    return sorted(files)


def _path_insert_violations(path: Path, tree: ast.AST) -> list[str]:
    sys_aliases = {alias.asname or "sys" for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names if alias.name == "sys"}
    path_aliases = {
        alias.asname or "path"
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "sys"
        for alias in node.names
        if alias.name == "path"
    }
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "insert":
            continue
        target = node.func.value
        direct = (
            isinstance(target, ast.Attribute)
            and target.attr == "path"
            and isinstance(target.value, ast.Name)
            and target.value.id in sys_aliases
        )
        imported_path = isinstance(target, ast.Name) and target.id in path_aliases
        if direct or imported_path:
            violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    return violations


def test_maintained_code_has_no_sys_path_insert_or_wildcard_imports() -> None:
    """Legacy bootstrap hacks must not leak into the maintained source tree."""

    path_insert_violations: list[str] = []
    wildcard_violations: list[str] = []
    syntax_violations: list[str] = []
    for path in _maintained_python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:  # report it alongside the static violations
            syntax_violations.append(f"{path.relative_to(ROOT)}:{exc.lineno}")
            continue
        path_insert_violations.extend(_path_insert_violations(path, tree))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
                wildcard_violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")

    assert not syntax_violations, f"syntax errors in maintained code: {syntax_violations}"
    assert not path_insert_violations, (
        "sys.path.insert/path.insert remains in maintained code: "
        + repr(path_insert_violations)
    )
    assert not wildcard_violations, (
        "wildcard imports remain in maintained code: " + repr(wildcard_violations)
    )
