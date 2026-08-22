"""Injectable subprocess adapter used by infrastructure integrations."""

from __future__ import annotations

from subprocess import DEVNULL, PIPE, STDOUT, Popen
from subprocess import call as subprocess_call
from subprocess import check_output as subprocess_check_output
from subprocess import run as subprocess_run
from time import sleep as time_sleep
from typing import Any

from .errors import RuntimeFailure


class SubprocessRuntime:
    """Small ``ProcessRuntime`` implementation with no import-time process."""

    def __init__(self, process_factory=None):
        self._process_factory = process_factory or Popen

    def run(self, command: Any, *args: Any, **kwargs: Any):
        return subprocess_run(command, *args, **kwargs)

    def call(self, command: Any, *args: Any, **kwargs: Any) -> int:
        return subprocess_call(command, *args, **kwargs)

    def check_output(self, command: Any, *args: Any, **kwargs: Any):
        return subprocess_check_output(command, *args, **kwargs)

    def sleep(self, seconds: float):
        return time_sleep(seconds)

    def start(self, command: Any, **kwargs: Any):
        try:
            return self._process_factory(command, **kwargs)
        except RuntimeFailure:
            raise
        except Exception as exc:
            raise RuntimeFailure("start", "process", None, cause=exc, retryable=True) from exc

    def terminate(self, process: Any, **kwargs: Any):
        del kwargs
        try:
            if process is None or (hasattr(process, "poll") and process.poll() is not None):
                return None
            return process.terminate()
        except RuntimeFailure:
            raise
        except Exception as exc:
            raise RuntimeFailure("terminate", "process", getattr(process, "pid", None), cause=exc, retryable=True) from exc

    def wait(self, process: Any, timeout: float | None = None):
        if process is None:
            return None
        try:
            return process.wait(timeout=timeout)
        except RuntimeFailure:
            raise
        except Exception as exc:
            raise RuntimeFailure("wait", "process", getattr(process, "pid", None), cause=exc, retryable=True) from exc


# Friendly adapter aliases for code that names implementations after the
# capability contract.
ProcessRuntimeAdapter = SubprocessRuntime
ProcessRuntime = SubprocessRuntime

__all__ = ["ProcessRuntime", "ProcessRuntimeAdapter", "SubprocessRuntime", "DEVNULL", "PIPE", "STDOUT"]
