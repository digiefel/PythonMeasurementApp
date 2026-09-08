"""Shared execution limits and connection outcomes; no driver dependencies."""

# The application permits native operations with a 120-second I/O timeout.
OPERATION_TIMEOUT_S = 130.0
STOP_TIMEOUT_S = 5.0


class InstrumentError(RuntimeError):
    """The connection failed; details are recorded in the application log."""


class InstrumentCancelled(InstrumentError):
    """The connection was stopped and its cleanup completed."""
