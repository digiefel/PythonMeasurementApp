"""
Python bindings for B1500 and WGFMU instruments using ctypes.

This module provides ctypes wrappers for the B1500 (agb1500_32.dll) and WGFMU (WGFMU.dll) instrument libraries.
It includes all functions from the respective header files, with proper argtypes and restypes defined.

Note: Some argtypes may need refinement based on exact VISA types. This is a generated starting point.
"""

import ctypes as ct
import re
import warnings

# Define VISA types (from vpptype.h)
ViStatus = ct.c_long
ViSession = ct.c_ulong
ViBoolean = ct.c_ushort
ViInt32 = ct.c_long
ViInt16 = ct.c_short
ViReal64 = ct.c_double
ViReal32 = ct.c_float
ViString = ct.c_char_p
ViRsrc = ct.c_char_p
ViPBoolean = ct.POINTER(ViBoolean)
ViPInt32 = ct.POINTER(ViInt32)
ViPInt16 = ct.POINTER(ViInt16)
ViPReal64 = ct.POINTER(ViReal64)
ViPReal32 = ct.POINTER(ViReal32)
ViPSession = ct.POINTER(ViSession)

# Hardware channel helpers
SMU_CHANNEL_MAP = {
    "SMU1": 3,
    "SMU2": 4,
    "SMU3": 5,
    "SMU4": 6,
}

WGFMU_CHANNEL_MAP = {
    "WGFMU1:RS": 101,
    "WGFMU2:RS": 102,
    "WGFMU3:RS": 201,
    "WGFMU4:RS": 202,
}

WGFMU_SLOT_MAP = {
    101: 1,
    102: 102,
    201: 2,
    202: 202,
}

# Range presets (from agb1500.h: positive = limited auto, negative = fixed, 0 = auto)
B1500_VOLTAGE_RANGES = [
    (0.0, "Auto"),
    (0.5, "Auto (≥0.5 V)"),
    (2.0, "Auto (≥2 V)"),
    (5.0, "Auto (≥5 V)"),
    (20.0, "Auto (≥20 V)"),
    (40.0, "Auto (≥40 V)"),
    (100.0, "Auto (≥100 V)"),
    (200.0, "Auto (≥200 V)"),
    (-0.5, "Fixed 0.5 V"),
    (-2.0, "Fixed 2 V"),
    (-5.0, "Fixed 5 V"),
    (-20.0, "Fixed 20 V"),
    (-40.0, "Fixed 40 V"),
    (-100.0, "Fixed 100 V"),
    (-200.0, "Fixed 200 V"),
]

B1500_CURRENT_RANGES = [
    (0.0, "Auto"),
    (1.0e-12, "Auto (≥1 pA)"),
    (1.0e-11, "Auto (≥10 pA)"),
    (1.0e-10, "Auto (≥100 pA)"),
    (1.0e-9, "Auto (≥1 nA)"),
    (10.0e-9, "Auto (≥10 nA)"),
    (100.0e-9, "Auto (≥100 nA)"),
    (1.0e-6, "Auto (≥1 µA)"),
    (10.0e-6, "Auto (≥10 µA)"),
    (100.0e-6, "Auto (≥100 µA)"),
    (1.0e-3, "Auto (≥1 mA)"),
    (10.0e-3, "Auto (≥10 mA)"),
    (100.0e-3, "Auto (≥100 mA)"),
    (1.0, "Auto (≥1 A)"),
    (-1.0e-12, "Fixed 1 pA"),
    (-1.0e-11, "Fixed 10 pA"),
    (-1.0e-10, "Fixed 100 pA"),
    (-1.0e-9, "Fixed 1 nA"),
    (-10.0e-9, "Fixed 10 nA"),
    (-100.0e-9, "Fixed 100 nA"),
    (-1.0e-6, "Fixed 1 µA"),
    (-10.0e-6, "Fixed 10 µA"),
    (-100.0e-6, "Fixed 100 µA"),
    (-1.0e-3, "Fixed 1 mA"),
    (-10.0e-3, "Fixed 10 mA"),
    (-100.0e-3, "Fixed 100 mA"),
    (-1.0, "Fixed 1 A"),
]

# CMU/C-V helper option lists for UI usage.
B1500_CMU_CHANNELS = [
    (7, "Default CMU"),
]

# Full MFCMU measurement mode list from the B1500 programming guide.
B1500_CMU_MEASUREMENT_MODES_ALL = [
    (1, "R-X"),
    (2, "G-B"),
    (10, "Z-Theta (radian)"),
    (11, "Z-Theta (degree)"),
    (20, "Y-Theta (radian)"),
    (21, "Y-Theta (degree)"),
    (100, "Cp-G"),
    (101, "Cp-D"),
    (102, "Cp-Q"),
    (103, "Cp-Rp"),
    (200, "Cs-Rs"),
    (201, "Cs-D"),
    (202, "Cs-Q"),
    (300, "Lp-G"),
    (301, "Lp-D"),
    (302, "Lp-Q"),
    (303, "Lp-Rp"),
    (400, "Ls-Rs"),
    (401, "Ls-D"),
    (402, "Ls-Q"),
]

B1500_CMU_MODE_NAME_BY_CODE = {code: label for code, label in B1500_CMU_MEASUREMENT_MODES_ALL}

# Split each CMU mode into primary/monitor quantity names used by sweepCv output.
B1500_CMU_MODE_COMPONENTS = {
    1: ("R", "X"),
    2: ("G", "B"),
    10: ("Z", "Theta_rad"),
    11: ("Z", "Theta_deg"),
    20: ("Y", "Theta_rad"),
    21: ("Y", "Theta_deg"),
    100: ("Cp", "G"),
    101: ("Cp", "D"),
    102: ("Cp", "Q"),
    103: ("Cp", "Rp"),
    200: ("Cs", "Rs"),
    201: ("Cs", "D"),
    202: ("Cs", "Q"),
    300: ("Lp", "G"),
    301: ("Lp", "D"),
    302: ("Lp", "Q"),
    303: ("Lp", "Rp"),
    400: ("Ls", "Rs"),
    401: ("Ls", "D"),
    402: ("Ls", "Q"),
}

B1500_CMU_COMPONENT_UNITS = {
    "R": "Ohm",
    "X": "Ohm",
    "Z": "Ohm",
    "Y": "S",
    "G": "S",
    "B": "S",
    "Cp": "F",
    "Cs": "F",
    "Lp": "H",
    "Ls": "H",
    "Rp": "Ohm",
    "Rs": "Ohm",
    "D": "",
    "Q": "",
    "Theta_rad": "rad",
    "Theta_deg": "deg",
}


def get_cmu_mode_name(mode: int) -> str:
    return B1500_CMU_MODE_NAME_BY_CODE.get(mode, f"Mode {mode}")


def get_cmu_mode_components(mode: int) -> tuple[str, str]:
    return B1500_CMU_MODE_COMPONENTS.get(mode, ("Primary", "Monitor"))


def format_cmu_component_label(component: str) -> str:
    unit = B1500_CMU_COMPONENT_UNITS.get(component, "")
    return f"{component} ({unit})" if unit else component


_FMT5_ITEM_RE = re.compile(r"^([A-Za-z])([A-Za-z0-9])([A-Za-z])([+-]?[0-9]*\.?[0-9]+E[+-][0-9]{2})$")


def _parse_fmt5_item(item: str) -> tuple[str, str, str, float]:
    """Parse one FMT1/FMT5 ASCII item into (status, channel, data_type, value).

    Per manual, each item is: Status(1) + Channel(1) + Type(1) + Value(12 digits for FMT 5).
    """
    token = item.strip().rstrip(',')
    match = _FMT5_ITEM_RE.match(token)
    if not match:
        raise ValueError(f"Invalid FMT5 token: {item!r}")
    status, channel, data_type, value_text = match.groups()
    return status, channel, data_type, float(value_text)


def _parse_scpi_status(item: str) -> int:
    """Extract status from the first character of a FMT 5 data item.

    The first character encodes measurement status:
    N=normal, T=another compliance, C=this compliance,
    V=over range, X=oscillation, G=search not found, D=other.
    """
    status_map = {
        'N': 0,
        'T': 1,
        'C': 2,
        'V': 4,
        'X': 8,
        'G': 16,
        'D': 32,
        'S': 64,
        'U': 128,
        'F': 256,
    }
    return status_map.get(item[0], 0)


# Curated subset shown in the UI by default.
B1500_CMU_MEASUREMENT_MODES = [
    (100, "Cp-G"),
    (103, "Cp-Rp"),
    (200, "Cs-Rs"),
    (11, "Z-Theta (degree)"),
]

B1500_CMU_INTEGRATION_MODES = [
    (0, "Auto"),
    (1, "Manual"),
    (2, "PLC"),
]

# MFCMU measurement range argument for sweepCv/spotCmuMeas.
# Values are representative inputs for each documented range bucket.
B1500_CMU_SWEEP_RANGES = [
    (0.0, "Auto ranging"),
    (50.0, "50 Ohm"),
    (100.0, "100 Ohm"),
    (300.0, "300 Ohm"),
    (1000.0, "1 kOhm"),
    (3000.0, "3 kOhm"),
    (10000.0, "10 kOhm"),
    (30000.0, "30 kOhm"),
    (100000.0, "100 kOhm"),
    (300001.0, "300 kOhm"),
]

# WGFMU constants (from WGFMU.cs)
WGFMU_OPERATION_MODE_OFFSET = 2000
WGFMU_OPERATION_MODE_DC = WGFMU_OPERATION_MODE_OFFSET + 0
WGFMU_OPERATION_MODE_FASTIV = WGFMU_OPERATION_MODE_OFFSET + 1
WGFMU_OPERATION_MODE_PG = WGFMU_OPERATION_MODE_OFFSET + 2
WGFMU_OPERATION_MODE_SMU = WGFMU_OPERATION_MODE_OFFSET + 3

