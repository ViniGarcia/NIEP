"""Alpine descriptors use the existing VM lifecycle and private-disk mechanism."""
from pathlib import Path
import shutil
from xml.etree import ElementTree

import pytest

from niep.application.loader import TopologyLoader
from niep.application.validator import TopologyValidator
from niep.runtime.vm import VM
from niep.runtime.vm_image_store import VMImageStore
from .fakes import FakeVMComputeRuntime, FakeVMNetworkRuntime

pytestmark = pytest.mark.contract
IMAGE_SOURCE = Path(__file__).resolve().parents[3] / "benchmarks/images/alpine-http"


def test_alpine_topology_creates_independent_disks_and_compatible_xml(tmp_path):
    loader = TopologyLoader()
    document = loader.load(str(IMAGE_SOURCE / "example/topology.json"))
    result = TopologyValidator(loader).validate(document)
    assert not result.issues
    assert len(result.value.vms) == 1

    images = tmp_path / "IMAGES"
    images.mkdir()
    base = images / "alpine-http.qcow2"
    base.write_bytes(b"base-disk")
    base.chmod(0o444)
    shutil.copyfile(IMAGE_SOURCE.parents[2] / "VEM/IMAGES/alpine-http.xml", images / "alpine-http.xml")
    store = VMImageStore(str(tmp_path))
    clones = []
    for identifier in ("clone-a", "clone-b"):
        runtime = FakeVMComputeRuntime()
        vm = VM(str(IMAGE_SOURCE / "example/vm.json"), identifier, None,
                runtime=runtime, image_store=store, network=FakeVMNetworkRuntime())
        assert vm.VM_STATUS == 0
        assert vm.createVM() == 0
        assert vm.modifyValidation() == 1
        xml = ElementTree.parse(store.instance_xml_path(identifier, "alpine-http"))
        assert xml.findtext("name") == identifier
        assert xml.findtext("memory") == str(256 * 1024)
        assert xml.find("devices/disk/source").get("file") == store.instance_disk_path(identifier, "alpine-http")
        assert xml.find("devices/interface/mac").get("address") == vm.MANAGEMENT_MAC
        assert xml.find("devices/interface/address").get("slot") == "0x03"
        assert len(xml.findall("devices/interface")) == 2
        assert vm.upVM() == 0
        assert runtime.calls[0][0] == "define_and_create"
        clones.append(vm)

    Path(store.instance_disk_path("clone-a", "alpine-http")).write_bytes(b"changed")
    assert Path(store.instance_disk_path("clone-b", "alpine-http")).read_bytes() == b"base-disk"
    assert base.read_bytes() == b"base-disk"
    for vm in clones:
        assert vm.cleanupVM() == 0
        assert vm.destroyVM() == 0
        assert not Path(store.instance_path(vm.ID)).exists()
    assert base.exists()
