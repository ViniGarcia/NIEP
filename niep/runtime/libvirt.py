try:  # libvirt is provided by the VM/system package for integration runs.
    import libvirt
except ImportError:  # pragma: no cover - import-only host fallback
    class _UnavailableLibvirt:
        VIR_DOMAIN_RUNNING = 1
        VIR_DOMAIN_BLOCKED = 2
        VIR_DOMAIN_PAUSED = 3

        class libvirtError(RuntimeError):
            pass

        @staticmethod
        def registerErrorHandler(*_args):
            return None

        @staticmethod
        def open(*_args, **_kwargs):
            raise _UnavailableLibvirt.libvirtError("libvirt is unavailable")

    libvirt = _UnavailableLibvirt()


from niep.runtime.errors import RuntimeFailure


def _ignore_libvirt_errors(userdata, error):
    # libvirt invokes this callback for asynchronous diagnostics.  Structured
    # failures are raised by the operation that triggered the callback.
    return None


DOMAIN_RUNNING_STATES = (
    libvirt.VIR_DOMAIN_RUNNING,
    libvirt.VIR_DOMAIN_BLOCKED,
    libvirt.VIR_DOMAIN_PAUSED,
)


class LibvirtRuntimeError(RuntimeFailure):
    """Typed error emitted by the libvirt adapter."""

    pass


class LibvirtRuntime:
    """Lazy, injectable libvirt connection adapter.

    A connection is opened only when an operation is requested.  Looking up
    or destroying an absent domain is represented as a normal compatibility
    result by ``exists``/``is_running`` and cleanup methods.
    """

    def __init__(self, uri="qemu:///system", connection=None, connection_factory=None):
        self.uri = uri
        self.connection = connection
        self._connection_factory = connection_factory
        self._handler_registered = False

    def _register_error_handler(self):
        if not self._handler_registered and hasattr(libvirt, "registerErrorHandler"):
            libvirt.registerErrorHandler(_ignore_libvirt_errors, None)
            self._handler_registered = True

    def get_connection(self):
        if self.connection is None:
            try:
                self._register_error_handler()
                opener = self._connection_factory or libvirt.open
                self.connection = opener(self.uri)
                if self.connection is None:
                    raise RuntimeError("libvirt.open returned no connection")
            except RuntimeFailure:
                self.connection = None
                raise
            except Exception as exc:
                raise LibvirtRuntimeError(
                    "connect",
                    "libvirt",
                    self.uri,
                    cause=exc,
                    retryable=True,
                    message="libvirt connection is unavailable",
                ) from exc
        return self.connection

    def define(self, domainXML):
        try:
            return self.get_connection().defineXML(domainXML)
        except LibvirtRuntimeError:
            raise
        except RuntimeFailure:
            raise
        except Exception as exc:
            raise LibvirtRuntimeError("create", "domain", None, cause=exc, message="Could not define libvirt domain") from exc

    def lookup(self, domainName):
        try:
            return self.get_connection().lookupByName(domainName)
        except LibvirtRuntimeError:
            raise
        except RuntimeFailure:
            raise
        except Exception as exc:
            raise LibvirtRuntimeError("inspect", "domain", domainName, cause=exc, message="Could not inspect libvirt domain") from exc

    def inspect(self, domainName):
        return self.lookup(domainName)

    def exists(self, domainName):
        try:
            self.lookup(domainName)
            return True
        except LibvirtRuntimeError as exc:
            if isinstance(exc.cause, getattr(libvirt, "libvirtError", RuntimeError)):
                return False
            raise

    def is_running(self, domainName):
        try:
            state, _ = self.lookup(domainName).state()
            return state in DOMAIN_RUNNING_STATES
        except LibvirtRuntimeError as exc:
            if isinstance(exc.cause, getattr(libvirt, "libvirtError", RuntimeError)):
                return False
            raise

    def create(self, domain):
        return self.start(domain)

    def start(self, domain):
        try:
            return domain.create()
        except RuntimeFailure:
            raise
        except Exception as exc:
            domain_id = getattr(domain, "name", None)
            raise LibvirtRuntimeError("start", "domain", domain_id, cause=exc, retryable=True, message="Could not start libvirt domain") from exc

    def stop(self, domain):
        try:
            return domain.destroy()
        except RuntimeFailure:
            raise
        except getattr(libvirt, "libvirtError", RuntimeError):
            # Stopping an already absent/stopped domain is idempotent cleanup.
            return None
        except Exception as exc:
            domain_id = getattr(domain, "name", None)
            raise LibvirtRuntimeError("stop", "domain", domain_id, cause=exc, retryable=True, message="Could not stop libvirt domain") from exc

    def destroy(self, domain):
        return self.stop(domain)

    def undefine(self, domain):
        try:
            return domain.undefine()
        except RuntimeFailure:
            raise
        except getattr(libvirt, "libvirtError", RuntimeError):
            return None
        except Exception as exc:
            domain_id = getattr(domain, "name", None)
            raise LibvirtRuntimeError("remove", "domain", domain_id, cause=exc, message="Could not remove libvirt domain definition") from exc

    def remove(self, domain):
        return self.undefine(domain)

    def define_and_create(self, domainName, domainXML):
        self.define(domainXML)
        domain = self.lookup(domainName)
        self.start(domain)
        return domain


DEFAULT_LIBVIRT_RUNTIME = LibvirtRuntime()
