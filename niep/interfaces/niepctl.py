#!/usr/bin/env python3
import json
import math
import os
import shlex
import socket
import sys
import time
from pathlib import Path
from typing import Annotated, List, Optional

import typer

from niep.application.commands import CommandRequest
from niep.application.stream import bridge_terminal


DEFAULT_SOCKET = "/run/niep.sock"
MAX_REQUEST_BYTES = 64 * 1024
CLIENT_TIMEOUT = 10.0
CLIENT_SESSION_TIMEOUT = 300.0

app = typer.Typer(
    name="niepctl",
    help="Control the local NIEP daemon.",
    no_args_is_help=True,
)
container_app = typer.Typer(help="Inspect and access Docker containers.", no_args_is_help=True)
vm_app = typer.Typer(help="Inspect and access virtual machines.", no_args_is_help=True)
vnf_app = typer.Typer(help="Control VNFs.", no_args_is_help=True)
sfc_app = typer.Typer(help="Control service function chains.", no_args_is_help=True)
mininet_app = typer.Typer(help="Run commands in the active Mininet topology.", no_args_is_help=True)

app.add_typer(container_app, name="container")
app.add_typer(vm_app, name="vm")
app.add_typer(vnf_app, name="vnf")
app.add_typer(sfc_app, name="sfc")
app.add_typer(mininet_app, name="mininet")


def send_request(socket_path, command, args):
    timeout = float(os.environ.get('NIEP_CLIENT_TIMEOUT', CLIENT_TIMEOUT))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('NIEP_CLIENT_TIMEOUT must be a positive finite number')
    payload = json.dumps(CommandRequest(command, tuple(args)).to_dict()) + "\n"
    encoded = payload.encode("utf-8")
    if len(encoded) > MAX_REQUEST_BYTES:
        raise ValueError("request exceeds the 64 KiB socket limit")
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.settimeout(timeout)
        client.connect(socket_path)
        client.sendall(encoded)
        shutdown = getattr(client, "shutdown", None)
        if shutdown is not None:
            shutdown(socket.SHUT_WR)
        frame = None
        buffer = bytearray()
        size = 0
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("NIEP daemon response timed out")
            client.settimeout(remaining)
            chunk = client.recv(4096)
            if not chunk:
                if frame is None:
                    raise RuntimeError("NIEP daemon closed before a complete response frame")
                break
            size += len(chunk)
            if size > MAX_REQUEST_BYTES:
                raise ValueError("response exceeds the socket limit")
            if frame is not None:
                raise RuntimeError("NIEP daemon sent bytes after the response frame")
            buffer.extend(chunk)
            if b"\n" in buffer:
                payload_part, _, trailing = bytes(buffer).partition(b"\n")
                if trailing:
                    raise RuntimeError("NIEP daemon sent bytes after the response frame")
                frame = payload_part
    finally:
        client.close()
    return json.loads(frame.decode("utf-8"))


def receive_line(client):
    data = b""
    deadline = time.monotonic() + CLIENT_TIMEOUT
    while b"\n" not in data:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("NIEP daemon response timed out")
        setter = getattr(client, "settimeout", None)
        if setter is not None:
            setter(remaining)
        chunk = client.recv(4096)
        if not chunk:
            break
        data += chunk
        if len(data) > MAX_REQUEST_BYTES:
            raise RuntimeError("NIEP daemon response exceeds the socket limit")
    line, separator, remaining = data.partition(b"\n")
    if not separator:
        raise RuntimeError("NIEP daemon closed the connection before sending a response")
    return json.loads(line.decode("utf-8")), remaining


def root_context(ctx):
    while ctx.parent is not None:
        ctx = ctx.parent
    return ctx


def socket_path(ctx):
    root = root_context(ctx)
    if root.obj:
        return root.obj.get("socket_path", DEFAULT_SOCKET)
    return root.params.get("socket_path", DEFAULT_SOCKET)


def json_enabled(ctx):
    root = root_context(ctx)
    return bool(root.obj and root.obj.get("json_output"))


def request(ctx, command, args=None):
    try:
        return send_request(socket_path(ctx), command, args or [])
    except (
        ConnectionError,
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
        RuntimeError,
        ValueError,
    ) as exc:
        typer.echo("Could not communicate with the NIEP daemon: " + str(exc), err=True)
        raise typer.Exit(1)


