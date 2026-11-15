from types import SimpleNamespace

import pytest

from niep.runtime.errors import RuntimeFailure
from niep.runtime.mininet_switch import start_switch


class BatchSwitch:
    name = 's1'
    batch = False

    def start(self, controllers):
        assert self.batch
        assert controllers == ['controller']
        # Above the canonical PTY line limit encountered at 64 VM ports.
        self.commands.append(' -- add-br s1 ' + ' -- add-port s1 interface ' * 256)

    @classmethod
    def batchStartup(cls, switches, run):
        for switch in switches:
            run('ovs-vsctl ' + ''.join(switch.commands), shell=True)


@pytest.mark.parametrize('returncode', [0, 1])
def test_large_switch_commands_bypass_pty_and_propagate_failure(returncode):
    calls = []
    switch = BatchSwitch()

    def run(argv, **kwargs):
        calls.append(argv)
        assert isinstance(argv, list)
        assert len(' '.join(argv)) > 4096
        assert 'shell' not in kwargs
        return SimpleNamespace(returncode=returncode, stdout='', stderr='failure' if returncode else '')

    runner = SimpleNamespace(run=run)
    if returncode:
        with pytest.raises(RuntimeFailure, match='Open vSwitch startup command failed'):
            start_switch(switch, ['controller'], runner=runner)
    else:
        start_switch(switch, ['controller'], runner=runner)
    assert calls[0][0] == 'ovs-vsctl'
    assert not switch.batch
    assert switch.commands == []


def test_non_ovs_switch_keeps_its_start_method():
    controllers = []
    switch = SimpleNamespace(start=lambda value: controllers.extend(value))
    start_switch(switch, ['c1'])
    assert controllers == ['c1']
