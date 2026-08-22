from os import path
from shutil import copyfile, rmtree
from niep.runtime.errors import RuntimeFailure


class VMImageStore:
    def __init__(self, basePath):
        self.basePath = basePath
        self.imagesPath = path.join(basePath, 'IMAGES')

    def base_disk_path(self, disk):
        return path.join(self.imagesPath, disk + '.qcow2')

    def template_xml_path(self, disk):
        return path.join(self.imagesPath, disk + '.xml')

    def instance_path(self, vmID):
        return path.join(self.imagesPath, vmID)

    def instance_disk_path(self, vmID, disk):
        return path.join(self.instance_path(vmID), disk + '.qcow2')

    def instance_xml_path(self, vmID, disk):
        return path.join(self.instance_path(vmID), disk + '.xml')

    def base_disk_exists(self, disk):
        return path.isfile(self.base_disk_path(disk))

    def validate(self, disk):
        """Validate a base image and return its path.

        Missing images are typed failures; callers that still expose numeric
        VM status codes can translate this at their compatibility boundary.
        """

        image_path = self.base_disk_path(disk)
        if not path.isfile(image_path):
            raise RuntimeFailure(
                "validate",
                "image",
                disk,
                message="VM base image does not exist",
                context={"path": image_path},
            )
        return image_path

    def instance_exists(self, vmID):
        return path.isdir(self.instance_path(vmID))

    def create_instance(self, vmID, disk):
        instancePath = self.instance_path(vmID)
        try:
            if not path.isdir(instancePath):
                from os import mkdir
                mkdir(instancePath)
            copyfile(self.base_disk_path(disk), self.instance_disk_path(vmID, disk))
        except OSError as exc:
            raise RuntimeFailure("instantiate", "image", disk, cause=exc, context={"instance_id": vmID}) from exc

    def instantiate(self, vmID, disk):
        self.validate(disk)
        self.create_instance(vmID, disk)
        return self.instance_path(vmID)

    def remove_instance(self, vmID):
        # Removing an absent instance is successful cleanup by contract.
        instance_path = self.instance_path(vmID)
        try:
            if path.isdir(instance_path):
                rmtree(instance_path)
        except OSError as exc:
            raise RuntimeFailure("remove", "image_instance", vmID, cause=exc) from exc
        return None

    def remove(self, vmID):
        return self.remove_instance(vmID)

    def copy_template_xml(self, vmID, disk):
        try:
            copyfile(self.template_xml_path(disk), self.instance_xml_path(vmID, disk))
        except OSError as exc:
            raise RuntimeFailure("instantiate", "image", disk, cause=exc, context={"instance_id": vmID}) from exc

    def read_domain_xml(self, vmID, disk):
        try:
            with open(self.instance_xml_path(vmID, disk), 'r') as domainFile:
                return domainFile.read()
        except OSError as exc:
            raise RuntimeFailure("inspect", "image_instance", vmID, cause=exc) from exc
