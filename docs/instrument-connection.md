# Instrument connection: maintainer notes

Users launch `Run Measurement App.cmd` and use the normal instrument controls.
They do not start, stop, configure, or recover a separate worker. Process and
protocol diagnostics belong in `log.txt`, not in operator error messages.

## Execution contract

- One 32-bit process owns the B1500 and its WGFMU session. Only its main thread
  calls native drivers. The input thread receives commands and cancellation;
  a watchdog bounds shutdown even after the parent disappears.
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

Cancellation is observed at call and callback boundaries. Arbitrary native DLL
calls cannot safely be interrupted by another driver-calling thread. Shutdown
therefore has a five-second grace period, after which the process is terminated.
If cleanup was not acknowledged, the application reports that the instrument's
output state could not be confirmed. Process termination does not establish
that the instrument stopped its outputs.

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
