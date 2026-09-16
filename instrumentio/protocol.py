"""Shared execution limits and connection outcomes; no driver dependencies."""

# Connection establishment and shutdown are bounded; measurement duration is not.
CONNECT_TIMEOUT_S = 10.0
STOP_TIMEOUT_S = 5.0


class InstrumentError(RuntimeError):
    """The connection failed; details are recorded in the application log."""


class InstrumentCancelled(InstrumentError):
    """The connection was stopped and its cleanup completed."""
