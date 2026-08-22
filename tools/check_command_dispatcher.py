#!/usr/bin/env python3
def assert_result(result, ok, code):
    if result.ok != ok or result.code.value != code:
        raise AssertionError(str(result.to_dict()))


def run_checks(dispatcher=None):
    """Run dispatcher assertions and return a process-style status code."""

    from niep.application.command import CommandDispatcher

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
