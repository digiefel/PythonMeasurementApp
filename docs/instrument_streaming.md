# B1500 streaming and cancellation

## Stream boundary

The installed Keysight `agb1500.c` implements automatic error detection through
`statusUpdate()`. With error detection enabled, this sends `*OPC?`, reads the
reply with `viScanf`, and polls status after each `agb1500_readData` call.
Measurement records themselves use `viRead`. Completion queries must not be
interleaved with those records.

The session adapter therefore owns this sequence:

1. `start_measure`: retain the configured setup checks. The installed driver's
   `startMeasure` checks setup before `XE`; after `XE` it polls status without a
   completion query. Then disable automatic checking before the first record.
2. `read_data`: return records through end-of-data, including trailing source and
   timestamp records. Native transport/parser failures raise; measurement status
   flags remain part of the returned data.
3. `finish_measure`: restore the previous error-checking setting after the caller
   has retained the final record. Its completion query uses the ordinary VISA
   timeout, not the indefinite acquisition-read timeout.

On error or cancellation, do not call `finish_measure` with unread records.
The failed session is closed by the worker's coordinated shutdown path.

## Cancellation ownership

The B1500 Programming Guide, edition 15, pp. 4-33–34, specifies device clear when
queued commands prevent `AB` from interrupting an operation. `AB` alone does not
necessarily remove bias. `DZ` sets outputs to zero (p. 4-79). `*OPC?` replies only
after pending operations complete (p. 4-161).

VISA separates terminating host I/O from clearing the instrument. Keysight
documents `viTerminate(session, VI_NULL, VI_NULL)` for requesting termination of
calls on that session in the current process. The cancellation thread issues only
this host-I/O request while a B1500 operation is active. It repeats the request
until the operation returns, covering cancellation immediately before native I/O
starts or between native calls within one driver function. These requests send no
instrument commands.

A lock coordinates the handoff: the worker marks the operation inactive only
after an in-flight termination request returns. No termination request can then
touch the session during cleanup. Cancellation also prevents new operations.

The worker performs `viClear`, followed by one `*OPC?`/read acknowledgement, then
closes any WGFMU session and the mainframe driver. Device clear initializes the
B1500 (Programming Guide p. 2-88); the former `AB`, `DZ`, and switch-off sequence
and the fallback's additional `*RST` are unnecessary. The same clear/confirmation
function is used by normal cleanup and the independent fallback.

The existing five-second worker shutdown budget remains. The parent no longer
shortens it to one second during an active call. If native I/O cannot be
interrupted, the existing process-termination fallback remains: it must stop the
old process before opening another session. A failure to clear or acknowledge
completion remains an error and prevents automatic queue continuation.

WGFMU native operations have an opaque session and are not passed to VISA
termination using the mainframe handle. They retain bounded process fallback if
blocked. WGFMU cleanup still initializes/disconnects its channels separately.

Shutdown logs identify resource opening, device clear, and the completion wait so
future failures can be located without attributing them to the debugger.

Sources:

- [B1500 Programming Guide](https://www.keysight.com/us/en/assets/9018-01851/programming-guides/9018-01851.pdf)
- Installed source: `C:\Program Files (x86)\IVI Foundation\VISA\WinNT\AGB1500\agb1500.c`
- [Keysight viTerminate reference](https://helpfiles.keysight.com/IO_Libraries_Suite/English/IOLS_Windows/VISA/Content/visa/viTerminate.htm)
