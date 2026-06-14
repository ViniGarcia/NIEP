#!/usr/bin/env python3
from os.path import abspath
from sys import path


ROOT = '/'.join(abspath(__file__).split('/')[:-2])
path.insert(0, ROOT + '/TOPO-MAN')
path.insert(0, ROOT + '/VEM')

from Command import CommandDispatcher


def assert_result(result, ok, code):
    if result.ok != ok or result.code.value != code:
        raise AssertionError(str(result.to_dict()))


def main():
    dispatcher = CommandDispatcher()
    assert_result(dispatcher.dispatch('status'), True, 'status')
    assert_result(dispatcher.dispatch('unknown'), False, 'unknown_command')
    assert_result(dispatcher.dispatch('define'), False, 'invalid_command_args')
    assert_result(dispatcher.dispatch('topoup'), False, 'no_topology')
    assert_result(dispatcher.dispatch('vm', ['list']), True, 'defined')
    assert_result(dispatcher.dispatch('vnf', ['management']), False, 'invalid_command_args')
    print('[ OK ] command dispatcher')


if __name__ == '__main__':
    main()
