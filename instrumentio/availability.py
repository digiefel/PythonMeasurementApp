"""GPIB interface preflight, without sending commands to an instrument."""

import ctypes as ct
import re

from .protocol import InstrumentError

VI_SUCCESS_DEV_NPRESENT = 0x3FFF007D


def gpib_interface_address(address):
    match = re.match(r"GPIB(\d*)::", address, re.IGNORECASE)
    return f"GPIB{match.group(1) or '0'}::INTFC" if match else None


def check_gpib_interface(address, open_resource, close_resource):
    """Use the caller's VISA backend; enumeration can contain stale resources."""
    interface = gpib_interface_address(address)
    if interface is None:
        return
    try:
        session, status = open_resource(interface)
    except Exception as exc:
        raise InstrumentError(f"GPIB interface {interface} is unavailable: {exc}") from exc
    try:
        if status == VI_SUCCESS_DEV_NPRESENT:
            raise InstrumentError(f"GPIB interface {interface} is configured but not responding.")
    finally:
        close_resource(session)


def check_native_gpib_interface(address):
    """Run in the existing 32-bit worker, before vendor initialization."""
    if gpib_interface_address(address) is None:
        return
    from .emergency import _load_visa, _check

    visa = _load_visa()
    rm = ct.c_uint32()
    _check(visa.viOpenDefaultRM(ct.byref(rm)), "Open VISA resource manager")
    try:
        def open_resource(resource):
            session = ct.c_uint32()
            status = visa.viOpen(rm, resource.encode(), 0, 0, ct.byref(session))
            _check(status, "Open GPIB interface")
            return session, status

        check_gpib_interface(address, open_resource,
                             lambda session: _check(visa.viClose(session), "Close GPIB interface"))
    finally:
        _check(visa.viClose(rm), "Close VISA resource manager")