def completion_socket_path():
    words = os.environ.get("COMP_WORDS") or os.environ.get("_TYPER_COMPLETE_ARGS", "")
    try:
        arguments = shlex.split(words)
    except ValueError:
        arguments = words.split()
    for index, argument in enumerate(arguments):
        if argument == "--socket" and index + 1 < len(arguments):
            return arguments[index + 1]
        if argument.startswith("--socket="):
            return argument.split("=", 1)[1]
    return os.environ.get("NIEP_SOCKET", DEFAULT_SOCKET)


def resource_names(key):
    try:
        response = send_request(completion_socket_path(), "status", [])
    except Exception:
        return []
    if not response.get("ok"):
        return []
    return response.get("data", {}).get(key, [])


def complete_resource(key):
    def complete(incomplete: str):
        return [name for name in resource_names(key) if name.startswith(incomplete)]

    return complete


complete_container = complete_resource("containers")
complete_vm = complete_resource("vms")
complete_vnf = complete_resource("vnfs")
complete_sfc = complete_resource("sfcs")


def print_response(ctx, response):
    if json_enabled(ctx):
        typer.echo(json.dumps(response, indent=2, sort_keys=True))
        return

    data = response.get("data")
    if response.get("code") == "container_exec" and isinstance(data, dict):
        output = data.get("output", "")
        if output:
            typer.echo(output, nl=not output.endswith("\n"))
        return
    if isinstance(data, list):
        for item in data:
            typer.echo(item)
        return
    if isinstance(data, dict):
        typer.echo(json.dumps(data, indent=2, sort_keys=True))
        return
    if data is not None:
        typer.echo(data)
        return

    message = response.get("message")
    if message:
        typer.echo(message, err=not response.get("ok"))
        detail = response.get("detail")
        if detail and detail != message:
            typer.echo("DETAIL: " + detail, err=not response.get("ok"))
        return
    typer.echo(response.get("code"))


def handle(ctx, response, preserve_exec_status=False):
    print_response(ctx, response)
    if preserve_exec_status and response.get("code") == "container_exec":
        raise typer.Exit(response.get("data", {}).get("exit_code", 1))
    if not response.get("ok"):
        raise typer.Exit(1)


def remaining_args(ctx, label):
    args = list(ctx.args)
    if not args:
        typer.echo(label + " requires a command", err=True)
        raise typer.Exit(2)
    return args


def run_interactive_shell(socket_path_value, args):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        typer.echo("container shell requires an interactive terminal", err=True)
        return 2

    payload = json.dumps(CommandRequest("container", tuple(args)).to_dict()) + "\n"
    if len(payload.encode("utf-8")) > MAX_REQUEST_BYTES:
        typer.echo("container shell request exceeds the 64 KiB socket limit", err=True)
        return 2
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.settimeout(CLIENT_TIMEOUT)
        client.connect(socket_path_value)
        client.sendall(payload.encode("utf-8"))
        response, remaining = receive_line(client)
        if not response.get("ok"):
            typer.echo(response.get("message") or response.get("code"), err=True)
            if response.get("detail"):
                typer.echo("DETAIL: " + response.get("detail"), err=True)
            return 1
        client.settimeout(None)
        bridge_terminal(client, initial_output=remaining, timeout=CLIENT_SESSION_TIMEOUT)
        return 0
    except (ConnectionError, FileNotFoundError, OSError, RuntimeError) as exc:
        typer.echo("Could not open the container shell: " + str(exc), err=True)
        return 1
    finally:
        client.close()


