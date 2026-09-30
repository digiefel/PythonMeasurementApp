/*****************************************************************************/
/* Driver for agb1500, $instrument desc$                                     */
/* Driver Version: A.03.00                                                   */
/*---------------------------------------------------------------------------*/
/* This driver is compatible with the following VXIplug&play standards:      */
/*    WIN32 System Framework revision 3.0                                    */
/*    VTL revision 3.0 & VISA revision 1.0                                   */
/*****************************************************************************/

#define agb1500_REV_CODE    "A.03.00"                     /* Driver Revision */

/*****************************************************************************/
/* Exactly one of the following must be defined for the program to           */
/*   compile correctly.                                                      */
/*                                                                           */
/* #define __hpux          (for compilation for HP-UX)                       */
/* #define WIN16           (for compilation for 16-bit Windows)              */
/* #define WIN32           (for compilation for 32-bit Windows)              */
/*                                                                           */
/* In addition, if WIN32 is defined, _CVI_ may also be defined to indicate   */
/*   that the program is being compiled under LabWindows CVI 4.0 or          */
/*   greater.                                                                */
/*****************************************************************************/

/*****************************************************************************/
/* The following defines are intended to provide OS compatibility among      */
/*   Windows 16-bit, Windows 32-bit, and HP-UX C compilers.                  */
/*****************************************************************************/

#ifdef __hpux
#define _fcvt    fcvt
#endif

#ifdef WIN16
#else
#define _fmemcpy memcpy
#define _huge
#endif

/*****************************************************************************/
/* The following define specifies the use of viWrite and viRead rather       */
/*   than viPrintf and viScanf.                                              */
/* NO_FORMAT_IO is preferred in the WIN16 environment.  In many WIN16        */
/*   implementations of VISA viPrintf and viScanf do not handle blocks       */
/*   of over 32K bytes well.  Formatted IO is preferred for WIN32 and        */
/*   HP-UX.                                                                  */
/*****************************************************************************/

/* #define NO_FORMAT_IO                                                      */

/*****************************************************************************/

#include <stdlib.h>                       /* prototype for malloc()          */
#include <string.h>                       /* prototype for strcpy()          */
#include <stdio.h>                        /* prototype for sprintf()         */
#include <math.h>                         /* prototype for pow()             */


#ifdef __hpux
#else
#include <windows.h>
#endif

#ifdef WIN32
#else
#include <winbase.h>
#endif

#include "visa.h"
#include "agb1500.h"

#define agb1500_ERR_MSG_LENGTH 256       /* size of error message buffer     */
#define ZERO_DELAY          0            /* Number of milliseconds to delay. */
                                         /* See doDelay function.            */

/*****************************************************************************/
/*  The string below is used to do the instrument identification in the      */
/*    init routine.  The string matches the first part of the instrument's   */
/*    response to it's *IDN? command.                                        */
/*****************************************************************************/
/*  DEVELOPER:                                                               */
/*  This string should match the instrument's model, but should not attempt  */
/*    to match firmware revision as a rule.  For instance, suppose the       */
/*    instrument responds to *IDN? with                                      */
/*          Agilent Technologies, 83475B, rev A.01.14                        */
/*    The appropriate IDN_STRING would be                                    */
/*          Agilent Technologies, 83475                                      */
/*    or                                                                     */
/*          Agilent Technologies, 83475B                                     */
/*    depending on how similar letter revisions of the instrument are.       */
/*****************************************************************************/

#define agb1500_IDN_STRING  "Agilent Technologies,B1500"  

#define agb1500_HPSMU_MODEL_NO	1510					   /* HPSMU		*/
#define agb1500_MPSMU_MODEL_NO  1511                       /* MPSMU     */
#define agb1500_HRSMU_MODEL_NO  1517                       /* HRSMU     */
#define agb1500_ASU_MODEL_NO    5288                       /* HRSMU wt ASU */ 
#define agb1500_CMU_MODEL_NO    1520                       /* CMU       */

/*****************************************************************************/
/*  Driver Message Strings.                                                  */
/*****************************************************************************/
/*  DEVELOPER:                                                               */
/*  Add instrument or instrument driver specific message to the bottom of    */
/*  list.                                                                    */
/*****************************************************************************/

#define agb1500_MSG_VI_OPEN_ERR           "vi was zero.  Was the agb1500_init() successful?"
#define agb1500_MSG_CONDITION             "condition"
#define agb1500_MSG_EVENT                 "event"    
#define agb1500_MSG_EVENT_HDLR_INSTALLED  "event handler is already installed for event happening"
#define agb1500_MSG_EVENT_HDLR_INST2      "Only 1 handler can be installed at a time."    
#define agb1500_MSG_INVALID_HAPPENING     "is not a valid happening."
#define agb1500_MSG_NOT_QUERIABLE         "is not queriable."    
#define agb1500_MSG_IN_FUNCTION           "in function"         
#define agb1500_MSG_INVALID_STATUS        "Parameter 2 is invalid in function agb1500_error_message()."
#define agb1500_MSG_INVALID_STATUS_VALUE  "is not a valid viStatus value."
#define agb1500_MSG_INVALID_VI            "Parameter 1 is invalid in function agb1500_error_message()."  \
                                          "  Using an inactive ViSession may cause this error."    \
                                          "  Was the instrument driver closed prematurely?"
#define agb1500_MSG_NO_ERRORS             "No Errors"
#define agb1500_MSG_SELF_TEST_FAILED      "Self test failed."     
#define agb1500_MSG_SELF_TEST_PASSED      "Self test passed."

#define agb1500_MSG_BOOLEAN               "Expected 0 or 1; Got %d"
#define agb1500_MSG_REAL                  "Expected %.7lg to %.7lg; Got %.7lg"
#define agb1500_MSG_INT                   "Expected %hd to %hd; Got %hd"
#define agb1500_MSG_LONG                  "Expected %ld to %ld; Got %ld"
#define agb1500_MSG_LOOKUP                "Error converting string response to integer"
#define agb1500_MSG_NO_MATCH              "Could not match string %s"

#define VI_ERROR_PARAMETER1_MSG           "Parameter 1 is invalid"
#define VI_ERROR_PARAMETER2_MSG           "Parameter 2 is invalid"
#define VI_ERROR_PARAMETER3_MSG           "Parameter 3 is invalid"
#define VI_ERROR_PARAMETER4_MSG           "Parameter 4 is invalid"
#define VI_ERROR_PARAMETER5_MSG           "Parameter 5 is invalid"
#define VI_ERROR_PARAMETER6_MSG           "Parameter 6 is invalid"
#define VI_ERROR_PARAMETER7_MSG           "Parameter 7 is invalid"
#define VI_ERROR_PARAMETER8_MSG           "Parameter 8 is invalid"
#define VI_ERROR_PARAMETER9_MSG           "Parameter 9 is invalid"
#define VI_ERROR_PARAMETER10_MSG          "Parameter 10 is invalid"
#define VI_ERROR_PARAMETER11_MSG          "Parameter 11 is invalid"
#define VI_ERROR_PARAMETER12_MSG          "Parameter 12 is invalid"
#define VI_ERROR_PARAMETER13_MSG          "Parameter 13 is invalid"
#define VI_ERROR_PARAMETER14_MSG          "Parameter 14 is invalid"
#define VI_ERROR_PARAMETER15_MSG          "Parameter 15 is invalid"
#define VI_ERROR_PARAMETER16_MSG          "Parameter 16 is invalid"
#define VI_ERROR_PARAMETER17_MSG          "Parameter 17 is invalid"
#define VI_ERROR_PARAMETER18_MSG          "Parameter 18 is invalid"
#define VI_ERROR_FAIL_ID_QUERY_MSG        "Instrument IDN does not match."

#define INSTR_ERROR_INV_SESSION_MSG       "ViSession (parameter 1) was not created by this driver"
#define INSTR_ERROR_NULL_PTR_MSG          "NULL pointer detected"
#define INSTR_ERROR_RESET_FAILED_MSG      "Reset failed"
#define INSTR_ERROR_UNEXPECTED_MSG        "An unexpected error occurred"
#define INSTR_ERROR_DETECTED_MSG          "Instrument Error Detected, call agb1500_error_query()."
#define INSTR_ERROR_LOOKUP_MSG            "String not found in table"

#define FILE_OPEN_ERROR_MSG               "File I/O error - could not open specified file"
#define FILE_READ_ERROR_MSG               "File I/O error - could not read from file"
#define FILE_WRITE_ERROR_MSG              "File I/O error - could not write to file"

#define MEAS_DATA_INCONSISTENCY_MSG       "Measurement Data Inconsistency"
#define NO_CMU_UNT_MSG					  "NO CMU(B1520A) is installed in this frame"

/*****************************************************************************/
/*  Error table structure.                                                   */
/*    The first element of the table is the error number, the second is the  */
/*    error message.  Error numbers in the "VISA Generic" section of the     */
/*    table are defined in the VISA header files.  Error numbers in the      */
/*    "Instrument Specific" section are defined in the driver header file.   */
/*    All of the error messages are defined above.                           */
/*****************************************************************************/
/*  DEVELOPER:                                                               */
/*  Add instrument or instrument driver specific numbers to the driver       */
/*    header file.                                                           */
/*  Add instrument or instrument driver specific messages to the bottom of   */
/*    messages listed above.                                                 */
/*  Add instrument specific table entries to the "Instrument Specific"       */
/*    section of the table below.                                            */
/*****************************************************************************/

struct instrErrStruct
{
    ViStatus errStatus;
    ViString errMessage;
};

const static struct instrErrStruct instrErrMsgTable[] =
{
        /**************************/
        /*  VISA Generic          */
        /**************************/

    { VI_ERROR_PARAMETER1,                VI_ERROR_PARAMETER1_MSG         },
    { VI_ERROR_PARAMETER2,                VI_ERROR_PARAMETER2_MSG         },
    { VI_ERROR_PARAMETER3,                VI_ERROR_PARAMETER3_MSG         },
    { VI_ERROR_PARAMETER4,                VI_ERROR_PARAMETER4_MSG         },
    { VI_ERROR_PARAMETER5,                VI_ERROR_PARAMETER5_MSG         },
    { VI_ERROR_PARAMETER6,                VI_ERROR_PARAMETER6_MSG         },
    { VI_ERROR_PARAMETER7,                VI_ERROR_PARAMETER7_MSG         },
    { VI_ERROR_PARAMETER8,                VI_ERROR_PARAMETER8_MSG         },
    { agb1500_INSTR_ERROR_PARAMETER9,     VI_ERROR_PARAMETER9_MSG         },
    { agb1500_INSTR_ERROR_PARAMETER10,    VI_ERROR_PARAMETER10_MSG        },
    { agb1500_INSTR_ERROR_PARAMETER11,    VI_ERROR_PARAMETER11_MSG        },
    { agb1500_INSTR_ERROR_PARAMETER12,    VI_ERROR_PARAMETER12_MSG        },
    { agb1500_INSTR_ERROR_PARAMETER13,    VI_ERROR_PARAMETER13_MSG        },
    { agb1500_INSTR_ERROR_PARAMETER14,    VI_ERROR_PARAMETER14_MSG        },
    { agb1500_INSTR_ERROR_PARAMETER15,    VI_ERROR_PARAMETER15_MSG        },
    { agb1500_INSTR_ERROR_PARAMETER16,    VI_ERROR_PARAMETER16_MSG        },
    { agb1500_INSTR_ERROR_PARAMETER17,    VI_ERROR_PARAMETER17_MSG        },
    { agb1500_INSTR_ERROR_PARAMETER18,    VI_ERROR_PARAMETER18_MSG        },
    { VI_ERROR_FAIL_ID_QUERY,             VI_ERROR_FAIL_ID_QUERY_MSG      },
    { agb1500_INSTR_ERROR_INV_SESSION,    INSTR_ERROR_INV_SESSION_MSG     },
    { agb1500_INSTR_ERROR_NULL_PTR,       INSTR_ERROR_NULL_PTR_MSG        },
    { agb1500_INSTR_ERROR_RESET_FAILED,   INSTR_ERROR_RESET_FAILED_MSG    },
    { agb1500_INSTR_ERROR_UNEXPECTED,     INSTR_ERROR_UNEXPECTED_MSG      },
    { agb1500_INSTR_ERROR_DETECTED,       INSTR_ERROR_DETECTED_MSG        },
    { agb1500_INSTR_ERROR_LOOKUP,         INSTR_ERROR_LOOKUP_MSG          },

        /**************************/
        /*  Instrument Specific   */
        /**************************/

    { agb1500_FILE_OPEN_ERROR,            FILE_OPEN_ERROR_MSG             },
    { agb1500_FILE_READ_ERROR,            FILE_READ_ERROR_MSG             },
    { agb1500_FILE_WRITE_ERROR,           FILE_WRITE_ERROR_MSG            },
    { agb1500_MEAS_DATA_INCONSISTENCY,    MEAS_DATA_INCONSISTENCY_MSG     },
	{ agb1500_NO_CMU_UNT,                 NO_CMU_UNT_MSG                  }

};


/*****************************************************************************/
/*  VISA Globals data structure.                                             */
/*  It is desireable to store global variables in VISA rather than the       */
/*    driver.  This avoids having any state variables in the driver.  This   */
/*    structure defines the driver's global data.  Memory is allocated to    */
/*    this structure in the init function, which passes the pointer to VISA, */
/*    and every function which follows retrieves a pointer to it.            */
/*****************************************************************************/
/*  DEVELOPER:                                                               */
/*  Add additional globals under the "Instrument Specific" section.          */
/*  In driver functions,  The globals can then be refered to via the         */
/*  thisPtr pointer to the globals which is retrieved by the GET_GLOBALS     */
/*  macro.  GET_GLOBALS must be executed in each driver function before      */
/*  any references to thisPtr are made.                                      */
/*****************************************************************************/


#define agb1500_MAX_UNIT   10

struct agb1500_globals
{
    ViSession    defRMSession;

    ViStatus     errNumber;

    ViChar       errFuncName[40];
    ViChar       errMessage[160];

    ViBoolean    errQueryDetect;

        /*****************************************************/
        /* Setting this to VI_TRUE,                          */
        /* will prevent I/O from occuring in an SRQ          */
        /* This is needed, because VTL 3.0 doesn't provide   */
        /* atomic write/read operations.  Don't want         */
        /* to do I/O if the driver is in the middle of       */
        /* a read from the instrument.                       */
        /*****************************************************/
    ViBoolean    blockSrqIO;
    ViInt32      countSrqIO;

    ViInt32      myDelay;

    ViUInt16     interfaceType;
        
        /**************************/
        /*  Instrument Specific   */
        /**************************/

  ViInt32  UNT[agb1500_MAX_UNIT];
};

/*****************************************************************************/
/*****************************************************************************/
/********************                                     ********************/
/**********                                                         **********/
/****                   SUPPORTING MACROS AND FUNCTIONS                   ****/
/**                                                                         **/
/**-------------------------------------------------------------------------**/
/**     These macros and functions are not exposed to the user, but         **/
/**     are used by other functions in the driver.                          **/
/****                                                                     ****/
/**********                                                         **********/
/********************                                     ********************/
/*****************************************************************************/
/*****************************************************************************/

/*****************************************************************************/
/*  DEBUG MACRO                                                              */
/*****************************************************************************/

                              /* don't check the debug pointer all the time! */
#ifdef DEBUG
#define agb1500_DEBUG_CHK_THIS( vi, thisPtr)                                   \
    /* check for NULL user data */                                             \
    if ( 0 == thisPtr)                                                          \
    {                                                                          \
         agb1500_LOG_STATUS(vi, NULL, agb1500_INSTR_ERROR_INV_SESSION );       \
    }                                                                          \
    {                                                                          \
        ViSession defRM;                                                       \
                                                                               \
        /* This should never fail */                                           \
        errStatus = viGetAttribute( vi, VI_ATTR_RM_SESSION, &defRM);           \
        if ( VI_SUCCESS > errStatus )                                           \
        {                                                                      \
             agb1500_LOG_STATUS(    vi, NULL, agb1500_INSTR_ERROR_UNEXPECTED );\
        }                                                                      \
        if ( defRM != thisPtr->defRMSession )                                   \
        {                                                                      \
             agb1500_LOG_STATUS(vi, NULL, agb1500_INSTR_ERROR_INV_SESSION );   \
        }                                                                      \
    }
#else
#define agb1500_DEBUG_CHK_THIS( vi, thisPtr)     
#endif

/*****************************************************************************/
/*  CONTEXT DEPENDENT ERROR MESSAGE                                          */
/*****************************************************************************/

#define WANT_CDE_INIT
#ifdef WANT_CDE_INIT
#define agb1500_CDE_INIT( funcname )                                           \
    strcpy(thisPtr->errFuncName, funcname );                                   \
    thisPtr->errNumber = VI_SUCCESS;                                           \
    thisPtr->errMessage[0] = 0;

#define agb1500_CDE_MESSAGE( message )                                         \
    strcpy(thisPtr->errMessage, message )
#else
#define agb1500_CDE_INIT( funcname )                                           \
    thisPtr->errNumber = VI_SUCCESS;                                           \

#define agb1500_CDE_MESSAGE( message )                                         \
    strcpy(thisPtr->errMessage, message )
#endif

/*****************************************************************************/
/*  SWAP MACROS                                                              */
/*****************************************************************************/
/*  Reorders bytes where instrument byte ordering of integers and reals      */
/*    differ from the computing framework.                                   */
/*                                                                           */
/*  PARAMETERS                                                               */
/*    dest                                                                   */
/*      The number to be reordered.  The reordered result is also stored in  */
/*      this variable on completion.                                         */
/*****************************************************************************/
/*  DEVELOPER:                                                               */
/*  You can remove the SWAP macros if you do not have block IO (arbitrary    */
/*  block) if you do then you must also remove the routines that use them    */
/*  (_cmd_arr... functions)                                                  */
/*****************************************************************************/

#define SWAP_FLOAT64(dest)                                         \
 { unsigned char    src[8];                                        \
      *((double *)src) = *((double *)dest);                        \
      ((unsigned char *)(dest))[0] =  ((unsigned char*)(src))[7];  \
      ((unsigned char *)(dest))[1] =  ((unsigned char*)(src))[6];  \
      ((unsigned char *)(dest))[2] =  ((unsigned char*)(src))[5];  \
      ((unsigned char *)(dest))[3] =  ((unsigned char*)(src))[4];  \
      ((unsigned char *)(dest))[4] =  ((unsigned char*)(src))[3];  \
      ((unsigned char *)(dest))[5] =  ((unsigned char*)(src))[2];  \
      ((unsigned char *)(dest))[6] =  ((unsigned char*)(src))[1];  \
      ((unsigned char *)(dest))[7] =  ((unsigned char*)(src))[0];  \
 }

#define SWAP_FLOAT32(dest)                                         \
 { unsigned char    src[4];                                        \
      *((float *)src) = *((float *)dest);                          \
      ((unsigned char *)(dest))[0] =  ((unsigned char*)(src))[3];  \
      ((unsigned char *)(dest))[1] =  ((unsigned char*)(src))[2];  \
      ((unsigned char *)(dest))[2] =  ((unsigned char*)(src))[1];  \
      ((unsigned char *)(dest))[3] =  ((unsigned char*)(src))[0];  \
 }

#define SWAP_32(dest)                                              \
 { unsigned char    src[4];                                        \
      *((long *)src) = *((long *)dest);                            \
      ((unsigned char *)(dest))[0] =  ((unsigned char*)(src))[3];  \
      ((unsigned char *)(dest))[1] =  ((unsigned char*)(src))[2];  \
      ((unsigned char *)(dest))[2] =  ((unsigned char*)(src))[1];  \
      ((unsigned char *)(dest))[3] =  ((unsigned char*)(src))[0];  \
 }

#define SWAP_16(dest)                                              \
 { unsigned char    src[2];                                        \
      *((int *)src) = *((int *)dest);                              \
      ((unsigned char *)(dest))[0] =  ((unsigned char*)(src))[1];  \
      ((unsigned char *)(dest))[1] =  ((unsigned char*)(src))[0];  \
 }


/*****************************************************************************/
/*  MACRO GET_GLOBALS                                                        */
/*****************************************************************************/
/*  Returns a pointer to the VISA globals storage.  This storage was         */
/*    allocated in init, but it is turned over to VISA to avoid holding      */
/*    state variables in the driver.                                         */
/*  If DEBUG is defined, thisPtr is checked for validity.                    */
/*                                                                           */
/*  PARAMETERS                                                               */
/*    ViSession            InstrDesc                                         */
/*      The instrument's VISA address.                                       */
/*    struct agb1500_globals  *thisPtr                                       */
/*      A pointer to the VISA globals storage                                */
/*****************************************************************************/

#define GET_GLOBALS(vi,thisPtr)                                                \
{                                                                              \
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);      \
    if (errStatus < VI_SUCCESS)                                                \
        return statusUpdate(vi, NULL, errStatus);                              \
}


/*****************************************************************************/
/*  MACRO CDE_INIT                                                           */
/*****************************************************************************/
/*  Defines context dependent errors                                         */
/*                                                                           */
/*  PARAMETERS                                                               */
/*    funcname                                                               */
/*      The name of the function to be stored with the context dependent     */
/*      error information.                                                   */
/*****************************************************************************/

#define CDE_INIT(funcname)                          \
    strcpy(thisPtr->errFuncName, funcname);         \
    thisPtr->errNumber = VI_SUCCESS;                \
    thisPtr->errMessage[0] = 0;


/*****************************************************************************/
/*  DELAY Functions                                                          */
/*  setDelay (located prior to init function) sets the delay time for the    */
/*    instrument.                                                            */
/*  doDelay uses delay time to slow down the driver after a read request.    */
/*---------------------------------------------------------------------------*/
/*  In some SCPI instruments, the instrument cannot change its state to      */
/*    'processing a read request' fast enough to keep another request        */
/*    from getting through to the instrument.  By setting a short delay      */
/*    (less than 100 microseconds should be sufficient) after each read,     */
/*    the driver will wait a sufficient amount of time before attempting     */
/*    to send the next string to the instrument.                             */
/*  DO NOT document these function in the fp file or the help file.  They    */
/*    are intended to address problems in specific instruments, problems     */
/*    that may only appear on faster CPU's.  They are designed so that the   */
/*    problem can be addressed quickly in the field once it is identified.   */
/*  If the problem is identified by driver developers, a 100 ms delay        */
/*    should be set in the agb1500_init function.  The template version of   */
/*    init currently sets the delay to 0.                                    */
/*****************************************************************************/

/*****************************************************************************/
void doDelay(ViInt32 delayTime)
/*****************************************************************************/
/*  Delays execution for a specified number of microseconds.                 */
/*  Platform   Code    Tick Resolution  Tick Increment  Call Overhead        */
/*   WIN       16-bit  1 ms             ~55 ms          0-55 ms              */
/*   WIN32     16-bit  1 ms             ~55 ms          0-55 ms              */
/*   WIN32     32-bit  CPU dependent    CPU dependent   0-20 us              */
/*   HP-UX     32-bit  1 us             CPU dependent   0-20 us              */
/*  PARAMETERS                                                               */
/*    long           delayTime (in)                                          */
/*      The number of micro-seconds to delay before proceeding.              */
/*****************************************************************************/

{
    long   ticksToCount;

        /*************************************************************/
        /*  WIN32 Version                                            */
        /*  WIN32 increments depend on the hardware.  If high-       */
        /*    frequency counting isn't supported, revert to common   */
        /*    standard functions (same as WIN16).                    */
        /*  The call overhead to execute doDelay if high-frequency   */
        /*    is supported is about 25-30 micro-seconds.             */
        /*  The call overhead to execute doDelay if high-frequency   */
        /*    is -NOT- supported is ~10 milli-seconds on             */
        /*    Windows 95 & NT.                                       */
        /*************************************************************/
#ifdef WIN32

#ifdef _CVI_
#else
    __int64  ticksPerSecond;
    __int64  startTicks;
    __int64  nowTicks;
#endif
    DWORD    msTicks;

    if (delayTime == 0)
        return;

#ifdef _CVI_
#else
    if (QueryPerformanceFrequency((LARGE_INTEGER *)&ticksPerSecond))
    {
        ticksToCount = (long)((ticksPerSecond/1E6)*delayTime) + 1;
        QueryPerformanceCounter((LARGE_INTEGER *)&nowTicks);
        startTicks = nowTicks;
        while (nowTicks - startTicks < (DWORD)ticksToCount)
            QueryPerformanceCounter((LARGE_INTEGER *)&nowTicks);
    }
    else
#endif
    {
        ticksToCount = (long)((1E3/1E6)*delayTime) + 1;
        msTicks = GetTickCount();
        while (GetTickCount() - msTicks < (DWORD)ticksToCount);
    }

#endif

        /*************************************************************/
        /*  WIN16 Version                                            */
        /*  WIN16 counts in 1 milli-second increments.               */
        /*  The call overhead to execute doDelay if high-frequency   */
        /*    is -NOT- supported is ~55 milli-seconds on Windows     */
        /*    3.1 and ~10 milli-seconds on Windows 95 & NT.          */
        /*************************************************************/
#ifdef WIN16

    DWORD    msTicks;

    if (delayTime == 0)
        return;

    ticksToCount = (long)((1E3/1E6)*delayTime) + 1;
    msTicks = GetTickCount();
    while (GetTickCount() - msTicks < (DWORD)ticksToCount);

#endif

        /*************************************************************/
        /*  HP-UX Version                                            */
        /*  HP-UX counts in 1 micro-second increments.               */
        /*  The call overhead to execute doDelay on HP-UX is about   */
        /*    15-20 micro-seconds.                                   */
        /*************************************************************/
#ifdef __hpux

    struct timeval t0, t1;

    if (delayTime == 0)
        return;
                                 /* printf("doDelay delaying %ld\n", ticks); */ 
    gettimeofday(&t0, NULL);
    t0.tv_usec += delayTime;
    t0.tv_sec += t0.tv_usec / 1000000;
    t0.tv_usec = t0.tv_usec % 1000000;

    gettimeofday(&t1, NULL);
    while (t1.tv_sec < t0.tv_sec)
        gettimeofday(&t1, NULL);

    if (t1.tv_sec > t0.tv_sec) return;          /* get out quick if past delay time */

    while (t1.tv_usec < t0.tv_usec)
        gettimeofday(&t1, NULL);

#endif

    return;
}        /* ----- end of function ----- */


/*****************************************************************************/
ViStatus delayScanf(
        ViSession  vi,
        ViInt32    delayTime,
        ViString   readFmt,
        ... ) 
/*****************************************************************************/
/*  Same as viVscanf, but with the delay added                               */
/*                                                                           */
/*  PARAMETERS (same as viVscanf, except added delayTime)                    */
/*    ViSession   InstrDesc (in)                                             */
/*    ViInt32     delayTime (in)                                             */
/*    ViString    readFmt (in)                                               */
/*    ...                                                                    */
/*****************************************************************************/

{
    ViStatus  errStatus;
    va_list   va;

    va_start(va, readFmt);
    errStatus = viVScanf(vi, readFmt, va);
    va_end(va);

    doDelay(delayTime);

    return errStatus;
}        /* ----- end of function ----- */


/*****************************************************************************/
ViStatus delayRead(
        ViSession  vi,
        ViInt32    delayTime,
        ViPBuf     buf,
        ViUInt32   cnt,
        ViPUInt32  retCnt) 
/*****************************************************************************/
/*  Same as viRead, but with the delay added                                 */
/*                                                                           */
/*  PARAMETERS (same as, except added delayTime)                             */
/*    ViSession   InstrDesc (in)                                             */
/*    ViInt32     delayTime (in)                                             */
/*    ...                                                                    */
/*****************************************************************************/

{
    ViStatus  errStatus;

    errStatus = viRead(vi, buf, cnt, retCnt);

    doDelay(delayTime);

    return errStatus;
}        /* ----- end of function ----- */

#define    agb1500_CHK_INST_ERR( vi, thisPtr ) \
    if (( errStatus = statusUpdate( vi, thisPtr, VI_SUCCESS )) != VI_SUCCESS ) \
        return( errStatus );

#define    agb1500_CHK_INST_ERR_AFTER_XE( vi, thisPtr ) \
    if (( errStatus = statusUpdateAfterXE( vi, thisPtr, VI_SUCCESS )) != VI_SUCCESS ) \
        return( errStatus );

#define    agb1500_LOG_STATUS( vi, thisPtr, status )             \
    return statusUpdate( vi, thisPtr, status )  

/*****************************************************************************/
ViStatus statusUpdate(
        ViSession  vi,
        struct     agb1500_globals *thisPtr,
        ViStatus   s ) 
/*****************************************************************************/
/*  PARAMETERS                                                               */
/*    ViSession            InstrDesc (in)                                    */
/*    struct agb1500_globals *thisPtr (in)                                    */
/*      A pointer to the VISA globals for this VISA session                  */
/*    ViStatus             s (in)                                            */
/*      A driver error return code.                                          */
/*****************************************************************************/

{   
    ViStatus  errStatus;
    ViUInt16  stb;

    if (thisPtr)
        thisPtr->errNumber = s;

        /*************************************************************/
        /*  If error query detect is set on and the instrument       */
        /*    has not timed out, then ...                            */
        /*  Read the status byte and check the error bit.            */
        /*  Potential status byte error is only 0x20 (Command Error).*/
        /*************************************************************/

    if (thisPtr && thisPtr->errQueryDetect && s != VI_ERROR_TMO)
    {   
          ViBoolean  instr_ready;

          errStatus = viPrintf(vi,"*OPC?\n");
        if (errStatus < VI_SUCCESS)
               return VI_ERROR_SYSTEM_ERROR;

        errStatus = delayScanf(vi, thisPtr->myDelay,
                                              "%hd%*t",&instr_ready);
        if (errStatus < VI_SUCCESS)     
        return VI_ERROR_SYSTEM_ERROR;          
     
        errStatus = viReadSTB(vi,&stb);
        if (errStatus < VI_SUCCESS)
            return VI_ERROR_SYSTEM_ERROR;

        if ( 0x20 & stb ) return agb1500_INSTR_ERROR_DETECTED;
    }

    return s;
}        /* ----- end of function ----- */

/*****************************************************************************/
ViStatus statusUpdateAfterXE(
        ViSession  vi,
        struct     agb1500_globals *thisPtr,
        ViStatus   s ) 
/*****************************************************************************/
/*  PARAMETERS                                                               */
/*    ViSession            InstrDesc (in)                                    */
/*    struct agb1500_globals *thisPtr (in)                                    */
/*      A pointer to the VISA globals for this VISA session                  */
/*    ViStatus             s (in)                                            */
/*      A driver error return code.                                          */
/*****************************************************************************/

{   
    ViStatus  errStatus;
    ViUInt16  stb;

    if (thisPtr)
        thisPtr->errNumber = s;

        /*************************************************************/
        /*  If error query detect is set on and the instrument       */
        /*    has not timed out, then ...                            */
        /*  Read the status byte and check the error bit.            */
        /*  Potential status byte error is only 0x20 (Command Error).*/
        /*************************************************************/

    if (thisPtr && thisPtr->errQueryDetect && s != VI_ERROR_TMO)
    {   
        doDelay(1000);

        errStatus = viReadSTB(vi,&stb);
        if (errStatus < VI_SUCCESS)
            return VI_ERROR_SYSTEM_ERROR;

        if ( 0x20 & stb ) return agb1500_INSTR_ERROR_DETECTED;
    }

    return s;
}        /* ----- end of function ----- */
/*****************************************************************************/
/*  MACRO agb1500_CHK_BOOLEAN                                                 */
/*****************************************************************************/
/*  Ref agb1500_chk_boolean and statusUpdate for info.                         */
/*****************************************************************************/

#define agb1500_CHK_BOOLEAN(my_val, err)                 \
if (agb1500_chk_boolean(thisPtr, my_val))                \
    return statusUpdate(vi, thisPtr, err);


/*****************************************************************************/
static ViBoolean agb1500_chk_boolean(
        struct        agb1500_globals *thisPtr,
        ViBoolean      my_val)
/*****************************************************************************/
/*  PARAMETERS                                                               */
/*    struct agb1500_globals *thisPtr (in)                                    */
/*      A pointer to the VISA globals for this VISA session                  */
/*    ViBoolean my_val (in)                                                  */
/*      The value to be checked.                                             */
/*****************************************************************************/

{
    ViChar message[agb1500_ERR_MSG_LENGTH];

    if ( (my_val != VI_TRUE) && (my_val != VI_FALSE) )
    {
        sprintf(message, agb1500_MSG_BOOLEAN, my_val);    
        strcpy(thisPtr->errMessage, message);                
        return VI_TRUE;
    }

    return VI_FALSE;
}        /* ----- end of function ----- */


/*****************************************************************************/
/*  MACRO agb1500_CHK_REAL_RANGE                                              */
/*****************************************************************************/
/*  Ref agb1500_chk_real_range and statusUpdate for info.                      */
/*****************************************************************************/

#define agb1500_CHK_REAL_RANGE(my_val, min, max, err)        \
if (agb1500_chk_real_range(thisPtr, my_val, min, max))       \
    return statusUpdate(vi, thisPtr, err);


/*****************************************************************************/
static ViBoolean agb1500_chk_real_range( 
        struct    agb1500_globals *thisPtr,
        ViReal64  my_val,
        ViReal64  min,
        ViReal64  max)
/*****************************************************************************/
/*  Tests to see if a ViReal64 is in range.                                  */
/*                                                                           */
/*  PARAMETERS                                                               */
/*    struct agb1500_globals *thisPtr (in)                                    */
/*      A pointer to the VISA globals for this VISA session                  */
/*    ViReal64             my_val (in)                                       */
/*      The value to be checked.                                             */
/*    ViReal64             min (in)                                          */
/*      The bottom of the range.                                             */
/*    ViReal64             max (in)                                          */
/*      The top of the range.                                                */
/*****************************************************************************/

{
    ViChar message[agb1500_ERR_MSG_LENGTH];

    if ( (my_val < min) || (my_val > max) ) 
    {                                
        sprintf(message, agb1500_MSG_REAL, min, max, my_val);    
        strcpy(thisPtr->errMessage, message);
        return VI_TRUE;
    }

    return VI_FALSE;
}        /* ----- end of function ----- */ 
 
  
/*****************************************************************************/
/*  MACRO agb1500_CHK_INT_RANGE                                               */
/*****************************************************************************/
/*  Ref agb1500_chk_int_range and statusUpdate for info.                       */
/*****************************************************************************/

#define agb1500_CHK_INT_RANGE(my_val, min, max, err)       \
if (agb1500_chk_int_range(thisPtr, my_val, min, max) )      \
    return statusUpdate(vi, thisPtr, err);


/*****************************************************************************/
static ViBoolean agb1500_chk_int_range( 
        struct   agb1500_globals *thisPtr,
        ViInt16  my_val,
        ViInt16  min,
        ViInt16  max)
/*****************************************************************************/
/*  Tests to see if a ViInt16 is in range.                                   */
/*                                                                           */
/*  PARAMETERS                                                               */
/*    struct agb1500_globals *thisPtr (in)                                   */
/*      A pointer to the VISA globals for this VISA session                  */
/*    ViInt16              my_val (in)                                       */
/*      The value to be checked.                                             */
/*    ViInt16              min (in)                                          */
/*      The bottom of the range.                                             */
/*    ViInt16              max (in)                                          */
/*      The top of the range.                                                */
/*****************************************************************************/

{
    ViChar message[agb1500_ERR_MSG_LENGTH];

    if ( (my_val < min) || (my_val > max) )              
    {                                
        sprintf(message, agb1500_MSG_INT, min, max, my_val);    
        strcpy(thisPtr->errMessage, message);
        return VI_TRUE;
    }

    return VI_FALSE;
}        /* ----- end of function ----- */ 
   
   
/*****************************************************************************/
/*  MACRO agb1500_CHK_LONG_RANGE                                              */
/*****************************************************************************/
/*  Ref agb1500_chk_long_range and statusUpdate for info.                     */
/*****************************************************************************/

#define agb1500_CHK_LONG_RANGE(my_val, min, max, err)      \
if (agb1500_chk_long_range(thisPtr, my_val, min, max))     \
    return statusUpdate(vi, thisPtr, err);


/*****************************************************************************/
static ViBoolean agb1500_chk_long_range( 
        struct  agb1500_globals *thisPtr,
        ViInt32 my_val,
        ViInt32 min,
        ViInt32 max)
/*****************************************************************************/
/*  Tests to see if a ViInt32 is in range.                                   */
/*                                                                           */
/*  PARAMETERS                                                               */
/*    struct agb1500_globals *thisPtr (in)                                   */
/*      A pointer to the VISA globals for this VISA session                  */
/*    ViInt32              my_val (in)                                       */
/*      The value to be checked.                                             */
/*    ViInt32              min (in)                                          */
/*      The bottom of the range.                                             */
/*    ViInt32              max (in)                                          */
/*      The top of the range.                                                */
/*****************************************************************************/

{
    ViChar message[agb1500_ERR_MSG_LENGTH];

    if ( (my_val < min) || (my_val > max) )              
    {                                
        sprintf(message, agb1500_MSG_LONG, min, max, my_val);    
        strcpy(thisPtr->errMessage, message);
        return VI_TRUE;
    }

    return VI_FALSE;
}        /* ----- end of function ----- */ 
   
   
/*****************************************************************************/
/*  MACRO agb1500_CHK_ENUM                                                   */
/*****************************************************************************/
/*  Ref agb1500_chk_enum and statusUpdate for info.                          */
/*****************************************************************************/

#define agb1500_CHK_ENUM( my_val, limit, err )             \
if ( agb1500_chk_enum( thisPtr, my_val, limit) )            \
    return statusUpdate( vi, thisPtr, err);


/*****************************************************************************/
static ViBoolean agb1500_chk_enum (
        struct agb1500_globals *thisPtr,
        ViInt16 my_val,
        ViInt16 limit)
/*****************************************************************************/
/* Chk_enum checks whether my_val lies between zero and limit                */
/*                                                                           */
/*  PARAMETERS                                                               */
/*    struct agb1500_globals *thisPtr (in)                                   */
/*      A pointer to the VISA globals for this VISA session                  */
/*    ViInt16              my_val (in)                                       */
/*      The value to be checked.                                             */
/*    ViInt16              limit (in)                                        */
/*      The top of the range.                                                */
/*****************************************************************************/

{
    ViChar message[agb1500_ERR_MSG_LENGTH];

    if ( ( my_val < 0 ) || (my_val > limit) )              
    {                                
        sprintf(message, agb1500_MSG_INT, 0, limit, my_val);    
        strcpy(thisPtr->errMessage, message);
        return VI_TRUE;
    }

    return VI_FALSE;
}        /* ----- end of function ----- */

/*****************************************************************************/
/*  MACRO agb1500_CHK_IMP_MEAS_MODE( my_val, err )                           */
/*****************************************************************************/
/*  Ref agb1500_CHK_IMP_MEAS_MODE and statusUpdate for info.                 */
/*****************************************************************************/

#define agb1500_CHK_IMP_MEAS_MODE( my_val, err )            \
if ( agb1500_chk_imp_meas_mode( thisPtr, my_val ) )            \
    return statusUpdate( vi, thisPtr, err);


/*****************************************************************************/
static ViBoolean agb1500_chk_imp_meas_mode (
        struct agb1500_globals *thisPtr,
        ViInt32 my_val)
/*****************************************************************************/
/* Chk_imp_meas_mode checks whether my_val is correct impedance measurement  */
/* mode.																	 */
/*                                                                           */
/*  PARAMETERS                                                               */
/*    struct agb1500_globals *thisPtr (in)                                   */
/*      A pointer to the VISA globals for this VISA session                  */
/*    ViInt16              my_val (in)                                       */
/*      The value to be checked.                                             */
/*****************************************************************************/

{
    if ( (my_val != agb1500_CMUM_R_X)    && (my_val != agb1500_CMUM_G_B)    &&
		 (my_val != agb1500_CMUM_Z_TRAD) && (my_val != agb1500_CMUM_Z_TDEG) &&
		 (my_val != agb1500_CMUM_Y_TRAD) && (my_val != agb1500_CMUM_Y_TDEG) &&
		 (my_val != agb1500_CMUM_CP_G)   && (my_val != agb1500_CMUM_CP_D)   &&
		 (my_val != agb1500_CMUM_CP_Q)   && (my_val != agb1500_CMUM_CP_RP)  &&
		 (my_val != agb1500_CMUM_CS_RS)  && (my_val != agb1500_CMUM_CS_D)   &&
		 (my_val != agb1500_CMUM_CS_Q)   && (my_val != agb1500_CMUM_LP_G)   &&
		 (my_val != agb1500_CMUM_LP_D)   && (my_val != agb1500_CMUM_LP_Q)   &&
		 (my_val != agb1500_CMUM_LP_RP)  && (my_val != agb1500_CMUM_LS_RS)  &&
		 (my_val != agb1500_CMUM_LS_D)   && (my_val != agb1500_CMUM_LS_Q) )
    {                                
        return VI_TRUE;
    }

    return VI_FALSE;
}        /* ----- end of function ----- */

/*****************************************************************************/
/*  MACRO agb1500_RTN_CMU_UNT					                             */
/*****************************************************************************/
/*  Ref agb1500_RTN_CMU_UNT and statusUpdate for info.                       */
/*****************************************************************************/

#define agb1500_RTN_CMU_UNT  agb1500_rtn_cmu_unt(thisPtr)

#define agb1500_NO_CMU 0
/*****************************************************************************/
static ViInt32 agb1500_rtn_cmu_unt ( struct agb1500_globals *thisPtr )
/*****************************************************************************/
/* Return CMU slot number.                                                   */
/*                                                                           */
/*  PARAMETERS                                                               */
/*    struct agb1500_globals *thisPtr (in)                                   */
/*      A pointer to the VISA globals for this VISA session                  */
/*****************************************************************************/
{
	ViInt32 i;

    for (i=0;i<agb1500_MAX_UNIT;i++) {
		if(thisPtr->UNT[i] == agb1500_CMU_MODEL_NO){
			return i+1;
		}
    }
	return agb1500_NO_CMU;
}        /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_setDelay (
        ViSession  vi,
        ViInt32    delayTime)
/*****************************************************************************/
/*  PARAMETERS                                                               */
/*    ViSession  vi (in)                                                     */
/*      Instrument Handle returned from agb1500_init()                       */
/*    ViInt32    delayTime (in)                                              */
/*      The delayTime in microseconds.  Must be between 0 and 1,000.  In     */
/*      practice, should never be set higher than 100.                       */
/*****************************************************************************/

{
    ViStatus   errStatus;

    struct agb1500_globals *thisPtr;

    GET_GLOBALS(vi,thisPtr)

    agb1500_CHK_LONG_RANGE(delayTime, 0L, 1000L, VI_ERROR_PARAMETER2);

    thisPtr->myDelay = delayTime;

    return statusUpdate(vi, thisPtr, VI_SUCCESS);
}        /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC initError(
        ViPSession vi,
        ViStatus   errStatus)
/*****************************************************************************/
/*  This function is only called from agb1500_init.                          */
/*                                                                           */
/*  PARAMETERS                                                               */
/*    ViPSession      vi (in)                                                */
/*      Pointer to Instrument Handle returned by viOpen.                     */
/*    ViStatus       errStatus (in)                                          */
/*      A driver error return code.                                          */
/*****************************************************************************/

{
    viClose(*vi);
    *vi=VI_NULL;
    return errStatus;
}        /* ----- end of function ----- */


/*****************************************************************************/
/*****************************************************************************/
/********************                                     ********************/
/**********                                                         **********/
/****                          DRIVER FUNCTIONS                           ****/
/**                                                                         **/
/**-------------------------------------------------------------------------**/
/**     The functions which are exposed to the driver user start here.      **/
/**     They are in the following order:                                    **/
/**        VPP required functions.                                          **/
/**        Agilent required utility functions                               **/
/**        Agilent passthrough functions                                    **/
/**        Instrument specific functions                                    **/
/****                                                                     ****/
/**********                                                         **********/
/********************                                     ********************/
/*****************************************************************************/
/*****************************************************************************/




/*****************************************************************************/
ViStatus _VI_FUNC agb1500_init(
        ViRsrc        InstrDesc,
        ViBoolean     id_query,
        ViBoolean     do_reset,
        ViPSession    vi)
/*****************************************************************************/
/*                                                                           */
/*    The initialize function initializes the software connection to         */
/*    the instrument and optionally  verifies  that instrument is in         */
/*    the system. In addition, it may perform any necessary actions to       */
/*    place the instrument in its reset state.                               */
/*                                                                           */
/*    If the agb1500_init( ) function  encounters an error, then the         */
/*    value of the vi output parameter will be VI_NULL.                      */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*   InstrDesc      The Instrument Description. Examples:GPIB0::1::INSTR.    */
/*               Data Type:  ViRsrc                                          */
/*               Input/Output:  IN                                           */
/*                                                                           */
/*   id_query      VI_TRUE (to perform system verification) or               */
/*               VI_FALSE (do not perform system verification)               */
/*               Data Type:  ViBoolean                                       */
/*               Input/Output:  IN                                           */
/*                                                                           */
/*   do_reset      VI_TRUE (to perform reset operation) or                   */
/*               VI_FALSE (do not perform reset operation)                   */
/*               Data Type:  ViBoolean                                       */
/*               Input/Output:  IN                                           */
/*                                                                           */
/*   vi              Instrument Handle. This is VI_NULL if an error occurred */
/*               during the init.                                            */
/*               Data Type:  ViPSession                                      */
/*               Input/Output:  OUT                                          */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    struct     agb1500_globals *thisPtr;
    ViStatus   errStatus;
    ViSession  defRM;
    ViBoolean  ret ;

    ViChar     idn_buf[256];
    ViChar     unt_buf[256];


    *vi = VI_NULL;

        /*************************************************************/
        /* Find the Default Resource Manager.  Potential errors are  */
        /*   VI_ERROR_SYSTEM_ERROR, VI_ERROR_ALLOC                   */
        /*************************************************************/

    errStatus = viOpenDefaultRM(&defRM);
    if (VI_SUCCESS > errStatus)
        return errStatus;

        /*************************************************************/
        /* Open a session to the instrument.  Potential errors are   */
        /*   VI_ERROR_NSUP_OPER, VI_ERROR_INV_RSRC_NAME,             */
        /*   VI_ERROR_INV_ACC_MODE, VI_ERROR_RSRC_NFOUND,            */
        /*   VI_ERROR_ALLOC                                          */
        /*************************************************************/

    errStatus = viOpen(defRM, InstrDesc, VI_NULL, VI_NULL, vi);
    if (VI_SUCCESS > errStatus) {
        viClose(defRM);
        *vi=VI_NULL;
        return errStatus;
    }

/* set timeout -> 20 sec*/
    errStatus = viSetAttribute(*vi, VI_ATTR_TMO_VALUE, 20000 /* 20 sec */ );
    if (VI_SUCCESS > errStatus)return initError(vi,errStatus);
        /*************************************************************/
        /* Allocate global memory for the session.  Inititalize the  */
        /*   memory.  Note that viSetAttribute should never fail,    */
        /*   as all of it's input conditions are satisfied.          */
        /*************************************************************/

    thisPtr = (struct agb1500_globals *)malloc(sizeof( struct agb1500_globals) );
    if (0 == thisPtr) {
        viClose(*vi);
        viClose(defRM);
        *vi=VI_NULL;
        return VI_ERROR_ALLOC ;
    }

    errStatus = viSetAttribute(*vi, VI_ATTR_USER_DATA, (ViAttrState)thisPtr); 
    if ( VI_SUCCESS > errStatus) {
        viClose(*vi);
        viClose(defRM);
        *vi=VI_NULL;
        return errStatus;
    }
        /*************************************************************/
        /* Set initial values of variables in global memory.         */
        /*************************************************************/

    thisPtr->defRMSession = defRM;
    thisPtr->errNumber = VI_SUCCESS;
    thisPtr->errFuncName[0] = 0;
    thisPtr->errMessage[0] = 0;
    thisPtr->errQueryDetect = VI_FALSE;
    thisPtr->blockSrqIO = VI_FALSE;
    thisPtr->countSrqIO = 0;
    thisPtr->myDelay = 0;
   
    errStatus = viGetAttribute(*vi, VI_ATTR_INTF_TYPE, &thisPtr->interfaceType);
    if ( VI_SUCCESS > errStatus)
        return initError(vi, errStatus);

        /*************************************************************/
        /* Reset the instrument if so instructed.                    */
        /*   GPIB reset includes a 488.2 device clear.               */
        /*************************************************************/

    if (( VI_TRUE == do_reset ) || ( VI_TRUE == id_query )) {
        if (thisPtr->interfaceType == VI_INTF_GPIB) {
            if (viClear(*vi) <  VI_SUCCESS)
                return initError(vi, agb1500_INSTR_ERROR_RESET_FAILED);

            doDelay(100000);  /* 100msec wait */
        }
    }

    if ( VI_TRUE == do_reset ) {
        if (agb1500_reset(*vi) <  VI_SUCCESS)
            return initError(vi, agb1500_INSTR_ERROR_RESET_FAILED);
        if (agb1500_opc_Q(*vi,&ret) < VI_SUCCESS)
            return initError(vi, agb1500_INSTR_ERROR_RESET_FAILED);
    }

        /*************************************************************/
        /* Validate the instrument's identity.                       */
        /*************************************************************/

    if ( VI_TRUE == id_query ) {
        if (  (viPrintf(*vi, "*IDN?\n") < VI_SUCCESS )
            || (delayScanf(*vi, 100, "%t", idn_buf) < VI_SUCCESS )
            || (strncmp(idn_buf, agb1500_IDN_STRING, strlen(agb1500_IDN_STRING))))
            return initError(vi, VI_ERROR_FAIL_ID_QUERY);
    }
  
        /*************************************************************/
        /* Checking the instrument's channel.                        */
        /*************************************************************/
    if (  (viPrintf(*vi, "UNT?\n") < VI_SUCCESS ) )         
        return initError(vi, VI_ERROR_FAIL_ID_QUERY);
    if ( (delayScanf(*vi, 100, "%t", unt_buf)) < VI_SUCCESS)
        return initError(vi, VI_ERROR_FAIL_ID_QUERY);
    {
#define UNT_SEPARATOR ",;"
#define MODEL_NUMBER_OFFSET 1
#define MODEL_NUMBER_OFFSET_ASU 8
        int i;
        char *token;

        for (i=0;i<agb1500_MAX_UNIT;i++) {   
            if ( i == 0 ) token = strtok( unt_buf, UNT_SEPARATOR );
            else          token = strtok( NULL, UNT_SEPARATOR );
            if ( *token == '0' ) thisPtr->UNT[i] = 0;
            else                 {
				if (!memchr(token,'/',8) || memchr(token,'N',9)) /* CMU with SCUU */
					sscanf( token + MODEL_NUMBER_OFFSET, "%d", &(thisPtr->UNT[i]) );
				else
					sscanf( token + MODEL_NUMBER_OFFSET_ASU,"%d", &(thisPtr->UNT[i]));
			}
			token = strtok( NULL, UNT_SEPARATOR );
        }
    }

    return statusUpdate(*vi, thisPtr, errStatus);
}        /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_close( 
        ViSession vi)
/*****************************************************************************/
/*                                                                           */
/*    The close function terminates the software connection to               */
/*    the instrument and deallocates system resources. It is generally       */
/*    a good programming habit to close the instrument handle when           */
/*    the program is done using the instrument.                              */
/*                                                                           */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*          vi      Instrument Handle returned from agb1500_init( ).         */
/*               Data Type:  ViSession                                       */
/*               Input/Output:  IN                                           */
/*                                                                           */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    struct agb1500_globals *thisPtr;
    ViStatus errStatus;
    ViSession defRM;

    GET_GLOBALS(vi,thisPtr);

        /*************************************************************/
        /* Retrieve Resource Management session, free global memory  */
        /*   for the session (if it exists), and close the vi and    */
        /*   RM sessions.                                            */
        /*************************************************************/

    defRM = thisPtr->defRMSession;

    if ( thisPtr )        
        free(thisPtr);


    return viClose(defRM);
}        /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_reset( 
        ViSession vi)
/*****************************************************************************/
/*                                                                           */
/*    The reset function places the instrument in a default state.           */
/*    Before issuing this function, it may be necessary to send a            */
/*    device clear to ensure that the instrument can execute a reset.        */
/*    A device clear can be issued by invoking agb1500_dcl( ).               */
/*                                                                           */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*          vi      Instrument Handle returned from agb1500_init( ).         */
/*               Data Type:  ViSession                                       */
/*               Input/Output:  IN                                           */
/*                                                                           */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    struct agb1500_globals *thisPtr;
    ViStatus errStatus;

    GET_GLOBALS(vi,thisPtr)
    agb1500_CDE_INIT( "agb1500_reset" );

    if ((errStatus = viPrintf(vi, "*RST\n")) < VI_SUCCESS)
        return statusUpdate(vi, thisPtr, errStatus);

    return statusUpdate(vi, thisPtr, errStatus);
}        /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_self_test(
        ViSession         vi,
        ViPInt16          test_result,
        ViChar _VI_FAR     test_message[])
/*****************************************************************************/
/*                                                                           */
/*    This function causes the instrument to perform a self-test             */
/*    and returns the test result.  This is used to verify that              */
/*    the instrument is operating properly.  A failure may indicate          */
/*    a potential hardware problem.                                          */
/*                                                                           */
/*                                                                           */
/*    Parameter       Description                                            */
/*                                                                           */
/*          vi       Instrument Handle returned from agb1500_init( ).        */
/*                Data Type:  ViSession                                      */
/*                Input/Output:  IN                                          */
/*                                                                           */
/*    test_result  Numeric result from self-test operation.                  */
/*                                                                           */
/*                 0 = no error ( test passed)                               */
/*                                                                           */
/*                 Data Type:  ViPInt16                                      */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*   test_message      Self-test status message.                             */
/*                 This is limited to 256 characters.                        */
/*                                                                           */
/*                 Data Type:  ViChar _VI_FAR [ ]                            */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    struct agb1500_globals *thisPtr;
    ViStatus errStatus;
	ViInt32   q_time_out;

    *test_result = -1; 
    test_message[0] = 0; 


    GET_GLOBALS(vi,thisPtr)
    agb1500_CDE_INIT( "agb1500_self_test" );

    thisPtr->blockSrqIO = VI_TRUE;

	/* query timeout */
	errStatus = viGetAttribute(vi, VI_ATTR_TMO_VALUE, &q_time_out);
    if (VI_SUCCESS > errStatus)
        return statusUpdate(vi, thisPtr, errStatus);

   /* set time out -> 300 sec */
    if ((errStatus = viSetAttribute(vi, VI_ATTR_TMO_VALUE, 300000)) /* 300 sec */ 
           < VI_SUCCESS)
        return statusUpdate(vi, thisPtr, errStatus);


    if ((errStatus = viPrintf(vi, "*TST?\n")) < VI_SUCCESS){
		viSetAttribute(vi, VI_ATTR_TMO_VALUE, q_time_out);
		return statusUpdate(vi, thisPtr, errStatus);
	
	}
    if ((errStatus = delayScanf(vi, thisPtr->myDelay,
                                             "%hd%*t", test_result)) < VI_SUCCESS) {
        *test_result = -1;
		viSetAttribute(vi, VI_ATTR_TMO_VALUE, q_time_out);
        return statusUpdate(vi, thisPtr, errStatus);
    }

    switch ( *test_result ) {
        case 0:
            sprintf(test_message, agb1500_MSG_SELF_TEST_PASSED);
            break;

        /*************************************************************/
        /* DEVELOPER:  Add instrument specific self-test error       */
        /*   codes and messages here.                                */
        /*************************************************************/

        default:
            sprintf(test_message, agb1500_MSG_SELF_TEST_FAILED);
            break;
    }

     /* set former time_out */
    if ((errStatus = viSetAttribute(vi, VI_ATTR_TMO_VALUE, q_time_out )) 
           < VI_SUCCESS)
        return statusUpdate(vi, thisPtr, errStatus);

    return statusUpdate(vi, thisPtr, errStatus);
}        /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_error_query(
        ViSession          vi,
        ViPInt32           inst_error_number,
        ViChar _VI_FAR     inst_error_message[])
/*****************************************************************************/
/*                                                                           */
/*      agb1500_error_query returns the error numbers and corresponding      */
/*      error messages in the error queue of an instrument. See Appendix     */
/*      of the manual for a listing of the instrument error numbers and      */
/*      messages.                                                            */
/*                                                                           */
/*      Instrument errors may occur when a user places the instrument        */
/*      in a bad state such as sending an invalid sequence of coupled        */
/*      commands.                                                            */
/*                                                                           */
/*      Instrument errors can be detected by polling.                        */
/*        Automatic polling can be accomplished by using the                 */
/*        agb1500_errorQueryDetect( ) function.                              */
/*                                                                           */
/*                                                                           */
/*                                                                           */
/*     Parameter     Description                                             */
/*                                                                           */
/*               vi   Instrument Handle returned from agb1500_init( ).       */
/*                    Data Type:  ViSession                                  */
/*                    Input/Output:  IN                                      */
/*                                                                           */
/*  inst_error_number Instrument's error code.                               */
/*                    Data Type:  ViPInt32                                   */
/*                    Input/Output:  OUT                                     */
/*                                                                           */
/* inst_error_message Instrument's error message.                            */
/*                    This is limited to 256 characters.                     */
/*                    Data Type:  ViChar _VI_FAR [ ]                         */
/*                    Input/Output:  OUT                                     */
/*                                                                           */
/*   Comments:                                                               */
/*                                                                           */
/*     Error Numbers/Messages in the Error Queue:  Errors generated by an    */
/*     instrument store an error number and corresponding error message in   */
/*     the error queue.                                                      */
/*     Each error message can be up to 255 characters long.                  */
/*                                                                           */
/*     Clearing the Error Queue: An error number/message is removed from     */
/*     the queue each time the agb1500_error_query function is sent.         */
/*     The errors are cleared first--in, first--out.                         */
/*     When the queue is empty, each following agb1500_error_query function  */
/*     returns 0, "No error".                                                */
/*                                                                           */
/*     Maximum Error Numbers/Messages in the Error Queue: The queue holds    */
/*     a maximum of 30 error numbers/messages for each instrument. If the    */
/*     queue overflows, the last error number/message in the queue is        */
/*     replaced by --350, "Too many errors".                                 */
/*     The oldest error numbers/messages remain in the queue and the most    */
/*     recent are lost.                                                      */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    struct agb1500_globals *thisPtr;
    ViStatus errStatus;

    *inst_error_number = -1; 
    inst_error_message[0] = 0; 


    GET_GLOBALS(vi,thisPtr)
    agb1500_CDE_INIT( "agb1500_error_query" );

    thisPtr->blockSrqIO = VI_TRUE;

    if ((errStatus = viPrintf( vi, "ERR? 1\n")) < VI_SUCCESS)
        return statusUpdate(vi, thisPtr, errStatus);

    if ((errStatus = delayScanf(vi, thisPtr->myDelay, "%ld%*t", inst_error_number)) < VI_SUCCESS) {
        *inst_error_number = -1; 
        inst_error_message[0] = 0; 
        return statusUpdate(vi, thisPtr, errStatus);
    }

    if ((errStatus = viPrintf( vi, "EMG? %d\n", *inst_error_number)) < VI_SUCCESS)
        return statusUpdate(vi, thisPtr, errStatus);

    if ((errStatus = delayScanf(vi, thisPtr->myDelay, "%t", inst_error_message)) < VI_SUCCESS) {
        inst_error_message[0] = 0; 
        return statusUpdate(vi, thisPtr, errStatus);
    }

    /* get rid of extra CR and LF at the end of the error_message */
    inst_error_message[strlen(inst_error_message)-2] = 0;


    return statusUpdate(vi, thisPtr, errStatus);
}        /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_error_message(
        ViSession          vi,
        ViStatus           driver_error_number,
        ViChar _VI_FAR     driver_error_message[])
/*****************************************************************************/
/*                                                                           */
/*    The error message function translates the error return value           */
/*    from an instrument driver function to a user--readable string.         */
/*                                                                           */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*          vi      Instrument Handle returned from agb1500_init( ).         */
/*               Data Type:  ViSession                                       */
/*               Input/Output:  IN                                           */
/*                                                                           */
/* driver_error_number                                                       */
/*               The error return value from an instrument driver function.  */
/*               Data Type:  ViStatus                                        */
/*               Input/Output:  IN                                           */
/*                                                                           */
/* driver_error_message                                                      */
/*               Error message string.                                       */
/*               This is limited to 256 characters.                          */
/*               Data Type:  ViChar _VI_FAR [ ]                              */
/*               Input/Output:  OUT                                          */
/*                                                                           */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    struct    agb1500_globals *thisPtr;
    ViStatus  errStatus;  
    ViInt32   idx;

    driver_error_message[0] = 0;


    thisPtr = NULL;
    if (vi != VI_NULL)
        GET_GLOBALS(vi,thisPtr)

    if (driver_error_number == VI_SUCCESS) {
        sprintf(driver_error_message, agb1500_MSG_NO_ERRORS);

        return statusUpdate(vi, thisPtr, VI_SUCCESS);
    }

        /*************************************************************/
        /* Search the error message table to see if the error is in  */
        /*   that table.  If it is, copy the corresponding error     */
        /*   message to the output error message.  If context        */
        /*   dependent error messages are being used, append the     */
        /*   context dependent information to the message.           */
        /* If the error is found in the table, exit the routine      */
        /*   successfully.                                           */
        /*************************************************************/

    for (idx=0; idx < (sizeof instrErrMsgTable /
                   sizeof(struct instrErrStruct)); idx++) {
        if (instrErrMsgTable[idx].errStatus == driver_error_number) {
            if ((thisPtr) && (thisPtr->errNumber == driver_error_number)) {
                sprintf(driver_error_message, "%s " agb1500_MSG_IN_FUNCTION " %s() %s",
                        instrErrMsgTable[idx].errMessage,
                        thisPtr->errFuncName,
                        thisPtr->errMessage);
            }
            else
                strcpy(driver_error_message, instrErrMsgTable[idx].errMessage);
            
            return statusUpdate(vi, thisPtr, VI_SUCCESS);
        }
    }

        /*************************************************************/
        /* Check to see if the error is a VTL/VISA error number      */
        /*   using viStatusDesc, which will also return the error    */
        /*   message.  If context dependent error messages are       */
        /*   used, append the context dependent information to the   */
        /*   message.                                                */
        /* If the error is found in the table, exit the routine      */
        /*   successfully.                                           */
        /*************************************************************/

    errStatus = viStatusDesc(vi, driver_error_number, driver_error_message);
    if (errStatus == VI_SUCCESS) {
        if ( (thisPtr) && (thisPtr->errNumber == driver_error_number)) {
            strcat(driver_error_message, " ");
            strcat(driver_error_message, agb1500_MSG_IN_FUNCTION);
            strcat(driver_error_message, " ");
            strcat(driver_error_message, thisPtr->errFuncName);
            strcat(driver_error_message, "() ");
            strcat(driver_error_message, thisPtr->errMessage);
        }

        return statusUpdate(vi, thisPtr, VI_SUCCESS);
    }

        /*************************************************************/
        /*   At this point vi is either INVALID or VI_NULL           */
        /*************************************************************/

    if ( VI_NULL == vi ) {
        strcpy(driver_error_message, agb1500_MSG_VI_OPEN_ERR);

        return statusUpdate(vi, thisPtr, VI_SUCCESS);
    } 

    sprintf(driver_error_message, agb1500_MSG_INVALID_STATUS "  %ld"
                               agb1500_MSG_INVALID_STATUS_VALUE, (long)driver_error_number);


    return statusUpdate(vi, thisPtr, VI_ERROR_PARAMETER2);
}        /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_revision_query(
        ViSession      vi,
        ViChar _VI_FAR driver_rev[],
        ViChar _VI_FAR instr_rev[])
/*****************************************************************************/
/*                                                                           */
/*    This function returns the instrument driver revision and               */
/*    the instrument firmware revision.                                      */
/*                                                                           */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*          vi   Instrument Handle returned from agb1500_init( ).            */
/*               Data Type:  ViSession                                       */
/*               Input/Output:  IN                                           */
/*                                                                           */
/*  driver_rev  Instrument driver revision.                                  */
/*              This is limited to 256 characters.                           */
/*              Data Type:  ViChar _VI_FAR [ ]                               */
/*              Input/Output:  OUT                                           */
/*                                                                           */
/*   instr_rev  Instrument firmware revision.                                */
/*              This is limited to 256 characters.                           */
/*              Data Type:  ViChar _VI_FAR [ ]                               */
/*              Input/Output:  OUT                                           */
/*                                                                           */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    struct    agb1500_globals *thisPtr;
    ViStatus  errStatus;
    ViChar    temp_str1[256];                    /* temp hold for instr rev string */
    ViChar    *last_comma;                        /* last comma in *IDN string      */
#define instr_rev_length 7


    GET_GLOBALS(vi,thisPtr)
    agb1500_CDE_INIT( "agb1500_revision_query" );

    driver_rev[0] = 0; 
    instr_rev[0] = 0; 

    sprintf( driver_rev, "%s", agb1500_REV_CODE);
    thisPtr->blockSrqIO = VI_TRUE;

    if ((errStatus = viPrintf( vi, "*IDN?\n")) < VI_SUCCESS) {
        driver_rev[0] = 0;  
        return statusUpdate(vi, thisPtr, errStatus); 
    }

        /*************************************************************/
        /* In the standard c template, the format string is          */
        /*   "%t%*t".  This removes white space from the end of the  */
        /*   returned string, but doesn't work if there are          */
        /*   embedded spaces in the returned string.  I used this    */
        /*   format string and resorted to stripping off spaces and  */
        /*   spaces and trainling non-printing characters below.     */
        /*   This is changed in the template for the 86120.          */
        /*************************************************************/

    if ((errStatus = delayScanf(vi, thisPtr->myDelay, "%t", temp_str1)) < VI_SUCCESS) {
        driver_rev[0] = 0; 
        instr_rev[0]  = 0; 
        return statusUpdate(vi, thisPtr, errStatus); 
    }
    
        /*************************************************************/
        /* error and exit if last comma not found                    */
        /*************************************************************/

    last_comma = strrchr(temp_str1,',');

    if (!last_comma)  {
        instr_rev[0] = 0;
        strcpy(thisPtr->errMessage, "no last comma found in IDN string");
        return statusUpdate(vi, thisPtr, agb1500_INSTR_ERROR_UNEXPECTED); 
    }

        /*************************************************************/
        /* The next statement assumes that the firmware revision of  */
        /*   the instrument follows the last comma/space pair.       */
        /*************************************************************/

    /* strcpy(instr_rev, last_comma+1); */
    {   
	    int i; 
		for(i=0;i<instr_rev_length;i++){
	        instr_rev[i] = last_comma[1+i];
			}
			instr_rev[instr_rev_length] = 0;
    }

    return statusUpdate(vi, thisPtr, VI_SUCCESS); 
}        /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_timeOut (
        ViSession  vi,
        ViInt32    time_out)
/*****************************************************************************/
/*                                                                           */
/*    This function sets a minimum timeout value for driver                  */
/*    I/O transactions in milliseconds.                                      */
/*    The timeout period may vary on computer platforms.                     */
/*                                                                           */
/*      The default timeout period is 5 seconds.                             */
/*                                                                           */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*          vi   Instrument Handle returned from agb1500_init( ).            */
/*               Data Type:  ViSession                                       */
/*               Input/Output:  IN                                           */
/*                                                                           */
/*    time_out  This value sets the I/O timeout for all functions            */
/*              in the driver.  It is specified in milliseconds.             */
/*              Data Type:  ViInt32                                          */
/*              Input/Output:  IN                                            */
/*              Values:                                                      */
/*              agb1500_TIMEOUT_MIN     1                                    */
/*              agb1500_TIMEOUT_MAX     2147483647                           */
/*                                                                           */
/*                                                                           */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0;
    struct agb1500_globals *thisPtr;


    GET_GLOBALS(vi,thisPtr)
    agb1500_CDE_INIT( "agb1500_timeOut" );

    agb1500_CHK_LONG_RANGE(time_out, agb1500_TIMEOUT_MIN,
                         agb1500_TIMEOUT_MAX, VI_ERROR_PARAMETER2);

    if ((errStatus = viSetAttribute(vi, VI_ATTR_TMO_VALUE, time_out)) < VI_SUCCESS)
        return statusUpdate(vi, thisPtr, errStatus);

    return statusUpdate(vi, thisPtr, errStatus);
}        /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_timeOut_Q (
        ViSession  vi,
        ViPInt32   q_time_out)
/*****************************************************************************/
/*                                                                           */
/*      This function returns the timeout value for driver                   */
/*      I/O transactions in milliseconds.  The timeout period                */
/*      may vary on computer platforms.                                      */
/*                                                                           */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*          vi   Instrument Handle returned from agb1500_init( ).            */
/*               Data Type:  ViSession                                       */
/*               Input/Output:  IN                                           */
/*                                                                           */
/*    q_time_out This is the minimum timeout period that the driver          */
/*               can be set to.  It is specified in milliseconds.            */
/*               Data Type:  ViPInt32                                        */
/*               Input/Output:  OUT                                          */
/*                                                                           */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0;
    struct agb1500_globals *thisPtr;


    GET_GLOBALS(vi,thisPtr)
    agb1500_CDE_INIT( "agb1500_timeOut_Q" );

    errStatus = viGetAttribute(vi, VI_ATTR_TMO_VALUE, q_time_out);
    if (VI_SUCCESS > errStatus)
        return statusUpdate(vi, thisPtr, errStatus);


    return statusUpdate(vi, thisPtr, errStatus);
}        /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_errorQueryDetect( 
        ViSession  vi,
        ViBoolean  eq_detect)
/*****************************************************************************/
/*                                                                           */
/*      This function enables (VI_TRUE) or disables (VI_FALSE)               */
/*      automatic instrument error checking.                                 */
/*                                                                           */
/*      If  automatic  error checking is enabled  then  the  driver          */
/*      will query  the instrument for  an error  at the end of each         */
/*      function call.                                                       */
/*                                                                           */
/*                                                                           */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*          vi   Instrument Handle returned from agb1500_init( ).            */
/*               Data Type:  ViSession                                       */
/*               Input/Output:  IN                                           */
/*                                                                           */
/*    eq_detect  Boolean which enables (VI_TRUE) or disables (VI_FALSE)      */
/*               automatic instrument error querying.                        */
/*               If VI_TRUE  this  will  query the instrument for            */
/*               an error before returning from all driver functions.        */
/*                                                                           */
/*               If VI_FALSE  this  will  not  query the  instrument         */
/*               for an error before returning from all driver functions.    */
/*               Data Type:  ViBoolean                                       */
/*               Input/Output:  IN                                           */
/*                                                                           */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0;

    struct agb1500_globals *thisPtr;


    GET_GLOBALS(vi,thisPtr)
    agb1500_CDE_INIT( "agb1500_errorQueryDetect" );

    agb1500_CHK_BOOLEAN(eq_detect, VI_ERROR_PARAMETER2);

    thisPtr->errQueryDetect = eq_detect;

    return statusUpdate( vi, thisPtr, VI_SUCCESS);
}        /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_errorQueryDetect_Q( 
        ViSession   vi,
        ViPBoolean  q_eq_detect)
/*****************************************************************************/
/*                                                                           */
/*      This function indicates if automatic instrument error detection      */
/*      is enabled (VI_TRUE) or disabled (VI_FALSE).                         */
/*                                                                           */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*          vi   Instrument Handle returned from agb1500_init( ).            */
/*               Data Type:  ViSession                                       */
/*               Input/Output:  IN                                           */
/*                                                                           */
/* q_eq_detect   Boolean indicating if automatic  nstrument error            */
/*               querying is performed.                                      */
/*               Data Type:  ViPBoolean                                      */
/*               Input/Output:  OUT                                          */
/*                                                                           */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0;

    struct agb1500_globals *thisPtr;


    GET_GLOBALS(vi,thisPtr)
    agb1500_CDE_INIT( "agb1500_errorQueryDetect_Q" );

    *q_eq_detect = thisPtr->errQueryDetect;


    return statusUpdate( vi, thisPtr, VI_SUCCESS);
}        /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_dcl( 
        ViSession  vi)
/*****************************************************************************/
/*                                                                           */
/*      This function sends a device clear (DCL) to the instrument.          */
/*      A device clear will abort the current operation and enable           */
/*      the instrument to accept a new command or query.                     */
/*                                                                           */
/*      This  is  particularly  useful  in  situations where it is           */
/*      not possible to determine the instrument state. In this case,        */
/*      it is customary  to  send  a  device  clear  before  issuing         */
/*      a  new instrument driver function.  The device clear ensures         */
/*      that the instrument will be able to begin processing the new         */
/*      commands.                                                            */
/*                                                                           */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*          vi   Instrument Handle returned from agb1500_init( ).            */
/*               Data Type:  ViSession                                       */
/*               Input/Output:  IN                                           */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0;
    struct agb1500_globals *thisPtr;


    GET_GLOBALS(vi,thisPtr)
    agb1500_CDE_INIT( "agb1500_dcl" );

    if (thisPtr->interfaceType == VI_INTF_GPIB) {
        if ((errStatus = viClear(vi)) < VI_SUCCESS)
            return statusUpdate( vi, thisPtr, errStatus);
        /*!! check this doDelay(1000000);  /* 1sec wait */
    }

    return statusUpdate( vi, thisPtr, errStatus);
}        /* ----- end of function ----- */

 
/*****************************************************************************/
ViStatus _VI_FUNC agb1500_opc_Q(
        ViSession   vi,
        ViPBoolean  instr_ready)
/*****************************************************************************/
/*                                                                           */
/*      This function sends the *OPC? command.                               */
/*                                                                           */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*          vi   Instrument Handle returned from agb1500_init( ).            */
/*               Data Type:  ViSession                                       */
/*               Input/Output:  IN                                           */
/*                                                                           */
/*  inst_ready   VI_TRUE: Operation complete.                                */
/*               VI_FALSE: Operation is pending.                             */
/*               Data Type:  ViPBoolean                                      */
/*               Input/Output:  OUT                                          */
/*                                                                           */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus;
    struct agb1500_globals *thisPtr;

 
    GET_GLOBALS(vi,thisPtr);
    agb1500_CDE_INIT( "agb1500_opc_Q" );

    if ((errStatus = viPrintf(vi,"*OPC?\n")) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);

    if ((errStatus = delayScanf(vi, thisPtr->myDelay,
                                              "%hd%*t", instr_ready)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);


    return statusUpdate( vi, thisPtr, errStatus);
}        /* ----- end of function ----- */ 


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_readStatusByte_Q(
        ViSession  vi,
        ViPInt16   status_byte)
/*****************************************************************************/
/*                                                                           */
/*      This routine returns the contents of the status byte register.       */
/*                                                                           */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*          vi   Instrument Handle returned from agb1500_init( ).            */
/*               Data Type:  ViSession                                       */
/*               Input/Output:  IN                                           */
/*                                                                           */
/* status_byte   The contents of the status byte are returned             */
/*               in this parameter.                                          */
/*               Data Type:  ViPInt16                                        */
/*               Input/Output:  OUT                                          */
/*                                                                           */
/*                                                                           */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus  errStatus = 0;
    struct    agb1500_globals *thisPtr;
    ViUInt16  stb;


    GET_GLOBALS(vi,thisPtr);
    agb1500_CDE_INIT( "agb1500_readStatusByte_Q" );

    if ((errStatus = viReadSTB(vi,&stb)) < VI_SUCCESS)
        return statusUpdate(vi, thisPtr, errStatus );

    *status_byte = (ViInt16)stb;


    return statusUpdate(vi, thisPtr, errStatus);
}        /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_cmd( 
        ViSession vi,
        ViString  cmd_string)
/*****************************************************************************/
/*                                                                           */
/*      Passes the cmd_string string to the instrument.                      */
/*      Must be a NULL terminated C string.  Note that cmd_str               */
/*      cannot exceed 256 bytes in length.                                   */
/*                                                                           */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*          vi   Instrument Handle returned from agb1500_init( ).            */
/*               Data Type:  ViSession                                       */
/*               Input/Output:  IN                                           */
/*                                                                           */
/*  cmd_string   agb1500 command. (cannot exceed 256 bytes in length)        */
/*               Data Type:  ViString                                        */
/*               Input/Output:  IN                                           */
/*                                                                           */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/


{
    ViStatus errStatus;
    struct   agb1500_globals *thisPtr;


    GET_GLOBALS(vi,thisPtr)
    agb1500_CDE_INIT( "agb1500_cmd" );

#ifdef NO_FORMAT_IO
    {
    ViUInt32 rtn_size;
    errStatus = viWrite(vi, (ViBuf)cmd_string, strlen(cmd_string), &rtn_size );
    }
#else
    errStatus = viPrintf(vi,"%s\n", cmd_string);
#endif
   
    return statusUpdate( vi, thisPtr, errStatus );
}        /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_cmdString_Q(
        ViSession       vi,
        ViString        sq_cmd_string,
        ViInt32         sq_size,
        ViChar _VI_FAR  sq_result[] )
/*****************************************************************************/
/*                                                                           */
/*      Passes  the  sq_cmd_string string  to  the instrument.               */
/*      This entry point WILL wait for a response which must be              */
/*      a string (character data).                                           */
/*                                                                           */
/*      A  max of Size-1 bytes will be read from the instrument and          */
/*      the string will  be NULL  terminated  (so its length  can be         */
/*      found with strlen).                                                  */
/*                                                                           */
/*      <for message based cards only> If more than size-1 bytes are         */
/*      generated  by the instrument then the instrument output buffer       */
/*      will be cleared.                                                     */
/*                                                                           */
/*      Note that the command string cannot exceed 256 bytes in length.      */
/*                                                                           */
/*                                                                           */
/*   Parameter       Description                                             */
/*                                                                           */
/*          vi    Instrument Handle returned from agb1500_init( ).           */
/*                Data Type:  ViSession                                      */
/*                Input/Output:  IN                                          */
/*                                                                           */
/* sq_cmd_string  agb1500 command. (cannot exceed 256 bytes in length)       */
/*                Data Type:  ViString                                       */
/*                Input/Output:  IN                                          */
/*                                                                           */
/*        size    IN -- length of param 4 (result) in bytes 32767 max.       */
/*                Data Type:  ViInt32                                        */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                agb1500_CMDSTRING_Q_MIN     2                              */
/*                agb1500_CMDSTRING_Q_MAX     32767                          */
/*                                                                           */
/*       result   Response from instrument.                                  */
/*                Data Type:  ViChar _VI_FAR [ ]                             */
/*                Input/Output:  OUT                                         */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus;
    struct   agb1500_globals *thisPtr;
   

        /* Command strings must have at least one non-null character */
    if (sq_size < 2)     return statusUpdate(vi,VI_NULL,VI_ERROR_PARAMETER3);

#ifdef WIN16
        /* Strings in 16-bit windows are limited to 32K characters. */    
    if (sq_size > 32767) return statusUpdate(vi,VI_NULL,VI_ERROR_PARAMETER3);
#endif
    
    GET_GLOBALS(vi,thisPtr);
    agb1500_CDE_INIT( "agb1500_cmdString_Q" );

#ifdef NO_FORMAT_IO
    {
    ViInt32   mySize;
    ViUInt32  rtn_size;
    if ((errStatus = viWrite(vi, (ViBuf)sq_cmd_string,
                             strlen(sq_cmd_string), &rtn_size )) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
    mySize = sq_size-1;

    if ((errStatus = delayRead(vi, thisPtr->myDelay,
                             (ViPBuf)sq_result, mySize, &rtn_size)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
    sq_result[rtn_size] = '\0';
    if (thisPtr->interfaceType == VI_INTF_GPIB)
        if (errStatus == VI_SUCCESS_MAX_CNT)
            viClear(vi);
    }
#else
    {
    int sz;
    if ((errStatus = viPrintf(vi, "%s\n",sq_cmd_string )) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
    sz = (int)sq_size;

    if ((errStatus = delayScanf(vi, thisPtr->myDelay, "%#c", &sz,sq_result)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
    sq_result[sz]='\0';
    }
#endif


    return statusUpdate( vi, thisPtr, errStatus );
}        /* ----- end of function ----- */ 


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_cmdData_Q(
        ViSession          vi,
        ViString           dq_cmd_string,
        ViInt32            dq_size,
        ViChar _VI_FAR     dq_result[])

/*****************************************************************************/
/*                                                                           */
/*      Passes  the  dq_cmd_string string to the instrument.                 */
/*      This entry point WILL wait for a response which may be any data.     */
/*                                                                           */
/*      A max of Size-1 bytes will be read from the instrument.              */
/*      Despite the Size-1 limitation NO termination character will be       */
/*      added to the data the calling program must decipher the data         */
/*      returned in result.                                                  */
/*                                                                           */
/*     <for message based cards only> If more than size--1 bytes  are        */
/*     generated by the instrument then the instrument's output buffer       */
/*     will be cleared.                                                      */
/*                                                                           */
/*     Note that the command string can not exceed 256 bytes in length.      */
/*                                                                           */
/*   Parameter       Description                                             */
/*                                                                           */
/*          vi    Instrument Handle returned from agb1500_init( ).           */
/*                Data Type:  ViSession                                      */
/*                Input/Output:  IN                                          */
/*                                                                           */
/* dq_cmd_string  agb1500 command. (cannot exceed 256 bytes in length)       */
/*                Data Type:  ViString                                       */
/*                Input/Output:  IN                                          */
/*                                                                           */
/*      dq_size   IN-length of param 4 (result) in bytes 32767 max.          */
/*                Data Type:  ViInt32                                        */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                agb1500_CMDSTRING_Q_MIN     2                              */
/*                agb1500_CMDSTRING_Q_MAX     32767                          */
/*                                                                           */
/*    dq_result   Response from instrument.                                  */
/*                Data Type:  ViChar _VI_FAR [ ]                             */
/*                Input/Output:  OUT                                         */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{  
    ViStatus  errStatus;
    ViInt32   mySize;
    struct    agb1500_globals *thisPtr;
    ViUInt32 rtn_size;
   

        /* Command strings must have at least one non-null character */
    if (dq_size < 2)     return statusUpdate(vi,VI_NULL,VI_ERROR_PARAMETER3);

#ifdef WIN16
        /* Strings in 16-bit windows are limited to 32K characters. */    
    if (dq_size > 32767) return statusUpdate(vi,VI_NULL,VI_ERROR_PARAMETER3);
#endif
    
    GET_GLOBALS(vi,thisPtr);
    agb1500_CDE_INIT( "agb1500_cmdData_Q" );

   /* If (message-based I/O) then write to instrument. */

    
    
    if ((errStatus = viPrintf(vi, "%s\n",dq_cmd_string )) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
    mySize = dq_size-1;
    
    if ((errStatus = delayRead(vi, thisPtr->myDelay,
                              (ViPBuf)dq_result, mySize, &rtn_size)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
    if (thisPtr->interfaceType == VI_INTF_GPIB)
        if (errStatus == VI_SUCCESS_MAX_CNT)
            viClear(vi);



    return statusUpdate( vi, thisPtr, errStatus ); 
}        /* ----- end of function ----- */
 

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_cmdInt(
        ViSession  vi,
        ViString   i_cmd_string,
        ViInt32    i_val )
/*****************************************************************************/
/*                                                                           */
/*      Passes the cmd_str string to the instrument. This  entry             */
/*      point  passes  the  string  in  i_cmd_string followed by a           */
/*      space and then the integer in val. Note  that  either an int16       */
/*      or 32 can be passed as the int16 will be promoted.                   */
/*      Also note that the i_cmd_string string cannot exceed 256 characters. */
/*                                                                           */
/*                                                                           */
/*   Parameter       Description                                             */
/*                                                                           */
/*          vi    Instrument Handle returned from agb1500_init( ).           */
/*                Data Type:  ViSession                                      */
/*                Input/Output:  IN                                          */
/*                                                                           */
/* i_cmd_string   agb1500 command. (cannot exceed 256 bytes in length)       */
/*                Data Type:  ViString                                       */
/*                Input/Output:  IN                                          */
/*                                                                           */
/*        i_val   Parameter for command                                      */
/*                Data Type:  ViInt32                                        */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                agb1500_CMDINT_MIN     -2147483647                         */
/*                agb1500_CMDINT_MAX     2147483647                          */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/


{  
    ViStatus errStatus;
    struct agb1500_globals *thisPtr;


    GET_GLOBALS(vi,thisPtr);
    agb1500_CDE_INIT( "agb1500_cmdInt" );

#ifdef NO_FORMAT_IO
    {
    ViUInt32 rtn_size;
    ViChar   lc[300];

    sprintf(lc,"%s %ld",i_cmd_string,i_val);
    if ((errStatus = viWrite(vi, (ViBuf)lc,
                                      strlen(lc), &rtn_size )) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
    }
#else
    if ((errStatus = viPrintf(vi, "%s %ld\n",i_cmd_string,i_val )) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
#endif

    return statusUpdate( vi, thisPtr, errStatus );
}        /* ----- end of function ----- */ 


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_cmdInt16_Q(
        ViSession  vi,
        ViString   iq_cmd_string,
        ViPInt16   iq_result)
/*****************************************************************************/
/*                                                                           */
/*      Passes the iq_cmd_string string to the instrument.                   */
/*      This command expects a response that can be returned as a            */
/*      16 bit integer.                                                      */
/*      Note that iq_cmd_string cannot exceed 256 bytes in length.           */
/*                                                                           */
/*                                                                           */
/*   Parameter       Description                                             */
/*                                                                           */
/*          vi    Instrument Handle returned from agb1500_init( ).           */
/*                Data Type:  ViSession                                      */
/*                Input/Output:  IN                                          */
/*                                                                           */
/* iq_cmd_string  agb1500 command. (cannot exceed 256 bytes in length)       */
/*                Data Type:  ViString                                       */
/*                Input/Output:  IN                                          */
/*                                                                           */
/*     iq_result  Result of command.                                         */
/*                Data Type:  ViPInt16                                       */
/*                Input/Output:  OUT                                         */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus;
    struct   agb1500_globals *thisPtr;


    GET_GLOBALS(vi,thisPtr)
    agb1500_CDE_INIT( "agb1500_cmdInt16_Q" );

#ifdef NO_FORMAT_IO
    {
    ViChar lc[100];
    ViUInt32 rtn_size;


    if ((errStatus = viWrite(vi, (ViBuf)iq_cmd_string,
                                 strlen(iq_cmd_string), &rtn_size )) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);

    if ((errStatus = delayRead(vi, thisPtr->myDelay,
                                 (ViPBuf)lc, 100, &rtn_size)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
    lc[rtn_size]='\0';
    *iq_result = atoi(lc);
    }
#else
    if ((errStatus = viPrintf(vi, "%s\n",iq_cmd_string)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);

    if ((errStatus = delayScanf(vi, thisPtr->myDelay, "%hd%*t",iq_result)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
#endif


    return statusUpdate( vi, thisPtr, errStatus );
}        /* ----- end of function ----- */ 


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_cmdInt32_Q(
        ViSession vi,
        ViString  lq_cmd_string,
        ViPInt32  lq_result)

/*****************************************************************************/
/*                                                                           */
/*      Passes the iq_cmd_string string to the instrument.                   */
/*      This command expects a response that can be returned as a            */
/*      32 bit integer.                                                      */
/*      Note that iq_cmd_string cannot exceed 256 bytes in length.           */
/*                                                                           */
/*                                                                           */
/*   Parameter       Description                                             */
/*                                                                           */
/*          vi    Instrument Handle returned from agb1500_init( ).           */
/*                Data Type:  ViSession                                      */
/*                Input/Output:  IN                                          */
/*                                                                           */
/* iq_cmd_string  agb1500 command. (cannot exceed 256 bytes in length)       */
/*                Data Type:  ViString                                       */
/*                Input/Output:  IN                                          */
/*                                                                           */
/*     iq_result  Result of command.                                         */
/*                Data Type:  ViPInt32                                       */
/*                Input/Output:  OUT                                         */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{  
    ViStatus  errStatus;
    struct    agb1500_globals *thisPtr;
 
    
    GET_GLOBALS(vi,thisPtr)
    agb1500_CDE_INIT( "agb1500_cmdInt32_Q" );

#ifdef NO_FORMAT_IO
    {
    ViUInt32 rtn_size;
    ViChar   lc[100];

    if ((errStatus = viWrite(vi, (ViBuf)lq_cmd_string,
                                 strlen(lq_cmd_string), &rtn_size )) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);

    if ((errStatus = delayRead(vi, thisPtr->myDelay,
                                 (ViPBuf)lc, 100, &rtn_size)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
    *lq_result = atol(lc);
    }
#else
    if ((errStatus = viPrintf(vi, "%s\n",lq_cmd_string)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);

    if ((errStatus = delayScanf(vi, thisPtr->myDelay, "%ld%*t", lq_result)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
#endif    
        

    return statusUpdate( vi, thisPtr, errStatus );
}        /* ----- end of function ----- */ 

    
/*****************************************************************************/
ViStatus _VI_FUNC agb1500_cmdInt16Arr_Q(
        ViSession         vi,
        ViString          iaq_cmd_string,
        ViInt32           iaq_size,
        ViInt16 _VI_FAR iaq_result[],
        ViPInt32          iaq_count)
/*****************************************************************************/
/*                                                                           */
/*      Passes the iaq_cmd_string string to the instrument.                  */
/*      This command expects a response that is a definite arbitrary         */
/*      block of 16 bit integers.                                            */
/*      Note that cmd_str cannot exceed 256 bytes in length.                 */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*          vi     Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/* iaq_cmd_string  agb1500 command. (cannot exceed 256 bytes in length)      */
/*                 Data Type:  ViString                                      */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*     iaq_size    Size of result                                            */
/*                 Data Type:  ViInt32Input/Output:  IN                      */
/*                 Values:                                                   */
/*                 agb1500_CMDINT16ARR_Q_MIN     1                           */
/*                 agb1500_CMDINT16ARR_Q_MAX     2147483647                  */
/*                                                                           */
/*   iaq_result    Result of command.                                        */
/*                 Data Type:  ViInt16 _VI_FAR [ ]                           */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*    iaq_count    Count of valid items in result.                           */
/*                 Data Type:  ViPInt32                                      */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus  errStatus ;
    ViUInt32  cnt;
    struct    agb1500_globals * thisPtr;
    ViChar    lc[100];
    ViInt32   i;
    ViInt32   ArrSize;
    ViInt32   nbytes;
    ViChar    _huge *Array;


    GET_GLOBALS(vi,thisPtr)
    agb1500_CDE_INIT( "agb1500_cmdInt16Arr_Q" );

    if (iaq_size < agb1500_CMDINT16ARR_Q_MIN || iaq_size > agb1500_CMDINT16ARR_Q_MAX)
        return statusUpdate(vi,thisPtr,VI_ERROR_PARAMETER3);

    if ((errStatus = viWrite(vi, (ViBuf)iaq_cmd_string,
                                     strlen(iaq_cmd_string), &cnt)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
            
    if ((errStatus = delayRead(vi, thisPtr->myDelay,
                                     (ViPBuf)lc, 1, &cnt)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
    
    if (lc[0] != '#')
        return statusUpdate(vi,thisPtr,VI_ERROR_INV_EXPR);
        
    if ((errStatus = delayRead(vi, thisPtr->myDelay,
                                     (ViPBuf)lc, 1, &cnt)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
    
    nbytes = lc[0]-'0';
        
    if (nbytes) {
        if ((errStatus = delayRead(vi, thisPtr->myDelay,
                                     (ViPBuf)lc, nbytes, &cnt)) < VI_SUCCESS)
            return statusUpdate(vi,thisPtr,errStatus);
        lc[cnt] = '\0';
        ArrSize = atol(lc);
    }
    else
        ArrSize = iaq_size*sizeof(ViInt16);
            
#ifdef WIN16
    Array = (ViChar _huge *)halloc(ArrSize, 1 ); 
#else                                     
    Array = (ViChar *)malloc(ArrSize ); 
#endif
    
    if (!Array )
        return statusUpdate(vi,thisPtr,VI_ERROR_ALLOC);
    
    if ((errStatus = delayRead(vi, thisPtr->myDelay,
                                     (ViPBuf)Array, ArrSize, &cnt)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
    if (thisPtr->interfaceType == VI_INTF_GPIB)
        if (errStatus == VI_SUCCESS_MAX_CNT)
            viClear(vi);
    ArrSize = cnt/sizeof(ViInt16);
    ArrSize = (ArrSize > iaq_size ) ? iaq_size : ArrSize;
    
    /*copy only as many as the user allows*/
    _fmemcpy(iaq_result,Array,(size_t)ArrSize*sizeof(ViInt16) ); 

#ifdef WIN16
    _hfree(Array);    
#else
    free(Array); 
#endif    

    *iaq_count=ArrSize;

    for (i=0; i<*iaq_count; i++)
        SWAP_16(&iaq_result[i]);


    return statusUpdate(vi,thisPtr,VI_SUCCESS);                
}        /* ----- end of function ----- */
                                                                         

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_cmdInt32Arr_Q(
        ViSession         vi,
        ViString         laq_cmd_string,
        ViInt32         laq_size,
        ViInt32 _VI_FAR laq_result[],
        ViPInt32         laq_count)
/*****************************************************************************/
/*                                                                           */
/*      Passes the iaq_cmd_string string to the instrument.                  */
/*      This command expects a response that is a definite arbitrary         */
/*      block of 32 bit integers.                                            */
/*      Note that cmd_str cannot exceed 256 bytes in length.                 */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*          vi     Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/* laq_cmd_string  agb1500 command. (cannot exceed 256 bytes in length)      */
/*                 Data Type:  ViString                                      */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*     laq_size    Size of result                                            */
/*                 Data Type:  ViInt32Input/Output:  IN                      */
/*                 Values:                                                   */
/*                 agb1500_CMDINT32ARR_Q_MIN     1                           */
/*                 agb1500_CMDINT32ARR_Q_MAX     2147483647                  */
/*                                                                           */
/*   iaq_result    Result of command.                                        */
/*                 Data Type:  ViInt32 _VI_FAR [ ]                           */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*    iaq_count    Count of valid items in result.                           */
/*                 Data Type:  ViPInt32                                      */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus  errStatus ;
    ViUInt32  cnt;
    struct    agb1500_globals * thisPtr;
    ViChar    lc[100];
    ViInt32   i;
    ViInt32   ArrSize;
    ViInt32   nbytes;
    ViChar    _huge *Array;

    
    GET_GLOBALS(vi,thisPtr)
    agb1500_CDE_INIT( "agb1500_cmdInt32Arr_Q" );

    if (laq_size < agb1500_CMDINT32ARR_Q_MIN || laq_size > agb1500_CMDINT32ARR_Q_MAX)
        return statusUpdate(vi,thisPtr,VI_ERROR_PARAMETER3);

    if ((errStatus = viWrite(vi, (ViBuf)laq_cmd_string,
                                     strlen(laq_cmd_string), &cnt)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
            
    if ((errStatus = delayRead(vi, thisPtr->myDelay,
                                     (ViPBuf)lc, 1, &cnt)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
    
    if (lc[0] != '#')
        return statusUpdate(vi,thisPtr,VI_ERROR_INV_EXPR);
        
    if ((errStatus = delayRead(vi, thisPtr->myDelay,
                                     (ViPBuf)lc, 1, &cnt)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
    
    nbytes = lc[0]-'0';

    if (nbytes) {
        if ((errStatus = delayRead(vi, thisPtr->myDelay,
                                     (ViPBuf)lc, nbytes, &cnt)) < VI_SUCCESS)
            return statusUpdate(vi,thisPtr,errStatus);
        lc[cnt] = '\0';
        ArrSize = atol(lc);
    }
    else
        ArrSize = laq_size*sizeof(ViInt32);
            
#ifdef WIN16
    Array = (ViChar _huge *)halloc(ArrSize, 1 ); 
#else                                     
    Array = (ViChar *)malloc(ArrSize ); 
#endif
    
    if (!Array)
        return statusUpdate(vi,thisPtr,VI_ERROR_ALLOC);

    if ((errStatus = delayRead(vi, thisPtr->myDelay,
                                     (ViPBuf)Array, ArrSize, &cnt)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
    if (thisPtr->interfaceType == VI_INTF_GPIB)
        if (errStatus == VI_SUCCESS_MAX_CNT)
            viClear(vi);
    ArrSize = cnt/sizeof(ViInt32);
    ArrSize = (ArrSize > laq_size ) ? laq_size : ArrSize;

     /*copy only as many as the user allows*/

    _fmemcpy(laq_result,Array,(size_t)ArrSize*sizeof(ViInt32) );
#ifdef WIN16
    _hfree(Array);
#else
    free(Array);
#endif

    *laq_count=ArrSize;

    for (i=0; i<*laq_count; i++)
        SWAP_32 (&laq_result[i]);

    return statusUpdate(vi,thisPtr,VI_SUCCESS);                
}        /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_cmdReal(
        ViSession  vi,
        ViString   r_cmd_string,
        ViReal64   r_val )
/*****************************************************************************/
/*                                                                           */
/*      Passes the r_cmd_string string to the instrument.                    */
/*      This  entry  point  passes  the  string  in  r_cmd_string            */
/*      followed by a space and then the Real in value.                      */
/*      Note that  either a Real32  or 64 can be  passed as the Real32       */
/*      will  be  promoted.                                                  */
/*      Also note that the r_cmd_string string  cannot exceed 256 characters.*/
/*                                                                           */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*          vi     Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/* r_cmd_string    agb1500 command. (cannot exceed 256 bytes in length)      */
/*                 Data Type:  ViString                                      */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*        r_val    Parameter for command.                                    */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 agb1500_CMDREAL_MIN     -1e+300                           */
/*                 agb1500_CMDREAL_MAX     1e+300                            */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus;
    struct   agb1500_globals *thisPtr;


    GET_GLOBALS(vi,thisPtr);
    agb1500_CDE_INIT( "agb1500_cmdReal" );

#ifdef NO_FORMAT_IO
    {
    ViUInt32  rtn_size;
    ViChar    lc[300];

    sprintf(lc,"%s %g",r_cmd_string,r_val);
    if ((errStatus = viWrite(vi, (ViBuf)lc,
                                   strlen(lc), &rtn_size )) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
    }
#else
    if ((errStatus = viPrintf(vi, "%s %g\n",r_cmd_string,r_val )) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
#endif

    return statusUpdate( vi, thisPtr, errStatus );
}        /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_cmdReal32_Q(
        ViSession  vi,
        ViString   rq_cmd_string,
        ViPReal32  rq_result)
/*****************************************************************************/
/*                                                                           */
/*      Passes the rq_cmd_string string to the instrument.                   */
/*      This  command  expects  a  response  that  can  be returned          */
/*      as a 32 bit realr.                                                   */
/*      Note rq_cmd_string cannot exceed 256 bytes in length.                */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*          vi     Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/* rq_cmd_string   agb1500 command. (cannot exceed 256 bytes in length)      */
/*                 Data Type:  ViString                                      */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*     rq_result   Result of command.                                        */
/*                 Data Type:  ViPReal32                                     */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{   
#ifdef NO_FORMAT_IO
    ViUInt32  rtn_size;
#endif

    ViStatus  errStatus;
    struct    agb1500_globals *thisPtr;

   
    GET_GLOBALS(vi,thisPtr)
    agb1500_CDE_INIT( "agb1500_cmdReal32_Q" );

#ifdef NO_FORMAT_IO
    {
    ViChar lc[100];
    if ((errStatus = viWrite(vi, (ViBuf)rq_cmd_string,
                                 strlen(rq_cmd_string), &rtn_size )) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);

    if ((errStatus = delayRead(vi, thisPtr->myDelay,
                                 (ViPBuf)lc, 100, &rtn_size)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
    *rq_result = (ViReal32)atof(lc);
    }
#else
    if ((errStatus = viPrintf(vi, "%s\n",rq_cmd_string)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);

    if ((errStatus = delayScanf(vi, thisPtr->myDelay,
                                 "%f%*t", rq_result)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
#endif    
        

    return statusUpdate( vi, thisPtr, errStatus );
}        /* ----- end of function ----- */ 

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_cmdReal64_Q(
    ViSession  vi,
    ViString   dq_cmd_string,
    ViPReal64  dq_result)
/*****************************************************************************/
/*                                                                           */
/*      Passes the dq_cmd_string string to the instrument.                   */
/*      This  command  expects  a  response  that  can  be returned          */
/*      as a 64 bit real.                                                    */
/*      Note dq_cmd_string cannot exceed 256 bytes in length.                */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*          vi     Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/* dq_cmd_string   agb1500 command. (cannot exceed 256 bytes in length)      */
/*                 Data Type:  ViString                                      */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*     dq_result   Result of command.                                        */
/*                 Data Type:  ViPReal64                                     */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{   
    ViStatus  errStatus;
    struct    agb1500_globals *thisPtr;


    GET_GLOBALS(vi,thisPtr)
    agb1500_CDE_INIT( "agb1500_cmdReal64_Q" );

#ifdef NO_FORMAT_IO
    {
    ViUInt32  rtn_size;
    ViChar    lc[100];

    if ((errStatus = viWrite(vi, (ViBuf)dq_cmd_string,
                                 strlen(dq_cmd_string), &rtn_size )) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);

    if ((errStatus = delayRead(vi, thisPtr->myDelay,
                                 (ViPBuf)lc, 100, &rtn_size)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
    *dq_result = atof(lc);
    }
#else
    if ((errStatus = viPrintf(vi, "%s\n",dq_cmd_string)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);

    if ((errStatus = delayScanf(vi, thisPtr->myDelay,
                                     "%lg%*t", dq_result)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
#endif    
        

    return statusUpdate( vi, thisPtr, errStatus );
}        /* ----- end of function ----- */ 


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_cmdReal32Arr_Q(
        ViSession              vi,
        ViString            raq_cmd_string,
        ViInt32                raq_size,
        ViReal32 _VI_FAR    raq_result[],
        ViPInt32               raq_count)
/*****************************************************************************/
/*                                                                           */
/*      Passes the cmd_str string to the instrument.                         */
/*      This  command  expects a response that is a definite                 */
/*      arbitrary block of 32 bit reals.                                     */
/*      Note that cmd_str cannot exceed 256 bytes in length.                 */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/* raq_cmd_string  agb1500 command. (cannot exceed 256 bytes in length)      */
/*                 Data Type:  ViString                                      */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*     raq_size        Size of result.                                       */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 agb1500_CMDREAL32ARR_Q_MIN     1                          */
/*                 agb1500_CMDREAL32ARR_Q_MAX     2147483647                 */
/*                                                                           */
/*     raq_resul   Result from instrument.                                   */
/*                 Data Type:  ViReal32 _VI_FAR [ ]                          */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*      raq_count  Count of valid entries in result.                         */
/*                 Data Type:  ViPInt32                                      */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus  errStatus ;
    ViUInt32  cnt;
    struct    agb1500_globals * thisPtr;
    ViChar    lc[100];
    ViInt32   i;
    ViInt32   ArrSize;
    ViInt32   nbytes;
    ViChar    _huge *Array;


    GET_GLOBALS(vi,thisPtr)
    agb1500_CDE_INIT( "agb1500_cmdReal32Arr_Q" );

    if (raq_size < agb1500_CMDREAL32ARR_Q_MIN || raq_size > agb1500_CMDREAL32ARR_Q_MAX)
        return statusUpdate(vi,thisPtr,VI_ERROR_PARAMETER3);

    if ((errStatus = viWrite(vi, (ViBuf)raq_cmd_string,
                                       strlen(raq_cmd_string),&cnt)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
            
    if ((errStatus = delayRead(vi, thisPtr->myDelay,
                                       (ViPBuf)lc, 1, &cnt)) < VI_SUCCESS)
         return statusUpdate(vi,thisPtr,errStatus);
    
    if (lc[0] != '#')
        return statusUpdate(vi,thisPtr,VI_ERROR_INV_EXPR);
        
    if ((errStatus = delayRead(vi, thisPtr->myDelay,
                                       (ViPBuf)lc, 1, &cnt)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);

    nbytes = lc[0]-'0';

    if (nbytes) {
        if ((errStatus = delayRead(vi, thisPtr->myDelay,
                                       (ViPBuf)lc, nbytes, &cnt)) < VI_SUCCESS)
            return statusUpdate(vi,thisPtr,errStatus);
        lc[cnt] = '\0';
        ArrSize = atol(lc); 
    }                  
    else
        ArrSize = raq_size*sizeof(ViReal32);

#ifdef WIN16
    Array = (ViChar _huge *)halloc(ArrSize, 1 );
#else                                     
    Array = (ViChar *)malloc(ArrSize); 
#endif
    
    if (!Array)
        return statusUpdate(vi,thisPtr,VI_ERROR_ALLOC);
    
    if ((errStatus = delayRead(vi, thisPtr->myDelay,
                                       (ViPBuf)Array, ArrSize, &cnt)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
    if (thisPtr->interfaceType == VI_INTF_GPIB)
        if (errStatus == VI_SUCCESS_MAX_CNT)
            viClear(vi);
    ArrSize = cnt/sizeof(ViReal32);
    ArrSize = (ArrSize > raq_size ) ? raq_size : ArrSize;

    _fmemcpy(raq_result,Array,(size_t)ArrSize*sizeof(ViReal32) );

#ifdef WIN16
    _hfree(Array);
#else
    free(Array);
#endif

    *raq_count=ArrSize;

    for (i=0; i<*raq_count; i++)
        SWAP_FLOAT32(&raq_result[i]);


    return statusUpdate(vi,thisPtr,VI_SUCCESS);            
}        /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_cmdReal64Arr_Q(
        ViSession              vi,
        ViString               daq_cmd_string,
        ViInt32                daq_size,
        ViReal64 _VI_FAR    daq_result[],
        ViPInt32               daq_count)
/*****************************************************************************/
/*                                                                           */
/*      Passes the cmd_str string to the instrument.                         */
/*      This  command  expects a response that is a definite                 */
/*      arbitrary block of 64 bit reals.                                     */
/*      Note that cmd_str cannot exceed 256 bytes in length.                 */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/* daq_cmd_string  agb1500 command. (cannot exceed 256 bytes in length)      */
/*                 Data Type:  ViString                                      */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*     daq_size    Size of result.                                           */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 agb1500_CMDREAL64ARR_Q_MIN     1                          */
/*                 agb1500_CMDREAL64ARR_Q_MAX     2147483647                 */
/*                                                                           */
/*     daq_resul   Result from instrument.                                   */
/*                 Data Type:  ViReal64 _VI_FAR [ ]                          */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*      daq_count  Count of valid entries in result.                         */
/*                 Data Type:  ViPInt32                                      */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus  errStatus ;
    ViUInt32  cnt;
    struct    agb1500_globals * thisPtr;
    ViChar    lc[100];
    ViInt32   i;
    ViInt32   ArrSize;
    ViInt32   nbytes;
    ViChar    _huge *Array;

    
    GET_GLOBALS(vi,thisPtr)
    agb1500_CDE_INIT( "agb1500_cndReal64Arr_Q" );

    if (daq_size < agb1500_CMDREAL64ARR_Q_MIN || daq_size > agb1500_CMDREAL64ARR_Q_MAX)
        return statusUpdate(vi,thisPtr,VI_ERROR_PARAMETER3);

    if ((errStatus = viWrite(vi, (ViBuf)daq_cmd_string,
                                       strlen(daq_cmd_string),&cnt))< VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
            
    if ((errStatus = delayRead(vi, thisPtr->myDelay,
                                       (ViPBuf)lc, 1, &cnt)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);

    if (lc[0] != '#')
        return statusUpdate(vi,thisPtr,VI_ERROR_INV_EXPR);
        
    if ((errStatus = delayRead(vi, thisPtr->myDelay,
                                       (ViPBuf)lc, 1, &cnt)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);

    nbytes = lc[0]-'0';

    if (nbytes) {
        if ((errStatus = delayRead(vi, thisPtr->myDelay,
                                       (ViPBuf)lc, nbytes, &cnt)) < VI_SUCCESS)
            return statusUpdate(vi,thisPtr,errStatus);
        lc[cnt]='\0';
        ArrSize = atol(lc);
    }
    else /* indefinate */
        ArrSize = daq_size*sizeof(ViReal64);

#ifdef WIN16
    Array = (ViChar _huge *)halloc(ArrSize, 1 );
#else
    Array = (ViChar *)malloc(ArrSize ); 
#endif
    
    if (!Array)
        return statusUpdate(vi,thisPtr,VI_ERROR_ALLOC);
    
    if ((errStatus = delayRead(vi, thisPtr->myDelay,
                                       (ViPBuf)Array, ArrSize, &cnt)) < VI_SUCCESS)
        return statusUpdate(vi,thisPtr,errStatus);
    if (thisPtr->interfaceType == VI_INTF_GPIB)
        if (errStatus == VI_SUCCESS_MAX_CNT)
            viClear(vi);
    ArrSize = cnt/sizeof(ViReal64);
    ArrSize = (ArrSize > daq_size ) ? daq_size : ArrSize;

     /*copy only as many as the user allows*/
    _fmemcpy(daq_result,Array,(size_t)ArrSize*sizeof(ViReal64) );

#ifdef WIN16
    _hfree(Array);
#else
    free(Array);
#endif

    *daq_count=ArrSize;

    for (i=0; i<*daq_count; i++)
        SWAP_FLOAT64(&daq_result[i]);


    return statusUpdate(vi,thisPtr,VI_SUCCESS);
}        /* ----- end of function ----- */
                                                                         


/*===========================================================================*/

/* I/V Range Definition */
#define agb1500_AUTOR_BORDER   1.0e-50

#define agb1500_5VR_BORDER     (agb1500_LMA_5V_RANGE     * 1.01)
#define agb1500_05VR_BORDER    (agb1500_LMA_05V_RANGE    * 1.01)

#define agb1500_2VR_BORDER     (agb1500_LMA_2V_RANGE     * 1.01)
#define agb1500_20VR_BORDER    (agb1500_LMA_20V_RANGE    * 1.01)
#define agb1500_40VR_BORDER    (agb1500_LMA_40V_RANGE    * 1.01)
#define agb1500_100VR_BORDER   (agb1500_LMA_100V_RANGE   * 1.01)
#define agb1500_200VR_BORDER   (agb1500_LMA_200V_RANGE   * 1.01)

#define agb1500_1pAR_BORDER    (agb1500_LMA_1pA_RANGE    * 1.01)
#define agb1500_10pAR_BORDER   (agb1500_LMA_10pA_RANGE   * 1.01)
#define agb1500_100pAR_BORDER  (agb1500_LMA_100pA_RANGE  * 1.01)

#define agb1500_1nAR_BORDER    (agb1500_LMA_1nA_RANGE    * 1.01)
#define agb1500_10nAR_BORDER   (agb1500_LMA_10nA_RANGE   * 1.01)
#define agb1500_100nAR_BORDER  (agb1500_LMA_100nA_RANGE  * 1.01)
#define agb1500_1uAR_BORDER    (agb1500_LMA_1uA_RANGE    * 1.01)
#define agb1500_10uAR_BORDER   (agb1500_LMA_10uA_RANGE   * 1.01)
#define agb1500_100uAR_BORDER  (agb1500_LMA_100uA_RANGE  * 1.01)
#define agb1500_1mAR_BORDER    (agb1500_LMA_1mA_RANGE    * 1.01)
#define agb1500_10mAR_BORDER   (agb1500_LMA_10mA_RANGE   * 1.01)
#define agb1500_100mAR_BORDER  (agb1500_LMA_100mA_RANGE  * 1.01)
#define agb1500_1AR_BORDER     (agb1500_LMA_1A_RANGE     * 1.01)

/* Auto Range */
#define agb1500_AUTO_RID       0

/* V Range */
#define agb1500_LMA_5V_RID     50
#define agb1500_LMA_05V_RID    5
#define agb1500_FIX_5V_RID    -50
#define agb1500_FIX_05V_RID   -5

#define agb1500_LMA_200V_RID   15
#define agb1500_LMA_100V_RID   14
#define agb1500_LMA_40V_RID    13
#define agb1500_LMA_20V_RID    12
#define agb1500_LMA_2V_RID     11
#define agb1500_FIX_200V_RID  -15
#define agb1500_FIX_100V_RID  -14
#define agb1500_FIX_40V_RID   -13
#define agb1500_FIX_20V_RID   -12
#define agb1500_FIX_2V_RID    -11

/* I Range */
#define agb1500_LMA_100pA_RID   10
#define agb1500_LMA_10pA_RID    9
#define agb1500_LMA_1pA_RID     8
#define agb1500_FIX_100pA_RID  -10
#define agb1500_FIX_10pA_RID   -9
#define agb1500_FIX_1pA_RID    -8

#define agb1500_LMA_1A_RID      20
#define agb1500_LMA_100mA_RID   19
#define agb1500_LMA_10mA_RID    18
#define agb1500_LMA_1mA_RID     17
#define agb1500_LMA_100uA_RID   16
#define agb1500_LMA_10uA_RID    15
#define agb1500_LMA_1uA_RID     14
#define agb1500_LMA_100nA_RID   13
#define agb1500_LMA_10nA_RID    12
#define agb1500_LMA_1nA_RID     11
#define agb1500_FIX_1A_RID     -20
#define agb1500_FIX_100mA_RID  -19
#define agb1500_FIX_10mA_RID   -18
#define agb1500_FIX_1mA_RID    -17
#define agb1500_FIX_100uA_RID  -16
#define agb1500_FIX_10uA_RID   -15
#define agb1500_FIX_1uA_RID    -14
#define agb1500_FIX_100nA_RID  -13
#define agb1500_FIX_10nA_RID   -12
#define agb1500_FIX_1nA_RID    -11

/* compliance ignore */
#define    COMP_IGNORE_VAL        1000.0


/********************* Internal Functions ************************************/

/*-----------------------------------------------------------------------------
 * FUNC    : ViInt32 vRangeId
 *-----------------------------------------------------------------------------
 *
 * PURPOSE :  This function returns V Range ID from specified real range value.
 *        
 *           
 * 
 * PARAM 1 : ViInt32 channel
 * IN        
 *            Channel number of the unit to get V Range ID
 *
 * PARAM 2 : ViInt32 unt
 *
 *            Type of module
 *            For HPSMU,		agb1500_HPSMU_MODEL_NO
 *            For MPSMU,		agb1500_MPSMU_MODEL_NO
 *            For HRSMU,		agb1500_HRSMU_MODEL_NO
 *            For HRSMU wt ASU, agb1500_ASU_MODEL_NO
 *
 * PARAM 2 : ViReal64 range
 * IN 
 *            Real V range value
 *
 * RETURN  : ViInt32
 *            V Range ID
 *
 *-----------------------------------------------------------------------------
 */
static
ViInt32 vRangeId(
            ViInt32   channel,
			ViInt32   unt,
            ViReal64  range )
{
	if( unt != agb1500_HPSMU_MODEL_NO ){
		switch ( channel ) {
		case agb1500_CH_1 :
		case agb1500_CH_2 :
		case agb1500_CH_3 :
		case agb1500_CH_4 :
		case agb1500_CH_5 :
		case agb1500_CH_6 :
		case agb1500_CH_7 :
		case agb1500_CH_8 :
		case agb1500_CH_9 :
		case agb1500_CH_10:
			if ( range > 0 ) {
				if ( range < agb1500_AUTOR_BORDER )  return( agb1500_AUTO_RID );
				if ( range < agb1500_05VR_BORDER )   return( agb1500_LMA_05V_RID );
				if ( range < agb1500_2VR_BORDER )    return( agb1500_LMA_2V_RID );
				if ( range < agb1500_5VR_BORDER )    return( agb1500_LMA_5V_RID );
				if ( range < agb1500_20VR_BORDER )   return( agb1500_LMA_20V_RID );
				if ( range < agb1500_40VR_BORDER )   return( agb1500_LMA_40V_RID );
					return( agb1500_LMA_100V_RID );
				}
			else {
				if ( -1 * range < agb1500_AUTOR_BORDER )  return( agb1500_AUTO_RID );
				if ( -1 * range < agb1500_05VR_BORDER )   return( agb1500_FIX_05V_RID );
				if ( -1 * range < agb1500_2VR_BORDER )    return( agb1500_FIX_2V_RID );
				if ( -1 * range < agb1500_5VR_BORDER )    return( agb1500_FIX_5V_RID );
				if ( -1 * range < agb1500_20VR_BORDER )   return( agb1500_FIX_20V_RID );
				if ( -1 * range < agb1500_40VR_BORDER )   return( agb1500_FIX_40V_RID );
					return( agb1500_FIX_100V_RID );
			}
			break;
		default :
			return( agb1500_AUTO_RID );
		}
	}else{
		switch ( channel ) {
		case agb1500_CH_1 :
		case agb1500_CH_2 :
		case agb1500_CH_3 :
		case agb1500_CH_4 :
		case agb1500_CH_5 :
		case agb1500_CH_6 :
		case agb1500_CH_7 :
		case agb1500_CH_8 :
		case agb1500_CH_9 :
		case agb1500_CH_10:
			if ( range > 0 ) {
				if ( range < agb1500_AUTOR_BORDER )  return( agb1500_AUTO_RID );
				if ( range < agb1500_2VR_BORDER )    return( agb1500_LMA_2V_RID );
				if ( range < agb1500_20VR_BORDER )   return( agb1500_LMA_20V_RID );
				if ( range < agb1500_40VR_BORDER )   return( agb1500_LMA_40V_RID );
				if ( range < agb1500_100VR_BORDER )  return( agb1500_LMA_100V_RID );
					return( agb1500_LMA_200V_RID );
				}
			else {
				if ( -1 * range < agb1500_AUTOR_BORDER )  return( agb1500_AUTO_RID );
				if ( -1 * range < agb1500_2VR_BORDER )    return( agb1500_FIX_2V_RID );
				if ( -1 * range < agb1500_20VR_BORDER )   return( agb1500_FIX_20V_RID );
				if ( -1 * range < agb1500_40VR_BORDER )   return( agb1500_FIX_40V_RID );
				if ( -1 * range < agb1500_100VR_BORDER )  return( agb1500_FIX_100V_RID );
					return( agb1500_FIX_200V_RID );
			}
			break;
		default :
			return( agb1500_AUTO_RID );
		}
	}
     return( VI_SUCCESS ); 
} /* ----- end of function ----- */


/*-----------------------------------------------------------------------------
 * FUNC    : ViInt32 iRangeId
 *-----------------------------------------------------------------------------
 *
 * PURPOSE :  This function returns I Range ID from specified real range value.
 *        
 *           
 * 
 * PARAM 1 : ViInt32 channel
 * IN        
 *            Channel number of the unit to get I Range ID
 *
 * PARAM 2 : ViInt32 unt
 * IN 
 *            Type of module
 *            For HPSMU,		agb1500_HPSMU_MODEL_NO
 *            For MPSMU,		agb1500_MPSMU_MODEL_NO
 *            For HRSMU,		agb1500_HRSMU_MODEL_NO
 *            For HRSMU wt ASU, agb1500_ASU_MODEL_NO
 *
 * PARAM 3 : ViReal64 range
 * IN 
 *            Real I range value
 *
 * RETURN  : ViInt32
 *            I Range ID
 *
 *-----------------------------------------------------------------------------
 */
static 
ViInt32 iRangeId(
                ViInt32   channel,
				ViInt32   unt,
                ViReal64  range )
{
	switch ( unt ){
	case agb1500_ASU_MODEL_NO:
	case agb1500_HRSMU_MODEL_NO:
		switch ( channel ) {
		case agb1500_CH_1 :
		case agb1500_CH_2 :
		case agb1500_CH_3 :
		case agb1500_CH_4 :
		case agb1500_CH_5 :
		case agb1500_CH_6 :
		case agb1500_CH_7 :
		case agb1500_CH_8 :
		case agb1500_CH_9 :
		case agb1500_CH_10:
			if ( range > (ViReal64)0.0 ) {
				/* Limited Auto Range */
				if ( range < agb1500_AUTOR_BORDER )  return( agb1500_AUTO_RID );
				if ( unt == agb1500_ASU_MODEL_NO ){
					if ( range < agb1500_1pAR_BORDER )   return( agb1500_LMA_1pA_RID );
				}
				if ( range < agb1500_10pAR_BORDER )  return( agb1500_LMA_10pA_RID );
				if ( range < agb1500_100pAR_BORDER ) return( agb1500_LMA_100pA_RID );
				if ( range < agb1500_1nAR_BORDER )   return( agb1500_LMA_1nA_RID );
				if ( range < agb1500_10nAR_BORDER )  return( agb1500_LMA_10nA_RID );
				if ( range < agb1500_100nAR_BORDER ) return( agb1500_LMA_100nA_RID );
				if ( range < agb1500_1uAR_BORDER )   return( agb1500_LMA_1uA_RID );
				if ( range < agb1500_10uAR_BORDER )  return( agb1500_LMA_10uA_RID );
				if ( range < agb1500_100uAR_BORDER ) return( agb1500_LMA_100uA_RID );
				if ( range < agb1500_1mAR_BORDER )   return( agb1500_LMA_1mA_RID );
				if ( range < agb1500_10mAR_BORDER )  return( agb1500_LMA_10mA_RID );
				return( agb1500_LMA_100mA_RID );
			}
			else {
				/* Fixed Range */
				if ( (ViReal64)-1.0 * range < agb1500_AUTOR_BORDER )  return( agb1500_AUTO_RID );
				if ( unt == agb1500_ASU_MODEL_NO ){
					if ( (ViReal64)-1.0 * range < agb1500_1pAR_BORDER )   return( agb1500_FIX_1pA_RID );
				}
				if ( (ViReal64)-1.0 * range < agb1500_10pAR_BORDER )  return( agb1500_FIX_10pA_RID );
				if ( (ViReal64)-1.0 * range < agb1500_100pAR_BORDER ) return( agb1500_FIX_100pA_RID );
				if ( (ViReal64)-1.0 * range < agb1500_1nAR_BORDER )   return( agb1500_FIX_1nA_RID );
				if ( (ViReal64)-1.0 * range < agb1500_10nAR_BORDER )  return( agb1500_FIX_10nA_RID );
				if ( (ViReal64)-1.0 * range < agb1500_100nAR_BORDER ) return( agb1500_FIX_100nA_RID );
				if ( (ViReal64)-1.0 * range < agb1500_1uAR_BORDER )   return( agb1500_FIX_1uA_RID );
				if ( (ViReal64)-1.0 * range < agb1500_10uAR_BORDER )  return( agb1500_FIX_10uA_RID );
				if ( (ViReal64)-1.0 * range < agb1500_100uAR_BORDER ) return( agb1500_FIX_100uA_RID );
				if ( (ViReal64)-1.0 * range < agb1500_1mAR_BORDER )   return( agb1500_FIX_1mA_RID );
				if ( (ViReal64)-1.0 * range < agb1500_10mAR_BORDER )  return( agb1500_FIX_10mA_RID );
				return( agb1500_FIX_100mA_RID );
			}
			break;

		default :
		 		return( agb1500_AUTO_RID );
		}	
 	case agb1500_MPSMU_MODEL_NO:
	case agb1500_HPSMU_MODEL_NO:
		switch ( channel ) {
		case agb1500_CH_1 :
		case agb1500_CH_2 :
		case agb1500_CH_3 :
		case agb1500_CH_4 :
		case agb1500_CH_5 :
		case agb1500_CH_6 :
		case agb1500_CH_7 :
		case agb1500_CH_8 :
		case agb1500_CH_9 :
		case agb1500_CH_10:
			if ( range > (ViReal64)0.0 ) {
				/* Limited Auto Range */
				if ( range < agb1500_AUTOR_BORDER )  return( agb1500_AUTO_RID );
				if ( range < agb1500_1nAR_BORDER )   return( agb1500_LMA_1nA_RID );
				if ( range < agb1500_10nAR_BORDER )  return( agb1500_LMA_10nA_RID );
				if ( range < agb1500_100nAR_BORDER ) return( agb1500_LMA_100nA_RID );
				if ( range < agb1500_1uAR_BORDER )   return( agb1500_LMA_1uA_RID );
				if ( range < agb1500_10uAR_BORDER )  return( agb1500_LMA_10uA_RID );
				if ( range < agb1500_100uAR_BORDER ) return( agb1500_LMA_100uA_RID );
				if ( range < agb1500_1mAR_BORDER )   return( agb1500_LMA_1mA_RID );
				if ( range < agb1500_10mAR_BORDER )  return( agb1500_LMA_10mA_RID );
				if ( unt == agb1500_HPSMU_MODEL_NO ){
					if ( range < agb1500_100mAR_BORDER ) return( agb1500_LMA_100mA_RID );
					return( agb1500_LMA_1A_RID );
				}else{
					return( agb1500_LMA_100mA_RID );
				}
			}
			else {
				/* Fixed Range */
				if ( (ViReal64)-1.0 * range < agb1500_AUTOR_BORDER )  return( agb1500_AUTO_RID );
				if ( (ViReal64)-1.0 * range < agb1500_1nAR_BORDER )   return( agb1500_FIX_1nA_RID );
				if ( (ViReal64)-1.0 * range < agb1500_10nAR_BORDER )  return( agb1500_FIX_10nA_RID );
				if ( (ViReal64)-1.0 * range < agb1500_100nAR_BORDER ) return( agb1500_FIX_100nA_RID );
				if ( (ViReal64)-1.0 * range < agb1500_1uAR_BORDER )   return( agb1500_FIX_1uA_RID );
				if ( (ViReal64)-1.0 * range < agb1500_10uAR_BORDER )  return( agb1500_FIX_10uA_RID );
				if ( (ViReal64)-1.0 * range < agb1500_100uAR_BORDER ) return( agb1500_FIX_100uA_RID );
				if ( (ViReal64)-1.0 * range < agb1500_1mAR_BORDER )   return( agb1500_FIX_1mA_RID );
				if ( (ViReal64)-1.0 * range < agb1500_10mAR_BORDER )  return( agb1500_FIX_10mA_RID );
				if( unt == agb1500_HPSMU_MODEL_NO ){
					if ( (ViReal64)-1.0 * range < agb1500_100mAR_BORDER ) return( agb1500_FIX_100mA_RID );
					return( agb1500_FIX_1A_RID );
				}else{
					return( agb1500_FIX_100mA_RID );
				}
			}
			break;

		default :
			return( agb1500_AUTO_RID );
		}
	}	
	return( VI_SUCCESS );  
} /* ----- end of function ----- */


/*-----------------------------------------------------------------------------
 * FUNC    : ViInt32 vRangeMode
 *-----------------------------------------------------------------------------
 *
 * PURPOSE :  This function returns returns V Range Mode from specified 
 *            real range value.
 *        
 *           
 * 
 * PARAM 1 : ViReal64 range
 * IN 
 *            Real V range value
 *
 * RETURN  : ViInt32
 *            V Range Mode [ AUTO_MODE | LIMIT_MODE | FIXED_MODE ]
 *
 *-----------------------------------------------------------------------------
 */
static
ViInt32 vRangeMode(
            ViReal64  range )
{
#define    AUTO_MODE         0
#define    LIMIT_MODE        1
#define    FIXED_MODE        2

    if ( range > 0 ) {
        if ( range < agb1500_AUTOR_BORDER )  return( AUTO_MODE );
        return( LIMIT_MODE );
    }
    else {
        if ( -1 * range < agb1500_AUTOR_BORDER )  return( AUTO_MODE );
        return( FIXED_MODE );
    }
} /* ----- end of function ----- */


/*-----------------------------------------------------------------------------
 * FUNC    : ViStatus asciiDataRead
 *-----------------------------------------------------------------------------
 *
 * PURPOSE :  This function read measurment data. 
 *        
 *           
 * 
 * PARAM 1 : ViSession vi
 * IN        
 *            Instrument Handle returned from agb1500_init().
 *
 * PARAM 2 : ViInt32 mode
 * OUT
 *            set/measurment mode.
 *                   0:Set data
 *                   1:Measurment data
 *
 * PARAM 3 : ViInt32 dataKind
 * OUT
 *            data kind.
 *                   0:voltage
 *                   1:electric current data
 *                   2:N.A.
 *                   3:Time Data
 *
 * PARAM 4 : ViPint32 range
 * OUT
 *            Set measurement range(code) value.
 *            
 *
 * PARAM 5 : ViPint32 value
 * OUT
 *            Return measurement value(code).
 *
 * PARAM 6 : ViPint32 status
 * OUT
 *            Return measurement status.
 *
 * PARAM 7 : ViPint32 channelNo
 * OUT
 *            Return measurement channel number.
 *
 * PARAM 8 : ViPint32 eod
 * OUT
 *            Return EOD 0:Not EOD   1:EOD
 *
 *
 *-----------------------------------------------------------------------------
 */
static

ViStatus _VI_FUNC asciiDataRead(ViSession vi, ViPInt32 dataKind,
                              ViPReal64 value, ViPInt32 status,
                              ViPInt32 channelNo, ViPInt32 eod )
{
/*--- measurment data length ---*/
#define MEAS_DATA_LEN   19
#define STATUS_CHAR_POSITION_BEGIN 0
#define STATUS_CHAR_POSITION_END 2
#define DATATYPE_CHAR_POSITION 4
#define CHANNEL_CHAR_POSITION 3
#define VALUE_POSITION 5

    ViStatus  errStatus = 0;
    ViInt32   act_len ;
    char      read_buf[MEAS_DATA_LEN+2] = {0};

    /* Read 1data + separator */
    errStatus = viRead(vi, (ViBuf)read_buf, MEAS_DATA_LEN, &act_len );


    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }


    /*--- Set Data Kind ---*/
   *dataKind = -1;
   switch (read_buf[DATATYPE_CHAR_POSITION]) {
   case 'I' : *dataKind = agb1500_DT_IM;
              break;
   case 'V' : *dataKind = agb1500_DT_VM;
              break;
   case 'i' : *dataKind = agb1500_DT_IS;
              break;
   case 'v' : *dataKind = agb1500_DT_VS;
              break;
   case 'T' : *dataKind = agb1500_DT_TM;
              break;
   case 'Z' : *dataKind = agb1500_DT_ZM;
			  break;
   case 'Y' : *dataKind = agb1500_DT_YM;
	          break;
   case 'C' : *dataKind = agb1500_DT_CM;
	          break;
   case 'D' : *dataKind = agb1500_DT_DM;
	          break;
   case 'Q' : *dataKind = agb1500_DT_QM;
	          break;
   case 'L' : *dataKind = agb1500_DT_LM;
	          break;
   case 'R' : *dataKind = agb1500_DT_RM;
	          break;
   case 'P' : *dataKind = agb1500_DT_PM;
	          break;
   case 'f' : *dataKind = agb1500_DT_FS;
	          break;
   case 'X' : *dataKind = agb1500_DT_X;
	          break;
   case 'z' : *dataKind = agb1500_DT_INV;
              break;
   default  : return( agb1500_MEAS_DATA_INCONSISTENCY );
   }


    /*--- Set Value ---*/
    errStatus = sscanf( &read_buf[VALUE_POSITION], "%le",value );

    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }
            
    /*--- Set Status ---*/
     if ( status != NULL) {  
         char status_buf[4];
         int i;

         if ( *dataKind == agb1500_DT_IS || *dataKind == agb1500_DT_VS) {
             *status = 0;
         }
         else {
             for ( i = STATUS_CHAR_POSITION_BEGIN;i <= STATUS_CHAR_POSITION_END; i++ )
                 status_buf[i] = read_buf[i];
             status_buf[3] = '\0';
             errStatus = sscanf ( status_buf, "%d", status );
             *status = *status & ~0x80;
        }
        if ( errStatus < VI_SUCCESS) {
            return( errStatus );
        }
    }

    /*--- Set EOD ---*/
    *eod = ( read_buf[MEAS_DATA_LEN-1] == ',' ? 0 : 1 );

    /*--- Set Channel No. ---*/
    if ( channelNo != (ViInt32 *) NULL) {
        if ( read_buf[CHANNEL_CHAR_POSITION] == 'Z') {
            *channelNo = agb1500_CH_NOCH;
        }
        else {
            *channelNo = read_buf[CHANNEL_CHAR_POSITION] - 'A' + 1;
        }
    }
    /*--- EOD Processs ---*/
    if ( *eod != 0 ) {
        errStatus = viRead(vi, read_buf, MEAS_DATA_LEN, &act_len );
        if ( errStatus < VI_SUCCESS) {
            return( errStatus );
        }
    }
    return( VI_SUCCESS );
}  /* ----- end of function ----- */


/********************* Miscilious Functions *********************/

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_autoCal(ViSession vi, ViInt32 state)
/*****************************************************************************/
/*                                                                           */
/*      This function enables or disables the auto calibration function.     */
/*                                                                           */
/*      The parameter 'state' specifies the auto calibration mode ON or OFF. */
/*                                                                           */
/*      This function implements the following command:                      */
/*                                                                           */
/*      CM                                                                   */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*        state    Select 0 for auto calibration mode OFF.                   */
/*                 Select 1 for auto calibration mode ON.                    */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                Value    Description                  */
/*                 agb1500_FLAG_OFF      0       AUTO CALIBRATION OFF        */
/*                 agb1500_FLAG_ON       1       AUTO CALIBRATION ON         */
/*                                                                           */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{
    ViStatus errStatus = 0;
    struct    agb1500_globals    *thisPtr;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if (errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_autoCal" );


    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( state, agb1500_FLAG_OFF, agb1500_FLAG_ON, 
                           VI_ERROR_PARAMETER2);


    errStatus = viPrintf(vi,"CM %d\n", state );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_setAdc(ViSession vi, ViInt32 adc, 
                                 ViInt32 mode, ViInt32 value, 
                                 ViInt32 autozero)
/*****************************************************************************/
/*                                                                           */
/*      This function sets the A/D converter of SMU.                         */
/*                                                                           */
/*      The parameter 'adc' specifies the ADC type                           */
/*       (high-speed ADC or high-resolution ADC).                            */
/*                                                                           */
/*      The parameter 'mode' specifies the integration/averaging mode.       */
/*                                                                           */
/*      The parameter 'value' sets the integration time for the              */
/*      high-resolution ADC or the number of averaging samples for           */
/*      the high-speed ADC.                                                  */
/*                                                                           */
/*      The parameter 'autozero' sets the ADC zero function of the high      */
/*      resolution ADC.                                                      */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      AIT                                                                  */
/*      AZ                                                                   */
/*                                                                           */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*          adc    Select the A/D converter type                             */
/*                  (high-speed or high-resolution).                         */
/*                 Data Type:  ViInt32Input/Output:  IN                      */
/*                 Values:                                                   */
/*                 Name                 Value     Description                */
/*                 agb1500_HSPEED_ADC     0     HIGH-SPEED ADC               */
/*                 agb1500_HRESOLN_ADC    1    HIGH-RESOLUTION ADC           */
/*                                                                           */
/*         mode    Select the integration/averaging mode.                    */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                 Value     Description                */
/*                 agb1500_INTEG_AUTO     0     AUTO                         */
/*                 agb1500_INTEG_MANUAL   1     MANUAL                       */
/*                 agb1500_INTEG_PLC      2     PLC                          */
/*                                                                           */
/*        value    Coefficient for a reference value to set the              */
/*                 integration time or the number of averaging samples.      */
/*                 The reference value depends on the adc and mode settings  */
/*                 as shown below:                                           */
/*                                                                           */
/*                 For high-resolution ADC: initial value for AUTO,          */
/*                 80 usec for MANUAL, and 1/power line frequency for PLC.   */
/*                                                                           */
/*                 For high-speed ADC: initial value for AUTO, 1 sample for  */
/*                 MANUAL, and 128 samples for PLC.                          */
/*                                                                           */
/*                 The initial value is the value automatically defined by   */
/*                    the instrument, and you cannot change.                 */
/*                                                                           */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                        Value                         */
/*                 agb1500_SETADC_VALUE_MIN     1                            */
/*                 agb1500_SETADC_VALUE_MAX     1023                         */
/*                                                                           */
/*        mode     Select 0 for ADC zero function OFF.                       */
/*                 Select 1 for ADC zero function ON.                        */
/*                 This parameter is available only for the                  */
/*                 high-resolution ADC.                                      */
/*                 For the high-speed ADC, this parameter setting is ignored.*/
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name               Value     Description                  */
/*                 agb1500_FLAG_OFF     0     ADC ZERO OFF                   */
/*                 agb1500_FLAG_ON      1     ADC ZERO ON                    */
/*                                                                           */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }
    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_setAdc" );


    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( adc, 
                agb1500_HSPEED_ADC, agb1500_HRESOLN_ADC, 
                VI_ERROR_PARAMETER2);

    agb1500_CHK_LONG_RANGE( mode, 
                agb1500_INTEG_AUTO, agb1500_INTEG_PLC, 
                VI_ERROR_PARAMETER3);

    agb1500_CHK_LONG_RANGE( value, 
                agb1500_SETADC_VALUE_MIN, agb1500_SETADC_VALUE_MAX, 
                VI_ERROR_PARAMETER4);

    if ( adc == agb1500_HRESOLN_ADC ) {
        agb1500_CHK_LONG_RANGE( autozero, 
                agb1500_FLAG_OFF, agb1500_FLAG_ON, 
                VI_ERROR_PARAMETER5);
    }


    if ( value == 0 ) {
        errStatus = viPrintf(vi,"AIT %d,%d\n", adc, mode);
    } 
    else {
        errStatus = viPrintf(vi,"AIT %d,%d,%d\n", adc, mode, value);
    }
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    if ( adc == agb1500_HRESOLN_ADC ) {
        errStatus = viPrintf(vi,"AZ %d\n", autozero );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_stopMode(ViSession vi, ViInt32 stop,
                                    ViInt32 last_mode)
/*****************************************************************************/
/*                                                                           */
/*      This function enables or disables the automatic abort function,      */
/*      and specifies the source output value after sweep measurement.       */
/*      This function is available for the IV and CV staircase sweep,        */
/*      IV pulsed sweep, IV staircase sweep with pulsed bias,                */
/*      multi channel IV sweep, and IV sampling measurements simultaneously. */                       
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      WM                                                                   */
/*      WMDCV                                                                */
/*      MSC                                                                  */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*          stop   Enables or disables the automatic abort function.         */
/*                 This function automatically stops sweep if a source       */
/*                 channel reaches its compliance, a measurement value       */
/*                 exceeds the specified measurement range, or an SMU        */
/*                 oscillates.                                               */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                Value     Description                 */
/*                 agb1500_FLAG_OFF     0     DISABLES FUNCTION              */
/*                 agb1500_FLAG_ON      1     ENABLES FUNCTION               */
/*                                                                           */
/*     last_mode   Sweep source output value after normal sweep end.         */
/*                 If the sweep measurement is stopped by the automatic abort*/
/*                 function, power compliance, or AB command, the sweep      */
/*                 source applies the sweep start value. After the pulsed    */
/*                 sweep measurement, the pulse sweep source always applies  */
/*                 the pulse base value.                                     */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                  Value     Description               */
/*                 agb1500_LAST_START     1     SWEEP START VALUE            */
/*                 agb1500_LAST_STOP      2     SWEEP STOP VALUE             */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
#define STM_MASK 0x27

    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
    

    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_stopMode" );


    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( stop, agb1500_FLAG_OFF, agb1500_FLAG_ON, 
                           VI_ERROR_PARAMETER2);

    agb1500_CHK_LONG_RANGE( last_mode, agb1500_LAST_START, agb1500_LAST_STOP, 
                           VI_ERROR_PARAMETER3);


    /*--- Set Command ---*/
    { 
    int abort = ((stop == agb1500_FLAG_OFF)?1:2);

    errStatus = viPrintf(vi,"WM %d,%d\n", abort, last_mode );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }
    errStatus = viPrintf(vi,"WMDCV %d,%d\n", abort, last_mode );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }
	errStatus = viPrintf(vi,"MSC %d,%d\n", abort, last_mode );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }
	}
    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_abortMeasure(ViSession vi)
/*****************************************************************************/
/*                                                                           */
/*      This function aborts the present operation and subsequent command    */
/*      execution.                                                           */
/*                                                                           */
/*      This function stops the operation now in progress, such as the       */
/*      measurement execution, source setup changing, and so on.             */
/*      But this function does not change the present condition.             */
/*      For example, if the B1500 just keeps to force the dc bias,           */
/*      this function does not stop the dc bias output.                      */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      AB                                                                   */
/*                                                                           */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct    agb1500_globals    *thisPtr;


    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_abortMeasure" );



    errStatus = viPrintf(vi,"AB\n" );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_resetTimestamp(ViSession vi)
/*****************************************************************************/
/*                                                                           */
/*      This function clears the count of the timer (time stamp).            */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      TSR                                                                  */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{
    ViStatus errStatus = 0 ;
    struct    agb1500_globals    *thisPtr;

    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if (errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_resetTimestamp" );



    errStatus = viPrintf(vi,"TSR\n" );
    if (errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/********************* Measurement Unit Setup Functions *********************/

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_setSwitch(ViSession vi, ViInt32 channel, 
                                    ViInt32 state)
/*****************************************************************************/
/*                                                                           */
/*      This function sets the output switch of the specified channel.       */
/*                                                                           */
/*      The parameter 'channel' specifies the channel.                       */
/*                                                                           */
/*      The parameter 'state' specifies the output switch status ON or OFF.  */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      CN                                                                   */
/*      CL                                                                   */
/*                                                                           */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      channel    Channel number of the channel.  Same as the slot number   */
/*                 for the SMU or CMU.                                       */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_ALL   0      All channel                       */
/*                 agb1500_CH_CMU  -1      CMU channel                       */
/*                 agb1500_CH_1     1      Channel 1                         */
/*                 agb1500_CH_2     2      Channel 2                         */
/*                 agb1500_CH_3     3      Channel 3                         */
/*                 agb1500_CH_4     4      Channel 4                         */
/*                 agb1500_CH_5     5      Channel 5                         */
/*                 agb1500_CH_6     6      Channel 6                         */
/*                 agb1500_CH_7     7      Channel 7                         */
/*                 agb1500_CH_8     8      Channel 8                         */
/*				   agb1500_CH_9		9	   Channel 9					     */
/*                 agb1500_CH_10   10      Channel 10                        */
/*                                                                           */
/*         state   Select 0 for the output switch OFF.                       */
/*                 Select 1 for the output switch ON.                        */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value   Description                     */
/*                 agb1500_FLAG_OFF   0     OUTPUT SWITCH OFF                */
/*                 agb1500_FLAG_ON    1     OUTPUT SWITCH ON                 */
/*                                                                           */
/*                                                                           */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct    agb1500_globals    *thisPtr;
    ViChar cmd_buf[256];
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_setSwitch" );


    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( channel, agb1500_CH_CMU, agb1500_CH_10,
						VI_ERROR_PARAMETER2 );
	if( channel == agb1500_CH_CMU ){
		if( (channel = agb1500_RTN_CMU_UNT) == agb1500_NO_CMU ){
			return agb1500_NO_CMU_UNT;
		}
	}

    agb1500_CHK_LONG_RANGE( state, agb1500_FLAG_OFF, agb1500_FLAG_ON, 
                           VI_ERROR_PARAMETER3);

    /*--- Set Command ---*/
    if ( state == agb1500_FLAG_ON )
        if ( channel == agb1500_CH_ALL )
            sprintf( cmd_buf, "CN" );
        else 
            sprintf( cmd_buf, "CN %d", channel );
    else
        if ( channel == agb1500_CH_ALL )
            sprintf( cmd_buf, "CL" );
        else 
            sprintf( cmd_buf, "CL %d", channel );
        

    errStatus = viPrintf(vi,"%s\n", cmd_buf );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_setFilter(ViSession vi, ViInt32 channel, 
                                    ViInt32 state)
/*****************************************************************************/
/*                                                                           */
/*      This function sets the output filter of the specified SMU.           */
/*                                                                           */
/*      The parameter 'channel' specifies the SMU.                           */
/*                                                                           */
/*      The parameter 'stateE specifies the output filter status            */
/*      ON or OFF.                                                           */
/*                                                                           */
/*      This function implements the following command:                      */
/*                                                                           */
/*      FL                                                                   */
/*                                                                           */
/*                                                                           */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      channel    Channel number of the channel.  Same as the slot number   */
/*                 for the SMU.                                              */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_ALL    0     All channel                       */
/*                 agb1500_CH_1      1     Channel 1                         */
/*                 agb1500_CH_2      2     Channel 2                         */
/*                 agb1500_CH_3      3     Channel 3                         */
/*                 agb1500_CH_4      4     Channel 4                         */
/*                 agb1500_CH_5      5     Channel 5                         */
/*                 agb1500_CH_6      6     Channel 6                         */
/*                 agb1500_CH_7      7     Channel 7                         */
/*                 agb1500_CH_8      8     Channel 8                         */
/*                 agb1500_CH_9		 9 	   Channel 9                         */
/*                 agb1500_CH_10    10     Channel 10                        */
/*                                                                           */
/*         state   Select 0 for output filter OFF.                           */
/*                 Select 1 for output filter ON.                            */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value   Description                     */
/*                 agb1500_FLAG_OFF   0     FILTER OFF                       */
/*                 agb1500_FLAG_ON    1     FILTER ON                        */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct    agb1500_globals    *thisPtr;
    ViChar cmd_buf[256];
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_setFilter" );


    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( channel, agb1500_CH_ALL, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);

    agb1500_CHK_LONG_RANGE( state, agb1500_FLAG_OFF, agb1500_FLAG_ON, 
                           VI_ERROR_PARAMETER3);

    /*--- Set Command ---*/
    if ( channel == agb1500_CH_ALL ) {
        sprintf( cmd_buf, "FL %d", state );
    }
    else {
        sprintf( cmd_buf, "FL %d,%d", state, channel );
    }


    errStatus = viPrintf(vi,"%s\n", cmd_buf );
    if (errStatus < VI_SUCCESS) {
       agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_setSerRes(ViSession vi, ViInt32 channel, 
                                          ViInt32 state)
/*****************************************************************************/
/*                                                                           */
/*      This function sets the series resistor of the specified SMU.         */
/*                                                                           */
/*      The parameter 'channel' specifies the SMU.                          */
/*                                                                           */
/*      The parameter 'state' specifies the series resistor status          */
/*      ON or OFF.                                                           */
/*                                                                           */
/*      This function implements the following command:                      */
/*                                                                           */
/*      SSR                                                                  */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      channel    Channel number of the channel.  Same as the slot number   */
/*                 for the SMU.                                              */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_ALL    0     All channel                       */
/*                 agb1500_CH_1      1     Channel 1                         */
/*                 agb1500_CH_2      2     Channel 2                         */
/*                 agb1500_CH_3      3     Channel 3                         */
/*                 agb1500_CH_4      4     Channel 4                         */
/*                 agb1500_CH_5      5     Channel 5                         */
/*                 agb1500_CH_6      6     Channel 6                         */
/*                 agb1500_CH_7      7     Channel 7                         */
/*                 agb1500_CH_8      8     Channel 8                         */
/*                 agb1500_CH_9      9     Channel 9                         */
/*                 agb1500_CH_10    10     Channel 10                        */
/*                                                                           */
/*         state   Select 0 for the SMU series resistor OFF.                 */
/*                 Select 1 for the SMU series resistor ON.                  */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value   Description                     */
/*                 agb1500_FLAG_OFF   0     SERIES RESISTOR OFF              */
/*                 agb1500_FLAG_ON    1     SERIES RESISTOR ON               */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_setSerRes" );


    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( channel, agb1500_CH_ALL, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);

    agb1500_CHK_LONG_RANGE( state, agb1500_FLAG_OFF, agb1500_FLAG_ON, 
                           VI_ERROR_PARAMETER3);



    if ( channel != agb1500_CH_ALL) {
        errStatus = viPrintf(vi,"SSR %d,%d\n", channel, state );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }
    else {
        int i;
        for (i=0;i<agb1500_MAX_UNIT;i++) {
            if ((thisPtr->UNT[i]!= 0)&&(thisPtr->UNT[i]!=agb1500_CMU_MODEL_NO)
				&&(thisPtr->UNT[i]!=agb1500_ASU_MODEL_NO)) {
                errStatus = viPrintf(vi,"SSR %d,%d\n", i+1, state );
                if ( errStatus < VI_SUCCESS) {
                    agb1500_LOG_STATUS( vi, thisPtr, errStatus );
                }
            }
        }
    }
    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_setAdcType(ViSession vi, ViInt32 channel, 
                                          ViInt32 adc)
/*****************************************************************************/
/*                                                                           */
/*      This function selects the ADC type for the measurement channel.      */
/*                                                                           */
/*      The parameter 'channel' specifies the SMU channel.                   */
/*                                                                           */
/*      The parameter 'adc' specifies the ADC type, high-speed ADC or        */
/*      high-resolution ADC.                                                 */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      AAD                                                                  */
/*                                                                           */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      channel    Channel number of the channel.  Same as the slot number   */
/*                 for the SMU.                                              */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_ALL    0     All channel                       */
/*                 agb1500_CH_1      1     Channel 1                         */
/*                 agb1500_CH_2      2     Channel 2                         */
/*                 agb1500_CH_3      3     Channel 3                         */
/*                 agb1500_CH_4      4     Channel 4                         */
/*                 agb1500_CH_5      5     Channel 5                         */
/*                 agb1500_CH_6      6     Channel 6                         */
/*                 agb1500_CH_7      7     Channel 7                         */
/*                 agb1500_CH_8      8     Channel 8                         */
/*                 agb1500_CH_9		 9	   Channel 9					     */
/*                 agb1500_CH_10    10     Channel 10                        */
/*                                                                           */
/*         state   Select 0 for the SMU series resistor OFF.                 */
/*                 Select 1 for the SMU series resistor ON.                  */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value   Description                     */
/*                 agb1500_FLAG_OFF   0     SERIES RESISTOR OFF              */
/*                 agb1500_FLAG_ON    1     SERIES RESISTOR ON               */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_setAdcType" );


    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( channel, agb1500_CH_ALL, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);

    agb1500_CHK_LONG_RANGE( adc, agb1500_HSPEED_ADC, agb1500_HRESOLN_ADC, 
                           VI_ERROR_PARAMETER3);



    if ( channel != agb1500_CH_ALL) {
        errStatus = viPrintf(vi,"AAD %d,%d\n", channel, adc );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }
    else {
        int i;
        for (i=0;i<agb1500_MAX_UNIT;i++) {
            if ((thisPtr->UNT[i]!= 0)&&(thisPtr->UNT[i]!=agb1500_CMU_MODEL_NO)) {
                errStatus = viPrintf(vi,"AAD %d,%d\n", i+1, adc );
                if ( errStatus < VI_SUCCESS) {
                    agb1500_LOG_STATUS( vi, thisPtr, errStatus );
                }
            }
        }
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/********************* Source Setup Functions ********************************/

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_force(ViSession vi, ViInt32 channel,
                               ViInt32 mode, ViReal64 range, ViReal64 value,
                               ViReal64 comp, ViInt32 polarity)
/*****************************************************************************/
/*                                                                           */
/*      This function specifies the dc current source or dc voltage source,  */
/*      and forces the output immediately.  To stop the output, use the      */
/*      agb1500_zeroOutput function with 0 (zero) output.                    */
/*                                                                           */
/*      The parameter 'channel' specifies the source channel.                */
/*      The parameter 'mode' selects current force mode or voltage           */
/*      force mode.                                                          */
/*      The parameter 'range' selects the output ranging type.               */
/*      The parameter 'value' specifies the output current or voltage        */
/*      value.                                                               */
/*      The parameter 'comp' specifies the compliance value.                 */
/*      The parameter 'polarity' sets the compliance polarity.               */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      DI                                                                   */
/*      DV                                                                   */
/*                                                                           */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      channel    Channel number of the channel.  Same as the slot number   */
/*                 for the SMU.                                              */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_1      1     Channel 1                         */
/*                 agb1500_CH_2      2     Channel 2                         */
/*                 agb1500_CH_3      3     Channel 3                         */
/*                 agb1500_CH_4      4     Channel 4                         */
/*                 agb1500_CH_5      5     Channel 5                         */
/*                 agb1500_CH_6      6     Channel 6                         */
/*                 agb1500_CH_7      7     Channel 7                         */
/*                 agb1500_CH_8      8     Channel 8                         */
/*                 agb1500_CH_9		 9     Channel 9                         */
/*                 agb1500_CH_10    10     Channel 10                        */
/*                                                                           */
/*         mode    Select 1 for current output.                              */
/*                 Select 2 for voltage output.                              */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value    Description                    */
/*                 agb1500_IF_MODE    1      CURRENT OUTPUT                  */
/*                 agb1500_VF_MODE    2      VOLTAGE OUTPUT                  */
/*                                                                           */
/*        range    Output ranging type.                                      */
/*                 For current output: 0, 1E-12 to 1.0                        */
/*                 For voltage output: 0, 0.5 to 200.0                       */
/*                 where,                                                    */
/*                 For auto ranging: Enter 0 (zero).                         */
/*                 For limited auto ranging: Enter positive value.           */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*       value     Output current or voltage value.                          */
/*                 For current output: -1.0 A to 1.0 A                       */
/*                 For voltage output: -200.0 V to 200.0 V                   */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name               Value                                  */
/*                 agb1500_SMUV_MIN    -200.0                                */
/*                 agb1500_SMUV_MAX    200.0                                 */
/*                                                                           */
/*         comp    Compliance value.                                         */
/*                 If the input comp value is out of the following range,    */
/*                 comp parameter and polarity parameter are ignored.        */
/*                 For voltage compliance: -200 V to 200 V                   */
/*                 For current compliance: -1.0 A to 1.0 A                   */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name               Value                                  */
/*                 agb1500_SMUV_MIN    -200.0                                */
/*                 agb1500_SMUV_MAX    200.0                                 */
/*                                                                           */
/*     polarity    Compliance polarity.                                      */
/*                 Select 0 for setting the same polarity as value           */
/*                 you entered.                                              */
/*                 Select 1 for setting the same polarity as comp            */
/*                 you entered.                                              */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                 Value    Description                 */
/*                 agb1500_POL_AUTO      0      AUTO                         */
/*                 agb1500_POL_MANUAL    1      MANUAL                       */
/*                                                                           */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0;
    struct agb1500_globals *thisPtr;
    ViInt16 comp_ignore;
    ViChar cmd_buf[256];

    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);

    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, 0, errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_force" );


    /* Check Channel & Set Compliance */
    if ( (channel < agb1500_CH_1) || (agb1500_CH_10 < channel) ) {
        comp = COMP_IGNORE_VAL ;
    }

    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE(channel, agb1500_CH_1, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);

    agb1500_CHK_LONG_RANGE(mode, agb1500_IF_MODE, agb1500_VF_MODE, 
                           VI_ERROR_PARAMETER3);

    agb1500_CHK_REAL_RANGE(range, agb1500_RANGE_MIN, agb1500_RANGE_MAX, 
                           VI_ERROR_PARAMETER4);

    agb1500_CHK_REAL_RANGE(value, agb1500_SMUV_MIN, agb1500_SMUV_MAX, 
                           VI_ERROR_PARAMETER5);
 
    if (agb1500_chk_real_range(thisPtr, comp, 
                               agb1500_SMUV_MIN, agb1500_SMUV_MAX)) {
        comp_ignore = 1;
    }
    else {
        comp_ignore = 0;
        agb1500_CHK_LONG_RANGE(polarity,agb1500_POL_AUTO,agb1500_POL_MANUAL,
                               VI_ERROR_PARAMETER7);
    }

    /* Send Command */
    if ( mode == agb1500_IF_MODE ) {
        if ( comp_ignore == 1 ) {
            sprintf( cmd_buf, "DI %d,%d,%e",channel,abs(iRangeId(channel,thisPtr->UNT[channel-1],range)),value);
        }
        else {
            sprintf( cmd_buf,"DI %d,%d,%e,%e,%d",
                                   channel,abs(iRangeId(channel,thisPtr->UNT[channel-1],range)),value,comp,polarity);
        }
    }
    else {
        if ( comp_ignore == 1 ) {
            sprintf( cmd_buf,"DV %d,%d,%e",
                                    channel,abs(vRangeId(channel,thisPtr->UNT[channel-1],range)),value);
        }
        else {
            sprintf( cmd_buf,"DV %d,%d,%e,%e,%d",
                                   channel,abs(vRangeId(channel,thisPtr->UNT[channel-1],range)),
								   value,comp,polarity);
        }
    }
    errStatus = viPrintf(vi,"%s\n", cmd_buf );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_zeroOutput(ViSession vi, ViInt32 channel)
/*****************************************************************************/
/*                                                                           */
/*      This function stores the source setup of the specified channels      */
/*      into the internal memory, and sets the channel output to 0 V.        */
/*      The source setup can be recovered by the agb1500_recoverOutput       */
/*      function.                                                            */
/*                                                                           */
/*      The parameter 'channel' specifies the channel.                       */
/*                                                                           */
/*      This function implements the following function:                     */
/*                                                                           */
/*       DZ                                                                  */
/*                                                                           */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      channel    Channel number of the channel.  Same as the slot number   */
/*                 for the SMU.                                              */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_ALL   0      All channel                       */
/*                 agb1500_CH_CMU  -1      CMU channel                       */
/*                 agb1500_CH_1     1      Channel 1                         */
/*                 agb1500_CH_2     2      Channel 2                         */
/*                 agb1500_CH_3     3      Channel 3                         */
/*                 agb1500_CH_4     4      Channel 4                         */
/*                 agb1500_CH_5     5      Channel 5                         */
/*                 agb1500_CH_6     6      Channel 6                         */
/*                 agb1500_CH_7     7      Channel 7                         */
/*                 agb1500_CH_8     8      Channel 8                         */
/*                 agb1500_CH_9     9      Channel 9                         */
/*                 agb1500_CH_10   10      Channel 10                        */
/*                                                                           */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct    agb1500_globals    *thisPtr;
    ViChar cmd_buf[256];
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_zeroOutput" );


    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( channel, agb1500_CH_CMU, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);
	if( channel == agb1500_CH_CMU ){
		if( (channel = agb1500_RTN_CMU_UNT) == agb1500_NO_CMU ){
			return agb1500_NO_CMU_UNT;
		}
	}

    /*--- Set Command ---*/
    if ( channel == agb1500_CH_ALL ) {
        sprintf( cmd_buf, "DZ" );
    }
    else {
        sprintf( cmd_buf, "DZ %d", channel );
    }


    errStatus = viPrintf(vi,"%s\n", cmd_buf );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_recoverOutput(ViSession vi, ViInt32 channel)
/*****************************************************************************/
/*                                                                           */
/*      This function recovers the source setup that is stored by            */
/*      the agb1500_zeroOutput function, and clears the setup data           */
/*      stored in the internal memory.                                       */
/*                                                                           */
/*      The  parameter  'channel' specifies the channel.                     */
/*                                                                           */
/*      This function implements the following command:                      */
/*                                                                           */
/*      RZ                                                                   */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      channel    Channel number of the channel.  Same as the slot number   */
/*                 for the SMU.                                              */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_ALL   0      All channel                       */
/*                 agb1500_CH_CMU  -1      CMU channel                       */
/*                 agb1500_CH_1     1      Channel 1                         */
/*                 agb1500_CH_2     2      Channel 2                         */
/*                 agb1500_CH_3     3      Channel 3                         */
/*                 agb1500_CH_4     4      Channel 4                         */
/*                 agb1500_CH_5     5      Channel 5                         */
/*                 agb1500_CH_6     6      Channel 6                         */
/*                 agb1500_CH_7     7      Channel 7                         */
/*                 agb1500_CH_8     8      Channel 8                         */
/*                 agb1500_CH_9     9      Channel 9                         */
/*                 agb1500_CH_10   10      Channel 10                        */
/*                                                                           */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct    agb1500_globals    *thisPtr;
    ViChar cmd_buf[256];
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_recoverOutput" );


    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( channel, agb1500_CH_CMU, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);
	if( channel == agb1500_CH_CMU ){
		if( (channel = agb1500_RTN_CMU_UNT) == agb1500_NO_CMU ){
			return agb1500_NO_CMU_UNT;
		}
	}

    /*--- Set Command ---*/
    if ( channel == agb1500_CH_ALL ) {
        sprintf( cmd_buf, "RZ" );
    }
    else {
        sprintf( cmd_buf, "RZ %d", channel );
    }


    errStatus = viPrintf(vi,"%s\n", cmd_buf );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_setIv(ViSession vi, 
                               ViInt32 channel, ViInt32 mode, ViReal64 range,
                               ViReal64 start, ViReal64 stop, ViInt32 point,
                               ViReal64 hold, ViReal64 delay, ViReal64 s_delay,
                               ViReal64 comp, ViReal64 p_comp )
/*****************************************************************************/
/*                                                                           */
/*      This function sets the primary sweep source for the staircase sweep, */
/*      staircase sweep with pulsed bias, and multi channel sweep            */
/*      measurements.                                                        */
/*                                                                           */
/*      To use the synchronous sweep source, execute the agb1500_setSweepSync*/
/*      function.                                                            */
/*                                                                           */
/*      To perform the staircase sweep measurements, execute the             */
/*      agb1500_sweepIv or agb1500_sweepMiv function.                        */
/*      The agb1500_sweepMiv function allows to use multiple measurement     */
/*      channels.                                                            */
/*                                                                           */
/*      To perform the staircase sweep with pulsed bias measurements,        */
/*      execute the agb1500_setPbias function to set the output pulse        */
/*      synchronized with the sweep output, and execute the                  */
/*      agb1500_sweepPbias function to start measurements.                   */
/*                                                                           */
/*      To perform the multi channel sweep measurements, execute the         */
/*      agb1500_setNthSweep function to set the synchronous sweep sources,   */
/*      and execute the agb1500_msweepIv or agb1500_msweepMiv function       */
/*      to start measurements. The agb1500_msweepMiv function allows to use  */
/*      multiple measurement channels.                                       */
/*                                                                           */
/*      Note:                                                                */
/*                                                                           */
/*      Up to 7 synchronous sweep sources can be set by executing the        */
/*      agb1500_setNthSweep function for each channel.                       */
/*                                                                           */
/*      The agb1500_setSweepSync function is not available for the multi     */
/*      channel sweep measurements.                                          */
/*                                                                           */
/*      The hold, delay, and s_delay parameters are not available for the    */
/*      staircase sweep with pulsed bias measurements.                       */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      WV                                                                   */
/*      WI                                                                   */
/*      WT                                                                   */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      channel    Channel number of the channel.  Same as the slot number   */
/*                 for the SMU.                                              */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_1      1     Channel 1                         */
/*                 agb1500_CH_2      2     Channel 2                         */
/*                 agb1500_CH_3      3     Channel 3                         */
/*                 agb1500_CH_4      4     Channel 4                         */
/*                 agb1500_CH_5      5     Channel 5                         */
/*                 agb1500_CH_6      6     Channel 6                         */
/*                 agb1500_CH_7      7     Channel 7                         */
/*                 agb1500_CH_8      8     Channel 8                         */
/*                 agb1500_CH_9      9     Channel 9                         */
/*                 agb1500_CH_10    10     Channel 10                        */
/*                                                                           */
/*         mode    Sweep source output mode.                                 */
/*                 For voltage output: Enter positive value.                 */
/*                 For current output: Enter negative value.                 */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                   Value   Description                */
/*                 agb1500_SWP_VF_SGLLIN   1     SINGLE LINEAR V             */
/*                 agb1500_SWP_VF_SGLLOG   2     SINGLE LOG V                */
/*                 agb1500_SWP_VF_DBLLIN   3     DOUBLE LINEAR V             */
/*                 agb1500_SWP_VF_DBLLOG   4     DOUBLE LOG V                */
/*                 agb1500_SWP_IF_SGLLIN   -1    SINGLE LINEAR I             */
/*                 agb1500_SWP_IF_SGLLOG   -2    SINGLE LOG I                */
/*                 agb1500_SWP_IF_DBLLIN   -3    DOUBLE LINEAR I             */
/*                 agb1500_SWP_IF_DBLLOG   -4    DOUBLE LOG I                */
/*                                                                           */
/*        range   Output ranging type.                                       */
/*                For current output: 0, 1E-12 to 1.0                         */
/*                For voltage output: 0, 0.5 to 200.0                        */
/*                where,                                                     */
/*                For auto ranging: Enter 0 (zero).                          */
/*                For limited auto ranging: Enter positive value.            */
/*                Data Type:  ViReal64                                       */
/*                Input/Output:  IN                                          */
/*                                                                           */
/*        start    Sweep start value (in A or V).                            */
/*                 For current sweep: -1.0 A to 1.0 A                        */
/*                 For voltage sweep: -200.0 V to 200.0 V                    */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value                                   */
/*                 agb1500_SMUV_MIN   -200.0                                 */
/*                 agb1500_SMUV_MAX   200.0                                  */
/*                                                                           */
/*          stop   Sweep stop value (in A or V).                             */
/*                 For current sweep: -1.0 A to 1.0 A                        */
/*                 For voltage sweep: -200.0 V to 200.0 V                    */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value                                   */
/*                 agb1500_SMUV_MIN   -200.0                                 */
/*                 agb1500_SMUV_MAX   200.0                                  */
/*                                                                           */
/*         point   Number of sweep steps.                                    */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                   Value                              */
/*                 agb1500_SWP_POINT_MIN   1                                 */
/*                 agb1500_SWP_POINT_MAX   1001                              */
/*                                                                           */
/*         hold   Hold time (in second).                                     */
/*                Time since starting the sweep measurement until starting   */
/*                the delay time for the first sweep step.                   */
/*                Data Type:  ViReal64                                       */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                Name                  Value                                */
/*                agb1500_SWP_HOLD_MIN   0.00                                */
/*                agb1500_SWP_HOLD_MAX   655.35                              */
/*                                                                           */
/*        delay   Delay time (in second).                                    */
/*                Time since starting to force a step output value until     */
/*                starting a step measurement.                               */
/*                Data Type:  ViReal64                                       */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                Name                   Value                               */
/*                agb1500_SWP_DELAY_MIN   0.0                                */
/*                agb1500_SWP_DELAY_MAX   65.535                             */
/*                                                                           */
/*      s_delay   Step delay time (in second).                               */
/*                Time since starting a step measurement until starting      */
/*                the delay time for the next sweep step.                    */
/*                Data Type:  ViReal64                                       */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                Name                    Value                              */
/*                agb1500_SWP_SDELAY_MIN   0.0                               */
/*                agb1500_SWP_SDELAY_MAX   1.0                               */
/*                                                                           */
/*         comp   Compliance (in V or A).                                    */
/*                If the comp value is out of the following range,           */
/*                the comp and p_comp parameters are ignored.                */
/*                Voltage compliance (for current sweep): -200.0 V to 200.0 V*/
/*                Current compliance (for voltage sweep): -1.0 A to 1.0 A    */
/*                Data Type:  ViReal64                                       */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                Name               Value                                   */
/*                agb1500_SMUV_MIN    -200.0                                 */
/*                agb1500_SMUV_MAX    200.0                                  */
/*                                                                           */
/*        p_comp   Power compliance (in VA).  If the p_comp value is         */
/*                 out of the following range, the p_comp value is ignored.  */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                   Value                              */
/*                 agb1500_SMU_POWER_MIN   1.0E-3                            */
/*                 agb1500_SMU_POWER_MAX   20.0                              */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct    agb1500_globals    *thisPtr;
    char    command[256] ;

    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_setIv" );


    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( channel, agb1500_CH_1, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);

    if (!((abs(mode) >= agb1500_SWP_VF_SGLLIN)&&
       (abs(mode) <= agb1500_SWP_VF_DBLLOG)))
        agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER3);

    if ( fabs(range) > agb1500_AUTOR_BORDER ) 
        agb1500_CHK_REAL_RANGE( range, agb1500_RANGE_MIN, agb1500_RANGE_MAX, 
                             VI_ERROR_PARAMETER4);
    
    agb1500_CHK_REAL_RANGE( start, agb1500_SMUV_MIN, agb1500_SMUV_MAX, 
                           VI_ERROR_PARAMETER5);

    agb1500_CHK_REAL_RANGE( stop, agb1500_SMUV_MIN, agb1500_SMUV_MAX, 
                           VI_ERROR_PARAMETER6);

    agb1500_CHK_LONG_RANGE( point, agb1500_SWP_POINT_MIN, agb1500_SWP_POINT_MAX, 
                           VI_ERROR_PARAMETER7);

    agb1500_CHK_REAL_RANGE( hold, agb1500_SWP_HOLD_MIN, agb1500_SWP_HOLD_MAX, 
                           VI_ERROR_PARAMETER8);

    agb1500_CHK_REAL_RANGE( delay, agb1500_SWP_DELAY_MIN, agb1500_SWP_DELAY_MAX, 
                           agb1500_INSTR_ERROR_PARAMETER9);

    agb1500_CHK_REAL_RANGE( s_delay, agb1500_SWP_SDELAY_MIN, agb1500_SWP_SDELAY_MAX, 
                           agb1500_INSTR_ERROR_PARAMETER10);

    /*--- Set Command ---*/
    if ( mode > 0 ) {        /*--- VOLTAGE ---*/
        if ( !(agb1500_SMUV_MIN <= comp  &&  comp <= agb1500_SMUV_MAX) ) 
            sprintf( command, "WV %d,%d,%d,%E,%E,%d", 
                channel, abs(mode), abs(vRangeId(channel,thisPtr->UNT[channel-1],range)), start, stop, point );
        
        else if ( !(agb1500_SMU_POWER_MIN <= p_comp  &&   p_comp <= agb1500_SMU_POWER_MAX) )
            sprintf( command, "WV %d,%d,%d,%E,%E,%d,%E", 
                channel, abs(mode), abs(vRangeId(channel,thisPtr->UNT[channel-1],range)), 
				start, stop, point, comp );
        
        else
            sprintf( command, "WV %d,%d,%d,%E,%E,%d,%E,%E", 
                channel, abs(mode), abs(vRangeId(channel,thisPtr->UNT[channel-1],range)), start, stop, point, comp, p_comp );
    }
    else {                    /*--- CURRENT ---*/
        if ( !(agb1500_SMUV_MIN <= comp  &&  comp <= agb1500_SMUV_MAX) ) 
            sprintf( command, "WI %d,%d,%d,%E,%E,%d", 
                channel, abs(mode), abs(iRangeId(channel,thisPtr->UNT[channel-1],range)), start, stop, point );
        
        else if ( !(agb1500_SMU_POWER_MIN <= p_comp  &&   p_comp <= agb1500_SMU_POWER_MAX) )
            sprintf( command, "WI %d,%d,%d,%E,%E,%d,%E", 
                channel, abs(mode), abs(iRangeId(channel,thisPtr->UNT[channel-1],range)), start, stop, point, comp );
        
        else
            sprintf( command, "WI %d,%d,%d,%E,%E,%d,%E,%E", 
                channel, abs(mode), abs(iRangeId(channel,thisPtr->UNT[channel-1],range)), start, stop, point, comp, p_comp );
    }


    errStatus = viPrintf(vi,"%s\n", command );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    sprintf( command, "WT %E,%E,%E", hold, delay, s_delay );

    errStatus = viPrintf(vi,"%s\n", command );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }
    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_setPbias(ViSession vi, ViInt32 channel, 
                                  ViInt32 mode, ViReal64 range, 
                                  ViReal64 base, ViReal64 peak,
                                  ViReal64 width, ViReal64 period, 
                                  ViReal64 hold, ViReal64 comp )
/*****************************************************************************/
/*                                                                           */
/*      This function sets the pulse source for the pulsed spot and          */
/*      staircase sweep with pulsed bias measurements                        */
/*                                                                           */
/*      To perform the pulsed spot measurements, execute the                 */
/*      agb1500_measureP function.                                           */
/*                                                                           */
/*      To perform the staircase sweep with pulsed bias measurements,        */
/*      execute the agb1500_setIv function to set the staircase sweep source,*/
/*      and execute the agb1500_sweepPbias function to start measurements.   */
/*      The output pulse synchronizes with the sweep source output.          */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      PV                                                                   */
/*      PI                                                                   */
/*      PT                                                                   */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      channel    Channel number of the channel.  Same as the slot number   */
/*                 for the SMU.                                              */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_1      1     Channel 1                         */
/*                 agb1500_CH_2      2     Channel 2                         */
/*                 agb1500_CH_3      3     Channel 3                         */
/*                 agb1500_CH_4      4     Channel 4                         */
/*                 agb1500_CH_5      5     Channel 5                         */
/*                 agb1500_CH_6      6     Channel 6                         */
/*                 agb1500_CH_7      7     Channel 7                         */
/*                 agb1500_CH_8      8     Channel 8                         */
/*                 agb1500_CH_9      9     Channel 9                         */
/*                 agb1500_CH_10    10     Channel 10                        */
/*                                                                           */
/*         mode    Pulse output mode.                                        */
/*                 Select 1 for current pulse output mode.                   */
/*                 Select 2 for voltage pulse output mode.                   */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_IF_MODE   1    CURRENT PULSE                      */
/*                 agb1500_VF_MODE   2    VOLTAGE PULSE                      */
/*                                                                           */
/*         range   Output ranging type.                                      */
/*                 For current output: 0, 1E-12 to 1.0                        */
/*                 For voltage output: 0, 0.5 to 200.0                       */
/*                 where,                                                    */
/*                 For auto ranging: Enter 0 (zero).                         */
/*                 For limited auto ranging: Enter positive value.           */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*         base    Pulse base value (in A or V).                             */
/*                 For current pulse: -1.0 A to 1.0 A                        */
/*                 For voltage pulse: -200.0 V to 200.0 V                    */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value                                   */
/*                 agb1500_SMUV_MIN   -200.0                                 */
/*                 agb1500_SMUV_MAX   200.0                                  */
/*                                                                           */
/*          peak   Pulse peak value (in A or V).                             */
/*                 For current pulse: -1.0 A to 1.0 A                        */
/*                 For voltage pulse: -200.0 V to 200.0 V                    */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value                                   */
/*                 agb1500_SMUV_MIN   -200.0                                 */
/*                 agb1500_SMUV_MAX   200.0                                  */
/*                                                                           */
/*         width   Pulse width (in second).                                  */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                    Value                             */
/*                 agb1500_SMUP_WIDTH_MIN   0.5E-3                           */
/*                 agb1500_SMUP_WIDTH_MAX   2.0                              */
/*                                                                           */
/*         period   Pulse period (in second).                                */
/*                  Data Type:  ViReal64                                     */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name                     Value                           */
/*                  agb1500_SMUP_PERIOD_MIN   5.0E-3                         */
/*                  agb1500_SMUP_PERIOD_MAX   5.0                            */
/*                                                                           */
/*         hold   Hold time (in second).                                     */
/*                Time since starting the measurement until starting         */
/*                the (1st) pulse output.                                    */
/*                Data Type:  ViReal64                                       */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                Name                  Value                                */
/*                agb1500_SWP_HOLD_MIN   0.00                                */
/*                agb1500_SWP_HOLD_MAX   655.35                              */
/*                                                                           */
/*         comp   Compliance (in V or A).                                    */
/*                If the comp value is out of the following range,           */
/*                the comp parameter is ignored.                             */
/*                Voltage compliance (for current pulse): -200.0 V to 200.0 V*/
/*                Current compliance (for voltage pulse): -1.0 A to 1.0 A    */
/*                Data Type:  ViReal64                                       */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                Name               Value                                   */
/*                agb1500_SMUV_MIN    -200.0                                 */
/*                agb1500_SMUV_MAX    200.0                                  */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct    agb1500_globals    *thisPtr;
    char    command[256] ;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_setPbias" );


    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( channel, agb1500_CH_1, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);

    agb1500_CHK_LONG_RANGE( mode, agb1500_IF_MODE, agb1500_VF_MODE, 
                           VI_ERROR_PARAMETER3);

    if ( fabs(range) > agb1500_AUTOR_BORDER ) 
        agb1500_CHK_REAL_RANGE( range, agb1500_RANGE_MIN, agb1500_RANGE_MAX, 
                            VI_ERROR_PARAMETER4);
    
    agb1500_CHK_REAL_RANGE( base, agb1500_SMUV_MIN, agb1500_SMUV_MAX, 
                           VI_ERROR_PARAMETER5);

    agb1500_CHK_REAL_RANGE( peak, agb1500_SMUV_MIN, agb1500_SMUV_MAX, 
                           VI_ERROR_PARAMETER6);


    agb1500_CHK_REAL_RANGE( width, agb1500_SMUP_WIDTH_MIN, agb1500_SMUP_WIDTH_MAX, 
                           VI_ERROR_PARAMETER7);

    agb1500_CHK_REAL_RANGE( period, agb1500_SMUP_PERIOD_MIN, agb1500_SMUP_PERIOD_MAX, 
                           VI_ERROR_PARAMETER8);

    agb1500_CHK_REAL_RANGE( hold, agb1500_SMUP_HOLD_MIN, agb1500_SMUP_HOLD_MAX, 
                           agb1500_INSTR_ERROR_PARAMETER9);


    /*--- Set Command ---*/
    if ( mode == agb1500_VF_MODE ) {        /*--- VOLTAGE PULSE ---*/
        if ( !(agb1500_SMUV_MIN <= comp  &&  comp <= agb1500_SMUV_MAX) ) 
            sprintf( command, "PV %d,%d,%E,%E", 
                channel, abs(vRangeId(channel,thisPtr->UNT[channel-1],range)), base, peak );
        
        else
            sprintf( command, "PV %d,%d,%E,%E,%E", 
                channel, abs(vRangeId(channel,thisPtr->UNT[channel-1],range)), 
				base, peak, comp );
    }
    else {                    /*--- CURRENT PULSE ---*/
        if ( !(agb1500_SMUV_MIN <= comp  &&  comp <= agb1500_SMUV_MAX) ) 
            sprintf( command, "PI %d,%d,%E,%E", 
                channel, abs(iRangeId(channel,thisPtr->UNT[channel-1],range)), base, peak );
        
        else
            sprintf( command, "PI %d,%d,%E,%E,%E", 
                channel, abs(iRangeId(channel,thisPtr->UNT[channel-1],range)), base, peak, comp );
    }


    errStatus = viPrintf(vi,"%s\n", command );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    sprintf( command, "PT %E,%E,%E", hold, width, period );

    errStatus = viPrintf(vi,"%s\n", command );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }
    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_setPiv(ViSession vi, 
                               ViInt32 channel, ViInt32 mode, ViReal64 range,
                               ViReal64 base, ViReal64 start, ViReal64 stop, 
                               ViInt32 point,
                               ViReal64 hold, ViReal64 width, ViReal64 period,
                               ViReal64 comp )
/*****************************************************************************/
/*                                                                           */
/*      This function sets the pulse sweep source for the pulsed sweep       */
/*      measurements.  To perform the pulsed sweep measurement, execute      */
/*      the agb1500_sweepPiv function.                                       */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      PWV                                                                  */
/*      PWI                                                                  */
/*      PT                                                                   */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi   Instrument Handle returned from agb1500_init( ).           */
/*                Data Type:  ViSession                                      */
/*                Input/Output:  IN                                          */
/*                                                                           */
/*      channel   Channel number of the channel.  Same as the slot number    */
/*                for the SMU.                                               */
/*                Data Type:  ViInt32                                        */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                Name            Value   Description                        */
/*                agb1500_CH_1      1     Channel 1                          */
/*                agb1500_CH_2      2     Channel 2                          */
/*                agb1500_CH_3      3     Channel 3                          */
/*                agb1500_CH_4      4     Channel 4                          */
/*                agb1500_CH_5      5     Channel 5                          */
/*                agb1500_CH_6      6     Channel 6                          */
/*                agb1500_CH_7      7     Channel 7                          */
/*                agb1500_CH_8      8     Channel 8                          */
/*                agb1500_CH_9      9     Channel 9                          */
/*                agb1500_CH_10    10     Channel 10                         */
/*                                                                           */
/*         mode   Pulse sweep source output mode.                            */
/*                For voltage output: Enter positive value.                  */
/*                For current output: Enter negative value.                  */
/*                Data Type:  ViInt32                                        */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                Name                   Value   Description                 */
/*                agb1500_SWP_VF_SGLLIN   1     SINGLE LINEAR V              */
/*                agb1500_SWP_VF_DBLLIN   3     DOUBLE LINEAR V              */
/*                agb1500_SWP_IF_SGLLIN   -1    SINGLE LINEAR I              */
/*                agb1500_SWP_IF_DBLLIN   -3    DOUBLE LINEAR I              */
/*                                                                           */
/*        range   Output ranging type.                                       */
/*                For current output: 0, 1E-12 to 1.0                         */
/*                For voltage output: 0, 0.5 to 200.0                        */
/*                where,                                                     */
/*                For auto ranging: Enter 0 (zero).                          */
/*                For limited auto ranging: Enter positive value.            */
/*                Data Type:  ViReal64                                       */
/*                Input/Output:  IN                                          */
/*                                                                           */
/*         base   Pulse base value (in A or V).                              */
/*                For current pulse: -1.0 A to 1.0 A                         */
/*                For voltage pulse: -200.0 V to 200.0 V                     */
/*                Data Type:  ViReal64                                       */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                Name              Value                                    */
/*                agb1500_SMUV_MIN   -200.0                                  */
/*                agb1500_SMUV_MAX   200.0                                   */
/*                                                                           */
/*          start Pulse sweep start value (in A or V).                       */
/*                For current sweep: -1.0 A to 1.0 A                         */
/*                For voltage sweep: -200.0 V to 200.0 V                     */
/*                Data Type:  ViReal64                                       */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                Name              Value                                    */
/*                agb1500_SMUV_MIN   -200.0                                  */
/*                agb1500_SMUV_MAX   200.0                                   */
/*                                                                           */
/*         stop   Pulse sweep start value (in A or V).                       */
/*                For current sweep: -1.0 A to 1.0 A                         */
/*                For voltage sweep: -200.0 V to 200.0 V                     */
/*                Data Type:  ViReal64                                       */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                Name              Value                                    */
/*                agb1500_SMUV_MIN   -200.0                                  */
/*                agb1500_SMUV_MAX   200.0                                   */
/*                                                                           */
/*         point  Number of sweep steps.                                     */
/*                Data Type:  ViInt32                                        */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                Name                   Value                               */
/*                agb1500_SWP_POINT_MIN   1                                  */
/*                agb1500_SWP_POINT_MAX   1001                               */
/*                                                                           */
/*          hold  Hold time (in second).                                     */
/*                Time since starting the measurement until starting         */
/*                the (1st) pulse output.                                    */
/*                Data Type:  ViReal64                                       */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                Name                  Value                                */
/*                agb1500_SWP_HOLD_MIN   0.00                                */
/*                agb1500_SWP_HOLD_MAX   655.35                              */
/*                                                                           */
/*         width  Pulse width (in second).                                   */
/*                Data Type:  ViReal64                                       */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                Name                    Value                              */
/*                agb1500_SMUP_WIDTH_MIN   0.5E-3                            */
/*                agb1500_SMUP_WIDTH_MAX   2.0                               */
/*                                                                           */
/*        period  Pulse period (in second).                                  */
/*                Data Type:  ViReal64                                       */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                Name                     Value                             */
/*                agb1500_SMUP_PERIOD_MIN   5.0E-3                           */
/*                agb1500_SMUP_PERIOD_MAX   5.0                              */
/*                                                                           */
/*         comp   Compliance (in V or A).                                    */
/*                If the comp value is out of the following range,           */
/*                the comp parameter is ignored.                             */
/*                Voltage compliance (for current pulse): -200.0 V to 200.0 V*/
/*                Current compliance (for voltage pulse): -1.0 A to 1.0 A    */
/*                Data Type:  ViReal64                                       */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                Name               Value                                   */
/*                agb1500_SMUV_MIN    -200.0                                 */
/*                agb1500_SMUV_MAX    200.0                                  */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct    agb1500_globals    *thisPtr;
    char    command[256] ;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_setPiv" );


    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( channel, agb1500_CH_1, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);

    if ( !((abs(mode) == agb1500_SWP_VF_SGLLIN)||
      (abs(mode) == agb1500_SWP_VF_DBLLIN)))
        agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER3);


    if ( fabs(range) > agb1500_AUTOR_BORDER ) 
        agb1500_CHK_REAL_RANGE( range, agb1500_RANGE_MIN, agb1500_RANGE_MAX, 
                            VI_ERROR_PARAMETER4);
    
    agb1500_CHK_REAL_RANGE( base, agb1500_SMUV_MIN, agb1500_SMUV_MAX, 
                           VI_ERROR_PARAMETER5);

    agb1500_CHK_REAL_RANGE( start, agb1500_SMUV_MIN, agb1500_SMUV_MAX, 
                           VI_ERROR_PARAMETER6);

    agb1500_CHK_REAL_RANGE( stop, agb1500_SMUV_MIN, agb1500_SMUV_MAX, 
                           VI_ERROR_PARAMETER7);

    agb1500_CHK_LONG_RANGE( point, agb1500_SWP_POINT_MIN, agb1500_SWP_POINT_MAX, 
                           VI_ERROR_PARAMETER8);

    agb1500_CHK_REAL_RANGE( hold, agb1500_SWP_HOLD_MIN, agb1500_SWP_HOLD_MAX, 
                           agb1500_INSTR_ERROR_PARAMETER9);

    agb1500_CHK_REAL_RANGE( width, agb1500_SMUP_WIDTH_MIN, agb1500_SMUP_WIDTH_MAX, 
                           agb1500_INSTR_ERROR_PARAMETER10);

    agb1500_CHK_REAL_RANGE( period, agb1500_SMUP_PERIOD_MIN, agb1500_SMUP_PERIOD_MAX, 
                           agb1500_INSTR_ERROR_PARAMETER11);

    /*--- Set Command ---*/
    if ( mode > 0 ) {        /*--- VOLTAGE PULSE ---*/
        if ( !(agb1500_SMUV_MIN <= comp  &&  comp <= agb1500_SMUV_MAX) ) 
            sprintf( command, "PWV %d,%d,%d,%E,%E,%E,%d", 
                channel, abs(mode), abs(vRangeId(channel,thisPtr->UNT[channel-1],range)), 
				base, start, stop, point );
        
        else
            sprintf( command, "PWV %d,%d,%d,%E,%E,%E,%d,%E", 
                channel, abs(mode), abs(vRangeId(channel,thisPtr->UNT[channel-1],range)),
				base, start, stop, point, comp );
    }
    else {                    /*--- CURRENT PULSE ---*/
        if ( !(agb1500_SMUV_MIN <= comp  &&  comp <= agb1500_SMUV_MAX) ) 
            sprintf( command, "PWI %d,%d,%d,%E,%E,%E,%d", 
                channel, abs(mode), abs(iRangeId(channel,thisPtr->UNT[channel-1],range)), base, start, stop, point );
        
        else
            sprintf( command, "PWI %d,%d,%d,%E,%E,%E,%d,%E", 
                channel, abs(mode), abs(iRangeId(channel,thisPtr->UNT[channel-1],range)), base, start, stop, point, comp );
    }


    errStatus = viPrintf(vi,"%s\n", command );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    sprintf( command, "PT %E,%E,%E", hold, width, period );

    errStatus = viPrintf(vi,"%s\n", command );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }
    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_setSweepSync(ViSession vi, 
                               ViInt32 channel, ViInt32 mode, ViReal64 range,
                               ViReal64 start, ViReal64 stop,
                               ViReal64 comp, ViReal64 p_comp )
/*****************************************************************************/
/*                                                                           */
/*      This function sets the synchronous sweep source for the staircase    */
/*      sweep, pulsed sweep, and staircase sweep with pulsed bias            */
/*      measurements.  The source output is the staircase sweep, and         */
/*      synchronized with the primary sweep source output.                   */
/*                                                                           */
/*      To perform the staircase sweep measurements, execute the             */
/*      agb1500_setIv function to set the primary sweep source, and execute  */
/*      the agb1500_sweepIv or agb1500_sweepMiv function to start            */
/*      measurement.  The agb1500_sweepMiv function allows to use multiple   */
/*      measurement channels.                                                */
/*                                                                           */
/*      To perform the pulsed sweep measurements, execute the agb1500_setPiv */
/*      function to set the primary sweep source, and execute the            */
/*      agb1500_sweepPiv function to start measurement.                      */
/*                                                                           */
/*      To perform the staircase sweep with pulsed bias measurements,        */
/*      execute the agb1500_setIv function to set the primary sweep source,  */
/*      execute the agb1500_setPbias function to set the pulse bias source,  */
/*      and execute the agb1500_sweepPbias function to start measurement.    */
/*                                                                           */
/*      Note: The agb1500_setIv or agb1500_setPiv function must be executed  */
/*      before executing this function.                                      */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      WSV                                                                  */
/*      WSI                                                                  */
/*                                                                           */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      channel    Channel number of the channel.  Same as the slot number   */
/*                 for the SMU.                                              */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_1      1     Channel 1                         */
/*                 agb1500_CH_2      2     Channel 2                         */
/*                 agb1500_CH_3      3     Channel 3                         */
/*                 agb1500_CH_4      4     Channel 4                         */
/*                 agb1500_CH_5      5     Channel 5                         */
/*                 agb1500_CH_6      6     Channel 6                         */
/*                 agb1500_CH_7      7     Channel 7                         */
/*                 agb1500_CH_8      8     Channel 8                         */
/*                 agb1500_CH_9      9     Channel 9						 */
/*                 agb1500_CH_10    10     Channel 10                        */
/*                                                                           */
/*         mode    Output mode, voltage or current (available only for SMU). */
/*                 Select voltage for the voltage output primary sweep       */
/*                 source.                                                   */
/*                 Select current for the current output primary sweep       */
/*                 source.                                                   */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value   Description                     */
/*                 agb1500_ IF_MODE   1     CURRENT OUTPUT                   */
/*                 agb1500_ VF_MODE   2     VOLTAGE OUTPUT                   */
/*                                                                           */
/*        range    Output ranging type.                                      */
/*                 For current output: 0, 1E-12 to 1.0                        */
/*                 For voltage output: 0, 0.5 to 200.0                       */
/*                 where,                                                    */
/*                 For auto ranging: Enter 0 (zero).                         */
/*                 For limited auto ranging: Enter positive value.           */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*        start    Sweep start value (in A or V).                            */
/*                 For current sweep: -1.0 A to 1.0 A                        */
/*                 For voltage sweep: -200.0 V to 200.0 V                    */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value                                   */
/*                 agb1500_SMUV_MIN   -200.0                                 */
/*                 agb1500_SMUV_MAX   200.0                                  */
/*                                                                           */
/*          stop   Sweep stop value (in A or V).                             */
/*                 For current sweep: -1.0 A to 1.0 A                        */
/*                 For voltage sweep: -200.0 V to 200.0 V                    */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value                                   */
/*                 agb1500_SMUV_MIN   -200.0                                 */
/*                 agb1500_SMUV_MAX   200.0                                  */
/*                                                                           */
/*         comp   Compliance (in V or A).                                    */
/*                If the comp value is out of the following range,           */
/*                the comp and p_comp parameters are ignored.                */
/*                Voltage compliance (for current sweep): -200.0 V to 200.0 V*/
/*                Current compliance (for voltage sweep): -1.0 A to 1.0 A    */
/*                Data Type:  ViReal64                                       */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                Name               Value                                   */
/*                agb1500_SMUV_MIN    -200.0                                 */
/*                agb1500_SMUV_MAX    200.0                                  */
/*                                                                           */
/*        p_comp   Power compliance (in VA).  If the p_comp value is         */
/*                 out of the following range, the p_comp value is ignored.  */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                   Value                              */
/*                 agb1500_SMU_POWER_MIN   1.0E-3                            */
/*                 agb1500_SMU_POWER_MAX   20.0                              */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct    agb1500_globals    *thisPtr;
    char    command[256] ;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_setSweepSync" );


    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( channel, agb1500_CH_1, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);

    agb1500_CHK_LONG_RANGE( mode, agb1500_IF_MODE, agb1500_VF_MODE, 
                           VI_ERROR_PARAMETER3);

    if ( fabs(range) > agb1500_AUTOR_BORDER )
        agb1500_CHK_REAL_RANGE( range, agb1500_RANGE_MIN, agb1500_RANGE_MAX, 
                                VI_ERROR_PARAMETER4);
    
    agb1500_CHK_REAL_RANGE( start, agb1500_SMUV_MIN, agb1500_SMUV_MAX, 
                           VI_ERROR_PARAMETER5);

    agb1500_CHK_REAL_RANGE( stop, agb1500_SMUV_MIN, agb1500_SMUV_MAX, 
                           VI_ERROR_PARAMETER6);


    /*--- Set Command ---*/
    if ( mode == agb1500_VF_MODE ) {        /*--- VOLTAGE ---*/
        if ( !(agb1500_SMUV_MIN <= comp  &&  comp <= agb1500_SMUV_MAX) ) 
            sprintf( command, "WSV %d,%d,%E,%E", 
                channel, abs(vRangeId(channel,thisPtr->UNT[channel-1],range)), 
				start, stop );
        
        else if ( !(agb1500_SMU_POWER_MIN <= p_comp  &&   p_comp <= agb1500_SMU_POWER_MAX) )
            sprintf( command, "WSV %d,%d,%E,%E,%E", 
                channel, abs(vRangeId(channel,thisPtr->UNT[channel-1],range)), 
				start, stop, comp );
        
        else
            sprintf( command, "WSV %d,%d,%E,%E,%E,%E", 
                channel, abs(vRangeId(channel,thisPtr->UNT[channel-1],range)), start, stop, comp, p_comp );
    }
    else {                                /*--- CURRENT ---*/
        if ( !(agb1500_SMUV_MIN <= comp  &&  comp <= agb1500_SMUV_MAX) ) 
            sprintf( command, "WSI %d,%d,%E,%E", 
                channel, abs(iRangeId(channel,thisPtr->UNT[channel-1],range)), start, stop );
        
        else if ( !(agb1500_SMU_POWER_MIN <= p_comp  &&   p_comp <= agb1500_SMU_POWER_MAX) )
            sprintf( command, "WSI %d,%d,%E,%E,%E", 
                channel, abs(iRangeId(channel,thisPtr->UNT[channel-1],range)), start, stop, comp );
        
        else
            sprintf( command, "WSI %d,%d,%E,%E,%E,%E", 
                channel, abs(iRangeId(channel,thisPtr->UNT[channel-1],range)), start, stop, comp, p_comp );
    }


    errStatus = viPrintf(vi,"%s\n", command );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_setNthSweep(ViSession vi, ViInt32 n,
                               ViInt32 channel, ViInt32 mode, ViReal64 range,
                               ViReal64 start, ViReal64 stop,
                               ViReal64 comp, ViReal64 p_comp )
/*****************************************************************************/
/*                                                                           */
/*      This function sets the synchronous sweep source for the multi        */
/*      channel sweep measurements.  Up to 7 synchronous sweep sources       */
/*      can be set by entering this command for each channel.                */
/*      The source output is the staircase sweep, and synchronizes with      */
/*      the primary sweep source output.                                     */
/*                                                                           */
/*      To perform the multi channel sweep measurements, execute the         */
/*      agb1500_setIv function to set the primary sweep source (1st sweep    */
/*      source), and execute the agb1500_msweepIv or agb1500_msweepMiv       */
/*      function to start measurement.                                       */
/*      The agb1500_msweepMiv function allows to use multiple measurement    */
/*      channels.                                                            */
/*                                                                           */
/*      Note: The agb1500_setIv function must be executed before executing   */
/*            this function.                                                 */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      WNX                                                                  */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*            n    Sweep source ID.                                          */
/*                 2 for the 2nd sweep source (1st synchronous sweep source),*/
/*                 3 for the 3rd sweep source (2nd synchronous sweep source),*/
/*                 ...., or 8 for the 8th sweep source (7th synchronous      */
/*                 sweep source).                                            */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                   Value                              */
/*                 agb1500_NTH_SWEEP_MIN   2                                 */
/*                 agb1500_NTH_SWEEP_MAX   10                                */
/*                                                                           */
/*      channel    Channel number of the channel.  Same as the slot number   */
/*                 for the SMU.                                              */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_1      1     Channel 1                         */
/*                 agb1500_CH_2      2     Channel 2                         */
/*                 agb1500_CH_3      3     Channel 3                         */
/*                 agb1500_CH_4      4     Channel 4                         */
/*                 agb1500_CH_5      5     Channel 5                         */
/*                 agb1500_CH_6      6     Channel 6                         */
/*                 agb1500_CH_7      7     Channel 7                         */
/*                 agb1500_CH_8      8     Channel 8                         */
/*                 agb1500_CH_9      9     Channel 9					     */
/*                 agb1500_CH_10    10     Channel 10                        */
/*                                                                           */
/*         mode    Select 1 for current output (available only for SMU).     */
/*                 Select 2 for voltage output.                              */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value   Description                     */
/*                 agb1500_ IF_MODE   1     CURRENT OUTPUT                   */
/*                 agb1500_ VF_MODE   2     VOLTAGE OUTPUT                   */
/*                                                                           */
/*        range    Output ranging type.                                      */
/*                 For current output: 0, 1E-12 to 1.0                        */
/*                 For voltage output: 0, 0.5 to 200.0                       */
/*                 where,                                                    */
/*                 For auto ranging: Enter 0 (zero).                         */
/*                 For limited auto ranging: Enter positive value.           */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*        start    Sweep start value (in A or V).                            */
/*                 For current sweep: -1.0 A to 1.0 A                        */
/*                 For voltage sweep: -200.0 V to 200.0 V                    */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value                                   */
/*                 agb1500_SMUV_MIN   -200.0                                 */
/*                 agb1500_SMUV_MAX   200.0                                  */
/*                                                                           */
/*          stop   Sweep stop value (in A or V).                             */
/*                 For current sweep: -1.0 A to 1.0 A                        */
/*                 For voltage sweep: -200.0 V to 200.0 V                    */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value                                   */
/*                 agb1500_SMUV_MIN   -200.0                                 */
/*                 agb1500_SMUV_MAX   200.0                                  */
/*                                                                           */
/*         comp   Compliance (in V or A).                                    */
/*                If the comp value is out of the following range,           */
/*                the comp parameter is ignored.                             */
/*                Voltage compliance (for current pulse): -200.0 V to 200.0 V*/
/*                Current compliance (for voltage pulse): -1.0 A to 1.0 A    */
/*                Data Type:  ViReal64                                       */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                Name               Value                                   */
/*                agb1500_SMUV_MIN    -200.0                                 */
/*                agb1500_SMUV_MAX    200.0                                  */
/*                                                                           */
/*        p_comp   Power compliance (in VA).  If the p_comp value is         */
/*                 out of the following range, the p_comp value is ignored.  */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                   Value                              */
/*                 agb1500_SMU_POWER_MIN   1.0E-3                            */
/*                 agb1500_SMU_POWER_MAX   20.0                              */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{

#define    WNX_VF_MODE     1
#define    WNX_IF_MODE     2

    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
    char     command[256] ;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_setNthSweep" );


    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( n, agb1500_NTH_SWEEP_MIN, agb1500_NTH_SWEEP_MAX, 
                           VI_ERROR_PARAMETER2);

    agb1500_CHK_LONG_RANGE( channel, agb1500_CH_1, agb1500_CH_10, 
                           VI_ERROR_PARAMETER3);

    agb1500_CHK_LONG_RANGE( mode, agb1500_IF_MODE, agb1500_VF_MODE, 
                           VI_ERROR_PARAMETER4);

    if ( fabs(range) > agb1500_AUTOR_BORDER )
        agb1500_CHK_REAL_RANGE( range, agb1500_RANGE_MIN, agb1500_RANGE_MAX, 
                                VI_ERROR_PARAMETER5);
    
    agb1500_CHK_REAL_RANGE( start, agb1500_SMUV_MIN, agb1500_SMUV_MAX, 
                           VI_ERROR_PARAMETER6);

    agb1500_CHK_REAL_RANGE( stop, agb1500_SMUV_MIN, agb1500_SMUV_MAX, 
                           VI_ERROR_PARAMETER7);

    /*--- Set Command ---*/
    if ( mode == agb1500_VF_MODE ) {        /*--- VOLTAGE ---*/
        if ( !(agb1500_SMUV_MIN <= comp  &&  comp <= agb1500_SMUV_MAX) ) 
            sprintf( command, "WNX %d,%d,%d,%d,%E,%E", 
                n, channel, WNX_VF_MODE, abs(vRangeId(channel,thisPtr->UNT[channel-1],range)), 
				start, stop );

        else if ( !(agb1500_SMU_POWER_MIN <= p_comp  &&   p_comp <= agb1500_SMU_POWER_MAX) )
            sprintf( command, "WNX %d,%d,%d,%d,%E,%E,%E", 
                n, channel, WNX_VF_MODE, abs(vRangeId(channel,thisPtr->UNT[channel-1],range)), start, stop, comp );

        else
            sprintf( command, "WNX %d,%d,%d,%d,%E,%E,%E,%E", 
                n, channel, WNX_VF_MODE, abs(vRangeId(channel,thisPtr->UNT[channel-1],range)), start, stop, comp, p_comp );
    }
    else {                                /*--- CURRENT ---*/
        if ( !(agb1500_SMUV_MIN <= comp  &&  comp <= agb1500_SMUV_MAX) ) 
            sprintf( command, "WNX %d,%d,%d,%d,%E,%E", 
                n, channel, WNX_IF_MODE, abs(iRangeId(channel,thisPtr->UNT[channel-1],range)), start, stop );
        
        else if ( !(agb1500_SMU_POWER_MIN <= p_comp  &&   p_comp <= agb1500_SMU_POWER_MAX) )
            sprintf( command, "WNX %d,%d,%d,%d,%E,%E,%E", 
                n, channel, WNX_IF_MODE, abs(iRangeId(channel,thisPtr->UNT[channel-1],range)), start, stop, comp );

        else
            sprintf( command, "WNX %d,%d,%d,%d,%E,%E,%E,%E", 
                n, channel, WNX_IF_MODE, abs(iRangeId(channel,thisPtr->UNT[channel-1],range)), start, stop, comp, p_comp );
    }


    errStatus = viPrintf(vi,"%s\n", command );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/********************* Measurement Execution Functions ***********************/

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_spotMeas(ViSession vi, ViInt32 channel,
                                    ViInt32 mode, ViReal64 range,
                                    ViPReal64 value, ViPInt32 status,
                                  ViPReal64 time)
/*****************************************************************************/
/*                                                                           */
/*      This function performs high speed spot measurement, and              */
/*      returns the measurement data, measurement status, and                */
/*      time stamp data.                                                     */
/*                                                                           */
/*      The parameter 'channel' specifies the measurement channel.           */
/*      The parameter 'mode' specifies the measurement mode, voltage or      */
/*      current.                                                             */
/*      The parameter 'range' specifies the measurement ranging type.        */
/*      The parameter 'value' returns the measurement data.                  */
/*      The parameter 'status' returns the measurement status.               */
/*      The parameter 'time' returns the time stamp data.                    */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      FMT                                                                  */
/*      TTI                                                                  */
/*      TTV                                                                  */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*                                                                           */
/*      channel    Channel number of the channel.  Same as the slot number   */
/*                 for the SMU.                                              */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_1      1     Channel 1                         */
/*                 agb1500_CH_2      2     Channel 2                         */
/*                 agb1500_CH_3      3     Channel 3                         */
/*                 agb1500_CH_4      4     Channel 4                         */
/*                 agb1500_CH_5      5     Channel 5                         */
/*                 agb1500_CH_6      6     Channel 6                         */
/*                 agb1500_CH_7      7     Channel 7                         */
/*                 agb1500_CH_8      8     Channel 8                         */
/*                 agb1500_CH_9      9     Channel 9						 */
/*                 agb1500_CH_10    10     Channel 10						 */
/*                                                                           */
/*         mode    Select 1 for current output (available only for SMU).     */
/*                 Select 2 for voltage output.                              */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value   Description                     */
/*                 agb1500_ IF_MODE   1     CURRENT OUTPUT                   */
/*                 agb1500_ VF_MODE   2     VOLTAGE OUTPUT                   */
/*                                                                           */
/*        range    Output ranging type.                                      */
/*                 For current output: 0, 1E-12 to 1.0                        */
/*                 For voltage output: 0, 0.5 to 200.0                       */
/*                 where,                                                    */
/*                 For auto ranging: Enter 0 (zero).                         */
/*                 For limited auto ranging: Enter positive value.           */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*        value    Measurement data.                                         */
/*                 Data Type:  ViPReal64                                     */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*       status    Measurement status.To disable the status data output,     */
/*                 set 0 (NULL pointer) instead of variable.                 */
/*                 Data Type:  ViPInt32                                      */
/*                 Input/Output:  OUT                                        */
/*                 Values:                                                   */
/*                 Name                  Value   Description                 */
/*                 agb1500_STAT_OVF_BIT   1     AD converter overflowed.     */
/*                 agb1500_STAT_OSC_BIT   2     One or more channels are     */
/*                                              oscillating.                 */
/*                 agb1500_STAT_OCC_BIT   3     Another channel reached      */
/*                                              compliance.                  */
/*                 agb1500_STAT_TCC_BIT   4     This channel reached         */
/*                                              compliance.                  */
/*                                                                           */
/*        time    Time stamp data (measurement start time).                  */
/*                To disable the time stamp data output, set 0 (NULL pointer)*/
/*                instead of variable.                                       */
/*                Data Type:  ViPReal64                                      */
/*                Input/Output:  OUT                                         */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
 
{
    ViStatus errStatus = 0;
    struct agb1500_globals *thisPtr;

    ViReal64  get_value ;
    ViInt32   get_status ;
    ViInt32   get_eod ;
    ViInt32   channelNo;
    ViInt32   dataKind;
   
   errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
   if ( errStatus < VI_SUCCESS)   {
       agb1500_LOG_STATUS( vi, 0, errStatus );
   }
   agb1500_DEBUG_CHK_THIS( vi, thisPtr );
   agb1500_CDE_INIT( "agb1500_spotMeas" );

    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( channel, agb1500_CH_1, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);

    agb1500_CHK_LONG_RANGE(mode, agb1500_IM_MODE, agb1500_VM_MODE, 
                           VI_ERROR_PARAMETER3);

    agb1500_CHK_REAL_RANGE(range, agb1500_RANGE_MIN, agb1500_RANGE_MAX, 
                           VI_ERROR_PARAMETER4);
    
    /* Instrument I/O */
    errStatus = viPrintf(vi,"FMT 21,0\n");

    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }


    if ( mode == agb1500_VM_MODE) {
        if ( time != (ViReal64 *) NULL) {
            errStatus = viPrintf(vi,"TTV %d,%d\n", channel, vRangeId(channel,thisPtr->UNT[channel-1],range) );
            if ( errStatus < VI_SUCCESS) {
                agb1500_LOG_STATUS( vi, thisPtr, errStatus );
            }

        }
        else {
            errStatus = viPrintf(vi,"TV %d,%d\n", channel, vRangeId(channel,thisPtr->UNT[channel-1],range) );
            if ( errStatus < VI_SUCCESS) {
                agb1500_LOG_STATUS( vi, thisPtr, errStatus );
            }

        }
    }
    else {
        if ( time != (ViReal64 *) NULL) {
            errStatus = viPrintf(vi,"TTI %d,%d\n", channel, iRangeId(channel,thisPtr->UNT[channel-1],range) );
            if ( errStatus < VI_SUCCESS) {
                agb1500_LOG_STATUS( vi, thisPtr, errStatus );
            }      
        }
        else {
            errStatus = viPrintf(vi,"TI %d,%d\n", channel, iRangeId(channel,thisPtr->UNT[channel-1],range) );
            if ( errStatus < VI_SUCCESS) {
                agb1500_LOG_STATUS( vi, thisPtr, errStatus );
            }      

        }
    }
    
	agb1500_CHK_INST_ERR_AFTER_XE( vi, thisPtr );

    /*--- get measurement data ---*/
    get_eod = 0;
    for ( ;get_eod == 0; ) {
        errStatus = asciiDataRead( vi,&dataKind, &get_value, &get_status,&channelNo, &get_eod );
        if ( errStatus < VI_SUCCESS)  {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
        if ( dataKind == agb1500_DT_TM) {
            if ( time != (ViReal64 *)NULL)
                *time = get_value;
        }
        else {
            *value = get_value;
            if ( status !=(ViInt32 *)NULL) {
                *status = get_status ;
            }
        }
    }
    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_measureM(ViSession vi, ViInt32 channel[], 
                                  ViInt32 mode[], ViReal64 range[],
                                  ViReal64 value[], ViInt32 status[],
                                  ViReal64 time[])
/*****************************************************************************/
/*                                                                           */
/*      This function performs multi-channel spot measurement using up to    */
/*      8 SMUs at a time, and returns the measurement data and the           */
/*      measurement status.                                                  */
/*                                                                           */
/*      The parameter 'channel[ ]' specifies the measurement channels.       */
/*      The parameter 'mode[ ]' specifies the measurement mode for           */
/*      each channel                                                         */
/*      The parameter 'range[ ]' specifies the measurement ranging type      */
/*      for each channel.                                                    */
/*      The parameter 'value[ ]' returns the measurement data of             */
/*      each channel.                                                        */
/*      The parameter 'status[ ]' returns the measurement status of          */
/*      each channel.                                                        */
/*      The parameter 'time[ ]' returns the time stamp data of each          */
/*      channel.                                                             */
/*                                                                           */
/*      The array size must be channel[N+1], mode[N], range[N], value[N],    */
/*      status[N], and time[N] (N: number of the measurement channels).      */
/*      Then the order of the array data is important.  For example,         */
/*      the measurement setup of the channel specified by channel[1] must    */
/*      be entered into mode[1] and range[1].  And the measured data, status */
/*      data, and time stamp data of the channel specified by channel[1]     */
/*      will be returned by value[1], status[1], and time[1], respectively.  */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      FMT                                                                  */
/*      TSC                                                                  */
/*      MM                                                                   */
/*      CMM                                                                  */
/*      RI                                                                   */
/*      RV                                                                   */
/*      XE                                                                   */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*                                                                           */
/*   channel[ ]    Channel number of the measurement channel.                */
/*                 Same as the slot number for the SMU.                      */
/*                 At the end of the channel definitions, enter 0 (zero)     */
/*                 into the last array element.                              */
/*                 For example, if you use four channels, array size should  */
/*                 be five, and 0 (zero) must be entered into the fifth array*/
/*                 element.                                                  */
/*                 Data Type:  ViInt32 [ ]                                   */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_1      1     Channel 1                         */
/*                 agb1500_CH_2      2     Channel 2                         */
/*                 agb1500_CH_3      3     Channel 3                         */
/*                 agb1500_CH_4      4     Channel 4                         */
/*                 agb1500_CH_5      5     Channel 5                         */
/*                 agb1500_CH_6      6     Channel 6                         */
/*                 agb1500_CH_7      7     Channel 7                         */
/*                 agb1500_CH_8      8     Channel 8                         */
/*                 agb1500_CH_9		 9     Channel 9                         */
/*                 agb1500_CH_10    10     Channel 10                        */
/*                                                                           */
/*       mode[ ]   Measurement mode.                                         */
/*                 Enter 1 for current measurement.                          */
/*                 Enter 2 for voltage measurement.                          */
/*                 Data Type:  ViInt32 [ ]                                   */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value   Description                     */
/*                 agb1500_ IF_MODE   1     CURRENT OUTPUT                   */
/*                 agb1500_ VF_MODE   2     VOLTAGE OUTPUT                   */
/*                                                                           */
/*     range[ ]    Measurement ranging type.                                 */
/*                 For current output: 0, 1E-12 to 1.0                        */
/*                 For voltage output: 0, 0.5 to 200.0                       */
/*                 where,                                                    */
/*                 For auto ranging: Enter 0 (zero).                         */
/*                 For limited auto ranging: Enter positive value.           */
/*                 Data Type:  ViReal64[ ]                                   */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      value[ ]   Measurement data.                                         */
/*                 Data Type:  ViPReal64[ ]                                  */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*    status[ ]    Measurement status.To disable the status data output,     */
/*                 set 0 (NULL pointer) instead of array.                    */
/*                 Data Type:  ViPInt32[ ]                                   */
/*                 Input/Output:  OUT                                        */
/*                 Values:                                                   */
/*                 Name                  Value   Description                 */
/*                 agb1500_STAT_OVF_BIT   1     AD converter overflowed.     */
/*                 agb1500_STAT_OSC_BIT   2     One or more channels are     */
/*                                              oscillating.                 */
/*                 agb1500_STAT_OCC_BIT   3     Another channel reached      */
/*                                              compliance.                  */
/*                 agb1500_STAT_TCC_BIT   4     This channel reached         */
/*                                              compliance.                  */
/*                                                                           */
/*     time[ ]    Time stamp data (measurement start time).                  */
/*                To disable the time stamp data output, set 0 (NULL pointer)*/
/*                instead of array.                                          */
/*                Data Type:  ViPReal64[ ]                                   */
/*                Input/Output:  OUT                                         */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{

    ViStatus errStatus = 0 ;
    struct    agb1500_globals    *thisPtr;
    int         cnt ;
    int         chCnt ;
    int         dmyCnt ;
    ViInt32     getStatus ;
    ViInt32     eod ;
    ViReal64    getValue ;
    ViInt32     chanNum;
    ViInt32     dataKind;
    ViChar      chChar[8] ;
    ViChar      chString[256] ;            

   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_measureM" );


    /* Check Prameter Range */
    for ( cnt=0; channel[cnt] != 0; cnt++ ) {
         agb1500_CHK_LONG_RANGE( channel[cnt], agb1500_CH_1, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);

         agb1500_CHK_LONG_RANGE( mode[cnt], agb1500_IM_MODE, agb1500_VM_MODE, 
                            VI_ERROR_PARAMETER3);

         if ( fabs(range[cnt]) > agb1500_AUTOR_BORDER ) {
             agb1500_CHK_REAL_RANGE( range[cnt], agb1500_RANGE_MIN, agb1500_RANGE_MAX, 
                                    VI_ERROR_PARAMETER4);
         }
    }

    /*--- Channel Non Set ---*/
    if ( cnt == 0 ) agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2 );

    /*--- Get Chunnel Number ---*/
    chanNum = cnt ;

    /*--- Set Command ---*/

    errStatus = viPrintf(vi,"FMT 21,0\n" );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    if ( time != (ViReal64 *)NULL) {

        errStatus = viPrintf(vi,"TSC 1\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }
    else {

        errStatus = viPrintf(vi,"TSC 0\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }

    /*--- Edit Channel Number ---*/
    memset( chString, (char)NULL, sizeof(chString) );
    for ( cnt=0; cnt<chanNum; cnt++) {
        if ( cnt != 0 )    sprintf( chChar, ",%d", channel[cnt] );
        else            sprintf( chChar, "%d", channel[cnt] );
        strcat( chString, chChar );
    }

    errStatus = viPrintf(vi,"MM 1,%s\n", chString );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    for ( cnt=0; cnt<chanNum; cnt++ ) {

        errStatus = viPrintf(vi,"CMM %d,%d\n", channel[cnt], mode[cnt] );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }

        if ( mode[cnt] == agb1500_VM_MODE ) {

            errStatus = viPrintf(vi,"RV %d,%d\n",
                channel[cnt], vRangeId(channel[cnt],thisPtr->UNT[channel[cnt]-1],range[cnt]));
            if ( errStatus < VI_SUCCESS) {
                agb1500_LOG_STATUS( vi, thisPtr, errStatus );
            }
        }
        else {

            errStatus = viPrintf(vi,"RI %d,%d\n",
                channel[cnt], iRangeId(channel[cnt],thisPtr->UNT[channel[cnt]-1],range[cnt]) );
            if ( errStatus < VI_SUCCESS) {
                agb1500_LOG_STATUS( vi, thisPtr, errStatus );
            }
        }
    }

    agb1500_CHK_INST_ERR( vi, thisPtr );


    errStatus = viPrintf(vi,"XE\n" );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_CHK_INST_ERR_AFTER_XE( vi, thisPtr );
    
   /* Read measurement data & timestamp data */
    eod = 0;
    chCnt = 0;
    for ( ;eod == 0;) {
        errStatus = asciiDataRead(vi,&dataKind,&getValue,&getStatus,NULL,&eod);
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
        if ( dataKind == agb1500_DT_TM) {
            time[chCnt] = getValue;
        }
        else {
            value[chCnt] = getValue;
            if ( status != (ViInt32 *)NULL )
                status[chCnt] = getStatus;
                chCnt++;
        }
    }
    for ( dmyCnt=chCnt; dmyCnt<chanNum; dmyCnt++ ) {
         value[dmyCnt] = agb1500_DUMMY_VALUE ;
         if ( status != (ViInt32 *)NULL )
              status[dmyCnt] = agb1500_DUMMY_STATUS ;
              if ( time != (ViReal64 *)NULL)
                  time[dmyCnt] = agb1500_DUMMY_TIMESTAMP ;
    }
    
    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_sweepIv(ViSession vi, 
                               ViInt32 channel, ViInt32 mode, ViReal64 range,
                               ViPInt32 point, ViReal64 source[], 
                               ViReal64 value[], ViInt32 status[],
                        ViReal64 time[])
/*****************************************************************************/
/*                                                                           */
/*      This function performs staircase sweep measurement, and returns      */
/*      the number of measurement points, sweep source data, measurement     */
/*      data, measurement status, and time stamp data.                       */
/*      Before executing this function, execute the agb1500_setIv function   */
/*      to set the primary sweep source.  Also execute the                   */
/*      agb1500_setSweepSync function if you use the synchronous sweep       */
/*      source.                                                              */
/*                                                                           */
/*      The parameter 'channel' specifies the measurement channel.           */
/*      The parameter 'mode' specifies the measurement mode.                 */
/*      The parameter 'range'  specifies the measurement ranging type.       */
/*      The parameter 'point' returns the number of measurement points.      */
/*      The parameter 'source[ ] ' returns the sweep source data.            */
/*      The parameter 'value[ ]' returns the measurement data.               */
/*      The parameter 'status[ ]' returns the measurement status.            */
/*      The parameter 'time[ ]' returns the time stamp data.                 */
/*                                                                           */
/*      The array size of source, value, status, and time must be the same   */
/*      together, and it must be greater than or equal to the number of      */
/*      sweep points defined by the agb1500_setIv function                   */
/*      ('point' parameter).                                                 */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      FMT                                                                  */
/*      TSC                                                                  */
/*      MM                                                                   */
/*      CMM                                                                  */
/*      RI                                                                   */
/*      RV                                                                   */
/*      XE                                                                   */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*                                                                           */
/*      channel    Channel number of the measurement channel.                */
/*                 Same as the slot number for the SMU.                      */                              
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_1      1     Channel 1                         */
/*                 agb1500_CH_2      2     Channel 2                         */
/*                 agb1500_CH_3      3     Channel 3                         */
/*                 agb1500_CH_4      4     Channel 4                         */
/*                 agb1500_CH_5      5     Channel 5                         */
/*                 agb1500_CH_6      6     Channel 6                         */
/*                 agb1500_CH_7      7     Channel 7                         */
/*                 agb1500_CH_8      8     Channel 8                         */
/*                 agb1500_CH_9		 9     Channel 9						 */
/*                 agb1500_CH_10	10	   Channel 10					     */
/*                                                                           */
/*       mode      Measurement mode.                                         */
/*                 Enter 1 for current measurement.                          */
/*                 Enter 2 for voltage measurement.                          */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value   Description                     */
/*                 agb1500_ IF_MODE   1     CURRENT OUTPUT                   */
/*                 agb1500_ VF_MODE   2     VOLTAGE OUTPUT                   */
/*                                                                           */
/*     range       Measurement ranging type.                                 */
/*                 For current output: 0, 1E-12 to 1.0                        */
/*                 For voltage output: 0, 0.5 to 200.0                       */
/*                 where,                                                    */
/*                 For auto ranging: Enter 0 (zero).                         */
/*                 For limited auto ranging: Enter positive value.           */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      point      Number of measurement points.                             */
/*                 Data Type:  ViPInt32                                      */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*     source[ ]   Sweep source data.                                        */
/*                 To disable the sweep source data output,                  */
/*                 set 0 (NULL pointer) instead of source.                   */
/*                 Data Type:  ViReal64 [ ]                                  */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*      value[ ]   Measurement data.                                         */
/*                 Data Type:  ViPReal64[ ]                                  */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*    status[ ]    Measurement status.To disable the status data output,     */
/*                 set 0 (NULL pointer) instead of status.                   */
/*                 Data Type:  ViPInt32[ ]                                   */
/*                 Input/Output:  OUT                                        */
/*                 Values:                                                   */
/*                 Name                  Value   Description                 */
/*                 agb1500_STAT_OVF_BIT   1     AD converter overflowed.     */
/*                 agb1500_STAT_OSC_BIT   2     One or more channels are     */
/*                                              oscillating.                 */
/*                 agb1500_STAT_OCC_BIT   3     Another channel reached      */
/*                                              compliance.                  */
/*                 agb1500_STAT_TCC_BIT   4     This channel reached         */
/*                                              compliance.                  */
/*                                                                           */
/*     time[ ]    Time stamp data (measurement start time).                  */
/*                To disable the time stamp data output, set 0 (NULL pointer)*/
/*                instead of array.                                          */
/*                Data Type:  ViPReal64[ ]                                   */
/*                Input/Output:  OUT                                         */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct    agb1500_globals    *thisPtr;
    int        cnt ;
    ViInt32        getStatus ;
    ViInt32        eod ;
    ViReal64    getValue ;
    ViInt32   dataKind;
   
    *point = 0;
    
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_sweepIv" );


    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( channel, agb1500_CH_1, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);

    agb1500_CHK_LONG_RANGE( mode, agb1500_IM_MODE, agb1500_VM_MODE, 
                           VI_ERROR_PARAMETER3);

    if ( fabs(range) > agb1500_AUTOR_BORDER ) {
        agb1500_CHK_REAL_RANGE( range, agb1500_RANGE_MIN, agb1500_RANGE_MAX, 
                               VI_ERROR_PARAMETER4);
    }


    /*--- Set Command ---*/
    if ( source == (ViReal64 *)NULL ) {

        errStatus = viPrintf(vi,"FMT 21,0\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }

    }
    else {

        errStatus = viPrintf(vi,"FMT 21,1\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }

    }

    if ( time == (ViReal64 *)NULL) {

        errStatus = viPrintf(vi,"TSC 0\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }
    else {

        errStatus = viPrintf(vi,"TSC 1\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }



    errStatus = viPrintf(vi,"MM 2,%d\n", channel );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }


    errStatus = viPrintf(vi,"CMM %d,%d\n", channel, mode );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    if ( mode == agb1500_VM_MODE ) {

        errStatus = viPrintf(vi,"RV %d,%d\n",
                channel, vRangeId(channel,thisPtr->UNT[channel-1],range));
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }
    else {

        errStatus = viPrintf(vi,"RI %d,%d\n", channel, iRangeId(channel,thisPtr->UNT[channel-1],range) );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }

    agb1500_CHK_INST_ERR( vi, thisPtr );


    errStatus = viPrintf(vi,"XE\n" );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_CHK_INST_ERR_AFTER_XE( vi, thisPtr );
   
    eod = 0;
    cnt = 0;

    do {        
        /*--- Read Time stamp Data ---*/       
        if ( time != (ViReal64 *)NULL) {
            if ( eod == 0) {
                errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
                if ( errStatus < VI_SUCCESS) {
                    agb1500_LOG_STATUS( vi, thisPtr, errStatus );
                }

                if ( dataKind == agb1500_DT_TM) {         
                    time[cnt] = getValue;
                }
                else {
                    return (agb1500_MEAS_DATA_INCONSISTENCY);
                }
            }
            else {
                time[cnt] = agb1500_DUMMY_TIMESTAMP;
            }
        }

        /*--- Read Measurement Data ---*/
        if (eod == 0) {
            errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
            if ( errStatus < VI_SUCCESS) {
                agb1500_LOG_STATUS( vi, thisPtr, errStatus );
            }
   
            if ( dataKind == agb1500_DT_VM || dataKind == agb1500_DT_IM) {         
                value[cnt] = getValue;
                /*--- Set Status ---*/
                if ( status != (ViInt32 *)NULL ) {
                    status[cnt] = getStatus ;
                }
            }
            else {
                return (agb1500_MEAS_DATA_INCONSISTENCY);
            }
        }
        else {
            value[cnt] = agb1500_DUMMY_VALUE;
            /*--- Set Status ---*/
            if ( status != (ViInt32 *)NULL ) {
                status[cnt] = agb1500_DUMMY_STATUS ;
            }
        }

        /*--- Read Source Data ---*/
        if ( source != (ViReal64 *)NULL) {
            if ( eod == 0) {
                errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
                if ( errStatus < VI_SUCCESS) {
                    agb1500_LOG_STATUS( vi, thisPtr, errStatus );
                }
  
                if ( dataKind == agb1500_DT_VS || dataKind == agb1500_DT_IS) {
                    source[cnt] = getValue;               
                }
                else {
                    return (agb1500_MEAS_DATA_INCONSISTENCY);
                }
            }
            else {
                source[cnt] = agb1500_DUMMY_VALUE;
            }
        }
         
        cnt++;
   
    } while(eod == 0);
        
    /*--- Set Point ---*/
    *point = cnt ;

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_sweepMiv(ViSession vi, 
                               ViInt32 channel[], ViInt32 mode[], 
                               ViReal64 range[],
                               ViPInt32 point, ViReal64 source[], 
                               ViReal64 value[], ViInt32 status[],
                        ViReal64 time[])
/*****************************************************************************/
/*                                                                           */
/*      This function performs staircase sweep measurement using up to       */
/*      8 SMUs at a time, and returns the number of measurement points,      */
/*      sweep source data, measurement data, measurement status, and time    */
/*      stamp data.                                                          */
/*      Before executing this function, execute the agb1500_setIv function   */
/*      to set the primary sweep source.  Also execute the                   */
/*      agb1500_setSweepSync function if you use the synchronous sweep       */
/*      source.                                                              */
/*                                                                           */
/*      The parameter 'channel[ ]' specifies the measurement channels.       */
/*      The parameter 'mode[ ]' specifies the measurement mode for           */
/*      each channel.                                                        */
/*      The parameter 'range[ ]' specifies the measurement ranging type      */
/*      for each channel.                                                    */
/*      The parameter 'point' returns the number of measurement points.      */
/*      The parameter 'source[ ]' returns the sweep source data.             */
/*      The parameter 'value[ ]' returns the measurement data.               */
/*      Two-dimensional array.                                               */
/*      The parameter 'status[ ]' returns the measurement status.            */
/*      Two-dimensional array.                                               */
/*      The parameter 'time[ ]' returns the time stamp data.                 */
/*      Two-dimensional array.                                               */
/*                                                                           */
/*      The parameters must be declared as shown below:                      */
/*      ViInt32    channel[N+1]                                              */
/*      ViInt32    mode[N]                                                   */
/*      ViReal64  range[N]                                                   */
/*      ViInt32    point                                                     */
/*      ViReal64  source[M]                                                  */
/*      ViReal64  value[M][N]                                                */
/*      ViReal64  status[M][N]                                               */
/*      ViReal64  times[M][N]                                                */
/*      where,                                                               */
/*      N: Number of measurement channels.                                   */
/*      M: Number of sweep points ('point' parameter value of                */
/*      agb1500_setIv function), or more.                                    */
/*                                                                           */
/*      For the parameter definition, the order of the array data is         */
/*      important.  For example, the measurement setup for the channel       */
/*      specified by channel[1] must be entered into mode[1] and range[1].   */
/*      And sweep source data, measurement data, status data, and time       */
/*      stamp data of the channel specified by channel[1] will be returned   */
/*      by source[M][1], value[M][1], status[M][1], and time[M][1],          */
/*      respectively.                                                        */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      FMT                                                                  */
/*      TSC                                                                  */
/*      MM                                                                   */
/*      CMM                                                                  */
/*      RI                                                                   */
/*      RV                                                                   */
/*      XE                                                                   */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*                                                                           */
/*   channel[ ]    Channel number of the measurement channel.                */
/*                 Same as the slot number for the SMU.                      */
/*                 At the end of the channel definitions, enter 0 (zero)     */
/*                 into the last array element.                              */
/*                 For example, if you use four measurement channels,        */
/*                 array size should be five, and 0 (zero) must be entered   */
/*                 into the fifth array element.                             */
/*                 Data Type:  ViInt32 [ ]                                   */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_1      1     Channel 1                         */
/*                 agb1500_CH_2      2     Channel 2                         */
/*                 agb1500_CH_3      3     Channel 3                         */
/*                 agb1500_CH_4      4     Channel 4                         */
/*                 agb1500_CH_5      5     Channel 5                         */
/*                 agb1500_CH_6      6     Channel 6                         */
/*                 agb1500_CH_7      7     Channel 7                         */
/*                 agb1500_CH_8      8     Channel 8                         */
/*                 agb1500_CH_9		 9	   Channel 9					     */
/*                 agb1500_CH_10    10     Channel 10						 */
/*                                                                           */
/*       mode[ ]   Measurement mode.                                         */
/*                 Enter 1 for current measurement.                          */
/*                 Enter 2 for voltage measurement.                          */
/*                 Data Type:  ViInt32[ ]                                    */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value   Description                     */
/*                 agb1500_ IF_MODE   1     CURRENT OUTPUT                   */
/*                 agb1500_ VF_MODE   2     VOLTAGE OUTPUT                   */
/*                                                                           */
/*     range[ ]    Measurement ranging type.                                 */
/*                 For current output: 0, 1E-12 to 1.0                        */
/*                 For voltage output: 0, 0.5 to 200.0                       */
/*                 where,                                                    */
/*                 For auto ranging: Enter 0 (zero).                         */
/*                 For limited auto ranging: Enter positive value.           */
/*                 Data Type:  ViReal64[ ]                                   */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      point      Number of measurement points.                             */
/*                 Data Type:  ViPInt32                                      */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*     source[ ]   Sweep source data.                                        */
/*                 To disable the sweep source data output,                  */
/*                 set 0 (NULL pointer) instead of source.                   */
/*                 Data Type:  ViReal64 [ ]                                  */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*      value[ ]   Measurement data.                                         */
/*                 Data Type:  ViPReal64[ ]                                  */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*    status[ ]    Measurement status.To disable the status data output,     */
/*                 set 0 (NULL pointer) instead of status.                   */
/*                 Data Type:  ViPInt32[ ]                                   */
/*                 Input/Output:  OUT                                        */
/*                 Values:                                                   */
/*                 Name                  Value   Description                 */
/*                 agb1500_STAT_OVF_BIT   1     AD converter overflowed.     */
/*                 agb1500_STAT_OSC_BIT   2     One or more channels are     */
/*                                              oscillating.                 */
/*                 agb1500_STAT_OCC_BIT   3     Another channel reached      */
/*                                              compliance.                  */
/*                 agb1500_STAT_TCC_BIT   4     This channel reached         */
/*                                              compliance.                  */
/*                                                                           */
/*     time[ ]    Time stamp data (measurement start time).                  */
/*                To disable the time stamp data output, set 0 (NULL pointer)*/
/*                instead of array.                                          */
/*                Data Type:  ViPReal64[ ]                                   */
/*                Input/Output:  OUT                                         */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct        agb1500_globals    *thisPtr;
    int            cnt ;
    int            chCnt ;
    ViInt32        getStatus ;
    ViInt32        eod ;
    ViInt32        dataKind;
    ViReal64       getValue ;
    ViInt32        chanNum ;
    ViChar         chChar[8] ;
    ViChar         chString[256] ;            

   
    *point = 0;
    
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }
    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_sweepMiv" );


    /* Check Prameter Range */
    for ( cnt=0; channel[cnt] != 0; cnt++ ) {
        agb1500_CHK_LONG_RANGE( channel[cnt], agb1500_CH_1, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);

        agb1500_CHK_LONG_RANGE( mode[cnt], agb1500_IM_MODE, agb1500_VM_MODE, 
                            VI_ERROR_PARAMETER3);

        if ( fabs(range[cnt]) > agb1500_AUTOR_BORDER ) {
            agb1500_CHK_REAL_RANGE( range[cnt], agb1500_RANGE_MIN, agb1500_RANGE_MAX,
                                    VI_ERROR_PARAMETER4);
        }
    }

    /*--- Channel Non Set ---*/
    if ( cnt == 0 ) {
         agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2 );
    }

    /*--- Get Chunnel Number ---*/
    chanNum = cnt ;

    /*--- Set Command ---*/
    if ( source == (ViReal64 *)NULL ) {

        errStatus = viPrintf(vi,"FMT 21,0\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }
    else {

        errStatus = viPrintf(vi,"FMT 21,1\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }
    if ( time == (ViReal64 *)NULL) {

        errStatus = viPrintf(vi,"TSC 0\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }
    else {

        errStatus = viPrintf(vi,"TSC 1\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }

    /*--- Edit Channel Number ---*/
    memset( chString, (char)NULL, sizeof(chString) );
    for ( cnt=0; cnt<chanNum; cnt++) {
        if ( cnt != 0 ) sprintf( chChar, ",%d", channel[cnt] );
        else            sprintf( chChar, "%d", channel[cnt] );
        strcat( chString, chChar );
    }

    errStatus = viPrintf(vi,"MM 2,%s\n", chString );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    for ( cnt=0; cnt<chanNum; cnt++ ) {

        errStatus = viPrintf(vi,"CMM %d,%d\n", channel[cnt], mode[cnt] );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }

        if ( mode[cnt] == agb1500_VM_MODE ) {

            errStatus = viPrintf(vi,"RV %d,%d\n",
                channel[cnt], vRangeId(channel[cnt],thisPtr->UNT[channel[cnt]-1],range[cnt]));
            if ( errStatus < VI_SUCCESS) {
                agb1500_LOG_STATUS( vi, thisPtr, errStatus );
            }
        }
        else {

            errStatus = viPrintf(vi,"RI %d,%d\n",
                channel[cnt], iRangeId(channel[cnt],thisPtr->UNT[channel[cnt]-1],range[cnt]) );
            if ( errStatus < VI_SUCCESS) {
                agb1500_LOG_STATUS( vi, thisPtr, errStatus );
            }
        }
    }

    agb1500_CHK_INST_ERR( vi, thisPtr );


    errStatus = viPrintf(vi,"XE\n" );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_CHK_INST_ERR_AFTER_XE( vi, thisPtr );

    eod = 0;
    cnt = 0;
    chCnt = 0;
   
    do {        
        for ( chCnt = 0 ;chCnt <chanNum  ; chCnt++) {

            /*--- Read Time stamp Data ---*/       
            if ( time != (ViReal64 *)NULL) {
                if ( eod == 0) {
                    errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
                    if ( errStatus < VI_SUCCESS) {
                        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
                    }
                    if ( dataKind == agb1500_DT_TM) {         
                        time[cnt*chanNum + chCnt] = getValue;
                    }
                    else {
                        return (agb1500_MEAS_DATA_INCONSISTENCY);
                    }
                }
                else {
                    time[cnt*chanNum +chCnt] = agb1500_DUMMY_TIMESTAMP;
                }
            }

            /*--- Read Measurement Data ---*/
            if (eod == 0) {
                errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
                if ( errStatus < VI_SUCCESS) {
                    agb1500_LOG_STATUS( vi, thisPtr, errStatus );
                }
   
                if ( dataKind == agb1500_DT_VM || dataKind == agb1500_DT_IM) {         
                    value[cnt*chanNum + chCnt] = getValue;
                    /*--- Set Status ---*/
                    if ( status != (ViInt32 *)NULL ) {
                        status[cnt*chanNum + chCnt] = getStatus ;
                    }
                }
                else {
                    return (agb1500_MEAS_DATA_INCONSISTENCY);
                }
            }
            else {
                value[cnt*chanNum +chCnt] = agb1500_DUMMY_VALUE;
                /*--- Set Status ---*/
                if ( status != (ViInt32 *)NULL ) {
                    status[cnt*chanNum + chCnt] = agb1500_DUMMY_STATUS ;
                }
            }
        }


        /*--- Read Source Data ---*/
        if ( source != (ViReal64 *)NULL) {
            if ( eod == 0) {
                errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
                if ( errStatus < VI_SUCCESS) {
                    agb1500_LOG_STATUS( vi, thisPtr, errStatus );
                }
         
                if ( dataKind == agb1500_DT_VS || dataKind == agb1500_DT_IS) {
                    source[cnt] = getValue;               
                }
                else {
                    return (agb1500_MEAS_DATA_INCONSISTENCY);
                }
            }
            else {
                source[cnt] = agb1500_DUMMY_VALUE;
            }
        }
         
        cnt++;
   
    } while(eod == 0);
  
    /*--- Set Point ---*/
    *point = cnt ;

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_measureP(ViSession vi, ViInt32 channel, 
                                  ViInt32 mode, ViReal64 range,
                                  ViPReal64 value, ViPInt32 status,
                                  ViPReal64 time)
/*****************************************************************************/
/*                                                                           */
/*      This function performs pulsed spot measurement, and returns the      */
/*      measurement data and the measurement status.                         */
/*                                                                           */
/*      The parameter 'channel' specifies the measurement channel.           */
/*      The parameter 'mode' specifies the measurement mode.                 */
/*      The parameter 'range' specifies the measurement ranging type.        */
/*      The parameter 'value' returns the measurement data.                  */
/*      The parameter 'status' returns the measurement status.               */
/*      The parameter 'time' returns the time stamp data.                    */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      FMT                                                                  */
/*      TSC                                                                  */
/*      MM                                                                   */
/*      CMM                                                                  */
/*      RI                                                                   */
/*      RV                                                                   */
/*      XE                                                                   */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*                                                                           */
/*      channel    Channel number of the channel.  Same as the slot number   */
/*                 for the SMU.                                              */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_1      1     Channel 1                         */
/*                 agb1500_CH_2      2     Channel 2                         */
/*                 agb1500_CH_3      3     Channel 3                         */
/*                 agb1500_CH_4      4     Channel 4                         */
/*                 agb1500_CH_5      5     Channel 5                         */
/*                 agb1500_CH_6      6     Channel 6                         */
/*                 agb1500_CH_7      7     Channel 7                         */
/*                 agb1500_CH_8      8     Channel 8                         */
/*                 agb1500_CH_9		 9	   Channel 9				    	 */
/*                 agb1500_CH_10	10     Channel 10                        */
/*                                                                           */
/*         mode    Select 1 for current output (available only for SMU).     */
/*                 Select 2 for voltage output.                              */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value   Description                     */
/*                 agb1500_ IF_MODE   1     CURRENT OUTPUT                   */
/*                 agb1500_ VF_MODE   2     VOLTAGE OUTPUT                   */
/*                                                                           */
/*        range    Output ranging type.                                      */
/*                 For current output: 0, 1E-12 to 1.0                        */
/*                 For voltage output: 0, 0.5 to 200.0                       */
/*                 where,                                                    */
/*                 For auto ranging: Enter 0 (zero).                         */
/*                 For limited auto ranging: Enter positive value.           */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*        value    Measurement data.                                         */
/*                 Data Type:  ViPReal64                                     */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*       status    Measurement status.To disable the status data output,     */
/*                 set 0 (NULL pointer) instead of variable.                 */
/*                 Data Type:  ViPInt32                                      */
/*                 Input/Output:  OUT                                        */
/*                 Values:                                                   */
/*                 Name                  Value   Description                 */
/*                 agb1500_STAT_OVF_BIT   1     AD converter overflowed.     */
/*                 agb1500_STAT_OSC_BIT   2     One or more channels are     */
/*                                              oscillating.                 */
/*                 agb1500_STAT_OCC_BIT   3     Another channel reached      */
/*                                              compliance.                  */
/*                 agb1500_STAT_TCC_BIT   4     This channel reached         */
/*                                              compliance.                  */
/*                                                                           */
/*        time    Time stamp data (measurement start time).                  */
/*                To disable the time stamp data output, set 0 (NULL pointer)*/
/*                instead of variable.                                       */
/*                Data Type:  ViPReal64                                      */
/*                Input/Output:  OUT                                         */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct    agb1500_globals    *thisPtr;
    ViInt32     getStatus ;
    ViInt32     eod ;
    ViReal64    getValue ;
    ViInt32     dataKind;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_measureP" );


    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( channel, agb1500_CH_1, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);

    agb1500_CHK_LONG_RANGE( mode, agb1500_IM_MODE, agb1500_VM_MODE, 
                           VI_ERROR_PARAMETER3);

    if ( fabs(range) > agb1500_AUTOR_BORDER ) {
        agb1500_CHK_REAL_RANGE( range, agb1500_RANGE_MIN, agb1500_RANGE_MAX,
                             VI_ERROR_PARAMETER4);
    }

    /*--- Set Command ---*/

    errStatus = viPrintf(vi,"FMT 21,0\n" );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    if ( time != (ViReal64 *)NULL) {

        errStatus = viPrintf(vi,"TSC 1\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }
    else {

         errStatus = viPrintf(vi,"TSC 0\n" );
         if ( errStatus < VI_SUCCESS) {
             agb1500_LOG_STATUS( vi, thisPtr, errStatus );
         }
    }

    errStatus = viPrintf(vi,"MM 3,%d\n", channel );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }


    errStatus = viPrintf(vi,"CMM %d,%d\n", channel, mode );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    if ( mode == agb1500_VM_MODE ) {

        errStatus = viPrintf(vi,"RV %d,%d\n",
                channel, vRangeId(channel,thisPtr->UNT[channel-1],range));
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }
    else {

        errStatus = viPrintf(vi,"RI %d,%d\n", channel, iRangeId(channel,thisPtr->UNT[channel-1],range) );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }

    agb1500_CHK_INST_ERR( vi, thisPtr );


    errStatus = viPrintf(vi,"XE\n" );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_CHK_INST_ERR_AFTER_XE( vi, thisPtr );

       /* Read measurement data & timestamp data */
    eod = 0;

    for ( ;eod == 0;) {
        errStatus = asciiDataRead(vi,&dataKind,&getValue,&getStatus,NULL,&eod);
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
        if ( dataKind == agb1500_DT_TM) {
            *time = getValue;
        }
        else {
            *value = getValue;
            if ( status != (ViInt32 *)NULL )
                *status= getStatus;
        }
    }
    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_sweepPiv(ViSession vi, 
                               ViInt32 channel, ViInt32 mode, ViReal64 range,
                               ViPInt32 point, ViReal64 source[], 
                               ViReal64 value[], ViInt32 status[],
                               ViReal64 time[])
/*****************************************************************************/
/*                                                                           */
/*      This function performs pulsed sweep measurement, and returns the     */
/*      number of measurement points, sweep source data, measurement value,  */
/*      measurement status, and time stamp data.                             */
/*      Before executing this function, execute the agb1500_setPiv function  */
/*      to set the pulse sweep source.  Also execute the agb1500_setSweepSync*/
/*      function if you use the synchronous sweep source.                    */
/*                                                                           */
/*      The parameter 'channel' specifies the measurement channel.           */
/*      The parameter 'mode' specifies the measurement mode.                 */
/*      The parameter 'range'  specifies the measurement ranging type.       */
/*      The parameter 'point' returns the number of measurement points.      */
/*      The parameter 'source[ ] ' returns the sweep source data.            */
/*      The parameter 'value[ ]' returns the measurement data.               */
/*      The parameter 'status[ ]' returns the measurement status.            */
/*      The parameter 'time[ ]' returns the time stamp data.                 */
/*                                                                           */
/*      The array size of source, value, status, and time must be the same   */
/*      together, and it must be greater than or equal to the number of      */
/*      sweep points defined by the agb1500_setPiv function                  */
/*      ('point' parameter).                                                 */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      FMT                                                                  */
/*      TSC                                                                  */
/*      MM                                                                   */
/*      CMM                                                                  */
/*      RI                                                                   */
/*      RV                                                                   */
/*      XE                                                                   */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*                                                                           */
/*      channel    Channel number of the measurement channel.                */
/*                 Same as the slot number for the SMU.                      */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_1      1     Channel 1                         */
/*                 agb1500_CH_2      2     Channel 2                         */
/*                 agb1500_CH_3      3     Channel 3                         */
/*                 agb1500_CH_4      4     Channel 4                         */
/*                 agb1500_CH_5      5     Channel 5                         */
/*                 agb1500_CH_6      6     Channel 6                         */
/*                 agb1500_CH_7      7     Channel 7                         */
/*                 agb1500_CH_8      8     Channel 8                         */
/*                 agb1500_CH_9		 9	   Channel 9						 */
/*                 agb1500_CH_10    10     Channel 10					     */
/*                                                                           */
/*       mode      Measurement mode.                                         */
/*                 Enter 1 for current measurement.                          */
/*                 Enter 2 for voltage measurement.                          */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value   Description                     */
/*                 agb1500_ IF_MODE   1     CURRENT OUTPUT                   */
/*                 agb1500_ VF_MODE   2     VOLTAGE OUTPUT                   */
/*                                                                           */
/*     range       Measurement ranging type.                                 */
/*                 For current output: 0, 1E-12 to 1.0                        */
/*                 For voltage output: 0, 0.5 to 200.0                       */
/*                 where,                                                    */
/*                 For auto ranging: Enter 0 (zero).                         */
/*                 For limited auto ranging: Enter positive value.           */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      point      Number of measurement points.                             */
/*                 Data Type:  ViPInt32                                      */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*     source[ ]   Sweep source data.                                        */
/*                 To disable the sweep source data output,                  */
/*                 set 0 (NULL pointer) instead of source.                   */
/*                 Data Type:  ViReal64 [ ]                                  */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*      value[ ]   Measurement data.                                         */
/*                 Data Type:  ViPReal64[ ]                                  */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*    status[ ]    Measurement status.To disable the status data output,     */
/*                 set 0 (NULL pointer) instead of status.                   */
/*                 Data Type:  ViPInt32[ ]                                   */
/*                 Input/Output:  OUT                                        */
/*                 Values:                                                   */
/*                 Name                  Value   Description                 */
/*                 agb1500_STAT_OVF_BIT   1     AD converter overflowed.     */
/*                 agb1500_STAT_OSC_BIT   2     One or more channels are     */
/*                                              oscillating.                 */
/*                 agb1500_STAT_OCC_BIT   3     Another channel reached      */
/*                                              compliance.                  */
/*                 agb1500_STAT_TCC_BIT   4     This channel reached         */
/*                                              compliance.                  */
/*                                                                           */
/*     time[ ]    Time stamp data (measurement start time).                  */
/*                To disable the time stamp data output, set 0 (NULL pointer)*/
/*                instead of array.                                          */
/*                Data Type:  ViPReal64[ ]                                   */
/*                Input/Output:  OUT                                         */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct    agb1500_globals    *thisPtr;
    int        cnt ;
    ViInt32    getStatus ;
    ViInt32    eod ;
    ViReal64   getValue ;
    ViInt32    dataKind ;
    *point = 0;
    
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_sweepPiv" );


    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( channel, agb1500_CH_1, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);

    agb1500_CHK_LONG_RANGE( mode, agb1500_IM_MODE, agb1500_VM_MODE, 
                           VI_ERROR_PARAMETER3);

    if ( fabs(range) > agb1500_AUTOR_BORDER ) {
        agb1500_CHK_REAL_RANGE( range, agb1500_RANGE_MIN, agb1500_RANGE_MAX, 
                             VI_ERROR_PARAMETER4);
    }


    /*--- Set Command ---*/
    if ( source == (ViReal64 *)NULL ) {

        errStatus = viPrintf(vi,"FMT 21,0\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }
    else {

        errStatus = viPrintf(vi,"FMT 21,1\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }

    if ( time == (ViReal64 *)NULL) {

        errStatus = viPrintf(vi,"TSC 0\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }
    else {

        errStatus = viPrintf(vi,"TSC 1\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }


    errStatus = viPrintf(vi,"MM 4,%d\n", channel );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }


    errStatus = viPrintf(vi,"CMM %d,%d\n", channel, mode );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    if ( mode == agb1500_VM_MODE ) {

        errStatus = viPrintf(vi,"RV %d,%d\n",
                channel, vRangeId(channel,thisPtr->UNT[channel-1],range));
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }
    else {

        errStatus = viPrintf(vi,"RI %d,%d\n", channel, iRangeId(channel,thisPtr->UNT[channel-1],range) );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }

    agb1500_CHK_INST_ERR( vi, thisPtr );


    errStatus = viPrintf(vi,"XE\n" );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_CHK_INST_ERR_AFTER_XE( vi, thisPtr );

    eod = 0;
    cnt = 0;
   
    do {        
         /*--- Read Time stamp Data ---*/       
        if ( time != (ViReal64 *)NULL) {
            if ( eod == 0) {
                errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
                if ( errStatus < VI_SUCCESS) {
                    agb1500_LOG_STATUS( vi, thisPtr, errStatus );
                }
   
                if ( dataKind == agb1500_DT_TM) {         
                    time[cnt] = getValue;
                }
                else {
                    return (agb1500_MEAS_DATA_INCONSISTENCY);
                }
            }
            else {
                time[cnt] = agb1500_DUMMY_TIMESTAMP;
            }
        }

        /*--- Read Measurement Data ---*/
        if ( eod == 0) {
             errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
             if ( errStatus < VI_SUCCESS) {
                 agb1500_LOG_STATUS( vi, thisPtr, errStatus );
             }
             if ( dataKind == agb1500_DT_VM || dataKind == agb1500_DT_IM) {         
                 value[cnt] = getValue;
                 /*--- Set Status ---*/
                 if ( status != (ViInt32 *)NULL ) {
                     status[cnt] = getStatus ;
                 }
             }
             else {
                 return (agb1500_MEAS_DATA_INCONSISTENCY);
             }
         }
         else {
             value[cnt] = agb1500_DUMMY_VALUE;
             /*--- Set Status ---*/
             if ( status != (ViInt32 *)NULL ) {
                 status[cnt] = agb1500_DUMMY_STATUS ;
             }
         }
      
         /*--- Read Source Data ---*/
         if ( source != (ViReal64 *)NULL) {
             if ( eod == 0) {
                 errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
                 if ( errStatus < VI_SUCCESS) {
                     agb1500_LOG_STATUS( vi, thisPtr, errStatus );
                 }
                 if ( dataKind == agb1500_DT_VS || dataKind == agb1500_DT_IS) {
                     source[cnt] = getValue;               
                 }
                 else {
                     return (agb1500_MEAS_DATA_INCONSISTENCY);
                 }
            }
            else {
                source[cnt] = agb1500_DUMMY_VALUE;
            }
        }
         
        cnt++;
   
    } while(eod == 0);

    /*--- Set Point ---*/
    *point = cnt ;

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_sweepPbias(ViSession vi, 
                               ViInt32 channel, ViInt32 mode, ViReal64 range,
                               ViPInt32 point, ViReal64 source[], 
                               ViReal64 value[], ViInt32 status[],
                        ViReal64 time[])
/*****************************************************************************/
/*                                                                           */
/*      This function performs staircase sweep with pulsed bias measurement, */
/*      and returns the number of measurement points, sweep source data,     */
/*      measurement data, measurement status, and time stamp data.           */
/*      Before executing this function, execute the agb1500_setIv function   */
/*      to set the primary sweep source, and execute the agb1500_setPbias    */
/*      function to set the pulse source.  Also execute the                  */
/*      agb1500_setSweepSync function if you use the synchronous sweep       */
/*      source.                                                              */
/*                                                                           */
/*      The parameter 'channel' specifies the measurement channel.           */
/*      The parameter 'mode' specifies the measurement mode.                 */
/*      The parameter 'range'  specifies the measurement ranging type.       */
/*      The parameter 'point' returns the number of measurement points.      */
/*      The parameter 'source[ ] ' returns the sweep source data.            */
/*      The parameter 'value[ ]' returns the measurement data.               */
/*      The parameter 'status[ ]' returns the measurement status.            */
/*      The parameter 'time[ ]' returns the time stamp data.                 */
/*                                                                           */
/*      The array size of source, value, status, and time must be the same   */
/*      together, and it must be greater than or equal to the number of      */
/*      sweep points defined by the agb1500_setIv function                   */
/*      ('point' parameter).                                                 */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      FMT                                                                  */
/*      TSC                                                                  */
/*      MM                                                                   */
/*      CMM                                                                  */
/*      RI                                                                   */
/*      RV                                                                   */
/*      XE                                                                   */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*                                                                           */
/*      channel    Channel number of the measurement channel.                */
/*                 Same as the slot number for the SMU.                      */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_1      1     Channel 1                         */
/*                 agb1500_CH_2      2     Channel 2                         */
/*                 agb1500_CH_3      3     Channel 3                         */
/*                 agb1500_CH_4      4     Channel 4                         */
/*                 agb1500_CH_5      5     Channel 5                         */
/*                 agb1500_CH_6      6     Channel 6                         */
/*                 agb1500_CH_7      7     Channel 7                         */
/*                 agb1500_CH_8      8     Channel 8                         */
/*                 agb1500_CH_9		 9	   Channel 9						 */
/*				   agb1500_CH_10	10	   Channel 10					     */
/*                                                                           */
/*       mode      Measurement mode.                                         */
/*                 Enter 1 for current measurement.                          */
/*                 Enter 2 for voltage measurement.                          */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value   Description                     */
/*                 agb1500_ IF_MODE   1     CURRENT OUTPUT                   */
/*                 agb1500_ VF_MODE   2     VOLTAGE OUTPUT                   */
/*                                                                           */
/*     range       Measurement ranging type.                                 */
/*                 For current output: 0, 1E-12 to 1.0                        */
/*                 For voltage output: 0, 0.5 to 200.0                       */
/*                 where,                                                    */
/*                 For auto ranging: Enter 0 (zero).                         */
/*                 For limited auto ranging: Enter positive value.           */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      point      Number of measurement points.                             */
/*                 Data Type:  ViPInt32                                      */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*     source[ ]   Sweep source data.                                        */
/*                 To disable the sweep source data output,                  */
/*                 set 0 (NULL pointer) instead of source.                   */
/*                 Data Type:  ViReal64 [ ]                                  */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*      value[ ]   Measurement data.                                         */
/*                 Data Type:  ViPReal64[ ]                                  */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*    status[ ]    Measurement status.To disable the status data output,     */
/*                 set 0 (NULL pointer) instead of status.                   */
/*                 Data Type:  ViPInt32[ ]                                   */
/*                 Input/Output:  OUT                                        */
/*                 Values:                                                   */
/*                 Name                  Value   Description                 */
/*                 agb1500_STAT_OVF_BIT   1     AD converter overflowed.     */
/*                 agb1500_STAT_OSC_BIT   2     One or more channels are     */
/*                                              oscillating.                 */
/*                 agb1500_STAT_OCC_BIT   3     Another channel reached      */
/*                                              compliance.                  */
/*                 agb1500_STAT_TCC_BIT   4     This channel reached         */
/*                                              compliance.                  */
/*                                                                           */
/*     time[ ]    Time stamp data (measurement start time).                  */
/*                To disable the time stamp data output, set 0 (NULL pointer)*/
/*                instead of array.                                          */
/*                Data Type:  ViPReal64[ ]                                   */
/*                Input/Output:  OUT                                         */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct    agb1500_globals    *thisPtr;
    int            cnt ;
    ViInt32        getStatus ;
    ViInt32        eod ;
    ViReal64       getValue ;
    ViInt32        dataKind ;
    *point = 0;
    
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_sweepPbias" );


    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( channel, agb1500_CH_1, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);

    agb1500_CHK_LONG_RANGE( mode, agb1500_IM_MODE, agb1500_VM_MODE, 
                           VI_ERROR_PARAMETER3);

    if ( fabs(range) > agb1500_AUTOR_BORDER ) {
        agb1500_CHK_REAL_RANGE( range, agb1500_RANGE_MIN, agb1500_RANGE_MAX, 
                             VI_ERROR_PARAMETER4);
    }


    /*--- Set Command ---*/
    if ( source == (ViReal64 *)NULL ) {

        errStatus = viPrintf(vi,"FMT 21,0\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }

    }
    else {

        errStatus = viPrintf(vi,"FMT 21,1\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }

    if ( time == (ViReal64 *)NULL) {

        errStatus = viPrintf(vi,"TSC 0\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }
    else {

        errStatus = viPrintf(vi,"TSC 1\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }


    errStatus = viPrintf(vi,"MM 5,%d\n", channel );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }


    errStatus = viPrintf(vi,"CMM %d,%d\n", channel, mode );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    if ( mode == agb1500_VM_MODE ) {

        errStatus = viPrintf(vi,"RV %d,%d\n",
                channel, vRangeId(channel,thisPtr->UNT[channel-1],range));
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }
    else {

        errStatus = viPrintf(vi,"RI %d,%d\n", channel, iRangeId(channel,thisPtr->UNT[channel-1],range) );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }

    agb1500_CHK_INST_ERR( vi, thisPtr );


    errStatus = viPrintf(vi,"XE\n" );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }
    agb1500_CHK_INST_ERR_AFTER_XE( vi, thisPtr );

    eod = 0;
    cnt = 0;
   
    do {        
        /*--- Read Time stamp Data ---*/       
        if ( time != (ViReal64 *)NULL) {
            if ( eod == 0) {
                errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
                if ( errStatus < VI_SUCCESS) {
                    agb1500_LOG_STATUS( vi, thisPtr, errStatus );
                }
   
                if ( dataKind == agb1500_DT_TM) {         
                    time[cnt] = getValue;
                }
                else {
                    return (agb1500_MEAS_DATA_INCONSISTENCY);
                }
            }
            else {
                time[cnt] = agb1500_DUMMY_TIMESTAMP;
            }
        }

        /*--- Read Measurement Data ---*/
        if ( eod == 0) {
            errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
            if ( errStatus < VI_SUCCESS) {
                agb1500_LOG_STATUS( vi, thisPtr, errStatus );
            }
   
            if ( dataKind == agb1500_DT_VM || dataKind == agb1500_DT_IM) {         
                value[cnt] = getValue;
                /*--- Set Status ---*/
                if ( status != (ViInt32 *)NULL ) {
                    status[cnt] = getStatus ;
                }
            }
            else {
                return (agb1500_MEAS_DATA_INCONSISTENCY);
            }
        }
        else {
            value[cnt] = agb1500_DUMMY_VALUE;
            /*--- Set Status ---*/
            if ( status != (ViInt32 *)NULL ) {
                status[cnt] = agb1500_DUMMY_STATUS ;
            }
        }
      

        /*--- Read Source Data ---*/
        if ( source != (ViReal64 *)NULL) {
            if ( eod == 0) {
                errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
                if ( errStatus < VI_SUCCESS) {
                    agb1500_LOG_STATUS( vi, thisPtr, errStatus );
                }
         
                if ( dataKind == agb1500_DT_VS || dataKind == agb1500_DT_IS) {
                    source[cnt] = getValue;               
                }
                else {
                   return (agb1500_MEAS_DATA_INCONSISTENCY);
                }
            }
            else {
                source[cnt] = agb1500_DUMMY_VALUE;
            }
        }
         
        cnt++;
   
    } while(eod == 0);   
   
    /*--- Set Point ---*/
    *point = cnt ;

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_msweepIv(ViSession vi, 
                               ViInt32 channel, ViInt32 mode, ViReal64 range,
                               ViPInt32 point, ViReal64 source[], 
                               ViReal64 value[], ViInt32 status[],
                               ViReal64 time[])
/*****************************************************************************/
/*                                                                           */
/*      This function performs sweep measurement, and returns the number of  */
/*      measurement points, sweep source data, measurement data, measurement */
/*      status, and the time stamp data.  Before executing this function,    */
/*      the sweep source setup function must be executed. To set the primary */
/*      sweep source, execute the agb1500_setIv function.  To set an         */
/*      synchronous sweep source, execute the agb1500_setNthSweep function.  */
/*      Up to 7 synchronous sweep sources can be set by executing the        */
/*      agb1500_setNthSweep function for each channel                        */
/*                                                                           */
/*      The parameter 'channel' specifies the measurement channel.           */
/*      The parameter 'mode' specifies the measurement mode.                 */
/*      The parameter 'range'  specifies the measurement ranging type.       */
/*      The parameter 'point' returns the number of measurement points.      */
/*      The parameter 'source[ ] ' returns the sweep source data.            */
/*      The parameter 'value[ ]' returns the measurement data.               */
/*      The parameter 'status[ ]' returns the measurement status.            */
/*      The parameter 'time[ ]' returns the time stamp data.                 */
/*                                                                           */
/*      The array size of source, value, status, and time must be the same   */
/*      together, and it must be greater than or equal to the number of      */
/*      sweep points defined by the agb1500_setIv function                   */
/*      ('point' parameter).                                                 */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      FMT                                                                  */
/*      TSC                                                                  */
/*      MM                                                                   */
/*      CMM                                                                  */
/*      RI                                                                   */
/*      RV                                                                   */
/*      XE                                                                   */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*                                                                           */
/*      channel    Channel number of the measurement channel.                */
/*                 Same as the slot number for the SMU.                      */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_1      1     Channel 1                         */
/*                 agb1500_CH_2      2     Channel 2                         */
/*                 agb1500_CH_3      3     Channel 3                         */
/*                 agb1500_CH_4      4     Channel 4                         */
/*                 agb1500_CH_5      5     Channel 5                         */
/*                 agb1500_CH_6      6     Channel 6                         */
/*                 agb1500_CH_7      7     Channel 7                         */
/*                 agb1500_CH_8      8     Channel 8                         */
/*                 agb1500_CH_9      9     Channel 9						 */
/*                 agb1500_CH_10    10     Channel 10                        */
/*                                                                           */
/*       mode      Measurement mode.                                         */
/*                 Enter 1 for current measurement.                          */
/*                 Enter 2 for voltage measurement.                          */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value   Description                     */
/*                 agb1500_ IF_MODE   1     CURRENT OUTPUT                   */
/*                 agb1500_ VF_MODE   2     VOLTAGE OUTPUT                   */
/*                                                                           */
/*     range       Measurement ranging type.                                 */
/*                 For current output: 0, 1E-12 to 1.0                       */
/*                 For voltage output: 0, 0.5 to 200.0                       */
/*                 where,                                                    */
/*                 For auto ranging: Enter 0 (zero).                         */
/*                 For limited auto ranging: Enter positive value.           */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      point      Number of measurement points.                             */
/*                 Data Type:  ViPInt32                                      */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*     source[ ]   Sweep source data.                                        */
/*                 To disable the sweep source data output,                  */
/*                 set 0 (NULL pointer) instead of source.                   */
/*                 Data Type:  ViReal64 [ ]                                  */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*      value[ ]   Measurement data.                                         */
/*                 Data Type:  ViPReal64[ ]                                  */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*    status[ ]    Measurement status.To disable the status data output,     */
/*                 set 0 (NULL pointer) instead of status.                   */
/*                 Data Type:  ViPInt32[ ]                                   */
/*                 Input/Output:  OUT                                        */
/*                 Values:                                                   */
/*                 Name                  Value   Description                 */
/*                 agb1500_STAT_OVF_BIT   1     AD converter overflowed.     */
/*                 agb1500_STAT_OSC_BIT   2     One or more channels are     */
/*                                              oscillating.                 */
/*                 agb1500_STAT_OCC_BIT   3     Another channel reached      */
/*                                              compliance.                  */
/*                 agb1500_STAT_TCC_BIT   4     This channel reached         */
/*                                              compliance.                  */
/*                                                                           */
/*     time[ ]    Time stamp data (measurement start time).                  */
/*                To disable the time stamp data output, set 0 (NULL pointer)*/
/*                instead of array.                                          */
/*                Data Type:  ViPReal64[ ]                                   */
/*                Input/Output:  OUT                                         */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct    agb1500_globals    *thisPtr;
    int        cnt ;
    ViInt32     getStatus ;
    ViInt32     eod ;
    ViReal64    getValue ;
    ViInt32     dataKind;

    *point = 0;
    
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_msweepIv" );


    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( channel, agb1500_CH_1, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);

    agb1500_CHK_LONG_RANGE( mode, agb1500_IM_MODE, agb1500_VM_MODE, 
                           VI_ERROR_PARAMETER3);

    if ( fabs(range) > agb1500_AUTOR_BORDER ) {
        agb1500_CHK_REAL_RANGE( range, agb1500_RANGE_MIN, agb1500_RANGE_MAX, 
                               VI_ERROR_PARAMETER4);
    }


    /*--- Set Command ---*/
    if ( source == (ViReal64 *)NULL ) {

        errStatus = viPrintf(vi,"FMT 21,0\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }
    else {

        errStatus = viPrintf(vi,"FMT 21,1\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }

    if ( time == (ViReal64 *)NULL) {

        errStatus = viPrintf(vi,"TSC 0\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }
    else {

        errStatus = viPrintf(vi,"TSC 1\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }


    errStatus = viPrintf(vi,"MM 16,%d\n", channel );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }


        errStatus = viPrintf(vi,"CMM %d,%d\n", channel, mode );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }

    if ( mode == agb1500_VM_MODE ) {

        errStatus = viPrintf(vi,"RV %d,%d\n",
                channel, vRangeId(channel,thisPtr->UNT[channel-1],range));
        if ( errStatus < VI_SUCCESS) {
             agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }
    else {

        errStatus = viPrintf(vi,"RI %d,%d\n", channel, iRangeId(channel,thisPtr->UNT[channel-1],range) );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }

    agb1500_CHK_INST_ERR( vi, thisPtr );


    errStatus = viPrintf(vi,"XE\n" );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_CHK_INST_ERR_AFTER_XE( vi, thisPtr );

    eod = 0;
    cnt = 0;
   
    do {        
        /*--- Read Time stamp Data ---*/       
        if ( time != (ViReal64 *)NULL) {
            if ( eod == 0) {
                errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
                if ( errStatus < VI_SUCCESS) {
                    agb1500_LOG_STATUS( vi, thisPtr, errStatus );
                }
   
                if ( dataKind == agb1500_DT_TM) {         
                    time[cnt] = getValue;
                }
                else {
                    return (agb1500_MEAS_DATA_INCONSISTENCY);
                }
            }
            else {
                time[cnt] = agb1500_DUMMY_TIMESTAMP;
            }
        }

        /*--- Read Measurement Data ---*/
        if ( eod == 0) {
            errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
            if ( errStatus < VI_SUCCESS) {
                agb1500_LOG_STATUS( vi, thisPtr, errStatus );
            }
   
            if ( dataKind == agb1500_DT_VM || dataKind == agb1500_DT_IM) {         
                value[cnt] = getValue;
                /*--- Set Status ---*/
                if ( status != (ViInt32 *)NULL ) {
                    status[cnt] = getStatus ;
                }
            }
            else {
                return (agb1500_MEAS_DATA_INCONSISTENCY);
            }
        }
        else {
            value[cnt] = agb1500_DUMMY_VALUE;
            /*--- Set Status ---*/
            if ( status != (ViInt32 *)NULL ) {
                status[cnt] = agb1500_DUMMY_STATUS ;
            }
        }
   

        /*--- Read Source Data ---*/
        if ( source != (ViReal64 *)NULL) {
            if ( eod == 0) {
                errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
                if ( errStatus < VI_SUCCESS) {
                    agb1500_LOG_STATUS( vi, thisPtr, errStatus );
                }
         
                if ( dataKind == agb1500_DT_VS || dataKind == agb1500_DT_IS) {
                    source[cnt] = getValue;               
                }
                else {
                    return (agb1500_MEAS_DATA_INCONSISTENCY);
                }
            }
            else {
                source[cnt] = agb1500_DUMMY_VALUE;
            }
        }
         
        cnt++;
   
    } while(eod == 0);

    /*--- Set Point ---*/
    *point = cnt ;

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_msweepMiv(ViSession vi, 
                               ViInt32 channel[], ViInt32 mode[], 
                               ViReal64 range[],
                               ViPInt32 point, ViReal64 source[], 
                               ViReal64 value[], ViInt32 status[],
                        ViReal64 time[])
/*****************************************************************************/
/*                                                                           */
/*      This function performs multi-channel sweep measurement using up to   */
/*      8 SMUs at a time, and returns the number of measurement points,      */
/*      sweep source data, measurement data, measurement status, and the     */
/*      time stamp data.  Before executing this function, the sweep source   */
/*      setup function must be executed. To set the primary sweep source,    */
/*      execute the agb1500_setIv function.  To set an synchronous sweep     */
/*      source, execute the agb1500_setNthSweep function.  Up to 9           */
/*      synchronous sweep sources can be set by executing the                */
/*      agb1500_setNthSweep function for each channel.                       */
/*                                                                           */
/*      The parameter 'channel[ ]' specifies the measurement channels.       */
/*      The parameter 'mode[ ]' specifies the measurement mode for           */
/*      each channel.                                                        */
/*      The parameter 'range[ ]' specifies the measurement ranging type      */
/*      for each channel.                                                    */
/*      The parameter 'point' returns the number of measurement points.      */
/*      The parameter 'source[ ]' returns the sweep source data.             */
/*      The parameter 'value[ ]' returns the measurement data.               */
/*      Two-dimensional array.                                               */
/*      The parameter 'status[ ]' returns the measurement status.            */
/*      Two-dimensional array.                                               */
/*      The parameter 'time[ ]' returns the time stamp data.                 */
/*      Two-dimensional array.                                               */
/*                                                                           */
/*      The parameters must be declared as shown below:                      */
/*      ViInt32    channel[N+1]                                              */
/*      ViInt32    mode[N]                                                   */
/*      ViReal64  range[N]                                                   */
/*      ViInt32    point                                                     */
/*      ViReal64  source[M]                                                  */
/*      ViReal64  value[M][N]                                                */
/*      ViReal64  status[M][N]                                               */
/*      ViReal64  times[M][N]                                                */
/*      where,                                                               */
/*      N: Number of measurement channels.                                   */
/*      M: Number of sweep points ('point' parameter value of                */
/*      agb1500_setIv function), or more.                                    */
/*                                                                           */
/*      For the parameter definition, the order of the array data is         */
/*      important.  For example, the measurement setup for the channel       */
/*      specified by channel[1] must be entered into mode[1] and range[1].   */
/*      And sweep source data, measurement data, status data, and time       */
/*      stamp data of the channel specified by channel[1] will be returned   */
/*      by source[M][1], value[M][1], status[M][1], and time[M][1],          */
/*      respectively.                                                        */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      FMT                                                                  */
/*      TSC                                                                  */
/*      MM                                                                   */
/*      CMM                                                                  */
/*      RI                                                                   */
/*      RV                                                                   */
/*      XE                                                                   */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*                                                                           */
/*   channel[ ]    Channel number of the measurement channel.                */
/*                 Same as the slot number for the SMU.                      */
/*                 At the end of the channel definitions, enter 0 (zero)     */
/*                 into the last array element.                              */
/*                 For example, if you use four measurement channels,        */
/*                 array size should be five, and 0 (zero) must be entered   */
/*                 into the fifth array element.                             */
/*                 Data Type:  ViInt32 [ ]                                   */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_1      1     Channel 1                         */
/*                 agb1500_CH_2      2     Channel 2                         */
/*                 agb1500_CH_3      3     Channel 3                         */
/*                 agb1500_CH_4      4     Channel 4                         */
/*                 agb1500_CH_5      5     Channel 5                         */
/*                 agb1500_CH_6      6     Channel 6                         */
/*                 agb1500_CH_7      7     Channel 7                         */
/*                 agb1500_CH_8      8     Channel 8                         */
/*                 agb1500_CH_9      9     Channel 9                         */
/*                 agb1500_CH_10    10     Channel 10                        */
/*                                                                           */
/*       mode[ ]   Measurement mode.                                         */
/*                 Enter 1 for current measurement.                          */
/*                 Enter 2 for voltage measurement.                          */
/*                 Data Type:  ViInt32[ ]                                    */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value   Description                     */
/*                 agb1500_ IF_MODE   1     CURRENT OUTPUT                   */
/*                 agb1500_ VF_MODE   2     VOLTAGE OUTPUT                   */
/*                                                                           */
/*     range[ ]    Measurement ranging type.                                 */
/*                 For current output: 0, 1E-12 to 1.0                        */
/*                 For voltage output: 0, 0.5 to 200.0                       */
/*                 where,                                                    */
/*                 For auto ranging: Enter 0 (zero).                         */
/*                 For limited auto ranging: Enter positive value.           */
/*                 Data Type:  ViReal64[ ]                                   */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      point      Number of measurement points.                             */
/*                 Data Type:  ViPInt32                                      */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*     source[ ]   Sweep source data.                                        */
/*                 To disable the sweep source data output,                  */
/*                 set 0 (NULL pointer) instead of source.                   */
/*                 Data Type:  ViReal64 [ ]                                  */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*      value[ ]   Measurement data.                                         */
/*                 Data Type:  ViPReal64[ ]                                  */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*    status[ ]    Measurement status.To disable the status data output,     */
/*                 set 0 (NULL pointer) instead of status.                   */
/*                 Data Type:  ViPInt32[ ]                                   */
/*                 Input/Output:  OUT                                        */
/*                 Values:                                                   */
/*                 Name                  Value   Description                 */
/*                 agb1500_STAT_OVF_BIT   1     AD converter overflowed.     */
/*                 agb1500_STAT_OSC_BIT   2     One or more channels are     */
/*                                              oscillating.                 */
/*                 agb1500_STAT_OCC_BIT   3     Another channel reached      */
/*                                              compliance.                  */
/*                 agb1500_STAT_TCC_BIT   4     This channel reached         */
/*                                              compliance.                  */
/*                                                                           */
/*     time[ ]    Time stamp data (measurement start time).                  */
/*                To disable the time stamp data output, set 0 (NULL pointer)*/
/*                instead of array.                                          */
/*                Data Type:  ViPReal64[ ]                                   */
/*                Input/Output:  OUT                                         */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/ 
{
    ViStatus errStatus = 0 ;
    struct         agb1500_globals    *thisPtr;
    int            cnt ;
    int            chCnt ;
    ViInt32        getStatus ;
    ViInt32        eod ;
    ViReal64       getValue ;
    ViInt32        chanNum ;
    ViChar         chChar[8] ;
    ViChar         chString[256] ;            
    ViInt32        dataKind;
   
    *point = 0;
    
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_msweepMiv" );


    /* Check Prameter Range */
    for ( cnt=0; channel[cnt] != 0; cnt++ ) {
         agb1500_CHK_LONG_RANGE( channel[cnt], agb1500_CH_1, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);

         agb1500_CHK_LONG_RANGE( mode[cnt], agb1500_IM_MODE, agb1500_VM_MODE, 
                            VI_ERROR_PARAMETER3);

         if ( fabs(range[cnt]) > agb1500_AUTOR_BORDER ) {
             agb1500_CHK_REAL_RANGE( range[cnt], agb1500_RANGE_MIN, agb1500_RANGE_MAX,
                                    VI_ERROR_PARAMETER4);
         }
    }

    /*--- Channel Non Set ---*/
    if ( cnt == 0 ) {
        agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2 );
    }

    /*--- Get Chunnel Number ---*/
    chanNum = cnt ;

    /*--- Set Command ---*/
    if ( source == (ViReal64 *)NULL ) {

        errStatus = viPrintf(vi,"FMT 21,0\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }

    }
    else {

        errStatus = viPrintf(vi,"FMT 21,1\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }

    }

    if ( time == (ViReal64 *)NULL) {

        errStatus = viPrintf(vi,"TSC 0\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }
    else {

        errStatus = viPrintf(vi,"TSC 1\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }

    /*--- Edit Channel Number ---*/
    memset( chString, (char)NULL, sizeof(chString) );
    for ( cnt=0; cnt<chanNum; cnt++) {
        if ( cnt != 0 ) sprintf( chChar, ",%d", channel[cnt] );
        else            sprintf( chChar, "%d", channel[cnt] );
        strcat( chString, chChar );
    }

    errStatus = viPrintf(vi,"MM 16,%s\n", chString );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    for ( cnt=0; cnt<chanNum; cnt++ ) {

        errStatus = viPrintf(vi,"CMM %d,%d\n", channel[cnt], mode[cnt] );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }

        if ( mode[cnt] == agb1500_VM_MODE ) {

            errStatus = viPrintf(vi,"RV %d,%d\n",
                channel[cnt], vRangeId(channel[cnt],thisPtr->UNT[channel[cnt]-1],range[cnt]));
            if ( errStatus < VI_SUCCESS) {
                agb1500_LOG_STATUS( vi, thisPtr, errStatus );
            }
        }
        else {

            errStatus = viPrintf(vi,"RI %d,%d\n",
                channel[cnt], iRangeId(channel[cnt],thisPtr->UNT[channel[cnt]-1],range[cnt]) );
            if ( errStatus < VI_SUCCESS) {
                agb1500_LOG_STATUS( vi, thisPtr, errStatus );
            }
        }
    }

    agb1500_CHK_INST_ERR( vi, thisPtr );


    errStatus = viPrintf(vi,"XE\n" );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_CHK_INST_ERR_AFTER_XE( vi, thisPtr );

    eod = 0;
    cnt = 0;
    chCnt = 0;
   
    do {        
        for ( chCnt = 0 ;chCnt <chanNum  ; chCnt++) {
            /*--- Read Time stamp Data ---*/       
            if ( time != (ViReal64 *)NULL) {
                if ( eod == 0) {
                    errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
                    if ( errStatus < VI_SUCCESS) {
                        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
                    }
   
                    if ( dataKind == agb1500_DT_TM) {         
                        time[cnt*chanNum + chCnt] = getValue;
                    }
                    else {
                        return (agb1500_MEAS_DATA_INCONSISTENCY);
                    }
                }
                else {
                    time[cnt*chanNum +chCnt] = agb1500_DUMMY_TIMESTAMP;
                }
            }

            /*--- Read Measurement Data ---*/
            if (eod == 0) {
                errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
                if ( errStatus < VI_SUCCESS) {
                    agb1500_LOG_STATUS( vi, thisPtr, errStatus );
                }
   
                if ( dataKind == agb1500_DT_VM || dataKind == agb1500_DT_IM) {         
                    value[cnt*chanNum + chCnt] = getValue;
                    /*--- Set Status ---*/
                    if ( status != (ViInt32 *)NULL ) {
                        status[cnt*chanNum + chCnt] = getStatus ;
                    }
                }
                else {
                    return (agb1500_MEAS_DATA_INCONSISTENCY);
                }
            }
            else {
                value[cnt*chanNum +chCnt] = agb1500_DUMMY_VALUE;
                /*--- Set Status ---*/
                if ( status != (ViInt32 *)NULL ) {
                    status[cnt*chanNum + chCnt] = agb1500_DUMMY_STATUS ;
                }
            }
        }

  
        /*--- Read Source Data ---*/
        if ( source != (ViReal64 *)NULL) {
            if ( eod == 0) {
                errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
                if ( errStatus < VI_SUCCESS) {
                    agb1500_LOG_STATUS( vi, thisPtr, errStatus );
                }
         
                if ( dataKind == agb1500_DT_VS || dataKind == agb1500_DT_IS) {
                    source[cnt] = getValue;               
                }
                else {
                    return (agb1500_MEAS_DATA_INCONSISTENCY);
                }
            }
            else {
                source[cnt] = agb1500_DUMMY_VALUE;
            }
        }
         
        cnt++;
   
    } while(eod == 0);  

    /*--- Set Point ---*/
    *point = cnt ;

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */


/********************* Quasi-Pulsed Measurement Functions *********************/

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_setBdv(ViSession vi, 
                               ViInt32 channel, ViReal64 range, 
                               ViReal64 start,  ViReal64 stop, 
                               ViReal64 current, 
                               ViReal64 hold,  ViReal64 delay )
/*****************************************************************************/
/*                                                                           */
/*      This function sets the quasi-pulse source used to perform the        */
/*      breakdown voltage measurement.  After the source setup, execute      */
/*      the agb1500_measureBdv function to trigger the measurement.          */
/*                                                                           */
/*      The parameter 'channel' specifies the quasi-pulse source channel.    */
/*      The parameter 'range' specifies the voltage output ranging type.     */
/*      The parameter 'start' sets the search start voltage.                 */
/*      The parameter 'stop' sets the search stop voltage.                   */
/*      The parameter 'current' sets the current compliance value of the     */
/*      quasi-pulse source.                                                  */
/*      The parameter 'hold' sets the hold time of the search start voltage. */
/*      The parameter 'delay' sets the delay time before starting the        */
/*      breakdown voltage measurement.                                       */
/*                                                                           */
/*      After the measurement trigger, the quasi-pulse source keeps the      */
/*      start voltage during the hold time.  After the hold time, the        */
/*      quasi-pulse source starts the voltage transition and settling        */
/*      detection.  And the source stops the settling detection and keeps    */
/*      the output when the following condition a or b occurs.               */
/*      After the delay time, the measurement channel starts the             */
/*      breakdown voltage measurement.                                       */
/*                                                                           */
/*      Condition:                                                           */
/*      a. quasi-pulse source reaches it current compliance setting.         */
/*      b. output voltage slew rate becomes 1/2 of the rate when starting    */
/*         the settling detection.                                           */
/*                                                                           */
/*      The condition b means that the quasi-pulse source applies the        */
/*      voltage close to the stop voltage, or the device under test          */
/*      reaches the breakdown condition.                                     */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      BDV                                                                  */
/*      BDT                                                                  */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      channel    Channel number of the channel.  Same as the slot number   */
/*                 for the SMU.                                              */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_1      1     Channel 1                         */
/*                 agb1500_CH_2      2     Channel 2                         */
/*                 agb1500_CH_3      3     Channel 3                         */
/*                 agb1500_CH_4      4     Channel 4                         */
/*                 agb1500_CH_5      5     Channel 5                         */
/*                 agb1500_CH_6      6     Channel 6                         */
/*                 agb1500_CH_7      7     Channel 7                         */
/*                 agb1500_CH_8      8     Channel 8                         */
/*                 agb1500_CH_9      9     Channel 9                         */
/*                 agb1500_CH_10    10     Channel 10                        */
/*                                                                           */
/*        range   Output ranging type.                                       */
/*                For current output: 0, 1E-12 to 1.0                        */
/*                For voltage output: 0, 0.5 to 200.0                        */
/*                where,                                                     */
/*                For auto ranging: Enter 0 (zero).                          */
/*                For limited auto ranging: Enter positive value.            */
/*                Data Type:  ViReal64                                       */
/*                Input/Output:  IN                                          */
/*                                                                           */
/*        start    Search start value (in A or V).                           */
/*                 The start and stop must be | start - stop | > 10 V.       */
/*                 For current sweep: -1.0 A to 1.0 A                        */
/*                 For voltage sweep: -200.0 V to 200.0 V                    */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value                                   */
/*                 agb1500_SMUV_MIN   -200.0                                 */
/*                 agb1500_SMUV_MAX   200.0                                  */
/*                                                                           */
/*          stop   Search start value (in A or V).                           */
/*                 The start and stop must be | start - stop | > 10 V.       */
/*                 For current sweep: -1.0 A to 1.0 A                        */
/*                 For voltage sweep: -200.0 V to 200.0 V                    */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value                                   */
/*                 agb1500_SMUV_MIN   -200.0                                 */
/*                 agb1500_SMUV_MAX   200.0                                  */
/*                                                                           */
/*       current   Current compliance.  This is a condition to stop the      */
/*                 settling detection.  If the quasi-pulse source reaches    */
/*                 this compliance value, it stops the voltage transition    */
/*                 and settling detection.                                   */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value                                   */
/*                 agb1500_SMUI_MIN   -1.0                                   */
/*                 agb1500_SMUI_MAX   1.0                                    */
/*                                                                           */
/*          hold   Hold time (in second).  After the measurement trigger,    */
/*                 the quasi-pulse source keeps the search start voltage     */
/*                 during the hold time.  After the hold time, the           */
/*                 quasi-pulse source starts the voltage transition and      */
/*                 settling detection.                                       */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                  Value                               */
/*                 agb1500_QPM_HOLD_MIN   0.00                               */
/*                 agb1500_QPM_HOLD_MAX   655.35                             */
/*                                                                           */
/*        delay    Delay time (in second).  After the settling detection was */
/*                 stopped, the quasi-pulse source keeps the output during   */
/*                 the delay time.  After the delay time, the measurement    */
/*                 channel starts the breakdown voltage measurement.         */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                   Value                              */
/*                 agb1500_QPM_DELAY_MIN   0.0                               */
/*                 agb1500_QPM_DELAY_MAX   6.5535                            */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
    char     command[256] ;

    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_setBdv" );


    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( channel, agb1500_CH_1, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);

    if ( fabs(range) > agb1500_AUTOR_BORDER ) 
        agb1500_CHK_REAL_RANGE( range, agb1500_RANGE_MIN, agb1500_RANGE_MAX, 
                             VI_ERROR_PARAMETER3);
    
    agb1500_CHK_REAL_RANGE( start, agb1500_SMUV_MIN, agb1500_SMUV_MAX, 
                           VI_ERROR_PARAMETER4);

    agb1500_CHK_REAL_RANGE( stop, agb1500_SMUV_MIN, agb1500_SMUV_MAX, 
                           VI_ERROR_PARAMETER5);

    agb1500_CHK_REAL_RANGE( hold, agb1500_QPM_HOLD_MIN, agb1500_QPM_HOLD_MAX, 
                           VI_ERROR_PARAMETER7);

    agb1500_CHK_REAL_RANGE( delay, agb1500_QPM_DELAY_MIN, agb1500_QPM_DELAY_MAX, 
                           VI_ERROR_PARAMETER8);

    /*--- Set Command ---*/
    if ( !(agb1500_SMUI_MIN <= current  &&  current <= agb1500_SMUI_MAX) ) 
        sprintf( command, "BDV %d,%d,%E,%E", 
            channel, abs(vRangeId(channel,thisPtr->UNT[channel-1],range)), start, stop );
    else
        sprintf( command, "BDV %d,%d,%E,%E,%E", 
            channel, abs(vRangeId(channel,thisPtr->UNT[channel-1],range)), start, stop, current );


    errStatus = viPrintf(vi,"%s\n", command );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    sprintf( command, "BDT %E,%E", hold, delay );

    errStatus = viPrintf(vi,"%s\n", command );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_measureBdv(ViSession vi, ViInt32 interval,
                                    ViPReal64 value, ViPInt32 status)
/*****************************************************************************/
/*                                                                           */
/*      This function triggers quasi-pulsed spot measurement to measure      */
/*      breakdown voltage.  Before executing this function, the              */
/*      agb1500_setBdv function must be executed.                            */
/*                                                                           */
/*      The parameter 'interval' specifies the settling detection interval.  */
/*      The parameter 'value' returns the breakdown voltage data.            */
/*      The parameter 'status' returns the measurement status.               */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      BDM                                                                  */
/*      FMT                                                                  */
/*      MM                                                                   */
/*      XE                                                                   */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*                                                                           */
/*      interval   Settling detection interval.                              */
/*                 Select 0 for interval short.                              */
/*                 Select 1 for interval long.                               */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                    Value   Description               */
/*                 agb1500_SHORT_INTERVAL   0     SHORT                      */
/*                 agb1500_LONG_INTERVAL    1      LONG                      */
/*                                                                           */
/*         value   Measurement data.                                         */
/*                 Data Type:  ViPReal64                                     */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*        status   Measurement status.                                       */
/*                 To disable the status data output, set 0 (NULL pointer)   */
/*                 instead of variable.                                      */
/*                 Data Type:  ViPInt32                                      */
/*                 Input/Output:  OUT                                        */
/*                 Values:                                                   */
/*                 Name                  Value   Description                 */
/*                 agb1500_STAT_OVF_BIT   1     AD converter overflowed.     */
/*                 agb1500_STAT_OSC_BIT   2     One or more channels are     */
/*                                              oscillating.                 */
/*                 agb1500_STAT_OCC_BIT   3     Another channel reached      */
/*                                              compliance.                  */
/*                 agb1500_STAT_TCC_BIT   4     This channel reached         */
/*                                              compliance.                  */
/*                 agb1500_STAT_SNF_BIT   5     Detection time was too long. */
/*                 agb1500_STAT_SAB_BIT   6     Output slew late was too     */
/*                                              slow.                        */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0;
    struct   agb1500_globals *thisPtr;

    ViReal64  get_value ;
    ViInt32   get_status ;
    ViInt32   get_eod ;
    ViInt32   dataKind;
   
   errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
   if ( errStatus < VI_SUCCESS)   {
       agb1500_LOG_STATUS( vi, 0, errStatus );
   }
   agb1500_DEBUG_CHK_THIS( vi, thisPtr );
   agb1500_CDE_INIT( "agb1500_measureBdv" );

   /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( interval, agb1500_SHORT_INTERVAL, agb1500_LONG_INTERVAL, 
                           VI_ERROR_PARAMETER2);

   /* Instrument I/O */

    errStatus = viPrintf(vi,"FMT 21,0\n");
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }


    errStatus = viPrintf(vi,"MM 9\n");
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }


    errStatus = viPrintf(vi,"BDM %d,0\n",interval);
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_CHK_INST_ERR( vi, thisPtr );


    errStatus = viPrintf(vi,"XE\n" );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_CHK_INST_ERR_AFTER_XE( vi, thisPtr );

     /*--- get measurement data ---*/
    get_eod = 0;
    for ( ;get_eod == 0; ) {
        errStatus = asciiDataRead( vi,&dataKind, &get_value, &get_status,NULL, &get_eod );
        if ( errStatus < VI_SUCCESS)  {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
        if ( dataKind == agb1500_DT_VM) {
            *value = get_value;
            if ( status !=(ViInt32 *)NULL) {
                *status = get_status ;
            }
        }
        else {
            return (agb1500_MEAS_DATA_INCONSISTENCY);
        }
    }
    
    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_setIleak(ViSession vi, 
                               ViInt32 channel, ViReal64 range, 
                               ViReal64 voltage,  ViReal64 compliance,
                               ViReal64 start,
                               ViReal64 hold,  ViReal64 delay )
/*****************************************************************************/
/*                                                                           */
/*      This function sets the quasi-pulse source used to perform the        */
/*      leakage current measurement.  After the source setup, execute the    */
/*      agb1500_measurelleak function to trigger the measurement.            */
/*                                                                           */
/*      The parameter 'channel' specifies the quasi-pulse source channel.    */
/*      The parameter 'range' specifies the voltage output ranging type.     */
/*      The parameter 'voltage' sets the measurement voltage.                */
/*      The parameter 'compliance' sets the current compliance value of      */
/*      the quasi-pulse source.                                              */
/*      The parameter 'start' sets the ramp-up start voltage.                */
/*      The parameter 'hold' sets the hold time of the search start          */
/*      voltage.                                                             */
/*      The parameter 'delay' sets the delay time before starting the        */
/*      leakage current measurement.                                         */
/*                                                                           */
/*      After the measurement trigger, the quasi-pulse source keeps the      */
/*      ramp-up start voltage during the hold time.  After the hold time,    */
/*      the quasi-pulse source starts the voltage transition and settling    */
/*      detection.  And the source stops the settling detection and keeps    */
/*      the output when the following condition a or b occurs.  After the    */
/*      delay time, the measurement channel starts the leakage current       */
/*      measurement.                                                         */
/*                                                                           */
/*      Condition:                                                           */
/*      a. quasi-pulse source reaches it current compliance setting.         */
/*      b. output voltage slew rate becomes 1/2 of the rate when starting    */
/*         the settling detection.                                           */
/*                                                                           */
/*      The condition b means that the quasi-pulse source applies the        */
/*      voltage close to the stop voltage, or the device under test          */
/*      reaches the breakdown condition.                                     */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      BDV                                                                  */
/*      BDT                                                                  */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      channel    Channel number of the channel.  Same as the slot number   */
/*                 for the SMU.                                              */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_1      1     Channel 1                         */
/*                 agb1500_CH_2      2     Channel 2                         */
/*                 agb1500_CH_3      3     Channel 3                         */
/*                 agb1500_CH_4      4     Channel 4                         */
/*                 agb1500_CH_5      5     Channel 5                         */
/*                 agb1500_CH_6      6     Channel 6                         */
/*                 agb1500_CH_7      7     Channel 7                         */
/*                 agb1500_CH_8      8     Channel 8                         */
/*                 agb1500_CH_9      9     Channel 9                         */
/*                 agb1500_CH_10    10     Channel 10                        */
/*                                                                           */
/*        range    Output ranging type.                                      */
/*                 For current output: 0, 1E-12 to 1.0                       */
/*                 For voltage output: 0, 0.5 to 200.0                       */
/*                 where,                                                    */
/*                 For auto ranging: Enter 0 (zero).                         */
/*                 For limited auto ranging: Enter positive value.           */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      voltage    Measurement voltage.                                      */
/*                 The start and voltage must be | start - voltage | > 10 V. */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value                                   */
/*                 agb1500_SMUV_MIN   -200.0                                 */
/*                 agb1500_SMUV_MAX   200.0                                  */
/*                                                                           */
/*   compliance    Current compliance.  This is a condition to stop the      */
/*                 settling detection.  If the quasi-pulse source reaches    */
/*                 this compliance value, it stops the voltage transition    */
/*                 and settling detection.                                   */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value                                   */
/*                 agb1500_SMUI_MIN   -1.0                                   */
/*                 agb1500_SMUI_MAX   1.0                                    */
/*                                                                           */
/*        start    Ramp-up start voltage.                                    */
/*                 The start and voltage must be | start - voltage | > 10 V. */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value                                   */
/*                 agb1500_SMUV_MIN   -200.0                                 */
/*                 agb1500_SMUV_MAX   200.0                                  */
/*                                                                           */
/*          hold   Hold time (in second).  After the measurement trigger,    */
/*                 the quasi-pulse source keeps the search start voltage     */
/*                 during the hold time.  After the hold time, the           */
/*                 quasi-pulse source starts the voltage transition and      */
/*                 settling detection.                                       */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                  Value                               */
/*                 agb1500_QPM_HOLD_MIN   0.00                               */
/*                 agb1500_QPM_HOLD_MAX   655.35                             */
/*                                                                           */
/*        delay    Delay time (in second).  After the settling detection was */
/*                 stopped, the quasi-pulse source keeps the output during   */
/*                 the delay time.  After the delay time, the measurement    */
/*                 channel starts the breakdown voltage measurement.         */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                   Value                              */
/*                 agb1500_QPM_DELAY_MIN   0.0                               */
/*                 agb1500_QPM_DELAY_MAX   6.5535                            */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
    char     command[256] ;

    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_setIleak" );


    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( channel, agb1500_CH_1, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);

    if ( fabs(range) > agb1500_AUTOR_BORDER ) 
        agb1500_CHK_REAL_RANGE( range, agb1500_RANGE_MIN, agb1500_RANGE_MAX, 
                             VI_ERROR_PARAMETER3);
    
    agb1500_CHK_REAL_RANGE( voltage, agb1500_SMUV_MIN, agb1500_SMUV_MAX, 
                           VI_ERROR_PARAMETER4);

    agb1500_CHK_REAL_RANGE( start, agb1500_SMUV_MIN, agb1500_SMUV_MAX, 
                           VI_ERROR_PARAMETER6);

    agb1500_CHK_REAL_RANGE( hold, agb1500_QPM_HOLD_MIN, agb1500_QPM_HOLD_MAX, 
                           VI_ERROR_PARAMETER7);

    agb1500_CHK_REAL_RANGE( delay, agb1500_QPM_DELAY_MIN, agb1500_QPM_DELAY_MAX, 
                           VI_ERROR_PARAMETER8);


    /*--- Set Command ---*/
    if ( !(agb1500_SMUI_MIN <= compliance  &&  compliance <= agb1500_SMUI_MAX) ) 
        sprintf( command, "BDV %d,%d,%E,%E", 
            channel, abs(vRangeId(channel,thisPtr->UNT[channel-1],range)), start, voltage );
    else
        sprintf( command, "BDV %d,%d,%E,%E,%E", 
            channel, abs(vRangeId(channel,thisPtr->UNT[channel-1],range)), start, voltage, compliance );


    errStatus = viPrintf(vi,"%s\n", command );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    sprintf( command, "BDT %E,%E", hold, delay );

    errStatus = viPrintf(vi,"%s\n", command );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }
    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_measureIleak(ViSession vi, ViInt32 channel,
                                    ViInt32 interval,
                                    ViPReal64 value, ViPInt32 status)
/*****************************************************************************/
/*                                                                           */
/*      This function triggers quasi-pulsed spot measurement to measure      */
/*      leakage current.  Before executing this function, the                */
/*      agb1500_setIleak function must be executed.                          */
/*                                                                           */
/*      The parameter 'channel' specifies the measurement channel.           */
/*      The parameter 'interval' specifies the settling detection interval.  */
/*      The parameter 'value' returns the breakdown voltage data.            */
/*      The parameter 'status' returns the measurement status.               */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      BDM                                                                  */
/*      FMT                                                                  */
/*      MM                                                                   */
/*      XE                                                                   */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*                                                                           */
/*      interval   Settling detection interval.                              */
/*                 Select 0 for interval short.                              */
/*                 Select 1 for interval long.                               */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                    Value   Description               */
/*                 agb1500_SHORT_INTERVAL   0     SHORT                      */
/*                 agb1500_LONG_INTERVAL    1      LONG                      */
/*                                                                           */
/*         value   Measurement data.                                         */
/*                 Data Type:  ViPReal64                                     */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*        status   Measurement status.                                       */
/*                 To disable the status data output, set 0 (NULL pointer)   */
/*                 instead of variable.                                      */
/*                 Data Type:  ViPInt32                                      */
/*                 Input/Output:  OUT                                        */
/*                 Values:                                                   */
/*                 Name                  Value   Description                 */
/*                 agb1500_STAT_OVF_BIT   1     AD converter overflowed.     */
/*                 agb1500_STAT_OSC_BIT   2     One or more channels are     */
/*                                              oscillating.                 */
/*                 agb1500_STAT_OCC_BIT   3     Another channel reached      */
/*                                              compliance.                  */
/*                 agb1500_STAT_TCC_BIT   4     This channel reached         */
/*                                              compliance.                  */
/*                 agb1500_STAT_SNF_BIT   5     Detection time was too long. */
/*                 agb1500_STAT_SAB_BIT   6     Output slew late was too     */
/*                                              slow.                        */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0;
    struct   agb1500_globals *thisPtr;

    ViReal64  get_value ;
    ViInt32   get_status ;
    ViInt32   dataKind;
    ViInt32   get_eod ;
   
   errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
   if ( errStatus < VI_SUCCESS)   {
       agb1500_LOG_STATUS( vi, 0, errStatus );
   }
   agb1500_DEBUG_CHK_THIS( vi, thisPtr );
   agb1500_CDE_INIT( "agb1500_measureIleak" );

    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( channel, agb1500_CH_1, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);

    agb1500_CHK_LONG_RANGE( interval, agb1500_SHORT_INTERVAL, agb1500_LONG_INTERVAL, 
                           VI_ERROR_PARAMETER3);

    /* Instrument I/O */

    errStatus = viPrintf(vi,"FMT 21,0\n");
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }


    errStatus = viPrintf(vi,"MM 9,%d\n",channel);
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }


    errStatus = viPrintf(vi,"BDM %d,1\n",interval);
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_CHK_INST_ERR( vi, thisPtr );


    errStatus = viPrintf(vi,"XE\n" );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_CHK_INST_ERR_AFTER_XE( vi, thisPtr );

    /*--- get measurement data ---*/
    get_eod = 0;
    for ( ;get_eod == 0; ) {
        errStatus = asciiDataRead( vi,&dataKind, &get_value, &get_status,NULL, &get_eod );
        if ( errStatus < VI_SUCCESS)  {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
        if ( dataKind == agb1500_DT_IM) {
            *value = get_value;
            if ( status !=(ViInt32 *)NULL) {
                *status = get_status ;
            }
        }
        else {
            return (agb1500_MEAS_DATA_INCONSISTENCY);
        }
    }
    
    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/********************* Primitive Measurement Functions ***********************/

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_startMeasure(ViSession vi, ViInt32 meas_type,
                               ViInt32 channel[], ViInt32 mode[], 
                               ViReal64 range[], ViInt32 source ,
                               ViInt32 timestamp, ViInt32 monitor)
/*****************************************************************************/
/*                                                                           */
/*      This function starts the specified measurement.                      */
/*                                                                           */
/*      The parameter 'meas_type' specifies the measurement type.            */
/*      The parameter 'channel[ ]' specifies the measurement channels.       */
/*      The parameter 'mode[ ]' specifies the measurement mode for each      */
/*      channel.                                                             */
/*      The parameter 'range[ ]' specifies the measurement ranging type      */
/*      for each channel.                                                    */
/*      The parameter 'source' specifies the source data output mode.        */
/*      The parameter 'time stamp' specifies the time stamp data output      */
/*      mode.                                                                */
/*      The parameter 'monitor' specifies the DC bias / AC level monitor     */
/*      data output mode.                                                    */
/*                                                                           */
/*      After the measurement, the measurement data will be put in           */
/*      the Agilent B1500 data output buffer in order of the measurement.    */
/*      To read the data, execute the agb1500_readData function.             */
/*                                                                           */
/*      To abort the measurement, execute the agb1500_abortMeasure function. */
/*                                                                           */
/*      The parameters must be declared as shown below:                      */
/*                                                                           */
/*      ViInt32     meas_type                                                */
/*      ViInt32     channel[N+1]                                             */
/*      ViInt32     mode[N]                                                  */
/*      ViReal64    range[N]                                                 */
/*      ViInt32     source                                                   */
/*      ViInt32     timestamp                                                */
/*      ViInt32     monitor                                                  */
/*      where,                                                               */
/*      N: Number of measurement channels.                                   */
/*                                                                           */
/*     For the parameter definition,  the order of the array data is         */
/*     important.  For example, the measurement setup for the channel        */
/*     specified by channel[1] must be entered into mode[1] and range[1].    */
/*                                                                           */
/*     This function implements the following commands:                      */
/*                                                                           */
/*     FMT                                                                   */
/*     TSC                                                                   */
/*     MM                                                                    */
/*     CMM                                                                   */
/*     RI                                                                    */
/*     RV                                                                    */
/*     RC                                                                    */
/*     IMP                                                                   */
/*     LMN                                                                   */
/*     XE                                                                    */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      meas_type   Measurement type.                                        */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:   For SMU                                        */
/*                  Name				Value   Description                  */
/*                  agb1500_MM_MSPOT	1		SPOT                         */
/*                  agb1500_MM_SWEEP	2		STAIRCASE SWEEP              */
/*                  agb1500_MM_PSPOT	3		PULSED SPOT                  */
/*                  agb1500_MM_PSWEEP	4		PULSED SWEEP                 */
/*                  agb1500_MM_SWEEPP	5		SWEEP w/ PULSED BIAS         */
/*                  agb1500_MM_QPSPOT	9		QUASI-PULSED SPOT            */
/*                  agb1500_MM_IVSMAPLE 10      I/V SAMPLING                 */
/*                  agb1500_MM_LSEARCH	14		LINEAR SEARCH                */
/*                  agb1500_MM_BSEARCH	15		BINARY SEARCH                */
/*                  agb1500_MM_MSWEEP	16		MULTI-CHANNEL SWEEP          */
/*                                                                           */
/*                  Values:   For CMU                                        */
/*                  Name				Value   Description                  */
/*                  agb1500_MM_CSPOT	17		C SPOT                       */
/*                  agb1500_MM_CVSWEEP	18		C-V STAIRCASE SWEEP          */
/*                                                                           */
/*     channel[ ]   Channel number of the measurement channel.               */
/*                  Same as the slot number for the SMU or CMU.              */
/*                  1 to 10 for the MPSMU, HPSMU, HRSMU, and HRSMU(ASU).     */
/*                  At the end of the channel definitions, enter 0 (zero)    */
/*                  into the last array element. For example, if you use     */
/*                  four channels, array size should be five, and 0 (zero)   */
/*                  must be entered into the fifth array element.            */
/*                  For meas_type =1, 2, or 16, up to 8 measurement channels */
/*                  can be set.                                              */
/*                  For meas_type =3, 4, 5, or 9, 17,18 only 1 channel       */
/*                  can be set.                                              */
/*                  For meas_type =14 or 15, set 0 (NULL pointer) instead of */
/*                  channel[ ].                                              */
/*                  Data Type:  ViInt32Input/Output:  IN                     */
/*                  Values:                                                  */
/*                  Name          Value   Description                        */
/*                  agb1500_CH_CMU -1     CMU channel                        */
/*                  agb1500_CH_1    1     Channel 1                          */
/*                  agb1500_CH_2    2     Channel 2                          */
/*                  agb1500_CH_3    3     Channel 3                          */
/*                  agb1500_CH_4    4     Channel 4                          */
/*                  agb1500_CH_5    5     Channel 5                          */
/*                  agb1500_CH_6    6     Channel 6                          */
/*                  agb1500_CH_7    7     Channel 7                          */
/*                  agb1500_CH_8    8     Channel 8                          */
/*                  agb1500_CH_9    9     Channel 9                          */
/*                  agb1500_CH_10  10     Channel 10                         */
/*                                                                           */
/*        mode[ ]   Measurement mode.                                        */
/*                  For meas_type = 1, 2, 3, 4, 5, 6, 9, 10, 13, 14, 15,     */
/*                  or 16,                                                   */       
/*                  Select 1 for current measurement.                        */
/*                  Select 2 for voltage measurement.                        */
/*                  For meas_type = 16,17, select the impedance measurement  */
/*                  mode.                                                    */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values: For SMU                                          */
/*                  Name             Value   Description                     */
/*                  agb1500_IM_MODE   1     CURRENT MEASUREMENT              */
/*                  agb1500_VM_MODE   2     VOLTAGE MEASUREMENT              */
/*                                                                           */
/*                  Values: For CMU                                          */
/*                  Name					Value   Description              */
/*                  agb1500_CMUM_R_X		1       R-X Mode			     */
/*                  agb1500_CMUM_G_B		2       G-B Mode                 */
/*                  agb1500_CMUM_Z_TRAD		10      Z-Theta(radian) Mode     */
/*                  agb1500_CMUM_Z_TDEG		11      Z-Theta(degree) Mode     */
/*                  agb1500_CMUM_Y_TRAD		20      Y-Theta(radian) Mode     */
/*                  agb1500_CMUM_Y_TDEG		21      Y-Theta(degree) Mode     */
/*                  agb1500_CMUM_CP_G		100     Cp-G Mode                */
/*                  agb1500_CMUM_CP_D		101     Cp-D Mode                */
/*                  agb1500_CMUM_CP_Q		102     Cp-Q Mode                */
/*                  agb1500_CMUM_CP_RP		103     Cp-Rp Mode               */
/*                  agb1500_CMUM_CS_RS		200     Cs-Rs Mode               */
/*                  agb1500_CMUM_CS_D		201     Cs-D Mode                */
/*                  agb1500_CMUM_CS_Q		202		Cs-Q Mode                */
/*                  agb1500_CMUM_LP_G		300     Lp-G Mode                */
/*                  agb1500_CMUM_LP_D		301     Lp-D Mode                */
/*                  agb1500_CMUM_LP_Q		302     Lp-Q Mode                */
/*                  agb1500_CMUM_LP_RP		303     Lp-Rp Mode               */
/*                  agb1500_CMUM_LS_RS		400     Ls-Rs Mode               */
/*                  agb1500_CMUM_LS_D		401     Ls-D Mode                */
/*                  agb1500_CMUM_LS_Q		402     Ls-Q Mode                */
/*                                                                           */   
/*      range[ ]    Measurement ranging type.                                */
/*                  For meas_type = 1, 2, 3, 4, 5, 9, 10, 13, 14, 15, or 16, */ 
/*                  For current measurement: 0, 1E-12 to 1.0, -1E-12 to -1.0 */
/*                  For voltage measurement: 0, 0.5 to 200.0, -0.5 to -200.0 */
/*                  where,                                                   */
/*                  For auto ranging: Enter 0 (zero).                        */
/*                  For limited auto ranging: Enter positive value.          */
/*                  For fixed ranging: Enter negative value.                 */
/*                  For meas_type = 17,18,                                   */
/*                  For auto ranging: Enter 0 (zero).                        */
/*                  For fixed ranging: Enter positive value.                 */ 
/*                  Data Type:  ViReal64                                     */
/*                  Input/Output:  INValues:  range value                    */
/*                                                                           */
/*        source    Enables or disables the source data output.              */
/*                  For meas_type =9, 14, and 15, enter 0 (zero).            */
/*                  Source data output is not available for these            */
/*                  measurement types.                                       */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name             Value   Description                     */
/*                  agb1500_FLAG_OFF   0    DISABLES SOURCE DATA OUTPUT      */
/*                  agb1500_FLAG_ON    1    ENABLES SOURCE DATA OUTPUT       */
/*                                                                           */
/*     timestamp    Enables or disables the time stamp data output.          */
/*                  For meas_type =9, 14, and 15, enter 0 (zero).            */
/*                  Time stamp data output is not available for these        */
/*                  measurement types.                                       */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name              Value   Description                    */
/*                  agb1500_FLAG_OFF   0    DISABLES TIME STAMP DATA OUTPUT  */
/*                  agb1500_FLAG_ON    1    ENABLES TIME STAMP DATA OUTPUT   */
/*                                                                           */
/*        monitor   Enables or disables the DC bias/AC level monitor         */
/*                  data output.                                             */
/*                  For meas_type =1, 2, 3, 4, 5, 9, 10, 14, 15, and 16,     */
/*                  enter 0 (zero).                                          */
/*                  DC bias/Ac level data output is not available for these  */
/*                  measurement types.                                       */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name              Value   Description                    */
/*                  agb1500_FLAG_OFF   0    DISABLES TIME STAMP DATA OUTPUT  */
/*                  agb1500_FLAG_ON    1    ENABLES TIME STAMP DATA OUTPUT   */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
    ViInt32  chanNum ;
    ViChar   chChar[8] ;
    ViChar   chString[256] ;            

    int      cnt ;

    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_startMeasure" );


    /* Check Prameter Range */
    if (!((( agb1500_MM_MSPOT  <= meas_type ) && ( meas_type <= agb1500_MM_SWEEPP ))
        ||(( agb1500_MM_LSEARCH <= meas_type ) && ( meas_type <= agb1500_MM_CVSWEEP ))
        ||(( agb1500_MM_QPSPOT <= meas_type ) && ( meas_type <= agb1500_MM_IVSAMPLE )))) {
        agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2 );
    }


    /* Check Prameter Range */

    if ( (meas_type == agb1500_MM_BSEARCH) || (meas_type == agb1500_MM_LSEARCH) ) {
        cnt = 0;
    }
    else {
        for ( cnt=0; channel[cnt] != 0; cnt++ ) {
            if( !((channel[cnt] == agb1500_CH_CMU) || 
				((channel[cnt] >= agb1500_CH_1) && (channel[cnt] <= agb1500_CH_10)))){
				agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER3);
			}
			if( channel[cnt] == agb1500_CH_CMU ){
			if( (channel[cnt] = agb1500_RTN_CMU_UNT) == agb1500_NO_CMU ){
				return agb1500_NO_CMU_UNT;
			}
		}
			if( meas_type < agb1500_MM_CSPOT ){  /* SMU */
				agb1500_CHK_LONG_RANGE( mode[cnt], agb1500_IM_MODE, agb1500_VM_MODE, 
					                VI_ERROR_PARAMETER4 );

				if ( fabs(range[cnt]) > agb1500_AUTOR_BORDER ) {
						agb1500_CHK_REAL_RANGE( range[cnt], agb1500_RANGE_MIN, agb1500_RANGE_MAX,
							                VI_ERROR_PARAMETER5);
				}
			}else{ /* CMU */
				agb1500_CHK_IMP_MEAS_MODE( mode[cnt], VI_ERROR_PARAMETER4);

				if( range[cnt] < 0 ){
					agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER5);
				}
			}
        }
    }

    /*--- Channel Non Set ---*/
    if (( meas_type != agb1500_MM_QPSPOT ) && 
        ( meas_type != agb1500_MM_LSEARCH ) &&
        ( meas_type != agb1500_MM_BSEARCH )) 
        if ( cnt == 0 ) agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER3 );

    /*--- Get Chunnel Number ---*/
    chanNum = cnt ;

   /* Check Range of the 6-th, 7-th and 8-th parameters */
    agb1500_CHK_LONG_RANGE( source, agb1500_FLAG_OFF, agb1500_FLAG_ON, 
                            VI_ERROR_PARAMETER6  );

    agb1500_CHK_LONG_RANGE( timestamp, agb1500_FLAG_OFF, agb1500_FLAG_ON, 
                            VI_ERROR_PARAMETER7  );

	agb1500_CHK_LONG_RANGE( monitor, agb1500_FLAG_OFF, agb1500_FLAG_ON, 
                            VI_ERROR_PARAMETER8  );

    /*--- Set Command ---*/
    if ( source == agb1500_FLAG_OFF ) {

        errStatus = viPrintf(vi,"FMT 21,0\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }
    else {

        errStatus = viPrintf(vi,"FMT 21,1\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }

    }

   /* set time stamp */
    if ( timestamp == agb1500_FLAG_OFF ) {

        errStatus = viPrintf(vi,"TSC 0\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }

    }
    else {

        errStatus = viPrintf(vi,"TSC 1\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }

    }

	/* set monitor */
	if( meas_type >= agb1500_MM_CSPOT ){ /* CMU */
		if ( monitor == agb1500_FLAG_OFF ) {

        errStatus = viPrintf(vi,"LMN 0\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }

		}
		else {

			errStatus = viPrintf(vi,"LMN 1\n" );
			if ( errStatus < VI_SUCCESS) {
				agb1500_LOG_STATUS( vi, thisPtr, errStatus );
			}
		}
	}


    /*--- Edit Channel Number ---*/
    memset( chString, (char)NULL, sizeof(chString) );
    for ( cnt=0; cnt<chanNum; cnt++) {
        if ( cnt != 0 )  sprintf( chChar, ",%d", channel[cnt] );
        else             sprintf( chChar, "%d", channel[cnt] );
        strcat( chString, chChar );
    }

    if ( chanNum != 0 )
        errStatus = viPrintf(vi,"MM %d,%s\n", meas_type, chString );
    else
        errStatus = viPrintf(vi,"MM %d\n", meas_type );

    if (errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    for ( cnt=0; cnt<chanNum; cnt++ ) {
	
		if( meas_type < agb1500_MM_CSPOT ){ /* SMU */
			if ( (agb1500_CH_1 <= channel[cnt]) && (channel[cnt] <= agb1500_CH_10) ) {
				errStatus = viPrintf(vi,"CMM %d,%d\n", channel[cnt], mode[cnt] );
				if ( errStatus < VI_SUCCESS) {
					agb1500_LOG_STATUS( vi, thisPtr, errStatus );
				}
			}
			if ( mode[cnt] == agb1500_VM_MODE ) {

				errStatus = viPrintf(vi,"RV %d,%d\n",
					channel[cnt], vRangeId(channel[cnt],thisPtr->UNT[channel[cnt]-1],range[cnt]));
				if ( errStatus < VI_SUCCESS) {
					agb1500_LOG_STATUS( vi, thisPtr, errStatus );
				}
			}
			else {

				errStatus = viPrintf(vi,"RI %d,%d\n",
					channel[cnt], iRangeId(channel[cnt],thisPtr->UNT[channel[cnt]-1],range[cnt]) );
				if ( errStatus < VI_SUCCESS) {
					agb1500_LOG_STATUS( vi, thisPtr, errStatus );
				}
			}
		}
		else{ /* CMU */
	
			errStatus = viPrintf(vi,"IMP %d\n", mode[cnt]);
			if ( errStatus < VI_SUCCESS) {
				agb1500_LOG_STATUS( vi, thisPtr, errStatus );
			}

			if ( range[cnt] == 0 ){
				errStatus = viPrintf(vi, "RC %d,0,%e\n",channel[cnt],range[cnt]);
			}else{
				errStatus = viPrintf(vi, "RC %d,2,%e\n",channel[cnt],range[cnt]);
			}
			if ( errStatus < VI_SUCCESS) {
					agb1500_LOG_STATUS( vi, thisPtr, errStatus );
			}
		}
	}

    agb1500_CHK_INST_ERR( vi, thisPtr );

    errStatus = viPrintf(vi,"XE\n" );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }
    agb1500_CHK_INST_ERR_AFTER_XE( vi, thisPtr );

    return (VI_SUCCESS);
} /* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_readData(ViSession vi, ViPInt32 eod,
                               ViPInt32 data_type, ViPReal64 value, 
                               ViPInt32 status, ViPInt32 channel )
/*****************************************************************************/
/*                                                                           */
/*      This function reads and returns the source setup data or the data    */
/*      measured by the agb1500_startMeasure function.                       */
/*                                                                           */
/*      The parameter 'eod' returns the end of data flag.                    */
/*      The parameter 'data_type'  returns the data type of the 'value'      */
/*      The parameter 'value' returns the measurement data or the source     */
/*      setup data.                                                          */
/*      The parameter 'status' returns the measurement status or the source  */
/*      status.                                                              */
/*      The parameter 'channel' returns the channel number of the channel    */
/*      used to measure or force the 'value'                                 */
/*                                                                           */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*           eod   End of data flag.                                         */
/*                 Data Type:  ViPInt32                                      */
/*                 Input/Output:  OUT                                        */
/*                 Values:                                                   */
/*                 Name              Value   Description                     */
/*                 agb1500_FLAG_OFF   0     NOT END OF DATA                  */
/*                 agb1500_FLAG_ON    1     END OF DATA                      */
/*                                                                           */
/*     data_type   Data type of the value.                                   */
/*                 Data Type:  ViPInt32                                      */
/*                 Input/Output:  OUT                                        */
/*                 Values:                                                   */
/*                 Name           Value   Description                        */
/*                 agb1500_DT_IM   1     Current measurement data            */
/*                 agb1500_DT_VM   2     Voltage measurement data            */
/*                 agb1500_DT_IS   3     Current output data                 */
/*                 agb1500_DT_VS   4     Voltage output data                 */
/*                 agb1500_DT_TM   5     Time stamp data                     */ 
/*                 agb1500_DT_ZM   6     Impedance measurement data          */      
/*                                       (Resistance and Reactance)          */
/*                 agb1500_DT_YM   7	 Admittance measurement data         */
/*                                       (Conductance and Susceptance)       */
/*                 agb1500_DT_CM   8     Capacitance measurement data        */
/*                 agb1500_DT_DM   9	 Dissipation measurement data        */
/*                 agb1500_DT_QM   10    Quality factor measurement data     */ 
/*                 agb1500_DT_LM   11    Inductance measurement data         */
/*                 agb1500_DT_RM   12    Phase measurement data(Radian)      */
/*                 agb1500_DT_PM   13    Phase measurement data(Degree)      */
/*                 agb1500_DT_FS   14    Frequency data                      */
/*                 agb1500_DT_X    15    Sampling index                      */
/*                 agb1500_DT_INV  16    Invalid data                        */
/*                 agb1500_CH_NOCH -1    No channel related data             */
/*                                                                           */
/*         value   Measurement data or source setup data.                    */
/*                 Data Type:  ViPReal64                                     */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*        status   Measurement status or source status.To disable the        */
/*                 status data output, set 0 (NULL pointer) instead of       */
/*                   variable.                                               */
/*                 Data Type:  ViPInt32                                      */
/*                 Input/Output:  OUT                                        */
/*                 Values:                                                   */
/*                 Name                  Value   Description                 */
/*                 agb1500_STAT_OVF_BIT   1   AD converter overflowed.       */
/*                 agb1500_STAT_OSC_BIT   2   One or more channels are       */
/*                                            oscillating.                   */
/*                 agb1500_STAT_OCC_BIT   3   Another channel reached        */
/*                                            compliance.                    */
/*                 agb1500_STAT_TCC_BIT   4   This channel reached           */
/*                                            compliance.                    */
/*                 agb1500_STAT_SNF_BIT   5   Search target value was not    */
/*                                            found.                         */
/*                 agb1500_STAT_SAB_BIT   6   Measurement was aborted.       */
/*                                                                           */
/*        channel   Channel number of the channel used to measure or force   */
/*                  the value.  Same as the slot number.                     */
/*                  If the value is not the measurement data or source       */
/*                  output data, -1 is returned.                             */
/*                  To disable the channel output, set 0 (NULL pointer)      */
/*                  instead of variable.                                     */
/*                  Data Type:  ViPInt32                                     */
/*                  Input/Output:  OUT                                       */
/*                  Values:                                                  */
/*                  Name              Value   Description                    */
/*                  agb1500_CH_NOCH   -1   No channel related data.          */
/*                  agb1500_CH_1        1   Channel 1                        */
/*                  agb1500_CH_2        2   Channel 2                        */
/*                  agb1500_CH_3        3   Channel 3                        */
/*                  agb1500_CH_4        4   Channel 4                        */
/*                  agb1500_CH_5        5   Channel 5                        */
/*                  agb1500_CH_6        6   Channel 6                        */
/*                  agb1500_CH_7        7   Channel 7                        */
/*                  agb1500_CH_8        8   Channel 8                        */
/*                  agb1500_CH_9		9   Channel 9                        */
/*                  agb1500_CH_10      10   Channel 10						 */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus    errStatus = 0;
    ViInt32     data_kind ;
    ViReal64    get_value ;
    ViInt32     get_status ;
    ViInt32     channelNo ;
    ViInt32     get_eod ;
    
    struct agb1500_globals *thisPtr;
    
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_readData" );

 
    /*--- read measurment data ---*/
    errStatus = asciiDataRead( vi, &data_kind, &get_value, &get_status, &channelNo, &get_eod );
    if ( errStatus < VI_SUCCESS) {
       return( errStatus );
    }

    *value = get_value;
    *data_type = data_kind ;
    if ( status != (ViInt32 *)NULL )    *status = get_status ;
    *eod = get_eod ;

    if ( channel != (ViInt32 *)NULL )    *channel = channelNo ;


    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_asuLed(ViSession vi, ViInt32 channel, ViInt32 mode )
/*****************************************************************************/
/*                                                                           */
/*      This function sets the LED state of ASU connected to HRSMU           */
/*                                                                           */
/*      The parameter 'channel' specifies the channel number of the HRSMU    */
/*                                                                           */
/*      The parameter 'mode' specifies the status of LED                     */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*        channel   Channel number of the HRSMU that ASU is connected.       */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name              Value   Description                    */
/*                  agb1500_CH_1        1   Channel 1                        */
/*                  agb1500_CH_2        2   Channel 2                        */
/*                  agb1500_CH_3        3   Channel 3                        */
/*                  agb1500_CH_4        4   Channel 4                        */
/*                  agb1500_CH_5        5   Channel 5                        */
/*                  agb1500_CH_6        6   Channel 6                        */
/*                  agb1500_CH_7        7   Channel 7                        */
/*                  agb1500_CH_8        8   Channel 8                        */
/*                  agb1500_CH_9		9   Channel 9                        */
/*                  agb1500_CH_10       10  Channel 10						 */
/*                                                                           */
/*        mode     Select 0 for LED OFF.                                     */
/*                 Select 1 for LED ON.                                      */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                Value    Description                  */
/*                 agb1500_FLAG_OFF      0       LED OFF                     */
/*                 agb1500_FLAG_ON       1       LED ON                      */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, 0, errStatus );        
    }
    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_asuLed" );

    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( channel, 
                agb1500_CH_1, agb1500_CH_10, 
                VI_ERROR_PARAMETER2);

    agb1500_CHK_LONG_RANGE( mode, 
                agb1500_FLAG_OFF, agb1500_FLAG_ON, 
                VI_ERROR_PARAMETER3);

    errStatus = viPrintf(vi,"SAL %d,%d\n", channel, mode );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );

}/* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_asuPath(ViSession vi, ViInt32 channel, ViInt32 path )
/*****************************************************************************/
/*                                                                           */
/*      This function sets the ASU measurement path                          */
/*                                                                           */
/*      The parameter 'channel' specifies the channel number of the HRSMU    */
/*                                                                           */
/*      The parameter 'path' specifies ASU connection path                   */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*        channel   Channel number of the HRSMU that ASU is connected.       */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name              Value   Description                    */
/*                  agb1500_CH_1        1   Channel 1                        */
/*                  agb1500_CH_2        2   Channel 2                        */
/*                  agb1500_CH_3        3   Channel 3                        */
/*                  agb1500_CH_4        4   Channel 4                        */
/*                  agb1500_CH_5        5   Channel 5                        */
/*                  agb1500_CH_6        6   Channel 6                        */
/*                  agb1500_CH_7        7   Channel 7                        */
/*                  agb1500_CH_8        8   Channel 8                        */
/*                  agb1500_CH_9        9   Channel 9                        */
/*                  agb1500_CH_10       10  Channel 10                       */ 
/*                                                                           */
/*        path     Select 1 for SMU output path.                             */
/*                 Select 2 for AUX output path.                             */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                Value    Description                  */
/*                 agb1500_ASU_DC        1       SMU Output Path             */
/*                 agb1500_ASU_AUX       2       AUX Output Path             */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, 0, errStatus );        
    }
    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_asuPath" );

    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( channel, 
                agb1500_CH_1, agb1500_CH_10, 
                VI_ERROR_PARAMETER2);

    agb1500_CHK_LONG_RANGE( path, 
                agb1500_ASU_DC, agb1500_ASU_AUX, 
                VI_ERROR_PARAMETER3);

    errStatus = viPrintf(vi,"SAP %d,%d\n", channel, path-1 );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );

}/* ----- end of function ----- */


/*****************************************************************************/
ViStatus _VI_FUNC agb1500_asuRange(ViSession vi, ViInt32 channel, ViInt32 mode )
/*****************************************************************************/
/*                                                                           */
/*      This function sets whether to use 1pA range or not                   */
/*      when auto range current measurement is performed                     */
/*      using ASU.                                                           */
/*                                                                           */
/*      The parameter 'channel' specifies the channel number of the HRSMU    */
/*                                                                           */
/*      The parameter 'mode' specifies the Range Mode                        */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*        channel   Channel number of the HRSMU that ASU is connected.       */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name              Value   Description                    */
/*                  agb1500_CH_1        1   Channel 1                        */
/*                  agb1500_CH_2        2   Channel 2                        */
/*                  agb1500_CH_3        3   Channel 3                        */
/*                  agb1500_CH_4        4   Channel 4                        */
/*                  agb1500_CH_5        5   Channel 5                        */
/*                  agb1500_CH_6        6   Channel 6                        */
/*                  agb1500_CH_7        7   Channel 7                        */
/*                  agb1500_CH_8        8   Channel 8                        */
/*                  agb1500_CH_9        9   Channel 9                        */
/*                  agb1500_CH_10      10   Channel 10                       */
/*                                                                           */
/*        mode     Select 0 for OFF. Measurement is done using 1pA Range.    */
/*                                                                           */
/*                 Select 1 for ON. This is default setting. Measurement     */
/*                 is done using 10pA range although the current is within   */
/*                 1pA range.                                                */
/*                                                                           */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                Value    Description                  */
/*                 agb1500_FLAG_OFF      0       Enables the 1 pA range.     */
/*                 agb1500_FLAG_ON       1       Disables the 1 pA range.    */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, 0, errStatus );        
    }
    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_asuRange" );

    /* Check Prameter Range */
    agb1500_CHK_LONG_RANGE( channel, 
                agb1500_CH_1, agb1500_CH_10, 
                VI_ERROR_PARAMETER2);

    agb1500_CHK_LONG_RANGE( mode, 
                agb1500_FLAG_OFF, agb1500_FLAG_ON, 
                VI_ERROR_PARAMETER3);

    errStatus = viPrintf(vi,"SAR %d,%d\n", channel, mode );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );

}/* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_setCmuInteg(ViSession vi,  
									  ViInt32 mode, ViInt32 value)
/*****************************************************************************/
/*                                                                           */
/*      This function sets the averaging cycle time of the CMU.              */
/*                                                                           */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      ACT                                                                  */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*         mode    Select the integration/averaging mode.                    */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                 Value     Description                */
/*                 agb1500_INTEG_AUTO     0     AUTO                         */
/*                 agb1500_INTEG_PLC      2     PLC                          */
/*                                                                           */
/*        value    Coefficient for a reference value to set the              */
/*                 integration time or the number of averaging samples.      */
/*                 For Auto Mode; Enter 1 to 1023                            */
/*				   For PLC Mode; Enter 1 To 100								 */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                        Value                         */
/*                 agb1500_SETADC_VALUE_MIN     1                            */
/*                 agb1500_SETADC_VALUE_MAX     1023                         */
/*                                                                           */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }
    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_setCmuInteg" );


    /* Check Prameter Range */
	if (mode != agb1500_INTEG_AUTO && mode != agb1500_INTEG_PLC){
		agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2);
	}

	agb1500_CHK_LONG_RANGE( value, 
					agb1500_SETADC_VALUE_MIN, agb1500_SETADC_VALUE_MAX, 
					VI_ERROR_PARAMETER3);

    if ( value == 0 ) {
        errStatus = viPrintf(vi,"ACT %d\n", mode);
    } 
    else {
        errStatus = viPrintf(vi,"ACT %d,%d\n", mode, value);
    }

    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_forceCmuDcBias(ViSession vi, ViInt32 channel, ViReal64 value )
/*****************************************************************************/
/*                                                                           */
/*      This function sets the DC Bias for CMU                               */
/*                                                                           */
/*      The parameter 'channel' specifies the channel number of CMU          */
/*                                                                           */
/*      The parameter 'value' specifies the DC Bias of CMU                   */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*        channel   Channel number of the HRSMU that ASU is connected.       */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name              Value   Description                    */
/*                  agb1500_CH_CMU     -1     CMU channel                    */
/*                  agb1500_CH_1        1     Channel 1                      */
/*                  agb1500_CH_2        2     Channel 2                      */
/*                  agb1500_CH_3        3     Channel 3                      */
/*                  agb1500_CH_4        4     Channel 4                      */
/*                  agb1500_CH_5        5     Channel 5                      */
/*                  agb1500_CH_6        6     Channel 6                      */
/*                  agb1500_CH_7        7     Channel 7                      */
/*                  agb1500_CH_8        8     Channel 8                      */
/*                  agb1500_CH_9		9     Channel 9                      */
/*                  agb1500_CH_10      10     Channel 10				     */
/*                                                                           */
/*        value										     					 */
/*                  Data Type:  ViReal64                                     */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name                Value    Description                 */
/*                  agb1500_CMUV_MIN    -100.0                               */
/*                  agb1500_CMUV_MAX    100.0                                */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, 0, errStatus );        
    }
    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_forceCmuDcBias" );

    /* Check Prameter Range */
    if( !((channel == agb1500_CH_CMU) || ((channel >= agb1500_CH_1) && (channel <= agb1500_CH_10)))){
		agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2);
	}
	if( channel == agb1500_CH_CMU ){
		if( (channel = agb1500_RTN_CMU_UNT) == agb1500_NO_CMU ){
			return agb1500_NO_CMU_UNT;
		}
	}

    agb1500_CHK_REAL_RANGE( value, 
                agb1500_CMUV_MIN, agb1500_CMUV_MAX, 
                VI_ERROR_PARAMETER3);

    errStatus = viPrintf(vi,"DCV %d,%e\n", channel, value );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );

}/* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_forceCmuAcLevel(ViSession vi, ViInt32 channel, ViReal64 value )
/*****************************************************************************/
/*                                                                           */
/*      This function sets the AC Level for CMU                              */
/*                                                                           */
/*      The parameter 'channel' specifies the channel number of CMU          */
/*                                                                           */
/*      The parameter 'value' specifies the AC Level of CMU                  */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*        channel   Channel number of the CMU.                               */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name              Value   Description                    */
/*                  agb1500_CH_CMU     -1     CMU channel                    */
/*                  agb1500_CH_1        1     Channel 1                      */
/*                  agb1500_CH_2        2     Channel 2                      */
/*                  agb1500_CH_3        3     Channel 3                      */
/*                  agb1500_CH_4        4     Channel 4                      */
/*                  agb1500_CH_5        5     Channel 5                      */
/*                  agb1500_CH_6        6     Channel 6                      */
/*                  agb1500_CH_7        7     Channel 7                      */
/*                  agb1500_CH_8        8     Channel 8                      */
/*                  agb1500_CH_9		9     Channel 9                      */
/*                  agb1500_CH_10      10     Channel 10				     */
/*                                                                           */
/*        freqency															 */
/*                  Data Type:  ViReal64                                     */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name                Value    Description                 */
/*                  agb1500_CMUAC_MIN   0.0                                  */
/*                  agb1500_CMUAC_MAX   0.25                                 */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, 0, errStatus );        
    }
    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_forceCmuAcLevel" );

    /* Check Prameter Range */
    if( !((channel == agb1500_CH_CMU) || ((channel >= agb1500_CH_1) && (channel <= agb1500_CH_10)))){
		agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2);
	}
	if( channel == agb1500_CH_CMU ){
		if( (channel = agb1500_RTN_CMU_UNT) == agb1500_NO_CMU ){
			return agb1500_NO_CMU_UNT;
		}
	}

    agb1500_CHK_REAL_RANGE( value, 
                agb1500_CMUAC_MIN, agb1500_CMUAC_MAX, 
                VI_ERROR_PARAMETER3);

    errStatus = viPrintf(vi,"ACV %d,%e\n", channel, value );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );

}/* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_setCmuFreq(ViSession vi, ViInt32 channel, ViReal64 frequency )
/*****************************************************************************/
/*                                                                           */
/*      This function sets the measurement frequency of CMU                  */
/*                                                                           */
/*      The parameter 'channel' specifies the channel number of CMU          */
/*                                                                           */
/*      The parameter 'frequency' specifies the measurement frequency of CMU */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*        channel   Channel number of the CMU.                               */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name              Value   Description                    */
/*                  agb1500_CH_CMU     -1     CMU channel                    */
/*                  agb1500_CH_1        1     Channel 1                      */
/*                  agb1500_CH_2        2     Channel 2                      */
/*                  agb1500_CH_3        3     Channel 3                      */
/*                  agb1500_CH_4        4     Channel 4                      */
/*                  agb1500_CH_5        5     Channel 5                      */
/*                  agb1500_CH_6        6     Channel 6                      */
/*                  agb1500_CH_7        7     Channel 7                      */
/*                  agb1500_CH_8        8     Channel 8                      */
/*                  agb1500_CH_9		9     Channel 9                      */
/*                  agb1500_CH_10      10     Channel 10				     */
/*                                                                           */
/*        freqency															 */
/*                  Data Type:  ViReal64                                     */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name                Value    Description                 */
/*                  agb1500_CMUF_MIN    1000.0                               */
/*                  agb1500_CMUF_MAX    5000000.0                            */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, 0, errStatus );        
    }
    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_setCmuFreq" );

    /* Check Prameter Range */
    if( !((channel == agb1500_CH_CMU) || ((channel >= agb1500_CH_1) && (channel <= agb1500_CH_10)))){
		agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2);
	}
	if( channel == agb1500_CH_CMU ){
		if( (channel = agb1500_RTN_CMU_UNT) == agb1500_NO_CMU ){
			return agb1500_NO_CMU_UNT;
		}
	}

    agb1500_CHK_REAL_RANGE( frequency, 
                agb1500_CMUF_MIN, agb1500_CMUF_MAX, 
                VI_ERROR_PARAMETER3);

    errStatus = viPrintf(vi,"FC %d,%e\n", channel, frequency );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );

}/* ----- end of function ----- */
/*****************************************************************************/
ViStatus _VI_FUNC agb1500_setCv(ViSession vi, 
                               ViInt32 channel, ViInt32 mode,
                               ViReal64 start, ViReal64 stop, ViInt32 point,
                               ViReal64 hold, ViReal64 delay, ViReal64 s_delay)
/*****************************************************************************/
/*                                                                           */
/*      This function sets the primary CV sweep source for the C-V sweep.    */
/*                                                                           */
/*      To use the synchronous sweep source, execute the agb1500_setSweepSync*/
/*      function.                                                            */
/*                                                                           */
/*      To perform the staircase CV sweep measurements, execute the          */
/*      agb1500_sweepCv function.                                            */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      WDCV                                                                 */
/*      WTDCV                                                                */
/*                                                                           */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      channel    Channel number of the channel.                            */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_CMU  -1      CMU channel                       */
/*                 agb1500_CH_1     1      Channel 1                         */
/*                 agb1500_CH_2     2      Channel 2                         */
/*                 agb1500_CH_3     3      Channel 3                         */
/*                 agb1500_CH_4     4      Channel 4                         */
/*                 agb1500_CH_5     5      Channel 5                         */
/*                 agb1500_CH_6     6      Channel 6                         */
/*                 agb1500_CH_7     7      Channel 7                         */
/*                 agb1500_CH_8     8      Channel 8                         */
/*                 agb1500_CH_9     9      Channel 9                         */
/*                 agb1500_CH_10   10      Channel 10                        */
/*                                                                           */
/*         mode    Sweep source output mode.                                 */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                   Value   Description                */
/*                 agb1500_SWP_VF_SGLLIN   1     SINGLE LINEAR V             */
/*                 agb1500_SWP_VF_SGLLOG   2     SINGLE LOG V                */
/*                 agb1500_SWP_VF_DBLLIN   3     DOUBLE LINEAR V             */
/*                 agb1500_SWP_VF_DBLLOG   4     DOUBLE LOG V                */
/*                                                                           */
/*                                                                           */
/*        start    Sweep start value (in V).                                 */
/*                 For CMU (DC Bias Source): -25.0 V to 25.0 V               */
/*                 For SCUU (DC Bias Source): -100.0 V to 100.0 V            */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value                                   */
/*                 agb1500_CMUV_MIN   -100.0                                 */
/*                 agb1500_CMUV_MAX   100.0                                  */
/*                                                                           */
/*          stop   Sweep stop value (in A or V).                             */
/*                 For CMU (DC Bias Source): -25.0 V to 25.0 V               */
/*                 For SCUU (DC Bias Source): -100.0 V to 100.0 V            */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name              Value                                   */
/*                 agb1500_CMUV_MIN   -100.0                                 */
/*                 agb1500_CMUV_MAX   100.0                                  */
/*                                                                           */
/*         point   Number of sweep steps.                                    */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                   Value                              */
/*                 agb1500_SWP_POINT_MIN   1                                 */
/*                 agb1500_SWP_POINT_MAX   1001                              */
/*                                                                           */
/*         hold   Hold time (in second).                                     */
/*                Time since starting the sweep measurement until starting   */
/*                the delay time for the first sweep step.                   */
/*                Data Type:  ViReal64                                       */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                Name                  Value                                */
/*                agb1500_SWP_HOLD_MIN   0.00                                */
/*                agb1500_SWP_HOLD_MAX   655.35                              */
/*                                                                           */
/*        delay   Delay time (in second).                                    */
/*                Time since starting to force a step output value until     */
/*                starting a step measurement.                               */
/*                Data Type:  ViReal64                                       */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                Name                        Value                          */
/*                agb1500_SWP_DELAY_MIN       0.0                            */
/*                agb1500_SWP_DELAY_CMU_MAX   655.535                        */
/*                                                                           */
/*      s_delay   Step delay time (in second).                               */
/*                Time since starting a step measurement until starting      */
/*                the delay time for the next sweep step.                    */
/*                Data Type:  ViReal64                                       */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                Name                    Value                              */
/*                agb1500_SWP_SDELAY_MIN   0.0                               */
/*                agb1500_SWP_SDELAY_MAX   1.0                               */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct    agb1500_globals    *thisPtr;
    char    command[256] ;

    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_setCv" );


    /* Check Prameter Range */
    if( !((channel == agb1500_CH_CMU) || ((channel >= agb1500_CH_1) && (channel <= agb1500_CH_10)))){
		agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2);
	}
	if( channel == agb1500_CH_CMU ){
		if( (channel = agb1500_RTN_CMU_UNT) == agb1500_NO_CMU ){
			return agb1500_NO_CMU_UNT;
		}
	}

	agb1500_CHK_LONG_RANGE( mode, agb1500_SWP_VF_SGLLIN, agb1500_SWP_VF_DBLLOG,
							VI_ERROR_PARAMETER3);
    
    agb1500_CHK_REAL_RANGE( start, agb1500_CMUV_MIN, agb1500_CMUV_MAX, 
                           VI_ERROR_PARAMETER4);

    agb1500_CHK_REAL_RANGE( stop, agb1500_CMUV_MIN, agb1500_CMUV_MAX, 
                           VI_ERROR_PARAMETER5);

    agb1500_CHK_LONG_RANGE( point, agb1500_SWP_POINT_MIN, agb1500_SWP_POINT_MAX, 
                           VI_ERROR_PARAMETER6);

    agb1500_CHK_REAL_RANGE( hold, agb1500_SWP_HOLD_MIN, agb1500_SWP_HOLD_MAX, 
                           VI_ERROR_PARAMETER7);

    agb1500_CHK_REAL_RANGE( delay, agb1500_SWP_DELAY_MIN, agb1500_SWP_DELAY_CMU_MAX, 
                           VI_ERROR_PARAMETER8);

    agb1500_CHK_REAL_RANGE( s_delay, agb1500_SWP_SDELAY_MIN, agb1500_SWP_SDELAY_MAX, 
                           agb1500_INSTR_ERROR_PARAMETER9);

    /*--- Set Command ---*/
    sprintf( command, "WDCV %d,%d,%E,%E,%d", 
                channel, mode, start, stop, point );
      
    errStatus = viPrintf(vi,"%s\n", command );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    sprintf( command, "WTDCV %E,%E,%E", hold, delay, s_delay );

    errStatus = viPrintf(vi,"%s\n", command );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }
    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */
/*****************************************************************************/
ViStatus _VI_FUNC agb1500_spotCmuMeas(ViSession vi, ViInt32 channel,
                                      ViInt32 mode, ViReal64 range,
                                      ViReal64 data[], ViInt32 status[],
									  ViReal64 monitor[], ViInt32 status_mon[],
                                      ViPReal64 time)
/*****************************************************************************/
/*                                                                           */
/*      This function performs high speed spot measurement of capacitance,   */
/*      and returns the measurement data, measurement status,                */ 
/*      AC Level monitor voltage, DC Bias monitor voltage                    */
/*      and time stamp data.                                                 */
/*                                                                           */
/*      The parameter 'channel' specifies the measurement channel.           */
/*      The parameter 'mode' specifies the measurement mode.                 */
/*      The parameter 'range' specifies the measurement ranging type.        */
/*      The parameter 'data[]' returns the measurement data.                 */
/*      Two-dimensional array.                                               */
/*      The parameter 'status[]' returns the measurement status.             */
/*      Two-dimensional array.                                               */
/*      The parameter 'monitor[]' returns the monitor data.				     */
/*      Two-dimensional array.                                               */
/*      The parameter 'status_mon[]' returns the monitor status.             */
/*      Two-dimensional array.                                               */
/*      The parameter 'time' returns the time stamp data.                    */
/*                                                                           */
/*      Primary measurement data, secondary measurement data,                */
/*		primary measurement status, and secondary measurement status will    */
/*      be returned by data[0], data[1], status[0], and status[1],           */
/*      respectively.                                                        */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      FMT                                                                  */
/*      IMP                                                                  */
/*      LMN                                                                  */
/*      TTC                                                                  */
/*                                                                           */
/*      Control:      CMU                                                    */
/*																			 */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*                                                                           */
/*      channel    Channel number of the channelof the CMU.                  */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_CMU  -1      CMU channel                       */
/*                 agb1500_CH_1     1      Channel 1                         */
/*                 agb1500_CH_2     2      Channel 2                         */
/*                 agb1500_CH_3     3      Channel 3                         */
/*                 agb1500_CH_4     4      Channel 4                         */
/*                 agb1500_CH_5     5      Channel 5                         */
/*                 agb1500_CH_6     6      Channel 6                         */
/*                 agb1500_CH_7     7      Channel 7                         */
/*                 agb1500_CH_8     8      Channel 8                         */
/*                 agb1500_CH_9     9      Channel 9						 */
/*                 agb1500_CH_10   10      Channel 10						 */
/*                                                                           */
/*         mode    CMU Impedance measurement mode.                           */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name					Value   Description                  */
/*                 agb1500_CMUM_R_X		1       R-X Mode					 */
/*                 agb1500_CMUM_G_B		2       G-B Mode                     */
/*                 agb1500_CMUM_Z_TRAD  10      Z-Theta(radian) Mode         */
/*                 agb1500_CMUM_Z_TDEG  11      Z-Theta(degree) Mode         */
/*                 agb1500_CMUM_Y_TRAD  20      Y-Theta(radian) Mode         */
/*                 agb1500_CMUM_Y_TDEG  21      Y-Theta(degree) Mode         */
/*                 agb1500_CMUM_CP_G    100     Cp-G Mode                    */
/*                 agb1500_CMUM_CP_D    101     Cp-D Mode                    */
/*                 agb1500_CMUM_CP_Q    102     Cp-Q Mode                    */
/*                 agb1500_CMUM_CP_RP   103     Cp-Rp Mode                   */
/*                 agb1500_CMUM_CS_RS   200     Cs-Rs Mode                   */
/*                 agb1500_CMUM_CS_D    201     Cs-D Mode                    */
/*                 agb1500_CMUM_CS_Q	202		Cs-Q Mode                    */
/*                 agb1500_CMUM_LP_G    300     Lp-G Mode                    */
/*                 agb1500_CMUM_LP_D    301     Lp-D Mode                    */
/*                 agb1500_CMUM_LP_Q    302     Lp-Q Mode                    */
/*                 agb1500_CMUM_LP_RP   303     Lp-Rp Mode                   */
/*                 agb1500_CMUM_LS_RS   400     Ls-Rs Mode                   */
/*                 agb1500_CMUM_LS_D    401     Ls-D Mode                    */
/*                 agb1500_CMUM_LS_Q    402     Ls-Q Mode                    */     
/*                                                                           */
/*        range    Output ranging type.                                      */
/*                 For auto ranging: Enter 0 (zero).                         */
/*                 For fixed ranging: Enter positive value.                  */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*        data[]   Measurement data.                                         */
/*                 Data Type:  ViReal64[]                                    */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*       status[]  Measurement status.To disable the status data output,     */
/*                 set 0 (NULL pointer) instead of variable.                 */
/*                 Data Type:  ViInt32[]                                     */
/*                 Input/Output:  OUT                                        */
/*                 Values:                                                   */
/*                 Name                  Value   Description                 */
/*                 agb1500_STAT_OVF_BIT   1      AD converter overflowed.    */
/*                 agb1500_STAT_NLUB_BIT  -2     Null Loop Unbalance.        */
/*                 agb1500_STAT_ASAT_BIT  -3     IV Amp Saturation.          */
/*                                                                           */
/*      monitor[]  Monitor data.                                             */
/*                 monitor[0]: AC Level monitor data                         */
/*                 monitor[1]: DC Bias monitor data                          */
/*                 Data Type:  ViReal64[]                                    */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*   status_mon[]  Monitor status.                                           */
/*                 status_mon[0]: AC Level monitor status                    */
/*                 status_mon[1]: DC Bias monitor status                     */              
/*                 To disable the status data output,                        */
/*                 set 0 (NULL pointer) instead of variable.                 */
/*                 Data Type:  ViInt32[]                                     */
/*                 Input/Output:  OUT                                        */
/*                 Values:                                                   */
/*                 Name                  Value   Description                 */
/*                 agb1500_STAT_OVF_BIT   1      AD converter overflowed.    */
/*                 agb1500_STAT_NLUB_BIT  -2     Null Loop Unbalance.        */
/*                 agb1500_STAT_ASAT_BIT  -3     IV Amp Saturation.          */
/*                                                                           */
/*        time    Time stamp data (measurement start time).                  */
/*                To disable the time stamp data output, set 0 (NULL pointer)*/
/*                instead of variable.                                       */
/*                Data Type:  ViPReal64                                      */
/*                Input/Output:  OUT                                         */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
 
{
    ViStatus errStatus = 0;
    struct agb1500_globals *thisPtr;

    ViReal64  get_value ;
    ViInt32   get_status ;
    ViInt32   get_eod ;
    ViInt32   channelNo;
    ViInt32   dataKind;
	ViChar	  cmd_buf[256];
	ViInt16   i_mon,i_meas;

   errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
   if ( errStatus < VI_SUCCESS)   {
       agb1500_LOG_STATUS( vi, 0, errStatus );
   }
   agb1500_DEBUG_CHK_THIS( vi, thisPtr );
   agb1500_CDE_INIT( "agb1500_spotCmuMeas" );

    /* Check Prameter Range */
    if( !((channel == agb1500_CH_CMU) || ((channel >= agb1500_CH_1) && (channel <= agb1500_CH_10)))){
		agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2);
	}
	if( channel == agb1500_CH_CMU ){
		if( (channel = agb1500_RTN_CMU_UNT) == agb1500_NO_CMU ){
			return agb1500_NO_CMU_UNT;
		}
	}

    agb1500_CHK_IMP_MEAS_MODE( mode, VI_ERROR_PARAMETER3);

	if( range < 0 ){
		agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER4);
	}
                         
    /* Instrument I/O */
    errStatus = viPrintf(vi,"FMT 21,0\n");

    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

	/* Set CMU Impedance Measurement Mode */
	errStatus = viPrintf(vi,"IMP %d\n", mode);
    if ( errStatus < VI_SUCCESS) {
		agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

	/* Set Level Monitor Mode */
	if ( monitor != (ViReal64 *) NULL ){
		errStatus = viPrintf(vi, "LMN 1\n");		/* Monitor ON */
		if ( errStatus < VI_SUCCESS) {
			agb1500_LOG_STATUS( vi, thisPtr, errStatus );
		}
	}else{
		errStatus = viPrintf(vi, "LMN 0\n");		/* Monitor OFF */
		if ( errStatus < VI_SUCCESS) {
			agb1500_LOG_STATUS( vi, thisPtr, errStatus );
		}
	}

    if ( time != (ViReal64 *) NULL) {
		if( range == 0.0 ){
			sprintf( cmd_buf, "TTC %d,0", channel);
		}else{
			sprintf( cmd_buf, "TTC %d,2,%e", channel, range );
		}
	}else{
		if( range == 0.0 ){
			sprintf( cmd_buf, "TC %d,0", channel);
		}else{
			sprintf( cmd_buf, "TC %d,2,%e", channel, range );
		}
	}

	errStatus = viPrintf(vi,"%s\n", cmd_buf );
    if ( errStatus < VI_SUCCESS) {
		agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }
    
	agb1500_CHK_INST_ERR_AFTER_XE( vi, thisPtr );

    /*--- get measurement data ---*/
    get_eod = 0;
	i_mon = 0;
	i_meas = 0;
    for ( ;get_eod == 0; ) {
        errStatus = asciiDataRead( vi,&dataKind, &get_value, &get_status,&channelNo, &get_eod );
        if ( errStatus < VI_SUCCESS)  {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
        if ( dataKind == agb1500_DT_TM) {
            if ( time != (ViReal64 *)NULL)
                *time = get_value;
        }else if ( dataKind == agb1500_DT_VM ){
			monitor[i_mon] = get_value;
			if ( status_mon != (ViInt32 * )NULL ){
				status_mon[i_mon] = get_status ;
			}
			i_mon++;
		}else {
            data[i_meas] = get_value;
            if ( status !=(ViInt32 *)NULL) {
                status[i_meas] = get_status ;
            }
			i_meas++;
        }
    }
    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */
/*****************************************************************************/
ViStatus _VI_FUNC agb1500_sweepCv(ViSession vi, 
                               ViInt32 channel, ViInt32 mode, ViReal64 range,
                               ViPInt32 point, ViReal64 source[], 
                               ViReal64 value[], ViInt32 status[],
							   ViReal64 monitor[],ViInt32 status_mon[],
							   ViReal64 time[])
/*****************************************************************************/
/*                                                                           */
/*      This function performs C-V sweep measurement, and returns            */
/*      the number of measurement points, sweep source data, measurement     */
/*      data, measurement status, AC level monitor data,                     */
/*      DC Bias monitor data, AC level monitor status,                       */
/*      DC Bias monitor status and time stamp data.                          */
/*      Before executing this function, execute the agb1500_setCv function   */
/*      to set the sweep source.                                             */
/*                                                                           */
/*      The parameter 'channel' specifies the measurement channel.           */
/*      The parameter 'mode' specifies the measurement mode.                 */
/*      The parameter 'range'  specifies the measurement ranging type.       */
/*      The parameter 'point' returns the number of measurement points.      */
/*      The parameter 'source[ ] ' returns the sweep source data.            */
/*      The parameter 'value[ ]' returns the measurement data.               */
/*      Two-dimensional array.                                               */            
/*      The parameter 'status[ ]' returns the measurement status.            */ 
/*      Two-dimensional array.                                               */
/*      The parameter 'monitor[]' returns the monitor data.                  */
/*      Two-dimensional array.                                               */
/*      The parameter 'status_mon[]' returns the monitor status.             */
/*      The parameter 'time[ ]' returns the time stamp data.                 */ 
/*																			 */
/*      The parameter must be declared as shown below:                       */
/*      ViReal64 source[M]                                                   */
/*      ViReal64 value[M][N]                                                 */
/*      ViReal64 status[M][N]                                                */
/*      ViReal64 monitor[M][L]                                               */
/*      ViInt32 status_mon[M]{L]                                             */
/*      ViReal64 time[M]                                                     */
/*      Where,                                                               */
/*      N: Number of measurement parameter (2 or more)                       */
/*      L: Number of monitor parameter ( 2 or more)                          */
/*      M: Number of sweep points                                            */
/*        ('point' parameter value of agb1500_setCv function or mode)        */
/*                                                                           */
/*      Sweep Source data and time stamp data will be returned by source[i]  */
/*      and time[i]. Primary measurement data, secondary measurement data,   */
/*      primary measurement status, and secondary measurement status wiil    */
/*      be returned by value[i][0], value[i][1], status[i][0] and            */
/*      status[i][1], respectively. And AC level monitor, DC bias monitor,   */
/*      AC level monitor status and DC bias monitor status will be returned  */
/*      by monitor[i][0], monitor[i][1], status_mon[i][0] and                */
/*      status_mon[i][1], respectively.                                      */
/*                                                                           */
/*      This function implements the following commands:                     */
/*                                                                           */
/*      FMT                                                                  */
/*      TSC                                                                  */
/*      MM                                                                   */
/*      LMN                                                                  */
/*      IMP                                                                  */
/*      XE                                                                   */
/*                                                                           */
/*   Parameter        Description                                            */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*                                                                           */
/*      channel    Channel number of the measurement channel.                */
/*                 Same as the slot number for the SMU.                      */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_CMU  -1      CMU channel                       */
/*                 agb1500_CH_1     1      Channel 1                         */
/*                 agb1500_CH_2     2      Channel 2                         */
/*                 agb1500_CH_3     3      Channel 3                         */
/*                 agb1500_CH_4     4      Channel 4                         */
/*                 agb1500_CH_5     5      Channel 5                         */
/*                 agb1500_CH_6     6      Channel 6                         */
/*                 agb1500_CH_7     7      Channel 7                         */
/*                 agb1500_CH_8     8      Channel 8                         */
/*                 agb1500_CH_9		9      Channel 9						 */
/*                 agb1500_CH_10   10	   Channel 10					     */
/*                                                                           */
/*         mode    CMU Impedance measurement mode.                           */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name					Value   Description                  */
/*                 agb1500_CMUM_R_X		1       R-X Mode					 */
/*                 agb1500_CMUM_G_B		2       G-B Mode                     */
/*                 agb1500_CMUM_Z_TRAD  10      Z-Theta(radian) Mode         */
/*                 agb1500_CMUM_Z_TDEG  11      Z-Theta(degree) Mode         */
/*                 agb1500_CMUM_Y_TRAD  20      Y-Theta(radian) Mode         */
/*                 agb1500_CMUM_Y_TDEG  21      Y-Theta(degree) Mode         */
/*                 agb1500_CMUM_CP_G    100     Cp-G Mode                    */
/*                 agb1500_CMUM_CP_D    101     Cp-D Mode                    */
/*                 agb1500_CMUM_CP_Q    102     Cp-Q Mode                    */
/*                 agb1500_CMUM_CP_RP   103     Cp-Rp Mode                   */
/*                 agb1500_CMUM_CS_RS   200     Cs-Rs Mode                   */
/*                 agb1500_CMUM_CS_D    201     Cs-D Mode                    */
/*                 agb1500_CMUM_CS_Q	202		Cs-Q Mode                    */
/*                 agb1500_CMUM_LP_G    300     Lp-G Mode                    */
/*                 agb1500_CMUM_LP_D    301     Lp-D Mode                    */
/*                 agb1500_CMUM_LP_Q    302     Lp-Q Mode                    */
/*                 agb1500_CMUM_LP_RP   303     Lp-Rp Mode                   */
/*                 agb1500_CMUM_LS_RS   400     Ls-Rs Mode                   */
/*                 agb1500_CMUM_LS_D    401     Ls-D Mode                    */
/*                 agb1500_CMUM_LS_Q    402     Ls-Q Mode                    */   
/*                                                                           */
/*        range    Output ranging type.                                      */
/*                 For auto ranging: Enter 0 (zero).                         */
/*                 For fixed ranging: Enter positive value.                  */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*        point    Number of measurement points.                             */
/*                 Data Type:  ViPInt32                                      */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*     source[ ]   Sweep source data.                                        */
/*                 To disable the sweep source data output,                  */
/*                 set 0 (NULL pointer) instead of source.                   */
/*                 Data Type:  ViReal64 [ ]                                  */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*      value[ ]   Measurement data.                                         */
/*                 Data Type:  ViPReal64[ ]                                  */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*       status[]  Measurement status.To disable the status data output,     */
/*                 set 0 (NULL pointer) instead of variable.                 */
/*                 Data Type:  ViInt32[]                                     */
/*                 Input/Output:  OUT                                        */
/*                 Values:                                                   */
/*                 Name                  Value   Description                 */
/*                 agb1500_STAT_OVF_BIT   1      AD converter overflowed.    */
/*                 agb1500_STAT_NLUB_BIT  -2     Null Loop Unbalance.        */
/*                 agb1500_STAT_ASAT_BIT  -3     IV Amp Saturation.          */
/*                                                                           */
/*      monitor[]  Monitor data.                                             */
/*                 monitor[0]: AC Level monitor data                         */
/*                 monitor[1]: DC Bias monitor data                          */
/*                 Data Type:  ViReal64[]                                    */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*   status_mon[]  Monitor status.                                           */
/*                 status_mon[0]: AC Level monitor status                    */
/*                 status_mon[1]: DC Bias monitor status                     */              
/*                 To disable the status data output,                        */
/*                 set 0 (NULL pointer) instead of variable.                 */
/*                 Data Type:  ViInt32[]                                     */
/*                 Input/Output:  OUT                                        */
/*                 Values:                                                   */
/*                 Name                  Value   Description                 */
/*                 agb1500_STAT_OVF_BIT   1      AD converter overflowed.    */
/*                 agb1500_STAT_NLUB_BIT  -2     Null Loop Unbalance.        */
/*                 agb1500_STAT_ASAT_BIT  -3     IV Amp Saturation.          */
/*                                                                           */
/*                                                                           */
/*     time[ ]    Time stamp data (measurement start time).                  */
/*                To disable the time stamp data output, set 0 (NULL pointer)*/
/*                instead of array.                                          */
/*                Data Type:  ViPReal64[ ]                                   */
/*                Input/Output:  OUT                                         */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/

{
    ViStatus errStatus = 0 ;
    struct    agb1500_globals    *thisPtr;
    int        cnt ;
    ViInt32        getStatus ;
    ViInt32        eod ;
    ViReal64    getValue ;
    ViInt32   dataKind;
   
    *point = 0;

#define agb1500_CMU_PRIMARY_MEAS_INDEX		0
#define agb1500_CMU_SECONDARY_MEAS_INDEX	1
#define agb1500_CMU_AC_MONITOR_INDEX		0
#define agb1500_CMU_DC_MONITOR_INDEX		1
    
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        return( errStatus );
    }

    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_sweepCv" );


    /* Check Prameter Range */
    if( !((channel == agb1500_CH_CMU) || ((channel >= agb1500_CH_1) && (channel <= agb1500_CH_10)))){
		agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2);
	}
	if( channel == agb1500_CH_CMU ){
		if( (channel = agb1500_RTN_CMU_UNT) == agb1500_NO_CMU ){
			return agb1500_NO_CMU_UNT;
		}
	}
    
    agb1500_CHK_IMP_MEAS_MODE( mode, VI_ERROR_PARAMETER3);

	if( range < 0 ){
		agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER4);
	}


    /*--- Set Command ---*/
    if ( source == (ViReal64 *)NULL ) {

        errStatus = viPrintf(vi,"FMT 21,0\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }

    }
    else {

        errStatus = viPrintf(vi,"FMT 21,1\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }

    }

    if ( time == (ViReal64 *)NULL) {

        errStatus = viPrintf(vi,"TSC 0\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }
    else {

        errStatus = viPrintf(vi,"TSC 1\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }

    errStatus = viPrintf(vi,"MM 18,%d\n", channel );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }


    /* Set CMU Impedance Measurement Mode */
	errStatus = viPrintf(vi,"IMP %d\n", mode);
    if ( errStatus < VI_SUCCESS) {
		agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

	/* Set Level Monitor Mode */
	if ( monitor != (ViReal64 *) NULL ){
		errStatus = viPrintf(vi, "LMN 1\n");		/* Monitor ON */
		if ( errStatus < VI_SUCCESS) {
			agb1500_LOG_STATUS( vi, thisPtr, errStatus );
		}
	}else{
		errStatus = viPrintf(vi, "LMN 0\n");		/* Monitor OFF */
		if ( errStatus < VI_SUCCESS) {
			agb1500_LOG_STATUS( vi, thisPtr, errStatus );
		}
	}

	/* Set Measurement Range */
	if ( range == 0 ){
		errStatus = viPrintf(vi, "RC %d,0,%e\n",channel,range);
	}else{
		errStatus = viPrintf(vi, "RC %d,2,%e\n",channel,range);
	}
	if( errStatus < VI_SUCCESS ){
		agb1500_LOG_STATUS(vi, thisPtr, errStatus );
	}

    agb1500_CHK_INST_ERR( vi, thisPtr );

    errStatus = viPrintf(vi,"XE\n" );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_CHK_INST_ERR_AFTER_XE( vi, thisPtr );
   
    eod = 0;
    cnt = 0;

    do {        
        /*--- Read Time stamp Data ---*/       
        if ( time != (ViReal64 *)NULL) {
            if ( eod == 0) {
                errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
                if ( errStatus < VI_SUCCESS) {
                    agb1500_LOG_STATUS( vi, thisPtr, errStatus );
                }

                if ( dataKind == agb1500_DT_TM) {         
                    time[cnt] = getValue;
                }
                else {
                    return (agb1500_MEAS_DATA_INCONSISTENCY);
                }
            }
            else {
                time[cnt] = agb1500_DUMMY_TIMESTAMP;
            }
        }

        /*--- Read Primary Measurement Data ---*/
        if (eod == 0) {
            errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
            if ( errStatus < VI_SUCCESS) {
                agb1500_LOG_STATUS( vi, thisPtr, errStatus );
            }
   
            if ( dataKind == agb1500_DT_ZM || dataKind == agb1500_DT_YM ||
				 dataKind == agb1500_DT_CM || dataKind == agb1500_DT_DM ||
				 dataKind == agb1500_DT_QM || dataKind == agb1500_DT_LM ||
				 dataKind == agb1500_DT_RM || dataKind == agb1500_DT_PM) {         
                value[agb1500_CMU_PRIMARY_MEAS_INDEX + 2*cnt] = getValue;
                /*--- Set Status ---*/
                if ( status != (ViInt32 *)NULL ) {
                    status[agb1500_CMU_PRIMARY_MEAS_INDEX + 2*cnt] = getStatus ;
                }
            }
            else {
                return (agb1500_MEAS_DATA_INCONSISTENCY);
            }
        }
        else {
            value[agb1500_CMU_PRIMARY_MEAS_INDEX + 2*cnt] = agb1500_DUMMY_VALUE;
            /*--- Set Status ---*/
            if ( status != (ViInt32 *)NULL ) {
                status[agb1500_CMU_PRIMARY_MEAS_INDEX + 2*cnt] = agb1500_DUMMY_STATUS ;
            }
        }

		/*--- Read Secondary Measurement Data ---*/
		if (eod == 0) {
            errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
            if ( errStatus < VI_SUCCESS) {
                agb1500_LOG_STATUS( vi, thisPtr, errStatus );
            }
   
            if ( dataKind == agb1500_DT_ZM || dataKind == agb1500_DT_YM ||
				 dataKind == agb1500_DT_CM || dataKind == agb1500_DT_DM ||
				 dataKind == agb1500_DT_QM || dataKind == agb1500_DT_LM ||
				 dataKind == agb1500_DT_RM || dataKind == agb1500_DT_PM) {         
                value[agb1500_CMU_SECONDARY_MEAS_INDEX + 2*cnt] = getValue;
                /*--- Set Status ---*/
                if ( status != (ViInt32 *)NULL ) {
                    status[agb1500_CMU_SECONDARY_MEAS_INDEX + 2*cnt] = getStatus ;
                }
            }
            else {
                return (agb1500_MEAS_DATA_INCONSISTENCY);
            }
        }
        else {
            value[agb1500_CMU_SECONDARY_MEAS_INDEX + 2*cnt] = agb1500_DUMMY_VALUE;
            /*--- Set Status ---*/
            if ( status != (ViInt32 *)NULL ) {
                status[agb1500_CMU_SECONDARY_MEAS_INDEX + 2*cnt] = agb1500_DUMMY_STATUS ;
            }
        }

		/*--- Read AC Level Monitor Data ---*/
        if ( monitor != (ViReal64 *)NULL) {
			if (eod == 0) {
				errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
				if ( errStatus < VI_SUCCESS) {
					agb1500_LOG_STATUS( vi, thisPtr, errStatus );
				}
   
				if ( dataKind == agb1500_DT_VM ) {         
					monitor[agb1500_CMU_AC_MONITOR_INDEX + 2*cnt] = getValue;
					/*--- Set Status ---*/
					if ( status_mon != (ViInt32 *)NULL ) {
						status_mon[agb1500_CMU_AC_MONITOR_INDEX + 2*cnt] = getStatus ;
					}
				}
				else {
					return (agb1500_MEAS_DATA_INCONSISTENCY);
				}
			}
			else {
				monitor[agb1500_CMU_AC_MONITOR_INDEX + 2*cnt] = agb1500_DUMMY_VALUE;
				/*--- Set Status ---*/
				if ( status_mon != (ViInt32 *)NULL ) {
					status_mon[agb1500_CMU_AC_MONITOR_INDEX + 2*cnt] = agb1500_DUMMY_STATUS ;
				}
			}

			/*--- Read DC Bias Monitor Data ---*/
			if (eod == 0) {
				errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
				if ( errStatus < VI_SUCCESS) {
					agb1500_LOG_STATUS( vi, thisPtr, errStatus );
				}
   
				if ( dataKind == agb1500_DT_VM ) {         
					monitor[agb1500_CMU_DC_MONITOR_INDEX + 2*cnt] = getValue;
					/*--- Set Status ---*/
					if ( status_mon != (ViInt32 *)NULL ) {
						status_mon[agb1500_CMU_DC_MONITOR_INDEX + 2*cnt] = getStatus ;
					}
				}
				else {
					return (agb1500_MEAS_DATA_INCONSISTENCY);
				}
			}
			else {
				monitor[agb1500_CMU_DC_MONITOR_INDEX + 2*cnt] = agb1500_DUMMY_VALUE;
				/*--- Set Status ---*/
				if ( status_mon != (ViInt32 *)NULL ) {
					status_mon[agb1500_CMU_DC_MONITOR_INDEX + 2*cnt] = agb1500_DUMMY_STATUS ;
				}
			}
		}
        /*--- Read Source Data ---*/
        if ( source != (ViReal64 *)NULL) {
            if ( eod == 0) {
                errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
                if ( errStatus < VI_SUCCESS) {
                    agb1500_LOG_STATUS( vi, thisPtr, errStatus );
                }
  
                if ( dataKind == agb1500_DT_VS || dataKind == agb1500_DT_IS) {
                    source[cnt] = getValue;               
                }
                else {
                    return (agb1500_MEAS_DATA_INCONSISTENCY);
                }
            }
            else {
                source[cnt] = agb1500_DUMMY_VALUE;
            }
        }
         
        cnt++;
   
    } while(eod == 0);
        
    /*--- Set Point ---*/
    *point = cnt ;

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
} /* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_scuuLed(ViSession vi, ViInt32 channel, ViInt32 mode )
/*****************************************************************************/
/*                                                                           */
/*      This function enables/disables the LED of SCUU connected to CMU.     */
/*                                                                           */
/*      The parameter 'channel' specifies the channel number of the CMU(SCUU)*/
/*                                                                           */
/*      The parameter 'mode' specifies the status of LED                     */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*        channel   Channel number of the CMU that SCUU is connected.        */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name              Value   Description                    */
/*                  agb1500_CH_CMU	   -1     CMU channel					 */
/*                  agb1500_CH_1        1     Channel 1                      */
/*                  agb1500_CH_2        2     Channel 2                      */
/*                  agb1500_CH_3        3     Channel 3                      */
/*                  agb1500_CH_4        4     Channel 4                      */
/*                  agb1500_CH_5        5     Channel 5                      */
/*                  agb1500_CH_6        6     Channel 6                      */
/*                  agb1500_CH_7        7     Channel 7                      */
/*                  agb1500_CH_8        8     Channel 8                      */
/*                  agb1500_CH_9		9     Channel 9                      */
/*                  agb1500_CH_10      10     Channel 10				     */
/*                                                                           */
/*        mode     Select 0 for LED OFF.                                     */
/*                 Select 1 for LED ON.                                      */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                Value    Description                  */
/*                 agb1500_FLAG_OFF      0       LED OFF                     */
/*                 agb1500_FLAG_ON       1       LED ON                      */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, 0, errStatus );        
    }
    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_scuuLed" );

    /* Check Prameter Range */
	if( !((channel == agb1500_CH_CMU) || ((channel >= agb1500_CH_1) && (channel <= agb1500_CH_10)))){
		agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2);
	}
	if( channel == agb1500_CH_CMU ){
		if( (channel = agb1500_RTN_CMU_UNT) == agb1500_NO_CMU ){
			return agb1500_NO_CMU_UNT;
		}
	}

    agb1500_CHK_LONG_RANGE( mode, 
                agb1500_FLAG_OFF, agb1500_FLAG_ON, 
                VI_ERROR_PARAMETER3);

    errStatus = viPrintf(vi,"SSL %d,%d\n", channel, mode );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );

}/* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_scuuPath(ViSession vi, ViInt32 channel, ViInt32 path )
/*****************************************************************************/
/*                                                                           */
/*      This function sets the SCUU path                                     */
/*                                                                           */
/*      The parameter 'channel' specifies the channel number of the CMU(SCUU)*/
/*                                                                           */
/*      The parameter 'path' specifies SCUU connection path                  */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*        channel   Channel number of the CMUthat SCUU is connected.         */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name              Value   Description                    */
/*                  agb1500_CH_CMU     -1     CMU channel                    */
/*                  agb1500_CH_1        1     Channel 1                      */
/*                  agb1500_CH_2        2     Channel 2                      */
/*                  agb1500_CH_3        3     Channel 3                      */
/*                  agb1500_CH_4        4     Channel 4                      */
/*                  agb1500_CH_5        5     Channel 5                      */
/*                  agb1500_CH_6        6     Channel 6                      */
/*                  agb1500_CH_7        7     Channel 7                      */
/*                  agb1500_CH_8        8     Channel 8                      */
/*                  agb1500_CH_9        9     Channel 9                      */
/*                  agb1500_CH_10      10     Channel 10                     */ 
/*                                                                           */
/*        path     Select 1 for Relay Path SMU (SMUH).                       */      
/*                 Select 2 for Relay Path SMU (SMUL).                       */
/*                 Select 3 for Relay Path SMU (SMUH and SMUL).              */
/*                 Select 4 for Relay Path CMU (CMU Bias Path).              */                
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                Value    Description                  */
/*                 agb1500_SCUU_SMUH   1        Relay Path SMU(SMUH)         */
/*                 agb1500_SCUU_SMUL   2        Relay Path SMU(SMUL)         */
/*                 agb1500_SCUU_SMUHL  3        Relay Path SMU(SMUH and SMUL)*/
/*                 agb1500_SCUU_CMU    4        Relay Path CMU(CMU Bias Path)*/
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, 0, errStatus );        
    }
    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_scuuPath" );

    /* Check Prameter Range */
    if( !((channel == agb1500_CH_CMU) || ((channel >= agb1500_CH_1) && (channel <= agb1500_CH_10)))){
		agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2);
	}
	if( channel == agb1500_CH_CMU ){
		if( (channel = agb1500_RTN_CMU_UNT) == agb1500_NO_CMU ){
			return agb1500_NO_CMU_UNT;
		}
	}

    agb1500_CHK_LONG_RANGE( path, 
                agb1500_SCUU_SMUH, agb1500_SCUU_CMU, 
                VI_ERROR_PARAMETER3);

    errStatus = viPrintf(vi,"SSP %d,%d\n", channel, path );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );

}/* ----- end of function ----- */

/*---------------------------------------------------------------------------*/
 ViStatus _VI_FUNC agb1500_setSample(ViSession vi, 
                               ViReal64 bias_hold, ViReal64 base_hold, ViReal64 interval, ViInt32 point) 
/*---------------------------------------------------------------------------*/
/*                                                                           */
/*      This function specifies the measurement timing of the sampling       */
/*      measurements. The sampling measurement units are defined by          */
/*      the agb1500_sample function.                                         */                                                                          
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*     channel     Channel number of the channel.  Same as the slot number   */
/*                 for the SMU.                                              */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_1      1     Channel 1                         */
/*                 agb1500_CH_2      2     Channel 2                         */
/*                 agb1500_CH_3      3     Channel 3                         */
/*                 agb1500_CH_4      4     Channel 4                         */
/*                 agb1500_CH_5      5     Channel 5                         */
/*                 agb1500_CH_6      6     Channel 6                         */
/*                 agb1500_CH_7      7     Channel 7                         */
/*                 agb1500_CH_8      8     Channel 8                         */
/*                 agb1500_CH_9      9     Channel 9                         */
/*                 agb1500_CH_10    10     Channel 10                        */
/*                                                                           */
/*   bias_hold     Bias hold time (in second ).                              */       
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                    Value    Description              */
/*                 agb1500_SMP_HOLD_MIN    -0.09                             */
/*                 agb1500_SMP_HOLD_MAX    655.35                            */
/*																			 */
/*   base_hold     Base hold time (in second ).                              */       
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                    Value    Description              */
/*                 agb1500_SMP_HOLD_MIN    0.00                              */
/*                 agb1500_SMP_HOLD_MAX    655.35                            */
/*                                                                           */
/*     interval    Sampling interval ( in second ).                          */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                    Value    Description              */
/*                 agb1500_SMP_INTVL_MIN   0.0001                            */
/*                 agb1500_SMP_INTVL_MAX   65.535                            */
/*                                                                           */
/*        point    Number of sampling points.                                */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                    Value    Description              */
/*                 agb1500_SMP_POINT_MIN   1                                 */
/*                 agb1500_SMP_POINT_MAX   100001                            */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{

    ViStatus errStatus = 0 ;
	struct	agb1500_globals	*thisPtr;
	ViChar	cmd_buf[256] ;
   
	errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
	if (errStatus < VI_SUCCESS) {
		return( errStatus ) ;
	}

	agb1500_DEBUG_CHK_THIS( vi, thisPtr );
	agb1500_CDE_INIT( "agb1500_setSample" );

	/* Check Prameter Range */
	agb1500_CHK_REAL_RANGE( bias_hold, agb1500_SMP_HOLD_MIN, agb1500_SMP_HOLD_MAX, 
	                        VI_ERROR_PARAMETER2);
	
	agb1500_CHK_REAL_RANGE( base_hold, agb1500_SMP_HOLD_MIN, agb1500_SMP_HOLD_MAX,
							VI_ERROR_PARAMETER3);

	agb1500_CHK_REAL_RANGE( interval, agb1500_SMP_INTVL_MIN, agb1500_SMP_INTVL_MAX, 
	                        VI_ERROR_PARAMETER4);

	agb1500_CHK_LONG_RANGE( point, agb1500_SMP_POINT_MIN, agb1500_SMP_POINT_MAX, 
	                        VI_ERROR_PARAMETER5);

	/*--- Set Command ---*/
	sprintf( cmd_buf, "MT %E,%E,%d,%E", bias_hold, interval, point,base_hold ) ;


	errStatus = viPrintf(vi,"%s\n", cmd_buf ) ;
	if (errStatus < VI_SUCCESS) {
		agb1500_LOG_STATUS( vi, thisPtr, errStatus );
	}

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
}/* ----- end of function ----- */
/*---------------------------------------------------------------------------*/
ViStatus _VI_FUNC agb1500_addSampleSyncIv(ViSession vi, 
                               ViInt32 channel, ViInt32 mode, ViReal64 range,
                               ViReal64 base, ViReal64 bias, ViReal64 comp )
/*---------------------------------------------------------------------------*/
/*                                                                           */
/*      This function specifies the constant current source or constant      */
/*      voltage source used for the sampling measurements, and sets the      */
/*      parameters. Source output starts at the beginning of the sampling    */
/*      measurement (beginning of the hold time), and stops at the end of    */
/*      the last sampling measurement points.                                */
/*                                                                           */
/*      Sampling measurement channels are defined by the agb1500_sample      */
/*      function, and sampling measurement timing is defined by              */
/*      agb1500_setSample function.                                          */                              
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*     channel     Channel number of the channel.  Same as the slot number   */
/*                 for the SMU.                                              */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_CH_1      1     Channel 1                         */
/*                 agb1500_CH_2      2     Channel 2                         */
/*                 agb1500_CH_3      3     Channel 3                         */
/*                 agb1500_CH_4      4     Channel 4                         */
/*                 agb1500_CH_5      5     Channel 5                         */
/*                 agb1500_CH_6      6     Channel 6                         */
/*                 agb1500_CH_7      7     Channel 7                         */
/*                 agb1500_CH_8      8     Channel 8                         */
/*                 agb1500_CH_9      9     Channel 9                         */
/*                 agb1500_CH_10    10     Channel 10                        */
/*                                                                           */
/*         mode    Select 1 for current output mode.                         */
/*                 Select 2 for voltage output mode.                         */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name            Value   Description                       */
/*                 agb1500_IF_MODE   1    CURRENT PULSE                      */
/*                 agb1500_VF_MODE   2    VOLTAGE PULSE                      */
/*                                                                           */
/*        range    Output ranging type.                                      */
/*                 For current output: 0, 1E-12 to 1.0                       */
/*                 For voltage output: 0, 0.5 to 200.0                       */
/*                 where,                                                    */
/*                 For auto ranging: Enter 0 (zero).                         */
/*                 For limited auto ranging: Enter positive value.           */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*				   Name					   Value   Description               */
/*                 agb1500_SMUV_MAX        200.0                             */
/*                                                                           */
/*         base    Base value (in A or V).                                   */
/*                 For current output: -1.0A to 1.0A.                        */
/*                 For voltage output: -200.0V to 200.0V                     */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*				   Name					   Value   Description               */
/*                 agb1500_SMUV_MIN        -200.0                            */
/*                 agb1500_SMUV_MAX        200.0                             */
/*                                                                           */
/*         bias    Bias value (in A or V).                                   */
/*                 For current output: -1.0A to 1.0A.                        */
/*                 For voltage output: -200.0V to 200.0V                     */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*				   Name					   Value   Description               */
/*                 agb1500_SMUV_MIN        -200.0                            */
/*                 agb1500_SMUV_MAX        200.0                             */
/*                                                                           */
/*         comp   Compliance (in V or A).                                    */
/*                If the comp value is out of the following range,           */
/*                the comp and p_comp parameters are ignored.                */
/*                Voltage compliance: -200.0V to 200.0V                      */
/*                Current compliance: -1.0A to 1.0A                          */
/*                Data Type:  ViReal64                                       */
/*                Input/Output:  IN                                          */
/*                Values:                                                    */
/*                Name               Value                                   */
/*                agb1500_SMUV_MIN    -200.0                                 */
/*                agb1500_SMUV_MAX    200.0                                  */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{
    ViStatus errStatus = 0 ;
	struct	agb1500_globals	*thisPtr;
	char	command[256] ;
   
	errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
	if (errStatus < VI_SUCCESS) {
		return( errStatus ) ;
	}

	agb1500_DEBUG_CHK_THIS( vi, thisPtr );
	agb1500_CDE_INIT( "agb1500_addSampleSyncIv" );


	/* Check Channel & Set Compliance */
	if( (channel < agb1500_CH_1) || (agb1500_CH_10 < channel) ) {
		comp = COMP_IGNORE_VAL ;
	}

	/* Check Prameter Range */
    agb1500_CHK_LONG_RANGE(channel, agb1500_CH_1, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);

	agb1500_CHK_LONG_RANGE( mode, agb1500_IF_MODE, agb1500_VF_MODE, 
                           VI_ERROR_PARAMETER3 );

	if( fabs(range) > agb1500_AUTOR_BORDER ) 
		agb1500_CHK_REAL_RANGE( range, 0.0, agb1500_RANGE_MAX, 
							VI_ERROR_PARAMETER4);
	
	agb1500_CHK_REAL_RANGE( base, agb1500_SMUV_MIN, agb1500_SMUV_MAX, 
                           VI_ERROR_PARAMETER5);

	agb1500_CHK_REAL_RANGE( bias, agb1500_SMUV_MIN, agb1500_SMUV_MAX, 
                           VI_ERROR_PARAMETER6);


	/*--- Set Command ---*/
	if( mode == agb1500_VF_MODE ) {		/*--- VOLTAGE PULSE ---*/
		if( !(agb1500_SMUV_MIN <= comp  &&  comp <= agb1500_SMUV_MAX) ) 
			sprintf( command, "MV %d,%d,%E,%E", 
				channel, abs(vRangeId(channel, thisPtr->UNT[channel-1], range)), base, bias ) ;
		
		else
			sprintf( command, "MV %d,%d,%E,%E,%E", 
				channel, abs(vRangeId(channel, thisPtr->UNT[channel-1], range)), base, bias, comp ) ;
	}
	else {					/*--- CURRENT PULSE ---*/
		if( !(agb1500_SMUV_MIN <= comp  &&  comp <= agb1500_SMUV_MAX) ) 
			sprintf( command, "MI %d,%d,%E,%E", 
				channel, abs(iRangeId(channel, thisPtr->UNT[channel-1], range)), base, bias ) ;
		
		else
			sprintf( command, "MI %d,%d,%E,%E,%E", 
				channel, abs(iRangeId(channel, thisPtr->UNT[channel-1], range)), base, bias, comp ) ;
	}


    errStatus = viPrintf(vi,"%s\n", command ) ;
    if (errStatus < VI_SUCCESS) {
       agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }
	
    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
}/* ----- end of function ----- */

/*---------------------------------------------------------------------------*/
 ViStatus _VI_FUNC agb1500_clearSampleSync(ViSession vi) 
/*---------------------------------------------------------------------------*/
/*                                                                           */
/*      This function clears the setting of the constant voltage/current     */   
/*      source defined by the agb1500_addSampleSyncIv function.              */                                                                  
/*                                                                           */
/*   Parameter     Description                                               */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{
    ViStatus errStatus = 0 ;
	struct	agb1500_globals	*thisPtr;
   
	errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
	if (errStatus < VI_SUCCESS) {
		return( errStatus ) ;
	}

	agb1500_DEBUG_CHK_THIS( vi, thisPtr );
	agb1500_CDE_INIT( "agb1500_cleanSampleSync" );

	/*--- Set Command ---*/
	

    errStatus = viPrintf(vi,"MCC\n" ) ;
    if (errStatus < VI_SUCCESS) {
       agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }


    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
}/* ----- end of function ----- */

/*---------------------------------------------------------------------------*/
ViStatus _VI_FUNC agb1500_sampleIv(ViSession vi, 
                               ViInt32 channel[], ViInt32 mode[], 
                               ViReal64 range[], 
                               ViPInt32 point, ViInt32 index[],
                               ViReal64 value[], ViInt32 status[], ViReal64 time[])
/*---------------------------------------------------------------------------*/
/*                                                                           */
/*      This function executes a sampling measurement by the specified       */
/*      channels, and returns the number of measurement points, measurement  */ 
/*      data and measurement status.                                         */
/*      Before executing this function, set the sampling timing by the       */
/*      agb1500_setSample function. The synchronous DC sources used with     */
/*      the sampling measurement units are defined by using the              */
/*      agb1500_addSampleSyncIv function.                                    */                        
/*                                                                           */
/*      The parameter 'channel[]' specifies the measurement channels.        */
/*      The parameter 'mode[]' specifies the measurement mode,               */
/*      voltage or current.                                                  */
/*      The parameter 'range[]' specifies the measurement ranging type.      */
/*      The parameter 'point' specifies the number of measurement points.    */
/*      The parameter 'index[]' returns the measurement data index.          */
/*      The parameter 'value[]' returns the measurement data.                */
/*      Two dimensional array.                                               */
/*      The parameter 'status[]' returns the measurement status.             */
/*      Two dimensional array.                                               */
/*      The parameter 'time[]' returns the measurement timestamp data.       */
/*      Two dimensional array.                                               */
/*                                                                           */
/*      The array size of channel, mode and range must be the same together. */
/*      And the array size of value and status must be the same together.    */
/*      Then the parameter should be declared as follows.                    */
/*                                                                           */
/*      ViInt32		channel[N+1]                                             */
/*      ViInt32		mode[N]                                                  */
/*      ViReal64	range[N]                                                 */
/*      ViInt32		point                                                    */
/*      ViInt32		index[M]                                                 */
/*      ViReal64	value[M][N]                                              */
/*      ViReal64	status[M][N]                                             */
/*      ViReal64    time[M][N]                                               */
/*		Where,                                                               */
/*      N: Number of channels used for the measurement                       */
/*      M: Number of sampling points ( 'point' parameter )                   */
/*                                                                           */                         
/*   Parameter     Description                                               */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*      channel    Data Type:  ViInt32 channel[]                             */
/*                 Input/Output: IN                                          */
/*				   Channel number of the units for the measurements.         */
/*                 At the end of the unit definition for the channel[]       */
/*                 array, do not forget to enter 0 (zero) into the           */
/*                 meaningful last array element.  For example, if you       */
/*                 use 4 measurement units, array size should be 5 or        */
/*                 more, and 0 (zero) must be entered into the fifth         */
/*                 array element of channel.                                 */
/*                                                                           */
/*         mode    Data Type:  ViInt32 mode[]                                */
/*                 Input/Output: IN                                          */
/*				   Measurement mode.                                         */
/*                 Select 1 for current measurement.                         */
/*                 Select 2 for voltage measurement.                         */
/*                                                                           */
/*         range   Measurement ranging type.                                 */
/*                 For current output: 0, 1E-12 to 1.0                       */
/*                 For voltage output: 0, 0.5 to 200.0                       */
/*                 where,                                                    */
/*                 For auto ranging: Enter 0 (zero).                         */
/*                 For limited auto ranging: Enter positive value.           */
/*                 Data Type:  ViReal64                                      */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*         point   Number of measurement points.                             */
/*                 Data Type:  ViPInt32                                      */
/*                 Input/Output:  OUT                                        */
/*                                                                           */
/*         index   Data Type:  ViPint32 index[]                              */
/*                 Input/Output:  OUT                                        */
/*                 Measurement data index.                                   */
/*                                                                           */
/*          value  Data Type:  ViReal64 value[]                              */
/*                 Input/Output:  OUT                                        */
/*                 Measurement data.                                         */
/*                                                                           */
/*         status  Data Type:  ViInt32 status[]                              */
/*                 Input/Output:  OUT                                        */
/*                 Measurement execution status.                             */
/*                 If you want to disable this status output, enter 0        */
/*                 (NULL pointer).                                           */
/*                                                                           */
/*         time    Data Type:  ViReal64 time[]                               */
/*                 Input/Output:  OUT                                        */
/*                 Measurement timestamp data.                               */
/*                 If you want to disable this status output, enter 0        */
/*                 (NULL pointer).                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{

    ViStatus errStatus = 0 ;
	struct	agb1500_globals	*thisPtr;
	int			cnt ;
	int            chCnt ;
	ViInt32		getStatus ;
	ViInt32		eod ;
	ViReal64	getValue ;
	ViInt32		chanNum ;
	ViChar		chChar[8] ;
	ViChar		chString[256] ;		
	ViInt32		dataKind;
	

    *point = 0;
   
	errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
	if (errStatus < VI_SUCCESS) {
		return( errStatus ) ;
	}

	agb1500_DEBUG_CHK_THIS( vi, thisPtr );
	agb1500_CDE_INIT( "agb1500_sampleIv" );


	/* Check Prameter Range */
	for( cnt=0; channel[cnt] != 0; cnt++ ) {

		agb1500_CHK_LONG_RANGE( channel[cnt], agb1500_CH_1, agb1500_CH_10, 
                           VI_ERROR_PARAMETER2);

		agb1500_CHK_LONG_RANGE( mode[cnt], agb1500_IM_MODE, agb1500_VM_MODE, 
	                        VI_ERROR_PARAMETER3);

		if( fabs(range[cnt]) > agb1500_AUTOR_BORDER ) {
			agb1500_CHK_REAL_RANGE( range[cnt], agb1500_RANGE_MIN, agb1500_RANGE_MAX,
									VI_ERROR_PARAMETER4);
		}
	}

	/*--- Channel Non Set ---*/
	if( cnt == 0 )  agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2 ) ;

	/*--- Get Chunnel Number ---*/
	chanNum = cnt ;

	/*--- Set Command ---*/

	errStatus = viPrintf(vi,"FMT 21,1\n" ) ;
	if (errStatus < VI_SUCCESS) {
		agb1500_LOG_STATUS( vi, thisPtr, errStatus );
	}

	if ( time != (ViReal64 *)NULL) {

        errStatus = viPrintf(vi,"TSC 1\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }
    else {

        errStatus = viPrintf(vi,"TSC 0\n" );
        if ( errStatus < VI_SUCCESS) {
            agb1500_LOG_STATUS( vi, thisPtr, errStatus );
        }
    }


	/*--- Edit Channel Number ---*/
	memset( chString, (char)NULL, sizeof(chString) ) ;
	for( cnt=0; cnt<chanNum; cnt++){
		if( cnt != 0 )	sprintf( chChar, ",%d", channel[cnt] ) ;
		else			sprintf( chChar, "%d", channel[cnt] ) ;
		strcat( chString, chChar ) ;
	}

	errStatus = viPrintf(vi,"MM 10,%s\n", chString ) ;
	if (errStatus < VI_SUCCESS) {
		agb1500_LOG_STATUS( vi, thisPtr, errStatus );
	}

	for( cnt=0; cnt<chanNum; cnt++ ) {
			
		errStatus = viPrintf(vi,"CMM %d,%d\n", channel[cnt], mode[cnt] ) ;
		if (errStatus < VI_SUCCESS) {
			agb1500_LOG_STATUS( vi, thisPtr, errStatus );
		}

		if( mode[cnt] == agb1500_VM_MODE ) {

			errStatus = viPrintf(vi,"RV %d,%d\n",
				channel[cnt], vRangeId(channel[cnt],thisPtr->UNT[channel[cnt]-1],range[cnt])) ;
			if (errStatus < VI_SUCCESS) {
				agb1500_LOG_STATUS( vi, thisPtr, errStatus );
			}
		}
		else {

			errStatus = viPrintf(vi,"RI %d,%d\n",
				channel[cnt], iRangeId(channel[cnt],thisPtr->UNT[channel[cnt]-1],range[cnt]) ) ;
			if (errStatus < VI_SUCCESS) {
				agb1500_LOG_STATUS( vi, thisPtr, errStatus );
			}
		}
	}

	agb1500_CHK_INST_ERR( vi, thisPtr ) ;


	errStatus = viPrintf(vi,"XE\n" ) ;
	if (errStatus < VI_SUCCESS) {
		agb1500_LOG_STATUS( vi, thisPtr, errStatus );
	}

	agb1500_CHK_INST_ERR_AFTER_XE( vi, thisPtr ) ;

	eod = 0;
	cnt = 0;
	do{
			
		/* Read Index Data */ 
		if(	eod == 0 ){
			errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
                
			if ( errStatus < VI_SUCCESS ) {
				agb1500_LOG_STATUS( vi, thisPtr, errStatus );
			}

			if ( dataKind == agb1500_DT_X ) {         
				index[cnt] = (ViInt32)getValue;
			}
			else {
				return (agb1500_MEAS_DATA_INCONSISTENCY);
			}   
		}
		else {
			index[cnt] = agb1500_DUMMY_INDEX;
		}

		for( chCnt = 0 ; chCnt <chanNum ; chCnt++ ){

			/*--- Read Time stamp Data ---*/       
            if ( time != (ViReal64 *)NULL) {
                if ( eod == 0) {
                    errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
                    if ( errStatus < VI_SUCCESS) {
                        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
                    }
                    if ( dataKind == agb1500_DT_TM) {         
                        time[cnt*chanNum + chCnt] = getValue;
                    }
                    else {
                        return (agb1500_MEAS_DATA_INCONSISTENCY);
                    }
                }
                else {
                    time[cnt*chanNum +chCnt] = agb1500_DUMMY_TIMESTAMP;
                }
            }
			
			/* Read Measurement Data */
			if(	eod == 0 ){
				errStatus = asciiDataRead( vi, &dataKind, &getValue, &getStatus, NULL, &eod ); 
                
				if ( errStatus < VI_SUCCESS ) {
					agb1500_LOG_STATUS( vi, thisPtr, errStatus );
				}
	
				if ( dataKind == agb1500_DT_IM || dataKind == agb1500_DT_VM ){
					value[cnt*chanNum + chCnt] = getValue;
					if ( status != (ViInt32 *)NULL ) {
						status[cnt*chanNum + chCnt] = getStatus ;
					}
				}else{
					return (agb1500_MEAS_DATA_INCONSISTENCY);
				}                
			}
			else {
				value[cnt*chanNum + chCnt] = agb1500_DUMMY_VALUE;
				 /*--- Set Status ---*/
				if ( status != (ViInt32 *)NULL ) {
					status[cnt*chanNum + chCnt] = agb1500_DUMMY_STATUS ;
				}
			}
		}
		cnt++;
	} while(eod == 0);

	/*--- Set Point ---*/
	*point = cnt;

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );
}/* ----- end of function ----- */
/*****************************************************************************/
ViStatus _VI_FUNC agb1500_setSampleMode(ViSession vi, ViInt32 mode )
/*****************************************************************************/
/*                                                                           */
/*      This function sets the sampling mode(linear or log sampling).        */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*           vi    Instrument Handle returned from agb1500_init( ).          */
/*                 Data Type:  ViSession                                     */
/*                 Input/Output:  IN                                         */
/*                                                                           */
/*        mode     Select the sampling mode.                                 */
/*                 Data Type:  ViInt32                                       */
/*                 Input/Output:  IN                                         */
/*                 Values:                                                   */
/*                 Name                Value    Description                  */
/*                 agb1500_SMP_LINEAR      0    Linear Sampling              */
/*                 agb1500_SMP_LOG10       1    Log10 Sampling               */
/*                 agb1500_SMP_LOG25       2    Log25 Sampling               */
/*                 agb1500_SMP_LOG50       3    Log50 Sampling               */
/*                 agb1500_SMP_LOG100      4    Log100 Sampling              */
/*                 agb1500_SMP_LOG250      5    Log250 Sampling              */
/*                 agb1500_SMP_LOG500      6    Log500 Sampling              */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, 0, errStatus );        
    }
    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_setSampleMode" );

    /* Check Prameter Range */

    agb1500_CHK_LONG_RANGE( mode, 
                agb1500_SMP_LINEAR, agb1500_SMP_LOG500, 
                VI_ERROR_PARAMETER2);

    errStatus = viPrintf(vi,"ML %d\n", mode + 1 );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );

}/* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_setCmuAdjustMode(ViSession vi, ViInt32 channel, ViInt32 mode)
/*****************************************************************************/
/*                                                                           */
/*      This function sets the CMU Adjust mode.                              */
/*                                                                           */
/*      The parameter 'channel' specifies the channel number of the CMU.     */
/*      The parameter 'mode' specifies the CMU adjust mode.                  */
/*                                                                           */
/*      This function implements the following commands:                     */
/*      ADJ                                                                  */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*        channel   Channel number of the CMU.                               */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name              Value   Description                    */
/*                  agb1500_CH_CMU     -1     CMU channel                    */ 
/*                  agb1500_CH_1        1     Channel 1                      */
/*                  agb1500_CH_2        2     Channel 2                      */
/*                  agb1500_CH_3        3     Channel 3                      */
/*                  agb1500_CH_4        4     Channel 4                      */
/*                  agb1500_CH_5        5     Channel 5                      */
/*                  agb1500_CH_6        6     Channel 6                      */
/*                  agb1500_CH_7        7     Channel 7                      */
/*                  agb1500_CH_8        8     Channel 8                      */
/*                  agb1500_CH_9        9     Channel 9                      */
/*                  agb1500_CH_10      10     Channel 10                     */ 
/*                                                                           */
/*         mode     Select 1 for Manual Mode.                                */
/*                  Select 0 for Auto Mode.                                  */
/*                  Data Type: ViInt32                                       */
/*                  Input/Output: IN                                         */
/*                  Values:                                                  */
/*                  Name					Value   Description              */
/*                  agb1500_CMUADJ_MANUAL   1		Manual Mode              */
/*                  agb1500_CMUADJ_AUTO     0       Auto Mode                */   
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, 0, errStatus );        
    }
    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_setCmuAdjustMode" );

    /* Check Prameter Range */
    if( !((channel == agb1500_CH_CMU) || ((channel >= agb1500_CH_1) && (channel <= agb1500_CH_10)))){
		agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2);
	}
	if( channel == agb1500_CH_CMU ){
		if( (channel = agb1500_RTN_CMU_UNT) == agb1500_NO_CMU ){
			return agb1500_NO_CMU_UNT;
		}
	}

	agb1500_CHK_LONG_RANGE( mode,
				agb1500_CMUADJ_AUTO, agb1500_CMUADJ_MANUAL,
				VI_ERROR_PARAMETER3);

	/* Set Null-Gain Phase Adjust Mode */
	errStatus = viPrintf(vi,"ADJ %d,%d\n",channel,mode);
	if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );

}/* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_execCmuAdjust(ViSession vi, ViInt32 channel, ViPInt16 result)
/*****************************************************************************/
/*                                                                           */
/*      This function execute the CMU Null-Gain Phase Adjust.                */
/*                                                                           */
/*      The parameter 'channel' specifies the channel number of the CMU.     */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*        channel   Channel number of the CMU.                               */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name              Value   Description                    */
/*                  agb1500_CH_CMU     -1     CMU channel                    */
/*                  agb1500_CH_1        1     Channel 1                      */
/*                  agb1500_CH_2        2     Channel 2                      */
/*                  agb1500_CH_3        3     Channel 3                      */
/*                  agb1500_CH_4        4     Channel 4                      */
/*                  agb1500_CH_5        5     Channel 5                      */
/*                  agb1500_CH_6        6     Channel 6                      */
/*                  agb1500_CH_7        7     Channel 7                      */
/*                  agb1500_CH_8        8     Channel 8                      */
/*                  agb1500_CH_9        9     Channel 9                      */
/*                  agb1500_CH_10      10     Channel 10                     */ 
/*                                                                           */
/*         result   Numeric result from Null-Gain Phase adjust operation.    */
/*                  0 = Passed.                                              */
/*                  1 = Fail.                                                */
/*                  2 = Abort.                                               */
/*                  Data Type: ViPInt16                                      */
/*                  Input/Output: IN                                         */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
	ViInt32   q_time_out;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, 0, errStatus );        
    }
    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_execCmuAdjust" );

    /* Check Prameter Range */
    if( !((channel == agb1500_CH_CMU) || ((channel >= agb1500_CH_1) && (channel <= agb1500_CH_10)))){
		agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2);
	}
	if( channel == agb1500_CH_CMU ){
		if( (channel = agb1500_RTN_CMU_UNT) == agb1500_NO_CMU ){
			return agb1500_NO_CMU_UNT;
		}
	}

	/* query timeout */
	errStatus = viGetAttribute(vi, VI_ATTR_TMO_VALUE, &q_time_out);
    if (VI_SUCCESS > errStatus)
        return statusUpdate(vi, thisPtr, errStatus);

   /* set time out -> 300 sec */
    if ((errStatus = viSetAttribute(vi, VI_ATTR_TMO_VALUE, 300000)) /* 300 sec */ 
           < VI_SUCCESS)
        return statusUpdate(vi, thisPtr, errStatus);

	/* Execute Null-Gain Phase Adjust */
	errStatus = viPrintf(vi,"ADJ? %d\n",channel);
	if( errStatus < VI_SUCCESS ){
		viSetAttribute(vi, VI_ATTR_TMO_VALUE, q_time_out);
		return statusUpdate(vi, thisPtr, errStatus);
	}

	if ((errStatus = delayScanf(vi, thisPtr->myDelay,
                                            "%hd%*t", result)) < VI_SUCCESS) {
        *result = 1;
		viSetAttribute(vi, VI_ATTR_TMO_VALUE, q_time_out);
        return statusUpdate(vi, thisPtr, errStatus);
	}


	/* set former time_out */
    if ((errStatus = viSetAttribute(vi, VI_ATTR_TMO_VALUE, q_time_out )) 
           < VI_SUCCESS)
        return statusUpdate(vi, thisPtr, errStatus);

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );

}/* ----- end of function ----- */
/*****************************************************************************/
ViStatus _VI_FUNC agb1500_setOpenCorrMode(ViSession vi, ViInt32 channel, ViInt32 mode)
/*****************************************************************************/
/*                                                                           */
/*      This function sets the CMU Open correction mode.                     */
/*                                                                           */
/*      The parameter 'channel' specifies the channel number of the CMU.     */
/*      The parameter 'mode' specifies the CMU Open correction mode.         */
/*                                                                           */
/*      This function implements the following commands:                     */
/*      CORRST                                                               */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*        channel   Channel number of the CMU.                               */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name              Value   Description                    */
/*                  agb1500_CH_CMU     -1     CMU channel                    */
/*                  agb1500_CH_1        1     Channel 1                      */
/*                  agb1500_CH_2        2     Channel 2                      */
/*                  agb1500_CH_3        3     Channel 3                      */
/*                  agb1500_CH_4        4     Channel 4                      */
/*                  agb1500_CH_5        5     Channel 5                      */
/*                  agb1500_CH_6        6     Channel 6                      */
/*                  agb1500_CH_7        7     Channel 7                      */
/*                  agb1500_CH_8        8     Channel 8                      */
/*                  agb1500_CH_9        9     Channel 9                      */
/*                  agb1500_CH_10       10    Channel 10                     */ 
/*                                                                           */
/*         mode     Select 1 for Open correction function ON.                */
/*                  Select 0 for Open correction function OFF.               */
/*                  Data Type: ViInt32                                       */
/*                  Input/Output: IN                                         */
/*                  Values:                                                  */
/*                  Name				Value   Description                  */
/*                  agb1500_FLAG_ON     1		Open Correction ON           */
/*                  agb1500_FLAG_OFF    0       Open Correction OFF          */   
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, 0, errStatus );        
    }
    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_setOpenCorrMode" );

    /* Check Prameter Range */
    if( !((channel == agb1500_CH_CMU) || ((channel >= agb1500_CH_1) && (channel <= agb1500_CH_10)))){
		agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2);
	}
	if( channel == agb1500_CH_CMU ){
		if( (channel = agb1500_RTN_CMU_UNT) == agb1500_NO_CMU ){
			return agb1500_NO_CMU_UNT;
		}
	}

	agb1500_CHK_LONG_RANGE( mode,
				agb1500_FLAG_OFF, agb1500_FLAG_ON,
				VI_ERROR_PARAMETER3);

	/* Set CMU OPEN Correction Mode */
	errStatus = viPrintf(vi,"CORRST %d,1,%d\n",channel,mode);
	if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );

}/* ----- end of function ----- */
/*****************************************************************************/
ViStatus _VI_FUNC agb1500_execOpenCorr(ViSession vi, ViInt32 channel, ViReal64 freq,
									   ViInt32 mode, ViReal64 primary, ViReal64 secondary,
									   ViPInt16 result)
/*****************************************************************************/
/*                                                                           */
/*      This function executes the CMU Open correction of the specified      */
/*      frequency.                                                           */
/*                                                                           */
/*      The parameter 'channel' specifies the channel number of the CMU.     */
/*      The parameter 'freq' specifies the frequency to adjust CMU.          */
/*      The parameter 'mode' specifies the measurement mode of the CMU.      */
/*      The parameter 'primary' specifies the primary parameter for Open     */
/*      standard.                                                            */
/*      The parameter 'secondary' specifies the secondary parameter for      */
/*      Open standard.                                                       */
/*      The prameter 'result' returns the numeric result from                */
/*      open correction operation.                                           */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*        channel   Channel number of the CMU.                               */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name              Value   Description                    */
/*                  agb1500_CMU_CH     -1     CMU channel                    */
/*                  agb1500_CH_1        1     Channel 1                      */
/*                  agb1500_CH_2        2     Channel 2                      */
/*                  agb1500_CH_3        3     Channel 3                      */
/*                  agb1500_CH_4        4     Channel 4                      */
/*                  agb1500_CH_5        5     Channel 5                      */
/*                  agb1500_CH_6        6     Channel 6                      */
/*                  agb1500_CH_7        7     Channel 7                      */
/*                  agb1500_CH_8        8     Channel 8                      */
/*                  agb1500_CH_9        9     Channel 9                      */
/*                  agb1500_CH_10       10    Channel 10                     */ 
/*                                                                           */
/*           freq   Measurement frequency of CMU.                            */
/*                  Data Type:  ViReal64                                     */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name                Value    Description                 */
/*                  agb1500_CMUF_MIN    1000.0                               */
/*                  agb1500_CMUF_MAX    5000000.0                            */
/*                                                                           */
/*         mode     CMU Impedance measurement mode.                          */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name					Value   Description              */
/*                  agb1500_CMUM_R_X		1       R-X Mode	    		 */
/*                  agb1500_CMUM_G_B		2       G-B Mode                 */
/*                  agb1500_CMUM_Z_TRAD		10      Z-Theta(radian) Mode     */
/*                  agb1500_CMUM_Z_TDEG		11      Z-Theta(degree) Mode     */
/*                  agb1500_CMUM_Y_TRAD		20      Y-Theta(radian) Mode     */
/*                  agb1500_CMUM_Y_TDEG		21      Y-Theta(degree) Mode     */
/*                  agb1500_CMUM_CP_G		100     Cp-G Mode                */
/*                  agb1500_CMUM_CP_D		101     Cp-D Mode                */
/*                  agb1500_CMUM_CP_Q		102     Cp-Q Mode                */
/*                  agb1500_CMUM_CP_RP		103     Cp-Rp Mode               */
/*                  agb1500_CMUM_CS_RS		200     Cs-Rs Mode               */
/*                  agb1500_CMUM_CS_D		201     Cs-D Mode                */
/*                  agb1500_CMUM_CS_Q		202		Cs-Q Mode                */
/*                  agb1500_CMUM_LP_G		300     Lp-G Mode                */
/*                  agb1500_CMUM_LP_D		301     Lp-D Mode                */
/*                  agb1500_CMUM_LP_Q		302     Lp-Q Mode                */
/*                  agb1500_CMUM_LP_RP		303     Lp-Rp Mode               */
/*                  agb1500_CMUM_LS_RS		400     Ls-Rs Mode               */
/*                  agb1500_CMUM_LS_D		401     Ls-D Mode                */
/*                  agb1500_CMUM_LS_Q		402     Ls-Q Mode                */     
/*                                                                           */
/*        primary   Primary parameter of Open standard.                      */
/*                  Data Type:  ViReal64                                     */
/*                  Input/Output:  IN                                        */
/*                                                                           */
/*      secondary   Secondary parameter of Open standard.                    */
/*                  Data Type:  ViReal64                                     */
/*                  Input/Output:  IN                                        */
/*                                                                           */
/*         result   Numeric result from CMU Open correction operation.       */
/*                  0 = Passed.                                              */
/*                  1 = Fail.                                                */
/*                  2 = Abort.                                               */
/*                  Data Type: ViPInt16                                      */
/*                  Input/Output: IN                                         */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
	ViInt32   q_time_out;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, 0, errStatus );        
    }
    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_execOpenCorr" );

    /* Check Prameter Range */
    if( !((channel == agb1500_CH_CMU) || ((channel >= agb1500_CH_1) && (channel <= agb1500_CH_10)))){
		agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2);
	}
	if( channel == agb1500_CH_CMU ){
		if( (channel = agb1500_RTN_CMU_UNT) == agb1500_NO_CMU ){
			return agb1500_NO_CMU_UNT;
		}
	}
	
	agb1500_CHK_REAL_RANGE( freq, 
                agb1500_CMUF_MIN, agb1500_CMUF_MAX, 
                VI_ERROR_PARAMETER3);

	agb1500_CHK_IMP_MEAS_MODE( mode, VI_ERROR_PARAMETER4);

	/* query timeout */
	errStatus = viGetAttribute(vi, VI_ATTR_TMO_VALUE, &q_time_out);
    if (VI_SUCCESS > errStatus)
        return statusUpdate(vi, thisPtr, errStatus);

   /* set time out -> 300 sec */
    if ((errStatus = viSetAttribute(vi, VI_ATTR_TMO_VALUE, 300000)) /* 300 sec */ 
           < VI_SUCCESS)
        return statusUpdate(vi, thisPtr, errStatus);

	/* Define CMU Open standard reference */
	errStatus = viPrintf(vi,"DCORR %d,1,%d,%e,%e\n", channel, mode, primary,secondary );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

	/* Set Frequency */
	errStatus = viPrintf(vi,"CORRL %d,%e\n", channel, freq );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

	/* Execute  */
	errStatus = viPrintf(vi,"CORR? %d,1\n",channel);
	if( errStatus < VI_SUCCESS ){
		viSetAttribute(vi, VI_ATTR_TMO_VALUE, q_time_out);
		return statusUpdate(vi, thisPtr, errStatus);
	}

	if ((errStatus = delayScanf(vi, thisPtr->myDelay,
                                            "%hd%*t", result)) < VI_SUCCESS) {
        *result = 1;
		viSetAttribute(vi, VI_ATTR_TMO_VALUE, q_time_out);
        return statusUpdate(vi, thisPtr, errStatus);
	}


	/* set former time_out */
    if ((errStatus = viSetAttribute(vi, VI_ATTR_TMO_VALUE, q_time_out )) 
           < VI_SUCCESS)
        return statusUpdate(vi, thisPtr, errStatus);

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );

}/* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_setShortCorrMode(ViSession vi, ViInt32 channel, ViInt32 mode)
/*****************************************************************************/
/*                                                                           */
/*      This function sets the CMU Short correction mode.                    */
/*                                                                           */
/*      The parameter 'channel' specifies the channel number of the CMU.     */
/*      The parameter 'mode' specifies the CMU Short correction mode.        */
/*                                                                           */
/*      This function implements the following commands:                     */
/*      CORRST                                                               */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*        channel   Channel number of the CMU.                               */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name              Value   Description                    */
/*                  agb1500_CH_CMU     -1     CMU channel                    */
/*                  agb1500_CH_1        1     Channel 1                      */
/*                  agb1500_CH_2        2     Channel 2                      */
/*                  agb1500_CH_3        3     Channel 3                      */
/*                  agb1500_CH_4        4     Channel 4                      */
/*                  agb1500_CH_5        5     Channel 5                      */
/*                  agb1500_CH_6        6     Channel 6                      */
/*                  agb1500_CH_7        7     Channel 7                      */
/*                  agb1500_CH_8        8     Channel 8                      */
/*                  agb1500_CH_9        9     Channel 9                      */
/*                  agb1500_CH_10      10     Channel 10                     */ 
/*                                                                           */
/*         mode     Select 1 for Short correction function ON.               */
/*                  Select 0 for Short correction function OFF.              */
/*                  Data Type: ViInt32                                       */
/*                  Input/Output: IN                                         */
/*                  Values:                                                  */
/*                  Name				Value   Description                  */
/*                  agb1500_FLAG_ON     1		Short Correction ON          */
/*                  agb1500_FLAG_OFF    0       Short Correction OFF         */   
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, 0, errStatus );        
    }
    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_setShortCorrMode" );

    /* Check Prameter Range */
    if( !((channel == agb1500_CH_CMU) || ((channel >= agb1500_CH_1) && (channel <= agb1500_CH_10)))){
		agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2);
	}
	if( channel == agb1500_CH_CMU ){
		if( (channel = agb1500_RTN_CMU_UNT) == agb1500_NO_CMU ){
			return agb1500_NO_CMU_UNT;
		}
	}

	agb1500_CHK_LONG_RANGE( mode,
				agb1500_FLAG_OFF, agb1500_FLAG_ON,
				VI_ERROR_PARAMETER3);

	/* Set CMU Short Correction Mode */
	errStatus = viPrintf(vi,"CORRST %d,2,%d\n",channel,mode);
	if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );

}/* ----- end of function ----- */
/*****************************************************************************/
ViStatus _VI_FUNC agb1500_execShortCorr(ViSession vi, ViInt32 channel, ViReal64 freq,
									   ViInt32 mode, ViReal64 primary, ViReal64 secondary,
									   ViPInt16 result)
/*****************************************************************************/
/*                                                                           */
/*      This function executes the CMU Short correction of the specified     */
/*      frequency.                                                           */
/*                                                                           */
/*      The parameter 'channel' specifies the channel number of the CMU.     */
/*      The parameter 'freq' specifies the frequency to adjust CMU.          */
/*      The parameter 'mode' specifies the measurement mode of the CMU.      */
/*      The parameter 'primary' specifies the primary parameter for Short    */
/*      standard.                                                            */
/*      The parameter 'secondary' specifies the secondary parameter for      */
/*      Short standard.                                                      */
/*      The prameter 'result' returns the numeric result from                */
/*      short correction operation.                                          */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*        channel   Channel number of the CMU.                               */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name              Value   Description                    */
/*                  agb1500_CH_CMU     -1     CMU channel                    */
/*                  agb1500_CH_1        1     Channel 1                      */
/*                  agb1500_CH_2        2     Channel 2                      */
/*                  agb1500_CH_3        3     Channel 3                      */
/*                  agb1500_CH_4        4     Channel 4                      */
/*                  agb1500_CH_5        5     Channel 5                      */
/*                  agb1500_CH_6        6     Channel 6                      */
/*                  agb1500_CH_7        7     Channel 7                      */
/*                  agb1500_CH_8        8     Channel 8                      */
/*                  agb1500_CH_9        9     Channel 9                      */
/*                  agb1500_CH_10      10     Channel 10                     */ 
/*                                                                           */
/*           freq   Measurement frequency of CMU.                            */
/*                  Data Type:  ViReal64                                     */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name                Value    Description                 */
/*                  agb1500_CMUF_MIN    1000.0                               */
/*                  agb1500_CMUF_MAX    5000000.0                            */
/*                                                                           */
/*         mode     CMU Impedance measurement mode.                          */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name					Value   Description              */
/*                  agb1500_CMUM_R_X		1       R-X Mode	    		 */
/*                  agb1500_CMUM_G_B		2       G-B Mode                 */
/*                  agb1500_CMUM_Z_TRAD		10      Z-Theta(radian) Mode     */
/*                  agb1500_CMUM_Z_TDEG		11      Z-Theta(degree) Mode     */
/*                  agb1500_CMUM_Y_TRAD		20      Y-Theta(radian) Mode     */
/*                  agb1500_CMUM_Y_TDEG		21      Y-Theta(degree) Mode     */
/*                  agb1500_CMUM_CP_G		100     Cp-G Mode                */
/*                  agb1500_CMUM_CP_D		101     Cp-D Mode                */
/*                  agb1500_CMUM_CP_Q		102     Cp-Q Mode                */
/*                  agb1500_CMUM_CP_RP		103     Cp-Rp Mode               */
/*                  agb1500_CMUM_CS_RS		200     Cs-Rs Mode               */
/*                  agb1500_CMUM_CS_D		201     Cs-D Mode                */
/*                  agb1500_CMUM_CS_Q		202		Cs-Q Mode                */
/*                  agb1500_CMUM_LP_G		300     Lp-G Mode                */
/*                  agb1500_CMUM_LP_D		301     Lp-D Mode                */
/*                  agb1500_CMUM_LP_Q		302     Lp-Q Mode                */
/*                  agb1500_CMUM_LP_RP		303     Lp-Rp Mode               */
/*                  agb1500_CMUM_LS_RS		400     Ls-Rs Mode               */
/*                  agb1500_CMUM_LS_D		401     Ls-D Mode                */
/*                  agb1500_CMUM_LS_Q		402     Ls-Q Mode                */     
/*                                                                           */
/*        primary   Primary parameter of Short standard.                     */
/*                  Data Type:  ViReal64                                     */
/*                  Input/Output:  IN                                        */
/*                                                                           */
/*      secondary   Secondary parameter of Short standard.                   */
/*                  Data Type:  ViReal64                                     */
/*                  Input/Output:  IN                                        */
/*                                                                           */
/*         result   Numeric result from CMU Open correction operation.       */
/*                  0 = Passed.                                              */
/*                  1 = Fail.                                                */
/*                  2 = Abort.                                               */
/*                  Data Type: ViPInt16                                      */
/*                  Input/Output: IN                                         */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
	ViInt32   q_time_out;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, 0, errStatus );        
    }
    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_execShortCorr" );

    /* Check Prameter Range */
    if( !((channel == agb1500_CH_CMU) || ((channel >= agb1500_CH_1) && (channel <= agb1500_CH_10)))){
		agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2);
	}
	if( channel == agb1500_CH_CMU ){
		if( (channel = agb1500_RTN_CMU_UNT) == agb1500_NO_CMU ){
			return agb1500_NO_CMU_UNT;
		}
	}
	
	agb1500_CHK_REAL_RANGE( freq, 
                agb1500_CMUF_MIN, agb1500_CMUF_MAX, 
                VI_ERROR_PARAMETER3);

	agb1500_CHK_IMP_MEAS_MODE( mode, VI_ERROR_PARAMETER4);

	/* query timeout */
	errStatus = viGetAttribute(vi, VI_ATTR_TMO_VALUE, &q_time_out);
    if (VI_SUCCESS > errStatus)
        return statusUpdate(vi, thisPtr, errStatus);

   /* set time out -> 300 sec */
    if ((errStatus = viSetAttribute(vi, VI_ATTR_TMO_VALUE, 300000)) /* 300 sec */ 
           < VI_SUCCESS)
        return statusUpdate(vi, thisPtr, errStatus);

	/* Define CMU Open standard reference */
	errStatus = viPrintf(vi,"DCORR %d,2,%d,%e,%e\n", channel, mode, primary,secondary );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

	/* Set Frequency */
	errStatus = viPrintf(vi,"CORRL %d,%e\n", channel, freq );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

	/* Execute  */
	errStatus = viPrintf(vi,"CORR? %d,2\n",channel);
	if( errStatus < VI_SUCCESS ){
		viSetAttribute(vi, VI_ATTR_TMO_VALUE, q_time_out);
		return statusUpdate(vi, thisPtr, errStatus);
	}

	if ((errStatus = delayScanf(vi, thisPtr->myDelay,
                                            "%hd%*t", result)) < VI_SUCCESS) {
        *result = 1;
		viSetAttribute(vi, VI_ATTR_TMO_VALUE, q_time_out);
        return statusUpdate(vi, thisPtr, errStatus);
	}


	/* set former time_out */
    if ((errStatus = viSetAttribute(vi, VI_ATTR_TMO_VALUE, q_time_out )) 
           < VI_SUCCESS)
        return statusUpdate(vi, thisPtr, errStatus);

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );

}/* ----- end of function ----- */

/*****************************************************************************/
ViStatus _VI_FUNC agb1500_setLoadCorrMode(ViSession vi, ViInt32 channel, ViInt32 mode)
/*****************************************************************************/
/*                                                                           */
/*      This function sets the CMU Load correction mode.                     */
/*                                                                           */
/*      The parameter 'channel' specifies the channel number of the CMU.     */
/*      The parameter 'mode' specifies the CMU Load correction mode.         */
/*                                                                           */
/*      This function implements the following commands:                     */
/*      CORRST                                                               */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*        channel   Channel number of the CMU.                               */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name              Value   Description                    */
/*                  agb1500_CH_CMU     -1     CMU channel                    */
/*                  agb1500_CH_1        1     Channel 1                      */
/*                  agb1500_CH_2        2     Channel 2                      */
/*                  agb1500_CH_3        3     Channel 3                      */
/*                  agb1500_CH_4        4     Channel 4                      */
/*                  agb1500_CH_5        5     Channel 5                      */
/*                  agb1500_CH_6        6     Channel 6                      */
/*                  agb1500_CH_7        7     Channel 7                      */
/*                  agb1500_CH_8        8     Channel 8                      */
/*                  agb1500_CH_9        9     Channel 9                      */
/*                  agb1500_CH_10      10     Channel 10                     */ 
/*                                                                           */
/*         mode     Select 1 for Load correction function ON.                */
/*                  Select 0 for Load correction function OFF.               */
/*                  Data Type: ViInt32                                       */
/*                  Input/Output: IN                                         */
/*                  Values:                                                  */
/*                  Name				Value   Description                  */
/*                  agb1500_FLAG_ON     1		Load Correction ON           */
/*                  agb1500_FLAG_OFF    0       Load Correction OFF          */   
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, 0, errStatus );        
    }
    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_setLoadCorrMode" );

    /* Check Prameter Range */
    if( !((channel == agb1500_CH_CMU) || ((channel >= agb1500_CH_1) && (channel <= agb1500_CH_10)))){
		agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2);
	}
	if( channel == agb1500_CH_CMU ){
		if( (channel = agb1500_RTN_CMU_UNT) == agb1500_NO_CMU ){
			return agb1500_NO_CMU_UNT;
		}
	}

	agb1500_CHK_LONG_RANGE( mode,
				agb1500_FLAG_OFF, agb1500_FLAG_ON,
				VI_ERROR_PARAMETER3);

	/* Set CMU Load Correction Mode */
	errStatus = viPrintf(vi,"CORRST %d,3,%d\n",channel,mode);
	if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );

}/* ----- end of function ----- */
/*****************************************************************************/
ViStatus _VI_FUNC agb1500_execLoadCorr(ViSession vi, ViInt32 channel, ViReal64 freq,
									   ViInt32 mode, ViReal64 primary, ViReal64 secondary,
									   ViPInt16 result)
/*****************************************************************************/
/*                                                                           */
/*      This function executes the CMU Load correction of the specified      */
/*      frequency.                                                           */
/*                                                                           */
/*      The parameter 'channel' specifies the channel number of the CMU.     */
/*      The parameter 'freq' specifies the frequency to adjust CMU.          */
/*      The parameter 'mode' specifies the measurement mode of the CMU.      */
/*      The parameter 'primary' specifies the primary parameter for Load     */
/*      standard.                                                            */
/*      The parameter 'secondary' specifies the secondary parameter for      */
/*      load standard.                                                       */
/*      The prameter 'result' returns the numeric result from                */
/*      load correction operation.                                           */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*        channel   Channel number of the CMU.                               */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name              Value   Description                    */
/*                  agb1500_CH_CMU     -1     CMU channel                    */
/*                  agb1500_CH_1        1     Channel 1                      */
/*                  agb1500_CH_2        2     Channel 2                      */
/*                  agb1500_CH_3        3     Channel 3                      */
/*                  agb1500_CH_4        4     Channel 4                      */
/*                  agb1500_CH_5        5     Channel 5                      */
/*                  agb1500_CH_6        6     Channel 6                      */
/*                  agb1500_CH_7        7     Channel 7                      */
/*                  agb1500_CH_8        8     Channel 8                      */
/*                  agb1500_CH_9        9     Channel 9                      */
/*                  agb1500_CH_10      10     Channel 10                     */ 
/*                                                                           */
/*           freq   Measurement frequency of CMU.                            */
/*                  Data Type:  ViReal64                                     */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name                Value    Description                 */
/*                  agb1500_CMUF_MIN    1000.0                               */
/*                  agb1500_CMUF_MAX    5000000.0                            */
/*                                                                           */
/*         mode     CMU Impedance measurement mode.                          */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name					Value   Description              */
/*                  agb1500_CMUM_R_X		1       R-X Mode	    		 */
/*                  agb1500_CMUM_G_B		2       G-B Mode                 */
/*                  agb1500_CMUM_Z_TRAD		10      Z-Theta(radian) Mode     */
/*                  agb1500_CMUM_Z_TDEG		11      Z-Theta(degree) Mode     */
/*                  agb1500_CMUM_Y_TRAD		20      Y-Theta(radian) Mode     */
/*                  agb1500_CMUM_Y_TDEG		21      Y-Theta(degree) Mode     */
/*                  agb1500_CMUM_CP_G		100     Cp-G Mode                */
/*                  agb1500_CMUM_CP_D		101     Cp-D Mode                */
/*                  agb1500_CMUM_CP_Q		102     Cp-Q Mode                */
/*                  agb1500_CMUM_CP_RP		103     Cp-Rp Mode               */
/*                  agb1500_CMUM_CS_RS		200     Cs-Rs Mode               */
/*                  agb1500_CMUM_CS_D		201     Cs-D Mode                */
/*                  agb1500_CMUM_CS_Q		202		Cs-Q Mode                */
/*                  agb1500_CMUM_LP_G		300     Lp-G Mode                */
/*                  agb1500_CMUM_LP_D		301     Lp-D Mode                */
/*                  agb1500_CMUM_LP_Q		302     Lp-Q Mode                */
/*                  agb1500_CMUM_LP_RP		303     Lp-Rp Mode               */
/*                  agb1500_CMUM_LS_RS		400     Ls-Rs Mode               */
/*                  agb1500_CMUM_LS_D		401     Ls-D Mode                */
/*                  agb1500_CMUM_LS_Q		402     Ls-Q Mode                */     
/*                                                                           */
/*        primary   Primary parameter of Load standard.                      */
/*                  Data Type:  ViReal64                                     */
/*                  Input/Output:  IN                                        */
/*                                                                           */
/*      secondary   Secondary parameter of Load standard.                    */
/*                  Data Type:  ViReal64                                     */
/*                  Input/Output:  IN                                        */
/*                                                                           */
/*         result   Numeric result from CMU Load correction operation.       */
/*                  0 = Passed.                                              */
/*                  1 = Fail.                                                */
/*                  2 = Abort.                                               */
/*                  Data Type: ViPInt16                                      */
/*                  Input/Output: IN                                         */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
	ViInt32   q_time_out;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, 0, errStatus );        
    }
    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_execLoadCorr" );

    /* Check Prameter Range */
    if( !((channel == agb1500_CH_CMU) || ((channel >= agb1500_CH_1) && (channel <= agb1500_CH_10)))){
		agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2);
	}
	if( channel == agb1500_CH_CMU ){
		if( (channel = agb1500_RTN_CMU_UNT) == agb1500_NO_CMU ){
			return agb1500_NO_CMU_UNT;
		}
	}
	
	agb1500_CHK_REAL_RANGE( freq, 
                agb1500_CMUF_MIN, agb1500_CMUF_MAX, 
                VI_ERROR_PARAMETER3);

	agb1500_CHK_IMP_MEAS_MODE( mode, VI_ERROR_PARAMETER4);

	/* query timeout */
	errStatus = viGetAttribute(vi, VI_ATTR_TMO_VALUE, &q_time_out);
    if (VI_SUCCESS > errStatus)
        return statusUpdate(vi, thisPtr, errStatus);

   /* set time out -> 300 sec */
    if ((errStatus = viSetAttribute(vi, VI_ATTR_TMO_VALUE, 300000)) /* 300 sec */ 
           < VI_SUCCESS)
        return statusUpdate(vi, thisPtr, errStatus);

	/* Define CMU Open standard reference */
	errStatus = viPrintf(vi,"DCORR %d,3,%d,%e,%e\n", channel, mode, primary,secondary );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

	/* Set Frequency */
	errStatus = viPrintf(vi,"CORRL %d,%e\n", channel, freq );
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

	/* Execute  */
	errStatus = viPrintf(vi,"CORR? %d,3\n",channel);
	if( errStatus < VI_SUCCESS ){
		viSetAttribute(vi, VI_ATTR_TMO_VALUE, q_time_out);
		return statusUpdate(vi, thisPtr, errStatus);
	}

	if ((errStatus = delayScanf(vi, thisPtr->myDelay,
                                            "%hd%*t", result)) < VI_SUCCESS) {
        *result = 1;
		viSetAttribute(vi, VI_ATTR_TMO_VALUE, q_time_out);
        return statusUpdate(vi, thisPtr, errStatus);
	}


	/* set former time_out */
    if ((errStatus = viSetAttribute(vi, VI_ATTR_TMO_VALUE, q_time_out )) 
           < VI_SUCCESS)
        return statusUpdate(vi, thisPtr, errStatus);

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );

}/* ----- end of function ----- */
/*****************************************************************************/
ViStatus _VI_FUNC agb1500_clearCorrData(ViSession vi, ViInt32 channel, ViInt32 mode)
/*****************************************************************************/
/*                                                                           */
/*      This function clears the CMU correction data.                        */
/*                                                                           */
/*      The parameter 'channel' specifies the channel number of the CMU.     */
/*                                                                           */
/*      This function implements the following commands:                     */
/*      CLCORR                                                               */
/*                                                                           */
/*   Parameter      Description                                              */
/*                                                                           */
/*        channel   Channel number of the CMU.                               */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name              Value   Description                    */
/*                  agb1500_CH_CMU     -1     CMU channel                    */
/*                  agb1500_CH_1        1     Channel 1                      */
/*                  agb1500_CH_2        2     Channel 2                      */
/*                  agb1500_CH_3        3     Channel 3                      */
/*                  agb1500_CH_4        4     Channel 4                      */
/*                  agb1500_CH_5        5     Channel 5                      */
/*                  agb1500_CH_6        6     Channel 6                      */
/*                  agb1500_CH_7        7     Channel 7                      */
/*                  agb1500_CH_8        8     Channel 8                      */
/*                  agb1500_CH_9        9     Channel 9                      */
/*                  agb1500_CH_10      10     Channel 10                     */ 
/*                                                                           */
/*         mode     0:Resets frequency setting after clearing the            */
/*                    correction data.                                       */
/*                  1:Keeps the setting after clearing the correction data   */
/*                  If mode = 0, the default measurement frequencies are     */
/*                  set to the CMU. The default frequencies are 1k, 2k, 10k, */
/*                  20k, 50k, 100k, 200k, 500k, 1M, 2M, and 5MHz.            */
/*                  Data Type:  ViInt32                                      */
/*                  Input/Output:  IN                                        */
/*                  Values:                                                  */
/*                  Name                       Value   Description           */
/*                  agb1500_CMUCORR_DEFAULT      0     Default               */
/*                  agb1500_CMUCORR_CLEAR        1     Clear                 */
/*                                                                           */
/*   Return Value:                                                           */
/*       VI_SUCCESS: No error                                                */
/*   Non VI_SUCCESS: Indicates error condition. To determine error message,  */
/*                   pass the return value to routine "agb1500_error_message"*/
/*                                                                           */
/*****************************************************************************/
{
    ViStatus errStatus = 0 ;
    struct   agb1500_globals    *thisPtr;
   
    errStatus = viGetAttribute(vi, VI_ATTR_USER_DATA, (ViAddr) &thisPtr);
    if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, 0, errStatus );        
    }
    agb1500_DEBUG_CHK_THIS( vi, thisPtr );
    agb1500_CDE_INIT( "agb1500_clearCorrData" );

    /* Check Prameter Range */
    if( !((channel == agb1500_CH_CMU) || ((channel >= agb1500_CH_1) && (channel <= agb1500_CH_10)))){
		agb1500_LOG_STATUS( vi, thisPtr, VI_ERROR_PARAMETER2);
	}
	if( channel == agb1500_CH_CMU ){
		if( (channel = agb1500_RTN_CMU_UNT) == agb1500_NO_CMU ){
			return agb1500_NO_CMU_UNT;
		}
	}
	
	mode = ((mode == agb1500_CMUCORR_DEFAULT)?2:1);

	/* Clear CMU Correction data */
	errStatus = viPrintf(vi,"CLCORR %d,%d\n",channel,mode);
	if ( errStatus < VI_SUCCESS) {
        agb1500_LOG_STATUS( vi, thisPtr, errStatus );
    }

    agb1500_LOG_STATUS( vi, thisPtr, VI_SUCCESS );

}/* ----- end of function ----- */










