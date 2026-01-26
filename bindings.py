"""
Python bindings for B1500 and WGFMU instruments using ctypes.

This module provides ctypes wrappers for the B1500 (agb1500_32.dll) and WGFMU (WGFMU.dll) instrument libraries.
It includes all functions from the respective header files, with proper argtypes and restypes defined.

Note: Some argtypes may need refinement based on exact VISA types. This is a generated starting point.
"""

import ctypes as ct
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

# Load DLLs
dll_b1500 = ct.windll.LoadLibrary(r"C:\Program Files (x86)\IVI Foundation\VISA\WinNT\Bin\agb1500_32.dll")
dll_wgfmu = ct.windll.LoadLibrary(r"C:\Windows\SysWOW64\WGFMU.dll")

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

    dll_b1500.agb1500_spotCmuMeas.argtypes = [ViSession, ViInt32, ViInt32, ViReal64, ct.POINTER(ViReal64), ct.POINTER(ViInt32), ct.POINTER(ViReal64), ViPReal64]
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
    SWP_VF_DBLLIN = 3    # Double linear voltage sweep
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
        self.session = ViSession()
        ret = dll_b1500.agb1500_init(gpib_addr.encode(), 1, 1, ct.byref(self.session))
        if ret != 0:
            raise RuntimeError(f"B1500 init failed: {ret}")
    
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

    def zero_output(self, channel):
        """Return channel to zero output state."""
        ret = dll_b1500.agb1500_zeroOutput(self.session, channel)
        self._check_ret(ret, "Zero output")

    def abort_measure(self):
        """Abort ongoing measurement/sweep."""
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

    def close(self):
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
        ret = dll_wgfmu.WGFMU_initialize()
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

    def wait_until_completed(self):
        ret = dll_wgfmu.WGFMU_waitUntilCompleted()
        self._check_ret(ret, "WGFMU wait until completed")

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
