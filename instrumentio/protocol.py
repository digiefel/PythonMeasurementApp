"""Shared execution limits and connection outcomes; no driver dependencies.

Worker terminal replies are ["stopped"] or ["error", reason, traceback, cleanup_ok].
An operation error with cleanup_ok=True retires the connection without repeating
instrument shutdown. Missing/failed cleanup requires the independent fallback.
"""

# Connection establishment and shutdown are bounded; measurement duration is not.
CONNECT_TIMEOUT_S = 10.0
STOP_TIMEOUT_S = 5.0


class InstrumentError(RuntimeError):
    """The connection failed; details are recorded in the application log."""


class InstrumentCancelled(InstrumentError):
    """The connection was stopped and its cleanup completed."""
