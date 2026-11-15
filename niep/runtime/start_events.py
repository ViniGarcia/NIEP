"""Opt-in runtime start instrumentation scoped to the topology-up request."""
from contextlib import contextmanager
from contextvars import ContextVar


_observer = ContextVar('niep_start_observer', default=None)


@contextmanager
def capture_starts(observer):
    token = _observer.set(observer)
    try:
        yield
    finally:
        _observer.reset(token)


@contextmanager
def timed_start(kind, resource):
    observer = _observer.get()
    if observer is None:
        yield
        return
    ticket = observer.prepare(kind, resource)
    ticket.begin()
    try:
        yield
    except BaseException as exc:
        ticket.failed(exc)
        raise
    else:
        ticket.finished()
