"""Standalone out-of-band B1500 emergency safe-shutdown.

Opens an independent 32-bit VISA session and drives the instrument into a
physically safe state, so a running measurement can be stopped even while the
main bridge worker is blocked inside a sweep read. This path does not depend on
any procedure code running its own cleanup.

Two steps, both straight from the B1500 programming manual (Edition 15):
  1. device clear -> ends the operation. While something is running, "the AB
     command cannot enter the command input buffer ... use a device clear to
     end the operation" (AB reference, page 4-34).
  2. *RST         -> resets to the initial settings, in which all output
     switches are OFF (page 4-184). That is the safe state, so DZ/CL are not
     needed.

AB is deliberately NOT sent. The manual requires AB before *RST only "while a
sweep measurement is being performed" (*RST reference, page 4-184), and the
device clear above has already ended the operation. AB would also add nothing
to the safe state -- "if the B1500 just keeps to force the DC bias, the AB
command does not stop the DC bias output" (page 4-33) -- while writing it to a
busy instrument blocks until the VISA timeout expires.

Run as:  python -m instrumentio.oob_abort <VISA_ADDRESS>

This module deliberately loads only ``visa32.dll`` directly (not the heavier
``bindings`` module that also loads the agb1500/WGFMU DLLs) so it starts fast --
a safe-shutdown should land in well under a second.
"""

from __future__ import annotations

import ctypes as ct
import os
import sys

# VI_ATTR_TMO_VALUE: VISA I/O timeout attribute (milliseconds).
VI_ATTR_TMO_VALUE = 0x3FFF001A


def _load_visa32():
    path = os.environ.get("PYMEASUREMENT_VISA32_DLL", r"C:\Windows\SysWOW64\visa32.dll")
    return ct.WinDLL(path)


def _write(visa, session, command: str) -> None:
    """Best-effort VISA write of a single command; never raises."""
    try:
        payload = (command + "\n").encode("ascii")
        count = ct.c_uint32(0)
        visa.viWrite(session, payload, len(payload), ct.byref(count))
    except Exception:
        pass


def safe_abort(address: str, timeout_ms: int = 2000) -> int:
    """Reset the instrument at ``address`` to its safe initial state.

    Issues device clear -> *RST. Returns 0 once the sequence has been issued,
    or a small nonzero code if the VISA session could not be opened.
    """
    try:
        visa = _load_visa32()
    except OSError:
        return 3

    rm = ct.c_ulong(0)
    session = ct.c_ulong(0)
    if visa.viOpenDefaultRM(ct.byref(rm)) < 0:
        return 1
    try:
        if visa.viOpen(rm, address.encode(), 0, timeout_ms, ct.byref(session)) < 0:
            return 2
        try:
            try:
                visa.viSetAttribute(session, VI_ATTR_TMO_VALUE, int(timeout_ms))
            except Exception:
                pass

            # 1. Device clear: ends the running operation (manual page 4-34).
            visa.viClear(session)

            # 2. Reset to the initial settings, in which all output switches
            #    are OFF -- the de-energized safe state (manual page 4-184).
            _write(visa, session, "*RST")
        finally:
            try:
                visa.viClose(session)
            except Exception:
                pass
    finally:
        try:
            visa.viClose(rm)
        except Exception:
            pass
    return 0


def main(argv) -> int:
    if len(argv) < 2:
        print("usage: python -m instrumentio.oob_abort <VISA_ADDRESS>", file=sys.stderr)
        return 2
    return safe_abort(argv[1])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
