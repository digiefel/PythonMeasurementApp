"""
Python bindings for B1500 and WGFMU instruments using ctypes.

This module provides ctypes wrappers for the B1500 (agb1500_32.dll) and WGFMU (WGFMU.dll) instrument libraries.
It includes all functions from the respective header files, with proper argtypes and restypes defined.

Note: Some argtypes may need refinement based on exact VISA types. This is a generated starting point.
"""

import ctypes as ct

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
    CH_ALL = 0
    IM_MODE = 1  # Measure current
    VM_MODE = 2  # Measure voltage

    IF_MODE = 1  # Force current
    VF_MODE = 2  # Force voltage

    AUTO_RANGE = 0.0

    # Sweep mode definitions (see agb1500.h)
    SWP_IF_SGLLIN = -1  # Single linear current sweep
    SWP_VF_SGLLIN = 1   # Single linear voltage sweep
    
    def __init__(self, gpib_addr="GPIB0::17::INSTR"):
        if not dll_b1500:
            raise RuntimeError("B1500 DLL not loaded.")
        self.session = ViSession()
        ret = dll_b1500.agb1500_init(gpib_addr.encode(), 1, 1, ct.byref(self.session))
        if ret != 0:
            raise RuntimeError(f"B1500 init failed: {ret}")

    def reset(self):
        dll_b1500.agb1500_reset(self.session)

    def set_timeout(self, ms):
        dll_b1500.agb1500_timeOut(self.session, ms)

    def enable_error_detect(self, enable):
        dll_b1500.agb1500_errorQueryDetect(self.session, 1 if enable else 0)

    def set_switch(self, channel, state):
        """Control switch matrix channel on/off state."""
        ret = dll_b1500.agb1500_setSwitch(self.session, channel, 1 if state else 0)
        if ret != 0:
            raise RuntimeError(f"Set switch failed: {ret}")

    def reset_timestamp(self):
        """Reset internal timestamp for measurements."""
        ret = dll_b1500.agb1500_resetTimestamp(self.session)
        if ret != 0:
            raise RuntimeError(f"Reset timestamp failed: {ret}")

    def force_current(self, channel, current, compliance=10.0, range_=AUTO_RANGE, polarity=0):
        """Force a current level on the specified channel."""
        ret = dll_b1500.agb1500_force(self.session, channel, self.IF_MODE, range_, current, compliance, polarity)
        if ret != 0:
            raise RuntimeError(f"Force current failed: {ret}")

    def force_voltage(self, channel, voltage, compliance=0.1, range_=AUTO_RANGE, polarity=0):
        """Force a voltage level on the specified channel."""
        ret = dll_b1500.agb1500_force(self.session, channel, self.VF_MODE, range_, voltage, compliance, polarity)
        if ret != 0:
            raise RuntimeError(f"Force voltage failed: {ret}")

    def set_ic_sweep(self, channel, sweep_mode, range_, start, stop, bias, points, hold=0.0, delay=0.0, second_delay=0.0, compliance=10.0, power_compliance=0.0):
        """
        Configure a sweep. For current sweeps use sweep_mode=SWP_IF_SGLLIN and range_ as the source current range.
        For voltage sweeps use sweep_mode=SWP_VF_SGLLIN and range_ as the source voltage range.
        """
        ret = dll_b1500.agb1500_setIv(self.session, channel, sweep_mode, range_, start, stop, bias, points, hold, delay, second_delay, compliance, power_compliance)
        if ret != 0:
            raise RuntimeError(f"Set IC sweep failed: {ret}")

    def sweep_ic(self, channel, measurement_mode, measurement_range, expected_points):
        """Execute configured sweep on channel and return measurement data."""
        source = (ViReal64 * expected_points)()
        value = (ViReal64 * expected_points)()
        status = (ViInt32 * expected_points)()
        time_ = (ViReal64 * expected_points)()
        point_count = ViInt32(expected_points)
        ret = dll_b1500.agb1500_sweepIv(self.session, channel, measurement_mode, measurement_range, ct.byref(point_count), source, value, status, time_)
        if ret != 0:
            raise RuntimeError(f"Sweep IC failed: {ret}")
        return list(source), list(value), list(status), list(time_), point_count.value

    def zero_output(self, channel):
        """Return channel to zero output state."""
        ret = dll_b1500.agb1500_zeroOutput(self.session, channel)
        if ret != 0:
            raise RuntimeError(f"Zero output failed: {ret}")

    def spot_meas(self, channel, mode, range_=AUTO_RANGE):
        """Single spot measurement on a channel."""
        value = ViReal64()
        status = ViInt32()
        timestamp = ViReal64()
        ret = dll_b1500.agb1500_spotMeas(self.session, channel, mode, range_, ct.byref(value), ct.byref(status), ct.byref(timestamp))
        if ret != 0:
            raise RuntimeError(f"Spot measurement failed: {ret}")
        return value.value, status.value, timestamp.value

    def close(self):
        dll_b1500.agb1500_close(self.session)

class WGFMUSession:
    """
    High-level wrapper for WGFMU instrument using ctypes bindings.
    """
    def __init__(self):
        if not dll_wgfmu:
            raise RuntimeError("WGFMU DLL not loaded.")
        ret = dll_wgfmu.WGFMU_initialize()
        if ret != 0:
            raise RuntimeError(f"WGFMU init failed: {ret}")

    def clear(self):
        ret = dll_wgfmu.WGFMU_clear()
        if ret != 0:
            raise RuntimeError(f"WGFMU clear failed: {ret}")

    def create_pattern(self, name, initial_voltage=0.0):
        ret = dll_wgfmu.WGFMU_createPattern(name.encode(), initial_voltage)
        if ret != 0:
            raise RuntimeError(f"Create pattern failed: {ret}")

    def add_vector(self, pattern_name, time, voltage):
        ret = dll_wgfmu.WGFMU_addVector(pattern_name.encode(), time, voltage)
        if ret != 0:
            raise RuntimeError(f"Add vector failed: {ret}")

    def add_sequence(self, channel_id, pattern_name, repetitions):
        ret = dll_wgfmu.WGFMU_addSequence(channel_id, pattern_name.encode(), repetitions)
        if ret != 0:
            raise RuntimeError(f"Add sequence failed: {ret}")

    def execute(self):
        ret = dll_wgfmu.WGFMU_execute()
        if ret != 0:
            raise RuntimeError(f"Execute failed: {ret}")

    def get_measure_value_size(self, channel_id):
        measured = ct.c_int()
        total = ct.c_int()
        ret = dll_wgfmu.WGFMU_getMeasureValueSize(channel_id, ct.byref(measured), ct.byref(total))
        if ret != 0:
            raise RuntimeError(f"Get measure value size failed: {ret}")
        return measured.value, total.value

    def get_measure_value(self, channel_id, index):
        time_ = ct.c_double()
        value = ct.c_double()
        ret = dll_wgfmu.WGFMU_getMeasureValue(channel_id, index, ct.byref(time_), ct.byref(value))
        if ret != 0:
            raise RuntimeError(f"Get measure value failed: {ret}")
        return time_.value, value.value