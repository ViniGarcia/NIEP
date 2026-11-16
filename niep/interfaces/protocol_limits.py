"""Shared frame bounds for the local daemon and its clients."""

MAX_REQUEST_BYTES = 64 * 1024
# Per-resource snapshots for 512 instances exceed the former 64 KiB bound.
MAX_RESPONSE_BYTES = 1024 * 1024
