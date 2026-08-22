"""Host-only test support for optional NIEP dependencies.

The legacy modules keep their historical imports for now.  This helper makes
the parser and service checks importable on a developer host where Docker,
libvirt, and Mininet are not installed.  It deliberately provides no fake
resources: tests still need to inject their own runtimes when they exercise a
resource operation.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _add_legacy_paths() -> None:
    for directory in (ROOT / "TOPO-MAN", ROOT / "VEM"):
        value = str(directory)
        if value not in sys.path:
            sys.path.insert(0, value)


def _install_docker_import_stub() -> None:
    """Make ``VEM/DockerRuntime.py`` importable without the docker package."""

    if "docker" in sys.modules:
        return
    try:
        __import__("docker")
    except ImportError:
        docker = types.ModuleType("docker")
        errors = types.ModuleType("docker.errors")

        class DockerException(Exception):
            pass

        class APIError(DockerException):
            pass

        class ImageNotFound(DockerException):
            pass

        class NotFound(DockerException):
            pass

        errors.DockerException = DockerException
        errors.APIError = APIError
        errors.ImageNotFound = ImageNotFound
        errors.NotFound = NotFound
        docker.errors = errors
        docker.DockerException = DockerException
        docker.from_env = lambda **_kwargs: (_ for _ in ()).throw(
            DockerException("Docker package is unavailable in host-only tests")
        )
        sys.modules["docker"] = docker
        sys.modules["docker.errors"] = errors


def _install_libvirt_import_stub() -> None:
    """Avoid registering handlers or opening a libvirt connection at import."""

    if "libvirt" in sys.modules:
        return
    libvirt = types.ModuleType("libvirt")
    libvirt.VIR_DOMAIN_RUNNING = 1
    libvirt.VIR_DOMAIN_BLOCKED = 2
    libvirt.VIR_DOMAIN_PAUSED = 3
    libvirt.libvirtError = type("libvirtError", (Exception,), {})
    libvirt.registerErrorHandler = lambda *_args: None

    class _UnavailableConnection:
        def lookupByName(self, _domain_name):
            raise libvirt.libvirtError("libvirt is unavailable in host-only tests")

        def defineXML(self, _domain_xml):
            raise libvirt.libvirtError("libvirt is unavailable in host-only tests")

    libvirt.open = lambda *_args, **_kwargs: _UnavailableConnection()
    sys.modules["libvirt"] = libvirt


def _install_requests_import_stub() -> None:
    """Allow Click-on-OSv adapters to load without the requests package."""

    if "requests" in sys.modules:
        return
    try:
        __import__("requests")
    except ImportError:
        requests = types.ModuleType("requests")

        def unavailable(*_args, **_kwargs):
            raise RuntimeError("requests is unavailable in host-only tests")

        requests.get = unavailable
        requests.post = unavailable
        sys.modules["requests"] = requests


def _install_mininet_import_stub() -> None:
    """Provide import-only Mininet classes; no network object is created."""

    if "mininet" in sys.modules:
        return

    mininet = types.ModuleType("mininet")
    net = types.ModuleType("mininet.net")
    node = types.ModuleType("mininet.node")
    link = types.ModuleType("mininet.link")
    clean = types.ModuleType("mininet.clean")

    class Mininet:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("Mininet is unavailable in host-only tests")

    class Cleanup:
        def cleanup(self):
            return None

    class _Unavailable:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("Mininet is unavailable in host-only tests")

    net.Mininet = Mininet
    node.Host = _Unavailable
    node.Switch = _Unavailable
    node.OVSSwitch = _Unavailable
    node.Controller = _Unavailable
    node.RemoteController = _Unavailable
    link.Link = _Unavailable
    link.Intf = _Unavailable
    clean.Cleanup = Cleanup

    mininet.net = net
    mininet.node = node
    mininet.link = link
    mininet.clean = clean
    sys.modules.update(
        {
            "mininet": mininet,
            "mininet.net": net,
            "mininet.node": node,
            "mininet.link": link,
            "mininet.clean": clean,
        }
    )


def install_optional_dependency_stubs() -> None:
    """Install import-only dependency shims and load the neutral parser once."""

    _add_legacy_paths()
    _install_docker_import_stub()
    _install_libvirt_import_stub()
    _install_requests_import_stub()
    _install_mininet_import_stub()

    # Loading this module here ensures legacy teardown checks cannot replace
    # the real parser with their historical placeholder in this pytest process.
    if "Parser" not in sys.modules:
        __import__("Parser")


install_optional_dependency_stubs()
