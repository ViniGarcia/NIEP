import libvirt


def _ignore_libvirt_errors(userdata, error):
    pass


libvirt.registerErrorHandler(_ignore_libvirt_errors, None)


DOMAIN_RUNNING_STATES = (
    libvirt.VIR_DOMAIN_RUNNING,
    libvirt.VIR_DOMAIN_BLOCKED,
    libvirt.VIR_DOMAIN_PAUSED,
)


class LibvirtRuntime:
    def __init__(self, uri="qemu:///system"):
        self.uri = uri
        self.connection = None

    def get_connection(self):
        if self.connection is None:
            self.connection = libvirt.open(self.uri)
        return self.connection

    def define(self, domainXML):
        return self.get_connection().defineXML(domainXML)

    def lookup(self, domainName):
        return self.get_connection().lookupByName(domainName)

    def exists(self, domainName):
        try:
            self.lookup(domainName)
            return True
        except libvirt.libvirtError:
            return False

    def is_running(self, domainName):
        try:
            state, _ = self.lookup(domainName).state()
            return state in DOMAIN_RUNNING_STATES
        except libvirt.libvirtError:
            return False

    def create(self, domain):
        return domain.create()

    def destroy(self, domain):
        return domain.destroy()

    def undefine(self, domain):
        return domain.undefine()

    def define_and_create(self, domainName, domainXML):
        self.define(domainXML)
        domain = self.lookup(domainName)
        self.create(domain)
        return domain


DEFAULT_LIBVIRT_RUNTIME = LibvirtRuntime()