WGFMU_FORCE_VOLTAGE_RANGE_OFFSET = 3000
WGFMU_FORCE_VOLTAGE_RANGE_AUTO = WGFMU_FORCE_VOLTAGE_RANGE_OFFSET + 0
WGFMU_FORCE_VOLTAGE_RANGE_3V = WGFMU_FORCE_VOLTAGE_RANGE_OFFSET + 1
WGFMU_FORCE_VOLTAGE_RANGE_5V = WGFMU_FORCE_VOLTAGE_RANGE_OFFSET + 2
WGFMU_FORCE_VOLTAGE_RANGE_10V_NEGATIVE = WGFMU_FORCE_VOLTAGE_RANGE_OFFSET + 3
WGFMU_FORCE_VOLTAGE_RANGE_10V_POSITIVE = WGFMU_FORCE_VOLTAGE_RANGE_OFFSET + 4

WGFMU_MEASURE_MODE_OFFSET = 4000
WGFMU_MEASURE_MODE_VOLTAGE = WGFMU_MEASURE_MODE_OFFSET + 0
WGFMU_MEASURE_MODE_CURRENT = WGFMU_MEASURE_MODE_OFFSET + 1

WGFMU_MEASURE_VOLTAGE_RANGE_OFFSET = 5000
WGFMU_MEASURE_VOLTAGE_RANGE_5V = WGFMU_MEASURE_VOLTAGE_RANGE_OFFSET + 1
WGFMU_MEASURE_VOLTAGE_RANGE_10V = WGFMU_MEASURE_VOLTAGE_RANGE_OFFSET + 2

WGFMU_MEASURE_CURRENT_RANGE_OFFSET = 6000
WGFMU_MEASURE_CURRENT_RANGE_1UA = WGFMU_MEASURE_CURRENT_RANGE_OFFSET + 1
WGFMU_MEASURE_CURRENT_RANGE_10UA = WGFMU_MEASURE_CURRENT_RANGE_OFFSET + 2
WGFMU_MEASURE_CURRENT_RANGE_100UA = WGFMU_MEASURE_CURRENT_RANGE_OFFSET + 3
WGFMU_MEASURE_CURRENT_RANGE_1MA = WGFMU_MEASURE_CURRENT_RANGE_OFFSET + 4
WGFMU_MEASURE_CURRENT_RANGE_10MA = WGFMU_MEASURE_CURRENT_RANGE_OFFSET + 5

WGFMU_MEASURE_ENABLED_OFFSET = 7000
WGFMU_MEASURE_ENABLED_DISABLE = WGFMU_MEASURE_ENABLED_OFFSET + 0
WGFMU_MEASURE_ENABLED_ENABLE = WGFMU_MEASURE_ENABLED_OFFSET + 1

WGFMU_MEASURE_EVENT_DATA_OFFSET = 12000
WGFMU_MEASURE_EVENT_DATA_AVERAGED = WGFMU_MEASURE_EVENT_DATA_OFFSET + 0
WGFMU_MEASURE_EVENT_DATA_RAW = WGFMU_MEASURE_EVENT_DATA_OFFSET + 1

WGFMU_FORCE_VOLTAGE_RANGES = [
    (WGFMU_FORCE_VOLTAGE_RANGE_AUTO, "Auto"),
    (WGFMU_FORCE_VOLTAGE_RANGE_3V, "3 V"),
    (WGFMU_FORCE_VOLTAGE_RANGE_5V, "5 V"),
    (WGFMU_FORCE_VOLTAGE_RANGE_10V_NEGATIVE, "10 V Negative"),
    (WGFMU_FORCE_VOLTAGE_RANGE_10V_POSITIVE, "10 V Positive"),
]

WGFMU_MEASURE_VOLTAGE_RANGES = [
    (WGFMU_MEASURE_VOLTAGE_RANGE_5V, "5 V"),
    (WGFMU_MEASURE_VOLTAGE_RANGE_10V, "10 V"),
]

WGFMU_MEASURE_CURRENT_RANGES = [
    (WGFMU_MEASURE_CURRENT_RANGE_1UA, "1 µA"),
    (WGFMU_MEASURE_CURRENT_RANGE_10UA, "10 µA"),
    (WGFMU_MEASURE_CURRENT_RANGE_100UA, "100 µA"),
    (WGFMU_MEASURE_CURRENT_RANGE_1MA, "1 mA"),
    (WGFMU_MEASURE_CURRENT_RANGE_10MA, "10 mA"),
]

# WGFMU status codes (from WGFMU manual)
WGFMU_STATUS_COMPLETED = 10000
WGFMU_STATUS_DONE = 10001
WGFMU_STATUS_RUNNING = 10002
WGFMU_STATUS_ABORT_COMPLETED = 10003
WGFMU_STATUS_ABORTED = 10004

# Load DLLs
dll_b1500 = ct.windll.LoadLibrary(r"C:\Program Files (x86)\IVI Foundation\VISA\WinNT\Bin\agb1500_32.dll")
dll_wgfmu = ct.windll.LoadLibrary(r"C:\Windows\SysWOW64\WGFMU.dll")
dll_visa32 = ct.windll.LoadLibrary(r"C:\Windows\SysWOW64\visa32.dll")

# VISA attribute constants for SCPI streaming
VI_ATTR_TERMCHAR = 0x3FFF0018
VI_ATTR_TERMCHAR_EN = 0x3FFF0038

