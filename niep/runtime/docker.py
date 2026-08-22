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


class DockerRuntimeError(RuntimeError):
    def __init__(self, operation, message, container_id=None, image=None):
        self.operation = operation
        self.container_id = container_id
        self.image = image
        details = [message, "operation=" + operation]
        if container_id is not None:
            details.append("container=" + container_id)
        if image is not None:
            details.append("image=" + image)
        super().__init__("; ".join(details))


class DockerRuntime:
    def __init__(self):
        self.client = None

    def get_client(self):
        if self.client is None:
            try:
                if docker is None:
                    raise DockerException("Docker SDK is not installed")
                self.client = docker.from_env(timeout=60)
                self.client.ping()
            except DockerException as exc:
                self.client = None
                raise DockerRuntimeError(
                    "connect",
                    "Docker daemon is unavailable or the current user cannot access it: " + str(exc),
                ) from exc
        return self.client

    def ensure_image(self, image):
        client = self.get_client()
        try:
            return client.images.get(image)
        except ImageNotFound:
            try:
                return client.images.pull(image)
            except (ImageNotFound, APIError, DockerException) as exc:
                raise DockerRuntimeError(
                    "image",
                    "Docker image is not available locally and could not be pulled: " + str(exc),
                    image=image,
                ) from exc
        except DockerException as exc:
            raise DockerRuntimeError("image", "Could not inspect Docker image: " + str(exc), image=image) from exc

    def exists(self, container_id):
        try:
            self.get_client().containers.get(container_id)
            return True
        except NotFound:
            return False
        except DockerException as exc:
            raise DockerRuntimeError("inspect", "Could not inspect Docker container: " + str(exc), container_id=container_id) from exc

    def is_running(self, container_id):
        try:
            container = self.get_client().containers.get(container_id)
            container.reload()
            return container.status == "running"
        except NotFound:
            return False
        except DockerException as exc:
            raise DockerRuntimeError("inspect", "Could not inspect Docker container state: " + str(exc), container_id=container_id) from exc

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
        except DockerException as exc:
            raise DockerRuntimeError(
                "create",
                "Could not create Docker container: " + str(exc),
                container_id=container_id,
                image=image,
            ) from exc

    def lookup(self, container_id):
        try:
            return self.get_client().containers.get(container_id)
        except NotFound as exc:
            raise DockerRuntimeError("inspect", "Docker container does not exist", container_id=container_id) from exc
        except DockerException as exc:
            raise DockerRuntimeError("inspect", "Could not inspect Docker container: " + str(exc), container_id=container_id) from exc

    def start(self, container):
        container_id = getattr(container, "name", None) or getattr(container, "id", None)
        try:
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
                )
            return container
        except DockerRuntimeError:
            raise
        except DockerException as exc:
            raise DockerRuntimeError("start", "Could not start Docker container: " + str(exc), container_id=container_id) from exc

    def remove(self, container_id):
        try:
            container = self.get_client().containers.get(container_id)
            container.remove(force=True)
        except NotFound:
            return
        except DockerException as exc:
            raise DockerRuntimeError("remove", "Could not remove Docker container: " + str(exc), container_id=container_id) from exc

    def exec(self, container_id, command):
        container = self.lookup(container_id)
        try:
            container.reload()
            if container.status != "running":
                raise DockerRuntimeError("exec", "Docker container is not running", container_id=container_id)
            result = container.exec_run(command)
        except DockerRuntimeError:
            raise
        except DockerException as exc:
            raise DockerRuntimeError("exec", "Could not execute command in Docker container: " + str(exc), container_id=container_id) from exc
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
        except DockerException as exc:
            raise DockerRuntimeError(
                "shell",
                "Could not open an interactive shell in Docker container: " + str(exc),
                container_id=container_id,
            ) from exc

    def ping(self):
        try:
            self.get_client().ping()
            return True
        except (DockerException, DockerRuntimeError):
            return False


DEFAULT_DOCKER_RUNTIME = DockerRuntime()
