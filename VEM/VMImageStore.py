from os import path
from shutil import copyfile, rmtree


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

    def instance_exists(self, vmID):
        return path.isdir(self.instance_path(vmID))

    def create_instance(self, vmID, disk):
        instancePath = self.instance_path(vmID)
        if not path.isdir(instancePath):
            from os import mkdir
            mkdir(instancePath)
        copyfile(self.base_disk_path(disk), self.instance_disk_path(vmID, disk))

    def remove_instance(self, vmID):
        rmtree(self.instance_path(vmID))

    def copy_template_xml(self, vmID, disk):
        copyfile(self.template_xml_path(disk), self.instance_xml_path(vmID, disk))

    def read_domain_xml(self, vmID, disk):
        with open(self.instance_xml_path(vmID, disk), 'r') as domainFile:
            return domainFile.read()