# B1500 Function declarations
if dll_b1500:
    dll_b1500.agb1500_init.argtypes = [ViRsrc, ViBoolean, ViBoolean, ViPSession]
    dll_b1500.agb1500_init.restype = ViStatus

    dll_b1500.agb1500_close.argtypes = [ViSession]
    dll_b1500.agb1500_close.restype = ViStatus

    dll_b1500.agb1500_reset.argtypes = [ViSession]
    dll_b1500.agb1500_reset.restype = ViStatus

    dll_b1500.agb1500_self_test.argtypes = [ViSession, ViPInt16, ct.c_char_p]
    dll_b1500.agb1500_self_test.restype = ViStatus

    dll_b1500.agb1500_error_query.argtypes = [ViSession, ViPInt32, ct.c_char_p]
    dll_b1500.agb1500_error_query.restype = ViStatus

    dll_b1500.agb1500_error_message.argtypes = [ViSession, ViStatus, ct.c_char_p]
    dll_b1500.agb1500_error_message.restype = ViStatus

    dll_b1500.agb1500_revision_query.argtypes = [ViSession, ct.c_char_p, ct.c_char_p]
    dll_b1500.agb1500_revision_query.restype = ViStatus

    dll_b1500.agb1500_timeOut.argtypes = [ViSession, ViInt32]
    dll_b1500.agb1500_timeOut.restype = ViStatus

    dll_b1500.agb1500_timeOut_Q.argtypes = [ViSession, ViPInt32]
    dll_b1500.agb1500_timeOut_Q.restype = ViStatus

    dll_b1500.agb1500_errorQueryDetect.argtypes = [ViSession, ViBoolean]
    dll_b1500.agb1500_errorQueryDetect.restype = ViStatus

    dll_b1500.agb1500_errorQueryDetect_Q.argtypes = [ViSession, ViPBoolean]
    dll_b1500.agb1500_errorQueryDetect_Q.restype = ViStatus

    dll_b1500.agb1500_dcl.argtypes = [ViSession]
    dll_b1500.agb1500_dcl.restype = ViStatus

    dll_b1500.agb1500_opc_Q.argtypes = [ViSession, ViPBoolean]
    dll_b1500.agb1500_opc_Q.restype = ViStatus

    dll_b1500.agb1500_readStatusByte_Q.argtypes = [ViSession, ViPInt16]
    dll_b1500.agb1500_readStatusByte_Q.restype = ViStatus

    dll_b1500.agb1500_cmd.argtypes = [ViSession, ViString]
    dll_b1500.agb1500_cmd.restype = ViStatus

    dll_b1500.agb1500_cmdString_Q.argtypes = [ViSession, ViString, ViInt32, ct.c_char_p]
    dll_b1500.agb1500_cmdString_Q.restype = ViStatus

    dll_b1500.agb1500_cmdData_Q.argtypes = [ViSession, ViString, ViInt32, ct.c_char_p]
    dll_b1500.agb1500_cmdData_Q.restype = ViStatus

    dll_b1500.agb1500_cmdInt.argtypes = [ViSession, ViString, ViInt32]
    dll_b1500.agb1500_cmdInt.restype = ViStatus

    dll_b1500.agb1500_cmdInt16_Q.argtypes = [ViSession, ViString, ViPInt16]
    dll_b1500.agb1500_cmdInt16_Q.restype = ViStatus

    dll_b1500.agb1500_cmdInt32_Q.argtypes = [ViSession, ViString, ViPInt32]
    dll_b1500.agb1500_cmdInt32_Q.restype = ViStatus

    dll_b1500.agb1500_cmdInt16Arr_Q.argtypes = [ViSession, ViString, ViInt32, ct.POINTER(ViInt16), ViPInt32]
    dll_b1500.agb1500_cmdInt16Arr_Q.restype = ViStatus

    dll_b1500.agb1500_cmdInt32Arr_Q.argtypes = [ViSession, ViString, ViInt32, ct.POINTER(ViInt32), ViPInt32]
    dll_b1500.agb1500_cmdInt32Arr_Q.restype = ViStatus

    dll_b1500.agb1500_cmdReal.argtypes = [ViSession, ViString, ViReal64]
    dll_b1500.agb1500_cmdReal.restype = ViStatus

    dll_b1500.agb1500_cmdReal64_Q.argtypes = [ViSession, ViString, ViPReal64]
    dll_b1500.agb1500_cmdReal64_Q.restype = ViStatus

    dll_b1500.agb1500_cmdReal64Arr_Q.argtypes = [ViSession, ViString, ViInt32, ct.POINTER(ViReal64), ViPInt32]
    dll_b1500.agb1500_cmdReal64Arr_Q.restype = ViStatus

    dll_b1500.agb1500_cmdReal32_Q.argtypes = [ViSession, ViString, ViPReal32]
    dll_b1500.agb1500_cmdReal32_Q.restype = ViStatus

    dll_b1500.agb1500_cmdReal32Arr_Q.argtypes = [ViSession, ViString, ViInt32, ct.POINTER(ViReal32), ViPInt32]
    dll_b1500.agb1500_cmdReal32Arr_Q.restype = ViStatus

    dll_b1500.agb1500_autoCal.argtypes = [ViSession, ViInt32]
    dll_b1500.agb1500_autoCal.restype = ViStatus

    dll_b1500.agb1500_setAdc.argtypes = [ViSession, ViInt32, ViInt32, ViInt32, ViInt32]
    dll_b1500.agb1500_setAdc.restype = ViStatus

    dll_b1500.agb1500_stopMode.argtypes = [ViSession, ViInt32, ViInt32]
    dll_b1500.agb1500_stopMode.restype = ViStatus

    dll_b1500.agb1500_abortMeasure.argtypes = [ViSession]
    dll_b1500.agb1500_abortMeasure.restype = ViStatus

    dll_b1500.agb1500_resetTimestamp.argtypes = [ViSession]
    dll_b1500.agb1500_resetTimestamp.restype = ViStatus

    dll_b1500.agb1500_setSwitch.argtypes = [ViSession, ViInt32, ViInt32]
    dll_b1500.agb1500_setSwitch.restype = ViStatus

    dll_b1500.agb1500_setFilter.argtypes = [ViSession, ViInt32, ViInt32]
    dll_b1500.agb1500_setFilter.restype = ViStatus

    dll_b1500.agb1500_setSerRes.argtypes = [ViSession, ViInt32, ViInt32]
    dll_b1500.agb1500_setSerRes.restype = ViStatus

    dll_b1500.agb1500_setAdcType.argtypes = [ViSession, ViInt32, ViInt32]
    dll_b1500.agb1500_setAdcType.restype = ViStatus

    dll_b1500.agb1500_force.argtypes = [ViSession, ViInt32, ViInt32, ViReal64, ViReal64, ViReal64, ViInt32]
    dll_b1500.agb1500_force.restype = ViStatus

    dll_b1500.agb1500_zeroOutput.argtypes = [ViSession, ViInt32]
    dll_b1500.agb1500_zeroOutput.restype = ViStatus

    dll_b1500.agb1500_recoverOutput.argtypes = [ViSession, ViInt32]
    dll_b1500.agb1500_recoverOutput.restype = ViStatus

    dll_b1500.agb1500_setIv.argtypes = [ViSession, ViInt32, ViInt32, ViReal64, ViReal64, ViReal64, ViInt32, ViReal64, ViReal64, ViReal64, ViReal64, ViReal64]
    dll_b1500.agb1500_setIv.restype = ViStatus

    dll_b1500.agb1500_setPbias.argtypes = [ViSession, ViInt32, ViInt32, ViReal64, ViReal64, ViReal64, ViReal64, ViReal64, ViReal64, ViReal64]
    dll_b1500.agb1500_setPbias.restype = ViStatus

    dll_b1500.agb1500_setPiv.argtypes = [ViSession, ViInt32, ViInt32, ViReal64, ViReal64, ViReal64, ViReal64, ViInt32, ViReal64, ViReal64, ViReal64, ViReal64]
    dll_b1500.agb1500_setPiv.restype = ViStatus

    dll_b1500.agb1500_setSweepSync.argtypes = [ViSession, ViInt32, ViInt32, ViReal64, ViReal64, ViReal64, ViReal64, ViReal64]
    dll_b1500.agb1500_setSweepSync.restype = ViStatus

    dll_b1500.agb1500_setNthSweep.argtypes = [ViSession, ViInt32, ViInt32, ViInt32, ViReal64, ViReal64, ViReal64, ViReal64, ViReal64]
    dll_b1500.agb1500_setNthSweep.restype = ViStatus

    dll_b1500.agb1500_spotMeas.argtypes = [ViSession, ViInt32, ViInt32, ViReal64, ViPReal64, ViPInt32, ViPReal64]
    dll_b1500.agb1500_spotMeas.restype = ViStatus

    dll_b1500.agb1500_measureM.argtypes = [ViSession, ct.POINTER(ViInt32), ct.POINTER(ViInt32), ct.POINTER(ViReal64), ct.POINTER(ViReal64), ct.POINTER(ViInt32), ct.POINTER(ViReal64)]
    dll_b1500.agb1500_measureM.restype = ViStatus

    dll_b1500.agb1500_sweepIv.argtypes = [ViSession, ViInt32, ViInt32, ViReal64, ViPInt32, ct.POINTER(ViReal64), ct.POINTER(ViReal64), ct.POINTER(ViInt32), ct.POINTER(ViReal64)]
    dll_b1500.agb1500_sweepIv.restype = ViStatus

    dll_b1500.agb1500_sweepMiv.argtypes = [ViSession, ct.POINTER(ViInt32), ct.POINTER(ViInt32), ct.POINTER(ViReal64), ViPInt32, ct.POINTER(ViReal64), ct.POINTER(ViReal64), ct.POINTER(ViInt32), ct.POINTER(ViReal64)]
    dll_b1500.agb1500_sweepMiv.restype = ViStatus

    dll_b1500.agb1500_measureP.argtypes = [ViSession, ViInt32, ViInt32, ViReal64, ViPReal64, ViPInt32, ViPReal64]
    dll_b1500.agb1500_measureP.restype = ViStatus

    dll_b1500.agb1500_sweepPiv.argtypes = [ViSession, ViInt32, ViInt32, ViReal64, ViPInt32, ct.POINTER(ViReal64), ct.POINTER(ViReal64), ct.POINTER(ViInt32), ct.POINTER(ViReal64)]
    dll_b1500.agb1500_sweepPiv.restype = ViStatus

    dll_b1500.agb1500_sweepPbias.argtypes = [ViSession, ViInt32, ViInt32, ViReal64, ViPInt32, ct.POINTER(ViReal64), ct.POINTER(ViReal64), ct.POINTER(ViInt32), ct.POINTER(ViReal64)]
    dll_b1500.agb1500_sweepPbias.restype = ViStatus

    dll_b1500.agb1500_msweepIv.argtypes = [ViSession, ViInt32, ViInt32, ViReal64, ViPInt32, ct.POINTER(ViReal64), ct.POINTER(ViReal64), ct.POINTER(ViInt32), ct.POINTER(ViReal64)]
    dll_b1500.agb1500_msweepIv.restype = ViStatus

    dll_b1500.agb1500_msweepMiv.argtypes = [ViSession, ct.POINTER(ViInt32), ct.POINTER(ViInt32), ct.POINTER(ViReal64), ViPInt32, ct.POINTER(ViReal64), ct.POINTER(ViReal64), ct.POINTER(ViInt32), ct.POINTER(ViReal64)]
    dll_b1500.agb1500_msweepMiv.restype = ViStatus

    dll_b1500.agb1500_setBdv.argtypes = [ViSession, ViInt32, ViReal64, ViReal64, ViReal64, ViReal64, ViReal64, ViReal64]
    dll_b1500.agb1500_setBdv.restype = ViStatus

    dll_b1500.agb1500_measureBdv.argtypes = [ViSession, ViInt32, ViPReal64, ViPInt32]
    dll_b1500.agb1500_measureBdv.restype = ViStatus

    dll_b1500.agb1500_setIleak.argtypes = [ViSession, ViInt32, ViReal64, ViReal64, ViReal64, ViReal64, ViReal64, ViReal64]
    dll_b1500.agb1500_setIleak.restype = ViStatus

    dll_b1500.agb1500_measureIleak.argtypes = [ViSession, ViInt32, ViInt32, ViPReal64, ViPInt32]
    dll_b1500.agb1500_measureIleak.restype = ViStatus

    dll_b1500.agb1500_startMeasure.argtypes = [ViSession, ViInt32, ct.POINTER(ViInt32), ct.POINTER(ViInt32), ct.POINTER(ViReal64), ViInt32, ViInt32, ViInt32]
    dll_b1500.agb1500_startMeasure.restype = ViStatus

    dll_b1500.agb1500_readData.argtypes = [ViSession, ViPInt32, ViPInt32, ViPReal64, ViPInt32, ViPInt32]
    dll_b1500.agb1500_readData.restype = ViStatus

    dll_b1500.agb1500_asuLed.argtypes = [ViSession, ViInt32, ViInt32]
    dll_b1500.agb1500_asuLed.restype = ViStatus

    dll_b1500.agb1500_asuPath.argtypes = [ViSession, ViInt32, ViInt32]
    dll_b1500.agb1500_asuPath.restype = ViStatus

    dll_b1500.agb1500_asuRange.argtypes = [ViSession, ViInt32, ViInt32]
    dll_b1500.agb1500_asuRange.restype = ViStatus

    dll_b1500.agb1500_forceCmuDcBias.argtypes = [ViSession, ViInt32, ViReal64]
    dll_b1500.agb1500_forceCmuDcBias.restype = ViStatus

    dll_b1500.agb1500_setCmuInteg.argtypes = [ViSession, ViInt32, ViInt32]
    dll_b1500.agb1500_setCmuInteg.restype = ViStatus

    dll_b1500.agb1500_forceCmuAcLevel.argtypes = [ViSession, ViInt32, ViReal64]
    dll_b1500.agb1500_forceCmuAcLevel.restype = ViStatus

    dll_b1500.agb1500_setCmuFreq.argtypes = [ViSession, ViInt32, ViReal64]
    dll_b1500.agb1500_setCmuFreq.restype = ViStatus

    dll_b1500.agb1500_setCv.argtypes = [ViSession, ViInt32, ViInt32, ViReal64, ViReal64, ViInt32, ViReal64, ViReal64, ViReal64]
    dll_b1500.agb1500_setCv.restype = ViStatus

    dll_b1500.agb1500_spotCmuMeas.argtypes = [ViSession, ViInt32, ViInt32, ViReal64, ct.POINTER(ViReal64), ct.POINTER(ViInt32), ct.POINTER(ViReal64), ct.POINTER(ViInt32), ViPReal64]
    dll_b1500.agb1500_spotCmuMeas.restype = ViStatus

    dll_b1500.agb1500_sweepCv.argtypes = [ViSession, ViInt32, ViInt32, ViReal64, ViPInt32, ct.POINTER(ViReal64), ct.POINTER(ViReal64), ct.POINTER(ViInt32), ct.POINTER(ViReal64), ct.POINTER(ViInt32), ct.POINTER(ViReal64)]
    dll_b1500.agb1500_sweepCv.restype = ViStatus

    dll_b1500.agb1500_scuuLed.argtypes = [ViSession, ViInt32, ViInt32]
    dll_b1500.agb1500_scuuLed.restype = ViStatus

    dll_b1500.agb1500_scuuPath.argtypes = [ViSession, ViInt32, ViInt32]
    dll_b1500.agb1500_scuuPath.restype = ViStatus

    dll_b1500.agb1500_setSample.argtypes = [ViSession, ViReal64, ViReal64, ViReal64, ViInt32]
    dll_b1500.agb1500_setSample.restype = ViStatus

    dll_b1500.agb1500_addSampleSyncIv.argtypes = [ViSession, ViInt32, ViInt32, ViReal64, ViReal64, ViReal64, ViReal64]
    dll_b1500.agb1500_addSampleSyncIv.restype = ViStatus

    dll_b1500.agb1500_clearSampleSync.argtypes = [ViSession]
    dll_b1500.agb1500_clearSampleSync.restype = ViStatus

    dll_b1500.agb1500_sampleIv.argtypes = [ViSession, ct.POINTER(ViInt32), ct.POINTER(ViInt32), ct.POINTER(ViReal64), ViPInt32, ct.POINTER(ViInt32), ct.POINTER(ViReal64), ct.POINTER(ViInt32), ct.POINTER(ViReal64)]
    dll_b1500.agb1500_sampleIv.restype = ViStatus

    dll_b1500.agb1500_setSampleMode.argtypes = [ViSession, ViInt32]
    dll_b1500.agb1500_setSampleMode.restype = ViStatus

    dll_b1500.agb1500_setCmuAdjustMode.argtypes = [ViSession, ViInt32, ViInt32]
    dll_b1500.agb1500_setCmuAdjustMode.restype = ViStatus

    dll_b1500.agb1500_execCmuAdjust.argtypes = [ViSession, ViInt32, ViPInt16]
    dll_b1500.agb1500_execCmuAdjust.restype = ViStatus

    dll_b1500.agb1500_setOpenCorrMode.argtypes = [ViSession, ViInt32, ViInt32]
    dll_b1500.agb1500_setOpenCorrMode.restype = ViStatus

    dll_b1500.agb1500_execOpenCorr.argtypes = [ViSession, ViInt32, ViReal64, ViInt32, ViReal64, ViReal64, ViPInt16]
    dll_b1500.agb1500_execOpenCorr.restype = ViStatus

    dll_b1500.agb1500_setShortCorrMode.argtypes = [ViSession, ViInt32, ViInt32]
    dll_b1500.agb1500_setShortCorrMode.restype = ViStatus

    dll_b1500.agb1500_execShortCorr.argtypes = [ViSession, ViInt32, ViReal64, ViInt32, ViReal64, ViReal64, ViPInt16]
    dll_b1500.agb1500_execShortCorr.restype = ViStatus

    dll_b1500.agb1500_setLoadCorrMode.argtypes = [ViSession, ViInt32, ViInt32]
    dll_b1500.agb1500_setLoadCorrMode.restype = ViStatus

    dll_b1500.agb1500_execLoadCorr.argtypes = [ViSession, ViInt32, ViReal64, ViInt32, ViReal64, ViReal64, ViPInt16]
    dll_b1500.agb1500_execLoadCorr.restype = ViStatus

    dll_b1500.agb1500_clearCorrData.argtypes = [ViSession, ViInt32, ViInt32]
    dll_b1500.agb1500_clearCorrData.restype = ViStatus

