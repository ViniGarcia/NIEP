"""Start OVS switches without sending large commands through a canonical PTY."""
import shlex
from subprocess import PIPE

from niep.runtime.errors import RuntimeFailure
from niep.runtime.process import SubprocessRuntime


def start_switch(switch, controllers, *, runner=None):
    batch_start = getattr(type(switch), 'batchStartup', None)
    if not callable(batch_start) or not hasattr(switch, 'batch'):
        return switch.start(controllers)
    runner = runner or SubprocessRuntime()

    def checked_run(command, **_kwargs):
        argv = shlex.split(command) if isinstance(command, str) else list(command)
        result = runner.run(argv, stdout=PIPE, stderr=PIPE, text=True)
        if result.returncode:
            raise RuntimeFailure('start', 'switch', switch.name,
                                 message='Open vSwitch startup command failed',
                                 context={'command': argv, 'status': result.returncode,
                                          'stderr': result.stderr})
        return result.stdout, result.stderr, result.returncode

    switch.batch = True
    switch.commands = []
    try:
        switch.start(controllers)
        batch_start([switch], run=checked_run)
    finally:
        switch.batch = False
        switch.commands = []
