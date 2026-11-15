try:  # Docker is an integration dependency, not needed for parsing/tests.
    import docker
    from docker.errors import APIError, DockerException, ImageNotFound, NotFound
except ImportError:  # pragma: no cover - exercised on host-only installations
    docker = None

    class DockerException(Exception):
        pass

    class APIError(DockerException):
        pass

    class ImageNotFound(DockerException):
        pass

    class NotFound(DockerException):
        pass


from niep.runtime.start_events import timed_start
from niep.runtime.errors import RuntimeFailure


class DockerRuntimeError(RuntimeFailure):
    """Legacy Docker error retaining the structured runtime failure fields."""

    def __init__(
        self,
        operation,
        message,
        container_id=None,
        image=None,
        *,
        cause=None,
        retryable=False,
        context=None,
    ):
        self.container_id = container_id
        self.image = image
        resource_type = "container" if container_id is not None else "image" if image is not None else "docker"
        resource_id = container_id if container_id is not None else image
        super().__init__(
            operation,
            resource_type,
            resource_id,
            cause=cause,
            retryable=retryable,
            context=context,
            message=message,
        )


class DockerRuntime:
    """Docker adapter with a lazy, injectable SDK client.

    ``client`` and ``client_factory`` are intentionally optional: importing or
    constructing this adapter never contacts a Docker daemon.  ``remove`` and
    ``stop`` treat an absent container as successful, idempotent cleanup.
    """

    def __init__(self, client=None, client_factory=None):
        self.client = client
        self._client_factory = client_factory

    def get_client(self):
        if self.client is None:
            try:
                if docker is None and self._client_factory is None:
                    raise DockerException("Docker SDK is not installed")
                factory = self._client_factory or docker.from_env
                try:
                    self.client = factory(timeout=60)
                except TypeError as first:
                    # Tiny fakes often expose a zero-argument factory.
                    try:
                        self.client = factory()
                    except TypeError:
                        raise first
                self.client.ping()
            except RuntimeFailure:
                self.client = None
                raise
            except Exception as exc:
                self.client = None
                raise DockerRuntimeError(
                    "connect",
                    "Docker daemon is unavailable or the current user cannot access it: " + str(exc),
                    cause=exc,
                    retryable=True,
                ) from exc
        return self.client

    def ensure_image(self, image):
        client = self.get_client()
        try:
            return client.images.get(image)
        except ImageNotFound:
            try:
                return client.images.pull(image)
            except RuntimeFailure:
                raise
            except Exception as exc:
                raise DockerRuntimeError(
                    "image",
                    "Docker image is not available locally and could not be pulled: " + str(exc),
                    image=image,
                    cause=exc,
                    retryable=True,
                ) from exc
        except RuntimeFailure:
            raise
        except Exception as exc:
            raise DockerRuntimeError("image", "Could not inspect Docker image: " + str(exc), image=image, cause=exc) from exc

    def exists(self, container_id):
        try:
            self.get_client().containers.get(container_id)
            return True
        except NotFound:
            return False
        except RuntimeFailure:
            raise
        except Exception as exc:
            raise DockerRuntimeError("inspect", "Could not inspect Docker container: " + str(exc), container_id=container_id, cause=exc) from exc

    def is_running(self, container_id):
        try:
            container = self.get_client().containers.get(container_id)
            container.reload()
            return container.status == "running"
        except NotFound:
            return False
        except RuntimeFailure:
            raise
        except Exception as exc:
            raise DockerRuntimeError("inspect", "Could not inspect Docker container state: " + str(exc), container_id=container_id, cause=exc) from exc

    def inspect(self, container_id):
        """Return a container handle, or a typed failure when it is absent."""

        return self.lookup(container_id)

    def create(self, container_id, image, command, privileged=True, entrypoint=None, sysctls=None):
        self.ensure_image(image)
        try:
            return self.get_client().containers.create(
                image=image,
                command=command,
                entrypoint=entrypoint,
                detach=True,
                name=container_id,
                hostname=container_id,
                network_mode="none",
                privileged=privileged,
                sysctls=sysctls or None,
            )
        except RuntimeFailure:
            raise
        except Exception as exc:
            raise DockerRuntimeError(
                "create",
                "Could not create Docker container: " + str(exc),
                container_id=container_id,
                image=image,
                cause=exc,
            ) from exc

    def lookup(self, container_id):
        try:
            return self.get_client().containers.get(container_id)
        except NotFound as exc:
            raise DockerRuntimeError("inspect", "Docker container does not exist", container_id=container_id, cause=exc) from exc
        except RuntimeFailure:
            raise
        except Exception as exc:
            raise DockerRuntimeError("inspect", "Could not inspect Docker container: " + str(exc), container_id=container_id, cause=exc) from exc

    def start(self, container):
        container_id = getattr(container, "name", None) or getattr(container, "id", None)
        try:
            with timed_start('container', container):
                container.start()
            container.reload()
            if container.status != "running":
                exit_code = container.attrs.get("State", {}).get("ExitCode")
                logs = container.logs(tail=20)
                if isinstance(logs, bytes):
                    logs = logs.decode("utf-8", "ignore")
                raise DockerRuntimeError(
                    "start",
                    "Container exited during startup with exit code "
                    + str(exit_code)
                    + (": " + logs.strip() if logs.strip() else ""),
                    container_id=container_id,
                    context={"exit_code": exit_code},
                )
            return container
        except DockerRuntimeError:
            raise
        except RuntimeFailure:
            raise
        except Exception as exc:
            raise DockerRuntimeError("start", "Could not start Docker container: " + str(exc), container_id=container_id, cause=exc, retryable=True) from exc

    def stop(self, container):
        """Stop a container when present; stopping an absent one is idempotent."""

        container_id = getattr(container, "name", None) or getattr(container, "id", container)
        try:
            handle = container if hasattr(container, "stop") else self.get_client().containers.get(container)
            handle.stop()
            return handle
        except NotFound:
            return None
        except RuntimeFailure:
            raise
        except Exception as exc:
            raise DockerRuntimeError("stop", "Could not stop Docker container: " + str(exc), container_id=container_id, cause=exc, retryable=True) from exc

    def remove(self, container_id):
        try:
            container = self.get_client().containers.get(container_id)
            container.remove(force=True)
        except NotFound:
            return None
        except RuntimeFailure:
            raise
        except Exception as exc:
            raise DockerRuntimeError("remove", "Could not remove Docker container: " + str(exc), container_id=container_id, cause=exc) from exc
        return None

    def exec(self, container_id, command):
        container = self.lookup(container_id)
        try:
            container.reload()
            if container.status != "running":
                raise DockerRuntimeError("exec", "Docker container is not running", container_id=container_id)
            result = container.exec_run(command)
        except DockerRuntimeError:
            raise
        except RuntimeFailure:
            raise
        except Exception as exc:
            raise DockerRuntimeError("exec", "Could not execute command in Docker container: " + str(exc), container_id=container_id, cause=exc) from exc
        output = result.output
        if isinstance(output, bytes):
            output = output.decode("utf-8", "ignore")
        return result.exit_code, output

    def open_interactive_exec(self, container_id, command):
        container = self.lookup(container_id)
        try:
            container.reload()
            if container.status != "running":
                raise DockerRuntimeError("shell", "Docker container is not running", container_id=container_id)
            exec_data = self.get_client().api.exec_create(
                container.id,
                command,
                stdin=True,
                stdout=True,
                stderr=True,
                tty=True,
            )
            return self.get_client().api.exec_start(
                exec_data["Id"],
                detach=False,
                tty=True,
                socket=True,
            )
        except DockerRuntimeError:
            raise
        except RuntimeFailure:
            raise
        except Exception as exc:
            raise DockerRuntimeError(
                "shell",
                "Could not open an interactive shell in Docker container: " + str(exc),
                container_id=container_id,
                cause=exc,
                retryable=True,
            ) from exc

    def ping(self):
        try:
            self.get_client().ping()
            return True
        except RuntimeFailure:
            raise
        except Exception:
            return False


DEFAULT_DOCKER_RUNTIME = DockerRuntime()
