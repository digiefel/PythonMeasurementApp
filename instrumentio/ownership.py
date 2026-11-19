"""Hold instrument ownership across normal execution and emergency shutdown."""

import hashlib
import os
from pathlib import Path
import tempfile
import threading
import time

from .availability import gpib_interface_address


def _open_lock_file(name):
    """Open the lock file that every process using `name` shares."""
    key = hashlib.sha256(name.strip().upper().encode()).hexdigest()
    file = open(Path(tempfile.gettempdir()) / f"pymeasurement-{key}.lock", "a+b")
    if file.tell() == 0:
        file.write(b"\0")
        file.flush()
    return file


def _try_lock(file):
    """Lock the file, or raise OSError when another process holds it."""
    file.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(file):
    file.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(file, fcntl.LOCK_UN)


class InstrumentLease:
    def __init__(self, address):
        self.file = _open_lock_file(address)
        try:
            _try_lock(self.file)
        except OSError as exc:
            self.file.close()
            raise RuntimeError("The instrument is already in use by another application instance.") from exc

    def close(self):
        # Closing releases the OS lock. Keep the file: unlinking it would allow
        # callers to lock different files for the same instrument.
        self.file.close()


class BusLock:
    """One complete exchange at a time on a GPIB interface, across threads and processes.

    Hold it from sending a command until its answer has been read, so that no other
    traffic lands in between. An instrument measuring on its own does not hold it.
    Stopping a measurement never waits for it. The prober and the B1500 share one
    interface, so both take this lock. Reentrant within a thread; a no-op for
    addresses that are not GPIB.
    """

    RETRY_S = 0.001

    def __init__(self, address):
        interface = gpib_interface_address(address)
        self._file = _open_lock_file(f"bus {interface}") if interface else None
        self._threads = threading.RLock()
        self._depth = 0

    def acquire(self, blocking=True, cancelled=None):
        """Return False when not blocking and busy, or when `cancelled` is set while waiting."""
        if not self._threads.acquire(blocking=blocking):
            return False
        if self._depth == 0 and self._file is not None:
            while True:
                try:
                    _try_lock(self._file)
                    break
                except OSError:
                    if not blocking or (cancelled is not None and cancelled.is_set()):
                        self._threads.release()
                        return False
                    time.sleep(self.RETRY_S)
        self._depth += 1
        return True

    def release(self):
        self._depth -= 1
        if self._depth == 0 and self._file is not None:
            _unlock(self._file)
        self._threads.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
