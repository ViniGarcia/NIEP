import docker
from docker.errors import DockerException, ImageNotFound, NotFound


class DockerRuntime:
    def __init__(self):
        self.client = None

    def get_client(self):
        if self.client is None:
            self.client = docker.from_env()
        return self.client

    def ensure_image(self, image):
        client = self.get_client()
        try:
            client.images.get(image)
        except ImageNotFound:
            client.images.pull(image)

    def exists(self, container_id):
        try:
            self.get_client().containers.get(container_id)
            return True
        except NotFound:
            return False

    def is_running(self, container_id):
        try:
            container = self.get_client().containers.get(container_id)
            return container.status == "running"
        except NotFound:
            return False

    def create(self, container_id, image, command, privileged=True):
        self.ensure_image(image)
        return self.get_client().containers.create(
            image=image,
            command=command,
            detach=True,
            name=container_id,
            hostname=container_id,
            network_mode="none",
            privileged=privileged,
        )

    def lookup(self, container_id):
        return self.get_client().containers.get(container_id)

    def start(self, container):
        container.start()
        container.reload()
        return container

    def remove(self, container_id):
        try:
            container = self.lookup(container_id)
            container.remove(force=True)
        except NotFound:
            return

    def exec(self, container_id, command):
        container = self.lookup(container_id)
        result = container.exec_run(command)
        output = result.output
        if isinstance(output, bytes):
            output = output.decode("utf-8", "ignore")
        return result.exit_code, output

    def ping(self):
        try:
            self.get_client().ping()
            return True
        except DockerException:
            return False


DEFAULT_DOCKER_RUNTIME = DockerRuntime()
