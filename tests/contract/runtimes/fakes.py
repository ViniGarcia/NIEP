"""Deterministic capability fakes shared by runtime contract tests."""

from __future__ import annotations


class FakeComputeRuntime:
    def __init__(self):
        self.resources = {}
        self.calls = []

    def create(self, resource_id, value=None, **kwargs):
        self.calls.append(("create", resource_id, value, kwargs))
        self.resources[resource_id] = {"value": value, "running": False}
        return resource_id

    def start(self, resource, **kwargs):
        self.calls.append(("start", resource, kwargs))
        self.resources.setdefault(resource, {})["running"] = True
        return resource

    def stop(self, resource, **kwargs):
        self.calls.append(("stop", resource, kwargs))
        self.resources.setdefault(resource, {})["running"] = False
        return resource

    def remove(self, resource, **kwargs):
        self.calls.append(("remove", resource, kwargs))
        self.resources.pop(resource, None)

    def inspect(self, resource_id, **kwargs):
        self.calls.append(("inspect", resource_id, kwargs))
        if resource_id not in self.resources:
            raise KeyError(resource_id)
        return self.resources[resource_id]


class FakeContainerComputeRuntime:
    def __init__(self):
        self.container = type("ContainerHandle", (), {"name": "fake-container", "status": "created", "attrs": {"State": {"Pid": 1}}})()
        self.calls = []
        self.present = False

    def create(self, resource_id, image, command, *args, **kwargs):
        self.calls.append(("create", resource_id, image, command, args, kwargs))
        self.present = True
        self.container.name = resource_id
        return self.container

    def start(self, resource, *args, **kwargs):
        self.calls.append(("start", resource, args, kwargs))
        resource.status = "running"
        return resource

    def stop(self, resource, *args, **kwargs):
        self.calls.append(("stop", resource, args, kwargs))
        resource.status = "exited"
        return resource

    def remove(self, resource, *args, **kwargs):
        self.calls.append(("remove", resource, args, kwargs))
        self.present = False

    def inspect(self, resource_id, *args, **kwargs):
        self.calls.append(("inspect", resource_id, args, kwargs))
        if not self.present:
            raise KeyError(resource_id)
        return self.container

    def exists(self, resource_id):
        self.calls.append(("exists", resource_id))
        return self.present

    def lookup(self, resource_id):
        self.calls.append(("lookup", resource_id))
        return self.container

    def is_running(self, resource_id):
        return self.present and self.container.status == "running"

    def exec(self, resource_id, command):
        return 0, ""

    def open_interactive_exec(self, resource_id, command):
        return object()


class FakeContainerNetworkRuntime:
    def __init__(self):
        self.calls = []

    def prepare(self, resource, *args, **kwargs):
        self.calls.append(("prepare", resource, args, kwargs))

    def attach(self, resource, interfaces):
        self.calls.append(("attach", resource, interfaces))

    def detach(self, interfaces):
        self.calls.append(("detach", interfaces))

    def cleanup(self, interfaces):
        self.calls.append(("cleanup", interfaces))

    def setup_interfaces(self, container, interfaces):
        self.calls.append(("setup_interfaces", container, interfaces))

    def release_interfaces(self, interfaces):
        self.calls.append(("release_interfaces", interfaces))

    def interface_exists(self, interface_id):
        return False

    def delete_interface(self, interface_id):
        return None

    def container_pid(self, container):
        return "1"


class FakeVMComputeRuntime:
    def __init__(self):
        self.domain = type("DomainHandle", (), {"name": "fake-vm"})()
        self.calls = []
        self.present = False
        self.running = False

    def create(self, *args, **kwargs):
        return self.define_and_create(*args, **kwargs)

    def start(self, resource, *args, **kwargs):
        self.running = True
        return 0

    def stop(self, resource, *args, **kwargs):
        self.running = False
        return 0

    def remove(self, resource, *args, **kwargs):
        self.present = False
        return 0

    def inspect(self, resource_id, *args, **kwargs):
        return self.lookup(resource_id)

    def exists(self, resource_id):
        return self.present

    def lookup(self, resource_id):
        return self.domain

    def is_running(self, resource_id):
        return self.running

    def define_and_create(self, resource_id, domain_xml):
        self.calls.append(("define_and_create", resource_id, domain_xml))
        self.present = True
        self.running = True
        self.domain.name = resource_id
        return self.domain

    def destroy(self, resource):
        self.running = False
        self.calls.append(("destroy", resource))
        return 0

    def undefine(self, resource):
        self.present = False
        self.calls.append(("undefine", resource))
        return 0


