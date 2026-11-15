"""Deterministic identities for the shared startup-benchmark LAN."""
from ipaddress import IPv4Address

MAX_INSTANCES = (1 << 24) - 3  # /8 minus network, broadcast and probe host.
PREFIX_LENGTH = 8


def positive_count(value):
    number = int(value)
    if number <= 0:
        raise ValueError('count must be a positive integer')
    return number


def validate_count(count):
    positive_count(count)
    if count > MAX_INSTANCES:
        raise ValueError(f'count exceeds the IPv4 address pool ({MAX_INSTANCES} endpoints)')


def mac(index, role):
    if not 0 <= index < MAX_INSTANCES:
        raise ValueError('instance index exceeds the IPv4 address pool')
    return ':'.join(f'{octet:02x}' for octet in bytes((2, role)) + index.to_bytes(4, 'big'))


def addresses(index):
    if not 0 <= index < MAX_INSTANCES:
        raise ValueError('instance index exceeds the IPv4 address pool')
    network = int(IPv4Address('10.0.0.0'))
    return str(IPv4Address(network + 1)), str(IPv4Address(network + index + 2))