@app.callback()
def configure(
    ctx: typer.Context,
    socket_path_value: str = typer.Option(
        DEFAULT_SOCKET,
        "--socket",
        envvar="NIEP_SOCKET",
        help="Path to the NIEP daemon Unix socket.",
        show_default=True,
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the complete JSON response."),
):
    ctx.ensure_object(dict)
    ctx.obj["socket_path"] = socket_path_value
    ctx.obj["json_output"] = json_output


@app.command()
def status(ctx: typer.Context):
    """Show daemon and topology status."""
    handle(ctx, request(ctx, "status"))


@app.command("disk-usage")
def disk_usage(ctx: typer.Context):
    """Show VM disk allocation and container writable-layer storage."""
    response = request(ctx, 'disk-usage')
    if not response.get('ok') or json_enabled(ctx):
        handle(ctx, response)
        return
    data = response['data']
    typer.echo(f"{'TYPE':<12} {'NAME':<24} {'DISK MiB':>12}  SOURCE")
    for row in data['resources']:
        size = '-' if row['disk_bytes'] is None else f"{row['disk_bytes'] / 1048576:.2f}"
        typer.echo(f"{row['kind']:<12} {row['id']:<24} {size:>12}  {row.get('source', '-')}")
        if row.get('error'):
            typer.echo(f"  {row['error']}")
    for name, total in data['totals'].items():
        typer.echo(f"TOTAL {name}: {total['disk_bytes'] / 1048576:.2f} MiB "
                   f"({total['measured_resources']}/{total['resources']} measured)")
    typer.echo('Excludes shared images, volumes, bind mounts and container logs. '
               'VM allocated blocks and Docker writable-layer sizes use different accounting.')


@app.command("stats-snapshot")
def stats_snapshot(ctx: typer.Context):
    """Print one CPU/memory snapshot as JSON."""
    response = request(ctx, "stats")
    if not response.get('ok'):
        handle(ctx, response)
        return
    typer.echo(json.dumps(response if json_enabled(ctx) else response['data'], indent=2))


@app.command("stats")
def stats_watch(ctx: typer.Context, interval: float = typer.Option(5.0, "--interval", min=0.1)):
    """Poll resource usage until Ctrl+C (default: every five seconds)."""
    if not math.isfinite(interval):
        raise typer.BadParameter('interval must be finite')
    try:
        while True:
            start = time.monotonic()
            response = request(ctx, 'stats')
            if not response.get('ok'):
                handle(ctx, response)
                return
            if json_enabled(ctx):
                typer.echo(json.dumps(response))
            else:
                data = response['data']
                if sys.stdout.isatty():
                    typer.clear()
                typer.echo(data['timestamp'])
                typer.echo(f"{'TYPE':<12} {'NAME':<24} {'CPU %':>10} {'MEM MiB':>12}  STATE")
                for row in data['resources'] + [data['daemon']]:
                    cpu = '-' if row['cpu_percent'] is None else f"{row['cpu_percent']:.2f}"
                    memory = '-' if row['memory_bytes'] is None else f"{row['memory_bytes'] / 1048576:.2f}"
                    typer.echo(f"{row['kind']:<12} {row['id']:<24} {cpu:>10} {memory:>12}  {row['state']}")
                    if row.get('error'):
                        typer.echo(f"  {row['error']}")
                for name, total in data['totals'].items():
                    typer.echo(f"TOTAL {name}: {total['cpu_percent']:.2f}% CPU, "
                               f"{total['memory_bytes'] / 1048576:.2f} MiB")
            time.sleep(max(0, interval - (time.monotonic() - start)))
    except KeyboardInterrupt:
        return


@app.command("define")
def define_topology(
    ctx: typer.Context,
    topology: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
):
    """Load a topology definition."""
    handle(ctx, request(ctx, "define", [str(topology)]))


@app.command()
def topoup(ctx: typer.Context):
    """Start the defined topology."""
    handle(ctx, request(ctx, "topoup"))


@app.command()
def topodown(ctx: typer.Context):
    """Stop the active topology."""
    handle(ctx, request(ctx, "topodown"))


@app.command()
def topoclean(ctx: typer.Context):
    """Stop and forget the defined topology."""
    handle(ctx, request(ctx, "topoclean"))


@app.command()
def topodestroy(ctx: typer.Context):
    """Destroy topology resources and generated files."""
    handle(ctx, request(ctx, "topodestroy"))


@container_app.command("list")
def container_list(ctx: typer.Context):
    """List active containers."""
    handle(ctx, request(ctx, "container", ["list"]))


@container_app.command(
    "exec",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def container_exec(
    ctx: typer.Context,
    container_id: Annotated[str, typer.Argument(autocompletion=complete_container)],
    command: List[str] = typer.Argument(..., help="Command and arguments to execute."),
):
    """Execute a non-interactive command in a container."""
    handle(
        ctx,
        request(ctx, "container", ["exec", container_id, *command]),
        preserve_exec_status=True,
    )


@container_app.command(
    "shell",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def container_shell(
    ctx: typer.Context,
    container_id: Annotated[str, typer.Argument(autocompletion=complete_container)],
    command: Optional[List[str]] = typer.Argument(
        None,
        help="Interactive program and arguments. Defaults to /bin/sh.",
    ),
):
    """Open an interactive container shell."""
    if json_enabled(ctx):
        typer.echo("--json cannot be used with container shell", err=True)
        raise typer.Exit(2)
    command = command or ["/bin/sh"]
    raise typer.Exit(
        run_interactive_shell(
            socket_path(ctx),
            ["shell", container_id, *command],
        )
    )


@vm_app.command("list")
def vm_list(ctx: typer.Context):
    """List active virtual machines."""
    handle(ctx, request(ctx, "vm", ["list"]))


@vm_app.command()
def management(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(autocompletion=complete_vm)],
):
    """Show a VM management address."""
    handle(ctx, request(ctx, "vm", ["management", vm_id]))


@vm_app.command()
def ssh(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(autocompletion=complete_vm)],
    user: str = typer.Argument(...),
    password: str = typer.Argument(...),
):
    """Open the legacy VM SSH flow."""
    handle(ctx, request(ctx, "vm", ["ssh", vm_id, user, password]))


@vnf_app.command("list")
def vnf_list(ctx: typer.Context):
    """List active VNFs."""
    handle(ctx, request(ctx, "vnf", ["list"]))


@vnf_app.command("management")
def management_vnf(
    ctx: typer.Context,
    vnf_id: Annotated[str, typer.Argument(autocompletion=complete_vnf)],
):
    """Show a VNF management address."""
    handle(ctx, request(ctx, "vnf", ["management", vnf_id]))


@vnf_app.command("up")
def vnf_up(
    ctx: typer.Context,
    vnf_id: Annotated[str, typer.Argument(autocompletion=complete_vnf)],
):
    """Wake a VNF."""
    handle(ctx, request(ctx, "vnf", ["up", vnf_id]))


@vnf_app.command("down")
def vnf_down(
    ctx: typer.Context,
    vnf_id: Annotated[str, typer.Argument(autocompletion=complete_vnf)],
):
    """Suspend a VNF."""
    handle(ctx, request(ctx, "vnf", ["down", vnf_id]))


@vnf_app.command(
    "action",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def vnf_action(
    ctx: typer.Context,
    vnf_id: Annotated[str, typer.Argument(autocompletion=complete_vnf)],
    action_name: str = typer.Argument(...),
):
    """Execute a VNF action."""
    handle(ctx, request(ctx, "vnf", ["action", vnf_id, action_name, *ctx.args]))


@vnf_app.command("script")
def vnf_script(
    ctx: typer.Context,
    vnf_id: Annotated[str, typer.Argument(autocompletion=complete_vnf)],
    script: Path = typer.Argument(..., exists=True, dir_okay=False),
    error_script: Optional[Path] = typer.Argument(None, exists=True, dir_okay=False),
):
    """Execute a VNF action script."""
    args = ["script", vnf_id, str(script)]
    if error_script is not None:
        args.append(str(error_script))
    handle(ctx, request(ctx, "vnf", args))


@sfc_app.command("list")
def sfc_list(ctx: typer.Context):
    """List active service function chains."""
    handle(ctx, request(ctx, "sfc", ["list"]))


@sfc_app.command("management")
def management_sfc(
    ctx: typer.Context,
    sfc_id: Annotated[str, typer.Argument(autocompletion=complete_sfc)],
):
    """Show SFC management addresses."""
    handle(ctx, request(ctx, "sfc", ["management", sfc_id]))


@sfc_app.command("up")
def sfc_up(
    ctx: typer.Context,
    sfc_id: Annotated[str, typer.Argument(autocompletion=complete_sfc)],
):
    """Wake an SFC."""
    handle(ctx, request(ctx, "sfc", ["up", sfc_id]))


@sfc_app.command("down")
def sfc_down(
    ctx: typer.Context,
    sfc_id: Annotated[str, typer.Argument(autocompletion=complete_sfc)],
):
    """Suspend an SFC."""
    handle(ctx, request(ctx, "sfc", ["down", sfc_id]))


@mininet_app.command()
def pingall(ctx: typer.Context):
    """Ping all Mininet hosts."""
    handle(ctx, request(ctx, "mininet", ["pingall"]))


@mininet_app.command(
    "cmd",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def mininet_cmd(
    ctx: typer.Context,
    node_id: str = typer.Argument(...),
):
    """Execute a command in a Mininet node."""
    command = remaining_args(ctx, "mininet cmd")
    handle(ctx, request(ctx, "mininet", ["cmd", node_id, *command]))


def main():
    app(prog_name="niepctl")


if __name__ == "__main__":
    main()