class FakeVMImageStore:
    def __init__(self):
        self.present = False
        self.calls = []

    def validate(self, image):
        self.calls.append(("validate", image))
        return image

    def instantiate(self, instance, image):
        self.calls.append(("instantiate", instance, image))
        self.present = True
        return instance

    def create_instance(self, instance, image):
        self.calls.append(("create_instance", instance, image))
        self.present = True
        return instance

    def remove(self, instance):
        self.calls.append(("remove", instance))
        self.present = False

    def remove_instance(self, instance):
        self.calls.append(("remove_instance", instance))
        self.present = False

    def base_disk_exists(self, image):
        return True

    def instance_exists(self, instance):
        return self.present

    def base_disk_path(self, image):
        return image

    def template_xml_path(self, image):
        return image + ".xml"

    def instance_path(self, instance):
        return instance

    def instance_disk_path(self, instance, image):
        return instance + "/" + image

    def instance_xml_path(self, instance, image):
        return instance + "/" + image + ".xml"

    def copy_template_xml(self, instance, image):
        self.calls.append(("copy_template_xml", instance, image))

    def read_domain_xml(self, instance, image):
        return "<domain><name>" + instance + "</name></domain>"


class FakeVMNetworkRuntime:
    def __init__(self):
        self.calls = []

    def prepare(self, interfaces):
        self.calls.append(("prepare", interfaces))

    def attach(self, interfaces):
        self.calls.append(("attach", interfaces))

    def detach(self, interfaces):
        self.calls.append(("detach", interfaces))

    def cleanup(self, interfaces):
        self.calls.append(("cleanup", interfaces))

    def prepare_interfaces(self, interfaces):
        self.calls.append(("prepare_interfaces", interfaces))

    def release_interfaces(self, interfaces):
        self.calls.append(("release_interfaces", interfaces))

    def bridge_lines(self):
        return []

    def bridge_exists(self, bridge_id):
        return False

    def create_bridge(self, bridge_id, mac):
        return None

    def enable_bridge(self, bridge_id):
        return None

    def disable_bridge(self, bridge_id):
        return 0

    def delete_bridge(self, bridge_id):
        return 0

    def management_ip(self, management_mac):
        return None

    def ssh(self, user, passwd, management_ip):
        return 0


class FakeNetworkRuntime:
    def __init__(self):
        self.attached = set()
        self.calls = []

    def prepare(self, resource, **kwargs):
        self.calls.append(("prepare", resource, kwargs))
        return resource

    def attach(self, resource, **kwargs):
        self.calls.append(("attach", resource, kwargs))
        self.attached.add(resource)
        return resource

    def detach(self, resource, **kwargs):
        self.calls.append(("detach", resource, kwargs))
        self.attached.discard(resource)

    def cleanup(self, resource, **kwargs):
        self.calls.append(("cleanup", resource, kwargs))
        self.attached.discard(resource)


class FakeProcessRuntime:
    def __init__(self):
        self.calls = []

    def start(self, command, **kwargs):
        process = {"command": command, "running": True}
        self.calls.append(("start", process, kwargs))
        return process

    def terminate(self, process, **kwargs):
        process["running"] = False
        self.calls.append(("terminate", process, kwargs))

    def wait(self, process, **kwargs):
        self.calls.append(("wait", process, kwargs))
        return 0


class FakeCommandRunner:
    """Command-only fake; deliberately has no process lifecycle methods."""

    def __init__(self, output=b"", status=0, error=None):
        self.output = output
        self.status = status
        self.error = error
        self.calls = []

    def run(self, command, **kwargs):
        self.calls.append(("run", command, kwargs))
        if self.error is not None:
            raise self.error
        from types import SimpleNamespace

        return SimpleNamespace(
            returncode=self.status,
            stdout=self.output.decode() if isinstance(self.output, bytes) else self.output,
        )

    def call(self, command, **kwargs):
        self.calls.append(("call", command, kwargs))
        if self.error is not None:
            raise self.error
        return self.status

    def check_output(self, command, **kwargs):
        self.calls.append(("check_output", command, kwargs))
        if self.error is not None:
            raise self.error
        return self.output

    def sleep(self, seconds):
        self.calls.append(("sleep", seconds))
