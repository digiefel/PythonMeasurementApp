# Instrument connection: maintainer notes

Users launch `Run Measurement App.cmd` and use the normal instrument controls.
They do not start, stop, configure, or recover a separate worker. Process and
protocol diagnostics belong in `log.txt`, not in operator error messages.

## Execution contract

- One 32-bit process owns the B1500 and its WGFMU session. Only its main thread
  calls native drivers. The input thread receives commands and cancellation;
  a watchdog bounds shutdown even after the parent disappears.
- An OS file lock excludes other app instances using the same instrument address.
  The application holds it until normal or emergency shutdown finishes.
- All instrument methods use the same call protocol. Callable arguments become
  acknowledged callbacks. The executor waits for each acknowledgement, so a
  slow consumer cannot silently lose measurement events.
- A connection permits one outstanding call. Concurrent callers serialize;
  `exclusive()` keeps multi-call configuration sequences together. Cancellation
  does not acquire this lock. Instrument calls from inside a data callback are
  rejected immediately; callbacks may raise to stop acquisition.
- A cancelled or failed operation retires the connection. No calls are retried,
  and waiting calls cannot execute on the retired connection. A subsequent
  requested run may create a new connection. Background probes cannot reconnect.
- Calls have no default elapsed-time deadline. The operator decides when a
  measurement needs to be stopped. Connection establishment has a separate
  10-second deadline. A caller may explicitly bound an operation with `_timeout_s`;
  `None` means no deadline. The streaming `timeout_s` argument follows the same
  rule. There are no method-specific timeout tables in the executor.

## Failure and shutdown

The executor always attempts session cleanup before acknowledging shutdown.
Cleanup tries abort, zero outputs, open switches, and both driver closes,
preserving errors while attempting the remaining steps. Native loader errors
retain the DLL path and original Windows exception in diagnostics.
WGFMU cleanup resets its channels and disconnects the channels it enabled before
closing its session; abort alone retains the instantaneous output voltage.

Cancellation is observed at call and callback boundaries. Arbitrary native DLL
calls cannot safely be interrupted by another driver-calling thread. Shutdown
has a one-second grace period during an active call (five seconds when idle),
after which the process is terminated.
If normal cleanup fails or is not acknowledged, the application runs a separate
32-bit emergency helper **after the old process has exited**, preventing an old
command from reapplying voltage after reset. The helper uses a fresh VISA session:
device clear, `*RST`, and `*OPC?` to check reset completion. If WGFMU was used, it
also opens that library's session and initializes its channels. Every failure is
retained, including negative VISA statuses and partial writes. Abort I/O is bounded
at two seconds per operation and the helper process at 15 seconds. These limits
apply to shutdown, never measurement duration.

Successful shutdown means the documented operations completed; it is not a voltage
measurement. Failed shutdown reports that output state could not be confirmed,
and Skip does not continue the device queue after that failure. Process termination
alone is never reported as a successful shutdown. If the application itself is
killed, its emergency helper cannot be relied on; the executor still attempts
normal cleanup and bounds its own lifetime.

B1500 acquisition and data-read methods temporarily use VISA's infinite I/O timeout,
restoring the prior communication timeout on exit. Configuration calls retain their
configured I/O timeout. Sources: B1500 Programming Guide 4-33/34, 4-184 and 2-88;
B1530A Guide 4-9, 4-21, 4-50 and the mixed SMU/WGFMU examples in chapter 3;
[Keysight VISA INSTR attributes](https://helpfiles.keysight.com/IO_Libraries_Suite/English/IOLS_Windows/VISA/Content/visa/Instrument_Control_INSTR_Resource.htm).

`bridge.py` owns transport and the remote facade. `bridge_worker.py` owns generic
dispatch and process cleanup. `protocol.py` contains shared deadlines and
exceptions. Instrument-specific operations, including bulk sample reads, live
in `sessions.py`; measurement procedures remain in the application.

## Validation

From the repository root:

```sh
python -m unittest discover -s tests -v
```

The tests use the production executor with a fake session in real subprocesses.
They cover concurrent callers, callback data and errors, cancellation, startup,
timeouts, queued calls, crashes, corrupt messages, parent EOF, hung cleanup,
configuration exclusion, connection recovery, and driver cleanup failures.
They require only Python's standard library and make no instrument calls.

Before lab use, validate on Windows with the installed 32-bit driver stack:
connect and reconnect; representative B1500 and WGFMU measurements; bulk sample
counts and values; Stop and Skip during activity; and closing the application
while idle and while measuring. Verify actual output shutdown on the instrument.
The automated macOS tests do not establish these hardware behaviors.

## First instrument checks

1. Connect and perform one short measurement. Confirm values and saved data.
2. Start a measurement that normally takes over 10 seconds; let it finish.
3. During an active B1500 measurement, click Abort. Confirm execution stops and
   outputs return to the expected disabled state. Start another measurement.
4. Repeat with WGFMU active; check the RSU/output state as well as the app.
5. Queue two devices and click Skip during the first acquisition. Confirm shutdown
   completes before the second device starts, with no stale commands or data.

If any step fails, preserve `log.txt` immediately along with the operation and what
the instrument displayed. Do not interpret the GUI becoming idle as an output check.
