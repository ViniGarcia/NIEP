#!/usr/bin/env python3
from os.path import abspath
from sys import path


ROOT = '/'.join(abspath(__file__).split('/')[:-2])
path.insert(0, ROOT + '/TOPO-MAN')
path.insert(0, ROOT + '/VEM')
path.insert(0, ROOT)


def assert_result(result, ok, code):
    if result.ok != ok or result.code.value != code:
        raise AssertionError(str(result.to_dict()))


def run_checks(dispatcher=None):
    """Run dispatcher assertions and return a process-style status code."""

    from tests.support import install_optional_dependency_stubs

    install_optional_dependency_stubs()
    from Command import CommandDispatcher

    dispatcher = dispatcher or CommandDispatcher()
    assert_result(dispatcher.dispatch('status'), True, 'status')
    assert_result(dispatcher.dispatch('unknown'), False, 'unknown_command')
    assert_result(dispatcher.dispatch('define'), False, 'invalid_command_args')
    assert_result(dispatcher.dispatch('topoup'), False, 'no_topology')
    assert_result(dispatcher.dispatch('mininet', ['pingall']), False, 'topology_not_up')
    assert_result(dispatcher.dispatch('vm', ['list']), True, 'defined')
    assert_result(dispatcher.dispatch('container', ['shell', 'missing']), False, 'invalid_command_args')
    assert_result(dispatcher.dispatch('vnf', ['management']), False, 'invalid_command_args')
    return 0


def main():
    run_checks()
    print('[ OK ] command dispatcher')


if __name__ == '__main__':
    main()
