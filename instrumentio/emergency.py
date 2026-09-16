"""Independent shutdown after the normal instrument process has been stopped.

B1500 Programming Guide 4-33/34: use device clear when AB cannot enter the
command buffer. Device clear restores initial settings (SMU switches open,
2-88). B1530A Guide 4-50: initialize resets WGFMU channels; abort alone retains
their voltage (4-9). Exit success means these operations succeeded, not a
measurement of the physical output voltage.

References are local: docs/B1500 Programmers Guide 9018-01851.pdf, printed
pp. 4-33–34 (AB), 2-88 (device-clear defaults), 4-161 (*OPC?); and
docs/B1500 WGFMU Guide.pdf, pp. 4-9 and 4-50. The helper must run only after
the old owner exits; otherwise a stale command could reapply bias after clear.
"""

import ctypes as ct
import logging
import os
import sys


IO_TIMEOUT_MS = 2000
PROCESS_TIMEOUT_S = 15
VI_ATTR_TMO_VALUE = 0x3FFF001A
VI_ERROR_TMO = -1073807339
logger = logging.getLogger(__name__)

def _load_visa():
    visa = ct.WinDLL(os.environ.get("PYMEASUREMENT_VISA32_DLL", r"C:\Windows\SysWOW64\visa32.dll"))
    session = ct.c_uint32
    signatures = {
        "viOpenDefaultRM": [ct.POINTER(session)],
        "viOpen": [session, ct.c_char_p, ct.c_uint32, ct.c_uint32, ct.POINTER(session)],
        "viSetAttribute": [session, ct.c_uint32, ct.c_uint32],
        "viClear": [session],
        "viWrite": [session, ct.c_char_p, ct.c_uint32, ct.POINTER(ct.c_uint32)],
        "viRead": [session, ct.c_void_p, ct.c_uint32, ct.POINTER(ct.c_uint32)],
        "viClose": [session],
    }
    for name, arguments in signatures.items():
        function = getattr(visa, name)
        function.argtypes = arguments
        function.restype = ct.c_int32
    return visa


def _check(status, operation):
    if status == VI_ERROR_TMO:
        raise RuntimeError(f"{operation} timed out before VISA confirmed completion (0xBFFF0015)")
    if status < 0:
        raise RuntimeError(f"{operation} failed: {status} (0x{status & 0xffffffff:08X})")


def _write(visa, session, command):
    data = (command + "\n").encode("ascii")
    count = ct.c_uint32()
    status = visa.viWrite(session, data, len(data), ct.byref(count))
    _check(status, f"Sending {command}")
    if count.value != len(data):
        raise RuntimeError(f"Incomplete write of {command}: {count.value}/{len(data)} bytes")


def clear_and_confirm(visa, session):
    """Clear on the owning thread, after outstanding I/O has returned.

    Device clear also discards VISA's formatted buffers, so the raw completion
    read cannot consume leftover measurement data or a buffered driver reply.
    It already initializes the B1500; an additional *RST is unnecessary.
    """
    _check(visa.viSetAttribute(session, VI_ATTR_TMO_VALUE, IO_TIMEOUT_MS), "Set shutdown I/O timeout")
    logger.info("Shutdown: issuing B1500 device clear")
    _check(visa.viClear(session), "Device clear")
    logger.info("Shutdown: waiting for device-clear completion (*OPC?)")
    _write(visa, session, "*OPC?")
    response, count = ct.create_string_buffer(64), ct.c_uint32()
    _check(visa.viRead(session, response, len(response), ct.byref(count)), "Wait for device-clear completion")
    if response.raw[:count.value].strip() != b"1":
        raise RuntimeError("Instrument did not acknowledge device-clear completion")
    logger.info("Shutdown: B1500 device-clear completion acknowledged")


def shutdown(address, *, wgfmu=False):
    errors = []

    def attempt(operation):
        try:
            operation()
        except Exception as exc:
            errors.append(exc)

    def reset_mainframe():
        visa = _load_visa()
        rm, session = ct.c_uint32(), ct.c_uint32()
        logger.info("Emergency shutdown: opening VISA resource manager")
        _check(visa.viOpenDefaultRM(ct.byref(rm)), "Open VISA resource manager")
        try:
            logger.info("Emergency shutdown: opening %s", address)
            _check(visa.viOpen(rm, address.encode(), 0, IO_TIMEOUT_MS, ct.byref(session)), "Open instrument")
            try:
                clear_and_confirm(visa, session)
            finally:
                attempt(lambda: _check(visa.viClose(session), "Close instrument"))
        finally:
            attempt(lambda: _check(visa.viClose(rm), "Close VISA resource manager"))

    attempt(reset_mainframe)
    if wgfmu:
        def reset_wgfmu():
            # Import the native library only in this 32-bit helper, when used.
            from .bindings import dll_wgfmu, require_dll
            driver = require_dll(dll_wgfmu, "PYMEASUREMENT_WGFMU_DLL")
            _check(driver.WGFMU_openSession(address.encode()), "Open WGFMU")
            try:
                attempt(lambda: _check(driver.WGFMU_setTimeout(IO_TIMEOUT_MS / 1000), "Set WGFMU abort timeout"))
                attempt(lambda: _check(driver.WGFMU_initialize(), "Reset WGFMU channels"))
            finally:
                attempt(lambda: _check(driver.WGFMU_closeSession(), "Close WGFMU"))
        attempt(reset_wgfmu)
    if errors:
        raise ExceptionGroup("Instrument emergency shutdown failed", errors)


def main():
    from app_logging import configure_logging
    configure_logging()
    try:
        shutdown(sys.argv[1], wgfmu="--wgfmu" in sys.argv[2:])
    except Exception as exc:
        # Preserve the failed operations across the process boundary. The outer
        # ExceptionGroup message alone hides whether reset, acknowledgement, or
        # connection cleanup failed.
        def details(error):
            if isinstance(error, BaseExceptionGroup):
                return "; ".join(details(child) for child in error.exceptions)
            return str(error)

        print(details(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