# WGFMU Function declarations
if dll_wgfmu:
    dll_wgfmu.WGFMU_openSession.argtypes = [ct.c_char_p]
    dll_wgfmu.WGFMU_openSession.restype = ct.c_int

    dll_wgfmu.WGFMU_closeSession.argtypes = []
    dll_wgfmu.WGFMU_closeSession.restype = ct.c_int

    dll_wgfmu.WGFMU_initialize.argtypes = []
    dll_wgfmu.WGFMU_initialize.restype = ct.c_int

    dll_wgfmu.WGFMU_setTimeout.argtypes = [ct.c_double]
    dll_wgfmu.WGFMU_setTimeout.restype = ct.c_int

    dll_wgfmu.WGFMU_doSelfCalibration.argtypes = [ct.POINTER(ct.c_int), ct.c_char_p, ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_doSelfCalibration.restype = ct.c_int

    dll_wgfmu.WGFMU_doSelfTest.argtypes = [ct.POINTER(ct.c_int), ct.c_char_p, ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_doSelfTest.restype = ct.c_int

    dll_wgfmu.WGFMU_getChannelIdSize.argtypes = [ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getChannelIdSize.restype = ct.c_int

    dll_wgfmu.WGFMU_getChannelIds.argtypes = [ct.POINTER(ct.c_int), ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getChannelIds.restype = ct.c_int

    dll_wgfmu.WGFMU_getErrorSize.argtypes = [ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getErrorSize.restype = ct.c_int

    dll_wgfmu.WGFMU_getError.argtypes = [ct.c_char_p, ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getError.restype = ct.c_int

    dll_wgfmu.WGFMU_getErrorSummarySize.argtypes = [ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getErrorSummarySize.restype = ct.c_int

    dll_wgfmu.WGFMU_getErrorSummary.argtypes = [ct.c_char_p, ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getErrorSummary.restype = ct.c_int

    dll_wgfmu.WGFMU_treatWarningsAsErrors.argtypes = [ct.c_int]
    dll_wgfmu.WGFMU_treatWarningsAsErrors.restype = ct.c_int

    dll_wgfmu.WGFMU_setWarningLevel.argtypes = [ct.c_int]
    dll_wgfmu.WGFMU_setWarningLevel.restype = ct.c_int

    dll_wgfmu.WGFMU_getWarningLevel.argtypes = [ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getWarningLevel.restype = ct.c_int

    dll_wgfmu.WGFMU_getWarningSummarySize.argtypes = [ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getWarningSummarySize.restype = ct.c_int

    dll_wgfmu.WGFMU_getWarningSummary.argtypes = [ct.c_char_p, ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getWarningSummary.restype = ct.c_int

    dll_wgfmu.WGFMU_openLogFile.argtypes = [ct.c_char_p]
    dll_wgfmu.WGFMU_openLogFile.restype = ct.c_int

    dll_wgfmu.WGFMU_closeLogFile.argtypes = []
    dll_wgfmu.WGFMU_closeLogFile.restype = ct.c_int

    dll_wgfmu.WGFMU_setOperationMode.argtypes = [ct.c_int, ct.c_int]
    dll_wgfmu.WGFMU_setOperationMode.restype = ct.c_int

    dll_wgfmu.WGFMU_getOperationMode.argtypes = [ct.c_int, ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getOperationMode.restype = ct.c_int

    dll_wgfmu.WGFMU_setForceVoltageRange.argtypes = [ct.c_int, ct.c_int]
    dll_wgfmu.WGFMU_setForceVoltageRange.restype = ct.c_int

    dll_wgfmu.WGFMU_getForceVoltageRange.argtypes = [ct.c_int, ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getForceVoltageRange.restype = ct.c_int

    dll_wgfmu.WGFMU_setMeasureMode.argtypes = [ct.c_int, ct.c_int]
    dll_wgfmu.WGFMU_setMeasureMode.restype = ct.c_int

    dll_wgfmu.WGFMU_getMeasureMode.argtypes = [ct.c_int, ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getMeasureMode.restype = ct.c_int

    dll_wgfmu.WGFMU_setMeasureVoltageRange.argtypes = [ct.c_int, ct.c_int]
    dll_wgfmu.WGFMU_setMeasureVoltageRange.restype = ct.c_int

    dll_wgfmu.WGFMU_getMeasureVoltageRange.argtypes = [ct.c_int, ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getMeasureVoltageRange.restype = ct.c_int

    dll_wgfmu.WGFMU_setMeasureCurrentRange.argtypes = [ct.c_int, ct.c_int]
    dll_wgfmu.WGFMU_setMeasureCurrentRange.restype = ct.c_int

    dll_wgfmu.WGFMU_getMeasureCurrentRange.argtypes = [ct.c_int, ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getMeasureCurrentRange.restype = ct.c_int

    dll_wgfmu.WGFMU_setForceDelay.argtypes = [ct.c_int, ct.c_double]
    dll_wgfmu.WGFMU_setForceDelay.restype = ct.c_int

    dll_wgfmu.WGFMU_getForceDelay.argtypes = [ct.c_int, ct.POINTER(ct.c_double)]
    dll_wgfmu.WGFMU_getForceDelay.restype = ct.c_int

    dll_wgfmu.WGFMU_setMeasureDelay.argtypes = [ct.c_int, ct.c_double]
    dll_wgfmu.WGFMU_setMeasureDelay.restype = ct.c_int

    dll_wgfmu.WGFMU_getMeasureDelay.argtypes = [ct.c_int, ct.POINTER(ct.c_double)]
    dll_wgfmu.WGFMU_getMeasureDelay.restype = ct.c_int

    dll_wgfmu.WGFMU_setMeasureEnabled.argtypes = [ct.c_int, ct.c_int]
    dll_wgfmu.WGFMU_setMeasureEnabled.restype = ct.c_int

    dll_wgfmu.WGFMU_isMeasureEnabled.argtypes = [ct.c_int, ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_isMeasureEnabled.restype = ct.c_int

    dll_wgfmu.WGFMU_setTriggerOutMode.argtypes = [ct.c_int, ct.c_int, ct.c_int]
    dll_wgfmu.WGFMU_setTriggerOutMode.restype = ct.c_int

    dll_wgfmu.WGFMU_getTriggerOutMode.argtypes = [ct.c_int, ct.POINTER(ct.c_int), ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getTriggerOutMode.restype = ct.c_int

    dll_wgfmu.WGFMU_connect.argtypes = [ct.c_int]
    dll_wgfmu.WGFMU_connect.restype = ct.c_int

    dll_wgfmu.WGFMU_disconnect.argtypes = [ct.c_int]
    dll_wgfmu.WGFMU_disconnect.restype = ct.c_int

    dll_wgfmu.WGFMU_clear.argtypes = []
    dll_wgfmu.WGFMU_clear.restype = ct.c_int

    dll_wgfmu.WGFMU_createPattern.argtypes = [ct.c_char_p, ct.c_double]
    dll_wgfmu.WGFMU_createPattern.restype = ct.c_int

    dll_wgfmu.WGFMU_addVector.argtypes = [ct.c_char_p, ct.c_double, ct.c_double]
    dll_wgfmu.WGFMU_addVector.restype = ct.c_int

    dll_wgfmu.WGFMU_addVectors.argtypes = [ct.c_char_p, ct.POINTER(ct.c_double), ct.POINTER(ct.c_double), ct.c_int]
    dll_wgfmu.WGFMU_addVectors.restype = ct.c_int

    dll_wgfmu.WGFMU_setVector.argtypes = [ct.c_char_p, ct.c_double, ct.c_double]
    dll_wgfmu.WGFMU_setVector.restype = ct.c_int

    dll_wgfmu.WGFMU_setVectors.argtypes = [ct.c_char_p, ct.POINTER(ct.c_double), ct.POINTER(ct.c_double), ct.c_int]
    dll_wgfmu.WGFMU_setVectors.restype = ct.c_int

    dll_wgfmu.WGFMU_createMergedPattern.argtypes = [ct.c_char_p, ct.c_char_p, ct.c_char_p, ct.c_int]
    dll_wgfmu.WGFMU_createMergedPattern.restype = ct.c_int

    dll_wgfmu.WGFMU_createMultipliedPattern.argtypes = [ct.c_char_p, ct.c_char_p, ct.c_double, ct.c_double]
    dll_wgfmu.WGFMU_createMultipliedPattern.restype = ct.c_int

    dll_wgfmu.WGFMU_createOffsetPattern.argtypes = [ct.c_char_p, ct.c_char_p, ct.c_double, ct.c_double]
    dll_wgfmu.WGFMU_createOffsetPattern.restype = ct.c_int

    dll_wgfmu.WGFMU_setMeasureEvent.argtypes = [ct.c_char_p, ct.c_char_p, ct.c_double, ct.c_int, ct.c_double, ct.c_double, ct.c_int]
    dll_wgfmu.WGFMU_setMeasureEvent.restype = ct.c_int

    dll_wgfmu.WGFMU_setRangeEvent.argtypes = [ct.c_char_p, ct.c_char_p, ct.c_double, ct.c_int]
    dll_wgfmu.WGFMU_setRangeEvent.restype = ct.c_int

    dll_wgfmu.WGFMU_setTriggerOutEvent.argtypes = [ct.c_char_p, ct.c_char_p, ct.c_double, ct.c_double]
    dll_wgfmu.WGFMU_setTriggerOutEvent.restype = ct.c_int

    dll_wgfmu.WGFMU_addSequence.argtypes = [ct.c_int, ct.c_char_p, ct.c_double]
    dll_wgfmu.WGFMU_addSequence.restype = ct.c_int

    dll_wgfmu.WGFMU_addSequences.argtypes = [ct.c_int, ct.POINTER(ct.c_char_p), ct.POINTER(ct.c_double), ct.c_int]
    dll_wgfmu.WGFMU_addSequences.restype = ct.c_int

    dll_wgfmu.WGFMU_getPatternForceValueSize.argtypes = [ct.c_char_p, ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getPatternForceValueSize.restype = ct.c_int

    dll_wgfmu.WGFMU_getPatternForceValues.argtypes = [ct.c_char_p, ct.c_int, ct.POINTER(ct.c_int), ct.POINTER(ct.c_double), ct.POINTER(ct.c_double)]
    dll_wgfmu.WGFMU_getPatternForceValues.restype = ct.c_int

    dll_wgfmu.WGFMU_getPatternForceValue.argtypes = [ct.c_char_p, ct.c_int, ct.POINTER(ct.c_double), ct.POINTER(ct.c_double)]
    dll_wgfmu.WGFMU_getPatternForceValue.restype = ct.c_int

    dll_wgfmu.WGFMU_getPatternInterpolatedForceValue.argtypes = [ct.c_char_p, ct.c_double, ct.POINTER(ct.c_double)]
    dll_wgfmu.WGFMU_getPatternInterpolatedForceValue.restype = ct.c_int

    dll_wgfmu.WGFMU_getPatternMeasureTimeSize.argtypes = [ct.c_char_p, ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getPatternMeasureTimeSize.restype = ct.c_int

    dll_wgfmu.WGFMU_getPatternMeasureTimes.argtypes = [ct.c_char_p, ct.c_int, ct.POINTER(ct.c_int), ct.POINTER(ct.c_double)]
    dll_wgfmu.WGFMU_getPatternMeasureTimes.restype = ct.c_int

    dll_wgfmu.WGFMU_getPatternMeasureTime.argtypes = [ct.c_char_p, ct.c_int, ct.POINTER(ct.c_double)]
    dll_wgfmu.WGFMU_getPatternMeasureTime.restype = ct.c_int

    dll_wgfmu.WGFMU_getForceValueSize.argtypes = [ct.c_int, ct.POINTER(ct.c_double)]
    dll_wgfmu.WGFMU_getForceValueSize.restype = ct.c_int

    dll_wgfmu.WGFMU_getForceValues.argtypes = [ct.c_int, ct.c_double, ct.POINTER(ct.c_int), ct.POINTER(ct.c_double), ct.POINTER(ct.c_double)]
    dll_wgfmu.WGFMU_getForceValues.restype = ct.c_int

    dll_wgfmu.WGFMU_getForceValue.argtypes = [ct.c_int, ct.c_double, ct.POINTER(ct.c_double), ct.POINTER(ct.c_double)]
    dll_wgfmu.WGFMU_getForceValue.restype = ct.c_int

    dll_wgfmu.WGFMU_getInterpolatedForceValue.argtypes = [ct.c_int, ct.c_double, ct.POINTER(ct.c_double)]
    dll_wgfmu.WGFMU_getInterpolatedForceValue.restype = ct.c_int

    dll_wgfmu.WGFMU_getMeasureTimeSize.argtypes = [ct.c_int, ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getMeasureTimeSize.restype = ct.c_int

    dll_wgfmu.WGFMU_getMeasureTimes.argtypes = [ct.c_int, ct.c_int, ct.POINTER(ct.c_int), ct.POINTER(ct.c_double)]
    dll_wgfmu.WGFMU_getMeasureTimes.restype = ct.c_int

    dll_wgfmu.WGFMU_getMeasureTime.argtypes = [ct.c_int, ct.c_int, ct.POINTER(ct.c_double)]
    dll_wgfmu.WGFMU_getMeasureTime.restype = ct.c_int

    dll_wgfmu.WGFMU_getMeasureEventSize.argtypes = [ct.c_int, ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getMeasureEventSize.restype = ct.c_int

    dll_wgfmu.WGFMU_getMeasureEvents.argtypes = [ct.c_int, ct.c_int, ct.POINTER(ct.c_int), ct.POINTER(ct.c_char_p), ct.POINTER(ct.c_char_p), ct.POINTER(ct.c_int), ct.POINTER(ct.c_double), ct.POINTER(ct.c_int), ct.POINTER(ct.c_int), ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getMeasureEvents.restype = ct.c_int

    dll_wgfmu.WGFMU_getMeasureEvent.argtypes = [ct.c_int, ct.c_int, ct.c_char_p, ct.c_char_p, ct.POINTER(ct.c_int), ct.POINTER(ct.c_double), ct.POINTER(ct.c_int), ct.POINTER(ct.c_int), ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getMeasureEvent.restype = ct.c_int

    dll_wgfmu.WGFMU_getMeasureEventAttribute.argtypes = [ct.c_int, ct.c_int, ct.POINTER(ct.c_double), ct.POINTER(ct.c_int), ct.POINTER(ct.c_double), ct.POINTER(ct.c_double), ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getMeasureEventAttribute.restype = ct.c_int

    dll_wgfmu.WGFMU_exportAscii.argtypes = [ct.c_char_p]
    dll_wgfmu.WGFMU_exportAscii.restype = ct.c_int

    dll_wgfmu.WGFMU_update.argtypes = []
    dll_wgfmu.WGFMU_update.restype = ct.c_int

    dll_wgfmu.WGFMU_updateChannel.argtypes = [ct.c_int]
    dll_wgfmu.WGFMU_updateChannel.restype = ct.c_int

    dll_wgfmu.WGFMU_execute.argtypes = []
    dll_wgfmu.WGFMU_execute.restype = ct.c_int

    dll_wgfmu.WGFMU_abort.argtypes = []
    dll_wgfmu.WGFMU_abort.restype = ct.c_int

    dll_wgfmu.WGFMU_abortChannel.argtypes = [ct.c_int]
    dll_wgfmu.WGFMU_abortChannel.restype = ct.c_int

    dll_wgfmu.WGFMU_getStatus.argtypes = [ct.POINTER(ct.c_int), ct.POINTER(ct.c_double), ct.POINTER(ct.c_double)]
    dll_wgfmu.WGFMU_getStatus.restype = ct.c_int

    dll_wgfmu.WGFMU_getChannelStatus.argtypes = [ct.c_int, ct.POINTER(ct.c_int), ct.POINTER(ct.c_double), ct.POINTER(ct.c_double)]
    dll_wgfmu.WGFMU_getChannelStatus.restype = ct.c_int

    dll_wgfmu.WGFMU_waitUntilCompleted.argtypes = []
    dll_wgfmu.WGFMU_waitUntilCompleted.restype = ct.c_int

    dll_wgfmu.WGFMU_getMeasureValueSize.argtypes = [ct.c_int, ct.POINTER(ct.c_int), ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getMeasureValueSize.restype = ct.c_int

    dll_wgfmu.WGFMU_getMeasureValues.argtypes = [ct.c_int, ct.c_int, ct.POINTER(ct.c_int), ct.POINTER(ct.c_double), ct.POINTER(ct.c_double)]
    dll_wgfmu.WGFMU_getMeasureValues.restype = ct.c_int

    dll_wgfmu.WGFMU_getMeasureValue.argtypes = [ct.c_int, ct.c_int, ct.POINTER(ct.c_double), ct.POINTER(ct.c_double)]
    dll_wgfmu.WGFMU_getMeasureValue.restype = ct.c_int

    dll_wgfmu.WGFMU_getCompletedMeasureEventSize.argtypes = [ct.c_int, ct.POINTER(ct.c_int), ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_getCompletedMeasureEventSize.restype = ct.c_int

    dll_wgfmu.WGFMU_isMeasureEventCompleted.argtypes = [ct.c_int, ct.c_char_p, ct.c_char_p, ct.c_int, ct.c_double, ct.c_int, ct.POINTER(ct.c_int), ct.POINTER(ct.c_int), ct.POINTER(ct.c_int), ct.POINTER(ct.c_int)]
    dll_wgfmu.WGFMU_isMeasureEventCompleted.restype = ct.c_int

    dll_wgfmu.WGFMU_dcforceVoltage.argtypes = [ct.c_int, ct.c_double]
    dll_wgfmu.WGFMU_dcforceVoltage.restype = ct.c_int

    dll_wgfmu.WGFMU_dcmeasureValue.argtypes = [ct.c_int, ct.POINTER(ct.c_double)]
    dll_wgfmu.WGFMU_dcmeasureValue.restype = ct.c_int

    dll_wgfmu.WGFMU_dcmeasureAveragedValue.argtypes = [ct.c_int, ct.c_int, ct.c_int, ct.POINTER(ct.c_double)]
    dll_wgfmu.WGFMU_dcmeasureAveragedValue.restype = ct.c_int

# High-level wrapper classes

class B1500Session:
    """
    High-level wrapper for B1500 instrument using ctypes bindings.
    """
    # Constants
    INSTR_ERROR_DETECTED = -1074000633
    CH_ALL = 0
    CH_NOCH = -1
    DATA_TYPE_TEXT = {
        -1: "Dummy",
        1: "Current (measure)",
        2: "Voltage (measure)",
        3: "Current (source)",
        4: "Voltage (source)",
        5: "Timestamp",
        6: "Impedance (R-X)",
        7: "Admittance (G-B)",
        8: "Capacitance",
        9: "Dissipation factor",
        10: "Quality factor",
        11: "Inductance",
        12: "Phase (rad)",
        13: "Phase (deg)",
        14: "Frequency",
        15: "Sampling index",
        16: "Invalid",
    }
    DATA_TYPE_SHORT = {
        -1: "DMY",
        1: "CM",
        2: "VM",
        3: "CS",
        4: "VS",
        5: "TS",
        6: "ZM",
        7: "YM",
        8: "CAP",
        9: "DF",
        10: "QF",
        11: "IND",
        12: "PR",
        13: "PD",
        14: "FRQ",
        15: "IDX",
        16: "INV",
    }
    STATUS_BIT_TEXT = {
        1: "A/D overflow",
        2: "Oscillation / NULL loop unbalanced",
        4: "Other channel compliance / IV amp saturation",
        8: "This channel compliance",
        16: "Search target not found / detection time too long",
        32: "Search stopped / slew too slow",
    }
    IM_MODE = 1  # Measure current
    VM_MODE = 2  # Measure voltage

    IF_MODE = 1  # Force current
    VF_MODE = 2  # Force voltage

    AUTO_RANGE = 0.0

    # Sweep mode definitions (see agb1500.h)
    SWP_IF_SGLLIN = -1   # Single linear current sweep
    SWP_IF_DBLLIN = -3   # Double linear current sweep
    SWP_VF_SGLLIN = 1    # Single linear voltage sweep
    SWP_VF_SGLLOG = 2    # Single log voltage sweep
    SWP_VF_DBLLIN = 3    # Double linear voltage sweep
    SWP_VF_DBLLOG = 4    # Double log voltage sweep
    # CMU modes (from agb1500.h)
    CMUM_R_X = 1
    CMUM_G_B = 2
    CMUM_Z_TRAD = 10
    CMUM_Z_TDEG = 11
    CMUM_Y_TRAD = 20
    CMUM_Y_TDEG = 21
    CMUM_CP_G = 100
    CMUM_CP_D = 101
    CMUM_CP_Q = 102
    CMUM_CP_RP = 103
    CMUM_CS_RS = 200
    CMUM_CS_D = 201
    CMUM_CS_Q = 202
    CMUM_LP_G = 300
    CMUM_LP_D = 301
    CMUM_LP_Q = 302
    CMUM_LP_RP = 303
    CMUM_LS_RS = 400
    CMUM_LS_D = 401
    CMUM_LS_Q = 402
    # Stop/last mode (see agb1500_stopMode)
    STOP_DISABLE = 0      # Do not abort on compliance/abort conditions
    STOP_ENABLE = 1       # Abort on stop conditions
    # hello
    LAST_START = 1        # Return to start level after stop
    LAST_STOP = 2         # Hold stop level after stop
    # Measurement type constants (agb1500.h)
    MEAS_TYPE_MSPOT = 1
    MEAS_TYPE_SWEEP = 2
    
    def __init__(self, gpib_addr="GPIB0::17::INSTR"):
        if not dll_b1500:
            raise RuntimeError("B1500 DLL not loaded.")
        self.gpib_addr = gpib_addr
        self.session = ViSession()
        self._wgfmu = None  # Lazy-loaded WGFMU session
        ret = dll_b1500.agb1500_init(gpib_addr.encode(), 1, 1, ct.byref(self.session))
        if ret != 0:
            raise RuntimeError(f"B1500 init failed: {ret}")

    @property
    def wgfmu(self):
        """Get or create the WGFMU session (lazy initialization)."""
        if self._wgfmu is None:
            self._wgfmu = WGFMUSession(self.gpib_addr)
        return self._wgfmu
    
    def error_query(self):
        """Return (error_number, error_message) from instrument."""
        errnum = ViInt32()
        errmsg = ct.create_string_buffer(256)
        ret = dll_b1500.agb1500_error_query(self.session, ct.byref(errnum), errmsg)
        if ret != 0:
            raise RuntimeError(f"Error query failed: {ret}")
        return errnum.value, errmsg.value.decode(errors='ignore').strip()

    def _describe_status(self, ret):
        """Return human-readable description for a driver status code."""
        try:
            buf = ct.create_string_buffer(256)
            dll_b1500.agb1500_error_message(self.session, ret, buf)
            msg = buf.value.decode(errors="ignore").strip()
            return msg
        except Exception:
            return ""

    def _check_ret(self, ret, context):
        if ret == self.INSTR_ERROR_DETECTED:
            errnum, errmsg = self.error_query()
            raise RuntimeError(f"{context}: instrument error {errnum}: {errmsg} (ret={ret})")
        if ret < 0:
            msg = self._describe_status(ret)
            raise RuntimeError(f"{context} failed: {ret} {f'({msg})' if msg else ''}".strip())
        if ret != 0:
            raise RuntimeError(f"{context} failed: {ret}")

    def reset(self):
        dll_b1500.agb1500_reset(self.session)

    def set_timeout(self, ms):
        dll_b1500.agb1500_timeOut(self.session, ms)

    def enable_error_detect(self, enable):
        dll_b1500.agb1500_errorQueryDetect(self.session, 1 if enable else 0)

    def set_switch(self, channel, state):
        """Control switch matrix channel on/off state."""
        ret = dll_b1500.agb1500_setSwitch(self.session, channel, 1 if state else 0)
        self._check_ret(ret, "Set switch")

    def reset_timestamp(self):
        """Reset internal timestamp for measurements."""
        ret = dll_b1500.agb1500_resetTimestamp(self.session)
        if ret != 0:
            raise RuntimeError(f"Reset timestamp failed: {ret}")

    def stop_mode(self, stop=STOP_DISABLE, last_mode=LAST_STOP):
        """
        Configure stop behavior. Set stop=STOP_DISABLE to prevent the instrument from
        aborting the sweep on compliance; last_mode controls post-stop output level.
        """
        ret = dll_b1500.agb1500_stopMode(self.session, stop, last_mode)
        self._check_ret(ret, "Stop mode")

    def force_current(self, channel, current, compliance=10.0, range_=AUTO_RANGE, polarity=0):
        """Force a current level on the specified channel."""
        ret = dll_b1500.agb1500_force(self.session, channel, self.IF_MODE, range_, current, compliance, polarity)
        self._check_ret(ret, "Force current")

    def force_voltage(self, channel, voltage, compliance=0.1, range_=AUTO_RANGE, polarity=0):
        """Force a voltage level on the specified channel."""
        ret = dll_b1500.agb1500_force(self.session, channel, self.VF_MODE, range_, voltage, compliance, polarity)
        self._check_ret(ret, "Force voltage")

    def asu_path(self, channel, path):
        """Select ASU path for a channel (see B1500 ASU path modes)."""
        ret = dll_b1500.agb1500_asuPath(self.session, channel, path)
        self._check_ret(ret, "ASU path")

    def asu_range(self, channel, rng):
        """Select ASU range for a channel (see B1500 ASU ranges)."""
        ret = dll_b1500.agb1500_asuRange(self.session, channel, rng)
        self._check_ret(ret, "ASU range")

    def asu_led(self, channel, on):
        """Control ASU LED (optional helper)."""
        ret = dll_b1500.agb1500_asuLed(self.session, channel, 1 if on else 0)
        self._check_ret(ret, "ASU LED")

    def set_iv_sweep(self, channel, sweep_mode, range_, start, stop, points, hold=0.0, delay=0.0, second_delay=0.0, compliance=10.0, power_compliance=0.0):
        """
        Configure a source sweep on a single channel.
        For current sweeps use sweep_mode=SWP_IF_SGLLIN and range_ as the source current range.
        For voltage sweeps use sweep_mode=SWP_VF_SGLLIN and range_ as the source voltage range.
        """
        ret = dll_b1500.agb1500_setIv(self.session, channel, sweep_mode, range_, start, stop, points, hold, delay, second_delay, compliance, power_compliance)
        self._check_ret(ret, "Set IV sweep")

    def sweep_iv(self, channel, measurement_mode, measurement_range, expected_points):
        """Execute configured sweep on channel and return measurement data."""
        source = (ViReal64 * expected_points)()
        value = (ViReal64 * expected_points)()
        status = (ViInt32 * expected_points)()
        time_ = (ViReal64 * expected_points)()
        point_count = ViInt32(expected_points)
        ret = dll_b1500.agb1500_sweepIv(self.session, channel, measurement_mode, measurement_range, ct.byref(point_count), source, value, status, time_)
        self._check_ret(ret, "Sweep IV")
        return list(source)[:point_count.value], list(value)[:point_count.value], list(status)[:point_count.value], list(time_)[:point_count.value], point_count.value

    def sweep_miv(self, channels, modes, ranges, expected_points):
        """Execute a sweep and measure multiple channels per point (agb1500_sweepMiv)."""
        n = len(channels)
        ch_arr = (ViInt32 * n)(*channels)
        mode_arr = (ViInt32 * n)(*modes)
        range_arr = (ViReal64 * n)(*ranges)
        total_points = expected_points * n
        source = (ViReal64 * total_points)()
        value = (ViReal64 * total_points)()
        status = (ViInt32 * total_points)()
        time_ = (ViReal64 * total_points)()
        point_count = ViInt32(expected_points)
        ret = dll_b1500.agb1500_sweepMiv(self.session, ch_arr, mode_arr, range_arr, ct.byref(point_count), source, value, status, time_)
        self._check_ret(ret, "Sweep MIV")
        data = {}
        for i, ch in enumerate(channels):
            start = i * point_count.value
            end = start + point_count.value
            data[ch] = {
                "source": list(source)[start:end],
                "value": list(value)[start:end],
                "status": list(status)[start:end],
                "time": list(time_)[start:end],
            }
        return data, point_count.value

    def force_cmu_dc_bias(self, channel, value):
        """Force a DC bias on the CMU channel."""
        ret = dll_b1500.agb1500_forceCmuDcBias(self.session, channel, value)
        self._check_ret(ret, "Force CMU DC bias")

    def set_cmu_integ(self, mode, value):
        """Set CMU integration mode/value (see agb1500_INTEG_* constants)."""
        ret = dll_b1500.agb1500_setCmuInteg(self.session, mode, value)
        self._check_ret(ret, "Set CMU integration")

    def force_cmu_ac_level(self, channel, value):
        """Set CMU AC test level."""
        ret = dll_b1500.agb1500_forceCmuAcLevel(self.session, channel, value)
        self._check_ret(ret, "Force CMU AC level")

    def set_cmu_freq(self, channel, frequency_hz):
        """Set CMU measurement frequency."""
        ret = dll_b1500.agb1500_setCmuFreq(self.session, channel, frequency_hz)
        self._check_ret(ret, "Set CMU frequency")

    def set_cv(self, channel, mode, start, stop, points, hold=0.0, delay=0.0, second_delay=0.0):
        """Configure a C-V sweep on the CMU."""
        ret = dll_b1500.agb1500_setCv(
            self.session,
            channel,
            mode,
            start,
            stop,
            points,
            hold,
            delay,
            second_delay,
        )
        self._check_ret(ret, "Set C-V sweep")

    def spot_cmu_meas(self, channel, mode, range_=AUTO_RANGE):
        """Single CMU measurement point.

        Returns (primary, status, monitor, status_monitor, timestamp).
        """
        data = ViReal64()
        status = ViInt32()
        monitor = ViReal64()
        status_mon = ViInt32()
        time_ = ViReal64()
        ret = dll_b1500.agb1500_spotCmuMeas(
            self.session,
            channel,
            mode,
            range_,
            ct.byref(data),
            ct.byref(status),
            ct.byref(monitor),
            ct.byref(status_mon),
            ct.byref(time_),
        )
        self._check_ret(ret, "Spot CMU measurement")
        return data.value, status.value, monitor.value, status_mon.value, time_.value

    def sweep_cv(self, channel, mode, measurement_range, expected_points):
        """Execute configured C-V sweep and return arrays with point_count.

        The DLL reports point_count = N (number of bias points) but writes
        2*N entries into value[], status[], monitor[], and status_mon[] —
        interleaving the two measurement components per bias point:
          value[2i]   = primary component (e.g. Cp)
          value[2i+1] = secondary component (e.g. Rp)
        source[] and time[] have exactly N entries (one per bias point).
        This method returns the full 2*N slice for value/status/monitor arrays.
        """
        expected = max(1, int(expected_points))
        # source/time: N entries; value/status/monitor: 2*N entries.
        cap_source = min(200000, max(expected + 64, expected * 2))
        cap_values = min(400000, max(expected * 2 + 64, expected * 3))

        source = (ViReal64 * cap_source)()
        value = (ViReal64 * cap_values)()
        status = (ViInt32 * cap_values)()
        monitor = (ViReal64 * cap_values)()
        status_mon = (ViInt32 * cap_values)()
        time_ = (ViReal64 * cap_source)()
        point_count = ViInt32(cap_source)
        ret = dll_b1500.agb1500_sweepCv(
            self.session,
            channel,
            mode,
            measurement_range,
            ct.byref(point_count),
            source,
            value,
            status,
            monitor,
            status_mon,
            time_,
        )
        self._check_ret(ret, "Sweep C-V")
        count = point_count.value
        if count < 0 or count > cap_source:
            raise RuntimeError(
                f"Sweep C-V returned invalid point_count={count} for capacity={cap_source}."
            )
        return (
            list(source)[:count],
            list(value)[:2 * count],
            list(status)[:2 * count],
            list(monitor)[:2 * count],
            list(status_mon)[:2 * count],
            list(time_)[:count],
            count,
        )

    def zero_output(self, channel):
        """Return channel to zero output state."""
        ret = dll_b1500.agb1500_zeroOutput(self.session, channel)
        self._check_ret(ret, "Zero output")

    def abort_measure(self):
        """Abort ongoing measurement/sweep on B1500 and WGFMU."""
        # Abort WGFMU first if it was used
        if self._wgfmu is not None:
            try:
                self._wgfmu.abort()
            except Exception:
                pass
        dll_b1500.agb1500_abortMeasure(self.session)

    def spot_meas(self, channel, mode, range_=AUTO_RANGE):
        """Single spot measurement on a channel."""
        value = ViReal64()
        status = ViInt32()
        timestamp = ViReal64()
        ret = dll_b1500.agb1500_spotMeas(self.session, channel, mode, range_, ct.byref(value), ct.byref(status), ct.byref(timestamp))
        self._check_ret(ret, "Spot measurement")
        return value.value, status.value, timestamp.value

    def start_measure(self, channels, modes, ranges, source_output=1, timestamp=1, monitor=0, meas_type=MEAS_TYPE_SWEEP):
        """
        Begin a measurement to enable streaming via read_data.
        startMeasure expects channel array terminated by 0. The source_output flag controls whether source data is reported.
        """
        ch_list = list(channels) + [0]
        mode_list = list(modes) + [0]
        range_list = list(ranges) + [0.0]
        ch_arr = (ViInt32 * len(ch_list))(*ch_list)
        mode_arr = (ViInt32 * len(mode_list))(*mode_list)
        range_arr = (ViReal64 * len(range_list))(*range_list)
        ret = dll_b1500.agb1500_startMeasure(self.session, meas_type, ch_arr, mode_arr, range_arr, source_output, timestamp, monitor)
        self._check_ret(ret, "Start measure")

    def read_data(self):
        """Read one measurement record from the streaming buffer.
        
        Returns (ret, eod, data_type, value, status, channel)
        - ret: driver return (can be -1 while data are valid; do not treat as fatal mid-measurement)
        - eod: End Of Data flag (1=data end, 0=data available)
        - data_type codes:
            1  Current measurement data
            2  Voltage measurement data
            3  Current output data
            4  Voltage output data
            5  Time stamp data
            6  Impedance (R-X) measurement data
            7  Admittance (G-B) measurement data
            8  Capacitance measurement data
            9  Dissipation factor measurement data
            10 Quality factor measurement data
            11 Inductance measurement data
            12 Phase measurement data (radian)
            13 Phase measurement data (degree)
            14 Frequency data
            15 Sampling index
            16 Invalid data
        - value: Measured data or source setup data.
        - status: Measurement status bitstring (compliance/overflow/etc).
        - channel: Channel number that generated this data (-1 means no channel).

        Notes on error handling (Keysight guidance):
        * The driver issues *OPC? internally; when the instrument is still busy this can time out and return -1 even
          though the data/status are valid. Do not abort on a lone -1.
        * ret < 0 should be logged as a driver/GPIB issue, separate from measurement quality (status bits).
        * Avoid calling error_query while streaming; it can hang the instrument.
        """
        eod = ViInt32()
        data_type = ViInt32()
        value = ViReal64()
        status = ViInt32()
        channel = ViInt32()
        ret = dll_b1500.agb1500_readData(self.session, ct.byref(eod), ct.byref(data_type), ct.byref(value), ct.byref(status), ct.byref(channel))
        # Do not call _check_ret here; caller decides how to handle transient negatives.
        return ret, eod.value, data_type.value, value.value, status.value, channel.value

    @classmethod
    def describe_status_bits(cls, status: int) -> str:
        """Return a human-readable description of status bitfields."""
        if not status:
            return "OK"
        parts = []
        for bit, text in cls.STATUS_BIT_TEXT.items():
            if status & bit:
                parts.append(text)
        if not parts:
            return f"0x{status:X} (unknown bits)"
        return "; ".join(parts)

    @classmethod
    def describe_data_type(cls, data_type: int) -> str:
        """Return human-readable description of data_type codes."""
        return cls.DATA_TYPE_TEXT.get(data_type, f"Type {data_type}")

    @classmethod
    def describe_data_type_short(cls, data_type: int) -> str:
        """Return short code for data_type."""
        return cls.DATA_TYPE_SHORT.get(data_type, f"T{data_type}")

    # --- Raw VISA methods for SCPI streaming ---

    def visa_write(self, command: str):
        """Send a SCPI command string via viWrite."""
        buf = command.encode('ascii')
        ret_count = ct.c_uint32(0)
        status = dll_visa32.viWrite(self.session, buf, len(buf), ct.byref(ret_count))
        if status < 0:
            raise RuntimeError(f"viWrite failed: {status}")

    def visa_read(self, max_bytes: int = 4096) -> str:
        """Read response via viRead. Returns decoded ASCII string."""
        buf = ct.create_string_buffer(max_bytes)
        ret_count = ct.c_uint32(0)
        status = dll_visa32.viRead(self.session, buf, max_bytes, ct.byref(ret_count))
        if status < 0:
            raise RuntimeError(f"viRead failed: {status}")
        return buf.raw[:ret_count.value].decode('ascii')

    def visa_set_termchar(self, char_code: int, enabled: bool = True):
        """Set the VISA termination character and enable/disable it."""
        dll_visa32.viSetAttribute(self.session, VI_ATTR_TERMCHAR, char_code)
        dll_visa32.viSetAttribute(self.session, VI_ATTR_TERMCHAR_EN, 1 if enabled else 0)

    def stream_cv_sweep(self, cmu_channel, cmu_mode, meas_range, expected_points, callback):
        """Execute a CV sweep via raw SCPI with per-point streaming.

        Uses FMT 5,0 (comma terminator) + XE and reads five FMT5 tokens per point:
        Time, Para1, Para2, OscLevel, DCBias.

        Args:
            cmu_channel: CMU channel number.
            cmu_mode: IMP mode code (e.g. 100 for Cp-G).
            meas_range: Measurement range (0 = auto).
            expected_points: Number of sweep steps to read.
            callback: Called as callback(step, dc_bias_v, para1, para2, time_s, s1, s2)
                      after each step completes.
        """
        # Set comma-terminated format, timestamp, monitor
        self.visa_write("FMT 5,0\n")
        self.visa_write("TSC 1\n")
        self.visa_write("LMN 1\n")
        # Measurement mode = CV DC bias sweep
        self.visa_write(f"MM 18,{cmu_channel}\n")
        self.visa_write(f"IMP {cmu_mode}\n")
        meas_range_int = int(meas_range) if meas_range == int(meas_range) else meas_range
        self.visa_write(f"RC {cmu_channel},{meas_range_int}\n")
        # Reset timestamp and trigger
        self.visa_write("TSR\n")

        # Set VISA termination character to comma (ASCII 44)
        self.visa_set_termchar(44, True)

        try:
            self.visa_write("XE\n")
            def _read_token():
                return _parse_fmt5_item(self.visa_read(64))

            for step in range(expected_points):
                # MM18 + LMN1 order: Time, Para1, Para2, Osc, DCBias.
                _ts, _tc, time_type, time_s = _read_token()
                p1_status, _c1, _t1, para1 = _read_token()
                p2_status, _c2, _t2, para2 = _read_token()
                _os, _oc, _ot, _ov = _read_token()
                _ds, _dc, _dt, dc_bias_v = _read_token()

                if time_type != 'T':
                    raise RuntimeError(
                        f"Unexpected CV stream layout at step {step}: first token type={time_type!r}, expected 'T'"
                    )

                callback(
                    step,
                    dc_bias_v,
                    para1,
                    para2,
                    time_s,
                    _parse_scpi_status(p1_status),
                    _parse_scpi_status(p2_status),
                )
        finally:
            # Restore normal termination (newline)
            self.visa_set_termchar(10, True)

    def close(self):
        # Close WGFMU session first if it was used
        if self._wgfmu is not None:
            try:
                self._wgfmu.close()
            except Exception:
                pass
            self._wgfmu = None
        dll_b1500.agb1500_close(self.session)

class WGFMUSession:
    """
    High-level wrapper for WGFMU instrument using ctypes bindings.
    """
    def __init__(self, address: str | None = None):
        if not dll_wgfmu:
            raise RuntimeError("WGFMU DLL not loaded.")
        if address is not None:
            ret = dll_wgfmu.WGFMU_openSession(address.encode())
            self._check_ret(ret, "WGFMU open session")
        ret = dll_wgfmu.WGFMU_clear()
        self._check_ret(ret, "WGFMU initialize")

    def _get_error_summary(self) -> str | None:
        try:
            size = ct.c_int()
            ret = dll_wgfmu.WGFMU_getErrorSummarySize(ct.byref(size))
            if ret < 0 or size.value <= 0:
                return None
            buf = ct.create_string_buffer(size.value)
            ret = dll_wgfmu.WGFMU_getErrorSummary(buf, ct.byref(size))
            if ret < 0:
                return None
            text = buf.value.decode(errors="replace").strip()
            return text or None
        except Exception:
            return None

    def _get_warning_summary(self) -> str | None:
        try:
            size = ct.c_int()
            ret = dll_wgfmu.WGFMU_getWarningSummarySize(ct.byref(size))
            if ret < 0 or size.value <= 0:
                return None
            buf = ct.create_string_buffer(size.value)
            ret = dll_wgfmu.WGFMU_getWarningSummary(buf, ct.byref(size))
            if ret < 0:
                return None
            text = buf.value.decode(errors="replace").strip()
            return text or None
        except Exception:
            return None

    def _check_ret(self, ret, context):
        # WGFMU returns:
        #   ret < 0  => error
        #   ret == 0 => OK
        #   ret > 0  => warning (non-fatal)
        if ret < 0:
            detail = self._get_error_summary()
            if detail:
                raise RuntimeError(f"{context} failed: {ret}. {detail}")
            raise RuntimeError(f"{context} failed: {ret}")
        if ret > 0:
            detail = self._get_warning_summary()
            if detail:
                warnings.warn(f"{context}: {detail} (code {ret})", RuntimeWarning)
            else:
                warnings.warn(f"{context}: warning code {ret}", RuntimeWarning)

    def close(self):
        ret = dll_wgfmu.WGFMU_closeSession()
        self._check_ret(ret, "WGFMU close session")

    def clear(self):
        ret = dll_wgfmu.WGFMU_clear()
        self._check_ret(ret, "WGFMU clear")
        
    def initialize(self):
        ret = dll_wgfmu.WGFMU_initialize()
        self._check_ret(ret, "WGFMU initialize")

    def connect(self, channel_id: int):
        ret = dll_wgfmu.WGFMU_connect(channel_id)
        self._check_ret(ret, "WGFMU connect")

    def disconnect(self, channel_id: int):
        ret = dll_wgfmu.WGFMU_disconnect(channel_id)
        self._check_ret(ret, "WGFMU disconnect")

    def set_operation_mode(self, channel_id: int, mode: int):
        ret = dll_wgfmu.WGFMU_setOperationMode(channel_id, mode)
        self._check_ret(ret, "WGFMU set operation mode")

    def set_force_voltage_range(self, channel_id: int, rng: int):
        ret = dll_wgfmu.WGFMU_setForceVoltageRange(channel_id, rng)
        self._check_ret(ret, "WGFMU set force voltage range")

    def set_measure_mode(self, channel_id: int, mode: int):
        ret = dll_wgfmu.WGFMU_setMeasureMode(channel_id, mode)
        self._check_ret(ret, "WGFMU set measure mode")

    def set_measure_voltage_range(self, channel_id: int, rng: int):
        ret = dll_wgfmu.WGFMU_setMeasureVoltageRange(channel_id, rng)
        self._check_ret(ret, "WGFMU set measure voltage range")

    def set_measure_current_range(self, channel_id: int, rng: int):
        ret = dll_wgfmu.WGFMU_setMeasureCurrentRange(channel_id, rng)
        self._check_ret(ret, "WGFMU set measure current range")

    def set_measure_enabled(self, channel_id: int, enabled: int):
        ret = dll_wgfmu.WGFMU_setMeasureEnabled(channel_id, enabled)
        self._check_ret(ret, "WGFMU set measure enabled")

    def set_measure_event(
        self,
        pattern_name: str,
        event_name: str,
        time: float,
        measurement_points: int,
        measurement_interval: float,
        averaging_time: float,
        raw_data: int,
    ):
        ret = dll_wgfmu.WGFMU_setMeasureEvent(
            pattern_name.encode(),
            event_name.encode(),
            time,
            measurement_points,
            measurement_interval,
            averaging_time,
            raw_data,
        )
        self._check_ret(ret, "WGFMU set measure event")

    def create_pattern(self, name, initial_voltage=0.0):
        ret = dll_wgfmu.WGFMU_createPattern(name.encode(), initial_voltage)
        self._check_ret(ret, "WGFMU create pattern")

    def add_vector(self, pattern_name, time, voltage):
        ret = dll_wgfmu.WGFMU_addVector(pattern_name.encode(), time, voltage)
        self._check_ret(ret, "WGFMU add vector")

    def add_sequence(self, channel_id, pattern_name, repetitions):
        ret = dll_wgfmu.WGFMU_addSequence(channel_id, pattern_name.encode(), repetitions)
        self._check_ret(ret, "WGFMU add sequence")

    def execute(self):
        ret = dll_wgfmu.WGFMU_execute()
        self._check_ret(ret, "WGFMU execute")

    def get_status(self):
        """Get execution status. Returns (status_code, elapsed_time, total_time)."""
        status = ct.c_int()
        elapsed = ct.c_double()
        total = ct.c_double()
        ret = dll_wgfmu.WGFMU_getStatus(ct.byref(status), ct.byref(elapsed), ct.byref(total))
        self._check_ret(ret, "WGFMU get status")
        return status.value, elapsed.value, total.value

    def get_measure_value_size(self, channel_id):
        measured = ct.c_int()
        total = ct.c_int()
        ret = dll_wgfmu.WGFMU_getMeasureValueSize(channel_id, ct.byref(measured), ct.byref(total))
        self._check_ret(ret, "WGFMU get measure value size")
        return measured.value, total.value

    def get_measure_value(self, channel_id, index):
        time_ = ct.c_double()
        value = ct.c_double()
        ret = dll_wgfmu.WGFMU_getMeasureValue(channel_id, index, ct.byref(time_), ct.byref(value))
        self._check_ret(ret, "WGFMU get measure value")
        return time_.value, value.value

    def abort(self, timeout_s: float = 2.0):
        """Abort all WGFMU channels and wait for abort to complete."""
        ret = dll_wgfmu.WGFMU_abort()
        if ret < 0:
            return ret  # Already failed, don't wait
        
        # Wait for ABORT_COMPLETED or IDLE status
        import time
        start = time.time()
        while time.time() - start < timeout_s:
            try:
                status, _, _ = self.get_status()
                # 10003 = ABORT_COMPLETED, 10001 = IDLE, 10000 = COMPLETED
                if status in (10003, 10001, 10000):
                    return 0  # Success
            except Exception:
                pass
            time.sleep(0.01)
        return ret  # Timeout, return original result

    def abort_channel(self, channel_id: int):
        """Abort a specific WGFMU channel."""
        ret = dll_wgfmu.WGFMU_abortChannel(channel_id)
        return ret
