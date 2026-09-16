"""Hold instrument ownership across normal execution and emergency shutdown."""

import hashlib
import os
from pathlib import Path
import tempfile


class InstrumentLease:
    def __init__(self, address):
        key = hashlib.sha256(address.strip().upper().encode()).hexdigest()
        path = Path(tempfile.gettempdir()) / f"pymeasurement-{key}.lock"
        self.file = open(path, "a+b")
        try:
            if self.file.tell() == 0:
                self.file.write(b"\0")
                self.file.flush()
            self.file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise RuntimeError("The instrument is already in use by another application instance.") from exc

    def close(self):
        # Closing releases the OS lock. Keep the file: unlinking it would allow
        # callers to lock different files for the same instrument.
        self.file.close()
